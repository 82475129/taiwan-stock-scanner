import requests
import re
from bs4 import BeautifulSoup
import json
import time

DB_FILE = "electronic_stocks_db.json"

ELECTRONIC_TAI_IDS = {
    40: "半導體",
    41: "電腦及週邊設備",
    42: "光電",
    43: "通信網路",
    44: "電子零組件",
    45: "電子通路",
    46: "資訊服務",
    47: "其他電子",
}

ELECTRONIC_TWO_IDS = {
    153: "上櫃半導體",
    154: "上櫃電腦及週邊",
    155: "上櫃光電",
    156: "上櫃通信網路",
    157: "上櫃電子零組件",
    158: "上櫃電子通路",
    159: "上櫃資訊服務",
    160: "上櫃其他電子",
}

def fetch_sector(sector_id, exchange, category_name):
    url = f"https://tw.stock.yahoo.com/class-quote?sectorId={sector_id}&exchange={exchange}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}
    
    try:
        r = requests.get(url, headers=headers, timeout=12)
        if r.status_code != 200:
            print(f"失敗 {url} status {r.status_code}")
            return {}
        
        soup = BeautifulSoup(r.text, "html.parser")
        stocks = {}
        rows = soup.find_all("div", class_=re.compile(r"table-row|D\(f\).*?Ai\(c\)"))
        
        for row in rows:
            name_div = row.find("div", class_=re.compile(r"Lh\(.*?Fw\(600\)"))
            code_span = row.find("span", class_=re.compile(r"Fz\(.*?C\(#.*?Ell"))
            if name_div and code_span:
                name = name_div.get_text(strip=True)
                sid = code_span.get_text(strip=True).strip()
                if re.match(r"^\d{4}\.(TW|TWO)$", sid):
                    stocks[sid] = {"name": name, "category": f"電子-{category_name}"}
        
        print(f"{exchange} {category_name} → {len(stocks)} 檔")
        return stocks
    except Exception as e:
        print(f"抓取失敗 {url}: {e}")
        return {}

def main():
    full_db = {}
    for sid, cat in ELECTRONIC_TAI_IDS.items():
        full_db.update(fetch_sector(sid, "TAI", cat))
        time.sleep(1.5)
    for sid, cat in ELECTRONIC_TWO_IDS.items():
        full_db.update(fetch_sector(sid, "TWO", cat))
        time.sleep(1.5)
    
    if full_db:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(full_db, f, ensure_ascii=False, indent=2)
        print(f"成功產生 {len(full_db)} 檔電子股")
    else:
        print("產生失敗，資料庫為空")

if __name__ == "__main__":
    main()
