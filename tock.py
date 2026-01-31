# -*- coding: utf-8 -*-
"""
台股 Pro 旗艦戰情室 - 完整本地版（Streamlit UI）
專案目標：提供台股全市場快速掃描、技術分析、可視化工具
核心特色：
  • 本地快取價格資料（yfinance + pickle）
  • FinMind API 自動更新股票清單與產業分類
  • 四種使用模式：手動 / 條件篩選 / 自動掃描 / 收藏追蹤
  • 支援三角收斂、箱型整理、爆量、MA排列等訊號
  • Plotly K線 + 壓力/支撐趨勢線
  • 即時收藏同步（data_editor checkbox）
  • 批次更新進度條、錯誤處理、使用者提示
使用前建議：
1. 第一次執行 → 側邊欄「更新股票清單 JSON (FinMind)」
2. 再執行「更新全市場價格快取」（約 15–40 分鐘，視網路而定）
3. 之後日常使用皆從本地快取讀取，速度極快
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

# 忽略部分常見警告，讓畫面更乾淨
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
#          FinMind API 更新股票清單
# ────────────────────────────────────────────────
def update_stock_json_from_finmind():
    """從 FinMind 抓取最新台股清單並儲存為 JSON"""
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {"dataset": "TaiwanStockInfo"}
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        result = r.json()
        if not result.get("success", True):
            st.error(f"FinMind API 回應失敗：{result.get('msg', '未知錯誤')}")
            return None, 0
        data = result.get("data", [])
        if not data:
            st.warning("FinMind 回傳資料為空")
            return None, 0
        stock_dict = {}
        for row in data:
            sid = row.get("stock_id")
            if sid and sid.isdigit():
                stock_dict[f"{sid}.TW"] = {
                    "name": row.get("stock_name", "").strip(),
                    "category": row.get("industry_category", "未知").strip(),
                    "type": row.get("type", "").strip()
                }
        if not stock_dict:
            st.warning("沒有有效股票資料")
            return None, 0
        with open(STOCK_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(stock_dict, f, ensure_ascii=False, indent=2)
        st.success(f"成功更新 {len(stock_dict)} 檔股票清單 → {STOCK_JSON_PATH}")
        return stock_dict, len(stock_dict)
    except requests.exceptions.RequestException as re:
        st.error(f"網路請求失敗：{str(re)}")
        return None, 0
    except Exception as e:
        st.error(f"更新股票清單時發生異常：{str(e)}")
        traceback.print_exc(file=sys.stderr)
        return None, 0

# ────────────────────────────────────────────────
#          載入股票資料庫（含 fallback）
# ────────────────────────────────────────────────
def load_stock_database():
    """載入 taiwan_full_market.json，支援多種格式並標準化"""
    if STOCK_JSON_PATH.exists():
        try:
            with open(STOCK_JSON_PATH, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            db = {}
            for symbol, val in raw.items():
                if isinstance(val, dict):
                    name = val.get("name", symbol)
                    cat = val.get("category", "未知")
                elif isinstance(val, str):
                    name = val
                    cat = "未知"
                else:
                    name = str(val)
                    cat = "未知"
                db[symbol] = {"name": name.strip(), "category": cat.strip()}
            if len(db) >= 20:
                st.info(f"股票清單載入成功：{len(db)} 檔")
                return db
            else:
                st.warning(f"JSON 資料量過少 ({len(db)})，使用 fallback")
        except json.JSONDecodeError:
            st.error("JSON 格式錯誤")
        except Exception as e:
            st.error(f"讀取 JSON 失敗：{str(e)}")
    # fallback 小資料
    fallback_db = {
        "2330.TW": {"name": "台積電", "category": "半導體"},
        "2454.TW": {"name": "聯發科", "category": "半導體"},
        "2317.TW": {"name": "鴻海", "category": "電子"},
        "2603.TW": {"name": "長榮", "category": "航運"},
        "2615.TW": {"name": "萬海", "category": "航運"},
        "1216.TW": {"name": "統一", "category": "食品"},
        "1101.TW": {"name": "台泥", "category": "水泥"},
        "2303.TW": {"name": "聯電", "category": "半導體"},
        "3034.TW": {"name": "聯詠", "category": "半導體"},
        "3443.TW": {"name": "創意", "category": "半導體"},
    }
    return fallback_db

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
        st.warning(f"無法下載 {symbol}：{str(e)}")
        return pd.DataFrame()

# ────────────────────────────────────────────────
#               核心技術分析邏輯
# ────────────────────────────────────────────────
def run_analysis(sid: str, name: str, df: pd.DataFrame, cfg: dict, is_manual: bool = False) -> dict | None:
    if df.empty or 'Close' not in df.columns or len(df) < 60:
        return None
    try:
        current_price = float(df['Close'].iloc[-1])
        ma20 = float(df['Close'].rolling(20).mean().iloc[-1])
        ma60 = float(df['Close'].rolling(60).mean().iloc[-1])
        trend = '🔴 多頭排列' if ma20 > ma60 else '🟢 空頭排列'
        lb = cfg.get("p_lookback", 15)
        if len(df) < lb:
            return None
        x = np.arange(lb)
        highs = df["High"].iloc[-lb:].values.flatten()
        lows  = df["Low"].iloc[-lb:].values.flatten()
        slope_h, int_h, _, _, _ = linregress(x, highs)
        slope_l, int_l, _, _, _ = linregress(x, lows)
        signals = []
        if slope_h < -0.001 and slope_l > 0.001:
            signals.append("📐三角收斂")
        if abs(slope_h) < 0.03 and abs(slope_l) < 0.03:
            signals.append("📦箱型整理")
        if len(df) >= 6 and cfg.get("check_vol", True):
            vol_today = float(df["Volume"].iloc[-1])
            vol_avg5 = float(df["Volume"].iloc[-6:-1].mean())
            if vol_today > vol_avg5 * 1.5:
                signals.append("🚀今日爆量")
        show = is_manual
        if not is_manual:
            show = any([
                cfg["check_tri"] and "📐" in "".join(signals),
                cfg["check_box"] and "📦" in "".join(signals),
                cfg["check_vol"] and "🚀" in "".join(signals)
            ])
            if cfg["f_ma_filter"] and current_price < ma20:
                show = False
            if current_price < cfg["min_price"]:
                show = False
        if show:
            return {
                "收藏": sid in st.session_state.favorites,
                "sid": sid,
                "名稱": name,
                "現價": round(current_price, 2),
                "趨勢": trend,
                "MA20": round(ma20, 2),
                "MA60": round(ma60, 2),
                "符合訊號": ", ".join(signals) if signals else "🔍 觀察中",
                "Yahoo": f"https://tw.stock.yahoo.com/quote/{sid.split('.')[0]}",
                "df": df.copy(),
                "lines": (slope_h, int_h, slope_l, int_l, x)
            }
    except Exception:
        # 單一股票出錯不影響整體
        pass
    return None

# ────────────────────────────────────────────────
#               側邊欄控制面板
# ────────────────────────────────────────────────
st.sidebar.title("🛡️ 台股 Pro 戰術控制台")
st.sidebar.markdown(f"**目前股票數量**：{len(full_db)} 檔")

mode = st.sidebar.radio(
    "選擇分析模式",
    options=["🔍 手動查詢", "⚖️ 條件篩選", "⚡ 自動掃描", "❤️ 收藏追蹤"],
    index=0,
    key="mode_selector"
)

if st.session_state.last_mode != mode:
    st.session_state.results_data = []
    st.session_state.last_mode = mode

cfg = {
    "p_lookback": 15,
    "min_price": 0.0,
    "check_tri": True,
    "check_box": True,
    "check_vol": True,
    "f_ma_filter": False,
    "scan_limit": 200
}

industry = st.sidebar.selectbox(
    "篩選產業類別",
    options=[
        "全部", "半導體", "光電", "電子零組件", "電腦週邊", "通訊網路",
        "塑膠", "紡織", "鋼鐵", "食品", "金融業", "航運", "生技醫療",
        "水泥", "玻璃陶瓷", "其他"
    ],
    index=1
)

if mode in ["⚖️ 條件篩選", "⚡ 自動掃描"]:
    st.sidebar.divider()
    st.sidebar.subheader("技術訊號篩選")
    c1, c2 = st.sidebar.columns(2)
    with c1:
        cfg["check_tri"] = st.checkbox("📐 三角收斂", value=True)
        cfg["check_box"] = st.checkbox("📦 箱型整理", value=True)
    with c2:
        cfg["check_vol"] = st.checkbox("🚀 今日爆量", value=True)
        cfg["f_ma_filter"] = st.checkbox("限站上 MA20", value=False)
    cfg["min_price"] = st.sidebar.slider("最低股價 (元)", 0.0, 1000.0, 0.0, 1.0)
    cfg["scan_limit"] = st.sidebar.slider("掃描上限檔數", 50, 2000, 200, 50)

st.sidebar.divider()
st.sidebar.subheader("資料維護")

if st.sidebar.button("🔄 更新全市場價格快取", type="primary"):
    with st.status("正在批次更新價格資料（請耐心等待）...", expanded=True) as status:
        symbols = list(full_db.keys())
        progress = st.progress(0)
        batch_size = 80
        updated = 0
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i+batch_size]
            try:
                data = yf.download(batch, period="1y", group_by="ticker", threads=True, auto_adjust=True)
                for sym in batch:
                    if sym in data:
                        price_cache[sym] = data[sym].copy()
                        updated += 1
            except Exception as e:
                st.warning(f"批次 {i//batch_size+1} 失敗：{str(e)}")
            progress.progress(min((i + batch_size) / len(symbols), 1.0))
            time.sleep(1.1)
        save_price_cache(price_cache)
        st.session_state.last_cache_update = datetime.now()
        status.update(label=f"價格更新完成（{updated} 檔）", state="complete")

if st.sidebar.button("🔄 更新股票清單 (FinMind)"):
    update_stock_json_from_finmind()
    st.session_state.full_db = load_stock_database()
    st.rerun()

if st.session_state.last_cache_update:
    st.sidebar.caption(f"價格最後更新：{st.session_state.last_cache_update.strftime('%Y-%m-%d %H:%M')}")

# ────────────────────────────────────────────────
#               主畫面邏輯
# ────────────────────────────────────────────────
st.title(f"📈 {mode}")

symbol_list = list(full_db.keys())
if industry != "全部":
    symbol_list = [
        s for s in symbol_list
        if industry in full_db.get(s, {}).get("category", "")
    ]

if mode == "🔍 手動查詢":
    codes = st.text_input("輸入股票代碼（多檔用半形逗號分隔）", placeholder="2330,2454,2603,1216")
    if codes:
        lst = [c.strip().upper() for c in codes.replace("，",",").split(",") if c.strip()]
        res = []
        with st.spinner("分析中..."):
            for c in lst:
                sym = c if '.' in c else f"{c}.TW"
                df = fetch_price(sym)
                name = full_db.get(sym, {}).get("name", c)
                r = run_analysis(sym, name, df, cfg, True)
                if r:
                    res.append(r)
        st.session_state.results_data = res

elif mode == "⚖️ 條件篩選":
    if st.button("🚀 開始條件篩選全市場", type="primary", use_container_width=True):
        scan_symbols = symbol_list[:cfg["scan_limit"]]
        res = []
        with st.status(f"掃描 {len(scan_symbols)} 檔 {industry} 類股...", expanded=True) as stt:
            prog = st.progress(0)
            for idx, sym in enumerate(scan_symbols):
                df = fetch_price(sym)
                name = full_db.get(sym, {}).get("name", "未知")
                r = run_analysis(sym, name, df, cfg, False)
                if r:
                    res.append(r)
                prog.progress((idx+1)/len(scan_symbols))
                if (idx+1) % 40 == 0:
                    time.sleep(0.03)
            st.session_state.results_data = res
            stt.update(label=f"篩選完成，找到 {len(res)} 檔符合條件", state="complete")

elif mode == "⚡ 自動掃描":
    st_autorefresh(interval=60000, key="auto_refresh")
    st.info("自動掃描模式已啟動，每 60 秒更新一次（限制前 150 檔）")
    scan_symbols = symbol_list[:150]
    res = []
    with st.spinner("正在自動掃描..."):
        for sym in scan_symbols:
            df = fetch_price(sym)
            name = full_db.get(sym, {}).get("name", "未知")
            r = run_analysis(sym, name, df, cfg, False)
            if r:
                res.append(r)
    st.session_state.results_data = res

elif mode == "❤️ 收藏追蹤":
    if not st.session_state.favorites:
        st.info("目前尚無收藏股票，請從其他模式加入")
    else:
        if st.button("🔄 更新所有收藏股最新資料", type="primary"):
            res = []
            with st.status("更新收藏清單中..."):
                for sym in st.session_state.favorites:
                    df = fetch_price(sym)
                    name = full_db.get(sym, {}).get("name", sym)
                    r = run_analysis(sym, name, df, cfg, True)
                    if r:
                        res.append(r)
            st.session_state.results_data = res
            st.success(f"更新完成，共 {len(res)} 檔有效資料")

# ────────────────────────────────────────────────
#               結果呈現
# ────────────────────────────────────────────────
results = st.session_state.results_data
if mode == "❤️ 收藏追蹤":
    results = [r for r in results if r["sid"] in st.session_state.favorites]

if results:
    # 表格
    rows = [{
        "收藏": r["收藏"],
        "代碼": r["sid"],
        "名稱": r["名稱"],
        "現價": r["現價"],
        "趨勢": r["趨勢"],
        "MA20": r["MA20"],
        "MA60": r["MA60"],
        "訊號": r["符合訊號"],
        "Yahoo": r["Yahoo"]
    } for r in results]

    df_show = pd.DataFrame(rows)

    edited = st.data_editor(
        df_show,
        column_config={
            "收藏": st.column_config.CheckboxColumn("❤️ 收藏", width="small"),
            "Yahoo": st.column_config.LinkColumn("Yahoo", display_text="🔍 查看", width="medium"),
            "現價": st.column_config.NumberColumn(format="%.2f"),
            "MA20": st.column_config.NumberColumn(format="%.2f"),
            "MA60": st.column_config.NumberColumn(format="%.2f"),
        },
        hide_index=True,
        use_container_width=True,
        key=f"table_{mode}_{industry}"
    )

    new_favs = set(edited[edited["收藏"] == True]["代碼"].tolist())
    if new_favs != st.session_state.favorites:
        st.session_state.favorites = new_favs
        st.rerun()

    st.divider()
    st.subheader("個股 K 線與壓力/支撐趨勢線")

    for r in results:
        with st.expander(f"{r['sid']}  {r['名稱']}  |  {r['訊號']}  |  {r['趨勢']}"):
            cols = st.columns(3)
            cols[0].metric("現價", f"{r['現價']:.2f} 元")
            cols[1].metric("MA20", f"{r['MA20']:.2f}")
            cols[2].metric("趨勢", r["趨勢"])

            plot_df = r["df"].tail(60).copy()
            fig = go.Figure()

            fig.add_trace(go.Candlestick(
                x=plot_df.index,
                open=plot_df['Open'], high=plot_df['High'],
                low=plot_df['Low'], close=plot_df['Close'],
                name="K線",
                increasing_line_color="#ef5350",
                decreasing_line_color="#26a69a"
            ))

            sh, ih, sl, il, xv = r["lines"]
            xd = plot_df.index[-len(xv):]

            fig.add_trace(go.Scatter(x=xd, y=sh*xv + ih,
                                     mode='lines', line=dict(color='red', dash='dash', width=2),
                                     name='壓力線'))
            fig.add_trace(go.Scatter(x=xd, y=sl*xv + il,
                                     mode='lines', line=dict(color='lime', dash='dash', width=2),
                                     name='支撐線'))

            template = "plotly_dark" if st.get_option("theme.base") == "dark" else "plotly_white"

            fig.update_layout(
                height=480,
                margin=dict(l=10, r=10, t=30, b=10),
                xaxis_rangeslider_visible=False,
                template=template
            )
            st.plotly_chart(fig, use_container_width=True, key=f"chart_{r['sid']}")

else:
    if mode == "⚖️ 條件篩選":
        st.info("請設定條件後按「開始條件篩選全市場」")
    elif mode == "❤️ 收藏追蹤":
        st.info("收藏清單為空，請先加入感興趣的股票")
    else:
        st.caption("目前無資料，請執行分析或加入收藏")

# ────────────────────────────────────────────────
#               頁尾資訊
# ────────────────────────────────────────────────
st.markdown("---")
st.caption("台股 Pro 旗艦戰情室 | 資料來源：yfinance + FinMind API | 僅供學習參考")
if st.session_state.last_cache_update:
    st.caption(f"價格資料最後更新：{st.session_state.last_cache_update.strftime('%Y-%m-%d %H:%M')}")
else:
    st.caption("尚未更新價格快取，請點擊側邊欄按鈕更新")
st.caption("投資有風險，請謹慎評估，祝交易順利！📈")
