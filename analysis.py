"""
analysis.py
-----------
موتور تحلیل تکنیکال با ۶ اندیکاتور استاندارد بازار.

⚠️ شفافیت مهم:
این تحلیل صرفاً پردازش آماری داده‌های گذشته است. هیچ اندیکاتوری،
حتی ترکیب چند اندیکاتور، آینده‌ی قیمت را با قطعیت پیش‌بینی نمی‌کند.
بازارهای مالی ذاتاً دارای عدم قطعیت هستند. این ابزار برای کمک به
تصمیم‌گیری آگاهانه طراحی شده، نه برای تضمین سود.

منبع داده: Twelve Data API (رایگان، نیاز به کلید دارد)
چرا نه Binance؟ سرورهای Railway به‌دلیل محدودیت جغرافیایی توسط
Binance مسدود می‌شوند (خطای HTTP 451). Twelve Data این محدودیت را ندارد.
"""

import pandas as pd
import numpy as np
import requests


# ============================================================
# بخش ۱: دریافت داده قیمت
# ============================================================

def get_market_data(symbol, api_key, interval="1h", outputsize=200):
    """
    دریافت داده‌ی کندل (OHLC) از Twelve Data.

    symbol: فرمت همیشه با اسلش است:
            کریپتو → "BTC/USD", "ETH/USD"
            فارکس  → "EUR/USD", "GBP/USD", "USD/JPY"
    interval: 1min, 5min, 15min, 30min, 1h, 4h, 1day
    outputsize: تعداد کندل اخیر (حداکثر معمول پلن رایگان: کافی برای 200-500)
    """
    if not api_key:
        raise ValueError(
            "کلید API تنظیم نشده است. از twelvedata.com یک کلید رایگان "
            "بگیرید و به‌عنوان متغیر محیطی TWELVE_DATA_API_KEY در Railway قرار دهید."
        )

    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": api_key,
    }
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    raw = response.json()

    if raw.get("status") == "error" or "values" not in raw:
        raise ValueError(f"خطای API: {raw.get('message', 'پاسخ نامعتبر از سرور داده')}")

    df = pd.DataFrame(raw["values"])
    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)

    # داده از API جدید→قدیم می‌آید؛ برمی‌گردانیم به ترتیب زمانی صحیح (قدیم→جدید)
    df = df.iloc[::-1].reset_index(drop=True)
    return df[["open", "high", "low", "close"]]


# ============================================================
# بخش ۲: اندیکاتورهای تکنیکال
# ============================================================

def calculate_rsi(df, period=14):
    """RSI: اشباع خرید (بالای ۷۰) یا اشباع فروش (پایین ۳۰)."""
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_macd(df, fast=12, slow=26, signal=9):
    """MACD: تفاوت دو EMA که قدرت و جهت مومنتوم را نشان می‌دهد."""
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calculate_moving_averages(df, short_period=20, long_period=50):
    """میانگین متحرک ساده: تشخیص روند کوتاه‌مدت در برابر بلندمدت."""
    sma_short = df["close"].rolling(window=short_period).mean()
    sma_long = df["close"].rolling(window=long_period).mean()
    return sma_short, sma_long


def calculate_bollinger_bands(df, period=20, num_std=2):
    """
    باندهای بولینگر: محدوده‌ی نوسان عادی قیمت حول میانگین.
    قیمت نزدیک باند بالا → اشباع خرید نسبی
    قیمت نزدیک باند پایین → اشباع فروش نسبی
    """
    sma = df["close"].rolling(window=period).mean()
    std = df["close"].rolling(window=period).std()
    upper_band = sma + (std * num_std)
    lower_band = sma - (std * num_std)
    return upper_band, sma, lower_band


def calculate_stochastic(df, period=14, smooth_k=3):
    """
    اسیلاتور استوکاستیک: موقعیت قیمت فعلی نسبت به بازه‌ی بالا/پایین اخیر.
    بالای ۸۰ → اشباع خرید | پایین ۲۰ → اشباع فروش
    """
    low_min = df["low"].rolling(window=period).min()
    high_max = df["high"].rolling(window=period).max()
    k_percent = 100 * (df["close"] - low_min) / (high_max - low_min)
    k_smooth = k_percent.rolling(window=smooth_k).mean()
    return k_smooth


def calculate_atr(df, period=14):
    """
    Average True Range: میزان نوسان/ریسک بازار (نه جهت آن).
    عددی بالاتر یعنی نوسان بیشتر و ریسک بالاتر معامله.
    """
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.rolling(window=period).mean()


# ============================================================
# بخش ۳: تولید سیگنال نهایی (رای‌گیری وزن‌دار بین اندیکاتورها)
# ============================================================

def generate_signal(df):
    """
    ترکیب ۵ اندیکاتور جهت‌دار (RSI, MACD, MA, Bollinger, Stochastic)
    + ۱ اندیکاتور ریسک (ATR) برای ارائه‌ی یک تحلیل جامع.

    ⚠️ این یک رای‌گیری آماری بین اندیکاتورهای استاندارد است،
    نه پیش‌بینی قطعی آینده‌ی قیمت.
    """
    if len(df) < 55:
        return {"error": "داده کافی برای تحلیل دقیق وجود ندارد (حداقل ۵۵ کندل لازم است)."}

    rsi = calculate_rsi(df)
    macd_line, signal_line, histogram = calculate_macd(df)
    sma_short, sma_long = calculate_moving_averages(df)
    upper_band, mid_band, lower_band = calculate_bollinger_bands(df)
    stoch = calculate_stochastic(df)
    atr = calculate_atr(df)

    last_price = df["close"].iloc[-1]
    last_rsi = rsi.iloc[-1]
    last_macd = macd_line.iloc[-1]
    last_signal = signal_line.iloc[-1]
    last_sma_short = sma_short.iloc[-1]
    last_sma_long = sma_long.iloc[-1]
    last_upper = upper_band.iloc[-1]
    last_lower = lower_band.iloc[-1]
    last_stoch = stoch.iloc[-1]
    last_atr = atr.iloc[-1]

    votes = []
    details = []

    # ۱. RSI
    if last_rsi < 30:
        votes.append(1)
        details.append(f"🔹 RSI = {last_rsi:.1f} → اشباع فروش (احتمال برگشت صعودی)")
    elif last_rsi > 70:
        votes.append(-1)
        details.append(f"🔹 RSI = {last_rsi:.1f} → اشباع خرید (احتمال اصلاح نزولی)")
    else:
        votes.append(0)
        details.append(f"🔹 RSI = {last_rsi:.1f} → منطقه خنثی")

    # ۲. MACD
    if last_macd > last_signal:
        votes.append(1)
        details.append("🔹 MACD بالای خط سیگنال → مومنتوم صعودی")
    else:
        votes.append(-1)
        details.append("🔹 MACD پایین خط سیگنال → مومنتوم نزولی")

    # ۳. میانگین متحرک
    if last_sma_short > last_sma_long:
        votes.append(1)
        details.append("🔹 SMA کوتاه‌مدت بالای بلندمدت → روند صعودی")
    else:
        votes.append(-1)
        details.append("🔹 SMA کوتاه‌مدت پایین بلندمدت → روند نزولی")

    # ۴. باندهای بولینگر
    band_width = last_upper - last_lower
    position_in_band = (last_price - last_lower) / band_width if band_width > 0 else 0.5
    if position_in_band > 0.85:
        votes.append(-1)
        details.append("🔹 قیمت نزدیک باند بالای بولینگر → احتمال اشباع خرید")
    elif position_in_band < 0.15:
        votes.append(1)
        details.append("🔹 قیمت نزدیک باند پایین بولینگر → احتمال اشباع فروش")
    else:
        votes.append(0)
        details.append("🔹 قیمت داخل محدوده نرمال بولینگر")

    # ۵. استوکاستیک
    if last_stoch < 20:
        votes.append(1)
        details.append(f"🔹 استوکاستیک = {last_stoch:.1f} → اشباع فروش")
    elif last_stoch > 80:
        votes.append(-1)
        details.append(f"🔹 استوکاستیک = {last_stoch:.1f} → اشباع خرید")
    else:
        votes.append(0)
        details.append(f"🔹 استوکاستیک = {last_stoch:.1f} → منطقه خنثی")

    total_score = sum(votes)

    if total_score >= 3:
        final_verdict = "📈 تمایل کلی: صعودی قوی (Strong Bullish)"
    elif total_score >= 1:
        final_verdict = "📈 تمایل کلی: صعودی ضعیف (Weak Bullish)"
    elif total_score <= -3:
        final_verdict = "📉 تمایل کلی: نزولی قوی (Strong Bearish)"
    elif total_score <= -1:
        final_verdict = "📉 تمایل کلی: نزولی ضعیف (Weak Bearish)"
    else:
        final_verdict = "➖ تمایل کلی: خنثی / نامشخص"

    # سطح ریسک بر اساس ATR نسبت به قیمت
    atr_percent = (last_atr / last_price) * 100 if last_price > 0 else 0
    if atr_percent > 2:
        risk_level = "🔴 نوسان بالا — ریسک معامله زیاد است"
    elif atr_percent > 0.8:
        risk_level = "🟡 نوسان متوسط"
    else:
        risk_level = "🟢 نوسان پایین — بازار نسبتاً آرام"

    return {
        "price": round(last_price, 5),
        "details": details,
        "final_verdict": final_verdict,
        "score": total_score,
        "max_score": len(votes),
        "risk_level": risk_level,
        "atr_percent": round(atr_percent, 2),
        "disclaimer": (
            "⚠️ این تحلیل صرفاً بر اساس اندیکاتورهای تکنیکال گذشته است و "
            "تضمینی برای حرکت آینده قیمت نیست. همواره مدیریت ریسک و سرمایه "
            "را رعایت کنید."
        ),
    }
