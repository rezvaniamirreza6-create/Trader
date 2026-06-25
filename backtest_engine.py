"""
backtest_engine.py
-------------------
موتور بک‌تست Walk-Forward برای ارزیابی علمی و قابل‌اعتماد موتور تحلیل.

⚠️ چرا Walk-Forward و نه یک بک‌تست ساده؟
بک‌تست ساده (یک‌بار اجرا روی کل داده) می‌تواند به‌راحتی نتیجه‌ای
گمراه‌کننده بدهد - یا به دلیل Overfitting (تنظیم پارامترها متناسب
با همان داده)، یا به دلیل Cherry-Picking (دیدن فقط بهترین دوره).

روش Walk-Forward داده را به چند پنجره‌ی متوالی تقسیم می‌کند و در هر
پنجره، فقط داده‌ی قبل از همان لحظه را می‌بیند (دقیقاً مثل واقعیت).
نتیجه‌ی هر پنجره جدا گزارش می‌شود تا **پایداری** عملکرد در طول زمان
مشخص شود - نه فقط یک عدد میانگین که می‌تواند نوسانات بزرگ را پنهان کند.

این ماژول می‌تواند:
1. روی داده‌ی واقعی بازار (دریافت‌شده از Twelve Data) اجرا شود
2. نتیجه را به‌صورت یک گزارش متنی واضح برای ادمین تولید کند
"""

import numpy as np
import pandas as pd

import analysis


def run_walk_forward_backtest(df, n_windows=6, horizon=5, min_window_data=65, user_weight_multipliers=None):
    """
    اجرای بک‌تست Walk-Forward روی یک دیتافریم OHLC واقعی یا شبیه‌سازی‌شده.

    df: دیتافریم با ستون‌های open, high, low, close (هر چه طولانی‌تر، بهتر)
    n_windows: تعداد پنجره‌های متوالی غیرهم‌پوشان
    horizon: تعداد کندل آینده برای سنجش نتیجه واقعی هر سیگنال
    min_window_data: حداقل کندل لازم در ابتدای هر پنجره برای محاسبه اندیکاتورها
    user_weight_multipliers: دیکشنری اختیاری وزن شخصی کاربر (برای بک‌تست استراتژی شخصی)

    خروجی: دیکشنری شامل نتیجه هر پنجره + خلاصه‌ی آماری کلی
    """
    n_total = len(df)
    if n_total < n_windows * min_window_data * 2:
        return {
            "error": (
                f"داده کافی برای {n_windows} پنجره وجود ندارد. "
                f"حداقل {n_windows * min_window_data * 2} کندل لازم است، "
                f"اما فقط {n_total} کندل موجود است."
            )
        }

    window_size = n_total // n_windows
    window_results = []

    for w in range(n_windows):
        start_idx = w * window_size
        end_idx = start_idx + window_size
        window_signals = []

        for i in range(start_idx + min_window_data, min(end_idx, n_total - horizon)):
            # نکته کلیدی: فقط داده تا همین لحظه دیده می‌شود (نه آینده)
            window_df = df.iloc[: i + 1].reset_index(drop=True)
            try:
                result = analysis.generate_signal(window_df, user_weight_multipliers=user_weight_multipliers)
            except Exception:
                continue
            if "error" in result or result["score"] == 0:
                continue

            current_price = df["close"].iloc[i]
            future_price = df["close"].iloc[i + horizon]
            actual_direction = 1 if future_price > current_price else -1
            predicted_direction = 1 if result["score"] > 0 else -1

            window_signals.append(predicted_direction == actual_direction)

        if window_signals:
            accuracy = float(np.mean(window_signals) * 100)
            window_results.append({
                "window": w + 1,
                "n_signals": len(window_signals),
                "accuracy": round(accuracy, 1),
            })

    if not window_results:
        return {"error": "هیچ سیگنال جهت‌داری در طول بک‌تست تولید نشد."}

    accuracies = [r["accuracy"] for r in window_results]

    return {
        "windows": window_results,
        "mean_accuracy": round(float(np.mean(accuracies)), 1),
        "std_accuracy": round(float(np.std(accuracies)), 1),
        "best_window": round(float(max(accuracies)), 1),
        "worst_window": round(float(min(accuracies)), 1),
        "range_accuracy": round(float(max(accuracies) - min(accuracies)), 1),
        "total_signals": sum(r["n_signals"] for r in window_results),
    }


def format_backtest_report(result, symbol="نامشخص"):
    """تولید گزارش متنی فارسی و قابل‌فهم از نتیجه بک‌تست Walk-Forward."""
    if "error" in result:
        return f"❌ {result['error']}"

    lines = [f"📊 *گزارش بک‌تست Walk-Forward — {symbol}*\n"]
    lines.append(f"تعداد پنجره‌های ارزیابی‌شده: {len(result['windows'])}")
    lines.append(f"کل سیگنال‌های بررسی‌شده: {result['total_signals']}\n")

    for w in result["windows"]:
        lines.append(f"پنجره {w['window']}: {w['n_signals']} سیگنال → دقت {w['accuracy']}%")

    lines.append("")
    lines.append(f"📈 میانگین دقت کلی: {result['mean_accuracy']}%")
    lines.append(f"📉 انحراف بین پنجره‌ها: {result['std_accuracy']}% (هرچه کمتر، پایدارتر)")
    lines.append(f"🔼 بهترین پنجره: {result['best_window']}% | 🔽 بدترین پنجره: {result['worst_window']}%")
    lines.append(f"↔️ دامنه نوسان: {result['range_accuracy']} درصد")

    lines.append(
        "\nℹ️ این گزارش با روش Walk-Forward تولید شده — یعنی در هر نقطه فقط "
        "داده‌ی گذشته دیده شده، دقیقاً مثل شرایط واقعی معامله. اگر دامنه‌ی "
        "نوسان بین پنجره‌ها بالا باشد (مثلاً بیش از ۱۰ درصد)، یعنی عملکرد "
        "در طول زمان ناپایدار است و میانگین به‌تنهایی گمراه‌کننده خواهد بود."
    )

    return "\n".join(lines)
