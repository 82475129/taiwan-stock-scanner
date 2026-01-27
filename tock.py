import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import os, json

# ==========================================
# 1. 系統初始化與狀態鎖定 (介面功能完全保留)
# ==========================================
st.set_page_config(page_title="台股 Pro 旗艦戰情室", layout="wide", initial_sidebar_state="expanded")

# 核心記憶體：確保點擊按鈕時，資料不會被重置
if 'favorites' not in st.session_state:
    st.session_state.favorites = {} 
if 'results_data' not in st.session_state:
    st.session_state.results_data = [] 

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
# 2. 專業分析引擎 (四大訊號邏輯)
# ==========================================
def run_analysis(sid, name, df, config, is_manual=False):
    if df is None or len(df) < 60: return None
    try:
        df = df.dropna()
        c = float(df["Close"].iloc[-1])
        v_last = df["Volume"].iloc[-1]
        v_avg = df["Volume"].iloc[-21:-1].mean()
        
        ma_val = config.get("p_ma_m", 20)
        ma_m = df["Close"].rolling(ma_val).mean().iloc[-1]
        
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / loss).iloc[-1]))

        lb = config.get("p_lookback", 15)
        x = np.arange(lb)
        h, l = df["High"].iloc[-lb:].values, df["Low"].iloc[-lb:].values
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        
        active_hits = []
        if config.get("check_tri") and (sh < -0.001 and sl > 0.001): active_hits.append("📐三角收斂")
        if config.get("check_box") and (abs(sh) < 0.03 and abs(sl) < 0.03): active_hits.append("📦箱型整理")
        if config.get("check_vol") and (v_last > v_avg * 1.8): active_hits.append("🚀今日爆量")
        if config.get("check_rsi") and (rsi < 35 or rsi > 70): active_hits.append(f"🌡️RSI:{round(rsi)}")

        if is_manual:
            should_show = True
        else:
            should_show = bool(active_hits)
            if config.get("f_ma_filter") and c < ma_m: should_show = False
            
        if should_show:
            return {
                "sid": sid, "name": name, "price": round(c, 2), "vol": int(v_last/1000), 
                "rsi": round(rsi, 1), "hits": active_hits if active_hits else ["🔍觀察"],
                "df": df, "lines": (sh, ih, sl, il, x)
            }
    except: pass
    return None

# ==========================================
# 3. Sidebar 左側控制面板 (手動按鈕在此)
# ==========================================
full_db = load_db()
with st.sidebar:
    st.title("🛡️ 戰術控制中心")
    app_mode = st.radio("模式切換", ["⚡ 自動掃描", "🔍 手動模式", "❤️ 追蹤清單"])
    
    st.divider()
    st.subheader("📡 訊號監控開關")
    check_tri = st.checkbox("📐 三角收斂", True)
    check_box = st.checkbox("📦 箱型整理", True)
    check_vol = st.checkbox("🚀 今日爆量", True)
    check_rsi = st.checkbox("🌡️ RSI 預警", False)
    
    st.divider()
    manual_exec = False
    s_input = ""
    if app_mode == "🔍 手動模式":
        st.subheader("手動掃描控制")
        s_input = st.text_input("輸入代碼 (選填)", placeholder="例如: 2330, 2603")
        manual_exec = st.button("🔍 執行搜尋/掃描", type="primary", use_container_width=True)
        st.caption("※ 點擊後才掃描。不輸入代碼則掃全市場。")

    st.divider()
    st.subheader("❤️ 收藏管理員")
    if st.session_state.favorites:
        st.dataframe(pd.DataFrame([{"代碼": k, "名稱": v} for k, v in st.session_state.favorites.items()]), hide_index=True)
        if st.button("🗑️ 清空收藏", use_container_width=True):
            st.session_state.favorites = {}; st.rerun()

    with st.expander("🛠️ 進階參數"):
        config = {
            "p_ma_m": st.number_input("均線", value=20),
            "p_lookback": st.slider("形態回溯", 10, 30, 15),
            "f_ma_filter": st.checkbox("限 MA20 之上", True),
            "check_tri": check_tri, "check_box": check_box,
            "check_vol": check_vol, "check_rsi": check_rsi
        }
        min_v = st.number_input("張數門檻", value=500)
        scan_limit = st.slider("掃描上限", 50, 500, 100)

# ==========================================
# 4. 掃描與執行 (邏輯優化：點收藏不重跑)
# ==========================================
st.title(f"📍 當前：{app_mode}")

if app_mode == "⚡ 自動掃描":
    # 僅在記憶體為空時自動跑一次
    if not st.session_state.results_data or st.button("🔄 重新強制掃描"):
        codes = list(full_db.keys())[:scan_limit]
        with st.status("📡 自動掃描中...", expanded=False) as status:
            data = yf.download(codes, period="6mo", group_by='ticker', progress=False)
            temp_res = []
            for sid in codes:
                df = data[sid] if len(codes) > 1 else data
                if not df.empty and (df["Volume"].iloc[-1] / 1000 >= min_v):
                    res = run_analysis(sid, full_db.get(sid, "未知"), df, config)
                    if res: temp_res.append(res)
            st.session_state.results_data = temp_res
            status.update(label="✅ 完成", state="complete")

elif app_mode == "🔍 手動模式":
    if manual_exec:
        # 點擊按鈕才執行
        codes = [c.strip()+".TW" if "." not in c else c.strip().upper() for c in s_input.split(",")] if s_input else list(full_db.keys())[:scan_limit]
        with st.spinner("手動抓取資料中..."):
            data = yf.download(codes, period="6mo", group_by='ticker', progress=False)
            temp_res = []
            for sid in codes:
                df = data[sid] if len(codes) > 1 else data
                if not df.empty:
                    res = run_analysis(sid, full_db.get(sid, "未知"), df, config, is_manual=bool(s_input))
                    if res: temp_res.append(res)
            st.session_state.results_data = temp_res
    elif not st.session_state.results_data:
        st.info("模式已就緒。請輸入代碼或按左側「執行搜尋」開始。")

# ==========================================
# 5. 渲染顯示區 (表格與 K 線同步)
# ==========================================
final_display = st.session_state.results_data
if app_mode == "❤️ 追蹤清單":
    final_display = [r for r in st.session_state.results_data if r['sid'] in st.session_state.favorites]

if final_display:
    # 總覽表格
    table_list = []
    for r in final_display:
        table_list.append({
            "標記": "❤️" if r['sid'] in st.session_state.favorites else "🤍",
            "代碼": r['sid'], "名稱": r["name"], "現價": r["price"], "訊號": ", ".join(r["hits"])
        })
    st.table(pd.DataFrame(table_list))

    # 詳細 K 線與收藏按鈕
    for r in final_display:
        is_fav = r['sid'] in st.session_state.favorites
        with st.container():
            col_chart, col_ctrl = st.columns([8, 1])
            with col_chart:
                with st.expander(f"{'❤️' if is_fav else '🔍'} {r['sid']} {r['name']} | {', '.join(r['hits'])}", expanded=True):
                    df_t, (sh, ih, sl, il, x) = r["df"].iloc[-50:], r["lines"]
                    fig = go.Figure(data=[go.Candlestick(x=df_t.index, open=df_t['Open'], high=df_t['High'], low=df_t['Low'], close=df_t['Close'], name='K線')])
                    if ("📐" in "".join(r["hits"])) or ("📦" in "".join(r["hits"])):
                        fig.add_scatter(x=df_t.index[-config["p_lookback"]:], y=sh*x+ih, mode='lines', line=dict(color='red', dash='dash'), name='壓')
                        fig.add_scatter(x=df_t.index[-config["p_lookback"]:], y=sl*x+il, mode='lines', line=dict(color='green', dash='dash'), name='支')
                    fig.update_layout(height=400, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10))
                    st.plotly_chart(fig, use_container_width=True, key=f"c_{r['sid']}")
            with col_ctrl:
                st.write("### ") # 對齊
                if st.button("收藏" if not is_fav else "移除", key=f"fbtn_{r['sid']}", use_container_width=True):
                    if is_fav: del st.session_state.favorites[r['sid']]
                    else: st.session_state.favorites[r['sid']] = r['name']
                    st.rerun() # 僅刷新 UI，不觸發掃描
else:
    if app_mode == "❤️ 追蹤清單":
        st.warning("清單為空。請先去掃描並點擊收藏。")
