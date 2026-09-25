import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import pytz

# ১. পেজ কনফিগারেশন
st.set_page_config(page_title="Institutional Smart Money Scanner", layout="wide")

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

st.title("🎯 Institutional Smart Money & Trend Reversal Scanner")

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
    index=0
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
# 🧠 INSTITUTIONAL SMART MONEY ALGORITHM
# ===================================================
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
        
        if df is None or df.empty or len(df) < 6:
            df = ticker_obj.history(period="1d", interval="5m", auto_adjust=True)

        if df is None or df.empty or len(df) < 6:
            return None

        # MCX Conversion Adjustments
        usd_inr = 94.00  
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

        # টেকনিক্যাল গণনা
        df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
        df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()

        # VWAP Approximated
        df['TP'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['VWAP'] = df['TP'].expanding().mean()

        # RSI calculation
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-10)
        df['RSI'] = 100 - (100 / (1 + rs))

        latest = df.iloc[-1]
        prev1 = df.iloc[-2]
        prev2 = df.iloc[-3]

        price = round(latest['Close'], 2)
        
        ist_tz = pytz.timezone('Asia/Kolkata')
        candle_time = latest.name.strftime("%H:%M") if latest.name.tzinfo is None else latest.name.tz_convert(ist_tz).strftime("%H:%M")

        rsi = round(latest['RSI'], 2) if pd.notna(latest['RSI']) else 50.0

        # ক্যান্ডেল মোমেন্টাম ফিল্টার (স্মার্ট মানি লজিক)
        is_green = latest['Close'] > latest['Open']
        is_red = latest['Close'] < latest['Open']

        # ক্যান্ডেলের সাইজ ও প্রাইস অ্যাকশন
        body_size = abs(latest['Close'] - latest['Open'])
        prev_high_3 = df['High'].iloc[-4:-1].max()
        prev_low_3 = df['Low'].iloc[-4:-1].min()

        # ব্রেকআউট কনফার্মেশন
        breakout_up = (price > prev_high_3) and is_green
        breakout_down = (price < prev_low_3) and is_red

        # ট্রেন্ড কন্ডিশন
        ema_bullish = latest['EMA_9'] > latest['EMA_21']
        ema_bearish = latest['EMA_9'] < latest['EMA_21']
        above_vwap = price >= latest['VWAP']
        below_vwap = price < latest['VWAP']

        signal = "NEUTRAL"
        status_text = "⚪ মার্কেট সাইডওয়েজ / কনসোলিডেশন"
        color = "gray"

        # কড়া প্রাতিষ্ঠানিক রুলস (NO FAKE SIGNALS)
        # Call Buy হতে হলে: ১) প্রাইজ ৩ ক্যান্ডেল হাই ভাঙতে হবে, ২) EMA বুলিশ হতে হবে, ৩) RSI ৫৫ এর উপরে, ৪) ক্যান্ডেল গ্রিন হতে হবে
        if breakout_up and ema_bullish and rsi >= 53 and above_vwap:
            signal = "🚀 CONFIRMED CALL BUY (CE)" if "Indices" in m_type else "🚀 STRONG BULLISH BREAKOUT"
            status_text = f"🔥 স্মার্ট মানি বাইং চালু হয়েছে! ({candle_time})"
            color = "green"

        # Put Buy হতে হলে: ১) প্রাইজ ৩ ক্যান্ডেল লো ভাঙতে হবে, ২) EMA বিয়ারিশ হতে হবে, ৩) RSI ৪৫ এর নিচে, ৪) ক্যান্ডেল রেড হতে হবে
        elif breakout_down and ema_bearish and rsi <= 47 and below_vwap:
            signal = "🔻 CONFIRMED PUT BUY (PE)" if "Indices" in m_type else "🔻 STRONG BEARISH BREAKDOWN"
            status_text = f"🔥 স্মার্ট মানি সেলিং চালু হয়েছে! ({candle_time})"
            color = "red"

        elif (ema_bullish and is_green) or (ema_bearish and is_red):
            signal = "WAIT & WATCH"
            status_text = "⚠️ রিভার্সাল বা ফেক আউট এড়াতে অপেক্ষা করুন"
            color = "orange"

        # টার্গেট ও স্টপলস হিসাব
        target_pct_1 = 0.004
        target_pct_2 = 0.008
        sl_pct = 0.003

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
            'rsi': rsi,
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

            st.metric("লাইভ প্রাইস", f"₹{data['price']:,.2f}")

            st.write(f"**RSI:** {data['rsi']} | **Time:** {data['candle_time']}")

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
