import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
from streamlit_autorefresh import st_autorefresh
import json, os

# ==========================================
# 0. 真實數據載入邏輯
# ==========================================
DB_FILE = "taiwan_electronic_stocks.json"

@st.cache_data(show_spinner=False)
def get_full_stock_list():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data: return data
        except: pass
    return {} # 若無數據則回傳空，導致介面顯示錯誤警告

db = get_full_stock_list()

# ==========================================
# 1. 形態分析引擎
# ==========================================
def analyze_patterns(df, config, days=15):
    if df is None or len(df) < 30: return None
    try:
        df['MA20'] = df['Close'].rolling(window=20).mean()
        p_now, m_now = float(df['Close'].iloc[-1]), float(df['MA20'].iloc[-1])
        if config.get('use_ma') and p_now < m_now: return None

        d = df.tail(days).copy()
        h, l, v = d['High'].values.astype(float), d['Low'].values.astype(float), d['Volume'].values.astype(float)
        x = np.arange(len(h))
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        v_m = df['Volume'].iloc[-21:-1].mean()
        
        hits = []
        if config.get('tri') and (sh < -0.003 and sl > 0.003): hits.append({"text": "📐 三角收斂", "class": "badge-tri"})
        if config.get('box') and (abs(sh) < 0.03 and abs(sl) < 0.03): hits.append({"text": "📦 旗箱整理", "class": "badge-box"})
        if config.get('vol') and (v[-1] > v_m * 1.5): hits.append({"text": "🚀 今日爆量", "class": "badge-vol"})
        
        if not hits: return None
        return {"labels": hits, "lines": (sh, ih, sl, il, x), "price": round(p_now, 2), "ma20": round(m_now, 2), "prev_close": float(df['Close'].iloc[-2]), "vol": int(v[-1] // 1000)}
    except: return None

# ==========================================
# 2. 介面設計
# ==========================================
st.set_page_config(page_title="台股 Pro-X 形態大師", layout="wide")
st.markdown("""<style>.stApp { background-color: #f4f7f6; }.stock-card { background: white; padding: 20px; border-radius: 12px; margin-bottom: 20px; border-left: 8px solid #6c5ce7; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }.badge { padding: 4px 10px; border-radius: 6px; font-size: 0.8rem; font-weight: bold; margin-right: 5px; color: white; }.badge-tri { background-color: #6c5ce7; }.badge-box { background-color: #2d3436; }.badge-vol { background-color: #d63031; }</style>""", unsafe_allow_html=True)

with st.sidebar:
    st.title("🎯 形態大師控制台")
    if not db:
        st.error("⚠️ 無真實數據！請檢查 JSON 檔案或執行爬蟲。")
    else:
        st.success(f"📁 已載入：{len(db)} 檔真實電子股")
    
    mode = st.radio("功能模式", ["⚡ 即時監控", "⏳ 歷史搜尋"])
    st.divider()
    
    if "⚡" in mode:
        st_autorefresh(interval=300000, key="auto_refresh")
        f_ma = st.checkbox("股價在 MA20 之上", value=True)
        t_tri = st.checkbox("📐 三角收斂", value=True)
        t_box = st.checkbox("📦 旗箱整理", value=True)
        t_vol = st.checkbox("🚀 今日爆量", value=True)
        t_min_v = st.number_input("最低成交量(張)", value=500)
        config = {'tri': t_tri, 'box': t_box, 'vol': t_vol, 'use_ma': f_ma}
        run = True
    else:
        h_sid = st.text_input("輸入股票代號")
        config = {'tri': True, 'box': True, 'vol': True, 'use_ma': False}
        run = st.button("🚀 開始掃描", type="primary")

# ==========================================
# 3. 掃描與結果 (使用 st.status)
# ==========================================
st.title("台股 Pro-X 形態大師")

if run and db:
    targets = [(f"{h_sid.upper()}.TW", h_sid.upper())] if ("⏳" in mode and h_sid) else list(db.items())
    final_results = []
    
    with st.status("🔍 市場形態深度掃描中...", expanded=True) as status:
        p_bar = st.progress(0)
        chunk_size = 40
        
        for i in range(0, len(targets), chunk_size):
            p_bar.progress(i / len(targets))
            chunk = targets[i : i + chunk_size]
            t_list = [t[0] for t in chunk]
            
            try:
                data = yf.download(t_list, period="2mo", group_by='ticker', progress=False)
                for sid, name in chunk:
                    try:
                        df_s = data[sid].dropna() if len(t_list) > 1 else data.dropna()
                        res = analyze_patterns(df_s, config)
                        if res and (not "⚡" in mode or res['vol'] >= t_min_v):
                            res.update({"sid": sid, "name": name, "df": df_s})
                            final_results.append(res)
                    except: continue
            except: continue
        p_bar.empty()
        status.update(label=f"✅ 掃描完成！找到 {len(final_results)} 檔標的", state="complete", expanded=False)

    if final_results:
        for item in final_results:
            p_color = "#d63031" if item['price'] >= item['prev_close'] else "#27ae60"
            b_html = "".join([f'<span class="badge {l["class"]}">{l["text"]}</span>' for l in item['labels']])
            st.markdown(f"""<div class="stock-card"><b>{item['sid']} {item['name']}</b> <span style="color:{p_color}; float:right; font-size:1.2rem;">${item['price']}</span><br><small>量: {item['vol']}張 | MA20: {item['ma20']}</small><br>{b_html}</div>""", unsafe_allow_html=True)
            with st.expander("📈 展開 K 線圖"):
                d_p = item['df'].tail(30)
                sh, ih, sl, il, x_r = item['lines']
                fig = go.Figure(data=[go.Candlestick(x=d_p.index, open=d_p['Open'], high=d_p['High'], low=d_p['Low'], close=d_p['Close'])])
                fig.add_trace(go.Scatter(x=d_p.tail(15).index, y=sh*x_r+ih, line=dict(color='#ff4757', dash='dash')))
                fig.add_trace(go.Scatter(x=d_p.tail(15).index, y=sl*x_r+il, line=dict(color='#2ed573', dash='dot')))
                fig.update_layout(height=400, template="plotly_white", showlegend=False, xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("💡 目前無符合形態的股票。")
