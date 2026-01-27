import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import sys, json, os, datetime

# ==========================================
# 0. 系統基礎設定
# ==========================================
IS_STREAMLIT = "streamlit" in sys.argv[0] or any("streamlit" in arg for arg in sys.argv)
# 支援多個可能的檔名
DB_FILES = ["taiwan_electronic_stocks.json", "taiwan_full_market.json"]

if IS_STREAMLIT:
    st.set_page_config(page_title="台股形態分析終端", layout="wide")

@st.cache_data(ttl=3600)
def load_and_fix_db():
    """讀取並自動修正代碼格式錯誤"""
    target_file = None
    for f_path in DB_FILES:
        if os.path.exists(f_path):
            target_file = f_path
            break
            
    if not target_file:
        return {"2330.TW": "台積電", "2317.TW": "鴻海"}

    try:
        with open(target_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        
        # 關鍵修正：將 ".TW.TW" 替換為 ".TW"，並移除多餘空白
        fixed_data = {
            k.replace(".TW.TW", ".TW").strip(): v 
            for k, v in raw_data.items()
        }
        return fixed_data
    except Exception as e:
        st.error(f"讀取 JSON 失敗: {e}")
        return {"2330.TW": "台積電"}

# ==========================================
# 1. 形態分析引擎
# ==========================================
def run_analysis(df, sid, name, config):
    if df is None or len(df) < 30:
        return None

    try:
        df = df.dropna()
        c = float(df["Close"].iloc[-1])
        m20 = df["Close"].rolling(20).mean().iloc[-1]
        v_last = df["Volume"].iloc[-1]
        v_avg = df["Volume"].iloc[-21:-1].mean()

        # 過濾：股價 > MA20
        if config["f_ma20"] and c < m20:
            return None

        d_len = 15
        x = np.arange(d_len)
        h = df["High"].iloc[-d_len:].astype(float).values
        l = df["Low"].iloc[-d_len:].astype(float).values

        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)

        hits = []
        # 三角收斂
        if config["f_tri"] and sh < -0.001 and sl > 0.001:
            hits.append("📐 三角收斂")
        # 箱型整理
        if config["f_box"] and abs(sh) < 0.02 and abs(sl) < 0.02:
            hits.append("📦 箱型整理")
        # 今日爆量
        if config["f_vol"] and v_last > v_avg * 2:
            hits.append("🚀 今日爆量")

        if not hits:
            return None

        return {
            "sid": sid, "name": name, "price": round(c, 2),
            "hits": hits, "df": df, "lines": (sh, ih, sl, il, x),
        }
    except:
        return None

# ==========================================
# 2. UI 介面
# ==========================================
db = load_and_fix_db()

with st.sidebar:
    st.header("🎯 策略控制")
    mode = st.radio("模式", ["⚡ 全市場掃描", "🔍 單檔診斷"])
    
    st.divider()
    st.subheader("形態過濾")
    f_tri = st.checkbox("📐 三角收斂", True)
    f_box = st.checkbox("📦 箱型整理", False)
    f_vol = st.checkbox("🚀 今日爆量", False)
    f_ma20 = st.checkbox("📈 股價 > MA20", True)
    
    config = {"f_tri": f_tri, "f_box": f_box, "f_vol": f_vol, "f_ma20": f_ma20}
    
    if mode == "⚡ 全市場掃描":
        min_v = st.number_input("成交量門檻 (張)", value=1000, step=100)
        scan_limit = st.slider("掃描上限", 50, 500, 100)
    else:
        sid_input = st.text_input("輸入代碼", value="2330.TW")

    run_btn = st.button("🚀 開始執行", type="primary", use_container_width=True)

# ==========================================
# 3. 執行邏輯
# ==========================================
if mode == "⚡ 全市場掃描":
    st.title("⚡ 台股即時形態雷達")
    
    if run_btn:
        codes = list(db.keys())
        
        with st.status("📡 正在掃描市場...", expanded=True) as status:
            # 第一步：獲取成交量（初步篩選）
            st.write("1. 獲取成交量數據...")
            v_df = yf.download(codes, period="5d", progress=False)["Volume"]
            
            # 找到最新有資料的一天
            latest_v_col = v_df.iloc[-1]
            if latest_v_col.isna().all():
                latest_v_col = v_df.iloc[-2]
            
            # 成交量過濾 (張數 = yf成交量 / 1000)
            vol_filtered = (latest_v_col / 1000).dropna()
            targets = vol_filtered[vol_filtered >= min_v].sort_values(ascending=False).head(scan_limit).index.tolist()
            
            st.write(f"2. 成交量達標股票: {len(targets)} 檔 (開始形態辨識...)")
            
            if not targets:
                st.error("❌ 找不到成交量達標的股票，請調低門檻。")
                st.stop()

            # 第二步：獲取歷史資料進行形態分析
            h_data = yf.download(targets, period="3mo", group_by="ticker", progress=False)
            
            results = []
            for sid in targets:
                # 處理單檔與多檔回傳格式差異
                df_sid = h_data[sid] if len(targets) > 1 else h_data
                res = run_analysis(df_sid, sid, db.get(sid, "未知"), config)
                if res:
                    results.append(res)

            status.update(label=f"✅ 掃描完成！找到 {len(results)} 檔符合條件", state="complete")

        # 渲染圖表
        if not results:
            st.info("💡 未偵測到符合選定形態的標的。")
        else:
            for item in results:
                with st.expander(f"📈 {item['sid']} {item['name']} | 現價: {item['price']}", expanded=True):
                    st.write(f"**偵測結果:** {'、'.join(item['hits'])}")
                    
                    df_t = item["df"].iloc[-15:]
                    sh, ih, sl, il, x = item["lines"]
                    
                    fig = go.Figure()
                    fig.add_candlestick(x=df_t.index, open=df_t["Open"], high=df_t["High"],
                                        low=df_t["Low"], close=df_t["Close"], name="K線")
                    fig.add_scatter(x=df_t.index, y=sh * x + ih, mode="lines", name="壓力", line=dict(color="red", dash="dash"))
                    fig.add_scatter(x=df_t.index, y=sl * x + il, mode="lines", name="支撐", line=dict(color="green", dash="dash"))
                    fig.update_layout(height=400, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10))
                    st.plotly_chart(fig, use_container_width=True)

else:
    # 單檔診斷邏輯
    if run_btn:
        sid = sid_input.strip().upper()
        if ".TW" not in sid: sid += ".TW"
        
        df = yf.download(sid, period="3mo", progress=False)
        res = run_analysis(df, sid, db.get(sid, "未知標的"), config)
        
        if res:
            st.success(f"✅ {sid} 符合條件: {', '.join(res['hits'])}")
            # ... 繪圖邏輯同上 ...
        else:
            st.warning("⚠️ 該標的不符合當前過濾條件。")
