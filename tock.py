# =========================================================
# 台股 Pro-X 形態大師 v3.0（完整最終版）
# 自動監控 + 手動掃描 + 三角 / 旗箱 / 反轉
# 形態與成交量完全解耦
# =========================================================

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

# =========================================================
# [ 1. 股票代碼引擎 ]
# =========================================================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_tw_codes():
    codes = {}
    try:
        for sid in range(1, 34):
            for ex in ["TAI", "TWO"]:
                url = f"https://tw.stock.yahoo.com/class-quote?sectorId={sid}&exchange={ex}"
                r = requests.get(url, timeout=5)
                soup = BeautifulSoup(r.text, "html.parser")
                for li in soup.find_all("li", class_="List(n)"):
                    code = li.find("span", string=re.compile(r"\d{4}\.(TW|TWO)"))
                    name = li.find("div", class_="Lh(20px) Fw(600) Fz(16px) Ell")
                    if code and name:
                        codes[code.text.strip()] = name.text.strip()
    except:
        pass
    return codes


# =========================================================
# [ 2. 成交量模組（獨立） ]
# =========================================================
def analyze_volume(df):
    v = df["Volume"].values.flatten()
    return {
        "boom": v[-1] > np.mean(v[-6:-1]) * 1.5,
        "shrink": np.mean(v[-5:]) < np.mean(v[-15:-5])
    }


# =========================================================
# [ 3. 形態模組 ]
# =========================================================
def detect_triangle(df):
    d = df.tail(30)
    x = np.arange(len(d))
    h, l, c = d["High"].values, d["Low"].values, d["Close"].values

    sh, ih, _, _, _ = linregress(x, h)
    sl, il, _, _, _ = linregress(x, l)

    return {
        "found": sh < -0.01 and sl > 0.01,
        "break": c[-1] > (sh * 29 + ih),
        "lines": (sh, ih, sl, il)
    }


def detect_box(df):
    d = df.tail(30)
    x = np.arange(len(d))
    h, l = d["High"].values, d["Low"].values
    sh, _, _, _, _ = linregress(x, h)
    sl, _, _, _, _ = linregress(x, l)
    return abs(sh) < 0.01 and abs(sl) < 0.01


def detect_flag(df):
    d = df.tail(30)
    x = np.arange(len(d))
    h, l = d["High"].values, d["Low"].values
    sh, _, _, _, _ = linregress(x, h)
    sl, _, _, _, _ = linregress(x, l)
    return sh < 0 and abs(sl) < 0.01


def detect_reversal(df):
    d = df.tail(30)
    c = d["Close"].values
    left = np.max(c[:10])
    mid = np.max(c[10:20])
    right = np.max(c[20:])
    return mid > left and mid > right and right < left


# =========================================================
# [ 4. 綜合分析核心 ]
# =========================================================
def analyze_all(df, m_tri, m_box, m_rev):
    labels = []
    lines = None

    vol = analyze_volume(df)

    if m_tri:
        tri = detect_triangle(df)
        if tri["found"]:
            labels.append("📐 三角整理")
            lines = tri["lines"]
            if tri["break"]:
                labels.append("⬆️ 三角突破")

    if m_box:
        if detect_box(df):
            labels.append("📦 箱型整理")
        if detect_flag(df):
            labels.append("🏳️ 旗形整理")

    if m_rev:
        if detect_reversal(df):
            labels.append("🔄 反轉形態")

    if vol["boom"]:
        labels.append("🚀 爆量")
    if vol["shrink"]:
        labels.append("🔇 量縮")

    return labels, lines, vol


# =========================================================
# [ 5. Streamlit UI ]
# =========================================================
st.set_page_config(page_title="台股 Pro-X 形態大師", layout="wide")

st.markdown("## 📈 台股 Pro-X 形態大師（完整版）")

with st.sidebar:
    st.markdown("### 📡 自動監控")
    display_modes = st.multiselect(
        "顯示條件",
        [
            "📐 三角",
            "📦 旗箱",
            "🔄 反轉",
            "🚀 爆量",
            "📐+🚀 突破"
        ],
        default=["📐 三角", "🚀 爆量"]
    )

    auto_monitor = st.toggle("開啟自動監控", True)
    if auto_monitor:
        st_autorefresh(interval=300000, key="auto")

    st.divider()

    st.markdown("### 🔍 手動掃描")
    m1 = st.checkbox("📐 三角系", True)
    m2 = st.checkbox("📦 旗箱系", False)
    m3 = st.checkbox("🔄 反轉系", False)

    scan_limit = st.slider("掃描數量", 10, 2000, 1000)
    min_vol = st.number_input("最低成交量(張)", 500, 50000, 1000)

    manual_run = st.button("🚀 開始掃描", use_container_width=True)


# =========================================================
# [ 6. 掃描主流程 ]
# =========================================================
run = auto_monitor or manual_run

if run:
    with st.status("掃描中...", expanded=True) as status:
        results = []
        market = fetch_tw_codes()
        targets = list(market.items())[:scan_limit]

        for i, (sid, name) in enumerate(targets):
            status.update(label=f"{sid} {name} ({i+1}/{len(targets)})")
            try:
                df = yf.download(sid, period="60d", progress=False)
                if df.empty or len(df) < 30:
                    continue

                vol = int(df["Volume"].iloc[-1].values[0] / 1000)
                if vol < min_vol:
                    continue

                labels, lines, vstat = analyze_all(df, m1, m2, m3)

                show = False
                if auto_monitor:
                    if "📐 三角" in display_modes and any("三角" in l for l in labels):
                        show = True
                    if "📦 旗箱" in display_modes and any(x in l for x in ["箱型", "旗形"] for l in labels):
                        show = True
                    if "🔄 反轉" in display_modes and any("反轉" in l for l in labels):
                        show = True
                    if "🚀 爆量" in display_modes and vstat["boom"]:
                        show = True
                    if "📐+🚀 突破" in display_modes and vstat["boom"] and any("突破" in l for l in labels):
                        show = True
                else:
                    show = bool(labels)

                if show:
                    results.append({
                        "sid": sid,
                        "name": name,
                        "df": df.tail(30),
                        "labels": labels,
                        "lines": lines,
                        "price": df["Close"].iloc[-1].values[0],
                        "vol": vol
                    })
            except:
                continue

        status.update(label="完成", state="complete", expanded=False)


# =========================================================
# [ 7. 結果顯示 ]
# =========================================================
if run:
    if not results:
        st.info("目前沒有符合條件的標的")
    else:
        cols = st.columns(2)
        for i, r in enumerate(results):
            with cols[i % 2]:
                st.markdown(
                    f"**{r['sid']} {r['name']}**  \n"
                    f"現價：{r['price']:.2f}｜成交：{r['vol']}張  \n"
                    f"{' / '.join(r['labels'])}"
                )

                fig = go.Figure(
                    data=[go.Candlestick(
                        x=r["df"].index,
                        open=r["df"]["Open"],
                        high=r["df"]["High"],
                        low=r["df"]["Low"],
                        close=r["df"]["Close"]
                    )]
                )

                if r["lines"]:
                    sh, ih, sl, il = r["lines"]
                    x = np.arange(len(r["df"]))
                    fig.add_trace(go.Scatter(
                        x=r["df"].index,
                        y=sh * x + ih,
                        line=dict(dash="dot"),
                        name="壓力線"
                    ))
                    fig.add_trace(go.Scatter(
                        x=r["df"].index,
                        y=sl * x + il,
                        line=dict(dash="dot"),
                        name="支撐線"
                    ))

                fig.update_layout(
                    height=300,
                    xaxis_rangeslider_visible=False,
                    margin=dict(l=0, r=0, t=20, b=0)
                )
                st.plotly_chart(fig, use_container_width=True)
