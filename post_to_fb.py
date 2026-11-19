import os
import requests

PAGE_ID = os.environ["FB_PAGE_ID"]
TOKEN = os.environ["FB_PAGE_TOKEN"]

caption = (
    "今日三大法人買賣超(上市)\n"
    "資料來源:臺灣證券交易所\n"
    "僅供參考,不構成投資建議。"
)

with open("chart.png", "rb") as f:
    r = requests.post(
        f"https://graph.facebook.com/v27.0/{PAGE_ID}/photos",
        data={"caption": caption, "access_token": TOKEN},
        files={"source": f},
        timeout=60,
    )

print(r.status_code, r.text)
r.raise_for_status()
