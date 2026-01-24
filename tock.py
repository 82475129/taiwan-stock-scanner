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
    """靜默抓取全台股 2000 檔代碼，確保掃描分母正確"""
    codes = {}
    try:
        for s_id in range(1, 34):
            for ex in ["TAI", "TWO"]:
                r = requests.get(f"https://tw.stock.yahoo.com/class-quote?sectorId={s_id}&exchange={ex}", timeout=5)
                soup = BeautifulSoup(r.text, "html.parser")
                for li in soup.find_all("li", class_="List(n)"):
                    sid = li.find("span", string=re.compile(r"\d{4}\.(TW|TWO)"))
                    sn = li.find("div", class_="Lh(20px) Fw(600) Fz(16px) Ell")
                    if sid and sn: codes[sid.text.strip()] = sn.text.strip()
    except:
        pass
    return codes


def _analyze_pattern(df, patterns=[]):
    """形態演算法核心：計算趨勢線與爆量"""
    d = df.tail(30)
    x = np.arange(len(d))
    h, l, c, v = d['High'].values.flatten(), d['Low'].values.flatten(), d['Close'].values.flatten(), d[
        'Volume'].values.flatten()
    sh, ih, _, _, _ = linregress(x, h)
    sl, il, _, _, _ = linregress(x, l)

    is_vol = v[-1] > (v[-6:-1].mean() * 1.5)
    is_tri = sh < -0.01 and sl > 0.01 and c[-1] > (sh * 29 + ih)

    found_labels = []
    if "三角系" in patterns and is_tri: found_labels.append("📐 三角形態")
    if is_vol: found_labels.append("🚀 爆量突破")
    return (", ".join(found_labels) if found_labels else None, (sh, ih, sl, il))


# --- [ 2. 視覺介面樣式 ] ---
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

# --- [ 3. 側邊決策中心 ] ---
with st.sidebar:
    st.markdown("## 🎯 決策中心")

    # 自動監控：獨立於表單外，切換即生效
    st.write("### 📡 監控狀態")
    auto_monitor = st.toggle("開啟自動監控", value=True)
    if auto_monitor:
        st.markdown('<div class="monitor-on">自動監控已啟動</div>', unsafe_allow_html=True)
        st_autorefresh(interval=300000, key="auto_pilot")  # 五分鐘定時刷新

    # 手動設定區：使用 Form 封裝防止勾選時自動觸發
    with st.form("manual_scan_form"):
        st.write("### 🔍 個股快查")
        input_sid = st.text_input("輸入股票代號", placeholder="例如: 2330")
        pop_sel = st.multiselect("熱門觀察清單", ["2330 台積電", "2317 鴻海", "2603 長榮", "2454 聯發科"])

        st.divider()
        st.write("### 🧪 形態偵測設定")
        m1 = st.checkbox("三角系 (對稱/擴散/下降)", value=True)
        m2 = st.checkbox("旗箱系 (矩形/上升旗)", value=False)
        m3 = st.checkbox("反轉系 (M頭/頭肩頂/倒V)", value=False)

        st.write("### ⚙️ 進階篩選器")
        scan_limit = st.slider("掃描標的數", 10, 2000, 2000)
        min_v = st.number_input("最低成交量 (張)", value=1000)
        ma_on = st.toggle("多頭排列 (站上 20MA)", value=True)

        # 點擊此按鈕才會啟動手動掃描任務
        manual_btn = st.form_submit_button("🚀 開始深度掃描", use_container_width=True, type="primary")

    if st.button("🔄 重新整理資料庫", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- [ 4. 核心執行邏輯：模式分離 ] ---
st.markdown("## 📈 台股 Pro-X 形態大師")
st.markdown(
    '<div style="background-color: #d1e7ff; color: #004085; padding: 12px; border-radius: 5px; margin-bottom: 20px;">💡 <b>操作說明：</b>左側勾選已鎖定。自動監控會每5分鐘巡航一次；若想立即按最新條件掃描，請點擊「開始深度掃描」。</div>',
    unsafe_allow_html=True)

# 觸發條件判定
run_scan = False
if auto_monitor or manual_btn or input_sid or pop_sel:
    run_scan = True

if run_scan:
    with st.status(f"🔍 {'全市場巡航中' if auto_monitor else '手動深度分析中'}...", expanded=True) as status:
        results = []
        market_data = _engine_core_fetch()

        # 整合手動觀察清單
        manual_targets = [f"{input_sid}.TW"] if input_sid else []
        for p in pop_sel: manual_targets.append(f"{p.split(' ')[0]}.TW")

        targets = list(market_data.items())[:scan_limit]
        active_p = ["三角系"] if m1 else []
        if m2: active_p.append("旗箱系")
        if m3: active_p.append("反轉系")

        for i, (sid, sname) in enumerate(targets):
            status.update(label=f"正在分析標的: {sid} ({i + 1}/{len(targets)})")
            try:
                is_manual = sid in manual_targets
                df = yf.download(sid, period="60d", progress=False)
                if df.empty or len(df) < 30: continue

                vol = int(df['Volume'].iloc[-1].values[0] / 1000)
                # 過濾器：手動指定的股票不被成交量與均線擋掉
                if not is_manual:
                    if vol < min_v: continue
                    if ma_on and df['Close'].iloc[-1].values[0] < df['Close'].rolling(20).mean().iloc[-1].values[
                        0]: continue

                # 執行形態分析
                res_label, lines = _analyze_pattern(df, patterns=active_p)

                if res_label or is_manual:
                    results.append(
                        {"id": sid, "name": sname, "df": df.tail(30), "lines": lines, "res": res_label or "觀察標的",
                         "price": df['Close'].iloc[-1].values[0], "vol": vol})
            except:
                continue
        status.update(label="✅ 本次掃描任務完成", state="complete", expanded=False)

    # --- [ 5. 掃描結果視覺化 ] ---
    if results:
        cols = st.columns(2)
        for idx, item in enumerate(results):
            with cols[idx % 2]:
                st.markdown(
                    f'<div class="stock-card"><div style="display:flex; justify-content:space-between;"><b>{item["id"]} {item["name"]}</b> <span class="tag-found">{item["res"]}</span></div>現價：{item["price"]:.2f} | 成交：{item["vol"]}張</div>',
                    unsafe_allow_html=True)

                fig = go.Figure(data=[
                    go.Candlestick(x=item['df'].index, open=item['df']['Open'], high=item['df']['High'],
                                   low=item['df']['Low'], close=item['df']['Close'])])
                d, (sh, ih, sl, il) = item['df'], item['lines']
                xv = np.arange(len(d))
                fig.add_trace(
                    go.Scatter(x=d.index, y=sh * xv + ih, line=dict(color='#ff7675', dash='dot'), name="壓力線"))
                fig.add_trace(
                    go.Scatter(x=d.index, y=sl * xv + il, line=dict(color='#55efc4', dash='dot'), name="支撐線"))
                fig.update_layout(height=320, template="plotly_white", xaxis_rangeslider_visible=False,
                                  margin=dict(l=0, r=0, t=0, b=0))
                st.plotly_chart(fig, use_container_width=True, key=f"c_{item['id']}")
    else:
        st.info("💡 目前全市場巡航中未發現符合條件標的。")
