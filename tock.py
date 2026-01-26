import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import concurrent.futures
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.stats import linregress
from streamlit_autorefresh import st_autorefresh
import requests
from bs4 import BeautifulSoup
import os

# ==========================================
# 0. 基礎設定與資料庫
# ==========================================
st.set_page_config(page_title="台股 Pro-X 形態大師", layout="wide")

if 'current_mode' not in st.session_state:
    st.session_state.current_mode = "⚡ 今日即時監控 (自動)"

DB_FILE = "taiwan_electronic_stocks.json"

@st.cache_data(ttl=3600)
def load_full_db():
    # 若 JSON 不存在，使用預設核心電子股
    base_list = {
        "2330.TW": "台積電", "2454.TW": "聯發科", "3025.TW": "星通", 
        "3406.TW": "玉晶光", "2498.TW": "宏達電", "2317.TW": "鴻海", 
        "3045.TW": "台灣大", "2303.TW": "聯電", "2382.TW": "廣達"
    }
    return base_list

# ==========================================
# 1. 強化版即時數據抓取 (解決 1,755 問題)
# ==========================================
def get_yahoo_live_price(sid):
    """ 強力抓取即時股價，處理千分位與動態 Class """
    try:
        url = f"https://tw.stock.yahoo.com/quote/{sid}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=3)
        if resp.status_code != 200: return None
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        # 關鍵：找尋固定的大字股價標籤，不論漲跌
        price_tag = soup.select_one('span[class*="Fz(32px)"]')
        if price_tag:
            # 處理如 "1,755" 的字串轉為浮點數
            return float(price_tag.text.replace(',', ''))
    except:
        pass
    return None

@st.cache_data(ttl=300)
def get_stock_data(sid):
    """ 下載資料並整合即時價 """
    try: 
        df = yf.download(sid, period="45d", progress=False, multi_level=False)
        if df.empty: return pd.DataFrame()
        
        # 覆蓋最新即時價 (確保 1,755 這種即時數據被納入)
        live_p = get_yahoo_live_price(sid)
        if live_p:
            df.iloc[-1, df.columns.get_loc('Close')] = live_p
            
        return df.dropna()
    except: 
        return pd.DataFrame()

# ==========================================
# 2. 形態核心演算法
# ==========================================
def analyze_patterns(df, config, days=15):
    if df is None or df.empty or len(df) < days: return None
    try:
        d = df.tail(days).copy()
        h = d['High'].values.astype(float)
        l = d['Low'].values.astype(float)
        v = d['Volume'].values.astype(float)
        x = np.arange(len(h))
        
        sh, ih, _, _, _ = linregress(x, h) 
        sl, il, _, _, _ = linregress(x, l) 
        v_mean = v[-6:-1].mean() if len(v)>5 else v.mean()
        
        hits = []
        if config.get('tri') and (sh < -0.003 and sl > 0.003): 
            hits.append({"text": "📐三角收斂", "class": "badge-tri"})
        if config.get('box') and (abs(sh) < 0.03 and abs(sl) < 0.03): 
            hits.append({"text": "📦旗箱整理", "class": "badge-box"})
        if config.get('vol') and (v[-1] > v_mean * 1.3): 
            hits.append({"text": "🚀今日爆量", "class": "badge-vol"})
        
        return {
            "labels": hits, "lines": (sh, ih, sl, il, x), 
            "price": round(float(df['Close'].iloc[-1]), 2), 
            "prev_close": round(float(df['Close'].iloc[-2]), 2),
            "vol": int(v[-1]), "df": df
        }
    except: return None

# ==========================================
# 3. CSS 樣式 (手機優化)
# ==========================================
st.markdown("""
    <style>
    .stApp { background-color: #f4f7f6; }
    .stock-card {
        background: white; padding: 16px; border-radius: 12px;
        margin-bottom: 15px; border-left: 6px solid #6c5ce7;
        box-shadow: 0 4px 10px rgba(0,0,0,0.06);
    }
    .card-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
    .sid-link { font-size: 1.1rem; font-weight: bold; color: #6c5ce7; text-decoration: none; }
    .price { font-weight: 800; font-size: 1.4rem; }
    .badge { padding: 4px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: bold; margin: 2px; color: white; display: inline-block; }
    .badge-tri { background-color: #6c5ce7; }
    .badge-box { background-color: #2d3436; }
    .badge-vol { background-color: #d63031; }
    .badge-none { background-color: #b2bec3; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 4. 側邊欄與模式控制
# ==========================================
db = load_full_db()
modes = ["⚡ 今日即時監控 (自動)", "⏳ 歷史形態搜尋 (手動)", "🌐 顯示所有股票連結"]

with st.sidebar:
    st.title("🎯 台股形態大師 Pro")
    selected_mode = st.radio("模式選擇", modes, index=modes.index(st.session_state.current_mode))
    st.session_state.current_mode = selected_mode
    st.divider()
    
    if selected_mode == "⚡ 今日即時監控 (自動)":
        st_autorefresh(interval=300000, key="auto_refresh")
        t_min_v = st.number_input("最低成交量 (張)", value=300)
        current_config = {'tri': True, 'box': True, 'vol': True}
        run_now = True
    elif selected_mode == "⏳ 歷史形態搜尋 (手動)":
        h_sid = st.text_input("輸入股票代號 (如: 2330)", placeholder="2330")
        current_config = {'tri': True, 'box': True, 'vol': True}
        run_now = st.button("🚀 開始分析", type="primary", use_container_width=True)
    else:
        run_now = False

# ==========================================
# 5. 主畫面渲染
# ==========================================
if selected_mode == "🌐 顯示所有股票連結":
    st.subheader("📑 電子股快速導航")
    for sid, name in db.items():
        st.markdown(f'• [{sid} {name}](https://tw.stock.yahoo.com/quote/{sid.split(".")[0]})')

elif run_now:
    targets = list(db.items())
    if selected_mode == "⏳ 歷史形態搜尋 (手動)" and h_sid:
        targets = [(f"{h_sid.upper()}.TW", "搜尋結果")]

    results = []
    # 使用併發加速處理多支股票，防止空白等待
    with st.spinner("正在同步即時報價與形態分析..."):
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_sid = {executor.submit(get_stock_data, s): (s, n) for s, n in targets}
            for future in concurrent.futures.as_completed(future_to_sid):
                sid, name = future_to_sid[future]
                df_stock = future.result()
                res = analyze_patterns(df_stock, current_config)
                if res:
                    # 過濾條件：若不是手動搜尋，則必須符合形態且量達標
                    if selected_mode == "⏳ 歷史形態搜尋 (手動)" or (res['labels'] and res['vol'] >= t_min_v):
                        res.update({"sid": sid, "name": name})
                        results.append(res)

    if not results:
        st.info("💡 目前沒有符合標籤條件的股票，請嘗試降低成交量門檻。")
    
    for item in results:
        # 計算漲跌顏色
        p_color = "#d63031" if item['price'] >= item['prev_close'] else "#27ae60"
        clean_id = item['sid'].split('.')[0]
        
        st.markdown(f"""
            <div class="stock-card">
                <div class="card-row">
                    <a class="sid-link" href="https://tw.stock.yahoo.com/quote/{clean_id}" target="_blank">🔗 {item['sid']}</a>
                    <span>{item['name']}</span>
                </div>
                <div class="card-row">
                    <span style="color:#666; font-size:0.9rem;">成交量: <b>{item['vol']:,} 張</b></span>
                    <span class="price" style="color:{p_color};">${item['price']:,}</span>
                </div>
                <div>
                    {" ".join([f'<span class="badge {l["class"]}">{l["text"]}</span>' for l in item['labels']]) if item['labels'] else '<span class="badge badge-none">🔘 一般走勢</span>'}
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        with st.expander("📈 檢視形態 K 線圖"):
            d_p = item['df'].tail(30)
            sh, ih, sl, il, x_r = item['lines']
            fig = make_subplots(rows=1, cols=1)
            fig.add_trace(go.Candlestick(x=d_p.index, open=d_p['Open'], high=d_p['High'], low=d_p['Low'], close=d_p['Close'], name="K線"))
            # 繪製趨勢線
            p_d = d_p.tail(15)
            fig.add_trace(go.Scatter(x=p_d.index, y=sh*x_r+ih, line=dict(color='#ff4757', width=2, dash='dash'), name="壓力線"))
            fig.add_trace(go.Scatter(x=p_d.index, y=sl*x_r+il, line=dict(color='#2ed573', width=2, dash='dot'), name="支撐線"))
            fig.update_layout(height=350, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False, template="plotly_white")
            st.plotly_chart(fig, use_container_width=True)

else:
    st.info("👈 請由左側選單選擇監控模式")
