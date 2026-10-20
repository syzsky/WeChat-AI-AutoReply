"""列出所有可见窗口，用来确定游戏窗口的类名/标题/PID。

用法：
    python tools\\window_list.py                # 全部
    python tools\\window_list.py --filter 传奇   # 只看标题含关键词的
    python tools\\window_list.py --json          # 机器可读

拿到结果后，三选一写进 mir_config.json：
    "window_hwnd": 123456          # 最精确，重启游戏失效
    "window_pid": 4321             # 多开时最稳，重启游戏失效
    "window_title_keywords": ["传奇"]  # 最省事，长期有效
"""
import argparse
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core import win32api as w32  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--filter", default="", help="标题或类名包含该字符串才显示")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not w32.IS_WINDOWS:
        print("只能在 Windows 上枚举窗口")
        return 2

    rows = []
    for hwnd, cls, title in w32.list_windows():
        if args.filter and args.filter not in title and args.filter not in cls:
            continue
        try:
            cw, ch = w32.client_size(hwnd)
        except Exception:
            cw = ch = 0
        pid = w32.pid_of(hwnd)
        rows.append({
            "hwnd": hwnd, "pid": pid, "class": cls, "title": title,
            "client": f"{cw}x{ch}", "process": w32.process_name(pid),
        })

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    if not rows:
        print("没有匹配的窗口（游戏可能没启动，或标题/类名不含该关键词）")
        return 1

    print(f"{'hwnd':>10}  {'pid':>6}  {'client':>11}  {'process':<18}  class / title")
    print("-" * 100)
    for r in sorted(rows, key=lambda x: x["hwnd"]):
        print(f"{r['hwnd']:>10}  {r['pid']:>6}  {r['client']:>11}  "
              f"{r['process'][:18]:<18}  {r['class']} | {r['title']}")
    print("\n把游戏那一行的 hwnd / pid / 标题关键词填进 mir_config.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
