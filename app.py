import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import warnings
from matplotlib.lines import Line2D
import matplotlib.font_manager as fm

# 忽略警告
warnings.filterwarnings('ignore')

# ============================================================
# 字體解決方案：設定中文字體
# ============================================================
def set_mpl_chinese_font():
    # 嘗試尋找系統中可能存在的中文字體
    common_fonts = [
        'Noto Sans CJK TC', 'Noto Sans TC', 'Microsoft JhengHei', 
        'Heiti TC', 'Arial Unicode MS', 'Droid Sans Fallback', 'PingFang TC'
    ]
    
    found_font = None
    system_fonts = [f.name for f in fm.fontManager.ttflist]
    
    for f in common_fonts:
        if f in system_fonts:
            found_font = f
            break
    
    if found_font:
        plt.rcParams['font.sans-serif'] = [found_font] + plt.rcParams['font.sans-serif']
    
    # 解決負號 '-' 顯示為方塊的問題
    plt.rcParams['axes.unicode_minus'] = False

set_mpl_chinese_font()

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
    s_lev = yf.download('00631L.TW', start=start, end=end, auto_adjust=True, progress=False)['Close']
    s_bm  = yf.download('0050.TW',   start=start, end=end, auto_adjust=True, progress=False)['Close']
    
    if isinstance(s_lev, pd.DataFrame): s_lev = s_lev.iloc[:, 0]
    if isinstance(s_bm, pd.DataFrame): s_bm = s_bm.iloc[:, 0]
        
    idx = s_lev.index.intersection(s_bm.index)
    return s_lev.loc[idx], s_bm.loc[idx]

def run_strategy(prices, init_cash, stock_ratio, trigger, commission, tax):
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
            
            if diff > 0:
                new_sh = diff / price * (1 - commission)
                cost   = diff / (1 - commission)
                if cash >= cost:
                    shares += new_sh
                    cash   -= cost
                    rebalances.append({'日期': date, '動作': '再平衡買入',
                                       '價格': round(price, 2), '金額': round(diff, 0),
                                       '原本比例': f'{cur_ratio:.1%}'})
            else:
                sell_sh = abs(diff) / price
                revenue = sell_sh * price * (1 - commission - tax)
                shares -= sell_sh
                cash   += revenue
                rebalances.append({'日期': date, '動作': '再平衡賣出',
                                   '價格': round(price, 2), '金額': round(abs(diff), 0),
                                   '原本比例': f'{cur_ratio:.1%}'})

        equity.append({'date': date, 'value': shares * price + cash,
                       'stock_value': shares * price, 'cash': cash})

    df = pd.DataFrame(equity).set_index('date')
    return df, pd.DataFrame(rebalances)

def run_buyhold(prices, init_cash, commission):
    price0 = float(prices.iloc[0])
    shares = init_cash * (1 - commission) / price0
    df = pd.DataFrame([{'date': d, 'value': shares * float(p)} for d, p in prices.items()]).set_index('date')
    return df

def calc_stats(eq, init_cash, name):
    final    = eq['value'].iloc[-1]
    ret      = (final - init_cash) / init_cash * 100
    years    = (eq.index[-1] - eq.index[0]).days / 365
    cagr     = ((final / init_cash) ** (1 / years) - 1) * 100
    roll_max = eq['value'].cummax()
    mdd      = ((roll_max - eq['value']) / roll_max).max() * 100
    dr       = eq['value'].pct_change().dropna()
    sharpe   = (dr.mean() * 252 - 0.015) / (dr.std() * np.sqrt(252))
    return {'策略': name, '最終資產': f'{final:,.0f} 元',
            '總報酬': f'{ret:+.2f}%', '年化報酬(CAGR)': f'{cagr:+.2f}%',
            '最大回撤': f'{mdd:.2f}%', 'Sharpe': f'{sharpe:.2f}'}

# ============================================================
# 主畫面執行邏輯
# ============================================================
if run_btn:
    with st.spinner('下載資料中...'):
        try:
            s_lev, s_bm = fetch_data(str(start_date), str(end_date))
        except Exception as e:
            st.error(f'資料下載失敗：{e}')
            st.stop()

    if len(s_lev) < 10:
        st.error('資料不足，請調整日期範圍')
        st.stop()

    with st.spinner('回測計算中...'):
        eq_lev, rebalance_df = run_strategy(s_lev, init_cash, stock_ratio,
                                             rebalance_trigger, commission, tax)
        eq_bm = run_buyhold(s_bm, init_cash, commission)

    # 績效指標
    s1 = calc_stats(eq_lev, init_cash, f'槓桿策略（正2 {stock_ratio*100:.0f}%）')
    s2 = calc_stats(eq_bm,  init_cash, '0050 買入持有')

    st.subheader('📊 績效比較')
    col1, col2 = st.columns(2)

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

    metric_card(col1, s1)
    metric_card(col2, s2)

    st.divider()

    # 繪圖
    fig, axes = plt.subplots(4, 1, figsize=(12, 16),
                              gridspec_kw={'height_ratios': [3, 1.5, 1.5, 1.5]})
    fig.patch.set_facecolor('#0e1117')
    
    for ax in axes:
        ax.set_facecolor('#0e1117')
        ax.tick_params(colors='white')
        ax.yaxis.label.set_color('white')
        ax.xaxis.label.set_color('white')
        for spine in ax.spines.values():
            spine.set_edgecolor('#444')

    # Chart 1: Equity Curve
    ax1 = axes[0]
    ax1.plot(eq_lev.index, eq_lev['value']/10000, label='槓桿再平衡策略', color='#e74c3c', lw=2)
    ax1.plot(eq_bm.index,  eq_bm['value']/10000,  label='0050 買入持有', color='#3498db', lw=2)
    ax1.axhline(init_cash/10000, color='gray', lw=0.8, ls='--', label='初始資金')

    if not rebalance_df.empty:
        sells = rebalance_df[rebalance_df['動作'] == '再平衡賣出']
        buys  = rebalance_df[rebalance_df['動作'] == '再平衡買入']
        ax1.scatter(sells['日期'], eq_lev.loc[sells['日期'], 'value']/10000, color='#ff6b6b', s=50, zorder=5)
        ax1.scatter(buys['日期'], eq_lev.loc[buys['日期'], 'value']/10000, color='#2ecc71', s=50, zorder=5)

    h, l = ax1.get_legend_handles_labels()
    h += [Line2D([0],[0], marker='o', color='w', markerfacecolor='#ff6b6b', ms=8),
          Line2D([0],[0], marker='o', color='w', markerfacecolor='#2ecc71', ms=8)]
    l += ['再平衡賣出點', '再平衡買入點']
    ax1.legend(handles=h, labels=l, fontsize=10, facecolor='#1a1a2e', labelcolor='white')
    ax1.set_ylabel('總資產 (萬元 TWD)')
    ax1.set_title('淨值曲線比較', color='white', pad=20)
    ax1.grid(alpha=0.2)

    # Chart 2: Allocation
    ax2 = axes[1]
    total = eq_lev['value']
    stock_pct = (eq_lev['stock_value'] / total) * 100
    cash_pct  = (eq_lev['cash'] / total) * 100
    ax2.stackplot(eq_lev.index, stock_pct, cash_pct, labels=['股票部位 %', '現金部位 %'], colors=['#e74c3c', '#7f8c8d'], alpha=0.8)
    ax2.axhline(stock_ratio*100, color='white', lw=1, ls='--', alpha=0.7)
    ax2.set_ylim(0, 100)
    ax2.set_ylabel('配置比例 (%)')
    ax2.set_title('策略持倉比例變動', color='white')
    ax2.legend(loc='upper right', fontsize=9)

    # Chart 3: Excess Return
    ax3 = axes[2]
    relative = (eq_lev['value'] / eq_bm['value'].reindex(eq_lev.index) - 1) * 100
    ax3.plot(eq_lev.index, relative, color='#9b59b6', lw=1.5)
    ax3.axhline(0, color='gray', lw=0.8, ls='--')
    ax3.fill_between(eq_lev.index, 0, relative, where=relative>=0, alpha=0.3, color='#2ecc71', label='勝過 0050')
    ax3.fill_between(eq_lev.index, 0, relative, where=relative<0, alpha=0.3, color='#e74c3c', label='落後 0050')
    ax3.set_ylabel('超額報酬 (%)')
    ax3.set_title('相對於 0050 的超額報酬', color='white')
    ax3.legend(fontsize=9)

    # Chart 4: Drawdown
    ax4 = axes[3]
    dd_lev = (eq_lev['value'] / eq_lev['value'].cummax() - 1) * 100
    dd_bm  = (eq_bm['value'] / eq_bm['value'].cummax() - 1) * 100
    ax4.plot(eq_lev.index, dd_lev, label='槓桿策略', color='#e74c3c')
    ax4.plot(eq_bm.index, dd_bm, label='0050', color='#3498db')
    ax4.set_ylabel('回撤比例 (%)')
    ax4.set_title('歷史回撤比較 (Drawdown)', color='white')
    ax4.legend(fontsize=9)

    plt.tight_layout()
    st.pyplot(fig)

    # 再平衡明細
    st.divider()
    st.subheader(f'📋 再平衡明細（共 {len(rebalance_df)} 次）')
    if not rebalance_df.empty:
        st.dataframe(rebalance_df, use_container_width=True)
    else:
        st.info('回測期間內未觸發再平衡')

else:
    st.info('請在左側設定參數後，點擊「執行回測」開始')

