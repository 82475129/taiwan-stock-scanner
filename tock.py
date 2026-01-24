import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import re
import plotly.graph_objects as go
from scipy.stats import linregress
from bs4 import BeautifulSoup
from streamlit_autorefresh import st_autorefresh


# --- [ 1. 隱藏式數據引擎 ] ---
@st.cache_data(ttl=3600, show_spinner=False)
def _engine_core_fetch():
    codes = {}
    try:
        for s_id in range(1, 34):
            for ex in ["TAI", "TWO"]:
                r = requests.get(
                    f"https://tw.stock.yahoo.com/class-quote?sectorId={s_id}&exchange={ex}",
                    timeout=5
                )
                soup = BeautifulSoup(r.text, "html.parser")
                for li in soup.find_all("li", class_="List(n)"):
                    sid = li.find("span", string=re.compile(r"\d{4}\.(TW|TWO)"))
                    sn = li.find("div", class_="Lh(20px) Fw(600) Fz(16px) Ell")
                    if sid and sn:
                        codes[sid.text.strip()] = sn.text.strip()
    except:
        pass
    return codes


# --- [ 2. 形態分析核心（完整） ] ---
def _analyze_pattern(df, use_tri=True, use_flag=False, use_rev=False):
    d = df.tail(30)
    x = np.arange(len(d))

    h = d['High'].values.flatten()
    l = d['Low'].values.flatten()
    c = d['Close'].values.flatten()
    v = d['Volume'].values.flatten()

    sh, ih, _, _, _ = linregress(x, h)
    sl, il, _, _, _ = linregress(x, l)

    labels = []

    # 爆量（獨立）
    is_vol = v[-1] > (v[-6:-1].mean() * 1.5)
    if is_vol:
        labels.append("🚀 爆量")

    # 三角形態
    is_tri = False
    if use_tri:
        is_tri = sh < -0.01 and sl > 0.01 and c[-1] > (sh * 29 + ih)
        if is_tri:
            labels.append("📐 三角收斂")

    # 旗箱 / 矩形
    is_flag = False
    if use_flag:
        price_range = np.max(h) - np.min(l)
        slope_sum = abs(sh) + abs(sl)
        is_flag = slope_sum < 0.02 and price_range / np.mean(c) < 0.06
        if is_flag:
            labels.append("📦 旗箱整理")

    # 反轉（M 頭 / 倒 V 簡化）
    is_rev = False
    if use_rev:
        mid = len(c) // 2
        left_high = np.max(c[:mid])
        right_high = np.max(c[mid:])
        is_rev = abs(left_high - right_high) / left_high < 0.03 and c[-1] < left_high * 0.97
        if is_rev:
            labels.append("🔄 反轉型")

    return (
        ", ".join(labels) if labels else None,
        (sh, ih, sl, il),
        is_tri,
        is_flag,
        is_rev,
        is_vol
    )


# --- [ 3. UI 樣式 ] ---
st.set_page_config(page_title="台股 Pro-X 形態大師", layout="wide")
st.markdown("""
<style>
.stApp { background: #f0f2f6; }
section[data-testid="stSidebar"] { background-color: #f8f9fa !important; border-right: 1px solid #e9ecef; }
.monitor-on { background-color: #d4edda; color: #155724; padding: 15px; border-radius: 8px; text-align: center; font-weight: bold; margin-bottom: 20px; border: 1px solid #c3e6cb; }
.stock-card { background: white; padding: 20px; border-radius: 10px; border: 1px solid #dee2e6; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
.tag-found { background-color: #ff4b4b; color: white; padding: 2px 10px; border-radius: 15px; font-size: 12px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)


# --- [ 4. Sidebar（完全不動） ] ---
with st.sidebar:
    st.markdown("## 🎯 決策中心")

    display_modes = st.multiselect(
        "自動監控要顯示的結果類型（可複選）",
        [
            "📐 只顯示三角形態（不管有沒有爆量）",
            "🚀 只顯示爆量突破（不管有沒有三角）",
            "🔺🚀 同時滿足三角+爆量才顯示",
            "📐或🚀 只要有任一就顯示（或的關係）"
        ],
        default=[
            "📐 只顯示三角形態（不管有沒有爆量）",
            "🚀 只顯示爆量突破（不管有沒有三角）"
        ]
    )

    auto_monitor = st.toggle("開啟自動監控", value=True)

    if auto_monitor:
        st_autorefresh(interval=300000, key="auto")

    with st.form("manual_scan_form"):
        input_sid = st.text_input("輸入股票代號")
        pop_sel = st.multiselect("熱門觀察清單", ["2330 台積電", "2317 鴻海", "2603 長榮", "2454 聯發科"])

        m1 = st.checkbox("三角系 (對稱/擴散/下降)", value=True)
        m2 = st.checkbox("旗箱系 (矩形/上升旗)", value=False)
        m3 = st.checkbox("反轉系 (M頭/頭肩頂/倒V)", value=False)

        scan_limit = st.slider("掃描標的數", 10, 2000, 2000)
        min_v = st.number_input("最低成交量 (張)", value=1000)
        ma_on = st.toggle("多頭排列 (站上 20MA)", value=True)

        manual_btn = st.form_submit_button("🚀 開始深度掃描", use_container_width=True)


# --- [ 5. 主執行 ] ---
run_scan = auto_monitor or manual_btn or input_sid or pop_sel

if run_scan:
    results = []
    market = _engine_core_fetch()

    manual_targets = []
    if input_sid:
        manual_targets.append(f"{input_sid}.TW")
    for p in pop_sel:
        manual_targets.append(f"{p.split()[0]}.TW")

    for sid, name in list(market.items())[:scan_limit]:
        try:
            df = yf.download(sid, period="60d", progress=False)
            if df.empty or len(df) < 30:
                continue

            vol = int(df['Volume'].iloc[-1].values[0] / 1000)
            price = df['Close'].iloc[-1].values[0]

            if sid not in manual_targets:
                if vol < min_v:
                    continue
                if ma_on and price < df['Close'].rolling(20).mean().iloc[-1].values[0]:
                    continue

            res, lines, has_tri, has_flag, has_rev, has_vol = _analyze_pattern(
                df, m1, m2, m3
            )

            show = (
                (m1 and has_tri) or
                (m2 and has_flag) or
                (m3 and has_rev) or
                sid in manual_targets
            )

            if show:
                results.append({
                    "id": sid,
                    "name": name,
                    "df": df.tail(30),
                    "lines": lines,
                    "res": res or "觀察",
                    "price": price,
                    "vol": vol
                })
        except:
            continue

    if results:
        cols = st.columns(2)
        for i, r in enumerate(results):
            with cols[i % 2]:
                st.markdown(
                    f"<div class='stock-card'><b>{r['id']} {r['name']}</b>"
                    f"<span class='tag-found'>{r['res']}</span><br>"
                    f"現價：{r['price']:.2f} ｜ 成交：{r['vol']} 張</div>",
                    unsafe_allow_html=True
                )

                d = r["df"]
                sh, ih, sl, il = r["lines"]
                x = np.arange(len(d))

                fig = go.Figure([
                    go.Candlestick(
                        x=d.index,
                        open=d['Open'],
                        high=d['High'],
                        low=d['Low'],
                        close=d['Close']
                    ),
                    go.Scatter(x=d.index, y=sh*x+ih, name="壓力線"),
                    go.Scatter(x=d.index, y=sl*x+il, name="支撐線")
                ])

                fig.update_layout(height=300, xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("目前沒有符合條件的標的")
