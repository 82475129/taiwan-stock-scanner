import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
import yfinance as yf
import re
import time
import plotly.graph_objects as go
from scipy.stats import linregress

# --- 網頁配置 ---
st.set_page_config(page_title="台股全標的收斂掃描系統", layout="wide")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# --- 初始化數據存儲 ---
if 'saved_results' not in st.session_state:
    st.session_state.saved_results = None

# --- 側邊欄：功能按鈕 ---
with st.sidebar:
    st.header("📊 控制面板")
    st.write("點擊按鈕掃描全市場分類（包含集團股、電子、生技及所有冷門股）。")
    start_scan = st.button("🔄 立即執行全市場掃描", use_container_width=True)

    if st.session_state.saved_results:
        st.write(f"上次掃描發現: {len(st.session_state.saved_results)} 檔")

# --- 主畫面顯示 ---
st.title("🎯 台股三角收斂形態自動掃描")

if start_scan:
    st.session_state.saved_results = []  # 清空舊資料

    # 1. 抓取 Yahoo 產業分類連結
    try:
        base_url = "https://tw.stock.yahoo.com/class"
        r = requests.get(base_url, headers=HEADERS)
        soup = BeautifulSoup(r.text, "html.parser")
        links = soup.find_all("a", href=re.compile(r"class-quote\?"))
        # 遍歷主要分類 (包含您提到的 sectorId=7, 2 等)
        cat_urls = ["https://tw.stock.yahoo.com" + l['href'] for l in links][:30]

        all_target_stocks = {}
        status_msg = st.empty()
        status_msg.info("正在連線至 Yahoo 股市獲取標的名單...")

        # 2. 解析個股 (對應 Jc(fe) 結構)
        for url in cat_urls:
            try:
                res = requests.get(url, headers=HEADERS, timeout=5)
                s_soup = BeautifulSoup(res.text, "html.parser")
                items = s_soup.find_all("li", class_="List(n)")
                for li in items:
                    code_tag = li.find("span", string=re.compile(r"\d{4}\.(TW|TWO)"))
                    name_tag = li.find("div", class_="Lh(20px) Fw(600) Fz(16px) Ell")
                    if code_tag and name_tag:
                        all_target_stocks[code_tag.get_text(strip=True)] = name_tag.get_text(strip=True)
            except:
                continue

        # 3. 分析形態
        found_list = []
        progress_bar = st.progress(0)
        total_stocks = len(all_target_stocks)

        for i, (sid, sname) in enumerate(all_target_stocks.items()):
            status_msg.text(f"分析中 ({i + 1}/{total_stocks}): {sid} {sname}")
            try:
                df = yf.download(sid, period="40d", interval="1d", progress=False)
                if not df.empty and len(df) >= 20:
                    recent = df.tail(20)
                    x = np.arange(len(recent))
                    # 計算壓力與支撐斜率
                    sh, ih, _, _, _ = linregress(x, recent['High'].values.flatten())
                    sl, il, _, _, _ = linregress(x, recent['Low'].values.flatten())

                    # 判斷收斂
                    if sh < -0.01 and sl > 0.01:
                        last_c = recent['Close'].iloc[-1].values[0]
                        resistance = sh * 19 + ih
                        status = "🚀 向上突破" if last_c > resistance else "⏳ 盤整收斂"
                        found_list.append({
                            "代碼": sid, "名稱": sname, "現價": round(last_c, 2),
                            "狀態": status, "回歸數據": (sh, ih, sl, il, recent)
                        })
                time.sleep(0.02)
            except:
                continue
            progress_bar.progress((i + 1) / total_stocks)

        st.session_state.saved_results = found_list
        status_msg.success(f"掃描完成！共發現 {len(found_list)} 檔標的。")
        st.rerun()

    except Exception as e:
        st.error(f"掃描失敗: {e}")

# --- 結果呈現區 ---
if st.session_state.saved_results:
    # 數據總表
    display_df = pd.DataFrame(st.session_state.saved_results).drop(columns=['回歸數據'])
    st.subheader("📋 收斂形態追蹤清單")
    st.dataframe(display_df, use_container_width=True)

    st.divider()
    st.subheader("📊 個股技術圖解")

    # 雙欄位畫圖表
    chart_cols = st.columns(2)
    for idx, item in enumerate(
            st.session_state.results if hasattr(st.session_state, 'results') else st.session_state.saved_results):
        sh, ih, sl, il, data = item['回歸數據']
        with chart_cols[idx % 2]:
            with st.expander(f"{item['代碼']} {item['名稱']} - {item['狀態']}", expanded=True):
                fig = go.Figure()
                fig.add_trace(go.Candlestick(
                    x=data.index, open=data['Open'], high=data['High'],
                    low=data['Low'], close=data['Close'], name="K線"
                ))
                x_val = np.arange(len(data))
                # 繪製壓力/支撐線
                fig.add_trace(go.Scatter(x=data.index, y=sh * x_val + ih, name="壓力線",
                                         line=dict(color='red', width=2, dash='dot')))
                fig.add_trace(go.Scatter(x=data.index, y=sl * x_val + il, name="支撐線",
                                         line=dict(color='green', width=2, dash='dot')))

                fig.update_layout(height=400, showlegend=False, margin=dict(l=10, r=10, t=30, b=10))
                st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("目前暫無掃描名單。請點擊左側面板的「🔄 立即執行全市場掃描」按鈕。")