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
    .main { background-color: #0c0c0e; }
    .stMetric { background-color: #161b22; padding: 20px; border-radius: 15px; border: 1px solid #30363d; }
    div[data-testid="stExpander"] { border: 1px solid #30363d; background-color: #161b22; border-radius: 10px; }
    </style>
""", unsafe_allow_html=True)

# --- 側邊欄控制 ---
with st.sidebar:
    st.header("🧪 策略參數")
    
    col_a, col_b = st.columns(2)
    with col_a:
        start_date = st.date_input("開始日期", value=datetime(2015, 1, 1))
    with col_b:
        end_date = st.date_input("結束日期", value=datetime.today())
    
    init_cash = st.number_input("初始資金 (TWD)", min_value=10000, value=1000000, step=100000)
    target_ratio = st.slider("目標股票比例 (槓桿部位 %)", 10, 90, 50) / 100
    trigger_threshold = st.slider("再平衡觸發閾值 (%)", 5, 100, 10) / 100
    
    st.divider()
    st.markdown("### 💸 交易成本設定")
    fee_rate = 0.001425  
    tax_rate = 0.003     
    
    run_btn = st.button("🚀 執行完整回測", type="primary", use_container_width=True)

st.title("⚖️ 槓桿 ETF 搭配再平衡回測系統")
st.caption("回測標的：00631L (台灣50正2) vs 0050 (台灣50)")

# --- 核心邏輯 ---
@st.cache_data(show_spinner=False)
def get_data(start, end):
    try:
        df_lev = yf.download('00631L.TW', start=start, end=end, auto_adjust=True, progress=False)
        df_bm = yf.download('0050.TW', start=start, end=end, auto_adjust=True, progress=False)
        
        if df_lev.empty or df_bm.empty: return None, None
        
        s_lev = df_lev['Close'].iloc[:, 0] if isinstance(df_lev.columns, pd.MultiIndex) else df_lev['Close']
        s_bm = df_bm['Close'].iloc[:, 0] if isinstance(df_bm.columns, pd.MultiIndex) else df_bm['Close']
        
        common_idx = s_lev.index.intersection(s_bm.index)
        return s_lev.loc[common_idx].dropna(), s_bm.loc[common_idx].dropna()
    except Exception as e:
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
        
        deviation = abs(current_ratio - target_ratio) / target_ratio
        
        if deviation >= trigger and date != prices.index[0]:
            target_stock_val = total_val * target_ratio
            diff = target_stock_val - stock_val
            
            if diff > 0: # 買入加碼
                cost = diff / (1 - fee_rate)
                if cash >= cost:
                    shares += (diff / price * (1 - fee_rate))
                    cash -= cost
                    log.append({"日期": date, "動作": "再平衡買入", "金額": round(diff), "原本比例": f"{current_ratio:.1%}"})
            else: # 賣出獲利
                shares -= (abs(diff) / price)
                cash += (abs(diff) * (1 - fee_rate - tax_rate))
                log.append({"日期": date, "動作": "再平衡賣出", "金額": round(abs(diff)), "原本比例": f"{current_ratio:.1%}"})
        
        history.append({
            "Date": date,
            "Total": shares * price + cash,
            "StockValue": shares * price,
            "Cash": cash,
            "Ratio": (shares * price) / (shares * price + cash) * 100
        })
        
    return pd.DataFrame(history).set_index("Date"), pd.DataFrame(log)

# --- 畫面呈現 ---
if run_btn:
    with st.spinner("正在獲取數據..."):
        s_lev, s_bm = get_data(start_date, end_date)
        
    if s_lev is not None:
        res_strat, res_log = run_backtest(s_lev, init_cash, target_ratio, trigger_threshold)
        bm_shares = (init_cash * (1 - fee_rate)) / s_bm.iloc[0]
        res_bm = (s_bm * bm_shares).to_frame(name="Total")
        
        # 指標計算
        def get_stats(df, initial):
            final = df['Total'].iloc[-1]
            ret = (final / initial - 1) * 100
            mdd = ((df['Total'].cummax() - df['Total']) / df['Total'].cummax()).max() * 100
            return final, ret, mdd

        f1, r1, d1 = get_stats(res_strat, init_cash)
        f2, r2, d2 = get_stats(res_bm, init_cash)

        st.subheader("📊 績效指標摘要")
        c_a, c_b = st.columns(2)
        with c_a:
            st.info(f"### 槓桿再平衡策略")
            m1, m2, m3 = st.columns(3)
            m1.metric("最終資產", f"${f1:,.0f}"); m2.metric("總報酬", f"{r1:+.1f}%"); m3.metric("最大回撤", f"-{d1:.1f}%")
        with c_b:
            st.info(f"### 0050 買入持有")
            m1, m2, m3 = st.columns(3)
            m1.metric("最終資產", f"${f2:,.0f}"); m2.metric("總報酬", f"{r2:+.1f}%"); m3.metric("最大回撤", f"-{d2:.1f}%")

        st.divider()

        # --- Plotly 圖表修正 (針對 Y 軸不完整問題) ---
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.1, # 增加子圖間距
                            subplot_titles=("📈 淨值成長曲線 (萬元)", "⚖️ 策略倉位比例變動 (%)", "📉 回撤深度比較 (%)"),
                            row_heights=[0.5, 0.25, 0.25])
        
        # 1. 淨值線
        fig.add_trace(go.Scatter(x=res_strat.index, y=res_strat['Total']/10000, name="槓桿策略", line=dict(color='#ff4b4b', width=2.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=res_bm.index, y=res_bm['Total']/10000, name="0050 持有", line=dict(color='#00d4ff', width=1.5, dash='dot')), row=1, col=1)
        
        # 2. 比例變動 (修正點：固定 Y 軸為 0-100)
        fig.add_trace(go.Scatter(x=res_strat.index, y=res_strat['Ratio'], name="股票比例 %", fill='tozeroy', line=dict(color='rgba(255, 75, 75, 0.5)')), row=2, col=1)
        fig.add_hline(y=target_ratio*100, line_dash="dash", line_color="white", row=2, col=1, annotation_text="目標比例")
        
        # 3. 回撤線
        dd_strat = (res_strat['Total'] / res_strat['Total'].cummax() - 1) * 100
        dd_bm = (res_bm['Total'] / res_bm['Total'].cummax() - 1) * 100
        fig.add_trace(go.Scatter(x=res_strat.index, y=dd_strat, name="策略回撤", fill='tozeroy', line=dict(color='#ff4b4b')), row=3, col=1)
        fig.add_trace(go.Scatter(x=res_bm.index, y=dd_bm, name="0050 回撤", fill='tozeroy', line=dict(color='#00d4ff')), row=3, col=1)

        # 全局佈局優化
        fig.update_layout(
            height=1000, 
            template="plotly_dark", 
            hovermode="x unified",
            margin=dict(l=60, r=30, t=80, b=60), # 增加左側邊距，確保 Y 軸數字不被切掉
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        # 關鍵修正：強制設定第二個圖 (比例圖) 的 Y 軸範圍
        fig.update_yaxes(range=[0, 100], ticksuffix="%", row=2, col=1)
        fig.update_yaxes(ticksuffix="w", row=1, col=1) # 第一圖加個 w 代表萬元
        fig.update_yaxes(ticksuffix="%", row=3, col=1) # 第三圖加 %

        st.plotly_chart(fig, use_container_width=True)

        if not res_log.empty:
            with st.expander(f"📋 查看再平衡歷史明細 (共 {len(res_log)} 次交易)"):
                st.dataframe(res_log, use_container_width=True)
    else:
        st.error("找不到資料，請確認代碼與日期。")
else:
    st.info("👈 請在左側設定參數後點擊「執行完整回測」。")

