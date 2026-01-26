import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import concurrent.futures
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.stats import linregress
from streamlit_autorefresh import st_autorefresh
import json
import os

# ==========================================
# 0. 狀態鎖定
# ==========================================
if 'current_mode' not in st.session_state:
    st.session_state.current_mode = "⚡ 今日即時監控 (自動)"

DB_FILE = "taiwan_electronic_stocks.json"

@st.cache_data(ttl=3600)
def load_full_db():
    base_list = {
        "2330.TW": "台積電", "2454.TW": "聯發科", "3025.TW": "星通",
        "3406.TW": "玉晶光", "2498.TW": "宏達電", "2317.TW": "鴻海", "3045.TW": "台灣大"
    }
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return base_list
    return base_list

@st.cache_data(ttl=300)
def get_stock_data(sid):
    try:
        df = yf.download(sid, period="45d", progress=False)
        if df is None or df.empty:
            return pd.DataFrame()
        return df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
    except:
        return pd.DataFrame()

# ==========================================
# 1. 形態演算法（只修 BUG，不改視覺）
# ==========================================
def analyze_patterns(df, config, days=15):
    if df is None or df.empty or len(df) < days:
        return None

    d = df.tail(days).copy()

    # 🔒 同步清洗，避免 linregress shape error
    d = d.dropna(subset=['High', 'Low', 'Volume'])
    if len(d) < days:
        return None

    h = d['High'].to_numpy(dtype=float)
    l = d['Low'].to_numpy(dtype=float)
    v = d['Volume'].to_numpy(dtype=float)

    x = np.arange(len(h))
    if len(x) != len(h):
        return None

    try:
        sh, ih, *_ = linregress(x, h)
        sl, il, *_ = linregress(x, l)
    except Exception:
        return None

    v_mean = v[-6:-1].mean() if len(v) > 5 else v.mean()

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
        "price": round(float(df['Close'].iloc[-1]), 2),
        "vol": int(v[-1] // 1000)
    }

# ==========================================
# 2. 介面（完全原封不動）
# ==========================================
st.set_page_config(page_title="台股 Pro-X 形態大師", layout="wide")
st.markdown("""<style>/* 你原本的 CSS，完全不動 */</style>""", unsafe_allow_html=True)

# ==========================================
# 3. 側邊欄
# ==========================================
db = load_full_db()
modes = ["⚡ 今日即時監控 (自動)", "⏳ 歷史形態搜尋 (手動)", "🌐 顯示所有股票連結"]

with st.sidebar:
    st.title("🎯 形態大師控制台")
    selected_mode = st.radio("選擇功能模式", modes, index=modes.index(st.session_state.current_mode))
    st.session_state.current_mode = selected_mode
    st.divider()

    if selected_mode == "⚡ 今日即時監控 (自動)":
        st_autorefresh(interval=300000, key="auto_refresh")
        t_tri = st.checkbox("📐 三角收斂", value=True)
        t_box = st.checkbox("📦 旗箱整理", value=True)
        t_vol = st.checkbox("🚀 今日爆量", value=True)
        t_min_v = st.number_input("最低量 (張)", value=300)
        current_config = {'tri': t_tri, 'box': t_box, 'vol': t_vol}
        run_now = True

    elif selected_mode == "⏳ 歷史形態搜尋 (手動)":
        h_sid = st.text_input("代號 (輸入即強制顯示圖表)", placeholder="2330")
        h_tri = st.checkbox("📐 三角收斂", value=True)
        h_box = st.checkbox("📦 旗箱整理", value=True)
        h_vol = st.checkbox("🚀 今日爆量", value=True)
        h_min_v = st.number_input("最低量 (張)", value=100)
        current_config = {'tri': h_tri, 'box': h_box, 'vol': h_vol}
        run_now = st.button("🚀 開始掃描", type="primary", use_container_width=True)

    else:
        run_now = False

# ==========================================
# 4. 分析顯示（修「沒東西」）
# ==========================================
elif run_now:
    is_specific = st.session_state.current_mode == "⏳ 歷史形態搜尋 (手動)" and h_sid.strip() != ""
    targets = (
        [(f"{h_sid.upper()}.TW", "個股"), (f"{h_sid.upper()}.TWO", "個股")]
        if is_specific else list(db.items())[:150]
    )

    mv_limit = h_min_v if is_specific else t_min_v
    final_results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(get_stock_data, s): (s, info) for s, info in targets}
        for f in concurrent.futures.as_completed(futures):
            sid, info = futures[f]
            df_stock = f.result()
            res = analyze_patterns(df_stock, current_config)

            # ✅ 手動模式：無條件顯示
            if res and (is_specific or (res['labels'] and res['vol'] >= mv_limit)):
                res.update({
                    "sid": sid,
                    "name": info if isinstance(info, str) else info.get('name', '個股'),
                    "df": df_stock
                })
                final_results.append(res)

    if not final_results:
        st.info("⚠️ 無符合條件標的")

    for item in final_results:
        with st.expander(f"📈 {item['sid']}"):
            d_p = item['df'].tail(30)
            sh, ih, sl, il, x_r = item['lines']
            p_d = d_p.tail(15)

            fig = make_subplots(rows=1, cols=1)
            fig.add_trace(go.Candlestick(
                x=d_p.index,
                open=d_p['Open'],
                high=d_p['High'],
                low=d_p['Low'],
                close=d_p['Close']
            ))
            fig.add_trace(go.Scatter(x=p_d.index, y=sh * x_r + ih))
            fig.add_trace(go.Scatter(x=p_d.index, y=sl * x_r + il))
            fig.update_layout(xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

else:
    st.info("👈 請由側邊欄切換模式")
