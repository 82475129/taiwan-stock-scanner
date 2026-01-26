import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import json
import os
import time
import concurrent.futures
from streamlit_autorefresh import st_autorefresh

# ==========================================
# 0. 系統核心與資料庫處理邏輯
# ==========================================
DB_FILE = "electronic_stocks_db.json"

def load_full_database():
    """讀取 JSON 並依照 category 分類，確保資料結構完整"""
    if not os.path.exists(DB_FILE):
        st.warning("找不到 electronic_stocks_db.json，使用預設測試資料")
        return {
            "電子板塊": {
                "2330.TW": {"name": "台積電", "category": "電子板塊"},
                "2317.TW": {"name": "鴻海", "category": "電子板塊"},
                "2379.TW": {"name": "瑞昱", "category": "電子板塊"},
                "2365.TW": {"name": "昆盈", "category": "電子板塊"}
            }
        }
    
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        organized = {}
        for sid, info in data.items():
            cat = info.get("category", "未分類")
            if cat not in organized:
                organized[cat] = {}
            organized[cat][sid] = info.get("name", "未知個股")
        return organized
    except Exception as e:
        st.error(f"讀取資料庫失敗：{e}")
        return {"錯誤": {"無資料": "請檢查 electronic_stocks_db.json"}}

@st.cache_data(ttl=600)
def fetch_stock_history(sid):
    """獲取技術分析所需的 K 線數據"""
    try:
        df = yf.download(sid, period="45d", progress=False)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df.dropna()
    except:
        return None

# ==========================================
# 1. 頁面設定與專業介面 CSS
# ==========================================
st.set_page_config(
    page_title="台股 Pro-X 旗艦終端",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Noto+Sans+TC:wght@400;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Noto Sans TC', sans-serif;
        background-color: #f4f7fa;
    }

    section[data-testid="stSidebar"] {
        background-color: #ffffff !important;
        border-right: 2px solid #e2e8f0;
        min-width: 320px;
    }

    .sector-header-box {
        background: #ffffff;
        padding: 15px 25px;
        border-radius: 12px;
        margin: 30px 0 15px 0;
        border-left: 10px solid #6366f1;
        box-shadow: 0 4px 6px rgba(0,0,0,0.02);
    }
    .sector-title {
        font-size: 24px;
        font-weight: 700;
        color: #1e293b;
    }

    .stock-card {
        background: white;
        padding: 24px;
        border-radius: 16px;
        border: 1px solid #e2e8f0;
        margin-bottom: 20px;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .stock-card:hover {
        transform: translateY(-5px);
        border-color: #6366f1;
        box-shadow: 0 10px 25px rgba(99, 102, 241, 0.1);
    }
    
    .stock-name-link {
        font-size: 20px;
        font-weight: 700;
        color: #4338ca;
        text-decoration: none;
    }
    .stock-name-link:hover {
        color: #5b21b6;
        text-decoration: underline;
    }

    .status-tag {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 6px;
        font-size: 12px;
        font-weight: 700;
        background: #f0fdf4;
        color: #16a34a;
        border: 1px solid #dcfce7;
    }
    
    .stButton > button {
        background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
        color: white;
        border: none;
        padding: 12px;
        border-radius: 10px;
        font-weight: 700;
        width: 100%;
        box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 左側邊欄：控制面板（完整固定）
# ==========================================
full_db = load_full_database()

with st.sidebar:
    st.markdown("<h2 style='color:#6366f1; margin-bottom:0;'>PRO-X 控制中心</h2>", unsafe_allow_html=True)
    st.caption("即時資料庫監控系統 v5.0")
    st.divider()

    st.markdown("### 🔎 搜尋過濾")
    search_input = st.text_input(
        "輸入股票代號或名稱",
        placeholder="搜尋如: 2330 / 台積電",
        key="sidebar_search"
    )
    
    st.markdown("### ⚙️ 系統維護")
    st_autorefresh(interval=600000, key="fixed_nav")  # 10分鐘自動刷新
    
    if st.button("🔄 重整資料庫快取", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    if st.button("🔄 強制重新載入頁面", use_container_width=True):
        st.rerun()
    
    st.divider()
    st.info("💡 操作提示：點擊右側卡片可展開技術圖表。")

# ==========================================
# 3. 主畫面：分組渲染邏輯（已完全移除成交量相關顯示）
# ==========================================
st.markdown(
    "<h1 style='text-align:center; color:#1e293b; margin:1.5rem 0;'>🎯 智能分組監控終端</h1>",
    unsafe_allow_html=True
)
st.caption(f"資料最後更新時間：{time.strftime('%Y-%m-%d %H:%M:%S')}")

# 搜尋過濾邏輯
render_data = {}
search_input = (search_input or "").strip()
if search_input:
    for cat, stocks in full_db.items():
        filtered = {
            sid: info["name"]
            for sid, info in stocks.items()
            if search_input in sid.upper() or search_input.upper() in info["name"].upper()
        }
        if filtered:
            render_data[cat] = filtered
else:
    render_data = {cat: {sid: info["name"] for sid, info in stocks.items()} 
                   for cat, stocks in full_db.items()}

if not render_data:
    st.warning("⚠️ 在資料庫中找不到匹配的項目，請調整搜尋條件或檢查資料庫檔案。")
else:
    for category, stocks in render_data.items():
        st.markdown(f"""
        <div class="sector-header-box">
            <span class="sector-title">📂 {category}板塊</span>
        </div>
        """, unsafe_allow_html=True)
        
        cols = st.columns(2)
        for idx, (sid, name) in enumerate(stocks.items()):
            col = cols[idx % 2]
            with col:
                st.markdown(f"""
                <div class="stock-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <a class="stock-name-link" href="https://tw.stock.yahoo.com/quote/{sid.split('.')[0]}" target="_blank">
                            🔗 {sid.split('.')[0]}　{name}
                        </a>
                        <span class="status-tag">監控中</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                with st.expander("📊 查看即時技術形態", expanded=False):
                    df = fetch_stock_history(sid)
                    if df is not None and not df.empty:
                        fig = go.Figure(data=[go.Candlestick(
                            x=df.index,
                            open=df['Open'],
                            high=df['High'],
                            low=df['Low'],
                            close=df['Close'],
                            increasing_line_color='#ef4444',
                            decreasing_line_color='#22c55e'
                        )])
                        fig.update_layout(
                            height=380,
                            margin=dict(t=20, b=40, l=10, r=10),
                            xaxis_rangeslider_visible=False,
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="#ffffff",
                            font=dict(family="Noto Sans TC"),
                            xaxis=dict(showgrid=True, gridcolor='#f1f5f9'),
                            yaxis=dict(showgrid=True, gridcolor='#f1f5f9')
                        )
                        st.plotly_chart(fig, use_container_width=True, key=f"chart_{sid}")
                    else:
                        st.warning(f"無法取得 {sid} 的資料（可能為停牌、非交易日或網路問題）")

st.markdown("---")
st.caption("提示：請定期執行 generate_db.py 更新 electronic_stocks_db.json 以保持最新清單。")
