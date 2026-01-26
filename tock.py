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
    if not os.path.exists(DB_FILE):
        return {"2330.TW": "台積電"}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# ==========================================
# 形態分析引擎
# ==========================================
def run_analysis(df, sid, name, config):
    if df is None or len(df) < 35:
        return None

    try:
        c = df["Close"].iloc[-1]
        m20 = df["Close"].rolling(20).mean().iloc[-1]
        v_last = df["Volume"].iloc[-1]
        v_avg = df["Volume"].iloc[-21:-1].mean()

        if config["f_ma20"] and c < m20:
            return None

        d_len = 15
        x = np.arange(d_len)
        h = df["High"].iloc[-d_len:].astype(float).values
        l = df["Low"].iloc[-d_len:].astype(float).values

        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)

        hits = []
        if config["f_tri"] and sh < -0.002 and sl > 0.002:
            hits.append("📐 三角收斂")
        if config["f_box"] and abs(sh) < 0.015 and abs(sl) < 0.015:
            hits.append("📦 箱型整理")
        if config["f_vol"] and v_last > v_avg * 2:
            hits.append("🚀 今日爆量")

        if not hits:
            return None

        return {
            "sid": sid,
            "name": name,
            "price": round(c, 2),
            "hits": hits,
            "df": df,
            "lines": (sh, ih, sl, il, x),
        }

    except Exception:
        return None

# ==========================================
# UI
# ==========================================
db = load_db()

with st.sidebar:
    st.title("🏹 策略控制台")
    mode = st.radio("功能選擇", ["⚡ 自動全市場監控", "⏳ 歷史手動搜尋"])
    st.divider()

    st.subheader("形態過濾設定")
    f_tri = st.checkbox("📐 三角收斂", False)
    f_box = st.checkbox("📦 箱型整理", False)
    f_vol = st.checkbox("🚀 今日爆量", False)
    f_ma20 = st.checkbox("📈 股價 > MA20", False)

    config = {
        "f_tri": f_tri,
        "f_box": f_box,
        "f_vol": f_vol,
        "f_ma20": f_ma20,
    }

    st.divider()

    if mode == "⚡ 自動全市場監控":
        min_v = st.number_input("成交量門檻 (張)", value=2000, step=500)
        scan_limit = st.slider("掃描上限", 50, 200, 100)
        run_btn = st.button("🚀 啟動掃描", type="primary", use_container_width=True)
    else:
        sid_input = st.text_input("輸入代碼", value="2330.TW")
        run_btn = st.button("🔍 執行分析", type="primary", use_container_width=True)

# ==========================================
# 主畫面
# ==========================================
if mode == "⚡ 自動全市場監控":
    st.header("⚡ 市場形態雷達")

    if run_btn:
        if not any([f_tri, f_box, f_vol]):
            st.warning("請至少勾選一種形態")
            st.stop()

        # ===== 非交易時段提示 =====
        now = datetime.datetime.now()
        if now.hour < 9 or now.hour > 14:
            st.info("📴 非台股交易時段，成交量可能不完整")

        all_codes = list(db.keys())

        with st.status("🔍 掃描中...", expanded=True) as status:

            # ===== 成交量抓取（防炸）=====
            v_raw = yf.download(
                all_codes,
                period="5d",          # ← 關鍵：避免假日炸
                progress=False,
                threads=True,
            )

            if v_raw.empty or "Volume" not in v_raw:
                st.error("❌ 無法取得成交量資料（假日或 Yahoo API 異常）")
                st.stop()

            v_data = v_raw["Volume"].dropna(how="all")

            if len(v_data) == 0:
                st.error("❌ 成交量資料為空")
                st.stop()

            latest_v = (v_data.iloc[-1] / 1000).dropna()

            targets = (
                latest_v[latest_v >= min_v]
                .sort_values(ascending=False)
                .head(scan_limit)
                .index.tolist()
            )

            if not targets:
                st.warning("⚠️ 無符合成交量門檻標的")
                st.stop()

            # ===== 歷史資料 =====
            h_data = yf.download(
                targets,
                period="3mo",
                group_by="ticker",
                progress=False,
                threads=True,
            )

            results = []
            for sid in targets:
                if sid not in h_data:
                    continue
                res = run_analysis(
                    h_data[sid].dropna(),
                    sid,
                    db.get(sid, ""),
                    config,
                )
                if res:
                    results.append(res)

            status.update(
                label=f"✅ 完成！找到 {len(results)} 檔符合條件",
                state="complete",
            )

        # ===== 顯示結果 =====
        for item in results:
            with st.expander(f"{item['sid']} {item['name']}", expanded=True):
                st.write(
                    f"現價：{item['price']} ｜ 形態：{', '.join(item['hits'])}"
                )

                df = item["df"]
                sh, ih, sl, il, x = item["lines"]
                df_t = df.iloc[-len(x):]

                fig = go.Figure()

                fig.add_candlestick(
                    x=df_t.index,
                    open=df_t["Open"],
                    high=df_t["High"],
                    low=df_t["Low"],
                    close=df_t["Close"],
                    name="K線",
                )

                fig.add_scatter(
                    x=df_t.index,
                    y=sh * x + ih,
                    mode="lines",
                    name="高點趨勢",
                )
                fig.add_scatter(
                    x=df_t.index,
                    y=sl * x + il,
                    mode="lines",
                    name="低點趨勢",
                )

                fig.update_layout(
                    height=420,
                    xaxis_rangeslider_visible=False,
                    margin=dict(l=10, r=10, t=30, b=10),
                )

                st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("👈 勾選形態後，點擊「啟動掃描」")

# ==========================================
# 手動模式
# ==========================================
else:
    if run_btn and sid_input:
        df = yf.download(sid_input, period="3mo", progress=False)
        res = run_analysis(df, sid_input, db.get(sid_input, ""), config)

        if res:
            st.success(f"{sid_input} 偵測到：{', '.join(res['hits'])}")
        else:
            st.warning("未偵測到符合形態")
