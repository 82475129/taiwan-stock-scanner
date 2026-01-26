import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
from streamlit_autorefresh import st_autorefresh
import json, os, requests, time
from bs4 import BeautifulSoup
from tqdm import tqdm

# ==========================================
# 配置與資料
# ==========================================
st.set_page_config(page_title="台股 Pro-X 形態大師", layout="wide")
DB_FILE = "taiwan_electronic_stocks.json"

# -----------------------------
# 抓取電子股資料
# -----------------------------
def fetch_electronic_stocks():
    SECTOR_MAP = {
        "TAI": {40: "半導體", 41: "電腦週邊", 42: "光電", 43: "通信網路",
                44: "電子零組件", 45: "電子通路", 46: "資訊服務", 47: "其他電子"},
        "TWO": {153: "半導體", 154: "電腦週邊", 155: "光電", 156: "通信網路",
                157: "電子零組件", 158: "電子通路", 159: "資訊服務", 160: "其他電子"}
    }
    db_result = {}
    headers = {'User-Agent': 'Mozilla/5.0'}

    for exchange, sectors in SECTOR_MAP.items():
        for sector_id, sector_name in sectors.items():
            url = f"https://tw.stock.yahoo.com/class-quote?sectorId={sector_id}&exchange={exchange}"
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(resp.text, 'html.parser')
                rows = soup.select('div[class*="table-row"]')
                for row in rows:
                    code_el = row.select_one('span[class*="C(#7c7e80)"]')
                    name_el = row.select_one('div[class*="Lh(20px)"]')
                    if code_el and name_el:
                        suffix = ".TW" if exchange == "TAI" else ".TWO"
                        db_result[f"{code_el.get_text(strip=True)}{suffix}"] = name_el.get_text(strip=True)
            except: continue
            time.sleep(0.2)
    # 儲存
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db_result, f, ensure_ascii=False, indent=2)
    return db_result

# -----------------------------
# 讀取資料，如果沒有自動抓
# -----------------------------
@st.cache_data(show_spinner=False)
def get_full_stock_list():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if len(data) > 0: return data
        except: pass
    return fetch_electronic_stocks()

db = get_full_stock_list()

# ==========================================
# 形態分析邏輯
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
# 介面
# ==========================================
st.markdown("""
<style>
.stApp { background-color: #f4f7f6; }
.stock-card { background: white; padding: 16px; border-radius: 12px; margin-bottom: 15px; border-left: 6px solid #6c5ce7; box-shadow: 0 4px 10px rgba(0,0,0,0.06); }
.badge { padding: 4px 10px; border-radius: 6px; font-size: 0.75rem; font-weight: bold; margin: 2px; color: white; display: inline-block; }
.badge-tri { background-color: #6c5ce7; }
.badge-box { background-color: #2d3436; }
.badge-vol { background-color: #d63031; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.title("🎯 形態大師控制台")
    st.success(f"📁 已載入：{len(db)} 檔電子股")

    # 手動更新按鈕
    if st.button("🔄 手動更新電子股清單"):
        with st.spinner("正在抓取最新電子股資料..."):
            db = fetch_electronic_stocks()
        st.success(f"✅ 完成更新！共 {len(db)} 檔電子股")

    selected_mode = st.radio("選擇模式", ["⚡ 今日即時監控 (自動)", "⏳ 歷史形態搜尋 (手動)", "🌐 所有股票連結"])
    st.divider()
    
    if "⚡" in selected_mode:
        st_autorefresh(interval=300000, key="auto_refresh")
        f_ma = st.checkbox("股價需在 20MA 之上", value=True)
        t_tri = st.checkbox("📐 三角收斂", value=True)
        t_box = st.checkbox("📦 旗箱整理", value=True)
        t_vol = st.checkbox("🚀 今日爆量", value=True)
        t_min_v = st.number_input("最低張數", value=500)
        current_config = {'tri': t_tri, 'box': t_box, 'vol': t_vol, 'use_ma': f_ma}
        run_now = True
    elif "⏳" in selected_mode:
        h_sid = st.text_input("輸入代號")
        current_config = {'tri': True, 'box': True, 'vol': True, 'use_ma': False}
        run_now = st.button("🚀 開始掃描", type="primary")
    else:
        run_now = False

st.title("台股 Pro-X 形態大師")

# ==========================================
# 掃描邏輯
# ==========================================
if run_now and selected_mode != "🌐 所有股票連結":
    targets = [(f"{h_sid.upper()}.TW", h_sid.upper())] if ("⏳" in selected_mode and h_sid) else list(db.items())
    final_results = []
    chunk_size = 50
    ticker_items = list(targets)
    
    with st.status("🚀 正在掃描全產業形態...", expanded=True) as status:
        p_bar = st.progress(0)
        for i in range(0, len(ticker_items), chunk_size):
            p_bar.progress(i / len(ticker_items))
            chunk = ticker_items[i : i + chunk_size]
            t_list = [t[0] for t in chunk]
            status.write(f"掃描中: 第 {i} ~ {min(i+chunk_size, len(ticker_items))} 檔...")
            
            try:
                data = yf.download(t_list, period="2mo", group_by='ticker', progress=False)
                if data.empty: continue
                for sid, name in chunk:
                    try:
                        df_s = data[sid].dropna() if len(t_list) > 1 else data.dropna()
                        res = analyze_patterns(df_s, current_config)
                        if res and (res['vol'] >= (t_min_v if "⚡" in selected_mode else 0)):
                            res.update({"sid": sid, "name": name, "df": df_s})
                            final_results.append(res)
                    except: continue
            except: continue
        p_bar.empty()
        status.update(label="✅ 掃描任務全部完成！", state="complete", expanded=False)

    if not final_results:
        st.info("目前無符合標的。")
    else:
        for item in final_results:
            p_color = "#d63031" if item['price'] >= item['prev_close'] else "#27ae60"
            b_html = "".join([f'<span class="badge {l["class"]}">{l["text"]}</span>' for l in item['labels']])
            st.markdown(f"""<div class="stock-card"><b>{item['sid']} {item['name']}</b> <span style="color:{p_color}; float:right;">${item['price']}</span><br><small>量: {item['vol']}張 | MA20: {item['ma20']}</small><br>{b_html}</div>""", unsafe_allow_html=True)
            with st.expander("📈 展開圖表"):
                d_p = item['df'].tail(30)
                sh, ih, sl, il, x_r = item['lines']
                fig = go.Figure(data=[go.Candlestick(x=d_p.index, open=d_p['Open'], high=d_p['High'], low=d_p['Low'], close=d_p['Close'])])
                fig.add_trace(go.Scatter(x=d_p.index, y=d_p['MA20'], line=dict(color='#3498db', width=1.5)))
                fig.add_trace(go.Scatter(x=d_p.tail(15).index, y=sh*x_r+ih, line=dict(color='#ff4757', dash='dash')))
                fig.add_trace(go.Scatter(x=d_p.tail(15).index, y=sl*x_r+il, line=dict(color='#2ed573', dash='dot')))
                fig.update_layout(height=400, template="plotly_white", showlegend=False, xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 所有股票連結模式
# ==========================================
if selected_mode == "🌐 所有股票連結":
    st.info("點擊下方股票代號即可跳轉到 Yahoo 股價頁面")
    for sid, name in db.items():
        url = f"https://tw.stock.yahoo.com/quote/{sid}"
        st.markdown(f"- [{sid} {name}]({url})", unsafe_allow_html=True)
