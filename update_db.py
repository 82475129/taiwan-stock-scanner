# -*- coding: utf-8 -*-
"""
檔名：update_db.py
功能：自動掃描證交所與櫃買中心，獲取「上市+上櫃」完整清單並包含「產業分類」
"""
import requests
import pandas as pd
import json
from datetime import datetime

def update_taiwan_stock_list():
    print(f"🚀 [{datetime.now().strftime('%H:%M:%S')}] update_db.py 任務啟動...")
    
    # 網址清單：strMode=2 是上市，strMode=4 是上櫃
    targets = [
        {"name": "上市", "url": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", "suffix": ".TW"},
        {"name": "上櫃", "url": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4", "suffix": ".TWO"}
    ]
    
    full_market_data = {}
    
    for target in targets:
        try:
            print(f"📡 正在從證交所/櫃買中心抓取【{target['name']}】股票清單...")
            res = requests.get(target['url'])
            # 使用 pandas read_html 直接解析表格，這比 BeautifulSoup 穩定且能拿到產業欄位
            dfs = pd.read_html(res.text)
            df = dfs[0]
            
            # 設定正確的標題列
            df.columns = df.iloc[0]
            df = df.iloc[1:]
            
            count = 0
            for _, row in df.iterrows():
                # 原始格式通常是 "2330　台積電"
                item = str(row['有價證券代號及名稱']).split('\u3000')
                
                if len(item) == 2:
                    sid, name = item
                    # 過濾條件：代號必須是 4 位數（濾掉權證、ETN等非普通股）
                    if len(sid) == 4:
                        industry = row.get('產業別', '其他')
                        full_market_data[f"{sid}{target['suffix']}"] = {
                            "name": name,
                            "category": industry,
                            "market": target['name']
                        }
                        count += 1
            print(f"✅ {target['name']} 處理完成，共計 {count} 檔。")
            
        except Exception as e:
            print(f"❌ 抓取 {target['name']} 失敗: {e}")

    # --- 核心動作：自動覆蓋 JSON ---
    if full_market_data:
        filename = "taiwan_full_market.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(full_market_data, f, ensure_ascii=False, indent=4)
        print("---")
        print(f"✨ 任務達成！已更新並覆蓋 {filename}")
        print(f"📊 目前總兵力：{len(full_market_data)} 檔上市/上櫃股票。")
    else:
        print("⚠️ 失敗：抓取不到任何資料，未執行檔案覆蓋。")

if __name__ == "__main__":
    update_taiwan_stock_list()
