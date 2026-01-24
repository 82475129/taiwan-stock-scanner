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

# --- [ 1. 數據引擎：確保全市場代碼完整 ] ---
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
    """形態演算法核心：分離判定並打標籤"""
    try:
        d = df.tail(30).copy()
        x = np.arange(len(d))
        h, l, c, v = d['High'].values.flatten(), d['Low'].values.flatten(), d['Close'].values.flatten(), d['Volume'].values.flatten()
        
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)

        found_labels = []
        # 靈敏判定：1.1倍爆量 & 0.0015 斜率
        is_tri = sh < -0.0015 and sl > 0.0015
        is_box = abs(sh) < 0.0015 and abs(sl) < 0.0015
        is_rev = (c[-1] > (sh*29+ih) or c[-1] < (sl*29+il))
        is_vol = v[-1] > (v[-6:-1].mean() * 1.1)

        if m1 and is_tri: found_labels.append("📐 三角形態")
        if m2 and is_box: found_labels.append("📦 旗箱系")
        if m3 and is_rev: found_labels.append("🔄 反轉系")
        if m4 and is_vol: found_labels.append("🚀 爆量突破")
        
        return found_labels, (sh, ih, sl, il)
    except:
        return [], (0,0,0,0)

# --- [ 2. 視覺介面樣式 ] ---
st.set_page_config(page_title="台股 Pro-X 形態大師", layout="wide")
st.markdown("""
    <style>
    .stApp { background: #f0f2f6; }
    section[data-testid="stSidebar"] { background-color: #f8f9fa !important; border-right: 1px solid #e9ecef; }
    .monitor-on { background-color: #d4edda; color: #155724; padding: 15px; border-radius: 8px; text-align: center; font-weight: bold; margin-bottom: 20px; border: 1px solid #c3e6cb; }
    .stock-card { background: white; padding: 20px; border-radius: 12px; border: 1px solid #dee2e6; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    .tag-found { background-color: #ff4b4b; color: white; padding: 3px 12px; border-radius: 15px; font-size: 13px; font-weight: bold; margin-left: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- [ 3. 側邊決策中心 - 恢復原始介面 ] ---
with st.sidebar:
    st.markdown("## 🎯 決策中心")
    auto_monitor = st.toggle("開啟自動監控", value=True)
    if auto_monitor:
        st.markdown('<div class="monitor-on">📡 數據自動掃描中</div>', unsafe_allow_html=True)
        st_autorefresh(interval=600000, key="auto_pilot")

    # 恢復完整的 Form 表單與控制項
    with st.form("manual_scan_form"):
        st.write("### 🔍 標的快查")
        input_sid = st.text_input("輸入股票代號", placeholder="例如: 2330")
        pop_sel = st.multiselect("熱門觀察清單", ["2330 台積電", "2317 鴻海", "2603 長榮", "2454 聯發科"])

        st.divider()
        st.write("### 🧪 形態偵測設定")
        m1 = st.checkbox("偵測三角系 (對稱/收斂)", value=True)
        m2 = st.checkbox("偵測旗箱系", value=False)
        m3 = st.checkbox("偵測反轉系", value=False)
        m4 = st.checkbox("偵測爆量突破", value=True)

        st.divider()
        st.write("### ⚙️ 進階篩選器")
        scan_limit = st.slider("掃描標的數", 10, 2000, 500)
        min_v = st.number_input("最低成交量 (張)", value=500)
        ma_on = st.toggle("站上 20MA (多頭排列)", value=True)

        manual_btn = st.form_submit_button("🚀 開始深度掃描", use_container_width=True, type="primary")

    if st.button("🔄 重新整理資料庫", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- [ 4. 核心執行邏輯 ] ---
if auto_monitor or manual_btn:
    with st.status("🔍 分析引擎正在確認全市場形態...", expanded=True) as status:
        results = []
        market_data = _engine_core_fetch()
        
        # 處理手動搜尋代號
        manual_targets = [f"{input_sid.strip()}.TW"] if input_sid else []
        for p in pop_sel: manual_targets.append(f"{p.split(' ')[0]}.TW")

        targets = list(market_data.items())[:scan_limit]

        for i, (sid, sname) in enumerate(targets):
            status.update(label=f"正在分析 ({i+1}/{len(targets)}): {sid} {sname}")
            try:
                is_manual = sid in manual_targets
                df = yf.download(sid, period="100d", progress=False, timeout=10)
                if df.empty or len(df) < 30: continue

                # 提取價格數據
                last_price = float(df['Close'].iloc[-1].values[0])
                last_vol = int(df['Volume'].iloc[-1].values[0] / 1000)
                
                # 過濾機制
                if not is_manual:
                    if last_vol < min_v: continue
                    ma20 = df['Close'].rolling(20).mean().iloc[-1].values[0]
                    if ma_on and last_price < ma20: continue

                # 呼叫形態判定
                res_labels, lines = _analyze_pattern(df, m1, m2, m3, m4)
                
                if res_labels or is_manual:
                    results.append({
                        "id": sid, "name": sname, "df": df.tail(40), "lines": lines, 
                        "labels": res_labels if res_labels else ["觀察清單"], 
                        "price": last_price, "vol": last_vol
                    })
            except: continue
        status.update(label="✅ 本次掃描任務完成", state="complete")

    # --- [ 5. 細緻視覺化輸出 ] ---
    if results:
        for idx, item in enumerate(results):
            with st.container():
                # 精美資訊卡片
                lbl_html = "".join([f'<span class="tag-found">{l}</span>' for l in item['labels']])
                st.markdown(f'''
                    <div class="stock-card">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <b>{item["id"]} {item["name"]}</b>
                            <div>{lbl_html}</div>
                        </div>
                        <div style="font-size:14px; color:#666; margin-top:5px;">
                            現價：{item["price"]:.2f} | 成交：{item["vol"]}張
                        </div>
                    </div>
                ''', unsafe_allow_html=True)
                
                # 建立細緻子圖 (K線 + 成交量)
                d = item['df']
                sh, ih, sl, il = item['lines']
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
                
                # 1. K線圖
                fig.add_trace(go.Candlestick(x=d.index, open=d['Open'], high=d['High'], low=d['Low'], close=d['Close'],
                    increasing_line_color='#eb4d4b', decreasing_line_color='#6ab04c', name="K線"), row=1, col=1)
                
                # 2. 均線
                fig.add_trace(go.Scatter(x=d.index, y=d['Close'].rolling(5).mean(), line=dict(color='#3498db', width=1), name="5MA"), row=1, col=1)
                fig.add_trace(go.Scatter(x=d.index, y=d['Close'].rolling(20).mean(), line=dict(color='#f39c12', width=1.5), name="20MA"), row=1, col=1)

                # 3. 形態趨勢線 (只顯示最近30天)
                xv = np.arange(30)
                fig.add_trace(go.Scatter(x=d.index[-30:], y=sh*xv + ih, line=dict(color='red', width=2, dash='dash'), name="壓力"), row=1, col=1)
                fig.add_trace(go.Scatter(x=d.index[-30:], y=sl*xv + il, line=dict(color='green', width=2, dash='dot'), name="支撐"), row=1, col=1)

                # 4. 成交量圖
                vol_colors = ['#eb4d4b' if c >= o else '#6ab04c' for o, c in zip(d['Open'], d['Close'])]
                fig.add_trace(go.Bar(x=d.index, y=d['Volume'], marker_color=vol_colors, name="成交量"), row=2, col=1)
                
                fig.update_layout(height=480, template="plotly_white", xaxis_rangeslider_visible=False, showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig, use_container_width=True, key=f"c_{item['id']}")
                st.divider()
    else:
        st.info("💡 掃描完畢，未發現符合勾選條件的標的。")
