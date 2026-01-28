import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
from streamlit_autorefresh import st_autorefresh
import json, os

# ================================
# 1. 系統初始化
# ================================
st.set_page_config(page_title="台股 Pro 旗艦戰情室", layout="wide")

if 'favorites' not in st.session_state:
    st.session_state.favorites = set()
if 'results_data' not in st.session_state:
    st.session_state.results_data = []

# ================================
# 2. 股票資料庫
# ================================
@st.cache_data(ttl=3600)
def load_db():
    path = "taiwan_full_market.json"
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {"2330.TW": "台積電", "2454.TW": "聯發科", "2603.TW": "長榮"}

full_db = load_db()

# ================================
# 3. 抓取資料 (修正防 MultiIndex)
# ================================
def fetch_price(symbol):
    df = yf.download(symbol, period="1y", auto_adjust=True, progress=False)
    if df.empty: return df
    # 處理 yfinance 可能回傳的 MultiIndex 欄位
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna()

# ================================
# 4. 技術分析核心
# ================================
def run_analysis(sid, name, df, cfg, is_manual=False):
    if df.empty or 'Close' not in df or len(df) < 60:
        return None
    try:
        # A. 基礎趨勢
        c = float(df['Close'].iloc[-1])
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        ma60 = df['Close'].rolling(60).mean().iloc[-1]
        trend = '🔴 多頭' if ma20 > ma60 else '🟢 空頭'

        # B. 形態偵測 (三角收斂/箱型/爆量)
        lb = cfg.get("p_lookback", 15)
        x = np.arange(lb)
        h, l = df["High"].iloc[-lb:].values, df["Low"].iloc[-lb:].values
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        
        active_hits = []
        if (sh < -0.001 and sl > 0.001): active_hits.append("📐三角收斂")
        if (abs(sh) < 0.03 and abs(sl) < 0.03): active_hits.append("📦箱型整理")
        v_avg = df["Volume"].iloc[-21:-1].mean()
        if (df["Volume"].iloc[-1] > v_avg * 1.8): active_hits.append("🚀今日爆量")

        # C. 篩選邏輯判斷
        # 手動查詢與收藏清單模式下 is_manual 為 True，強制顯示
        should_show = is_manual 
        if not is_manual:
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
# 5. 側邊欄控制台
# ================================
st.sidebar.title("🛡️ 戰術控制台")
mode = st.sidebar.radio("模式切換", ["🔍 手動查詢", "⚖️ 條件篩選", "⚡ 自動掃描", "❤️ 收藏追蹤"])

# 預設參數
cfg = {"p_lookback": 15, "min_price": 0, "check_tri": True, "check_box": True, "check_vol": True, "f_ma_filter": True}

if mode != "❤️ 收藏追蹤":
    st.sidebar.divider()
    st.sidebar.subheader("⚙️ 訊號監控")
    cfg["check_tri"] = st.sidebar.checkbox("📐 三角收斂", True)
    cfg["check_box"] = st.sidebar.checkbox("📦 箱型整理", True)
    cfg["check_vol"] = st.sidebar.checkbox("🚀 今日爆量", True)
    
    with st.sidebar.expander("🛠️ 進階設定", expanded=(mode != "🔍 手動查詢")):
        cfg["p_lookback"] = st.slider("形態回溯天數", 10, 30, 15)
        cfg["f_ma_filter"] = st.checkbox("限 MA20 之上", True)
        cfg["min_price"] = st.slider("最低股價", 0, 1000, 0)
        cfg["scan_limit"] = st.slider("掃描上限", 30, 200, 50)

# ================================
# 6. 主畫面執行邏輯
# ================================
st.title(f"📈 {mode}")

if mode == "🔍 手動查詢":
    code = st.text_input("輸入股票代碼 (例如: 2330, 2603)")
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

elif mode == "⚖️ 條件篩選":
    if st.button("🚀 開始篩選"):
        temp_res = []
        codes = list(full_db.keys())[:cfg.get('scan_limit', 50)]
        with st.status("掃描全市場中...") as status:
            for s in codes:
                df = fetch_price(s)
                res = run_analysis(s, full_db.get(s, "未知"), df, cfg)
                if res: temp_res.append(res)
            st.session_state.results_data = temp_res
            status.update(label="✅ 篩選完成", state="complete")

elif mode == "⚡ 自動掃描":
    st.warning("自動輪巡中 (每 60 秒更新)")
    st_autorefresh(interval=60000, key="auto_scan")
    codes = list(full_db.keys())[:30]
    temp_res = []
    for s in codes:
        df = fetch_price(s)
        res = run_analysis(s, full_db.get(s, "未知"), df, cfg)
        if res: temp_res.append(res)
    st.session_state.results_data = temp_res

elif mode == "❤️ 收藏追蹤":
    if not st.session_state.favorites:
        st.info("尚無收藏標的。")
    else:
        if st.button("🔄 刷新數據"):
            temp_res = []
            for s in st.session_state.favorites:
                df = fetch_price(s)
                res = run_analysis(s, full_db.get(s, s), df, cfg, is_manual=True)
                if res: temp_res.append(res)
            st.session_state.results_data = temp_res

# ================================
# 7. 渲染顯示區
# ================================
display_data = st.session_state.results_data
if mode == "❤️ 收藏追蹤":
    display_data = [r for r in display_data if r['sid'] in st.session_state.favorites]

if display_data:
    # A. 數據表
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
        use_container_width=True, hide_index=True, key=f"table_{mode}"
    )

    # 同步收藏狀態
    new_favs = set(edit[edit["收藏"] == True]["代碼"])
    if new_favs != st.session_state.favorites:
        st.session_state.favorites = new_favs
        st.rerun()

    st.divider()

    # B. K 線圖
    for r in display_data:
        with st.expander(f"📊 {r['sid']} {r['名稱']}｜{r['趨勢']}｜{r['符合訊號']}", expanded=True):
            c1, c2, c3 = st.columns(3)
            c1.metric("收盤價", f"{r['現價']} 元")
            c2.metric("MA20", r["MA20"])
            c3.metric("趨勢", r["趨勢"])
            
            df_t, (sh, ih, sl, il, x) = r["df"].iloc[-60:], r["lines"]
            fig = go.Figure(data=[go.Candlestick(
                x=df_t.index, open=df_t['Open'], high=df_t['High'], 
                low=df_t['Low'], close=df_t['Close'], name='K線'
            )])
            
            # 畫壓力支撐
            fig.add_scatter(x=df_t.index[-len(x):], y=sh*x+ih, mode='lines', line=dict(color='red', dash='dash'), name='壓力')
            fig.add_scatter(x=df_t.index[-len(x):], y=sl*x+il, mode='lines', line=dict(color='green', dash='dash'), name='支撐')
            
            fig.update_layout(height=450, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True, key=f"k_{r['sid']}_{mode}")
else:
    st.info("請輸入代碼或執行掃描。")
