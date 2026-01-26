import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import sys, requests, json, os

# ==========================================
# 0. 系統基礎設定
# ==========================================
IS_STREAMLIT = "streamlit" in sys.argv[0] or any("streamlit" in arg for arg in sys.argv)
DB_FILE = "taiwan_full_market.json"

if IS_STREAMLIT:
    st.set_page_config(page_title="台股策略分析終端", layout="wide")

@st.cache_data(ttl=3600)
def load_db():
    if not os.path.exists(DB_FILE): return {"2330.TW": "台積電"}
    with open(DB_FILE, 'r', encoding='utf-8') as f: return json.load(f)

# 形態分析引擎
def run_analysis(df, sid, name, config):
    if df is None or len(df) < 35: return None
    try:
        c = df['Close'].iloc[-1]
        m20 = df['Close'].rolling(window=20).mean().iloc[-1]
        v_last = df['Volume'].iloc[-1]
        v_avg = df['Volume'].iloc[-21:-1].mean()
        
        # MA20 過濾
        if config['f_ma20'] and c < m20: return None
        
        # 趨勢線
        d_len = 15
        x = np.arange(d_len)
        h, l = df['High'].iloc[-d_len:].values.astype(float), df['Low'].iloc[-d_len:].values.astype(float)
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        
        hits = []
        if config['f_tri'] and (sh < -0.002 and sl > 0.002): hits.append("📐 三角收斂")
        if config['f_box'] and (abs(sh) < 0.015 and abs(sl) < 0.015): hits.append("📦 箱型整理")
        if config['f_vol'] and (v_last > v_avg * 2.0): hits.append("🚀 今日爆量")
        
        if not hits: return None
        return {"sid": sid, "name": name, "price": round(c, 2), "hits": hits, "df": df, "lines": (sh, ih, sl, il, x)}
    except: return None

# ==========================================
# 1. 介面設計 (預設開關為 OFF)
# ==========================================
if IS_STREAMLIT:
    db = load_db()
    with st.sidebar:
        st.title("🏹 策略控制台")
        mode = st.radio("功能選擇", ["⚡ 自動全市場監控", "⏳ 歷史手動搜尋"], key="main_mode")
        st.divider()
        
        # --- 預設開關全部設為關閉 (False) ---
        st.subheader("形態過濾設定")
        f_tri = st.checkbox("📐 三角收斂", value=False, key=f"{mode}_tri")
        f_box = st.checkbox("📦 箱型整理", value=False, key=f"{mode}_box")
        f_vol = st.checkbox("🚀 今日爆量", value=False, key=f"{mode}_vol")
        f_ma20 = st.checkbox("📈 股價 > MA20", value=False, key=f"{mode}_ma")
        
        config = {"f_tri": f_tri, "f_box": f_box, "f_vol": f_vol, "f_ma20": f_ma20}
        
        st.divider()
        if mode == "⚡ 自動全市場監控":
            min_v = st.number_input("成交量門檻 (張)", value=2000, step=500)
            scan_limit = st.slider("掃描上限", 50, 200, 100)
            # 只有點擊按鈕才執行，防止自動載入白屏
            run_btn = st.button("🚀 啟動掃描", type="primary", use_container_width=True)
        else:
            sid_input = st.text_input("輸入代碼", value="2330")
            run_btn = st.button("🔍 執行分析", type="primary", use_container_width=True)

    # --- 右側主內容 ---
    if mode == "⚡ 自動全市場監控":
        st.header("⚡ 市場形態雷達")
        
        # 檢查是否有勾選任何形態，且按鈕已按下
        if run_btn:
            if not any([f_tri, f_box, f_vol]):
                st.warning("請至少勾選一種形態過濾器 (左側 Checkbox) 再執行掃描。")
            else:
                all_codes = list(db.keys())
                with st.status("🔍 掃描中...", expanded=True) as status:
                    # 快速篩量
                    v_data = yf.download(all_codes, period="1d", progress=False, threads=True)['Volume']
                    latest_v = (v_data.iloc[-1] / 1000).dropna()
                    targets = latest_v[latest_v >= min_v].sort_values(ascending=False).head(scan_limit).index.tolist()
                    
                    # 形態分析
                    h_data = yf.download(targets, period="3mo", group_by='ticker', progress=False, threads=True)
                    results = []
                    for sid in targets:
                        res = run_analysis(h_data[sid].dropna(), sid, db.get(sid, ""), config)
                        if res: results.append(res)
                    status.update(label=f"✅ 完成！找到 {len(results)} 檔符合標的", state="complete")

                # 顯示結果 (略...)
                if results:
                    for item in results:
                        with st.expander(f"{item['sid']} {item['name']}", expanded=True):
                            st.write(f"現價: {item['price']} | 形態: {', '.join(item['hits'])}")
                            # (繪圖邏輯...)
                            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("👋 歡迎使用！請在左側勾選想要偵測的形態，然後點擊「啟動掃描」。")

    elif mode == "⏳ 歷史手動搜尋":
        # (手動搜尋邏輯，同樣改為點擊按鈕才執行)
        if run_btn and sid_input:
            st.write(f"正在分析 {sid_input}...")
            # ...分析邏輯...
