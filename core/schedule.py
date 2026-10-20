"""时段调度：只在配置的时间窗内挂机，跨零点也支持。

配置示例：
    "schedule": {"enabled": true, "windows": ["08:00-12:00", "14:00-23:30"], "weekdays": [1,2,3,4,5,6,7]}
"""
import time


def parse_window(text: str):
    """'08:00-12:00' → (480, 720) 分钟；跨零点 '22:00-06:00' → (1320, 1800+360)。"""
    try:
        a, b = text.split("-")
        ah, am = [int(x) for x in a.strip().split(":")]
        bh, bm = [int(x) for x in b.strip().split(":")]
        start = ah * 60 + am
        end = bh * 60 + bm
        if end <= start:      # 跨零点
            end += 24 * 60
        return start, end
    except Exception:
        return None


def minutes_now(now=None) -> int:
    t = time.localtime(time.time() if now is None else now)
    return t.tm_hour * 60 + t.tm_min


def weekday_now(now=None) -> int:
    """1=周一 ... 7=周日（和配置里写的习惯一致）。"""
    t = time.localtime(time.time() if now is None else now)
    return t.tm_wday + 1


def is_active(cfg: dict, now=None) -> bool:
    """当前是否该挂机。未配置或 enabled=false 时永远返回 True。"""
    sched = (cfg or {}).get("schedule") or {}
    if not sched.get("enabled"):
        return True

    days = sched.get("weekdays") or [1, 2, 3, 4, 5, 6, 7]
    if weekday_now(now) not in days:
        return False

    windows = [parse_window(w) for w in (sched.get("windows") or [])]
    windows = [w for w in windows if w]
    if not windows:
        return True

    cur = minutes_now(now)
    for start, end in windows:
        if start <= cur < end:
            return True
        if end > 24 * 60 and cur + 24 * 60 < end:  # 跨零点后半夜
            return True
    return False


def next_start_minutes(cfg: dict, now=None):
    """距离下一个可用时间窗还有多少分钟；已在窗内返回 0。"""
    if is_active(cfg, now):
        return 0
    sched = (cfg or {}).get("schedule") or {}
    windows = [parse_window(w) for w in (sched.get("windows") or [])]
    windows = [w for w in windows if w]
    if not windows:
        return 0
    cur = minutes_now(now)
    best = None
    for start, _end in windows:
        delta = (start - cur) % (24 * 60)
        if delta == 0:
            delta = 24 * 60
        best = delta if best is None else min(best, delta)
    return best or 0
