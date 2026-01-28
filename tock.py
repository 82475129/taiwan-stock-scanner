# -*- coding: utf-8 -*-
"""
台股 Pro 旗艦戰情室 - v4.0 本地快取完整版
功能：
- 近 2000 檔股票資料庫（上市 + 上櫃）
- 產業分類篩選（預設電子）
- 技術形態偵測：三角收斂、箱型整理、今日爆量（前5天×1.5）
- 全市場價格資料本地 pickle 快取（避免 yfinance rate limit）
- 掃描上限預設 200，可手動調整至 2000
- 收藏功能、K 線圖、壓力/支撐趨勢線
- 進度條、錯誤處理、每日更新提醒

使用方式：
1. 第一次執行 → 點側邊欄「更新全市場價格資料庫」（需 10–30 分鐘）
2. 之後掃描全部從本地讀取，極速
3. 資料僅供參考，非投資建議

作者：基於使用者需求迭代
更新日期：2026 年
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
import pickle
from pathlib import Path
import warnings
import traceback

# 忽略常見警告
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=pd.errors.SettingWithCopyWarning)

# ================================
# 1. 頁面配置與 Session State 初始化
# ================================
st.set_page_config(
    page_title="台股 Pro 旗艦戰情室 v4.0",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://github.com/streamlit/streamlit',
        'Report a bug': "https://github.com/streamlit/streamlit/issues",
        'About': "台股 Pro 旗艦戰情室 - 個人學習專案，非商業用途"
    }
)

# Session State 變數初始化
default_states = {
    'favorites': set(),
    'results_data': [],
    'last_mode': None,
    'full_db': None,
    'price_data_cache': None,
    'last_cache_update': None
}

for key, value in default_states.items():
    if key not in st.session_state:
        st.session_state[key] = value

# 檔案路徑
DB_JSON_PATH = Path("taiwan_full_market.json")
CACHE_PKL_PATH = Path("taiwan_stock_prices_cache.pkl")

# ================================
# 2. 載入股票基本資料庫（代碼 + 名稱 + 產業分類）
# ================================
@st.cache_data(ttl=86400 * 3, show_spinner="正在載入證交所股票清單...")
def load_stock_database():
    """
    從證交所 ISIN 頁面抓取上市與上櫃股票清單
    包含：symbol, name, category
    """
    db = {}
    fallback_db = {
        "2330.TW": {"name": "台積電", "category": "電子"},
        "2454.TW": {"name": "聯發科", "category": "電子"},
        "2317.TW": {"name": "鴻海", "category": "電子"},
        "2603.TW": {"name": "長榮", "category": "傳產"},
        "1216.TW": {"name": "統一", "category": "食品"},
        "1101.TW": {"name": "台泥", "category": "傳產"},
        "2303.TW": {"name": "聯電", "category": "電子"}
    }

    def classify_industry(industry_str: str) -> str:
        text = str(industry_str).strip().lower()
        if any(word in text for word in [
            "半導體", "電腦週邊", "光電", "通信網路", "電子零組件",
            "其他電子", "電子通路", "資訊服務業"
        ]):
            return "電子"
        if "食品" in text or "飲料" in text:
            return "食品"
        return "傳產"  # 其他預設為傳產

    modes = [
        ("2", ".TW", "上市"),
        ("4", ".TWO", "上櫃")
    ]

    loaded_count = 0

    for mode, suffix, market in modes:
        url = f"https://isin.twse.com.tw/isin/C_public.jsp?strMode={mode}"
        try:
            tables = pd.read_html(url)
            if not tables:
                continue
            df = tables[0]
            df = df.iloc[1:].reset_index(drop=True)
            if len(df.columns) < 5:
                continue

            # 強制欄位名稱
            possible_cols = ['有價證券代號及名稱', 'ISIN', '上市日', '市場別', '產業別']
            df.columns = possible_cols[:len(df.columns)]

            # 過濾有效股票行
            df = df[df['有價證券代號及名稱'].str.contains(r'^\d{4,6}\s', na=False, regex=True)]

            df[['code', 'name']] = df['有價證券代號及名稱'].str.split(n=1, expand=True)
            df['symbol'] = df['code'].astype(str) + suffix
            df['category'] = df['產業別'].apply(classify_industry)

            for _, row in df.iterrows():
                sym = row['symbol']
                if pd.notna(row['name']) and row['code'].isdigit():
                    db[sym] = {
                        "name": row['name'].strip(),
                        "category": row['category']
                    }
                    loaded_count += 1

        except Exception as e:
            st.warning(f"載入 {market} 資料失敗：{str(e)}")

    if loaded_count == 0:
        st.error("無法從證交所載入任何股票，使用 fallback 資料")
        db = fallback_db
    else:
        st.info(f"股票清單載入完成：{loaded_count} 檔")

    return db

# 載入資料庫
if st.session_state.full_db is None:
    st.session_state.full_db = load_stock_database()

full_db = st.session_state.full_db

# ================================
# 3. 價格資料快取管理
# ================================
def load_price_cache():
    if CACHE_PKL_PATH.exists():
        try:
            with open(CACHE_PKL_PATH, "rb") as f:
                data = pickle.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            st.error(f"讀取價格快取失敗：{e}")
    return {}

def save_price_cache(cache_dict):
    try:
        with open(CACHE_PKL_PATH, "wb") as f:
            pickle.dump(cache_dict, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as e:
        st.error(f"儲存價格快取失敗：{e}")

# 初始化快取
if st.session_state.price_data_cache is None:
    st.session_state.price_data_cache = load_price_cache()

price_cache = st.session_state.price_data_cache

# ================================
# 4. 價格資料獲取（優先本地快取）
# ================================
def fetch_price(symbol: str) -> pd.DataFrame:
    if symbol in price_cache:
        df = price_cache[symbol]
        if not df.empty and 'Close' in df.columns:
            return df.copy()

    # 即時下載並存入快取
    try:
        df = yf.download(
            symbol,
            period="1y",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=False
        )
        if not df.empty:
            price_cache[symbol] = df.copy()
            save_price_cache(price_cache)
            st.session_state.last_cache_update = datetime.now()
        return df
    except Exception as e:
        st.warning(f"即時下載 {symbol} 失敗：{e}")
        return pd.DataFrame()

# ================================
# 5. 技術分析核心函式
# ================================
def run_analysis(sid: str, name: str, df: pd.DataFrame, cfg: dict, is_manual: bool = False) -> dict | None:
    if df.empty or 'Close' not in df.columns or len(df) < 60:
        return None

    try:
        # 最新價格與均線
        close_price = float(df['Close'].iloc[-1])
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        ma60 = df['Close'].rolling(60).mean().iloc[-1]

        trend_label = '🔴 多頭排列' if ma20 > ma60 else '🟢 空頭排列'

        # 最近 lb 天的壓力/支撐線
        lb = cfg.get("p_lookback", 15)
        if len(df) < lb:
            return None

        x = np.arange(lb)
        highs = df["High"].iloc[-lb:].values
        lows = df["Low"].iloc[-lb:].values

        slope_high, intercept_high, _, _, _ = linregress(x, highs)
        slope_low, intercept_low, _, _, _ = linregress(x, lows)

        signals = []

        # 三角收斂
        if slope_high < -0.001 and slope_low > 0.001:
            signals.append("📐三角收斂")

        # 箱型整理
        if abs(slope_high) < 0.03 and abs(slope_low) < 0.03:
            signals.append("📦箱型整理")

        # 今日爆量（前5天平均 × 1.5）
        if len(df) >= 6 and cfg.get("check_vol", True):
            vol_prev5 = df["Volume"].iloc[-6:-1].mean()
            vol_today = df["Volume"].iloc[-1]
            if vol_today > vol_prev5 * 1.5:
                signals.append("🚀今日爆量")

        # 決定是否顯示
        show_item = is_manual

        if not is_manual:
            has_checked_signal = any([
                cfg.get("check_tri", False) and "📐" in "".join(signals),
                cfg.get("check_box", False) and "📦" in "".join(signals),
                cfg.get("check_vol", False) and "🚀" in "".join(signals)
            ])
            show_item = has_checked_signal

            # 額外過濾條件
            if cfg.get("f_ma_filter", False) and close_price < ma20:
                show_item = False
            if close_price < cfg.get("min_price", 0):
                show_item = False

        if show_item:
            return {
                "收藏": sid in st.session_state.favorites,
                "sid": sid,
                "名稱": name,
                "現價": round(close_price, 2),
                "趨勢": trend_label,
                "MA20": round(ma20, 2),
                "MA60": round(ma60, 2),
                "符合訊號": ", ".join(signals) if signals else "🔍 觀察中",
                "Yahoo": f"https://tw.stock.yahoo.com/quote/{sid.split('.')[0]}",
                "df": df.copy(),
                "lines": (slope_high, intercept_high, slope_low, intercept_low, x)
            }
    except Exception as e:
        st.warning(f"分析 {sid} 時發生錯誤：{str(e)}")
    return None

# ================================
# 6. 側邊欄控制面板
# ================================
st.sidebar.title("🛡️ 台股 Pro 戰術控制台")
st.sidebar.markdown(f"**版本**：v4.0 本地快取 | **總標的**：{len(full_db)} 檔")

mode = st.sidebar.radio(
    label="分析模式",
    options=["🔍 手動查詢", "⚖️ 條件篩選", "⚡ 自動掃描", "❤️ 收藏追蹤"],
    index=0,
    key="mode_selector"
)

# 模式切換時清空舊結果
if st.session_state.last_mode != mode:
    st.session_state.results_data = []
    st.session_state.last_mode = mode

# 共通設定
cfg = {
    "p_lookback": 15,
    "min_price": 0.0,
    "check_tri": True,
    "check_box": True,
    "check_vol": True,
    "f_ma_filter": False,
    "scan_limit": 200
}

# 產業選擇
category_filter = st.sidebar.selectbox(
    "主要產業",
    options=["全部", "電子", "傳產", "食品"],
    index=1,
    key="category_select"
)

if mode in ["⚖️ 條件篩選", "⚡ 自動掃描"]:
    st.sidebar.divider()
    st.sidebar.subheader("篩選條件設定")

    col_a, col_b = st.sidebar.columns(2)
    with col_a:
        cfg["check_tri"] = st.checkbox("📐 三角收斂", value=True)
        cfg["check_box"] = st.checkbox("📦 箱型整理", value=True)
    with col_b:
        cfg["check_vol"] = st.checkbox("🚀 今日爆量 (前5天×1.5)", value=True)
        cfg["f_ma_filter"] = st.checkbox("限 MA20 之上", value=False)

    cfg["min_price"] = st.sidebar.slider(
        "最低股價門檻 (元)",
        min_value=0.0,
        max_value=1000.0,
        value=0.0,
        step=1.0
    )

    cfg["scan_limit"] = st.sidebar.slider(
        "本次掃描上限 (檔)",
        min_value=50,
        max_value=2000,
        value=200,
        step=50,
        help="建議 200–500 檔，避免記憶體過載"
    )

# 資料庫更新區塊
st.sidebar.divider()
st.sidebar.subheader("資料庫管理")

update_button = st.sidebar.button(
    "🔄 更新全市場價格資料庫",
    type="primary",
    help="建議每天執行一次，更新後掃描速度極快（本地讀取）"
)

if update_button:
    with st.status("正在更新全市場價格資料（約 1800 檔）...", expanded=True) as status:
        codes = list(full_db.keys())
        progress_bar = st.progress(0)
        batch_size = 80  # 較保守的 batch，避免被 Yahoo 限速
        updated_count = 0

        for i in range(0, len(codes), batch_size):
            batch_symbols = codes[i:i + batch_size]
            try:
                multi_df = yf.download(
                    batch_symbols,
                    period="1y",
                    group_by="ticker",
                    threads=True,
                    auto_adjust=True
                )
                for sym in batch_symbols:
                    if sym in multi_df.columns.levels[0]:
                        price_cache[sym] = multi_df[sym].copy()
                        updated_count += 1
            except Exception as ex:
                st.warning(f"Batch {i//batch_size + 1} 下載失敗：{ex}")

            progress_bar.progress(min((i + batch_size) / len(codes), 1.0))
            time.sleep(1.5)  # 避免過快請求

        save_price_cache(price_cache)
        st.session_state.last_cache_update = datetime.now()
        status.update(
            label=f"更新完成！新增/更新 {updated_count} 檔資料",
            state="complete"
        )

if st.session_state.last_cache_update:
    st.sidebar.caption(f"最後更新：{st.session_state.last_cache_update.strftime('%Y-%m-%d %H:%M')}")

# ================================
# 7. 主畫面內容
# ================================
st.title(f"📈 {mode}")
st.caption(f"目前模式：{mode} | 產業篩選：{category_filter} | 總可用標的：{len(full_db)} 檔")

# 過濾符合產業的代碼
all_symbols_list = list(full_db.keys())
if category_filter == "全部":
    filtered_list = all_symbols_list
else:
    filtered_list = [
        s for s in all_symbols_list
        if full_db.get(s, {}).get("category") == category_filter
    ]

# 各模式邏輯
if mode == "🔍 手動查詢":
    input_codes = st.text_input(
        "請輸入股票代碼（多檔用逗號分隔）",
        placeholder="例：2330, 2454, 2603, 1216",
        key="manual_codes"
    )

    if input_codes:
        raw_list = [c.strip().upper() for c in input_codes.replace("，", ",").split(",") if c.strip()]
        temp_results = []

        with st.spinner("分析手動輸入標的中..."):
            for code in raw_list:
                sym = code if ".TW" in code or ".TWO" in code else f"{code}.TW"
                df = fetch_price(sym)
                name = full_db.get(sym, {}).get("name", code)
                result = run_analysis(sym, name, df, cfg, is_manual=True)
                if result:
                    temp_results.append(result)

        st.session_state.results_data = temp_results

elif mode == "⚖️ 條件篩選":
    st.info("設定左側條件後，按下方按鈕開始掃描")

    if st.button("🚀 開始條件篩選", type="primary", use_container_width=True):
        scan_codes = filtered_list[:cfg["scan_limit"]]
        temp_results = []

        with st.status(f"正在掃描 {len(scan_codes)} 檔 {category_filter} 類股票...", expanded=True) as status:
            progress = st.progress(0)
            for idx, sym in enumerate(scan_codes):
                df = fetch_price(sym)
                name = full_db.get(sym, {}).get("name", "未知")
                result = run_analysis(sym, name, df, cfg, is_manual=False)
                if result:
                    temp_results.append(result)
                progress.progress((idx + 1) / len(scan_codes))
                if (idx + 1) % 50 == 0:
                    time.sleep(0.1)  # 輕微延遲，避免 CPU 過載

            st.session_state.results_data = temp_results
            status.update(
                label=f"掃描完成！找到 {len(temp_results)} 檔符合條件",
                state="complete"
            )

elif mode == "⚡ 自動掃描":
    st_autorefresh(interval=60000, key="auto_refresh_key")
    st.warning("自動掃描模式：每 60 秒更新一次（限前 150 檔）")

    auto_codes = filtered_list[:150]
    temp_results = []

    with st.spinner(f"自動掃描 {len(auto_codes)} 檔中..."):
        for sym in auto_codes:
            df = fetch_price(sym)
            name = full_db.get(sym, {}).get("name", "未知")
            result = run_analysis(sym, name, df, cfg, is_manual=False)
            if result:
                temp_results.append(result)

    st.session_state.results_data = temp_results

elif mode == "❤️ 收藏追蹤":
    if not st.session_state.favorites:
        st.info("目前收藏清單為空，請從其他模式加入股票")
    else:
        if st.button("🔄 立即更新收藏報價"):
            temp_results = []
            with st.status("更新收藏股票中..."):
                for sym in list(st.session_state.favorites):
                    df = fetch_price(sym)
                    name = full_db.get(sym, {}).get("name", sym)
                    result = run_analysis(sym, name, df, cfg, is_manual=True)
                    if result:
                        temp_results.append(result)
            st.session_state.results_data = temp_results
            st.success(f"更新完成，共 {len(temp_results)} 檔")

# ================================
# 8. 結果呈現區
# ================================
display_results = st.session_state.results_data

if mode == "❤️ 收藏追蹤":
    display_results = [r for r in display_results if r["sid"] in st.session_state.favorites]

if display_results:
    # 表格
    table_rows = []
    for r in display_results:
        table_rows.append({
            "收藏": r["收藏"],
            "代碼": r["sid"],
            "名稱": r["名稱"],
            "現價": r["現價"],
            "趨勢": r["趨勢"],
            "MA20": r["MA20"],
            "MA60": r["MA60"],
            "訊號": r["符合訊號"],
            "Yahoo": r["Yahoo"]
        })

    df_table = pd.DataFrame(table_rows)

    edited = st.data_editor(
        df_table,
        column_config={
            "收藏": st.column_config.CheckboxColumn("❤️", width="small"),
            "Yahoo": st.column_config.LinkColumn("Yahoo", display_text="🔍 Yahoo", width="medium"),
            "現價": st.column_config.NumberColumn(format="%.2f"),
            "MA20": st.column_config.NumberColumn(format="%.2f"),
            "MA60": st.column_config.NumberColumn(format="%.2f"),
        },
        hide_index=True,
        use_container_width=True,
        key=f"data_editor_{mode}_{category_filter}"
    )

    # 同步收藏變更
    new_favorites = set(edited[edited["收藏"] == True]["代碼"])
    if new_favorites != st.session_state.favorites:
        st.session_state.favorites = new_favorites
        st.rerun()

    st.divider()

    # K線圖展示
    st.subheader("個股詳細 K 線與趨勢線")
    for item in display_results:
        with st.expander(
            f"{item['sid']} {item['名稱']}  |  {item['符合訊號']}  |  {item['趨勢']}",
            expanded=False
        ):
            col1, col2, col3 = st.columns(3)
            col1.metric("現價", f"{item['現價']:.2f} 元")
            col2.metric("MA20", f"{item['MA20']:.2f}")
            col3.metric("趨勢", item["趨勢"])

            # 繪製圖表
            plot_df = item["df"].iloc[-60:]
            fig = go.Figure()

            fig.add_trace(go.Candlestick(
                x=plot_df.index,
                open=plot_df['Open'],
                high=plot_df['High'],
                low=plot_df['Low'],
                close=plot_df['Close'],
                name="K 線",
                increasing_line_color="#ef5350",
                decreasing_line_color="#26a69a"
            ))

            sh, ih, sl, il, x_range = item["lines"]
            x_dates = plot_df.index[-len(x_range):]

            fig.add_trace(go.Scatter(
                x=x_dates,
                y=sh * x_range + ih,
                mode="lines",
                line=dict(color="red", dash="dash", width=2),
                name="壓力線"
            ))

            fig.add_trace(go.Scatter(
                x=x_dates,
                y=sl * x_range + il,
                mode="lines",
                line=dict(color="lime", dash="dash", width=2),
                name="支撐線"
            ))

            fig.update_layout(
                height=450,
                margin=dict(l=10, r=10, t=30, b=10),
                xaxis_rangeslider_visible=False,
                template="plotly_dark" if "dark" in st.get_option("theme.base", "light") else "plotly_white"
            )

            st.plotly_chart(fig, use_container_width=True, key=f"chart_{item['sid']}")

else:
    if mode == "⚖️ 條件篩選":
        st.info("請設定條件後點擊「開始條件篩選」")
    elif mode == "❤️ 收藏追蹤":
        st.info("收藏清單為空，請加入股票")
    else:
        st.caption("尚未有符合條件的結果")

# 頁尾資訊
st.markdown("---")
st.caption(
    "台股 Pro 旗艦戰情室 v4.0 | "
    "資料來源：證交所 + yfinance | "
    "僅供學習與參考，投資有風險，請自行評估"
)
st.caption(f"最後快取更新：{st.session_state.last_cache_update.strftime('%Y-%m-%d %H:%M') if st.session_state.last_cache_update else '尚未更新'}")
