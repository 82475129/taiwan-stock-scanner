import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
from streamlit_autorefresh import st_autorefresh
from bs4 import BeautifulSoup
import json, os, requests, time

# ==========================================
# 0. 真實數據載入與自動爬蟲邏輯 (新增合併部分)
# ==========================================
DB_FILE = "taiwan_electronic_stocks.json"

def update_json_database():
    """整合多個 Yahoo 網址並生成 JSON 資料庫"""
    # 這裡可以自由增加你要的網址 (sectorId 或 category 格式皆可)
    urls = [
        "https://tw.stock.yahoo.com/class-quote?sectorId=2&exchange=TAI", # 食品
        "https://tw.stock.yahoo.com/class-quote?sectorId=7&exchange=TAI", # 電機
        "https://tw.stock.yahoo.com/class-quote?category=%E4%B8%AD%E5%A4%A9%E7%94%9F%E6%8A%80&categoryLabel=%E9%9B%86%E5%9C%98%E8%82%A1"
    ]
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    new_db = {}

    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')
            rows = soup.select('li.List\(n\)')
            for row in rows:
                name_el = row.select_one('div.Lh\(20px\)')
                code_el = row.select_one('span.Fz\(14px\)')
                if name_el and code_el:
                    new_db[code_el.text.strip()] = name_el.text.strip()
            time.sleep(0.5)
        except: continue
        
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(new_db, f, ensure_ascii=False, indent=2)
    return new_db

@st.cache_data(show_spinner=False)
def get_full_stock_list():
    # 如果檔案不存在，先跑一次爬蟲
    if not os.path.exists(DB_FILE):
        return update_json_database()
    
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if data else {}
    except:
        return {}

db = get_full_stock_list()

# ==========================================
# 1. 形態分析引擎 (維持原樣)
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
# 2. 介面設計 (維持原樣)
# ==========================================
st.set_page_config(page_title="台股 Pro-X 形態大師", layout="wide")
st.markdown("""<style>.stApp { background-color: #f4f7f6; }.stock-card { background: white; padding: 20px; border-radius: 12px; margin-bottom: 20px; border-left: 8px solid #6c5ce7; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }.badge { padding: 4px 10px; border-radius: 6px; font-size: 0.8rem; font-weight: bold; margin-right: 5px; color: white; }.badge-tri { background-color: #6c5ce7; }.badge-box { background-color: #2d3436; }.badge-vol { background-color: #d63031; }</style>""", unsafe_allow_html=True)

with st.sidebar:
    st.title("🎯 形態大師控制台")
    
    # 新增一個手動更新按鈕
    if st.button("🔄 同步網頁最新清單"):
        db = update_json_database()
        st.success("已完成多網址同步！")
        st.cache_data.clear()

    if not db:
        st.error("⚠️ 無真實數據！請點擊上方按鈕執行爬蟲。")
    else:
        st.success(f"📁 已載入：{len(db)} 檔標的")
    
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
# 3. 掃描與結果 (邏輯微調以相容搜尋代碼)
# ==========================================
st.title("台股 Pro-X 形態大師")

if run and db:
    # 搜尋模式代碼處理
    if "⏳" in mode and h_sid:
        s_code = h_sid.upper()
        if not s_code.endswith((".TW", ".TWO")):
            s_code = f"{s_code}.TW"
        targets = [(s_code, db.get(s_code, h_sid.upper()))]
    else:
        targets = list(db.items())
        
    final_results = []
    
    with st.status("🔍 市場形態深度掃描中...", expanded=True) as status:
        p_bar = st.progress(0)
        chunk_size = 40
        
        for i in range(0, len(targets), chunk_size):
            p_bar.progress(min(i / len(targets), 1.0))
            chunk = targets[i : i + chunk_size]
            t_list = [t[0] for t in chunk]
            
            try:
                # 下載數據，考慮到單檔搜尋與多檔批次的結構差異
                data = yf.download(t_list, period="2mo", group_by='ticker', progress=False)
                for sid, name in chunk:
                    try:
                        df_s = data[sid].dropna() if len(t_list) > 1 else data.dropna()
                        if df_s.empty: continue
                        
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
