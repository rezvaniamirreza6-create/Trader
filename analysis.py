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


def calculate_adx(df, period=14):
    """
    ADX (Average Directional Index): قدرت روند را اندازه می‌گیرد
    (نه جهت آن). این مهم‌ترین تفاوت تحلیل حرفه‌ای با آماتور است:
    تحلیلگر آماتور فقط می‌پرسد "روند صعودی یا نزولی؟"
    تحلیلگر حرفه‌ای اول می‌پرسد "آیا اصلاً روندی وجود دارد؟"

    ADX > 25  → بازار روند‌دار (Trending) — اندیکاتورهای روندی (MACD, MA) معتبرترند
    ADX < 20  → بازار رنج/خنثی (Ranging) — اسیلاتورها (RSI, Stochastic) معتبرترند
    """
    up_move = df["high"].diff()
    down_move = -df["low"].diff()

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

    atr_smooth = true_range.rolling(window=period).mean()
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr_smooth)
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr_smooth)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.rolling(window=period).mean()
    return adx, plus_di, minus_di


def calculate_ichimoku(df, conv_period=9, base_period=26, span_b_period=52):
    """
    ایچیموکو (نسخه‌ی ساده‌شده برای سیگنال): یک سیستم چندبعدی ژاپنی که
    همزمان روند، حمایت/مقاومت، و مومنتوم را در یک نگاه نشان می‌دهد.

    Tenkan-sen (خط تبدیل): میانگین بالا/پایین ۹ کندل اخیر — مومنتوم سریع
    Kijun-sen (خط پایه): میانگین بالا/پایین ۲۶ کندل اخیر — روند میان‌مدت
    Senkou Span A/B: ابر ایچیموکو — ناحیه حمایت/مقاومت پویا
    """
    conv_line = (df["high"].rolling(conv_period).max() + df["low"].rolling(conv_period).min()) / 2
    base_line = (df["high"].rolling(base_period).max() + df["low"].rolling(base_period).min()) / 2
    span_a = (conv_line + base_line) / 2
    span_b = (df["high"].rolling(span_b_period).max() + df["low"].rolling(span_b_period).min()) / 2
    return conv_line, base_line, span_a, span_b


# ============================================================
# بخش ۳: تولید سیگنال نهایی (رای‌گیری وزن‌دار بین اندیکاتورها)
# ============================================================

def generate_signal(df, user_weight_multipliers=None):
    """
    موتور تحلیل دو مرحله‌ای (سبک تحلیلگر حرفه‌ای):

    مرحله ۱ - تشخیص رژیم بازار با ADX:
        آیا بازار روند‌دار است یا در حال نوسان رنج (بدون روند مشخص)؟
        این تشخیص، وزن هر اندیکاتور را در مرحله بعد تغییر می‌دهد.

    مرحله ۲ - رای‌گیری وزن‌دار متناسب با رژیم:
        در بازار روند‌دار → MACD, MA, Ichimoku وزن بیشتر می‌گیرند
        در بازار رنج     → RSI, Stochastic, Bollinger وزن بیشتر می‌گیرند
        (این دقیقاً تفاوت یک تحلیل حرفه‌ای با رای‌گیری ساده و یکسان‌وزن
        تحلیلگرهای آماتور است — اندیکاتور روندی در بازار بی‌روند، و
        اسیلاتور اشباع در بازار پرروند، هر دو می‌توانند گمراه‌کننده باشند.)

    user_weight_multipliers: دیکشنری اختیاری برای استراتژی شخصی کاربر،
        مثلاً {"rsi": 2.0, "macd": 0.5, "ma": 1.0, "bollinger": 1.0, "stochastic": 1.0}.
        این ضرایب روی وزن‌های پایه (رژیم‌محور) ضرب می‌شوند - یعنی هوش
        تشخیص رژیم حفظ می‌ماند، فقط تأکید شخصی کاربر روی هر اندیکاتور
        اضافه می‌شود. اگر None باشد، فقط وزن‌دهی استاندارد رژیم اعمال می‌شود.

    ⚠️ توجه: این هنوز یک پیش‌بینی قطعی نیست. تطبیق وزن با رژیم بازار،
    دقت آماری مدل را بهبود می‌دهد اما عدم قطعیت ذاتی بازار را از بین
    نمی‌برد. همیشه با مدیریت ریسک معامله کنید.
    """
    if len(df) < 60:
        return {"error": "داده کافی برای تحلیل دقیق وجود ندارد (حداقل ۶۰ کندل لازم است)."}

    rsi = calculate_rsi(df)
    macd_line, signal_line, histogram = calculate_macd(df)
    sma_short, sma_long = calculate_moving_averages(df)
    upper_band, mid_band, lower_band = calculate_bollinger_bands(df)
    stoch = calculate_stochastic(df)
    atr = calculate_atr(df)
    adx, plus_di, minus_di = calculate_adx(df)
    conv_line, base_line, span_a, span_b = calculate_ichimoku(df)

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
    last_adx = adx.iloc[-1]
    last_plus_di = plus_di.iloc[-1]
    last_minus_di = minus_di.iloc[-1]
    last_conv = conv_line.iloc[-1]
    last_base = base_line.iloc[-1]
    last_span_a = span_a.iloc[-1]
    last_span_b = span_b.iloc[-1]

    # نگه‌داری مقدار pandas به‌جای NaN خام (در صروت کافی نبودن داده ADX)
    if pd.isna(last_adx):
        last_adx = 0.0

    # ============================================================
    # مرحله ۱: تشخیص رژیم بازار
    # ============================================================
    is_trending = last_adx > 25
    is_ranging = last_adx < 20
    # بین ۲۰ تا ۲۵ → رژیم گذار (transitional)، وزن‌ها متوسط می‌مانند

    if is_trending:
        regime = "روند‌دار (Trending)"
        # در رژیم روند‌دار: اندیکاتورهای روندی وزن بیشتر، اسیلاتورها وزن کمتر
        weights = {"rsi": 0.7, "macd": 1.5, "ma": 1.5, "bollinger": 0.6, "stochastic": 0.6, "ichimoku": 1.5}
    elif is_ranging:
        regime = "رنج / بدون روند مشخص (Ranging)"
        # در رژیم رنج: اسیلاتورهای اشباع وزن بیشتر، اندیکاتورهای روندی وزن کمتر
        weights = {"rsi": 1.5, "macd": 0.6, "ma": 0.6, "bollinger": 1.5, "stochastic": 1.5, "ichimoku": 0.7}
    else:
        regime = "گذار / نامشخص (Transitional)"
        weights = {"rsi": 1.0, "macd": 1.0, "ma": 1.0, "bollinger": 1.0, "stochastic": 1.0, "ichimoku": 1.0}

    # اعمال استراتژی شخصی کاربر (در صورت وجود) - ضرب در وزن پایه رژیم‌محور
    if user_weight_multipliers:
        for indicator_key, multiplier in user_weight_multipliers.items():
            if indicator_key in weights:
                weights[indicator_key] = weights[indicator_key] * multiplier

    votes = []   # هر آیتم: (امتیاز خام -1/0/+1, وزن)
    details = []

    # ۱. RSI
    if last_rsi < 30:
        votes.append((1, weights["rsi"]))
        details.append(f"🔹 RSI = {last_rsi:.1f} → اشباع فروش (احتمال برگشت صعودی)")
    elif last_rsi > 70:
        votes.append((-1, weights["rsi"]))
        details.append(f"🔹 RSI = {last_rsi:.1f} → اشباع خرید (احتمال اصلاح نزولی)")
    else:
        votes.append((0, weights["rsi"]))
        details.append(f"🔹 RSI = {last_rsi:.1f} → منطقه خنثی")

    # ۲. MACD
    if last_macd > last_signal:
        votes.append((1, weights["macd"]))
        details.append("🔹 MACD بالای خط سیگنال → مومنتوم صعودی")
    else:
        votes.append((-1, weights["macd"]))
        details.append("🔹 MACD پایین خط سیگنال → مومنتوم نزولی")

    # ۳. میانگین متحرک
    if last_sma_short > last_sma_long:
        votes.append((1, weights["ma"]))
        details.append("🔹 SMA کوتاه‌مدت بالای بلندمدت → روند صعودی")
    else:
        votes.append((-1, weights["ma"]))
        details.append("🔹 SMA کوتاه‌مدت پایین بلندمدت → روند نزولی")

    # ۴. باندهای بولینگر
    band_width = last_upper - last_lower
    position_in_band = (last_price - last_lower) / band_width if band_width > 0 else 0.5
    if position_in_band > 0.85:
        votes.append((-1, weights["bollinger"]))
        details.append("🔹 قیمت نزدیک باند بالای بولینگر → احتمال اشباع خرید")
    elif position_in_band < 0.15:
        votes.append((1, weights["bollinger"]))
        details.append("🔹 قیمت نزدیک باند پایین بولینگر → احتمال اشباع فروش")
    else:
        votes.append((0, weights["bollinger"]))
        details.append("🔹 قیمت داخل محدوده نرمال بولینگر")

    # ۵. استوکاستیک
    if last_stoch < 20:
        votes.append((1, weights["stochastic"]))
        details.append(f"🔹 استوکاستیک = {last_stoch:.1f} → اشباع فروش")
    elif last_stoch > 80:
        votes.append((-1, weights["stochastic"]))
        details.append(f"🔹 استوکاستیک = {last_stoch:.1f} → اشباع خرید")
    else:
        votes.append((0, weights["stochastic"]))
        details.append(f"🔹 استوکاستیک = {last_stoch:.1f} → منطقه خنثی")

    # ۶. ایچیموکو (موقعیت قیمت نسبت به ابر + تقاطع تنکان/کیجون)
    cloud_top = max(last_span_a, last_span_b)
    cloud_bottom = min(last_span_a, last_span_b)
    if last_price > cloud_top and last_conv > last_base:
        votes.append((1, weights["ichimoku"]))
        details.append("🔹 ایچیموکو: قیمت بالای ابر + تقاطع صعودی تنکان/کیجون")
    elif last_price < cloud_bottom and last_conv < last_base:
        votes.append((-1, weights["ichimoku"]))
        details.append("🔹 ایچیموکو: قیمت پایین ابر + تقاطع نزولی تنکان/کیجون")
    else:
        votes.append((0, weights["ichimoku"]))
        details.append("🔹 ایچیموکو: قیمت داخل ابر یا سیگنال‌های متناقض → بلاتکلیف")

    # ۷. ADX (قدرت روند، برچسب جهت با DI+ / DI-)
    if is_trending:
        adx_direction = "صعودی" if last_plus_di > last_minus_di else "نزولی"
        details.append(f"🔹 ADX = {last_adx:.1f} → روند قوی و {adx_direction} در جریان است")
    elif is_ranging:
        details.append(f"🔹 ADX = {last_adx:.1f} → روند ضعیف، بازار در حالت رنج/نوسان")
    else:
        details.append(f"🔹 ADX = {last_adx:.1f} → قدرت روند نامشخص (رژیم گذار)")

    # ============================================================
    # مرحله ۲: جمع‌بندی وزن‌دار
    # ============================================================
    weighted_sum = sum(score * weight for score, weight in votes)
    max_possible = sum(weight for _, weight in votes)
    normalized_score = weighted_sum / max_possible if max_possible > 0 else 0  # بازه تقریبی [-1, +1]

    if normalized_score >= 0.35:
        final_verdict = "📈 تمایل کلی: صعودی قوی (Strong Bullish)"
        total_score = 3
    elif normalized_score >= 0.12:
        final_verdict = "📈 تمایل کلی: صعودی ضعیف (Weak Bullish)"
        total_score = 1
    elif normalized_score <= -0.35:
        final_verdict = "📉 تمایل کلی: نزولی قوی (Strong Bearish)"
        total_score = -3
    elif normalized_score <= -0.12:
        final_verdict = "📉 تمایل کلی: نزولی ضعیف (Weak Bearish)"
        total_score = -1
    else:
        final_verdict = "➖ تمایل کلی: خنثی / نامشخص"
        total_score = 0

    # سطح ریسک بر اساس ATR نسبت به قیمت
    atr_percent = (last_atr / last_price) * 100 if last_price > 0 else 0
    if atr_percent > 2:
        risk_level = "🔴 نوسان بالا — ریسک معامله زیاد است"
    elif atr_percent > 0.8:
        risk_level = "🟡 نوسان متوسط"
    else:
        risk_level = "🟢 نوسان پایین — بازار نسبتاً آرام"

    # ============================================================
    # محاسبه حد سود (TP) و حد ضرر (SL) بر اساس ATR
    # ============================================================
    sl_distance = last_atr * 1.5
    rr_ratio = 1.5
    tp_distance = sl_distance * rr_ratio

    if total_score > 0:
        direction = "BUY (خرید)"
        entry_price = last_price
        stop_loss = last_price - sl_distance
        take_profit = last_price + tp_distance
    elif total_score < 0:
        direction = "SELL (فروش)"
        entry_price = last_price
        stop_loss = last_price + sl_distance
        take_profit = last_price - tp_distance
    else:
        direction = None
        entry_price = last_price
        stop_loss = None
        take_profit = None

    trade_plan = None
    if direction:
        trade_plan = {
            "direction": direction,
            "entry": round(entry_price, 5),
            "stop_loss": round(stop_loss, 5),
            "take_profit": round(take_profit, 5),
            "risk_reward_ratio": rr_ratio,
            "sl_distance_pct": round((sl_distance / last_price) * 100, 2),
        }

    return {
        "price": round(last_price, 5),
        "regime": regime,
        "adx": round(last_adx, 1),
        "details": details,
        "final_verdict": final_verdict,
        "score": total_score,
        "normalized_score": round(normalized_score, 3),
        "max_score": 3,
        "risk_level": risk_level,
        "atr_percent": round(atr_percent, 2),
        "trade_plan": trade_plan,
        "disclaimer": (
            "⚠️ این تحلیل صرفاً بر اساس اندیکاتورهای تکنیکال گذشته است و "
            "تضمینی برای حرکت آینده قیمت نیست. وزن‌دهی اندیکاتورها بر اساس "
            "رژیم فعلی بازار (روند‌دار/رنج) تطبیق یافته، اما عدم قطعیت ذاتی "
            "بازار از بین نمی‌رود. سطح TP/SL بر مبنای نوسان آماری (ATR) "
            "محاسبه شده، نه پیش‌بینی جهت. تصمیم نهایی بر عهده‌ی شماست."
        ),
    }
