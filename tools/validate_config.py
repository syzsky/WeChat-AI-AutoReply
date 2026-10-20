"""配置体检：在开挂之前把明显的坑挑出来，省得跑起来才发现。

用法：
    python tools/validate_config.py                      # 检查 mir_config.json
    python tools/validate_config.py --config data/accounts/a1.json
"""
import argparse
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core import schedule  # noqa: E402
from games.mir2 import layout as lay  # noqa: E402

ERROR, WARN = "ERROR", "WARN"


def check_rect(name, rect, errors, warns):
    if not isinstance(rect, (list, tuple)) or len(rect) != 4:
        errors.append(f"layout.{name} 必须是 4 个数字")
        return
    try:
        x1, y1, x2, y2 = [float(v) for v in rect]
    except (TypeError, ValueError):
        errors.append(f"layout.{name} 含非数字")
        return
    if not all(0.0 <= v <= 1.0 for v in (x1, y1, x2, y2)):
        warns.append(f"layout.{name} 超出 0~1 范围（应为归一化坐标）")
    if x2 <= x1 or y2 <= y1:
        errors.append(f"layout.{name} 右下角必须大于左上角")


def validate(cfg: dict):
    errors, warns = [], []

    # 窗口绑定
    if not cfg.get("window_title_keywords") and not cfg.get("window_class_keywords") \
            and not cfg.get("window_hwnd") and not cfg.get("window_pid"):
        errors.append("窗口绑定为空：至少要填 window_title_keywords 或 hwnd/pid")

    # 阈值
    for key in ("potion_hp_threshold", "potion_mp_threshold"):
        v = cfg.get(key)
        if v is not None and not (0.0 <= float(v) <= 1.0):
            errors.append(f"{key}={v} 必须在 0~1 之间")

    # 布局
    layout = lay.get_layout(cfg.get("layout"))
    for name, rect in layout.items():
        check_rect(name, rect, errors, warns)

    # 路线
    for key in ("travel_route", "grind_route", "resupply_route"):
        route = cfg.get(key) or {}
        if route and not route.get("npc"):
            errors.append(f"{key} 缺 npc 字段")

    # 时段
    sched = cfg.get("schedule") or {}
    if sched.get("enabled"):
        for w in sched.get("windows") or []:
            if not schedule.parse_window(w):
                errors.append(f"schedule.windows 格式错误：{w!r}（应为 08:00-12:00）")
        if not sched.get("windows"):
            warns.append("schedule.enabled=true 但没写 windows，等于全天挂机")

    # 补给
    if cfg.get("potion_count_enabled") and cfg.get("potion_low_threshold") is None:
        warns.append("开了药水计数但没设 potion_low_threshold，不会触发补给")

    # 重登
    if cfg.get("account_name") and not cfg.get("account_password"):
        warns.append("配了 account_name 但没 account_password，重登会失败")

    return errors, warns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(BASE_DIR, "mir_config.json"))
    args = ap.parse_args()

    path = args.config
    if not os.path.exists(path):
        example = os.path.join(BASE_DIR, "games", "mir2", "config.example.json")
        print(f"{path} 不存在，改为检查示例配置 {example}")
        path = example

    with open(path, "r", encoding="utf-8-sig") as f:
        cfg = json.load(f)

    errors, warns = validate(cfg)
    for e in errors:
        print(f"[ERROR] {e}")
    for w in warns:
        print(f"[WARN ] {w}")
    if not errors and not warns:
        print("配置没问题")
    elif not errors:
        print(f"\n没有致命错误，{len(warns)} 条提醒")
    else:
        print(f"\n{len(errors)} 个错误必须先修")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
