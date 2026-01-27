import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import os, json

# ==========================================
# 1. 系統初始化與狀態管理
# ==========================================
st.set_page_config(page_title="台股 Pro 旗艦戰情室", layout="wide")

# 初始化 Session State 儲存空間
if 'favorites' not in st.session_state:
    st.session_state.favorites = set() 
if 'results_data' not in st.session_state:
    st.session_state.results_data = [] 
if 'last_config_key' not in st.session_state:
    st.session_state.last_config_key = ""

@st.cache_data(ttl=3600)
def load_db():
    """載入台股代碼對照表"""
    f = "taiwan_full_market.json"
    if os.path.exists(f):
        try:
            with open(f, "r", encoding="utf-8") as file:
                return json.load(file)
        except: return {"2330.TW": "台積電"}
    return {"2330.TW": "台積電"}

# ==========================================
# 2. 專業技術分析引擎
# ==========================================
def run_analysis(sid, name, df, config, is_manual=False):
    if df is None or len(df) < 60: return None
    try:
        df = df.dropna()
        c = float(df["Close"].iloc[-1])
        v_last = df["Volume"].iloc[-1]
        v_avg = df["Volume"].iloc[-21:-1].mean()
        ma_m = df["Close"].rolling(config.get("p_ma_m", 20)).mean().iloc[-1]
        
        # 形態回溯計算 (壓力/支撐線)
        lb = config.get("p_lookback", 15)
        x = np.arange(lb)
        h, l = df["High"].iloc[-lb:].values, df["Low"].iloc[-lb:].values
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        
        # 訊號偵測
        active_hits = []
        if (sh < -0.001 and sl > 0.001): active_hits.append("📐三角收斂")
        if (abs(sh) < 0.03 and abs(sl) < 0.03): active_hits.append("📦箱型整理")
        if (v_last > v_avg * 1.8): active_hits.append("🚀今日爆量")
        
        # 決定是否顯示 (手動模式則無視條件強制顯示)
        should_show = False
        if is_manual:
            should_show = True
        else:
            # 自動模式需符合勾選條件與均線過濾
            hit_match = any([
                config.get("check_tri") and "📐" in "".join(active_hits),
                config.get("check_box") and "📦" in "".join(active_hits),
                config.get("check_vol") and "🚀" in "".join(active_hits)
            ])
            should_show = hit_match
            if config.get("f_ma_filter") and c < ma_m: should_show = False
            
        if should_show:
            pure_id = sid.split('.')[0]
            return {
                "收藏": sid in st.session_state.favorites,
                "sid": sid, 
                "名稱": name, 
                "現價": round(c, 2), 
                "符合訊號": ", ".join(active_hits) if active_hits else "🔍觀察中",
                "Yahoo": f"https://tw.stock.yahoo.com/quote/{pure_id}.TW",
                "df": df, 
                "lines": (sh, ih, sl, il, x)
            }
    except: pass
    return None

# ==========================================
# 3. Sidebar 控制面板 (追蹤清單模式自動簡化)
# ==========================================
full_db = load_db()
with st.sidebar:
    st.title("🛡️ 戰術控制台")
    app_mode = st.radio("模式切換", ["⚡ 自動掃描", "🔍 手動模式", "❤️ 追蹤清單"])
    
    # 手動模式切換立即清空舊結果
    if "m_state" not in st.session_state: st.session_state.m_state = app_mode
    if app_mode != st.session_state.m_state:
        if app_mode == "🔍 手動模式": st.session_state.results_data = []
        st.session_state.m_state = app_mode
        st.rerun()

    if app_mode != "❤️ 追蹤清單":
        st.divider()
        st.subheader("📡 訊號監控 (自動模式有效)")
        check_tri = st.checkbox("📐 三角收斂", True)
        check_box = st.checkbox("📦 箱型整理", True)
        check_vol = st.checkbox("🚀 今日爆量", True)
        
        if app_mode == "🔍 手動模式":
            st.divider()
            s_input = st.text_input("輸入代碼 (例如: 2330, 2603)", key="manual_in")
            manual_exec = st.button("🔍 執行搜尋", type="primary", use_container_width=True)
        else: manual_exec = False

        with st.expander("🛠️ 參數設定", expanded=True):
            p_ma_m = st.number_input("均線 (MA)", value=20)
            p_lookback = st.slider("形態回溯天數", 10, 30, 15)
            f_ma_filter = st.checkbox("限 MA20 之上 (自動)", True)
            min_v = st.number_input("成交量門檻 (張)", value=500)
            scan_limit = st.slider("掃描上限", 50, 500, 100)
            config = locals()

        # 自動掃描觸發判定
        current_key = f"{app_mode}-{check_tri}-{check_box}-{check_vol}-{min_v}-{scan_limit}"
        trigger_scan = (app_mode == "⚡ 自動掃描" and current_key != st.session_state.last_config_key)
        if trigger_scan: st.session_state.last_config_key = current_key
    else: trigger_scan = False

# ==========================================
# 4. 執行與抓取邏輯
# ==========================================
st.title(f"📍 {app_mode}")

if app_mode == "⚡ 自動掃描" and (trigger_scan or not st.session_state.results_data):
    codes = list(full_db.keys())[:scan_limit]
    with st.status("📡 市場掃描中...", expanded=False) as status:
        data = yf.download(codes, period="6mo", group_by='ticker', progress=False)
        temp_res = []
        for sid in codes:
            df = data[sid] if len(codes) > 1 else data
            if not df.empty and (df["Volume"].iloc[-1] / 1000 >= min_v):
                res = run_analysis(sid, full_db.get(sid, "未知"), df, config)
                if res: temp_res.append(res)
        st.session_state.results_data = temp_res
        status.update(label="✅ 掃描完成", state="complete")

elif app_mode == "🔍 手動模式" and manual_exec:
    if not s_input:
        st.warning("請輸入代碼")
    else:
        # 處理輸入代碼，補齊 .TW
        raw_list = s_input.replace("，", ",").split(",")
        final_codes = [c.strip().upper() + ".TW" if "." not in c else c.strip().upper() for c in raw_list if c.strip()]
        
        with st.spinner("強制抓取數據中..."):
            data = yf.download(final_codes, period="6mo", group_by='ticker', progress=False)
            temp_res = []
            for sid in final_codes:
                df = data[sid] if len(final_codes) > 1 else data
                if df is not None and not df.empty:
                    name = full_db.get(sid, sid.split('.')[0])
                    # 手動模式：is_manual=True 保證顯示
                    res = run_analysis(sid, name, df, config, is_manual=True)
                    if res: temp_res.append(res)
            st.session_state.results_data = temp_res

# ==========================================
# 5. 表格與 K 線渲染 (核心顯示區)
# ==========================================
display_data = st.session_state.results_data
if app_mode == "❤️ 追蹤清單":
    display_data = [r for r in st.session_state.results_data if r['sid'] in st.session_state.favorites]

if display_data:
    # --- 表格區 ---
    st.subheader("📊 數據總覽 (可點擊愛心收藏)")
    table_df = pd.DataFrame([{
        "收藏": r["收藏"],
        "代碼": r["sid"],
        "名稱": r["名稱"],
        "現價": r["現價"],
        "符合訊號": r["符合訊號"],
        "Yahoo": r["Yahoo"]
    } for r in display_data])

    edited_df = st.data_editor(
        table_df,
        column_config={
            "收藏": st.column_config.CheckboxColumn("❤️", default=False),
            "Yahoo": st.column_config.LinkColumn("Yahoo", display_text="🔍"),
        },
        disabled=["代碼", "名稱", "現價", "符合訊號", "Yahoo"],
        hide_index=True, use_container_width=True, key=f"tbl_{app_mode}"
    )

    # 同步收藏狀態 (免重複下載)
    new_favs = set(edited_df[edited_df["收藏"] == True]["代碼"])
    if new_favs != st.session_state.favorites:
        st.session_state.favorites = new_favs
        for r in st.session_state.results_data:
            r["收藏"] = r["sid"] in new_favs
        st.rerun()

    st.divider()

    # --- K 線圖區 (標題顯示訊號) ---
    st.subheader("📈 技術分析圖表")
    for r in display_data:
        sid = r['sid']
        is_fav = sid in st.session_state.favorites
        
        # 標題連動訊號
        expander_title = f"{'❤️' if is_fav else '🔍'} {sid} {r['名稱']} | {r['符合訊號']}"
        
        with st.expander(expander_title, expanded=True):
            df_t, (sh, ih, sl, il, x) = r["df"].iloc[-60:], r["lines"]
            fig = go.Figure(data=[go.Candlestick(
                x=df_t.index, open=df_t['Open'], high=df_t['High'], 
                low=df_t['Low'], close=df_t['Close'], name='K線'
            )])
            
            # 只有符合特定形態才畫壓力支撐線
            if any(s in r["符合訊號"] for s in ["三角", "箱型"]):
                fig.add_scatter(x=df_t.index[-config["p_lookback"]:], y=sh*x+ih, 
                                mode='lines', line=dict(color='red', dash='dash'), name='壓力線')
                fig.add_scatter(x=df_t.index[-config["p_lookback"]:], y=sl*x+il, 
                                mode='lines', line=dict(color='green', dash='dash'), name='支撐線')
            
            fig.update_layout(
                height=450, 
                xaxis_rangeslider_visible=False, 
                margin=dict(l=10, r=10, t=10, b=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig, use_container_width=True, key=f"k_{sid}")
else:
    st.info("尚無符合條件之數據，請調整參數或執行搜尋。")
