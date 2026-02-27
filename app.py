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
st.set_page_config(page_title="正2槓桿再平衡回測系統 Pro", page_icon="⚖️", layout="wide")

# 自定義 CSS 美化
st.markdown("""
    <style>
    .main { background-color: #0c0c0e; }
    .stMetric { background-color: #161b22; padding: 20px; border-radius: 15px; border: 1px solid #30363d; }
    div[data-testid="stExpander"] { border: 1px solid #30363d; background-color: #161b22; }
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
    
    # 修改觸發邏輯描述，讓使用者更明白
    trigger_type = st.radio("觸發模式", ["絕對百分比偏移 (推薦)", "相對比例偏移"])
    if trigger_type == "絕對百分比偏移 (推薦)":
        abs_threshold = st.slider("比例偏離目標幾 % 時觸發？", 1, 20, 5) / 100
    else:
        rel_threshold = st.slider("相對偏移百分比 (舊版邏輯 %)", 10, 100, 20) / 100

    st.divider()
    st.markdown("### 💸 交易成本設定")
    fee_rate = 0.001425  
    tax_rate = 0.003     
    
    run_btn = st.button("🚀 執行診斷回測", type="primary", use_container_width=True)

st.title("⚖️ 槓桿 ETF 搭配再平衡回測系統 Pro")
st.caption("透過數據診斷：為什麼 2022 年沒有觸發再平衡？")

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

# --- 回測核心邏輯 ---
def run_backtest(prices, init_total, target_ratio, trigger_val, is_absolute):
    cash = init_total * (1 - target_ratio)
    price_init = float(prices.iloc[0])
    shares = (init_total * target_ratio * (1 - fee_rate)) / price_init
    
    history = []
    log = []
    
    # 計算邊界線供圖表顯示
    if is_absolute:
        upper_limit = (target_ratio + trigger_val) * 100
        lower_limit = (target_ratio - trigger_val) * 100
    else:
        upper_limit = target_ratio * (1 + trigger_val) * 100
        lower_limit = target_ratio * (1 - trigger_val) * 100

    for date, price in prices.items():
        price = float(price)
        stock_val = shares * price
        total_val = stock_val + cash
        current_ratio = stock_val / total_val
        
        # 判斷觸發
        trigger_hit = False
        if is_absolute:
            if abs(current_ratio - target_ratio) >= trigger_val:
                trigger_hit = True
        else:
            if (abs(current_ratio - target_ratio) / target_ratio) >= trigger_val:
                trigger_hit = True

        if trigger_hit and date != prices.index[0]:
            target_stock_val = total_val * target_ratio
            diff = target_stock_val - stock_val
            
            if diff > 0: # 買入加碼
                cost = diff / (1 - fee_rate)
                if cash >= cost:
                    shares += (diff / price * (1 - fee_rate))
                    cash -= cost
                    log.append({"日期": date, "動作": "再平衡買入", "金額": round(diff), "Equity": total_val})
            else: # 賣出獲利
                shares -= (abs(diff) / price)
                cash += (abs(diff) * (1 - fee_rate - tax_rate))
                log.append({"日期": date, "動作": "再平衡賣出", "金額": round(abs(diff)), "Equity": total_val})
        
        history.append({
            "Date": date,
            "Total": shares * price + cash,
            "Ratio": current_ratio * 100
        })
        
    return pd.DataFrame(history).set_index("Date"), pd.DataFrame(log), upper_limit, lower_limit

# --- 畫面渲染 ---
if run_btn:
    with st.spinner("計算中..."):
        s_lev, s_bm = get_data(start_date, end_date)
        
    if s_lev is not None:
        # 執行回測
        thresh = abs_threshold if trigger_type == "絕對百分比偏移 (推薦)" else rel_threshold
        is_abs = (trigger_type == "絕對百分比偏移 (推薦)")
        res_strat, res_log, up_line, low_line = run_backtest(s_lev, init_cash, target_ratio, thresh, is_abs)
        
        # 0050 對照
        bm_shares = (init_cash * (1 - fee_rate)) / s_bm.iloc[0]
        res_bm = (s_bm * bm_shares).to_frame(name="Total")
        
        # 顯示績效
        final_val = res_strat['Total'].iloc[-1]
        st.subheader("📊 策略回測總結")
        c1, c2, c3 = st.columns(3)
        c1.metric("最終資產", f"${final_val:,.0f} 元")
        c2.metric("總報酬率", f"{(final_val/init_cash-1)*100:+.1f}%")
        c3.metric("再平衡次數", f"{len(res_log)} 次")

        st.divider()

        # --- Plotly 圖表 ---
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.1, 
                            subplot_titles=("📈 淨值曲線與交易點", "⚖️ 比例變動 (包含觸發邊界)", "📉 回撤深度 (%)"),
                            row_heights=[0.5, 0.25, 0.25])
        
        # 1. 淨值圖
        fig.add_trace(go.Scatter(x=res_strat.index, y=res_strat['Total']/10000, name="策略淨值", line=dict(color='#ff4b4b', width=2.5)), row=1, col=1)
        if not res_log.empty:
            b = res_log[res_log['動作'] == '再平衡買入']
            s = res_log[res_log['動作'] == '再平衡賣出']
            fig.add_trace(go.Scatter(x=b['日期'], y=b['Equity']/10000, mode='markers', name='買入加碼', marker=dict(symbol='triangle-up', color='#00ff88', size=12)), row=1, col=1)
            fig.add_trace(go.Scatter(x=s['日期'], y=s['Equity']/10000, mode='markers', name='賣出獲利', marker=dict(symbol='triangle-down', color='#f1c40f', size=12)), row=1, col=1)

        # 2. 比例圖 (包含診斷紅線)
        fig.add_trace(go.Scatter(x=res_strat.index, y=res_strat['Ratio'], name="目前股票比例 %", fill='tozeroy', fillcolor='rgba(255, 75, 75, 0.1)', line=dict(color='#ff4b4b')), row=2, col=1)
        fig.add_hline(y=target_ratio*100, line_dash="dash", line_color="white", row=2, col=1, annotation_text="目標")
        # 觸發邊界線 (診斷為什麼 2022 沒動的原因)
        fig.add_hline(y=up_line, line_dash="dot", line_color="red", opacity=0.5, row=2, col=1, annotation_text="賣出閾值")
        fig.add_hline(y=low_line, line_dash="dot", line_color="green", opacity=0.5, row=2, col=1, annotation_text="買入閾值")

        # 3. 回撤圖
        dd_strat = (res_strat['Total'] / res_strat['Total'].cummax() - 1) * 100
        dd_bm = (res_bm['Total'] / res_bm['Total'].cummax() - 1) * 100
        fig.add_trace(go.Scatter(x=res_strat.index, y=dd_strat, name="策略回撤", fill='tozeroy', line=dict(color='#ff4b4b', width=1)), row=3, col=1)
        fig.add_trace(go.Scatter(x=res_bm.index, y=dd_bm, name="0050 回撤", line=dict(color='#00d4ff', width=1)), row=3, col=1)

        fig.update_layout(height=1100, template="plotly_dark", hovermode="x unified", margin=dict(l=80, r=40, t=80, b=100))
        fig.update_yaxes(range=[0, 100], ticksuffix="%", row=2, col=1)
        
        st.plotly_chart(fig, use_container_width=True)
        
        st.warning(f"💡 **診斷提示：** 觀察中間那張圖。在 2022 年大跌時，股票比例（紅色區塊）是否有觸碰到底部的 **『買入閾值（綠色虛線）』**？如果沒有觸碰到，表示當時的跌幅還不足以讓比例偏移達到你設定的觸發門檻。")

    else:
        st.error("下載失敗。")
else:
    st.info("👈 請點擊「執行診斷回測」開始。")

