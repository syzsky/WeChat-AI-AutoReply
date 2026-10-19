"""图像工具：归一化裁剪、进度条读数、色块检测、画面差分。

坐标约定：所有区域用 0~1 的归一化 (x1, y1, x2, y2)，与实际分辨率无关，
换窗口大小 / 换 DPI 都不用改配置。
"""
import numpy as np
from PIL import Image


def crop_norm(img: Image.Image, rect) -> Image.Image:
    """按归一化矩形裁剪。"""
    w, h = img.size
    x1, y1, x2, y2 = rect
    box = (int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h))
    box = (max(0, box[0]), max(0, box[1]), min(w, box[2]), min(h, box[3]))
    if box[2] <= box[0] or box[3] <= box[1]:
        return Image.new("RGB", (1, 1))
    return img.crop(box)


def to_np(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGB"), dtype=np.uint8)


def bar_ratio(img: Image.Image, rect, sample_y=0.5, min_saturation=0.25,
              bg_max_gray=60, step=1):
    """读血/蓝/经验条填充比例。

    做法：在条内取一行像素，从左往右数“明显非背景色”的像素，
    直到遇到背景（暗色/近灰）为止，返回 已填充宽度 / 总宽度。
    比 OCR 快一个数量级，也不怕数字被遮挡。
    """
    crop = crop_norm(img, rect)
    if crop.size[0] < 4 or crop.size[1] < 2:
        return 0.0
    arr = to_np(crop)
    row = arr[int(arr.shape[0] * sample_y)]
    total = len(row)
    filled = 0
    for i in range(0, total, step):
        r, g, b = row[i]
        mx, mn = int(max(r, g, b)), int(min(r, g, b))
        gray = (int(r) + int(g) + int(b)) / 3.0
        sat = (mx - mn) / mx if mx else 0.0
        if gray <= bg_max_gray and sat < min_saturation:
            break
        if sat >= min_saturation and mx >= 90:
            filled = i + 1
    return round(filled / float(total), 3) if total else 0.0


def diff_ratio(a: Image.Image, b: Image.Image, rect=None, threshold=18) -> float:
    """两帧在指定区域的差异像素占比，用于判断“画面有没有变化”。"""
    if a is None or b is None:
        return 1.0
    if rect:
        a, b = crop_norm(a, rect), crop_norm(b, rect)
    if a.size != b.size:
        b = b.resize(a.size)
    x = to_np(a).astype(np.int16)
    y = to_np(b).astype(np.int16)
    d = np.abs(x - y).max(axis=2)
    return float((d > threshold).mean())


def find_color_blobs(img: Image.Image, rect, target_rgb, tolerance=28,
                     min_pixels=12, max_blobs=8):
    """在区域内找指定颜色（或近似色）的连通块，返回中心点（客户区像素坐标）。

    用于找怪名、掉落物高亮、地图标记等。
    """
    crop = crop_norm(img, rect)
    arr = to_np(crop).astype(np.int16)
    tr, tg, tb = target_rgb
    mask = ((np.abs(arr[:, :, 0] - tr) <= tolerance) &
            (np.abs(arr[:, :, 1] - tg) <= tolerance) &
            (np.abs(arr[:, :, 2] - tb) <= tolerance))
    if mask.sum() < min_pixels:
        return []

    # 简易连通域：按行列投影分块，避免引入 scipy/opencv
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return []
    w, h = img.size
    x1, y1 = int(rect[0] * w), int(rect[1] * h)
    bw = max(8, int(0.06 * w))
    bh = max(8, int(0.06 * h))

    buckets = {}
    for x, y in zip(xs, ys):
        buckets.setdefault((x // bw, y // bh), []).append((x, y))

    blobs = []
    for _, pts in buckets.items():
        if len(pts) < min_pixels:
            continue
        cx = int(np.mean([p[0] for p in pts])) + x1
        cy = int(np.mean([p[1] for p in pts])) + y1
        blobs.append((len(pts), cx, cy))
    blobs.sort(reverse=True)
    return [(cx, cy) for _, cx, cy in blobs[:max_blobs]]


def region_is_dark(img: Image.Image, rect, threshold=45) -> bool:
    """判断区域是否整体偏暗（死亡黑屏、过图黑屏）。"""
    arr = to_np(crop_norm(img, rect))
    return float(arr.mean()) < threshold
