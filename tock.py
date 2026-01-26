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
# 0. DB 檔案路徑 & 更新邏輯
# ==========================================
DB_FILE = "electronic_stocks_db.json"
UPDATE_INTERVAL_HOURS = 24

def should_update_db():
    if not os.path.exists(DB_FILE):
        return True
    last_modified = datetime.fromtimestamp(os.path.getmtime(DB_FILE))
    if datetime.now() - last_modified > timedelta(hours=UPDATE_INTERVAL_HOURS):
        return True
    return False

# ==========================================
# 1. 核心數據引擎
# ==========================================
def fetch_all_electronic_stocks(force_save=False):
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
    
    if len(full_db) > 0:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(full_db, f, ensure_ascii=False, indent=4)
    return full_db

def load_db():
    if should_update_db():
        st.info("🔄 正在更新電子產業資料...")
        db = fetch_all_electronic_stocks(force_save=True)
    else:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            db = json.load(f)
    return db

# ==========================================
# 2. 形態分析演算法
# ==========================================
@st.cache_data(ttl=1800)
def get_stock_data(sid):
    try:
        df = yf.download(sid, period="90d", progress=False, timeout=15)
        return df
    except:
        return pd.DataFrame()

def _analyze_pattern_logic(df):
    if df.empty or len(df) < 45:
        return [], (0, 0, 0, 0), False, False, False

    d = df.tail(45).copy()
    x = np.arange(len(d))
    h, l, v = d['High'].values.flatten(), d['Low'].values.flatten(), d['Volume'].values.flatten()
    sh, ih, _, _, _ = linregress(x, h)
    sl, il, _, _, _ = linregress(x, l)

    # 形態判定
    is_tri = (sh < -0.0001 and sl > 0.0001)
    is_box = (abs(sh) < 0.0006) and (abs(sl) < 0.0006)
    vol_mean = v[-10:-1].mean() if len(v) > 10 else v.mean()
    is_vol = v[-1] > (vol_mean * 1.4)

    labels = []
    if is_tri: labels.append("📐 三角收斂")
    if is_box: labels.append("📦 旗箱矩形")
    if is_vol: labels.append("🚀 爆量突破")
    return labels, (sh, ih, sl, il), is_tri, is_box, is_vol

# ==========================================
# 3. 分析引擎 (核心邏輯)
# ==========================================
def execute_engine(cats, pats, input_sid, max_limit, min_vol_val):
    if not cats and not input_sid:
        return [], "🔍 形態掃描結果"

    db = load_db()
    results = []

    if input_sid:
        sid = input_sid.strip().upper()
        targets = [(f"{sid}.TW", {"name": "查詢標的", "category": "手動"}),
                   (f"{sid}.TWO", {"name": "查詢標的", "category": "手動"})]
    else:
        targets = [(sid, info) for sid, info in db.items() if info['category'] in cats][:max_limit]

    min_vol_threshold = 150 if "電子" in cats else min_vol_val

    def worker(target):
        sid, info = target
        try:
            df = get_stock_data(sid)
            if df.empty or len(df) < 45: return None
            v_now = int(df['Volume'].iloc[-1] // 1000)
            if not input_sid and v_now < min_vol_threshold: return None
            
            labels, lines, i_tri, i_bx, i_vo = _analyze_pattern_logic(df)
            selected_labels = []
            if pats.get('tri') and i_tri: selected_labels.append("📐 三角收斂")
            if pats.get('box') and i_bx: selected_labels.append("📦 旗箱矩形")
            if pats.get('vol') and i_vo: selected_labels.append("🚀 爆量突破")
            
            if input_sid: selected_labels = labels
            
            if selected_labels:
                return {
                    "sid": sid, "name": info['name'], "cat": info['category'],
                    "df": df.tail(50), "lines": lines, "labels": selected_labels,
                    "price": float(df['Close'].iloc[-1]), "vol": v_now
                }
        except: return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker, t) for t in targets]
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            if res: results.append(res)

    return results, "🔍 掃描結果"

# ==========================================
# 4. 介面設定
# ==========================================
st.set_page_config(page_title="台股 Pro-X 形態大師", layout="wide")
st.markdown("""
    <style>
    .stApp { background: #f9f9fb; }
    .hero-section { background: white; padding: 25px; border-radius: 15px; text-align: center; border-bottom: 5px solid #6c5ce7; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-bottom: 20px; }
    .badge { padding: 4px 10px; border-radius: 5px; font-size: 12px; font-weight: bold; color: white; margin-left: 6px; }
    .badge-tri { background: #6c5ce7; } .badge-vol { background: #ff7675; } .badge-box { background: #2d3436; }
    </style>
""", unsafe_allow_html=True)

st.markdown(f"""
    <div class="hero-section">
        <h1 style='color: #6c5ce7; margin:0;'>🎯 台股 Pro-X 形態大師</h1>
        <p style='color: #636e72; margin-top:10px;'>專業級大數據掃描系統 | 同步時間：{datetime.now().strftime('%H:%M:%S')}</p>
    </div>
""", unsafe_allow_html=True)

# ==========================================
# 5. 側邊欄 (手動+自動全保留)
# ==========================================
with st.sidebar:
    st.header("⚙️ 設定中心")
    
    # --- A. 自動巡航 ---
    auto_toggle = st.toggle("啟動自動巡航 (5分/次)", value=False)
    if auto_toggle:
        st_autorefresh(interval=300000, key="auto_refresh")

    with st.expander("📡 A. 自動監控設定", expanded=auto_toggle):
        a_elec = st.checkbox("自動-電子類股", value=True)
        a_food = st.checkbox("自動-食品類股", value=False)
        a_other = st.checkbox("自動-其他類股", value=False)
        st.write("---")
        a_tri = st.checkbox("自動-監控三角", value=False)
        a_box = st.checkbox("自動-監控旗箱", value=False)
        a_vol = st.checkbox("自動-監控爆量", value=True)

    st.divider()

    # --- B. 手動掃描 ---
    with st.expander("🚀 B. 手動掃描設定", expanded=not auto_toggle):
        m_elec = st.checkbox("手動-電子類股", value=True)
        m_food = st.checkbox("手動-食品類股", value=False)
        m_other = st.checkbox("手動-其他類股", value=False)
        st.write("---")
        m_tri = st.checkbox("手動-偵測三角", value=False)
        m_box = st.checkbox("手動-偵測旗箱", value=False)
        m_vol = st.checkbox("手動-偵測爆量", value=True)

    st.divider()
    input_sid = st.text_input("輸入個股代號 (優先查詢)", placeholder="例如: 2330")
    max_limit = st.slider("掃描上限", 50, 1000, 200)
    min_vol_val = st.number_input("最低張數門檻", value=300)
    
    run_search = st.button("🚀 執行手動搜尋", use_container_width=True, type="primary")

# ==========================================
# 6. 主程式執行邏輯
# ==========================================
# 決定要用哪一組設定 (自動或手動)
if auto_toggle:
    current_cats = [c for c, v in {"電子": a_elec, "食品": a_food, "其他": a_other}.items() if v]
    current_pats = {"tri": a_tri, "box": a_box, "vol": a_vol}
else:
    current_cats = [c for c, v in {"電子": m_elec, "食品": m_food, "其他": m_other}.items() if v]
    current_pats = {"tri": m_tri, "box": m_box, "vol": m_vol}

# 觸發條件：按下按鈕、自動巡航開啟、或是輸入了個股代號
if run_search or auto_toggle or input_sid:
    with st.status("🔍 市場掃描中...", expanded=True) as status:
        final_list, scan_title = execute_engine(current_cats, current_pats, input_sid, max_limit, min_vol_val)
        
        if final_list:
            st.subheader(scan_title)
            # 表格化顯示
            table_data = []
            for item in final_list:
                badges = " ".join([f'<span class="badge {"badge-tri" if "三角" in l else "badge-vol" if "爆量" in l else "badge-box"}">{l}</span>' for l in item['labels']])
                table_data.append({
                    "代號": item['sid'], "名稱": item['name'], "現價": f"{item['price']:.2f}",
                    "成交量(張)": item['vol'], "形態": badges
                })
            st.write(pd.DataFrame(table_data).to_html(escape=False, index=False), unsafe_allow_html=True)

            # K線圖顯示
            for item in final_list:
                with st.expander(f"📊 {item['sid']} {item['name']} 詳情"):
                    d, (sh, ih, sl, il) = item['df'], item['lines']
                    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)
                    fig.add_trace(go.Candlestick(x=d.index, open=d['Open'], high=d['High'], low=d['Low'], close=d['Close']), row=1, col=1)
                    xv = np.arange(len(d))
                    fig.add_trace(go.Scatter(x=d.index, y=sh * xv + ih, line=dict(color='red', width=2, dash='dash')), row=1, col=1)
                    fig.add_trace(go.Scatter(x=d.index, y=sl * xv + il, line=dict(color='green', width=2, dash='dot')), row=1, col=1)
                    fig.add_trace(go.Bar(x=d.index, y=d['Volume'], marker_color='blue', opacity=0.4), row=2, col=1)
                    fig.update_layout(height=450, template="plotly_white", xaxis_rangeslider_visible=False, showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("未發現符合形態的個股，請調整篩選條件。")
        status.update(label=f"✅ 完成！發現 {len(final_list)} 檔標的", state="complete")
