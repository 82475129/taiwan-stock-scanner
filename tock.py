import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import concurrent.futures
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.stats import linregress
from streamlit_autorefresh import st_autorefresh
import os

# ==========================================
# 0. 系統核心設定與導航鎖定
# ==========================================
st.set_page_config(page_title="台股 Pro-X 形態大師", layout="wide")

if 'current_mode' not in st.session_state:
    st.session_state.current_mode = "⚡ 今日即時監控 (自動)"

# 預設電子標的資料庫
DEFAULT_DB = {
    "2330.TW": "台積電", "2454.TW": "聯發科", "3025.TW": "星通", 
    "3406.TW": "玉晶光", "2498.TW": "宏達電", "2317.TW": "鴻海", "3045.TW": "台灣大"
}

# ==========================================
# 1. 精準數據抓取 (解決股價錯誤關鍵)
# ==========================================
@st.cache_data(ttl=300)
def get_clean_stock_data(sid):
    try:
        ticker = yf.Ticker(sid)
        # 抓取 60 天歷史 K 線
        df = ticker.history(period="60d", interval="1d")
        if df.empty: return None
        
        # 強制從 fast_info 抓取盤中最新價，若失敗則取 Close 最後一筆
        try:
            current_price = float(ticker.fast_info['last_price'])
        except:
            current_price = float(df['Close'].iloc[-1])
            
        return {"df": df.dropna(), "price": current_price}
    except:
        return None

# ==========================================
# 2. 形態演算法 (三角/期箱/爆量)
# ==========================================
def analyze_patterns(data_obj, config, days=15):
    if not data_obj or data_obj['df'].empty or len(data_obj['df']) < days: return None
    df = data_obj['df']
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
            "labels": hits, "lines": (sh, ih, sl, il, x), 
            "price": data_obj['price'], "vol": int(v[-1]//1000)
        }
    except: return None

# ==========================================
# 3. 手機版 UI 樣式優化
# ==========================================
st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; }
    .stock-card {
        background: white; padding: 18px; border-radius: 15px;
        margin-bottom: 15px; border-left: 8px solid #6c5ce7;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }
    .card-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
    .sid-title { font-size: 1.2rem; font-weight: bold; color: #2d3436; }
    .price { color: #d63031; font-weight: 900; font-size: 1.4rem; }
    .badge { padding: 5px 12px; border-radius: 8px; font-size: 0.8rem; font-weight: bold; margin-right: 5px; color: white; }
    .badge-tri { background-color: #6c5ce7; } /* 紫色 */
    .badge-box { background-color: #636e72; } /* 灰色 */
    .badge-vol { background-color: #d63031; } /* 紅色 */
    .badge-none { background-color: #b2bec3; }
    .link-item {
        display: block; background: white; border: 1px solid #dfe6e9; padding: 15px;
        margin-bottom: 10px; border-radius: 12px; text-decoration: none; color: #2d3436;
        font-weight: 600; text-align: center;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 4. 導航與功能邏輯
# ==========================================
modes = ["⚡ 今日即時監控 (自動)", "⏳ 歷史形態搜尋 (手動)", "🌐 顯示所有股票連結"]
with st.sidebar:
    st.title("🎯 形態大師 Pro")
    st.session_state.current_mode = st.radio("功能模式", modes, index=modes.index(st.session_state.current_mode))
    st.divider()
    
    if "今日" in st.session_state.current_mode:
        st_autorefresh(interval=300000)
        config = {'tri': st.checkbox("📐 三角收斂", True), 'box': st.checkbox("📦 旗箱整理", True), 'vol': st.checkbox("🚀 今日爆量", True)}
        min_v = st.number_input("最低量 (張)", 300)
        run = True
    elif "歷史" in st.session_state.current_mode:
        h_sid = st.text_input("輸入個股代號", "2330").strip().upper()
        config = {'tri': True, 'box': True, 'vol': True}
        run = st.button("🚀 執行搜尋", type="primary", use_container_width=True)
    else:
        run = False

# ==========================================
# 5. 渲染頁面
# ==========================================
if st.session_state.current_mode == "🌐 顯示所有股票連結":
    st.subheader("🌐 股市快速跳轉")
    st.markdown('<div style="display:grid; grid-template-columns:1fr 1fr; gap:10px;">'
                '<a class="link-item" href="https://tw.stock.yahoo.com" target="_blank">Yahoo 股市</a>'
                '<a class="link-item" href="https://www.wantgoo.com" target="_blank">玩股網</a>'
                '</div>', unsafe_allow_html=True)
    st.divider()
    for sid, name in DEFAULT_DB.items():
        st.markdown(f'<a href="https://tw.stock.yahoo.com/quote/{sid.split(".")[0]}" target="_blank" class="link-item">🔗 {sid} {name}</a>', unsafe_allow_html=True)

elif run:
    targets = [(f"{h_sid}.TW", "個股"), (f"{h_sid}.TWO", "個股")] if "歷史" in st.session_state.current_mode else list(DEFAULT_DB.items())
    
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(get_clean_stock_data, s): (s, n) for s, n in targets}
        for f in concurrent.futures.as_completed(futs):
            s, n = futs[f]
            data = f.result()
            res = analyze_patterns(data, config)
            if res:
                # 搜尋模式強制顯示；監控模式需過濾形態
                if ("歷史" in st.session_state.current_mode) or (res['labels'] and res['vol'] >= min_v):
                    res.update({"sid": s, "name": n, "df": data['df']})
                    results.append(res)

    if not results: st.warning("未找到匹配標的。")
    for item in results:
        b_html = "".join([f'<span class="badge {l["class"]}">{l["text"]}</span>' for l in item['labels']]) or '<span class="badge badge-none">🔘 一般走勢</span>'
        st.markdown(f"""
            <div class="stock-card">
                <div class="card-row">
                    <span class="sid-title">🔗 <a href="https://tw.stock.yahoo.com/quote/{item['sid'].split('.')[0]}" target="_blank" style="text-decoration:none; color:#6c5ce7;">{item['sid']}</a></span>
                    <span style="color:#636e72; font-weight:bold;">{item['name']}</span>
                </div>
                <div class="card-row">
                    <span style="font-size:0.9rem; color:#636e72;">量: <b>{item['vol']:,} 張</b></span>
                    <span class="price">${item['price']:,.1f}</span>
                </div>
                <div style="margin-top:10px;">{b_html}</div>
            </div>
        """, unsafe_allow_html=True)
        with st.expander("📈 展開 K 線圖分析"):
            df_p = item['df'].tail(30); sh, ih, sl, il, x_r = item['lines']
            fig = make_subplots(rows=1, cols=1)
            fig.add_trace(go.Candlestick(x=df_p.index, open=df_p['Open'], high=df_p['High'], low=df_p['Low'], close=df_p['Close'], name="K"))
            fig.add_trace(go.Scatter(x=df_p.tail(15).index, y=sh*x_r+ih, line=dict(color='#ff4757', width=2, dash='dash')))
            fig.add_trace(go.Scatter(x=df_p.tail(15).index, y=sl*x_r+il, line=dict(color='#2ed573', width=2, dash='dot')))
            fig.update_layout(height=350, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False, template="plotly_white", showlegend=False)
            st.plotly_chart(fig, use_container_width=True, key=f"fig_{item['sid']}")
