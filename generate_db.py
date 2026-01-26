import json
import requests
from bs4 import BeautifulSoup
import time
from tqdm import tqdm

def generate_electronic_stocks_db():
    print("🚀 啟動深度爬取真實電子股名單...")
    
    # 模擬真實瀏覽器，避免被 Yahoo 擋掉
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    
    db_result = {}
    # 電子產業分類 ID
    sector_ids = list(range(40, 48)) + list(range(153, 161))
    
    pbar = tqdm(sector_ids, desc="掃描分類")

    for sid in pbar:
        exchange = "TAI" if sid < 100 else "TWO"
        url = f"https://tw.stock.yahoo.com/class-quote?sectorId={sid}&exchange={exchange}"
        
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                # 這是目前 Yahoo 最穩定的選取方式
                rows = soup.find_all('div', class_=lambda x: x and 'table-row' in x)
                
                for row in rows:
                    # 尋找代號與名稱
                    code_el = row.find('span', class_=lambda x: x and 'C(#7c7e80)' in x)
                    name_el = row.find('div', class_=lambda x: x and 'Lh(20px)' in x)
                    
                    if code_el and name_el:
                        code = code_el.get_text(strip=True)
                        name = name_el.get_text(strip=True)
                        
                        if code.isdigit() and len(code) >= 4:
                            suffix = ".TW" if exchange == "TAI" else ".TWO"
                            db_result[f"{code}{suffix}"] = name
            time.sleep(1) # 增加延遲，降低被封鎖風險
        except Exception as e:
            tqdm.write(f"⚠️ ID {sid} 失敗: {e}")

    # 儲存結果
    output_file = "taiwan_electronic_stocks.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(db_result, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 成功！已抓取 {len(db_result)} 檔。")

if __name__ == "__main__":
    generate_electronic_stocks_db()
