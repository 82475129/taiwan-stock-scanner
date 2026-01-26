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
# 0. 資料庫引擎
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
# 1. 形態核心演算法 (顏色與邏輯整合)
# ==========================================
def analyze_patterns(df, config, days=15):
    if df is None or df.empty or len(df) < days: return None
    try:
        d = df.tail(days).copy()
        h = d['High'].values.flatten().astype(float)
        l = d['Low'].values.flatten().astype(float)
        v = d['Volume'].values.flatten().astype(float)
        x = np.arange(len(h))
        
        sh, ih, _, _, _ = linregress(x, h) 
        sl, il, _, _, _ = linregress(x, l) 
        v_mean = v[-6:-1].mean() if len(v)>5 else v.mean()
        
        hits = []
        # 紫色 - 三角收斂
        if config.get('tri') and (sh < -0.003 and sl > 0.003): 
            hits.append({"text": "📐三角收斂", "class": "badge-tri"})
        # 灰色 - 旗箱整理
        if config.get('box') and (abs(sh) < 0.03 and abs(sl) < 0.03): 
            hits.append({"text": "📦旗箱整理", "class": "badge-box"})
        # 紅色 - 今日爆量
        if config.get('vol') and (v[-1] > v_mean * 1.3): 
            hits.append({"text": "🚀今日爆量", "class": "badge-vol"})
        
        return {
            "labels": hits, 
            "lines": (sh, ih, sl, il, x), 
            "price": round(float(df['Close'].iloc[-1]), 2), 
            "vol": int(v[-1]//1000)
        }
    except: return None

# ==========================================
# 2. 手機版專屬 CSS 樣式
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
    .sid-link { font-size: 1.1rem; font-weight: bold; color: #6c5ce7; text-decoration: none; }
    .s-name { font-size: 1rem; color: #333; font-weight: 500; }
    .price { color: #d63031; font-weight: 800; font-size: 1.2rem; }
    .badge {
        padding: 4px 10px; border-radius: 6px; font-size: 0.75rem; 
        font-weight: bold; margin-right: 5px; margin-top: 5px; color: white; display: inline-block;
    }
    .badge-tri { background-color: #6c5ce7; }
    .badge-box { background-color: #2d3436; }
    .badge-vol { background-color: #d63031; }
    .badge-none { background-color: #b2bec3; }
    
    /* 連結模式按鈕 */
    .link-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
    .link-btn { 
        background: #fff; border: 1px solid #ddd; padding: 12px; border-radius: 8px; 
        text-align: center; text-decoration: none; color: #333; font-weight: bold; font-size: 0.9rem;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 側邊欄控制與導航
# ==========================================
db = load_full_db()

with st.sidebar:
    st.title("🎯 形態大師控制台")
    mode = st.radio("選擇功能模式", ["⚡ 今日即時監控 (自動)", "⏳ 歷史形態搜尋 (手動)", "🌐 顯示所有股票連結"], index=0)
    st.divider()
    
    if mode == "⚡ 今日即時監控 (自動)":
        st_autorefresh(interval=300000, key="auto_refresh")
        st.subheader("📡 自動監控過濾")
        t_tri = st.checkbox("📐 三角收斂", value=True)
        t_box = st.checkbox("📦 旗箱整理", value=True)
        t_vol = st.checkbox("🚀 今日爆量", value=True)
        t_min_v = st.number_input("最低成交量 (張)", value=300)
        current_config = {'tri': t_tri, 'box': t_box, 'vol': t_vol}
        run_now = True
    elif mode == "⏳ 歷史形態搜尋 (手動)":
        st.subheader("⏳ 搜尋指定條件")
        h_sid = st.text_input("輸入個股代號 (強制顯示圖表)", placeholder="例如: 2330")
        h_tri = st.checkbox("📐 三角收斂", value=True)
        h_box = st.checkbox("📦 旗箱整理", value=True)
        h_vol = st.checkbox("🚀 今日爆量", value=True)
        h_min_v = st.number_input("最低成交量 (張)", value=100)
        current_config = {'tri': h_tri, 'box': h_box, 'vol': h_vol}
        run_now = st.button("🚀 開始掃描資料庫", type="primary", use_container_width=True)
    else:
        run_now = False

# ==========================================
# 4. 各模式渲染邏輯
# ==========================================
if mode == "🌐 顯示所有股票連結":
    st.subheader("🌐 常用股市工具")
    st.markdown("""
    <div class="link-grid">
        <a class="link-btn" href="https://tw.stock.yahoo.com" target="_blank">📉 Yahoo 股市</a>
        <a class="link-btn" href="https://www.wantgoo.com" target="_blank">📈 玩股網</a>
        <a class="link-btn" href="https://www.tradingview.com" target="_blank">📊 TradingView</a>
        <a class="link-btn" href="https://goodinfo.tw" target="_blank">📒 Goodinfo</a>
    </div>
    """, unsafe_allow_html=True)
    st.divider()
    st.subheader("📑 電子股資料庫快速連結")
    cols = st.columns(2)
    for idx, (sid, name) in enumerate(db.items()):
        clean_id = sid.split('.')[0]
        s_name = name if isinstance(name, str) else name.get('name', '個股')
        cols[idx % 2].link_button(f"{clean_id} {s_name}", f"https://tw.stock.yahoo.com/quote/{clean_id}", use_container_width=True)

elif run_now:
    st.subheader(f"🔍 {mode} ({datetime.now().strftime('%H:%M:%S')})")
    # 強制顯示判斷
    is_specific = bool(mode == "⏳ 歷史形態搜尋 (手動)" and h_sid)
    
    if is_specific:
        targets = [(f"{h_sid.upper()}.TW", "手動"), (f"{h_sid.upper()}.TWO", "手動")]
    else:
        targets = list(db.items())[:150]

    mv_limit = t_min_v if mode == "⚡ 今日即時監控 (自動)" else h_min_v
    final_results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(get_stock_data, s): (s, info) for s, info in targets}
        for f in concurrent.futures.as_completed(futures):
            sid, info = futures[f]
            df_stock = f.result()
            res = analyze_patterns(df_stock, current_config)
            
            if res:
                # 判斷是否符合顯示條件
                if is_specific or (res['labels'] and res['vol'] >= mv_limit):
                    res.update({"sid": sid, "name": info if isinstance(info, str) else info.get('name', '個股'), "df": df_stock})
                    final_results.append(res)

    if not final_results:
        st.info("💡 目前未發現符合條件的標的。")

    for item in final_results:
        clean_id = item['sid'].split('.')[0]
        # 生成彩色標籤
        if item['labels']:
            b_html = "".join([f'<span class="badge {l["class"]}">{l["text"]}</span>' for l in item['labels']])
        else:
            b_html = '<span class="badge badge-none">🔘 一般走勢 (手動查詢)</span>'
        
        # 卡片顯示
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
                <div class="badge-box">{b_html}</div>
            </div>
        """, unsafe_allow_html=True)
        
        with st.expander("📈 展開精準趨勢圖表"):
            d_p = item['df'].tail(30); sh, ih, sl, il, x_r = item['lines']
            fig = make_subplots(rows=1, cols=1)
            fig.add_trace(go.Candlestick(x=d_p.index, open=d_p['Open'], high=d_p['High'], low=d_p['Low'], close=d_p['Close'], name="K"))
            # 趨勢線繪製 (末端15天)
            p_d = d_p.tail(15)
            fig.add_trace(go.Scatter(x=p_d.index, y=sh*x_r+ih, line=dict(color='#ff4757', width=3, dash='dash')))
            fig.add_trace(go.Scatter(x=p_d.index, y=sl*x_r+il, line=dict(color='#2ed573', width=3, dash='dot')))
            fig.update_layout(height=400, margin=dict(l=5,r=5,t=5,b=5), xaxis_rangeslider_visible=False, template="plotly_white", showlegend=False)
            st.plotly_chart(fig, use_container_width=True, key=f"fig_{item['sid']}")
else:
    st.info("👈 請從左側選單開始您的分析。")
