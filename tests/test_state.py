"""决策状态机单测：纯逻辑，不依赖 Windows。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from games.base import Observation  # noqa: E402
from games.mir2.state import Decider  # noqa: E402

CFG = {
    "potion_hp_threshold": 0.55,
    "potion_mp_threshold": 0.25,
    "stuck_seconds": 8.0,
    "skill_interval": 0.0,
    "use_mp_potion": True,
}


def obs(**kw):
    base = dict(hp=1.0, mp=1.0, dead=False, monsters=[], items=[],
                screen_changed=True, stuck_seconds=0.0)
    base.update(kw)
    return Observation(**base)


class TestDecider(unittest.TestCase):
    def setUp(self):
        self.d = Decider(dict(CFG))

    def test_dead_has_top_priority(self):
        a = self.d.decide(obs(dead=True, hp=0.0, monsters=[{"x": 1, "y": 2}]))
        self.assertEqual(a.kind, "revive")
        self.assertEqual(self.d.state, "dead")

    def test_low_hp_drinks_potion_before_fighting(self):
        a = self.d.decide(obs(hp=0.30, monsters=[{"x": 10, "y": 10}]))
        self.assertEqual(a.kind, "potion")
        self.assertEqual(a.params["slot"], "hp")

    def test_low_mp_drinks_mp_potion(self):
        a = self.d.decide(obs(mp=0.10))
        self.assertEqual(a.kind, "potion")
        self.assertEqual(a.params["slot"], "mp")

    def test_mp_potion_disabled(self):
        d = Decider(dict(CFG, use_mp_potion=False))
        a = d.decide(obs(mp=0.05))
        self.assertNotEqual((a.kind, a.params.get("slot")), ("potion", "mp"))

    def test_attack_when_monster_visible(self):
        a = self.d.decide(obs(monsters=[{"name": "鸡", "x": 100, "y": 200}]))
        self.assertEqual(a.kind, "attack")
        self.assertEqual(a.params["x"], 100)

    def test_loot_when_item_visible(self):
        a = self.d.decide(obs(items=[{"name": "金币", "x": 50, "y": 60}]))
        self.assertEqual(a.kind, "loot")

    def test_unstick_after_stuck(self):
        a = self.d.decide(obs(stuck_seconds=9.0))
        self.assertEqual(a.kind, "unstick")
        self.assertEqual(self.d.state, "stuck")

    def test_patrol_is_default(self):
        a = self.d.decide(obs())
        self.assertEqual(a.kind, "patrol")

    def test_skill_fires_on_interval(self):
        d = Decider(dict(CFG, skill_interval=1.0))
        first = d.decide(obs(), now=100.0)
        self.assertEqual(first.kind, "skill")
        second = d.decide(obs(), now=100.5)
        self.assertNotEqual(second.kind, "skill")
        third = d.decide(obs(), now=101.5)
        self.assertEqual(third.kind, "skill")

    def test_counters(self):
        self.d.decide(obs(hp=0.1))
        self.d.decide(obs(items=[{"x": 1, "y": 1}]))
        self.d.decide(obs(dead=True, hp=0.0))
        self.assertEqual(self.d.counters["potions"], 1)
        self.assertEqual(self.d.counters["loots"], 1)
        self.assertEqual(self.d.counters["deaths"], 1)


if __name__ == "__main__":
    unittest.main()
