"""
analysis.py
-----------
این فایل مسئول تحلیل تکنیکال است.

⚠️ نکته مهم و صادقانه:
این تحلیل‌ها بر اساس اندیکاتورهای استاندارد بازار (RSI, MACD, میانگین متحرک) هستند.
هیچ اندیکاتوری "پیش‌بینی قطعی" آینده‌ی قیمت نمی‌کند. این ابزار صرفاً
داده‌های گذشته را پردازش می‌کند و یک دیدگاه آماری ارائه می‌دهد، نه تضمین سود.

برای داده‌ی قیمت زنده، باید یک API واقعی (مثل Binance برای کریپتو یا
Alpha Vantage / Twelve Data برای فارکس) متصل کنید. در این نسخه یک تابع
نمونه برای دریافت داده گذاشته شده که باید کلید API خودتان را در آن قرار دهید.
"""

import pandas as pd
import numpy as np
import requests


# ============================================================
# بخش ۱: دریافت داده قیمت
# ============================================================

def get_market_data(symbol, api_key, interval="1h", outputsize=200):
    """
    دریافت داده‌ی کندل (OHLC) از Twelve Data برای کریپتو یا فارکس.

    ⚠️ چرا از Binance استفاده نمی‌کنیم؟
    سرورهای Railway روی IP رنج‌هایی هستند که Binance به‌خاطر محدودیت
    قانونی/منطقه‌ای مسدودشان کرده (خطای HTTP 451). Twelve Data این
    محدودیت را ندارد، برای همین برای هر دو بازار از همین یک منبع
    استفاده می‌کنیم.

    symbol: فرمت Twelve Data همیشه با اسلش است:
            کریپتو → "BTC/USD", "ETH/USD"
            فارکس  → "EUR/USD", "GBP/USD"
    """
    if not api_key:
        raise ValueError(
            "برای دریافت داده به یک API Key نیاز است. "
            "از twelvedata.com یک کلید رایگان بگیرید و در Railway به عنوان "
            "متغیر محیطی TWELVE_DATA_API_KEY قرار دهید."
        )

    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": api_key,
    }
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    raw = response.json()

    if "values" not in raw:
        raise ValueError(f"خطا در دریافت داده: {raw.get('message', 'نامشخص')}")

    df = pd.DataFrame(raw["values"])
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["open"] = df["open"].astype(float)
    df = df.iloc[::-1].reset_index(drop=True)
    return df[["open", "high", "low", "close"]]

    if "values" not in raw:
        raise ValueError(f"خطا در دریافت داده: {raw.get('message', 'نامشخص')}")

    df = pd.DataFrame(raw["values"])
    df = df.rename(columns={"close": "close", "high": "high", "low": "low", "open": "open"})
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["open"] = df["open"].astype(float)

    # داده از API به ترتیب نزولی (جدید به قدیم) می‌آد، برمی‌گردونیم به ترتیب صحیح
    df = df.iloc[::-1].reset_index(drop=True)
    return df[["open", "high", "low", "close"]]


# ============================================================
# بخش ۲: اندیکاتورهای تکنیکال
# ============================================================

def calculate_rsi(df, period=14):
    """
    RSI (Relative Strength Index): نشون می‌ده دارایی در منطقه‌ی
    "اشباع خرید" (بالای 70، احتمال اصلاح به پایین) یا
    "اشباع فروش" (پایین 30، احتمال برگشت به بالا) هست یا نه.
    """
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_macd(df, fast=12, slow=26, signal=9):
    """
    MACD: تفاوت بین دو میانگین متحرک نمایی (EMA) که روند و قدرت
    حرکت قیمت رو نشون می‌ده. وقتی خط MACD از خط سیگنال رد بشه،
    معمولاً به عنوان سیگنال تغییر روند در نظر گرفته می‌شه.
    """
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()

    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


def calculate_moving_averages(df, short_period=20, long_period=50):
    """
    میانگین متحرک ساده (SMA): وقتی میانگین کوتاه‌مدت از بلندمدت
    رد بشه (Golden Cross / Death Cross)، سیگنال احتمالی روند می‌ده.
    """
    sma_short = df["close"].rolling(window=short_period).mean()
    sma_long = df["close"].rolling(window=long_period).mean()
    return sma_short, sma_long


# ============================================================
# بخش ۳: تولید سیگنال نهایی (ترکیب اندیکاتورها)
# ============================================================

def generate_signal(df):
    """
    این تابع همه‌ی اندیکاتورها رو حساب می‌کنه و یک تحلیل خوانا
    برای کاربر تولید می‌کنه. خروجی یک دیکشنری شامل جزئیات است.

    ⚠️ این یک "رای‌گیری" ساده بین اندیکاتورهاست، نه پیش‌بینی قطعی.
    """
    if len(df) < 50:
        return {"error": "داده کافی برای تحلیل وجود ندارد (حداقل ۵۰ کندل لازم است)."}

    rsi = calculate_rsi(df)
    macd_line, signal_line, histogram = calculate_macd(df)
    sma_short, sma_long = calculate_moving_averages(df)

    last_rsi = rsi.iloc[-1]
    last_macd = macd_line.iloc[-1]
    last_signal = signal_line.iloc[-1]
    last_sma_short = sma_short.iloc[-1]
    last_sma_long = sma_long.iloc[-1]
    last_price = df["close"].iloc[-1]

    votes = []  # هر اندیکاتور یک رای می‌ده: +1 صعودی، -1 نزولی، 0 خنثی

    # رای RSI
    if last_rsi < 30:
        votes.append(1)
        rsi_comment = f"RSI = {last_rsi:.1f} → منطقه اشباع فروش (احتمال برگشت صعودی)"
    elif last_rsi > 70:
        votes.append(-1)
        rsi_comment = f"RSI = {last_rsi:.1f} → منطقه اشباع خرید (احتمال اصلاح نزولی)"
    else:
        votes.append(0)
        rsi_comment = f"RSI = {last_rsi:.1f} → منطقه خنثی"

    # رای MACD
    if last_macd > last_signal:
        votes.append(1)
        macd_comment = "خط MACD بالای خط سیگنال → مومنتوم صعودی"
    else:
        votes.append(-1)
        macd_comment = "خط MACD پایین خط سیگنال → مومنتوم نزولی"

    # رای میانگین متحرک
    if last_sma_short > last_sma_long:
        votes.append(1)
        ma_comment = "میانگین کوتاه‌مدت بالای بلندمدت → روند صعودی"
    else:
        votes.append(-1)
        ma_comment = "میانگین کوتاه‌مدت پایین بلندمدت → روند نزولی"

    total_score = sum(votes)

    if total_score >= 2:
        final_verdict = "📈 تمایل کلی: صعودی (Bullish)"
    elif total_score <= -2:
        final_verdict = "📉 تمایل کلی: نزولی (Bearish)"
    else:
        final_verdict = "➖ تمایل کلی: نامشخص / خنثی"

    return {
        "price": round(last_price, 5),
        "rsi_comment": rsi_comment,
        "macd_comment": macd_comment,
        "ma_comment": ma_comment,
        "final_verdict": final_verdict,
        "score": total_score,
        "disclaimer": (
            "⚠️ این تحلیل صرفاً بر اساس اندیکاتورهای تکنیکال گذشته است "
            "و تضمینی برای حرکت آینده قیمت نیست. مدیریت ریسک و سرمایه را "
            "فراموش نکنید."
        ),
    }
