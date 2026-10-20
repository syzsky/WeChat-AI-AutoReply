"""指标落库：每角色一份 SQLite，线程/进程安全，附 JSON 快照给控制台读。

表结构：
    events(ts, account, kind, value)   —— 击杀/拾取/喝药/死亡/传送/异常
    snapshots(ts, account, json)       —— 每 30 秒一次完整状态
"""
import json
import os
import sqlite3
import threading
import time


class Metrics:
    def __init__(self, path: str, account: str = "default"):
        self.path = path
        self.account = account
        self._lock = threading.Lock()
        d = os.path.dirname(os.path.abspath(path))
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS events("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, account TEXT, kind TEXT, value REAL)")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS snapshots("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, account TEXT, json TEXT)")
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_ev ON events(account, kind, ts)")
        self._db.commit()

    # ---------- 写入 ----------
    def event(self, kind: str, value: float = 1):
        with self._lock:
            self._db.execute("INSERT INTO events(ts, account, kind, value) VALUES(?,?,?,?)",
                             (time.time(), self.account, kind, float(value)))
            self._db.commit()

    def snapshot(self, data: dict):
        with self._lock:
            self._db.execute("INSERT INTO snapshots(ts, account, json) VALUES(?,?,?)",
                             (time.time(), self.account,
                              json.dumps(data, ensure_ascii=False)))
            self._db.commit()

    # ---------- 读取 ----------
    def totals(self, since_hours: float = 24.0) -> dict:
        since = time.time() - since_hours * 3600
        with self._lock:
            rows = self._db.execute(
                "SELECT kind, COUNT(*), COALESCE(SUM(value),0) FROM events "
                "WHERE account=? AND ts>=? GROUP BY kind",
                (self.account, since)).fetchall()
        return {k: {"count": int(c), "sum": float(s)} for k, c, s in rows}

    def last_snapshot(self):
        with self._lock:
            row = self._db.execute(
                "SELECT ts, json FROM snapshots WHERE account=? ORDER BY ts DESC LIMIT 1",
                (self.account,)).fetchone()
        if not row:
            return None
        try:
            return {"ts": row[0], "data": json.loads(row[1])}
        except Exception:
            return None

    def close(self):
        try:
            with self._lock:
                self._db.close()
        except Exception:
            pass


def write_status(path: str, data: dict):
    """原子写状态文件，控制台/GUI 轮询这个。"""
    tmp = path + ".tmp"
    try:
        d = os.path.dirname(os.path.abspath(path))
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        pass


def read_status(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
