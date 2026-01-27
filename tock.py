import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import os, json, time

# ==========================================
# 1. 系統初始化與持久化記憶體
# ==========================================
st.set_page_config(page_title="台股 Pro 旗艦戰情室", layout="wide", initial_sidebar_state="expanded")

# 確保在互動過程中資料不會消失
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
# 2. 專業技術分析引擎
# ==========================================
def run_analysis(sid, name, df, config, is_specific_search=False):
    if df is None or len(df) < 60: return None
    try:
        df = df.dropna()
        c = float(df["Close"].iloc[-1])
        v_last = df["Volume"].iloc[-1]
        v_avg = df["Volume"].iloc[-21:-1].mean()
        
        # 均線與 RSI 計算
        ma_m = df["Close"].rolling(config["p_ma_m"]).mean().iloc[-1]
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / loss).iloc[-1]))

        # 形態辨識 (線性回歸支撐與壓力)
        lb = config["p_lookback"]
        x = np.arange(lb)
        h, l = df["High"].iloc[-lb:].values, df["Low"].iloc[-lb:].values
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        
        active_hits = []
        # 四大訊號勾選邏輯
        if config["check_tri"] and (sh < -0.001 and sl > 0.001): active_hits.append("📐三角收斂")
        if config["check_box"] and (abs(sh) < 0.03 and abs(sl) < 0.03): active_hits.append("📦箱型整理")
        if config["check_vol"] and (v_last > v_avg * 1.8): active_hits.append("🚀今日爆量")
        if config["check_rsi"]:
            if rsi < 35: active_hits.append("💧超跌反彈")
            if rsi > 70: active_hits.append("🔥高點警戒")

        bias = (c - ma_m) / ma_m * 100
        
        # 篩選門檻
        if is_specific_search:
            should_show = True
        else:
            should_show = bool(active_hits)
            if config["f_ma_filter"] and c < ma_m: should_show = False
            if config["f_bias_filter"] and bias > 10: should_show = False
            
        if should_show:
            return {
                "sid": sid, "name": name, "price": round(c, 2), "vol": int(v_last/1000), 
                "bias": round(bias, 1), "rsi": round(rsi, 1), 
                "hits": active_hits if active_hits else ["🔍技術觀察"],
                "df": df, "lines": (sh, ih, sl, il, x)
            }
    except: pass
    return None

# ==========================================
# 3. Sidebar：左側控制面板 (人性化設計)
# ==========================================
full_db = load_db()
with st.sidebar:
    st.title("🛡️ 戰術控制中心")
    app_mode = st.radio("模式切換", ["⚡ 全市場自動掃描", "🔍 手動觸發模式", "❤️ 追蹤清單"])
    
    st.divider()
    st.subheader("📡 訊號開關 (全域)")
    check_tri = st.checkbox("📐 三角收斂", True)
    check_box = st.checkbox("📦 箱型整理", True)
    check_vol = st.checkbox("🚀 今日爆量", True)
    check_rsi = st.checkbox("🌡️ RSI 預警", False)
    
    st.divider()
    # 手動模式專屬區
    manual_btn = False
    s_input = ""
    if app_mode == "🔍 手動觸發模式":
        st.subheader("手動搜尋控制")
        s_input = st.text_input("輸入特定代碼 (選填)", placeholder="2330, 2603")
        manual_btn = st.button("🔍 執行手動掃描", type="primary", use_container_width=True)
        st.caption("※ 不輸入代碼則依訊號掃描全市場")

    st.divider()
    # 收藏清單
    st.subheader("❤️ 我的最愛")
    if st.session_state.favorites:
        st.dataframe(pd.DataFrame([{"代碼": k, "名稱": v} for k, v in st.session_state.favorites.items()]), hide_index=True)
        if st.button("🗑️ 清空收藏", use_container_width=True):
            st.session_state.favorites = {}; st.rerun()

    with st.expander("🛠️ 進階指標微調"):
        p_ma_m = st.number_input("均線 MA", value=20)
        p_lookback = st.slider("形態回溯天數", 10, 30, 15)
        f_ma_filter = st.checkbox("限 MA20 之上", True)
        f_bias_filter = st.checkbox("過濾高乖離", True)
        min_v = st.number_input("成交量張數門檻", value=500)
        scan_limit = st.slider("掃描筆數上限", 50, 500, 100)
        config = locals() # 自動獲取所有局部變數

# ==========================================
# 4. 掃描執行邏輯
# ==========================================
st.title(f"📍 模式：{app_mode}")

# --- 邏輯 A：自動掃描 ---
if app_mode == "⚡ 全市場自動掃描":
    codes = list(full_db.keys())[:scan_limit]
    with st.status("📡 自動監控中...", expanded=False) as status:
        data = yf.download(codes, period="6mo", group_by='ticker', progress=False)
        results = []
        for sid in codes:
            df = data[sid] if len(codes) > 1 else data
            if not df.empty and (df["Volume"].iloc[-1] / 1000 >= min_v):
                res = run_analysis(sid, full_db.get(sid, "未知"), df, config)
                if res: results.append(res)
        st.session_state.last_results = results
        status.update(label=f"✅ 自動扫瞄完成 (符合 {len(results)} 檔)", state="complete")

# --- 邏輯 B：手動觸發 (關鍵修復：不輸入代碼也能掃) ---
elif app_mode == "🔍 手動觸發模式" and manual_btn:
    results = []
    if s_input:
        codes = [c.strip()+".TW" if "." not in c else c.strip().upper() for c in s_input.split(",")]
        is_specific = True
    else:
        codes = list(full_db.keys())[:scan_limit]
        is_specific = False
        
    with st.status("📡 手動任務執行中...", expanded=False) as status:
        data = yf.download(codes, period="6mo", group_by='ticker', progress=False)
        for sid in codes:
            df = data[sid] if len(codes) > 1 else data
            if not df.empty:
                # 全市場模式下需過濾成交量
                if not is_specific and (df["Volume"].iloc[-1] / 1000 < min_v): continue
                res = run_analysis(sid, full_db.get(sid, "未知"), df, config, is_manual=is_specific)
                if res: results.append(res)
        st.session_state.last_results = results
        status.update(label="✅ 手動掃描完畢", state="complete")

# --- 邏輯 C：追蹤清單 ---
elif app_mode == "❤️ 追蹤清單":
    st.session_state.last_results = [r for r in st.session_state.last_results if r['sid'] in st.session_state.favorites]

# ==========================================
# 5. 結果呈現與圖表
# ==========================================
display_list = st.session_state.last_results

if display_list:
    # 總覽表格
    st.dataframe(pd.DataFrame([{
        "收藏": "❤️" if r['sid'] in st.session_state.favorites else "🤍",
        "代碼": r['sid'], "名稱": r["name"], "現價": r["price"], 
        "RSI": r["rsi"], "符合訊號": ", ".join(r["hits"])
    } for r in display_list]), hide_index=True, use_container_width=True)

    # 詳細 K 線資料
    for r in display_list:
        c1, c2 = st.columns([8, 1])
        with c1:
            is_fav = r['sid'] in st.session_state.favorites
            with st.expander(f"{'❤️' if is_fav else '🔍'} {r['sid']} {r['name']} | {', '.join(r['hits'])}", expanded=True):
                df_t, (sh, ih, sl, il, x) = r["df"].iloc[-50:], r["lines"]
                fig = go.Figure(data=[go.Candlestick(x=df_t.index, open=df_t['Open'], high=df_t['High'], low=df_t['Low'], close=df_t['Close'], name='K線')])
                
                # 自動繪製形態趨勢線
                if ("📐" in "".join(r["hits"])) or ("📦" in "".join(r["hits"])):
                    fig.add_scatter(x=df_t.index[-config["p_lookback"]:], y=sh*x+ih, mode='lines', line=dict(color='red', dash='dash'), name='壓力線')
                    fig.add_scatter(x=df_t.index[-config["p_lookback"]:], y=sl*x+il, mode='lines', line=dict(color='green', dash='dash'), name='支撐線')
                
                fig.update_layout(height=450, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig, use_container_width=True)
        with c2:
            # 點擊按鈕刷新狀態，資料不重抓
            if st.button("❤️" if not is_fav else "🗑️", key=f"btn_{r['sid']}", use_container_width=True):
                if is_fav: del st.session_state.favorites[r['sid']]
                else: st.session_state.favorites[r['sid']] = r['name']
                st.rerun()
else:
    st.warning("⚠️ 查無符合條件之個股，請調整左側過濾參數或點擊執行掃描。")
