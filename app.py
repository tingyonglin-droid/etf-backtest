import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings

# 忽略警告
warnings.filterwarnings('ignore')

# 頁面設定
st.set_page_config(page_title='槓桿ETF回測系統', page_icon='📈', layout='wide')
st.title('📈 槓桿ETF回測系統')
st.caption('策略：00631L（0050正2）+ 現金，定期再平衡 vs 0050買入持有')

# ============================================================
# 側邊欄參數設定
# ============================================================
with st.sidebar:
    st.header('⚙️ 回測參數')
    
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input('開始日期', value=pd.to_datetime('2015-01-01'),
                                   min_value=pd.to_datetime('2014-10-31'))
    with col2:
        end_date = st.date_input('結束日期', value=pd.to_datetime('2024-12-31'))

    init_cash = st.number_input('初始資金（元）', min_value=10000, max_value=100000000,
                                 value=1000000, step=100000, format='%d')

    stock_ratio = st.slider('股票配置比例（%）', min_value=10, max_value=90,
                             value=50, step=5) / 100

    rebalance_trigger = st.slider('再平衡觸發偏移（%）', min_value=10, max_value=100,
                                   value=50, step=5) / 100

    commission = 0.001425
    tax = 0.003

    st.divider()
    st.caption(f'現金比例：{(1-stock_ratio)*100:.0f}%')
    st.caption(f'等效曝險：{stock_ratio*2*100:.0f}%（正2x{stock_ratio*100:.0f}%）')
    st.caption('手續費：0.1425%，交易稅：0.3%')

    run_btn = st.button('🚀 執行回測', type='primary', use_container_width=True)

# ============================================================
# 回測函數
# ============================================================
@st.cache_data(show_spinner=False)
def fetch_data(start, end):
    # 下載數據並處理 yfinance 可能的多重索引
    df_lev = yf.download('00631L.TW', start=start, end=end, auto_adjust=True, progress=False)
    df_bm  = yf.download('0050.TW',   start=start, end=end, auto_adjust=True, progress=False)
    
    if df_lev.empty or df_bm.empty:
        return pd.Series(), pd.Series()

    # 提取 Close 價格
    if 'Close' in df_lev.columns:
        s_lev = df_lev['Close']
    else:
        s_lev = df_lev.iloc[:, 0]
        
    if 'Close' in df_bm.columns:
        s_bm = df_bm['Close']
    else:
        s_bm = df_bm.iloc[:, 0]

    # 轉為 Series 並處理多重索引
    if isinstance(s_lev, pd.DataFrame): s_lev = s_lev.iloc[:, 0]
    if isinstance(s_bm, pd.DataFrame): s_bm = s_bm.iloc[:, 0]
        
    idx = s_lev.index.intersection(s_bm.index)
    return s_lev.loc[idx].dropna(), s_bm.loc[idx].dropna()

def run_strategy(prices, init_cash, stock_ratio, trigger, commission, tax):
    if prices.empty: return pd.DataFrame(), pd.DataFrame()
    
    cash_ratio = 1 - stock_ratio
    cash       = init_cash * cash_ratio
    price0     = float(prices.iloc[0])
    shares     = (init_cash * stock_ratio) * (1 - commission) / price0
    
    rebalances = []
    equity     = []

    for date, price in prices.items():
        price       = float(price)
        stock_val   = shares * price
        total       = stock_val + cash
        cur_ratio   = stock_val / total
        deviation   = abs(cur_ratio - stock_ratio) / stock_ratio

        if deviation >= trigger and date != prices.index[0]:
            target = total * stock_ratio
            diff   = target - stock_val
            
            if diff > 0: # 買入
                new_sh = diff / price * (1 - commission)
                cost   = diff / (1 - commission)
                if cash >= cost:
                    shares += new_sh
                    cash   -= cost
                    rebalances.append({'日期': date, '動作': '再平衡買入', '價格': round(price, 2), 
                                       '金額': round(diff, 0), '目前比例': f'{cur_ratio:.1%}'})
            else: # 賣出
                sell_sh = abs(diff) / price
                revenue = sell_sh * price * (1 - commission - tax)
                shares -= sell_sh
                cash   += revenue
                rebalances.append({'日期': date, '動作': '再平衡賣出', '價格': round(price, 2), 
                                   '金額': round(abs(diff), 0), '目前比例': f'{cur_ratio:.1%}'})

        equity.append({'date': date, 'value': shares * price + cash, 
                       'stock_value': shares * price, 'cash': cash})

    df = pd.DataFrame(equity).set_index('date')
    return df, pd.DataFrame(rebalances)

def run_buyhold(prices, init_cash, commission):
    if prices.empty: return pd.DataFrame()
    price0 = float(prices.iloc[0])
    shares = init_cash * (1 - commission) / price0
    df = pd.DataFrame([{'date': d, 'value': shares * float(p)} for d, p in prices.items()]).set_index('date')
    return df

def calc_stats(eq, init_cash, name):
    if eq.empty: return {}
    final    = eq['value'].iloc[-1]
    ret      = (final - init_cash) / init_cash * 100
    years    = (eq.index[-1] - eq.index[0]).days / 365
    if years == 0: years = 1
    cagr     = ((final / init_cash) ** (1 / years) - 1) * 100
    roll_max = eq['value'].cummax()
    mdd      = ((roll_max - eq['value']) / roll_max).max() * 100
    dr       = eq['value'].pct_change().dropna()
    sharpe   = (dr.mean() * 252 - 0.015) / (dr.std() * np.sqrt(252)) if dr.std() != 0 else 0
    return {'策略': name, '最終資產': f'{final:,.0f} 元',
            '總報酬': f'{ret:+.2f}%', '年化報酬(CAGR)': f'{cagr:+.2f}%',
            '最大回撤': f'{mdd:.2f}%', 'Sharpe': f'{sharpe:.2f}'}

# ============================================================
# 主畫面執行邏輯
# ============================================================
if run_btn:
    with st.spinner('下載資料中...'):
        s_lev, s_bm = fetch_data(str(start_date), str(end_date))

    if len(s_lev) < 5:
        st.error('資料不足（可能因日期範圍過短或代號錯誤），請調整日期範圍')
        st.stop()

    with st.spinner('回測計算中...'):
        eq_lev, rebalance_df = run_strategy(s_lev, init_cash, stock_ratio,
                                             rebalance_trigger, commission, tax)
        eq_bm = run_buyhold(s_bm, init_cash, commission)

    # 績效指標
    s1 = calc_stats(eq_lev, init_cash, f'槓桿策略（正2 {stock_ratio*100:.0f}%）')
    s2 = calc_stats(eq_bm,  init_cash, '0050 買入持有')

    st.subheader('📊 績效比較')
    col_a, col_b = st.columns(2)

    def metric_card(col, stats):
        with col:
            st.markdown(f"### {stats['策略']}")
            m1, m2 = st.columns(2)
            m1.metric('最終資產', stats['最終資產'])
            m2.metric('總報酬',   stats['總報酬'])
            m3, m4, m5 = st.columns(3)
            m3.metric('年化報酬', stats['年化報酬(CAGR)'])
            m4.metric('最大回撤', stats['最大回撤'])
            m5.metric('Sharpe',   stats['Sharpe'])

    metric_card(col_a, s1)
    metric_card(col_b, s2)

    st.divider()

    # ============================================================
    # 使用 Plotly 繪圖 (解決中文字體問題)
    # ============================================================
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.05,
                        subplot_titles=("淨值曲線比較 (萬元 TWD)", "策略持倉比例變動 (%)", 
                                        "相對於 0050 的超額報酬 (%)", "歷史回撤比較 (Drawdown %)"),
                        row_heights=[0.4, 0.2, 0.2, 0.2])

    # 1. 淨值曲線
    fig.add_trace(go.Scatter(x=eq_lev.index, y=eq_lev['value']/10000, name='槓桿再平衡策略', line=dict(color='#e74c3c', width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=eq_bm.index, y=eq_bm['value']/10000, name='0050 買入持有', line=dict(color='#3498db', width=2)), row=1, col=1)
    
    # 加入再平衡點點
    if not rebalance_df.empty:
        buys = rebalance_df[rebalance_df['動作'] == '再平衡買入']
        sells = rebalance_df[rebalance_df['動作'] == '再平衡賣出']
        fig.add_trace(go.Scatter(x=buys['日期'], y=eq_lev.loc[buys['日期'], 'value']/10000, 
                                 mode='markers', name='再平衡買入點', marker=dict(color='#2ecc71', size=8)), row=1, col=1)
        fig.add_trace(go.Scatter(x=sells['日期'], y=eq_lev.loc[sells['日期'], 'value']/10000, 
                                 mode='markers', name='再平衡賣出點', marker=dict(color='#ff6b6b', size=8)), row=1, col=1)

    # 2. 持倉比例
    total = eq_lev['value']
    stock_p = (eq_lev['stock_value'] / total) * 100
    cash_p  = (eq_lev['cash'] / total) * 100
    fig.add_trace(go.Scatter(x=eq_lev.index, y=stock_p, name='股票比例 %', stackgroup='one', fillcolor='rgba(231, 76, 60, 0.6)', line=dict(width=0)), row=2, col=1)
    fig.add_trace(go.Scatter(x=eq_lev.index, y=cash_p, name='現金比例 %', stackgroup='one', fillcolor='rgba(127, 140, 141, 0.6)', line=dict(width=0)), row=2, col=1)
    fig.add_hline(y=stock_ratio*100, line_dash="dash", line_color="white", row=2, col=1)

    # 3. 超額報酬
    excess = (eq_lev['value'] / eq_bm['value'].reindex(eq_lev.index) - 1) * 100
    fig.add_trace(go.Scatter(x=excess.index, y=excess, name='超額報酬 %', fill='tozeroy', line=dict(color='#9b59b6')), row=3, col=1)

    # 4. 回撤
    dd_lev = (eq_lev['value'] / eq_lev['value'].cummax() - 1) * 100
    dd_bm  = (eq_bm['value'] / eq_bm['value'].cummax() - 1) * 100
    fig.add_trace(go.Scatter(x=dd_lev.index, y=dd_lev, name='槓桿策略回撤', line=dict(color='#e74c3c')), row=4, col=1)
    fig.add_trace(go.Scatter(x=dd_bm.index, y=dd_bm, name='0050 回撤', line=dict(color='#3498db')), row=4, col=1)

    fig.update_layout(height=1000, template="plotly_dark", showlegend=True, 
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                      margin=dict(l=20, r=20, t=80, b=20))
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(255,255,255,0.1)')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(255,255,255,0.1)')
    
    st.plotly_chart(fig, use_container_width=True)

    # 再平衡明細
    st.divider()
    st.subheader(f'📋 再平衡明細（共 {len(rebalance_df)} 次）')
    if not rebalance_df.empty:
        st.dataframe(rebalance_df, use_container_width=True)
    else:
        st.info('回測期間內未觸發再平衡')

else:
    st.info('請在左側設定參數後，點擊「執行回測」開始')
    st.markdown('''
    **為什麼圖表現在可以顯示中文了？**
    本系統已將圖表引擎從 Matplotlib 更換為 **Plotly**。
    - **原理**：Plotly 在您的瀏覽器上直接顯示文字，不需要伺服器端安裝字型。
    - **優點**：除了中文正常，您還可以用滑鼠縮放圖表，或將游標移到線上查看每日數據。
    ''')

