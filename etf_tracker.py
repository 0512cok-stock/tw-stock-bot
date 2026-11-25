import datetime as dt
import html as htmllib
import io
import json
import os
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import pandas as pd
import requests
import urllib3

urllib3.disable_warnings()

plt.rcParams["font.sans-serif"] = ["Noto Sans CJK TC", "Noto Sans CJK JP", "Noto Sans CJK SC"]
plt.rcParams["axes.unicode_minus"] = False

ETF_CODE = "00981A"
ETF_NAME = "主動統一台股增長"
FUND_CODE = "49YTW"  # 統一投信官網(ezmoney)的基金代碼
BASE = "https://www.ezmoney.com.tw"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
MAX_ROWS = 10  # 每一類最多畫幾列
RED, GREEN = "#c62828", "#2e7d32"


# ---------- 抓資料 ----------
def fetch_raw(fund_code):
    s = requests.Session()
    s.headers.update(UA)
    page = f"{BASE}/ETF/Fund/Info?fundCode={fund_code}"
    r = s.get(page, timeout=60, verify=False)
    r.raise_for_status()
    r2 = s.get(
        f"{BASE}/ETF/Fund/AssetExcelNPOI",
        params={"fundCode": fund_code},
        headers={"Referer": page},
        timeout=60,
        verify=False,
    )
    r2.raise_for_status()
    return r.text, r2.content


def num(x):
    if x is None:
        return None
    t = re.sub(r"[^0-9.\-]", "", str(x))
    if t in ("", "-", ".", "-."):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def parse_excel(content):
    df = pd.read_excel(io.BytesIO(content), header=None, dtype=str).fillna("")
    rows = df.values.tolist()

    date = None
    for r in rows[:6]:
        m = re.search(r"(\d{2,3})/(\d{1,2})/(\d{1,2})", str(r[0]))
        if m:
            date = dt.date(int(m.group(1)) + 1911, int(m.group(2)), int(m.group(3))).isoformat()
            break
    if not date:
        raise ValueError("找不到資料日期")

    info = {"date": date}
    for r in rows:
        k = str(r[0]).strip()
        if k == "淨資產" and "nav" not in info:
            info["nav"] = num(r[1])
        elif k == "流通在外單位數" and "units" not in info:
            info["units"] = num(r[1])
        elif k == "每單位淨值" and "nav_per_unit" not in info:
            info["nav_per_unit"] = num(r[1])

    stocks = {}
    futures = []
    for i, r in enumerate(rows):
        k = str(r[0]).strip()
        if k == "股票代號":
            for row in rows[i + 1:]:
                code = str(row[0]).strip()
                shares = num(row[2])
                if not code or shares is None:
                    break
                stocks[code] = {"name": str(row[1]).strip(), "shares": int(shares), "weight": num(row[3]) or 0.0}
        elif k == "期貨代號":
            for row in rows[i + 1:]:
                code = str(row[0]).strip()
                lots = num(row[3])
                if not code or lots is None:
                    break
                futures.append({"code": code, "name": str(row[1]).strip(), "weight": num(row[2]) or 0.0, "lots": int(lots)})

    if not info.get("nav") or len(stocks) < 10:
        raise ValueError(f"Excel 內容異常:淨資產={info.get('nav')},股票 {len(stocks)} 檔")
    info["stocks"] = stocks
    info["futures"] = futures
    return info


def parse_prices(page_html):
    """網頁內嵌的資料含每檔股票的股數與金額,相除就是當天收盤價"""
    m = re.search(r'id="DataAsset"\s+data-content="(.*?)"', page_html, re.S)
    if not m:
        return {}
    try:
        items = json.loads(htmllib.unescape(m.group(1)))
    except ValueError:
        return {}
    out = {}
    for it in items:
        if it.get("AssetCode") != "ST":
            continue
        code = str(it.get("DetailCode", "")).strip()
        try:
            share, amt = float(it.get("Share")), float(it.get("Amount"))
        except (TypeError, ValueError):
            continue
        if code and share > 0 and amt > 0:
            out[code] = amt / share
    return out


def build_snapshot(page_html, content):
    snap = parse_excel(content)
    prices = parse_prices(page_html)
    from_page = 0
    for code, s in snap["stocks"].items():
        p = prices.get(code)
        if p:
            from_page += 1
        elif s["shares"] > 0:
            p = s["weight"] / 100 * snap["nav"] / s["shares"]  # 備用:用權重反推
        s["price"] = round(p, 4) if p else None
    print(f"收盤價:網頁取得 {from_page} 檔,其餘用權重反推")
    snap["fund"] = ETF_CODE
    return snap


# ---------- 比對 ----------
def compare(prev, cur):
    rows = []
    unchanged = 0
    for c in set(prev["stocks"]) | set(cur["stocks"]):
        a, b = prev["stocks"].get(c), cur["stocks"].get(c)
        ps = a["shares"] if a else 0
        cs = b["shares"] if b else 0
        d = cs - ps
        if abs(d) < 1000:
            if a and b:
                unchanged += 1
            continue
        price = (b or {}).get("price") or (a or {}).get("price")
        kind = "新增" if ps == 0 else ("剔除" if cs == 0 else ("加碼" if d > 0 else "減碼"))
        rows.append({
            "code": c,
            "name": (b or a)["name"],
            "delta": d / 1000,
            "pct": (d / ps * 100) if ps else None,
            "value": (d * price / 1e8) if price else None,
            "w0": a["weight"] if a else 0.0,
            "w1": b["weight"] if b else 0.0,
            "kind": kind,
        })
    groups = {}
    for kind in ("新增", "加碼", "減碼", "剔除"):
        g = [r for r in rows if r["kind"] == kind]
        g.sort(key=lambda r: abs(r["value"]) if r["value"] is not None else abs(r["delta"]), reverse=True)
        groups[kind] = g
    return groups, unchanged


def md(date_str):
    d = dt.date.fromisoformat(date_str)
    return f"{d.month}/{d.day}"


# ---------- 畫圖 ----------
def render(cur, prev, groups, unchanged, path, demo=False):
    sections = [(k, groups[k][:MAX_ROWS], len(groups[k])) for k in ("加碼", "減碼", "新增", "剔除") if groups[k]]
    n_rows = sum(len(g) + 1 for _, g, _ in sections)
    extra_lines = 3
    h = 3.1 + 0.44 * n_rows + 0.45 * extra_lines + 0.9
    fig = plt.figure(figsize=(10, h), dpi=140, facecolor="white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    ax.set_xlim(0, 100)
    ax.set_ylim(h, 0)  # y 以「英吋」為單位,由上往下
    renderer = fig.canvas.get_renderer()

    ax.text(50, 0.75, f"{ETF_CODE} {md(cur['date'])} 加減碼", ha="center", va="center",
            fontsize=30, fontweight="bold", color="#1b2a49")
    ax.text(50, 1.35, f"{ETF_NAME} · {md(cur['date'])} 持股 vs {md(prev['date'])} · 規模 {cur['nav'] / 1e8:,.0f} 億",
            ha="center", va="center", fontsize=13, color="#555")
    if demo:
        ax.text(50, 1.7, "【示範資料:前一日持股為模擬,並非真實異動】", ha="center", va="center",
                fontsize=12, color="#d81b60", fontweight="bold")

    # 摘要方塊
    boxes = [
        (f"加碼 {len(groups['加碼'])} 檔", "#fdecea", RED),
        (f"減碼 {len(groups['減碼'])} 檔", "#e8f5e9", GREEN),
        (f"新增 {len(groups['新增'])} · 剔除 {len(groups['剔除'])}", "#eceff1", "#455a64"),
    ]
    bw, gap, x0 = 30, 2.5, 3
    for i, (txt, bg, fg) in enumerate(boxes):
        x = x0 + i * (bw + gap)
        ax.add_patch(Rectangle((x, 2.0), bw, 0.6, fc=bg, ec="none"))
        ax.text(x + bw / 2, 2.3, txt, ha="center", va="center", fontsize=15, fontweight="bold", color=fg)

    y = 3.05
    heads = [(3, "標的", "left"), (50, "張數增減", "right"), (62, "增減幅", "right"),
             (77, "增減市值", "right"), (97, "權重 前→後", "right")]
    for x, t, ha in heads:
        ax.text(x, y, t, ha=ha, va="center", fontsize=10.5, color="#777")
    ax.plot([2, 98], [y + 0.2, y + 0.2], color="#222", linewidth=1.2)
    y += 0.5

    for kind, g, total in sections:
        color = RED if kind in ("加碼", "新增") else GREEN
        ax.add_patch(Rectangle((2, y - 0.17), 0.6, 0.34, fc=color, ec="none"))
        label = kind if total <= len(g) else f"{kind}(僅列前 {len(g)} 檔,共 {total} 檔)"
        ax.text(4, y, label, ha="left", va="center", fontsize=14, fontweight="bold", color="#222")
        y += 0.44
        for r in g:
            nm = ax.text(3, y, f"{r['name']}", ha="left", va="center", fontsize=13, fontweight="bold", color="#111")
            bb = nm.get_window_extent(renderer)
            x_end = ax.transData.inverted().transform((bb.x1, bb.y0))[0]
            ax.text(x_end + 1.0, y, r["code"], ha="left", va="center", fontsize=9.5, color="#999")
            ax.text(50, y, f"{r['delta']:+,.0f}", ha="right", va="center", fontsize=13, color=color)
            ax.text(62, y, "—" if r["pct"] is None else f"{r['pct']:+.1f}%", ha="right", va="center", fontsize=12, color=color)
            ax.text(77, y, "—" if r["value"] is None else f"{r['value']:+,.2f} 億", ha="right", va="center", fontsize=12.5, color=color)
            ax.text(97, y, f"{r['w0']:.2f}% → {r['w1']:.2f}%", ha="right", va="center", fontsize=11, color="#444")
            ax.plot([2, 98], [y + 0.22, y + 0.22], color="#e5e5e5", linewidth=0.7)
            y += 0.44

    # 其他資訊
    y += 0.2
    lines = [f"其他持股 {unchanged} 檔張數不變"]
    du = (cur.get("units") or 0) - (prev.get("units") or 0)
    if cur.get("units") and prev.get("units") and cur.get("nav_per_unit") and abs(du) >= 1e6:
        lines[0] += f" · 受益權單位 {du / 1e8:+.2f} 億(估算淨申贖約 {du * cur['nav_per_unit'] / 1e8:+,.1f} 億元)"
    fut_prev = {f["code"]: f for f in prev.get("futures", [])}
    for f in cur.get("futures", []):
        p = fut_prev.get(f["code"])
        s = f"{f['name']} {f['code']} {f['lots']:,} 口"
        if p:
            s += f"(前一日 {p['lots']:,} 口)"
        lines.append(s)
    for t in lines:
        ax.text(3, y, t, ha="left", va="center", fontsize=11, color="#333")
        y += 0.45

    ax.text(50, h - 0.55, "依統一投信公布之每日持股比對前一次公布 · 增減市值以當日收盤價估算 · 資料整理,僅供參考,不構成投資建議",
            ha="center", va="center", fontsize=8.5, color="#777")
    fig.savefig(path)
    plt.close(fig)


def make_caption(cur, prev, groups, unchanged):
    lines = [f"{ETF_CODE} {ETF_NAME} {md(cur['date'])} 持股異動(對照 {md(prev['date'])})"]
    lines.append(f"加碼 {len(groups['加碼'])} 檔、減碼 {len(groups['減碼'])} 檔,新增 {len(groups['新增'])} 檔、剔除 {len(groups['剔除'])} 檔。")

    def top(kind, label):
        g = groups[kind]
        if not g:
            return
        r = g[0]
        v = f"(約 {r['value']:+,.1f} 億元)" if r["value"] is not None else ""
        lines.append(f"{label}:{r['name']} {r['delta']:+,.0f} 張{v}")

    top("加碼", "加碼最多")
    top("減碼", "減碼最多")
    top("新增", "新增")
    top("剔除", "剔除")
    if cur.get("units") and prev.get("units") and cur.get("nav_per_unit") and abs(cur["units"] - prev["units"]) >= 1e6:
        du = cur["units"] - prev["units"]
        lines.append(f"受益權單位 {du / 1e8:+.2f} 億(估算淨申贖約 {du * cur['nav_per_unit'] / 1e8:+,.1f} 億元)")
    lines.append("")
    lines.append("資料來源:統一投信官網每日持股公告")
    lines.append("增減市值以當日收盤價估算 · 僅供參考,不構成投資建議。")
    return "\n".join(lines)


# ---------- 示範模式 ----------
def make_demo_prev(cur):
    prev = json.loads(json.dumps(cur))
    prev["date"] = (dt.date.fromisoformat(cur["date"]) - dt.timedelta(days=1)).isoformat()
    codes = sorted(prev["stocks"])
    for i, c in enumerate(codes):
        s = prev["stocks"][c]
        if s["shares"] < 5000:
            continue
        if i % 4 == 0:
            s["shares"] = int(s["shares"] * 0.93 // 1000 * 1000)
        elif i % 5 == 0:
            s["shares"] = int(s["shares"] * 1.06 // 1000 * 1000)
    prev["stocks"].pop(codes[3], None)  # 讓這檔變成「新增」
    prev["stocks"]["9999"] = {"name": "示範剔除股", "shares": 800000, "weight": 0.3, "price": 50.0}
    prev["units"] = cur["units"] * 1.009
    return prev


# ---------- 主流程 ----------
def main():
    demo = os.environ.get("DEMO") == "true"
    page_html, content = fetch_raw(FUND_CODE)
    cur = build_snapshot(page_html, content)
    print(f"資料日期 {cur['date']},持股 {len(cur['stocks'])} 檔,淨資產 {cur['nav'] / 1e8:,.1f} 億")

    folder = f"data/{ETF_CODE}"
    os.makedirs(folder, exist_ok=True)
    snaps = sorted(f[:-5] for f in os.listdir(folder) if f.endswith(".json"))

    if demo:
        prev = make_demo_prev(cur)
    else:
        if cur["date"] in snaps:
            print("這個日期已經處理過(或官網還沒更新),不重複發文")
            return
        if snaps and cur["date"] < snaps[-1]:
            print("官網資料比已存的快照還舊,略過")
            return
        prev = None
        if snaps:
            with open(f"{folder}/{snaps[-1]}.json", encoding="utf-8") as f:
                prev = json.load(f)
        with open(f"{folder}/{cur['date']}.json", "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=1)
        print("已存下今天的快照")
        if prev is None:
            print("這是第一次執行,沒有前一次的持股可以比對,明天開始發文")
            return

    groups, unchanged = compare(prev, cur)
    print({k: len(v) for k, v in groups.items()}, "不變:", unchanged)
    if not any(groups.values()):
        print("持股完全沒有變動,不發文")
        return
    render(cur, prev, groups, unchanged, "etf.png", demo=demo)
    with open("caption_etf.txt", "w", encoding="utf-8") as f:
        f.write(make_caption(cur, prev, groups, unchanged))
    print("完成:etf.png")


if __name__ == "__main__":
    main()
