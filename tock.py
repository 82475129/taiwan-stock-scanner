import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import os
import time
import concurrent.futures
from streamlit_autorefresh import st_autorefresh

# ==========================================
# 1. 全域系統配置與資料庫路徑
# ==========================================
DB_FILE = "electronic_stocks_db.json"
st.set_page_config(page_title="Pro-X 智能終端系統", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# 2. 核心資料處理函數 (後端邏輯)
# ==========================================

def load_organized_db():
    """讀取 JSON 並依照 category 進行結構化分組"""
    if not os.path.exists(DB_FILE):
        # 初始預設資料，防止讀取失敗
        return {"電子板塊": {"2330.TW": {"name": "台積電", "category": "電子板塊"}}}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        
        organized = {}
        for sid, info in raw_data.items():
            # 支援您的爬蟲格式: {"2330.TW": {"name": "台積電", "category": "電子"}}
            cat = info.get("category", "未分類板塊")
            if cat not in organized:
                organized[cat] = {}
            organized[cat][sid] = info.get("name", "未知名稱")
        return organized
    except Exception as e:
        st.error(f"資料庫讀取失敗: {e}")
        return {}

def save_to_json(sid, name, category):
    """將新搜尋的股票寫入 JSON 資料庫"""
    db = {}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
    
    db[sid] = {"name": name, "category": category}
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=4)

@st.cache_data(ttl=300)
def fetch_stock_financials(sid):
    """抓取 K 線數據並處理 yfinance 的多重索引問題"""
    try:
        ticker = yf.Ticker(sid)
        df = ticker.history(period="60d", interval="1d")
        if df.empty: return None
        # 修正欄位名稱
        df = df.reset_index()
        return df
    except:
        return None

# ==========================================
# 3. 專業視覺美化 (CSS 注入)
# ==========================================
st.markdown("""
<style>
    /* 引入專業字體 */
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Noto+Sans+TC:wght@400;700&display=swap');
    
    html, body, [class*="css"] { font-family: 'Noto Sans TC', sans-serif; background-color: #f4f7f9; }

    /* 左側側邊欄固定樣式 (不隨主畫面滾動或閃爍) */
    section[data-testid="stSidebar"] {
        background-color: #ffffff !important;
        border-right: 2px solid #eef2f6;
        padding-top: 2rem;
    }

    /* 分類區塊大標題 */
    .category-container {
        background: white;
        padding: 15px 25px;
        border-radius: 12px;
        margin: 35px 0 20px 0;
        border-left: 10px solid #4f46e5;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .category-text { font-size: 24px; font-weight: 700; color: #1e293b; }

    /* 股票卡片樣式 */
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
        border-color: #4f46e5;
        box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
    }

    .stock-id-title {
        font-size: 20px; font-weight: 700; color: #4f46e5; text-decoration: none;
    }

    /* 高級漸層按鈕 */
    .stButton>button {
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
        color: white; border: none; padding: 12px 24px;
        border-radius: 12px; font-weight: 700; width: 100%;
        transition: all 0.3s;
    }
    .stButton>button:hover {
        opacity: 0.9;
        box-shadow: 0 8px 20px rgba(79, 70, 229, 0.4);
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 4. 左側側邊欄固定區 (Sidebar)
# ==========================================
organized_db = load_organized_db()

with st.sidebar:
    st.markdown("<h2 style='color:#4f46e5;'>PRO-X 終端</h2>", unsafe_allow_html=True)
    st.caption("版本 4.0 | 資料庫連動版")
    st.divider()

    # 功能 A: 搜尋與寫入
    st.markdown("### 🔍 搜尋並寫入")
    new_input = st.text_input("輸入代號 (例如 2360)", key="search_input")
    
    if new_input:
        full_sid = f"{new_input.upper()}.TW" if "." not in new_input else new_input.upper()
        try:
            with st.spinner("查詢中..."):
                t = yf.Ticker(full_sid)
                s_name = t.info.get('shortName') or t.info.get('longName') or "未知個股"
            
            st.info(f"偵測標的: {s_name}")
            # 選擇現有分類或新增
            all_cats = list(organized_db.keys()) + ["+ 新增板塊"]
            selected_cat = st.selectbox("歸類板塊", all_cats)
            
            final_cat = selected_cat
            if selected_cat == "+ 新增板塊":
                final_cat = st.text_input("輸入新板塊名稱")
            
            if st.button("📥 寫入 JSON 資料庫"):
                save_to_json(full_sid, s_name, final_cat)
                st.success("寫入成功！")
                time.sleep(1)
                st.rerun()
        except:
            st.error("代號無效")

    st.divider()
    
    # 功能 B: 過濾與自動刷新
    st.markdown("### ⚙️ 介面過濾")
    filter_query = st.text_input("過濾主畫面代號", placeholder="輸入代號...")
    
    st_autorefresh(interval=600000, key="auto_ref") # 10分鐘自動更新
    
    if st.button("🔄 重整快取"):
        st.cache_data.clear()
        st.rerun()

# ==========================================
# 5. 主畫面渲染區 (Main Content)
# ==========================================
st.markdown("<h1 style='text-align:center;'>🎯 智能分組監控系統</h1>", unsafe_allow_html=True)

# 執行搜尋過濾
display_groups = {}
if filter_query:
    for cat, stocks in organized_db.items():
        sub_match = {sid: name for sid, name in stocks.items() if filter_query in sid}
        if sub_match: display_groups[cat] = sub_match
else:
    display_groups = organized_db

# 循環產生板塊
if not display_groups:
    st.warning("⚠️ 資料庫為空或查無符合項目，請於左側搜尋並寫入股票。")
else:
    for category, stocks in display_groups.items():
        # 分類標題區
        st.markdown(f"""
        <div class="category-container">
            <span class="category-text">📁 {category}</span>
        </div>
        """, unsafe_allow_html=True)
        
        # 股票卡片網格 (雙欄)
        cols = st.columns(2)
        for idx, (sid, name) in enumerate(stocks.items()):
            with cols[idx % 2]:
                st.markdown(f"""
                <div class="stock-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <a class="stock-id-title" href="https://tw.stock.yahoo.com/quote/{sid.split('.')[0]}" target="_blank">
                            🔗 {sid.split('.')[0]} {name}
                        </a>
                        <span style="background:#f1f5f9; color:#64748b; padding:4px 10px; border-radius:8px; font-size:12px;">
                            Active
                        </span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # 嵌入 K 線圖表
                with st.expander("📊 查看技術形態圖表"):
                    df_data = fetch_stock_financials(sid)
                    if df_data is not None:
                        fig = go.Figure(data=[go.Candlestick(
                            x=df_data['Date'],
                            open=df_data['Open'],
                            high=df_data['High'],
                            low=df_data['Low'],
                            close=df_data['Close']
                        )])
                        fig.update_layout(
                            height=350, margin=dict(t=0, b=0, l=0, r=0),
                            xaxis_rangeslider_visible=False,
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="#f8fafc"
                        )
                        st.plotly_chart(fig, use_container_width=True, key=f"fig_{sid}")
                    else:
                        st.error("數據獲取超時")
