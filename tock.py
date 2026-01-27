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
st.set_page_config(page_title="台股 Pro 戰術終端", layout="wide")

# 初始化 Session State (記憶體)
if 'favorites' not in st.session_state:
    st.session_state.favorites = {} # 格式: {"2330.TW": "台積電"}
if 'last_results' not in st.session_state:
    st.session_state.last_results = [] # 儲存最近一次掃描的所有資料物件

@st.cache_data(ttl=3600)
def load_db():
    f = "taiwan_full_market.json"
    if os.path.exists(f):
        with open(f, "r", encoding="utf-8") as file:
            return json.load(file)
    return {"2330.TW": "台積電"}

# ==========================================
# 2. 技術分析引擎
# ==========================================
def run_analysis(sid, name, df, config, is_monitor_mode=False):
    if df is None or len(df) < 80: return None
    try:
        df = df.dropna()
        c = float(df["Close"].iloc[-1])
        v_last = df["Volume"].iloc[-1]
        v_avg = df["Volume"].iloc[-21:-1].mean()
        
        # 均線與 RSI
        ma_m = df["Close"].rolling(config["p_ma_m"]).mean().iloc[-1]
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / loss).iloc[-1]))

        # 形態回溯
        lb = config["p_lookback"]
        x = np.arange(lb)
        h, l = df["High"].iloc[-lb:].values, df["Low"].iloc[-lb:].values
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        
        active_hits = []
        if config["f_tri"] and (sh < -0.001 and sl > 0.001): active_hits.append("📐三角收斂")
        if config["f_box"] and (abs(sh) < 0.03 and abs(sl) < 0.03): active_hits.append("📦箱型整理")
        if (v_last > v_avg * 1.5): active_hits.append("🚀今日爆量")

        bias = (c - ma_m) / ma_m * 100
        
        # 篩選邏輯
        should_show = True if is_monitor_mode else bool(active_hits)
        if not is_monitor_mode:
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
# 3. Sidebar 控制面板與最愛清單
# ==========================================
full_db = load_db()
with st.sidebar:
    st.title("🛡️ 戰術設定")
    app_mode = st.selectbox("🎯 運作模式", ["⚡ 全市場掃描", "🔍 手動搜尋", "❤️ 追蹤清單"])
    
    # 收藏清單管理區
    st.divider()
    st.subheader("❤️ 收藏管理員")
    if st.session_state.favorites:
        # 顯示簡易列表
        fav_df = pd.DataFrame([{"代碼": k, "名稱": v} for k, v in st.session_state.favorites.items()])
        st.dataframe(fav_df, hide_index=True, use_container_width=True)
        if st.button("🗑️ 一鍵清空收藏"):
            st.session_state.favorites = {}
            st.rerun()
    else:
        st.caption("尚無收藏。在掃描結果中點擊收藏按鈕即可加入。")
    
    st.divider()
    # 掃描參數設定
    with st.expander("⚙️ 篩選與形態參數"):
        p_ma_m = st.number_input("中均線 (MA)", value=20)
        p_lookback = st.slider("形態回溯天數", 10, 30, 15)
        f_tri = st.checkbox("📐 三角收斂", True)
        f_box = st.checkbox("📦 箱型整理", True)
        f_ma_filter = st.checkbox("📈 必須站上中均線", True)
        f_bias_filter = st.checkbox("🚫 排除過度乖離", True)
        config = locals()

    min_v = st.number_input("成交量門檻 (張)", value=500)
    scan_limit = st.slider("掃描上限", 50, 500, 100)
    
    trigger_scan = st.button("🚀 開始全市場掃描", type="primary", use_container_width=True) if app_mode == "⚡ 全市場掃描" else False

# ==========================================
# 4. 掃描核心與記憶體處理
# ==========================================
if trigger_scan:
    codes_to_scan = list(full_db.keys())
    results = []
    with st.status("📡 掃描中...", expanded=False) as status:
        batch_size = 40
        for i in range(0, len(codes_to_scan[:scan_limit]), batch_size):
            batch = codes_to_scan[i:i+batch_size]
            raw_data = yf.download(batch, period="6mo", group_by='ticker', progress=False)
            for sid in batch:
                df = raw_data[sid] if len(batch) > 1 else raw_data
                if not df.empty and (df["Volume"].iloc[-1] / 1000 >= min_v):
                    res = run_analysis(sid, full_db.get(sid, "未知"), df, config)
                    if res: results.append(res)
        st.session_state.last_results = results # 將詳細資料存入 Session
        status.update(label=f"✅ 完成：找到 {len(results)} 檔", state="complete")

if app_mode == "🔍 手動搜尋":
    search_input = st.text_input("輸入代碼 (例如: 2330, 2454)")
    if search_input:
        codes = [c.strip()+".TW" if "." not in c else c.strip().upper() for c in search_input.split(",")]
        manual_results = []
        raw_data = yf.download(codes, period="6mo", group_by='ticker', progress=False)
        for sid in codes:
            df = raw_data[sid] if len(codes) > 1 else raw_data
            if not df.empty:
                res = run_analysis(sid, full_db.get(sid, "未知"), df, config, True)
                if res: manual_results.append(res)
        st.session_state.last_results = manual_results # 覆蓋記憶體供顯示

# ==========================================
# 5. 結果呈現與互動
# ==========================================
# 過濾出要顯示的清單
if app_mode == "❤️ 追蹤清單":
    display_list = [r for r in st.session_state.last_results if r['sid'] in st.session_state.favorites]
else:
    display_list = st.session_state.last_results

if display_list:
    st.subheader(f"📊 篩選結果 ({len(display_list)} 檔)")
    
    # 顯示主表格
    table_data = []
    for r in display_list:
        table_data.append({
            "狀態": "❤️" if r['sid'] in st.session_state.favorites else "🤍",
            "代碼": f"https://tw.stock.yahoo.com/quote/{r['sid']}",
            "名稱": r["name"], "現價": r["price"], "RSI": r["rsi"],
            "訊號": " + ".join(r["hits"]) if r["hits"] else "觀察中"
        })
    st.dataframe(pd.DataFrame(table_data), column_config={"代碼": st.column_config.LinkColumn("連結", display_text=r"quote/(.*)$")}, hide_index=True, use_container_width=True)

    # 顯示詳細 K 線
    for r in display_list:
        c_main, c_fav = st.columns([7, 1])
        with c_main:
            is_fav = r['sid'] in st.session_state.favorites
            with st.expander(f"{'❤️' if is_fav else '🔍'} {r['sid']} {r['name']} | RSI:{r['rsi']} | {', '.join(r['hits'])}", expanded=(app_mode != "⚡ 全市場掃描")):
                df_t = r["df"].iloc[-50:]
                fig = go.Figure(data=[go.Candlestick(x=df_t.index, open=df_t['Open'], high=df_t['High'], low=df_t['Low'], close=df_t['Close'], name='K線')])
                fig.update_layout(height=400, xaxis_rangeslider_visible=False, margin=dict(l=5, r=5, t=5, b=5))
                st.plotly_chart(fig, use_container_width=True)
        with c_fav:
            if st.button("收藏" if r['sid'] not in st.session_state.favorites else "移除", key=f"fbtn_{r['sid']}"):
                if r['sid'] in st.session_state.favorites:
                    del st.session_state.favorites[r['sid']]
                else:
                    st.session_state.favorites[r['sid']] = r['name']
                st.rerun() # 重新整理 UI 狀態，但不重跑 yf.download
else:
    st.info("💡 暫無顯示資料。請先執行掃描或收藏個股。")
