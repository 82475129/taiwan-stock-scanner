import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from scipy.stats import linregress
import os, json

# ==========================================
# 1. 系統初始化與狀態管理
# ==========================================
st.set_page_config(page_title="台股 Pro 戰情表格", layout="wide")

if 'favorites' not in st.session_state:
    st.session_state.favorites = set()  # 使用 set 存代碼更快速
if 'results_df' not in st.session_state:
    st.session_state.results_df = pd.DataFrame() 
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
# 2. 專業分析引擎 (回傳 dict 用於組建 DataFrame)
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
            return {
                "收藏": sid in st.session_state.favorites,
                "代碼": sid, "名稱": name, "現價": round(c, 2), 
                "符合訊號": ", ".join(active_hits) if active_hits else "🔍觀察"
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
    
    # 邏輯：換到手動立即清空
    if "m_state" not in st.session_state: st.session_state.m_state = app_mode
    if app_mode != st.session_state.m_state:
        if app_mode == "🔍 手動模式": st.session_state.results_df = pd.DataFrame()
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

        # 自動模式勾選即掃描邏輯
        current_key = f"{app_mode}-{check_tri}-{check_box}-{check_vol}-{check_rsi}-{min_v}-{scan_limit}"
        trigger_scan = (app_mode == "⚡ 自動掃描" and current_key != st.session_state.last_config_key)
        if trigger_scan: st.session_state.last_config_key = current_key
    else:
        trigger_scan = False

# ==========================================
# 4. 掃描與資料組建
# ==========================================
st.title(f"📍 {app_mode}")

if app_mode == "⚡ 自動掃描" and (trigger_scan or st.session_state.results_df.empty):
    codes = list(full_db.keys())[:scan_limit]
    with st.status("📡 掃描中...", expanded=False) as status:
        data = yf.download(codes, period="6mo", group_by='ticker', progress=False)
        rows = []
        for sid in codes:
            df = data[sid] if len(codes) > 1 else data
            if not df.empty and (df["Volume"].iloc[-1] / 1000 >= min_v):
                res = run_analysis(sid, full_db.get(sid, "未知"), df, config)
                if res: rows.append(res)
        st.session_state.results_df = pd.DataFrame(rows)
        status.update(label="✅ 完成", state="complete")

elif app_mode == "🔍 手動模式" and manual_exec:
    codes = [c.strip()+".TW" if "." not in c else c.strip().upper() for c in s_input.split(",")] if s_input else list(full_db.keys())[:scan_limit]
    with st.spinner("搜尋中..."):
        data = yf.download(codes, period="6mo", group_by='ticker', progress=False)
        rows = []
        for sid in codes:
            df = data[sid] if len(codes) > 1 else data
            if not df.empty:
                res = run_analysis(sid, full_db.get(sid, "未知"), df, config, is_manual=bool(s_input))
                if res: rows.append(res)
        st.session_state.results_df = pd.DataFrame(rows)

# ==========================================
# 5. 表格顯示區 (使用 Data Editor 實現愛心連動)
# ==========================================
df_to_show = st.session_state.results_df

if app_mode == "❤️ 追蹤清單":
    if not st.session_state.results_df.empty:
        df_to_show = st.session_state.results_df[st.session_state.results_df['代碼'].isin(st.session_state.favorites)]
    else:
        st.info("請先從掃描結果中勾選收藏。")
        st.stop()

if not df_to_show.empty:
    st.subheader("📊 戰情即時數據 (勾選第一欄即可收藏)")
    
    # 使用 data_editor 讓表格可以互動
    edited_df = st.data_editor(
        df_to_show,
        column_config={
            "收藏": st.column_config.CheckboxColumn("收藏 ❤️", default=False),
            "現價": st.column_config.NumberColumn("現價", format="$%.2f"),
            "代碼": st.column_config.TextColumn("代碼"),
        },
        disabled=["代碼", "名稱", "現價", "符合訊號"], # 只有收藏欄位能點
        hide_index=True,
        use_container_width=True,
        key="main_table"
    )

    # 處理表格勾選連動：當 edited_df 改變時，更新 session_state.favorites
    new_favs = set(edited_df[edited_df["收藏"] == True]["代碼"])
    if new_favs != st.session_state.favorites:
        st.session_state.favorites = new_favs
        # 更新原始數據中的收藏狀態，確保切換模式時狀態還在
        st.session_state.results_df["收藏"] = st.session_state.results_df["代碼"].apply(lambda x: x in new_favs)
        st.rerun()
else:
    st.warning("⚠️ 目前無資料，請調整勾選框或執行手動搜尋。")
