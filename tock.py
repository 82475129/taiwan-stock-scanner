import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import os, json, time

# ==========================================
# 1. 系統環境偵測
# ==========================================
IS_STREAMLIT = hasattr(st, "runtime") and st.runtime.exists()

if IS_STREAMLIT:
    st.set_page_config(page_title="台股形態雷達 Pro", layout="wide")
    if 'favorites' not in st.session_state:
        st.session_state.favorites = {}

def get_favorites():
    return st.session_state.get('favorites', {}) if IS_STREAMLIT else {}

@st.cache_data(ttl=3600)
def load_db():
    for f in ["taiwan_full_market.json", "taiwan_electronic_stocks.json"]:
        if os.path.exists(f):
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
            return {k.replace(".TW.TW", ".TW").strip(): v for k, v in data.items()}
    return {"2330.TW": "台積電"}

# 形態核心邏輯
def run_analysis(sid, name, df, config, force_show=False):
    if df is None or len(df) < 20: return None
    try:
        df = df.dropna()
        c, v_last = float(df["Close"].iloc[-1]), df["Volume"].iloc[-1]
        v_avg = df["Volume"].iloc[-21:-1].mean()
        
        active_hits = []
        x = np.arange(15)
        h, l = df["High"].iloc[-15:].values, df["Low"].iloc[-15:].values
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        
        if config["f_tri"] and (sh < -0.001 and sl > 0.001): active_hits.append("📐三角收斂")
        if config["f_box"] and (abs(sh) < 0.02 and abs(sl) < 0.02): active_hits.append("📦箱型整理")
        if config["f_vol"] and (v_last > v_avg * 2): active_hits.append("🚀今日爆量")
        
        should_show = force_show or bool(active_hits)
        if config["f_ma20"] and c < df["Close"].rolling(20).mean().iloc[-1]: should_show = False
            
        if should_show:
            return {"sid": sid, "name": name, "price": round(c, 2), "vol": int(v_last/1000), 
                    "hits": active_hits if active_hits else ["🔍一般"], "df": df, "lines": (sh, ih, sl, il, x)}
    except: pass
    return None

# ==========================================
# 2. 介面與控制 (Sidebar)
# ==========================================
full_db = load_db()
all_codes = list(full_db.keys())

# 預設設定
config = {"f_tri": True, "f_box": True, "f_vol": False, "f_ma20": False}
min_v = 500
scan_limit = 100
search_input = ""
app_mode = "⚡ 自動雷達"

if IS_STREAMLIT:
    with st.sidebar:
        st.subheader("🎯 交易控制台")
        app_mode = st.radio("模式", ["⚡ 自動雷達", "🛠️ 手動工具"], label_visibility="collapsed")
        search_input = st.text_input("🔍 個股搜尋", placeholder="2330, 2454")
        f_tri = st.checkbox("📐 三角收斂", True)
        f_box = st.checkbox("📦 箱型整理", True)
        f_vol = st.checkbox("🚀 今日爆量", False)
        f_ma20 = st.checkbox("📈 股價 > MA20", False)
        config = {"f_tri": f_tri, "f_box": f_box, "f_vol": f_vol, "f_ma20": f_ma20}
        min_v = st.number_input("張數門檻", value=500)
        scan_limit = st.slider("掃描上限", 50, 1000, 100)
        trigger_scan = True if app_mode == "⚡ 自動雷達" else st.button("🚀 開始掃描", type="primary")
else:
    trigger_scan = True # GitHub Actions 預設執行

# ==========================================
# 3. 執行掃描 (解決 Rate Limit 與 NoneType 錯誤)
# ==========================================
if IS_STREAMLIT: st.subheader(f"📈 形態監控 ({app_mode})")

results = []
if trigger_scan:
    # 解決 AttributeError: 只有網頁版才呼叫 status
    status_ui = st.status("📡 掃描中...", expanded=False) if IS_STREAMLIT else None
    
    is_searching = bool(search_input)
    active_codes = [c.strip()+".TW" if "." not in c else c.strip().upper() for c in search_input.split(",")] if is_searching else all_codes

    try:
        # 分批抓取數據，避免 Rate Limit
        batch_size = 50
        for i in range(0, len(active_codes[:scan_limit]), batch_size):
            batch = active_codes[i:i+batch_size]
            raw_data = yf.download(batch, period="3mo", group_by='ticker', progress=False)
            
            for sid in batch:
                df = raw_data[sid] if len(batch) > 1 else raw_data
                if not df.empty:
                    if is_searching or (df["Volume"].iloc[-1] / 1000 >= min_v):
                        res = run_analysis(sid, full_db.get(sid, "未知"), df, config, force_show=is_searching)
                        if res: results.append(res)
            
            if not IS_STREAMLIT: time.sleep(1) # GitHub 執行時每批停 1 秒避免被鎖

        if status_ui: status_ui.update(label=f"✅ 完成 (找到 {len(results)} 檔)", state="complete")
        else: print(f"✅ 掃描完成: 找到 {len(results)} 檔")

    except Exception as e:
        if status_ui: status_ui.update(label=f"❌ 錯誤: {e}", state="error")
        else: print(f"❌ 錯誤: {e}")

# ==========================================
# 4. 顯示結果 (僅在網頁模式顯示)
# ==========================================
if IS_STREAMLIT and results:
    summary_data = [{"代碼": f"https://tw.stock.yahoo.com/quote/{r['sid']}", "名稱": r["name"], "現價": r["price"], "張數": r["vol"], "狀態": "\n".join(r["hits"])} for r in results]
    st.dataframe(pd.DataFrame(summary_data), column_config={"代碼": st.column_config.LinkColumn("代碼", display_text=r"quote/(.*)$"), "狀態": st.column_config.TextColumn("符合形態", width="medium")}, hide_index=True, use_container_width=True)

    for r in results:
        with st.expander(f"🔍 {r['sid']} {r['name']} | {' + '.join(r['hits'])}"):
            df_t, (sh, ih, sl, il, x) = r["df"].iloc[-15:], r["lines"]
            fig = go.Figure(data=[go.Candlestick(x=df_t.index, open=df_t['Open'], high=df_t['High'], low=df_t['Low'], close=df_t['Close'], name='K線')])
            if config["f_tri"] or config["f_box"]:
                fig.add_scatter(x=df_t.index, y=sh*x+ih, mode='lines', line=dict(color='red', dash='dash'))
                fig.add_scatter(x=df_t.index, y=sl*x+il, mode='lines', line=dict(color='green', dash='dash'))
            fig.update_layout(height=400, xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
