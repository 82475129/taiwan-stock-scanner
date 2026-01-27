import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import os, json, time

# ==========================================
# 1. 基礎設定
# ==========================================
st.set_page_config(page_title="台股 Pro 旗艦戰情室", layout="wide")

if 'favorites' not in st.session_state: st.session_state.favorites = set()
if 'results_data' not in st.session_state: st.session_state.results_data = []
if 'last_config_key' not in st.session_state: st.session_state.last_config_key = ""

@st.cache_data(ttl=3600)
def load_db():
    f = "taiwan_full_market.json"
    if os.path.exists(f):
        try:
            with open(f, "r", encoding="utf-8") as file: return json.load(file)
        except: pass
    return {"2330.TW": "台積電"}

# ==========================================
# 2. 分析引擎 (手動模式無視任何過濾條件)
# ==========================================
def run_analysis(sid, name, df, config, is_manual=False):
    if df is None or len(df) < 20: return None
    try:
        df = df.dropna()
        c = float(df["Close"].iloc[-1])
        v_last = df["Volume"].iloc[-1]
        v_avg = df["Volume"].iloc[-21:-1].mean() if len(df) > 21 else v_last
        
        # 形態回溯
        lb = min(len(df), config.get("p_lookback", 15))
        x = np.arange(lb)
        h, l = df["High"].iloc[-lb:].values, df["Low"].iloc[-lb:].values
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        
        active_hits = []
        if (sh < -0.001 and sl > 0.001): active_hits.append("📐三角收斂")
        if (abs(sh) < 0.03 and abs(sl) < 0.03): active_hits.append("📦箱型整理")
        if (v_last > v_avg * 1.8): active_hits.append("🚀今日爆量")
        
        # 手動模式：只要有資料就回傳，不看任何開關或均線
        if is_manual:
            pure_id = sid.split('.')[0]
            return {
                "收藏": sid in st.session_state.favorites,
                "sid": sid, "名稱": name, "現價": round(c, 2), 
                "符合訊號": ", ".join(active_hits) if active_hits else "🔍觀察",
                "Yahoo": f"https://tw.stock.yahoo.com/quote/{pure_id}.TW",
                "df": df, "lines": (sh, ih, sl, il, x)
            }
        
        # 自動模式：才看過濾器
        hit_str = "".join(active_hits)
        is_hit = any([
            config.get("check_tri") and "📐" in hit_str,
            config.get("check_box") and "📦" in hit_str,
            config.get("check_vol") and "🚀" in hit_str
        ])
        ma_ok = not config.get("f_ma_filter") or c >= df["Close"].rolling(20).mean().iloc[-1]
        
        if is_hit and ma_ok:
            pure_id = sid.split('.')[0]
            return {
                "收藏": sid in st.session_state.favorites,
                "sid": sid, "名稱": name, "現價": round(c, 2), 
                "符合訊號": hit_str,
                "Yahoo": f"https://tw.stock.yahoo.com/quote/{pure_id}.TW",
                "df": df, "lines": (sh, ih, sl, il, x)
            }
    except: pass
    return None

# ==========================================
# 3. 側邊欄控制
# ==========================================
full_db = load_db()
with st.sidebar:
    st.title("🛡️ 戰術控制台")
    app_mode = st.radio("模式選擇", ["⚡ 自動掃描", "🔍 手動模式", "❤️ 追蹤清單"])
    
    if app_mode != "❤️ 追蹤清單":
        st.divider()
        check_tri = st.checkbox("📐 三角收斂", True)
        check_box = st.checkbox("📦 箱型整理", True)
        check_vol = st.checkbox("🚀 今日爆量", True)
        
        if app_mode == "🔍 手動模式":
            st.info("💡 手動模式會顯示所有輸入的股票，不受下方參數過濾。")
            s_input = st.text_input("輸入代碼 (例如: 2330, 2603)", value="2330")
            # 增加一個 unique key 確保按鈕觸發
            manual_exec = st.button("🚀 開始搜尋", type="primary", use_container_width=True)
        else:
            manual_exec = False

        with st.expander("🛠️ 進階參數", expanded=False):
            p_ma_m = 20
            p_lookback = st.slider("回溯天數", 10, 30, 15)
            f_ma_filter = st.checkbox("限 MA20 之上 (自動掃描用)", True)
            min_v = st.number_input("張數門檻", value=500)
            scan_limit = st.slider("上限", 50, 500, 100)
            config = locals()

# ==========================================
# 4. 抓取邏輯 (徹底解決輸入沒東西的問題)
# ==========================================
st.title(f"📍 {app_mode}")

if app_mode == "🔍 手動模式" and manual_exec:
    st.session_state.results_data = [] # 先清空防止卡死
    raw_list = s_input.replace("，", ",").split(",")
    targets = [c.strip().upper() + ".TW" if "." not in c else c.strip().upper() for c in raw_list if c.strip()]
    
    if targets:
        with st.spinner("正在強制抓取資料..."):
            # threads=False 避免 Streamlit 多線程衝突
            data = yf.download(targets, period="6mo", group_by='ticker', progress=False, threads=False)
            temp = []
            for sid in targets:
                # 解決 yfinance 單複數回傳結構不同的關鍵點
                df = data[sid] if len(targets) > 1 else data
                if df is not None and not df.empty:
                    name = full_db.get(sid, sid.split('.')[0])
                    res = run_analysis(sid, name, df, config, is_manual=True)
                    if res: temp.append(res)
            st.session_state.results_data = temp
            if not temp: st.error("找不到該代碼，請確認代碼是否正確。")

elif app_mode == "⚡ 自動掃描":
    # 這裡放自動掃描邏輯...
    codes = list(full_db.keys())[:scan_limit]
    # (省略部分與之前一致的自動掃描代碼，確保邏輯流暢)
    if not st.session_state.results_data or trigger_scan:
        with st.status("📡 掃描中..."):
            data = yf.download(codes, period="6mo", group_by='ticker', progress=False)
            temp = []
            for sid in codes:
                df = data[sid] if len(codes) > 1 else data
                if not df.empty and (df["Volume"].iloc[-1]/1000 >= min_v):
                    res = run_analysis(sid, full_db.get(sid, "未知"), df, config)
                    if res: temp.append(res)
            st.session_state.results_data = temp

# ==========================================
# 5. 渲染顯示 (使用時間戳避免表格卡死)
# ==========================================
display_data = st.session_state.results_data
if app_mode == "❤️ 追蹤清單":
    display_data = [r for r in st.session_state.results_data if r['sid'] in st.session_state.favorites]

if display_data:
    # 表格
    table_df = pd.DataFrame([{ "收藏": r["收藏"], "代碼": r["sid"], "名稱": r["名稱"], "現價": r["現價"], "符合訊號": r["符合訊號"], "Yahoo": r["Yahoo"] } for r in display_data])
    # 使用時間戳作為 Key 強制表格刷新
    edited_df = st.data_editor(table_df, column_config={"收藏": st.column_config.CheckboxColumn("❤️"), "Yahoo": st.column_config.LinkColumn("Yahoo", display_text="🔍")}, disabled=["代碼", "名稱", "現價", "符合訊號", "Yahoo"], hide_index=True, use_container_width=True, key=f"editor_{int(time.time())}")

    # 更新收藏
    new_favs = set(edited_df[edited_df["收藏"] == True]["代碼"])
    if new_favs != st.session_state.favorites:
        st.session_state.favorites = new_favs
        for r in st.session_state.results_data: r["收藏"] = r["sid"] in new_favs
        st.rerun()

    # K線
    for r in display_data:
        with st.expander(f"{'❤️' if r['sid'] in st.session_state.favorites else '🔍'} {r['sid']} {r['名稱']} | {r['符合訊號']}", expanded=True):
            df_t, (sh, ih, sl, il, x) = r["df"].iloc[-60:], r["lines"]
            fig = go.Figure(data=[go.Candlestick(x=df_t.index, open=df_t['Open'], high=df_t['High'], low=df_t['Low'], close=df_t['Close'], name='K線')])
            # 只有符合訊號才畫線
            if any(s in r["符合訊號"] for s in ["三角", "箱型"]):
                fig.add_scatter(x=df_t.index[-len(x):], y=sh*x+ih, mode='lines', line=dict(color='red', dash='dash'), name='壓力線')
                fig.add_scatter(x=df_t.index[-len(x):], y=sl*x+il, mode='lines', line=dict(color='green', dash='dash'), name='支撐線')
            fig.update_layout(height=450, xaxis_rangeslider_visible=False, margin=dict(l=5, r=5, t=5, b=5))
            st.plotly_chart(fig, use_container_width=True)
else:
    if app_mode == "🔍 手動模式":
        st.warning("請在左側輸入代碼並點擊『🚀 開始搜尋』按鈕。")
