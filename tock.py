import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import os, json

# ==========================================
# 1. 系統初始化與狀態管理
# ==========================================
st.set_page_config(page_title="台股 Pro 旗艦戰情室", layout="wide")

if 'favorites' not in st.session_state:
    st.session_state.favorites = set() 
if 'results_data' not in st.session_state:
    st.session_state.results_data = [] 
if 'last_config_key' not in st.session_state:
    st.session_state.last_config_key = ""

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
# 2. 專業分析引擎
# ==========================================
def run_analysis(sid, name, df, config, is_manual=False):
    if df is None or len(df) < 60: return None
    try:
        df = df.dropna()
        c = float(df["Close"].iloc[-1])
        v_last = df["Volume"].iloc[-1]
        v_avg = df["Volume"].iloc[-21:-1].mean()
        ma_m = df["Close"].rolling(config.get("p_ma_m", 20)).mean().iloc[-1]
        
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
        if config.get("check_tri") and (sh < -0.001 and sl > 0.001): active_hits.append("📐三角")
        if config.get("check_box") and (abs(sh) < 0.03 and abs(sl) < 0.03): active_hits.append("📦箱型")
        if config.get("check_vol") and (v_last > v_avg * 1.8): active_hits.append("🚀爆量")
        if config.get("check_rsi") and (rsi < 35 or rsi > 70): active_hits.append(f"🌡️RSI")

        if is_manual or (bool(active_hits) and (not config.get("f_ma_filter") or c >= ma_m)):
            # 生成 Yahoo 股市連結
            pure_id = sid.split('.')[0]
            yahoo_url = f"https://tw.stock.yahoo.com/quote/{pure_id}.TW"
            
            return {
                "收藏": sid in st.session_state.favorites,
                "代碼": sid, "名稱": name, "現價": round(c, 2), 
                "符合訊號": ", ".join(active_hits) if active_hits else "🔍觀察",
                "Yahoo": yahoo_url, # 新增連結欄位
                "df": df, "lines": (sh, ih, sl, il, x)
            }
    except: pass
    return None

# ==========================================
# 3. Sidebar 控制面板
# ==========================================
full_db = load_db()
with st.sidebar:
    st.title("🛡️ 戰術控制台")
    app_mode = st.radio("模式切換", ["⚡ 自動掃描", "🔍 手動模式", "❤️ 追蹤清單"])
    
    if "m_state" not in st.session_state: st.session_state.m_state = app_mode
    if app_mode != st.session_state.m_state:
        if app_mode == "🔍 手動模式": st.session_state.results_data = []
        st.session_state.m_state = app_mode
        st.rerun()

    if app_mode != "❤️ 追蹤清單":
        st.divider()
        st.subheader("📡 訊號監控")
        check_tri = st.checkbox("📐 三角收斂", True)
        check_box = st.checkbox("📦 箱型整理", True)
        check_vol = st.checkbox("🚀 今日爆量", True)
        check_rsi = st.checkbox("🌡️ RSI 預警", False)
        
        if app_mode == "🔍 手動模式":
            st.divider()
            s_input = st.text_input("輸入代碼", placeholder="2330, 2603")
            manual_exec = st.button("🔍 執行搜尋", type="primary", use_container_width=True)
        else: manual_exec = False

        with st.expander("🛠️ 進階參數", expanded=True):
            p_ma_m = st.number_input("均線", value=20)
            p_lookback = st.slider("形態回溯", 10, 30, 15)
            f_ma_filter = st.checkbox("限 MA20 之上", True)
            min_v = st.number_input("張數門檻", value=500)
            scan_limit = st.slider("上限", 50, 500, 100)
            config = locals()

        current_key = f"{app_mode}-{check_tri}-{check_box}-{check_vol}-{check_rsi}-{min_v}-{scan_limit}"
        trigger_scan = (app_mode == "⚡ 自動掃描" and current_key != st.session_state.last_config_key)
        if trigger_scan: st.session_state.last_config_key = current_key
    else: trigger_scan = False

# ==========================================
# 4. 資料處理區
# ==========================================
st.title(f"📍 {app_mode}")

if app_mode == "⚡ 自動掃描" and (trigger_scan or not st.session_state.results_data):
    codes = list(full_db.keys())[:scan_limit]
    with st.status("📡 掃描中...", expanded=False) as status:
        data = yf.download(codes, period="6mo", group_by='ticker', progress=False)
        temp_list = []
        for sid in codes:
            df = data[sid] if len(codes) > 1 else data
            if not df.empty and (df["Volume"].iloc[-1] / 1000 >= min_v):
                res = run_analysis(sid, full_db.get(sid, "未知"), df, config)
                if res: temp_list.append(res)
        st.session_state.results_data = temp_list
        status.update(label="✅ 完成", state="complete")

elif app_mode == "🔍 手動模式" and manual_exec:
    codes = [c.strip()+".TW" if "." not in c else c.strip().upper() for c in s_input.split(",")] if s_input else list(full_db.keys())[:scan_limit]
    with st.spinner("抓取中..."):
        data = yf.download(codes, period="6mo", group_by='ticker', progress=False)
        temp_list = []
        for sid in codes:
            df = data[sid] if len(codes) > 1 else data
            if not df.empty:
                res = run_analysis(sid, full_db.get(sid, "未知"), df, config, is_manual=bool(s_input))
                if res: temp_list.append(res)
        st.session_state.results_data = temp_list

# ==========================================
# 5. 渲染顯示區 (表格 + K線 + 連結)
# ==========================================
display_data = st.session_state.results_data
if app_mode == "❤️ 追蹤清單":
    display_data = [r for r in st.session_state.results_data if r['sid'] in st.session_state.favorites]

if display_data:
    # --- 表格區 ---
    st.subheader("📊 概覽表格 (可按愛心、可點 Yahoo 連結)")
    table_df = pd.DataFrame([{k: v for k, v in r.items() if k not in ['df', 'lines']} for r in display_data])
    
    edited_df = st.data_editor(
        table_df,
        column_config={
            "收藏": st.column_config.CheckboxColumn("❤️", default=False),
            "現價": st.column_config.NumberColumn("現價", format="$%.2f"),
            "Yahoo": st.column_config.LinkColumn("Yahoo 連結", display_text="點我開頁面"),
        },
        disabled=["代碼", "名稱", "現價", "符合訊號", "Yahoo"],
        hide_index=True, use_container_width=True, key=f"tbl_{app_mode}"
    )

    # 同步收藏狀態 (免重掃)
    new_favs = set(edited_df[edited_df["收藏"] == True]["代碼"])
    if new_favs != st.session_state.favorites:
        st.session_state.favorites = new_favs
        for r in st.session_state.results_data:
            r["收藏"] = r["sid"] in new_favs
        st.rerun()

    st.divider()

    # --- K 線圖區 ---
    for r in display_data:
        is_fav = r['sid'] in st.session_state.favorites
        with st.expander(f"{'❤️' if is_fav else '🔍'} {r['sid']} {r['name']} | K線分析", expanded=True):
            df_t, (sh, ih, sl, il, x) = r["df"].iloc[-50:], r["lines"]
            fig = go.Figure(data=[go.Candlestick(x=df_t.index, open=df_t['Open'], high=df_t['High'], low=df_t['Low'], close=df_t['Close'], name='K線')])
            if any(s in r["符合訊號"] for s in ["三角", "箱型"]):
                fig.add_scatter(x=df_t.index[-config["p_lookback"]:], y=sh*x+ih, mode='lines', line=dict(color='red', dash='dash'))
                fig.add_scatter(x=df_t.index[-config["p_lookback"]:], y=sl*x+il, mode='lines', line=dict(color='green', dash='dash'))
            fig.update_layout(height=450, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True, key=f"k_{r['sid']}")
else:
    st.info("尚無數據。")
