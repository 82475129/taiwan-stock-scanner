import json
import requests
from bs4 import BeautifulSoup
import time
from tqdm import tqdm

def generate_electronic_stocks_db():
    print("🚀 啟動深度爬取模式：抓取 Yahoo 股市電子產業真實名單...")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    db_result = {}
    # 電子產業分類 ID：上市 (40-47), 上櫃 (153-160)
    sector_ids = list(range(40, 48)) + list(range(153, 161))
    
    pbar = tqdm(sector_ids, desc="掃描分類進度")

    for sid in pbar:
        exchange = "TAI" if sid < 100 else "TWO"
        url = f"https://tw.stock.yahoo.com/class-quote?sectorId={sid}&exchange={exchange}"
        
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                # 鎖定新版 Yahoo 的 table-row 結構
                rows = soup.select('div[class*="table-row"]')
                
                for row in rows:
                    code_el = row.select_one('span[class*="C(#7c7e80)"]')
                    name_el = row.select_one('div[class*="Lh(20px)"]')
                    
                    if code_el and name_el:
                        code = code_el.get_text(strip=True)
                        name = name_el.get_text(strip=True)
                        
                        if code.isdigit() and len(code) == 4:
                            suffix = ".TW" if exchange == "TAI" else ".TWO"
                            db_result[f"{code}{suffix}"] = name
            time.sleep(0.5) 
        except Exception as e:
            tqdm.write(f"⚠️ 分類 {sid} 抓取失敗: {e}")

    output_file = "taiwan_electronic_stocks.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(db_result, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 完成！共抓取 {len(db_result)} 檔真實電子股。")

if __name__ == "__main__":
    generate_electronic_stocks_db()
