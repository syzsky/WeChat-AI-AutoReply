"""工作室总控：一个角色一个进程，崩溃隔离 + 自动重启 + 状态汇总。

用法：
    python apps/studio.py                        # 按 studio_config.json 拉起全部角色
    python apps/studio.py --http 8765            # 附带只读状态接口
    python apps/studio.py --only a1,a3           # 只跑指定角色

设计取舍：
- **一角色一进程**：OCR/抓图都是 CPU 密集，线程会被 GIL 拖死；进程崩了也不影响别人
- **配置生成**：模板 + 每角色覆盖，生成到 data/accounts/<name>.json，角色之间不共享文件
- **重启退避**：1 分钟内崩 5 次就停手，避免死循环刷日志
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core.metrics import read_status, write_status  # noqa: E402

DATA_DIR = os.path.join(BASE_DIR, "data")
ACCOUNTS_DIR = os.path.join(DATA_DIR, "accounts")
STUDIO_CONFIG = os.path.join(BASE_DIR, "studio_config.json")
TEMPLATE = os.path.join(BASE_DIR, "mir_config.json")
EXAMPLE = os.path.join(BASE_DIR, "games", "mir2", "config.example.json")
STUDIO_STATUS = os.path.join(DATA_DIR, "studio_status.json")


def deep_merge(base, override):
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_studio_config():
    if os.path.exists(STUDIO_CONFIG):
        with open(STUDIO_CONFIG, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    return {
        "accounts": [{"name": "a1", "overrides": {}}],
        "restart_delay": 5,
        "max_restarts_per_hour": 5,
    }


def load_template():
    path = TEMPLATE if os.path.exists(TEMPLATE) else EXAMPLE
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def build_account_config(template, account):
    cfg = deep_merge(template, account.get("overrides") or {})
    os.makedirs(ACCOUNTS_DIR, exist_ok=True)
    path = os.path.join(ACCOUNTS_DIR, f"{account['name']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return path


class Account:
    def __init__(self, spec, template, restart_delay, max_per_hour, log):
        self.name = spec["name"]
        self.spec = spec
        self.cfg_path = build_account_config(template, spec)
        self.restart_delay = restart_delay
        self.max_per_hour = max_per_hour
        self.log = log
        self.proc = None
        self.restarts = []
        self.started_at = 0.0
        self.stopped = False

    def start(self):
        if self.stopped:
            return
        cmd = [sys.executable, os.path.join(BASE_DIR, "apps", "mir_bot.py"),
               "--config", self.cfg_path, "--account", self.name]
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.proc = subprocess.Popen(cmd, cwd=BASE_DIR, creationflags=creation)
        self.started_at = time.time()
        self.log(f"[{self.name}] 启动 pid={self.proc.pid}")

    def stop(self):
        self.stopped = True
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=8)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.log(f"[{self.name}] 已停止")

    def supervise(self, now):
        """返回 True 表示需要重启（已按退避等待）。"""
        if self.stopped or self.proc is None:
            return False
        if self.proc.poll() is None:
            return False

        self.restarts = [t for t in self.restarts if now - t < 3600]
        if len(self.restarts) >= self.max_per_hour:
            self.log(f"[{self.name}] 一小时内崩溃 {len(self.restarts)} 次，停止重启")
            self.stopped = True
            return False
        if now - self.started_at < self.restart_delay:
            return False

        self.restarts.append(now)
        self.log(f"[{self.name}] 进程退出（code={self.proc.returncode}），重启第 {len(self.restarts)} 次")
        self.start()
        return True

    def status(self):
        child = read_status(os.path.join(DATA_DIR, f"status_{self.name}.json")) or {}
        return {
            "name": self.name,
            "pid": self.proc.pid if self.proc else None,
            "alive": bool(self.proc and self.proc.poll() is None),
            "restarts_1h": len(self.restarts),
            "uptime": round(time.time() - self.started_at, 1) if self.started_at else 0,
            "child": child,
        }


def make_handler(studio):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False, indent=2).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/status"):
                self._json(studio.status())
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            # 只允许本机控制：/start/<name> /stop/<name> /start_all /stop_all
            parts = [p for p in self.path.strip("/").split("/") if p]
            if not parts:
                self._json({"error": "empty"}, 400)
                return
            result = studio.control(parts[0], parts[1] if len(parts) > 1 else "")
            self._json(result, 200 if result.get("ok") else 400)

        def log_message(self, *args):
            pass

    return Handler


class Studio:
    def __init__(self, cfg, template, only=None):
        self.cfg = cfg
        self.log_lines = []
        self.accounts = []
        names = [a["name"] for a in cfg.get("accounts", [])]
        if only:
            names = [n for n in names if n in only]
        for spec in cfg.get("accounts", []):
            if spec["name"] not in names:
                continue
            self.accounts.append(Account(
                spec, template,
                float(cfg.get("restart_delay", 5)),
                int(cfg.get("max_restarts_per_hour", 5)),
                self.log,
            ))
        self.started = time.time()

    def log(self, msg):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        self.log_lines.append(line)
        self.log_lines = self.log_lines[-500:]

    def start_all(self):
        for a in self.accounts:
            a.stopped = False
            a.start()

    def stop_all(self):
        for a in self.accounts:
            a.stop()

    def control(self, action: str, name: str = "") -> dict:
        """控制入口：HTTP 与本地调用共用，返回结果字典。"""
        if action == "start_all":
            self.start_all()
            return {"ok": True, "action": "start_all"}
        if action == "stop_all":
            self.stop_all()
            return {"ok": True, "action": "stop_all"}
        if action in ("start", "stop"):
            acct = next((a for a in self.accounts if a.name == name), None)
            if not acct:
                return {"ok": False, "error": f"no such account: {name}"}
            if action == "start":
                acct.stopped = False
                acct.start()
            else:
                acct.stop()
            return {"ok": True, "account": name, "action": action}
        return {"ok": False, "error": f"bad command: {action}"}

    def status(self):
        return {
            "studio_uptime": round(time.time() - self.started, 1),
            "accounts": [a.status() for a in self.accounts],
            "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def run(self):
        self.start_all()
        try:
            while True:
                now = time.time()
                for a in self.accounts:
                    a.supervise(now)
                write_status(STUDIO_STATUS, self.status())
                if all(a.stopped for a in self.accounts):
                    self.log("所有角色已停止，总控退出")
                    break
                time.sleep(3)
        except KeyboardInterrupt:
            self.log("收到中断，停止全部角色")
        finally:
            self.stop_all()
            write_status(STUDIO_STATUS, self.status())


def main():
    ap = argparse.ArgumentParser(description="传奇工作室总控")
    ap.add_argument("--http", type=int, default=0, help="状态接口端口，0=不开")
    ap.add_argument("--only", default="", help="只跑指定角色，逗号分隔")
    args = ap.parse_args()

    if not os.path.exists(STUDIO_CONFIG):
        print(f"未找到 {STUDIO_CONFIG}，先复制 docs/studio_config.example.json 过去")
        return 2

    cfg = load_studio_config()
    studio = Studio(cfg, load_template(),
                    only=[x.strip() for x in args.only.split(",") if x.strip()])

    if args.http:
        srv = HTTPServer(("127.0.0.1", args.http), make_handler(studio))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        studio.log(f"状态接口 http://127.0.0.1:{args.http}/status")

    studio.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
