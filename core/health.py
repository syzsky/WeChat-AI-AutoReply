"""异常诊断：把"卡住了"拆成可判定的几种具体故障，并给出处置动作。

故障类型（按严重度）：
    window_lost   窗口没了          → rebind（重新绑定）
    black_screen  画面全黑          → recover（按 ESC / 等过图）
    frozen        画面长时间不变     → unstick（走位脱困）
    death_loop    短时间内反复死亡   → relocate（换图）
    no_progress   长时间零击杀       → relocate（换图）
    disconnected  出现断线弹窗       → relogin（重登）

判定逻辑是纯函数（diagnose），不碰窗口，可在任何平台单测。
"""
import time

SEV_WINDOW = "window_lost"
SEV_BLACK = "black_screen"
SEV_FROZEN = "frozen"
SEV_DEATH_LOOP = "death_loop"
SEV_NO_PROGRESS = "no_progress"
SEV_DISCONNECT = "disconnected"

ACTION_REBIND = "rebind"
ACTION_RECOVER = "recover"
ACTION_UNSTICK = "unstick"
ACTION_RELOCATE = "relocate"
ACTION_RELOGIN = "relogin"

DISCONNECT_WORDS = ["与服务器断开", "连接中断", "重新连接", "网络错误", "掉线", "服务器维护"]


class Issue:
    __slots__ = ("code", "action", "detail")

    def __init__(self, code, action, detail=""):
        self.code = code
        self.action = action
        self.detail = detail

    def __repr__(self):
        return f"Issue({self.code}→{self.action}, {self.detail})"


def diagnose(*, window_ok=True, black_seconds=0.0, frozen_seconds=0.0,
             deaths_recent=0, kill_gap_seconds=0.0, notice_text="",
             cfg=None) -> list:
    """输入各项计时/计数，输出故障列表（按严重度排序）。"""
    cfg = cfg or {}
    issues = []

    if not window_ok:
        issues.append(Issue(SEV_WINDOW, ACTION_REBIND, "窗口句柄失效"))
        return issues  # 窗口没了，其他判定无意义

    if any(w and w in (notice_text or "") for w in DISCONNECT_WORDS):
        issues.append(Issue(SEV_DISCONNECT, ACTION_RELOGIN, notice_text[:30]))

    black_limit = float(cfg.get("black_screen_seconds", 12))
    if black_seconds >= black_limit:
        issues.append(Issue(SEV_BLACK, ACTION_RECOVER, f"黑屏 {black_seconds:.0f}s"))

    frozen_limit = float(cfg.get("frozen_seconds", 20))
    if frozen_seconds >= frozen_limit:
        issues.append(Issue(SEV_FROZEN, ACTION_UNSTICK, f"画面静止 {frozen_seconds:.0f}s"))

    death_limit = int(cfg.get("death_loop_count", 3))
    if deaths_recent >= death_limit:
        issues.append(Issue(SEV_DEATH_LOOP, ACTION_RELOCATE,
                            f"{deaths_recent} 次死亡"))

    progress_limit = float(cfg.get("no_progress_minutes", 20)) * 60
    if progress_limit > 0 and kill_gap_seconds >= progress_limit:
        issues.append(Issue(SEV_NO_PROGRESS, ACTION_RELOCATE,
                            f"{kill_gap_seconds / 60:.0f} 分钟无击杀"))

    return issues


class HealthMonitor:
    """维护计时器，把每帧观测喂进来，输出当前故障。"""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.black_since = 0.0
        self.frozen_since = 0.0
        self.deaths = []          # 死亡时间戳
        self.last_kill_at = time.time()
        self.last_notice = ""
        self.last_issues = []

    def feed(self, *, now=None, window_ok=True, dark=False, changed=True,
             dead=False, notice_text=""):
        now = time.time() if now is None else now

        self.black_since = (self.black_since or now) if dark else 0.0
        self.frozen_since = (self.frozen_since or now) if not changed else 0.0

        if dead:
            self.deaths.append(now)
            self.last_kill_at = now  # 死亡也算"有动静"，避免和 no_progress 叠加
        self.deaths = [t for t in self.deaths if now - t <= 600]

        if notice_text:
            self.last_notice = notice_text

        issues = diagnose(
            window_ok=window_ok,
            black_seconds=(now - self.black_since) if self.black_since else 0.0,
            frozen_seconds=(now - self.frozen_since) if self.frozen_since else 0.0,
            deaths_recent=len(self.deaths),
            kill_gap_seconds=now - self.last_kill_at,
            notice_text=self.last_notice,
            cfg=self.cfg,
        )
        self.last_issues = issues
        return issues

    def note_kill(self, now=None):
        self.last_kill_at = time.time() if now is None else now
        self.deaths.clear()

    def note_progress(self, now=None):
        """任何有效进展（击杀/拾取/换图）都重置无进展计时。"""
        self.last_kill_at = time.time() if now is None else now
