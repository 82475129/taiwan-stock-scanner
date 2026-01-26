import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import concurrent.futures
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.stats import linregress
from streamlit_autorefresh import st_autorefresh
import json
import os

# ==========================================
# 0. 狀態鎖定
# ==========================================
if "current_mode" not in st.session_state:
    st.session_state.current_mode = "⚡ 今日即時監控 (自動)"

DB_FILE = "taiwan_electronic_stocks.json"

@st.cache_data(ttl=3600)
def load_full_db():
    base = {
        "2330.TW": "台積電",
        "2454.TW": "聯發科",
        "2317.TW": "鴻海",
        "3045.TW": "台灣大"
    }
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return base
    return base

@st.cache_data(ttl=300)
def get_stock_data(sid):
    try:
        df = yf.download(sid, period="45d", progress=False)
        if df.empty:
            return pd.DataFrame()
        df = df.dropna()
        return df
    except:
        return pd.DataFrame()

# ==========================================
# 1. 形態分析（UI 不變）
# ==========================================
def analyze_patterns(df, config, days=15):
    if df is None or df.empty or len(df) < days:
        return None

    d = df.tail(days)
    h = d["High"].values.astype(float)
    l = d["Low"].values.astype(float)
    v = d["Volume"].values.astype(float)
    x = np.arange(len(h))

    sh, ih, *_ = linregress(x, h)
    sl, il, *_ = linregress(x, l)

    v_mean = np.mean(v[-6:-1]) if len(v) >= 6 else np.mean(v)

    hits = []

    if config.get("tri") and sh < -0.003 and sl > 0.003:
        hits.append({"text": "📐三角收斂", "class": "badge-tri"})

    if config.get("box") and abs(sh) < 0.03 and abs(sl) < 0.03:
        hits.append({"text": "📦旗箱整理", "class": "badge-box"})

    if config.get("vol") and v[-1] > v_mean * 1.3:
        hits.append({"text": "🚀今日爆量", "class": "badge-vol"})

    return {
        "labels": hits,
        "lines": (sh, ih, sl, il, x),
        "price": round(float(df["Close"].iloc[-1]), 2),
        "vol": int(v[-1] // 1000),
    }

# ==========================================
# 2. UI（完全不變）
# ==========================================
st.set_page_config(page_title="台股 Pro-X 形態大師", layout="wide")
st.markdown("""
<style>
.stApp { background-color: #f4f7f6; }
.stock-card {
    background: white; padding: 16px; border-radius: 12px;
    margin-bottom: 15px; border-left: 6px solid #6c5ce7;
}
.card-row { display:flex; justify-content:space-between; margin-bottom:6px; }
.sid-link { font-weight:bold; color:#6c5ce7; text-decoration:none; }
.price { color:#d63031; font-size:1.2rem; font-weight:800; }
.badge { padding:4px 10px; border-radius:6px; font-size:0.75rem; color:white; }
.badge-tri { background:#6c5ce7; }
.badge-box { background:#2d3436; }
.badge-vol { background:#d63031; }
.badge-none { background:#b2bec3; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 側邊欄
# ==========================================
db = load_full_db()
modes = [
    "⚡ 今日即時監控 (自動)",
    "⏳ 歷史形態搜尋 (手動)",
    "🌐 顯示所有股票連結"
]

with st.sidebar:
    st.title("🎯 形態大師控制台")
    mode = st.radio("選擇功能模式", modes, index=modes.index(st.session_state.current_mode))
    st.session_state.current_mode = mode
    st.divider()

    if mode == "⚡ 今日即時監控 (自動)":
        st_autorefresh(interval=300000, key="auto")
        t_tri = st.checkbox("📐 三角收斂", True)
        t_box = st.checkbox("📦 旗箱整理", True)
        t_vol = st.checkbox("🚀 今日爆量", True)
        t_min_v = st.number_input("最低量 (張)", value=300)
        current_config = {"tri": t_tri, "box": t_box, "vol": t_vol}
        run_now = True

    elif mode == "⏳ 歷史形態搜尋 (手動)":
        h_sid = st.text_input("代號 (輸入即強制顯示圖表)", placeholder="2330")
        h_tri = st.checkbox("📐 三角收斂", True)
        h_box = st.checkbox("📦 旗箱整理", True)
        h_vol = st.checkbox("🚀 今日爆量", True)
        h_min_v = st.number_input("最低量 (張)", value=100)
        current_config = {"tri": h_tri, "box": h_box, "vol": h_vol}
        run_now = st.button("🚀 開始掃描", use_container_width=True)
    else:
        run_now = False

# ==========================================
# 4. 主畫面邏輯（⭐ 關鍵修正在這）
# ==========================================
if mode == "🌐 顯示所有股票連結":
    for sid, name in db.items():
        clean = sid.split(".")[0]
        st.markdown(
            f'<a class="sid-link" target="_blank" href="https://tw.stock.yahoo.com/quote/{clean}">{clean} {name}</a>',
            unsafe_allow_html=True
        )

elif run_now:
    is_specific = (
        mode == "⏳ 歷史形態搜尋 (手動)"
        and "h_sid" in locals()
        and h_sid.strip() != ""
    )

    targets = (
        [(f"{h_sid.upper()}.TW", "個股"), (f"{h_sid.upper()}.TWO", "個股")]
        if is_specific else list(db.items())
    )

    mv_limit = t_min_v if mode.startswith("⚡") else h_min_v
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as exe:
        fs = {exe.submit(get_stock_data, s): (s, n) for s, n in targets}
        for f in concurrent.futures.as_completed(fs):
            sid, name = fs[f]
            df = f.result()
            res = analyze_patterns(df, current_config)

            # ⭐ 關鍵：手動輸入一定顯示
            if res and (
                is_specific
                or (res["labels"] and res["vol"] >= mv_limit)
            ):
                res.update({"sid": sid, "name": name, "df": df})
                results.append(res)

    if not results:
        st.info("🔍 尚未符合條件的股票")

    for item in results:
        clean = item["sid"].split(".")[0]
        badges = (
            "".join(
                f'<span class="badge {b["class"]}">{b["text"]}</span>'
                for b in item["labels"]
            )
            if item["labels"]
            else '<span class="badge badge-none">🔘 一般走勢</span>'
        )

        st.markdown(f"""
        <div class="stock-card">
            <div class="card-row">
                <a class="sid-link" target="_blank" href="https://tw.stock.yahoo.com/quote/{clean}">
                    🔗 {item["sid"]}
                </a>
                <span>{item["name"]}</span>
            </div>
            <div class="card-row">
                <span>成交量 <b>{item["vol"]} 張</b></span>
                <span class="price">${item["price"]}</span>
            </div>
            <div>{badges}</div>
        </div>
        """, unsafe_allow_html=True)

        with st.expander("📈 展開形態圖表"):
            d = item["df"].tail(30)
            sh, ih, sl, il, x = item["lines"]
            fig = make_subplots(rows=1, cols=1)
            fig.add_candlestick(
                x=d.index,
                open=d["Open"],
                high=d["High"],
                low=d["Low"],
                close=d["Close"],
            )
            p = d.tail(15)
            fig.add_scatter(x=p.index, y=sh * x + ih, line=dict(dash="dash"))
            fig.add_scatter(x=p.index, y=sl * x + il, line=dict(dash="dot"))
            fig.update_layout(
                height=400,
                xaxis_rangeslider_visible=False,
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)

else:
    st.info("👈 請從左側選擇功能")
