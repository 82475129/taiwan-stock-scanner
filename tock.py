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
    # 預設基礎資料，若 JSON 檔案不存在時使用
    base = {
        "2330.TW": {"name": "台積電", "cat": "電子"},
        "2454.TW": {"name": "聯發科", "cat": "電子"},
        "2317.TW": {"name": "鴻海", "cat": "電子"},
        "2481.TW": {"name": "強茂", "cat": "電子"}
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
        # 下載最近 45 天數據
        df = yf.download(sid, period="45d", progress=False)
        if df.empty: return pd.DataFrame()
        
        # 處理 yfinance 新版 MultiIndex 欄位結構
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # ✨ 解決 Narwhals DuplicateError：移除重複名稱的欄位
        df = df.loc[:, ~df.columns.duplicated()]
        
        # 強制過濾必要欄位，排除雜訊
        required = ["Open", "High", "Low", "Close", "Volume"]
        df = df[required].dropna()
        return df
    except:
        return pd.DataFrame()

# ==========================================
# 1. 形態分析與回歸邏輯
# ==========================================
def analyze_patterns(df, config, days=15):
    if df is None or df.empty or len(df) < days:
        return None
    
    d = df.tail(days)
    try:
        # 提取數據並轉為 1D 陣列
        h = d["High"].values.flatten().astype(float)
        l = d["Low"].values.flatten().astype(float)
        v = d["Volume"].values.flatten().astype(float)
        x = np.arange(len(h))
        
        # 計算壓力線(High)與支撐線(Low)的斜率
        sh, ih, *_ = linregress(x, h)
        sl, il, *_ = linregress(x, l)
        
        v_mean = np.mean(v[:-1]) if len(v) >= 2 else np.mean(v)
        hits = []
        
        # 標籤邏輯
        if config.get("tri") and sh < -0.003 and sl > 0.003:
            hits.append({"text": "📐三角收斂", "class": "badge-tri"})
        if config.get("box") and abs(sh) < 0.03 and abs(sl) < 0.03:
            hits.append({"text": "📦旗箱整理", "class": "badge-box"})
        if config.get("vol") and v[-1] > v_mean * 1.3:
            hits.append({"text": "🚀今日爆量", "class": "badge-vol"})
            
        return {"labels": hits, "lines": (sh, ih, sl, il, x), "vol": int(v[-1] // 1000)}
    except:
        return None

# ==========================================
# 2. UI 樣式與自定義標題 (科技+動態+專業)
# ==========================================
st.set_page_config(page_title="台股 Pro-X 形態大師", layout="wide")

# 頂部視覺化標題區塊
st.markdown("""
<div style="text-align: center; padding: 25px; background: linear-gradient(135deg, #6c5ce7 0%, #a29bfe 100%); border-radius: 15px; margin-bottom: 25px; color: white; box-shadow: 0 4px 15px rgba(108, 92, 231, 0.2);">
    <h1 style="margin: 0; font-size: 2.2rem; font-weight: 800; letter-spacing: 1px;">🎯 台股 Pro-X：即時形態 AI 偵測系統</h1>
    <p style="margin: 10px 0 0 0; opacity: 0.9; font-size: 1.1rem; font-weight: 300;">⚡ 自動秒級掃描 · 📐 核心形態捕捉 · 🚀 成交量異動追蹤</p>
</div>
<style>
.stApp { background-color: #f8f9fa; }
.stock-card {
    background: white; padding: 20px; border-radius: 12px;
    margin-bottom: 12px; border-left: 6px solid #6c5ce7;
    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}
.card-header { display:flex; justify-content:space-between; align-items:center; }
.sid-link { font-weight:bold; color:#6c5ce7; text-decoration:none; font-size:1.2rem; }
.vol-info { color:#636e72; font-size:0.9rem; background:#f1f2f6; padding:4px 10px; border-radius:6px; }
.badge { padding:5px 12px; border-radius:6px; font-size:0.8rem; color:white; margin-right:6px; font-weight:600; display:inline-block; margin-top:5px; }
.badge-tri { background:#6c5ce7; }
.badge-box { background:#2d3436; }
.badge-vol { background:#d63031; }
.badge-none { background:#b2bec3; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 側邊欄控制 (保留原始介面)
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
        h_sid = st.text_input("代號 (輸入即強制顯示圖表)", placeholder="例如: 2330")
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
# 4. 主畫面邏輯與渲染
# ==========================================
if mode == "🌐 顯示所有股票連結":
    for sid, info in db.items():
        name = info['name'] if isinstance(info, dict) else info
        clean = sid.split(".")[0]
        st.markdown(f'· <a class="sid-link" target="_blank" href="https://tw.stock.yahoo.com/quote/{clean}">{clean} {name}</a>', unsafe_allow_html=True)

elif run_now:
    is_specific = (mode == "⏳ 歷史形態搜尋 (手動)" and h_sid.strip() != "")
    
    if is_specific:
        sid_tw = f"{h_sid.upper()}.TW"
        sid_two = f"{h_sid.upper()}.TWO"
        # 搜尋時自動比對名稱
        def find_name(s):
            info = db.get(s)
            return (info['name'] if isinstance(info, dict) else info) if info else None
        
        actual_name = find_name(sid_tw) or find_name(sid_two) or "個股"
        targets = [(sid_tw, actual_name), (sid_two, actual_name)]
    else:
        targets = []
        for sid, info in db.items():
            name = info['name'] if isinstance(info, dict) else info
            targets.append((sid, name))
    
    mv_limit = t_min_v if mode.startswith("⚡") else h_min_v
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as exe:
        future_to_sid = {exe.submit(get_stock_data, sid): (sid, name) for sid, name in targets}
        for f in concurrent.futures.as_completed(future_to_sid):
            sid, name = future_to_sid[f]
            df = f.result()
            res = analyze_patterns(df, current_config)
            if res and (is_specific or (res["labels"] and res["vol"] >= mv_limit)):
                res.update({"sid": sid, "name": name, "df": df})
                results.append(res)

    if not results:
        st.info("🔍 尚未發現符合條件的股票。")
    
    # 排序：有形態標籤的排在最前面
    results.sort(key=lambda x: len(x["labels"]), reverse=True)

    for item in results:
        clean = item["sid"].split(".")[0]
        badges = "".join(f'<span class="badge {b["class"]}">{b["text"]}</span>' for b in item["labels"]) if item["labels"] else '<span class="badge badge-none">🔘 一般走勢</span>'

        st.markdown(f"""
        <div class="stock-card">
            <div class="card-header">
                <a class="sid-link" target="_blank" href="https://tw.stock.yahoo.com/quote/{clean}">🔗 {clean} {item["name"]}</a>
                <span class="vol-info">成交 {item["vol"]} 張</span>
            </div>
            <div style="margin-top:10px;">{badges}</div>
        </div>
        """, unsafe_allow_html=True)

        with st.expander("📈 展開形態分析圖表"):
            d = item["df"].tail(30)
            sh, ih, sl, il, x_reg = item["lines"]
            
            fig = make_subplots(rows=1, cols=1)
            fig.add_candlestick(x=d.index, open=d["Open"], high=d["High"], low=d["Low"], close=d["Close"], name="K線")
            
            # 繪製預測趨勢線 (只顯示最近 15 天)
            p = d.tail(15)
            fig.add_scatter(x=p.index, y=sh * x_reg + ih, line=dict(dash="dash", color="#d63031"), name="壓力線")
            fig.add_scatter(x=p.index, y=sl * x_reg + il, line=dict(dash="dot", color="#6c5ce7"), name="支撐線")
            
            fig.update_layout(
                height=400, 
                xaxis_rangeslider_visible=False, 
                showlegend=False, 
                margin=dict(t=0, b=0, l=0, r=0),
                hovermode="x unified"
            )
            # ✨ 使用唯一 key 避免重複渲染錯誤
            st.plotly_chart(fig, use_container_width=True, key=f"final_chart_{item['sid']}")
else:
    st.info("👈 請從左側控制台選擇模式並開始掃描。")
