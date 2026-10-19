"""抓一张游戏窗口截图并画出网格，用来量归一化坐标。

用法：
    python tools/snapshot.py                 # 自动找窗口
    python tools/snapshot.py --title 传奇     # 指定标题关键词
输出：logs/snapshot.png（带 10% 网格 + 像素坐标标注）
"""
import argparse
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from PIL import ImageDraw  # noqa: E402

from core import win32api as w32  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", default="", help="标题关键词")
    ap.add_argument("--out", default=os.path.join(BASE_DIR, "logs", "snapshot.png"))
    args = ap.parse_args()

    if not w32.IS_WINDOWS:
        print("只能在 Windows 上抓窗口")
        return 2

    kws = [args.title] if args.title else ["传奇", "Mir", "Legend"]
    hwnd, cls, title = w32.find_window(title_keywords=kws)
    if not hwnd:
        print(f"没找到窗口，关键词={kws}")
        return 3

    img = w32.capture(hwnd)
    if img is None:
        print("抓图失败：请确认游戏是窗口化模式")
        return 4

    w, h = img.size
    draw = ImageDraw.Draw(img)
    for i in range(1, 10):
        x, y = int(w * i / 10), int(h * i / 10)
        draw.line([(x, 0), (x, h)], fill=(255, 0, 0), width=1)
        draw.line([(0, y), (w, y)], fill=(255, 0, 0), width=1)
        draw.text((x + 3, 3), f"{i/10:.1f}", fill=(255, 255, 0))
        draw.text((3, y + 2), f"{i/10:.1f}", fill=(255, 255, 0))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    img.save(args.out)
    print(f"窗口: hwnd={hwnd} class={cls} title={title} size={w}x{h}")
    print(f"已保存: {args.out}")
    print("把量到的区域按 [x1,y1,x2,y2] 归一化填进 mir_config.json 的 layout 里")
    return 0


if __name__ == "__main__":
    sys.exit(main())
