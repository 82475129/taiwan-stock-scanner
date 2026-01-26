import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import json
import os
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime

# ==========================================
# 0. 啟動即執行：資料庫自動化建立 (800+ 檔)
# ==========================================
DB_FILE = "taiwan_electronic_stocks.json"

def init_db():
    """在程式啟動的第一時間執行爬蟲"""
    if not os.path.exists(DB_FILE):
        print("🚀 [系統通知] 正在進行初次設定，抓取全台電子股清單 (約 800+ 檔)...")
        sectors = {
            "TAI": {40: "半導體", 41: "電腦週邊", 42: "光電", 43: "通信網路", 44: "電子零組件", 45: "電子通路", 46: "資訊服務", 47: "其他電子"},
            "TWO": {153: "半導體", 154: "電腦週邊", 155: "光電", 156: "通信網路", 157: "電子零組件", 158: "電子通路", 159: "資訊服務", 160: "其他電子"}
        }
        full_db = {}
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        
        for ex, cats in sectors.items():
            for sid, cat_name in cats.items():
                try:
                    url = f"https://tw.stock.yahoo.com/class-quote?sectorId={sid}&exchange={ex}"
                    resp = requests.get(url, headers=headers, timeout=10)
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    rows = soup.select('div[class*="table-row"]')
                    for row in rows:
                        c = row.select_one('span[class*="C(#7c7e80)"]')
                        n = row.select_one('div[class*="Lh(20px)"]')
                        if c and n:
                            suffix = ".TW" if ex == "TAI" else ".TWO"
                            full_db[f"{c.get_text(strip=True)}{suffix}"] = n.get_text(strip=True)
                    time.sleep(0.3)
                except Exception as e:
                    print(f"⚠️ 抓取 {cat_name} 時發生錯誤: {e}")
        
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(full_db, f, ensure_ascii=False, indent=2)
        print(f"✨ [系統通知] 初始化成功！已儲存 {len(full_db)} 檔電子股至 {DB_FILE}")

# 強制執行初始化
init_db()

# ==========================================
# 1. 形態分析與篩選引擎
# ==========================================
def run_analysis(df, config, days=15):
    """回傳符合條件的形態結果與繪圖數據"""
    if df is None or len(df) < 30: return None
    try:
        # 1. 均線篩選 (MA20)
        df['MA20'] = df['Close'].rolling(window=20).mean()
        price_now = df['Close'].iloc[-1]
        ma20_now = df['MA20'].iloc[-1]
        
        if config['use_ma'] and price_now < ma20_now:
            return None # 股價在月線下，剔除

        # 2. 形態分析數據準備
        d = df.tail(days).copy()
        h, l, v = d['High'].values.astype(float), d['Low'].values.astype(float), d['Volume'].values.astype(float)
        x = np.arange(len(h))
        
        sh, ih, _, _, _ = linregress(x, h) # 高點連線
        sl, il, _, _, _ = linregress(x, l) # 低點連線
        v_avg = df['Volume'].iloc[-21:-1].mean() # 過去20天均量
        
        hits = []
        # 三角收斂: 高點下降，低點墊高
        if config['tri'] and (sh < -0.002 and sl > 0.002):
            hits.append({"text": "📐 三角收斂", "css": "b-tri"})
        # 旗箱整理: 高低點皆在水平區間
        if config['box'] and (abs(sh) < 0.02 and abs(sl) < 0.02):
            hits.append({"text": "📦 旗箱整理", "css": "b-box"})
        # 爆量: 今日量 > 20日均量 * 1.5
        if config['vol'] and (v[-1] > v_avg * 1.5):
            hits.append({"text": "🚀 帶量轉強", "css": "b-vol"})
            
        if not hits: return None
        
        return {
            "tags": hits, "lines": (sh, ih, sl, il, x),
            "p": round(price_now, 2),
            "ma": round(ma20_now, 2),
            "diff": round(price_now - df['Close'].iloc[-2], 2),
            "v_qty": int(v[-1] // 1000)
        }
    except: return None

# ==========================================
# 2. Streamlit 介面渲染
# ==========================================
st.set_page_config(page_title="台股 Pro-X 形態大師", layout="wide")

st.markdown("""
<style>
    .card { background: #fff; padding: 20px; border-radius: 15px; border-left: 6px solid #4834d4; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 20px; }
    .b-tri { background: #4834d4; color: white; padding: 4px 8px; border-radius: 5px; font-size: 12px; font-weight: bold; }
    .b-box { background: #2f3542; color: white; padding: 4px 8px; border-radius: 5px; font-size: 12px; font-weight: bold; }
    .b-vol { background: #eb4d4b; color: white; padding: 4px 8px; border-radius: 5px; font-size: 12px; font-weight: bold; }
    .ma-val { color: #2980b9; font-size: 13px; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

with open(DB_FILE, 'r', encoding='utf-8') as f:
    db = json.load(f)

# 側邊欄控制
with st.sidebar:
    st.title("🎯 形態篩選器")
    st.info(f"📁 已載入：{len(db)} 檔電子股")
    st.divider()
    
    min_v = st.number_input("最低成交量 (張)", value=500)
    st.write("### 條件設定")
    use_ma = st.checkbox("股價需在 20MA 之上", value=True)
    c_tri = st.checkbox("📐 三角收斂", value=True)
    c_box = st.checkbox("📦 旗箱整理", value=True)
    c_vol = st.checkbox("🚀 今日爆量", value=True)
    
    cfg = {'tri': c_tri, 'box': c_box, 'vol': c_vol, 'use_ma': use_ma}
    start = st.button("🔍 開始全量掃描", type="primary", use_container_width=True)

# 主畫面執行
if start:
    st.subheader(f"📊 掃描報告 - {datetime.now().strftime('%Y/%m/%d %H:%M')}")
    t_list = list(db.keys())
    
    with st.spinner("正在下載全產業 K 線數據..."):
        # 批量下載提高 10 倍效能
        raw_data = yf.download(t_list, period="3mo", group_by='ticker', progress=False)
    
    found_cnt = 0
    grid = st.columns(2)
    
    for ticker in t_list:
        try:
            df_one = raw_data[ticker].dropna()
            res = run_analysis(df_one, cfg)
            
            if res and res['v_qty'] >= min_v:
                with grid[found_cnt % 2]:
                    trend_color = "#eb4d4b" if res['diff'] >= 0 else "#2ecc71"
                    tags_html = "".join([f'<span class="{t["css"]}">{t["text"]}</span> ' for t in res['tags']])
                    
                    st.markdown(f"""
                    <div class="card">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <span style="font-size:20px;"><b>{ticker} {db[ticker]}</b></span>
                            <span style="color:{trend_color}; font-size:24px; font-weight:800;">${res['p']}</span>
                        </div>
                        <div style="margin: 10px 0;">{tags_html} <span class="ma-val">月線: {res['ma']}</span></div>
                        <div style="color:#7f8c8d; font-size:14px;">量: {res['v_qty']} 張 | 漲跌: {res['diff']}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # 繪製 Plotly 圖表
                    p_df = df_one.tail(30)
                    sh, ih, sl, il, x_axis = res['lines']
                    fig = go.Figure(data=[go.Candlestick(
                        x=p_df.index, open=p_df['Open'], high=p_df['High'], low=p_df['Low'], close=p_df['Close'], name="K線"
                    )])
                    
                    # 疊加 MA20 與 形態趨勢線
                    fig.add_trace(go.Scatter(x=p_df.index, y=p_df['MA20'], line=dict(color='#3498db', width=1.5), name="MA20"))
                    fig.add_trace(go.Scatter(x=p_df.tail(15).index, y=sh*x_axis + ih, line=dict(color='#e74c3c', dash='dash'), name="壓"))
                    fig.add_trace(go.Scatter(x=p_df.tail(15).index, y=sl*x_axis + il, line=dict(color='#2ecc71', dash='dash'), name="撐"))
                    
                    fig.update_layout(height=350, margin=dict(l=5,r=5,t=5,b=5), xaxis_rangeslider_visible=False, template="plotly_white", showlegend=False)
                    st.plotly_chart(fig, use_container_width=True, key=f"s_{ticker}")
                    found_cnt += 1
        except: continue

    if found_cnt == 0:
        st.warning("☹️ 掃描完畢，沒有符合條件的股票，請放寬篩選標準。")
    else:
        st.success(f"🎊 掃描完畢！在 {len(db)} 檔中發現 {found_cnt} 檔優質標的。")
else:
    st.info("💡 點擊左側「開始全量掃描」按鈕來分析 800+ 檔電子股形態。")
