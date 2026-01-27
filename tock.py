import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import os, json

# ==========================================
# 1. 系統初始化與核心狀態鎖定
# ==========================================
st.set_page_config(page_title="台股 Pro 旗艦戰情室", layout="wide", initial_sidebar_state="expanded")

# 初始化 Session State
if 'favorites' not in st.session_state:
    st.session_state.favorites = {} 
if 'results_data' not in st.session_state:
    st.session_state.results_data = [] 
if 'current_mode' not in st.session_state:
    st.session_state.current_mode = "⚡ 自動掃描"

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
# 3. Sidebar 控制中心
# ==========================================
full_db = load_db()
with st.sidebar:
    st.title("🛡️ 戰術控制中心")
    
    # 模式切換邏輯：若模式改變，且新模式是手動，則清空資料
    new_mode = st.radio("模式切換", ["⚡ 自動掃描", "🔍 手動模式", "❤️ 追蹤清單"])
    if new_mode != st.session_state.current_mode:
        st.session_state.current_mode = new_mode
        if new_mode == "🔍 手動模式":
            st.session_state.results_data = [] # 按到手動立刻清空
        st.rerun()

    st.divider()
    check_tri = st.checkbox("📐 三角收斂", True)
    check_box = st.checkbox("📦 箱型整理", True)
    check_vol = st.checkbox("🚀 今日爆量", True)
    check_rsi = st.checkbox("🌡️ RSI 預警", False)
    
    st.divider()
    manual_exec = False
    s_input = ""
    if st.session_state.current_mode == "🔍 手動模式":
        s_input = st.text_input("輸入代碼 (選填)", placeholder="2330, 2603")
        manual_exec = st.button("🔍 執行手動搜尋", type="primary", use_container_width=True)

    st.divider()
    if st.session_state.favorites:
        st.subheader("❤️ 快速收藏夾")
        st.write(", ".join(st.session_state.favorites.keys()))
        if st.button("🗑️ 清空收藏", use_container_width=True):
            st.session_state.favorites = {}; st.rerun()

    with st.expander("🛠️ 進階參數"):
        config = {
            "p_ma_m": st.number_input("均線", value=20),
            "p_lookback": st.slider("形態回溯", 10, 30, 15),
            "f_ma_filter": st.checkbox("限 MA20 之上", True),
            "check_tri": check_tri, "check_box": check_box, "check_vol": check_vol, "check_rsi": check_rsi
        }
        min_v = st.number_input("張數門檻", value=500)
        scan_limit = st.slider("上限", 50, 500, 100)

# ==========================================
# 4. 掃描與執行 (邏輯優化)
# ==========================================
st.title(f"📍 {st.session_state.current_mode}")

if st.session_state.current_mode == "⚡ 自動掃描":
    if not st.session_state.results_data:
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

elif st.session_state.current_mode == "🔍 手動模式" and manual_exec:
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

# ==========================================
# 5. 渲染顯示區 (表格愛心按鈕鎖定)
# ==========================================
final_display = st.session_state.results_data
if st.session_state.current_mode == "❤️ 追蹤清單":
    final_display = [r for r in st.session_state.results_data if r['sid'] in st.session_state.favorites]

if final_display:
    # 這裡就是你要的：表格愛心要可以按
    st.subheader("📊 掃描清單 (點擊 ❤️ 收藏/移除)")
    
    # 為了讓表格愛心能按，我們用 container 做出類似表格的佈局
    head_cols = st.columns([1, 1.5, 1.5, 1.5, 3])
    head_cols[0].write("**標記**")
    head_cols[1].write("**代碼**")
    head_cols[2].write("**名稱**")
    head_cols[3].write("**現價**")
    head_cols[4].write("**符合訊號**")
    st.divider()

    for r in final_display:
        is_fav = r['sid'] in st.session_state.favorites
        row_cols = st.columns([1, 1.5, 1.5, 1.5, 3])
        
        # 表格裡的愛心按鈕 (針對這一檔)
        if row_cols[0].button("❤️" if is_fav else "🤍", key=f"table_fav_{r['sid']}"):
            if is_fav: del st.session_state.favorites[r['sid']]
            else: st.session_state.favorites[r['sid']] = r['name']
            st.rerun() # 僅重新渲染介面，不重掃資料
            
        row_cols[1].write(r['sid'])
        row_cols[2].write(r['name'])
        row_cols[3].write(str(r['price']))
        row_cols[4].write(", ".join(r['hits']))

    st.divider()
    
    # 詳細 K 線圖
    for r in final_display:
        is_fav = r['sid'] in st.session_state.favorites
        with st.expander(f"{'❤️' if is_fav else '🔍'} {r['sid']} {r['name']} | 詳細技術圖表", expanded=True):
            df_t, (sh, ih, sl, il, x) = r["df"].iloc[-50:], r["lines"]
            fig = go.Figure(data=[go.Candlestick(x=df_t.index, open=df_t['Open'], high=df_t['High'], low=df_t['Low'], close=df_t['Close'], name='K線')])
            
            if ("📐" in "".join(r["hits"])) or ("📦" in "".join(r["hits"])):
                fig.add_scatter(x=df_t.index[-config["p_lookback"]:], y=sh*x+ih, mode='lines', line=dict(color='red', dash='dash'), name='壓')
                fig.add_scatter(x=df_t.index[-config["p_lookback"]:], y=sl*x+il, mode='lines', line=dict(color='green', dash='dash'), name='支')
            
            fig.update_layout(height=400, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True, key=f"chart_{r['sid']}")
else:
    if st.session_state.current_mode == "🔍 手動模式":
        st.info("💡 手動模式已就緒，請輸入代碼或直接點擊「🔍 執行手動搜尋」。")
    elif st.session_state.current_mode == "❤️ 追蹤清單":
        st.warning("目前收藏夾空空如也。")
