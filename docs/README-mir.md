# 传奇挂机（mir-bot 分支）

在上游「微信 AI 自动回复」的**无痕窗口操作**底座上重写的传奇（Mir2 系）挂机框架。

保留上游三条硬约束，替换掉业务层：

| 上游能力 | 本分支用途 |
|---|---|
| PrintWindow 离屏抓图 | 游戏窗口被遮挡/挪到屏幕外照样读画面 |
| AttachThreadInput 提权激活 | 需要键盘输入时短暂抢焦点，之后自动让出 |
| PostMessage 点击（物理鼠标 0 移动） | 打怪、走位、点 NPC 全走窗口消息 |
| RapidOCR 本地识别 | 读怪物名、物品名、死亡提示 |
| OpenAI 兼容 AI 引擎 | 游戏内私聊自动回复（可选） |

## 目录结构

```
core/                 通用底座（与游戏无关）
├── win32api.py       窗口枚举 / 离屏挂载 / 抓图 / 消息注入
├── vision.py         归一化裁剪 / 血条读数 / 色块检测 / 帧差
├── ocr.py            RapidOCR 封装（整图 / 区域 / 找文本 / 读数字）
├── llm.py            OpenAI 兼容客户端（含重试）
├── config.py         JSON 配置 + 深合并 + 热重载
└── logger.py         滚动日志

games/
├── base.py           GameAdapter 抽象（换游戏只实现这一层）
└── mir2/
    ├── layout.py     界面区域（归一化坐标，分辨率无关）
    ├── reader.py     血/蓝/死亡/怪物/物品 读数
    ├── state.py      状态机（纯逻辑，可单测）
    └── adapter.py    决策 → 注入

apps/
├── mir_bot.py        无界面守护（主力）
└── mir_gui.py        控制中心（看日志、改配置、起停）

tools/snapshot.py     抓一张游戏窗口截图，用来量坐标
tests/                20 个单测，不需要 Windows
legacy/wechat/        上游微信实现，保留作参考
```

## 快速开始（Windows）

```bat
pip install -r requirements-mir.txt
copy games\mir2\config.example.json mir_config.json
:: 先量坐标
python tools\snapshot.py
:: 调试单帧
python apps\mir_bot.py --dry-run --once
:: 正式挂机
python apps\mir_bot.py
:: 或开控制中心
python apps\mir_gui.py
```

## 配置要点（`mir_config.json`）

| 键 | 说明 |
|---|---|
| `window_title_keywords` | 窗口标题关键词，默认 `["传奇","Mir","Legend"]` |
| `layout` | 覆盖 `games/mir2/layout.py` 里的任意区域，如 `{"hp_bar": [0.05,0.90,0.29,0.92]}` |
| `potion_hp_threshold` | 血量低于此比例喝红（0~1） |
| `monster_names` | 要打的怪名，OCR 命中即点击 |
| `item_names` | 要捡的物品名 |
| `skill_interval` | 技能按键间隔秒数，0 = 关 |
| `stuck_seconds` | 画面 N 秒无变化判定卡位，自动 ESC + 走位 |
| `chat_reply_enabled` | 游戏内聊天 AI 回复开关 |

配置改完**不用重启**，守护进程每轮热重载。

## 工作室模式（多开）

一角色一进程，崩溃隔离，总控负责重启和汇总。

```bat
copy docs\studio_config.example.json studio_config.json
python apps\studio.py --http 8765
```

`studio_config.json` 里每个角色一份 `overrides`，会和模板合并后生成到 `data/accounts/<name>.json`：

```json
{
  "restart_delay": 5,
  "max_restarts_per_hour": 5,
  "accounts": [
    {"name": "a1", "overrides": {"window_title_keywords": ["传奇1"]}},
    {"name": "a2", "overrides": {"window_title_keywords": ["传奇2"], "window_pid": 12345}}
  ]
}
```

**四种能力**

| 能力 | 实现 | 位置 |
|---|---|---|
| 多开隔离 | 每角色独立进程 + 独立配置/日志/指标 | `apps/studio.py` |
| 崩溃自愈 | 退出自动重启，1 小时超 5 次停手 | `Account.supervise()` |
| 状态汇总 | `data/studio_status.json` + `GET /status` | `Studio.status()` |
| 行为限速 | 延迟抖动 ±25%、点击偏移 ±6px、定时休息 | `core/human.py` |

**任务链**：挂机 → 到点补给（`resupply_every_minutes`）→ 回挂机图 → 循环。补给/回图失败会重试，连续 3 次放弃并原地挂机，避免死循环。

**指标**：`data/metrics.db`（SQLite），每角色一张表空间，记 `attack/loot/potion/death/unstick/resupply`。查：

```python
from core.metrics import Metrics
m = Metrics("data/metrics.db", "a1")
print(m.totals(24))      # 最近 24 小时
print(m.last_snapshot())
```

## 窗口绑定

绑定只是拿到窗口句柄 `hwnd`，不注入、不挂钩子。三种方式，优先级从高到低：

| 方式 | 配置键 | 优点 | 缺点 |
|---|---|---|---|
| 句柄 | `window_hwnd` | 最精确，多开也不会绑错 | 重启游戏就失效 |
| 进程 | `window_pid` | 多开时最稳 | 重启游戏就失效 |
| 关键词 | `window_title_keywords` / `window_class_keywords` | 长期有效 | 标题相似时会绑错 |

先用清单工具看清楚有哪些窗口：

```bat
python tools\window_list.py
python tools\window_list.py --filter 传奇
```

输出每行的 `hwnd / pid / class / title`，挑游戏那一行：

```
      hwnd     pid       client  process             class / title
    131082    4321     1024x768  legend.exe          TApplication | 传奇-比奇省
```

然后把关键词写进配置（推荐，不用每次改）：

```json
"window_title_keywords": ["传奇"],
"window_class_keywords": ["TApplication"],
"window_hwnd": 0,
"window_pid": 0
```

`hwnd`/`pid` 填 0 表示不启用。程序每轮都会 `IsWindow()` 校验句柄，游戏重开就自动重新找。

## NPC 传送（进图）

传奇的传送没有可读协议，只能照 UI 走：**点 NPC → 弹对话窗 → 点选项**。

```json
"travel_route": {
  "npc": "传送员",
  "options": ["比奇省", "比奇城"],
  "map": "比奇城"
}
```

启动挂机时自动执行一次（`--dry-run` 不执行）。流程见 `games/mir2/travel.py`：

1. 读小地图上方地图名，已经是目标图就直接返回
2. OCR 主视野找 `npc` 名字，点它
3. 等对话窗，OCR `dialog` 区域，按优先级找选项：**目标地图名 → options 顺序 → 传送/进入/确定/确认/前往**
4. 点到就再等 0.8 秒，回到第 1 步校验；多级菜单（比奇省 → 比奇城）靠这个循环逐级点下去
5. 视野里找不到 NPC 就走两步换视角，25 秒超时退出

需要手动触发时：

```python
adapter.travel_to({"npc": "传送员", "options": ["盟重省"], "map": "盟重省"})
```

**两个坐标必须先校准**：`layout.dialog`（对话框范围）和 `layout.map_name`（地图名位置）。用 `tools/snapshot.py` 截图后量。

## 决策优先级

```
死亡复活 → 喝红 → 喝蓝 → 打怪 → 捡物 → 放技能 → 防卡脱困 → 随机巡逻
```

## 已知边界

1. **独占全屏（DirectX 独占）抓不到** —— 请用窗口化/无边框窗口模式；PrintWindow 抓不到时会自动退回屏幕截图。
2. **部分反外挂会拦 PostMessage** —— 本框架不注入、不读内存、不改协议，但服务端仍可能判定异常操作频率，参数别调太激进。
3. **坐标要校准** —— 默认布局按经典 1024×768 估算，第一次用必须 `tools/snapshot.py` 量一遍。
4. **只在 Windows 跑** —— 单测可在任意平台跑（`python -m unittest discover -s tests`）。
