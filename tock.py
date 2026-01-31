# -*- coding: utf-8 -*-
"""
台股 Pro 旗艦戰情室 - 完整本地版（Streamlit UI）
專案目標：提供台股全市場快速篩選、技術分析、可視化工具
主要特色：
  • FinMind API 自動更新股票清單與產業分類
  • yfinance 價格資料 + 本地 pickle 快取（避免 rate limit）
  • 四種模式：手動查詢、條件篩選、自動掃描、收藏追蹤
  • 技術訊號：三角收斂、箱型整理、爆量、MA排列
  • Plotly K線圖 + 壓力/支撐趨勢線
  • data_editor 即時勾選收藏（跨模式同步）
  • 批次更新進度條、錯誤處理、使用者提示
使用建議流程：
1. 第一次執行 → 側邊欄「更新股票清單 JSON (FinMind)」
2. 再執行「更新全市場價格快取」（約15–40分鐘）
3. 之後日常使用都從本地快取讀取，速度極快
注意事項：
• 所有資料僅供個人學習與參考
• 非投資建議，交易風險自負
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
import requests
import traceback
import sys
import os

# 忽略常見警告，讓介面更乾淨
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=pd.errors.SettingWithCopyWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# ────────────────────────────────────────────────
#               頁面基本設定
# ────────────────────────────────────────────────
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

# ────────────────────────────────────────────────
#               Session State 初始化
# ────────────────────────────────────────────────
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

# ────────────────────────────────────────────────
#               檔案路徑定義
# ────────────────────────────────────────────────
STOCK_JSON_PATH = Path("taiwan_full_market.json")
PRICE_CACHE_PATH = Path("taiwan_stock_prices.pkl")

# ────────────────────────────────────────────────
#          FinMind API 更新股票清單（強制覆蓋）
# ────────────────────────────────────────────────
def update_stock_json_from_finmind():
    """從 FinMind 抓取最新台股清單並強制覆蓋本地 JSON"""
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {"dataset": "TaiwanStockInfo"}
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        result = r.json()
        if not result.get("success", True):
            st.error(f"FinMind API 失敗：{result.get('msg', '未知錯誤')}")
            return None, 0
        data = result.get("data", [])
        if not data:
            st.warning("FinMind 回傳資料為空")
            return None, 0
        
        stock_dict = {}
        for row in data:
            sid = row.get("stock_id")
            if sid and sid.isdigit():
                name = row.get("stock_name", sid)
                category = row.get("industry_category", "未知")
                stock_dict[f"{sid}.TW"] = {
                    "name": str(name).strip(),
                    "category": str(category).strip()
                }
        
        # 強制覆蓋寫入
        with open(STOCK_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(stock_dict, f, ensure_ascii=False, indent=2)
        
        st.success(f"成功覆蓋更新 {len(stock_dict)} 檔股票清單 → {STOCK_JSON_PATH}")
        return stock_dict, len(stock_dict)
    
    except requests.exceptions.RequestException as re:
        st.error(f"網路請求失敗：{str(re)}")
        return None, 0
    except Exception as e:
        st.error(f"更新股票清單異常：{str(e)}")
        traceback.print_exc(file=sys.stderr)
        return None, 0

# ────────────────────────────────────────────────
#          載入股票資料庫（超強防呆版）
# ────────────────────────────────────────────────
def load_stock_database():
    """載入 taiwan_full_market.json，處理各種異常格式"""
    if STOCK_JSON_PATH.exists():
        try:
            with open(STOCK_JSON_PATH, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            
            db = {}
            abnormal_count = 0
            for symbol, val in raw.items():
                name = symbol
                category = "未知"
                
                if isinstance(val, dict):
                    name = val.get("name", symbol)
                    category = val.get("category", "未知")
                elif isinstance(val, str):
                    name = val
                else:
                    # 處理 float/int/None/list 等異常情況
                    name = str(val) if val is not None else symbol
                    abnormal_count += 1
                
                # 只對字串做 strip
                name = name.strip() if isinstance(name, str) else str(name)
                category = category.strip() if isinstance(category, str) else str(category)
                
                db[symbol] = {"name": name, "category": category}
            
            if abnormal_count > 0:
                st.warning(f"發現 {abnormal_count} 筆非標準格式資料，已轉為字串處理")
            
            if len(db) >= 50:
                st.info(f"股票清單載入完成：{len(db)} 檔")
                return db
            else:
                st.warning(f"JSON 資料量過少 ({len(db)})，使用 fallback")
        except json.JSONDecodeError:
            st.error("JSON 格式錯誤，請刪除檔案後重新更新")
        except Exception as e:
            st.error(f"讀取 JSON 失敗：{str(e)}")
            traceback.print_exc(file=sys.stderr)
    
    # fallback 小資料
    st.warning("使用內建 fallback 股票清單（少量範例）")
    fallback_db = {
        "2330.TW": {"name": "台積電",     "category": "半導體"},
        "2454.TW": {"name": "聯發科",     "category": "半導體"},
        "2317.TW": {"name": "鴻海",       "category": "電子"},
        "2603.TW": {"name": "長榮",       "category": "航運"},
        "2615.TW": {"name": "萬海",       "category": "航運"},
        "1216.TW": {"name": "統一",       "category": "食品"},
        "1101.TW": {"name": "台泥",       "category": "水泥"},
        "2303.TW": {"name": "聯電",       "category": "半導體"},
        "3034.TW": {"name": "聯詠",       "category": "半導體"},
        "3443.TW": {"name": "創意",       "category": "半導體"},
    }
    return fallback_db

# 載入資料庫（只執行一次）
if st.session_state.full_db is None:
    st.session_state.full_db = load_stock_database()
full_db = st.session_state.full_db

# ────────────────────────────────────────────────
#               價格快取管理
# ────────────────────────────────────────────────
def load_price_cache():
    if PRICE_CACHE_PATH.exists():
        try:
            with open(PRICE_CACHE_PATH, 'rb') as f:
                data = pickle.load(f)
                return data if isinstance(data, dict) else {}
        except Exception as e:
            st.error(f"讀取價格快取失敗：{str(e)}")
    return {}

def save_price_cache(cache):
    try:
        with open(PRICE_CACHE_PATH, 'wb') as f:
            pickle.dump(cache, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as e:
        st.error(f"儲存價格快取失敗：{str(e)}")

if st.session_state.price_cache is None:
    st.session_state.price_cache = load_price_cache()
price_cache = st.session_state.price_cache

def fetch_price(symbol: str) -> pd.DataFrame:
    """優先從快取取，若無則下載並儲存"""
    if symbol in price_cache:
        df = price_cache[symbol]
        if isinstance(df, pd.DataFrame) and not df.empty:
            return df.copy()
    
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
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            price_cache[symbol] = df.copy()
            save_price_cache(price_cache)
            st.session_state.last_cache_update = datetime.now()
        return df
    except Exception as e:
        st.warning(f"下載 {symbol} 失敗：{str(e)}")
        return pd.DataFrame()

# ────────────────────────────────────────────────
#               核心技術分析函式
# ────────────────────────────────────────────────
def run_analysis(
    sid: str,
    name: str,
    df: pd.DataFrame,
    cfg: dict,
    is_manual: bool = False
) -> dict | None:
    """
    分析單檔股票走勢與訊號
    
    sid : 股票代碼 (含 .TW)
    name : 股票名稱
    df : 歷史價格資料 (需含 Close, High, Low, Volume)
    cfg : 分析參數設定 (dict)
    is_manual : 是否手動模式，手動模式會直接顯示所有結果
    """
    
    # -------------------- 基本檢查 --------------------
    required_cols = ["Close", "High", "Low", "Volume"]
    if df.empty or not all(col in df.columns for col in required_cols) or len(df) < 60:
        return None

    try:
        # -------------------- 計算現價與均線 --------------------
        current_price = float(df['Close'].iloc[-1])
        ma20_val = float(df['Close'].rolling(window=20).mean().iloc[-1])
        ma60_val = float(df['Close'].rolling(window=60).mean().iloc[-1])

        trend_label = '🔴 多頭排列' if ma20_val > ma60_val else '🟢 空頭排列'

        # -------------------- 三角 / 箱型訊號 --------------------
        lookback = cfg.get("p_lookback", 15)
        if len(df) < lookback:
            return None

        x_arr = np.arange(lookback)
        high_prices = df["High"].iloc[-lookback:].values.flatten()
        low_prices  = df["Low"].iloc[-lookback:].values.flatten()

        slope_high, intercept_high, _, _, _ = linregress(x_arr, high_prices)
        slope_low,  intercept_low,  _, _, _ = linregress(x_arr, low_prices)

        signals_list = []
        # 三角收斂：上升與下降趨勢互相收斂
        if slope_high < -0.001 and slope_low > 0.001:
            signals_list.append("📐三角收斂")
        # 箱型整理：高低價趨勢平緩
        if abs(slope_high) < 0.03 and abs(slope_low) < 0.03:
            signals_list.append("📦箱型整理")

        # -------------------- 成交量訊號 --------------------
        if len(df) >= 6 and cfg.get("check_vol", True):
            vol_today = float(df["Volume"].iloc[-1])
            vol_prev5 = df["Volume"].iloc[-6:-1]
            vol_avg5 = vol_prev5.mean() if not vol_prev5.empty else 0
            if vol_avg5 > 0 and vol_today > vol_avg5 * 1.5:
                signals_list.append("🚀今日爆量")

        # -------------------- 是否顯示 --------------------
        should_display = is_manual
        if not is_manual:
            has_valid_signal = any([
                cfg.get("check_tri", False) and any("📐" in s for s in signals_list),
                cfg.get("check_box", False) and any("📦" in s for s in signals_list),
                cfg.get("check_vol", False) and any("🚀" in s for s in signals_list)
            ])
            should_display = has_valid_signal

            # 均線濾掉低於 MA20 的股票
            if cfg.get("f_ma_filter", False) and current_price < ma20_val:
                should_display = False
            # 價格下限濾掉
            if current_price < cfg.get("min_price", 0):
                should_display = False

        # -------------------- 組合返回字典 --------------------
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
        # 單檔股票失敗不影響整體
        st.warning(f"⚠️ 股票 {sid} 分析失敗: {exc}")
        return None

    return None


# ────────────────────────────────────────────────
#               側邊欄控制面板
# ────────────────────────────────────────────────
st.sidebar.title("🛡️ 台股 Pro 戰術控制台")
st.sidebar.markdown(f"**股票清單**：{len(full_db)} 檔")

mode_selected = st.sidebar.radio(
    "分析模式",
    options=["🔍 手動查詢", "⚖️ 條件篩選", "⚡ 自動掃描", "❤️ 收藏追蹤"],
    index=0,
    key="main_mode_radio"
)

if st.session_state.last_mode != mode_selected:
    st.session_state.results_data = []
    st.session_state.last_mode = mode_selected

analysis_cfg = {
    "p_lookback": 15,
    "min_price": 0.0,
    "check_tri": True,
    "check_box": True,
    "check_vol": True,
    "f_ma_filter": False,
    "scan_limit": 200
}

industry_filter = st.sidebar.selectbox(
    "主要產業類別",
    options=[
       "全部",
        "半導體業",          # ← 這是關鍵，之前你用「半導體」會找不到
        "光電業",
        "電子零組件業",
        "電腦及週邊設備業",
        "通信網路業",
        "生技醫療業",
        "塑膠工業",
        "紡織纖維",
        "鋼鐵工業",
        "食品工業",
        "金融保險業",
        "航運業",
        "觀光餐旅",
        "建材營造業",
        "電機機械",
        "化學工業",
        "其他電子業",
        "其他業",
        "綠能環保",
        "汽車工業",
        "居家生活",
        "文化創意業",
        "數位雲端",
        "資訊服務業",
        "貿易百貨業",
        "玻璃陶瓷",
        "水泥工業",
        "橡膠工業",
        "造紙工業"
    ],
    index=1,  # 改成預設「半導體業」
    key="industry_select"
)

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

st.sidebar.divider()
st.sidebar.subheader("資料庫管理")

update_price_button = st.sidebar.button(
    "🔄 更新全市場價格快取",
    type="primary",
    help="建議每天執行一次，更新後掃描速度極快（本地讀取）"
)

if update_price_button:
    with st.status("正在更新全市場價格資料（約 1800 檔）...", expanded=True) as update_status:
        all_symbols = list(full_db.keys())
        progress_bar = st.progress(0)
        batch_size = 80
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
            time.sleep(1.2)
        save_price_cache(price_cache)
        st.session_state.last_cache_update = datetime.now()
        update_status.update(
            label=f"更新完成！處理 {updated_items} 檔資料",
            state="complete"
        )

update_list_button = st.sidebar.button(
    "🔄 更新股票清單 JSON (FinMind)",
    type="secondary",
    help="從 FinMind API 抓取最新股票名稱與產業分類，強制覆蓋本地 JSON"
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

# ────────────────────────────────────────────────
#               主畫面內容
# ────────────────────────────────────────────────
st.title(f"📈 {mode_selected}")
st.caption(f"目前模式：{mode_selected} | 產業：{industry_filter} | 總標的：{len(full_db)} 檔")

# ================= 股票清單與產業篩選 =================
# ================= 股票清單與產業篩選 =================
symbol_list = list(full_db.keys())

# 只有當不是收藏模式且選擇了特定產業才篩選
if mode_selected != industry_filter != "全部":
    filtered = []
    for s in symbol_list:
        value = full_db.get(s, {})
        if isinstance(value, dict):
            category_value = str(value.get("category", "")).strip()
            if category_value == industry_filter:
                filtered.append(s)
    symbol_list = filtered

    if not symbol_list:
        st.warning(f"⚠️ 找不到產業為「{industry_filter}」的股票，請確認 JSON 是否包含 category 或名稱拼寫正確")
        symbol_list = list(full_db.keys())


# ================= 各模式邏輯 =================
display_results = []

# -------- 手動查詢模式 --------
if mode_selected == "🔍 手動查詢":
    manual_input = st.text_input(
        "請輸入股票代碼（多檔用逗號分隔）",
        placeholder="例：2330, 2454, 2603, 1216",
        key="manual_input_box"
    )
    
    if manual_input:
        code_list = [c.strip().upper() for c in manual_input.replace("，", ",").split(",") if c.strip()]
        if code_list:  # 避免空輸入重複跑
            results_temp = []
            with st.spinner("正在分析手動輸入的標的..."):
                for code in code_list:
                    sym = code if '.' in code else f"{code}.TW"
                    if sym not in full_db:
                        st.warning(f"找不到股票 {sym}，已跳過")
                        continue
                    df_data = fetch_price(sym)
                    stock_name = full_db.get(sym, {}).get("name", code)
                    analysis_result = run_analysis(sym, stock_name, df_data, analysis_cfg, is_manual=True)
                    if analysis_result:
                        results_temp.append(analysis_result)
            
            # 只在有新輸入或結果改變時才更新
            if results_temp != st.session_state.get('last_manual_results', []):
                st.session_state.results_data = results_temp
                st.session_state.last_manual_results = results_temp  # 額外暫存，避免重複計算
            display_results = st.session_state.results_data
    else:
        # 沒有輸入時，清空結果（可選）
        display_results = []
        if 'results_data' in st.session_state:
            del st.session_state.results_data

# -------- 條件篩選模式 --------
elif mode_selected == "⚖️ 條件篩選":
    st.info("請設定左側條件，然後點擊下方按鈕開始全市場掃描")
    
    # 如果已經有暫存結果，先顯示它
    if 'condition_scan_results' not in st.session_state:
        st.session_state.condition_scan_results = []

    display_results = st.session_state.condition_scan_results

    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("🚀 開始條件篩選 / 重新掃描", type="primary", use_container_width=True):
            max_scan = analysis_cfg.get("scan_limit", len(symbol_list))
            scan_symbols = symbol_list[:max_scan]
            temp_results = []
            with st.status(f"掃描中...（{len(scan_symbols)} 檔，{industry_filter}類）", expanded=True) as scan_status:
                progress_bar = st.progress(0)
                for idx, sym in enumerate(scan_symbols):
                    df_data = fetch_price(sym)
                    stock_name = full_db.get(sym, {}).get("name", "未知")
                    analysis_result = run_analysis(sym, stock_name, df_data, analysis_cfg, is_manual=False)
                    if analysis_result:
                        temp_results.append(analysis_result)
                    progress_bar.progress((idx + 1) / len(scan_symbols))
                    if (idx + 1) % 50 == 0:
                        time.sleep(0.05)
                st.session_state.condition_scan_results = temp_results  # 存到專屬暫存
                st.session_state.results_data = temp_results
                if not temp_results:
                    st.info("⚠️ 沒有符合條件的股票，請調整篩選條件")
                scan_status.update(
                    label=f"掃描完成！共找到 {len(temp_results)} 檔符合條件",
                    state="complete"
                )
            display_results = temp_results
            st.rerun()  # 掃描完成後主動 rerun 一次，確保畫面更新

    with col2:
        if st.button("🗑️ 清空結果", type="secondary"):
            st.session_state.condition_scan_results = []
            if 'results_data' in st.session_state:
                del st.session_state.results_data
            st.rerun()

# -------- 自動掃描模式 --------
elif mode_selected == "⚡ 自動掃描":
    st_autorefresh(interval=60000, key="auto_scan_refresh")
    st.warning("自動掃描模式啟動，每 60 秒更新一次（限制前 150 檔避免過載）")
    
    auto_scan_limit = min(len(symbol_list), 150)
    scan_symbols = symbol_list[:auto_scan_limit]
    temp_results = []
    
    with st.spinner(f"自動掃描 {len(scan_symbols)} 檔中..."):
        for sym in scan_symbols:
            df_data = fetch_price(sym)
            stock_name = full_db.get(sym, {}).get("name", "未知")
            analysis_result = run_analysis(sym, stock_name, df_data, analysis_cfg, is_manual=False)
            if analysis_result:
                temp_results.append(analysis_result)

    st.session_state.results_data = temp_results
    if not temp_results:
        st.info("⚠️ 自動掃描沒有找到符合條件的股票")
    display_results = temp_results

# -------- 收藏追蹤模式 --------
# ────────────────────────────────────────────────
# 收藏追蹤模式
# ────────────────────────────────────────────────
elif mode_selected == "❤️ 收藏追蹤":
    industry_filter = None  # 忽略產業篩選
    fav_syms = list(st.session_state.favorites)

    if not fav_syms:
        st.info("目前沒有收藏股票。從其他模式點擊 ❤️ 加入收藏吧！")
        display_results = []
    else:
        st.subheader(f"收藏清單（{len(fav_syms)} 檔）")

        # 每次進入收藏頁，先清空舊的 results_data，避免累積舊資料
        st.session_state.results_data = []

        # 按鈕更新報價
        if st.button("🔄 立即更新收藏報價", type="primary"):
            with st.status("更新收藏股中...", expanded=True) as status:
                temp_results = []
                for sym in fav_syms:
                    df_data = fetch_price(sym)
                    stock_name = full_db.get(sym, {}).get("name", sym)
                    analysis_result = run_analysis(sym, stock_name, df_data, analysis_cfg, is_manual=True)
                    if analysis_result:
                        temp_results.append(analysis_result)
                    else:
                        # 防呆基本顯示
                        if not df_data.empty:
                            current_price = float(df_data['Close'].iloc[-1])
                            ma20 = float(df_data['Close'].rolling(20).mean().iloc[-1]) if len(df_data) >= 20 else None
                            ma60 = float(df_data['Close'].rolling(60).mean().iloc[-1]) if len(df_data) >= 60 else None
                            trend = '🔴 多頭排列' if (ma20 is not None and ma60 is not None and ma20 > ma60) else '🟢 空頭排列'
                            analysis_result = {
                                "收藏": True,
                                "sid": sym,
                                "名稱": stock_name,
                                "現價": round(current_price, 2),
                                "趨勢": trend,
                                "MA20": round(ma20, 2) if ma20 is not None else None,
                                "MA60": round(ma60, 2) if ma60 is not None else None,
                                "符合訊號": "🔍 觀察中",
                                "Yahoo": f"https://tw.stock.yahoo.com/quote/{sym.split('.')[0]}",
                                "df": df_data.copy() if not df_data.empty else pd.DataFrame(),
                                "lines": None
                            }
                        temp_results.append(analysis_result)
                st.session_state.results_data = temp_results
                status.update(label=f"更新完成！共處理 {len(temp_results)} 檔", state="complete")
            st.success("報價更新完成，畫面已刷新")
            st.rerun()  # 更新後 rerun，讓 K線與表格即時顯示最新

        # 產生 display_results（直接從 fav_syms 重新分析或使用快取）
        display_results = []
        seen_sids = set()
        for sym in fav_syms:
            if sym in seen_sids:
                continue
            df_data = fetch_price(sym)
            stock_name = full_db.get(sym, {}).get("name", sym)
            analysis_result = run_analysis(sym, stock_name, df_data, analysis_cfg, is_manual=True)
            if analysis_result:
                display_results.append(analysis_result)
            else:
                # 防呆基本顯示
                if not df_data.empty:
                    current_price = float(df_data['Close'].iloc[-1])
                    ma20 = float(df_data['Close'].rolling(20).mean().iloc[-1]) if len(df_data) >= 20 else None
                    ma60 = float(df_data['Close'].rolling(60).mean().iloc[-1]) if len(df_data) >= 60 else None
                    trend = '🔴 多頭排列' if (ma20 is not None and ma60 is not None and ma20 > ma60) else '🟢 空頭排列'
                    display_result = {
                        "收藏": True,
                        "sid": sym,
                        "名稱": stock_name,
                        "現價": round(current_price, 2),
                        "趨勢": trend,
                        "MA20": round(ma20, 2) if ma20 is not None else None,
                        "MA60": round(ma60, 2) if ma60 is not None else None,
                        "符合訊號": "🔍 觀察中",
                        "Yahoo": f"https://tw.stock.yahoo.com/quote/{sym.split('.')[0]}",
                        "df": df_data.copy(),
                        "lines": None
                    }
                    display_results.append(display_result)
            seen_sids.add(sym)

# ────────────────────────────────────────────────
# 只在收藏追蹤模式才強制補收藏（其他頁面不補）
# ────────────────────────────────────────────────
if mode_selected == "❤️ 收藏追蹤":
    # 已經在上面處理，不需再補
    pass
# 其他模式不補收藏（符合你「不要其他頁也顯示收藏」）

# ────────────────────────────────────────────────
# 結果呈現區塊（所有模式共用）
# ────────────────────────────────────────────────
if display_results:
    table_records = []
    for item in display_results:
        is_favorited = item["sid"] in st.session_state.favorites
        table_records.append({
            "收藏": is_favorited,
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

    is_favorite_mode = (mode_selected == "❤️ 收藏追蹤")

    # 收藏欄位設定：所有頁面都可見可點，但邏輯上限制
    column_config = {
        "收藏": st.column_config.CheckboxColumn(
            "❤️ 收藏",
            width="small",
            disabled=False  # 表面不禁用，讓未收藏的可以點
        ),
        "Yahoo": st.column_config.LinkColumn("Yahoo", display_text="🔍 Yahoo", width="medium"),
        "現價": st.column_config.NumberColumn(format="%.2f"),
        "MA20": st.column_config.NumberColumn(format="%.2f"),
        "MA60": st.column_config.NumberColumn(format="%.2f"),
    }

    edited_table = st.data_editor(
        df_table,
        column_config=column_config,
        hide_index=True,
        use_container_width=True,
        key=f"editor_{mode_selected}_{industry_filter or 'all'}"
    )

    # 從表格取得使用者勾選的結果
    new_checked = set(edited_table[edited_table["收藏"] == True]["代碼"].tolist())

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("💾 儲存收藏變更", type="primary", use_container_width=True, key=f"save_fav_{mode_selected}"):
            current_favs = st.session_state.favorites.copy()
            updated = False

            if is_favorite_mode:
                # 收藏頁面：允許完整更新（新增 + 移除）
                if new_checked != current_favs:
                    st.session_state.favorites = new_checked
                    updated = True
                    st.success(f"收藏清單已更新！目前總共 {len(new_checked)} 檔")
            else:
                # 其他頁面：只允許新增，不允許移除
                to_add = new_checked - current_favs
                if to_add:
                    st.session_state.favorites.update(to_add)
                    updated = True
                    st.success(f"已新增 {len(to_add)} 檔到收藏清單！")
                else:
                    st.info("沒有新的股票被勾選加入收藏")

            if updated:
                st.rerun()  # 更新後刷新畫面，讓勾選狀態即時顯示

    with col2:
        pending_add = len(new_checked - st.session_state.favorites)
        if pending_add > 0 and not is_favorite_mode:
            st.caption(f"待新增收藏：{pending_add} 檔（按上方按鈕儲存）")
        elif pending_add == 0 and not is_favorite_mode:
            st.caption("目前無新收藏變更（已收藏的無法在此取消）")

    st.divider()
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

            if item.get("lines"):
                sh, ih, sl, il, x_vals = item["lines"]
                x_dates = plot_df.index[-len(x_vals):]
                fig.add_trace(go.Scatter(
                    x=x_dates, y=sh * x_vals + ih,
                    mode='lines', line=dict(color='red', dash='dash', width=2),
                    name='壓力線'
                ))
                fig.add_trace(go.Scatter(
                    x=x_dates, y=sl * x_vals + il,
                    mode='lines', line=dict(color='lime', dash='dash', width=2),
                    name='支撐線'
                ))

            try:
                theme_setting = st.get_option("theme.base")
                chart_template = "plotly_dark" if theme_setting == "dark" else "plotly_white"
            except:
                chart_template = "plotly_white"

            fig.update_layout(
                height=480,
                margin=dict(l=10, r=10, t=30, b=10),
                xaxis_rangeslider_visible=False,
                template=chart_template
            )

            st.plotly_chart(fig, use_container_width=True, key=f"chart_{item['sid']}")

else:
    if mode_selected == "⚖️ 條件篩選":
        st.info("尚未執行篩選，請設定條件後按「開始條件篩選」")
    elif mode_selected == "❤️ 收藏追蹤":
        st.info("收藏清單為空，快去其他模式加入喜歡的股票吧！")
    else:
        st.caption("目前無符合條件標的，或尚未執行分析")

# 頁尾資訊（保持不變）
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
