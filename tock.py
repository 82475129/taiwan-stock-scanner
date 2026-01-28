# -*- coding: utf-8 -*-
"""
台股 Pro 旗艦戰情室 - 完整優化版
支援近 2000 檔股票掃描，產業分類（電子/傳產/食品），爆量前5天×1.5
預設掃描 200 檔，可手動拉到 2000
作者：基於使用者需求迭代優化
最後更新：2026
"""

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
from streamlit_autorefresh import st_autorefresh
import json
import os
import time
from datetime import datetime

# ================================
# 1. 頁面基本設定與 Session State 初始化
# ================================
st.set_page_config(
    page_title="台股 Pro 旗艦戰情室 v2.0",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Session State 管理
if 'favorites' not in st.session_state:
    st.session_state.favorites = set()

if 'results_data' not in st.session_state:
    st.session_state.results_data = []

if 'last_mode' not in st.session_state:
    st.session_state.last_mode = None

if 'full_db' not in st.session_state:
    st.session_state.full_db = None  # 延遲載入

# ================================
# 2. 載入完整台灣股票資料庫（上市 + 上櫃）
#    目標：接近 2000 檔，包含產業分類
# ================================
@st.cache_data(ttl=86400, show_spinner="正在從證交所載入最新股票清單...")
def load_full_market_db():
    """
    從台灣證交所 ISIN 頁面動態抓取上市 & 上櫃股票
    上市：strMode=2   上櫃：strMode=4
    回傳格式：{symbol: {"name": str, "category": str}}
    """
    db = {}
    fallback = {
        "2330.TW": {"name": "台積電", "category": "電子"},
        "2454.TW": {"name": "聯發科", "category": "電子"},
        "2317.TW": {"name": "鴻海", "category": "電子"},
        "2603.TW": {"name": "長榮", "category": "傳產"},
        "1216.TW": {"name": "統一", "category": "食品"}
    }

    def get_category(industry: str) -> str:
        industry = str(industry).strip()
        if not industry:
            return "其他"
        # 電子相關（最廣泛）
        if any(k in industry for k in [
            "半導體", "電腦", "光電", "通訊網路", "電子零組件",
            "其他電子", "電子通路", "資訊服務"
        ]):
            return "電子"
        # 食品
        elif "食品" in industry or "飲料" in industry:
            return "食品"
        # 其他歸傳產（水泥、塑膠、鋼鐵、紡織、汽車、造紙、橡膠等）
        else:
            return "傳產"

    for mode, suffix, market_name in [
        ("2", ".TW", "上市"),
        ("4", ".TWO", "上櫃")
    ]:
        url = f"https://isin.twse.com.tw/isin/C_public.jsp?strMode={mode}"
        try:
            dfs = pd.read_html(url, flavor='bs4')
            if not dfs:
                st.warning(f"{market_name} 表格載入失敗，使用 fallback")
                continue

            df = dfs[0]
            # 清理：跳過第一列標題、移除無效行
            df = df.iloc[1:].reset_index(drop=True)
            if len(df.columns) < 5:
                continue

            # 欄位名稱可能因網站變動而異，強制指定
            df.columns = ['有價證券代號及名稱', 'ISIN', '上市日', '市場別', '產業別', 'CFICode', '備註'][:len(df.columns)]

            # 只保留有代碼的股票行（過濾權證/ETF等）
            df = df[df['有價證券代號及名稱'].str.match(r'^\d{4,6}\s+.*')]

            # 分離代碼與名稱
            df[['code', 'name']] = df['有價證券代號及名稱'].str.split(n=1, expand=True)
            df['symbol'] = df['code'] + suffix
            df['category'] = df['產業別'].apply(get_category)

            # 加入 db
            for _, row in df.iterrows():
                if pd.notna(row['name']) and row['code'].isdigit():
                    db[row['symbol']] = {
                        "name": row['name'].strip(),
                        "category": row['category']
                    }

            st.info(f"{market_name} 載入成功：{len(df)} 檔")

        except Exception as e:
            st.warning(f"載入 {market_name} 資料失敗 ({e})，跳過...")

    if not db:
        st.error("無法從證交所載入任何資料，使用內建 fallback")
        db = fallback
    else:
        st.success(f"總股票資料庫載入完成：{len(db)} 檔（接近 2000 目標）")

    return db

# 載入 db（只執行一次）
if st.session_state.full_db is None:
    st.session_state.full_db = load_full_market_db()

full_db = st.session_state.full_db

# ================================
# 3. 資料抓取函式（yfinance）
# ================================
@st.cache_data(ttl=300, show_spinner=False)  # 5分鐘 cache，減少 API 呼叫
def fetch_price(symbol: str) -> pd.DataFrame:
    try:
        df = yf.download(
            symbol,
            period="1y",
            auto_adjust=True,
            progress=False,
            threads=False
        )
        if df.empty:
            return pd.DataFrame()
        # 處理 MultiIndex 欄位（偶發）
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df.dropna(how='all')
    except Exception:
        return pd.DataFrame()

# ================================
# 4. 核心技術分析引擎
# ================================
def run_analysis(
    sid: str,
    name: str,
    df: pd.DataFrame,
    cfg: dict,
    is_manual: bool = False
) -> dict | None:
    if df.empty or 'Close' not in df.columns or len(df) < 60:
        return None

    try:
        # 最新收盤價與均線
        c = float(df['Close'].iloc[-1])
        ma20 = df['Close'].rolling(window=20).mean().iloc[-1]
        ma60 = df['Close'].rolling(window=60).mean().iloc[-1]
        trend = '🔴 多頭排列' if ma20 > ma60 else '🟢 空頭排列'

        # 壓力/支撐線（最近 lb 天）
        lb = cfg.get("p_lookback", 15)
        if len(df) < lb:
            return None
        x = np.arange(lb)
        h = df["High"].iloc[-lb:].values
        l = df["Low"].iloc[-lb:].values
        sh, ih, _, _, _ = linregress(x, h)   # 壓力線斜率 & 截距
        sl, il, _, _, _ = linregress(x, l)   # 支撐線

        # 訊號偵測
        active_hits = []

        # 三角收斂：壓力下降 + 支撐上升
        if sh < -0.001 and sl > 0.001:
            active_hits.append("📐三角收斂")

        # 箱型整理：斜率接近 0
        if abs(sh) < 0.03 and abs(sl) < 0.03:
            active_hits.append("📦箱型整理")

        # 爆量：前 5 天平均 × 1.5 倍（使用者指定）
        if len(df) >= 6 and cfg.get("check_vol", True):
            v_prev5 = df["Volume"].iloc[-6:-1].mean()  # -6 ~ -2
            today_vol = df["Volume"].iloc[-1]
            if today_vol > v_prev5 * 1.5:
                active_hits.append("🚀今日爆量")

        # 篩選邏輯
        should_show = False
        if is_manual:
            should_show = True
        else:
            # 至少符合一個勾選訊號
            hit_match = any([
                cfg.get("check_tri", False) and "📐" in "".join(active_hits),
                cfg.get("check_box", False) and "📦" in "".join(active_hits),
                cfg.get("check_vol", False) and "🚀" in "".join(active_hits)
            ])
            should_show = hit_match

            # 額外過濾
            if cfg.get("f_ma_filter", False) and c < ma20:
                should_show = False
            if c < cfg.get("min_price", 0):
                should_show = False

        if should_show:
            return {
                "收藏": sid in st.session_state.favorites,
                "sid": sid,
                "名稱": name,
                "現價": round(c, 2),
                "趨勢": trend,
                "MA20": round(ma20, 2),
                "MA60": round(ma60, 2),
                "符合訊號": ", ".join(active_hits) if active_hits else "🔍 觀察中",
                "Yahoo": f"https://tw.stock.yahoo.com/quote/{sid.split('.')[0]}",
                "df": df.copy(),
                "lines": (sh, ih, sl, il, x)
            }
    except Exception as e:
        st.warning(f"分析 {sid} 失敗：{e}")
    return None

# ================================
# 5. 側邊欄控制台
# ================================
st.sidebar.title("🛡️ 台股戰術控制台")
st.sidebar.markdown("**Pro 版 v2.0** | 近2000檔掃描引擎")

mode = st.sidebar.radio(
    "分析模式",
    ["🔍 手動查詢", "⚖️ 條件篩選", "⚡ 自動掃描", "❤️ 收藏追蹤"],
    index=0
)

# 模式切換時清除舊結果
if st.session_state.last_mode != mode:
    st.session_state.results_data = []
    st.session_state.last_mode = mode

# 共通參數
cfg = {
    "p_lookback": 15,
    "min_price": 0.0,
    "check_tri": True,
    "check_box": True,
    "check_vol": True,
    "f_ma_filter": False,
    "scan_limit": 200  # 預設 200
}

# 產業過濾（預設電子）
category_options = ["全部", "電子", "傳產", "食品"]
category_filter = st.sidebar.selectbox(
    "主要產業類別（預設電子）",
    category_options,
    index=1
)

if mode in ["⚖️ 條件篩選", "⚡ 自動掃描"]:
    st.sidebar.divider()
    st.sidebar.subheader("🎯 篩選條件")

    col1, col2 = st.sidebar.columns(2)
    with col1:
        cfg["check_tri"] = st.checkbox("📐 三角收斂", value=True)
        cfg["check_box"] = st.checkbox("📦 箱型整理", value=True)
    with col2:
        cfg["check_vol"] = st.checkbox("🚀 今日爆量 (前5天×1.5)", value=True)
        cfg["f_ma_filter"] = st.checkbox("限 MA20 之上", value=False)

    cfg["min_price"] = st.sidebar.slider(
        "最低股價門檻 (元)",
        0.0, 1000.0, 0.0, step=1.0
    )

    cfg["scan_limit"] = st.sidebar.slider(
        "掃描上限（總庫約1800-1900檔，預設200）",
        min_value=50,
        max_value=2000,
        value=200,
        step=50
    )

    st.sidebar.caption("⚠️ 掃描 500+ 檔可能需 3–10 分鐘，yfinance 有速率限制")

# ================================
# 6. 主畫面標題與各模式邏輯
# ================================
st.title(f"📈 {mode} - 台股 Pro 戰情室")
st.caption(f"今日：{datetime.now().strftime('%Y-%m-%d %H:%M')} | 資料來源：yfinance + 證交所")

# 過濾符合產業的 symbol 清單
all_symbols = list(full_db.keys())
if category_filter != "全部":
    filtered_symbols = [
        s for s in all_symbols
        if full_db.get(s, {}).get("category") == category_filter
    ]
else:
    filtered_symbols = all_symbols

st.sidebar.markdown(f"**可用標的數**：{len(filtered_symbols)} 檔（{category_filter}）")

# --------------------
# 模式：手動查詢
# --------------------
if mode == "🔍 手動查詢":
    st.info("輸入股票代碼（可多筆，用逗號或空格分隔）")
    code_input = st.text_input(
        "股票代碼",
        placeholder="例：2330, 2454, 2603, 1216",
        key="manual_input"
    )

    if code_input:
        raw_codes = [c.strip().upper() for c in code_input.replace("，", ",").split(",") if c.strip()]
        temp_res = []

        with st.status("正在分析手動輸入標的...", expanded=True) as status:
            progress = st.progress(0)
            for i, c in enumerate(raw_codes):
                sym = c if '.' in c else f"{c}.TW"
                df = fetch_price(sym)
                name = full_db.get(sym, {}).get("name", c)
                res = run_analysis(sym, name, df, cfg, is_manual=True)
                if res:
                    temp_res.append(res)
                progress.progress((i + 1) / len(raw_codes))
            status.update(label=f"完成！找到 {len(temp_res)} 檔有效資料", state="complete")

        st.session_state.results_data = temp_res

# --------------------
# 模式：條件篩選
# --------------------
elif mode == "⚖️ 條件篩選":
    st.info("設定左側條件後，點擊下方按鈕開始全市場掃描")
    
    if st.button("🚀 開始條件篩選", type="primary", use_container_width=True):
        max_scan = cfg.get("scan_limit", 200)
        codes = filtered_symbols[:max_scan]

        temp_res = []
        with st.status(f"掃描中...（{len(codes)} 檔，{category_filter}類）", expanded=True) as status:
            progress_bar = st.progress(0)
            for i, s in enumerate(codes):
                df = fetch_price(s)
                name = full_db.get(s, {}).get("name", "未知")
                res = run_analysis(s, name, df, cfg, is_manual=False)
                if res:
                    temp_res.append(res)
                progress_bar.progress((i + 1) / len(codes))
                time.sleep(0.05)  # 避免過快被 yfinance 限速
            st.session_state.results_data = temp_res
            status.update(
                label=f"✅ 篩選完成！共 {len(temp_res)} 檔符合條件",
                state="complete"
            )

# --------------------
# 模式：自動掃描
# --------------------
elif mode == "⚡ 自動掃描":
    st_autorefresh(interval=60000, key="auto_scan_refresh")  # 每 60 秒
    st.warning("⚡ 自動掃描模式啟動，每 60 秒更新一次（限前 150 檔避免過載）")

    max_auto = min(len(filtered_symbols), 150)
    codes = filtered_symbols[:max_auto]

    temp_res = []
    with st.spinner(f"自動掃描 {len(codes)} 檔中..."):
        for s in codes:
            df = fetch_price(s)
            name = full_db.get(s, {}).get("name", "未知")
            res = run_analysis(s, name, df, cfg, is_manual=False)
            if res:
                temp_res.append(res)
    st.session_state.results_data = temp_res

    st.success(f"自動更新完成！找到 {len(temp_res)} 檔符合訊號")

# --------------------
# 模式：收藏追蹤
# --------------------
elif mode == "❤️ 收藏追蹤":
    if not st.session_state.favorites:
        st.info("目前沒有收藏股票。從其他模式點擊 ❤️ 加入收藏吧！")
    else:
        st.subheader(f"收藏清單（{len(st.session_state.favorites)} 檔）")
        if st.button("🔄 立即更新收藏報價", type="primary"):
            temp_res = []
            with st.status("更新收藏股中..."):
                for s in st.session_state.favorites:
                    df = fetch_price(s)
                    name = full_db.get(s, {}).get("name", s)
                    res = run_analysis(s, name, df, cfg, is_manual=True)
                    if res:
                        temp_res.append(res)
            st.session_state.results_data = temp_res
            st.success("收藏更新完成！")

# ================================
# 7. 結果呈現 - 表格 + K線圖
# ================================
display_data = st.session_state.results_data

# 收藏模式額外過濾（防意外）
if mode == "❤️ 收藏追蹤":
    display_data = [r for r in display_data if r["sid"] in st.session_state.favorites]

if display_data:
    # 表格呈現
    table_data = [{
        "收藏": r["收藏"],
        "代碼": r["sid"],
        "名稱": r["名稱"],
        "現價": r["現價"],
        "趨勢": r["趨勢"],
        "MA20": r["MA20"],
        "MA60": r["MA60"],
        "訊號": r["符合訊號"],
        "Yahoo": r["Yahoo"]
    } for r in display_data]

    df_display = pd.DataFrame(table_data)

    edited_df = st.data_editor(
        df_display,
        column_config={
            "收藏": st.column_config.CheckboxColumn("❤️ 收藏", width="small"),
            "Yahoo": st.column_config.LinkColumn("Yahoo", display_text="🔍 看Yahoo", width="medium"),
            "現價": st.column_config.NumberColumn("現價", format="%.2f"),
            "MA20": st.column_config.NumberColumn("MA20", format="%.2f"),
            "MA60": st.column_config.NumberColumn("MA60", format="%.2f"),
        },
        hide_index=True,
        use_container_width=True,
        key=f"editor_{mode}_{category_filter}"
    )

    # 處理收藏變更
    new_favs = set(edited_df[edited_df["收藏"] == True]["代碼"].tolist())
    if new_favs != st.session_state.favorites:
        st.session_state.favorites = new_favs
        st.rerun()

    st.divider()

    # K線圖區（展開式卡片）
    st.subheader("個股 K 線與趨勢線")
    for r in display_data:
        with st.expander(
            f"{r['sid']} {r['名稱']}  |  {r['符合訊號']}  |  {r['趨勢']}",
            expanded=False
        ):
            cols = st.columns([1, 1, 1, 2])
            with cols[0]:
                st.metric("現價", f"{r['現價']:.2f} 元")
            with cols[1]:
                st.metric("MA20", f"{r['MA20']:.2f}")
            with cols[2]:
                st.metric("MA60", f"{r['MA60']:.2f}")
            with cols[3]:
                st.metric("趨勢", r["趨勢"])

            # 繪製 K 線（最近 60 天）
            df_plot = r["df"].iloc[-60:].copy()
            fig = go.Figure()

            fig.add_trace(go.Candlestick(
                x=df_plot.index,
                open=df_plot['Open'],
                high=df_plot['High'],
                low=df_plot['Low'],
                close=df_plot['Close'],
                name='K線',
                increasing_line_color='red',
                decreasing_line_color='green'
            ))

            # 壓力 / 支撐線
            sh, ih, sl, il, x_vals = r["lines"]
            x_dates = df_plot.index[-len(x_vals):]

            fig.add_trace(go.Scatter(
                x=x_dates, y=sh * x_vals + ih,
                mode='lines', line=dict(color='red', dash='dash', width=2),
                name='壓力線'
            ))
            fig.add_trace(go.Scatter(
                x=x_dates, y=sl * x_vals + il,
                mode='lines', line=dict(color='green', dash='dash', width=2),
                name='支撐線'
            ))

            fig.update_layout(
                height=450,
                margin=dict(l=10, r=10, t=30, b=10),
                xaxis_rangeslider_visible=False,
                template="plotly_dark" if st.get_option("theme.base") == "dark" else "plotly_white"
            )

            st.plotly_chart(fig, use_container_width=True, key=f"chart_{r['sid']}_{mode}")

else:
    # 無結果提示
    if mode == "⚖️ 條件篩選":
        st.info("尚未執行篩選，請設定條件後按「開始篩選標的」")
    elif mode == "❤️ 收藏追蹤":
        st.info("收藏清單為空，快去其他模式加入喜歡的股票吧！")
    else:
        st.caption("目前無符合條件標的，或尚未執行分析")

# 頁腳
st.markdown("---")
st.caption("Powered by Streamlit + yfinance + 證交所資料 | 僅供參考，非投資建議")
