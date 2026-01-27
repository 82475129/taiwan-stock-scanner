import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import sys, json, os

# 1. 初始化與環境安全檢查
IS_STREAMLIT = hasattr(st, "runtime") and st.runtime.exists()
if IS_STREAMLIT:
    st.set_page_config(page_title="台股形態雷達", layout="wide")
    if 'favorites' not in st.session_state: st.session_state.favorites = {}

def get_favorites():
    return st.session_state.get('favorites', {}) if IS_STREAMLIT else {}

@st.cache_data(ttl=3600)
def load_and_fix_db():
    DB_FILES = ["taiwan_electronic_stocks.json", "taiwan_full_market.json"]
    target_file = next((f for f in DB_FILES if os.path.exists(f)), None)
    if not target_file: return {"2330.TW": "台積電"}
    try:
        with open(target_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        return {k.replace(".TW.TW", ".TW").strip(): v for k, v in raw_data.items()}
    except: return {"2330.TW": "台積電"}

# 2. 核心分析邏輯 (標籤與篩選完全連動)
def run_analysis(df, sid, name, config, force_show=False):
    if df is None or len(df) < 30: return None
    try:
        df = df.dropna()
        c = float(df["Close"].iloc[-1])
        m20 = df["Close"].rolling(20).mean().iloc[-1]
        v_last, v_avg = df["Volume"].iloc[-1], df["Volume"].iloc[-21:-1].mean()
        
        # 形態判定
        x = np.arange(15)
        h, l = df["High"].iloc[-15:].values, df["Low"].iloc[-15:].values
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        
        is_tri = sh < -0.001 and sl > 0.001
        is_box = abs(sh) < 0.02 and abs(sl) < 0.02
        is_vol = v_last > v_avg * 2
        
        # 標籤產生 (靈活連動：沒勾選就不顯示文字)
        active_hits = []
        if config["f_tri"] and is_tri: active_hits.append("📐三角收斂")
        if config["f_box"] and is_box: active_hits.append("📦箱型整理")
        if config["f_vol"] and is_vol: active_hits.append("🚀今日爆量")
        
        # 決定是否抓取股票 (篩選連動)
        should_output = force_show or bool(active_hits)
        if config.get("f_ma20") and c < m20: should_output = False
        
        if should_output:
            return {"sid": sid, "name": name, "price": round(c, 2), "vol": int(v_last/1000), 
                    "hits": active_hits if active_hits else ["🔍一般觀察"], "df": df, "lines": (sh, ih, sl, il, x)}
        return None
    except: return None

# 3. 左側控制面板 (Sidebar)
full_db = load_and_fix_db()
all_codes = list(full_db.keys())

with st.sidebar:
    st.subheader("🎯 交易控制台")
    app_mode = st.radio("模式", ["⚡ 自動雷達", "🛠️ 手動工具"], label_visibility="collapsed")
    st.divider()
    search_input = st.text_input("🔍 個股搜尋", placeholder="2330, 2454")
    st.caption("⚙️ 篩選與顯示設定 (勾選才顯示標籤)")
    f_tri = st.checkbox("📐 三角收斂", True)
    f_box = st.checkbox("📦 箱型整理", True)
    f_vol = st.checkbox("🚀 今日爆量", False)
    f_ma20 = st.checkbox("📈 股價 > MA20", False)
    config = {"f_tri": f_tri, "f_box": f_box, "f_vol": f_vol, "f_ma20": f_ma20}
    min_v = st.number_input("張數門檻", value=500)
    scan_limit = st.slider("掃描上限", 50, 1000, 100)
    
    trigger_scan = True if app_mode == "⚡ 自動雷達" else st.button("🚀 開始掃描", type="primary", use_container_width=True)
    
    st.divider()
    st.subheader("❤️ 我的最愛")
    curr_favs = get_favorites()
    for fid, fname in list(curr_favs.items()):
        fcol1, fcol2 = st.columns([4, 1])
        fcol1.markdown(f"**{fid}** {fname}")
        if fcol2.button("🗑️", key=f"side_{fid}"):
            del st.session_state.favorites[fid]; st.rerun()

# 4. 主畫面顯示
if IS_STREAMLIT:
    st.subheader(f"📈 形態雷達 ({app_mode})")
    is_searching = bool(search_input)
    active_codes = [c.strip() + ".TW" if "." not in c else c.strip().upper() for c in search_input.split(",")] if is_searching else all_codes

    results = []
    if trigger_scan:
        with st.status("📡 正在掃描台股數據...", expanded=False) as status:
            try:
                v_all = yf.download(active_codes, period="5d", progress=False)["Volume"]
                v_latest = v_all.iloc[-1] if not v_all.iloc[-1].isna().all() else v_all.iloc[-2]
                v_sorted = (v_latest / 1000).dropna()
                targets = v_sorted.index.tolist() if is_searching else v_sorted[v_sorted >= min_v].sort_values(ascending=False).head(scan_limit).index.tolist()
                
                if targets:
                    h_data = yf.download(targets, period="3mo", group_by="ticker", progress=False)
                    for sid in targets:
                        df_sid = h_data[sid] if len(targets) > 1 else h_data
                        res = run_analysis(df_sid, sid, full_db.get(sid, "未知"), config, force_show=is_searching)
                        if res: results.append(res)
                status.update(label=f"✅ 掃描完成 (找到 {len(results)} 檔)", state="complete")
            except Exception as e:
                status.update(label="❌ 數據下載失敗", state="error"); st.error(f"錯誤詳情: {e}")

    if results:
        # 表格垂直換行
        summary_df = pd.DataFrame([{"代碼": f"https://tw.stock.yahoo.com/quote/{r['sid']}", "名稱": r['name'], "現價": r['price'], "張數": r['vol'], "狀態": "\n".join(r['hits'])} for r in results])
        st.dataframe(summary_df, column_config={"代碼": st.column_config.LinkColumn("代碼", display_text=r"quote/(.*)$"), "狀態": st.column_config.TextColumn("符合形態", width="medium")}, hide_index=True, use_container_width=True)

        for item in results:
            c1, c2 = st.columns([5, 1])
            with c1: exp = st.expander(f"🔍 {item['sid']} {item['name']} | {' + '.join(item['hits'])}", expanded=is_searching)
            with c2:
                if st.button("❤️" if item['sid'] in get_favorites() else "🤍", key=f"f_{item['sid']}"):
                    if item['sid'] in st.session_state.favorites: del st.session_state.favorites[item['sid']]
                    else: st.session_state.favorites[item['sid']] = item['name']
                    st.rerun()
            with exp:
                df_t, (sh, ih, sl, il, x) = item["df"].iloc[-15:], item["lines"]
                fig = go.Figure(data=[go.Candlestick(x=df_t.index, open=df_t['Open'], high=df_t['High'], low=df_t['Low'], close=df_t['Close'], name='K線')])
                fig.add_scatter(x=df_t.index, y=sh*x+ih, mode='lines', line=dict(color='red', dash='dash'), name='壓力')
                fig.add_scatter(x=df_t.index, y=sl*x+il, mode='lines', line=dict(color='green', dash='dash'), name='支撐')
                fig.update_layout(height=400, xaxis_rangeslider_visible=False, margin=dict(l=5, r=5, t=5, b=5))
                st.plotly_chart(fig, use_container_width=True)
