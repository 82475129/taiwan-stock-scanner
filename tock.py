import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import re
import concurrent.futures
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.stats import linregress
from bs4 import BeautifulSoup
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timedelta
import json
import os

# ==========================================
# 0. 初始化設定
# ==========================================
DB_FILE = "electronic_stocks_db.json"
UPDATE_INTERVAL_HOURS = 24

def should_update_db():
    if not os.path.exists(DB_FILE): return True
    last_modified = datetime.fromtimestamp(os.path.getmtime(DB_FILE))
    return (datetime.now() - last_modified) > timedelta(hours=UPDATE_INTERVAL_HOURS)

# ==========================================
# 1. 核心數據引擎
# ==========================================
def fetch_all_electronic_stocks():
    ELECTRONIC_TAI_IDS = [40, 41, 42, 43, 44, 45, 46, 47]
    ELECTRONIC_TWO_IDS = [153, 154, 155, 156, 157, 158, 159, 160]
    full_db = {}
    
    def fetch_sector(sector_id, exchange):
        url = f"https://tw.stock.yahoo.com/class-quote?sectorId={sector_id}&exchange={exchange}"
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code != 200: return
            soup = BeautifulSoup(r.text, "html.parser")
            for row in soup.find_all("div", class_=re.compile(r"table-row D\(f\) H\(48px\) Ai\(c\)")):
                name_div = row.find("div", class_=re.compile(r"Lh\(20px\) Fw\(600\) Fz\(16px\) Ell"))
                code_span = row.find("span", class_=re.compile(r"Fz\(14px\) C\(#979ba7\) Ell"))
                if name_div and code_span:
                    name = name_div.get_text(strip=True)
                    sid = code_span.get_text(strip=True)
                    if re.match(r"^\d{4}\.(TW|TWO)$", sid):
                        full_db[sid] = {"name": name, "category": "電子"}
        except: pass

    for sid in ELECTRONIC_TAI_IDS: fetch_sector(sid, "TAI")
    for sid in ELECTRONIC_TWO_IDS: fetch_sector(sid, "TWO")
    
    if full_db:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(full_db, f, ensure_ascii=False, indent=4)
    return full_db

def load_db():
    if should_update_db():
        st.info("🔄 正在更新電子股資料...")
        return fetch_all_electronic_stocks()
    with open(DB_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

# ==========================================
# 2. 形態分析演算法 (手機端視覺優化版)
# ==========================================
@st.cache_data(ttl=1800)
def get_stock_data(sid):
    try:
        df = yf.download(sid, period="100d", progress=False, timeout=15)
        return df
    except: return pd.DataFrame()

def _analyze_pattern_logic(df):
    if df.empty or len(df) < 60: return [], (0,0,0,0), False, False, False
    
    # 取最近 60 天進行分析，增加穩定性
    d = df.tail(60).copy()
    x = np.arange(len(d))
    h, l, v = d['High'].values.flatten(), d['Low'].values.flatten(), d['Volume'].values.flatten()
    
    sh, ih, _, _, _ = linregress(x, h)
    sl, il, _, _, _ = linregress(x, l)

    # 更嚴謹的三角判定：高點下降，低點上升，且斜率絕對值需大於門檻
    is_tri = (sh < -0.05) and (sl > 0.05)
    is_box = (abs(sh) < 0.03) and (abs(sl) < 0.03)
    vol_mean = v[-15:-1].mean()
    is_vol = v[-1] > (vol_mean * 1.5)

    labels = []
    if is_tri: labels.append("📐三角收斂")
    if is_box: labels.append("📦旗箱矩形")
    if is_vol: labels.append("🚀爆量突破")
    return labels, (sh, ih, sl, il), is_tri, is_box, is_vol

# ==========================================
# 3. 分析引擎
# ==========================================
def execute_engine(cats, pats, input_sid, max_limit, min_vol_val):
    db = load_db()
    results = []
    if input_sid:
        sid = input_sid.strip().upper()
        targets = [(f"{sid}.TW", {"name": "查詢中", "category": "手動"}), (f"{sid}.TWO", {"name": "查詢中", "category": "手動"})]
    else:
        targets = [(sid, info) for sid, info in db.items() if info['category'] in cats][:max_limit]

    def worker(target):
        sid, info = target
        df = get_stock_data(sid)
        if df.empty or len(df) < 60: return None
        v_now = int(df['Volume'].iloc[-1] // 1000)
        if not input_sid and v_now < min_vol_val: return None
        
        labels, lines, i_tri, i_bx, i_vo = _analyze_pattern_logic(df)
        hit = []
        if pats.get('tri') and i_tri: hit.append("📐三角收斂")
        if pats.get('box') and i_bx: hit.append("📦旗箱矩形")
        if pats.get('vol') and i_vo: hit.append("🚀爆量突破")
        
        if input_sid or hit:
            return {"sid": sid, "name": info['name'], "df": df.tail(60), "lines": lines, "labels": hit if hit else labels, "price": float(df['Close'].iloc[-1]), "vol": v_now}
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        for res in executor.map(worker, targets):
            if res: results.append(res)
    return results

# ==========================================
# 4. 手機版 CSS 優化
# ==========================================
st.set_page_config(page_title="台股 Pro-X", layout="wide")
st.markdown("""
    <style>
    .stApp { background: #f8f9fa; }
    /* 手機版卡片樣式 */
    .stock-card {
        background: white; padding: 15px; border-radius: 12px;
        margin-bottom: 12px; border: 1px solid #e0e0e0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .stock-title { font-size: 1.1rem; font-weight: bold; color: #6c5ce7; margin-bottom: 5px; }
    .stock-info { font-size: 0.9rem; color: #636e72; display: flex; justify-content: space-between; }
    .badge {
        padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; 
        font-weight: bold; color: white; margin-right: 4px;
    }
    .badge-tri { background: #6c5ce7; } .badge-vol { background: #ff7675; } .badge-box { background: #2d3436; }
    /* 隱藏桌面版大表格，適配手機 */
    @media (max-width: 600px) {
        .hero-section h1 { font-size: 1.5rem; }
        .stButton button { width: 100%; }
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 5. UI 與 側邊欄
# ==========================================
st.title("🎯 台股形態大師 (手機優化版)")

with st.sidebar:
    st.header("⚙️ 設定")
    auto_toggle = st.toggle("啟動自動巡航", value=False)
    if auto_toggle: st_autorefresh(interval=300000, key="auto_refresh")
    
    with st.expander("🔍 搜尋模式", expanded=True):
        m_elec = st.checkbox("電子類股", value=True)
        m_tri = st.checkbox("偵測三角", value=True)
        m_box = st.checkbox("偵測旗箱", value=False)
        m_vol = st.checkbox("偵測爆量", value=True)
    
    input_sid = st.text_input("輸入個股代號", placeholder="例如: 2330")
    min_vol = st.number_input("最低成交量(張)", value=300)
    run_search = st.button("🚀 立即搜尋", type="primary")

# ==========================================
# 6. 執行與顯示
# ==========================================
if run_search or auto_toggle or input_sid:
    cats = ["電子"] if m_elec else []
    pats = {"tri": m_tri, "box": m_box, "vol": m_vol}
    
    with st.spinner("🔍 掃描中..."):
        results = execute_engine(cats, pats, input_sid, 200, min_vol)
        
        if results:
            for item in results:
                # 1. 顯示手機版卡片
                clean_sid = item['sid'].split('.')[0]
                yahoo_url = f"https://tw.stock.yahoo.com/quote/{clean_sid}"
                
                badges_html = "".join([f'<span class="badge {"badge-tri" if "三角" in l else "badge-vol" if "爆量" in l else "badge-box"}">{l}</span>' for l in item['labels']])
                
                st.markdown(f"""
                    <div class="stock-card">
                        <div class="stock-title"><a href="{yahoo_url}" target="_blank">{item['sid']} {item['name']}</a></div>
                        <div class="stock-info">
                            <span>價格: <b>{item['price']}</b></span>
                            <span>量: <b>{item['vol']} 張</b></span>
                        </div>
                        <div style="margin-top:8px;">{badges_html}</div>
                    </div>
                """, unsafe_allow_html=True)
                
                # 2. 顯示圖表 (手機端自動縮小)
                with st.expander(f"📈 查看 {item['sid']} K線圖"):
                    d, (sh, ih, sl, il) = item['df'], item['lines']
                    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.03)
                    fig.add_trace(go.Candlestick(x=d.index, open=d['Open'], high=d['High'], low=d['Low'], close=d['Close']), row=1, col=1)
                    xv = np.arange(len(d))
                    fig.add_trace(go.Scatter(x=d.index, y=sh*xv+ih, line=dict(color='red', width=1, dash='dash')), row=1, col=1)
                    fig.add_trace(go.Scatter(x=d.index, y=sl*xv+il, line=dict(color='green', width=1, dash='dot')), row=1, col=1)
                    fig.add_trace(go.Bar(x=d.index, y=d['Volume'], marker_color='blue', opacity=0.5), row=2, col=1)
                    fig.update_layout(height=400, margin=dict(l=5, r=5, t=10, b=10), xaxis_rangeslider_visible=False, showlegend=False)
                    st.plotly_chart(fig, use_container_width=True, key=f"plot_{item['sid']}")
        else:
            st.info("目前無符合形態的股票。")
