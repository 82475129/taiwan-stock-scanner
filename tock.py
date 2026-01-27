import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import sys, json, os

# ==========================================
# 1. 系統初始化與安全設定 (防止 Session 報錯)
# ==========================================
# 確保在 Streamlit 環境下正確執行
IS_STREAMLIT = hasattr(st, "runtime") and st.runtime.exists()

if IS_STREAMLIT:
    st.set_page_config(page_title="台股形態雷達 Pro", layout="wide")
    # 初始化最愛清單，解決你截圖中的 AttributeError
    if 'favorites' not in st.session_state:
        st.session_state.favorites = {}

def get_favorites():
    return st.session_state.get('favorites', {}) if IS_STREAMLIT else {}

@st.cache_data(ttl=3600)
def load_and_fix_db():
    # 自動偵測資料庫檔案
    DB_FILES = ["taiwan_electronic_stocks.json", "taiwan_full_market.json"]
    target_file = next((f for f in DB_FILES if os.path.exists(f)), None)
    if not target_file: return {"2330.TW": "台積電"}
    try:
        with open(target_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        return {k.replace(".TW.TW", ".TW").strip(): v for k, v in raw_data.items()}
    except: return {"2330.TW": "台積電"}

# ==========================================
# 2. 核心分析引擎 (靈活標籤顯示邏輯)
# ==========================================
def run_analysis(df, sid, name, config, force_show=False):
    if df is None or len(df) < 30: return None
    try:
        df = df.dropna()
        c = float(df["Close"].iloc[-1])
        m20 = df["Close"].rolling(20).mean().iloc[-1]
        v_last = df["Volume"].iloc[-1]
        v_avg = df["Volume"].iloc[-21:-1].mean()
        
        # 形態計算 (壓力與支撐線)
        d_len = 15
        x = np.arange(d_len)
        h, l = df["High"].iloc[-d_len:].values, df["Low"].iloc[-d_len:].values
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        
        # 符合性判定
        is_tri = sh < -0.001 and sl > 0.001
        is_box = abs(sh) < 0.02 and abs(sl) < 0.02
        is_vol = v_last > v_avg * 2
        
        # --- 靈活標籤邏輯：只有勾選且符合才顯示 ---
        active_hits = []
        if config["f_tri"] and is_tri: active_hits.append("📐三角收斂")
        if config["f_box"] and is_box: active_hits.append("📦箱型整理")
        if config["f_vol"] and is_vol: active_hits.append("🚀今日爆量")
        
        # 決定是否輸出結果
        should_output = False
        if force_show: 
            should_output = True # 手動搜尋永遠顯示
        elif active_hits: 
            should_output = True # 掃描模式：有勾選且符合才顯示
            
        # MA20 過濾
        if config.get("f_ma20") and c < m20: should_output = False
        
        if should_output:
            final_tags = active_hits if active_hits else ["🔍一般觀察"]
            return {
                "sid": sid, "name": name, "price": round(c, 2), 
                "vol": int(v_last/1000), "hits": final_tags, 
                "df": df, "lines": (sh, ih, sl, il, x)
            }
        return None
    except: return None

# ==========================================
# 3. 左側介面 (Sidebar) - 功能都在這
# ==========================================
full_db = load_and_fix_db()
all_codes = list(full_db.keys())

with st.sidebar:
    st.subheader("🎯 交易控制台")
    app_mode = st.radio("模式選擇", ["⚡ 自動雷達", "🛠️ 手動工具"], label_visibility="collapsed")
    st.divider()
    
    # 手動搜尋框 (左側)
    search_input = st.text_input("🔍 個股搜尋 (無視過濾)", placeholder="例如: 2330, 2002")
    
    st.caption("⚙️ 篩選與顯示連動設定")
    f_tri = st.checkbox("📐 三角收斂", True)
    f_box = st.checkbox("📦 箱型整理", True)
    f_vol = st.checkbox("🚀 今日爆量", False) # 預設不勾，符合你「不勾就不顯」的要求
    f_ma20 = st.checkbox("📈 股價 > MA20", False)
    config = {"f_tri": f_tri, "f_box": f_box, "f_vol": f_vol, "f_ma20": f_ma20}
    
    min_v = st.number_input("張數門檻 (張)", value=500)
    scan_limit = st.slider("掃描上限 (筆)", 50, 1000, 100)
    
    # 掃描觸發器
    trigger_scan = True if app_mode == "⚡ 自動雷達" else st.button("🚀 開始手動掃描", type="primary", use_container_width=True)

    st.divider()
    st.subheader("❤️ 我的最愛")
    fav_list = get_favorites()
    if not fav_list:
        st.caption("尚未收藏任何個股")
    else:
        for fid, fname in list(fav_list.items()):
            c_a, c_b = st.columns([4, 1])
            c_a.markdown(f"**{fid}** {fname}")
            if c_b.button("🗑️", key=f"del_side_{fid}"):
                del st.session_state.favorites[fid]; st.rerun()

# ==========================================
# 4. 主畫面執行與顯示
# ==========================================
if IS_STREAMLIT:
    # 標題縮小
    st.subheader(f"📈 形態監控中心 ({app_mode})")
    
    is_searching = bool(search_input)
    # 處理多代碼搜尋
    active_codes = [c.strip() + ".TW" if "." not in c else c.strip().upper() for c in search_input.split(",")] if is_searching else all_codes

    results = []
    if trigger_scan:
        # 搜尋中狀態顯示
        with st.status("📡 正在掃描台股數據...", expanded=False) as status:
            try:
                # 下載最新成交量排序
                v_all = yf.download(active_codes, period="5d", progress=False)["Volume"]
                v_latest = v_all.iloc[-1] if not v_all.iloc[-1].isna().all() else v_all.iloc[-2]
                v_sorted = (v_latest / 1000).dropna()
                
                # 篩選張數門檻
                targets = v_sorted.index.tolist() if is_searching else v_sorted[v_sorted >= min_v].sort_values(ascending=False).head(scan_limit).index.tolist()
                
                if targets:
                    # 分批下載防止報錯
                    batch_size = 40
                    for i in range(0, len(targets), batch_size):
                        batch = targets[i:i+batch_size]
                        h_data = yf.download(batch, period="3mo", group_by="ticker", progress=False)
                        for sid in batch:
                            df_sid = h_data[sid] if len(batch) > 1 else h_data
                            res = run_analysis(df_sid, sid, full_db.get(sid, "未知"), config, force_show=is_searching)
                            if res: results.append(res)
                
                status.update(label=f"✅ 掃描完成 (找到 {len(results)} 檔)", state="complete")
            except Exception as e:
                status.update(label=f"❌ 錯誤: {e}", state="error")

    # 結果表格顯示 (狀態垂直換行)
    if results:
        summary_df = pd.DataFrame([{
            "代碼": f"https://tw.stock.yahoo.com/quote/{r['sid']}",
            "名稱": r["name"], "現價": r["price"], "張數": r["vol"],
            "符合形態": "\n".join(r["hits"]) # 垂直換行
        } for r in results])

        st.dataframe(
            summary_df, 
            column_config={
                "代碼": st.column_config.LinkColumn("代碼", display_text=r"quote/(.*)$"),
                "符合形態": st.column_config.TextColumn("符合形態", width="medium")
            }, 
            hide_index=True, use_container_width=True
        )

        # 個股細節與 K 線圖
        for item in results:
            col_exp, col_fav = st.columns([5, 1])
            with col_exp:
                exp = st.expander(f"🔍 {item['sid']} {item['name']} | {' + '.join(item['hits'])}", expanded=is_searching)
            with col_fav:
                # 收藏按鈕
                is_fav = item['sid'] in get_favorites()
                if st.button("❤️" if is_fav else "🤍", key=f"fav_btn_{item['sid']}"):
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
        st.info("💡 目前沒有符合條件的股票，請調整左側過濾條件。")
