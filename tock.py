import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import re
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.stats import linregress
from bs4 import BeautifulSoup
from streamlit_autorefresh import st_autorefresh

# --- [ 1. 核心數據引擎 ] ---
@st.cache_data(ttl=3600, show_spinner=False)
def _engine_core_fetch():
    codes = {}
    try:
        # 抓取 Yahoo 財經台股分類代碼
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

def _analyze_patterns(df, m1, m2, m3, m4):
    """形態偵測核心演算法"""
    try:
        d = df.tail(30).copy()
        x = np.arange(len(d))
        h, l, c, v = d['High'].values.flatten(), d['Low'].values.flatten(), d['Close'].values.flatten(), d['Volume'].values.flatten()
        
        # 線性回歸計算趨勢線
        sh, ih, _, _, _ = linregress(x, h) # 壓力線
        sl, il, _, _, _ = linregress(x, l) # 支撐線

        labels = []
        # 1. 三角系 (壓力下傾, 支撐上揚)
        if m1 and (sh < -0.002 and sl > 0.002): labels.append("📐 三角形態")
        # 2. 旗箱系 (兩線趨近水平平行)
        if m2 and (abs(sh) < 0.002 and abs(sl) < 0.002): labels.append("📦 旗箱矩形")
        # 3. 反轉系 (價格突破或跌破 30日趨勢)
        if m3 and (c[-1] > (sh*29+ih) or c[-1] < (sl*29+il)): labels.append("🔄 反轉預警")
        # 4. 爆量型 (今日量 > 5日均量 1.1倍)
        has_vol = v[-1] > (v[-6:-1].mean() * 1.1)
        if m4 and has_vol: labels.append("🚀 爆量突破")
        
        return labels, (sh, ih, sl, il), has_vol
    except:
        return [], (0,0,0,0), False

# --- [ 2. 介面樣式美化 ] ---
st.set_page_config(page_title="台股 Pro-X 終極版", layout="wide")
st.markdown("""
    <style>
    .stApp { background: #f4f7f9; }
    .stock-card { background: white; padding: 20px; border-radius: 15px; border: 1px solid #e0e6ed; margin-bottom: 25px; box-shadow: 0 6px 15px rgba(0,0,0,0.05); }
    .tag { padding: 4px 12px; border-radius: 8px; font-size: 12px; font-weight: bold; color: white; margin-left: 5px; }
    .tag-tri { background: #6c5ce7; }
    .tag-vol { background: #ff7675; }
    .tag-other { background: #2d3436; }
    .monitor-box { background: #e3f2fd; border: 1px solid #90caf9; padding: 15px; border-radius: 10px; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

# --- [ 3. 側邊決策中心 ] ---
with st.sidebar:
    st.markdown("# 🎯 決策中心")
    
    # 區塊 A：即時過濾區 (與掃描邏輯分離)
    st.markdown("### 📡 顯示過濾 (即時生效)")
    f_tri = st.checkbox("顯示三角形態", value=True)
    f_vol = st.checkbox("顯示爆量突破", value=True)
    f_other = st.checkbox("顯示其他形態", value=True)
    
    auto_monitor = st.toggle("開啟自動監控模式", value=True)
    if auto_monitor:
        st.markdown('<div class="monitor-box">🛰️ 系統自動掃描中</div>', unsafe_allow_html=True)
        st_autorefresh(interval=600000, key="auto_pilot") # 10分鐘刷一次
    
    st.divider()
    
    # 區塊 B：掃描設定區 (Form 內)
    with st.form("scan_settings"):
        st.markdown("### 🧪 掃描核心設定")
        m1 = st.checkbox("偵測：三角系", value=True)
        m2 = st.checkbox("偵測：旗箱系", value=True)
        m3 = st.checkbox("偵測：反轉系", value=False)
        m4 = st.checkbox("偵測：爆量型", value=True)
        
        st.divider()
        st.markdown("### ⚙️ 進階篩選")
        input_sid = st.text_input("個股代號查詢", placeholder="2330")
        scan_limit = st.slider("掃描標的數量", 10, 2000, 500)
        min_v = st.number_input("最低成交量 (張)", value=500)
        ma_on = st.toggle("過濾：站上 20MA", value=True)
        
        submit = st.form_submit_button("🚀 開始深度執行", use_container_width=True, type="primary")

# --- [ 4. 核心執行與邏輯判斷 ] ---
if auto_monitor or submit:
    with st.status("🔍 形態引擎深度分析中...", expanded=True) as status:
        results = []
        market_data = _engine_core_fetch()
        manual_list = [f"{input_sid.strip()}.TW"] if input_sid else []
        targets = list(market_data.items())[:scan_limit]

        for i, (sid, sname) in enumerate(targets):
            status.update(label=f"正在分析 ({i+1}/{len(targets)}): {sid} {sname}")
            try:
                is_manual = sid in manual_list
                df = yf.download(sid, period="100d", progress=False, timeout=10)
                if df.empty or len(df) < 40: continue

                # 提取數據
                price = float(df['Close'].iloc[-1].values[0])
                vol = int(df['Volume'].iloc[-1].values[0] / 1000)
                ma20 = df['Close'].rolling(20).mean().iloc[-1].values[0]
                
                # 基本過濾
                if not is_manual:
                    if vol < min_v: continue
                    if ma_on and price < ma20: continue

                # 形態分析
                labels, lines, is_vol_hit = _analyze_patterns(df, m1, m2, m3, m4)
                
                # 判定過濾區是否要顯示
                show = False
                if is_manual: show = True
                if f_tri and any("三角" in l for l in labels): show = True
                if f_vol and is_vol_hit: show = True
                if f_other and any(("旗箱" in l or "反轉" in l) for l in labels): show = True

                if show:
                    results.append({"id": sid, "name": sname, "df": df.tail(40), "lines": lines, "labels": labels, "price": price, "vol": vol})
            except: continue
        status.update(label="✅ 分析任務完成", state="complete")

    # --- [ 5. 細緻圖表輸出 ] ---
    if results:
        
        for item in results:
            with st.container():
                # 頂部資訊卡
                lbl_html = "".join([f'<span class="tag {"tag-tri" if "三角" in l else "tag-vol" if "爆量" in l else "tag-other"}">{l}</span>' for l in item['labels']])
                st.markdown(f'''
                    <div class="stock-card">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <span style="font-size:22px; font-weight:bold; color:#2c3e50;">{item["id"]} {item["name"]}</span>
                            <div>{lbl_html}</div>
                        </div>
                        <div style="color:#7f8c8d; font-size:14px; margin-top:5px;">現價：{item["price"]:.2f} | 成交量：{item["vol"]}張</div>
                    </div>
                ''', unsafe_allow_html=True)

                # 繪製專業子圖
                d = item['df']
                sh, ih, sl, il = item['lines']
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])

                # 1. K線 (漲紅跌綠)
                fig.add_trace(go.Candlestick(x=d.index, open=d['Open'], high=d['High'], low=d['Low'], close=d['Close'],
                    increasing_line_color='#eb4d4b', decreasing_line_color='#6ab04c', name="K線"), row=1, col=1)
                
                # 2. 均線
                fig.add_trace(go.Scatter(x=d.index, y=d['Close'].rolling(5).mean(), line=dict(color='#3498db', width=1), name="5MA"), row=1, col=1)
                fig.add_trace(go.Scatter(x=d.index, y=d['Close'].rolling(20).mean(), line=dict(color='#f39c12', width=1.5), name="20MA"), row=1, col=1)

                # 3. 形態趨勢線 (只畫後30天)
                xv = np.arange(30)
                fig.add_trace(go.Scatter(x=d.index[-30:], y=sh*xv + ih, line=dict(color='red', width=2, dash='dash'), name="壓力"), row=1, col=1)
                fig.add_trace(go.Scatter(x=d.index[-30:], y=sl*xv + il, line=dict(color='green', width=2, dash='dash'), name="支撐"), row=1, col=1)

                # 4. 成交量
                vol_colors = ['#eb4d4b' if c >= o else '#6ab04c' for o, c in zip(d['Open'], d['Close'])]
                fig.add_trace(go.Bar(x=d.index, y=d['Volume'], marker_color=vol_colors, name="成交量"), row=2, col=1)

                fig.update_layout(height=500, template="plotly_white", xaxis_rangeslider_visible=False, 
                                  showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig, use_container_width=True, key=f"plot_{item['id']}")
                st.divider()
    else:
        st.info("💡 掃描完畢，未發現符合顯示過濾條件的標的。")
