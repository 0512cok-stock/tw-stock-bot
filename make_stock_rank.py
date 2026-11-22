import datetime as dt
import os
import requests
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Noto Sans CJK TC", "Noto Sans CJK JP", "Noto Sans CJK SC"]
plt.rcParams["axes.unicode_minus"] = False

URL = "https://www.twse.com.tw/rwd/zh/fund/T86"


def fetch(day):
    r = requests.get(
        URL,
        params={"date": day.strftime("%Y%m%d"), "selectType": "ALLBUT0999", "response": "json"},
        headers={"User-Agent": "Mozilla/5.0"},
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


def to_zhang(s):
    return int(s.replace(",", "")) / 1000


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
        data = fetch(today - dt.timedelta(days=i))
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

    fig.suptitle(f"{date_text} 外資、投信買賣超排行(上市,單位:張)", fontsize=22)
    fig.text(0.5, 0.01, "資料來源:臺灣證券交易所 · 僅供參考,不構成投資建議",
             ha="center", fontsize=11, color="#666")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95), h_pad=3, w_pad=3)
    fig.savefig("rank.png")
    print("完成:rank.png")


main()
