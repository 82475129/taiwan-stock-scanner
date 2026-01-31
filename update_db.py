# -*- coding: utf-8 -*-
"""
黨名：update_db.py
功能：自動掃描證交所與櫃買中心，獲取「上市+上櫃」完整清單並包含「產業分類」
特色：支援無中生有，自動生成並覆蓋 taiwan_full_market.json
"""
import requests
import pandas as pd
import json
import io
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
            print(f"📡 正在從證交所/櫃買中心抓取【{target['name']}】清單...")
            
            # 使用 requests 抓取，並強制指定編碼為 big5 (證交所標準)
            response = requests.get(target['url'], timeout=30)
            response.encoding = 'big5'
            
            # 使用 io.StringIO 包裝，避免 pandas 抓不到正確編碼
            dfs = pd.read_html(io.StringIO(response.text))
            df = dfs[0]
            
            # 設定正確的標題列 (第一列通常是標題)
            df.columns = df.iloc[0]
            df = df.iloc[1:]
            
            count = 0
            for _, row in df.iterrows():
                # 原始格式通常是 "2330　台積電" (中間是全形空白)
                raw_value = str(row['有價證券代號及名稱'])
                item = raw_value.split('\u3000')
                
                if len(item) == 2:
                    sid, name = item[0].strip(), item[1].strip()
                    # 過濾條件：代號必須是 4 位數（濾掉權證、認購證等）
                    if len(sid) == 4 and sid.isdigit():
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

    # --- 核心動作：無中生有並自動覆蓋 ---
    if full_market_data:
        filename = "taiwan_full_market.json"
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(full_market_data, f, ensure_ascii=False, indent=4)
            print("---")
            print(f"✨ 任務達成！已成功生出並覆蓋 {filename}")
            print(f"📊 目前總兵力：{len(full_market_data)} 檔上市/上櫃股票。")
        except Exception as e:
            print(f"❌ 寫入檔案失敗: {e}")
    else:
        print("⚠️ 錯誤：抓取不到任何資料，未生成檔案。這將導致 Workflow 報錯。")
        # 這裡故意讓程式報錯，好讓 GitHub Actions 知道出問題了
        exit(1)

if __name__ == "__main__":
    update_taiwan_stock_list()
