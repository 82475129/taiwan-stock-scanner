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
# 0. 強大資料庫引擎 (整合電子股名單)
# ==========================================
DB_FILE = "taiwan_electronic_stocks.json"

@st.cache_data(ttl=3600)
def load_and_sync_db():
    # 預設名單，防止檔案讀取失敗
    default_db = {"2330.TW": "台積電", "2454.TW": "聯發科", "3025.TW": "星通", 
                  "3406.TW": "玉晶光", "2498.TW": "宏達電", "3045.TW": "台灣大", "2450.TW": "神腦"}
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return default_db
    return default_db

# ==========================================
# 1. 精準形態演算法 (聚焦末端 15 天)
# ==========================================
@st.cache_data(ttl=600)
def get_clean_data(sid):
    try: 
        df = yf.download(sid, period="40d", progress=False)
        return df.dropna() if not df.empty else pd.DataFrame()
    except: return pd.DataFrame()

def analyze_tail_pattern(df, config):
    if df is None or df.empty or len(df) < 15: return None
    try:
        # 核心：只抓最後 15 天數據，這會讓三角收斂在手機圖表上非常尖銳
        d = df.tail(15).copy()
        h = d['High'].values.flatten().astype(float)
        l = d['Low'].values.flatten().astype(float)
        v = d['Volume'].values.flatten().astype(float)
        x = np.arange(len(h))
        
        # 計算斜率
        sh, ih, _, _, _ = linregress(x, h) # 高點斜率
        sl, il, _, _, _ = linregress(x, l) # 低點斜率
        
        # 判定條件 (微調靈敏度)
        is_tri = (sh < -0.003 and sl > 0.003) 
        v_mean = v[-6:-1].mean() if len(v)>5 else v.mean()
        is_vol = v[-1] > (v_mean * 1.2)
        is_box = (abs(sh) < 0.03 and abs(sl) < 0.03)

        hits = []
        if config['tri'] and is_tri: hits.append("📐末端收斂")
        if config['box'] and is_box: hits.append("📦橫盤整理")
        if config['vol'] and is_vol: hits.append("🚀今日爆量")
        
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
# 2. 手機版 UI 強化 (防止表格消失)
# ==========================================
st.set_page_config(page_title="台股 Pro-X 形態大師", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; }
    /* 手機卡片式設計 */
    .stock-card {
        background: white; padding: 16px; border-radius: 12px;
        margin-bottom: 12px; border-left: 6px solid #6c5ce7;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }
    .card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
    .card-mid { display: flex; justify-content: space-between; align-items: baseline; }
    .stock-id { font-size: 1.2rem; font-weight: bold; color: #6c5ce7; text-decoration: none; }
    .stock-name { font-size: 1rem; color: #444; font-weight: 500; }
    .price-tag { color: #d63031; font-weight: 800; font-size: 1.3rem; }
    .badge-box { margin-top: 10px; display: flex; gap: 6px; flex-wrap: wrap; }
    .badge {
        background: #efecff; color: #6c5ce7; padding: 4px 10px; 
        border-radius: 6px; font-size: 0.8rem; font-weight: bold;
        border: 1px solid #6c5ce7;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 側邊欄：功能解耦設定
# ==========================================
db = load_and_sync_db()

with st.sidebar:
    st.title("🎯 形態掃描儀")
    mode = st.radio("功能模式", ["📡 自動巡航 (5分刷新)", "🚀 手動即時掃描"])
    st.divider()
    
    if mode == "📡 自動巡航 (5分刷新)":
        st_autorefresh(interval=300000, key="auto_ref")
        # 自動模式預設全開
        c_tri, c_box, c_vol = True, False, True
        min_v = st.number_input("最低成交量 (張)", value=100)
        should_run = True
    else:
        st.subheader("手動篩選")
        m_sid = st.text_input("輸入代號 (選填)", placeholder="例如: 2330")
        c_tri = st.checkbox("末端收斂", value=True)
        c_box = st.checkbox("橫盤整理", value=False)
        c_vol = st.checkbox("今日爆量", value=True)
        min_v = st.number_input("最低成交量 (張)", value=0)
        should_run = st.button("🚀 開始手動掃描", type="primary", use_container_width=True)

# ==========================================
# 4. 執行與渲染
# ==========================================
if should_run:
    st.subheader(f"🔍 {mode} 結果")
    
    # 決定掃描標的
    if mode == "🚀 手動即時掃描" and m_sid:
        targets = [(f"{m_sid.upper()}.TW", {"name": "查詢中"}), (f"{m_sid.upper()}.TWO", {"name": "查詢中"})]
    else:
        # 自動掃描資料庫前 120 檔
        targets = list(db.items())[:120]

    config = {'tri': c_tri, 'box': c_box, 'vol': c_vol}
    scan_results = []
    
    # 多執行緒加速
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        f_to_s = {executor.submit(get_clean_data, s): (s, info) for s, info in targets}
        for f in concurrent.futures.as_completed(f_to_s):
            sid, info = f_to_s[f]
            df_stock = f.result()
            res = analyze_tail_pattern(df_stock, config)
            if res and (res['vol'] >= min_v or (mode == "🚀 手動即時掃描" and m_sid)):
                res.update({"sid": sid, "name": info['name'] if isinstance(info, dict) else info, "df": df_stock})
                scan_results.append(res)

    if not scan_results:
        st.info("💡 目前沒有符合形態的標的。")
    
    for item in scan_results:
        clean_sid = item['sid'].split('.')[0]
        badges_html = "".join([f'<span class="badge">{l}</span>' for l in item['labels']])
        
        # 顯示手機優化卡片 (取代表格)
        st.markdown(f"""
            <div class="stock-card">
                <div class="card-top">
                    <a class="stock-id" href="https://tw.stock.yahoo.com/quote/{clean_sid}" target="_blank">🔗 {item['sid']}</a>
                    <span class="stock-name">{item['name']}</span>
                </div>
                <div class="card-mid">
                    <span style="color:#666;">量: <b>{item['vol']} 張</b></span>
                    <span class="price-tag">${item['price']}</span>
                </div>
                <div class="badge-box">{badges_html}</div>
            </div>
        """, unsafe_allow_html=True)
        
        # 圖表展開
        with st.expander("📈 查看精準末端趨勢線"):
            d_plot = item['df'].tail(30)
            sh, ih, sl, il, x_range = item['lines']
            
            fig = make_subplots(rows=1, cols=1)
            # K線圖
            fig.add_trace(go.Candlestick(
                x=d_plot.index, open=d_plot['Open'], high=d_plot['High'], 
                low=d_plot['Low'], close=d_plot['Close'], name="K線"
            ))
            
            # 繪製末端 15 天趨勢線 (紅色壓力，綠色支撐)
            d_tail = d_plot.tail(15)
            fig.add_trace(go.Scatter(x=d_tail.index, y=sh*x_range+ih, line=dict(color='#ff4757', width=3, dash='dash'), name="壓力"))
            fig.add_trace(go.Scatter(x=d_tail.index, y=sl*x_range+il, line=dict(color='#2ed573', width=3, dash='dot'), name="支撐"))
            
            fig.update_layout(
                height=400, margin=dict(l=5,r=5,t=5,b=5),
                xaxis_rangeslider_visible=False,
                showlegend=False,
                template="plotly_white"
            )
            st.plotly_chart(fig, use_container_width=True, key=f"fig_{item['sid']}")
else:
    st.info("👈 請在側邊欄進行設定後開始。")
