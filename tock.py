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
# 0. 資料庫引擎 (Yahoo 電子股)
# ==========================================
DB_FILE = "taiwan_electronic_stocks.json"

def fetch_electronic_db():
    SECTOR_IDS = [40, 41, 42, 43, 44, 45, 46, 47] 
    db = {}
    headers = {'User-Agent': 'Mozilla/5.0'}
    for sid in SECTOR_IDS:
        for ex in ["TAI", "TWO"]:
            try:
                url = f"https://tw.stock.yahoo.com/class-quote?sectorId={sid}&exchange={ex}"
                r = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(r.text, "html.parser")
                for row in soup.find_all("div", class_=re.compile(r"table-row")):
                    n = row.find("div", class_=re.compile(r"Lh\(20px\) Fw\(600\)"))
                    c = row.find("span", class_=re.compile(r"Fz\(14px\) C\(#979ba7\)"))
                    if n and c:
                        code = c.get_text(strip=True)
                        if re.match(r"^\d{4}\.(TW|TWO)$", code):
                            db[code] = {"name": n.get_text(strip=True), "cat": "電子"}
            except: continue
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False)
    return db

def load_db():
    if not os.path.exists(DB_FILE): return fetch_electronic_db()
    with open(DB_FILE, 'r', encoding='utf-8') as f: return json.load(f)

# ==========================================
# 1. 形態核心演算法 (聚焦尾端 20 天)
# ==========================================
@st.cache_data(ttl=600)
def get_data(sid):
    try: return yf.download(sid, period="45d", progress=False)
    except: return pd.DataFrame()

def analyze_logic(df, config):
    if df.empty or len(df) < 20: return None
    d = df.tail(20).copy()
    x = np.arange(len(d))
    h, l, v = d['High'].values.flatten(), d['Low'].values.flatten(), d['Volume'].values.flatten()
    sh, ih, _, _, _ = linregress(x, h)
    sl, il, _, _, _ = linregress(x, l)

    is_tri = (sh < -0.01 and sl > 0.01)
    is_box = (abs(sh) < 0.05 and abs(sl) < 0.05)
    v_mean = v[-6:-1].mean() if len(v)>5 else v.mean()
    is_vol = v[-1] > (v_mean * 1.3)

    hits = []
    if config['tri'] and is_tri: hits.append("📐 尾端收斂")
    if config['box'] and is_box: hits.append("📦 近期橫盤")
    if config['vol'] and is_vol: hits.append("🚀 今日爆量")
    
    if hits:
        return {"labels": hits, "lines": (sh, ih, sl, il), "price": round(float(df['Close'].iloc[-1]), 2), "vol": int(v[-1]//1000)}
    return None

# ==========================================
# 2. 手機版介面 CSS
# ==========================================
st.set_page_config(page_title="Pro-X 尾端掃描", layout="wide")
st.markdown("""
    <style>
    .stApp { background: #f8f9fa; }
    .stock-card { background: white; padding: 15px; border-radius: 12px; margin-bottom: 12px; border-left: 6px solid #6c5ce7; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    .s-link { font-size: 1.1rem; font-weight: bold; color: #6c5ce7; text-decoration: none; }
    .badge { padding: 3px 10px; border-radius: 5px; font-size: 0.75rem; color: white; margin-right: 5px; font-weight: bold; }
    .bg-tri { background: #6c5ce7; } .bg-vol { background: #ff7675; } .bg-box { background: #2d3436; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 側邊欄：自動與手動欄位分開
# ==========================================
with st.sidebar:
    st.header("⚙️ 系統設定")
    
    # 預設開啟自動巡航
    mode = st.radio("選擇操作模式", ["自動巡航監控", "手動即時掃描"], index=0)
    
    st.divider()

    if mode == "自動巡航監控":
        st_autorefresh(interval=300000, key="auto_ref")
        st.subheader("📡 自動監控設定")
        a_tri = st.checkbox("自動-偵測收斂", value=True)
        a_box = st.checkbox("自動-偵測橫盤", value=False)
        a_vol = st.checkbox("自動-偵測爆量", value=True)
        a_min_v = st.number_input("自動-最低張數", value=300)
        # 設定傳遞
        current_config = {'tri': a_tri, 'box': a_box, 'vol': a_vol}
        current_min_v = a_min_v
        is_manual_sid = False
    else:
        st.subheader("🚀 手動掃描設定")
        m_sid = st.text_input("輸入個股代號", placeholder="例如: 2330")
        m_tri = st.checkbox("手動-偵測收斂", value=True)
        m_box = st.checkbox("手動-偵測橫盤", value=True)
        m_vol = st.checkbox("手動-偵測爆量", value=True)
        m_min_v = st.number_input("手動-最低張數", value=100)
        # 設定傳遞
        current_config = {'tri': m_tri, 'box': m_box, 'vol': m_vol}
        current_min_v = m_min_v
        is_manual_sid = m_sid

# ==========================================
# 4. 執行引擎
# ==========================================
db = load_db()
if is_manual_sid:
    scan_list = [(f"{is_manual_sid.upper()}.TW", {"name": "手動"}), (f"{is_manual_sid.upper()}.TWO", {"name": "手動"})]
else:
    # 模式不同，掃描範圍可微調
    limit = 100 if mode == "自動巡航監控" else 150
    scan_list = list(db.items())[:limit]

final_res = []
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    future_to_sid = {executor.submit(get_data, s): (s, info) for s, info in scan_list}
    for future in concurrent.futures.as_completed(future_to_sid):
        sid, info = future_to_sid[future]
        df = future.result()
        res = analyze_logic(df, current_config)
        if res and (res['vol'] >= current_min_v or is_manual_sid):
            res.update({"sid": sid, "name": info['name'], "df": df})
            final_res.append(res)

# ==========================================
# 5. 結果顯示
# ==========================================
st.subheader(f"🔍 {mode} 結果 ({datetime.now().strftime('%H:%M:%S')})")

if not final_res:
    st.info("💡 目前條件下無符合標的。請更改側邊欄欄位。")

for item in final_res:
    clean_sid = item['sid'].split('.')[0]
    b_html = "".join([f'<span class="badge {"bg-tri" if "收斂" in l else "bg-vol" if "爆量" in l else "bg-box"}">{l}</span>' for l in item['labels']])
    
    st.markdown(f"""
        <div class="stock-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <a href="https://tw.stock.yahoo.com/quote/{clean_sid}" target="_blank" class="s-link">🔗 {item['sid']} {item['name']}</a>
                <span style="color:#d63031; font-weight:bold; font-size:1.1rem;">${item['price']}</span>
            </div>
            <div style="font-size:0.85rem; color:#636e72; margin: 6px 0;">今日成交量: <b>{item['vol']} 張</b></div>
            <div style="margin-top:5px;">{b_html}</div>
        </div>
    """, unsafe_allow_html=True)
    
    with st.expander("📈 檢視尾端趨勢線"):
        d = item['df'].tail(30)
        sh, ih, sl, il = item['lines']
        fig = make_subplots(rows=1, cols=1)
        fig.add_trace(go.Candlestick(x=d.index, open=d['Open'], high=d['High'], low=d['Low'], close=d['Close'], name="K"))
        # 繪製尾端 20 天趨勢線
        d_tail = d.tail(20)
        xv = np.arange(len(d_tail))
        fig.add_trace(go.Scatter(x=d_tail.index, y=sh*xv+ih, line=dict(color='#ff4757', width=2, dash='dash'), name="壓"))
        fig.add_trace(go.Scatter(x=d_tail.index, y=sl*xv+il, line=dict(color='#2ed573', width=2, dash='dot'), name="支"))
        fig.update_layout(height=350, margin=dict(l=5,r=5,t=5,b=5), xaxis_rangeslider_visible=False, template="plotly_white")
        st.plotly_chart(fig, use_container_width=True, key=f"p_{item['sid']}_{datetime.now().microsecond}")
