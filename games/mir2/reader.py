"""传奇画面读数：血/蓝条比例、死亡检测、怪物与掉落物识别。"""
from core import ocr, vision
from games.base import Observation
from games.mir2 import layout as lay


class MirReader:
    def __init__(self, layout: dict, cfg: dict, log=None):
        self.layout = layout
        self.cfg = cfg
        self.log = log or (lambda *a, **k: None)

    def read(self, img, prev_img=None, stuck_seconds=0.0) -> Observation:
        if img is None:
            return Observation(hp=0.0, dead=True, screen_changed=False,
                               stuck_seconds=stuck_seconds)

        hp = vision.bar_ratio(img, self.layout["hp_bar"])
        mp = vision.bar_ratio(img, self.layout["mp_bar"])

        # 条状读数偶尔会被半透明特效干扰，用数字 OCR 兜底校正
        if self.cfg.get("ocr_hp_fallback", True) and hp <= 0.02:
            hp = self._hp_from_text(img)

        dead = self._is_dead(img, hp)
        monsters = self._find_monsters(img)
        items = self._find_items(img)

        changed = True
        if prev_img is not None:
            changed = vision.diff_ratio(prev_img, img, self.layout["view"]) > 0.002

        return Observation(hp=hp, mp=mp, dead=dead, monsters=monsters,
                           items=items, screen_changed=changed,
                           stuck_seconds=stuck_seconds)

    # ---------- 内部 ----------
    def _hp_from_text(self, img):
        num = ocr.read_number(img, self.layout["hp_text"])
        max_hp = int(self.cfg.get("max_hp", 0) or 0)
        if num and max_hp > 0:
            return max(0.0, min(1.0, num / float(max_hp)))
        return 0.0

    def _is_dead(self, img, hp):
        if hp > 0.02:
            return False
        # 血条见底 + 画面整体偏暗 / 中央出现死亡提示，判定死亡
        if vision.region_is_dark(img, self.layout["notice"], threshold=50):
            return True
        hits = ocr.find_text(img, self.layout["notice"],
                             ["死亡", "复活", "你已", "重新开始"], min_score=0.45)
        return bool(hits)

    def _find_monsters(self, img):
        names = self.cfg.get("monster_names") or []
        if not names:
            return []
        hits = ocr.find_text(img, self.layout["view"], names, min_score=0.45)
        w, h = img.size
        out = []
        for text, cx, cy, score in hits:
            cx, cy = lay.clamp_to_view(cx, cy, self.layout["view"], w, h)
            out.append({"name": text, "x": cx, "y": cy, "score": score})
        out.sort(key=lambda m: (m["x"] - w / 2) ** 2 + (m["y"] - h / 2) ** 2)
        return out

    def _find_items(self, img):
        names = self.cfg.get("item_names") or []
        if not names:
            return []
        hits = ocr.find_text(img, self.layout["view"], names, min_score=0.45)
        w, h = img.size
        out = []
        for text, cx, cy, score in hits:
            cx, cy = lay.clamp_to_view(cx, cy, self.layout["view"], w, h)
            out.append({"name": text, "x": cx, "y": cy, "score": score})
        return out
