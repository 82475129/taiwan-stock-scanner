import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from scipy.stats import linregress
import os, json

# ==========================================
# 1. 初始化與狀態鎖定
# ==========================================
st.set_page_config(page_title="台股 Pro 戰情室", layout="wide")

if 'favorites' not in st.session_state:
    st.session_state.favorites = {} 
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

        if is_manual:
            should_show = True
        else:
            should_show = bool(active_hits)
            if config.get("f_ma_filter") and c < ma_m: should_show = False
            
        if should_show:
            return {
                "sid": sid, "name": name, "price": round(c, 2), "vol": int(v_last/1000), 
                "rsi": round(rsi, 1), "hits": active_hits if active_hits else ["🔍觀察"]
            }
    except: pass
    return None

# ==========================================
# 3. Sidebar 控制面板 (動態顯示)
# ==========================================
full_db = load_db()
with st.sidebar:
    st.title("🛡️ 戰術控制台")
    app_mode = st.radio("模式切換", ["⚡ 自動掃描", "🔍 手動模式", "❤️ 追蹤清單"])
    
    # 邏輯：換到手動立即清空
    if "m_state" not in st.session_state: st.session_state.m_state = app_mode
    if app_mode != st.session_state.m_state:
        if app_mode == "🔍 手動模式": st.session_state.results_data = []
        st.session_state.m_state = app_mode
        st.rerun()

    # --- 關鍵：追蹤清單不要顯示這些 ---
    if app_mode != "❤️ 追蹤清單":
        st.divider()
        st.subheader("📡 訊號監控開關")
        check_tri = st.checkbox("📐 三角收斂", True)
        check_box = st.checkbox("📦 箱型整理", True)
        check_vol = st.checkbox("🚀 今日爆量", True)
        check_rsi = st.checkbox("🌡️ RSI 預警", False)
        
        if app_mode == "🔍 手動模式":
            st.divider()
            s_input = st.text_input("輸入個股代碼", placeholder="例如: 2330, 2603")
            manual_exec = st.button("🔍 執行手動搜尋", type="primary", use_container_width=True)
        else:
            manual_exec = False

        with st.expander("🛠️ 進階參數", expanded=True):
            p_ma_m = st.number_input("均線", value=20)
            p_lookback = st.slider("形態回溯", 10, 30, 15)
            f_ma_filter = st.checkbox("限 MA20 之上", True)
            min_v = st.number_input("成交量門檻", value=500)
            scan_limit = st.slider("上限", 50, 500, 100)
            config = locals()

        # 自動模式勾選即掃描
        current_key = f"{app_mode}-{check_tri}-{check_box}-{check_vol}-{check_rsi}-{min_v}-{scan_limit}"
        trigger_scan = (app_mode == "⚡ 自動掃描" and current_key != st.session_state.last_config_key)
        if trigger_scan: st.session_state.last_config_key = current_key
    else:
        # 追蹤清單模式下，不需要配置邏輯
        trigger_scan = False

# ==========================================
# 4. 掃描執行
# ==========================================
st.title(f"📍 {app_mode}")

if app_mode == "⚡ 自動掃描" and (trigger_scan or not st.session_state.results_data):
    codes = list(full_db.keys())[:scan_limit]
    with st.status("📡 掃描中...", expanded=False) as status:
        data = yf.download(codes, period="6mo", group_by='ticker', progress=False)
        temp = []
        for sid in codes:
            df = data[sid] if len(codes) > 1 else data
            if not df.empty and (df["Volume"].iloc[-1] / 1000 >= min_v):
                res = run_analysis(sid, full_db.get(sid, "未知"), df, config)
                if res: temp.append(res)
        st.session_state.results_data = temp
        status.update(label="✅ 掃描完成", state="complete")

elif app_mode == "🔍 手動模式" and manual_exec:
    codes = [c.strip()+".TW" if "." not in c else c.strip().upper() for c in s_input.split(",")] if s_input else list(full_db.keys())[:scan_limit]
    with st.spinner("搜尋中..."):
        data = yf.download(codes, period="6mo", group_by='ticker', progress=False)
        temp = []
        for sid in codes:
            df = data[sid] if len(codes) > 1 else data
            if not df.empty:
                res = run_analysis(sid, full_db.get(sid, "未知"), df, config, is_manual=bool(s_input))
                if res: temp.append(res)
        st.session_state.results_data = temp

# ==========================================
# 5. 全表格顯示 (模擬表格排列)
# ==========================================
final_list = st.session_state.results_data
if app_mode == "❤️ 追蹤清單":
    # 追蹤清單只過濾收藏夾內的代碼
    final_list = [r for r in st.session_state.results_data if r['sid'] in st.session_state.favorites]

if final_list:
    # --- 模擬表格標題 ---
    h_cols = st.columns([1, 1.5, 1.5, 1.5, 3])
    h_cols[0].write("**收藏**")
    h_cols[1].write("**代碼**")
    h_cols[2].write("**名稱**")
    h_cols[3].write("**現價**")
    h_cols[4].write("**符合訊號**")
    st.divider()

    # --- 模擬表格內容 (每一列都有可按愛心) ---
    for r in final_list:
        is_fav = r['sid'] in st.session_state.favorites
        r_cols = st.columns([1, 1.5, 1.5, 1.5, 3])
        
        # 表格內的愛心：點擊切換狀態，不觸發掃描
        if r_cols[0].button("❤️" if is_fav else "🤍", key=f"f_{app_mode}_{r['sid']}"):
            if is_fav: del st.session_state.favorites[r['sid']]
            else: st.session_state.favorites[r['sid']] = r['name']
            st.rerun() 
            
        r_cols[1].write(r['sid'])
        r_cols[2].write(r['name'])
        r_cols[3].write(f"**{r['price']}**")
        r_cols[4].write(", ".join(r['hits']))
else:
    st.info("目前無符合條件之資料。" if app_mode != "❤️ 追蹤清單" else "收藏夾目前是空的。")
