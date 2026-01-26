import json
import os
import requests
from bs4 import BeautifulSoup
import time

def generate_electronic_stocks_db():
    """
    專門抓取 Yahoo 股市電子產業真實資料的獨立腳本
    """
    print("🚀 開始執行 generate_db.py: 正在建立全台電子股資料庫...")
    
    # 定義台股上市與上櫃的電子產業分類 ID (真實 Yahoo 股市 ID)
    SECTOR_MAP = {
        "TAI": { # 上市電子
            40: "半導體", 41: "電腦週邊", 42: "光電", 43: "通信網路", 
            44: "電子零組件", 45: "電子通路", 46: "資訊服務", 47: "其他電子"
        },
        "TWO": { # 上櫃電子
            153: "半導體", 154: "電腦週邊", 155: "光電", 156: "通信網路", 
            157: "電子零組件", 158: "電子通路", 159: "資訊服務", 160: "其他電子"
        }
    }
    
    db_result = {}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    total_categories = sum(len(v) for v in SECTOR_MAP.values())
    count = 0

    for exchange, sectors in SECTOR_MAP.items():
        for sector_id, sector_name in sectors.items():
            count += 1
            url = f"https://tw.stock.yahoo.com/class-quote?sectorId={sector_id}&exchange={exchange}"
            
            try:
                print(f"[{count}/{total_categories}] 正在抓取: {exchange} - {sector_name}...")
                response = requests.get(url, headers=headers, timeout=15)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    # 抓取表格中所有股票行
                    rows = soup.select('div[class*="table-row"]')
                    
                    for row in rows:
                        try:
                            # 抓取股票代號
                            code_element = row.select_one('span[class*="C(#7c7e80)"]')
                            # 抓取股票名稱
                            name_element = row.select_one('div[class*="Lh(20px)"]')
                            
                            if code_element and name_element:
                                code = code_element.get_text(strip=True)
                                name = name_element.get_text(strip=True)
                                # 根據市場加入字尾 (.TW 為上市, .TWO 為上櫃)
                                suffix = ".TW" if exchange == "TAI" else ".TWO"
                                db_result[f"{code}{suffix}"] = name
                        except Exception:
                            continue
                
                # 稍微延遲避免被 Yahoo 偵測為攻擊
                time.sleep(0.5)
                
            except Exception as e:
                print(f"❌ 抓取 {sector_name} 時發生錯誤: {e}")
                continue

    # 儲存為 JSON 檔案
    output_file = "taiwan_electronic_stocks.json"
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(db_result, f, ensure_ascii=False, indent=2)
        
        print("-" * 30)
        print(f"✅ 資料庫建立完成！")
        print(f"📁 檔案名稱: {output_file}")
        print(f"📊 總計檔數: {len(db_result)} 檔電子股")
        print("-" * 30)
    except Exception as e:
        print(f"❌ 檔案儲存失敗: {e}")

if __name__ == "__main__":
    generate_electronic_stocks_db()
