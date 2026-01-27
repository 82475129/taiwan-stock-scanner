import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import os, json

# ==========================================
# 1. 系統初始化
# ==========================================
st.set_page_config(page_title="台股 Pro 旗艦戰情室", layout="wide")

if 'favorites' not in st.session_state:
    st.session_state.favorites = set() 
if 'results_data' not in st.session_state:
    st.session_state.results_data = [] 

@st.cache_data(ttl=3600)
def load_db():
    return {"2330.TW": "台積電", "2454.TW": "聯發科", "2603.TW": "長榮", "2317.TW": "鴻海"} # 範例，可自載 JSON

# ==========================================
# 2. 核心分析引擎 (修正數據抓取邏輯)
# ==========================================
def run_analysis(sid, name, df, config, is_manual=False):
    """
    is_manual=True 時，跳過所有過濾邏輯，直接回傳數據
    """
    if df is None or len(df) < 20: return None
    try:
        df = df.dropna()
        c = float(df["Close"].iloc[-1])
        v_last = df["Volume"].iloc[-1]
        
        # 形態計算
        lb = config.get("p_lookback", 15)
        if len(df) < lb: lb = len(df)
        x = np.arange(lb)
        h, l = df["High"].iloc[-lb:].values, df["Low"].iloc[-lb:].values
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        
        active_hits = []
        if (sh < -0.001 and sl > 0.001): active_hits.append("📐三角收斂")
        if (abs(sh) < 0.03 and abs(sl) < 0.03): active_hits.append("📦箱型整理")
        if (v_last > df["Volume"].iloc[-21:-1].mean() * 1.8): active_hits.append("🚀今日爆量")
        
        if is_manual:
            # 手動模式：只要有數據就顯示
            pure_id = sid.split('.')[0]
            return {
                "收藏": sid in st.session_state.favorites,
                "sid": sid, "名稱": name, "現價": round(c, 2), 
                "符合訊號": ", ".join(active_hits) if active_hits else "🔍觀察中",
                "Yahoo": f"https://tw.stock.yahoo.com/quote/{pure_id}.TW",
                "df": df, "lines": (sh, ih, sl, il, x)
            }
        else:
            # 自動模式：執行過濾
            hit_match = any([
                config.get("check_tri") and "📐" in "".join(active_hits),
                config.get("check_box") and "📦" in "".join(active_hits),
                config.get("check_vol") and "🚀" in "".join(active_hits)
            ])
            ma_m = df["Close"].rolling(config.get("p_ma_m", 20)).mean().iloc[-1]
            if config.get("f_ma_filter") and c < ma_m: hit_match = False
            
            if hit_match:
                return {
                    "收藏": sid in st.session_state.favorites,
                    "sid": sid, "名稱": name, "現價": round(c, 2), 
                    "符合訊號": ", ".join(active_hits),
                    "Yahoo": f"https://tw.stock.yahoo.com/quote/{sid.split('.')[0]}.TW",
                    "df": df, "lines": (sh, ih, sl, il, x)
                }
    except Exception as e:
        print(f"Error analyzing {sid}: {e}")
    return None

# ==========================================
# 3. Sidebar 控制面板
# ==========================================
full_db = load_db()
with st.sidebar:
    st.title("🛡️ 戰術控制台")
    app_mode = st.radio("模式切換", ["⚡ 自動掃描", "🔍 手動模式", "❤️ 追蹤清單"])
    
    # 切換模式清空數據
    if "prev_mode" not in st.session_state: st.session_state.prev_mode = app_mode
    if app_mode != st.session_state.prev_mode:
        st.session_state.results_data = []
        st.session_state.prev_mode = app_mode
        st.rerun()

    st.divider()
    st.subheader("⚙️ 全域參數")
    p_ma_m = st.number_input("均線參考 (MA)", value=20)
    p_lookback = st.slider("形態回溯天數", 10, 30, 15)
    
    if app_mode == "⚡ 自動掃描":
        check_tri = st.checkbox("📐 三角收斂", True)
        check_box = st.checkbox("📦 箱型整理", True)
        check_vol = st.checkbox("🚀 今日爆量", True)
        f_ma_filter = st.checkbox("限 MA20 之上", True)
        min_v = st.number_input("成交量門檻 (張)", value=500)
        scan_limit = st.slider("掃描數量", 10, 200, 50)
    
    config = locals()

# ==========================================
# 4. 主頁面：手動輸入區 (完全獨立)
# ==========================================
st.title(f"📍 {app_mode}")

if app_mode == "🔍 手動模式":
    with st.container():
        col1, col2 = st.columns([4, 1])
        with col1:
            s_input = st.text_input("輸入代碼", placeholder="例如: 2330, 2603", help="多筆請用逗號隔開")
        with col2:
            st.write(" ") 
            manual_exec = st.button("🚀 立即分析", type="primary", use_container_width=True)
    
    if manual_exec and s_input:
        raw_codes = [c.strip().upper() for c in s_input.replace("，", ",").split(",") if c.strip()]
        final_codes = [c if "." in c else f"{c}.TW" for c in raw_codes]
        
        with st.spinner("抓取數據中..."):
            # 這裡強迫一次只抓指定的代碼
            temp_res = []
            for sid in final_codes:
                df = yf.download(sid, period="6mo", progress=False)
                if not df.empty:
                    name = full_db.get(sid, sid.split('.')[0])
                    res = run_analysis(sid, name, df, config, is_manual=True)
                    if res: temp_res.append(res)
            st.session_state.results_data = temp_res

# ==========================================
# 5. 自動掃描與追蹤清單邏輯
# ==========================================
if app_mode == "⚡ 自動掃描" and not st.session_state.results_data:
    if st.button("📡 開始全市場掃描"):
        codes = list(full_db.keys())[:scan_limit]
        with st.status("掃描中...") as status:
            temp_res = []
            for sid in codes:
                df = yf.download(sid, period="6mo", progress=False)
                if not df.empty and (df["Volume"].iloc[-1] / 1000 >= min_v):
                    res = run_analysis(sid, full_db.get(sid, "未知"), df, config)
                    if res: temp_res.append(res)
            st.session_state.results_data = temp_res
            status.update(label="掃描完成！", state="complete")

# ==========================================
# 6. 渲染顯示區
# ==========================================
display_data = st.session_state.results_data
if app_mode == "❤️ 追蹤清單":
    # 追蹤清單模式需要重新抓取數據
    if st.button("🔄 更新追蹤清單數據"):
        temp_res = []
        for sid in st.session_state.favorites:
            df = yf.download(sid, period="6mo", progress=False)
            if not df.empty:
                res = run_analysis(sid, full_db.get(sid, sid), df, config, is_manual=True)
                if res: temp_res.append(res)
        st.session_state.results_data = temp_res
    display_data = [r for r in st.session_state.results_data if r['sid'] in st.session_state.favorites]

if display_data:
    # 數據表格
    table_df = pd.DataFrame([{
        "收藏": r["收藏"], "代碼": r["sid"], "名稱": r["名稱"], "現價": r["現價"], "符合訊號": r["符合訊號"]
    } for r in display_data])
    
    st.data_editor(table_df, hide_index=True, use_container_width=True, disabled=True)

    # K線圖
    for r in display_data:
        with st.expander(f"📈 {r['sid']} {r['名稱']} - {r['符合訊號']}", expanded=True):
            df_t = r["df"].iloc[-60:]
            fig = go.Figure(data=[go.Candlestick(
                x=df_t.index, open=df_t['Open'], high=df_t['High'], 
                low=df_t['Low'], close=df_t['Close']
            )])
            # 只有手動輸入或符合訊號才畫線
            sh, ih, sl, il, x = r["lines"]
            fig.add_scatter(x=df_t.index[-len(x):], y=sh*x+ih, mode='lines', line=dict(color='red', dash='dash'), name='壓力')
            fig.add_scatter(x=df_t.index[-len(x):], y=sl*x+il, mode='lines', line=dict(color='green', dash='dash'), name='支撐')
            
            fig.update_layout(height=400, xaxis_rangeslider_visible=False, margin=dict(l=5, r=5, t=5, b=5))
            st.plotly_chart(fig, use_container_width=True)
            
            # 收藏按鈕
            if st.button(f"{'💔 取消收藏' if r['sid'] in st.session_state.favorites else '❤️ 加入收藏'} {r['sid']}", key=f"btn_{r['sid']}"):
                if r['sid'] in st.session_state.favorites:
                    st.session_state.favorites.remove(r['sid'])
                else:
                    st.session_state.favorites.add(r['sid'])
                st.rerun()
else:
    st.info("目前沒有數據。請在手動模式輸入代碼，或執行自動掃描。")
