import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import re
import concurrent.futures
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.stats import linregress
from bs4 import BeautifulSoup
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
import json
import os

# ==========================================
# 0. 強大資料庫與數據引擎
# ==========================================
DB_FILE = "taiwan_electronic_stocks.json"

@st.cache_data(ttl=3600)
def load_full_db():
    base_list = {"2330.TW": "台積電", "2454.TW": "聯發科", "3025.TW": "星通", 
                 "3406.TW": "玉晶光", "2498.TW": "宏達電", "2317.TW": "鴻海", "3045.TW": "台灣大"}
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except: return base_list
    return base_list

@st.cache_data(ttl=300)
def get_stock_data(sid):
    try: 
        df = yf.download(sid, period="45d", progress=False)
        return df.dropna() if not df.empty else pd.DataFrame()
    except: return pd.DataFrame()

# ==========================================
# 1. 形態演算法 (三角、旗箱、爆量)
# ==========================================
def analyze_patterns(df, config, days=15):
    if df is None or df.empty or len(df) < days: return None
    try:
        d = df.tail(days).copy()
        h = d['High'].values.flatten().astype(float)
        l = d['Low'].values.flatten().astype(float)
        v = d['Volume'].values.flatten().astype(float)
        x = np.arange(len(h))
        
        # 線性回歸計算斜率
        sh, ih, _, _, _ = linregress(x, h) 
        sl, il, _, _, _ = linregress(x, l) 
        
        v_mean = v[-6:-1].mean() if len(v)>5 else v.mean()
        
        hits = []
        # 三角收斂邏輯
        if config.get('tri') and (sh < -0.003 and sl > 0.003): hits.append("📐三角收斂")
        # 旗箱整理邏輯
        if config.get('box') and (abs(sh) < 0.03 and abs(sl) < 0.03): hits.append("📦旗箱整理")
        # 今日爆量邏輯
        if config.get('vol') and (v[-1] > v_mean * 1.3): hits.append("🚀今日爆量")
        
        if hits:
            return {
                "labels": hits, 
                "lines": (sh, ih, sl, il, x), 
                "price": round(float(df['Close'].iloc[-1]), 2), 
                "vol": int(v[-1]//1000)
            }
    except: return None
    return None

# ==========================================
# 2. 手機版專屬樣式 (解決排版擠壓)
# ==========================================
st.set_page_config(page_title="台股 Pro-X 形態大師", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: #f4f7f6; }
    .stock-card {
        background: white; padding: 16px; border-radius: 12px;
        margin-bottom: 15px; border-left: 6px solid #6c5ce7;
        box-shadow: 0 4px 10px rgba(0,0,0,0.06);
    }
    .card-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
    .sid-link { font-size: 1.2rem; font-weight: bold; color: #6c5ce7; text-decoration: none; }
    .s-name { font-size: 1rem; color: #333; font-weight: 500; }
    .price { color: #d63031; font-weight: 800; font-size: 1.3rem; }
    .badge {
        background: #efecff; color: #6c5ce7; padding: 3px 10px; 
        border-radius: 6px; font-size: 0.75rem; font-weight: bold; 
        border: 1px solid #6c5ce7; margin-right: 5px; margin-top: 5px;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 側邊欄：完整功能分類
# ==========================================
db = load_full_db()

with st.sidebar:
    st.title("🎯 形態大師控制台")
    # 模式選擇
    mode = st.radio("功能模式", ["⚡ 今日即時監控 (自動)", "⏳ 歷史形態搜尋 (手動)"], index=0)
    st.divider()
    
    if "今日" in mode:
        st_autorefresh(interval=300000, key="auto_ref_today")
        st.subheader("今日監控設定")
        t_min_v = st.number_input("最低成交量 (張)", value=300)
        # 預設監控今日的三角與爆量
        current_config = {'tri': True, 'box': False, 'vol': True}
        run_now = True
    else:
        st.subheader("歷史形態篩選")
        h_sid = st.text_input("輸入代號 (選填優先)", placeholder="例如: 2330")
        h_tri = st.checkbox("搜尋「三角收斂」", value=True)
        h_box = st.checkbox("搜尋「旗箱整理」", value=True)
        h_vol = st.checkbox("搜尋「今日爆量」", value=True)
        h_min_v = st.number_input("搜尋最低量 (張)", value=100)
        current_config = {'tri': h_tri, 'box': h_box, 'vol': h_vol}
        run_now = st.button("🚀 開始掃描資料庫", type="primary", use_container_width=True)

# ==========================================
# 4. 分析與卡片渲染
# ==========================================
if run_now:
    st.subheader(f"🔍 {mode} 結果")
    
    # 確定名單範圍
    if "手動" in mode and h_sid:
        targets = [(f"{h_sid.upper()}.TW", "手動"), (f"{h_sid.upper()}.TWO", "手動")]
    else:
        targets = list(db.items())[:150] # 掃描資料庫前 150 檔

    mv_limit = t_min_v if "今日" in mode else h_min_v
    scan_results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(get_stock_data, s): (s, info) for s, info in targets}
        for f in concurrent.futures.as_completed(futures):
            sid, info = futures[f]
            df_stock = f.result()
            res = analyze_patterns(df_stock, current_config, days=15)
            if res and (res['vol'] >= mv_limit or ("手動" in mode and h_sid)):
                res.update({"sid": sid, "name": info['name'] if isinstance(info, dict) else info, "df": df_stock})
                scan_results.append(res)

    if not scan_results:
        st.info("💡 目前未發現符合形態的個股。")

    for item in scan_results:
        clean_id = item['sid'].split('.')[0]
        badges_html = "".join([f'<span class="badge">{l}</span>' for l in item['labels']])
        
        # 顯示卡片 (取代 Table)
        st.markdown(f"""
            <div class="stock-card">
                <div class="card-row">
                    <a class="sid-link" href="https://tw.stock.yahoo.com/quote/{clean_id}" target="_blank">🔗 {item['sid']}</a>
                    <span class="s-name">{item['name']}</span>
                </div>
                <div class="card-row">
                    <span style="color:#666; font-size:0.9rem;">成交量: <b>{item['vol']} 張</b></span>
                    <span class="price">${item['price']}</span>
                </div>
                <div class="badge-box">{badges_html}</div>
            </div>
        """, unsafe_allow_html=True)
        
        # 展開 K 線分析
        with st.expander("📈 展開分析圖表"):
            d_tail = item['df'].tail(30)
            sh, ih, sl, il, x_range = item['lines']
            fig = make_subplots(rows=1, cols=1)
            fig.add_trace(go.Candlestick(x=d_tail.index, open=d_tail['Open'], high=d_tail['High'], low=d_tail['Low'], close=d_tail['Close'], name="K"))
            
            # 趨勢線繪製
            plot_d = d_tail.tail(15)
            fig.add_trace(go.Scatter(x=plot_d.index, y=sh*x_range+ih, line=dict(color='red', width=3, dash='dash')))
            fig.add_trace(go.Scatter(x=plot_d.index, y=sl*x_range+il, line=dict(color='green', width=3, dash='dot')))
            
            fig.update_layout(height=400, margin=dict(l=5,r=5,t=5,b=5), xaxis_rangeslider_visible=False, showlegend=False, template="plotly_white")
            st.plotly_chart(fig, use_container_width=True, key=f"f_{item['sid']}")
else:
    st.info("👈 請從側邊欄選單開啟「今日監控」或執行「手動搜尋」")
