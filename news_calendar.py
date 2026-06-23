"""
news_calendar.py
-----------------
پایش تقویم اقتصادی و هشدار ریسک خبری.

⚠️ شفافیت مهم: این ماژول نتیجه‌ی خبر را پیش‌بینی نمی‌کند. کاری که
انجام می‌دهد:
1. اعلام می‌کند کدام اخبار مهم در راه است (قبل از انتشار) تا کاربر
   بداند در آن بازه‌ی زمانی، نوسان شدید و غیرقابل‌پیش‌بینی احتمال دارد.
2. بعد از انتشار، عدد واقعی را با پیش‌بینی بازار (Forecast) مقایسه
   می‌کند و می‌گوید نتیجه بهتر یا بدتر از انتظار بود — این یک فکت
   عینی است، نه پیش‌بینی جهت قیمت.

منبع داده: Finnhub Economic Calendar API (رایگان، نیاز به کلید دارد)
ثبت‌نام رایگان: https://finnhub.io/register
"""

import requests
from datetime import datetime, timedelta

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"

# اخبار با این کلیدواژه‌ها معمولاً بیشترین تأثیر روی فارکس/طلا/شاخص‌ها دارند
HIGH_IMPACT_KEYWORDS = [
    "interest rate", "rate decision", "fomc", "fed", "federal reserve",
    "non-farm", "nonfarm", "nfp", "payrolls", "cpi", "inflation",
    "gdp", "unemployment", "central bank", "ecb", "boe", "boj",
    "retail sales", "pmi", "fed chair", "powell", "press conference",
]


def _is_high_impact_by_keyword(event_name):
    """اگر impact level از API نامشخص بود، با کلیدواژه تشخیص می‌دهیم."""
    name_lower = event_name.lower()
    return any(kw in name_lower for kw in HIGH_IMPACT_KEYWORDS)


def get_economic_calendar(api_key, hours_ahead=48):
    """
    دریافت لیست اخبار اقتصادی از Finnhub برای بازه‌ی زمانی پیش رو.

    خروجی: لیستی از دیکشنری‌های رویداد، مرتب‌شده بر اساس زمان، شامل:
        - event: نام رویداد
        - country: کشور/واحد پولی مرتبط
        - time: زمان انتشار (datetime)
        - impact: سطح اهمیت ("high", "medium", "low")
        - actual / estimate / prev: مقادیر واقعی/پیش‌بینی/قبلی (اگر موجود بود)
    """
    if not api_key:
        raise ValueError(
            "کلید API تنظیم نشده است. از finnhub.io یک کلید رایگان "
            "بگیرید و به‌عنوان متغیر محیطی FINNHUB_API_KEY در Railway قرار دهید."
        )

    now = datetime.utcnow()
    from_date = now.strftime("%Y-%m-%d")
    to_date = (now + timedelta(hours=hours_ahead)).strftime("%Y-%m-%d")

    url = f"{FINNHUB_BASE_URL}/calendar/economic"
    params = {"from": from_date, "to": to_date, "token": api_key}

    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    raw = response.json()

    events_raw = raw.get("economicCalendar", raw.get("data", []))
    events = []

    for ev in events_raw:
        try:
            event_time = datetime.strptime(ev.get("time", ev.get("date", "")), "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            continue

        if event_time < now:
            # رویدادهایی که از این لحظه به قبل بودند را هم نگه می‌داریم اگر
            # خیلی تازه باشند (برای مقایسه‌ی actual/forecast بعد از انتشار)
            if now - event_time > timedelta(hours=6):
                continue

        impact_raw = str(ev.get("impact", "")).lower()
        event_name = ev.get("event", "نامشخص")
        if impact_raw not in ("high", "medium", "low"):
            impact_raw = "high" if _is_high_impact_by_keyword(event_name) else "low"

        events.append({
            "event": event_name,
            "country": ev.get("country", "—"),
            "time": event_time,
            "impact": impact_raw,
            "actual": ev.get("actual"),
            "estimate": ev.get("estimate"),
            "prev": ev.get("prev"),
        })

    events.sort(key=lambda e: e["time"])
    return events


def get_upcoming_high_impact(api_key, within_hours=6):
    """
    لیست اخبار پراهمیت که در `within_hours` ساعت آینده منتشر می‌شوند.
    برای هشدار «نوسان شدید احتمالی پیش رو».
    """
    all_events = get_economic_calendar(api_key, hours_ahead=within_hours + 1)
    now = datetime.utcnow()

    upcoming = [
        e for e in all_events
        if e["impact"] == "high" and now <= e["time"] <= now + timedelta(hours=within_hours)
    ]
    return upcoming


def get_recent_released(api_key, within_hours=3):
    """
    اخباری که در `within_hours` ساعت گذشته منتشر شده‌اند و عدد واقعی
    (actual) دارند — برای مقایسه با پیش‌بینی بازار.
    """
    all_events = get_economic_calendar(api_key, hours_ahead=1)
    now = datetime.utcnow()

    released = [
        e for e in all_events
        if e["actual"] is not None and now - timedelta(hours=within_hours) <= e["time"] <= now
    ]
    return released


def compare_actual_vs_forecast(event):
    """
    مقایسه‌ی عینی عدد واقعی با پیش‌بینی بازار. این فکت است، نه پیش‌بینی.
    خروجی: متن توضیحی فارسی.
    """
    actual = event.get("actual")
    estimate = event.get("estimate")

    if actual is None or estimate is None:
        return "داده‌ی کافی برای مقایسه موجود نیست."

    try:
        actual_val = float(actual)
        estimate_val = float(estimate)
    except (ValueError, TypeError):
        return f"واقعی: {actual} | پیش‌بینی: {estimate}"

    if actual_val > estimate_val:
        return f"📈 عدد واقعی ({actual_val}) بالاتر از پیش‌بینی بازار ({estimate_val}) بود."
    elif actual_val < estimate_val:
        return f"📉 عدد واقعی ({actual_val}) پایین‌تر از پیش‌بینی بازار ({estimate_val}) بود."
    else:
        return f"➖ عدد واقعی دقیقاً مطابق پیش‌بینی بازار ({actual_val}) بود."


def get_news_risk_warning(api_key, within_hours=6):
    """
    خلاصه‌ی آماده برای نمایش در پیام تلگرام — هشدار ریسک خبری پیش رو.
    اگر هیچ خبر پرریسکی در این بازه نباشد، None برمی‌گرداند.
    """
    try:
        upcoming = get_upcoming_high_impact(api_key, within_hours=within_hours)
    except Exception:
        return None  # اگر API مشکل داشت، تحلیل تکنیکال بدون این بخش ادامه پیدا کند

    if not upcoming:
        return None

    lines = [f"⚠️ *هشدار ریسک خبری* (در {within_hours} ساعت آینده):\n"]
    for ev in upcoming[:5]:
        time_str = ev["time"].strftime("%H:%M UTC")
        lines.append(f"🔴 {time_str} | {ev['country']} | {ev['event']}")
    lines.append(
        "\nدر این بازه‌ی زمانی، نوسان شدید و ناگهانی بازار محتمل است. "
        "ورود به معامله با حجم بالا یا بدون Stop Loss در این بازه توصیه نمی‌شود."
    )
    return "\n".join(lines)
