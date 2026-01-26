import json
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
import time

def get_target_configs():
    """定義要爬取的分類：包含產業 ID 與 特殊集團股網址"""
    configs = []
    # 1. 電子產業分類 (上市 40~47, 上櫃 153~160)
    sids = list(range(40, 48)) + list(range(153, 161))
    for sid in sids:
        ex = "TAI" if sid < 100 else "TWO"
        configs.append({"name": f"Sector_{sid}", "url": f"https://tw.stock.yahoo.com/class-quote?sectorId={sid}&exchange={ex}"})
    
    # 2. 加入你提到的集團股 (中天生技)
    configs.append({
        "name": "中天集團股",
        "url": "https://tw.stock.yahoo.com/class-quote?category=%E4%B8%AD%E5%A4%A9%E7%94%9F%E6%8A%80&categoryLabel=%E9%9B%86%E5%9C%98%E8%82%A1"
    })
    return configs

def crawl_yahoo_class(config):
    """核心爬蟲：抓取 HTML 列表中的所有股票與詳細數值"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    results = {}
    try:
        resp = requests.get(config['url'], headers=headers, timeout=15)
        if resp.status_code != 200: return {}
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        rows = soup.select('li.List\(n\)') # 定位每一列股票
        
        for row in rows:
            # 抓取名稱與代碼
            name_div = row.select_one('div.Lh\(20px\)')
            code_span = row.select_one('span.Fz\(14px\)')
            if not name_div or not code_span: continue
            
            symbol = code_span.text.strip() # 如 2330.TW
            
            # 抓取所有數值欄位 (依序為：成交、漲跌、漲跌幅、開盤、昨收、最高、最低、成交量)
            cols = row.select('div.Ta\(end\)')
            if len(cols) >= 8:
                results[symbol] = {
                    "name": name_div.text.strip(),
                    "price": cols[0].text.strip(),
                    "change_p": cols[2].text.strip(),
                    "open": cols[3].text.strip(),
                    "high": cols[5].text.strip(),
                    "low": cols[6].text.strip(),
                    "vol": cols[7].text.strip().replace(',', '') # 去除千分位
                }
        return results
    except Exception as e:
        print(f"Error in {config['name']}: {e}")
        return {}

def main():
    print("🚀 啟動全量資料抓取...")
    all_stocks = {}
    configs = get_target_configs()
    
    for conf in tqdm(configs):
        data = crawl_yahoo_class(conf)
        all_stocks.update(data)
        time.sleep(0.5)
    
    if all_stocks:
        with open("taiwan_electronic_stocks.json", "w", encoding="utf-8") as f:
            json.dump(all_stocks, f, ensure_ascii=False, indent=2)
        print(f"🎉 完成！共存儲 {len(all_stocks)} 檔股票詳細資料")

if __name__ == "__main__":
    main()
