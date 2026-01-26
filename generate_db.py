# generate_db.py - 純產生 JSON 的腳本（給 GitHub Actions 用）
import requests
import re
from bs4 import BeautifulSoup
import json

DB_FILE = "electronic_stocks_db.json"

def fetch_all_electronic_stocks():
    ELECTRONIC_TAI_IDS = [40, 41, 42, 43, 44, 45, 46, 47]
    ELECTRONIC_TWO_IDS = [153, 154, 155, 156, 157, 158, 159, 160]
    
    full_db = {}
    
    def fetch_sector(sector_id, exchange):
        url = f"https://tw.stock.yahoo.com/class-quote?sectorId={sector_id}&exchange={exchange}"
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code != 200:
                return
            soup = BeautifulSoup(r.text, "html.parser")
            for row in soup.find_all("div", class_=re.compile(r"table-row D\(f\) H\(48px\) Ai\(c\)")):
                name_div = row.find("div", class_=re.compile(r"Lh\(20px\) Fw\(600\) Fz\(16px\) Ell"))
                code_span = row.find("span", class_=re.compile(r"Fz\(14px\) C\(#979ba7\) Ell"))
                if name_div and code_span:
                    name = name_div.get_text(strip=True)
                    sid = code_span.get_text(strip=True)
                    if re.match(r"^\d{4}\.(TW|TWO)$", sid):
                        full_db[sid] = {"name": name, "category": "電子"}
        except:
            pass

    for sid in ELECTRONIC_TAI_IDS:
        fetch_sector(sid, "TAI")
    for sid in ELECTRONIC_TWO_IDS:
        fetch_sector(sid, "TWO")
    
    num_stocks = len(full_db)
    if num_stocks > 0:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(full_db, f, ensure_ascii=False, indent=4)
        print(f"成功產生 JSON，共 {num_stocks} 檔電子股！")
    else:
        print("抓取失敗：資料庫為空！")

if __name__ == "__main__":
    fetch_all_electronic_stocks()
