"""分层自检：在真实 Windows + 游戏客户端上逐层验证，定位断在哪一步。

用法：
    python tools\\selftest.py                 # 只读检查（不点击）
    python tools\\selftest.py --click         # 额外测一次点击落点
    python tools\\selftest.py --title 传奇     # 指定窗口标题关键词

输出：控制台逐项 PASS/FAIL + logs/selftest/ 下的截图与报告
"""
import argparse
import json
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

OUT_DIR = os.path.join(BASE_DIR, "logs", "selftest")


class Report:
    def __init__(self):
        self.items = []

    def add(self, step, ok, detail=""):
        self.items.append({"step": step, "ok": bool(ok), "detail": str(detail)})
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {step}" + (f" — {detail}" if detail else ""), flush=True)

    @property
    def all_ok(self):
        return all(i["ok"] for i in self.items)

    def save(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.items, f, ensure_ascii=False, indent=2)


def step_platform(rep):
    import platform
    ok = sys.platform == "win32"
    rep.add("1. 平台", ok, f"{platform.platform()} / python {platform.python_version()}"
            + ("" if ok else "（非 Windows，后续步骤会跳过）"))
    return ok


def step_deps(rep):
    missing = []
    for mod in ("PIL", "numpy", "requests", "pyperclip"):
        try:
            __import__(mod)
        except Exception:
            missing.append(mod)
    try:
        __import__("rapidocr_onnxruntime")
    except Exception:
        missing.append("rapidocr_onnxruntime")
    rep.add("2. 依赖", not missing,
            "全部就绪" if not missing else f"缺 {missing} → pip install -r requirements-mir.txt")
    return not missing


def step_window(rep, title_kw):
    from core import win32api as w32
    kws = [title_kw] if title_kw else ["传奇", "Mir", "Legend"]
    hwnd, cls, title = w32.find_window(title_keywords=kws)
    if hwnd:
        w, h = w32.client_size(hwnd)
        rep.add("3. 找窗口", True, f"hwnd={hwnd} class={cls} title={title!r} client={w}x{h}")
        return hwnd
    # 找不到就列出所有可见窗口，方便用户挑关键词
    cands = w32.list_windows()
    listing = [f"{c} | {t!r}" for _h, c, t in cands if t][:15]
    rep.add("3. 找窗口", False,
            f"关键词 {kws} 未命中。当前可见窗口（类名 | 标题）：\n    " + "\n    ".join(listing))
    return None


def step_capture(rep, hwnd):
    from core import win32api as w32
    t0 = time.time()
    img = w32.capture(hwnd)
    cost = (time.time() - t0) * 1000
    if img is None:
        rep.add("4. 抓图", False, "返回 None（游戏可能独占全屏）")
        return None
    path = os.path.join(OUT_DIR, "capture.png")
    os.makedirs(OUT_DIR, exist_ok=True)
    img.save(path)
    gray = img.convert("L")
    lo, hi = gray.getextrema()
    ratio_bright = sum(1 for p in gray.resize((80, 60)).getdata() if p > 20) / 4800.0
    ok = hi > 30 and ratio_bright > 0.05
    rep.add("4. 抓图", ok, f"{img.size[0]}x{img.size[1]} 耗时{cost:.0f}ms "
                           f"亮度{lo}-{hi} 非黑占比{ratio_bright:.0%} → {path}")
    return img


def step_bars(rep, img, cfg):
    from core import vision
    from games.mir2 import layout as lay
    layout = lay.get_layout(cfg.get("layout"))
    hp = vision.bar_ratio(img, layout["hp_bar"])
    mp = vision.bar_ratio(img, layout["mp_bar"])
    ok = hp > 0.01 or mp > 0.01
    rep.add("5. 血/蓝条读数", ok,
            f"hp={hp:.2f} mp={mp:.2f}" +
            ("" if ok else " → 两条都是 0，说明 layout 坐标不对，需要校准"))
    return hp, mp


def step_ocr(rep, img, cfg):
    from core import ocr
    from games.mir2 import layout as lay
    layout = lay.get_layout(cfg.get("layout"))
    try:
        texts = ocr.ocr_region(img, layout["view"], min_score=0.4)
    except Exception as e:
        rep.add("6. OCR 主视野", False, f"OCR 初始化/识别失败：{e}")
        return []
    shown = [t for t, _b, _s in texts][:12]
    rep.add("6. OCR 主视野", bool(texts),
            f"识别到 {len(texts)} 条：" + (" / ".join(shown) if shown else "空白，可能是视野区没框对"))
    names = cfg.get("monster_names") or []
    if names:
        hits = [t for t, _b, _s in texts if any(n in t for n in names)]
        rep.add("6b. 怪物名匹配", bool(hits),
                f"命中 {hits}" if hits else f"视野里没有 {names} 中的名字（旁边有怪时才有输出）")
    return texts


def step_click(rep, hwnd, img):
    from core import win32api as w32
    from core import vision
    w, h = img.size
    x, y = int(w * 0.6), int(h * 0.45)
    before = w32.capture(hwnd)
    w32.click_client(hwnd, x, y)
    time.sleep(0.6)
    after = w32.capture(hwnd)
    if before is None or after is None:
        rep.add("7. 点击落点", False, "点击前后抓图失败，无法比对")
        return
    d = vision.diff_ratio(before, after, [0.2, 0.05, 0.95, 0.85])
    rep.add("7. 点击落点", d > 0.0005,
            f"点击({x},{y})后画面变化 {d:.3%}" +
            ("" if d > 0.0005 else " → 消息没生效（窗口可能拒绝 PostMessage 或点在了空地上）"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", default="")
    ap.add_argument("--click", action="store_true")
    ap.add_argument("--config", default=os.path.join(BASE_DIR, "mir_config.json"))
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    rep = Report()
    print("=== 传奇挂机分层自检 ===")

    if not step_platform(rep):
        rep.save(os.path.join(OUT_DIR, "report.json"))
        print("\n非 Windows：只能验证依赖，其余步骤跳过。")
        return 1

    if not step_deps(rep):
        rep.save(os.path.join(OUT_DIR, "report.json"))
        return 1

    cfg = {}
    path = args.config if os.path.exists(args.config) else os.path.join(
        BASE_DIR, "games", "mir2", "config.example.json")
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
        rep.add("2b. 配置", True, path)
    except Exception as e:
        rep.add("2b. 配置", False, f"{path}: {e}")

    hwnd = step_window(rep, args.title)
    if not hwnd:
        rep.save(os.path.join(OUT_DIR, "report.json"))
        print("\n窗口没找到，后面全部跳过。把上面列出的标题关键词填进 config 的 window_title_keywords。")
        return 2

    img = step_capture(rep, hwnd)
    if img is None:
        rep.save(os.path.join(OUT_DIR, "report.json"))
        return 3

    step_bars(rep, img, cfg)
    step_ocr(rep, img, cfg)
    if args.click:
        step_click(rep, hwnd, img)

    report_path = os.path.join(OUT_DIR, "report.json")
    rep.save(report_path)
    print(f"\n截图：{os.path.join(OUT_DIR, 'capture.png')}")
    print(f"报告：{report_path}")
    print("结论：" + ("全部通过" if rep.all_ok else "有 FAIL 项，按上面提示校准后再跑"))
    return 0 if rep.all_ok else 4


if __name__ == "__main__":
    sys.exit(main())
