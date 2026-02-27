import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# 1. 頁面初始化與樣式美化
st.set_page_config(page_title="台股深度分析終端", page_icon="📈", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0c0c0e; color: #e1e1e1; }
    div[data-testid="stMetricValue"] { font-size: 28px; font-weight: bold; color: #58a6ff; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { 
        height: 50px; 
        background-color: #161b22; 
        border-radius: 10px 10px 0 0; 
        padding: 0 20px;
        color: #8b949e;
    }
    .stTabs [aria-selected="true"] { background-color: #1f6feb !important; color: white !important; }
    </style>
""", unsafe_allow_html=True)

# 2. 側邊欄控制台
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2422/2422796.png", width=80)
    st.header("🔍 分析設定")
    stock_id = st.text_input("輸入台股代碼 (例如: 2330, 2454)", value="2330")
    
    # 自動補完代碼字尾
    if ".TW" not in stock_id.upper() and ".TWO" not in stock_id.upper():
        full_symbol = f"{stock_id}.TW"
    else:
        full_symbol = stock_id.upper()

    lookback = st.selectbox("分析週期", ["1個月", "3個月", "6個月", "1年", "2年", "5年"], index=3)
    period_map = {"1個月": "1mo", "3個月": "3mo", "6個月": "6mo", "1年": "1y", "2年": "2y", "5年": "5y"}
    
    st.divider()
    st.markdown("### 🛠️ 指標快選")
    show_ma = st.checkbox("移動平均線 (MA)", value=True)
    show_rsi = st.checkbox("強弱指標 (RSI)", value=True)
    show_macd = st.checkbox("平滑異同平均線 (MACD)", value=False)
    
    run_btn = st.button("🚀 開始深度分析", type="primary", use_container_width=True)

# 3. 數據獲取與處理
@st.cache_data(show_spinner=False, ttl=600)
def fetch_stock_data(symbol, period):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period)
        if df.empty:
            # 嘗試切換代碼後綴 (有些股在 .TWO 上櫃)
            alt_symbol = symbol.replace(".TW", ".TWO") if ".TW" in symbol else symbol.replace(".TWO", ".TW")
            df = yf.Ticker(alt_symbol).history(period=period)
            if not df.empty: symbol = alt_symbol
        
        info = ticker.info
        return df, info, symbol
    except Exception as e:
        return None, None, symbol

# 4. 圖表渲染函數
def draw_pro_chart(df, symbol, show_rsi, show_macd):
    # 計算指標
    df['MA5'] = ta.sma(df['Close'], length=5)
    df['MA20'] = ta.sma(df['Close'], length=20)
    df['MA60'] = ta.sma(df['Close'], length=60)
    
    rows = 2
    heights = [0.7, 0.3]
    if show_rsi and show_macd:
        rows = 3
        heights = [0.5, 0.25, 0.25]
    elif show_rsi or show_macd:
        rows = 2
        heights = [0.7, 0.3]
    else:
        rows = 1
        heights = [1.0]

    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.03, row_heights=heights)

    # 主圖: K線與均線
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], 
                                 low=df['Low'], close=df['Close'], name="K線"), row=1, col=1)
    if show_ma:
        fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], name="MA5", line=dict(color='#FFD700', width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], name="MA20", line=dict(color='#00BFFF', width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], name="MA60", line=dict(color='#FF00FF', width=1)), row=1, col=1)

    # RSI 子圖
    curr_row = 2
    if show_rsi:
        df['RSI'] = ta.rsi(df['Close'], length=14)
        fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name="RSI", line=dict(color='#00FF7F')), row=curr_row, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=curr_row, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=curr_row, col=1)
        curr_row += 1

    # MACD 子圖
    if show_macd:
        macd = ta.macd(df['Close'])
        fig.add_trace(go.Bar(x=df.index, y=macd['MACDh_12_26_9'], name="MACD Histogram"), row=curr_row, col=1)
        curr_row += 1

    fig.update_layout(height=800, template="plotly_dark", xaxis_rangeslider_visible=False,
                      margin=dict(l=50, r=50, t=50, b=50), legend=dict(orientation="h", y=1.02))
    return fig

# 5. 主程式畫面
if run_btn or stock_id:
    with st.spinner(f"正在連線市場抓取 {full_symbol} 資料..."):
        df, info, actual_symbol = fetch_stock_data(full_symbol, period_map[lookback])

    if df is not None and not df.empty:
        # 顯示頭部資訊
        curr_p = df['Close'].iloc[-1]
        prev_p = df['Close'].iloc[-2]
        change = curr_p - prev_p
        pct = (change / prev_p) * 100
        
        st.subheader(f"📊 {info.get('longName', actual_symbol)} ({actual_symbol})")
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("目前股價", f"{curr_p:,.2f}", f"{change:+.2f} ({pct:+.2f}%)")
        c2.metric("最高/最低 (區間)", f"{df['High'].max():,.0f} / {df['Low'].min():,.0f}")
        c3.metric("本益比 (PE)", f"{info.get('trailingPE', 'N/A')}")
        c4.metric("市值", f"{info.get('marketCap', 0)/1e8:,.0f} 億")

        tab_main, tab_fin, tab_news = st.tabs(["📈 圖表分析", "📂 財務績效", "📰 相關數據"])
        
        with tab_main:
            st.plotly_chart(draw_pro_chart(df, actual_symbol, show_rsi, show_macd), use_container_width=True)
            
        with tab_fin:
            st.markdown("### 近年財務關鍵數據")
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                st.write("**每股盈餘 (EPS)**")
                st.info(f"最新 EPS: {info.get('trailingEps', '資料載入中...')}")
            with col_f2:
                st.write("**股息殖利率**")
                yield_val = info.get('dividendYield', 0)
                st.info(f"{yield_val*100:.2f} %" if yield_val else "未發放股利")
            
            st.markdown("---")
            st.markdown("### 業務摘要")
            st.write(info.get('longBusinessSummary', '尚無中文介紹'))

        with tab_news:
            st.success("🤖 AI 自動分析建議")
            if df['Close'].iloc[-1] > df['MA20'].iloc[-1]:
                st.markdown("- **技術面**：目前股價位於月線之上，屬於多頭排列。")
            else:
                st.markdown("- **技術面**：股價跌破月線，建議保守觀察支撐點。")
            
            if show_rsi:
                rsi_val = df['RSI'].iloc[-1]
                if rsi_val > 70: st.markdown("- **動能**：RSI 進入超買區，需留意回檔。")
                elif rsi_val < 30: st.markdown("- **動能**：RSI 進入超跌區，反彈機會大。")

    else:
        st.error(f"❌ 無法取得代碼 {full_symbol} 的資料。")
        st.markdown("""
        **可能原因：**
        1. 網路上暫時無法連線至 Yahoo Finance。
        2. 台股代碼輸入錯誤（應為四位數字，如 2330）。
        3. 該股票已退市或更改名稱。
        """)
else:
    st.info("請在左側輸入台股代碼並按分析開始。本系統採用 Plotly 渲染，100% 解決中文亂碼問題。")

