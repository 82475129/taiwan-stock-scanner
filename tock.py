# -*- coding: utf-8 -*-
"""
台股 Pro 旗艦戰情室 - 完整本地版（Streamlit UI 完整版，超過700行）
專案對應檔案：
- taiwan_full_market.json → 股票清單（支援 FinMind 自動更新）
- taiwan_stock_prices.pkl → 價格快取（本地儲存）
- requirements.txt → 依賴套件（需包含 requests）
主要功能總覽：
- 股票清單從 JSON 讀取，支援側邊欄一鍵從 FinMind API 更新（含產業分類）
- 價格資料使用 pickle 快取（解決 yfinance rate limit）
- 爆量計算：前 5 天平均成交量 × 1.5 倍
- 掃描上限預設 200，可調至 2000
- 四種模式：手動查詢、條件篩選、自動掃描、收藏追蹤
- K 線圖 + 壓力/支撐趨勢線（Plotly）
- 側邊欄「更新價格快取」與「更新股票清單」按鈕（批次下載 + 進度條）
- 收藏功能跨模式共享（表格勾選即時同步）
- 豐富錯誤處理、使用者提示、進度顯示、防呆邏輯（解決 AttributeError）
使用步驟：
1. 第一次執行 → 點側邊欄「更新股票清單 JSON (FinMind)」
2. 再點「更新全市場價格快取」（需 10–30 分鐘）
3. 之後掃描全部從本地讀取，速度極快
4. 資料僅供參考，非投資建議
最後更新：2026 年 1 月
"""
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
from streamlit_autorefresh import st_autorefresh
import pickle
from pathlib import Path
import time
from datetime import datetime
import json
import warnings
import os
import sys
import traceback
import requests  # 新增：用於 FinMind API 更新股票清單

# ================================
# 忽略常見警告，讓介面更乾淨
# ================================
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=pd.errors.SettingWithCopyWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# ================================
# 頁面基本設定
# ================================
st.set_page_config(
    page_title="台股 Pro 旗艦戰情室 - 完整本地版",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://github.com/streamlit/streamlit',
        'Report a bug': "https://github.com/streamlit/streamlit/issues",
        'About': "台股 Pro 旗艦戰情室 - 個人學習專案，非商業用途"
    }
)

# ================================
# Session State 初始化與管理
# ================================
if 'favorites' not in st.session_state:
    st.session_state.favorites = set()
if 'results_data' not in st.session_state:
    st.session_state.results_data = []
if 'last_mode' not in st.session_state:
    st.session_state.last_mode = None
if 'full_db' not in st.session_state:
    st.session_state.full_db = None
if 'price_cache' not in st.session_state:
    st.session_state.price_cache = None
if 'last_cache_update' not in st.session_state:
    st.session_state.last_cache_update = None

# ================================
# 檔案路徑定義
# ================================
STOCK_JSON_PATH = Path("taiwan_full_market.json")
PRICE_CACHE_PATH = Path("taiwan_stock_prices.pkl")

# ================================
# 新增：從 FinMind API 更新股票清單 JSON
# ================================
def update_stock_json_from_finmind():
    import requests, json, os

    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockInfo"
    }

    r = requests.get(url, params=params, timeout=20)
    result = r.json()

    if not result.get("success", True):
        raise RuntimeError(f"FinMind API 失敗：{result.get('msg', result)}")

    if "data" not in result:
        raise ValueError(f"FinMind API 回傳異常：{result}")

    data = result["data"]

    # ✅ 組成「代碼 → 詳細資訊」的新結構
    stock_dict = {}
    for row in data:
        stock_id = row.get("stock_id")
        if not stock_id:
            continue

        stock_dict[f"{stock_id}.TW"] = {
        "name": row.get("stock_name", ""),
        "category": row.get("industry_category", ""),  # ✅ 關鍵
        "type": row.get("type", "")
    }


    # ✅ 關鍵：寫入你現在正在用的那個檔案
    json_path = "taiwan_full_market.json"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(stock_dict, f, ensure_ascii=False, indent=2)

    print(f"✅ 已更新 {len(stock_dict)} 筆股票 → {json_path}")
    return stock_dict, len(stock_dict)


def load_stock_database():
    """
    從專案中的 taiwan_full_market.json 載入股票清單
    支援多種結構防呆：
    - { "2330.TW": {"name": "...", "category": "..."} }
    - { "2330.TW": "台積電" }
    - 其他格式轉為 fallback
    """
    if STOCK_JSON_PATH.exists():
        try:
            with open(STOCK_JSON_PATH, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            # 標準化成 {symbol: {"name": "...", "category": "..."}} 格式
            normalized_db = {}
            for symbol, value in raw_data.items():
                if isinstance(value, dict):
                    name = value.get("name", symbol)
                    category = value.get("category", "未知")
                elif isinstance(value, str):
                    name = value
                    category = "未知"
                elif isinstance(value, list) and len(value) >= 1:
                    name = value[0]
                    category = value[1] if len(value) > 1 else "未知"
                else:
                    name = str(value)
                    category = "未知"
                normalized_db[symbol] = {"name": name, "category": category}
            if len(normalized_db) < 10:
                raise ValueError("JSON 內容太少")
            st.success(f"股票清單載入完成：{len(normalized_db)} 檔（來自自動更新）")
            return normalized_db
        except json.JSONDecodeError as je:
            st.error(f"JSON 解析失敗：{je}")
        except Exception as e:
            st.error(f"讀取 taiwan_full_market.json 失敗：{str(e)}")
            traceback.print_exc(file=sys.stderr)
    # fallback 資料（少量範例）
    st.warning("JSON 載入失敗或未找到，使用 fallback 資料")
    fallback_db = {
        "2330.TW": {"name": "台積電", "category": "半導體"},
        "2454.TW": {"name": "聯發科", "category": "半導體"},
        "2317.TW": {"name": "鴻海", "category": "電子"},
        "2603.TW": {"name": "長榮", "category": "航運"},
        "1216.TW": {"name": "統一", "category": "食品"},
        "1101.TW": {"name": "台泥", "category": "水泥"},
        "2303.TW": {"name": "聯電", "category": "半導體"}
    }
    return fallback_db

# 載入資料庫（只執行一次）
if st.session_state.full_db is None:
    st.session_state.full_db = load_stock_database()
full_db = st.session_state.full_db

# ================================
# 價格快取管理函式
# ================================
def load_price_cache():
    """從 pickle 載入價格快取"""
    if PRICE_CACHE_PATH.exists():
        try:
            with open(PRICE_CACHE_PATH, 'rb') as f:
                data = pickle.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            st.error(f"讀取價格快取失敗：{str(e)}")
    return {}

def save_price_cache(cache_dict):
    """儲存價格快取到 pickle"""
    try:
        with open(PRICE_CACHE_PATH, 'wb') as f:
            pickle.dump(cache_dict, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as e:
        st.error(f"儲存價格快取失敗：{str(e)}")

# 初始化價格快取
if st.session_state.price_cache is None:
    st.session_state.price_cache = load_price_cache()
price_cache = st.session_state.price_cache

# ================================
# 抓取價格資料（優先本地快取）
# ================================
def fetch_price(symbol: str) -> pd.DataFrame:
    """
    優先從本地快取取資料，若無則即時下載並存入快取
    """
    if symbol in price_cache:
        df = price_cache[symbol]
        if isinstance(df, pd.DataFrame) and not df.empty and 'Close' in df.columns:
            return df.copy()
    # 即時下載
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
        st.warning(f"下載 {symbol} 失敗：{str(e)}")
        return pd.DataFrame()

# ================================
# 核心技術分析函式
# ================================
def run_analysis(
    sid: str,
    name: str,
    df: pd.DataFrame,
    cfg: dict,
    is_manual: bool = False
) -> dict | None:
    """
    對單一股票進行技術分析
    回傳符合條件的結果字典，或 None
    """
    if df.empty or 'Close' not in df.columns or len(df) < 60:
        return None
    try:
        # 最新價格與均線
        current_price = float(df['Close'].iloc[-1])
        ma20_val = df['Close'].rolling(window=20).mean().iloc[-1]
        ma60_val = df['Close'].rolling(window=60).mean().iloc[-1]
        trend_label = '🔴 多頭排列' if ma20_val > ma60_val else '🟢 空頭排列'
        # 最近 lb 天的壓力/支撐線
        lookback = cfg.get("p_lookback", 15)
        if len(df) < lookback:
            return None
        x_arr = np.arange(lookback)
        high_prices = df["High"].iloc[-lookback:].values
        low_prices = df["Low"].iloc[-lookback:].values
        slope_high, intercept_high, _, _, _ = linregress(x_arr, high_prices)
        slope_low, intercept_low, _, _, _ = linregress(x_arr, low_prices)
        # 訊號收集
        signals_list = []
        # 三角收斂
        if slope_high < -0.001 and slope_low > 0.001:
            signals_list.append("📐三角收斂")
        # 箱型整理
        if abs(slope_high) < 0.03 and abs(slope_low) < 0.03:
            signals_list.append("📦箱型整理")
        # 爆量判斷
        if len(df) >= 6 and cfg.get("check_vol", True):
        vol_last5 = df["Volume"].iloc[-6:-1]
        if not vol_last5.empty:
        vol_last5_mean = vol_last5.mean()
        vol_today = df["Volume"].iloc[-1]
        if np.isscalar(vol_today) and np.isscalar(vol_last5_mean):
            if vol_today > vol_last5_mean * 1.5:
                signals_list.append("🚀今日爆量")

        # 是否顯示邏輯
        should_display = is_manual
        if not is_manual:
            has_valid_signal = any([
                cfg.get("check_tri", False) and "📐" in "".join(signals_list),
                cfg.get("check_box", False) and "📦" in "".join(signals_list),
                cfg.get("check_vol", False) and "🚀" in "".join(signals_list)
            ])
            should_display = has_valid_signal
            # 額外過濾
            if cfg.get("f_ma_filter", False) and current_price < ma20_val:
                should_display = False
            if current_price < cfg.get("min_price", 0):
                should_display = False
        if should_display:
            return {
                "收藏": sid in st.session_state.favorites,
                "sid": sid,
                "名稱": name,
                "現價": round(current_price, 2),
                "趨勢": trend_label,
                "MA20": round(ma20_val, 2),
                "MA60": round(ma60_val, 2),
                "符合訊號": ", ".join(signals_list) if signals_list else "🔍 觀察中",
                "Yahoo": f"https://tw.stock.yahoo.com/quote/{sid.split('.')[0]}",
                "df": df.copy(),
                "lines": (slope_high, intercept_high, slope_low, intercept_low, x_arr)
            }
    except Exception as exc:
        st.warning(f"分析 {sid} 失敗：{str(exc)}")
        traceback.print_exc(file=sys.stderr)
    return None

# ================================
# 側邊欄控制面板
# ================================
st.sidebar.title("🛡️ 台股 Pro 戰術控制台")
st.sidebar.markdown(f"**股票清單**：{len(full_db)} 檔（自動更新）")

# 模式選擇
mode_selected = st.sidebar.radio(
    "分析模式",
    options=["🔍 手動查詢", "⚖️ 條件篩選", "⚡ 自動掃描", "❤️ 收藏追蹤"],
    index=0,
    key="main_mode_radio"
)

# 模式切換清空舊結果
if st.session_state.last_mode != mode_selected:
    st.session_state.results_data = []
    st.session_state.last_mode = mode_selected

# 參數設定
analysis_cfg = {
    "p_lookback": 15,
    "min_price": 0.0,
    "check_tri": True,
    "check_box": True,
    "check_vol": True,
    "f_ma_filter": False,
    "scan_limit": 200
}

# 產業選擇（擴充細分類）
industry_filter = st.sidebar.selectbox(
    "主要產業類別",
    options=[
        "全部", "半導體", "光電", "電子零組件", "電腦週邊", "通訊網路",
        "塑膠", "紡織", "鋼鐵", "食品", "金融業", "航運", "生技醫療",
        "水泥", "玻璃陶瓷", "其他"
    ],
    index=1,
    key="industry_select"
)

# 條件篩選 / 自動掃描 專用設定區
if mode_selected in ["⚖️ 條件篩選", "⚡ 自動掃描"]:
    st.sidebar.divider()
    st.sidebar.subheader("篩選條件設定")
    col_check1, col_check2 = st.sidebar.columns(2)
    with col_check1:
        analysis_cfg["check_tri"] = st.checkbox("📐 三角收斂", value=True)
        analysis_cfg["check_box"] = st.checkbox("📦 箱型整理", value=True)
    with col_check2:
        analysis_cfg["check_vol"] = st.checkbox("🚀 今日爆量 (前5天×1.5)", value=True)
        analysis_cfg["f_ma_filter"] = st.checkbox("限 MA20 之上", value=False)
    analysis_cfg["min_price"] = st.sidebar.slider(
        "最低股價門檻 (元)",
        min_value=0.0,
        max_value=1000.0,
        value=0.0,
        step=1.0
    )
    analysis_cfg["scan_limit"] = st.sidebar.slider(
        "掃描上限 (檔數)",
        min_value=50,
        max_value=2000,
        value=200,
        step=50,
        help="建議 200–500 檔，避免記憶體過載"
    )

# 資料庫管理區塊
st.sidebar.divider()
st.sidebar.subheader("資料庫管理")

# 更新全市場價格快取（原有）
update_price_button = st.sidebar.button(
    "🔄 更新全市場價格快取",
    type="primary",
    help="建議每天執行一次，更新後掃描速度極快（本地讀取）"
)
if update_price_button:
    with st.status("正在更新全市場價格資料（約 1800 檔）...", expanded=True) as update_status:
        all_symbols = list(full_db.keys())
        progress_bar = st.progress(0)
        batch_size = 80  # 保守批次大小，避免被 Yahoo 限速
        updated_items = 0
        for batch_idx in range(0, len(all_symbols), batch_size):
            batch_list = all_symbols[batch_idx : batch_idx + batch_size]
            try:
                multi_data = yf.download(
                    batch_list,
                    period="1y",
                    group_by="ticker",
                    threads=True,
                    auto_adjust=True
                )
                for sym in batch_list:
                    if sym in multi_data.columns.levels[0]:
                        price_cache[sym] = multi_data[sym].copy()
                        updated_items += 1
            except Exception as batch_err:
                st.warning(f"批次 {batch_idx//batch_size + 1} 下載失敗：{batch_err}")
            progress_bar.progress(min((batch_idx + batch_size) / len(all_symbols), 1.0))
            time.sleep(1.2)  # 避免過快請求
        save_price_cache(price_cache)
        st.session_state.last_cache_update = datetime.now()
        update_status.update(
            label=f"更新完成！處理 {updated_items} 檔資料",
            state="complete"
        )

# 新增：更新股票清單 JSON
update_list_button = st.sidebar.button(
    "🔄 更新股票清單 JSON (FinMind)",
    type="secondary",
    help="從 FinMind API 抓取最新股票名稱與產業分類，覆蓋本地 JSON"
)
if update_list_button:
    new_data, count = update_stock_json_from_finmind()
    if new_data:
        st.session_state.full_db = load_stock_database()
        full_db = st.session_state.full_db
        st.success("股票清單已更新，請重新選擇模式或產業")
        st.rerun()

if st.session_state.last_cache_update:
    st.sidebar.caption(f"最後更新時間：{st.session_state.last_cache_update.strftime('%Y-%m-%d %H:%M')}")

# ================================
# 主畫面內容
# ================================
st.title(f"📈 {mode_selected}")
st.caption(f"目前模式：{mode_selected} | 產業：{industry_filter} | 總標的：{len(full_db)} 檔")

# 過濾符合產業的代碼清單（防呆版）
symbol_list = list(full_db.keys())

# ✅ 檢查 JSON 裡到底有沒有 category
has_category = any(
    isinstance(v, dict) and "category" in v
    for v in full_db.values()
)

# ✅ 只有「真的有 category」才做產業篩選
if industry_filter != "全部" and has_category:
    filtered = []
    for s in symbol_list:
        value = full_db.get(s)

        if isinstance(value, dict):
            category_value = value.get("category", "")
        else:
            category_value = ""

        if industry_filter in str(category_value):
            filtered.append(s)

    symbol_list = filtered
    if not symbol_list:
        st.sidebar.warning(f"找不到產業為「{industry_filter}」的股票，請確認 JSON 是否包含 category 欄位")

# ================================
# 各模式邏輯
# ================================
if mode_selected == "🔍 手動查詢":
    manual_input = st.text_input(
        "請輸入股票代碼（多檔用逗號分隔）",
        placeholder="例：2330, 2454, 2603, 1216",
        key="manual_input_box"
    )
    if manual_input:
        code_list = [c.strip().upper() for c in manual_input.replace("，", ",").split(",") if c.strip()]
        results_temp = []
        with st.spinner("正在分析手動輸入的標的..."):
            for code in code_list:
                sym = code if '.' in code else f"{code}.TW"
                df_data = fetch_price(sym)
                stock_name = full_db.get(sym, {}).get("name", code) if isinstance(full_db.get(sym), dict) else code
                analysis_result = run_analysis(sym, stock_name, df_data, analysis_cfg, is_manual=True)
                if analysis_result:
                    results_temp.append(analysis_result)
        st.session_state.results_data = results_temp

elif mode_selected == "⚖️ 條件篩選":
    st.info("請設定左側條件，然後點擊下方按鈕開始全市場掃描")
    if st.button("🚀 開始條件篩選", type="primary", use_container_width=True):
        max_scan = analysis_cfg["scan_limit"]
        scan_symbols = symbol_list[:max_scan]
        temp_results = []
        with st.status(f"掃描中...（{len(scan_symbols)} 檔，{industry_filter}類）", expanded=True) as scan_status:
            progress_bar = st.progress(0)
            for idx, sym in enumerate(scan_symbols):
                df_data = fetch_price(sym)
                stock_name = full_db.get(sym, {}).get("name", "未知") if isinstance(full_db.get(sym), dict) else "未知"
                analysis_result = run_analysis(sym, stock_name, df_data, analysis_cfg, is_manual=False)
                if analysis_result:
                    temp_results.append(analysis_result)
                progress_bar.progress((idx + 1) / len(scan_symbols))
                if (idx + 1) % 50 == 0:
                    time.sleep(0.05)  # 輕微延遲，避免 CPU 過載
            st.session_state.results_data = temp_results
            scan_status.update(
                label=f"掃描完成！共找到 {len(temp_results)} 檔符合條件",
                state="complete"
            )

elif mode_selected == "⚡ 自動掃描":
    st_autorefresh(interval=60000, key="auto_scan_refresh")
    st.warning("自動掃描模式啟動，每 60 秒更新一次（限制前 150 檔避免過載）")
    auto_scan_limit = min(len(symbol_list), 150)
    scan_symbols = symbol_list[:auto_scan_limit]
    temp_results = []
    with st.spinner(f"自動掃描 {len(scan_symbols)} 檔中..."):
        for sym in scan_symbols:
            df_data = fetch_price(sym)
            stock_name = full_db.get(sym, {}).get("name", "未知") if isinstance(full_db.get(sym), dict) else "未知"
            analysis_result = run_analysis(sym, stock_name, df_data, analysis_cfg, is_manual=False)
            if analysis_result:
                temp_results.append(analysis_result)
    st.session_state.results_data = temp_results

elif mode_selected == "❤️ 收藏追蹤":
    fav_count = len(st.session_state.favorites)
    if fav_count == 0:
        st.info("目前沒有收藏股票。從其他模式點擊 ❤️ 加入收藏吧！")
    else:
        st.subheader(f"收藏清單（{fav_count} 檔）")
        if st.button("🔄 立即更新收藏報價", type="primary"):
            temp_results = []
            with st.status("更新收藏股中..."):
                for sym in list(st.session_state.favorites):
                    df_data = fetch_price(sym)
                    stock_name = full_db.get(sym, {}).get("name", sym) if isinstance(full_db.get(sym), dict) else sym
                    analysis_result = run_analysis(sym, stock_name, df_data, analysis_cfg, is_manual=True)
                    if analysis_result:
                        temp_results.append(analysis_result)
            st.session_state.results_data = temp_results
            st.success(f"更新完成，共 {len(temp_results)} 檔")

# ================================
# 結果呈現區塊
# ================================
display_results = st.session_state.results_data
# 收藏模式額外過濾
if mode_selected == "❤️ 收藏追蹤":
    display_results = [item for item in display_results if item["sid"] in st.session_state.favorites]

if display_results:
    # 表格資料準備
    table_records = []
    for item in display_results:
        table_records.append({
            "收藏": item["收藏"],
            "代碼": item["sid"],
            "名稱": item["名稱"],
            "現價": item["現價"],
            "趨勢": item["趨勢"],
            "MA20": item["MA20"],
            "MA60": item["MA60"],
            "訊號": item["符合訊號"],
            "Yahoo": item["Yahoo"]
        })
    df_table = pd.DataFrame(table_records)
    edited_table = st.data_editor(
        df_table,
        column_config={
            "收藏": st.column_config.CheckboxColumn("❤️ 收藏", width="small"),
            "Yahoo": st.column_config.LinkColumn("Yahoo", display_text="🔍 Yahoo", width="medium"),
            "現價": st.column_config.NumberColumn(format="%.2f"),
            "MA20": st.column_config.NumberColumn(format="%.2f"),
            "MA60": st.column_config.NumberColumn(format="%.2f"),
        },
        hide_index=True,
        use_container_width=True,
        key=f"editor_{mode_selected}_{industry_filter}"
    )
    # 處理即時收藏變更
    new_favorites = set(edited_table[edited_table["收藏"] == True]["代碼"].tolist())
    if new_favorites != st.session_state.favorites:
        st.session_state.favorites = new_favorites
        st.rerun()
    st.divider()
    # K線圖區
    st.subheader("個股 K 線與趨勢線詳圖")
    for item in display_results:
        with st.expander(
            f"{item['sid']} {item['名稱']} | {item['符合訊號']} | {item['趨勢']}",
            expanded=False
        ):
            cols = st.columns(3)
            cols[0].metric("現價", f"{item['現價']:.2f} 元")
            cols[1].metric("MA20", f"{item['MA20']:.2f}")
            cols[2].metric("趨勢", item["趨勢"])
            # 繪製 K 線（最近 60 天）
            plot_df = item["df"].iloc[-60:].copy()
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
            # 加入壓力與支撐趨勢線
            sh, ih, sl, il, x_vals = item["lines"]
            x_dates = plot_df.index[-len(x_vals):]
            fig.add_trace(go.Scatter(
                x=x_dates,
                y=sh * x_vals + ih,
                mode='lines',
                line=dict(color='red', dash='dash', width=2),
                name='壓力線'
            ))
            fig.add_trace(go.Scatter(
                x=x_dates,
                y=sl * x_vals + il,
                mode='lines',
                line=dict(color='lime', dash='dash', width=2),
                name='支撐線'
            ))
            fig.update_layout(
                height=480,
                margin=dict(l=10, r=10, t=30, b=10),
                xaxis_rangeslider_visible=False,
                template="plotly_dark" if "dark" in str(st.get_option("theme.base", "light")).lower() else "plotly_white"
            )

            st.plotly_chart(fig, use_container_width=True, key=f"chart_{item['sid']}")
else:
    # 無結果提示
    if mode_selected == "⚖️ 條件篩選":
        st.info("尚未執行篩選，請設定條件後按「開始條件篩選」")
    elif mode_selected == "❤️ 收藏追蹤":
        st.info("收藏清單為空，快去其他模式加入喜歡的股票吧！")
    else:
        st.caption("目前無符合條件標的，或尚未執行分析")

# ================================
# 頁尾資訊
# ================================
st.markdown("---")
st.caption(
    "台股 Pro 旗艦戰情室 | "
    "股票清單來源：taiwan_full_market.json（FinMind 自動更新） | "
    "價格資料來源：yfinance + 本地快取 | "
    "僅供學習與參考，投資有風險，請自行評估"
)
if st.session_state.last_cache_update:
    st.caption(f"價格資料最後更新：{st.session_state.last_cache_update.strftime('%Y-%m-%d %H:%M')}")
else:
    st.caption("價格資料尚未更新，請點擊側邊欄更新按鈕")
st.caption("祝交易順利！📈")






