import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
from streamlit_autorefresh import st_autorefresh
import json, os

# ================================
# 1. 系統初始化與自動清除邏輯
# ================================
st.set_page_config(page_title="台股 Pro 旗艦戰情室", layout="wide")

if 'favorites' not in st.session_state:
    st.session_state.favorites = set()
if 'results_data' not in st.session_state:
    st.session_state.results_data = []
if 'last_mode' not in st.session_state:
    st.session_state.last_mode = None

# ================================
# 2. 股票資料庫 (載入台灣市場清單)
# ================================
@st.cache_data(ttl=3600)
def load_db():
    path = "taiwan_full_market.json"
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {"2330.TW": "台積電", "2454.TW": "聯發科", "2603.TW": "長榮", "2317.TW": "鴻海"}

full_db = load_db()

# ================================
# 3. 抓取資料 (處理 yfinance 資料格式)
# ================================
def fetch_price(symbol):
    df = yf.download(symbol, period="1y", auto_adjust=True, progress=False)
    if df.empty: return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna()

# ================================
# 4. 技術分析引擎 (形態偵測 + 趨勢判斷)
# ================================
def run_analysis(sid, name, df, cfg, is_manual=False):
    if df.empty or 'Close' not in df or len(df) < 60:
        return None
    try:
        # 基礎指標計算
        c = float(df['Close'].iloc[-1])
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        ma60 = df['Close'].rolling(60).mean().iloc[-1]
        trend = '🔴 多頭' if ma20 > ma60 else '🟢 空頭'

        # 形態回溯計算 (壓力與支撐線)
        lb = cfg.get("p_lookback", 15)
        x = np.arange(lb)
        h, l = df["High"].iloc[-lb:].values, df["Low"].iloc[-lb:].values
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        
        # 訊號特徵偵測
        active_hits = []
        if (sh < -0.001 and sl > 0.001): active_hits.append("📐三角收斂")
        if (abs(sh) < 0.03 and abs(sl) < 0.03): active_hits.append("📦箱型整理")
        v_avg = df["Volume"].iloc[-21:-1].mean()
        if (df["Volume"].iloc[-1] > v_avg * 1.8): active_hits.append("🚀今日爆量")

        # 篩選過濾邏輯
        if is_manual:
            should_show = True # 手動模式或收藏模式，清除所有限制
        else:
            hit_match = any([
                cfg.get("check_tri") and "📐" in "".join(active_hits),
                cfg.get("check_box") and "📦" in "".join(active_hits),
                cfg.get("check_vol") and "🚀" in "".join(active_hits)
            ])
            should_show = hit_match
            if cfg.get("f_ma_filter") and c < ma20: should_show = False
            if c < cfg.get("min_price", 0): should_show = False

        if should_show:
            return {
                "收藏": sid in st.session_state.favorites,
                "sid": sid, "名稱": name, "現價": round(c, 2),
                "趨勢": trend, "MA20": round(ma20, 2), "MA60": round(ma60, 2),
                "符合訊號": ", ".join(active_hits) if active_hits else "🔍觀察中",
                "Yahoo": f"https://tw.stock.yahoo.com/quote/{sid.split('.')[0]}.TW",
                "df": df, "lines": (sh, ih, sl, il, x)
            }
    except: pass
    return None

# ================================
# 5. 側邊欄與模式監控 (執行清除動作)
# ================================
st.sidebar.title("🛡️ 戰術控制台")
mode = st.sidebar.radio("模式切換", ["🔍 手動查詢", "⚖️ 條件篩選", "⚡ 自動掃描", "❤️ 收藏追蹤"])

# 重點：偵測模式切換，一進新模式就清空 results_data
if st.session_state.last_mode != mode:
    st.session_state.results_data = [] # 清除舊結果
    st.session_state.last_mode = mode # 更新當前模式紀錄

# 模式參數設定
cfg = {"p_lookback": 15, "min_price": 0, "check_tri": True, "check_box": True, "check_vol": True, "f_ma_filter": False}

if mode in ["⚖️ 條件篩選", "⚡ 自動掃描"]:
    st.sidebar.divider()
    st.sidebar.subheader("🎯 篩選條件設定")
    cfg["check_tri"] = st.sidebar.checkbox("📐 三角收斂", True)
    cfg["check_box"] = st.sidebar.checkbox("📦 箱型整理", True)
    cfg["check_vol"] = st.sidebar.checkbox("🚀 今日爆量", True)
    cfg["f_ma_filter"] = st.sidebar.checkbox("限 MA20 之上", True)
    cfg["min_price"] = st.sidebar.slider("最低股價門檻", 0, 1000, 0)
    cfg["scan_limit"] = st.sidebar.slider("掃描上限", 30, 200, 50)

# ================================
# 6. 主畫面各模式邏輯
# ================================
st.title(f"📈 {mode}")

# --- 手動模式 ---
if mode == "🔍 手動查詢":
    code = st.text_input("輸入股票代碼 (例如: 2330, 2603)", placeholder="多筆請用逗號隔開")
    if code:
        raw_list = code.replace("，", ",").split(",")
        temp_res = []
        for c in raw_list:
            sym = c.strip().upper()
            sym = sym if '.TW' in sym else f"{sym}.TW"
            df = fetch_price(sym)
            res = run_analysis(sym, full_db.get(sym, sym.split('.')[0]), df, cfg, is_manual=True)
            if res: temp_res.append(res)
        st.session_state.results_data = temp_res

# --- 條件篩選 ---
elif mode == "⚖️ 條件篩選":
    st.info("模式已切換：請設定左側參數並點擊下方按鈕開始掃描。")
    if st.button("🚀 開始篩選標的", type="primary"):
        temp_res = []
        codes = list(full_db.keys())[:cfg.get('scan_limit', 50)]
        with st.status("正在依據條件分析市場...") as status:
            for s in codes:
                df = fetch_price(s)
                res = run_analysis(s, full_db.get(s, "未知"), df, cfg, is_manual=False)
                if res: temp_res.append(res)
            st.session_state.results_data = temp_res
            status.update(label="✅ 篩選完成", state="complete")

# --- 自動掃描 ---
elif mode == "⚡ 自動掃描":
    st_autorefresh(interval=60000, key="auto_refresh")
    st.warning("每 60 秒自動更新市場掃描結果")
    codes = list(full_db.keys())[:30]
    temp_res = []
    for s in codes:
        df = fetch_price(s)
        res = run_analysis(s, full_db.get(s, "未知"), df, cfg, is_manual=False)
        if res: temp_res.append(res)
    st.session_state.results_data = temp_res

# --- 收藏追蹤 ---
elif mode == "❤️ 收藏追蹤":
    if not st.session_state.favorites:
        st.info("目前追蹤清單為空。")
    else:
        if st.button("🔄 立即更新收藏股報價"):
            temp_res = []
            for s in st.session_state.favorites:
                df = fetch_price(s)
                res = run_analysis(s, full_db.get(s, s), df, cfg, is_manual=True)
                if res: temp_res.append(res)
            st.session_state.results_data = temp_res

# ================================
# 7. 數據渲染與 K 線圖表
# ================================
display_data = st.session_state.results_data

# 收藏追蹤模式下的特殊過濾
if mode == "❤️ 收藏追蹤":
    display_data = [r for r in display_data if r['sid'] in st.session_state.favorites]

if display_data:
    # 頂部數據表格
    t_df = pd.DataFrame([{
        "收藏": r["收藏"], "代碼": r["sid"], "名稱": r["名稱"], 
        "現價": r["現價"], "趨勢": r["趨勢"], "訊號": r["符合訊號"], "Yahoo": r["Yahoo"]
    } for r in display_data])

    edit = st.data_editor(
        t_df,
        column_config={
            "收藏": st.column_config.CheckboxColumn("❤️"),
            "Yahoo": st.column_config.LinkColumn("Yahoo", display_text="🔍"),
        },
        use_container_width=True, hide_index=True, key=f"table_view_{mode}"
    )

    # 處理即時收藏變更
    current_favs = set(edit[edit["收藏"] == True]["代碼"])
    if current_favs != st.session_state.favorites:
        st.session_state.favorites = current_favs
        st.rerun()

    st.divider()

    # 底部 K 線圖卡片區
    for r in display_data:
        with st.expander(f"📈 {r['sid']} {r['名稱']}｜{r['符合訊號']}", expanded=True):
            c1, c2, c3 = st.columns(3)
            c1.metric("目前價格", f"{r['現價']} 元")
            c2.metric("MA20 支撐", r["MA20"])
            c3.metric("趨勢方向", r["趨勢"])
            
            df_t, (sh, ih, sl, il, x) = r["df"].iloc[-60:], r["lines"]
            fig = go.Figure(data=[go.Candlestick(
                x=df_t.index, open=df_t['Open'], high=df_t['High'], 
                low=df_t['Low'], close=df_t['Close'], name='K線'
            )])
            
            # 加入壓力與支撐趨勢線 (來自 linregress)
            fig.add_scatter(x=df_t.index[-len(x):], y=sh*x+ih, mode='lines', line=dict(color='red', dash='dash'), name='壓力線')
            fig.add_scatter(x=df_t.index[-len(x):], y=sl*x+il, mode='lines', line=dict(color='green', dash='dash'), name='支撐線')
            
            fig.update_layout(height=400, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True, key=f"chart_{r['sid']}_{mode}")
else:
    if mode == "⚖️ 條件篩選":
        st.write("---")
        st.caption("🔍 尚未開始篩選，請確認參數後按下「開始篩選標的」。")
