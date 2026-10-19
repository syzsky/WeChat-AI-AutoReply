"""传奇挂机守护进程（无界面）。

用法：
    python -m apps.mir_bot --config mir_config.json
    python -m apps.mir_bot --once          # 只跑一帧，用于调试布局/读数
    python -m apps.mir_bot --dry-run       # 只观测不操作
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import win32api as w32  # noqa: E402
from core.config import Config  # noqa: E402
from core.logger import Logger  # noqa: E402
from games.mir2.adapter import MirAdapter  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG = os.path.join(BASE_DIR, "games", "mir2", "config.example.json")
LOG_PATH = os.path.join(BASE_DIR, "logs", "mir_bot.log")
STOP_FILE = os.path.join(BASE_DIR, "mir_bot.stop")


def parse_args():
    p = argparse.ArgumentParser(description="传奇挂机守护")
    p.add_argument("--config", default=os.path.join(BASE_DIR, "mir_config.json"))
    p.add_argument("--once", action="store_true", help="只跑一帧")
    p.add_argument("--dry-run", action="store_true", help="只观测不注入")
    p.add_argument("--seconds", type=float, default=0, help="运行时长，0=一直跑")
    return p.parse_args()


def main():
    args = parse_args()
    log = Logger(LOG_PATH)

    cfg_path = args.config if os.path.exists(args.config) else DEFAULT_CONFIG
    if cfg_path == DEFAULT_CONFIG:
        log.warn(f"未找到 {args.config}，使用示例配置（只读，不会写回）")
    cfg = Config(cfg_path, _defaults())
    data = cfg.data

    adapter = MirAdapter(data, log=log)
    if not w32.IS_WINDOWS:
        log.error("当前不是 Windows，无法挂机")
        return 2
    if not adapter.find_window():
        log.error("没找到游戏窗口，请先启动游戏；必要时在配置里填 window_title_keywords")
        return 3

    log(f"开始挂机 game={data.get('game')} interval={data.get('loop_interval')}s")
    started = time.time()
    last_stats = started
    frames = 0

    try:
        while True:
            if os.path.exists(STOP_FILE):
                os.remove(STOP_FILE)
                log("收到停止信号，退出")
                break
            if args.seconds and time.time() - started > args.seconds:
                break

            hwnd = adapter.ensure_window()
            if not hwnd:
                log.warn("窗口丢失，3 秒后重试")
                time.sleep(3)
                continue

            img = w32.capture(hwnd)
            if img is None:
                log.warn("抓图失败（游戏可能最小化或用独占全屏），1 秒后重试")
                time.sleep(1)
                continue

            obs = adapter.observe(img)
            action = adapter.decider.decide(obs)
            adapter.maybe_reply_chat(img)

            if not args.dry_run:
                adapter.execute(action)
                adapter.decider.mark_action()
            else:
                log(f"[dry-run] {obs} -> {action}")

            frames += 1
            if args.once:
                log(f"单帧结果：{obs} -> {action}")
                break

            if time.time() - last_stats > 30:
                c = adapter.decider.counters
                log(f"状态={adapter.decider.state} 帧={frames} "
                    f"击杀={c['kills']} 拾取={c['loots']} 喝药={c['potions']} 死亡={c['deaths']}")
                last_stats = time.time()

            cfg.reload()
            time.sleep(float(cfg.get("loop_interval", 0.35)))
    except KeyboardInterrupt:
        log("手动中断")
    return 0


def _defaults():
    import json
    with open(DEFAULT_CONFIG, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    sys.exit(main())
