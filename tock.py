import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import json
import os
from streamlit_autorefresh import st_autorefresh

# ==========================================
# 0. 資料庫核心：讀取 JSON
# ==========================================
DB_FILE = "electronic_stocks_db.json"

def load_organized_db():
    if not os.path.exists(DB_FILE):
        return {"電子": {"2330.TW": {"name": "台積電", "category": "電子"}}}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    
    organized = {}
    for sid, info in raw_data.items():
        cat = info.get("category", "電子板塊")
        if cat not in organized: organized[cat] = {}
        organized[cat][sid] = info.get("name", "未知個股")
    return organized

@st.cache_data(ttl=300)
def get_k_line_data(sid):
    try:
        df = yf.download(sid, period="45d", progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): 
            df.columns = df.columns.get_level_values(0)
        return df.dropna()
    except: return None

# ==========================================
# 1. 專業介面 CSS (移除成交量小框框)
# ==========================================
st.set_page_config(page_title="Pro-X 形態大師", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans TC', sans-serif; background-color: #f8fafc; }

    /* 左側側邊欄固定 */
    section[data-testid="stSidebar"] { background-color: #ffffff !important; border-right: 2px solid #eef2f6; }

    /* 分類大標題 */
    .sector-header {
        font-size: 24px; font-weight: 700; color: #1e293b;
        background: white; padding: 15px 25px; border-radius: 12px;
        margin: 30px 0 15px 0; border-left: 10px solid #6366f1;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }

    /* 股票卡片：純淨版 (移除右上角資訊欄) */
    .stock-card {
        background: white; padding: 22px; border-radius: 18px;
        border: 1px solid #e2e8f0; margin-bottom: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }
    
    .stock-title { font-size: 22px; font-weight: 700; color: #4338ca; text-decoration: none; }
    
    /* 形態標籤 */
    .tag-pattern { 
        display: inline-block; background: #f3e8ff; color: #7e22ce; 
        padding: 4px 12px; border-radius: 8px; font-size: 14px; 
        font-weight: 700; margin-top: 10px; 
    }
    .tag-vol { 
        display: inline-block; background: #fee2e2; color: #dc2626; 
        padding: 4px 12px; border-radius: 8px; font-size: 14px; 
        font-weight: 700; margin-top: 10px; 
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 側邊欄控制 (左側介面固定)
# ==========================================
db_groups = load_organized_db()

with st.sidebar:
    st.markdown("<h1 style='color:#6366f1;'>🎯 形態大師控制台</h1>", unsafe_allow_html=True)
    st.divider()
    
    # 功能模式選單
    st.radio("選擇功能模式", ["⚡ 今日即時監控", "⏳ 歷史形態搜尋", "🌐 顯示所有連結"])
    
    st.divider()
    search_q = st.text_input("🔍 過濾股票代號", placeholder="輸入代號...")
    
    st.divider()
    st_autorefresh(interval=600000, key="fixed_nav")
    if st.button("🔄 刷新數據"):
        st.cache_data.clear()
        st.rerun()

# ==========================================
# 3. 主畫面：卡片渲染 (已拿掉成交張數)
# ==========================================
st.markdown("<h2 style='text-align:center;'>🚀 智能個股監控終端</h2>", unsafe_allow_html=True)

final_groups = {}
if search_q:
    for cat, stocks in db_groups.items():
        match = {sid: name for sid, name in stocks.items() if search_q in sid}
        if match: final_groups[cat] = match
else:
    final_groups = db_groups

for category, stocks in final_groups.items():
    st.markdown(f'<div class="sector-header">📂 {category}板塊</div>', unsafe_allow_html=True)
    
    for sid, name in stocks.items():
        # 卡片內容：只保留連結標題與形態標籤
        st.markdown(f"""
        <div class="stock-card">
            <div>
                <a class="stock-title" href="https://tw.stock.yahoo.com/quote/{sid.split('.')[0]}" target="_blank">
                    🔗 {sid.split('.')[0]} {name}
                </a>
            </div>
            <div>
                <span class="tag-pattern">📐 三角收斂</span>
                <span class="tag-vol">🚀 今日爆量</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # 展開圖表 (純 K 線，無成交量)
        with st.expander("📈 展開形態圖表"):
            df = get_k_line_data(sid)
            if df is not None:
                fig = go.Figure(data=[go.Candlestick(
                    x=df.index, open=df['Open'], high=df['High'], 
                    low=df['Low'], close=df['Close']
                )])
                fig.update_layout(
                    height=350, margin=dict(t=10, b=10, l=10, r=10),
                    xaxis_rangeslider_visible=False,
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#f8fafc"
                )
                st.plotly_chart(fig, use_container_width=True, key=f"f_{sid}")


