import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import os, json, time

# ==========================================
# 1. 系統環境與狀態初始化 (持久化記憶體)
# ==========================================
st.set_page_config(page_title="台股 Pro 戰術終端", layout="wide", initial_sidebar_state="expanded")

# 初始化記憶體，確保操作按鈕時資料不消失
if 'favorites' not in st.session_state:
    st.session_state.favorites = {} 
if 'last_results' not in st.session_state:
    st.session_state.last_results = [] 
if 'scan_status' not in st.session_state:
    st.session_state.scan_status = ""

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
# 2. 核心技術分析引擎
# ==========================================
def run_analysis(sid, name, df, config, is_manual=False):
    if df is None or len(df) < 60: return None
    try:
        df = df.dropna()
        c = float(df["Close"].iloc[-1])
        v_last = df["Volume"].iloc[-1]
        v_avg = df["Volume"].iloc[-21:-1].mean()
        
        # 指標計算
        ma_m = df["Close"].rolling(config["p_ma_m"]).mean().iloc[-1]
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / loss).iloc[-1]))

        # 形態線性回歸
        lb = config["p_lookback"]
        x = np.arange(lb)
        h, l = df["High"].iloc[-lb:].values, df["Low"].iloc[-lb:].values
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        
        active_hits = []
        if (sh < -0.001 and sl > 0.001): active_hits.append("📐三角收斂")
        if (abs(sh) < 0.03 and abs(sl) < 0.03): active_hits.append("📦箱型整理")
        if (v_last > v_avg * 1.8): active_hits.append("🚀今日爆量")
        if rsi < 35: active_hits.append("💧超跌")
        if rsi > 70: active_hits.append("🔥過熱")

        bias = (c - ma_m) / ma_m * 100
        
        # 篩選邏輯
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
# 3. Sidebar 側邊欄 (最愛清單與專業參數)
# ==========================================
full_db = load_db()
with st.sidebar:
    st.title("🛡️ 戰術控制台")
    app_mode = st.radio("主功能切換", ["⚡ 全市場掃描", "🔍 手動搜尋", "❤️ 追蹤清單"])
    
    st.divider()
    st.subheader("❤️ 收藏管理員")
    if st.session_state.favorites:
        fav_data = [{"代碼": k, "名稱": v} for k, v in st.session_state.favorites.items()]
        st.dataframe(pd.DataFrame(fav_data), hide_index=True, use_container_width=True)
        if st.button("🗑️ 清空所有收藏", use_container_width=True):
            st.session_state.favorites = {}
            st.rerun()
    else:
        st.info("尚未收藏個股")

    st.divider()
    with st.expander("🛠️ 專業參數微調"):
        p_ma_m = st.number_input("中均線 MA", value=20)
        p_lookback = st.slider("形態回溯天數", 10, 30, 15)
        f_ma_filter = st.checkbox("僅看站上 MA20", True)
        f_bias_filter = st.checkbox("過濾高乖離 (>10%)", True)
        config = locals() # 封裝參數

    min_v = st.number_input("成交量門檻 (張)", value=500)
    scan_limit = st.slider("掃描上限 (筆數)", 50, 500, 100)

# ==========================================
# 4. 主畫面：功能執行區
# ==========================================
st.title(f"📍 模式：{app_mode}")

# --- 模式 A: 全市場 ---
if app_mode == "⚡ 全市場掃描":
    c1, c2 = st.columns([3, 1])
    with c1: st.info("點擊右方按鈕對台股進行形態大掃描。")
    with c2: btn_scan = st.button("🚀 開始全市場掃描", type="primary", use_container_width=True)
    
    if btn_scan:
        codes = list(full_db.keys())
        results = []
        with st.status("📡 全市場過濾中...", expanded=False) as status:
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
            status.update(label=f"✅ 掃描完成：找到 {len(results)} 檔", state="complete")

# --- 模式 B: 手動搜尋 ---
elif app_mode == "🔍 手動搜尋":
    c1, c2 = st.columns([3, 1])
    with c1: search_input = st.text_input("輸入代碼", placeholder="例如: 2330, 2454", label_visibility="collapsed")
    with c2: btn_search = st.button("🔍 執行搜尋", type="primary", use_container_width=True)
    
    if btn_search and search_input:
        codes = [c.strip()+".TW" if "." not in c else c.strip().upper() for c in search_input.split(",")]
        manual_results = []
        with st.spinner("獲取數據中..."):
            data = yf.download(codes, period="6mo", group_by='ticker', progress=False)
            for sid in codes:
                df = data[sid] if len(codes) > 1 else data
                if not df.empty:
                    res = run_analysis(sid, full_db.get(sid, "未知"), df, config, is_manual=True)
                    if res: manual_results.append(res)
            st.session_state.last_results = manual_results

# --- 模式 C: 追蹤清單 ---
elif app_mode == "❤️ 追蹤清單":
    # 這裡直接過濾記憶體，不需要搜尋按鈕
    display_favs = [r for r in st.session_state.last_results if r['sid'] in st.session_state.favorites]
    if not display_favs:
        st.warning("💡 追蹤清單目前在記憶體中無資料。請先從全市場模式收藏符合條件的股票。")
    # 暫時覆蓋顯示清單但不影響原始掃描紀錄
    current_display = display_favs
else:
    current_display = st.session_state.last_results

# ==========================================
# 5. 數據呈現與收藏互動
# ==========================================
# 統一使用 current_display 進行渲染，如果是全市場/手動則用 last_results
if app_mode != "❤️ 追蹤清單":
    current_display = st.session_state.last_results

if current_display:
    # 1. 總覽表格
    table_data = []
    for r in current_display:
        table_data.append({
            "收藏": "❤️" if r['sid'] in st.session_state.favorites else "🤍",
            "代碼": f"https://tw.stock.yahoo.com/quote/{r['sid']}",
            "名稱": r["name"], "現價": r["price"], "RSI": r["rsi"], "乖離": f"{r['bias']}%",
            "符合訊號": ", ".join(r["hits"]) if r["hits"] else "觀察中"
        })
    st.dataframe(pd.DataFrame(table_data), column_config={"代碼": st.column_config.LinkColumn("連結", display_text=r"quote/(.*)$")}, hide_index=True, use_container_width=True)

    # 2. 詳細 K 線與收藏切換
    for r in current_display:
        col_main, col_fav = st.columns([8, 1])
        with col_main:
            is_fav = r['sid'] in st.session_state.favorites
            with st.expander(f"{'❤️' if is_fav else '🔍'} {r['sid']} {r['name']} | RSI:{r['rsi']} | {', '.join(r['hits'])}", expanded=(app_mode != "⚡ 全市場掃描")):
                df_t, (sh, ih, sl, il, x) = r["df"].iloc[-50:], r["lines"]
                fig = go.Figure(data=[go.Candlestick(x=df_t.index, open=df_t['Open'], high=df_t['High'], low=df_t['Low'], close=df_t['Close'], name='K線')])
                
                # 形態趨勢線
                if any(icon in "".join(r["hits"]) for icon in ["📐", "📦"]):
                    fig.add_scatter(x=df_t.index[-config["p_lookback"]:], y=sh*x+ih, mode='lines', line=dict(color='red', dash='dash'), name='壓')
                    fig.add_scatter(x=df_t.index[-config["p_lookback"]:], y=sl*x+il, mode='lines', line=dict(color='green', dash='dash'), name='支')
                
                fig.update_layout(height=450, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig, use_container_width=True)
        with col_fav:
            if st.button("收藏" if not is_fav else "移除", key=f"f_{r['sid']}", use_container_width=True):
                if is_fav: del st.session_state.favorites[r['sid']]
                else: st.session_state.favorites[r['sid']] = r['name']
                st.rerun()
