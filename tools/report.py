"""指标报表：把 data/metrics.db 导出成控制台表格 / CSV / HTML。

用法：
    python tools/report.py                 # 控制台
    python tools/report.py --csv out.csv
    python tools/report.py --html out.html --hours 24
"""
import argparse
import os
import sqlite3
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE_DIR, "data", "metrics.db")

KINDS = ["attack", "loot", "potion", "death", "unstick", "resupply", "health"]


def query(db, hours):
    since = time.time() - hours * 3600
    con = sqlite3.connect(db)
    try:
        rows = con.execute(
            "SELECT account, kind, COUNT(*), COALESCE(SUM(value),0) FROM events "
            "WHERE ts>=? GROUP BY account, kind", (since,)).fetchall()
        snaps = con.execute(
            "SELECT account, MAX(ts) FROM snapshots GROUP BY account").fetchall()
    finally:
        con.close()

    data = {}
    for acct, kind, cnt, total in rows:
        data.setdefault(acct, {})[kind] = {"count": int(cnt), "sum": float(total)}
    last = {a: t for a, t in snaps}
    return data, last


def render_table(data, last, hours):
    accounts = sorted(data)
    if not accounts:
        print(f"最近 {hours} 小时没有数据")
        return
    head = f"{'角色':<12}{'攻击':>8}{'拾取':>8}{'喝药':>8}{'死亡':>8}{'脱困':>8}{'补给':>8}{'异常':>8}  最后活跃"
    print(head)
    print("-" * len(head))
    for a in accounts:
        d = data[a]
        cells = [d.get(k, {}).get("count", 0) for k in KINDS]
        ts = last.get(a)
        stamp = time.strftime("%m-%d %H:%M", time.localtime(ts)) if ts else "-"
        print(f"{a:<12}" + "".join(f"{c:>8}" for c in cells) + f"  {stamp}")


def write_csv(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        f.write("account," + ",".join(KINDS) + "\n")
        for a in sorted(data):
            f.write(a + "," + ",".join(str(data[a].get(k, {}).get("count", 0)) for k in KINDS) + "\n")


def write_html(path, data, last, hours):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    rows = []
    for a in sorted(data):
        cells = "".join(f"<td>{data[a].get(k, {}).get('count', 0)}</td>" for k in KINDS)
        ts = last.get(a)
        stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "-"
        rows.append(f"<tr><td>{a}</td>{cells}<td>{stamp}</td></tr>")
    html = f"""<!doctype html><meta charset="utf-8">
<title>传奇挂机报表</title>
<style>
body{{font-family:system-ui,-apple-system,"Microsoft YaHei",sans-serif;margin:32px;background:#111;color:#eee}}
table{{border-collapse:collapse;margin-top:16px}}
th,td{{padding:8px 14px;border-bottom:1px solid #333;text-align:right}}
th:first-child,td:first-child{{text-align:left}}
h1{{font-size:20px}}
.muted{{color:#888;font-size:13px}}
</style>
<h1>传奇挂机报表</h1>
<p class="muted">统计窗口：最近 {hours} 小时 · 生成于 {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
<table>
<tr><th>角色</th>{''.join(f'<th>{k}</th>' for k in KINDS)}<th>最后活跃</th></tr>
{''.join(rows)}
</table>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--csv", default="")
    ap.add_argument("--html", default="")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print(f"没有指标库：{args.db}（还没跑过挂机？）")
        return 2

    data, last = query(args.db, args.hours)
    render_table(data, last, args.hours)
    if args.csv:
        write_csv(args.csv, data)
        print(f"\nCSV → {args.csv}")
    if args.html:
        write_html(args.html, data, last, args.hours)
        print(f"HTML → {args.html}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
