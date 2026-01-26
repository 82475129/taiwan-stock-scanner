import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import concurrent.futures
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.stats import linregress
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
import json
import os

# ==========================================
# 0. 狀態與導航管理
# ==========================================
if 'current_mode' not in st.session_state:
    st.session_state.current_mode = "⚡ 今日即時監控 (自動)"

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
        # 下載足夠的歷史數據以供計算
        df = yf.download(sid, period="60d", progress=False)
        return df.dropna() if not df.empty else pd.DataFrame()
    except: return pd.DataFrame()

# ==========================================
# 1. 形態核心演算法 (修正欄位抓取)
# ==========================================
def analyze_patterns(df, config, days=15):
    if df is None or df.empty or len(df) < days: return None
    try:
        # 取得最後 15 天數據進行線條回歸
        d = df.tail(days).copy()
        h = d['High'].values.flatten().astype(float)
        l = d['Low'].values.flatten().astype(float)
        v = d['Volume'].values.flatten().astype(float)
        
        # 【修正核心】確保抓取的是 Close 欄位的最後一個數值作為現價
        current_close = float(df['Close'].iloc[-1])
        
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
            "labels": hits, 
            "lines": (sh, ih, sl, il, x), 
            "price": current_close, # 正確的現價
            "vol": int(v[-1]//1000)
        }
    except: return None

# ==========================================
# 2. 手機版樣式設計
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
    .price { color: #d63031; font-weight: 800; font-size: 1.3rem; }
    .badge { padding: 4px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: bold; margin: 2px; color: white; display: inline-block; }
    .badge-tri { background-color: #6c5ce7; } .badge-box { background-color: #2d3436; } .badge-vol { background-color: #d63031; } .badge-none { background-color: #b2bec3; }
    .link-item {
        display: block; background: white; border: 1px solid #e0e0e0; padding: 15px;
        margin-bottom: 8px; border-radius: 10px; text-decoration: none; color: #333;
        font-weight: 600; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.03);
    }
    .link-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 側邊欄與模式同步
# ==========================================
db = load_full_db()
modes = ["⚡ 今日即時監控 (自動)", "⏳ 歷史形態搜尋 (手動)", "🌐 顯示所有股票連結"]

with st.sidebar:
    st.title("🎯 形態掃描儀")
    selected_mode = st.radio("功能模式", modes, index=modes.index(st.session_state.current_mode))
    st.session_state.current_mode = selected_mode
    st.divider()
    
    if "今日" in selected_mode:
        st_autorefresh(interval=300000, key="auto_refresh")
        t_tri = st.checkbox("📐 三角收斂", value=True)
        t_box = st.checkbox("📦 旗箱整理", value=True)
        t_vol = st.checkbox("🚀 今日爆量", value=True)
        t_min_v = st.number_input("最低成交量 (張)", value=300)
        current_config = {'tri': t_tri, 'box': t_box, 'vol': t_vol}
        run_now = True
    elif "歷史" in selected_mode:
        h_sid = st.text_input("個股代號 (強制顯示)", placeholder="例如: 2330")
        h_tri = st.checkbox("📐 三角收斂", value=True)
        h_box = st.checkbox("📦 旗箱整理", value=True)
        h_vol = st.checkbox("🚀 今日爆量", value=True)
        h_min_v = st.number_input("搜尋最低量", value=100)
        current_config = {'tri': h_tri, 'box': h_box, 'vol': h_vol}
        run_now = st.button("🚀 啟動掃描", type="primary", use_container_width=True)
    else:
        run_now = False

# ==========================================
# 4. 模式渲染
# ==========================================
if st.session_state.current_mode == "🌐 顯示所有股票連結":
    st.subheader("🌐 常用快捷工具")
    st.markdown('<div class="link-grid">'
                '<a class="link-item" href="https://tw.stock.yahoo.com" target="_blank">📉 Yahoo 股市</a>'
                '<a class="link-item" href="https://www.wantgoo.com" target="_blank">📈 玩股網</a>'
                '</div>', unsafe_allow_html=True)
    st.divider()
    st.subheader("📑 資料庫快速連結")
    for sid, name in db.items():
        clean_id = sid.split('.')[0]
        s_name = name if isinstance(name, str) else name.get('name', '個股')
        st.markdown(f'<a href="https://tw.stock.yahoo.com/quote/{clean_id}" target="_blank" class="link-item">{clean_id} {s_name}</a>', unsafe_allow_html=True)

elif run_now:
    st.subheader(f"🔍 {st.session_state.current_mode}")
    is_specific = bool("歷史" in st.session_state.current_mode and h_sid)
    # 如果有輸入代號，強制搜尋該代號的兩種後綴
    targets = [(f"{h_sid.upper()}.TW", "個股"), (f"{h_sid.upper()}.TWO", "個股")] if is_specific else list(db.items())[:150]
    mv_limit = t_min_v if "今日" in st.session_state.current_mode else h_min_v
    
    scan_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(get_stock_data, s): (s, info) for s, info in targets}
        for f in concurrent.futures.as_completed(futures):
            sid, info = futures[f]
            df_stock = f.result()
            res = analyze_patterns(df_stock, current_config)
            if res and (is_specific or (res['labels'] and res['vol'] >= mv_limit)):
                res.update({"sid": sid, "name": info if isinstance(info, str) else info.get('name', '個股'), "df": df_stock})
                scan_results.append(res)

    for item in scan_results:
        clean_id = item['sid'].split('.')[0]
        b_html = "".join([f'<span class="badge {l["class"]}">{l["text"]}</span>' for l in item['labels']]) if item['labels'] else '<span class="badge badge-none">🔘 一般走勢</span>'
        
        # 修正：精準顯示價格，並加入千分位
        formatted_price = f"{item['price']:,.1f}"
        
        st.markdown(f"""
            <div class="stock-card">
                <div class="card-row">
                    <a class="sid-link" href="https://tw.stock.yahoo.com/quote/{clean_id}" target="_blank">🔗 {item['sid']}</a>
                    <span class="s-name">{item['name']}</span>
                </div>
                <div class="card-row">
                    <span style="color:#666; font-size:0.9rem;">成交量: <b>{item['vol']:,} 張</b></span>
                    <span class="price">${formatted_price}</span>
                </div>
                <div>{b_html}</div>
            </div>
        """, unsafe_allow_html=True)
        
        with st.expander("📈 形態分析圖表"):
            d_p = item['df'].tail(30); sh, ih, sl, il, x_r = item['lines']; fig = make_subplots(rows=1, cols=1)
            fig.add_trace(go.Candlestick(x=d_p.index, open=d_p['Open'], high=d_p['High'], low=d_p['Low'], close=d_p['Close'], name="K"))
            # 趨勢線回歸
            p_d = d_p.tail(15)
            fig.add_trace(go.Scatter(x=p_d.index, y=sh*x_r+ih, line=dict(color='#ff4757', width=3, dash='dash')))
            fig.add_trace(go.Scatter(x=p_d.index, y=sl*x_r+il, line=dict(color='#2ed573', width=3, dash='dot')))
            fig.update_layout(height=400, margin=dict(l=5,r=5,t=5,b=5), xaxis_rangeslider_visible=False, template="plotly_white", showlegend=False)
            st.plotly_chart(fig, use_container_width=True, key=f"fig_{item['sid']}")
else:
    st.info("👈 請由左側選單開始")
