import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# Streamlit Page Config
st.set_page_config(page_title="Pro Scalping Scanner v3.0", layout="wide")

st.title("⚡ Pro Scalper: Stock, Commodity & Crypto Scanner")
st.markdown("---")

# ---------------------------------------------------------
# 1. SIDEBAR MULTI-MARKET SELECTOR
# ---------------------------------------------------------
st.sidebar.header("🎯 Market & Timeframe Options")

market_type = st.sidebar.radio(
    "Select Market Domain:",
    ["NSE Indices & Stocks", "MCX Commodities", "Crypto (24/7)"]
)

timeframe = st.sidebar.selectbox("Select Timeframe:", ["1m", "3m", "5m", "15m"], index=2)

# Define Asset List based on Market Selection
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

# Session State for Signal History (Memory)
if "signal_memory" not in st.session_state:
    st.session_state.signal_memory = []

# ---------------------------------------------------------
# 2. INDICATOR & MATH CALCULATIONS
# ---------------------------------------------------------
def calculate_indicators(df):
    # RSI (14)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df['RSI'] = 100 - (100 / (1 + rs))

    # Stochastic RSI (14, 3, 3)
    rsi = df['RSI']
    rsi_min = rsi.rolling(window=14).min()
    rsi_max = rsi.rolling(window=14).max()
    stoch_rsi = (rsi - rsi_min) / (rsi_max - rsi_min + 1e-10)
    df['Stoch_K'] = stoch_rsi.rolling(window=3).mean() * 100
    df['Stoch_D'] = df['Stoch_K'].rolling(window=3).mean()

    # EMA 20 & EMA 50
    df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()

    # Candle Buying/Selling Power (%)
    candle_range = df['High'] - df['Low']
    candle_range = candle_range.replace(0, 1e-10)
    df['Buying_Power'] = ((df['Close'] - df['Low']) / candle_range) * 100
    df['Selling_Power'] = ((df['High'] - df['Close']) / candle_range) * 100

    return df

# ---------------------------------------------------------
# 3. LIVE DATA FETCHING & SIGNAL ENGINE
# ---------------------------------------------------------
st.subheader(f"📊 Live Scan Dashboard - [{market_type}] ({timeframe})")

scanned_results = []

for name, symbol in tickers.items():
    try:
        data = yf.download(symbol, period="2d", interval=timeframe, progress=False)
        if len(data) < 20:
            continue
        
        # Clean MultiIndex Columns if present
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
        
        # Breakout Checks
        past_5_high = df['High'].iloc[-6:-1].max()
        past_5_low = df['Low'].iloc[-6:-1].min()

        # Signal Logic Conditions
        is_green = curr['Close'] > curr['Open']
        is_red = curr['Close'] < curr['Open']

        stoch_call_cross = (prev['Stoch_K'] <= prev['Stoch_D']) and (stoch_k > stoch_d)
        stoch_put_cross = (prev['Stoch_K'] >= prev['Stoch_D']) and (stoch_k < stoch_d)

        # CALL SIGNAL
        is_call = (
            (price > past_5_high or stoch_call_cross)
            and is_green
            and buy_pwr >= 68.0
            and rsi > 42 and rsi < 68
        )

        # PUT SIGNAL
        is_put = (
            (price < past_5_low or stoch_put_cross)
            and is_red
            and sell_pwr >= 68.0
            and rsi < 58 and rsi > 32
        )

        signal_type = "NEUTRAL"
        if is_call:
            signal_type = "🚀 CONFIRMED CALL (CE)"
        elif is_put:
            signal_type = "🔻 CONFIRMED PUT (PE)"

        # Save to Live View Table
        scanned_results.append({
            "Asset": name,
            "Price": price,
            "RSI": rsi,
            "Stoch %K/%D": f"{stoch_k} / {stoch_d}",
            "Buy Power %": f"{buy_pwr}%",
            "Sell Power %": f"{sell_pwr}%",
            "Signal": signal_type
        })

        # Save to Permanent Memory Log if Signal Triggered
        if signal_type != "NEUTRAL":
            candle_time = datetime.now().strftime("%H:%M:%S")
            st.session_state.signal_memory.append({
                "Time": candle_time,
                "Market": market_type,
                "Asset": name,
                "Signal": signal_type,
                "Price": price,
                "RSI": rsi,
                "Buy/Sell Power": f"B: {buy_pwr}% | S: {sell_pwr}%",
                "Stoch K/D": f"{stoch_k}/{stoch_d}"
            })

    except Exception as e:
        continue

# Render Live Results Table
if scanned_results:
    res_df = pd.DataFrame(scanned_results)
    st.dataframe(res_df, use_container_width=True)
else:
    st.warning("Fetching live market data...")

# ---------------------------------------------------------
# 4. SIGNAL MEMORY TABLE & TRADINGVIEW VISUAL
# ---------------------------------------------------------
st.markdown("---")
st.subheader("📜 Confirmed Signal Memory Log (Saved History)")

if len(st.session_state.signal_memory) > 0:
    mem_df = pd.DataFrame(st.session_state.signal_memory)
    st.dataframe(mem_df.iloc[::-1], use_container_width=True)
else:
    st.info("No strong signals triggered yet. Monitoring market momentum...")

# TradingView Embedded Visual Chart Section
st.markdown("---")
st.subheader("🖥️ Interactive TradingView Visual Screen")

selected_asset_symbol = tickers[st.selectbox("Select Asset for Live Visual Chart:", list(tickers.keys()))]

tv_widget_html = f"""
<div class="tradingview-widget-container" style="height:500px;width:100%;">
  <iframe src="https://s.tradingview.com/widgetembed/?frameElementId=tradingview_1&symbol={selected_asset_symbol}&interval=5&hidesidetoolbar=0&symboledit=1&saveimage=1&toolbarbg=f1f3f6&studies=RSI@tv-basicstudies%2CStochasticRSI@tv-basicstudies&theme=dark&style=1" 
          style="width: 100%; height: 500px; border: none;"></iframe>
</div>
"""
st.components.v1.html(tv_widget_html, height=520)
