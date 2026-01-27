import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import os, json, time

# ==========================================
# 1. 系統環境與資料庫讀取
# ==========================================
IS_STREAMLIT = hasattr(st, "runtime") and st.runtime.exists()

if IS_STREAMLIT:
    st.set_page_config(page_title="台股形態雷達 Pro X", layout="wide")
    if 'favorites' not in st.session_state:
        st.session_state.favorites = {}

def load_db():
    f = "taiwan_full_market.json"
    if os.path.exists(f):
        with open(f, "r", encoding="utf-8") as file:
            data = json.load(file)
        return {k.replace(".TW.TW", ".TW").strip(): v for k, v in data.items()}
    return {"2330.TW": "台積電"}

# ==========================================
# 2. 專業指標運算邏輯
# ==========================================
def run_analysis(sid, name, df, config, force_show=False):
    if df is None or len(df) < 60: return None # 專業版需要更長數據計算 MA
    try:
        df = df.dropna()
        c = float(df["Close"].iloc[-1])
        v_last = df["Volume"].iloc[-1]
        v_avg = df["Volume"].iloc[-21:-1].mean()
        
        # --- 技術指標計算 ---
        ma5 = df["Close"].rolling(5).mean().iloc[-1]
        ma20 = df["Close"].rolling(20).mean().iloc[-1]
        ma60 = df["Close"].rolling(60).mean().iloc[-1]
        
        # RSI 計算
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs.iloc[-1]))

        active_hits = []
        
        # 1. 形態判定 (三角/箱型)
        x = np.arange(15)
        h, l = df["High"].iloc[-15:].values, df["Low"].iloc[-15:].values
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        
        if config["f_tri"] and (sh < -0.001 and sl > 0.001): active_hits.append("📐三角收斂")
        if config["f_box"] and (abs(sh) < 0.02 and abs(sl) < 0.02): active_hits.append("📦箱型整理")
        
        # 2. 專業功能：多頭排列 (5MA > 20MA > 60MA)
        if config["f_trend"] and (ma5 > ma20 > ma60): active_hits.append("🔥多頭排列")
        
        # 3. 今日爆量
        if config["f_vol"] and (v_last > v_avg * 2): active_hits.append("🚀今日爆量")
        
        # 4. RSI 預警 (超賣區強彈機率高)
        if config["f_rsi"] and rsi < 30: active_hits.append("💧RSI超賣")
        
        # --- 篩選與過濾 ---
        should_show = force_show or bool(active_hits)
        
        # 5. 專業過濾：乖離率限制 (防止追高，股價離 MA20 太遠不顯示)
        bias = (c - ma20) / ma20 * 100
        if config["f_bias"] and bias > 10: should_show = False 
        
        if config["f_ma20"] and c < ma20: should_show = False
            
        if should_show:
            return {
                "sid": sid, "name": name, "price": round(c, 2), "vol": int(v_last/1000), 
                "bias": round(bias, 1), "rsi": round(rsi, 1),
                "hits": active_hits if active_hits else ["🔍觀察中"], 
                "df": df, "lines": (sh, ih, sl, il, x)
            }
    except: pass
    return None

# ==========================================
# 3. Sidebar 控制面板 (專業功能開關)
# ==========================================
full_db = load_db()
with st.sidebar:
    st.title("🛡️ Pro-X 策略終端")
    app_mode = st.radio("主功能", ["⚡ 全市場掃描", "❤️ 追蹤清單"], label_visibility="collapsed")
    
    st.divider()
    st.caption("📈 策略組合")
    f_tri = st.checkbox("📐 三角收斂 (壓縮)", True)
    f_box = st.checkbox("📦 箱型整理 (打底)", True)
    f_trend = st.checkbox("🔥 多頭排列 (強勢)", True)
    f_vol = st.checkbox("🚀 今日爆量 (攻擊)", False)
    f_rsi = st.checkbox("💧 RSI 超賣 (抄底)", False)
    
    st.divider()
    st.caption("🛡️ 風控與過濾")
    f_ma20 = st.checkbox("📈 僅看站上 MA20", True)
    f_bias = st.checkbox("🚫 排除過度追高 (>10%)", True)
    
    config = {
        "f_tri": f_tri, "f_box": f_box, "f_trend": f_trend, 
        "f_vol": f_vol, "f_rsi": f_rsi, "f_ma20": f_ma20, "f_bias": f_bias
    }
    
    min_v = st.number_input("成交量門檻", value=500)
    scan_limit = st.slider("掃描檔數", 50, 500, 100)
    
    search_input = st.text_input("🔍 手動輸入代碼 (2330, 2454)")

# ==========================================
# 4. 掃描引擎與顯示
# ==========================================
st.header(f"📡 目前模式：{app_mode}")

# 根據模式決定掃描代碼
if app_mode == "❤️ 追蹤清單":
    active_codes = list(st.session_state.favorites.keys())
    is_searching = True # 追蹤清單模式強制顯示所有細節
else:
    is_searching = bool(search_input)
    active_codes = [c.strip()+".TW" if "." not in c else c.strip().upper() for c in search_input.split(",")] if is_searching else list(full_db.keys())

results = []
if active_codes:
    with st.status(f"正在對 {len(active_codes[:scan_limit])} 檔個股進行策略比對...", expanded=False) as status:
        batch_size = 50
        for i in range(0, len(active_codes[:scan_limit]), batch_size):
            batch = active_codes[i:i+batch_size]
            raw_data = yf.download(batch, period="4mo", group_by='ticker', progress=False)
            for sid in batch:
                df = raw_data[sid] if len(batch) > 1 else raw_data
                if not df.empty and (is_searching or (df["Volume"].iloc[-1] / 1000 >= min_v)):
                    res = run_analysis(sid, full_db.get(sid, "未知"), df, config, force_show=is_searching)
                    if res: results.append(res)
        status.update(label=f"✅ 分析完成：符合策略 {len(results)} 檔", state="complete")

if results:
    # 專業數據表格
    summary_df = pd.DataFrame([{
        "代碼": f"https://tw.stock.yahoo.com/quote/{r['sid']}",
        "名稱": r["name"], "價格": r["price"], "成交量": r["vol"],
        "乖離%": r["bias"], "RSI": r["rsi"],
        "狀態": "\n".join(r["hits"])
    } for r in results])
    
    st.dataframe(summary_df, column_config={
        "代碼": st.column_config.LinkColumn("代碼", display_text=r"quote/(.*)$"),
        "乖離%": st.column_config.NumberColumn("乖離%", format="%.1f%%"),
        "狀態": st.column_config.TextColumn("符合策略", width="medium")
    }, hide_index=True, use_container_width=True)

    # 展開 K 線細節與收藏管理
    for r in results:
        ce, cf = st.columns([6, 1])
        with ce:
            exp = st.expander(f"📊 {r['sid']} {r['name']} | RSI: {r['rsi']} | {' + '.join(r['hits'])}", expanded=is_searching)
        with cf:
            if st.button("❤️" if r['sid'] in st.session_state.favorites else "🤍", key=f"fav_{r['sid']}"):
                if r['sid'] in st.session_state.favorites:
                    del st.session_state.favorites[r['sid']]
                else:
                    st.session_state.favorites[r['sid']] = r['name']
                st.rerun()
        
        with exp:
            df_t, (sh, ih, sl, il, x) = r["df"].iloc[-30:], r["lines"]
            fig = go.Figure(data=[go.Candlestick(x=df_t.index, open=df_t['Open'], high=df_t['High'], low=df_t['Low'], close=df_t['Close'], name='K線')])
            
            # 加入 20MA
            ma20_line = r["df"]["Close"].rolling(20).mean().iloc[-30:]
            fig.add_scatter(x=df_t.index, y=ma20_line, mode='lines', line=dict(color='orange', width=1), name='20MA')
            
            if "📐" in "".join(r["hits"]) or "📦" in "".join(r["hits"]):
                fig.add_scatter(x=df_t.index[-15:], y=sh*x+ih, mode='lines', line=dict(color='red', dash='dash'), name='壓力')
                fig.add_scatter(x=df_t.index[-15:], y=sl*x+il, mode='lines', line=dict(color='green', dash='dash'), name='支撐')
            
            fig.update_layout(height=450, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
else:
    st.info("💡 目前沒有符合選股策略的個股。試著放寬左側選股條件，或是切換模式至『追蹤清單』。")
