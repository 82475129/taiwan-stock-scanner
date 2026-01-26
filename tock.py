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
# 0. 狀態鎖定與資料庫載入
# ==========================================
if "current_mode" not in st.session_state:
    st.session_state.current_mode = "⚡ 今日即時監控 (自動)"

DB_FILE = "taiwan_electronic_stocks.json"

@st.cache_data(ttl=3600)
def load_full_db():
    base = {
        "2330.TW": {"name": "台積電", "cat": "電子"},
        "2454.TW": {"name": "聯發科", "cat": "電子"},
        "2317.TW": {"name": "鴻海", "cat": "電子"},
        "3045.TW": {"name": "台灣大", "cat": "電子"}
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
        if df.empty: return pd.DataFrame()
        
        # ✨ 解決 DuplicateError：處理 MultiIndex 並刪除重複名稱的欄位
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # 只保留第一次出現的欄位 (例如重複的 Open, High 等)
        df = df.loc[:, ~df.columns.duplicated()]
        
        # 強制選取必要欄位，確保資料純淨
        required = ["Open", "High", "Low", "Close", "Volume"]
        df = df[required].dropna()
        return df
    except:
        return pd.DataFrame()

# ==========================================
# 1. 形態分析邏輯
# ==========================================
def analyze_patterns(df, config, days=15):
    if df is None or df.empty or len(df) < days:
        return None
    
    d = df.tail(days)
    try:
        # 確保提取為 1D 陣列
        h = d["High"].values.flatten().astype(float)
        l = d["Low"].values.flatten().astype(float)
        v = d["Volume"].values.flatten().astype(float)
        x = np.arange(len(h))
        
        # 線性回歸計算
        sh, ih, *_ = linregress(x, h)
        sl, il, *_ = linregress(x, l)
    except:
        return None

    v_mean = np.mean(v[:-1]) if len(v) >= 2 else np.mean(v)
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
        "vol": int(v[-1] // 1000)
    }

# ==========================================
# 2. UI 樣式設定
# ==========================================
st.set_page_config(page_title="台股 Pro-X 形態大師", layout="wide")
st.markdown("""
<style>
.stApp { background-color: #f4f7f6; }
.stock-card {
    background: white; padding: 18px; border-radius: 12px;
    margin-bottom: 12px; border-left: 6px solid #6c5ce7;
    box-shadow: 0 2px 5px rgba(0,0,0,0.05);
}
.card-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
.sid-link { font-weight:bold; color:#6c5ce7; text-decoration:none; font-size:1.1rem; }
.vol-info { color:#636e72; font-size:0.85rem; background:#f1f2f6; padding:3px 8px; border-radius:5px; }
.badge { padding:4px 10px; border-radius:6px; font-size:0.75rem; color:white; margin-right:5px; font-weight:600; }
.badge-tri { background:#6c5ce7; }
.badge-box { background:#2d3436; }
.badge-vol { background:#d63031; }
.badge-none { background:#b2bec3; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 側邊欄控制
# ==========================================
db = load_full_db()
modes = ["⚡ 今日即時監控 (自動)", "⏳ 歷史形態搜尋 (手動)", "🌐 顯示所有股票連結"]

with st.sidebar:
    st.title("🎯 形態大師控制台")
    mode = st.radio("選擇功能模式", modes, index=modes.index(st.session_state.current_mode))
    st.session_state.current_mode = mode
    st.divider()

    if mode == "⚡ 今日即時監控 (自動)":
        st_autorefresh(interval=300000, key="auto")
        current_config = {
            "tri": st.checkbox("📐 三角收斂", True),
            "box": st.checkbox("📦 旗箱整理", True),
            "vol": st.checkbox("🚀 今日爆量", True)
        }
        t_min_v = st.number_input("最低量 (張)", value=300)
        run_now = True
    elif mode == "⏳ 歷史形態搜尋 (手動)":
        h_sid = st.text_input("輸入個股代號", placeholder="例如: 2330")
        current_config = {
            "tri": st.checkbox("📐 三角收斂", True),
            "box": st.checkbox("📦 旗箱整理", True),
            "vol": st.checkbox("🚀 今日爆量", True)
        }
        h_min_v = st.number_input("最低量 (張)", value=100)
        run_now = st.button("🚀 開始掃描", use_container_width=True)
    else:
        run_now = False

# ==========================================
# 4. 主畫面顯示
# ==========================================
if mode == "🌐 顯示所有股票連結":
    for sid, info in db.items():
        name = info['name'] if isinstance(info, dict) else info
        clean = sid.split(".")[0]
        st.markdown(f'· <a class="sid-link" target="_blank" href="https://tw.stock.yahoo.com/quote/{clean}">{clean} {name}</a>', unsafe_allow_html=True)

elif run_now:
    is_specific = (mode == "⏳ 歷史形態搜尋 (手動)" and h_sid.strip() != "")
    targets = [(f"{h_sid.upper()}.TW", "個股"), (f"{h_sid.upper()}.TWO", "個股")] if is_specific else list(db.items())
    
    mv_limit = t_min_v if mode.startswith("⚡") else h_min_v
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as exe:
        # ✨ 修正：解構 db 內容，確保拿到字串名稱
        future_to_sid = {}
        for sid, info in (targets if not is_specific else targets):
            name = info['name'] if isinstance(info, dict) else info
            future_to_sid[exe.submit(get_stock_data, sid)] = (sid, name)
            
        for f in concurrent.futures.as_completed(future_to_sid):
            sid, name = future_to_sid[f]
            df = f.result()
            res = analyze_patterns(df, current_config)
            
            if res and (is_specific or (res["labels"] and res["vol"] >= mv_limit)):
                res.update({"sid": sid, "name": name, "df": df})
                results.append(res)

    if not results:
        st.info("🔍 尚未發現符合條件的股票")

    for item in results:
        clean = item["sid"].split(".")[0]
        badges = "".join(f'<span class="badge {b["class"]}">{b["text"]}</span>' for b in item["labels"]) if item["labels"] else '<span class="badge badge-none">🔘 一般走勢</span>'

        # ✨ 修正後的卡片：移除股價，顯示名稱
        st.markdown(f"""
        <div class="stock-card">
            <div class="card-header">
                <a class="sid-link" target="_blank" href="https://tw.stock.yahoo.com/quote/{clean}">🔗 {clean} {item["name"]}</a>
                <span class="vol-info">成交 {item["vol"]} 張</span>
            </div>
            <div>{badges}</div>
        </div>
        """, unsafe_allow_html=True)

        with st.expander("📈 展開形態圖表"):
            d = item["df"].tail(30)
            sh, ih, sl, il, x_reg = item["lines"]
            
            fig = make_subplots(rows=1, cols=1)
            fig.add_candlestick(x=d.index, open=d["Open"], high=d["High"], low=d["Low"], close=d["Close"], name="K線")
            
            p = d.tail(15)
            fig.add_scatter(x=p.index, y=sh * x_reg + ih, line=dict(dash="dash", color="#d63031"), name="壓力線")
            fig.add_scatter(x=p.index, y=sl * x_reg + il, line=dict(dash="dot", color="#6c5ce7"), name="支撐線")
            
            fig.update_layout(height=400, xaxis_rangeslider_visible=False, showlegend=False, margin=dict(t=0, b=0, l=0, r=0))
            # ✨ 修正：使用唯一 key 避免重複元件錯誤
            st.plotly_chart(fig, use_container_width=True, key=f"plotly_{item['sid']}")
else:
    st.info("👈 請由左側功能表開始掃描")
