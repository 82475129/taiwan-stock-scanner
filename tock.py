import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import sys
from bs4 import BeautifulSoup
import json, os, requests, time

# ==========================================
# 檢查運行環境
# ==========================================
IS_STREAMLIT = "streamlit" in sys.argv[0] or any("streamlit" in arg for arg in sys.argv)

# ==========================================
# 0. 全產業資料庫爬蟲 (目標 1500+ 檔)
# ==========================================
DB_FILE = "taiwan_electronic_stocks.json"

def update_json_database():
    """抓取 Yahoo 財經所有產業分類，達成全台股覆蓋"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    new_db = {}
    
    # 掃描範圍：上市 ID (2~47), 上櫃 ID (65~165)
    # 這涵蓋了台股 99% 的產業分類
    sector_ranges = [
        {"exchange": "TAI", "ids": list(range(2, 48))},
        {"exchange": "TWO", "ids": list(range(65, 166))}
    ]
    
    print("📡 開始全產業掃描...")
    
    for item in sector_ranges:
        exch = item["exchange"]
        for sid in item["ids"]:
            url = f"https://tw.stock.yahoo.com/class-quote?sectorId={sid}&exchange={exch}"
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code != 200: continue
                
                soup = BeautifulSoup(resp.text, 'html.parser')
                rows = soup.select('li.List\(n\)')
                
                if not rows: continue
                
                counter = 0
                for row in rows:
                    name_el = row.select_one('div.Lh\(20px\)')
                    code_el = row.select_one('span.Fz\(14px\)')
                    if name_el and code_el:
                        code = code_el.text.strip()
                        # 格式化為 yfinance 代號
                        suffix = ".TW" if exch == "TAI" else ".TWO"
                        full_code = f"{code}{suffix}"
                        new_db[full_code] = name_el.text.strip()
                        counter += 1
                
                # 僅列印有抓到資料的類股以節省日誌空間
                if counter > 0:
                    print(f"✅ {exch} 類股 ID {sid}: 抓取 {counter} 檔")
                
                time.sleep(0.05) # 稍微快一點，因為數量龐大
            except:
                continue
    
    # 儲存結果
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(new_db, f, ensure_ascii=False, indent=2)
    
    print(f"🏁 掃描結束，總計：{len(new_db)} 檔股票")
    return new_db

def load_db():
    if not os.path.exists(DB_FILE):
        return update_json_database()
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except: return {}

# ==========================================
# 1. 形態分析引擎 (維持高效運算)
# ==========================================
def analyze_patterns(df, config, days=15):
    if df is None or len(df) < 30: return None
    try:
        df['MA20'] = df['Close'].rolling(window=20).mean()
        p_now = float(df['Close'].iloc[-1])
        m_now = float(df['MA20'].iloc[-1])
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
# 2. 執行分流邏輯
# ==========================================
if IS_STREAMLIT:
    from streamlit_autorefresh import st_autorefresh
    db = load_db()
    
    st.set_page_config(page_title="台股全產業形態掃描器", layout="wide")
    st.markdown("""<style>.stApp { background-color: #f4f7f6; }.stock-card { background: white; padding: 20px; border-radius: 12px; margin-bottom: 20px; border-left: 8px solid #6c5ce7; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }.badge { padding: 4px 10px; border-radius: 6px; font-size: 0.8rem; font-weight: bold; margin-right: 5px; color: white; }.badge-tri { background-color: #6c5ce7; }.badge-box { background-color: #2d3436; }.badge-vol { background-color: #d63031; }</style>""", unsafe_allow_html=True)

    with st.sidebar:
        st.title("🎯 全產業掃描控制台")
        if st.button("🔄 同步全台股清單 (1500+)"):
            with st.spinner("深度掃描各產業中..."):
                db = update_json_database()
                st.cache_data.clear()
                st.success("同步完成！")
        st.info(f"📁 已載入：{len(db)} 檔標的")
        mode = st.radio("功能模式", ["⚡ 即時監控", "⏳ 歷史搜尋"])
        st.divider()
        
        run = False
        if "⚡" in mode:
            st_autorefresh(interval=300000, key="auto_refresh")
            f_ma = st.checkbox("股價在 MA20 之上", value=True)
            t_tri = st.checkbox("📐 三角收斂", value=True)
            t_box = st.checkbox("📦 旗箱整理", value=True)
            t_vol = st.checkbox("🚀 今日爆量", value=True)
            t_min_v = st.number_input("最低成交量(張)", value=1000)
            config = {'tri': t_tri, 'box': t_box, 'vol': t_vol, 'use_ma': f_ma}
            run = True
        else:
            h_sid = st.text_input("輸入股票代號 (如 2330)")
            config = {'tri': True, 'box': True, 'vol': True, 'use_ma': False}
            run = st.button("🚀 開始掃描", type="primary")

    if run:
        st.title("台股形態分析結果")
        targets = []
        if "⏳" in mode and h_sid:
            code = h_sid.upper()
            target_list = [c for c in db.keys() if code in c]
            targets = [(c, db[c]) for c in target_list]
        else:
            targets = list(db.items())
            
        final_results = []
        with st.status(f"🔍 正在篩選 {len(targets)} 檔形態...", expanded=True) as status:
            p_bar = st.progress(0)
            # 由於標的變多，chunk_size 稍微調大以加快速度
            chunk_size = 40 
            for i in range(0, len(targets), chunk_size):
                p_bar.progress(min(i / len(targets), 1.0))
                chunk = targets[i : i + chunk_size]
                t_list = [t[0] for t in chunk]
                try:
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
            status.update(label=f"✅ 找到 {len(final_results)} 檔形態符合標的", state="complete", expanded=False)

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
            st.info("💡 暫無符合形態的股票，建議調整成交量門檻。")

else:
    # --- GitHub Actions 專用 ---
    if __name__ == "__main__":
        update_json_database()
