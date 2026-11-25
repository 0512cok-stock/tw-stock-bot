import datetime as dt
import os
import re
import requests
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Noto Sans CJK TC", "Noto Sans CJK JP", "Noto Sans CJK SC"]
plt.rcParams["axes.unicode_minus"] = False

TWSE_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"
TPEX_URL = "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php"
TPEX_OPENAPI = "https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch_twse(day):
    r = requests.get(
        TWSE_URL,
        params={"date": day.strftime("%Y%m%d"), "selectType": "ALLBUT0999", "response": "json"},
        headers=HEADERS,
        timeout=30,
    )
    j = r.json()
    return j if j.get("stat") == "OK" else None


def find_col(fields, kind):
    for i, f in enumerate(fields):
        if kind == "foreign" and f.startswith(("外陸資", "外資及陸資")) and "買賣超股數" in f:
            return i
        if kind == "trust" and f == "投信買賣超股數":
            return i
    raise SystemExit(f"找不到欄位 {kind},實際欄位:{fields}")


def strip_tags(s):
    return re.sub(r"<[^>]+>", "", str(s)).strip()


def to_int(s):
    try:
        return int(float(strip_tags(s).replace(",", "")))
    except ValueError:
        return None


def to_zhang(s):
    return int(s.replace(",", "")) / 1000


def collect_rows(obj, out):
    """從 JSON 裡找出所有「一列資料」(只含文字或數字的清單)"""
    if isinstance(obj, list):
        if len(obj) >= 2 and all(not isinstance(x, (list, dict)) for x in obj):
            out.append(obj)
        else:
            for x in obj:
                collect_rows(x, out)
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_rows(v, out)


def html_rows(text):
    rows = []
    for tr in re.findall(r"<tr.*?>(.*?)</tr>", text, re.S):
        cells = [strip_tags(c) for c in re.findall(r"<t[dh].*?>(.*?)</t[dh]>", tr, re.S)]
        if cells:
            rows.append(cells)
    return rows


def parse_tpex_rows(rows):
    """
    櫃買欄位排列:代號、名稱,之後每 3 欄一組(買進、賣出、買賣超):
    外資(不含外資自營商)、外資自營商、外資及陸資、投信、自營商…
    用「買進-賣出=買賣超」驗算,找出正確的起始欄位。
    回傳 [(代號 名稱, 外資買賣超張數, 投信買賣超張數), ...]
    """
    parsed = []
    for row in rows:
        if len(row) >= 20:
            parsed.append((row, [to_int(c) for c in row]))
    if not parsed:
        return []

    def ok(cells, s):
        seg = cells[s:s + 12]
        if len(seg) < 12 or None in seg:
            return False
        return seg[0] - seg[1] == seg[2] and seg[9] - seg[10] == seg[11]

    best = max((2, 1, 3), key=lambda s: sum(ok(c, s) for _, c in parsed))
    good = sum(ok(c, best) for _, c in parsed)
    if good < len(parsed) * 0.8:
        return []

    out = []
    for row, cells in parsed:
        if not ok(cells, best):
            continue
        code = strip_tags(row[best - 2])
        name = strip_tags(row[best - 1])
        out.append((f"{code} {name}", cells[best + 2] / 1000, cells[best + 11] / 1000))
    return out


def fetch_tpex(day):
    roc = f"{day.year - 1911}/{day.month:02d}/{day.day:02d}"
    for fmt in ("json", "htm"):
        rows = []
        try:
            r = requests.get(
                TPEX_URL,
                params={"l": "zh-tw", "o": fmt, "se": "EW", "t": "D", "d": roc, "s": "0"},
                headers=HEADERS,
                timeout=60,
            )
            if fmt == "json":
                collect_rows(r.json(), rows)
            else:
                rows = html_rows(r.text)
        except Exception as e:
            print(f"上櫃個股({fmt})讀取失敗:{e}")
            continue
        items = parse_tpex_rows(rows)
        if items:
            print(f"上櫃個股OK({fmt}):{len(items)} 檔")
            return items
        print(f"上櫃個股({fmt})無法辨識,抓到 {len(rows)} 列資料")

    # 備援:OpenAPI(只提供最新一個交易日,所以要確認日期)
    try:
        j = requests.get(TPEX_OPENAPI, headers=HEADERS, timeout=60).json()
        want = f"{day.year - 1911}{day.month:02d}{day.day:02d}"
        rows = []
        for d in j:
            if isinstance(d, dict):
                vals = list(d.values())
                if vals and strip_tags(vals[0]) == want:
                    rows.append(vals)
        items = parse_tpex_rows(rows)
        if items:
            print(f"上櫃個股OK(OpenAPI):{len(items)} 檔")
            return items
        if isinstance(j, list) and j and isinstance(j[0], dict):
            print("上櫃個股(OpenAPI)無法辨識,第一筆欄位:", list(j[0].items())[:6])
    except Exception as e:
        print(f"上櫃個股(OpenAPI)讀取失敗:{e}")
    return None


def panel(ax, items, title, color):
    labels = [n for n, _ in items][::-1]
    vals = [v for _, v in items][::-1]
    ax.barh(labels, vals, color=color)
    ax.set_title(title, fontsize=17, pad=12)
    for i, v in enumerate(vals):
        ax.annotate(
            f"{v:+,.0f}",
            (v, i),
            ha="left" if v >= 0 else "right",
            va="center",
            fontsize=11,
            xytext=(4 if v >= 0 else -4, 0),
            textcoords="offset points",
        )
    ax.margins(x=0.25)
    ax.tick_params(axis="y", labelsize=12)
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)


def main():
    tw = dt.timezone(dt.timedelta(hours=8))
    today = dt.datetime.now(tw).date()
    use_latest = os.environ.get("USE_LATEST") == "true"

    data = None
    for i in range(8 if use_latest else 1):
        data = fetch_twse(today - dt.timedelta(days=i))
        if data:
            break
    if not data:
        print("今天沒有新資料(休市或尚未公布),不發文")
        raise SystemExit(0)

    fields = data["fields"]
    ci = find_col(fields, "foreign")
    ti = find_col(fields, "trust")

    foreign, trust = [], []
    for row in data["data"]:
        label = f"{row[0].strip()} {row[1].strip()}"
        foreign.append((label, to_zhang(row[ci])))
        trust.append((label, to_zhang(row[ti])))

    scope = "上市"
    source = "臺灣證券交易所"
    tpex = fetch_tpex(dt.datetime.strptime(data["date"], "%Y%m%d").date())
    if tpex:
        for label, f, t in tpex:
            foreign.append((label, f))
            trust.append((label, t))
        scope = "上市+上櫃"
        source = "臺灣證券交易所、證券櫃檯買賣中心"
    else:
        print("沒有取得上櫃個股資料,這次只用上市資料")

    foreign.sort(key=lambda x: x[1], reverse=True)
    trust.sort(key=lambda x: x[1], reverse=True)

    d = data["date"]
    date_text = f"{d[:4]}/{d[4:6]}/{d[6:]}"

    fig, axes = plt.subplots(2, 2, figsize=(15, 12), dpi=120)
    red, green = "#e53935", "#2e7d32"
    panel(axes[0][0], foreign[:10], "外資買超前10名", red)
    panel(axes[0][1], trust[:10], "投信買超前10名", red)
    panel(axes[1][0], foreign[::-1][:10], "外資賣超前10名", green)
    panel(axes[1][1], trust[::-1][:10], "投信賣超前10名", green)

    fig.suptitle(f"{date_text} 外資、投信買賣超排行({scope},單位:張)", fontsize=22)
    fig.text(0.5, 0.01, f"資料來源:{source} · 僅供參考,不構成投資建議",
             ha="center", fontsize=11, color="#666")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95), h_pad=3, w_pad=3)
    fig.savefig("rank.png")

    caption = (
        f"{date_text} 外資、投信買賣超排行({scope},單位:張)\n"
        f"外資買超第一名:{foreign[0][0]}({foreign[0][1]:+,.0f} 張)\n"
        f"外資賣超第一名:{foreign[-1][0]}({foreign[-1][1]:+,.0f} 張)\n"
        f"投信買超第一名:{trust[0][0]}({trust[0][1]:+,.0f} 張)\n"
        f"投信賣超第一名:{trust[-1][0]}({trust[-1][1]:+,.0f} 張)\n\n"
        f"資料來源:{source}\n僅供參考,不構成投資建議。"
    )
    with open("caption_rank.txt", "w", encoding="utf-8") as f:
        f.write(caption)
    print("完成:rank.png")


main()
