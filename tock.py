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
# 0. 核心資料載入與格式化
# ==========================================
if "current_mode" not in st.session_state:
    st.session_state.current_mode = "⚡ 今日即時監控 (自動)"

@st.cache_data(ttl=3600)
def load_db():
    DB_FILE = "taiwan_electronic_stocks.json"
    # 預設資料庫
    base = {"2330.TW": "台積電", "2454.TW": "聯發科", "2317.TW": "鴻海", "2481.TW": "強茂", "2352.TW": "佳世達"}
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {k: (v['name'] if isinstance(v, dict) else v) for k, v in data.items()}
        except:
            return base
    return base

@st.cache_data(ttl=300)
def get_stock_data(sid):
    try:
        df = yf.download(sid, period="45d", progress=False)
        if df.empty: return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df.loc[:, ~df.columns.duplicated()]
        return df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    except:
        return pd.DataFrame()

# ==========================================
# 1. 形態演算法 (線性回歸分析)
# ==========================================
def analyze(df, config):
    if df.empty or len(df) < 15: return None
    d = df.tail(15)
    h, l, v = d["High"].values.flatten(), d["Low"].values.flatten(), d["Volume"].values.flatten()
    x = np.arange(len(h))
    sh, ih, *_ = linregress(x, h)
    sl, il, *_ = linregress(x, l)
    v_mean = np.mean(v[:-1]) if len(v) > 1 else 1

    hits = []
    if config.get("tri") and sh < -0.003 and sl > 0.003: hits.append("📐 三角收斂")
    if config.get("box") and abs(sh) < 0.03 and abs(sl) < 0.03: hits.append("📦 旗箱整理")
    if config.get("vol") and v[-1] > v_mean * 1.3: hits.append("🚀 今日爆量")

    return {"labels": hits, "lines": (sh, ih, sl, il, x), "vol": int(v[-1] // 1000)}

# ==========================================
# 2. 高級 UI 質感設計 (CSS)
# ==========================================
st.set_page_config(page_title="台股 Pro-X 形態大師", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@300;500;700&display=swap');
html, body, [class*="css"] { font-family: 'Noto Sans TC', sans-serif; background-color: #f8f9fa; }

.title-container { text-align: center; padding: 30px 0; background: #ffffff; border-bottom: 1px solid #e9ecef; margin-bottom: 30px; }
.main-title { font-size: 28px; font-weight: 700; color: #212529; margin-bottom: 5px; letter-spacing: 1px; }
.sub-title { font-size: 13px; color: #adb5bd; font-weight: 300; letter-spacing: 3px; text-transform: uppercase; }

.stock-card { background: white; padding: 20px; border-radius: 10px; border: 1px solid #edf2f7; margin-bottom: 15px; transition: all 0.2s ease; }
.stock-card:hover { border-color: #cbd5e0; box-shadow: 0 4px 12px rgba(0,0,0,0.03); }
.card-id { font-size: 19px; font-weight: 700; color: #4a5568; text-decoration: none; }
.card-id:hover { color: #667eea; }
.card-vol { float: right; font-size: 14px; color: #a0aec0; font-weight: 500; background: #f7fafc; padding: 2px 8px; border-radius: 4px; }

.badge { display: inline-block; padding: 4px 10px; border-radius: 5px; font-size: 12px; font-weight: 600; margin-right: 8px; margin-top: 12px; color: white; }
.bg-pattern { background: #667eea; }
.bg-vol { background: #f56565; }
.bg-none { background: #edf2f7; color: #a0aec0; }

/* 新增漂亮股票列表 */
.stock-list { padding: 15px; background: #ffffff; border-radius: 8px; border: 1px solid #e9ecef; }
.stock-list a { text-decoration: none; color: #1f2937; font-weight: 500; }
.stock-list a:hover { color: #3b82f6; }
.stock-list .symbol { font-weight: 700; margin-right: 6px; }
</style>
""", unsafe_allow_html=True)

# 標題
st.markdown('<div class="title-container"><div class="main-title">🎯 台股 Pro-X 形態大師</div><div class="sub-title">Advanced Technical Analysis System</div></div>', unsafe_allow_html=True)

# ==========================================
# 3. 側邊欄控制
# ==========================================
db = load_db()
modes = ["⚡ 今日即時監控 (自動)", "⏳ 歷史形態搜尋 (手動)", "🌐 顯示所有股票連結"]

with st.sidebar:
    st.title("Settings")
    mode = st.radio("功能模式", modes, index=modes.index(st.session_state.current_mode))
    st.session_state.current_mode = mode
    st.divider()

    if "自動" in mode:
        st_autorefresh(interval=300000, key="auto")
        conf = {"tri": st.checkbox("📐 三角收斂", True), "box": st.checkbox("📦 旗箱整理", True), "vol": st.checkbox("🚀 今日爆量", True)}
        min_v = st.number_input("最低成交量 (張)", value=300)
        run = True
    elif "手動" in mode:
        sid_in = st.text_input("輸入代號 (如 2330)")
        conf = {"tri": st.checkbox("📐 三角收斂", True), "box": st.checkbox("📦 旗箱整理", True), "vol": st.checkbox("🚀 今日爆量", True)}
        min_v = 0
        run = st.button("🚀 開始分析", use_container_width=True)
    else:
        run = False

# ==========================================
# 4. 邏輯與介面渲染
# ==========================================
if mode == "🌐 顯示所有股票連結":
    st.info("💡 點擊股票代號可直接跳轉至 Yahoo 股市頁面")
    
    # 排序股票
    sorted_stocks = sorted(db.items(), key=lambda x: x[0])
    
    # 人性化漂亮列表
    st.markdown('<div class="stock-list">', unsafe_allow_html=True)
    for sid, name in sorted_stocks:
        st.markdown(f'<div>· <a target="_blank" href="https://tw.stock.yahoo.com/quote/{sid.split(".")[0]}"><span class="symbol">{sid.split(".")[0]}</span>{name}</a></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

elif run:
    is_manual = ("手動" in mode and sid_in.strip() != "")
    if is_manual:
        targets = [(f"{sid_in.upper()}.TW", db.get(f"{sid_in.upper()}.TW", "搜尋標的")),
                   (f"{sid_in.upper()}.TWO", db.get(f"{sid_in.upper()}.TWO", "搜尋標的"))]
    else:
        targets = list(db.items())

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as exe:
        futures = {exe.submit(get_stock_data, s): (s, n) for s, n in targets}
        for f in concurrent.futures.as_completed(futures):
            s, n = futures[f]
            df = f.result()
            res = analyze(df, conf)
            if res and (is_manual or (res["labels"] and res["vol"] >= min_v)):
                res.update({"sid": s, "name": n, "df": df})
                results.append(res)

    results.sort(key=lambda x: len(x["labels"]), reverse=True)

    if not results:
        st.info("🔍 目前沒有符合篩選條件的標的")

    for item in results:
        clean_sid = item['sid'].split('.')[0]
        badge_html = ' '.join([f'<span class="badge {"bg-vol" if "爆量" in t else "bg-pattern"}">{t}</span>' for t in item['labels']])
        if not badge_html:
            badge_html = '<span class="badge bg-none">🔘 一般走勢</span>'

        st.markdown(f"""
        <div class="stock-card">
            <span class="card-vol">成交量 {item['vol']} 張</span>
            <a class="card-id" target="_blank" href="https://tw.stock.yahoo.com/quote/{clean_sid}">🔗 {clean_sid} {item['name']}</a><br>
            {badge_html}
        </div>
        """, unsafe_allow_html=True)

        with st.expander("📈 展開技術形態圖表"):
            d = item["df"].tail(30)
            sh, ih, sl, il, x_reg = item["lines"]
            fig = make_subplots(rows=1, cols=1)
            fig.add_candlestick(x=d.index, open=d["Open"], high=d["High"], low=d["Low"], close=d["Close"], name="K線")
            p = d.tail(15)
            fig.add_scatter(x=p.index, y=sh * x_reg + ih, line=dict(dash="dash", color="#f56565", width=1.5), name="阻力")
            fig.add_scatter(x=p.index, y=sl * x_reg + il, line=dict(dash="dash", color="#667eea", width=1.5), name="支撐")
            fig.update_layout(
                height=400, xaxis_rangeslider_visible=False, showlegend=False,
                margin=dict(t=10, b=10, l=10, r=10),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(248, 249, 250, 0.5)"
            )
            st.plotly_chart(fig, use_container_width=True, key=f"f_{item['sid']}")
else:
    st.info("👈 請選擇操作模式並點擊掃描")
