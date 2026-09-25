import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import pytz

# ১. পেজ কনফিগারেশন
st.set_page_config(page_title="Early Entry Price Action Scanner", layout="wide")

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

st.title("⚡ Early Entry Fast Price Action Scanner")

# ==========================================
# ⚙️ SIDEBAR CONFIGURATION
# ==========================================
st.sidebar.header("⚙️ কন্ট্রোল প্যানেল")

if st.sidebar.button("🔄 ম্যানুয়াল রিফ্রেশ"):
    st.rerun()

st.sidebar.markdown("---")

timeframe = st.sidebar.selectbox(
    "⏱️ ক্যান্ডেল টাইমফ্রেম:",
    ["1m", "3m", "5m"],
    index=1
)

auto_refresh = st.sidebar.checkbox("⏱️ অটো-রিফ্রেশ চালু রাখুন", value=True)
if auto_refresh:
    refresh_interval = st.sidebar.slider("রিফ্রেশ ইন্টারভাল (সেকেন্ড):", min_value=5, max_value=30, value=10)
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
# 🧠 EARLY BREAKOUT PRICE ACTION ENGINE
# ===================================================
def get_data_and_signal(target_info, m_type, tf):
    ticker = target_info['ticker']
    strike_step = target_info['step']
    opt_mult = target_info['mult']
    asset_type = target_info.get('type', 'index')

    try:
        ticker_obj = yf.Ticker(ticker)
        df = ticker_obj.history(period="1d", interval="1m", auto_adjust=True)

        if df is None or df.empty or len(df) < 5:
            return None

        if tf == "3m":
            df = df.resample('3min').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
            }).dropna()
        elif tf == "5m":
            df = df.resample('5min').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
            }).dropna()

        # MCX Currency Adjustment
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

        latest = df.iloc[-1]
        
        # দ্রুত এন্ট্রির জন্য বিগত ৩টি ক্যান্ডেলের হাই ও লো হাইলাইট
        past_3_high = df['High'].iloc[-4:-1].max()
        past_3_low = df['Low'].iloc[-4:-1].min()

        price = round(latest['Close'], 2)
        
        ist_tz = pytz.timezone('Asia/Kolkata')
        candle_time = latest.name.strftime("%H:%M") if latest.name.tzinfo is None else latest.name.tz_convert(ist_tz).strftime("%H:%M")

        is_green = latest['Close'] >= latest['Open']
        is_red = latest['Close'] < latest['Open']

        signal = "NEUTRAL"
        status_text = "⚪ মার্কেট শান্ত / সাইডওয়েজ"
        color = "gray"

        # EARLY ENTRY TRIGGER (প্রাইজ আগের হাই/লো ক্রস করার সাথে সাথেই সিগন্যাল)
        if (price > past_3_high) and is_green:
            signal = "🚀 EARLY CALL BUY (CE)" if "Indices" in m_type else "🚀 EARLY BULLISH BREAKOUT"
            status_text = f"⚡ দ্রুত এন্ট্রি! বুলিশ ব্রেকআউট শুরু হয়েছে ({candle_time})"
            color = "green"

        elif (price < past_3_low) and is_red:
            signal = "🔻 EARLY PUT BUY (PE)" if "Indices" in m_type else "🔻 EARLY BEARISH BREAKDOWN"
            status_text = f"⚡ দ্রুত এন্ট্রি! বিয়ারিশ ব্রেকডাউন শুরু হয়েছে ({candle_time})"
            color = "red"

        else:
            signal = "WAIT & WATCH"
            status_text = "⚠️ উপযুক্ত মোমেন্টামের অপেক্ষা করুন"
            color = "orange"

        # টার্গেট ও স্টপলস
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
            option_suggestion = f"💡 **Suggested Strike:** ITM {itm_ce} CE | ATM {atm_strike} CE"
        elif color == "red" and "Indices" in m_type:
            option_suggestion = f"💡 **Suggested Strike:** ITM {itm_pe} PE | ATM {atm_strike} PE"

        return {
            'price': price,
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

            st.write(f"**Candle Time:** {data['candle_time']}")

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
