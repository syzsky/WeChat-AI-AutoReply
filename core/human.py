"""人类化节律：抖动延迟、点击偏移、定时休息。

工作室脚本最先死在"太规律"上：固定 0.35 秒一轮、每次都点正中心。
这里统一给所有动作加随机量，并把连续工作时长切段。
"""
import random
import time


class Humanizer:
    def __init__(self, cfg: dict):
        self.jitter = float(cfg.get("jitter", 0.25))          # 延迟抖动 ±25%
        self.click_radius = int(cfg.get("click_radius", 6))    # 点击偏移像素
        self.rest_every = float(cfg.get("rest_every_minutes", 90)) * 60
        self.rest_for = float(cfg.get("rest_minutes", 8)) * 60
        self.rest_jitter = float(cfg.get("rest_jitter", 0.4))
        self._started = time.time()
        self._rest_until = 0.0
        self._next_rest = self._started + self.rest_every * random.uniform(
            1 - self.rest_jitter, 1 + self.rest_jitter)

    # ---------- 延迟 ----------
    def delay(self, base: float) -> float:
        """把基准间隔抖动后返回（调用方自己 sleep）。"""
        lo = max(0.01, 1 - self.jitter)
        hi = 1 + self.jitter
        return max(0.01, base * random.uniform(lo, hi))

    def sleep(self, base: float):
        time.sleep(self.delay(base))

    # ---------- 点击 ----------
    def offset(self, x: int, y: int):
        """在半径内随机偏移，避免每次都点同一个像素。"""
        if self.click_radius <= 0:
            return int(x), int(y)
        dx = random.randint(-self.click_radius, self.click_radius)
        dy = random.randint(-self.click_radius, self.click_radius)
        return int(x) + dx, int(y) + dy

    # ---------- 休息 ----------
    def resting(self, now=None) -> bool:
        now = time.time() if now is None else now
        return now < self._rest_until

    def tick_rest(self, now=None) -> bool:
        """到点就进入休息；返回是否正在休息。"""
        now = time.time() if now is None else now
        if now < self._rest_until:
            return True
        if now >= self._next_rest:
            self._rest_until = now + self.rest_for * random.uniform(
                1 - self.rest_jitter, 1 + self.rest_jitter)
            self._next_rest = self._rest_until + self.rest_every * random.uniform(
                1 - self.rest_jitter, 1 + self.rest_jitter)
            return True
        return False

    def rest_remaining(self, now=None) -> float:
        now = time.time() if now is None else now
        return max(0.0, self._rest_until - now)

    def uptime(self, now=None) -> float:
        now = time.time() if now is None else now
        return now - self._started
