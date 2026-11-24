import datetime as dt
import requests
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Noto Sans CJK TC", "Noto Sans CJK JP", "Noto Sans CJK SC"]
plt.rcParams["axes.unicode_minus"] = False

URL = "https://www.twse.com.tw/rwd/zh/fund/BFI82U"


def fetch(day):
    r = requests.get(
        URL,
        params={"type": "day", "dayDate": day.strftime("%Y%m%d"), "response": "json"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    j = r.json()
    return j if j.get("stat") == "OK" else None


def num(row):
    return int(row[3].replace(",", "")) / 1e8


def main():
    tw = dt.timezone(dt.timedelta(hours=8))
    today = dt.datetime.now(tw).date()

    data = None
    for i in range(8):
        data = fetch(today - dt.timedelta(days=i))
        if data:
            break
    if not data:
        raise SystemExit("找不到資料")

    if data["date"] != today.strftime("%Y%m%d"):
        print("今天沒有新資料(休市或尚未公布),不發文")
        raise SystemExit(0)

    rows = {r[0]: num(r) for r in data["data"]}
    foreign = rows["外資及陸資(不含外資自營商)"] + rows["外資自營商"]
    trust = rows["投信"]
    dealer = rows["自營商(自行買賣)"] + rows["自營商(避險)"]
    total = rows["合計"]

    names = ["外資", "投信", "自營商", "三大法人合計"]
    values = [foreign, trust, dealer, total]
    colors = ["#e53935" if v >= 0 else "#2e7d32" for v in values]  # 台股習慣:紅買綠賣

    d = data["date"]
    date_text = f"{d[:4]}/{d[4:6]}/{d[6:]}"

    fig, ax = plt.subplots(figsize=(8, 8), dpi=150)
    bars = ax.bar(names, values, color=colors, width=0.6)
    ax.axhline(0, color="#888", linewidth=1)
    ax.set_title(f"{date_text} 三大法人買賣超(上市,億元)", fontsize=20, pad=20)
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
    fig.text(0.5, 0.01, "資料來源:臺灣證券交易所 · 僅供參考,不構成投資建議",
             ha="center", fontsize=10, color="#666")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig("chart.png")
    def word(v):
        return "買超" if v >= 0 else "賣超"

    caption = (
        f"{date_text} 三大法人買賣超(上市)\n"
        f"外資{word(foreign)} {abs(foreign):.1f} 億、"
        f"投信{word(trust)} {abs(trust):.1f} 億、"
        f"自營商{word(dealer)} {abs(dealer):.1f} 億,"
        f"三大法人合計{word(total)} {abs(total):.1f} 億。\n\n"
        "資料來源:臺灣證券交易所\n僅供參考,不構成投資建議。"
    )
    with open("caption_chart.txt", "w", encoding="utf-8") as f:
        f.write(caption)
    print("完成:chart.png")


main()
