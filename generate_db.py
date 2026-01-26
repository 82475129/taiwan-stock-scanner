import json
import requests
from bs4 import BeautifulSoup
import time
from tqdm import tqdm

def generate_electronic_stocks_db():
    print("🚀 啟動底層真實資料抓取 (來源: Yahoo 股市)...")
    
    # 真實電子產業分類 ID
    SECTOR_MAP = {
        "TAI": {40: "半導體", 41: "電腦週邊", 42: "光電", 43: "通信網路", 
                44: "電子零組件", 45: "電子通路", 46: "資訊服務", 47: "其他電子"},
        "TWO": {153: "半導體", 154: "電腦週邊", 155: "光電", 156: "通信網路", 
                157: "電子零組件", 158: "電子通路", 159: "資訊服務", 160: "其他電子"}
    }
    
    db_result = {}
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    # 建立任務清單用於進度條
    tasks = []
    for exchange, sectors in SECTOR_MAP.items():
        for sector_id, sector_name in sectors.items():
            tasks.append((exchange, sector_id, sector_name))

    # --- 終端機進度條 ---
    pbar = tqdm(tasks, desc="爬取產業進度", unit="分類")

    for exchange, sector_id, sector_name in pbar:
        pbar.set_description(f"正在抓取: {exchange}-{sector_name}")
        url = f"https://tw.stock.yahoo.com/class-quote?sectorId={sector_id}&exchange={exchange}"
        
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                rows = soup.select('div[class*="table-row"]')
                for row in rows:
                    code_el = row.select_one('span[class*="C(#7c7e80)"]')
                    name_el = row.select_one('div[class*="Lh(20px)"]')
                    if code_el and name_el:
                        code = code_el.get_text(strip=True)
                        name = name_el.get_text(strip=True)
                        suffix = ".TW" if exchange == "TAI" else ".TWO"
                        db_result[f"{code}{suffix}"] = name
            time.sleep(0.3) 
        except Exception as e:
            tqdm.write(f"⚠️ {sector_name} 抓取失敗: {e}")

    # 儲存結果
    output_file = "taiwan_electronic_stocks.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(db_result, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 完成！共抓取 {len(db_result)} 檔。")

if __name__ == "__main__":
    generate_electronic_stocks_db()
