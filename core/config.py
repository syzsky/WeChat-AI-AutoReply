"""配置加载：JSON + 深合并默认值 + 按 mtime 热重载。"""
import copy
import json
import os
import threading


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    def __init__(self, path: str, defaults: dict):
        self.path = path
        self.defaults = defaults
        self._data = copy.deepcopy(defaults)
        self._mtime = 0.0
        self._lock = threading.Lock()
        self.reload(force=True)

    def reload(self, force=False):
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            return self._data
        if not force and mtime == self._mtime:
            return self._data
        try:
            with open(self.path, "r", encoding="utf-8-sig") as f:
                user = json.load(f)
            with self._lock:
                self._data = deep_merge(self.defaults, user)
                self._mtime = mtime
        except Exception:
            pass
        return self._data

    @property
    def data(self) -> dict:
        return self.reload()

    def get(self, dotted: str, default=None):
        cur = self.data
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def save(self, data: dict):
        with self._lock:
            self._data = deep_merge(self.defaults, data)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            try:
                self._mtime = os.path.getmtime(self.path)
            except OSError:
                self._mtime = 0.0
