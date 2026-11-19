import datetime as dt
import requests

URL = "https://www.twse.com.tw/rwd/zh/fund/BFI82U"


def fetch(day):
    r = requests.get(
        URL,
        params={"type": "day", "dayDate": day.strftime("%Y%m%d"), "response": "json"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    j = r.json()
    if j.get("stat") != "OK":
        return None
    return j


def main():
    tw = dt.timezone(dt.timedelta(hours=8))
    today = dt.datetime.now(tw).date()

    data = None
    for i in range(8):  # 今天沒資料就往前找,最多找 8 天
        day = today - dt.timedelta(days=i)
        data = fetch(day)
        if data:
            break

    if not data:
        print("找不到資料")
        return

    print("資料日期:", data["date"])
    for row in data["data"]:
        name = row[0]
        diff = int(row[3].replace(",", ""))
        print(f"{name}:買賣超 {diff / 1e8:+.1f} 億")


main()
