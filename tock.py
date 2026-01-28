import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from scipy.stats import linregress
import os, json, time

# ==========================================
# 1. 系統初始化
# ==========================================
st.set_page_config(page_title="台股 Pro CL3", layout="wide")

if 'favorites' not in st.session_state: st.session_state.favorites = set()
if 'results_data' not in st.session_state: st.session_state.results_data = []
if 'last_config_key' not in st.session_state: st.session_state.last_config_key = ""
if 'm_state' not in st.session_state: st.session_state.m_state = ''

# ==========================================
# 2. 資料庫讀取函式
# ==========================================
@st.cache_data(ttl=3600)
def load_db():
    f = "taiwan_full_market.json"
    if os.path.exists(f):
        try:
            with open(f,"r",encoding="utf-8") as file:
                return json.load(file)
        except: pass
    # 預設示範資料
    return {"2330.TW":"台積電","2603.TW":"長榮","2303.TW":"聯電","2412.TW":"中華電"}

# ==========================================
# 3. 訊號計算函式
# ==========================================
def calc_signals(df, config):
    signals = []
    try:
        lb = min(config.get('p_lookback',15), len(df))
        x = np.arange(lb)
        h,l = df['High'].iloc[-lb:].values, df['Low'].iloc[-lb:].values
        sh,ih,_,_,_ = linregress(x,h)
        sl,il,_,_,_ = linregress(x,l)
        if sh<-0.001 and sl>0.001: signals.append("📐三角收斂")
        if abs(sh)<0.03 and abs(sl)<0.03: signals.append("📦箱型整理")
        v_slice = df['Volume'].iloc[-21:-1] if len(df)>1 else []
        v_avg = float(v_slice.mean()) if len(v_slice)>0 else 0
        v_last = df['Volume'].iloc[-1]
        if v_avg>0 and v_last>v_avg*1.8: signals.append("🚀今日爆量")
    except:
        sh=sl=ih=il=x=None
    return signals, (sh,ih,sl,il,x)

# ==========================================
# 4. 分析函式
# ==========================================
def run_analysis(sid,name,df,config,is_manual=False):
    if df is None or df.empty: return None
    df = df.copy().dropna()
    if len(df)<5: return None
    c = float(df['Close'].iloc[-1])
    signals, lines = calc_signals(df, config)
    should_show = is_manual
    if not is_manual:
        hit_match = any([
            config.get('check_tri') and '📐' in ''.join(signals),
            config.get('check_box') and '📦' in ''.join(signals),
            config.get('check_vol') and '🚀' in ''.join(signals)
        ])
        should_show = hit_match
        try:
            ma_m = df['Close'].rolling(config.get('p_ma_m',20)).mean().iloc[-1]
            if config.get('f_ma_filter') and c<ma_m: should_show=False
        except: pass
    if not should_show: return None
    return {
        "收藏": sid in st.session_state.favorites,
        "sid": sid,
        "名稱": name,
        "現價": round(c,2),
        "符合訊號": ', '.join(signals) if signals else "🔍觀察中",
        "Yahoo": f"https://tw.stock.yahoo.com/quote/{sid.split('.')[0]}.TW",
        "df": df,
        "lines": lines
    }

# ==========================================
# 5. Sidebar 控制面板
# ==========================================
full_db = load_db()
with st.sidebar:
    st.title("🛡️ 戰術控制台")
    app_mode = st.radio("模式切換",["⚡ 自動掃描","🔍 手動模式","❤️ 追蹤清單"])
    if st.session_state.m_state != app_mode:
        st.session_state.results_data=[]
        st.session_state.m_state=app_mode
        st.rerun()

    if app_mode!="❤️ 追蹤清單":
        st.divider()
        st.subheader("📡 訊號監控")
        check_tri = st.checkbox("📐 三角收斂",True)
        check_box = st.checkbox("📦 箱型整理",True)
        check_vol = st.checkbox("🚀 今日爆量",True)
        with st.expander("🛠️ 參數設定",expanded=True):
            p_ma_m = st.number_input("均線(MA)",value=20)
            p_lookback = st.slider("形態回溯天數",10,30,15)
            f_ma_filter = st.checkbox("限 MA20 之上(自動)",True)
            min_v = st.number_input("成交量門檻 (張)",value=500)
            scan_limit = st.slider("掃描上限",50,500,100)
            config = locals()
    else:
        config={"p_ma_m":20,"p_lookback":15}

    current_key=f"{app_mode}-{config.get('scan_limit',0)}"
    trigger_scan=(app_mode=="⚡ 自動掃描" and current_key!=st.session_state.last_config_key)
    if trigger_scan: st.session_state.last_config_key=current_key

# ==========================================
# 6. 主頁面邏輯
# ==========================================
st.title(f"📍 {app_mode}")

# --- 手動模式 ---
if app_mode=="🔍 手動模式":
    st.subheader("🔹 個股搜尋")
    c1,c2=st.columns([4,1])
    with c1: s_input=st.text_input("輸入代碼 (例如:2330,2603)",key="min")
    with c2: manual_exec=st.button("🔍 執行搜尋",type="primary",use_container_width=True)

    st.markdown("---")
    st.subheader("🔹 條件篩選市場股票")
    with st.expander("📊 篩選條件",expanded=True):
        sel_tri=st.checkbox("📐 三角收斂",True)
        sel_box=st.checkbox("📦 箱型整理",True)
        sel_vol=st.checkbox("🚀 今日爆量",True)
        sel_ma_filter=st.checkbox("限 MA20 之上",True)
        sel_limit=st.slider("掃描前幾檔",50,500,100)

    if manual_exec:
        temp=[]
        codes=[]
        if s_input:
            codes=[c.strip().upper()+".TW" if "." not in c else c.strip().upper() for c in s_input.replace("，",",").split(",") if c.strip()]
        else:
            codes=list(full_db.keys())[:sel_limit]
        with st.spinner("抓取資料中..."):
            data=yf.download(codes,period="6mo",group_by='ticker',progress=False)
            for s in codes:
                df=data[s] if len(codes)>1 else data
                if not df.empty:
                    cfg_tmp={'p_lookback':p_lookback,'check_tri':sel_tri,'check_box':sel_box,'check_vol':sel_vol,'f_ma_filter':sel_ma_filter,'p_ma_m':p_ma_m}
                    res=run_analysis(s,full_db.get(s,s.split('.')[0]),df,cfg_tmp,is_manual=True)
                    if res: temp.append(res)
        st.session_state.results_data=temp

# --- 自動掃描 ---
elif app_mode=="⚡ 自動掃描" and (trigger_scan or not st.session_state.results_data):
    all_codes=list(full_db.keys())[:config.get("scan_limit",50)]
    temp=[]
    with st.status("📡 市場掃描中...") as status:
        data=yf.download(all_codes,period="6mo",group_by='ticker',progress=False)
        for s in all_codes:
            df=data[s] if len(all_codes)>1 else data
            if not df.empty:
                res=run_analysis(s,full_db.get(s,s.split('.')[0]),df,config)
                if res: temp.append(res)
    st.session_state.results_data=temp
    status.update(label="✅ 掃描完成",state="complete")

# --- 追蹤清單 ---
elif app_mode=="❤️ 追蹤清單" and not st.session_state.results_data:
    if st.session_state.favorites:
        temp=[]
        with st.spinner("更新追蹤清單..."):
            for s in st.session_state.favorites:
                df=yf.download(s,period="6mo",progress=False)
                if not df.empty:
                    res=run_analysis(s,full_db.get(s,s),df,config,is_manual=True)
                    if res: temp.append(res)
        st.session_state.results_data=temp

# ==========================================
# 7. 渲染表格與 K 線
# ==========================================
if st.session_state.results_data:
    d_data=st.session_state.results_data
    if app_mode=="❤️ 追蹤清單": d_data=[r for r in d_data if r['sid'] in st.session_state.favorites]

    t_df=pd.DataFrame([{"收藏":r["收藏"],"代碼":r["sid"],"名稱":r["名稱"],"現價":r["現價"],"符合訊號":r["符合訊號"]} for r in d_data])
    edit=st.data_editor(t_df,column_config={"收藏":st.column_config.CheckboxColumn("❤️")},use_container_width=True,hide_index=True,key=f"ed_{app_mode}")

    new_favs=set(edit[edit["收藏"]==True]["代碼"])
    if new_favs != st.session_state.favorites:
        st.session_state.favorites=new_favs
        st.rerun()

    for r in d_data:
        with st.expander(f"📈 {r['sid']} {r['名稱']} | {r['符合訊號']}",expanded=True):
            df_t,(sh,ih,sl,il,x)=r["df"].iloc[-60:],r["lines"]
            fig=go.Figure(data=[go.Candlestick(x=df_t.index,open=df_t["Open"],high=df_t["High"],low=df_t["Low"],close=df_t["Close"])]
            )
            if sh is not None and x is not None:
                fig.add_scatter(x=df_t.index[-len(x):],y=sh*x+ih,mode='lines',line=dict(color='red',dash='dash'),name='壓力')
                fig.add_scatter(x=df_t.index[-len(x):],y=sl*x+il,mode='lines',line=dict(color='green',dash='dash'),name='支撐')
            fig.update_layout(height=400,xaxis_rangeslider_visible=False,margin=dict(l=10,r=10,t=10,b=10))
            st.plotly_chart(fig,use_container_width=True,key=f"k_{r['sid']}_{app_mode}")
else:
    st.info("尚無數據。手動模式請輸入代碼或按條件篩選。")
