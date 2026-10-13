import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import datetime as dt
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Streamlit Page Config (Wide Layout)
st.set_page_config(page_title="Pro Scalping Scanner v3.0", layout="wide")

# Custom CSS for Professional Terminal Look
st.markdown("""
    <style>
        .block-container {
            padding-top: 0.5rem;
            padding-bottom: 0.5rem;
            padding-left: 1rem;
            padding-right: 1rem;
        }
        h1 { font-size: 1.3rem !important; margin-bottom: 0rem; color: #00ffcc; }
        h3 { font-size: 0.95rem !important; margin-top: 0.2rem; margin-bottom: 0.2rem; }
        hr { margin-top: 0.3rem; margin-bottom: 0.3rem; }
    </style>
""", unsafe_allow_html=True)

# Safe Auto-Refresh Import
try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except ImportError:
    HAS_AUTOREFRESH = False

st.title("⚡ Pro Scalper: Stock, Commodity & Crypto Scanner")

# ---------------------------------------------------------
# 1. SIDEBAR MULTI-MARKET SELECTOR & REFRESH CONTROLLER
# ---------------------------------------------------------
st.sidebar.header("🎯 Market & Timeframe")

market_type = st.sidebar.radio(
    "Select Market Domain:",
    ["NSE Indices & Stocks", "MCX Commodities", "Crypto (24/7)"]
)

timeframe = st.sidebar.selectbox("Select Timeframe:", ["1m", "3m", "5m", "15m"], index=2)

st.sidebar.markdown("---")
st.sidebar.subheader("🔄 Refresh Settings")

if st.sidebar.button("🔄 Manual Refresh Now"):
    st.rerun()

refresh_option = st.sidebar.selectbox(
    "Auto Refresh Interval:",
    ["Off", "10 Seconds", "15 Seconds", "30 Seconds", "1 Minute"],
    index=0
)

if refresh_option != "Off" and HAS_AUTOREFRESH:
    sec_map = {"10 Seconds": 10, "15 Seconds": 15, "30 Seconds": 30, "1 Minute": 60}
    interval_ms = sec_map[refresh_option] * 1000
    st_autorefresh(interval=interval_ms, key="scanner_autorefresh")

if st.sidebar.button("🗑️ Clear Signal Memory"):
    st.session_state.signal_memory = []
    st.rerun()

# Asset Tickers
if market_type == "NSE Indices & Stocks":
    tickers = {
        "NIFTY 50": "^NSEI",
        "BANK NIFTY": "^NSEBANK",
        "SENSEX": "^BSESN",
        "RELIANCE": "RELIANCE.NS"
    }
elif market_type == "MCX Commodities":
    tickers = {
        "CRUDE OIL": "CL=F",
        "NATURAL GAS": "NG=F",
        "GOLD": "GC=F",
        "SILVER": "SI=F"
    }
else:  # Crypto
    tickers = {
        "BITCOIN (BTC)": "BTC-USD",
        "ETHEREUM (ETH)": "ETH-USD",
        "SOLANA (SOL)": "SOL-USD",
        "BINANCE COIN (BNB)": "BNB-USD"
    }

# Signal Memory Initialization
if "signal_memory" not in st.session_state:
    st.session_state.signal_memory = []

# ---------------------------------------------------------
# 2. INDICATOR CALCULATIONS (ROBUST & DYNAMIC)
# ---------------------------------------------------------
def calculate_indicators(df):
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0.0)).rolling(window=14, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=14, min_periods=1).mean()
    rs = gain / (loss + 1e-10)
    df['RSI'] = 100 - (100 / (1 + rs))

    rsi = df['RSI']
    rsi_min = rsi.rolling(window=14, min_periods=1).min()
    rsi_max = rsi.rolling(window=14, min_periods=1).max()
    stoch_rsi = (rsi - rsi_min) / (rsi_max - rsi_min + 1e-10)
    df['Stoch_K'] = stoch_rsi.rolling(window=3, min_periods=1).mean() * 100
    df['Stoch_D'] = df['Stoch_K'].rolling(window=3, min_periods=1).mean()

    candle_range = df['High'] - df['Low']
    candle_range = candle_range.replace(0, 1e-10)
    df['Buying_Power'] = ((df['Close'] - df['Low']) / candle_range) * 100
    df['Selling_Power'] = ((df['High'] - df['Close']) / candle_range) * 100

    median_price = (df['High'] + df['Low']) / 2
    ao = median_price.rolling(window=5, min_periods=1).mean() - median_price.rolling(window=34, min_periods=1).mean()
    df['AO'] = ao

    return df

@st.cache_data(ttl=5)
def fetch_data_safe(symbol, tf, m_type):
    fetch_p = "2d" if m_type == "Crypto (24/7)" else "1d"
    return yf.download(symbol, period=fetch_p, interval=tf, progress=False)

# ---------------------------------------------------------
# 3. LIVE DATA FETCHING ENGINE (TOP SECTION)
# ---------------------------------------------------------
st.subheader(f"📊 Live Scan Dashboard - [{market_type}] ({timeframe})")

scanned_results = []

for name, symbol in tickers.items():
    try:
        data = fetch_data_safe(symbol, timeframe, market_type)
        if data.empty or len(data) < 2:
            continue
        
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        df = calculate_indicators(data.copy())
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]

        price = round(float(curr['Close']), 2)
        rsi = round(float(curr['RSI']), 2)
        stoch_k = round(float(curr['Stoch_K']), 2)
        stoch_d = round(float(curr['Stoch_D']), 2)
        buy_pwr = round(float(curr['Buying_Power']), 1)
        sell_pwr = round(float(curr['Selling_Power']), 1)
        ao_val = round(float(curr['AO']), 2)

        is_green = curr['Close'] > curr['Open']
        is_red = curr['Close'] < curr['Open']

        stoch_bull_cross = (prev['Stoch_K'] <= prev['Stoch_D']) and (stoch_k > stoch_d)
        stoch_bear_cross = (prev['Stoch_K'] >= prev['Stoch_D']) and (stoch_k < stoch_d)

        is_call = stoch_bull_cross and is_green and buy_pwr >= 50.0
        is_put = stoch_bear_cross and is_red and sell_pwr >= 50.0

        signal_type = "NEUTRAL"
        if is_call:
            signal_type = "🚀 CALL (CE)"
        elif is_put:
            signal_type = "🔻 PUT (PE)"

        scanned_results.append({
            "Asset": name,
            "Price": price,
            "RSI": rsi,
            "Stoch %K/%D": f"{stoch_k} / {stoch_d}",
            "AO": ao_val,
            "Buy%": f"{buy_pwr}%",
            "Sell%": f"{sell_pwr}%",
            "Signal": signal_type
        })

        if signal_type != "NEUTRAL":
            ist_time = datetime.utcnow() + dt.timedelta(hours=5, minutes=30)
            candle_time = ist_time.strftime("%I:%M:%S %p")
            
            already_exists = any(
                item['Asset'] == name and item['Time (IST)'] == candle_time 
                for item in st.session_state.signal_memory
            )
            
            if not already_exists:
                st.session_state.signal_memory.append({
                    "Time (IST)": candle_time,
                    "Market": market_type,
                    "Asset": name,
                    "Signal": signal_type,
                    "Price": price,
                    "RSI": rsi,
                    "AO": ao_val,
                    "Buy/Sell Power": f"B: {buy_pwr}% | S: {sell_pwr}%",
                    "Stoch K/D": f"{stoch_k}/{stoch_d}"
                })
                
                if len(st.session_state.signal_memory) > 15:
                    st.session_state.signal_memory = st.session_state.signal_memory[-15:]

    except Exception:
        continue

# Render Scan Results Table (Optimized Height 130px)
if scanned_results:
    res_df = pd.DataFrame(scanned_results)
    st.dataframe(res_df, use_container_width=True, height=130)
else:
    st.warning("Fetching live market data...")

# ---------------------------------------------------------
# 4. LIVE PROFESSIONAL CANDLESTICK & INDICATORS (EXPANDED CHART)
# ---------------------------------------------------------
st.markdown("---")

c_head1, c_head2 = st.columns([2, 2])
with c_head1:
    st.subheader("🖥️ Live Visual Chart")
with c_head2:
    selected_asset = st.selectbox("Select Asset for Chart:", list(tickers.keys()), label_visibility="collapsed")

asset_symbol = tickers[selected_asset]

try:
    c_data = fetch_data_safe(asset_symbol, timeframe, market_type)
    
    if isinstance(c_data.columns, pd.MultiIndex):
        c_data.columns = c_data.columns.get_level_values(0)

    if not c_data.empty and len(c_data) >= 2:
        df_chart = calculate_indicators(c_data.copy()).tail(50)

        # UTC to IST Timezone Conversion
        df_chart.index = pd.to_datetime(df_chart.index)
        if df_chart.index.tz is None:
            df_chart.index = df_chart.index.tz_localize('UTC').tz_convert('Asia/Kolkata')
        else:
            df_chart.index = df_chart.index.tz_convert('Asia/Kolkata')

        # Create Expanded 4 Subplots for Better Clarity
        fig = make_subplots(
            rows=4, cols=1, 
            shared_xaxes=True, 
            vertical_spacing=0.03,
            row_heights=[0.42, 0.19, 0.19, 0.20],
            subplot_titles=(f"{selected_asset} Price Movement", "RSI (14)", "Stochastic RSI", "Awesome Oscillator (AO)")
        )

        # 1. Candlestick Chart
        fig.add_trace(
            go.Candlestick(
                x=df_chart.index,
                open=df_chart['Open'],
                high=df_chart['High'],
                low=df_chart['Low'],
                close=df_chart['Close'],
                name="Price",
                increasing_line_color='#089981',
                decreasing_line_color='#f23645'
            ),
            row=1, col=1
        )

        # 2. RSI Line
        fig.add_trace(
            go.Scatter(x=df_chart.index, y=df_chart['RSI'], name="RSI", line=dict(color='#ab47bc', width=1.5)),
            row=2, col=1
        )
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

        # 3. Stochastic RSI (%K & %D)
        fig.add_trace(
            go.Scatter(x=df_chart.index, y=df_chart['Stoch_K'], name="Stoch %K", line=dict(color='#2196f3', width=1.2)),
            row=3, col=1
        )
        fig.add_trace(
            go.Scatter(x=df_chart.index, y=df_chart['Stoch_D'], name="Stoch %D", line=dict(color='#ff9800', width=1.2)),
            row=3, col=1
        )
        fig.add_hline(y=80, line_dash="dash", line_color="red", row=3, col=1)
        fig.add_hline(y=20, line_dash="dash", line_color="green", row=3, col=1)

        # 4. Awesome Oscillator (AO)
        ao_colors = []
        for i in range(len(df_chart)):
            if i == 0:
                ao_colors.append('#089981')
            else:
                if df_chart['AO'].iloc[i] >= df_chart['AO'].iloc[i-1]:
                    ao_colors.append('#089981')
                else:
                    ao_colors.append('#f23645')

        fig.add_trace(
            go.Bar(
                x=df_chart.index,
                y=df_chart['AO'],
                name="AO",
                marker_color=ao_colors
            ),
            row=4, col=1
        )
        fig.add_hline(y=0, line_dash="solid", line_color="gray", row=4, col=1)

        # Expanded Chart Layout (Height 360px for crystal clear visibility)
        fig.update_layout(
            template="plotly_dark",
            xaxis_rangeslider_visible=False,
            height=360,
            margin=dict(l=5, r=5, t=20, b=5),
            showlegend=False,
            hovermode="x unified",
            font=dict(size=10)
        )

        fig.update_xaxes(
            type='date',
            tickformat="%I:%M %p",
            row=4, col=1
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("⚠️ Insufficient intraday data available.")
except Exception as e:
    st.error(f"Error loading chart: {e}")

# ---------------------------------------------------------
# 5. SIGNAL MEMORY TABLE (BOTTOM SECTION - FIXED 15 SLOTS)
# ---------------------------------------------------------
st.markdown("---")
st.subheader("📜 Confirmed Signal Memory Log (Last 15)")

mem_list = st.session_state.signal_memory[::-1]
fixed_rows = []

for i in range(15):
    if i < len(mem_list):
        fixed_rows.append(mem_list[i])
    else:
        fixed_rows.append({
            "Time (IST)": "-",
            "Market": "-",
            "Asset": "-",
            "Signal": "-",
            "Price": "-",
            "RSI": "-",
            "AO": "-",
            "Buy/Sell Power": "-",
            "Stoch K/D": "-"
        })

mem_df = pd.DataFrame(fixed_rows)
st.dataframe(mem_df, use_container_width=True, height=140)
