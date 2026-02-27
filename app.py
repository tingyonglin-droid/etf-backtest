import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
from datetime import datetime, timedelta

# 忽略警告
warnings.filterwarnings('ignore')

# 1. 頁面配置與美化
st.set_page_config(page_title='槓桿 ETF 旗艦回測系統', page_icon='🚀', layout='wide')

# 自定義 CSS 讓介面更像專業交易端
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #1a1c24; padding: 15px; border-radius: 15px; border: 1px solid #30363d; }
    .stButton>button { border-radius: 10px; height: 3em; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

st.title('🚀 槓桿 ETF 專業回測終端')
st.markdown("---")

# 2. 側邊欄參數設定
with st.sidebar:
    st.header('⚙️ 策略參數設定')
    
    with st.container():
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            start_date = st.date_input('開始日期', value=datetime(2015, 1, 1))
        with col_d2:
            end_date = st.date_input('結束日期', value=datetime.today())

    init_cash = st.number_input('初始投入資金 (TWD)', min_value=10000, value=1000000, step=100000)
    
    st.markdown("### 部位配置")
    stock_ratio = st.slider('目標股票比例 (%)', 10, 90, 50) / 100
    rebalance_trigger = st.slider('再平衡觸發偏移 (%)', 10, 100, 50) / 100
    
    st.markdown("### 交易成本")
    commission = 0.001425
    tax = 0.003
    
    run_btn = st.button('🔥 開始執行回測', type='primary', use_container_width=True)

# 3. 核心運算函數
@st.cache_data(show_spinner=False)
def get_clean_data(start, end):
    try:
        # 下載 00631L (正2) 與 0050 (基準)
        lev_df = yf.download('00631L.TW', start=start, end=end, auto_adjust=True, progress=False)
        bm_df = yf.download('0050.TW', start=start, end=end, auto_adjust=True, progress=False)
        
        if lev_df.empty or bm_df.empty: return None, None
        
        # 處理 yfinance 可能返回的 MultiIndex
        s_lev = lev_df['Close'].iloc[:, 0] if isinstance(lev_df.columns, pd.MultiIndex) else lev_df['Close']
        s_bm = bm_df['Close'].iloc[:, 0] if isinstance(bm_df.columns, pd.MultiIndex) else bm_df['Close']
        
        common_idx = s_lev.index.intersection(s_bm.index)
        return s_lev.loc[common_idx].dropna(), s_bm.loc[common_idx].dropna()
    except:
        return None, None

def calculate_strategy(prices, init_cash, target_ratio, trigger):
    cash = init_cash * (1 - target_ratio)
    shares = (init_cash * target_ratio * (1 - commission)) / prices.iloc[0]
    
    history = []
    rebalances = []
    
    for date, price in prices.items():
        price = float(price)
        stock_val = shares * price
        total_val = stock_val + cash
        current_ratio = stock_val / total_val
        
        # 檢查是否觸發再平衡
        deviation = abs(current_ratio - target_ratio) / target_ratio
        if deviation >= trigger and date != prices.index[0]:
            target_stock_val = total_val * target_ratio
            diff = target_stock_val - stock_val
            
            if diff > 0: # 買入
                shares_to_buy = diff / price * (1 - commission)
                shares += shares_to_buy
                cash -= (diff / (1 - commission))
                rebalances.append({'日期': date, '動作': '加碼買入', '金額': round(diff)})
            else: # 賣出
                shares_to_sell = abs(diff) / price
                shares -= shares_to_sell
                cash += (abs(diff) * (1 - commission - tax))
                rebalances.append({'日期': date, '動作': '獲利賣出', '金額': round(abs(diff))})
        
        history.append({'date': date, 'total': total_val, 'stock': shares * price, 'cash': cash})
        
    return pd.DataFrame(history).set_index('date'), pd.DataFrame(rebalances)

# 4. 主畫面邏輯
if run_btn:
    with st.spinner('🚀 正在從 Yahoo Finance 抓取數據...'):
        s_lev, s_bm = get_clean_data(start_date, end_date)
        
    if s_lev is not None:
        # 執行回測
        res_strat, res_rebal = calculate_strategy(s_lev, init_cash, stock_ratio, rebalance_trigger)
        
        # 0050 買入持有對照組
        bm_shares = (init_cash * (1 - commission)) / s_bm.iloc[0]
        res_bm = (s_bm * bm_shares).to_frame(name='total')

        # 計算指標
        def get_stats(df, label):
            final = df['total'].iloc[-1]
            total_ret = (final / init_cash - 1) * 100
            mdd = ((df['total'].cummax() - df['total']) / df['total'].cummax()).max() * 100
            return final, total_ret, mdd

        f1, r1, d1 = get_stats(res_strat, '策略')
        f2, r2, d2 = get_stats(res_bm, '0050')

        # 顯示指標卡片
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("最終資產 (策略)", f"${f1:,.0f}", f"{r1:+.1f}%")
        col2.metric("最大回撤 (策略)", f"-{d1:.1f}%", delta_color="inverse")
        col3.metric("最終資產 (0050)", f"${f2:,.0f}", f"{r2:+.1f}%")
        col4.metric("最大回撤 (0050)", f"-{d2:.1f}%", delta_color="inverse")

        # 繪製 Plotly 圖表
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                            subplot_titles=("📈 淨值曲線比較", "⚖️ 倉位比例變動", "📉 回撤深度 (%)"))
        
        # 淨值線
        fig.add_trace(go.Scatter(x=res_strat.index, y=res_strat['total'], name='槓桿再平衡', line=dict(color='#ff4b4b', width=2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=res_bm.index, y=res_bm['total'], name='0050 買入持有', line=dict(color='#00d4ff', width=1.5, dash='dot')), row=1, col=1)
        
        # 部位佔比
        fig.add_trace(go.Scatter(x=res_strat.index, y=res_strat['stock']/res_strat['total']*100, name='股票佔比', fill='tozeroy', line=dict(color='rgba(255, 75, 75, 0.5)')), row=2, col=1)
        
        # 回撤線
        dd_strat = (res_strat['total'] / res_strat['total'].cummax() - 1) * 100
        dd_bm = (res_bm['total'] / res_bm['total'].cummax() - 1) * 100
        fig.add_trace(go.Scatter(x=res_strat.index, y=dd_strat, name='策略回撤', fill='tozeroy', line=dict(color='#ff4b4b')), row=3, col=1)
        fig.add_trace(go.Scatter(x=res_bm.index, y=dd_bm, name='0050回撤', line=dict(color='#00d4ff')), row=3, col=1)

        fig.update_layout(height=900, template="plotly_dark", hovermode="x unified", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

        if not res_rebal.empty:
            with st.expander("📋 查看再平衡歷史明細"):
                st.table(res_rebal.tail(10))
    else:
        st.error("❌ 抓取數據失敗，請檢查網路連接或代號是否正確。")
else:
    st.info("💡 請在左側調整參數後按下『執行回測』。本系統使用 Plotly 渲染，完美支援中文顯示。")

