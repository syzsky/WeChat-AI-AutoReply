"""统一日志：同时写 stdout 与滚动日志文件，避免日志无限增长。"""
import os
import sys
import time

MAX_BYTES = 8 * 1024 * 1024
KEEP_BACKUPS = 3


class Logger:
    def __init__(self, path: str, echo: bool = True):
        self.path = path
        self.echo = echo
        self._ensure_dir()
        try:
            if sys.stdout:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            if sys.stderr:
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    def _ensure_dir(self):
        d = os.path.dirname(os.path.abspath(self.path))
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)

    def _rotate(self):
        try:
            if os.path.exists(self.path) and os.path.getsize(self.path) > MAX_BYTES:
                for i in range(KEEP_BACKUPS - 1, 0, -1):
                    src = f"{self.path}.{i}"
                    dst = f"{self.path}.{i + 1}"
                    if os.path.exists(src):
                        os.replace(src, dst)
                os.replace(self.path, f"{self.path}.1")
        except Exception:
            pass

    def __call__(self, msg: str, level: str = "INFO"):
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}][{level}] {msg}"
        if self.echo:
            try:
                print(line, flush=True)
            except Exception:
                try:
                    print(line.encode("gbk", errors="ignore").decode("gbk"), flush=True)
                except Exception:
                    pass
        try:
            self._rotate()
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def warn(self, msg: str):
        self(msg, "WARN")

    def error(self, msg: str):
        self(msg, "ERROR")
