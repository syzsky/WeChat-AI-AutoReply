"""传奇挂机控制中心（Tkinter）。

只做三件事：看状态、改配置、起停守护进程。
真正的挂机逻辑在 apps/mir_bot.py 里跑，GUI 崩了不影响挂机。
"""
import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

CONFIG_PATH = os.path.join(BASE_DIR, "mir_config.json")
EXAMPLE_PATH = os.path.join(BASE_DIR, "games", "mir2", "config.example.json")
LOG_PATH = os.path.join(BASE_DIR, "logs", "mir_bot.log")
STOP_FILE = os.path.join(BASE_DIR, "mir_bot.stop")


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    with open(EXAMPLE_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)


class MirBotGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("传奇挂机控制中心")
        self.geometry("860x620")
        self.proc = None
        self.cfg = load_config()
        self._build()
        self.after(500, self._tick)

    def _build(self):
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")

        self.status_var = tk.StringVar(value="未运行")
        ttk.Label(top, text="状态：").pack(side="left")
        ttk.Label(top, textvariable=self.status_var).pack(side="left", padx=(0, 12))

        ttk.Button(top, text="启动", command=self.start).pack(side="left", padx=2)
        ttk.Button(top, text="停止", command=self.stop).pack(side="left", padx=2)
        ttk.Button(top, text="保存配置", command=self.save).pack(side="left", padx=2)
        ttk.Button(top, text="打开日志", command=self.open_log).pack(side="left", padx=2)

        body = ttk.Frame(self, padding=(8, 0))
        body.pack(fill="both", expand=True)

        left = ttk.LabelFrame(body, text="参数", padding=8)
        left.pack(side="left", fill="y", padx=(0, 8))

        self.vars = {}
        fields = [
            ("window_title_keywords", "窗口标题关键词（逗号分隔）", "list"),
            ("potion_hp_threshold", "喝红阈值(0-1)", "float"),
            ("potion_mp_threshold", "喝蓝阈值(0-1)", "float"),
            ("hp_potion_key", "红药快捷键", "str"),
            ("mp_potion_key", "蓝药快捷键", "str"),
            ("loot_key", "捡物快捷键", "str"),
            ("skill_interval", "技能间隔(秒，0=关)", "float"),
            ("stuck_seconds", "卡位判定(秒)", "float"),
            ("monster_names", "怪物名（逗号分隔）", "list"),
            ("item_names", "物品名（逗号分隔）", "list"),
        ]
        for i, (key, label, kind) in enumerate(fields):
            ttk.Label(left, text=label).grid(row=i, column=0, sticky="w", pady=3)
            var = tk.StringVar()
            val = self.cfg.get(key, "")
            if kind == "list":
                var.set("，".join(val) if isinstance(val, list) else str(val))
            else:
                var.set(str(val))
            ttk.Entry(left, textvariable=var, width=34).grid(row=i, column=1, pady=3)
            self.vars[key] = (var, kind)

        right = ttk.LabelFrame(body, text="运行日志", padding=8)
        right.pack(side="left", fill="both", expand=True)
        self.log_text = tk.Text(right, wrap="none", state="disabled")
        self.log_text.pack(fill="both", expand=True)

    # ---------- 操作 ----------
    def start(self):
        if self.proc and self.proc.poll() is None:
            return
        self.save(silent=True)
        self.proc = subprocess.Popen(
            [sys.executable, os.path.join(BASE_DIR, "apps", "mir_bot.py"),
             "--config", CONFIG_PATH],
            cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.status_var.set(f"运行中 pid={self.proc.pid}")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            time.sleep(0.3)
        self.status_var.set("已停止")

    def save(self, silent=False):
        for key, (var, kind) in self.vars.items():
            raw = var.get().strip()
            if kind == "list":
                self.cfg[key] = [x.strip() for x in raw.replace(",", "，").split("，") if x.strip()]
            elif kind == "float":
                try:
                    self.cfg[key] = float(raw)
                except ValueError:
                    pass
            else:
                self.cfg[key] = raw
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.cfg, f, ensure_ascii=False, indent=2)
        if not silent:
            messagebox.showinfo("提示", "配置已保存（守护进程会自动热重载）")

    def open_log(self):
        if os.path.exists(LOG_PATH):
            os.startfile(LOG_PATH) if hasattr(os, "startfile") else None

    # ---------- 日志轮询 ----------
    def _tick(self):
        try:
            if os.path.exists(LOG_PATH):
                with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()[-200:]
                self.log_text.configure(state="normal")
                self.log_text.delete("1.0", "end")
                self.log_text.insert("end", "".join(lines))
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
            if self.proc:
                alive = self.proc.poll() is None
                self.status_var.set(f"运行中 pid={self.proc.pid}" if alive else "已退出")
        except Exception:
            pass
        self.after(1000, self._tick)


if __name__ == "__main__":
    MirBotGUI().mainloop()
