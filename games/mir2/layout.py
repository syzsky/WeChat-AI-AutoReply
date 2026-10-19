"""传奇（Mir2 系）界面布局：全部使用归一化坐标，分辨率无关。

默认值按经典 1024×768 客户端布局估算，实测请用 tools/calibrate.py 校准后覆盖到配置里。
"""

DEFAULT_LAYOUT = {
    # 血条 / 蓝条（左下角弧形条，取中间那一行采样最稳）
    "hp_bar": [0.055, 0.900, 0.290, 0.922],
    "mp_bar": [0.055, 0.925, 0.290, 0.947],

    # 血蓝数字（可选，OCR 兜底）
    "hp_text": [0.060, 0.885, 0.200, 0.905],
    "mp_text": [0.060, 0.950, 0.200, 0.970],

    # 主视野（找怪 / 走位都限制在这个区域，避免点到 UI）
    "view": [0.240, 0.040, 0.960, 0.860],

    # 聊天框（游戏内聊天，AI 回复用）
    "chat": [0.010, 0.700, 0.360, 0.880],

    # 小地图
    "minimap": [0.860, 0.020, 0.995, 0.180],

    # 背包 / 技能栏（预留）
    "inventory": [0.760, 0.300, 0.995, 0.700],
    "skillbar": [0.300, 0.955, 0.700, 0.995],

    # 中央提示（"你已死亡"、"等级提升" 等）
    "notice": [0.300, 0.400, 0.700, 0.600],
}


def get_layout(overrides=None):
    """合并默认布局与用户覆盖。"""
    layout = {k: list(v) for k, v in DEFAULT_LAYOUT.items()}
    for k, v in (overrides or {}).items():
        if k not in DEFAULT_LAYOUT:
            continue  # 忽略拼错的键，避免把垃圾配置带进运行时
        if isinstance(v, (list, tuple)) and len(v) == 4:
            layout[k] = list(v)
    return layout


def denormalize(rect, width, height):
    """归一化矩形 → 像素矩形。"""
    x1, y1, x2, y2 = rect
    return (int(x1 * width), int(y1 * height), int(x2 * width), int(y2 * height))


def center_of(rect, width, height):
    """归一化矩形中心 → 像素坐标。"""
    x1, y1, x2, y2 = rect
    return int((x1 + x2) / 2 * width), int((y1 + y2) / 2 * height)


def clamp_to_view(x, y, view, width, height, margin=12):
    """把点击点限制在视野内，防止误点到 UI 面板。"""
    x1, y1, x2, y2 = denormalize(view, width, height)
    x = max(x1 + margin, min(x2 - margin, x))
    y = max(y1 + margin, min(y2 - margin, y))
    return x, y
