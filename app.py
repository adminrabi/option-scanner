import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import pytz

# ১. পেজ কনফিগারেশন
st.set_page_config(page_title="Price Action Multi-Indicator Scanner Pro", layout="wide")

# ২. অটো রিফ্রেশ
try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except ImportError:
    HAS_AUTOREFRESH = False

# ৩. সিগন্যাল মেমোরি
if 'signal_history_nse' not in st.session_state:
    st.session_state.signal_history_nse = []
if 'signal_history_mcx' not in st.session_state:
    st.session_state.signal_history_mcx = []
if 'last_logged_time' not in st.session_state:
    st.session_state.last_logged_time = {}

st.title("🎯 High-Precision Price Action & Dashboard Pro")

# ==========================================
# ⚙️ SIDEBAR CONFIGURATION
# ==========================================
st.sidebar.header("⚙️ কন্ট্রোল প্যানেল")

if st.sidebar.button("🔄 ম্যানুয়াল রিফ্রেশ"):
    st.rerun()

st.sidebar.markdown("---")

timeframe = st.sidebar.selectbox(
    "⏱️ ক্যান্ডেল টাইমফ্রেম:",
    ["3m", "5m"],
    index=1
)

auto_refresh = st.sidebar.checkbox("⏱️ অটো-রিফ্রেশ চালু রাখুন", value=True)
if auto_refresh:
    refresh_interval = st.sidebar.slider("রিফ্রেশ ইন্টারভাল (সেকেন্ড):", min_value=10, max_value=60, value=15)
    if HAS_AUTOREFRESH:
        st_autorefresh(interval=refresh_interval * 1000, key="datarefresh")

market_type = st.sidebar.radio(
    "মার্কেট সিলেক্ট করুন:",
    ["📊 NSE & BSE Indices", "🛢️ MCX Commodities"]
)

if market_type == "📊 NSE & BSE Indices":
    targets = [
        {"name": "NIFTY 50", "ticker": "^NSEI", "step": 50, "mult": 2, "type": "index"},
        {"name": "BANK NIFTY", "ticker": "^NSEBANK", "step": 100, "mult": 2, "type": "index"},
        {"name": "FINNIFTY", "ticker": "NIFTY_FIN_SERVICE.NS", "step": 50, "mult": 2, "type": "index"},
        {"name": "SENSEX", "ticker": "^BSESN", "step": 100, "mult": 2, "type": "index"}
    ]
else:
    targets = [
        {"name": "CRUDE OIL", "ticker": "CL=F", "step": 50, "mult": 1, "type": "crude"},
        {"name": "NATURAL GAS", "ticker": "NG=F", "step": 5, "mult": 1, "type": "ng"},
        {"name": "GOLD", "ticker": "GC=F", "step": 100, "mult": 1, "type": "gold"},
        {"name": "SILVER", "ticker": "SI=F", "step": 250, "mult": 1, "type": "silver"}
    ]

# ===================================================
# 🧠 INDICATORS & PRICE ACTION ENGINE
# ===================================================
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(series, fast=12, slow=26, signal=9):
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line

def get_data_and_signal(target_info, m_type, tf):
    ticker = target_info['ticker']
    strike_step = target_info['step']
    opt_mult = target_info['mult']
    asset_type = target_info.get('type', 'index')

    try:
        ticker_obj = yf.Ticker(ticker)
        df = None

        if tf == "3m":
            df_1m = ticker_obj.history(period="1d", interval="1m", auto_adjust=True)
            if df_1m is not None and not df_1m.empty and len(df_1m) >= 3:
                df = df_1m.resample('3min').agg({
                    'Open': 'first',
                    'High': 'max',
                    'Low': 'min',
                    'Close': 'last',
                    'Volume': 'sum'
                }).dropna()
        
        if df is None or df.empty or len(df) < 20:
            df = ticker_obj.history(period="1d", interval="5m", auto_adjust=True)

        if df is None or df.empty or len(df) < 20:
            return None

        # MCX Currency Adjustment
        usd_inr = 95.98  
        duty_tax = 1.15   

        if asset_type == "gold":
            factor = (10 / 31.10347) * usd_inr * duty_tax
            df['Close'] *= factor; df['Open'] *= factor; df['High'] *= factor; df['Low'] *= factor
        elif asset_type == "silver":
            factor = (1000 / 31.10347) * usd_inr * duty_tax
            df['Close'] *= factor; df['Open'] *= factor; df['High'] *= factor; df['Low'] *= factor
        elif asset_type in ["crude", "ng"]:
            factor = usd_inr
            df['Close'] *= factor; df['Open'] *= factor; df['High'] *= factor; df['Low'] *= factor

        # --------------------------------------------------
        # TECHNICAL INDICATORS
        # --------------------------------------------------
        df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['RSI'] = calculate_rsi(df['Close'], period=14)
        df['MACD'], df['MACD_Signal'] = calculate_macd(df['Close'])
        df['Avg_Vol'] = df['Volume'].rolling(window=10).mean()

        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        past_10_high = df['High'].iloc[-11:-1].max()
        past_10_low = df['Low'].iloc[-11:-1].min()

        price = round(latest['Close'], 2)
        price_change = round(latest['Close'] - prev['Close'], 2)
        pct_change = round((price_change / prev['Close']) * 100, 2)

        rsi_val = round(latest['RSI'], 1) if not np.isnan(latest['RSI']) else 50.0
        ema_val = latest['EMA_20']
        macd_val = latest['MACD']
        macd_sig_val = latest['MACD_Signal']
        
        # Vol Multiplier
        vol_ratio = round(latest['Volume'] / latest['Avg_Vol'], 1) if latest['Avg_Vol'] > 0 else 1.0

        ist_tz = pytz.timezone('Asia/Kolkata')
        candle_time = latest.name.strftime("%H:%M") if latest.name.tzinfo is None else latest.name.tz_convert(ist_tz).strftime("%H:%M")

        is_green = latest['Close'] > latest['Open']
        is_red = latest['Close'] < latest['Open']

        body_range = abs(latest['Close'] - latest['Open'])
        upper_wick = latest['High'] - max(latest['Close'], latest['Open'])
        lower_wick = min(latest['Close'], latest['Open']) - latest['Low']

        vol_spike = vol_ratio >= 1.2

        # Status Indicators
        is_above_ema = price > ema_val
        is_macd_bullish = macd_val > macd_sig_val

        signal = "WAIT & WATCH"
        status_text = "⚠️ মার্কেট সাইডওয়েজ বা কনসোলিডেশনে আছে"
        color = "orange"

        # --------------------------------------------------
        # STRICT SIGNAL LOGIC
        # --------------------------------------------------
        if (price > past_10_high) and is_green and is_above_ema and (rsi_val > 52) and is_macd_bullish and vol_spike and (upper_wick < body_range * 0.4):
            signal = "🚀 CONFIRMED CALL BUY (CE)" if "Indices" in m_type else "🚀 BULLISH BREAKOUT"
            status_text = f"🔥 স্ট্রং ১০-ক্যান্ডেল ব্রেকআউট ও মাল্টি-ইন্ডিকেটর কনফার্মড! ({candle_time})"
            color = "green"

        elif (price < past_10_low) and is_red and (not is_above_ema) and (rsi_val < 48) and (not is_macd_bullish) and vol_spike and (lower_wick < body_range * 0.4):
            signal = "🔻 CONFIRMED PUT BUY (PE)" if "Indices" in m_type else "🔻 BEARISH BREAKDOWN"
            status_text = f"🔥 স্ট্রং ১০-ক্যান্ডেল ব্রেকডাউন ও সেলিং প্রেসার! ({candle_time})"
            color = "red"

        # Targets & SL
        target_pct_1 = 0.005
        target_pct_2 = 0.010
        sl_pct = 0.0035

        sl, target1, target2 = 0.0, 0.0, 0.0
        if color == "green":
            sl = round(price * (1 - sl_pct), 2)
            target1 = round(price * (1 + target_pct_1), 2)
            target2 = round(price * (1 + target_pct_2), 2)
        elif color == "red":
            sl = round(price * (1 + sl_pct), 2)
            target1 = round(price * (1 - target_pct_1), 2)
            target2 = round(price * (1 - target_pct_2), 2)

        atm_strike = int(round(price / strike_step) * strike_step)
        itm_ce = atm_strike - (strike_step * opt_mult)
        itm_pe = atm_strike + (strike_step * opt_mult)

        option_suggestion = ""
        if color == "green" and "Indices" in m_type:
            option_suggestion = f"💡 **Recommended:** ITM {itm_ce} CE | ATM {atm_strike} CE"
        elif color == "red" and "Indices" in m_type:
            option_suggestion = f"💡 **Recommended:** ITM {itm_pe} PE | ATM {atm_strike} PE"

        return {
            'price': price,
            'change': price_change,
            'pct_change': pct_change,
            'rsi': rsi_val,
            'is_above_ema': is_above_ema,
            'is_macd_bullish': is_macd_bullish,
            'vol_ratio': vol_ratio,
            'signal': signal,
            'status_text': status_text,
            'color': color,
            'sl': sl,
            'target1': target1,
            'target2': target2,
            'option_suggestion': option_suggestion,
            'candle_time': candle_time
        }
    except Exception:
        return None

# ==========================================
# 🖥️ DASHBOARD DISPLAY
# ==========================================
cols = st.columns(len(targets))

for idx, item in enumerate(targets):
    data = get_data_and_signal(item, market_type, timeframe)
    with cols[idx]:
        st.subheader(f"📌 {item['name']}")
        if data:
            if data['color'] == 'green': st.success(f"### {data['signal']}\n\n{data['status_text']}")
            elif data['color'] == 'red': st.error(f"### {data['signal']}\n\n{data['status_text']}")
            elif data['color'] == 'orange': st.warning(f"### {data['signal']}\n\n{data['status_text']}")
            else: st.info(f"### {data['signal']}\n\n{data['status_text']}")

            # Price & Change Metric
            st.metric(
                label="লাইভ প্রাইস", 
                value=f"₹{data['price']:,.2f}", 
                delta=f"{data['change']:+.2f} ({data['pct_change']:+.2f}%)"
            )

            st.write(f"⏱️ **Time:** {data['candle_time']}")

            # --------------------------------------------------
            # MULTI-INDICATOR METRICS DASHBOARD (BADGES)
            # --------------------------------------------------
            st.markdown("##### 📊 ইন্ডিকেটর স্ট্যাটাস:")
            
            # 1. RSI Badge
            if data['rsi'] >= 55:
                st.markdown(f"🟢 **RSI:** `{data['rsi']}` (Bullish)")
            elif data['rsi'] <= 45:
                st.markdown(f"🔴 **RSI:** `{data['rsi']}` (Bearish)")
            else:
                st.markdown(f"⚪ **RSI:** `{data['rsi']}` (Neutral)")

            # 2. MACD Badge
            if data['is_macd_bullish']:
                st.markdown("🟢 **MACD:** `Bullish Cross`")
            else:
                st.markdown("🔴 **MACD:** `Bearish Cross`")

            # 3. EMA 20 Trend Badge
            if data['is_above_ema']:
                st.markdown("🟢 **20-EMA:** `Price Above`")
            else:
                st.markdown("🔴 **20-EMA:** `Price Below`")

            # 4. Volume Spike Badge
            if data['vol_ratio'] >= 1.2:
                st.markdown(f"🟢 **Volume:** `{data['vol_ratio']}x Spike`")
            else:
                st.markdown(f"⚪ **Volume:** `{data['vol_ratio']}x Normal`")

            # --------------------------------------------------
            # TARGETS & SL
            # --------------------------------------------------
            is_confirmed_signal = data['color'] in ['green', 'red']

            if is_confirmed_signal:
                st.markdown("---")
                st.write(f"🎯 **T1:** {data['target1']:,.2f} | **T2:** {data['target2']:,.2f}")
                st.write(f"🛑 **SL:** {data['sl']:,.2f}")
                if data['option_suggestion']:
                    st.caption(data['option_suggestion'])

            asset_name = item['name']
            last_time = st.session_state.last_logged_time.get(asset_name, "")
            
            if is_confirmed_signal and data['candle_time'] != last_time:
                timestamp = datetime.datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%I:%M:%S %p")
                log_entry = {
                    "সময়": timestamp,
                    "এসেট": asset_name,
                    "সিগন্যাল": data['signal'],
                    "এন্ট্রি প্রাইস": f"₹{data['price']:,.2f}",
                    "টার্গেট ১": f"₹{data['target1']:,.2f}",
                    "টার্গেট ২": f"₹{data['target2']:,.2f}",
                    "স্টপ লস": f"₹{data['sl']:,.2f}"
                }
                
                if "Indices" in market_type:
                    st.session_state.signal_history_nse.insert(0, log_entry)
                    if len(st.session_state.signal_history_nse) > 10: st.session_state.signal_history_nse.pop()
                else:
                    st.session_state.signal_history_mcx.insert(0, log_entry)
                    if len(st.session_state.signal_history_mcx) > 10: st.session_state.signal_history_mcx.pop()
                    
                st.session_state.last_logged_time[asset_name] = data['candle_time']
        else:
            st.error(f"⚠️ {item['name']} ডাটা পাওয়া যাচ্ছে না।")

# 📜 মেমোরি টেবিল
st.markdown("---")
if "Indices" in market_type:
    st.subheader("📜 NSE & BSE অপশন বায়িং সিগন্যাল মেমোরি")
    active_history = st.session_state.signal_history_nse
else:
    st.subheader("📜 MCX কমোডিটি সিগন্যাল মেমোরি")
    active_history = st.session_state.signal_history_mcx

if active_history:
    st.dataframe(pd.DataFrame(active_history), use_container_width=True)
else:
    st.info("এখনো পর্যন্ত কোনো স্ক্যালপিং সিগন্যাল মেমোরিতে রেকর্ড হয়নি।")
