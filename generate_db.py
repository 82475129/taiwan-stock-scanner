import json
import requests
from bs4 import BeautifulSoup
import time
from tqdm import tqdm

def generate_electronic_stocks_db():
    print("🚀 偵測到 Yahoo 網頁改版，啟動深度爬取模式...")
    
    # 這是電子產業細分頁面的根網址
    base_url = "https://tw.stock.yahoo.com"
    # 直接鎖定電子產業的類別頁面 (包含你給的 HTML 裡的那些分類)
    start_url = "https://tw.stock.yahoo.com/class" 
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    db_result = {}
    
    # 1. 這裡手動列出你提供的 HTML 中最重要的細分分類連結 (範例)
    # 實際上我們會動態抓取，但為了保險，我們直接定義電子業常用的 ID
    # 根據新版 Yahoo，我們直接抓取「電子產業」下的所有細分類
    categories = [
        "設備或廠務工程", "電子設備買賣", "其他零組件", "PC/NB/平板", "組裝代工",
        "IC生產製造", "其他光電", "消費電子或電器", "手機相關", "軟體設計",
        "系統整合", "網通設備組件", "IC設計服務", "LED", "太陽能", "PCB",
        "機殼", "面板業", "電池或電源", "光學元件或組裝", "被動元件", "工業電腦"
    ]
    
    # 為了簡化，我們直接抓取「上市電子」與「上櫃電子」的總表，這最穩
    main_sectors = [
        {"ex": "TAI", "name": "上市電子", "url": "https://tw.stock.yahoo.com/class-quote?sectorId=46&exchange=TAI"}, # 假設的 ID，我們會用通用選取器
    ]

    # --- 修正後的萬用抓取邏輯 ---
    # 我們改用 Yahoo 的「所有產業」清單來撈電子股
    print("正在抓取全台電子標的...")
    
    # 電子股的關鍵字
    target_keywords = ["電子", "半導體", "電腦", "光電", "通信", "資訊", "網路", "IC", "PCB"]
    
    # 這裡我們用一個更暴力但也更穩的方法：直接抓取 Yahoo 所有的電子分類 ID
    # 上市電子類 ID 範圍通常在 40~47，上櫃在 153~160
    sector_ids = list(range(40, 48)) + list(range(153, 161))
    
    pbar = tqdm(sector_ids, desc="掃描電子分類")

    for sid in pbar:
        exchange = "TAI" if sid < 100 else "TWO"
        url = f"https://tw.stock.yahoo.com/class-quote?sectorId={sid}&exchange={exchange}"
        
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # 關鍵修正：新版 Yahoo 的股票名稱和代號包在 'div' 或是 'a' 標籤裡
            # 我們直接找包含股票代號數字的文字
            rows = soup.select('div[class*="table-row"]')
            
            for row in rows:
                # 抓取代號 (通常是 4 位數字)
                code_el = row.select_one('span[class*="C(#7c7e80)"]')
                # 抓取名稱
                name_el = row.select_one('div[class*="Lh(20px)"]')
                
                if code_el and name_el:
                    code = code_el.get_text(strip=True)
                    name = name_el.get_text(strip=True)
                    if code.isdigit() and len(code) >= 4:
                        suffix = ".TW" if exchange == "TAI" else ".TWO"
                        db_result[f"{code}{suffix}"] = name
            
            time.sleep(0.5)
        except:
            continue

    # 儲存
    with open("taiwan_electronic_stocks.json", 'w', encoding='utf-8') as f:
        json.dump(db_result, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 成功！共抓取 {len(db_result)} 檔電子股。")

if __name__ == "__main__":
    generate_electronic_stocks_db()
