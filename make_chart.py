import datetime as dt
import re
import requests
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Noto Sans CJK TC", "Noto Sans CJK JP", "Noto Sans CJK SC"]
plt.rcParams["axes.unicode_minus"] = False

TWSE_URL = "https://www.twse.com.tw/rwd/zh/fund/BFI82U"
TPEX_URL = "https://www.tpex.org.tw/web/stock/3insti/3insti_summary/3itrdsum_result.php"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch_twse(day):
    r = requests.get(
        TWSE_URL,
        params={"type": "day", "dayDate": day.strftime("%Y%m%d"), "response": "json"},
        headers=HEADERS,
        timeout=30,
    )
    j = r.json()
    return j if j.get("stat") == "OK" else None


def twse_num(row):
    return int(row[3].replace(",", "")) / 1e8


def strip_tags(s):
    return re.sub(r"<[^>]+>", "", str(s)).strip()


def to_int(s):
    try:
        return int(float(strip_tags(s).replace(",", "")))
    except ValueError:
        return None


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


def fetch_tpex(day):
    """回傳 (外資, 投信, 自營商) 買賣超,單位億元;失敗回傳 None"""
    roc = f"{day.year - 1911}/{day.month:02d}/{day.day:02d}"
    for fmt in ("json", "htm"):
        rows = []
        try:
            r = requests.get(
                TPEX_URL,
                params={"l": "zh-tw", "t": "D", "p": "1", "d": roc, "o": fmt},
                headers=HEADERS,
                timeout=30,
            )
            if fmt == "json":
                collect_rows(r.json(), rows)
            else:
                rows = html_rows(r.text)
        except Exception as e:
            print(f"上櫃({fmt})讀取失敗:{e}")
            continue

        vals = {}
        for row in rows:
            name = strip_tags(row[0])
            v = to_int(row[-1])
            if name and v is not None and name not in vals:
                vals[name] = v / 1e8

        foreign = next((v for k, v in vals.items() if k.startswith("外資及陸資") and "不含" in k), None)
        trust = vals.get("投信")
        dealer = vals.get("自營商合計", vals.get("自營商"))
        if None in (foreign, trust, dealer):
            print(f"上櫃({fmt})欄位無法辨識,抓到的名稱:{list(vals)[:12]}")
            continue
        print(f"上櫃資料OK({fmt}):外資{foreign:.1f} 投信{trust:.1f} 自營商{dealer:.1f}")
        return foreign, trust, dealer
    return None


def main():
    tw = dt.timezone(dt.timedelta(hours=8))
    today = dt.datetime.now(tw).date()

    data = None
    for i in range(8):
        data = fetch_twse(today - dt.timedelta(days=i))
        if data:
            break
    if not data:
        raise SystemExit("找不到資料")

    if data["date"] != today.strftime("%Y%m%d"):
        print("今天沒有新資料(休市或尚未公布),不發文")
        raise SystemExit(0)

    rows = {r[0]: twse_num(r) for r in data["data"]}
    foreign = rows["外資及陸資(不含外資自營商)"] + rows["外資自營商"]
    trust = rows["投信"]
    dealer = rows["自營商(自行買賣)"] + rows["自營商(避險)"]

    scope = "上市"
    source = "臺灣證券交易所"
    tpex = fetch_tpex(dt.datetime.strptime(data["date"], "%Y%m%d").date())
    if tpex:
        foreign += tpex[0]
        trust += tpex[1]
        dealer += tpex[2]
        scope = "上市+上櫃"
        source = "臺灣證券交易所、證券櫃檯買賣中心"
    else:
        print("沒有取得上櫃資料,這次只用上市資料")
    total = foreign + trust + dealer

    names = ["外資", "投信", "自營商", "三大法人合計"]
    values = [foreign, trust, dealer, total]
    colors = ["#e53935" if v >= 0 else "#2e7d32" for v in values]  # 台股習慣:紅買綠賣

    d = data["date"]
    date_text = f"{d[:4]}/{d[4:6]}/{d[6:]}"

    fig, ax = plt.subplots(figsize=(8, 8), dpi=150)
    bars = ax.bar(names, values, color=colors, width=0.6)
    ax.axhline(0, color="#888", linewidth=1)
    ax.set_title(f"{date_text} 三大法人買賣超({scope},億元)", fontsize=20, pad=20)
    ax.tick_params(axis="x", labelsize=15)
    for b, v in zip(bars, values):
        y = b.get_height()
        ax.annotate(
            f"{v:+.1f}",
            (b.get_x() + b.get_width() / 2, y),
            ha="center",
            va="bottom" if v >= 0 else "top",
            fontsize=16,
            xytext=(0, 6 if v >= 0 else -6),
            textcoords="offset points",
        )
    ax.margins(y=0.15)
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    fig.text(0.5, 0.01, f"資料來源:{source} · 僅供參考,不構成投資建議",
             ha="center", fontsize=10, color="#666")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig("chart.png")

    def word(v):
        return "買超" if v >= 0 else "賣超"

    caption = (
        f"{date_text} 三大法人買賣超({scope})\n"
        f"外資{word(foreign)} {abs(foreign):.1f} 億、"
        f"投信{word(trust)} {abs(trust):.1f} 億、"
        f"自營商{word(dealer)} {abs(dealer):.1f} 億,"
        f"三大法人合計{word(total)} {abs(total):.1f} 億。\n\n"
        f"資料來源:{source}\n僅供參考,不構成投資建議。"
    )
    with open("caption_chart.txt", "w", encoding="utf-8") as f:
        f.write(caption)
    print("完成:chart.png")


main()
