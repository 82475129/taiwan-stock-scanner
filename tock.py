import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import sys, requests, json, os, time
from bs4 import BeautifulSoup

# ==========================================
# 0. 環境與全方位爬蟲邏輯
# ==========================================
IS_STREAMLIT = "streamlit" in sys.argv[0] or any("streamlit" in arg for arg in sys.argv)
DB_FILE = "taiwan_full_market.json" # 改名代表全市場

def update_json_database():
    """全方位爬蟲：產業股 + ETF + 集團股"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    new_db = {}
    
    # 1. 掃描所有產業分類 (上市 2~47, 上櫃 65~165)
    scan_configs = [
        {"exch": "TAI", "suffix": ".TW", "ids": list(range(2, 48))},
        {"exch": "TWO", "suffix": ".TWO", "ids": list(range(65, 166))}
    ]
    
    # 2. 額外加入 ETF 與 特殊分類網址
    extra_urls = [
        "https://tw.stock.yahoo.com/class-quote?category=ETF&categoryLabel=ETF",
        "https://tw.stock.yahoo.com/class-quote?category=%E5%85%AC%E7%9B%8A%E8%AD%89%E5%88%B8&categoryLabel=%E5%85%AC%E7%9B%8A%E8%AD%89%E5%88%B8",
        "https://tw.stock.yahoo.com/class-quote?category=%E5%85%B6%E4%BB%96%E9%9B%BB%E5%AD%90&categoryLabel=%E5%85%B6%E4%BB%96%E9%9B%BB%E5%AD%90"
    ]

    print("📡 啟動全市場掃描 (含 ETF)...")

    # 執行產業掃描
    for config in scan_configs:
        for sid in config["ids"]:
            url = f"https://tw.stock.yahoo.com/class-quote?sectorId={sid}&exchange={config['exch']}"
            try:
                resp = requests.get(url, headers=headers, timeout=5)
                soup = BeautifulSoup(resp.text, 'html.parser')
                rows = soup.select('li.List\(n\)')
                for row in rows:
                    name_el = row.select_one('div.Lh\(20px\)')
                    code_el = row.select_one('span.Fz\(14px\)')
                    if name_el and code_el:
                        new_db[f"{code_el.text.strip()}{config['suffix']}"] = name_el.text.strip()
            except: continue
        time.sleep(0.1)

    # 執行額外/ETF 掃描
    for url in extra_urls:
        try:
            resp = requests.get(url, headers=headers, timeout=5)
            soup = BeautifulSoup(resp.text, 'html.parser')
            rows = soup.select('li.List\(n\)')
            for row in rows:
                name_el = row.select_one('div.Lh\(20px\)')
                code_el = row.select_one('span.Fz\(14px\)')
                if name_el and code_el:
                    # ETF 通常在上市掛牌，若抓不到可預設 .TW
                    code = code_el.text.strip()
                    new_db[f"{code}.TW"] = name_el.text.strip()
        except: continue

    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(new_db, f, ensure_ascii=False, indent=2)
    
    print(f"🏁 全市場掃描完成！總計：{len(new_db)} 檔")
    return new_db

@st.cache_data(ttl=3600)
def load_db():
    if not os.path.exists(DB_FILE): return update_json_database()
    with open(DB_FILE, 'r', encoding='utf-8') as f: return json.load(f)

# ==========================================
# 1. 形態分析引擎 (維持 Turbo 效能)
# ==========================================
def analyze_patterns(df, config, days=15):
    if df is None or len(df) < 25: return None
    try:
        close_arr = df['Close'].values.astype(float)
        vol_arr = df['Volume'].values.astype(float)
        ma20 = np.mean(close_arr[-20:])
        p_now = close_arr[-1]
        
        if config.get('use_ma') and p_now < ma20: return None

        d = df.tail(days)
        h, l = d['High'].values.astype(float), d['Low'].values.astype(float)
        x = np.arange(days)
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        
        hits = []
        if config.get('tri') and (sh < -0.002 and sl > 0.002): hits.append({"text": "📐 三角收斂", "class": "badge-tri"})
        if config.get('box') and (abs(sh) < 0.02 and abs(sl) < 0.02): hits.append({"text": "📦 旗箱整理", "class": "badge-box"})
        if config.get('vol') and (vol_arr[-1] > np.mean(vol_arr[-21:-1]) * 1.5): hits.append({"text": "🚀 今日爆量", "class": "badge-vol"})
        
        if not hits: return None
        return {"labels": hits, "lines": (sh, ih, sl, il, x), "price": round(p_now, 2), "vol": int(vol_arr[-1]//1000)}
    except: return None

# ==========================================
# 2. UI 顯示與多執行緒掃描
# ==========================================
if IS_STREAMLIT:
    from streamlit_autorefresh import st_autorefresh
    st.set_page_config(page_title="台股全市場 Pro 掃描", layout="wide")
    db = load_db()

    with st.sidebar:
        st.title("🎯 形態大師 (Full)")
        st.info(f"📁 已載入：{len(db)} 檔 (含 ETF)")
        if st.button("🔄 更新全市場清單"):
            db = update_json_database()
            st.cache_data.clear()
        
        t_min_v = st.number_input("最低成交量(張)", value=1000)
        f_ma = st.checkbox("MA20 之上", value=True)
        config = {'tri': True, 'box': True, 'vol': True, 'use_ma': f_ma}
        run = st.button("🚀 啟動全市場掃描", type="primary")

    if run:
        targets = list(db.items())
        final_results = []
        chunk_size = 80 # 大量標的時增加一次抓取的數量
        
        p_bar = st.progress(0)
        for i in range(0, len(targets), chunk_size):
            p_bar.progress(min(i / len(targets), 1.0))
            chunk = targets[i : i + chunk_size]
            t_codes = [t[0] for t in chunk]
            
            # 使用 threads=True 加速
            data = yf.download(t_codes, period="2mo", interval="1d", group_by='ticker', progress=False, threads=True)
            
            for sid, name in chunk:
                try:
                    df_s = data[sid].dropna() if len(t_codes) > 1 else data.dropna()
                    res = analyze_patterns(df_s, config)
                    if res and res['vol'] >= t_min_v:
                        res.update({"sid": sid, "name": name, "df": df_s})
                        final_results.append(res)
                except: continue
                
        p_bar.empty()
        st.success(f"掃描完畢！共找到 {len(final_results)} 檔符合標的")

        # 雙欄位顯示
        cols = st.columns(2)
        for idx, item in enumerate(final_results[:80]):
            with cols[idx % 2]:
                with st.container():
                    st.markdown(f"**{item['sid']} {item['name']}**")
                    st.write(f"現價: {item['price']} | 量: {item['vol']}張")
                    for l in item['labels']:
                        st.caption(f"✨ {l['text']}")
                    with st.expander("查看 K 線分析圖"):
                        d_p = item['df'].tail(30)
                        sh, ih, sl, il, x_r = item['lines']
                        fig = go.Figure(data=[go.Candlestick(x=d_p.index, open=d_p['Open'], high=d_p['High'], low=d_p['Low'], close=d_p['Close'])])
                        # 畫出壓力與支撐線
                        fig.add_trace(go.Scatter(x=d_p.tail(15).index, y=sh*x_r+ih, line=dict(color='red', width=1, dash='dash'), name="壓力線"))
                        fig.add_trace(go.Scatter(x=d_p.tail(15).index, y=sl*x_r+il, line=dict(color='green', width=1, dash='dash'), name="支撐線"))
                        fig.update_layout(height=400, margin=dict(l=5, r=5, t=5, b=5), xaxis_rangeslider_visible=False, showlegend=False)
                        st.plotly_chart(fig, use_container_width=True)

else:
    if __name__ == "__main__":
        # GitHub Actions 執行區
        update_json_database()
