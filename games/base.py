"""游戏适配器基类：把「抓图 → 读数 → 决策 → 注入」四步抽象出来。

换游戏只要实现一个 GameAdapter 子类，核心库与 GUI 都不用改。
"""


class Observation:
    """一帧的观测结果。"""

    __slots__ = ("hp", "mp", "dead", "monsters", "items", "screen_changed",
                 "stuck_seconds", "extra")

    def __init__(self, hp=1.0, mp=1.0, dead=False, monsters=None,
                 items=None, screen_changed=True, stuck_seconds=0.0, extra=None):
        self.hp = hp
        self.mp = mp
        self.dead = dead
        self.monsters = monsters or []
        self.items = items or []
        self.screen_changed = screen_changed
        self.stuck_seconds = stuck_seconds
        self.extra = extra or {}

    def __repr__(self):
        return (f"Observation(hp={self.hp:.2f}, mp={self.mp:.2f}, dead={self.dead}, "
                f"monsters={len(self.monsters)}, stuck={self.stuck_seconds:.1f}s)")


class Action:
    """决策输出：一个可执行动作。"""

    __slots__ = ("kind", "params")

    def __init__(self, kind: str, **params):
        self.kind = kind
        self.params = params

    def __repr__(self):
        return f"Action({self.kind}, {self.params})"


class GameAdapter:
    """子类需实现：find_window / observe / execute / name"""

    name = "base"

    def find_window(self):
        raise NotImplementedError

    def observe(self, img) -> Observation:
        raise NotImplementedError

    def execute(self, action: Action) -> bool:
        raise NotImplementedError
