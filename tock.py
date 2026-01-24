import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.stats import linregress
from streamlit_autorefresh import st_autorefresh

# --- [ 1. 介面樣式：還原截圖色彩繽紛感 ] ---
st.set_page_config(page_title="台股 Pro-X 形態大師", layout="wide")
st.markdown("""
    <style>
    /* 左側側邊欄標籤樣式 */
    .tag-tri-side { background-color: #e8f8f5; color: #1abc9c; padding: 2px 8px; border-radius: 4px; font-size: 13px; border: 1px solid #1abc9c; font-weight: bold; }
    .tag-rev-side { background-color: #fdf2f2; color: #e74c3c; padding: 2px 8px; border-radius: 4px; font-size: 13px; border: 1px solid #e74c3c; font-weight: bold; }
    .tag-vol-side { background-color: #eef2ff; color: #4f46e5; padding: 2px 8px; border-radius: 4px; font-size: 13px; border: 1px solid #4f46e5; font-weight: bold; }
    .tag-box-side { background-color: #f0fdf4; color: #16a34a; padding: 2px 8px; border-radius: 4px; font-size: 13px; border: 1px solid #16a34a; font-weight: bold; }
    
    /* 右側結果卡片 */
    .stock-card { background: white; padding: 15px; border-radius: 12px; border: 1px solid #e5e7eb; margin-bottom: 10px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }
    .badge { color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 12px; margin-left: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- [ 2. 核心分析引擎 ] ---
def _analyze_core(df, m1, m2, m3, m4):
    try:
        d = df.tail(30).copy()
        x = np.arange(len(d))
        h, l, c, v = d['High'].values.flatten(), d['Low'].values.flatten(), d['Close'].values.flatten(), d['Volume'].values.flatten()
        sh, ih, _, _, _ = linregress(x, h)
        sl, il, _, _, _ = linregress(x, l)
        
        labels = []
        is_tri = (sh < -0.0015 and sl > 0.0015)
        is_box = (abs(sh) < 0.0015 and abs(sl) < 0.0015)
        is_rev = (c[-1] > (sh*29+ih) or c[-1] < (sl*29+il))
        is_vol = (v[-1] > v[-6:-1].mean() * 1.1)

        if m1 and is_tri: labels.append("📐 三角形態")
        if m2 and is_box: labels.append("📦 旗箱系")
        if m3 and is_rev: labels.append("🔄 反轉系")
        if m4 and is_vol: labels.append("🚀 爆量突破")
        
        return labels, (sh, ih, sl, il), (is_tri or is_box or is_rev or is_vol)
    except: return [], (0,0,0,0), False

# --- [ 3. 左側：色彩繽紛決策中心 ] ---
with st.sidebar:
    st.markdown("### 🎯 決策中心")
    st.markdown('<div style="background-color:#dcfce7; color:#166534; padding:10px; border-radius:8px; text-align:center; font-weight:bold; margin-bottom:15px;">📡 系統自動值勤中</div>', unsafe_allow_html=True)
    st_autorefresh(interval=600000, key="refresh")

    with st.form("scan_form"):
        st.subheader("🔍 標的快查")
        target_sid = st.text_input("輸入股票代碼", value="2330")
        
        st.divider()
        st.subheader("🧬 形態偵測設定")
        # 色彩繽紛的 Checkbox 區域
        c1, c2 = st.columns([0.6, 0.4])
        with c1: m1 = st.checkbox("三角系", value=True)
        with c2: st.markdown('<span class="tag-tri-side">△ 攻學/收斂</span>', unsafe_allow_html=True)
        
        c1, c2 = st.columns([0.6, 0.4])
        with c1: m2 = st.checkbox("旗箱系", value=True)
        with c2: st.markdown('<span class="tag-box-side">📦 矩形/旗形</span>', unsafe_allow_html=True)
        
        c1, c2 = st.columns([0.6, 0.4])
        with c1: m3 = st.checkbox("反轉系", value=False)
        with c2: st.markdown('<span class="tag-rev-side">↺ 反轉1格系</span>', unsafe_allow_html=True)
        
        c1, c2 = st.columns([0.6, 0.4])
        with c1: m4 = st.checkbox("爆量突破", value=True)
        with c2: st.markdown('<span class="tag-vol-side">🚀 爆量系</span>', unsafe_allow_html=True)

        st.divider()
        st.subheader("⚙️ 進階過濾")
        min_v = st.number_input("最低張數", value=500)
        ma_on = st.toggle("站上 20MA", value=True)
        
        submit = st.form_submit_button("🚀 開始深度掃描", use_container_width=True)

    # 側邊欄下方的小圖表預覽
    st.markdown("---")
    st.write("📊 即時預覽")
    try:
        side_df = yf.download(f"{target_sid}.TW", period="40d", progress=False)
        fig_side = go.Figure(data=[go.Candlestick(x=side_df.index, open=side_df['Open'], high=side_df['High'], low=side_df['Low'], close=side_df['Close'])])
        fig_side.update_layout(height=180, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False, template="plotly_white")
        st.plotly_chart(fig_side, use_container_width=True, config={'displayModeBar': False})
    except: pass

# --- [ 4. 主畫面：完整結果輸出 ] ---
st.header("📈 形態大師分析報告")

# 這裡以熱門股為範例，實戰可接入全市場列表
watch_list = [f"{target_sid}.TW", "2317.TW", "2454.TW", "2603.TW", "2303.TW", "2609.TW", "3037.TW"]
results = []

with st.status("🔍 引擎正在全力掃描中...", expanded=True) as status:
    for sid in watch_list:
        try:
            df = yf.download(sid, period="100d", progress=False)
            if df.empty: continue
            
            labels, lines, is_hit = _analyze_core(df, m1, m2, m3, m4)
            price = float(df['Close'].iloc[-1])
            vol = int(df['Volume'].iloc[-1]/1000)
            
            if is_hit or sid == f"{target_sid}.TW":
                results.append({"id": sid, "df": df.tail(40), "labels": labels, "lines": lines, "price": price, "vol": vol})
        except: continue
    status.update(label="✅ 掃描任務完成", state="complete")

# --- [ 5. 色彩繽紛的結果卡片 ] ---
if results:
    
    cols = st.columns(2)
    for idx, item in enumerate(results):
        with cols[idx % 2]:
            # 彩色標籤 HTML
            badge_html = "".join([f'<span class="badge" style="background:{"#1abc9c" if "三角" in l else "#4f46e5" if "爆量" in l else "#16a34a" if "旗箱" in l else "#e74c3c"}">{l}</span>' for l in item['labels']])
            
            st.markdown(f'''
                <div class="stock-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:20px; font-weight:bold; color:#1e293b;">{item["id"]}</span>
                        <div>{badge_html}</div>
                    </div>
                    <div style="font-size:14px; color:#64748b; margin-top:4px;">現價：{item["price"]:.2f} | 成交：{item["vol"]}張</div>
                </div>
            ''', unsafe_allow_html=True)
            
            # 精緻子圖 (K線 + 成交量)
            d = item['df']
            sh, ih, sl, il = item['lines']
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
            
            # K線
            fig.add_trace(go.Candlestick(x=d.index, open=d['Open'], high=d['High'], low=d['Low'], close=d['Close'], increasing_line_color='#ef4444', decreasing_line_color='#22c55e', name="K線"), row=1, col=1)
            
            # 趨勢線 (虛線)
            xv = np.arange(30)
            fig.add_trace(go.Scatter(x=d.index[-30:], y=sh*xv + ih, line=dict(color='#f43f5e', width=2, dash='dash'), name="壓力"), row=1, col=1)
            fig.add_trace(go.Scatter(x=d.index[-30:], y=sl*xv + il, line=dict(color='#10b981', width=2, dash='dash'), name="支撐"), row=1, col=1)
            
            # 成交量
            v_cols = ['#ef4444' if c >= o else '#22c55e' for o, c in zip(d['Open'], d['Close'])]
            fig.add_trace(go.Bar(x=d.index, y=d['Volume'], marker_color=v_cols, name="成交量"), row=2, col=1)
            
            fig.update_layout(height=450, template="plotly_white", xaxis_rangeslider_visible=False, showlegend=False, margin=dict(l=5,r=5,t=5,b=5))
            st.plotly_chart(fig, use_container_width=True, key=f"plot_{item['id']}")
            st.divider()
else:
    st.warning("💡 暫時沒發現形態標的，請試著調整左側的最低張數。")
