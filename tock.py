import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
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
def get_full_stock_data(sid):
    try:
        # 抓取包含 Open, High, Low, Close, Volume 的完整數據
        df = yf.download(sid, period="45d", progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): 
            df.columns = df.columns.get_level_values(0)
        return df.dropna()
    except: return None

# ==========================================
# 1. 介面美化 CSS (鎖定左側 + 專業卡片)
# ==========================================
st.set_page_config(page_title="Pro-X 形態大師", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans TC', sans-serif; background-color: #fcfcfc; }

    /* 固定左側邊欄 */
    section[data-testid="stSidebar"] { background-color: #ffffff !important; border-right: 2px solid #f1f5f9; }

    /* 分類大標題 */
    .sector-header {
        font-size: 24px; font-weight: 700; color: #0f172a;
        background: white; padding: 15px 25px; border-radius: 12px;
        margin: 30px 0 15px 0; border-left: 10px solid #6366f1;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
    }

    /* 專業卡片樣式 */
    .stock-card {
        background: white; padding: 25px; border-radius: 18px;
        border: 1px solid #e2e8f0; margin-bottom: 20px;
        transition: all 0.3s ease;
    }
    .stock-card:hover { transform: translateY(-4px); border-color: #6366f1; box-shadow: 0 12px 20px rgba(99, 102, 241, 0.1); }
    
    .stock-title { font-size: 20px; font-weight: 700; color: #4338ca; text-decoration: none; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 側邊欄控制中心 (固定在左邊)
# ==========================================
db_groups = load_organized_db()

with st.sidebar:
    st.markdown("<h2 style='color:#6366f1;'>PRO-X 控制台</h2>", unsafe_allow_html=True)
    st.divider()
    
    search_q = st.text_input("🔍 快速搜尋代號", placeholder="輸入代號...")
    
    st.divider()
    st.markdown("### ⚙️ 系統維護")
    st_autorefresh(interval=600000, key="fixed_nav")
    
    if st.button("🔄 刷新快取數據"):
        st.cache_data.clear()
        st.rerun()

# ==========================================
# 3. 主畫面：K 線 + 成交量雙層圖表
# ==========================================
st.markdown("<h2 style='text-align:center;'>🎯 智能分組監控終端</h2>", unsafe_allow_html=True)

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
        st.markdown(f'<div class="sector-header">📁 {category}板塊</div>', unsafe_allow_html=True)
        
        cols = st.columns(2)
        for i, (sid, name) in enumerate(stocks.items()):
            with cols[i % 2]:
                st.markdown(f"""
                <div class="stock-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <a class="stock-title" href="https://tw.stock.yahoo.com/quote/{sid.split('.')[0]}" target="_blank">
                            🔗 {sid.split('.')[0]} {name}
                        </a>
                        <span style="background:#f1f5f9; color:#6366f1; padding:4px 10px; border-radius:8px; font-size:12px; font-weight:700;">監視中</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                with st.expander("📈 查看完整 K 線與成交量"):
                    df = get_full_stock_data(sid)
                    if df is not None:
                        # 建立子圖：第一行畫 K 線 (70%高度)，第二行畫成交量 (30%高度)
                        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                           vertical_spacing=0.05, row_heights=[0.7, 0.3])

                        # 1. K 線圖
                        fig.add_trace(go.Candlestick(
                            x=df.index, open=df['Open'], high=df['High'], 
                            low=df['Low'], close=df['Close'], name="K線"
                        ), row=1, col=1)

                        # 2. 成交量 (Volume) - 根據漲跌自動上色
                        colors = ['#ef4444' if row['Close'] >= row['Open'] else '#22c55e' for _, row in df.iterrows()]
                        fig.add_trace(go.Bar(
                            x=df.index, y=df['Volume'], name="成交量",
                            marker_color=colors, opacity=0.8
                        ), row=2, col=1)

                        fig.update_layout(
                            height=500, margin=dict(t=10, b=10, l=10, r=10),
                            xaxis_rangeslider_visible=False,
                            showlegend=False,
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#f8fafc"
                        )
                        st.plotly_chart(fig, use_container_width=True, key=f"f_{sid}")
                    else:
                        st.warning("數據獲取超時")
