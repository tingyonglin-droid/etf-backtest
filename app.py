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
st.set_page_config(page_title="正2價格再平衡診斷終端", page_icon="🔍", layout="wide")

# 自定義 CSS 讓圖表更清晰
st.markdown("""
    <style>
    .stApp { background-color: #0c0c0e; color: #e1e1e1; }
    .status-box { background-color: #161b22; padding: 20px; border-radius: 15px; border: 1px solid #30363d; margin-bottom: 20px; }
    </style>
""", unsafe_allow_html=True)

# --- 側邊欄控制 ---
with st.sidebar:
    st.header("🔍 策略診斷參數")
    
    col_a, col_b = st.columns(2)
    with col_a:
        start_date = st.date_input("開始日期", value=datetime(2015, 1, 1))
    with col_b:
        end_date = st.date_input("結束日期", value=datetime.today())
    
    init_cash = st.number_input("初始總資產 (TWD)", min_value=10000, value=1000000, step=100000)
    target_ratio = st.slider("目標股票比例 (%)", 10, 90, 50) / 100
    
    # 使用者要求的價格變動閾值
    price_trigger = st.slider("股價漲跌達多少 % 時再平衡？", 5, 100, 50) / 100

    st.divider()
    st.markdown("### 🛠️ 高級設定")
    fee_rate = 0.001425  
    tax_rate = 0.003
    # 允許使用者微調數據偏移 (有些數據源 Close 價包含除息調整)
    adj_close = st.checkbox("使用還原股價 (Adjusted Close)", value=True)
    
    run_btn = st.button("🚀 執行深度診斷", type="primary", use_container_width=True)

st.title("🔍 正2 價格再平衡：為什麼 2022 沒動？")
st.caption("本系統專門診斷「價格觸發」邏輯，監控每一個基準價格的變化點。")

# --- 數據抓取 ---
@st.cache_data(show_spinner=False)
def fetch_pro_data(symbol, start, end, adj):
    try:
        data = yf.download(symbol, start=start, end=end, auto_adjust=adj, progress=False)
        if data.empty: return None
        # 處理 yfinance 可能返回的 MultiIndex 或單列
        if isinstance(data.columns, pd.MultiIndex):
            return data['Close'].iloc[:, 0].dropna()
        return data['Close'].dropna()
    except:
        return None

# --- 回測核心邏輯 (加入基準價追蹤) ---
def run_diagnostic_backtest(prices, init_total, target_ratio, trigger_val):
    cash = init_total * (1 - target_ratio)
    base_price = float(prices.iloc[0]) # 初始基準價
    shares = (init_total * target_ratio * (1 - fee_rate)) / base_price
    
    history = []
    log = []

    for date, price in prices.items():
        price = float(price)
        stock_val = shares * price
        total_val = stock_val + cash
        
        # 計算相對於上次基準價的變動
        change_from_base = (price - base_price) / base_price
        
        # 診斷：計算距離觸發還差多少
        if change_from_base > 0:
            dist_to_trigger = (trigger_val - change_from_base) * 100
        else:
            dist_to_trigger = (abs(change_from_base) - trigger_val) * 100 # 負值代表還沒跌夠

        rebalanced = False
        action = ""
        if abs(change_from_base) >= trigger_val and date != prices.index[0]:
            rebalanced = True
            target_stock_val = total_val * target_ratio
            diff = target_stock_val - stock_val
            
            if diff > 0: # 買入
                shares += (diff / price * (1 - fee_rate))
                cash -= (diff / (1 - fee_rate))
                action = "再平衡買入"
            else: # 賣出
                shares -= (abs(diff) / price)
                cash += (abs(diff) * (1 - fee_rate - tax_rate))
                action = "再平衡賣出"
            
            log.append({
                "日期": date.strftime('%Y-%m-%d'),
                "動作": action,
                "成交價": round(price, 2),
                "前次基準價": round(base_price, 2),
                "變動幅度": f"{change_from_base:+.1%}",
                "總資產": f"{total_val:,.0f}"
            })
            
            # 更新基準價
            base_price = price

        history.append({
            "Date": date,
            "Total": total_val,
            "Price": price,
            "BasePrice": base_price,
            "ChangeFromBase": change_from_base * 100,
            "Ratio": (stock_val / total_val) * 100
        })
        
    return pd.DataFrame(history).set_index("Date"), pd.DataFrame(log)

# --- 畫面呈現 ---
if run_btn:
    with st.spinner("正在對齊歷史數據..."):
        s_lev = fetch_pro_data('00631L.TW', start_date, end_date, adj_close)
        s_bm = fetch_pro_data('0050.TW', start_date, end_date, adj_close)
        
    if s_lev is not None and s_bm is not None:
        # 對齊日期
        common = s_lev.index.intersection(s_bm.index)
        s_lev, s_bm = s_lev.loc[common], s_bm.loc[common]

        res_strat, res_log = run_diagnostic_backtest(s_lev, init_cash, target_ratio, price_trigger)
        
        # 績效卡片
        st.subheader("🚩 診斷結果總結")
        c1, c2, c3 = st.columns(3)
        final_eq = res_strat['Total'].iloc[-1]
        c1.metric("策略最終資產", f"${final_eq:,.0f}")
        c2.metric("再平衡總次數", f"{len(res_log)} 次")
        c3.metric("2022 年最低點價格", f"${s_lev.loc['2022'].min():.2f}")

        # --- 圖表部分 ---
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.07,
                            subplot_titles=("📈 淨值曲線與基準價變動點", "📏 相對於『上次基準價』的漲跌幅 (%)", "⚖️ 股票部位佔比變動 (%)"),
                            row_heights=[0.5, 0.25, 0.25])
        
        # 1. 淨值圖 + 基準價線
        fig.add_trace(go.Scatter(x=res_strat.index, y=res_strat['Total']/10000, name="策略淨值 (萬元)", line=dict(color='#ff4b4b', width=2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=res_strat.index, y=res_strat['BasePrice'], name="當前基準價", line=dict(color='rgba(255,255,255,0.3)', dash='dash'), yaxis="y2"), row=1, col=1)
        
        if not res_log.empty:
            res_log['日期'] = pd.to_datetime(res_log['日期'])
            b = res_log[res_log['動作'] == '再平衡買入']
            s = res_log[res_log['動作'] == '再平衡賣出']
            fig.add_trace(go.Scatter(x=b['日期'], y=pd.to_numeric(b['總資產'].str.replace(',',''))/10000, mode='markers', name='再平衡買入', marker=dict(symbol='triangle-up', color='#00ff88', size=12)), row=1, col=1)
            fig.add_trace(go.Scatter(x=s['日期'], y=pd.to_numeric(s['總資產'].str.replace(',',''))/10000, mode='markers', name='再平衡賣出', marker=dict(symbol='triangle-down', color='#f1c40f', size=12)), row=1, col=1)

        # 2. 漲跌幅監控 (關鍵診斷圖)
        fig.add_trace(go.Scatter(x=res_strat.index, y=res_strat['ChangeFromBase'], name="距基準價變動 %", line=dict(color='#ff9f43')), row=2, col=1)
        fig.add_hline(y=price_trigger*100, line_dash="dot", line_color="#f1c40f", row=2, col=1, annotation_text="賣出臨界")
        fig.add_hline(y=-price_trigger*100, line_dash="dot", line_color="#00ff88", row=2, col=1, annotation_text="買入臨界")

        # 3. 比例變動
        fig.add_trace(go.Scatter(x=res_strat.index, y=res_strat['Ratio'], name="股票比例 %", fill='tozeroy', fillcolor='rgba(255, 75, 75, 0.1)', line=dict(color='#ff4b4b', width=1)), row=3, col=1)

        fig.update_layout(height=1100, template="plotly_dark", hovermode="x unified",
                          margin=dict(l=80, r=40, t=80, b=100),
                          yaxis2=dict(title="股價 (基準)", overlaying="y", side="right", showgrid=False))
        
        fig.update_yaxes(ticksuffix="w", row=1, col=1)
        fig.update_yaxes(ticksuffix="%", row=2, col=1)
        fig.update_yaxes(range=[0, 100], ticksuffix="%", row=3, col=1)

        st.plotly_chart(fig, use_container_width=True)

        # 診斷分析文字
        st.info("💡 **診斷指南：** 觀察中間那張圖（橘色線）。如果橘色線在 2022 年沒有觸碰到下方的 **『買入臨界（綠色虛線）』**，這就解釋了為什麼沒有交易。這代表從「上一個基準點」算起，跌幅尚未達到你設定的百分比。")

        if not res_log.empty:
            with st.expander("📋 詳細交易紀錄"):
                st.table(res_log)
    else:
        st.error("無法抓取數據，請確認代碼與網路。")

