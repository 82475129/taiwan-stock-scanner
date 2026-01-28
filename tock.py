import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import os, json

# ==========================================
# 1. 系統初始化與狀態管理
# ================================
st.set_page_config(page_title="台股 Pro 旗艦戰情室", layout="wide")

if 'favorites' not in st.session_state:
    st.session_state.favorites = set() 
if 'results_data' not in st.session_state:
    st.session_state.results_data = [] 

# ================================
# 2. 股票資料庫
# ================================
@st.cache_data(ttl=3600)
def load_db():
    path = "taiwan_full_market.json"
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {"2330.TW": "台積電", "2603.TW": "長榮"}

full_db = load_db()

# ================================
# 3. 專業分析引擎 (結合多頭判斷與形態偵測)
# ================================
def run_analysis(sid, name, df, config, is_manual=False):
    if df is None or len(df) < 20: return None
    try:
        df = df.copy().dropna()
        if df.empty: return None
        
        # 基本數據 (來自第一個程式的邏輯)
        c = float(df['Close'].iloc[-1])
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        ma60 = df['Close'].rolling(60).mean().iloc[-1]
        trend = '🔴 多頭' if ma20 > ma60 else '🟢 空頭'
        
        # 形態與量能 (來自第二個程式的邏輯)
        lb = config.get("p_lookback", 15)
        x = np.arange(lb)
        h, l = df["High"].iloc[-lb:].values, df["Low"].iloc[-lb:].values
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        
        active_hits = []
        if (sh < -0.001 and sl > 0.001): active_hits.append("📐三角收斂")
        if (abs(sh) < 0.03 and abs(sl) < 0.03): active_hits.append("📦箱型整理")
        v_last = df["Volume"].iloc[-1]
        v_avg = df["Volume"].iloc[-21:-1].mean()
        if (v_last > v_avg * 1.8): active_hits.append("🚀今日爆量")
        
        # 判斷是否顯示
        should_show = is_manual
        if not is_manual:
            hit_match = any([
                config.get("check_tri") and "📐" in "".join(active_hits),
                config.get("check_box") and "📦" in "".join(active_hits),
                config.get("check_vol") and "🚀" in "".join(active_hits)
            ])
            should_show = hit_match
            if config.get("f_ma_filter") and c < ma20: should_show = False
            
        if should_show:
            pure_id = sid.split('.')[0]
            return {
                "收藏": sid in st.session_state.favorites,
                "sid": sid, "名稱": name, "現價": round(c, 2),
                "趨勢": trend, "MA20": round(ma20, 2),
                "符合訊號": ", ".join(active_hits) if active_hits else "🔍觀察中",
                "Yahoo": f"https://tw.stock.yahoo.com/quote/{pure_id}.TW",
                "df": df, "lines": (sh, ih, sl, il, x)
            }
    except: pass
    return None

# ================================
# 4. Sidebar 控制面板
# ================================
with st.sidebar:
    st.title("🛡️ 戰術控制台")
    app_mode = st.radio("模式切換", ["⚡ 自動掃描", "🔍 手動模式", "❤️ 追蹤清單"])
    
    # 切換模式清空暫存資料
    if "m_state" not in st.session_state: st.session_state.m_state = app_mode
    if app_mode != st.session_state.m_state:
        st.session_state.results_data = []
        st.session_state.m_state = app_mode
        st.rerun()

    # 只有非追蹤清單模式才顯示參數設定 (回應你的簡化要求)
    if app_mode != "❤️ 追蹤清單":
        st.divider()
        st.subheader("⚙️ 篩選設定")
        check_tri = st.checkbox("📐 三角收斂", True)
        check_box = st.checkbox("📦 箱型整理", True)
        check_vol = st.checkbox("🚀 今日爆量", True)
        
        with st.expander("🛠️ 進階參數", expanded=True):
            p_lookback = st.slider("形態回溯天數", 10, 30, 15)
            f_ma_filter = st.checkbox("限 MA20 之上 (自動)", True)
            min_v = st.number_input("成交量門檻 (張)", value=500)
            scan_limit = st.slider("掃描上限", 50, 500, 100)
            config = locals()
    else:
        config = {"p_lookback": 15}

# ================================
# 5. 主頁面執行邏輯
# ================================
st.title(f"📍 {app_mode}")

# --- 手動模式 ---
if app_mode == "🔍 手動模式":
    c1, c2 = st.columns([4, 1])
    with c1:
        s_input = st.text_input("輸入股票代碼 (如 2330, 2603)", key="m_in")
    with c2:
        st.write(" ")
        manual_exec = st.button("🔍 執行搜尋", type="primary", use_container_width=True)
    
    if manual_exec and s_input:
        raw = s_input.replace("，", ",").split(",")
        codes = [c.strip().upper() + ".TW" if "." not in c else c.strip().upper() for c in raw if c.strip()]
        temp = []
        for s in codes:
            # 強制單筆下載，解決 2330 無數據問題
            df = yf.download(s, period="1y", progress=False)
            if not df.empty:
                res = run_analysis(s, full_db.get(s, s.split('.')[0]), df, config, is_manual=True)
                if res: temp.append(res)
        st.session_state.results_data = temp

# --- 自動掃描 ---
elif app_mode == "⚡ 自動掃描" and not st.session_state.results_data:
    codes = list(full_db.keys())[:config.get('scan_limit', 50)]
    with st.status("📡 市場掃描中...") as status:
        data = yf.download(codes, period="1y", group_by='ticker', progress=False)
        temp = []
        for s in codes:
            df = data[s] if len(codes) > 1 else data
            if not df.empty and (df["Volume"].iloc[-1] / 1000 >= config.get('min_v', 0)):
                res = run_analysis(s, full_db.get(s, "未知"), df, config)
                if res: temp.append(res)
        st.session_state.results_data = temp
        status.update(label="✅ 掃描完成", state="complete")

# --- 追蹤清單 ---
elif app_mode == "❤️ 追蹤清單" and st.session_state.favorites:
    if st.button("🔄 重新整理清單"):
        temp = []
        for s in st.session_state.favorites:
            df = yf.download(s, period="1y", progress=False)
            if not df.empty:
                res = run_analysis(s, full_db.get(s, s), df, config, is_manual=True)
                if res: temp.append(res)
        st.session_state.results_data = temp

# ================================
# 6. 介面渲染 (數據、Yahoo、K線)
# ================================
display_data = st.session_state.results_data
if app_mode == "❤️ 追蹤清單":
    display_data = [r for r in st.session_state.results_data if r['sid'] in st.session_state.favorites]

if display_data:
    # 數據表 (整合 Yahoo 連結)
    t_df = pd.DataFrame([{
        "收藏": r["收藏"], "代碼": r["sid"], "名稱": r["名稱"], 
        "現價": r["現價"], "趨勢": r["趨勢"], "符合訊號": r["符合訊號"], "Yahoo": r["Yahoo"]
    } for r in display_data])

    edit = st.data_editor(
        t_df,
        column_config={
            "收藏": st.column_config.CheckboxColumn("❤️"),
            "Yahoo": st.column_config.LinkColumn("Yahoo", display_text="🔍"),
        },
        use_container_width=True, hide_index=True, key=f"table_{app_mode}"
    )

    # 同步收藏狀態
    new_favs = set(edit[edit["收藏"] == True]["代碼"])
    if new_favs != st.session_state.favorites:
        st.session_state.favorites = new_favs
        st.rerun()

    st.divider()

    # 圖表區 (結合第一個程式的 metric)
    for r in display_data:
        with st.expander(f"📈 {r['sid']} {r['名稱']} ({r['趨勢']})", expanded=True):
            m1, m2, m3 = st.columns(3)
            m1.metric("目前股價", f"{r['現價']} 元")
            m2.metric("MA20", r["MA20"])
            m3.metric("訊號", r["符合訊號"])
            
            df_t, (sh, ih, sl, il, x) = r["df"].iloc[-60:], r["lines"]
            fig = go.Figure(data=[go.Candlestick(
                x=df_t.index, open=df_t['Open'], high=df_t['High'], 
                low=df_t['Low'], close=df_t['Close'], name='K線'
            )])
            
            # 壓力支撐線
            fig.add_scatter(x=df_t.index[-len(x):], y=sh*x+ih, mode='lines', line=dict(color='red', dash='dash'), name='壓力')
            fig.add_scatter(x=df_t.index[-len(x):], y=sl*x+il, mode='lines', line=dict(color='green', dash='dash'), name='支撐')
            
            fig.update_layout(height=450, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True, key=f"k_{r['sid']}_{app_mode}")
else:
    st.info("尚無數據，請執行搜尋或掃描。")
