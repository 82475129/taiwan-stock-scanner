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

# --- [ 1. 數據引擎 ] ---
@st.cache_data(ttl=3600, show_spinner=False)
def _engine_core_fetch():
    codes = {}
    try:
        for s_id in range(1, 34):
            for ex in ["TAI", "TWO"]:
                r = requests.get(f"https://tw.stock.yahoo.com/class-quote?sectorId={s_id}&exchange={ex}", timeout=10)
                soup = BeautifulSoup(r.text, "html.parser")
                for li in soup.find_all("li", class_="List(n)"):
                    sid = li.find("span", string=re.compile(r"\d{4}\.(TW|TWO)"))
                    sn = li.find("div", class_="Lh(20px) Fw(600) Fz(16px) Ell")
                    if sid and sn: codes[sid.text.strip()] = sn.text.strip()
    except: pass
    return codes

def _analyze_pattern(df, m1, m2, m3, m4):
    """形態演算法核心：確保所有勾選的形態都能獨立判定並並存"""
    try:
        d = df.tail(30)
        x = np.arange(len(d))
        h, l, c, v = d['High'].values.flatten(), d['Low'].values.flatten(), d['Close'].values.flatten(), d['Volume'].values.flatten()
        
        # 計算回歸趨勢線
        sh, ih, _, _, _ = linregress(x, h) # 壓力線 (斜率 sh)
        sl, il, _, _, _ = linregress(x, l) # 支撐線 (斜率 sl)

        found_labels = []

        # 1. 三角系判定 (壓力下傾 sh < -0.002 且 支撐上揚 sl > 0.002)
        # 調降閾值至 0.002 以提高偵測靈敏度，避免形態消失
        is_tri = sh < -0.002 and sl > 0.002 
        if m1 and is_tri:
            found_labels.append("📐 三角形態")

        # 2. 旗箱系判定 (兩線趨近水平平行)
        is_box = abs(sh) < 0.002 and abs(sl) < 0.002
        if m2 and is_box:
            found_labels.append("📦 旗箱矩形")

        # 3. 反轉系判定 (簡易：價格穿透 30 日趨勢線邊界)
        is_rev = (c[-1] < (sl * 29 + il)) or (c[-1] > (sh * 29 + ih))
        if m3 and is_rev:
            found_labels.append("🔄 反轉預警")

        # 4. 爆量突破判定 (今日量 > 近 5 日均量 1.1 倍)
        is_vol = v[-1] > (v[-6:-1].mean() * 1.1)
        if m4 and is_vol:
            found_labels.append("🚀 爆量突破")
        
        return (", ".join(found_labels) if found_labels else None, (sh, ih, sl, il))
    except:
        return None, (0,0,0,0)

# --- [ 2. 視覺介面樣式 ] ---
st.set_page_config(page_title="台股 Pro-X 形態大師", layout="wide")
st.markdown("""
    <style>
    .stApp { background: #f0f2f6; }
    section[data-testid="stSidebar"] { background-color: #f8f9fa !important; border-right: 1px solid #e9ecef; }
    .monitor-on { background-color: #d4edda; color: #155724; padding: 15px; border-radius: 8px; text-align: center; font-weight: bold; margin-bottom: 20px; border: 1px solid #c3e6cb; }
    .stock-card { background: white; padding: 20px; border-radius: 12px; border: 1px solid #dee2e6; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    .tag-found { background-color: #ff4b4b; color: white; padding: 3px 12px; border-radius: 15px; font-size: 13px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- [ 3. 側邊決策中心 - 完整介面 ] ---
with st.sidebar:
    st.markdown("## 🎯 決策中心")
    auto_monitor = st.toggle("開啟自動監控", value=True)
    if auto_monitor:
        st.markdown('<div class="monitor-on">📡 數據自動掃描中</div>', unsafe_allow_html=True)
        st_autorefresh(interval=600000, key="auto_pilot")

    with st.form("manual_scan_form"):
        st.write("### 🔍 標的快查")
        input_sid = st.text_input("輸入股票代號", placeholder="例如: 2330")
        pop_sel = st.multiselect("熱門觀察清單", ["2330 台積電", "2317 鴻海", "2603 長榮", "2454 聯發科"])

        st.divider()
        st.write("### 🧪 形態偵測設定")
        m1 = st.checkbox("偵測三角系 (對稱/收斂)", value=True)
        m2 = st.checkbox("偵測旗箱系", value=True)
        m3 = st.checkbox("偵測反轉系", value=False)
        m4 = st.checkbox("偵測爆量突破", value=True)

        st.divider()
        st.write("### ⚙️ 進階篩選器")
        scan_limit = st.slider("掃描標的數", 10, 2000, 2000)
        min_v = st.number_input("最低成交量 (張)", value=500)
        ma_on = st.toggle("站上 20MA (多頭排列)", value=True)

        manual_btn = st.form_submit_button("🚀 開始深度掃描", use_container_width=True, type="primary")

    if st.button("🔄 重新整理資料庫", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- [ 4. 核心執行邏輯 ] ---
if auto_monitor or manual_btn:
    with st.status("🔍 正在核對全市場形態數據...", expanded=True) as status:
        results = []
        market_data = _engine_core_fetch()
        manual_targets = [f"{input_sid.strip()}.TW"] if input_sid else []
        for p in pop_sel: manual_targets.append(f"{p.split(' ')[0]}.TW")

        targets = list(market_data.items())[:scan_limit]

        for i, (sid, sname) in enumerate(targets):
            status.update(label=f"核對中: {sid} {sname}")
            try:
                is_manual = sid in manual_targets
                df = yf.download(sid, period="60d", progress=False, timeout=10)
                if df.empty or len(df) < 30: continue

                last_price = float(df['Close'].iloc[-1].values[0])
                last_vol = int(df['Volume'].iloc[-1].values[0] / 1000)
                
                if not is_manual:
                    if last_vol < min_v: continue
                    ma20 = df['Close'].rolling(20).mean().iloc[-1].values[0]
                    if ma_on and last_price < ma20: continue

                # 傳入所有 Checkbox 狀態進行多重判定
                res_label, lines = _analyze_pattern(df, m1, m2, m3, m4)
                
                if res_label or is_manual:
                    results.append({
                        "id": sid, "name": sname, "df": df.tail(30), "lines": lines, 
                        "res": res_label or "自選觀察", "price": last_price, "vol": last_vol
                    })
            except: continue
        status.update(label="✅ 分析完成", state="complete")

    # --- [ 5. 結果顯示與繪圖 ] ---
    if results:
        
        cols = st.columns(2)
        for idx, item in enumerate(results):
            with cols[idx % 2]:
                st.markdown(f'<div class="stock-card"><b>{item["id"]} {item["name"]}</b> <span class="tag-found">{item["res"]}</span><br>現價：{item["price"]:.2f} | 成交：{item["vol"]}張</div>', unsafe_allow_html=True)
                
                fig = go.Figure(data=[go.Candlestick(x=item['df'].index, open=item['df']['Open'], high=item['df']['High'], low=item['df']['Low'], close=item['df']['Close'])])
                
                d, (sh, ih, sl, il) = item['df'], item['lines']
                xv = np.arange(len(d))
                # 繪製自動計算的趨勢線
                fig.add_trace(go.Scatter(x=d.index, y=sh * xv + ih, line=dict(color='red', width=2, dash='dot'), name="壓力線"))
                fig.add_trace(go.Scatter(x=d.index, y=sl * xv + il, line=dict(color='green', width=2, dash='dot'), name="支撐線"))
                
                fig.update_layout(height=320, template="plotly_white", xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, t=0, b=0))
                st.plotly_chart(fig, use_container_width=True, key=f"c_{item['id']}")
    else:
        st.info("💡 目前未發現符合勾選形態的標的。")
