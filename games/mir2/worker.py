"""单角色任务链：挂机 → 到点补给 → 回挂机图 → 循环。

任务切换是纯逻辑（next_task），执行部分才碰窗口，
所以任务链可以在没有 Windows 的机器上单测。
"""
import time

TASK_GRIND = "grind"
TASK_RESUPPLY = "resupply"
TASK_RETURN = "return"
TASK_IDLE = "idle"

# 任务优先级：补给 > 回图 > 挂机
_VALID = {TASK_GRIND, TASK_RESUPPLY, TASK_RETURN, TASK_IDLE}


class TaskState:
    __slots__ = ("task", "last_resupply", "last_return", "resupply_count",
                 "return_failures")

    def __init__(self, task=TASK_GRIND, last_resupply=None, last_return=None):
        self.task = task
        self.last_resupply = last_resupply or time.time()
        self.last_return = last_return or 0.0
        self.resupply_count = 0
        self.return_failures = 0

    def to_dict(self):
        return {"task": self.task, "last_resupply": self.last_resupply,
                "resupply_count": self.resupply_count,
                "return_failures": self.return_failures}


def next_task(state: TaskState, cfg: dict, now=None) -> str:
    """决定这一轮该干什么。纯函数，方便单测。"""
    now = time.time() if now is None else now
    interval = float(cfg.get("resupply_every_minutes", 0) or 0) * 60

    # 补给中/回图中：由执行层推进，不在这里重判
    if state.task in (TASK_RESUPPLY, TASK_RETURN):
        return state.task

    if interval > 0 and (now - state.last_resupply) >= interval:
        return TASK_RESUPPLY

    # 没配挂机图就直接挂机
    return TASK_GRIND


class StudioWorker:
    """把一个 adapter 包成带任务链、人类化节律、指标上报的工作单元。"""

    def __init__(self, adapter, cfg: dict, human=None, metrics=None, log=None):
        self.adapter = adapter
        self.cfg = cfg
        self.human = human
        self.metrics = metrics
        self.log = log or adapter.log
        self.state = TaskState()

    # ---------- 主入口 ----------
    def step(self, img):
        """跑一轮：返回 (observation, action)。任务切换在这里发生。"""
        import time as _t

        if self.human and self.human.tick_rest():
            self.log(f"休息中，剩余 {self.human.rest_remaining():.0f}s")
            _t.sleep(min(5.0, max(1.0, self.human.rest_remaining())))
            return None, None

        task = next_task(self.state, self.cfg)
        if task != self.state.task:
            self.log(f"任务切换 {self.state.task} → {task}")
            self.state.task = task

        if task == TASK_RESUPPLY:
            self._do_resupply()
            return None, None
        if task == TASK_RETURN:
            self._do_return()
            return None, None

        obs = self.adapter.observe(img)
        action = self.adapter.decider.decide(obs)
        self._record(obs, action)
        return obs, action

    # ---------- 任务执行 ----------
    def _do_resupply(self):
        route = self.cfg.get("resupply_route") or {}
        if not route.get("npc"):
            self.log("未配置 resupply_route，跳过补给")
            self.state.last_resupply = time.time()
            self.state.task = TASK_RETURN
            return
        ok = self.adapter.travel_to(route, timeout=float(self.cfg.get("travel_timeout", 25)))
        if self.metrics:
            self.metrics.event("resupply", 1 if ok else 0)
        if ok:
            self.state.last_resupply = time.time()
            self.state.resupply_count += 1
            self.state.task = TASK_RETURN
            self.log("补给完成，准备回挂机图")
        else:
            self.log("补给失败，30 秒后重试")
            time.sleep(30)

    def _do_return(self):
        route = self.cfg.get("grind_route") or {}
        if not route.get("npc"):
            self.state.task = TASK_GRIND
            return
        ok = self.adapter.travel_to(route, timeout=float(self.cfg.get("travel_timeout", 25)))
        if ok:
            self.state.return_failures = 0
            self.state.task = TASK_GRIND
            self.log("已回到挂机图")
        else:
            self.state.return_failures += 1
            self.log(f"回图失败（第 {self.state.return_failures} 次），10 秒后重试")
            time.sleep(10)
            if self.state.return_failures >= 3:
                self.state.task = TASK_GRIND  # 放弃回图，原地挂机，避免死循环

    # ---------- 指标 ----------
    def _record(self, obs, action):
        if not self.metrics:
            return
        k = action.kind
        if k == "attack":
            self.metrics.event("attack")
        elif k == "loot":
            self.metrics.event("loot")
        elif k == "potion":
            self.metrics.event("potion")
        elif k == "revive":
            self.metrics.event("death")
        elif k == "unstick":
            self.metrics.event("unstick")
