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
# 1. 核心數據引擎：抓取電子股並保存 DB
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
            if r.status_code != 200:
                return
            soup = BeautifulSoup(r.text, "html.parser")
            for row in soup.find_all("div", class_=re.compile(r"table-row D\(f\) H\(48px\) Ai\(c\)")):
                name_div = row.find("div", class_=re.compile(r"Lh\(20px\) Fw\(600\) Fz\(16px\) Ell"))
                code_span = row.find("span", class_=re.compile(r"Fz\(14px\) C\(#979ba7\) Ell"))
                if name_div and code_span:
                    name = name_div.get_text(strip=True)
                    sid = code_span.get_text(strip=True)
                    if re.match(r"^\d{4}\.(TW|TWO)$", sid):
                        full_db[sid] = {"name": name, "category": "電子"}
        except:
            pass

    for sid in ELECTRONIC_TAI_IDS:
        fetch_sector(sid, "TAI")
    for sid in ELECTRONIC_TWO_IDS:
        fetch_sector(sid, "TWO")
    
    num_stocks = len(full_db)
    if num_stocks > 0:
        if force_save:
            st.success(f"強制抓取並保存電子產業資料庫，共 {num_stocks} 檔股票！")
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(full_db, f, ensure_ascii=False, indent=4)
    else:
        st.error("抓取失敗：電子產業資料庫為空！")
    
    return full_db


# ==========================================
# 2. 載入 DB（網頁執行時）
# ==========================================
def load_db():
    if should_update_db():
        st.info("DB 超過 24 小時或不存在，正在自動更新電子產業資料...")
        db = fetch_all_electronic_stocks(force_save=True)
    else:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            db = json.load(f)
        num_stocks = len(db)
        st.info(f"使用既有 DB，共 {num_stocks} 檔電子股（上次更新於 {datetime.fromtimestamp(os.path.getmtime(DB_FILE)).strftime('%Y-%m-%d %H:%M')}）")
    return db


# ==========================================
# 3. 形態分析演算法
# ==========================================
def _analyze_pattern_logic(df):
    try:
        d = df.tail(45).copy()
        x = np.arange(len(d))
        h, l, v = d['High'].values.flatten(), d['Low'].values.flatten(), d['Volume'].values.flatten()
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)

        labels = []
        is_tri = (sh < -0.0008) and (sl > 0.0008)
        is_box = (abs(sh) < 0.0006) and (abs(sl) < 0.0006)
        vol_mean = v[-10:-1].mean() if len(v) > 10 else v.mean()
        is_vol = v[-1] > (vol_mean * 1.6)

        is_near_tri = (sh < -0.0004) and (sl > 0.0004) and not is_tri
        if is_near_tri: labels.append("📐 接近三角")
        if is_tri: labels.append("📐 三角收斂")
        if is_box: labels.append("📦 旗箱矩形")
        if is_vol: labels.append("🚀 爆量突破")

        return labels, (sh, ih, sl, il), is_tri, is_box, is_vol
    except:
        return [], (0, 0, 0, 0), False, False, False


# ==========================================
# 4. 介面 CSS
# ==========================================
st.set_page_config(page_title="台股 Pro-X 形態大師", layout="wide")
st.markdown("""
    <style>
    .stApp { background: #f9f9fb; }
    .hero-section { background: white; padding: 25px; border-radius: 15px; text-align: center; border-bottom: 5px solid #6c5ce7; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-bottom: 20px; }
    .stock-card { background: white; padding: 18px; border-radius: 12px; border-left: 8px solid #6c5ce7; margin-top: 15px; box-shadow: 0 4px 8px rgba(0,0,0,0.03); }
    .badge { padding: 4px 10px; border-radius: 5px; font-size: 12px; font-weight: bold; color: white; margin-left: 6px; }
    .badge-tri { background: #6c5ce7; } .badge-vol { background: #ff7675; } .badge-box { background: #2d3436; }
    </style>
""", unsafe_allow_html=True)


# ==========================================
# 5. 首頁標題
# ==========================================
st.markdown(f"""
    <div class="hero-section">
        <h1 style='color: #6c5ce7; margin:0;'>🎯 台股 Pro-X 形態大師</h1>
        <p style='color: #636e72; margin-top:10px;'>專業級大數據掃描系統 | 電子與三角收斂預設監控</p>
        <p style='color: #b2bec3; font-size: 0.8em;'>同步時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
""", unsafe_allow_html=True)


# ==========================================
# 6. 側邊欄
# ==========================================
with st.sidebar:
    st.header("⚙️ 設定中心")

    st.subheader("📡 A. 自動監控模式")
    auto_toggle = st.toggle("啟動自動巡航", value=False)
    with st.expander("自動監控勾選藍", expanded=auto_toggle):
        a_elec = st.checkbox("自動-電子類股", value=True)
        a_food = st.checkbox("自動-食品類股", value=False)
        a_other = st.checkbox("自動-其他類股", value=False)
        st.write("---")
        a_tri = st.checkbox("自動-監控三角", value=False)
        a_box = st.checkbox("自動-監控旗箱", value=False)
        a_vol = st.checkbox("自動-監控爆量", value=True)
    if auto_toggle:
        st_autorefresh(interval=300000, key="auto_refresh")

    st.divider()

    st.subheader("🚀 B. 手動掃描模式")
    with st.expander("手動掃描勾選藍", expanded=True):
        m_elec = st.checkbox("手動-電子類股", value=True)
        m_food = st.checkbox("手動-食品類股", value=False)
        m_other = st.checkbox("手動-其他類股", value=False)
        st.write("---")
        m_tri = st.checkbox("手動-偵測三角", value=False)
        m_box = st.checkbox("手動-偵測旗箱", value=False)
        m_vol = st.checkbox("手動-偵測爆量", value=True)

    st.divider()
    input_sid = st.text_input("輸入個股代號", placeholder="例如: 2330")
    max_limit = st.slider("掃描上限", 50, 1000, 200)
    min_vol_val = st.number_input("最低張數門檻", value=300)
    btn_manual = st.button("🚀 執行手動掃描", use_container_width=True, type="primary")


# ==========================================
# 7. 分析引擎（標題動態調整）
# ==========================================
def execute_engine(is_auto_mode):
    if is_auto_mode:
        cats = [c for c, v in {"電子": a_elec, "食品": a_food, "其他": a_other}.items() if v]
        pats = {"tri": a_tri, "box": a_box, "vol": a_vol}
    else:
        cats = [c for c, v in {"電子": m_elec, "食品": m_food, "其他": m_other}.items() if v]
        pats = {"tri": m_tri, "box": m_box, "vol": m_vol}

    if not cats and not input_sid:
        st.warning("⚠️ 請勾選產業類別或輸入代號。")
        return [], "🔍 形態掃描結果"

    with st.status("🔍 分析引擎運作中...", expanded=True) as status:
        db = load_db()  # 自動載入/更新 DB
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
                df = yf.download(sid, period="90d", progress=False, timeout=10)
                if df.empty or len(df) < 45:
                    return None
                v_now = int(df['Volume'].iloc[-1] // 1000)
                if not input_sid and v_now < min_vol_threshold:
                    return None
                labels, lines, i_tri, i_bx, i_vo = _analyze_pattern_logic(df)
                match = input_sid or (pats['tri'] and i_tri) or (pats['box'] and i_bx) or (pats['vol'] and i_vo)
                if match:
                    return {
                        "sid": sid,
                        "name": info['name'],
                        "cat": info['category'],
                        "df": df.tail(50),
                        "lines": lines,
                        "labels": labels,
                        "price": float(df['Close'].iloc[-1]),
                        "vol": v_now
                    }
            except Exception as e:
                st.warning(f"{sid} 下載失敗：{str(e)}")
                return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(worker, t) for t in targets]
            for f in concurrent.futures.as_completed(futures):
                res = f.result()
                if res:
                    results.append(res)

        # 動態標題
        if pats.get('vol'):
            title = "🔍 爆量突破掃描結果"
        elif pats.get('tri'):
            title = "🔍 三角收斂掃描結果"
        elif pats.get('box'):
            title = "🔍 旗箱矩形掃描結果"
        else:
            title = "🔍 形態掃描結果"

        status.update(label=f"✅ 完成！發現 {len(results)} 檔標的", state="complete")
        return results, title


# ==========================================
# 8. 渲染結果（標題動態 + 連結可點擊）
# ==========================================
final_list = []
scan_title = "🔍 形態掃描結果"

if auto_toggle:
    final_list, scan_title = execute_engine(True)
elif btn_manual or input_sid:
    final_list, scan_title = execute_engine(False)
else:
    st.info("💡 系統就緒。請從左側點擊按鈕或開啟自動監控。")

if final_list:
    table_data = []
    for item in final_list:
        sid = item['sid']
        yahoo_url = f"https://tw.stock.yahoo.com/quote/{sid}"
        link_sid = f"[{sid}]({yahoo_url})"
        badges = " ".join([f'<span class="badge {"badge-tri" if "三角" in l else "badge-vol" if "爆量" in l else "badge-box"}">{l}</span>' for l in item['labels']])
        table_data.append({
            "代號": link_sid,
            "名稱": item['name'],
            "現價": f"{item['price']:.2f}",
            "成交量(張)": item['vol'],
            "形態": badges
        })

    df_table = pd.DataFrame(table_data)
    st.subheader(scan_title)  # 使用動態標題
    st.markdown(df_table.to_markdown(index=False), unsafe_allow_html=True)

    st.subheader("📊 個股 K 線圖")
    for item in final_list:
        with st.expander(f"{item['sid']} {item['name']} ({item['cat']})"):
            d, (sh, ih, sl, il) = item['df'], item['lines']
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
            fig.add_trace(go.Candlestick(x=d.index, open=d['Open'], high=d['High'], low=d['Low'], close=d['Close']), row=1, col=1)
            xv = np.arange(len(d))
            fig.add_trace(go.Scatter(x=d.index, y=sh * xv + ih, line=dict(color='red', width=2, dash='dash')), row=1, col=1)
            fig.add_trace(go.Scatter(x=d.index, y=sl * xv + il, line=dict(color='green', width=2, dash='dot')), row=1, col=1)
            fig.add_trace(go.Bar(x=d.index, y=d['Volume'], marker_color='blue', opacity=0.4), row=2, col=1)
            fig.update_layout(height=450, template="plotly_white", xaxis_rangeslider_visible=False, showlegend=False,
                              margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True, key=f"f_{item['sid']}")
