import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import sys, requests, json, os

# ==========================================
# 0. 基礎設定與容錯處理
# ==========================================
IS_STREAMLIT = "streamlit" in sys.argv[0] or any("streamlit" in arg for arg in sys.argv)
DB_FILE = "taiwan_full_market.json"

# 強制讓 Streamlit 頁面先出來
if IS_STREAMLIT:
    st.set_page_config(page_title="台股 Pro 雙模式監控", layout="wide")

def load_db():
    if not os.path.exists(DB_FILE):
        return {"2330.TW": "台積電"}
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"2330.TW": "台積電"}

# 分析核心
def run_analysis(df, sid, name, config):
    if df is None or len(df) < 35: return None
    try:
        c = df['Close'].iloc[-1]
        m20 = df['Close'].rolling(window=20).mean().iloc[-1]
        v_last = df['Volume'].iloc[-1]
        v_avg = df['Volume'].iloc[-21:-1].mean()
        
        if config['f_ma20'] and c < m20: return None
        
        d_len = 15
        x = np.arange(d_len)
        h, l = df['High'].iloc[-d_len:].values.astype(float), df['Low'].iloc[-d_len:].values.astype(float)
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        
        hits = []
        if config['f_tri'] and (sh < -0.002 and sl > 0.002): hits.append("📐 三角收斂")
        if config['f_box'] and (abs(sh) < 0.015 and abs(sl) < 0.015): hits.append("📦 箱型整理")
        if config['f_vol'] and (v_last > v_avg * 2): hits.append("🚀 今日爆量")
        
        if not hits: return None
        return {"sid": sid, "name": name, "price": round(c, 2), "hits": hits, "df": df, "lines": (sh, ih, sl, il, x)}
    except: return None

# ==========================================
# 1. 介面設計 (左側完全分流)
# ==========================================
if IS_STREAMLIT:
    db = load_db()
    with st.sidebar:
        st.title("🏹 策略控制台")
        mode = st.radio("功能切換", ["⚡ 自動掃描", "⏳ 歷史搜尋", "⚙️ 設定"], key="main_mode")
        st.divider()
        
        # 使用相同的配置但不同的控制邏輯
        st.subheader("形態過濾器")
        f_tri = st.checkbox("📐 三角收斂", value=True, key=f"{mode}_tri")
        f_box = st.checkbox("📦 箱型整理", value=True, key=f"{mode}_box")
        f_vol = st.checkbox("🚀 今日爆量", value=True, key=f"{mode}_vol")
        f_ma20 = st.checkbox("📈 站上 MA20", value=True, key=f"{mode}_ma")
        config = {"f_tri": f_tri, "f_box": f_box, "f_vol": f_vol, "f_ma20": f_ma20}

        st.divider()
        if mode == "⚡ 自動掃描":
            min_v = st.number_input("最低成交量 (張)", value=1500, step=500)
            scan_limit = st.slider("掃描前 N 檔", 50, 300, 150)
            go_btn = st.button("🚀 執行自動掃描", type="primary", use_container_width=True)
        elif mode == "⏳ 歷史搜尋":
            sid_input = st.text_input("輸入代碼 (2330)", "2330")
            go_btn = st.button("🔍 執行搜尋分析", type="primary", use_container_width=True)
        else:
            go_btn = False

    # 右側顯示區
    if mode == "⚡ 自動掃描":
        st.title("自動全市場雷達")
        if go_btn:
            all_codes = list(db.keys())
            with st.status("⚡ 快速篩選中...", expanded=True) as s:
                v_data = yf.download(all_codes, period="1d", progress=False, threads=True)['Volume']
                latest_v = (v_data.iloc[-1] / 1000).dropna()
                targets = latest_v[latest_v >= min_v].sort_values(ascending=False).head(scan_limit).index.tolist()
                
                h_data = yf.download(targets, period="3mo", group_by='ticker', progress=False, threads=True)
                res_list = []
                for sid in targets:
                    res = run_analysis(h_data[sid].dropna(), sid, db.get(sid, ""), config)
                    if res: res_list.append(res)
                s.update(label=f"✅ 找到 {len(res_list)} 檔符合標的", state="complete")
            
            for item in res_list:
                with st.expander(f"【{item['sid']} {item['name']}】 - {', '.join(item['hits'])}", expanded=True):
                    st.write(f"現價: {item['price']} | 形態: {', '.join(item['hits'])}")
                    d_p = item['df'].tail(30)
                    sh, ih, sl, il, xr = item['lines']
                    fig = go.Figure(data=[go.Candlestick(x=d_p.index, open=d_p['Open'], high=d_p['High'], low=d_p['Low'], close=d_p['Close'])])
                    fig.add_trace(go.Scatter(x=d_p.tail(15).index, y=sh*xr+ih, line=dict(color='red', dash='dash')))
                    fig.add_trace(go.Scatter(x=d_p.tail(15).index, y=sl*xr+il, line=dict(color='green', dash='dash')))
                    fig.update_layout(height=400, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=0,r=0,b=0,t=0))
                    st.plotly_chart(fig, use_container_width=True)

    elif mode == "⏳ 歷史搜尋":
        st.title("單一標的歷史診斷")
        if go_btn and sid_input:
            full_sid = sid_input.upper() + (".TW" if "." not in sid_input else "")
            df = yf.download(full_sid, period="1y", progress=False)
            res = run_analysis(df, full_sid, db.get(full_sid, "手動輸入"), config)
            if res:
                st.subheader(f"{res['sid']} {res['name']}")
                st.success(f"符合形態：{', '.join(res['hits'])}")
                fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
                sh, ih, sl, il, xr = res['lines']
                fig.add_trace(go.Scatter(x=df.tail(15).index, y=sh*xr+ih, line=dict(color='red', dash='dash')))
                fig.add_trace(go.Scatter(x=df.tail(15).index, y=sl*xr+il, line=dict(color='green', dash='dash')))
                fig.update_layout(height=500, template="plotly_dark", xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("該標的不符合當前勾選的形態。")
