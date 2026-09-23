import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import pytz

# ১. পেজ সেটআপ
st.set_page_config(page_title="Institutional Option Buying Scanner", layout="wide")

# ২. অটো-রিফ্রেশ সাপোর্ট
try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except ImportError:
    HAS_AUTOREFRESH = False

# ৩. মেমোরি হ্যান্ডলিং (১০টি সিগন্যাল লগার)
if 'signal_history_nse' not in st.session_state:
    st.session_state.signal_history_nse = []
if 'signal_history_mcx' not in st.session_state:
    st.session_state.signal_history_mcx = []
if 'last_logged_time' not in st.session_state:
    st.session_state.last_logged_time = {}

st.title("🎯 Fast Institutional Option Buying & Scalping Scanner")

# ==========================================
# ⚙️ SIDEBAR CONFIGURATION
# ==========================================
st.sidebar.header("⚙️ স্ক্যানার কন্ট্রোল")

if st.sidebar.button("🔄 ম্যানুয়াল রিফ্রেশ"):
    st.rerun()

st.sidebar.markdown("---")

# টাইমফ্রেম সিলেকশন (3m / 5m)
timeframe = st.sidebar.selectbox(
    "⏱️ ক্যান্ডেল টাইমফ্রেম সিলেক্ট করুন:",
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
    # MCX-এর জন্য নির্ভরযোগ্য আন্তর্জাতিক লাইভ ফিউচার্স
    targets = [
        {"name": "CRUDE OIL", "ticker": "CL=F", "step": 50, "mult": 1},
        {"name": "NATURAL GAS", "ticker": "NG=F", "step": 5, "mult": 1},
        {"name": "GOLD", "ticker": "GC=F", "step": 100, "mult": 1},
        {"name": "SILVER", "ticker": "SI=F", "step": 250, "mult": 1}
    ]

# ===================================================
# 🧠 OPTIMIZED ALGORITHM ENGINE
# ===================================================
def get_data_and_signal(target_info, m_type, tf):
    ticker = target_info['ticker']
    strike_step = target_info['step']
    multiplier = target_info['mult']

    try:
        ticker_obj = yf.Ticker(ticker)

        # ৩ মিনিটের জন্য ১ মিনিটের ডেটা রিস্যাম্পল করা হচ্ছে (ডাটা মিস হওয়া বন্ধ করতে)
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

        # ১. টেকনিক্যাল ইন্ডিকেটর
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

        low_min = df['Low'].rolling(window=14).min()
        high_max = df['High'].rolling(window=14).max()
        df['Stoch_K'] = 100 * ((df['Close'] - low_min) / ((high_max - low_min) + 1e-10))
        df['Stoch_D'] = df['Stoch_K'].rolling(window=3).mean()

        median_price = (df['High'] + df['Low']) / 2
        df['AO'] = median_price.rolling(window=5).mean() - median_price.rolling(window=34).mean()

        df['Vol_SMA'] = df['Volume'].rolling(window=10).mean()

        hl2 = (df['High'] + df['Low']) / 2
        atr = (df['High'] - df['Low']).rolling(window=10).mean()
        df['ST_Direction'] = np.where(df['Close'] > (hl2 - 3 * atr), 1, -1)

        # Fair Value Gap (FVG)
        df['Bullish_FVG'] = (df['Low'] > df['High'].shift(2))
        df['Bearish_FVG'] = (df['High'] < df['Low'].shift(2))

        latest = df.iloc[-1]
        price = round(latest['Close'], 2)
        
        # IST সময়
        ist_tz = pytz.timezone('Asia/Kolkata')
        if latest.name.tzinfo is None:
            candle_time = latest.name.strftime("%H:%M")
        else:
            candle_time = latest.name.tz_convert(ist_tz).strftime("%H:%M")

        rsi = round(latest['RSI'], 2) if pd.notna(latest['RSI']) else 50.0
        stoch_k = round(latest['Stoch_K'], 2) if pd.notna(latest['Stoch_K']) else 50.0
        
        vol_ratio = round(latest['Volume'] / latest['Vol_SMA'], 2) if (pd.notna(latest['Vol_SMA']) and latest['Vol_SMA'] > 0) else 1.0
        
        # 🎯 দ্রুত সিগন্যালের জন্য নতুন অপ্টিমাইজড ফিল্টার
        high_vol = vol_ratio >= 01.99  # অত্যন্ত সাধারণ ভলিউম সাপোর্ট থাকলেই সিগন্যাল দেবে
        required_score = 3             # ৬টির মধ্যে ৩টি শর্ত মিললেই স্ক্যালপিং সিগন্যাল ট্রিগার হবে

        has_bull_fvg = df['Bullish_FVG'].tail(2).any()
        has_bear_fvg = df['Bearish_FVG'].tail(2).any()

        bull_score, bear_score = 0, 0

        if latest['EMA_9'] > latest['EMA_21']: bull_score += 1
        else: bear_score += 1

        if rsi >= 50: bull_score += 1
        elif rsi <= 50: bear_score += 1

        if latest['ST_Direction'] > 0: bull_score += 1
        elif latest['ST_Direction'] < 0: bear_score += 1

        if latest['MACD'] > latest['MACD_Signal']: bull_score += 1
        else: bear_score += 1

        if stoch_k > latest['Stoch_D']: bull_score += 1
        else: bear_score += 1

        if latest['AO'] > 0: bull_score += 1
        else: bear_score += 1

        is_green_candle = latest['Close'] >= latest['Open']
        is_red_candle = latest['Close'] <= latest['Open']

        atm_strike = int(round(price / strike_step) * strike_step)
        itm_ce = atm_strike - (strike_step * multiplier)
        itm_pe = atm_strike + (strike_step * multiplier)

        sl, target1, target2 = 0.0, 0.0, 0.0
        option_suggestion = ""
        signal = "NEUTRAL"
        status_text = "⚪ মার্কেট কন্সোলিডেশন / ওয়েটিং"
        color = "gray"

        target_pct_1 = 0.004
        target_pct_2 = 0.008
        sl_pct = 0.003

        # BULLISH SIGNAL
        if bull_score >= required_score and is_green_candle and high_vol:
            if has_bull_fvg:
                signal = "🚀 HIGH ACCURACY BUY CALL (CE)" if "Indices" in m_type else "🚀 STRONG BUY"
                status_text = f"🔥 Institutional FVG Breakout! (Vol: {vol_ratio}x)"
            else:
                signal = "📈 BUY CALL (CE)" if "Indices" in m_type else "📈 BUY / BULLISH"
                status_text = f"⚡ স্ক্যালপিং মোমেন্টাম বাই (Vol: {vol_ratio}x)"
                
            color = "green"
            sl = round(price * (1 - sl_pct), 2)
            target1 = round(price * (1 + target_pct_1), 2)
            target2 = round(price * (1 + target_pct_2), 2)
            
            if "Indices" in m_type:
                option_suggestion = f"💡 **Recommended Strike:** ITM {itm_ce} CE | ATM {atm_strike} CE"

        # BEARISH SIGNAL
        elif bear_score >= required_score and is_red_candle and high_vol:
            if has_bear_fvg:
                signal = "🔻 HIGH ACCURACY BUY PUT (PE)" if "Indices" in m_type else "🔻 STRONG SELL"
                status_text = f"🔥 Institutional FVG Breakdown! (Vol: {vol_ratio}x)"
            else:
                signal = "📉 BUY PUT (PE)" if "Indices" in m_type else "📉 SELL / BEARISH"
                status_text = f"⚡ স্ক্যালপিং মোমেন্টাম সেল (Vol: {vol_ratio}x)"
                
            color = "red"
            sl = round(price * (1 + sl_pct), 2)
            target1 = round(price * (1 - target_pct_1), 2)
            target2 = round(price * (1 - target_pct_2), 2)
            
            if "Indices" in m_type:
                option_suggestion = f"💡 **Recommended Strike:** ITM {itm_pe} PE | ATM {atm_strike} PE"

        elif bull_score >= 2 or bear_score >= 2:
            signal = "WAIT & WATCH"
            status_text = "⚠️ মোমেন্টাম তৈরি হচ্ছে..."
            color = "orange"

        return {
            'price': price,
            'rsi': rsi,
            'stoch_k': stoch_k,
            'vol_ratio': vol_ratio,
            'has_fvg': "Yes ✅" if (has_bull_fvg or has_bear_fvg) else "No ❌",
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

            st.write(f"**RSI:** {data['rsi']} | **Stoch:** {data['stoch_k']} | **FVG Gap:** {data['has_fvg']}")

            is_confirmed_signal = data['color'] in ['green', 'red']

            if is_confirmed_signal:
                st.markdown("---")
                st.write(f"🎯 **T1:** {data['target1']} | **T2:** {data['target2']}")
                st.write(f"🛑 **SL:** {data['sl']}")
                st.info("⏱️ **Scalping Alert:** ৩-৬ মিনিটের বেশি হোল্ড করবেন না।")
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

# 📜 মেমোরি টেবিল (১০টি সেভড সিগন্যাল)
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
