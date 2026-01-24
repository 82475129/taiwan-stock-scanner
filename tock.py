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
        for s_id in range(1, 34):
            for ex in ["TAI", "TWO"]:
                r = requests.get(f"https://tw.stock.yahoo.com/class-quote?sectorId={s_id}&exchange={ex}", timeout=10)
                soup = BeautifulSoup(r.text, "html.parser")
                for li in soup.find_all("li", class_="List(n)"):
                    sid_element = li.find("span", string=re.compile(r"\d{4}\.(TW|TWO)"))
                    sn_element = li.find("div", class_="Lh(20px) Fw(600) Fz(16px) Ell")
                    if sid_element and sn_element:
                        codes[sid_element.text.strip()] = sn_element.text.strip()
    except: pass
    return codes

def _analyze_patterns(df):
    try:
        d = df.tail(30).copy()
        x = np.arange(len(d))
        h, l, v = d['High'].values.flatten(), d['Low'].values.flatten(), d['Volume'].values.flatten()
        
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)

        res = []
        is_tri = sh < -0.001 and sl > 0.001
        is_vol = v[-1] > (v[-6:-1].mean() * 1.05)
        is_box = abs(sh) < 0.0015 and abs(sl) < 0.0015

        if is_tri: res.append("📐 三角收斂")
        if is_vol: res.append("🚀 爆量突破")
        if is_box: res.append("📦 旗箱矩形")
        
        return res, (sh, ih, sl, il), is_tri, is_vol, is_box
    except:
        return [], (0,0,0,0), False, False, False

# --- [ 2. 視覺樣式 ] ---
st.set_page_config(page_title="台股 Pro-X 形態大師", layout="wide")
st.markdown("""
    <style>
    .stApp { background: #f8f9fa; }
    .welcome-box { background: white; padding: 40px; border-radius: 20px; text-align: center; box-shadow: 0 10px 25px rgba(0,0,0,0.05); margin-top: 50px; }
    .stock-card { background: white; padding: 15px; border-radius: 12px; border-left: 6px solid #6c5ce7; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    .tag { padding: 3px 10px; border-radius: 6px; font-size: 12px; font-weight: bold; color: white; margin-left: 5px; }
    .tag-tri { background: #6c5ce7; }
    .tag-vol { background: #ff7675; }
    .tag-box { background: #2d3436; }
    </style>
    """, unsafe_allow_html=True)

# --- [ 3. 側邊決策中心 ] ---
with st.sidebar:
    st.markdown("## 🎯 決策中心")
    auto_monitor = st.toggle("開啟自動監控", value=False)
    if auto_monitor:
        st_autorefresh(interval=300000, key="auto_pilot")
        st.info("📡 即時巡航中...")

    st.divider()
    with st.form("scan_config"):
        st.write("### 🧪 掃描設定")
        input_sid = st.text_input("輸入個股代號", placeholder="例如: 2330")
        scan_limit = st.slider("掃描數量", 10, 2000, 500)
        min_v = st.number_input("最低張數", value=100)
        ma_on = st.toggle("過濾 20MA", value=False)
        
        st.write("### 🔍 偵測形態")
        m1 = st.checkbox("偵測三角系", value=True)
        m2 = st.checkbox("偵測旗箱系", value=True)
        m4 = st.checkbox("偵測爆量型", value=True)
        
        submit = st.form_submit_button("🚀 執行掃描 / 查詢", use_container_width=True, type="primary")

# --- [ 4. 執行邏輯 ] ---
if not (auto_monitor or submit):
    st.markdown("""
        <div class="welcome-box">
            <h1 style='color: #6c5ce7;'>🎯 台股 Pro-X 形態大師</h1>
            <p style='color: #666; font-size: 18px;'>歡迎使用專業形態掃描系統</p>
            <div style='display: flex; justify-content: center; gap: 20px; margin-top: 30px;'>
                <div style='padding: 20px; background: #f1f2f6; border-radius: 10px; width: 200px;'>
                    <h3>🔍 個股查詢</h3>
                    <p>輸入代號立即分析 K 線形態</p>
                </div>
                <div style='padding: 20px; background: #f1f2f6; border-radius: 10px; width: 200px;'>
                    <h3>🚀 全場掃描</h3>
                    <p>自動篩選三角收斂與爆量股</p>
                </div>
            </div>
            <p style='margin-top: 40px; color: #a2a2a2;'>請使用左側面板開始您的第一次掃描</p>
        </div>
    """, unsafe_allow_html=True)
else:
    with st.status("🔍 數據讀取中...", expanded=True) as status:
        results = []
        market_data = _engine_core_fetch()
        
        if input_sid:
            s_clean = input_sid.strip().upper()
            # 名稱匹配：優先檢查 .TW 再檢查 .TWO
            name = market_data.get(f"{s_clean}.TW", market_data.get(f"{s_clean}.TWO", f"個股 {s_clean}"))
            targets = [(f"{s_clean}.TW", name), (f"{s_clean}.TWO", name)]
        else:
            targets = list(market_data.items())[:scan_limit]

        for sid, sname in targets:
            try:
                df = yf.download(sid, period="60d", progress=False, timeout=5)
                if df.empty or len(df) < 30: continue
                
                close_vals = df['Close'].values.flatten()
                price = float(close_vals[-1])
                vol = int(df['Volume'].values.flatten()[-1] / 1000)
                
                if not input_sid:
                    if vol < min_v: continue
                    if ma_on:
                        ma20 = df['Close'].rolling(20).mean().iloc[-1].values[0]
                        if price < ma20: continue

                labels, lines, is_tri, is_vol, is_box = _analyze_patterns(df)
                
                show = False
                if input_sid: 
                    show = True # 手動查詢強制顯示
                elif (m1 and is_tri) or (m2 and is_box) or (m4 and is_vol):
                    show = True
                
                if show:
                    results.append({"id": sid, "name": sname, "df": df.tail(40), "lines": lines, "labels": labels, "price": price, "vol": vol})
                    if input_sid: break 
            except: continue
        status.update(label="✅ 處理完成", state="complete")

    if results:
        st.subheader("📋 股票追蹤清單")
        summary_list = []
        for item in results:
            summary_list.append({
                "代號": item["id"],
                "名稱": item["name"],
                "現價": item["price"],
                "成交(張)": item["vol"],
                "形態狀態": " | ".join(item["labels"]), # 如果 labels 為空，這會是空字串
                "近期走勢": item["df"]['Close'].values.flatten().tolist()
            })
        
        st.data_editor(
            pd.DataFrame(summary_list),
            column_config={
                "近期走勢": st.column_config.LineChartColumn("40日趨勢"),
                "現價": st.column_config.NumberColumn(format="%.2f"),
                "形態狀態": st.column_config.TextColumn("形態狀態") # 無形態時呈現空白
            },
            hide_index=True, use_container_width=True, disabled=True, key="main_table"
        )
        
        st.divider() 
        
        for item in results:
            with st.container():
                # Card 顯示處理：無形態則不產標籤 HTML
                lbl_html = "".join([f'<span class="tag {"tag-tri" if "三角" in l else "tag-vol" if "爆量" in l else "tag-box"}">{l}</span>' for l in item['labels']])
                st.markdown(f'<div class="stock-card"><div style="display:flex; justify-content:space-between;"><b>{item["id"]} {item["name"]}</b><div>{lbl_html}</div></div><div style="font-size:14px; color:#666;">現價：{item["price"]:.2f} | 成交：{item["vol"]}張</div></div>', unsafe_allow_html=True)
                
                d = item['df']
                sh, ih, sl, il = item['lines']
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
                fig.add_trace(go.Candlestick(x=d.index, open=d['Open'].values.flatten(), high=d['High'].values.flatten(), low=d['Low'].values.flatten(), close=d['Close'].values.flatten(), name="K線"), row=1, col=1)
                
                xv = np.arange(30)
                fig.add_trace(go.Scatter(x=d.index[-30:], y=sh*xv + ih, line=dict(color='red', width=2, dash='dash')), row=1, col=1)
                fig.add_trace(go.Scatter(x=d.index[-30:], y=sl*xv + il, line=dict(color='green', width=2, dash='dot')), row=1, col=1)
                
                colors = ['#ff4d4d' if c >= o else '#00b050' for o, c in zip(d['Open'].values.flatten(), d['Close'].values.flatten())]
                fig.add_trace(go.Bar(x=d.index, y=d['Volume'].values.flatten(), marker_color=colors), row=2, col=1)
                fig.update_layout(height=400, template="plotly_white", xaxis_rangeslider_visible=False, showlegend=False, margin=dict(l=10,r=10,t=10,b=10))
                st.plotly_chart(fig, use_container_width=True, key=f"f_{item['id']}")
    else:
        st.warning("💡 未找到對應數據。")
