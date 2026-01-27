import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import os, json

# ==========================================
# 1. 系統環境與資料庫讀取
# ==========================================
st.set_page_config(page_title="台股形態雷達 Pro", layout="wide")

if 'favorites' not in st.session_state:
    st.session_state.favorites = {}

def get_favorites():
    return st.session_state.get('favorites', {})

@st.cache_data(ttl=3600)
def load_db():
    # 優先讀取全市場資料庫，若無則讀取電子股
    for f in ["taiwan_full_market.json", "taiwan_electronic_stocks.json"]:
        if os.path.exists(f):
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
            return {k.replace(".TW.TW", ".TW").strip(): v for k, v in data.items()}
    return {"2330.TW": "台積電"}

# ==========================================
# 2. 核心分析引擎 (篩選與標籤 100% 同步)
# ==========================================
def run_analysis(sid, name, df, config, force_show=False):
    if df is None or len(df) < 20: return None
    try:
        df = df.dropna()
        c, v_last = float(df["Close"].iloc[-1]), df["Volume"].iloc[-1]
        v_avg = df["Volume"].iloc[-21:-1].mean()
        
        # 只有在需要時才計算形態，節省 CPU
        active_hits = []
        sh, ih, sl, il, x = 0, 0, 0, 0, np.arange(15)
        
        # 形態計算
        h, l = df["High"].iloc[-15:].values, df["Low"].iloc[-15:].values
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        
        # 勾選連動邏輯：沒勾選就不會被放入 active_hits
        if config["f_tri"] and (sh < -0.001 and sl > 0.001): active_hits.append("📐三角收斂")
        if config["f_box"] and (abs(sh) < 0.02 and abs(sl) < 0.02): active_hits.append("📦箱型整理")
        if config["f_vol"] and (v_last > v_avg * 2): active_hits.append("🚀今日爆量")
        
        # 決定是否顯示：掃描模式下，必須符合「已勾選」的形態才搜出
        should_show = force_show or bool(active_hits)
        
        # MA20 強制過濾
        if config["f_ma20"] and c < df["Close"].rolling(20).mean().iloc[-1]: 
            should_show = False
            
        if should_show:
            return {
                "sid": sid, "name": name, "price": round(c, 2), "vol": int(v_last/1000), 
                "hits": active_hits if active_hits else ["🔍一般觀察"], 
                "df": df, "lines": (sh, ih, sl, il, x)
            }
    except: pass
    return None

# ==========================================
# 3. 左側完整控制介面 (Sidebar)
# ==========================================
full_db = load_db()
all_codes = list(full_db.keys())

with st.sidebar:
    st.subheader("🎯 交易控制台")
    app_mode = st.radio("模式選擇", ["⚡ 自動雷達", "🛠️ 手動工具"], label_visibility="collapsed")
    st.divider()
    
    # 搜尋框
    search_input = st.text_input("🔍 個股搜尋 (無視過濾)", placeholder="2330, 2454")
    
    st.caption("⚙️ 篩選與標籤連動 (勾選才顯示)")
    f_tri = st.checkbox("📐 三角收斂", True)
    f_box = st.checkbox("📦 箱型整理", True)
    f_vol = st.checkbox("🚀 今日爆量", False) # 預設不勾，符合你要求
    f_ma20 = st.checkbox("📈 股價 > MA20", False)
    config = {"f_tri": f_tri, "f_box": f_box, "f_vol": f_vol, "f_ma20": f_ma20}
    
    min_v = st.number_input("成交量門檻 (張)", value=500)
    scan_limit = st.slider("掃描上限", 50, 1000, 100)
    
    # 按鈕邏輯
    trigger_scan = True if app_mode == "⚡ 自動雷達" else st.button("🚀 開始掃描", type="primary", use_container_width=True)

    st.divider()
    st.subheader("❤️ 我的最愛")
    favs = get_favorites()
    for fid, fname in list(favs.items()):
        c1, c2 = st.columns([4, 1])
        c1.write(f"**{fid}** {fname}")
        if c2.button("🗑️", key=f"del_{fid}"):
            del st.session_state.favorites[fid]; st.rerun()

# ==========================================
# 4. 主畫面執行與極速抓取
# ==========================================
st.subheader(f"📈 形態監控 ({app_mode})") # 標題縮小

is_searching = bool(search_input)
active_codes = [c.strip()+".TW" if "." not in c else c.strip().upper() for c in search_input.split(",")] if is_searching else all_codes

results = []
if trigger_scan:
    # 搜尋中狀態顯示
    with st.status("📡 極速掃描中...", expanded=False) as status:
        try:
            # 提速關鍵：Bulk Download
            # 先抓 5 天數據判斷成交量門檻
            raw_data = yf.download(active_codes, period="5d", group_by='ticker', progress=False)
            
            # 過濾成交量，減少無效計算
            valid_targets = []
            for sid in active_codes:
                df = raw_data[sid] if len(active_codes) > 1 else raw_data
                if df.empty: continue
                v_now = df["Volume"].iloc[-1] / 1000
                if is_searching or v_now >= min_v:
                    valid_targets.append((sid, df))
            
            # 只取前 N 檔進行深度分析
            for sid, df in valid_targets[:scan_limit]:
                res = run_analysis(sid, full_db.get(sid, "未知"), df, config, force_show=is_searching)
                if res: results.append(res)
            
            status.update(label=f"✅ 完成 (找到 {len(results)} 檔)", state="complete")
        except Exception as e:
            status.update(label=f"❌ 錯誤: {e}", state="error")

# ==========================================
# 5. 結果顯示 (垂直換行標籤)
# ==========================================
if results:
    # 總覽表格
    summary_data = []
    for r in results:
        summary_data.append({
            "代碼": f"https://tw.stock.yahoo.com/quote/{r['sid']}",
            "名稱": r["name"],
            "現價": r["price"],
            "張數": r["vol"],
            "符合形態": "\n".join(r["hits"]) # 垂直換行標籤
        })
    
    st.dataframe(
        pd.DataFrame(summary_data),
        column_config={
            "代碼": st.column_config.LinkColumn("代碼", display_text=r"quote/(.*)$"),
            "符合形態": st.column_config.TextColumn("符合形態", width="medium")
        },
        hide_index=True, use_container_width=True
    )

    # 詳細 K 線圖與收藏按鈕
    for r in results:
        col_exp, col_fav = st.columns([5, 1])
        with col_exp:
            exp = st.expander(f"🔍 {r['sid']} {r['name']} | {' + '.join(r['hits'])}", expanded=is_searching)
        with col_fav:
            if st.button("❤️" if r['sid'] in get_favorites() else "🤍", key=f"b_{r['sid']}"):
                if r['sid'] in st.session_state.favorites: del st.session_state.favorites[r['sid']]
                else: st.session_state.favorites[r['sid']] = r['name']
                st.rerun()
        
        with exp:
            df_t, (sh, ih, sl, il, x) = r["df"].iloc[-15:], r["lines"]
            fig = go.Figure(data=[go.Candlestick(x=df_t.index, open=df_t['Open'], high=df_t['High'], low=df_t['Low'], close=df_t['Close'], name='K線')])
            # 只有勾選形態才畫支撐壓力線
            if config["f_tri"] or config["f_box"]:
                fig.add_scatter(x=df_t.index, y=sh*x+ih, mode='lines', line=dict(color='red', dash='dash'), name='壓力')
                fig.add_scatter(x=df_t.index, y=sl*x+il, mode='lines', line=dict(color='green', dash='dash'), name='支撐')
            fig.update_layout(height=400, xaxis_rangeslider_visible=False, margin=dict(l=5, r=5, t=5, b=5))
            st.plotly_chart(fig, use_container_width=True)
elif trigger_scan:
    st.info("💡 搜尋不到結果，請嘗試調低「張數門檻」或勾選更多形態。")
