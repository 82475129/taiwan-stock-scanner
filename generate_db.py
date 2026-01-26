# generate_db.py - 更新版：抓取 Yahoo 股市目前有效的電子細分類
import requests
import re
from bs4 import BeautifulSoup
import json
import time

DB_FILE = "electronic_stocks_db.json"

# 目前（2026年）仍有效的電子相關 sectorId
# 來源：直接訪問 tw.stock.yahoo.com/class-quote 頁面觀察
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
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        r = requests.get(url, headers=headers, timeout=12)
        if r.status_code != 200:
            print(f"請求失敗 {url} → status {r.status_code}")
            return {}
        
        soup = BeautifulSoup(r.text, "html.parser")
        
        stocks = {}
        # 目前 Yahoo 類股頁面的 row 結構仍是 flex div
        rows = soup.find_all("div", class_=re.compile(r"table-row|D\(f\).*?Ai\(c\)"))
        
        for row in rows:
            # 名稱區塊（通常是較粗體）
            name_div = row.find("div", class_=re.compile(r"Lh\(.*?Fw\(600\)"))
            # 代碼區塊（通常灰色小字）
            code_span = row.find("span", class_=re.compile(r"Fz\(.*?C\(#.*?Ell"))
            
            if name_div and code_span:
                name = name_div.get_text(strip=True)
                sid = code_span.get_text(strip=True).strip()
                
                # 驗證格式：1234.TW 或 1234.TWO
                if re.match(r"^\d{4}\.(TW|TWO)$", sid):
                    stocks[sid] = {
                        "name": name,
                        "category": f"電子-{category_name}"  # 細分電子子類別
                    }
        
        print(f"{exchange} sector {sector_id} ({category_name}) → 取得 {len(stocks)} 檔")
        return stocks
    
    except Exception as e:
        print(f"抓取 {url} 失敗：{e}")
        return {}


def main():
    full_db = {}
    
    # 上市電子類
    for sid, cat_name in ELECTRONIC_TAI_IDS.items():
        stocks = fetch_sector(sid, "TAI", cat_name)
        full_db.update(stocks)
        time.sleep(1.2)  # 避免太快被 ban
    
    # 上櫃電子類
    for sid, cat_name in ELECTRONIC_TWO_IDS.items():
        stocks = fetch_sector(sid, "TWO", cat_name)
        full_db.update(stocks)
        time.sleep(1.2)
    
    num_stocks = len(full_db)
    if num_stocks > 0:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(full_db, f, ensure_ascii=False, indent=2)
        print(f"\n成功產生 electronic_stocks_db.json，共 {num_stocks} 檔電子股！")
        print("範例：", list(full_db.items())[:3])
    else:
        print("抓取完全失敗，JSON 為空。請檢查網路或 Yahoo 頁面是否又改版。")


if __name__ == "__main__":
    main()
