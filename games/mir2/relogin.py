"""掉线重登：走登录器 UI，不碰协议。

流程（每一步都可配）：
    1. 找登录窗口（标题关键词）
    2. OCR 找"账号"/"密码"标签，点它右边的输入框
    3. 剪贴板粘贴账号，Tab 到密码框，粘贴密码
    4. OCR 找"登录"/"进入游戏"按钮，点它
    5. 等游戏窗口出现

登录器千差万别，这里只保证"能按坐标+文字驱动"，坐标靠配置校准。
"""
import time

from core import ocr, win32api as w32


class ReloginFlow:
    def __init__(self, cfg: dict, log=None):
        self.cfg = cfg
        self.log = log or (lambda *a, **k: None)
        self.login_titles = cfg.get("login_window_keywords") or ["登录", "Login", "登陆"]
        self.account = str(cfg.get("account_name", ""))
        self.password = str(cfg.get("account_password", ""))
        self.account_label = cfg.get("account_label", "账号")
        self.password_label = cfg.get("password_label", "密码")
        self.submit_words = cfg.get("login_button_words") or ["登录", "进入游戏", "开始游戏"]
        self.field_offset = int(cfg.get("login_field_offset", 120))

    # ---------- 主流程 ----------
    def run(self, timeout=60.0) -> bool:
        if not self.account:
            self.log("未配置 account_name，无法自动重登")
            return False

        deadline = time.time() + timeout
        while time.time() < deadline:
            hwnd, cls, title = w32.find_window(title_keywords=self.login_titles)
            if not hwnd:
                self.log("未找到登录窗口，等待...")
                time.sleep(2)
                continue

            self.log(f"找到登录窗口 hwnd={hwnd} title={title}")
            img = w32.capture(hwnd)
            if img is None:
                time.sleep(1)
                continue

            if self._fill_account(hwnd, img) and self._fill_password(hwnd, img):
                if self._submit(hwnd, img):
                    if self._wait_game_window(deadline):
                        self.log("重登成功，游戏窗口已出现")
                        return True
            time.sleep(2)

        self.log("重登超时")
        return False

    # ---------- 步骤 ----------
    def _find_field(self, img, label):
        hits = ocr.find_text(img, self.cfg.get("login_panel", [0.2, 0.2, 0.8, 0.8]),
                             [label], min_score=0.45)
        if not hits:
            return None
        _text, x, y, _score = hits[0]
        return x + self.field_offset, y

    def _fill_account(self, hwnd, img):
        pos = self._find_field(img, self.account_label)
        if not pos:
            self.log(f"没找到「{self.account_label}」标签")
            return False
        w32.click_client(hwnd, *pos)
        time.sleep(0.2)
        self._paste(hwnd, self.account)
        return True

    def _fill_password(self, hwnd, img):
        pos = self._find_field(img, self.password_label)
        if pos:
            w32.click_client(hwnd, *pos)
            time.sleep(0.2)
        else:
            # 找不到标签就按 Tab 从账号框切过去
            w32.press_key(hwnd, "TAB")
            time.sleep(0.15)
        self._paste(hwnd, self.password)
        return True

    def _submit(self, hwnd, img):
        panel = self.cfg.get("login_panel", [0.2, 0.2, 0.8, 0.8])
        hits = ocr.find_text(img, panel, self.submit_words, min_score=0.45)
        if hits:
            _t, x, y, _s = hits[0]
            self.log(f"点击登录按钮 ({x},{y})")
            w32.click_client(hwnd, x, y)
        else:
            self.log("没找到登录按钮，按回车提交")
            w32.press_key(hwnd, "ENTER")
        return True

    def _wait_game_window(self, deadline):
        while time.time() < deadline:
            time.sleep(2)
            hwnd, _cls, _title = w32.find_window(
                title_keywords=self.cfg.get("window_title_keywords") or ["传奇", "Mir"])
            if hwnd:
                return True
        return False

    def _paste(self, hwnd, text):
        try:
            import pyperclip
            pyperclip.copy(text)
        except Exception:
            self.log("剪贴板不可用，改用逐字输入")
            for ch in text:
                w32.press_key(hwnd, ch)
                time.sleep(0.03)
            return
        # Ctrl+A 清空 → Ctrl+V 粘贴
        for vk in (0x11, 0x41):
            w32.user32.keybd_event(vk, 0, 0, 0)
        for vk in (0x41, 0x11):
            w32.user32.keybd_event(vk, 0, 2, 0)
        time.sleep(0.05)
        for vk in (0x11, 0x56):
            w32.user32.keybd_event(vk, 0, 0, 0)
        for vk in (0x56, 0x11):
            w32.user32.keybd_event(vk, 0, 2, 0)
        time.sleep(0.15)
