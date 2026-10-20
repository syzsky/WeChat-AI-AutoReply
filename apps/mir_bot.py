"""单角色挂机进程（工作室由 apps/studio.py 拉起多个本进程）。

用法：
    python -m apps.mir_bot --config mir_config.json --account a1
    python -m apps.mir_bot --once          # 只跑一帧，用于调试布局/读数
    python -m apps.mir_bot --dry-run       # 只观测不操作
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import win32api as w32  # noqa: E402
from core.config import Config  # noqa: E402
from core.human import Humanizer  # noqa: E402
from core.logger import Logger  # noqa: E402
from core.metrics import Metrics, write_status  # noqa: E402
from games.mir2.adapter import MirAdapter  # noqa: E402
from games.mir2.worker import StudioWorker  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG = os.path.join(BASE_DIR, "games", "mir2", "config.example.json")
STOP_FILE = os.path.join(BASE_DIR, "mir_bot.stop")


def parse_args():
    p = argparse.ArgumentParser(description="传奇挂机守护（单角色）")
    p.add_argument("--config", default=os.path.join(BASE_DIR, "mir_config.json"))
    p.add_argument("--account", default="default", help="角色标识，用于日志/指标/状态隔离")
    p.add_argument("--once", action="store_true", help="只跑一帧")
    p.add_argument("--dry-run", action="store_true", help="只观测不注入")
    p.add_argument("--seconds", type=float, default=0, help="运行时长，0=一直跑")
    return p.parse_args()


def main():
    args = parse_args()
    acct = args.account
    log = Logger(os.path.join(BASE_DIR, "logs", f"{acct}.log"))

    cfg_path = args.config if os.path.exists(args.config) else DEFAULT_CONFIG
    if cfg_path == DEFAULT_CONFIG:
        log.warn(f"未找到 {args.config}，使用示例配置（只读，不会写回）")
    cfg = Config(cfg_path, _defaults())

    if not w32.IS_WINDOWS:
        log.error("当前不是 Windows，无法挂机")
        return 2

    adapter = MirAdapter(cfg.data, log=log)
    if not adapter.find_window():
        log.error("没找到游戏窗口，先跑 tools/window_list.py 确认标题/类名")
        return 3

    metrics = Metrics(os.path.join(BASE_DIR, "data", "metrics.db"), acct)
    human = Humanizer(cfg.data)
    worker = StudioWorker(adapter, cfg.data, human=human, metrics=metrics, log=log)
    status_path = os.path.join(BASE_DIR, "data", f"status_{acct}.json")

    log(f"开始挂机 account={acct} interval={cfg.get('loop_interval')}s")

    # 启动时先按配置传送到挂机地图（可选）
    route = cfg.get("travel_route") or {}
    if route.get("npc") and not args.dry_run:
        ok = adapter.travel_to(route, timeout=float(cfg.get("travel_timeout", 25)))
        log(f"传送{'成功' if ok else '失败'}：{route.get('map') or route.get('options')}")

    started = time.time()
    last_status = 0.0
    frames = 0

    try:
        while True:
            if os.path.exists(STOP_FILE):
                try:
                    os.remove(STOP_FILE)
                except OSError:
                    pass
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
                log.warn("抓图失败（最小化/独占全屏？），1 秒后重试")
                time.sleep(1)
                continue

            obs, action = worker.step(img)

            if action is not None and not args.dry_run:
                adapter.execute(action)
                adapter.decider.mark_action()
                adapter.maybe_reply_chat(img)
            elif action is not None:
                log(f"[dry-run] {obs} -> {action}")

            frames += 1
            if args.once:
                log(f"单帧：{obs} -> {action}")
                break

            if time.time() - last_status > 10:
                snap = {
                    "account": acct, "pid": os.getpid(),
                    "state": adapter.decider.state, "task": worker.state.task,
                    "uptime": round(time.time() - started, 1), "frames": frames,
                    "counters": adapter.decider.counters,
                    "hp": round(obs.hp, 2) if obs else None,
                    "mp": round(obs.mp, 2) if obs else None,
                    "last_update": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                write_status(status_path, snap)
                metrics.snapshot(snap)
                last_status = time.time()

            cfg.reload()
            interval = float(cfg.get("loop_interval", 0.35))
            time.sleep(human.delay(interval))
    except KeyboardInterrupt:
        log("手动中断")
    finally:
        write_status(status_path, {"account": acct, "state": "stopped",
                                   "pid": os.getpid(),
                                   "last_update": time.strftime("%Y-%m-%d %H:%M:%S")})
        metrics.close()
    return 0


def _defaults():
    with open(DEFAULT_CONFIG, "r", encoding="utf-8-sig") as f:
        return json.load(f)


if __name__ == "__main__":
    sys.exit(main())
