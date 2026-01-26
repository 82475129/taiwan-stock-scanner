import streamlit as st
import json
import os
import requests
from bs4 import BeautifulSoup

# 將載入邏輯封裝進緩存，確保網頁一啟動就跑底層爬蟲
@st.cache_data(ttl=86400) # 每天只抓一次真實資料
def force_init_db():
    print("🚀 啟動底層真實資料抓取...")
    # 定義真實的分類 ID
    SECTOR_MAP = {
        "TAI": {40: "半導體", 41: "電腦週邊", 42: "光電", 43: "通信網路", 44: "電子零組件", 45: "電子通路", 46: "資訊服務", 47: "其他電子"},
        "TWO": {153: "半導體", 154: "電腦週邊", 155: "光電", 156: "通信網路", 157: "電子零組件", 158: "電子通路", 159: "資訊服務", 160: "其他電子"}
    }
    db_result = {}
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # 直接從 Yahoo 股市爬取真實 HTML
    for ex, sectors in SECTOR_MAP.items():
        for sid, name in sectors.items():
            url = f"https://tw.stock.yahoo.com/class-quote?sectorId={sid}&exchange={ex}"
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(resp.text, 'html.parser')
                # 抓取真實的股票名稱與代號
                rows = soup.select('div[class*="table-row"]')
                for row in rows:
                    code = row.select_one('span[class*="C(#7c7e80)"]').text
                    name = row.select_one('div[class*="Lh(20px)"]').text
                    suffix = ".TW" if ex == "TAI" else ".TWO"
                    db_result[f"{code}{suffix}"] = name
            except:
                continue
    return db_result

# 網頁一打開，立即執行底層載入
db = force_init_db()

# 左側介面顯示真實數量
with st.sidebar:
    st.success(f"📁 已載入：{len(db)} 檔電子股 (真實數據)")
