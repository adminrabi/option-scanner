import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import pytz

# ১. পেজ কনফিগারেশন
st.set_page_config(page_title="High Accuracy Institutional Scanner", layout="wide")

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

st.title("🎯 Strict High-Accuracy Breakout Scanner")

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
        {"name": "NIFTY 50", "ticker": "^NSEI", "step": 50, "mult": 2},
        {"name": "BANK NIFTY", "ticker": "^NSEBANK", "step": 100, "mult": 2},
        {"name": "FINNIFTY", "ticker": "NIFTY_FIN_SERVICE.NS", "step": 50, "mult": 2},
        {"name": "SENSEX", "ticker": "^BSESN", "step": 100, "mult": 2}
    ]
else:
    targets = [
        {"name": "CRUDE OIL", "ticker": "CL=F", "step": 50, "mult": 1},
        {"name": "NATURAL GAS", "ticker": "NG=F", "step": 5, "mult": 1},
        {"name": "GOLD", "ticker": "GC=F", "step": 100, "mult": 1},
        {"name": "SILVER", "ticker": "SI=F", "step": 250, "mult": 1}
    ]

# ===================================================
# 🧠 STRICT ACCURACY BREAKOUT ALGORITHM
# ===================================================
def get_data_and_signal(target_info, m_type, tf):
    ticker = target_info['ticker']
    strike_step = target_info['step']
    multiplier = target_info['mult']

    try:
        ticker_obj = yf.Ticker(ticker)

        # ৩ মিনিটের ক্যান্ডেল তৈরি
        if tf == "3m":
            df_1m = ticker_obj.history(period="1d", interval="1m", auto_adjust=True)
            if df_1m is None or df_1m.empty or len(df_1m) < 10:
                return None
            
            df = df_1m.resample('3min').agg({
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                'Close': 'last',
                'Volume': 'sum'
            }).dropna()
        else:
            df = ticker_obj.history(period="5d", interval="5m", auto_adjust=True)

        if df is None or df.empty or len(df) < 15:
            return None

        # ইন্ডিকেটর ক্যালকুলেশন
        df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
        df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()

        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-10)
        df['RSI'] = 100 - (100 / (1 + rs))

        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

        df['Vol_SMA'] = df['Volume'].rolling(window=10).mean()

        # ৫টি ক্যান্ডেলের স্ট্রং ব্রেকআউট লেভেল
        df['Prev_High_5'] = df['High'].shift(1).rolling(5).max()
        df['Prev_Low_5'] = df['Low'].shift(1).rolling(5).min()

        latest = df.iloc[-1]
        price = round(latest['Close'], 2)
        
        ist_tz = pytz.timezone('Asia/Kolkata')
        if latest.name.tzinfo is None:
            candle_time = latest.name.strftime("%H:%M")
        else:
            candle_time = latest.name.tz_convert(ist_tz).strftime("%H:%M")

        rsi = round(latest['RSI'], 2) if pd.notna(latest['RSI']) else 50.0
        vol_ratio = round(latest['Volume'] / latest['Vol_SMA'], 2) if (pd.notna(latest['Vol_SMA']) and latest['Vol_SMA'] > 0) else 1.0

        # কড়া শর্তসমূহ:
        is_high_volume = vol_ratio >= 1.15  # ভলিউম অন্তত ১৫% বেশি হতে হবে
        is_breakout_up = price > latest['Prev_High_5']
        is_breakout_down = price < latest['Prev_Low_5']

        # কড়া স্কোরিং (Required Score = 4)
        bull_score, bear_score = 0, 0

        if latest['EMA_9'] > latest['EMA_21']: bull_score += 1
        else: bear_score += 1

        if rsi >= 55: bull_score += 1
        elif rsi <= 45: bear_score += 1

        if latest['MACD'] > latest['MACD_Signal']: bull_score += 1
        else: bear_score += 1

        if is_breakout_up: bull_score += 2
        if is_breakout_down: bear_score += 2

        is_green_candle = latest['Close'] > latest['Open']
        is_red_candle = latest['Close'] < latest['Open']

        atm_strike = int(round(price / strike_step) * strike_step)
        itm_ce = atm_strike - (strike_step * multiplier)
        itm_pe = atm_strike + (strike_step * multiplier)

        sl, target1, target2 = 0.0, 0.0, 0.0
        option_suggestion = ""
        signal = "NEUTRAL"
        status_text = "⚪ মার্কেট শান্ত / কন্সোলিডেশন"
        color = "gray"

        target_pct_1 = 0.005
        target_pct_2 = 0.010
        sl_pct = 0.004

        # 🎯 কেবল কড়া শর্তের পরেই স্ট্রং সিগন্যাল আসবে
        if bull_score >= 4 and is_green_candle and is_high_volume:
            signal = "🚀 STRONG BUY CALL (CE)" if "Indices" in m_type else "🚀 CONFIRMED BULLISH BREAKOUT"
            status_text = f"🔥 কনফার্মড ভলিউম ব্রেকআউট! (Vol: {vol_ratio}x)"
            color = "green"
            sl = round(price * (1 - sl_pct), 2)
            target1 = round(price * (1 + target_pct_1), 2)
            target2 = round(price * (1 + target_pct_2), 2)
            
            if "Indices" in m_type:
                option_suggestion = f"💡 **Recommended Strike:** ITM {itm_ce} CE | ATM {atm_strike} CE"

        elif bear_score >= 4 and is_red_candle and is_high_volume:
            signal = "🔻 STRONG BUY PUT (PE)" if "Indices" in m_type else "🔻 CONFIRMED BEARISH BREAKDOWN"
            status_text = f"🔥 কনফার্মড ভলিউম ব্রেকডাউন! (Vol: {vol_ratio}x)"
            color = "red"
            sl = round(price * (1 + sl_pct), 2)
            target1 = round(price * (1 - target_pct_1), 2)
            target2 = round(price * (1 - target_pct_2), 2)
            
            if "Indices" in m_type:
                option_suggestion = f"💡 **Recommended Strike:** ITM {itm_pe} PE | ATM {atm_strike} PE"

        elif bull_score >= 2 or bear_score >= 2:
            signal = "WAIT & WATCH"
            status_text = "⚠️ মার্কেট পর্যবেক্ষণ করা হচ্ছে (অপেক্ষা করুন)"
            color = "orange"

        return {
            'price': price,
            'rsi': rsi,
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

            st.metric("স্পট প্রাইস", f"₹{data['price']}" if "Indices" in market_type else f"${data['price']}")

            st.write(f"**RSI:** {data['rsi']} | **Vol Ratio:** {data['vol_ratio']}x | **Time:** {data['candle_time']}")

            is_confirmed_signal = data['color'] in ['green', 'red']

            if is_confirmed_signal:
                st.markdown("---")
                st.write(f"🎯 **T1:** {data['target1']} | **T2:** {data['target2']}")
                st.write(f"🛑 **SL:** {data['sl']}")
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
                    "এন্ট্রি প্রাইস": f"{data['price']}",
                    "টার্গেট ১": f"{data['target1']}",
                    "টার্গেট ২": f"{data['target2']}",
                    "স্টপ লস": f"{data['sl']}"
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
