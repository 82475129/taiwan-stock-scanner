import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import re
import time
import concurrent.futures
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.stats import linregress
from bs4 import BeautifulSoup
from streamlit_autorefresh import st_autorefresh
from datetime import datetime


# ==========================================
# 1. 核心數據引擎 (產業分類爬蟲)
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False)
def _engine_core_fetch_database():
    """從 Yahoo 財經爬取產業結構，支援電子、食品及其他分類"""
    ELECTRONIC_IDS = {1, 2, 4, 13, 24, 25, 26, 27, 28, 29, 30, 31}
    FOOD_IDS = {3}
    full_db = {}
    try:
        for sector_id in range(1, 34):
            cat_label = "電子" if sector_id in ELECTRONIC_IDS else ("食品" if sector_id in FOOD_IDS else "其他")
            for exchange in ["TAI", "TWO"]:
                r = requests.get(f"https://tw.stock.yahoo.com/class-quote?sectorId={sector_id}&exchange={exchange}",
                                 timeout=10)
                soup = BeautifulSoup(r.text, "html.parser")
                for item in soup.find_all("li", class_="List(n)"):
                    id_span = item.find("span", string=re.compile(r"\d{4}\.(TW|TWO)"))
                    name_div = item.find("div", class_="Lh(20px) Fw(600) Fz(16px) Ell")
                    if id_span and name_div:
                        full_db[id_span.text.strip()] = {"name": name_div.text.strip(), "category": cat_label}
    except:
        pass
    return full_db


# ==========================================
# 2. 形態分析演算法（加強版，讓掃電子更容易有結果）
# ==========================================
def _analyze_pattern_logic(df):
    """計算回歸斜率，偵測三角收斂、旗箱、爆量"""
    try:
        # 使用最近 45 天來判斷（更能捕捉完整整理型態）
        d = df.tail(45).copy()
        x = np.arange(len(d))
        h, l, v = d['High'].values.flatten(), d['Low'].values.flatten(), d['Volume'].values.flatten()
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)

        labels = []

        # 放寬三角收斂條件（斜率更小也能接受）
        is_tri = (sh < -0.0008) and (sl > 0.0008)  # 原: ±0.0015 → 放寬到 ±0.0008

        # 旗型/箱型：斜率更接近水平
        is_box = (abs(sh) < 0.0006) and (abs(sl) < 0.0006)  # 原: 0.001 → 放寬到 0.0006

        # 爆量：建議至少放大 1.6 倍才算有意義
        vol_mean = v[-10:-1].mean()  # 改用前9天平均（更穩定）
        is_vol = v[-1] > (vol_mean * 1.6)  # 原 1.1 → 改成 1.6

        # 接近三角收斂（選用，增加靈敏度）
        is_near_tri = (sh < -0.0004) and (sl > 0.0004) and not is_tri
        if is_near_tri: labels.append("📐 接近三角")

        if is_tri: labels.append("📐 三角收斂")
        if is_box: labels.append("📦 旗箱矩形")
        if is_vol: labels.append("🚀 爆量突破")

        return labels, (sh, ih, sl, il), is_tri, is_box, is_vol
    except:
        return [], (0, 0, 0, 0), False, False, False


# ==========================================
# 3. 介面視覺 CSS
# ==========================================
st.set_page_config(page_title="台股 Pro-X 形態大師", layout="wide")
st.markdown("""
    <style>
    .stApp { background: #f9f9fb; }
    .hero-section { background: white; padding: 25px; border-radius: 15px; text-align: center; border-bottom: 5px solid #6c5ce7; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-bottom: 20px; }
    .stock-card { background: white; padding: 18px; border-radius: 12px; border-left: 8px solid #6c5ce7; margin-top: 15px; box-shadow: 0 4px 8px rgba(0,0,0,0.03); }
    .badge { padding: 4px 10px; border-radius: 5px; font-size: 12px; font-weight: bold; color: white; margin-left: 6px; }
    .badge-tri { background: #6c5ce7; } .badge-vol { background: #ff7675; } .badge-box { background: #2d3436; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 4. 固定首頁標題
# ==========================================
st.markdown(f"""
    <div class="hero-section">
        <h1 style='color: #6c5ce7; margin:0;'>🎯 台股 Pro-X 形態大師</h1>
        <p style='color: #636e72; margin-top:10px;'>專業級大數據掃描系統 | 電子與三角收斂預設監控</p>
        <p style='color: #b2bec3; font-size: 0.8em;'>同步時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
""", unsafe_allow_html=True)

# ==========================================
# 5. 固定側邊欄：手動與自動雙區 (各六個勾選藍)
# ==========================================
with st.sidebar:
    st.header("⚙️ 設定中心")

    # --- A. 自動監控區 ---
    st.subheader("📡 A. 自動監控模式")
    auto_toggle = st.toggle("啟動自動巡航", value=False)
    with st.expander("自動監控勾選藍", expanded=auto_toggle):
        a_elec = st.checkbox("自動-電子類股", value=True)
        a_food = st.checkbox("自動-食品類股", value=False)
        a_other = st.checkbox("自動-其他類股", value=False)
        st.write("---")
        a_tri = st.checkbox("自動-監控三角", value=True)
        a_box = st.checkbox("自動-監控旗箱", value=False)
        a_vol = st.checkbox("自動-監控爆量", value=False)
    if auto_toggle:
        st_autorefresh(interval=300000, key="auto_refresh")

    st.divider()

    # --- B. 手動掃描區 ---
    st.subheader("🚀 B. 手動掃描模式")
    with st.expander("手動掃描勾選藍", expanded=True):
        m_elec = st.checkbox("手動-電子類股", value=True)
        m_food = st.checkbox("手動-食品類股", value=False)
        m_other = st.checkbox("手動-其他類股", value=False)
        st.write("---")
        m_tri = st.checkbox("手動-偵測三角", value=True)
        m_box = st.checkbox("手動-偵測旗箱", value=False)
        m_vol = st.checkbox("手動-偵測爆量", value=False)

    st.divider()
    input_sid = st.text_input("輸入個股代號", placeholder="例如: 2330")
    max_limit = st.slider("掃描上限", 50, 1000, 200)
    min_vol_val = st.number_input("最低張數門檻", value=300)
    btn_manual = st.button("🚀 執行手動掃描", use_container_width=True, type="primary")


# ==========================================
# 6. 分析引擎邏輯（加強版，針對電子降低量能門檻）
# ==========================================
def execute_engine(is_auto_mode):
    if is_auto_mode:
        cats = [c for c, v in {"電子": a_elec, "食品": a_food, "其他": a_other}.items() if v]
        pats = {"tri": a_tri, "box": a_box, "vol": a_vol}
    else:
        cats = [c for c, v in {"電子": m_elec, "食品": m_food, "其他": m_other}.items() if v]
        pats = {"tri": m_tri, "box": m_box, "vol": m_vol}

    if not cats and not input_sid:
        st.warning("⚠️ 請勾選產業類別或輸入代號。")
        return []

    with st.status("🔍 分析引擎運作中...", expanded=True) as status:
        db = _engine_core_fetch_database()
        results = []

        if input_sid:
            sid = input_sid.strip().upper()
            targets = [(f"{sid}.TW", {"name": "查詢標的", "category": "手動"}),
                       (f"{sid}.TWO", {"name": "查詢標的", "category": "手動"})]
        else:
            targets = [(sid, info) for sid, info in db.items() if info['category'] in cats][:max_limit]

        # 針對電子類股降低量能門檻
        min_vol_threshold = 150 if "電子" in cats else min_vol_val

        def worker(target):
            sid, info = target
            try:
                df = yf.download(sid, period="90d", progress=False, timeout=10)  # 擴大到90天，確保有足夠數據
                if df.empty or len(df) < 45: return None
                v_now = int(df['Volume'].iloc[-1] / 1000)
                if not input_sid and v_now < min_vol_threshold: return None
                labels, lines, i_tri, i_bx, i_vo = _analyze_pattern_logic(df)
                match = False
                if input_sid:
                    match = True
                elif (pats['tri'] and i_tri) or (pats['box'] and i_bx) or (pats['vol'] and i_vo):
                    match = True
                if match:
                    return {"sid": sid, "name": info['name'], "cat": info['category'], "df": df.tail(50),  # 圖表顯示50天
                            "lines": lines, "labels": labels, "price": float(df['Close'].iloc[-1]), "vol": v_now}
            except:
                return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker, t) for t in targets]
            for f in concurrent.futures.as_completed(futures):
                res = f.result()
                if res: results.append(res)

        status.update(label=f"✅ 完成！發現 {len(results)} 檔標的", state="complete")
        return results


# ==========================================
# 7. 渲染結果
# ==========================================


final_list = []
if auto_toggle:
    final_list = execute_engine(is_auto_mode=True)
elif btn_manual or input_sid:
    final_list = execute_engine(is_auto_mode=False)
else:
    st.info("💡 系統就緒。請從左側點擊按鈕或開啟自動監控。")

if final_list:
    for item in final_list:
        with st.container():
            badge_html = "".join([
                f'<span class="badge {"badge-tri" if "三角" in l else "badge-vol" if "爆量" in l else "badge-box"}">{l}</span>'
                for l in item['labels']])
            st.markdown(
                f'<div class="stock-card"><h3>{item["sid"]} {item["name"]} <small>({item["cat"]})</small> {badge_html}</h3><p>現價：{item["price"]:.2f} | 量：{item["vol"]}張</p></div>',
                unsafe_allow_html=True)
            d, (sh, ih, sl, il) = item['df'], item['lines']
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
            fig.add_trace(go.Candlestick(x=d.index, open=d['Open'], high=d['High'], low=d['Low'], close=d['Close']),
                          row=1, col=1)
            xv = np.arange(len(d))
            fig.add_trace(go.Scatter(x=d.index, y=sh * xv + ih, line=dict(color='red', width=2, dash='dash')),
                          row=1, col=1)
            fig.add_trace(go.Scatter(x=d.index, y=sl * xv + il, line=dict(color='green', width=2, dash='dot')),
                          row=1, col=1)
            fig.add_trace(go.Bar(x=d.index, y=d['Volume'], marker_color='blue', opacity=0.4), row=2, col=1)
            fig.update_layout(height=450, template="plotly_white", xaxis_rangeslider_visible=False, showlegend=False,
                              margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True, key=f"f_{item['sid']}")
