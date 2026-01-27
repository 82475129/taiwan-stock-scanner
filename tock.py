import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import sys, json, os

# ==========================================
# 0. 環境偵測與 Session 初始化
# ==========================================
IS_STREAMLIT = hasattr(st, "runtime") and st.runtime.exists()
DB_FILES = ["taiwan_electronic_stocks.json", "taiwan_full_market.json"]

# 統一 Session 處理，避免 thread 錯誤
if IS_STREAMLIT:
    st.set_page_config(page_title="台股 Pro-X 終端", layout="wide")
    if 'favorites' not in st.session_state:
        st.session_state.favorites = {}

def get_favorites():
    return st.session_state.favorites if IS_STREAMLIT else {}

@st.cache_data(ttl=3600)
def load_and_fix_db():
    target_file = next((f for f in DB_FILES if os.path.exists(f)), None)
    if not target_file: return {"2330.TW": "台積電"}
    try:
        with open(target_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
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
def run_analysis(df, sid, name, config, force_show=False):
    if df is None or len(df) < 30: return None
    try:
        df = df.dropna()
        c = float(df["Close"].iloc[-1])
        m20 = df["Close"].rolling(20).mean().iloc[-1]
        v_last = df["Volume"].iloc[-1]
        v_avg = df["Volume"].iloc[-21:-1].mean()
        
        d_len = 15
        x = np.arange(d_len)
        h, l = df["High"].iloc[-d_len:].values, df["Low"].iloc[-d_len:].values
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        
        hits = []
        if sh < -0.001 and sl > 0.001: hits.append("📐三角收斂")
        if abs(sh) < 0.02 and abs(sl) < 0.02: hits.append("📦箱型整理")
        if v_last > v_avg * 2: hits.append("🚀今日爆量")
        
        if force_show:
            return {"sid": sid, "name": name, "price": round(c, 2), "vol": int(v_last/1000), "hits": hits if hits else ["🔍觀察"], "df": df, "lines": (sh, ih, sl, il, x)}
        
        is_hit = False
        if config["f_tri"] and "📐三角收斂" in hits: is_hit = True
        if config["f_box"] and "📦箱型整理" in hits: is_hit = True
        if config["f_vol"] and "🚀今日爆量" in hits: is_hit = True
        if config.get("f_ma20") and c < m20: is_hit = False
        
        if is_hit:
            return {"sid": sid, "name": name, "price": round(c, 2), "vol": int(v_last/1000), "hits": hits, "df": df, "lines": (sh, ih, sl, il, x)}
        return None
    except: return None

# ==========================================
# 2. 左側介面 (Sidebar)
# ==========================================
full_db = load_and_fix_db()
all_codes = list(full_db.keys())
sectors = ["全部"] + sorted(list(set(get_auto_sector(c) for c in all_codes)))

with st.sidebar:
    st.title("🎯 交易控制台")
    app_mode = st.radio("🛰️ 模式", ["⚡ 自動雷達", "🛠️ 手動工具"])
    st.divider()

    st.subheader("🔍 代碼搜尋 (強顯)")
    search_input = st.text_input("輸入代碼 (2330, 2454)", key="search_box")
    
    st.subheader("⚙️ 篩選設定")
    selected_sector = st.selectbox("產業分類", sectors)
    f_tri = st.checkbox("📐 三角收斂", True)
    f_box = st.checkbox("📦 箱型整理", True)
    f_vol = st.checkbox("🚀 今日爆量", False)
    f_ma20 = st.checkbox("📈 股價 > MA20", False)
    config = {"f_tri": f_tri, "f_box": f_box, "f_vol": f_vol, "f_ma20": f_ma20}
    
    min_v = st.number_input("成交量門檻 (張)", value=500)
    scan_limit = st.slider("掃描上限", 50, 2000, 100)
    
    # 邏輯判斷是否啟動
    trigger_scan = False
    if app_mode == "🛠️ 手動工具":
        if st.button("🚀 開始手動掃描", type="primary"): trigger_scan = True
    else:
        trigger_scan = True

    st.divider()
    st.subheader("❤️ 我的最愛")
    favs = get_favorites()
    if not favs: st.caption("尚未收藏")
    else:
        for fid, fname in list(favs.items()):
            fcol1, fcol2 = st.columns([4, 1])
            fcol1.markdown(f"**{fid}** {fname}")
            if fcol2.button("🗑️", key=f"side_del_{fid}"):
                del st.session_state.favorites[fid]
                st.rerun()

# ==========================================
# 3. 掃描執行 (整合邏輯)
# ==========================================
if IS_STREAMLIT: st.title(f"📈 形態雷達 ({app_mode})")

is_searching = bool(search_input)
active_codes = [c.strip() + ".TW" if "." not in c else c.strip().upper() for c in search_input.split(",")] if is_searching else \
               (all_codes if selected_sector == "全部" else [c for c in all_codes if get_auto_sector(c) == selected_sector])

results = []
if trigger_scan:
    try:
        # 下載初步成交量數據
        v_data = yf.download(active_codes, period="5d", progress=False)["Volume"]
        latest_v = v_data.iloc[-1] if not v_data.iloc[-1].isna().all() else v_data.iloc[-2]
        vol_filtered = (latest_v / 1000).dropna()
        
        targets = vol_filtered.index.tolist() if is_searching else vol_filtered[vol_filtered >= min_v].sort_values(ascending=False).head(scan_limit).index.tolist()
        
        if targets:
            batch_size = 40 # 縮小批次以降低執行緒壓力
            for i in range(0, len(targets), batch_size):
                batch = targets[i : i + batch_size]
                h_data = yf.download(batch, period="3mo", group_by="ticker", progress=False)
                for sid in batch:
                    df_sid = h_data[sid] if len(batch) > 1 else h_data
                    res = run_analysis(df_sid, sid, full_db.get(sid, "未知"), config, force_show=is_searching)
                    if res: results.append(res)
    except Exception as e:
        st.error(f"📡 掃描暫時中斷: {e}")

# ==========================================
# 4. 結果顯示 (表格垂直換行)
# ==========================================
if results:
    st.subheader("📊 掃描總覽")
    # 處理垂直換行
    summary_data = []
    for r in results:
        summary_data.append({
            "代碼": f"https://tw.stock.yahoo.com/quote/{r['sid']}",
            "名稱": r["name"],
            "現價": r["price"],
            "張數": r["vol"],
            "狀態": "\n".join(r["hits"]) # 使用換行
        })
    
    st.dataframe(
        pd.DataFrame(summary_data),
        column_config={
            "代碼": st.column_config.LinkColumn("代碼", display_text=r"quote/(.*)$"),
            "狀態": st.column_config.TextColumn("符合形態", width="medium") # 確保寬度足夠換行
        },
        hide_index=True, use_container_width=True
    )

    for item in results:
        c_title, c_fav = st.columns([5, 1])
        with c_title:
            exp = st.expander(f"🔍 {item['sid']} {item['name']} | {' + '.join(item['hits'])}", expanded=is_searching)
        with c_fav:
            is_fav = item['sid'] in st.session_state.favorites
            # 收藏按鈕：點擊後僅更新 state，不強制 global rerun 減少報錯
            if st.button("❤️" if is_fav else "🤍 收藏", key=f"fav_{item['sid']}"):
                if is_fav: del st.session_state.favorites[item['sid']]
                else: st.session_state.favorites[item['sid']] = item['name']
                st.rerun()
        with exp:
            df_t, (sh, ih, sl, il, x) = item["df"].iloc[-15:], item["lines"]
            fig = go.Figure(data=[go.Candlestick(x=df_t.index, open=df_t['Open'], high=df_t['High'], low=df_t['Low'], close=df_t['Close'], name='K線')])
            fig.add_scatter(x=df_t.index, y=sh*x+ih, mode='lines', line=dict(color='red', dash='dash'), name='壓力')
            fig.add_scatter(x=df_t.index, y=sl*x+il, mode='lines', line=dict(color='green', dash='dash'), name='支撐')
            fig.update_layout(height=400, xaxis_rangeslider_visible=False, margin=dict(l=5, r=5, t=5, b=5))
            st.plotly_chart(fig, use_container_width=True)
elif trigger_scan:
    st.warning("💡 未找到符合條件的股票。")
