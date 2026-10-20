"""NPC 传送：找 NPC → 点开对话 → 认选项 → 点进目标地图 → 校验到达。

传奇的传送没有可读协议，只能走 UI：
    视野里找 NPC 名字 → 点它 → 等对话窗 → OCR 选项列表 → 点含目标关键字的选项
一次点击可能只是打开二级菜单（比如"传送员"→"比奇省"→"比奇城"），
所以按 options 列表顺序逐级点击，直到出现到达标志。
"""
import time

from core import ocr, vision
from games.mir2 import layout as lay


def build_keywords(options, target_map):
    """选项匹配关键词，按优先级排列：目标地图 > 配置选项 > 通用确认词。"""
    kws = [k for k in ([target_map] if target_map else []) + list(options or []) if k]
    kws += ["传送", "进入", "确定", "确认", "前往"]
    return kws


def pick_option(texts, keywords):
    """从 OCR 结果里挑第一个命中的选项，返回 (text, box) 或 (None, None)。

    texts: [(text, box, score), ...]，box=(x1,y1,x2,y2)
    """
    for kw in keywords:
        if not kw:
            continue
        for text, box, _score in texts:
            if kw in text:
                return text, box
    return None, None


class Traveler:
    def __init__(self, adapter, log=None):
        self.adapter = adapter
        self.cfg = adapter.cfg
        self.layout = adapter.layout
        self.log = log or adapter.log

    # ---------- 对外入口 ----------
    def travel_to(self, route: dict, timeout=25.0) -> bool:
        """route = {"npc": "传送员", "options": ["比奇省", "比奇城"], "map": "比奇城"}"""
        npc_name = route.get("npc", "")
        options = route.get("options") or []
        target_map = route.get("map") or (options[-1] if options else "")
        deadline = time.time() + timeout

        self.log(f"开始传送：NPC={npc_name} 目标={target_map}")
        while time.time() < deadline:
            img = self.adapter.grab()
            if img is None:
                time.sleep(0.5)
                continue

            # 1) 已经到达
            if target_map and self.current_map(img) == target_map:
                self.log(f"已到达 {target_map}")
                return True

            # 2) 对话窗里点选项
            if self._click_dialog_option(img, options, target_map):
                time.sleep(0.8)
                continue

            # 3) 找 NPC 并点开
            hit = self._find_npc(img, npc_name)
            if hit:
                _, x, y, _ = hit
                self.log(f"点击 NPC {npc_name} @({x},{y})")
                self.adapter.click(x, y)
                time.sleep(0.9)
                continue

            # 4) 视野里没有 NPC：走两步换视角再找
            self.adapter.patrol(steps=1)
            time.sleep(0.6)

        self.log(f"传送超时：没能在 {timeout:.0f}s 内到达 {target_map}")
        return False

    # ---------- 内部 ----------
    def current_map(self, img) -> str:
        """读当前地图名（小地图上方那行字）。"""
        rect = self.layout.get("map_name") or [0.855, 0.185, 0.995, 0.235]
        try:
            texts = ocr.ocr_region(img, rect, min_score=0.4)
        except Exception:
            return ""
        return texts[0][0] if texts else ""

    def _find_npc(self, img, npc_name):
        if not npc_name:
            return None
        try:
            hits = ocr.find_text(img, self.layout["view"], [npc_name], min_score=0.45)
        except Exception:
            return None
        if not hits:
            return None
        # 取离屏幕中心最近的
        w, h = img.size
        hits.sort(key=lambda t: (t[1] - w / 2) ** 2 + (t[2] - h / 2) ** 2)
        text, cx, cy, score = hits[0]
        cx, cy = lay.clamp_to_view(cx, cy, self.layout["view"], w, h)
        return text, cx, cy, score

    def _click_dialog_option(self, img, options, target_map) -> bool:
        """在对话框里找选项并点击；点到了返回 True。"""
        rect = self.layout.get("dialog") or [0.30, 0.25, 0.72, 0.80]
        try:
            texts = ocr.ocr_region(img, rect, min_score=0.4)
        except Exception:
            return False
        if not texts:
            return False

        keywords = build_keywords(options, target_map)
        text, box = pick_option(texts, keywords)
        if text is None:
            return False
        cx = int((box[0] + box[2]) / 2)
        cy = int((box[1] + box[3]) / 2)
        self.log(f"对话选项命中「{text}」→ 点击({cx},{cy})")
        self.adapter.click(cx, cy)
        return True

    # ---------- 工具 ----------
    def wait_dialog(self, timeout=3.0) -> bool:
        """等对话框出现（画面在 dialog 区域有明显变化）。"""
        deadline = time.time() + timeout
        prev = None
        while time.time() < deadline:
            img = self.adapter.grab()
            if img is None:
                time.sleep(0.2)
                continue
            if prev is not None:
                rect = self.layout.get("dialog") or [0.30, 0.25, 0.72, 0.80]
                if vision.diff_ratio(prev, img, rect) > 0.01:
                    return True
            prev = img
            time.sleep(0.2)
        return False
