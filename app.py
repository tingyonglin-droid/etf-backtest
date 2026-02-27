import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas_ta as ta
from datetime import datetime, timedelta

# 頁面配置
st.set_page_config(page_title="台股個股分析終端", page_icon="📊", layout="wide")

# 自定義 CSS 美化
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #ffffff; }
    .metric-card { 
        background-color: #1a1c24; 
        padding: 20px; 
        border-radius: 15px; 
        border: 1px solid #30363d;
        text-align: center;
    }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { 
        font-size: 18px; 
        font-weight: 600; 
        color: #8b949e; 
    }
    .stTabs [aria-selected="true"] { color: #58a6ff !important; }
    </style>
""", unsafe_allow_html=True)

# 標題區
st.title("📊 台股個股智慧分析系統")
st.caption("整合技術指標、基本面與 AI 的專業投資決策工具")

# 側邊欄控制
with st.sidebar:
    st.header("🔍 個股查詢")
    symbol_input = st.text_input("輸入台股代碼 (例: 2330)", value="2330")
    
    # 自動處理台股字尾
    if not symbol_input.endswith(".TW") and not symbol_input.endswith(".TWO"):
        symbol = f"{symbol_input}.TW"
    else:
        symbol = symbol_input

    period = st.selectbox("分析區間", ["1mo", "3mo", "6mo", "1y", "2y", "5y"], index=3)
    
    st.divider()
    st.markdown("### 🛠️ 指標設定")
    ma_short = st.number_input("短期均線 (MA)", value=5)
    ma_long = st.number_input("長期均線 (MA)", value=20)
    
    analyze_btn = st.button("🚀 執行深度分析", use_container_width=True, type="primary")

# 核心數據處理
@st.cache_data(ttl=3600)
def fetch_stock_full_data(symbol, period):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period)
        info = ticker.info
        return df, info, ticker
    except:
        return None, None, None

def plot_technical_chart(df, symbol):
    # 計算技術指標
    df['MA_S'] = ta.sma(df['Close'], length=ma_short)
    df['MA_L'] = ta.sma(df['Close'], length=ma_long)
    df['RSI'] = ta.rsi(df['Close'], length=14)
    
    # 建立多子圖 (K線 + RSI)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.1, row_heights=[0.7, 0.3],
                        subplot_titles=(f"{symbol} 歷史 K 線與均線", "RSI 強弱指標"))

    # K線圖
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'],
                                 low=df['Low'], close=df['Close'], name="K線"), row=1, col=1)
    
    # 均線
    fig.add_trace(go.Scatter(x=df.index, y=df['MA_S'], name=f'MA {ma_short}', line=dict(color='#FFD700', width=1)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA_L'], name=f'MA {ma_long}', line=dict(color='#00BFFF', width=1)), row=1, col=1)

    # RSI
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name='RSI', line=dict(color='#FF69B4', width=1.5)), row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", opacity=0.5, row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", opacity=0.5, row=2, col=1)

    fig.update_layout(height=700, template="plotly_dark", 
                      xaxis_rangeslider_visible=False,
                      margin=dict(l=20, r=20, t=50, b=20))
    return fig

# 執行分析
if analyze_btn or symbol:
    df, info, ticker = fetch_stock_full_data(symbol, period)
    
    if df is not None and not df.empty:
        # 1. 頂部摘要資訊卡
        current_price = df['Close'].iloc[-1]
        prev_price = df['Close'].iloc[-2]
        change = current_price - prev_price
        pct_change = (change / prev_price) * 100
        
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f'<div class="metric-card"><small>股票名稱</small><h3>{info.get("longName", symbol)}</h3></div>', unsafe_allow_html=True)
        with c2:
            color = "#ff4b4b" if change < 0 else "#00c853"
            st.markdown(f'<div class="metric-card"><small>當前市價</small><h3 style="color:{color}">${current_price:.2f}</h3></div>', unsafe_allow_html=True)
        with c3:
            st.markdown(f'<div class="metric-card"><small>今日漲跌</small><h3 style="color:{color}">{change:+.2f} ({pct_change:+.2f}%)</h3></div>', unsafe_allow_html=True)
        with c4:
            pe_ratio = info.get('trailingPE', 'N/A')
            st.markdown(f'<div class="metric-card"><small>本益比 (PE)</small><h3>{pe_ratio if pe_ratio == "N/A" else f"{pe_ratio:.2f}"}</h3></div>', unsafe_allow_html=True)

        st.markdown("---")

        # 2. 主要分析分頁
        tab1, tab2, tab3 = st.tabs(["📈 技術分析", "🏢 基本面資訊", "🤖 AI 投資建議"])

        with tab1:
            st.plotly_chart(plot_technical_chart(df, symbol), use_container_width=True)
            
            # 技術數據表格
            with st.expander("查看原始技術數據"):
                st.dataframe(df.tail(10).sort_index(ascending=False), use_container_width=True)

        with tab2:
            st.subheader("財務關鍵數據")
            f1, f2, f3 = st.columns(3)
            f1.metric("市值 (Market Cap)", f"{info.get('marketCap', 0)/1e8:.2f} 億")
            f2.metric("股息殖利率", f"{info.get('dividendYield', 0)*100:.2f} %" if info.get('dividendYield') else "N/A")
            f3.metric("每股盈餘 (EPS)", f"{info.get('trailingEps', 0):.2f}")

            st.divider()
            
            col_info1, col_info2 = st.columns(2)
            with col_info1:
                st.markdown("### 業務簡介")
                st.write(info.get("longBusinessSummary", "暫無中文介紹"))
            with col_info2:
                st.markdown("### 財務報表 (最新年度)")
                try:
                    income_stmt = ticker.calendar
                    st.write(income_stmt)
                except:
                    st.info("暫時無法取得詳細財報，請參考 Yahoo Finance 原站。")

        with tab3:
            st.subheader("🤖 AI 智慧診斷")
            st.info("此模組會結合當前技術指標與基本面數據，產出投資參考報告。")
            
            # 這裡可以整合 Gemini API 進行文本分析
            recommendation = "買入" if df['Close'].iloc[-1] > df['MA_S'].iloc[-1] else "觀望"
            
            st.markdown(f"""
            **當前評價：** `{recommendation}`
            - **技術面分析：** 短期股價{'位於均線之上，動能轉強' if recommendation == '買入' else '偏弱，建議等待收復均線'}。
            - **風險提示：** 請注意量價背離風險以及台幣匯率波動對權值股的影響。
            """)

    else:
        st.error(f"找不到代碼 `{symbol}` 的資料，請確認輸入是否正確。")
else:
    st.info("請在側邊欄輸入台股代碼並點擊「執行深度分析」。")

