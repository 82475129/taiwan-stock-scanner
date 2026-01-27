import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import os, json, time

# ==========================================
# 1. 系統環境與狀態初始化
# ==========================================
st.set_page_config(page_title="台股 Pro 旗艦終端", layout="wide", initial_sidebar_state="expanded")

if 'favorites' not in st.session_state:
    st.session_state.favorites = {} 
if 'last_results' not in st.session_state:
    st.session_state.last_results = [] 

@st.cache_data(ttl=3600)
def load_db():
    f = "taiwan_full_market.json"
    if os.path.exists(f):
        try:
            with open(f, "r", encoding="utf-8") as file:
                return json.load(file)
        except: return {"2330.TW": "台積電"}
    return {"2330.TW": "台積電"}

# ==========================================
# 2. 核心技術引擎 (含四種訊號邏輯)
# ==========================================
def run_analysis(sid, name, df, config, is_manual=False):
    if df is None or len(df) < 60: return None
    try:
        df = df.dropna()
        c = float(df["Close"].iloc[-1])
        v_last = df["Volume"].iloc[-1]
        v_avg = df["Volume"].iloc[-21:-1].mean()
        
        ma_m = df["Close"].rolling(config["p_ma_m"]).mean().iloc[-1]
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / loss).iloc[-1]))

        lb = config["p_lookback"]
        x = np.arange(lb)
        h, l = df["High"].iloc[-lb:].values, df["Low"].iloc[-lb:].values
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        
        active_hits = []
        # 四種訊號勾選連動
        if config["check_tri"] and (sh < -0.001 and sl > 0.001): active_hits.append("📐三角收斂")
        if config["check_box"] and (abs(sh) < 0.03 and abs(sl) < 0.03): active_hits.append("📦箱型整理")
        if config["check_vol"] and (v_last > v_avg * 1.8): active_hits.append("🚀今日爆量")
        if config["check_rsi"]:
            if rsi < 35: active_hits.append("💧超跌反彈")
            if rsi > 70: active_hits.append("🔥高點警戒")

        bias = (c - ma_m) / ma_m * 100
        
        # 決定是否顯示
        should_show = True if is_manual else bool(active_hits)
        if not is_manual:
            if config["f_ma_filter"] and c < ma_m: should_show = False
            if config["f_bias_filter"] and bias > 10: should_show = False
            
        if should_show:
            return {
                "sid": sid, "name": name, "price": round(c, 2), "vol": int(v_last/1000), 
                "bias": round(bias, 1), "rsi": round(rsi, 1), "hits": active_hits,
                "df": df, "lines": (sh, ih, sl, il, x)
            }
    except: pass
    return None

# ==========================================
# 3. Sidebar：手動按鈕、訊號勾選、專業參數
# ==========================================
full_db = load_db()
with st.sidebar:
    st.title("🛡️ 戰術控制台")
    app_mode = st.radio("模式切換", ["⚡ 全市場自動掃描", "🔍 手動搜尋", "❤️ 追蹤清單"])
    
    st.divider()
    # 訊號勾選區 (主控訊號)
    st.subheader("📡 訊號監控開關")
    check_tri = st.checkbox("📐 三角收斂", True)
    check_box = st.checkbox("📦 箱型整理", True)
    check_vol = st.checkbox("🚀 今日爆量", True)
    check_rsi = st.checkbox("🌡️ RSI 預警", False)
    
    st.divider()
    # 手動搜尋區 (依據要求移至左邊)
    if app_mode == "🔍 手動搜尋":
        st.subheader("個股手動查詢")
        search_input = st.text_input("輸入代碼 (2330, 2454)", placeholder="代碼用逗號隔開")
        btn_manual = st.button("🔍 執行搜尋", type="primary", use_container_width=True)
    else:
        search_input = ""
        btn_manual = False

    st.divider()
    # 收藏列表
    st.subheader("❤️ 我的最愛清單")
    if st.session_state.favorites:
        st.dataframe(pd.DataFrame([{"代碼": k, "名稱": v} for k, v in st.session_state.favorites.items()]), hide_index=True)
        if st.button("🗑️ 清空收藏", use_container_width=True):
            st.session_state.favorites = {}; st.rerun()

    with st.expander("🛠️ 進階指標參數"):
        p_ma_m = st.number_input("均線天數", value=20)
        p_lookback = st.slider("形態天數", 10, 30, 15)
        f_ma_filter = st.checkbox("僅看 MA20 之上", True)
        f_bias_filter = st.checkbox("過濾高乖離", True)
        min_v = st.number_input("成交量門檻", value=500)
        scan_limit = st.slider("掃描上限", 50, 500, 100)
        config = locals() # 封裝所有參數

# ==========================================
# 4. 掃描執行邏輯
# ==========================================
st.title(f"📍 當前：{app_mode}")

# --- 自動掃描邏輯 ---
if app_mode == "⚡ 全市場自動掃描":
    # 只要模式是自動，且參數變動，就直接跑 (不需按鈕)
    codes = list(full_db.keys())
    results = []
    with st.status("📡 自動掃描過濾中...", expanded=False) as status:
        batch_size = 40
        for i in range(0, len(codes[:scan_limit]), batch_size):
            batch = codes[i:i+batch_size]
            data = yf.download(batch, period="6mo", group_by='ticker', progress=False)
            for sid in batch:
                df = data[sid] if len(batch) > 1 else data
                if not df.empty and (df["Volume"].iloc[-1] / 1000 >= min_v):
                    res = run_analysis(sid, full_db.get(sid, "未知"), df, config)
                    if res: results.append(res)
        st.session_state.last_results = results
        status.update(label=f"✅ 掃描完畢 (符合：{len(results)} 檔)", state="complete")

# --- 手動搜尋邏輯 ---
elif app_mode == "🔍 手動搜尋" and btn_manual:
    if search_input:
        codes = [c.strip()+".TW" if "." not in c else c.strip().upper() for c in search_input.split(",")]
        manual_results = []
        with st.spinner("個股數據抓取中..."):
            data = yf.download(codes, period="6mo", group_by='ticker', progress=False)
            for sid in codes:
                df = data[sid] if len(codes) > 1 else data
                if not df.empty:
                    res = run_analysis(sid, full_db.get(sid, "未知"), df, config, is_manual=True)
                    if res: manual_results.append(res)
            st.session_state.last_results = manual_results

# --- 追蹤清單邏輯 (免掃描) ---
elif app_mode == "❤️ 追蹤清單":
    st.session_state.last_results = [r for r in st.session_state.last_results if r['sid'] in st.session_state.favorites]

# ==========================================
# 5. 數據呈現與 K 線輔助線
# ==========================================
display_list = st.session_state.last_results

if display_list:
    # 1. 概覽表
    table_data = [{"收藏": "❤️" if r['sid'] in st.session_state.favorites else "🤍", "代碼": r['sid'], "名稱": r["name"], "價": r["price"], "RSI": r["rsi"], "訊號": ", ".join(r["hits"])} for r in display_list]
    st.dataframe(pd.DataFrame(table_data), hide_index=True, use_container_width=True)

    # 2. 詳細 K 線
    for r in display_list:
        c1, c2 = st.columns([8, 1])
        with c1:
            is_fav = r['sid'] in st.session_state.favorites
            with st.expander(f"{'❤️' if is_fav else '🔍'} {r['sid']} {r['name']} | {', '.join(r['hits'])}", expanded=(app_mode != "⚡ 全市場自動掃描")):
                df_t, (sh, ih, sl, il, x) = r["df"].iloc[-50:], r["lines"]
                fig = go.Figure(data=[go.Candlestick(x=df_t.index, open=df_t['Open'], high=df_t['High'], low=df_t['Low'], close=df_t['Close'], name='K線')])
                
                # 趨勢線連動
                if ("📐" in "".join(r["hits"]) and check_tri) or ("📦" in "".join(r["hits"]) and check_box):
                    fig.add_scatter(x=df_t.index[-config["p_lookback"]:], y=sh*x+ih, mode='lines', line=dict(color='red', dash='dash'), name='壓')
                    fig.add_scatter(x=df_t.index[-config["p_lookback"]:], y=sl*x+il, mode='lines', line=dict(color='green', dash='dash'), name='支')
                
                fig.update_layout(height=450, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig, use_container_width=True)
        with c2:
            if st.button("❤️" if not is_fav else "🗑️", key=f"btn_{r['sid']}", use_container_width=True):
                if is_fav: del st.session_state.favorites[r['sid']]
                else: st.session_state.favorites[r['sid']] = r['name']
                st.rerun()
else:
    st.warning("目前無符合資料。請在左側調整訊號勾選或執行搜尋。")
