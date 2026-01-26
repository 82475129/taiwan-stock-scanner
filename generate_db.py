import json, requests, time
from bs4 import BeautifulSoup
from tqdm import tqdm

def generate_db():
    # 這裡整合你說的 7, 2 不同 ID，以及集團股網址
    target_urls = [
        "https://tw.stock.yahoo.com/class-quote?sectorId=2&exchange=TAI", # 食品
        "https://tw.stock.yahoo.com/class-quote?sectorId=7&exchange=TAI", # 電機
        "https://tw.stock.yahoo.com/class-quote?category=%E4%B8%AD%E5%A4%A9%E7%94%9F%E6%8A%80&categoryLabel=%E9%9B%86%E5%9C%98%E8%82%A1"
    ]
    # 如果要自動包含所有電子股，解除下面註解：
    # sector_ids = list(range(40, 48)) + list(range(153, 161))
    # target_urls += [f"https://tw.stock.yahoo.com/class-quote?sectorId={i}&exchange={'TAI' if i<100 else 'TWO'}" for i in sector_ids]

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    full_db = {}

    for url in tqdm(target_urls, desc="抓取分類中"):
        try:
            resp = requests.get(url, headers=headers)
            soup = BeautifulSoup(resp.text, 'html.parser')
            rows = soup.select('li.List\(n\)')
            for row in rows:
                name = row.select_one('div.Lh\(20px\)').text.strip()
                code = row.select_one('span.Fz\(14px\)').text.strip()
                # 為了相容你原本的 App 邏輯，存成 {代碼: 名稱}
                full_db[code] = name
            time.sleep(0.5)
        except: continue

    with open("taiwan_electronic_stocks.json", "w", encoding="utf-8") as f:
        json.dump(full_db, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    generate_db()
