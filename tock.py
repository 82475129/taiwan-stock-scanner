import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import json
import os
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# ==========================================
# 0. 資料庫核心：讀取 JSON（支援細分類）
# ==========================================
DB_FILE = "electronic_stocks_db.json"

def load_organized_db():
    if not os.path.exists(DB_FILE):
        st.warning("找不到 electronic_stocks_db.json，使用預設測試資料")
        return {
            "電子-半導體": {"2330.TW": "台積電", "2303.TW": "聯電"},
            "電子-零組件": {"2313.TW": "華通", "2059.TW": "川湖"},
            "電子-其他": {"2317.TW": "鴻海"}
        }
    
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        
        organized = {}
        for sid, info in raw_data.items():
            # 如果 generate_db.py 已細分 category 如 "電子-半導體"
            cat = info.get("category", "電子-其他")
            if cat not in organized:
                organized[cat] = {}
            organized[cat][sid] = info.get("name", "未知")
        return organized
    except Exception as e:
        st.error(f"讀取 JSON 失敗：{e}")
        return {"錯誤": {"無資料": "請檢查 JSON 檔案"}}

@st.cache_data(ttl=300)  # 5 分鐘快取
def get_k_line_data(sid: str) -> pd.DataFrame | None:
    try:
        df = yf.download(sid, period="60d", progress=False, auto_adjust=True)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]
        return df.dropna(how='all')
    except:
        return None

# ==========================================
# 1. 頁面設定與 CSS
# ==========================================
st.set_page_config(page_title="Pro-X 形態大師", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans TC', sans-serif !important; background-color: #f8fafc; }
    section[data-testid="stSidebar"] { background-color: #ffffff !important; border-right: 2px solid #eef2f6; }
    
    .sector-header {
        font-size: 24px; font-weight: 700; color: #1e293b;
        background: white; padding: 16px 24px; border-radius: 12px;
        margin: 32px 0 16px 0; border-left: 10px solid #6366f1;
        box-shadow: 0 4px 10px rgba(0,0,0,0.06);
    }
    .stock-card {
        background: white; padding: 20px; border-radius: 16px;
        border: 1px solid #e2e8f0; margin-bottom: 12px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.04);
    }
    .stock-title {
        font-size: 22px; font-weight: 700; color: #4338ca; text-decoration: none;
    }
    .stock-title:hover { color: #5b21b6; text-decoration: underline; }
    .tag {
        display: inline-block; padding: 5px 12px; border-radius: 10px;
        font-size: 13.5px; font-weight: 600; margin: 8px 6px 0 0;
    }
    .tag-pattern { background: #f3e8ff; color: #7e22ce; }
    .tag-vol { background: #fee2e2; color: #dc2626; }
    .tag-up { background: #dcfce7; color: #15803d; }
    .tag-down { background: #fee2e2; color: #b91c1c; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 側邊欄
# ==========================================
db_groups = load_organized_db()

with st.sidebar:
    st.markdown("<h1 style='color:#6366f1;'>🎯 形態大師控制台</h1>", unsafe_allow_html=True)
    st.caption("電子股即時形態監控")
    st.divider()
    
    mode = st.radio("功能模式", [
        "⚡ 今日即時監控",
        "⏳ 歷史形態搜尋",
        "🌐 顯示所有連結"
    ], index=0)
    
    st.divider()
    search_q = st.text_input("🔍 過濾代號／名稱", placeholder="2330 / 台積電")
    
    st.divider()
    st_autorefresh(interval=600000, key="autorefresh")  # 10分鐘自動刷新
    if st.button("🔄 強制刷新", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ==========================================
# 3. 主畫面
# ==========================================
st.markdown("<h2 style='text-align:center; color:#1e293b;'>🚀 智能電子股形態監控</h2>", unsafe_allow_html=True)
st.caption(f"資料最後更新：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}（yfinance + JSON）")

final_groups = {}
search_q = (search_q or "").strip().upper()

if search_q:
    for cat, stocks in db_groups.items():
        matched = {sid: name for sid, name in stocks.items() 
                   if search_q in sid.upper() or search_q in name.upper()}
        if matched:
            final_groups[cat] = matched
else:
    final_groups = db_groups

if not final_groups:
    st.info("目前沒有符合條件的股票，請調整搜尋或檢查 JSON 資料庫。")
else:
    for category, stocks in final_groups.items():
        st.markdown(f'<div class="sector-header">📂 {category}</div>', unsafe_allow_html=True)
        
        # 兩欄式排列（若股票 >=2 則分欄）
        cols = st.columns(2) if len(stocks) >= 2 else [st.container() for _ in range(1)]
        col_idx = 0
        
        for sid, name in stocks.items():
            with cols[col_idx % len(cols)]:
                # 示範標籤（之後可換成真實偵測）
                tags = [
                    '<span class="tag tag-pattern">📐 三角收斂</span>',
                    '<span class="tag tag-vol">🚀 放量</span>'
                ]
                
                df = get_k_line_data(sid)
                if df is not None and len(df) >= 2:
                    pct = (df['Close'][-1] - df['Close'][-2]) / df['Close'][-2] * 100
                    if pct > 0.5:
                        tags.append(f'<span class="tag tag-up">+{pct:.1f}%</span>')
                    elif pct < -0.5:
                        tags.append(f'<span class="tag tag-down">{pct:.1f}%</span>')
                
                st.markdown(f"""
                <div class="stock-card">
                    <div>
                        <a class="stock-title" href="https://tw.stock.yahoo.com/quote/{sid.split('.')[0]}" target="_blank">
                            {sid.split('.')[0]}　{name}
                        </a>
                    </div>
                    <div>{' '.join(tags)}</div>
                </div>
                """, unsafe_allow_html=True)
                
                with st.expander("📈 展開 K 線圖（近60日）", expanded=False):
                    if df is not None:
                        fig = go.Figure(data=[go.Candlestick(
                            x=df.index,
                            open=df['Open'], high=df['High'],
                            low=df['Low'], close=df['Close'],
                            increasing_line_color='#ef4444',  # 紅漲
                            decreasing_line_color='#22c55e'   # 綠跌
                        )])
                        fig.update_layout(
                            height=380,
                            margin=dict(t=20, b=30, l=10, r=10),
                            xaxis_rangeslider_visible=False,
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="#ffffff",
                            font=dict(family="Noto Sans TC"),
                            xaxis=dict(showgrid=True, gridcolor='#f1f5f9'),
                            yaxis=dict(showgrid=True, gridcolor='#f1f5f9')
                        )
                        st.plotly_chart(fig, use_container_width=True, key=f"chart_{sid}")
                    else:
                        st.warning(f"無法載入 {sid} 資料（非交易日或代號異常）")
            
            col_idx += 1

st.markdown("---")
st.caption("提示：請定期執行 generate_db.py 更新 electronic_stocks_db.json 以保持最新電子股清單。")
