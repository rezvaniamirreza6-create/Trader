"""
user_strategies.py
-------------------
مدیریت استراتژی‌های شخصی کاربران.

هر کاربر می‌تواند برای ۵ اندیکاتور جهت‌دار (RSI, MACD, MA, Bollinger,
Stochastic) یک ضریب وزن شخصی انتخاب کند. این ضرایب روی وزن‌دهی
رژیم‌محور پیش‌فرض موتور تحلیل ضرب می‌شوند.

⚠️ اصل مهم صداقت آماری:
هیچ استراتژی فقط بر اساس ادعای کاربر یا چند معامله‌ی موفق «برنده»
اعلام نمی‌شود. هر استراتژی، فوراً بعد از ساخت، با بک‌تست Walk-Forward
واقعی (همان ماژول backtest_engine) روی داده‌ی تاریخی واقعی ارزیابی
می‌شود و نتیجه‌ی همان بک‌تست (نه چیز دیگری) ذخیره و نمایش داده می‌شود.
"""

import json
import os
import random
import string
from datetime import datetime

DATA_DIR = "data"
STRATEGIES_FILE = os.path.join(DATA_DIR, "user_strategies.json")

# اندیکاتورهایی که کاربر می‌تواند وزن آن‌ها را شخصی‌سازی کند
CUSTOMIZABLE_INDICATORS = ["rsi", "macd", "ma", "bollinger", "stochastic"]

# گزینه‌های ضریب وزن قابل‌انتخاب (نمایش به کاربر)
WEIGHT_MULTIPLIER_OPTIONS = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0]


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


def create_strategy(user_id, name, weights):
    """
    ساخت یک استراتژی جدید برای کاربر (بدون بک‌تست - این کار جدا انجام می‌شود).

    weights: دیکشنری مثل {"rsi": 2.0, "macd": 1.0, "ma": 1.0, "bollinger": 1.0, "stochastic": 0.5}

    خروجی: شناسه‌ی یکتای استراتژی (strategy_id)
    """
    strategies = _load_json(STRATEGIES_FILE)
    uid = str(user_id)

    if uid not in strategies:
        strategies[uid] = {}

    strategy_id = f"strat_{int(datetime.utcnow().timestamp())}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=4))}"
    strategies[uid][strategy_id] = {
        "name": name,
        "weights": weights,
        "created_at": datetime.utcnow().isoformat(),
        "backtest_result": None,  # بعد از اجرای بک‌تست پر می‌شود
    }
    _save_json(STRATEGIES_FILE, strategies)
    return strategy_id


def save_backtest_result(user_id, strategy_id, backtest_result):
    """ذخیره‌ی نتیجه‌ی واقعی بک‌تست Walk-Forward برای یک استراتژی."""
    strategies = _load_json(STRATEGIES_FILE)
    uid = str(user_id)

    if uid not in strategies or strategy_id not in strategies[uid]:
        return False

    strategies[uid][strategy_id]["backtest_result"] = backtest_result
    strategies[uid][strategy_id]["backtested_at"] = datetime.utcnow().isoformat()
    _save_json(STRATEGIES_FILE, strategies)
    return True


def get_user_strategies(user_id):
    """لیست همه‌ی استراتژی‌های یک کاربر."""
    strategies = _load_json(STRATEGIES_FILE)
    return strategies.get(str(user_id), {})


def delete_strategy(user_id, strategy_id):
    """حذف یک استراتژی کاربر."""
    strategies = _load_json(STRATEGIES_FILE)
    uid = str(user_id)
    if uid in strategies and strategy_id in strategies[uid]:
        del strategies[uid][strategy_id]
        _save_json(STRATEGIES_FILE, strategies)
        return True
    return False


def get_all_strategies_with_results():
    """
    همه‌ی استراتژی‌های همه‌ی کاربران که نتیجه‌ی بک‌تست واقعی دارند.
    برای رتبه‌بندی و شناسایی الگوهای موفق توسط ادمین استفاده می‌شود.

    خروجی: لیستی از (user_id, strategy_id, strategy_data)
    """
    strategies = _load_json(STRATEGIES_FILE)
    result = []
    for uid, user_strats in strategies.items():
        for sid, data in user_strats.items():
            if data.get("backtest_result") and "error" not in data["backtest_result"]:
                result.append((uid, sid, data))
    return result


def rank_strategies_by_performance(min_signals=30):
    """
    رتبه‌بندی استراتژی‌های همه کاربران بر اساس نتیجه‌ی واقعی بک‌تست.

    ⚠️ اصل صداقت آماری: فقط استراتژی‌هایی که حداقل `min_signals` سیگنال
    در بک‌تست‌شان بررسی شده رتبه‌بندی می‌شوند. استراتژی با تعداد سیگنال
    کم (مثلاً ۳ یا ۴ سیگنال) می‌تواند به‌شانس خوب به نظر برسد، اما این
    آمار معتبر نیست (نمونه‌ی کوچک). این فیلتر دقیقاً برای جلوگیری از
    تکرار خطای Survivorship Bias / Cherry-Picking است.

    خروجی: لیست مرتب‌شده بر اساس میانگین دقت، نزولی
    """
    all_strategies = get_all_strategies_with_results()
    eligible = []

    for uid, sid, data in all_strategies:
        result = data["backtest_result"]
        total_signals = result.get("total_signals", 0)
        if total_signals < min_signals:
            continue
        eligible.append({
            "user_id": uid,
            "strategy_id": sid,
            "name": data["name"],
            "weights": data["weights"],
            "mean_accuracy": result["mean_accuracy"],
            "std_accuracy": result["std_accuracy"],
            "total_signals": total_signals,
        })

    eligible.sort(key=lambda s: s["mean_accuracy"], reverse=True)
    return eligible


def get_common_patterns_in_top_strategies(top_n=10, min_signals=30):
    """
    بررسی استراتژی‌های برتر (بر اساس بک‌تست واقعی) برای یافتن الگوهای
    مشترک - مثلاً «اکثر استراتژی‌های برتر وزن RSI بالاتری دارند».

    ⚠️ این تابع صرفاً یک مشاهده‌ی آماری از داده‌ی موجود ارائه می‌دهد،
    نه یک قانون قطعی. با تعداد کم استراتژی، این الگوها می‌توانند
    تصادفی باشند.

    خروجی: دیکشنری میانگین وزن هر اندیکاتور در بین استراتژی‌های برتر
    """
    ranked = rank_strategies_by_performance(min_signals=min_signals)
    top_strategies = ranked[:top_n]

    if not top_strategies:
        return None

    avg_weights = {indicator: [] for indicator in CUSTOMIZABLE_INDICATORS}
    for strat in top_strategies:
        for indicator in CUSTOMIZABLE_INDICATORS:
            if indicator in strat["weights"]:
                avg_weights[indicator].append(strat["weights"][indicator])

    summary = {}
    for indicator, values in avg_weights.items():
        if values:
            summary[indicator] = round(sum(values) / len(values), 2)

    return {
        "n_strategies_analyzed": len(top_strategies),
        "average_weights": summary,
    }
