import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import re
from bs4 import BeautifulSoup
from scipy.stats import linregress
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# ---------------- [1] 股市資料抓取引擎 ----------------
@st.cache_data(ttl=3600, show_spinner=False)
def _engine_core_fetch():
    """抓取全台股 2000 檔代碼與名稱"""
    codes = {}
    try:
        for s_id in range(1, 34):
            for ex in ["TAI", "TWO"]:
                r = requests.get(f"https://tw.stock.yahoo.com/class-quote?sectorId={s_id}&exchange={ex}", timeout=5)
                soup = BeautifulSoup(r.text, "html.parser")
                for li in soup.find_all("li", class_="List(n)"):
                    sid = li.find("span", string=re.compile(r"\d{4}\.(TW|TWO)"))
                    sn = li.find("div", class_="Lh(20px) Fw(600) Fz(16px) Ell")
                    if sid and sn:
                        codes[sid.text.strip()] = sn.text.strip()
    except:
        pass
    return codes

# ---------------- [2] 形態分析函數 ----------------
def _analyze_pattern(df):
    """計算三角收斂與爆量突破"""
    d = df.tail(30)
    x = np.arange(len(d))
    h, l, c, v = d['High'].values.flatten(), d['Low'].values.flatten(), d['Close'].values.flatten(), d['Volume'].values.flatten()

    sh, ih, _, _, _ = linregress(x, h)
    sl, il, _, _, _ = linregress(x, l)

    is_vol = v[-1] > (v[-6:-1].mean() * 1.5)
    is_tri = sh < -0.01 and sl > 0.01 and c[-1] > (sh * 29 + ih)

    labels = []
    if is_tri: labels.append("📐 三角形態")
    if is_vol: labels.append("🚀 爆量突破")

    return ", ".join(labels) if labels else None, (sh, ih, sl, il), is_tri, is_vol

# ---------------- [3] 介面樣式 ----------------
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

# ---------------- [4] 側邊決策中心 ----------------
with st.sidebar:
    st.markdown("## 🎯 決策中心")
    st.write("### 📡 自動監控狀態")

    # 顯示條件
    auto_tri = st.checkbox("📐 只顯示三角形態（不管有沒有爆量）", value=True)
    auto_vol = st.checkbox("🚀 只顯示爆量突破（不管有沒有三角）", value=True)
    auto_both = st.checkbox("🔺🚀 同時滿足三角 + 爆量才顯示", value=False)
    auto_any = st.checkbox("📐 或 🚀 只要有任一就顯示（OR）", value=False)
    auto_monitor = st.toggle("開啟自動監控", value=True)

    if auto_monitor:
        selected_modes = []
        if auto_tri: selected_modes.append("📐 三角形態")
        if auto_vol: selected_modes.append("🚀 爆量突破")
        if auto_both: selected_modes.append("🔺🚀 三角+爆量")
        if auto_any: selected_modes.append("📐 或 🚀 任一")
        mode_text = "<br>顯示條件：" + "　＋　".join(selected_modes) if selected_modes else "未選擇條件"
        st.markdown(f'<div class="monitor-on">自動監控已啟動<br>{mode_text}</div>', unsafe_allow_html=True)
        st_autorefresh(interval=300000, key="auto_pilot")  # 5分鐘刷新

    # 手動掃描
    with st.form("manual_scan_form"):
        st.write("### 🔍 個股快查")
        input_sid = st.text_input("輸入股票代號", placeholder="例如: 2330")
        pop_sel = st.multiselect("熱門觀察清單", ["2330 台積電", "2317 鴻海", "2603 長榮", "2454 聯發科"])
        st.divider()
        st.write("### 🧪 形態偵測設定（手動掃描用）")
        m1 = st.checkbox("三角系", value=True)
        m2 = st.checkbox("旗箱系", value=False)
        m3 = st.checkbox("反轉系", value=False)
        st.write("### ⚙️ 進階篩選器")
        scan_limit = st.slider("掃描標的數", 10, 2000, 2000)
        min_v = st.number_input("最低成交量 (張)", value=1000)
        ma_on = st.toggle("多頭排列 (站上 20MA)", value=True)
        manual_btn = st.form_submit_button("🚀 開始深度掃描", use_container_width=True, type="primary")

    if st.button("🔄 重新整理資料庫", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ---------------- [5] 主畫面 ----------------
st.markdown("## 📈 台股 Pro-X 形態大師")
st.markdown('<div style="background-color: #d1e7ff; color: #004085; padding: 12px; border-radius: 5px; margin-bottom: 20px;">💡 <b>操作說明：</b>自動監控每5分鐘巡航一次，可自由選擇要顯示哪種形態結果；手動掃描請點下方按鈕。</div>', unsafe_allow_html=True)

run_scan = auto_monitor or manual_btn or input_sid or pop_sel

if run_scan:
    with st.status(f"🔍 {'全市場巡航中' if auto_monitor else '手動深度分析中'}...", expanded=True) as status:
        results = []
        market_data = _engine_core_fetch()
        manual_targets = [f"{input_sid}.TW"] if input_sid else []
        for p in pop_sel:
            manual_targets.append(f"{p.split(' ')[0]}.TW")

        targets = list(market_data.items())[:scan_limit]

        for i, (sid, sname) in enumerate(targets):
            status.update(label=f"正在分析標的: {sid} ({i+1}/{len(targets)})")
            try:
                is_manual = sid in manual_targets
                df = yf.download(sid, period="60d", progress=False)
                if df.empty or len(df) < 30: continue

                vol = int(df['Volume'].iloc[-1] / 1000)
                if not is_manual:
                    if vol < min_v: continue
                    if ma_on and df['Close'].iloc[-1] < df['Close'].rolling(20).mean().iloc[-1]: continue

                res_label, lines, has_tri, has_vol = _analyze_pattern(df)

                show_this = False
                if auto_monitor:
                    if auto_tri and has_tri: show_this = True
                    if auto_vol and has_vol: show_this = True
                    if auto_both and has_tri and has_vol: show_this = True
                    if auto_any and (has_tri or has_vol): show_this = True
                else:
                    show_this = bool(res_label) or is_manual

                if show_this:
                    display_label = res_label or "觀察標的"
                    results.append({
                        "id": sid,
                        "name": sname,
                        "df": df.tail(30),
                        "lines": lines,
                        "res": display_label,
                        "price": df['Close'].iloc[-1],
                        "vol": vol
                    })
            except:
                continue
        status.update(label="✅ 本次掃描任務完成", state="complete", expanded=False)

    # ---------------- [6] 結果可視化 (超漂亮趨勢圖) ----------------
    if results:
        cols = st.columns(2)
        for idx, item in enumerate(results):
            with cols[idx % 2]:
                st.markdown(
                    f'<div class="stock-card"><div style="display:flex; justify-content:space-between;"><b>{item["id"]} {item["name"]}</b> <span class="tag-found">{item["res"]}</span></div>現價：{item["price"]:.2f} | 成交：{item["vol"]}張</div>',
                    unsafe_allow_html=True
                )

                d, (sh, ih, sl, il) = item['df'], item['lines']
                xv = np.arange(len(d))
                fig = go.Figure()

                # K線
                fig.add_trace(go.Candlestick(
                    x=d.index,
                    open=d['Open'],
                    high=d['High'],
                    low=d['Low'],
                    close=d['Close'],
                    increasing_line_color='#00b894',
                    decreasing_line_color='#d63031',
                    increasing_fillcolor='rgba(0,184,148,0.3)',
                    decreasing_fillcolor='rgba(214,48,49,0.3)',
                    name='K線'
                ))

                # 壓力線
                fig.add_trace(go.Scatter(
                    x=d.index,
                    y=sh*xv + ih,
                    mode='lines',
                    line=dict(color='#0984e3', width=2, dash='dash'),
                    name='壓力線'
                ))

                # 支撐線
                fig.add_trace(go.Scatter(
                    x=d.index,
                    y=sl*xv + il,
                    mode='lines',
                    line=dict(color='#fdcb6e', width=2, dash='dash'),
                    name='支撐線'
                ))

                # 信號標註
                if item['res']:
                    fig.add_trace(go.Scatter(
                        x=[d.index[-1]],
                        y=[d['Close'].iloc[-1]],
                        mode='markers+text',
                        marker=dict(color='#6c5ce7', size=12, symbol='star'),
                        text=[item['res']],
                        textposition='top center',
                        name='信號點'
                    ))

                # 美化版面
                fig.update_layout(
                    height=360,
                    template='plotly_dark',
                    xaxis_title='日期',
                    yaxis_title='價格 (TWD)',
                    xaxis_rangeslider_visible=False,
                    margin=dict(l=5, r=5, t=25, b=5)
                )

                st.plotly_chart(fig, use_container_width=True, key=f"c_{item['id']}")
    else:
        st.info("💡 目前未發現符合您選擇顯示條件的標的。")
