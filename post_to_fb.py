import os
import sys
import requests

JOBS = {
    "chart": (
        "chart.png",
        "今日三大法人買賣超(上市)\n資料來源:臺灣證券交易所\n僅供參考,不構成投資建議。",
    ),
    "rank": (
        "rank.png",
        "今日外資、投信買賣超排行(上市,單位:張)\n資料來源:臺灣證券交易所\n僅供參考,不構成投資建議。",
    ),
}

job = sys.argv[1] if len(sys.argv) > 1 else "chart"
img, caption = JOBS[job]

if not os.path.exists(img):
    print("沒有圖片,今天不發文")
    raise SystemExit(0)

PAGE_ID = os.environ["FB_PAGE_ID"]
TOKEN = os.environ["FB_PAGE_TOKEN"]

with open(img, "rb") as f:
    r = requests.post(
        f"https://graph.facebook.com/v27.0/{PAGE_ID}/photos",
        data={"caption": caption, "access_token": TOKEN},
        files={"source": f},
        timeout=60,
    )

print(r.status_code, r.text)
r.raise_for_status()
