"""NPC 传送选项匹配单测（纯逻辑）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from games.mir2.travel import build_keywords, pick_option  # noqa: E402


def texts(*pairs):
    return [(t, (0, 0, 100, 20), 0.9) for t in pairs]


class TestBuildKeywords(unittest.TestCase):
    def test_target_map_first(self):
        kws = build_keywords(["比奇省", "比奇城"], "比奇城")
        self.assertEqual(kws[0], "比奇城")

    def test_generic_confirm_last(self):
        kws = build_keywords([], "")
        self.assertIn("传送", kws)
        self.assertIn("确定", kws)

    def test_no_empty_keywords(self):
        self.assertNotIn("", build_keywords([""], ""))


class TestPickOption(unittest.TestCase):
    def test_picks_target_map(self):
        t, _ = pick_option(texts("欢迎光临", "比奇城", "盟重省"), ["比奇城", "盟重省"])
        self.assertEqual(t, "比奇城")

    def test_priority_beats_list_order(self):
        # 目标地图优先，即使列表里别的词先出现
        t, _ = pick_option(texts("前往盟重省", "比奇城"), build_keywords(["盟重省"], "比奇城"))
        self.assertEqual(t, "比奇城")

    def test_falls_back_to_generic(self):
        t, _ = pick_option(texts("老张：要点什么", "传送"), build_keywords([], ""))
        self.assertEqual(t, "传送")

    def test_no_match(self):
        t, box = pick_option(texts("你好", "再见"), ["比奇城"])
        self.assertIsNone(t)
        self.assertIsNone(box)

    def test_substring_match(self):
        t, _ = pick_option(texts("【传送】比奇城（安全区）"), ["比奇城"])
        self.assertEqual(t, "【传送】比奇城（安全区）")


if __name__ == "__main__":
    unittest.main()
