import re
import requests
import urllib3

urllib3.disable_warnings()

FUND = "49YTW"  # 00981A(統一投信 ezmoney 的基金代碼)
PAGE = f"https://www.ezmoney.com.tw/ETF/Fund/Info?fundCode={FUND}"
EXCEL = f"https://www.ezmoney.com.tw/ETF/Fund/AssetExcelNPOI?fundCode={FUND}"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

s = requests.Session()
s.headers.update(UA)

print("=== 1. 官網頁面 ===")
try:
    r = s.get(PAGE, timeout=60, verify=False)
    html = r.text
    print("狀態:", r.status_code, "長度:", len(html))
    for kw in ("AssetExcel", "DataAsset", "2330"):
        hits = [m.start() for m in re.finditer(kw, html)]
        print(f"『{kw}』出現 {len(hits)} 次")
        if hits:
            i = hits[0]
            print("  前後文:", html[max(0, i - 120): i + 280].replace("\n", " "))
except Exception as e:
    print("頁面讀取失敗:", e)

print("=== 2. 官方 Excel ===")
try:
    r2 = s.get(EXCEL, headers={"Referer": PAGE}, timeout=60, verify=False)
    print("狀態:", r2.status_code, "類型:", r2.headers.get("content-type"), "大小:", len(r2.content))
    if r2.content[:2] == b"PK":
        open("probe.xlsx", "wb").write(r2.content)
        import pandas as pd
        df = pd.read_excel("probe.xlsx", header=None)
        print(df.head(70).to_string())
    else:
        print("不是 Excel,內容開頭:", r2.text[:300].replace("\n", " "))
except Exception as e:
    print("Excel 讀取失敗:", e)
