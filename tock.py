import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import sys, requests, json, os

# ==========================================
# 系統與資料庫設定
# ==========================================
IS_STREAMLIT = "streamlit" in sys.argv[0] or any("streamlit" in arg for arg in sys.argv)
DB_FILE = "taiwan_full_market.json"

@st.cache_data(ttl=3600)
def load_db():
    if not os.path.exists(DB_FILE): return {"2330.TW": "台積電"}
    with open(DB_FILE, 'r', encoding='utf-8') as f: return json.load(f)

# ==========================================
# 核心形態分析邏輯 (封裝成通用函數)
# ==========================================
def run_analysis(df, sid, name, config):
    """
    通用分析器：輸入數據與配置，輸出判斷結果
    """
    if len(df) < 35: return None
    
    # 基礎指標
    close_val = df['Close'].iloc[-1]
    ma20_val = df['Close'].rolling(window=20).mean().iloc[-1]
    vol_last = df['Volume'].iloc[-1]
    vol_avg = df['Volume'].iloc[-21:-1].mean()
    
    # MA20 門檻檢查
    if config['f_ma20'] and close_val < ma20_val: return None
    
    # 趨勢線計算 (最近 15 天)
    d_len = 15
    x = np.arange(d_len)
    h_seg = df['High'].iloc[-d_len:].values.astype(float)
    l_seg = df['Low'].iloc[-d_len:].values.astype(float)
    sh, ih, _, _, _ = linregress(x, h_seg)
    sl, il, _, _, _ = linregress(x, l_seg)
    
    hits = []
    # 1. 三角收斂 (壓力下壓，支撐上揚)
    if config['f_tri'] and (sh < -0.002 and sl > 0.002): hits.append("📐 三角收斂")
    # 2. 箱型整理 (斜率接近水平)
    if config['f_box'] and (abs(sh) < 0.015 and abs(sl) < 0.015): hits.append("📦 箱型整理")
    # 3. 今日爆量 (成交量 > 20日均量 2倍)
    if config['f_vol'] and (vol_last > vol_avg * 2): hits.append("🚀 今日爆量")
    
    if not hits: return None
    
    return {
        "sid": sid, "name": name, "price": round(close_val, 2),
        "vol": int(vol_last // 1000), "hits": hits, 
        "df": df, "lines": (sh, ih, sl, il, x)
    }

# ==========================================
# UI 介面設計 (左側完全分流)
# ==========================================
if IS_STREAMLIT:
    st.set_page_config(page_title="台股 Pro 雙模式掃描", layout="wide")
    db = load_db()

    with st.sidebar:
        st.title("🏹 策略控制台")
        mode = st.radio("選擇模式", ["⚡ 自動全市場掃描", "⏳ 歷史手動搜尋", "⚙️ 資料庫維護"])
        st.divider()
        
        # 根據模式顯示對應的 Checkbox (雖然邏輯一樣，但控制變數分開)
        st.subheader("形態過濾 (通用)")
        f_tri = st.checkbox("📐 三角收斂", value=True, key=f"{mode}_tri")
        f_box = st.checkbox("📦 箱型整理", value=True, key=f"{mode}_box")
        f_vol = st.checkbox("🚀 今日爆量", value=True, key=f"{mode}_vol")
        f_ma20 = st.checkbox("📈 股價 > MA20", value=True, key=f"{mode}_ma")
        
        config = {"f_tri": f_tri, "f_box": f_box, "f_vol": f_vol, "f_ma20": f_ma20}
        
        st.divider()
        if mode == "⚡ 自動全市場掃描":
            min_v = st.number_input("最低成交量 (張)", value=1500, step=500)
            scan_limit = st.slider("掃描前 N 檔熱門股", 50, 500, 200)
        elif mode == "⏳ 歷史手動搜尋":
            sid_input = st.text_input("輸入股票代碼 (例: 2330)", value="2330")

    # ==========================================
    # 右側主內容顯示
    # ==========================================
    if mode == "⚡ 自動全市場掃描":
        st.title("自動全市場形態監控")
        if st.button("🚀 啟動掃描", type="primary", use_container_width=True):
            all_codes = list(db.keys())
            with st.status("掃描中...", expanded=True) as status:
                # 篩選量能
                v_data = yf.download(all_codes, period="1d", progress=False, threads=True)['Volume']
                latest_v = (v_data.iloc[-1] / 1000).dropna()
                targets = latest_v[latest_v >= min_v].sort_values(ascending=False).head(scan_limit).index.tolist()
                
                # 深度分析
                h_data = yf.download(targets, period="4mo", group_by='ticker', progress=False, threads=True)
                results = []
                for sid in targets:
                    df = h_data[sid].dropna()
                    res = run_analysis(df, sid, db.get(sid, ""), config)
                    if res: results.append(res)
                status.update(label=f"✅ 完成！找到 {len(results)} 檔符合標的", state="complete")

            # 顯示
            for item in results:
                st.subheader(f"{item['sid']} {item['name']}")
                st.write(f"現價: {item['price']} | 成交量: {item['vol']}張 | 形態: {', '.join(item['hits'])}")
                with st.expander("查看圖表"):
                    fig = go.Figure(data=[go.Candlestick(x=item['df'].index, open=item['df']['Open'], high=item['df']['High'], low=item['df']['Low'], close=item['df']['Close'])])
                    sh, ih, sl, il, xr = item['lines']
                    fig.add_trace(go.Scatter(x=item['df'].tail(15).index, y=sh*xr+ih, line=dict(color='red', dash='dash')))
                    fig.add_trace(go.Scatter(x=item['df'].tail(15).index, y=sl*xr+il, line=dict(color='green', dash='dash')))
                    fig.update_layout(height=400, template="plotly_dark", xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)

    elif mode == "⏳ 歷史手動搜尋":
        st.title("單一標的歷史診斷")
        if sid_input:
            full_sid = sid_input.upper() + (".TW" if "." not in sid_input else "")
            df = yf.download(full_sid, period="1y", progress=False)
            if not df.empty:
                res = run_analysis(df, full_sid, db.get(full_sid, "手動輸入"), config)
                if res:
                    st.success(f"符合標的形態：{', '.join(res['hits'])}")
                    # 顯示圖表邏輯 (同上)
                    fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
                    sh, ih, sl, il, xr = res['lines']
                    fig.add_trace(go.Scatter(x=df.tail(15).index, y=sh*xr+ih, line=dict(color='red', dash='dash')))
                    fig.add_trace(go.Scatter(x=df.tail(15).index, y=sl*xr+il, line=dict(color='green', dash='dash')))
                    fig.update_layout(height=500, template="plotly_dark", xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("該標的在當前設定下不符合任何勾選的形態。")
            else:
                st.error("找不到該股票代碼。")

    elif mode == "⚙️ 資料庫維護":
        st.title("系統維護")
        if st.button("🔄 同步全台股資料庫", use_container_width=True):
            st.info("執行中...")
