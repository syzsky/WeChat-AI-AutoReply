"""单实例锁：同一角色只允许跑一个进程，防止重复启动导致互相抢窗口。"""
import os
import sys
import time


class InstanceLock:
    def __init__(self, path: str):
        self.path = path
        self.acquired = False

    def acquire(self) -> bool:
        """拿到锁返回 True；已被活进程占用返回 False。"""
        if self.acquired:
            return True
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        pid = self._read_pid()
        if pid and self._alive(pid):
            return False
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(f"{os.getpid()}\n{int(time.time())}\n")
            self.acquired = True
            return True
        except Exception:
            return False

    def release(self):
        if not self.acquired:
            return
        try:
            if self._read_pid() == os.getpid():
                os.remove(self.path)
        except Exception:
            pass
        self.acquired = False

    # ---------- 内部 ----------
    def _read_pid(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return int(f.readline().strip())
        except Exception:
            return 0

    @staticmethod
    def _alive(pid: int) -> bool:
        if pid <= 0:
            return False
        if sys.platform == "win32":
            try:
                import psutil
                return psutil.pid_exists(pid)
            except Exception:
                return True  # 无法判断时按存活处理，宁可不启动
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
