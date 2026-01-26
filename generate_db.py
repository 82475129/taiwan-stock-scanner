import requests
import re
from bs4 import BeautifulSoup
import json
import time

DB_FILE = "taiwan_electronic_stocks.json"

# 定義電子股分類 ID (Yahoo 股市)
SECTOR_MAP = {
    "TAI": {40: "半導體", 41: "電腦週邊", 42: "光電", 43: "通信網路", 44: "電子零組件", 45: "電子通路", 46: "資訊服務", 47: "其他電子"},
    "TWO": {153: "半導體", 154: "電腦週邊", 155: "光電", 156: "通信網路", 157: "電子零組件", 158: "電子通路", 159: "資訊服務", 160: "其他電子"}
}

def start_crawling():
    full_db = {}
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}
    
    print("🚀 開始抓取全台股電子類股清單...")
    
    for exchange, sectors in SECTOR_MAP.items():
        for sid, name in sectors.items():
            url = f"https://tw.stock.yahoo.com/class-quote?sectorId={sid}&exchange={exchange}"
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                # 抓取股票代號與名稱
                # 結構通常是：代號在 <span>, 名稱在 <div>
                rows = soup.select('div[class*="table-row"]')
                for row in rows:
                    code_tag = row.select_one('span[class*="C(#7c7e80)"]')
                    name_tag = row.select_one('div[class*="Lh(20px)"]')
                    
                    if code_tag and name_tag:
                        ticker = code_tag.get_text(strip=True)
                        stock_name = name_tag.get_text(strip=True)
                        
                        # 格式化為 yfinance 格式
                        suffix = ".TW" if exchange == "TAI" else ".TWO"
                        full_db[f"{ticker}{suffix}"] = stock_name
                
                print(f"✅ 已完成: {exchange} {name}")
                time.sleep(1) # 禮貌性延遲
            except Exception as e:
                print(f"❌ 抓取失敗 {name}: {e}")

    # 儲存到 JSON
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(full_db, f, ensure_ascii=False, indent=2)
    
    print(f"\n✨ 抓取完成！總計 {len(full_db)} 檔電子股已存入 {DB_FILE}")

if __name__ == "__main__":
    start_crawling()
