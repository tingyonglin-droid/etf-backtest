import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
from datetime import datetime

# 基礎設定
warnings.filterwarnings('ignore')
st.set_page_config(page_title="正2槓桿再平衡回測系統", page_icon="⚖️", layout="wide")

# 自定義 CSS 美化
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #1a1c24; padding: 15px; border-radius: 12px; border: 1px solid #30363d; }
    div[data-testid="stExpander"] { border: none; background-color: #161b22; }
    </style>
""", unsafe_allow_html=True)

# --- 側邊欄控制 ---
with st.sidebar:
    st.header("🧪 策略參數")
    
    # 日期選擇
    col_a, col_b = st.columns(2)
    with col_a:
        start_date = st.date_input("開始日期", value=datetime(2015, 1, 1))
    with col_b:
        end_date = st.date_input("結束日期", value=datetime.today())
    
    # 資金與比例
    init_cash = st.number_input("初始資金 (TWD)", min_value=10000, value=1000000, step=100000)
    target_ratio = st.slider("目標股票比例 (槓桿部位 %)", 10, 90, 50) / 100
    trigger_threshold = st.slider("再平衡觸發閾值 (%)", 5, 100, 10) / 100
    
    st.divider()
    st.markdown("### 💸 交易成本設定")
    fee_rate = 0.001425  # 手續費
    tax_rate = 0.003     # 交易稅 (賣出時)
    
    run_btn = st.button("🚀 執行完整回測", type="primary", use_container_width=True)

st.title("⚖️ 槓桿 ETF 搭配再平衡回測系統")
st.caption("研究對象：00631L (元大台灣50正2) vs 0050 (元大台灣50)")

# --- 核心邏輯 ---
@st.cache_data(show_spinner=False)
def get_data(start, end):
    try:
        # 下載數據
        df_lev = yf.download('00631L.TW', start=start, end=end, auto_adjust=True, progress=False)
        df_bm = yf.download('0050.TW', start=start, end=end, auto_adjust=True, progress=False)
        
        if df_lev.empty or df_bm.empty: return None, None
        
        # 處理 yfinance 可能的 MultiIndex
        s_lev = df_lev['Close'].iloc[:, 0] if isinstance(df_lev.columns, pd.MultiIndex) else df_lev['Close']
        s_bm = df_bm['Close'].iloc[:, 0] if isinstance(df_bm.columns, pd.MultiIndex) else df_bm['Close']
        
        common_idx = s_lev.index.intersection(s_bm.index)
        return s_lev.loc[common_idx].dropna(), s_bm.loc[common_idx].dropna()
    except Exception as e:
        st.error(f"數據下載失敗: {e}")
        return None, None

def run_backtest(prices, init_total, target_ratio, trigger):
    cash = init_total * (1 - target_ratio)
    price_init = float(prices.iloc[0])
    shares = (init_total * target_ratio * (1 - fee_rate)) / price_init
    
    history = []
    log = []
    
    for date, price in prices.items():
        price = float(price)
        stock_val = shares * price
        total_val = stock_val + cash
        current_ratio = stock_val / total_val
        
        # 檢查是否需要再平衡 (相對於目標比例的偏離度)
        deviation = abs(current_ratio - target_ratio) / target_ratio
        
        if deviation >= trigger and date != prices.index[0]:
            target_stock_val = total_val * target_ratio
            diff = target_stock_val - stock_val
            
            if diff > 0: # 買入加碼
                cost = diff / (1 - fee_rate)
                if cash >= cost:
                    shares_to_buy = diff / price * (1 - fee_rate)
                    shares += shares_to_buy
                    cash -= cost
                    log.append({"日期": date, "動作": "再平衡買入", "金額": round(diff), "目前比例": f"{current_ratio:.1%}"})
            else: # 賣出獲利
                shares_to_sell = abs(diff) / price
                revenue = abs(diff) * (1 - fee_rate - tax_rate)
                shares -= shares_to_sell
                cash += revenue
                log.append({"日期": date, "動作": "再平衡賣出", "金額": round(abs(diff)), "目前比例": f"{current_ratio:.1%}"})
        
        history.append({
            "Date": date,
            "Total": shares * price + cash,
            "StockValue": shares * price,
            "Cash": cash,
            "Ratio": (shares * price) / (shares * price + cash)
        })
        
    return pd.DataFrame(history).set_index("Date"), pd.DataFrame(log)

# --- 畫面呈現 ---
if run_btn:
    with st.spinner("正在獲取台股歷史數據..."):
        s_lev, s_bm = get_data(start_date, end_date)
        
    if s_lev is not None:
        # 1. 執行回測
        res_strat, res_log = run_backtest(s_lev, init_cash, target_ratio, trigger_threshold)
        
        # 2. 計算對照組 (0050 買入持有)
        bm_shares = (init_cash * (1 - fee_rate)) / s_bm.iloc[0]
        res_bm = (s_bm * bm_shares).to_frame(name="Total")
        
        # 3. 績效統計
        def get_stats(df, initial):
            final = df['Total'].iloc[-1]
            ret = (final / initial - 1) * 100
            years = (df.index[-1] - df.index[0]).days / 365
            cagr = ((final / initial) ** (1/max(years, 0.1)) - 1) * 100
            mdd = ((df['Total'].cummax() - df['Total']) / df['Total'].cummax()).max() * 100
            return final, ret, cagr, mdd

        f1, r1, c1, d1 = get_stats(res_strat, init_cash)
        f2, r2, c2, d2 = get_stats(res_bm, init_cash)

        # 4. 數據看板
        st.subheader("📊 績效指標比較")
        c_a, c_b = st.columns(2)
        with c_a:
            st.info(f"### 槓桿再平衡策略")
            m1, m2 = st.columns(2); m1.metric("最終資產", f"${f1:,.0f}"); m2.metric("總報酬", f"{r1:+.1f}%")
            m3, m4 = st.columns(2); m3.metric("年化報酬", f"{c1:.1f}%"); m4.metric("最大回撤", f"-{d1:.1f}%")
        with c_b:
            st.info(f"### 0050 買入持有")
            m1, m2 = st.columns(2); m1.metric("最終資產", f"${f2:,.0f}"); m2.metric("總報酬", f"{r2:+.1f}%")
            m3, m4 = st.columns(2); m3.metric("年化報酬", f"{c2:.1f}%"); m4.metric("最大回撤", f"-{d2:.1f}%")

        st.divider()

        # 5. Plotly 互動圖表
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                            subplot_titles=("📈 淨值成長曲線 (萬元)", "⚖️ 策略倉位比例變動 (%)", "📉 回撤深度比較 (%)"),
                            row_heights=[0.5, 0.25, 0.25])
        
        # 淨值線
        fig.add_trace(go.Scatter(x=res_strat.index, y=res_strat['Total']/10000, name="槓桿策略", line=dict(color='#ff4b4b', width=2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=res_bm.index, y=res_bm['Total']/10000, name="0050 買入持有", line=dict(color='#00d4ff', width=1.5, dash='dot')), row=1, col=1)
        
        # 再平衡標記
        if not res_log.empty:
            buys = res_log[res_log['動作'] == '再平衡買入']
            sells = res_log[res_log['動作'] == '再平衡賣出']
            fig.add_trace(go.Scatter(x=buys['日期'], y=res_strat.loc[buys['日期'], 'Total']/10000, mode='markers', name='再平衡買點', marker=dict(symbol='triangle-up', color='#00ff88', size=10)), row=1, col=1)
            fig.add_trace(go.Scatter(x=sells['日期'], y=res_strat.loc[sells['日期'], 'Total']/10000, mode='markers', name='再平衡賣點', marker=dict(symbol='triangle-down', color='#f1c40f', size=10)), row=1, col=1)

        # 比例變動
        fig.add_trace(go.Scatter(x=res_strat.index, y=res_strat['Ratio']*100, name="實際股票比例", fill='tozeroy', line=dict(color='rgba(255, 75, 75, 0.3)')), row=2, col=1)
        fig.add_hline(y=target_ratio*100, line_dash="dash", line_color="white", row=2, col=1)

        # 回撤線
        dd_strat = (res_strat['Total'] / res_strat['Total'].cummax() - 1) * 100
        dd_bm = (res_bm['Total'] / res_bm['Total'].cummax() - 1) * 100
        fig.add_trace(go.Scatter(x=res_strat.index, y=dd_strat, name="策略回撤", fill='tozeroy', line=dict(color='#ff4b4b')), row=3, col=1)
        fig.add_trace(go.Scatter(x=res_bm.index, y=dd_bm, name="0050 回撤", fill='tozeroy', line=dict(color='#00d4ff')), row=3, col=1)

        fig.update_layout(height=1000, template="plotly_dark", hovermode="x unified",
                          margin=dict(l=50, r=50, t=80, b=50), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        
        st.plotly_chart(fig, use_container_width=True)

        # 6. 詳細明細
        if not res_log.empty:
            with st.expander(f"📋 查看再平衡歷史明細 (共 {len(res_log)} 次交易)"):
                st.dataframe(res_log, use_container_width=True)
    else:
        st.error("無法取得數據，請確認代碼 00631L.TW 及 0050.TW 於該日期範圍內有交易資料。")
else:
    st.info("👈 請在左側設定參數後點擊「執行完整回測」。")
    st.markdown("""
    ### 📖 策略原理說明
    1. **本尊與分身**：持有 50% 的「0050正2」加上 50% 的「現金」，在理論上與持有 100% 的 0050 有相似的市場曝險（100%）。
    2. **再平衡紅利**：
       - 當股市大漲，正2部位增值，比例會超過 50%。此時「再平衡」會**賣高**，將獲利轉為現金。
       - 當股市大跌，正2部位縮水，比例會低於 50%。此時「再平衡」會**買低**，用現金加碼正2。
    3. **波動率勝出**：在長期波動向上的市場，這種「自動低買高賣」的機制往往能創造比單純持有 0050 更高的年化報酬，同時保留現金緩衝。
    """)

