import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import re
import time
import plotly.graph_objects as go
from scipy.stats import linregress
from bs4 import BeautifulSoup

# --- 1. 視覺 UI 配置 (旗艦漸層介面) ---
st.set_page_config(page_title="台股 Pro-X 旗艦版", layout="wide")

st.markdown("""
    <style>
    /* 全域漸層背景 */
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        color: #2d3436;
    }

    /* 側邊欄玻璃擬態 */
    section[data-testid="stSidebar"] {
        background: rgba(255, 255, 255, 0.6) !important;
        backdrop-filter: blur(15px);
        border-right: 1px solid rgba(255, 255, 255, 0.3);
    }

    /* 玻璃擬態質感卡片 */
    .stock-card {
        background: rgba(255, 255, 255, 0.7);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.4);
        padding: 20px;
        border-radius: 15px;
        margin-bottom: 20px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
        transition: transform 0.3s ease;
    }
    .stock-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 25px rgba(0,0,0,0.1);
    }

    /* 狀態標籤 */
    .tag {
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 700;
        text-transform: uppercase;
    }
    .tag-breakout { background: #ff7675; color: white; }
    .tag-consolidate { background: #55efc4; color: #00b894; }

    /* 隱藏預設介面字樣 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)


# --- 2. 靜默加載數據 (隱藏 Running get_total_market) ---
@st.cache_data(ttl=3600, show_spinner=False)
def get_total_market_silent():
    codes = {}
    try:
        url = "https://tw.stock.yahoo.com/class"
        res = requests.get(url, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        links = soup.find_all("a", href=re.compile(r"class-quote\?sectorId=\d+"))[:40]
        for link in links:
            cat_url = "https://tw.stock.yahoo.com" + link['href']
            r = requests.get(cat_url, timeout=5)
            s_soup = BeautifulSoup(r.text, "html.parser")
            items = s_soup.find_all("li", class_="List(n)")
            for li in items:
                c = li.find("span", string=re.compile(r"\d{4}\.(TW|TWO)"))
                n = li.find("div", class_="Lh(20px) Fw(600) Fz(16px) Ell")
                if c and n: codes[c.text.strip()] = n.text.strip()
    except:
        pass
    return codes


# --- 3. 形態偵測引擎 ---
def detect_12_patterns(df, selected):
    recent = df.tail(30)
    x = np.arange(len(recent))
    h, l, c = recent['High'].values.flatten(), recent['Low'].values.flatten(), recent['Close'].values.flatten()
    sh, ih, _, _, _ = linregress(x, h)
    sl, il, _, _, _ = linregress(x, l)

    match = None
    if "三角系" in selected:
        if sh < -0.01 and sl > 0.01:
            match = ("對稱三角形", (sh, ih, sl, il), "⏳ 形態收斂")
        elif abs(sh) < 0.005 and sl > 0.01:
            match = ("上升三角形", (sh, ih, sl, il), "🚀 蓄勢待發")

    if "旗箱系" in selected and not match:
        if abs(sh - sl) < 0.008 and abs(sh) < 0.005:
            match = ("矩形箱型", (sh, ih, sl, il), "📦 區間整理")

    # 若無特定形態則返回基本線段
    if not match:
        match = ("走勢觀察", (sh, ih, sl, il), "📊 數據同步")
    return match


# --- 4. 側邊欄：決策中心 (新增搜尋與選單) ---
with st.sidebar:
    st.markdown("<h1 style='font-size: 24px;'>🎯 決策中心</h1>", unsafe_allow_html=True)

    # 功能一：個股搜尋與下拉
    st.write("### 🔍 個股快查")
    search_input = st.text_input("輸入股票代號", placeholder="例如: 2330")

    pop_list = ["請選擇...", "2330 台積電", "2317 鴻海", "2454 聯發科", "2603 長榮", "8046 南電"]
    selected_pop = st.selectbox("熱門觀察清單", pop_list)

    st.divider()

    # 功能二：全市場形態設定
    st.write("### 🧪 全市場形態偵測")
    p1 = st.checkbox("三角系 (對稱/擴散/下降)", value=True)
    p2 = st.checkbox("旗箱系 (矩形/上升旗)", value=False)
    p3 = st.checkbox("反轉系 (M頭/頭肩頂/倒V)", value=False)

    sel_patterns = []
    if p1: sel_patterns.append("三角系")
    if p2: sel_patterns.append("旗箱系")
    if p3: sel_patterns.append("反轉系")

    st.write("### ⚙️ 進階篩選器")
    scan_scope = st.radio("掃描量級", ["快速 (Top 100)", "全市場 (1700+)", "低價股特搜"])
    min_v = st.number_input("最低成交量 (張)", value=1000)
    ma_on = st.toggle("多頭排列 (站上 20MA)", value=True)

    st.divider()
    run_btn = st.button("🚀 開始深度掃描", use_container_width=True, type="primary")

# --- 5. 主畫面執行邏輯 ---
st.markdown("## 📈 台股 Pro-X 形態大師")
st.markdown("---")

# 判斷目標股票
target_sid = None
if search_input:
    target_sid = f"{search_input}.TW" if "." not in search_input else search_input
elif selected_pop != "請選擇...":
    target_sid = f"{selected_pop.split(' ')[0]}.TW"

if target_sid or run_btn:
    # 動態執行示意
    with st.status("🔍 正在初始化深度數據同步邏輯...", expanded=True) as status_box:
        results = []

        # 情況 A: 單股分析
        if target_sid:
            status_box.update(label=f"🔄 個股數據分析中: {target_sid}", state="running")
            try:
                df = yf.download(target_sid, period="60d", interval="1d", progress=False)
                if not df.empty:
                    res = detect_12_patterns(df, ["三角系", "旗箱系"])
                    results.append({"id": target_sid, "name": "個股快查", "price": df['Close'].iloc[-1].values[0],
                                    "vol": int(df['Volume'].tail(1).values[0] / 1000), "pt_name": res[0],
                                    "status": res[2], "lines": res[1], "df": df.tail(30)})
                else:
                    st.warning(f"找不到代號 {target_sid}")
            except:
                pass

        # 情況 B: 全市場掃描
        elif run_btn:
            market = get_total_market_silent()
            targets = list(market.items())
            if scan_scope == "快速 (Top 100)": targets = targets[:100]

            prog = st.progress(0)
            for i, (sid, sname) in enumerate(targets):
                status_box.update(label=f"🔄 全市場掃描中: {sid} ({i + 1}/{len(targets)})", state="running")
                try:
                    df = yf.download(sid, period="60d", interval="1d", progress=False)
                    if df.empty or len(df) < 30: continue

                    cur_p = df['Close'].iloc[-1].values[0]
                    v_avg = df['Volume'].tail(5).mean().values[0] / 1000
                    if v_avg < min_v: continue
                    if ma_on and cur_p < df['Close'].rolling(20).mean().iloc[-1].values[0]: continue

                    res = detect_12_patterns(df, sel_patterns)
                    if "觀察" not in res[0]:
                        results.append({"id": sid, "name": sname, "price": cur_p, "vol": int(v_avg),
                                        "pt_name": res[0], "status": res[2], "lines": res[1], "df": df.tail(30)})
                except:
                    continue
                prog.progress((i + 1) / len(targets))

        status_box.update(label="✅ 分析完成！", state="complete", expanded=False)

    st.session_state.scan_cache = results

# --- 6. 結果可視化呈現 ---
if st.session_state.get('scan_cache'):
    cols = st.columns(2)
    for idx, item in enumerate(st.session_state.scan_cache):
        with cols[idx % 2]:
            st.markdown(f"""
            <div class="stock-card">
                <div style="display:flex; justify-content:space-between;">
                    <span style="font-size:20px; font-weight:800; color:#2d3436;">{item['id']} {item['name']}</span>
                    <span class="tag tag-breakout">{item['status']}</span>
                </div>
                <div style="margin-top:10px; font-size:14px; color:#636e72;">
                    現價：{item['price']:.2f} | 均量：{item['vol']}張 | 形態：{item['pt_name']}
                </div>
            </div>
            """, unsafe_allow_html=True)

            fig = go.Figure()
            d = item['df']
            sh, ih, sl, il = item['lines']
            fig.add_trace(
                go.Candlestick(x=d.index, open=d['Open'], high=d['High'], low=d['Low'], close=d['Close'], name="K線"))
            xv = np.arange(len(d))
            fig.add_trace(
                go.Scatter(x=d.index, y=sh * xv + ih, line=dict(color='#ff7675', width=2, dash='dot'), name="壓力"))
            fig.add_trace(
                go.Scatter(x=d.index, y=sl * xv + il, line=dict(color='#55efc4', width=2, dash='dot'), name="支撐"))
            fig.update_layout(height=380, template="plotly_white", xaxis_rangeslider_visible=False,
                              margin=dict(l=5, r=5, t=5, b=5), paper_bgcolor='rgba(0,0,0,0)',
                              plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)
else:
    st.info("💡 操作指南：可在側邊欄『個股快查』輸入代號，或調整參數點擊『開始深度掃描』分析全市場。")
