"""运维组件单测：时段调度、异常诊断、单实例锁、药水触发补给。"""
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import schedule  # noqa: E402
from core.health import (  # noqa: E402
    ACTION_REBIND, ACTION_RELOGIN, ACTION_UNSTICK, HealthMonitor, diagnose,
)
from core.lock import InstanceLock  # noqa: E402
from games.mir2.worker import TASK_GRIND, TASK_RESUPPLY, TaskState, next_task  # noqa: E402


def epoch_at(hour, minute=0, days_offset=0):
    t = time.localtime()
    return time.mktime((t.tm_year, t.tm_mon, t.tm_mday + days_offset,
                        hour, minute, 0, 0, 0, -1))


class TestSchedule(unittest.TestCase):
    def test_parse_normal(self):
        self.assertEqual(schedule.parse_window("08:00-12:30"), (480, 750))

    def test_parse_cross_midnight(self):
        self.assertEqual(schedule.parse_window("22:00-06:00"), (1320, 1800))

    def test_parse_invalid(self):
        self.assertIsNone(schedule.parse_window("乱七八糟"))

    def test_disabled_always_active(self):
        self.assertTrue(schedule.is_active({}))

    def test_inside_window(self):
        cfg = {"schedule": {"enabled": True, "windows": ["08:00-12:00"]}}
        self.assertTrue(schedule.is_active(cfg, now=epoch_at(10)))
        self.assertFalse(schedule.is_active(cfg, now=epoch_at(13)))

    def test_weekday_filter(self):
        today = schedule.weekday_now()
        other = today % 7 + 1
        cfg = {"schedule": {"enabled": True, "windows": ["00:00-23:59"], "weekdays": [other]}}
        self.assertFalse(schedule.is_active(cfg))

    def test_next_start(self):
        cfg = {"schedule": {"enabled": True, "windows": ["23:59-23:59"]}}
        self.assertGreaterEqual(schedule.next_start_minutes(cfg), 0)


class TestHealth(unittest.TestCase):
    def test_window_lost_is_terminal(self):
        issues = diagnose(window_ok=False, black_seconds=99, frozen_seconds=99)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].action, ACTION_REBIND)

    def test_black_screen(self):
        issues = diagnose(black_seconds=20, cfg={"black_screen_seconds": 12})
        self.assertEqual(issues[0].code, "black_screen")

    def test_frozen(self):
        issues = diagnose(frozen_seconds=30, cfg={"frozen_seconds": 20})
        self.assertEqual(issues[0].action, ACTION_UNSTICK)

    def test_death_loop(self):
        issues = diagnose(deaths_recent=3, cfg={"death_loop_count": 3})
        self.assertEqual(issues[0].code, "death_loop")

    def test_disconnect_text(self):
        issues = diagnose(notice_text="与服务器断开连接")
        self.assertEqual(issues[0].action, ACTION_RELOGIN)

    def test_no_progress(self):
        issues = diagnose(kill_gap_seconds=1300, cfg={"no_progress_minutes": 20})
        self.assertEqual(issues[0].code, "no_progress")

    def test_monitor_tracks_frozen(self):
        m = HealthMonitor({"frozen_seconds": 5})
        m.feed(now=100, changed=False)
        self.assertEqual(m.feed(now=101, changed=False), [])
        issues = m.feed(now=110, changed=False)
        self.assertTrue(any(i.code == "frozen" for i in issues))
        # 画面恢复后故障消失
        self.assertEqual(m.feed(now=111, changed=True), [])

    def test_monitor_resets_black(self):
        m = HealthMonitor({"black_screen_seconds": 3})
        m.feed(now=10, dark=True)
        issues = m.feed(now=15, dark=True)
        self.assertTrue(any(i.code == "black_screen" for i in issues))
        self.assertEqual(m.feed(now=16, dark=False), [])


class TestLock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mir_lock_")
        self.path = os.path.join(self.tmp, "a1.lock")

    def test_acquire_release(self):
        lock = InstanceLock(self.path)
        self.assertTrue(lock.acquire())
        self.assertTrue(os.path.exists(self.path))
        lock.release()
        self.assertFalse(os.path.exists(self.path))

    def test_blocks_when_live_pid(self):
        with open(self.path, "w") as f:
            f.write(f"{os.getpid()}\n")
        self.assertFalse(InstanceLock(self.path).acquire())

    def test_takes_over_dead_pid(self):
        with open(self.path, "w") as f:
            f.write("999999\n")
        self.assertTrue(InstanceLock(self.path).acquire())


class TestStudioControl(unittest.TestCase):
    def _studio(self):
        import apps.studio as sm
        cfg = {"accounts": [{"name": "a1", "overrides": {}},
                            {"name": "a2", "overrides": {}}],
               "restart_delay": 1, "max_restarts_per_hour": 2}
        s = sm.Studio(cfg, {"game": "mir2"}, only=None)
        for a in s.accounts:          # 不真的起进程
            a.start = lambda: None
            a.stop = lambda: None
        return s

    def test_start_stop_known_account(self):
        s = self._studio()
        self.assertTrue(s.control("start", "a1")["ok"])
        self.assertTrue(s.control("stop", "a2")["ok"])

    def test_unknown_account(self):
        r = self._studio().control("start", "nope")
        self.assertFalse(r["ok"])
        self.assertIn("no such account", r["error"])

    def test_bad_command(self):
        self.assertFalse(self._studio().control("rm -rf")["ok"])

    def test_start_all_and_stop_all(self):
        s = self._studio()
        self.assertTrue(s.control("start_all")["ok"])
        self.assertTrue(s.control("stop_all")["ok"])

    def test_status_shape(self):
        st = self._studio().status()
        self.assertEqual(len(st["accounts"]), 2)
        self.assertIn("alive", st["accounts"][0])


class TestPotionTrigger(unittest.TestCase):
    def test_low_potions_trigger_resupply(self):
        st = TaskState()
        cfg = {"potion_low_threshold": 5}
        self.assertEqual(next_task(st, cfg, potions=10), TASK_GRIND)
        self.assertEqual(next_task(st, cfg, potions=5), TASK_RESUPPLY)

    def test_none_potions_ignored(self):
        st = TaskState()
        cfg = {"potion_low_threshold": 5}
        self.assertEqual(next_task(st, cfg, potions=None), TASK_GRIND)


if __name__ == "__main__":
    unittest.main()
