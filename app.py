import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import datetime as dt

# Streamlit Page Config
st.set_page_config(page_title="Pro Scalping Scanner v3.0", layout="wide")

# Safe Auto-Refresh Import
try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except ImportError:
    HAS_AUTOREFRESH = False

st.title("⚡ Pro Scalper: Stock, Commodity & Crypto Scanner")
st.markdown("---")

# ---------------------------------------------------------
# 1. SIDEBAR MULTI-MARKET SELECTOR & REFRESH CONTROLLER
# ---------------------------------------------------------
st.sidebar.header("🎯 Market & Timeframe Options")

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

if "signal_memory" not in st.session_state:
    st.session_state.signal_memory = []

# ---------------------------------------------------------
# 2. INDICATOR CALCULATIONS
# ---------------------------------------------------------
def calculate_indicators(df):
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df['RSI'] = 100 - (100 / (1 + rs))

    rsi = df['RSI']
    rsi_min = rsi.rolling(window=14).min()
    rsi_max = rsi.rolling(window=14).max()
    stoch_rsi = (rsi - rsi_min) / (rsi_max - rsi_min + 1e-10)
    df['Stoch_K'] = stoch_rsi.rolling(window=3).mean() * 100
    df['Stoch_D'] = df['Stoch_K'].rolling(window=3).mean()

    candle_range = df['High'] - df['Low']
    candle_range = candle_range.replace(0, 1e-10)
    df['Buying_Power'] = ((df['Close'] - df['Low']) / candle_range) * 100
    df['Selling_Power'] = ((df['High'] - df['Close']) / candle_range) * 100

    return df

# ---------------------------------------------------------
# 3. LIVE DATA FETCHING ENGINE
# ---------------------------------------------------------
st.subheader(f"📊 Live Scan Dashboard - [{market_type}] ({timeframe})")

scanned_results = []

for name, symbol in tickers.items():
    try:
        data = yf.download(symbol, period="5d", interval=timeframe, progress=False)
        if data.empty or len(data) < 15:
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

        is_green = curr['Close'] > curr['Open']
        is_red = curr['Close'] < curr['Open']

        stoch_bull_cross = (prev['Stoch_K'] <= prev['Stoch_D']) and (stoch_k > stoch_d)
        stoch_bear_cross = (prev['Stoch_K'] >= prev['Stoch_D']) and (stoch_k < stoch_d)

        # Signal Logic
        is_call = stoch_bull_cross and is_green and buy_pwr >= 50.0
        is_put = stoch_bear_cross and is_red and sell_pwr >= 50.0

        signal_type = "NEUTRAL"
        if is_call:
            signal_type = "🚀 CONFIRMED CALL (CE)"
        elif is_put:
            signal_type = "🔻 CONFIRMED PUT (PE)"

        scanned_results.append({
            "Asset": name,
            "Price": price,
            "RSI": rsi,
            "Stoch %K/%D": f"{stoch_k} / {stoch_d}",
            "Buy Power %": f"{buy_pwr}%",
            "Sell Power %": f"{sell_pwr}%",
            "Signal": signal_type
        })

        if signal_type != "NEUTRAL":
            ist_time = datetime.utcnow() + dt.timedelta(hours=5, minutes=30)
            candle_time = ist_time.strftime("%I:%M:%S %p")
            
            st.session_state.signal_memory.append({
                "Time (IST)": candle_time,
                "Market": market_type,
                "Asset": name,
                "Signal": signal_type,
                "Price": price,
                "RSI": rsi,
                "Buy/Sell Power": f"B: {buy_pwr}% | S: {sell_pwr}%",
                "Stoch K/D": f"{stoch_k}/{stoch_d}"
            })
            
            if len(st.session_state.signal_memory) > 15:
                st.session_state.signal_memory = st.session_state.signal_memory[-15:]

    except Exception:
        continue

# Render Results
if scanned_results:
    res_df = pd.DataFrame(scanned_results)
    st.dataframe(res_df, use_container_width=True)
else:
    st.warning("Fetching live market data... Please wait a moment.")

# ---------------------------------------------------------
# 4. SIGNAL MEMORY TABLE (PERMANENTLY VISIBLE)
# ---------------------------------------------------------
st.markdown("---")
st.subheader("📜 Confirmed Signal Memory Log (Saved History - Last 15)")

if len(st.session_state.signal_memory) > 0:
    mem_df = pd.DataFrame(st.session_state.signal_memory)
    st.dataframe(mem_df.iloc[::-1], use_container_width=True)
else:
    empty_df = pd.DataFrame(columns=["Time (IST)", "Market", "Asset", "Signal", "Price", "RSI", "Buy/Sell Power", "Stoch K/D"])
    st.dataframe(empty_df, use_container_width=True)
    st.info("No strong signals triggered yet. Monitoring market momentum...")

# ---------------------------------------------------------
# 5. LIVE INTERACTIVE CANDLESTICK CHART (100% WORKING FIX)
# ---------------------------------------------------------
st.markdown("---")
st.subheader("🖥️ Live Interactive Candlestick Chart")

selected_asset = st.selectbox("Select Asset for Live Visual Chart:", list(tickers.keys()))
asset_symbol = tickers[selected_asset]

try:
    c_data = yf.download(asset_symbol, period="2d", interval=timeframe, progress=False)
    
    if isinstance(c_data.columns, pd.MultiIndex):
        c_data.columns = c_data.columns.get_level_values(0)

    if not c_data.empty and len(c_data) >= 5:
        c_df = c_data.tail(60)

        # HTML and CSS Chart Generation (No JS Block/No White Screen)
        candles_html = ""
        for idx, row in c_df.iterrows():
            o, h, l, c = row['Open'], row['High'], row['Low'], row['Close']
            color = "#089981" if c >= o else "#f23645"
            time_str = idx.strftime('%H:%M')
            
            candles_html += f"""
            <div style="display:inline-block; margin:0 2px; text-align:center; font-size:10px; color:#aaa;">
                <div style="height:100px; display:flex; flex-direction:column; align-items:center; justify-content:center;">
                    <div style="font-weight:bold; color:{color};">{round(c, 1)}</div>
                    <div style="width:2px; height:15px; background-color:{color};"></div>
                    <div style="width:12px; height:35px; background-color:{color}; border-radius:2px;"></div>
                    <div style="width:2px; height:15px; background-color:{color};"></div>
                </div>
                <div>{time_str}</div>
            </div>
            """

        # Custom Streamlit HTML View with Dark Theme
        st.markdown(
            f"""
            <div style="background-color:#131722; padding:20px; border-radius:10px; border:1px solid #2a2e39;">
                <div style="color:#d1d4dc; font-size:16px; font-weight:bold; margin-bottom:10px;">
                    📈 {selected_asset} Live Price Movement ({timeframe})
                </div>
                <div style="overflow-x:auto; white-space:nowrap; padding:10px 0;">
                    {candles_html}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.info("Fetching market data for chart...")
except Exception as e:
    st.error(f"Unable to load chart data: {e}")
