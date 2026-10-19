"""Win32 底层：窗口枚举 / 离屏挂载 / PrintWindow 抓图 / 消息注入。

所有 API 调用都在 Windows 上执行；在非 Windows 平台上模块可导入，
但调用会抛 RuntimeError，方便在 CI 里跑纯逻辑单测。
"""
import ctypes
import sys
import time

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    kernel32 = ctypes.windll.kernel32
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor DPI aware
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
else:  # pragma: no cover - 非 Windows 只用于语法/逻辑测试
    user32 = gdi32 = kernel32 = None
    WNDENUMPROC = None


def _require_windows():
    if not IS_WINDOWS:
        raise RuntimeError("Win32 API 仅支持 Windows")


def bind_default_desktop():
    """把当前线程绑定到 Default 桌面，避免服务/计划任务会话里抓不到窗口。"""
    if not IS_WINDOWS:
        return
    try:
        h = user32.OpenDesktopW("Default", 0, False, 0x01FF)
        if h:
            user32.SetThreadDesktop(h)
            user32.CloseDesktop(h)
    except Exception:
        pass


def dpi_scale() -> float:
    """当前进程 DPI 缩放（1.0 / 1.25 / 1.5 ...）。"""
    if not IS_WINDOWS:
        return 1.0
    try:
        dc = user32.GetDC(0)
        dpi = gdi32.GetDeviceCaps(dc, 88)  # LOGPIXELSX
        user32.ReleaseDC(0, dc)
        return max(1.0, dpi / 96.0)
    except Exception:
        return 1.0


def list_windows(class_keywords=(), title_keywords=()):
    """枚举顶层窗口，返回 [(hwnd, class_name, title), ...]。"""
    _require_windows()
    bind_default_desktop()
    out = []

    def _proc(hwnd, _lp):
        cb = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cb, 256)
        cls = cb.value
        tb = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, tb, 512)
        title = tb.value
        if class_keywords and not any(k.lower() in cls.lower() for k in class_keywords):
            return True
        if title_keywords and not any(k.lower() in title.lower() for k in title_keywords):
            return True
        if not user32.IsWindowVisible(hwnd):
            return True
        out.append((hwnd, cls, title))
        return True

    user32.EnumWindows(WNDENUMPROC(_proc), 0)
    return out


def find_window(class_keywords=(), title_keywords=(), exclude_titles=()):
    """按类名/标题找主窗口；找不到返回 (None, None, None)。"""
    cands = list_windows(class_keywords, title_keywords)
    for hwnd, cls, title in cands:
        if any(x and x == title for x in exclude_titles):
            continue
        return hwnd, cls, title
    return None, None, None


def window_rect(hwnd):
    """返回 (left, top, right, bottom)。"""
    _require_windows()
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def client_size(hwnd):
    """返回客户区 (w, h)。"""
    _require_windows()
    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    return r.right - r.left, r.bottom - r.top


def capture(hwnd):
    """PrintWindow 离屏抓图，返回 PIL.Image（RGB）或 None。

    优先 PW_RENDERFULLCONTENT(2)，失败回退 0；全黑则用屏幕截图兜底。
    """
    _require_windows()
    from PIL import Image, ImageGrab

    try:
        left, top, right, bottom = window_rect(hwnd)
        w, h = right - left, bottom - top
        if w <= 0 or h <= 0:
            w, h = client_size(hwnd)
            left, top = 0, 0
        if w <= 0 or h <= 0:
            return None

        hwnd_dc = mfc_dc = bmp = None
        try:
            hwnd_dc = user32.GetWindowDC(hwnd)
            mfc_dc = gdi32.CreateCompatibleDC(hwnd_dc)
            bmp = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
            gdi32.SelectObject(mfc_dc, bmp)

            ok = user32.PrintWindow(hwnd, mfc_dc, 2)
            if not ok:
                ok = user32.PrintWindow(hwnd, mfc_dc, 0)
            if not ok:
                return None

            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD),
                ]

            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = w
            bmi.biHeight = -h
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0

            buf = ctypes.create_string_buffer(w * h * 4)
            gdi32.GetDIBits(mfc_dc, bmp, 0, h, buf, ctypes.byref(bmi), 0)
            img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
        finally:
            if bmp:
                gdi32.DeleteObject(bmp)
            if mfc_dc:
                gdi32.DeleteDC(mfc_dc)
            if hwnd_dc:
                user32.ReleaseDC(hwnd, hwnd_dc)

        # 全黑说明 D3D/独占渲染抓不到，退回屏幕截图
        extrema = img.convert("L").getextrema()
        if extrema[1] <= 10:
            if left > -10000 and top > -10000:
                s = dpi_scale()
                box = (int(left * s), int(top * s), int(right * s), int(bottom * s))
                return ImageGrab.grab(bbox=box).convert("RGB")
        return img
    except Exception:
        return None


def activate(hwnd, settle=0.03):
    """把窗口提到前台（绕过 Windows 防抢焦点限制）。"""
    _require_windows()
    try:
        bind_default_desktop()
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            time.sleep(0.04)

        fg = user32.GetForegroundWindow()
        fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        target_thread = user32.GetWindowThreadProcessId(hwnd, None)
        my_thread = kernel32.GetCurrentThreadId()

        attached_fg = attached_my = False
        try:
            if fg_thread and fg_thread != target_thread:
                attached_fg = bool(user32.AttachThreadInput(fg_thread, target_thread, True))
            if my_thread != target_thread:
                attached_my = bool(user32.AttachThreadInput(my_thread, target_thread, True))
            user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0003 | 0x0040)  # HWND_TOPMOST
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            user32.SwitchToThisWindow(hwnd, True)
            user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0003)  # HWND_NOTOPMOST
        finally:
            if attached_fg:
                user32.AttachThreadInput(fg_thread, target_thread, False)
            if attached_my:
                user32.AttachThreadInput(my_thread, target_thread, False)

        time.sleep(settle)
        return user32.GetForegroundWindow() == hwnd
    except Exception:
        return False


def move_offscreen(hwnd, dx=-32000, dy=-32000):
    """把窗口挪到屏幕外（虚拟离屏挂载），物理桌面看不到但仍在渲染。"""
    _require_windows()
    left, top, right, bottom = window_rect(hwnd)
    w, h = right - left, bottom - top
    # SWP_NOSIZE=0x1 | SWP_NOZORDER=0x4 | SWP_NOACTIVATE=0x10
    return bool(user32.SetWindowPos(hwnd, 0, dx, dy, w, h, 0x1 | 0x4 | 0x10))


def restore_position(hwnd, x, y):
    _require_windows()
    left, top, right, bottom = window_rect(hwnd)
    w, h = right - left, bottom - top
    return bool(user32.SetWindowPos(hwnd, 0, x, y, w, h, 0x1 | 0x4 | 0x10))


def click_client(hwnd, x, y, hold_ms=20):
    """向客户区坐标 (x, y) 投递鼠标点击，物理光标不动。"""
    _require_windows()
    try:
        lp = (int(y) << 16) | (int(x) & 0xFFFF)
        user32.PostMessageW(hwnd, 0x0200, 0, lp)      # WM_MOUSEMOVE
        time.sleep(0.008)
        user32.PostMessageW(hwnd, 0x0201, 0x0001, lp)  # WM_LBUTTONDOWN
        time.sleep(hold_ms / 1000.0)
        user32.PostMessageW(hwnd, 0x0202, 0, lp)       # WM_LBUTTONUP
        return True
    except Exception:
        return False


def right_click_client(hwnd, x, y):
    _require_windows()
    try:
        lp = (int(y) << 16) | (int(x) & 0xFFFF)
        user32.PostMessageW(hwnd, 0x0200, 0, lp)
        user32.PostMessageW(hwnd, 0x0204, 0x0002, lp)  # WM_RBUTTONDOWN
        time.sleep(0.02)
        user32.PostMessageW(hwnd, 0x0205, 0, lp)       # WM_RBUTTONUP
        return True
    except Exception:
        return False


# 常用虚拟键码
VK = {
    "ESC": 0x1B, "SPACE": 0x20, "ENTER": 0x0D, "TAB": 0x09,
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73, "F5": 0x74,
    "F6": 0x75, "F7": 0x76, "F8": 0x77, "F9": 0x78, "F10": 0x79,
    "F11": 0x7A, "F12": 0x7B,
    "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34, "5": 0x35,
    "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39, "0": 0x30,
}


def key_down(hwnd, key):
    _require_windows()
    vk = VK.get(str(key).upper(), None)
    if vk is None:
        vk = ord(str(key).upper()[:1])
    scan = user32.MapVirtualKeyW(vk, 0)
    lp = 1 | (scan << 16)
    user32.PostMessageW(hwnd, 0x0100, vk, lp)  # WM_KEYDOWN
    return True


def key_up(hwnd, key):
    _require_windows()
    vk = VK.get(str(key).upper(), None)
    if vk is None:
        vk = ord(str(key).upper()[:1])
    scan = user32.MapVirtualKeyW(vk, 0)
    lp = 1 | (scan << 16) | (1 << 30) | (1 << 31)
    user32.PostMessageW(hwnd, 0x0101, vk, lp)  # WM_KEYUP
    return True


def press_key(hwnd, key, hold_ms=30):
    """按一下键（按下+抬起）。"""
    key_down(hwnd, key)
    time.sleep(hold_ms / 1000.0)
    key_up(hwnd, key)
    return True
