"""传奇挂机适配器：窗口查找 → 抓图 → 读数 → 决策 → 注入。"""
import random
import time

from core import win32api as w32
from core.llm import LLMClient
from games.base import Action, GameAdapter
from games.mir2 import layout as lay
from games.mir2.reader import MirReader
from games.mir2.state import Decider

VK_CONTROL = 0x11
VK_V = 0x56
VK_A = 0x41


class MirAdapter(GameAdapter):
    name = "mir2"

    def __init__(self, cfg: dict, log=None):
        self.cfg = cfg
        self.log = log or (lambda *a, **k: None)
        self.layout = lay.get_layout(cfg.get("layout"))
        self.reader = MirReader(self.layout, cfg, log=self.log)
        self.decider = Decider(cfg)
        self.llm = LLMClient.from_config(cfg)
        self.hwnd = None
        self.prev_img = None
        self.last_change_at = time.time()
        self.last_chat_scan = 0.0
        self.chat_history = []
        self._skill_idx = 0

    # ---------- 窗口 ----------
    def find_window(self):
        """三种绑定方式，优先级：hwnd > pid > 类名/标题关键词。"""
        # 1) 直接指定句柄（最精确，重启游戏后失效）
        pinned = self.cfg.get("window_hwnd")
        if pinned and w32.is_valid(int(pinned)):
            _, cls, title = next(
                ((h, c, t) for h, c, t in w32.list_windows() if h == int(pinned)),
                (pinned, "", ""))
            self.hwnd = int(pinned)
            self.log(f"已绑定窗口 hwnd={self.hwnd}（配置指定）class={cls} title={title}")
            return self.hwnd

        # 2) 按进程 PID（多开时最稳，重启游戏后需更新）
        pid = self.cfg.get("window_pid")
        if pid:
            hwnd, cls, title = w32.find_window_by_pid(int(pid))
            if hwnd:
                self.hwnd = hwnd
                self.log(f"已绑定窗口 hwnd={hwnd} pid={pid} class={cls} title={title}")
                return hwnd
            self.log(f"配置的 pid={pid} 没找到窗口，回退到关键词匹配")

        # 3) 按类名/标题关键词（默认，最省事）
        hwnd, cls, title = w32.find_window(
            class_keywords=self.cfg.get("window_class_keywords") or [],
            title_keywords=self.cfg.get("window_title_keywords") or ["传奇", "Mir"],
            exclude_titles=self.cfg.get("exclude_titles") or [],
        )
        self.hwnd = hwnd
        if hwnd:
            self.log(f"已绑定窗口 hwnd={hwnd} class={cls} title={title} pid={w32.pid_of(hwnd)}")
        return hwnd

    def ensure_window(self):
        if self.hwnd and w32.is_valid(self.hwnd):
            return self.hwnd
        return self.find_window()

    # ---------- 观测 ----------
    def observe(self, img):
        if self.prev_img is not None:
            from core import vision
            if vision.diff_ratio(self.prev_img, img, self.layout["view"]) > 0.002:
                self.last_change_at = time.time()
        stuck = time.time() - self.last_change_at
        obs = self.reader.read(img, self.prev_img, stuck_seconds=stuck)
        self.prev_img = img
        return obs

    # ---------- 供 Traveler 等子模块调用的基础动作 ----------
    def grab(self):
        if not self.hwnd:
            return None
        return w32.capture(self.hwnd)

    def click(self, x, y):
        if not self.hwnd:
            return False
        return w32.click_client(self.hwnd, x, y, hold_ms=int(self.cfg.get("click_hold_ms", 20)))

    def patrol(self, steps=1):
        self._patrol(steps)

    def travel_to(self, route: dict, timeout=25.0):
        from games.mir2.travel import Traveler
        return Traveler(self, self.log).travel_to(route, timeout=timeout)

    # ---------- 执行 ----------
    def execute(self, action: Action) -> bool:
        hwnd = self.hwnd
        if not hwnd:
            return False
        k = action.kind
        p = action.params

        if k == "attack":
            x, y = p.get("x"), p.get("y")
            if x is None or y is None:
                return False
            w32.click_client(hwnd, x, y, hold_ms=int(self.cfg.get("click_hold_ms", 20)))
            time.sleep(self.cfg.get("attack_interval", 0.45))
            return True

        if k == "loot":
            key = self.cfg.get("loot_key", "Z")
            w32.press_key(hwnd, key)
            time.sleep(0.25)
            return True

        if k == "potion":
            key = (self.cfg.get("hp_potion_key", "1") if p.get("slot") == "hp"
                   else self.cfg.get("mp_potion_key", "2"))
            w32.press_key(hwnd, key)
            time.sleep(0.35)
            return True

        if k == "skill":
            keys = self.cfg.get("skill_keys") or ["F1"]
            key = keys[self._skill_idx % len(keys)]
            self._skill_idx += 1
            w32.press_key(hwnd, key)
            time.sleep(0.2)
            return True

        if k == "patrol":
            self._patrol()
            return True

        if k == "unstick":
            self.log("检测到卡位，执行脱困")
            w32.press_key(hwnd, "ESC")
            time.sleep(0.2)
            self._patrol(steps=2)
            self.last_change_at = time.time()
            return True

        if k == "revive":
            key = self.cfg.get("revive_key", "")
            if key:
                w32.press_key(hwnd, key)
            else:
                w, h = w32.client_size(hwnd)
                cx, cy = lay.center_of(self.layout["notice"], w, h)
                w32.click_client(hwnd, cx, cy)
            time.sleep(2.0)
            return True

        return False

    def _patrol(self, steps=1):
        w, h = w32.client_size(self.hwnd)
        view = self.layout["view"]
        x1, y1, x2, y2 = lay.denormalize(view, w, h)
        for _ in range(steps):
            x = random.randint(x1 + 20, max(x1 + 21, x2 - 20))
            y = random.randint(y1 + 20, max(y1 + 21, y2 - 20))
            w32.click_client(self.hwnd, x, y)
            time.sleep(random.uniform(0.3, 0.7))

    # ---------- 游戏内聊天（可选，复用上游 AI 回复能力） ----------
    def maybe_reply_chat(self, img):
        if not self.cfg.get("chat_reply_enabled") or not self.llm.enabled:
            return
        now = time.time()
        if now - self.last_chat_scan < float(self.cfg.get("chat_scan_interval", 3.0)):
            return
        self.last_chat_scan = now

        from core import ocr
        lines = [t for t, _b, s in ocr.ocr_region(img, self.layout["chat"], 0.45)]
        if not lines:
            return
        tail = lines[-1]
        prefix = self.cfg.get("chat_trigger_prefix", "")
        if prefix and prefix not in tail:
            return

        question = tail.split(prefix, 1)[-1].strip() if prefix else tail.strip()
        if len(question) < 2:
            return
        reply = self.llm.chat(question, self.chat_history)
        if not reply:
            return
        self.chat_history.append({"role": "user", "content": question})
        self.chat_history.append({"role": "assistant", "content": reply})
        self.send_text(reply)

    def send_text(self, text: str):
        """激活窗口 → 剪贴板粘贴 → 回车。仅在需要聊天时短暂抢焦点。"""
        try:
            import pyperclip
            pyperclip.copy(text)
        except Exception:
            return
        if not w32.activate(self.hwnd):
            self.log("聊天回复失败：窗口无法激活", )
            return
        w32.key_down(self.hwnd, "ENTER")
        w32.key_up(self.hwnd, "ENTER")
        time.sleep(0.15)
        try:
            w32.user32.keybd_event(VK_CONTROL, 0, 0, 0)
            w32.user32.keybd_event(VK_V, 0, 0, 0)
            time.sleep(0.05)
            w32.user32.keybd_event(VK_V, 0, 2, 0)
            w32.user32.keybd_event(VK_CONTROL, 0, 2, 0)
        except Exception:
            pass
        time.sleep(0.2)
        w32.key_down(self.hwnd, "ENTER")
        w32.key_up(self.hwnd, "ENTER")
