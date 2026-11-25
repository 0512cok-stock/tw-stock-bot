import datetime as dt
import requests
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Noto Sans CJK TC", "Noto Sans CJK JP", "Noto Sans CJK SC"]
plt.rcParams["axes.unicode_minus"] = False

TWSE_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap05_L"
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
MIN_FOUND = 45  # 50 家裡至少要找到幾家才發文
FINANCIAL = {"2881", "2891", "2882", "2887", "2885", "2884",
             "2886", "2890", "2883", "2892", "2880", "5880"}


def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=60)
        r.raise_for_status()
        return [{k.strip().lstrip("\ufeff"): v for k, v in d.items()} for d in r.json()]
    except Exception as e:
        print(f"讀取失敗 {url}:{e}")
        return []


def to_float(s):
    try:
        return float(str(s).replace(",", "").strip())
    except ValueError:
        return None


def parse(rows, ym):
    out = {}
    for r in rows:
        if str(r.get("資料年月", "")).strip() != ym:
            continue
        code = str(r.get("公司代號", "")).strip()
        name = str(r.get("公司名稱", "")).strip()
        rev = to_float(r.get("營業收入-當月營收"))
        yoy = to_float(r.get("營業收入-去年同月增減(%)"))
        if code and rev is not None and yoy is not None:
            out[code] = (name, rev, yoy)
    if rows and not out:
        print(f"沒有符合 {ym} 的資料,第一筆內容:", list(rows[0].items())[:6])
    return out


def load_codes():
    codes = []
    with open("0050_list.txt", encoding="utf-8") as f:
        for line in f:
            line = line.split("#")[0].strip()
            if line:
                codes.append(line)
    return codes


def panel(ax, items, title):
    labels = [n for n, _ in items][::-1]
    vals = [v for _, v in items][::-1]
    colors = ["#e53935" if v >= 0 else "#2e7d32" for v in vals]
    ax.barh(labels, vals, color=colors)
    ax.set_title(title, fontsize=17, pad=12)
    for i, v in enumerate(vals):
        ax.annotate(
            f"{v:+,.1f}%",
            (v, i),
            ha="left" if v >= 0 else "right",
            va="center",
            fontsize=10,
            xytext=(4 if v >= 0 else -4, 0),
            textcoords="offset points",
        )
    ax.axvline(0, color="#888", linewidth=1)
    ax.margins(x=0.25)
    ax.tick_params(axis="y", labelsize=11)
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)


def main():
    tw = dt.timezone(dt.timedelta(hours=8))
    today = dt.datetime.now(tw).date()
    y, m = today.year, today.month - 1
    if m == 0:
        y, m = y - 1, 12
    ym = f"{y - 1911}{m:02d}"  # 民國年月,例如 11510

    codes = load_codes()
    twse = parse(fetch(TWSE_URL), ym)
    tpex = parse(fetch(TPEX_URL), ym)
    data = {**tpex, **twse}
    print(f"月營收資料 {ym}:上市 {len(twse)} 家、上櫃 {len(tpex)} 家")

    found = [c for c in codes if c in data]
    missing = [c for c in codes if c not in data]
    print(f"0050 成分股:找到 {len(found)}/{len(codes)} 家")
    if missing:
        print("尚未找到:", missing)
    if len(found) < MIN_FOUND:
        print("營收資料尚未公布完整,不發文")
        raise SystemExit(0)

    items = sorted(
        ((f"{c} {data[c][0]}", data[c][1], data[c][2]) for c in found if c not in FINANCIAL),
        key=lambda x: x[2],
        reverse=True,
    )
    half = (len(items) + 1) // 2
    left = [(n, yo) for n, _, yo in items[:half]]
    right = [(n, yo) for n, _, yo in items[half:]]
    up = sum(1 for _, _, yo in items if yo > 0)
    down = len(items) - up

    fig, axes = plt.subplots(1, 2, figsize=(16, 13), dpi=110)
    panel(axes[0], left, f"年增率較高(第 1~{half} 名)")
    panel(axes[1], right, f"年增率較低(第 {half + 1}~{len(items)} 名)")
    fig.suptitle(f"{y}年{m}月 0050成分股月營收年增率(不含金融股,共 {len(items)} 家)", fontsize=22)
    fig.text(0.5, 0.01, "資料來源:公開資訊觀測站(證交所、櫃買中心開放資料) · 僅供參考,不構成投資建議",
             ha="center", fontsize=11, color="#666")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95), w_pad=3)
    fig.savefig("rev.png")

    best, worst = items[0], items[-1]
    lines = [
        f"{y}年{m}月 0050成分股月營收年增率排行(不含金融股,{len(items)} 家)",
        f"年增率最高:{best[0]}({best[2]:+,.1f}%)",
        f"年增率最低:{worst[0]}({worst[2]:+,.1f}%)",
    ]
    tsmc = data.get("2330")
    if tsmc:
        lines.append(f"台積電:當月營收 {tsmc[1] / 1e5:,.0f} 億元,年增 {tsmc[2]:+,.1f}%")
    lines.append(f"{len(items)} 家中 {up} 家營收年增、{down} 家年減。")
    caption = "\n".join(lines) + "\n\n資料來源:公開資訊觀測站(證交所、櫃買中心開放資料)\n僅供參考,不構成投資建議。"
    with open("caption_rev.txt", "w", encoding="utf-8") as f:
        f.write(caption)
    print("完成:rev.png")


main()
