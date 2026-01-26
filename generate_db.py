import json
import requests
from tqdm import tqdm
import time

# -------------------------------
# 1️⃣ 取得台股電子股代碼清單
# -------------------------------
def get_electronic_stock_codes():
    """
    抓取 Yahoo 電子股分類代碼 (上市 + 上櫃)
    """
    codes = []

    # 上市 (TAI) 與 上櫃 (TWO) 的電子產業 sector IDs
    sector_ids = list(range(40, 48)) + list(range(153, 161))

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    for sid in tqdm(sector_ids, desc="抓取分類股票代碼"):
        exchange = "TAI" if sid < 100 else "TWO"
        url = f"https://tw.stock.yahoo.com/class-quote?sectorId={sid}&exchange={exchange}"

        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            html = resp.text

            # 用簡單字串搜尋股票代碼 (4~5 位數字)
            import re
            matches = re.findall(r'\"symbol\":\"(\d{4,5})\"', html)
            suffix = ".TW" if exchange == "TAI" else ".TWO"
            codes.extend([f"{m}{suffix}" for m in matches])
            time.sleep(0.5)  # 避免被封鎖

        except Exception as e:
            tqdm.write(f"⚠️ sectorId {sid} 失敗: {e}")

    # 去重
    return list(set(codes))

# -------------------------------
# 2️⃣ 抓取 Yahoo Finance JSON
# -------------------------------
def fetch_stock_info(symbols):
    """
    透過 Yahoo Finance API 抓股票名稱
    """
    db_result = {}
    batch_size = 50  # 一次抓 50 檔，避免 URL 太長
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    for i in tqdm(range(0, len(symbols), batch_size), desc="抓取股票名稱"):
        batch = symbols[i:i+batch_size]
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={','.join(batch)}"
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            for item in data.get('quoteResponse', {}).get('result', []):
                symbol = item.get('symbol')
                name = item.get('shortName')
                if symbol and name:
                    db_result[symbol] = name
            time.sleep(0.5)
        except Exception as e:
            tqdm.write(f"⚠️ 批次抓取失敗: {e}")

    return db_result

# -------------------------------
# 3️⃣ 主程式
# -------------------------------
def generate_electronic_stocks_db():
    print("🚀 啟動電子股資料庫生成...")

    # 1. 取得代碼清單
    codes = get_electronic_stock_codes()
    print(f"📈 共抓到 {len(codes)} 檔代碼")

    if not codes:
        print("❌ 沒抓到任何代碼，停止生成 JSON")
        return

    # 2. 抓取股票名稱
    db_result = fetch_stock_info(codes)
    print(f"✅ 共成功抓到 {len(db_result)} 檔資料")

    if not db_result:
        print("❌ 沒抓到任何名稱資料，停止生成 JSON")
        return

    # 3. 儲存 JSON
    output_file = "taiwan_electronic_stocks.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(db_result, f, ensure_ascii=False, indent=2)

    print(f"🎉 完成！已生成 {output_file}")

# -------------------------------
# 4️⃣ 執行
# -------------------------------
if __name__ == "__main__":
    generate_electronic_stocks_db()
