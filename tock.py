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
# 2. 專業技術分析引擎 (修正版)
# ==========================================
def run_analysis(sid, name, df, config, is_manual=False):
    if df is None or len(df) < 5: return None # 降低門檻，確保手動能出圖
    try:
        # 數據清理
        df = df.copy().dropna()
        if df.empty: return None

        # 取得最後價格與成交量
        c = float(df["Close"].iloc[-1])
        v_last = df["Volume"].iloc[-1]
        
        # 形態回溯計算
        lb = min(len(df), config.get("p_lookback", 15))
        x = np.arange(lb)
        h, l = df["High"].iloc[-lb:].values, df["Low"].iloc[-lb:].values
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        
        # 訊號偵測
        active_hits = []
        if (sh < -0.001 and sl > 0.001): active_hits.append("📐三角收斂")
        if (abs(sh) < 0.03 and abs(sl) < 0.03): active_hits.append("📦箱型整理")
        v_avg = df["Volume"].iloc[-21:-1].mean() if len(df) > 21 else 1
        if (v_last > v_avg * 1.8): active_hits.append("🚀今日爆量")
        
        # 邏輯判斷
        if is_manual:
            should_show = True # 手動模式強制顯示
        else:
            hit_match = any([
                config.get("check_tri") and "📐" in "".join(active_hits),
                config.get("check_box") and "📦" in "".join(active_hits),
                config.get("check_vol") and "🚀" in "".join(active_hits)
            ])
            should_show = hit_match
            ma_m = df["Close"].rolling(config.get("p_ma_m", 20)).mean().iloc[-1] if len(df) >= 20 else 0
            if config.get("f_ma_filter") and c < ma_m: should_show = False
            
        if should_show:
            return {
                "收藏": sid in st.session_state.favorites,
                "sid": sid, "名稱": name, "現價": round(c, 2), 
                "符合訊號": ", ".join(active_hits) if active_hits else "🔍觀察中",
                "Yahoo": f"https://tw.stock.yahoo.com/quote/{sid.split('.')[0]}.TW",
                "df": df, "lines": (sh, ih, sl, il, x)
            }
    except: pass
    return None

# ==========================================
# 3. Sidebar 控制面板 (保持原有自動觸發邏輯)
# ==========================================
full_db = load_db()
with st.sidebar:
    st.title("🛡️ 戰術控制台")
    app_mode = st.radio("模式切換", ["⚡ 自動掃描", "🔍 手動模式", "❤️ 追蹤清單"])
    
    if "m_state" not in st.session_state: st.session_state.m_state = app_mode
    if app_mode != st.session_state.m_state:
        st.session_state.results_data = [] # 切換時清空舊資料
        st.session_state.m_state = app_mode
        st.rerun()

    st.divider()
    st.subheader("⚙️ 參數設定")
    check_tri = st.checkbox("📐 三角收斂", True)
    check_box = st.checkbox("📦 箱型整理", True)
    check_vol = st.checkbox("🚀 今日爆量", True)

    with st.expander("🛠️ 進階設定", expanded=True):
        p_ma_m = st.number_input("均線 (MA)", value=20)
        p_lookback = st.slider("形態回溯天數", 10, 30, 15)
        f_ma_filter = st.checkbox("限 MA20 之上 (自動)", True)
        min_v = st.number_input("成交量門檻 (張)", value=500)
        scan_limit = st.slider("掃描上限", 50, 500, 100)
        config = locals()

    # 自動模式配置監控
    current_key = f"{app_mode}-{check_tri}-{check_box}-{check_vol}-{min_v}-{scan_limit}"
    trigger_scan = (app_mode == "⚡ 自動掃描" and current_key != st.session_state.last_config_key)
    if trigger_scan: st.session_state.last_config_key = current_key

# ==========================================
# 4. 主頁面執行邏輯
# ==========================================
st.title(f"📍 {app_mode}")

if app_mode == "🔍 手動模式":
    c1, c2 = st.columns([4, 1])
    with c1:
        s_input = st.text_input("輸入代碼 (例如: 2330, 2603)", key="manual_in")
    with c2:
        st.write(" ")
        manual_exec = st.button("🔍 執行搜尋", type="primary", use_container_width=True)
    
    if manual_exec and s_input:
        raw_list = s_input.replace("，", ",").split(",")
        final_codes = [c.strip().upper() + ".TW" if "." not in c else c.strip().upper() for c in raw_list if c.strip()]
        
        with st.spinner("強制抓取數據中..."):
            temp_res = []
            for sid in final_codes:
                df = yf.download(sid, period="6mo", progress=False) # 單筆下載避免結構問題
                if not df.empty:
                    name = full_db.get(sid, sid.split('.')[0])
                    res = run_analysis(sid, name, df, config, is_manual=True)
                    if res: temp_res.append(res)
            st.session_state.results_data = temp_res

elif app_mode == "⚡ 自動掃描" and (trigger_scan or not st.session_state.results_data):
    codes = list(full_db.keys())[:scan_limit]
    with st.status("📡 市場掃描中...", expanded=False) as status:
        data = yf.download(codes, period="6mo", group_by='ticker', progress=False)
        temp_res = []
        for sid in codes:
            df = data[sid] if len(codes) > 1 else data
            if not df.empty and (df["Volume"].iloc[-1] / 1000 >= min_v):
                res = run_analysis(sid, full_db.get(sid, "未知"), df, config)
                if res: temp_res.append(res)
        st.session_state.results_data = temp_res
        status.update(label="✅ 掃描完成", state="complete")

# ==========================================
# 5. 渲染顯示區
# ==========================================
display_data = st.session_state.results_data
if app_mode == "❤️ 追蹤清單":
    display_data = [r for r in st.session_state.results_data if r['sid'] in st.session_state.favorites]

if display_data:
    st.subheader("📊 數據總覽")
    table_df = pd.DataFrame([{
        "收藏": r["收藏"], "代碼": r["sid"], "名稱": r["名稱"], "現價": r["現價"], "符合訊號": r["符合訊號"]
    } for r in display_data])
    
    st.data_editor(table_df, use_container_width=True, hide_index=True, disabled=True)

    st.divider()
    for r in display_data:
        with st.expander(f"📈 {r['sid']} {r['名稱']} | {r['符合訊號']}", expanded=True):
            df_t, (sh, ih, sl, il, x) = r["df"].iloc[-60:], r["lines"]
            fig = go.Figure(data=[go.Candlestick(x=df_t.index, open=df_t['Open'], high=df_t['High'], low=df_t['Low'], close=df_t['Close'])])
            
            # 畫壓力支撐線
            fig.add_scatter(x=df_t.index[-len(x):], y=sh*x+ih, mode='lines', line=dict(color='red', dash='dash'), name='壓力')
            fig.add_scatter(x=df_t.index[-len(x):], y=sl*x+il, mode='lines', line=dict(color='green', dash='dash'), name='支撐')
            
            fig.update_layout(height=450, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True, key=f"k_{r['sid']}")

            # 收藏按鈕
            if st.button(f"{'💔 移除收藏' if r['sid'] in st.session_state.favorites else '❤️ 加入收藏'} {r['sid']}", key=f"fav_{r['sid']}"):
                if r['sid'] in st.session_state.favorites:
                    st.session_state.favorites.remove(r['sid'])
                else:
                    st.session_state.favorites.add(r['sid'])
                st.rerun()
else:
    st.info("尚無符合條件之數據。如果是手動模式，請輸入代碼後點擊「執行搜尋」。")
