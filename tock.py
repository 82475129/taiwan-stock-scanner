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
        return {"電子板塊": {"2330.TW": {"name": "台積電", "category": "電子板塊"}}}
    
    with open(DB_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # 將資料結構化：{分類名稱: {代號: 名稱}}
    organized = {}
    for sid, info in data.items():
        cat = info.get("category", "未分類")
        if cat not in organized:
            organized[cat] = {}
        organized[cat][sid] = info.get("name", "未知個股")
    return organized

@st.cache_data(ttl=600)
def fetch_stock_history(sid):
    """獲取技術分析所需的 K 線數據"""
    try:
        # 下載 45 天數據確保技術指標計算完整
        df = yf.download(sid, period="45d", progress=False)
        if df.empty: return None
        # 修正 yfinance 多重索引問題
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df.dropna()
    except:
        return None

# ==========================================
# 1. 介面美化 CSS (拒絕單調連結，改用專業卡片)
# ==========================================
st.set_page_config(page_title="台股 Pro-X 旗艦終端", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Noto+Sans+TC:wght@400;700&display=swap');
    
    /* 整體背景色與字體 */
    html, body, [class*="css"] { font-family: 'Noto Sans TC', sans-serif; background-color: #f4f7fa; }

    /* 左側側邊欄固定樣式 */
    section[data-testid="stSidebar"] {
        background-color: #ffffff !important;
        border-right: 2px solid #e2e8f0;
        min-width: 320px;
    }

    /* 分類大標題區塊 */
    .sector-header-box {
        background: #ffffff;
        padding: 15px 25px;
        border-radius: 12px;
        margin: 30px 0 15px 0;
        border-left: 10px solid #6366f1;
        box-shadow: 0 4px 6px rgba(0,0,0,0.02);
    }
    .sector-title { font-size: 24px; font-weight: 700; color: #1e293b; }

    /* 專業個股卡片 */
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

    /* 專業狀態標籤 */
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
    
    /* 左側按鈕樣式 */
    .stButton>button {
        background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
        color: white; border: none; padding: 12px; border-radius: 10px;
        font-weight: 700; width: 100%; box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 左側邊欄：控制面板 (介面固定不動)
# ==========================================
full_db = load_full_database()

with st.sidebar:
    st.markdown("<h2 style='color:#6366f1;'>PRO-X 控制中心</h2>", unsafe_allow_html=True)
    st.caption("即時資料庫監控系統 v5.0")
    st.divider()

    # 搜尋與篩選鎖定在此
    st.markdown("### 🔎 搜尋過濾")
    search_input = st.text_input("輸入股票代號或名稱", placeholder="搜尋如: 2330")
    
    st.markdown("### ⚙️ 系統維護")
    st_autorefresh(interval=600000, key="fixed_nav") # 10分鐘自動刷新
    
    if st.button("🔄 重整資料庫快取"):
        st.cache_data.clear()
        st.rerun()
    
    st.divider()
    st.info("💡 操作提示：點擊右側卡片可展開技術圖表。")

# ==========================================
# 3. 主畫面：分組渲染邏輯
# ==========================================
st.markdown("<h1 style='text-align:center;'>🎯 智能分組監控終端</h1>", unsafe_allow_html=True)

# 搜尋邏輯處理
render_data = {}
if search_input:
    for cat, stocks in full_db.items():
        # 同時搜尋代號與名稱
        filtered = {sid: name for sid, name in stocks.items() if search_input in sid or search_input in name}
        if filtered: render_data[cat] = filtered
else:
    render_data = full_db

# 開始渲染板塊
if not render_data:
    st.warning("⚠️ 在資料庫中找不到匹配的項目。")
else:
    for category, stocks in render_data.items():
        # 繪製分類標題區
        st.markdown(f"""
        <div class="sector-header-box">
            <span class="sector-title">📂 {category}板塊</span>
        </div>
        """, unsafe_allow_html=True)
        
        # 採用兩欄式佈局，視覺更平衡
        cols = st.columns(2)
        for i, (sid, name) in enumerate(stocks.items()):
            current_col = cols[i % 2]
            with current_col:
                # 繪製美化卡片
                st.markdown(f"""
                <div class="stock-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <a class="stock-name-link" href="https://tw.stock.yahoo.com/quote/{sid.split('.')[0]}" target="_blank">
                            🔗 {sid.split('.')[0]} {name}
                        </a>
                        <span class="status-tag">監控中</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # 下拉式技術圖表 (不點擊時保持畫面乾淨)
                with st.expander("📊 查看即時技術形態"):
                    df_price = fetch_stock_history(sid)
                    if df_price is not None:
                        fig = go.Figure(data=[go.Candlestick(
                            x=df_price.index,
                            open=df_price['Open'],
                            high=df_price['High'],
                            low=df_price['Low'],
                            close=df_price['Close']
                        )])
                        fig.update_layout(
                            height=350, margin=dict(t=0, b=0, l=0, r=0),
                            xaxis_rangeslider_visible=False,
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="#f8fafc"
                        )
                        st.plotly_chart(fig, use_container_width=True, key=f"chart_{sid}")
                    else:
                        st.error("暫時無法獲取該股技術數據")
