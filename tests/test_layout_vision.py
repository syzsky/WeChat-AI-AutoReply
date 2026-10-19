"""布局与图像读数单测：不需要 Windows，用合成图验证。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from core import vision  # noqa: E402
from games.mir2 import layout as lay  # noqa: E402


class TestLayout(unittest.TestCase):
    def test_default_layout_has_core_regions(self):
        l = lay.get_layout()
        for key in ("hp_bar", "mp_bar", "view", "chat", "notice"):
            self.assertIn(key, l)
            self.assertEqual(len(l[key]), 4)

    def test_override_merges(self):
        l = lay.get_layout({"hp_bar": [0.1, 0.1, 0.2, 0.2], "bogus": [1, 2, 3, 4]})
        self.assertEqual(l["hp_bar"], [0.1, 0.1, 0.2, 0.2])
        self.assertNotIn("bogus", l)

    def test_denormalize(self):
        self.assertEqual(lay.denormalize([0.5, 0.5, 1.0, 1.0], 800, 600),
                         (400, 300, 800, 600))

    def test_clamp_to_view(self):
        x, y = lay.clamp_to_view(0, 0, [0.25, 0.05, 0.95, 0.85], 1000, 1000)
        self.assertGreaterEqual(x, 250)
        self.assertGreaterEqual(y, 50)


class TestBarRatio(unittest.TestCase):
    def _img(self, filled_ratio, w=200, h=20):
        img = Image.new("RGB", (w, h), (12, 10, 8))
        fill_w = int(w * filled_ratio)
        for x in range(fill_w):
            for y in range(h):
                img.putpixel((x, y), (200, 30, 30))
        return img

    def test_full_bar(self):
        self.assertGreater(vision.bar_ratio(self._img(1.0), [0, 0, 1, 1]), 0.95)

    def test_half_bar(self):
        r = vision.bar_ratio(self._img(0.5), [0, 0, 1, 1])
        self.assertTrue(0.45 <= r <= 0.55, r)

    def test_empty_bar(self):
        self.assertLess(vision.bar_ratio(self._img(0.0), [0, 0, 1, 1]), 0.05)

    def test_region_is_dark(self):
        dark = Image.new("RGB", (50, 50), (5, 5, 5))
        bright = Image.new("RGB", (50, 50), (200, 200, 200))
        self.assertTrue(vision.region_is_dark(dark, [0, 0, 1, 1]))
        self.assertFalse(vision.region_is_dark(bright, [0, 0, 1, 1]))


class TestDiff(unittest.TestCase):
    def test_identical_frames(self):
        a = Image.new("RGB", (100, 100), (30, 30, 30))
        self.assertLess(vision.diff_ratio(a, a.copy(), [0, 0, 1, 1]), 0.001)

    def test_changed_frames(self):
        a = Image.new("RGB", (100, 100), (30, 30, 30))
        b = Image.new("RGB", (100, 100), (200, 200, 200))
        self.assertGreater(vision.diff_ratio(a, b, [0, 0, 1, 1]), 0.9)


if __name__ == "__main__":
    unittest.main()
