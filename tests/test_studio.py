"""工作室组件单测：节律、任务链、指标库。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.human import Humanizer  # noqa: E402
from core.metrics import Metrics, read_status, write_status  # noqa: E402
from games.mir2.worker import (  # noqa: E402
    TASK_GRIND, TASK_RESUPPLY, TASK_RETURN, TaskState, next_task,
)


class TestHumanizer(unittest.TestCase):
    def test_delay_within_jitter(self):
        h = Humanizer({"jitter": 0.2})
        for _ in range(50):
            d = h.delay(1.0)
            self.assertGreaterEqual(d, 0.79)
            self.assertLessEqual(d, 1.21)

    def test_zero_jitter_is_stable(self):
        h = Humanizer({"jitter": 0.0})
        self.assertAlmostEqual(h.delay(0.5), 0.5, places=2)

    def test_offset_within_radius(self):
        h = Humanizer({"click_radius": 5})
        for _ in range(50):
            x, y = h.offset(100, 200)
            self.assertLessEqual(abs(x - 100), 5)
            self.assertLessEqual(abs(y - 200), 5)

    def test_zero_radius_no_offset(self):
        h = Humanizer({"click_radius": 0})
        self.assertEqual(h.offset(10, 20), (10, 20))

    def test_rest_triggers_after_interval(self):
        h = Humanizer({"rest_every_minutes": 1, "rest_minutes": 1, "rest_jitter": 0})
        t0 = h._started
        self.assertFalse(h.tick_rest(now=t0 + 10))
        self.assertTrue(h.tick_rest(now=t0 + 61))
        self.assertTrue(h.resting(now=t0 + 62))
        # 休息 1 分钟结束后恢复工作（下一次休息在 121s 之后）
        self.assertFalse(h.tick_rest(now=t0 + 130))
        # 到下一个周期再休息
        self.assertTrue(h.tick_rest(now=t0 + 190))


class TestTaskChain(unittest.TestCase):
    def test_default_is_grind(self):
        st = TaskState()
        self.assertEqual(next_task(st, {}), TASK_GRIND)

    def test_resupply_after_interval(self):
        st = TaskState(last_resupply=1000.0)
        cfg = {"resupply_every_minutes": 30}
        self.assertEqual(next_task(st, cfg, now=1000 + 60), TASK_GRIND)
        self.assertEqual(next_task(st, cfg, now=1000 + 1801), TASK_RESUPPLY)

    def test_resupply_sticky(self):
        st = TaskState(task=TASK_RESUPPLY)
        self.assertEqual(next_task(st, {"resupply_every_minutes": 1}, now=9e9), TASK_RESUPPLY)

    def test_return_sticky(self):
        st = TaskState(task=TASK_RETURN)
        self.assertEqual(next_task(st, {}, now=9e9), TASK_RETURN)

    def test_disabled_when_zero(self):
        st = TaskState(last_resupply=0.0)
        self.assertEqual(next_task(st, {"resupply_every_minutes": 0}, now=9e9), TASK_GRIND)


class TestMetrics(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mir_metrics_")
        self.path = os.path.join(self.tmp, "m.db")
        self.m = Metrics(self.path, "a1")

    def tearDown(self):
        self.m.close()

    def test_event_counters(self):
        self.m.event("attack")
        self.m.event("attack")
        self.m.event("loot")
        t = self.m.totals()
        self.assertEqual(t["attack"]["count"], 2)
        self.assertEqual(t["loot"]["count"], 1)

    def test_accounts_isolated(self):
        other = Metrics(self.path, "a2")
        other.event("attack")
        self.assertEqual(self.m.totals().get("attack", {}).get("count", 0), 0)
        self.assertEqual(other.totals()["attack"]["count"], 1)
        other.close()

    def test_snapshot_roundtrip(self):
        self.m.snapshot({"hp": 0.8, "task": "grind"})
        last = self.m.last_snapshot()
        self.assertEqual(last["data"]["hp"], 0.8)

    def test_status_file(self):
        p = os.path.join(self.tmp, "status.json")
        write_status(p, {"state": "running"})
        self.assertEqual(read_status(p)["state"], "running")

    def test_read_missing_status(self):
        self.assertIsNone(read_status(os.path.join(self.tmp, "nope.json")))


if __name__ == "__main__":
    unittest.main()
