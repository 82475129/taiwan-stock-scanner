import requests
from bs4 import BeautifulSoup
import json
import os

def update_taiwan_stock_list():
    print("📡 正在抓取證交所最新上市股票名單...")
    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    try:
        res = requests.get(url)
        res.encoding = 'big5' # 證交所使用 Big5 編碼
        soup = BeautifulSoup(res.text, "html.parser")
        stocks = {}
        
        # 解析表格
        for row in soup.find_all('tr'):
            cols = row.find_all('td')
            if len(cols) > 0:
                text = cols[0].text.split('\u3000') # 移除全型空白
                if len(text) == 2 and len(text[0]) == 4: # 只要 4 位數代碼的普通股
                    stocks[f"{text[0]}.TW"] = text[1]
        
        # 存檔
        with open("taiwan_full_market.json", "w", encoding="utf-8") as f:
            json.dump(stocks, f, ensure_ascii=False, indent=4)
        
        print(f"✅ 更新成功！目前共存入 {len(stocks)} 檔股票。")
    except Exception as e:
        print(f"❌ 更新失敗: {e}")

if __name__ == "__main__":
    update_taiwan_stock_list()
