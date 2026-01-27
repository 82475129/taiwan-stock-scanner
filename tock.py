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
DB_FILE = "taiwan_full_market.json"

if IS_STREAMLIT:
    st.set_page_config(page_title="台股策略分析終端", layout="wide")

@st.cache_data(ttl=3600)
def load_db():
    # 如果檔案不存在，建立一個基礎清單（權值股測試用）
    if not os.path.exists(DB_FILE):
        default_db = {
            "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", 
            "2308.TW": "台達電", "2382.TW": "廣達", "2881.TW": "富邦金",
            "2882.TW": "國泰金", "2303.TW": "聯電", "3711.TW": "日月光投控"
        }
        return default_db
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"2330.TW": "台積電"}

# ==========================================
# 核心形態分析引擎
# ==========================================
def run_analysis(df, sid, name, config):
    if df is None or len(df) < 30:
        return None

    try:
        # 清除任何可能的空值
        df = df.dropna()
        c = float(df["Close"].iloc[-1])
        m20 = df["Close"].rolling(20).mean().iloc[-1]
        v_last = df["Volume"].iloc[-1]
        v_avg = df["Volume"].iloc[-21:-1].mean()

        # 過濾條件 1: 股價必須在 MA20 之上 (如果勾選)
        if config["f_ma20"] and c < m20:
            return None

        # 形態計算
        d_len = 15
        x = np.arange(d_len)
        h = df["High"].iloc[-d_len:].astype(float).values
        l = df["Low"].iloc[-d_len:].astype(float).values

        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)

        hits = []
        # 判定 A: 三角收斂 (高點下壓，低點支撐)
        if config["f_tri"] and sh < -0.001 and sl > 0.001:
            hits.append("📐 三角收斂")
        
        # 判定 B: 箱型整理 (斜率接近 0)
        if config["f_box"] and abs(sh) < 0.02 and abs(sl) < 0.02:
            hits.append("📦 箱型整理")
            
        # 判定 C: 今日爆量 (成交量 > 20日均量 2 倍)
        if config["f_vol"] and v_last > v_avg * 2:
            hits.append("🚀 今日爆量")

        if not hits:
            return None

        return {
            "sid": sid, "name": name, "price": round(c, 2),
            "hits": hits, "df": df, "lines": (sh, ih, sl, il, x),
        }
    except Exception as e:
        return None

# ==========================================
# UI 介面
# ==========================================
db = load_db()

with st.sidebar:
    st.title("🏹 策略控制台")
    mode = st.radio("功能選擇", ["⚡ 自動全市場監控", "⏳ 手動分析"])
    st.divider()

    st.subheader("形態過濾設定")
    f_tri = st.checkbox("📐 三角收斂", True)
    f_box = st.checkbox("📦 箱型整理", False)
    f_vol = st.checkbox("🚀 今日爆量", False)
    f_ma20 = st.checkbox("📈 股價 > MA20", False)

    config = {"f_tri": f_tri, "f_box": f_box, "f_vol": f_vol, "f_ma20": f_ma20}
    st.divider()

    if mode == "⚡ 自動全市場監控":
        min_v = st.number_input("成交量門檻 (張)", value=500, step=500) # 調低門檻測試
        scan_limit = st.slider("掃描上限", 50, 500, 100)
        run_btn = st.button("🚀 啟動掃描", type="primary", use_container_width=True)
    else:
        sid_input = st.text_input("輸入代碼 (需含.TW)", value="2330.TW")
        run_btn = st.button("🔍 執行分析", type="primary", use_container_width=True)

# ==========================================
# 主邏輯
# ==========================================
if mode == "⚡ 自動全市場監控":
    st.header("⚡ 市場形態雷達")

    if run_btn:
        if not any([f_tri, f_box, f_vol]):
            st.warning("⚠️ 請至少勾選一種形態過濾條件")
            st.stop()

        all_codes = list(db.keys())
        
        with st.status("🔍 正在獲取市場資料...", expanded=True) as status:
            # 1. 抓取近期資料 (多抓幾天避免假日或開盤無資料)
            st.write("📡 下載成交量數據...")
            raw_v = yf.download(all_codes, period="5d", progress=False)["Volume"]
            
            if raw_v.empty:
                st.error("❌ 無法取得數據，請檢查網路或 Yahoo Finance 狀態")
                st.stop()

            # 確保取得「最新一個有資料的交易日」
            latest_v_series = raw_v.iloc[-1]
            if latest_v_series.isna().all():
                latest_v_series = raw_v.iloc[-2]
            
            latest_v = (latest_v_series / 1000).dropna()
            
            # 2. 初步成交量篩選
            targets = latest_v[latest_v >= min_v].sort_values(ascending=False).head(scan_limit).index.tolist()
            st.write(f"📊 成交量達標股票: {len(targets)} 檔")

            if not targets:
                status.update(label="⚠️ 無符合成交量門檻標的", state="error")
                st.stop()

            # 3. 細部形態分析
            st.write("🧪 執行形態辨識演算法...")
            h_data = yf.download(targets, period="3mo", group_by="ticker", progress=False)
            
            results = []
            for sid in targets:
                # 處理單檔或多檔回傳格式差異
                df_sid = h_data[sid] if len(targets) > 1 else h_data
                res = run_analysis(df_sid, sid, db.get(sid, "未知"), config)
                if res:
                    results.append(res)

            status.update(label=f"✅ 完成！找到 {len(results)} 檔符合條件", state="complete")

        # 顯示圖表
        if not results:
            st.info("💡 目前沒有偵測到符合選定形態的股票。")
        else:
            for item in results:
                with st.expander(f"📌 {item['sid']} {item['name']} - {item['price']}", expanded=True):
                    cols = st.columns([1, 3])
                    with cols[0]:
                        st.metric("當前股價", item['price'])
                        st.write("**偵測形態:**")
                        for h in item['hits']:
                            st.info(h)
                    
                    with cols[1]:
                        df_t = item["df"].iloc[-15:]
                        sh, ih, sl, il, x = item["lines"]
                        
                        fig = go.Figure()
                        fig.add_candlestick(x=df_t.index, open=df_t["Open"], high=df_t["High"],
                                            low=df_t["Low"], close=df_t["Close"], name="K線")
                        fig.add_scatter(x=df_t.index, y=sh * x + ih, mode="lines", name="壓力線", line=dict(color="red", dash="dash"))
                        fig.add_scatter(x=df_t.index, y=sl * x + il, mode="lines", name="支撐線", line=dict(color="green", dash="dash"))
                        fig.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10), xaxis_rangeslider_visible=False)
                        st.plotly_chart(fig, use_container_width=True)

else: # 手動模式
    if run_btn and sid_input:
        df = yf.download(sid_input, period="3mo", progress=False)
        res = run_analysis(df, sid_input, db.get(sid_input, ""), config)
        if res:
            st.success(f"✅ {sid_input} 偵測到形態：{', '.join(res['hits'])}")
            # ... 繪圖邏輯同上 ...
        else:
            st.warning("❌ 該標的不符合目前形態過濾設定")
