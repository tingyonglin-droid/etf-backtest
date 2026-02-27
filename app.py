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
st.set_page_config(page_title="正2價格變動再平衡回測", page_icon="⚖️", layout="wide")

# 自定義 CSS
st.markdown("""
    <style>
    .main { background-color: #0c0c0e; }
    .stMetric { background-color: #161b22; padding: 20px; border-radius: 15px; border: 1px solid #30363d; }
    </style>
""", unsafe_allow_html=True)

# --- 側邊欄控制 ---
with st.sidebar:
    st.header("🧪 價格策略參數")
    
    col_a, col_b = st.columns(2)
    with col_a:
        start_date = st.date_input("開始日期", value=datetime(2015, 1, 1))
    with col_b:
        end_date = st.date_input("結束日期", value=datetime.today())
    
    init_cash = st.number_input("初始總資產 (TWD)", min_value=10000, value=1000000, step=100000)
    target_ratio = st.slider("目標股票比例 (%)", 10, 90, 50) / 100
    
    # 這裡改成使用者要求的「價格漲跌幅」觸發
    price_trigger = st.slider("股價漲跌幅達多少 % 時再平衡？", 10, 100, 50) / 100

    st.divider()
    st.markdown("### 💸 交易成本")
    fee_rate = 0.001425  
    tax_rate = 0.003     
    
    run_btn = st.button("🚀 執行價格回測", type="primary", use_container_width=True)

st.title("⚖️ 槓桿 ETF 價格再平衡系統")
st.caption(f"策略邏輯：當 00631L 股價相對於前次再平衡價格漲跌達 {price_trigger*100:.0f}% 時，重新配置至 {target_ratio*100:.0f}% 股票。")

# --- 數據抓取 ---
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
    except Exception:
        return None, None

# --- 回測核心邏輯 (股價觸發版) ---
def run_price_backtest(prices, init_total, target_ratio, price_trigger):
    cash = init_total * (1 - target_ratio)
    last_price = float(prices.iloc[0]) # 基準價格
    shares = (init_total * target_ratio * (1 - fee_rate)) / last_price
    
    history = []
    log = []

    for date, price in prices.items():
        price = float(price)
        stock_val = shares * price
        total_val = stock_val + cash
        
        # 計算相對於上次再平衡的價格漲跌幅
        price_change = (price - last_price) / last_price
        
        # 觸發判斷：漲跌超過設定閾值
        if abs(price_change) >= price_trigger and date != prices.index[0]:
            # 執行再平衡：將總價值重新按目標比例分配
            target_stock_val = total_val * target_ratio
            diff = target_stock_val - stock_val
            
            action_type = "再平衡買入" if diff > 0 else "再平衡賣出"
            
            if diff > 0: # 加碼
                shares += (diff / price * (1 - fee_rate))
                cash -= (diff / (1 - fee_rate))
            else: # 獲利了結
                shares -= (abs(diff) / price)
                cash += (abs(diff) * (1 - fee_rate - tax_rate))
            
            log.append({
                "日期": date, 
                "動作": action_type, 
                "標的價格": round(price, 2), 
                "基準變動": f"{price_change:+.1%}",
                "Equity": total_val
            })
            
            # 更新基準價格為當前價格
            last_price = price
        
        history.append({
            "Date": date,
            "Total": shares * price + cash,
            "StockValue": shares * price,
            "Price": price,
            "Ratio": (shares * price) / (shares * price + cash) * 100
        })
        
    return pd.DataFrame(history).set_index("Date"), pd.DataFrame(log)

# --- 畫面渲染 ---
if run_btn:
    with st.spinner("回測計算中..."):
        s_lev, s_bm = get_data(start_date, end_date)
        
    if s_lev is not None:
        res_strat, res_log = run_price_backtest(s_lev, init_cash, target_ratio, price_trigger)
        
        # 對照組 0050
        bm_shares = (init_cash * (1 - fee_rate)) / s_bm.iloc[0]
        res_bm = (s_bm * bm_shares).to_frame(name="Total")
        
        # 數據看板
        st.subheader("📊 回測績效摘要")
        c1, c2, c3 = st.columns(3)
        final_val = res_strat['Total'].iloc[-1]
        c1.metric("最終資產", f"${final_val:,.0f} 元")
        c2.metric("總報酬率", f"{(final_val/init_cash-1)*100:+.1f}%")
        c3.metric("再平衡交易次數", f"{len(res_log)} 次")

        st.divider()

        # --- Plotly 圖表 ---
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.08, 
                            subplot_titles=("📈 淨值曲線 (萬元) 與價格觸發點", "🏷️ 00631L 股價變動 (基準監控)", "⚖️ 資產比例變動 (%)"),
                            row_heights=[0.5, 0.25, 0.25])
        
        # 1. 淨值圖
        fig.add_trace(go.Scatter(x=res_strat.index, y=res_strat['Total']/10000, name="價格再平衡策略", line=dict(color='#ff4b4b', width=2.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=res_bm.index, y=res_bm['Total']/10000, name="0050 持有", line=dict(color='#00d4ff', width=1, dash='dot')), row=1, col=1)
        
        if not res_log.empty:
            b = res_log[res_log['動作'] == '再平衡買入']
            s = res_log[res_log['動作'] == '再平衡賣出']
            fig.add_trace(go.Scatter(x=b['日期'], y=b['Equity']/10000, mode='markers', name='低點加碼點', marker=dict(symbol='triangle-up', color='#00ff88', size=12)), row=1, col=1)
            fig.add_trace(go.Scatter(x=s['日期'], y=s['Equity']/10000, mode='markers', name='高點獲利點', marker=dict(symbol='triangle-down', color='#f1c40f', size=12)), row=1, col=1)

        # 2. 標的價格圖 (用來觀察為什麼觸發)
        fig.add_trace(go.Scatter(x=res_strat.index, y=res_strat['Price'], name="00631L 股價", line=dict(color='#ff9f43')), row=2, col=1)

        # 3. 比例圖
        fig.add_trace(go.Scatter(x=res_strat.index, y=res_strat['Ratio'], name="股票佔比 %", fill='tozeroy', fillcolor='rgba(255, 75, 75, 0.1)', line=dict(color='#ff4b4b', width=1)), row=3, col=1)
        fig.add_hline(y=target_ratio*100, line_dash="dash", line_color="white", row=3, col=1)

        fig.update_layout(height=1100, template="plotly_dark", hovermode="x unified", margin=dict(l=80, r=40, t=80, b=100))
        fig.update_yaxes(ticksuffix="w", row=1, col=1)
        fig.update_yaxes(range=[0, 100], ticksuffix="%", row=3, col=1)

        st.plotly_chart(fig, use_container_width=True)

        if not res_log.empty:
            with st.expander("📋 查看詳細交易明細"):
                st.dataframe(res_log, use_container_width=True)
    else:
        st.error("數據獲取失敗。")

