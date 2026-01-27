import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import sys, json, os

# ==========================================
# 0. 系統基礎設定與 Session 初始化
# ==========================================
DB_FILES = ["taiwan_electronic_stocks.json", "taiwan_full_market.json"]

st.set_page_config(page_title="台股 Pro-X 形態大師", layout="wide")

# 初始化最愛清單 (Session 儲存，重新整理前都會在)
if 'favorites' not in st.session_state:
    st.session_state.favorites = {} 

@st.cache_data(ttl=3600)
def load_and_fix_db():
    target_file = next((f for f in DB_FILES if os.path.exists(f)), None)
    if not target_file: return {"2330.TW": "台積電"}
    try:
        with open(target_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        # 針對截圖中提到的 .TW.TW 進行自動修正
        return {k.replace(".TW.TW", ".TW").strip(): v for k, v in raw_data.items()}
    except: return {"2330.TW": "台積電"}

def get_auto_sector(sid):
    prefix = sid[:2]
    mapping = {
        "11": "水泥", "12": "食品", "13": "塑膠", "14": "紡織", "15": "機電",
        "16": "電纜", "17": "化學", "18": "玻璃", "19": "造紙", "20": "鋼鐵",
        "21": "橡膠", "22": "汽車", "23": "電子/半導體", "24": "電腦/通信",
        "25": "營建", "26": "航運", "27": "觀光", "28": "金融", "29": "百貨",
        "30": "電子通路", "31": "其它電子", "65": "油電燃氣", "99": "其它"
    }
    return mapping.get(prefix, "其它")

# ==========================================
# 1. 核心分析引擎
# ==========================================
def run_analysis(df, sid, name, config):
    if df is None or len(df) < 30: return None
    try:
        df = df.dropna()
        c = float(df["Close"].iloc[-1])
        m20 = df["Close"].rolling(20).mean().iloc[-1]
        v_last = df["Volume"].iloc[-1]
        v_avg = df["Volume"].iloc[-21:-1].mean()
        
        if config["f_ma20"] and c < m20: return None
        
        d_len = 15
        x = np.arange(d_len)
        h, l = df["High"].iloc[-d_len:].values, df["Low"].iloc[-d_len:].values
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        
        hits = []
        if config["f_tri"] and sh < -0.001 and sl > 0.001: hits.append("📐 三角收斂")
        if config["f_box"] and abs(sh) < 0.02 and abs(sl) < 0.02: hits.append("📦 箱型整理")
        if config["f_vol"] and v_last > v_avg * 2: hits.append("🚀 今日爆量")
        
        if not hits: return None
        return {"sid": sid, "name": name, "price": round(c, 2), "vol": int(v_last/1000), "hits": hits, "df": df, "lines": (sh, ih, sl, il, x)}
    except: return None

# ==========================================
# 2. 左側介面 (Sidebar)
# ==========================================
full_db = load_and_fix_db()
all_codes = list(full_db.keys())
sectors = ["全部"] + sorted(list(set(get_auto_sector(c) for c in all_codes)))

with st.sidebar:
    st.title("🏹 交易監控中心")
    
    # --- A. 我的最愛區塊 ---
    with st.container():
        st.subheader("❤️ 我的最愛清單")
        if not st.session_state.favorites:
            st.info("尚未收藏標的")
        else:
            # 以簡潔列表呈現
            for fid, fname in list(st.session_state.favorites.items()):
                fcol1, fcol2 = st.columns([4, 1])
                fcol1.markdown(f"**{fid}** {fname}")
                if fcol2.button("🗑️", key=f"del_{fid}"):
                    del st.session_state.favorites[fid]
                    st.rerun()
            if st.button("清除全部收藏"):
                st.session_state.favorites = {}
                st.rerun()
    
    st.divider()
    
    # --- B. 掃描控制參數 ---
    st.subheader("⚙️ 掃描參數")
    selected_sector = st.selectbox("產業分類", sectors)
    
    st.write("形態過濾")
    f_tri = st.checkbox("📐 三角收斂", True)
    f_box = st.checkbox("📦 箱型整理", True)
    f_vol = st.checkbox("🚀 今日爆量", False)
    f_ma20 = st.checkbox("📈 股價 > MA20", False)
    config = {"f_tri": f_tri, "f_box": f_box, "f_vol": f_vol, "f_ma20": f_ma20}
    
    st.divider()
    min_v = st.number_input("成交量門檻 (張)", value=500, step=100)
    scan_limit = st.slider("掃描上限 (由大到小)", 50, 2000, 100)
    
    st.caption("版本: Pro-X Auto v2.1")

# ==========================================
# 3. 主畫面掃描邏輯
# ==========================================
st.title("📈 形態大師：即時雷達")

active_codes = all_codes if selected_sector == "全部" else [c for c in all_codes if get_auto_sector(c) == selected_sector]
results = []

# 自動執行掃描
with st.status(f"📡 掃描中: {selected_sector}...", expanded=False) as status:
    v_df = yf.download(active_codes, period="5d", progress=False)["Volume"]
    latest_v = v_df.iloc[-1] if not v_df.iloc[-1].isna().all() else v_df.iloc[-2]
    vol_filtered = (latest_v / 1000).dropna()
    targets = vol_filtered[vol_filtered >= min_v].sort_values(ascending=False).head(scan_limit).index.tolist()
    
    if targets:
        batch_size = 50
        for i in range(0, len(targets), batch_size):
            batch = targets[i : i + batch_size]
            h_data = yf.download(batch, period="3mo", group_by="ticker", progress=False)
            for sid in batch:
                df_sid = h_data[sid] if len(batch) > 1 else h_data
                res = run_analysis(df_sid, sid, full_db.get(sid, "未知"), config)
                if res: results.append(res)
    status.update(label=f"✅ 完成！找到 {len(results)} 檔符合標的", state="complete")

# ==========================================
# 4. 資料視覺化 (表格 + 圖表)
# ==========================================
if results:
    # --- 頂部總覽表格 ---
    st.subheader("📊 形態偵測總覽 (代碼連動 Yahoo)")
    summary_df = pd.DataFrame([{
        "代碼": f"https://tw.stock.yahoo.com/quote/{r['sid']}",
        "名稱": r["name"],
        "現價": r["price"],
        "成交量(張)": r["vol"],
        "符合形態": " / ".join(r["hits"]),
        "SID": r['sid'] # 隱藏用
    } for r in results])

    st.dataframe(
        summary_df,
        column_config={
            "代碼": st.column_config.LinkColumn("代碼", display_text=r"quote/(.*)$"),
            "SID": None
        },
        hide_index=True,
        use_container_width=True
    )

    st.divider()
    
    # --- 詳細圖表區 ---
    st.subheader("🖼️ 技術形態細節")
    for item in results:
        # 佈置標題與收藏按鈕
        col_title, col_fav = st.columns([5, 1])
        with col_title:
            exp = st.expander(f"🔍 {item['sid']} {item['name']} | {' + '.join(item['hits'])}", expanded=False)
        with col_fav:
            is_fav = item['sid'] in st.session_state.favorites
            if st.button("❤️" if is_fav else "🤍 收藏", key=f"btn_{item['sid']}"):
                if is_fav:
                    del st.session_state.favorites[item['sid']]
                else:
                    st.session_state.favorites[item['sid']] = item['name']
                st.rerun()

        with exp:
            df_t, (sh, ih, sl, il, x) = item["df"].iloc[-15:], item["lines"]
            fig = go.Figure(data=[go.Candlestick(x=df_t.index, open=df_t['Open'], high=df_t['High'], low=df_t['Low'], close=df_t['Close'], name='K線')])
            fig.add_scatter(x=df_t.index, y=sh*x+ih, mode='lines', line=dict(color='red', dash='dash'), name='壓力')
            fig.add_scatter(x=df_t.index, y=sl*x+il, mode='lines', line=dict(color='green', dash='dash'), name='支撐')
            fig.update_layout(height=400, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("💡 目前條件下沒有符合形態的股票。")
