import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
import json
import os
import requests
from bs4 import BeautifulSoup
import time
import concurrent.futures

# ==========================================
# 0. 系統啟動初始化 (執行程式即抓取 800+ 檔)
# ==========================================
DB_FILE = "taiwan_electronic_stocks.json"

def init_database():
    """啟動時自動檢查並建立全電子股資料庫"""
    if not os.path.exists(DB_FILE):
        # 這裡會輸出在你的終端機 (Terminal)
        print("🚀 [首次執行] 正在自動抓取全台電子產業清單 (約 800+ 檔)...")
        sectors = {
            "TAI": {40: "半導體", 41: "電腦週邊", 42: "光電", 43: "通信網路", 44: "電子零組件", 45: "電子通路", 46: "資訊服務", 47: "其他電子"},
            "TWO": {153: "半導體", 154: "電腦週邊", 155: "光電", 156: "通信網路", 157: "電子零組件", 158: "電子通路", 159: "資訊服務", 160: "其他電子"}
        }
        full_db = {}
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        
        for ex, cats in sectors.items():
            for sid, cat_name in cats.items():
                try:
                    url = f"https://tw.stock.yahoo.com/class-quote?sectorId={sid}&exchange={ex}"
                    resp = requests.get(url, headers=headers, timeout=10)
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    rows = soup.select('div[class*="table-row"]')
                    for row in rows:
                        c = row.select_one('span[class*="C(#7c7e80)"]')
                        n = row.select_one('div[class*="Lh(20px)"]')
                        if c and n:
                            suffix = ".TW" if ex == "TAI" else ".TWO"
                            full_db[f"{c.get_text(strip=True)}{suffix}"] = n.get_text(strip=True)
                    time.sleep(0.2)
                except: pass
        
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(full_db, f, ensure_ascii=False, indent=2)
        print(f"✨ [初始化成功] 已存入 {len(full_db)} 檔電子股數據。")

# 強制在載入 Streamlit 前執行
init_database()

# ==========================================
# 1. 形態分析與篩選引擎 (新增 MA20 邏輯)
# ==========================================
def analyze_patterns(df, config, days=15):
    if df is None or len(df) < 30: return None
    try:
        # 計算 MA20 均線
        df['MA20'] = df['Close'].rolling(window=20).mean()
        price_now = float(df['Close'].iloc[-1])
        ma20_now = float(df['MA20'].iloc[-1])
        
        # --- [新增篩選] 必須站上月線 (MA20) ---
        if config.get('use_ma', True) and price_now < ma20_now:
            return None

        d = df.tail(days).copy()
        h, l, v = d['High'].values.astype(float), d['Low'].values.astype(float), d['Volume'].values.astype(float)
        x = np.arange(len(h))
        
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        v_mean = df['Volume'].iloc[-21:-1].mean() # 20日均量
        
        hits = []
        if config.get('tri') and (sh < -0.003 and sl > 0.003):
            hits.append({"text": "📐 三角收斂", "class": "badge-tri"})
        if config.get('box') and (abs(sh) < 0.03 and abs(sl) < 0.03):
            hits.append({"text": "📦 旗箱整理", "class": "badge-box"})
        if config.get('vol') and (v[-1] > v_mean * 1.5):
            hits.append({"text": "🚀 今日爆量", "class": "badge-vol"})
        
        if not hits: return None
        
        return {
            "labels": hits, "lines": (sh, ih, sl, il, x),
            "price": round(price_now, 2),
            "ma20": round(ma20_now, 2),
            "prev_close": float(df['Close'].iloc[-2]),
            "vol": int(v[-1] // 1000)
        }
    except: return None

# ==========================================
# 2. 介面與 CSS (保持原介面設計)
# ==========================================
st.set_page_config(page_title="台股 Pro-X 形態大師", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #f4f7f6; font-family: 'Noto Sans TC', sans-serif; }
    .stock-card { background: white; padding: 16px; border-radius: 12px; margin-bottom: 15px; border-left: 6px solid #6c5ce7; box-shadow: 0 4px 10px rgba(0,0,0,0.06); }
    .card-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
    .sid-link { font-size: 1.1rem; font-weight: bold; color: #6c5ce7; text-decoration: none; }
    .price { font-weight: 800; font-size: 1.2rem; }
    .badge { padding: 4px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: bold; margin: 2px; color: white; display: inline-block; }
    .badge-tri { background-color: #6c5ce7; }
    .badge-box { background-color: #2d3436; }
    .badge-vol { background-color: #d63031; }
    .ma-text { color: #0984e3; font-size: 12px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# 載入資料庫
with open(DB_FILE, 'r', encoding='utf-8') as f:
    db = json.load(f)

# ==========================================
# 3. 左側邊欄 (完整保留你的設定介面)
# ==========================================
if 'current_mode' not in st.session_state:
    st.session_state.current_mode = "⚡ 今日即時監控 (自動)"

modes = ["⚡ 今日即時監控 (自動)", "⏳ 歷史形態搜尋 (手動)", "🌐 顯示所有股票連結"]

with st.sidebar:
    st.title("🎯 形態大師控制台")
    st.info(f"📁 已載入：{len(db)} 檔電子股")
    selected_mode = st.radio("選擇功能模式", modes, index=modes.index(st.session_state.current_mode))
    st.session_state.current_mode = selected_mode
    st.divider()
    
    if selected_mode == "⚡ 今日即時監控 (自動)":
        st_autorefresh(interval=300000, key="auto_refresh")
        st.markdown("### 形態與趨勢篩選")
        f_ma = st.checkbox("股價需在 20MA 之上", value=True)
        t_tri = st.checkbox("📐 三角收斂", value=True)
        t_box = st.checkbox("📦 旗箱整理", value=True)
        t_vol = st.checkbox("🚀 今日爆量", value=True)
        t_min_v = st.number_input("最低成交量 (張)", value=500, min_value=100)
        current_config = {'tri': t_tri, 'box': t_box, 'vol': t_vol, 'use_ma': f_ma}
        run_now = True
    elif selected_mode == "⏳ 歷史形態搜尋 (手動)":
        h_sid = st.text_input("輸入代號", placeholder="例如：2330")
        current_config = {'tri': True, 'box': True, 'vol': True, 'use_ma': False}
        run_now = st.button("🚀 開始掃描", type="primary", use_container_width=True)
    else:
        run_now = False

# ==========================================
# 4. 主畫面掃描執行
# ==========================================
st.title("台股 Pro-X 形態大師")

if run_now:
    targets = [(f"{h_sid.upper()}.TW", h_sid.upper())] if selected_mode == "⏳ 歷史形態搜尋 (手動)" and h_sid else list(db.items())
    
    with st.spinner(f"正在分析 {len(targets)} 檔數據..."):
        # 批量下載優化速度
        tickers_list = [t[0] for t in targets]
        all_data = yf.download(tickers_list, period="2mo", group_by='ticker', progress=False)
        
        final_results = []
        for sid, name in targets:
            try:
                df_stock = all_data[sid].dropna() if len(tickers_list) > 1 else all_data.dropna()
                res = analyze_patterns(df_stock, current_config)
                if res and (selected_mode == "⏳ 歷史形態搜尋 (手動)" or res['vol'] >= t_min_v):
                    res.update({"sid": sid, "name": name, "df": df_stock})
                    final_results.append(res)
            except: continue

    if not final_results:
        st.info("目前沒有符合篩選條件的標的。")
    else:
        for item in final_results:
            p_color = "#d63031" if item['price'] >= item['prev_close'] else "#27ae60"
            b_html = "".join([f'<span class="badge {l["class"]}">{l["text"]}</span>' for l in item['labels']])
            
            st.markdown(f"""
                <div class="stock-card">
                    <div class="card-row">
                        <a class="sid-link" href="https://tw.stock.yahoo.com/quote/{item['sid'].split('.')[0]}" target="_blank">
                            🔗 {item['sid'].split('.')[0]} {item['name']}
                        </a>
                        <span class="price" style="color:{p_color};">${item['price']}</span>
                    </div>
                    <div class="card-row">
                        <span style="color:#666; font-size:0.9rem;">成交量: <b>{item['vol']} 張</b></span>
                        <span class="ma-text">MA20: {item['ma20']}</span>
                    </div>
                    <div>{b_html}</div>
                </div>
            """, unsafe_allow_html=True)
            
            with st.expander("📈 展開形態圖表"):
                d_p = item['df'].tail(30)
                sh, ih, sl, il, x_r = item['lines']
                fig = go.Figure(data=[go.Candlestick(x=d_p.index, open=d_p['Open'], high=d_p['High'], low=d_p['Low'], close=d_p['Close'], name="K線")])
                fig.add_trace(go.Scatter(x=d_p.index, y=d_p['MA20'], line=dict(color='#3498db', width=1.5), name="MA20"))
                fig.add_trace(go.Scatter(x=d_p.tail(15).index, y=sh*x_r + ih, line=dict(color='#ff4757', dash='dash'), name="壓"))
                fig.add_trace(go.Scatter(x=d_p.tail(15).index, y=sl*x_r + il, line=dict(color='#2ed573', dash='dot'), name="撐"))
                fig.update_layout(height=400, margin=dict(l=5,r=5,t=5,b=5), xaxis_rangeslider_visible=False, template="plotly_white", showlegend=False)
                st.plotly_chart(fig, use_container_width=True, key=f"fig_{item['sid']}")

st.caption(f"最後更新：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
