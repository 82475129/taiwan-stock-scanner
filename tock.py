import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import json
import os
from streamlit_autorefresh import st_autorefresh

# ==========================================
# 0. 資料庫核心：讀取 JSON 並自動分類
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
        # 只抓取價格數據
        df = yf.download(sid, period="45d", progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): 
            df.columns = df.columns.get_level_values(0)
        return df.dropna()
    except: return None

# ==========================================
# 1. 專業介面 CSS (比照你截圖的高級質感)
# ==========================================
st.set_page_config(page_title="Pro-X 形態大師", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans TC', sans-serif; background-color: #f8fafc; }

    /* 固定左側邊欄 */
    section[data-testid="stSidebar"] { background-color: #ffffff !important; border-right: 2px solid #eef2f6; }

    /* 分類大標題樣式 (專業紫色側條) */
    .sector-header {
        font-size: 24px; font-weight: 700; color: #1e293b;
        background: white; padding: 15px 25px; border-radius: 12px;
        margin: 30px 0 15px 0; border-left: 10px solid #6366f1;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }

    /* 股票卡片美化 */
    .stock-card {
        background: white; padding: 25px; border-radius: 20px;
        border: 1px solid #e2e8f0; margin-bottom: 10px;
        transition: all 0.2s ease;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }
    .stock-card:hover { transform: translateY(-3px); border-color: #6366f1; }
    
    .stock-title { font-size: 22px; font-weight: 700; color: #4338ca; text-decoration: none; }
    
    /* 標籤樣式 (紅/紫) */
    .tag-red { background: #fee2e2; color: #dc2626; padding: 4px 12px; border-radius: 8px; font-size: 13px; font-weight: 700; }
    .tag-purple { background: #f3e8ff; color: #7e22ce; padding: 4px 12px; border-radius: 8px; font-size: 13px; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 側邊欄控制中心 (左邊介面固定不動)
# ==========================================
db_groups = load_organized_db()

with st.sidebar:
    st.markdown("<h1 style='color:#6366f1;'>PRO-X 控制台</h1>", unsafe_allow_html=True)
    st.divider()
    
    search_q = st.text_input("🔍 快速過濾代號", placeholder="輸入代號...")
    
    st.divider()
    st.markdown("### ⚙️ 系統設定")
    st_autorefresh(interval=600000, key="fixed_nav")
    
    if st.button("🔄 刷新數據"):
        st.cache_data.clear()
        st.rerun()

# ==========================================
# 3. 主畫面：純 K 線圖表 (拿掉成交量)
# ==========================================
st.markdown("<h2 style='text-align:center;'>🚀 智能個股監控終端</h2>", unsafe_allow_html=True)

final_groups = {}
if search_q:
    for cat, stocks in db_groups.items():
        match = {sid: name for sid, name in stocks.items() if search_q in sid}
        if match: final_groups[cat] = match
else:
    final_groups = db_groups

if not final_groups:
    st.info("💡 找不到符合條件的股票。")
else:
    for category, stocks in final_groups.items():
        st.markdown(f'<div class="sector-header">📂 {category}板塊</div>', unsafe_allow_html=True)
        
        cols = st.columns(2)
        for i, (sid, name) in enumerate(stocks.items()):
            with cols[i % 2]:
                st.markdown(f"""
                <div class="stock-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <a class="stock-title" href="https://tw.stock.yahoo.com/quote/{sid.split('.')[0]}" target="_blank">
                            🔗 {sid.split('.')[0]} {name}
                        </a>
                        <span class="tag-red">🚀 今日爆量</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                with st.expander("📈 展開形態圖表"):
                    df = get_k_line_data(sid)
                    if df is not None:
                        # 只有一個圖層，且完全拿掉成交量數據
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
                    else:
                        st.warning("暫無價格數據")
