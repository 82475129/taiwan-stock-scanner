import requests
import re
from bs4 import BeautifulSoup
import json
import time

# 統一檔名
DB_FILE = "taiwan_electronic_stocks.json"

# 分類 ID 定義
SECTORS = {
    "TAI": {40: "半導體", 41: "電腦週邊", 42: "光電", 43: "通信網路", 44: "電子零組件", 45: "電子通路", 46: "資訊服務", 47: "其他電子"},
    "TWO": {153: "上櫃半導體", 154: "上櫃電腦", 155: "上櫃光電", 156: "上櫃通信", 157: "上櫃零組件", 158: "上櫃通路", 159: "上櫃資服", 160: "上櫃其他"}
}

def fetch_all_electronics():
    full_db = {}
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    for exchange, categories in SECTORS.items():
        for sec_id, cat_name in categories.items():
            url = f"https://tw.stock.yahoo.com/class-quote?sectorId={sec_id}&exchange={exchange}"
            try:
                r = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(r.text, "html.parser")
                
                # 抓取包含代號與名稱的區塊
                # Yahoo 結構：代號通常在 <span> 中，名稱在 <div> 中
                items = soup.select('.table-row, .List\(n\)')
                
                count = 0
                for item in items:
                    name_tag = item.select_one('div[class*="Lh(20px)"]')
                    code_tag = item.select_one('span[class*="C(#7c7e80)"]')
                    
                    if name_tag and code_tag:
                        name = name_tag.get_text(strip=True)
                        raw_code = code_tag.get_text(strip=True)
                        # 格式化為 yfinance 需要的格式
                        suffix = ".TW" if exchange == "TAI" else ".TWO"
                        full_code = f"{raw_code}{suffix}"
                        
                        full_db[full_code] = name
                        count += 1
                
                print(f"✅ {cat_name} ({exchange}): 抓取 {count} 檔")
                time.sleep(1) # 避免被封鎖
            except Exception as e:
                print(f"❌ 抓取 {cat_name} 失敗: {e}")
                
    # 儲存檔案
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(full_db, f, ensure_ascii=False, indent=2)
    
    print(f"\n✨ 完成！總共抓取 {len(full_db)} 檔電子股，已存至 {DB_FILE}")

if __name__ == "__main__":
    fetch_all_electronics()
