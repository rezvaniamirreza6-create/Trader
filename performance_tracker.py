"""
performance_tracker.py
-----------------------
سیستم ثبت و ارزیابی واقعی عملکرد سیگنال‌ها.

ایده‌ی اصلی: به‌جای ادعای یک عدد دقت ثابت و فرضی، هر سیگنالی که ربات
به کاربر می‌دهد را ثبت می‌کنیم. بعداً، وقتی زمان کافی گذشت، با گرفتن
قیمت واقعی همان لحظه، نتیجه‌ی واقعی سیگنال را محاسبه و ذخیره می‌کنیم.

دو افق ارزیابی جداگانه:
- کوتاه‌مدت: ۵ کندل بعد از سیگنال (بسته به تایم‌فریم، با 1h یعنی ۵ ساعت بعد)
- بلندمدت: ۲۴ ساعت بعد از سیگنال

نتیجه نهایی یک "داشبورد عملکرد واقعی" است که از داده‌ی واقعی بازار
ساخته می‌شود، نه از یک عدد ادعایی.
"""

import json
import os
from datetime import datetime, timedelta

DATA_DIR = "data"
SIGNALS_FILE = os.path.join(DATA_DIR, "signal_history.json")


def _ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)


def _load_json(filepath):
    _ensure_data_dir()
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def _save_json(filepath, data):
    _ensure_data_dir()
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _now():
    return datetime.utcnow()


# ============================================================
# ثبت سیگنال جدید
# ============================================================

def log_signal(symbol, direction, score, entry_price, interval="1h", user_id=None):
    """
    هر بار که ربات یک سیگنال جهت‌دار (غیر خنثی) به کاربر می‌دهد،
    این تابع آن را برای ارزیابی بعدی ثبت می‌کند.

    خروجی: شناسه‌ی یکتای سیگنال (signal_id)
    """
    signals = _load_json(SIGNALS_FILE)

    signal_id = f"{symbol.replace('/', '')}_{int(_now().timestamp())}_{len(signals)}"

    # تخمین فاصله زمانی هر کندل بر اساس interval، برای محاسبه افق "۵ کندل بعد"
    interval_minutes_map = {
        "1min": 1, "5min": 5, "15min": 15, "30min": 30,
        "45min": 45, "1h": 60, "2h": 120, "4h": 240,
        "8h": 480, "1day": 1440,
    }
    candle_minutes = interval_minutes_map.get(interval, 60)

    now = _now()
    signals[signal_id] = {
        "symbol": symbol,
        "direction": direction,        # "BUY" یا "SELL"
        "score": score,
        "entry_price": entry_price,
        "interval": interval,
        "user_id": user_id,
        "logged_at": now.isoformat(),
        "short_term_due_at": (now + timedelta(minutes=candle_minutes * 5)).isoformat(),
        "long_term_due_at": (now + timedelta(hours=24)).isoformat(),
        "short_term_result": None,   # None = هنوز ارزیابی نشده
        "long_term_result": None,
    }
    _save_json(SIGNALS_FILE, signals)
    return signal_id


# ============================================================
# ارزیابی سیگنال‌های سررسیدشده
# ============================================================

def get_pending_evaluations():
    """
    لیست سیگنال‌هایی که زمان ارزیابی‌شان رسیده ولی هنوز ارزیابی نشده‌اند.
    خروجی: [(signal_id, info, "short"|"long"), ...]
    """
    signals = _load_json(SIGNALS_FILE)
    now = _now()
    pending = []

    for sid, info in signals.items():
        if info["short_term_result"] is None:
            due = datetime.fromisoformat(info["short_term_due_at"])
            if now >= due:
                pending.append((sid, info, "short"))
        if info["long_term_result"] is None:
            due = datetime.fromisoformat(info["long_term_due_at"])
            if now >= due:
                pending.append((sid, info, "long"))

    return pending


def record_evaluation_result(signal_id, horizon, current_price):
    """
    ثبت نتیجه‌ی واقعی یک سیگنال با مقایسه‌ی قیمت فعلی با قیمت ورود.

    horizon: "short" یا "long"
    """
    signals = _load_json(SIGNALS_FILE)
    if signal_id not in signals:
        return False

    info = signals[signal_id]
    entry_price = info["entry_price"]
    direction = info["direction"]

    price_went_up = current_price > entry_price

    if direction == "BUY":
        correct = price_went_up
    else:  # SELL
        correct = not price_went_up

    price_change_pct = ((current_price - entry_price) / entry_price) * 100

    result = {
        "correct": correct,
        "price_at_evaluation": current_price,
        "price_change_pct": round(price_change_pct, 3),
        "evaluated_at": _now().isoformat(),
    }

    if horizon == "short":
        signals[signal_id]["short_term_result"] = result
    else:
        signals[signal_id]["long_term_result"] = result

    _save_json(SIGNALS_FILE, signals)
    return True


# ============================================================
# داشبورد عملکرد واقعی
# ============================================================

def get_performance_dashboard(symbol=None):
    """
    خلاصه‌ی آماری واقعی از تمام سیگنال‌های ارزیابی‌شده.
    اگر symbol داده شود، فقط برای آن بازار فیلتر می‌شود.
    """
    signals = _load_json(SIGNALS_FILE)

    short_results = []
    long_results = []

    for sid, info in signals.items():
        if symbol and info["symbol"] != symbol:
            continue
        if info["short_term_result"] is not None:
            short_results.append(info["short_term_result"]["correct"])
        if info["long_term_result"] is not None:
            long_results.append(info["long_term_result"]["correct"])

    def _summarize(results):
        total = len(results)
        if total == 0:
            return {"total": 0, "correct": 0, "accuracy_pct": None}
        correct = sum(1 for r in results if r)
        return {
            "total": total,
            "correct": correct,
            "accuracy_pct": round((correct / total) * 100, 1),
        }

    return {
        "short_term": _summarize(short_results),
        "long_term": _summarize(long_results),
        "total_signals_logged": len(signals) if not symbol else sum(1 for i in signals.values() if i["symbol"] == symbol),
    }


def get_recent_evaluated_signals(limit=10):
    """آخرین سیگنال‌هایی که حداقل یک نتیجه (کوتاه یا بلندمدت) دارند — برای نمایش لیست به ادمین."""
    signals = _load_json(SIGNALS_FILE)
    evaluated = [
        (sid, info) for sid, info in signals.items()
        if info["short_term_result"] is not None or info["long_term_result"] is not None
    ]
    evaluated.sort(key=lambda x: x[1]["logged_at"], reverse=True)
    return evaluated[:limit]
