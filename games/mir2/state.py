"""挂机状态机：纯逻辑，不碰 Win32，可在任何平台单测。

优先级（从高到低）：
  死亡 → 回血 → 回蓝 → 打怪 → 捡物 → 技能 → 防卡 → 巡逻
"""
import time

from games.base import Action, Observation

STATE_IDLE = "idle"
STATE_FIGHT = "fight"
STATE_LOOT = "loot"
STATE_POTION = "potion"
STATE_DEAD = "dead"
STATE_STUCK = "stuck"
STATE_PATROL = "patrol"


class Decider:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.last_action_at = 0.0
        self.last_skill_at = 0.0
        self.state = STATE_IDLE
        self.counters = {"kills": 0, "loots": 0, "potions": 0, "deaths": 0}

    # ---------- 配置快捷读取 ----------
    def _f(self, key, default):
        v = (self.cfg or {}).get(key, default)
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    def _i(self, key, default):
        v = (self.cfg or {}).get(key, default)
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    # ---------- 主决策 ----------
    def decide(self, obs: Observation, now=None) -> Action:
        now = time.time() if now is None else now
        hp_th = self._f("potion_hp_threshold", 0.55)
        mp_th = self._f("potion_mp_threshold", 0.25)
        min_gap = self._f("min_action_gap", 0.15)

        if obs.dead:
            self.state = STATE_DEAD
            self.counters["deaths"] += 1
            return Action("revive", reason="dead")

        if obs.hp <= hp_th:
            self.state = STATE_POTION
            self.counters["potions"] += 1
            return Action("potion", slot="hp", ratio=obs.hp)

        if obs.mp <= mp_th and self.cfg.get("use_mp_potion", True):
            self.state = STATE_POTION
            return Action("potion", slot="mp", ratio=obs.mp)

        if obs.monsters:
            self.state = STATE_FIGHT
            # 最近的怪优先（按与屏幕中心距离）
            target = obs.monsters[0]
            return Action("attack", x=target.get("x"), y=target.get("y"),
                          name=target.get("name", ""))

        if obs.items:
            self.state = STATE_LOOT
            self.counters["loots"] += 1
            it = obs.items[0]
            return Action("loot", x=it.get("x"), y=it.get("y"),
                          name=it.get("name", ""))

        skill_gap = self._f("skill_interval", 0.0)
        if skill_gap > 0 and (now - self.last_skill_at) >= skill_gap:
            self.last_skill_at = now
            self.state = STATE_FIGHT
            return Action("skill")

        if obs.stuck_seconds >= self._f("stuck_seconds", 8.0):
            self.state = STATE_STUCK
            return Action("unstick")

        if not obs.screen_changed and (now - self.last_action_at) >= min_gap:
            self.state = STATE_PATROL
            return Action("patrol")

        self.state = STATE_PATROL
        return Action("patrol")

    def mark_action(self, now=None):
        self.last_action_at = time.time() if now is None else now
