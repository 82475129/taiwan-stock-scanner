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
                    sid = li.find("span", string=re.compile(r"\d{4}\.(TW|TWO)"))
                    sn = li.find("div", class_="Lh(20px) Fw(600) Fz(16px) Ell")
                    if sid and sn: codes[sid.text.strip()] = sn.text.strip()
    except: pass
    return codes

def _analyze_patterns(df):
    """形態偵測：放寬門檻，確保不漏抓"""
    try:
        d = df.tail(30).copy()
        x = np.arange(len(d))
        h, l, c, v = d['High'].values.flatten(), d['Low'].values.flatten(), d['Close'].values.flatten(), d['Volume'].values.flatten()
        
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
    
    st.write("### 📡 監控狀態")
    auto_monitor = st.toggle("開啟自動監控", value=True)
    if auto_monitor:
        st_autorefresh(interval=300000, key="auto_pilot")
        st.info("📡 系統正在即時巡航中...")

    st.divider()
    
    with st.form("scan_config"):
        st.write("### 🧪 掃描設定")
        input_sid = st.text_input("輸入個股代號", placeholder="例如: 2330")
        scan_limit = st.slider("掃描數量", 10, 2000, 500)
        min_v = st.number_input("最低張數 (設 0 則不限)", value=100)
        ma_on = st.toggle("過濾 20MA (不勾則顯示全部)", value=False)
        
        st.write("### 🔍 偵測形態")
        m1 = st.checkbox("偵測三角系", value=True)
        m2 = st.checkbox("偵測旗箱系", value=True)
        m4 = st.checkbox("偵測爆量型", value=True)
        
        submit = st.form_submit_button("🚀 執行掃描 / 查詢", use_container_width=True, type="primary")

# --- [ 4. 執行邏輯 ] ---
if auto_monitor or submit:
    with st.status("🔍 正在讀取數據...", expanded=True) as status:
        results = []
        
        # 決定目標清單
        if input_sid:
            # 如果有輸入代號，只查該股票
            s_clean = input_sid.strip().upper()
            suffix = ".TWO" if len(s_clean) == 4 and s_clean.startswith(('5','6','8')) else ".TW" # 簡單判斷上櫃與否
            targets = [(f"{s_clean}{suffix}", "手動查詢")]
        else:
            # 否則執行全市場掃描
            market_data = _engine_core_fetch()
            targets = list(market_data.items())[:scan_limit]

        for sid, sname in targets:
            try:
                df = yf.download(sid, period="60d", progress=False, timeout=5)
                if df.empty or len(df) < 30: continue
                
                # 安全提取數值
                close_vals = df['Close'].values.flatten()
                price = float(close_vals[-1])
                vol = int(df['Volume'].values.flatten()[-1] / 1000)
                
                # 過濾判定 (僅在非手動查詢時生效)
                if not input_sid:
                    if vol < min_v: continue
                    if ma_on:
                        ma20 = df['Close'].rolling(20).mean().iloc[-1].values[0]
                        if price < ma20: continue

                labels, lines, is_tri, is_vol, is_box = _analyze_patterns(df)
                
                # 顯示判定
                show = False
                if input_sid: 
                    show = True
                    if not labels: labels = ["🔍 個股追蹤"] # 手動查詢若無形態則標註
                elif (m1 and is_tri) or (m2 and is_box) or (m4 and is_vol):
                    show = True
                
                if show:
                    results.append({"id": sid, "name": sname, "df": df.tail(40), "lines": lines, "labels": labels, "price": price, "vol": vol})
            except: continue
        status.update(label="✅ 處理完成", state="complete")

    # --- [ 5. 輸出介面 ] ---
    if results:
        # --- 總覽清單 ---
        st.subheader("📋 股票追蹤清單")
        summary_list = []
        for item in results:
            trend_data = item["df"]['Close'].values.flatten().tolist()
            summary_list.append({
                "代號": item["id"],
                "名稱": item["name"],
                "現價": item["price"],
                "成交(張)": item["vol"],
                "符合狀態": " | ".join(item["labels"]),
                "40日走勢": trend_data
            })
        
        df_summary = pd.DataFrame(summary_list)
        st.data_editor(
            df_summary,
            column_config={
                "代號": st.column_config.TextColumn("代號"),
                "現價": st.column_config.NumberColumn("現價", format="%.2f"),
                "成交(張)": st.column_config.NumberColumn("成交(張)", format="%d"),
                "40日走勢": st.column_config.LineChartColumn("近期走勢"),
                "符合狀態": st.column_config.TextColumn("狀態/形態"),
            },
            hide_index=True,
            use_container_width=True,
            disabled=True,
            key="summary_table"
        )
        
        st.divider() 
        
        # --- 詳細 K 線圖表 ---
        for item in results:
            with st.container():
                lbl_html = "".join([f'<span class="tag {"tag-tri" if "三角" in l else "tag-vol" if "爆量" in l else "tag-box"}">{l}</span>' for l in item['labels']])
                st.markdown(f'''<div class="stock-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:20px; font-weight:bold;">{item["id"]} {item["name"]}</span>
                        <div>{lbl_html}</div>
                    </div>
                    <div style="color:#666; font-size:14px; margin-top:5px;">現價：{item["price"]:.2f} | 成交：{item["vol"]}張</div>
                </div>''', unsafe_allow_html=True)
                
                d = item['df']
                sh, ih, sl, il = item['lines']
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
                
                # K線
                fig.add_trace(go.Candlestick(x=d.index, open=d['Open'].values.flatten(), high=d['High'].values.flatten(), 
                                            low=d['Low'].values.flatten(), close=d['Close'].values.flatten(),
                    increasing_line_color='#ff4d4d', decreasing_line_color='#00b050', name="K線"), row=1, col=1)
                
                # 趨勢線
                xv = np.arange(30)
                fig.add_trace(go.Scatter(x=d.index[-30:], y=sh*xv + ih, line=dict(color='red', width=2, dash='dash'), name="壓力"), row=1, col=1)
                fig.add_trace(go.Scatter(x=d.index[-30:], y=sl*xv + il, line=dict(color='green', width=2, dash='dot'), name="支撐"), row=1, col=1)

                # 成交量
                colors = ['#ff4d4d' if c >= o else '#00b050' for o, c in zip(d['Open'].values.flatten(), d['Close'].values.flatten())]
                fig.add_trace(go.Bar(x=d.index, y=d['Volume'].values.flatten(), marker_color=colors, name="成交量"), row=2, col=1)

                fig.update_layout(height=450, template="plotly_white", xaxis_rangeslider_visible=False, showlegend=False, margin=dict(l=10,r=10,t=10,b=10))
                st.plotly_chart(fig, use_container_width=True, key=f"f_{item['id']}")
    else:
        st.warning("💡 未找到符合條件的數據，請確認代號是否正確或調整過濾設定。")
