"""
chart_generator.py
-------------------
رسم نمودار کندل‌استیک همراه با اندیکاتورهای کلیدی (میانگین متحرک و
باندهای بولینگر) برای ارسال به‌عنوان عکس در کنار تحلیل متنی.

از matplotlib خام استفاده می‌شود (بدون وابستگی به mplfinance) تا
نصب پروژه ساده‌تر و قابل‌اعتمادتر بماند.
"""

import os
import matplotlib
matplotlib.use("Agg")  # بدون نیاز به نمایشگر - برای اجرای سرور
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

import analysis

CHARTS_DIR = "data/charts"

# رنگ‌بندی تم تاریک (مناسب برای تماشا در تلگرام)
BG_COLOR = "#0e1117"
UP_COLOR = "#26a69a"
DOWN_COLOR = "#ef5350"
SMA_SHORT_COLOR = "#ffeb3b"
SMA_LONG_COLOR = "#42a5f5"
BAND_COLOR = "#9575cd"
TEXT_COLOR = "white"


def _ensure_charts_dir():
    if not os.path.exists(CHARTS_DIR):
        os.makedirs(CHARTS_DIR)


def generate_chart(df, symbol, interval, display_name=None, max_candles=80):
    """
    رسم نمودار کندل‌استیک از آخرین `max_candles` کندل، همراه با
    میانگین متحرک کوتاه/بلندمدت و باندهای بولینگر.

    نکته: عنوان و برچسب‌ها به‌صورت لاتین/سیمبل نوشته می‌شوند (نه فارسی)
    چون matplotlib بدون کتابخانه‌های اضافه (arabic_reshaper + python-bidi)
    متن فارسی را برعکس (راست‌به‌چپ نادرست) رسم می‌کند. توضیح کامل فارسی
    در پیام متنی همراه نمودار ارسال می‌شود.

    خروجی: مسیر فایل PNG ذخیره‌شده (برای ارسال در تلگرام).
    """
    _ensure_charts_dir()

    plot_df = df.tail(max_candles).reset_index(drop=True)

    sma_short, sma_long = analysis.calculate_moving_averages(df)
    upper_band, mid_band, lower_band = analysis.calculate_bollinger_bands(df)

    offset = len(df) - len(plot_df)
    sma_short_plot = sma_short.iloc[offset:].reset_index(drop=True)
    sma_long_plot = sma_long.iloc[offset:].reset_index(drop=True)
    upper_plot = upper_band.iloc[offset:].reset_index(drop=True)
    lower_plot = lower_band.iloc[offset:].reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(10, 6), facecolor=BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    for i in range(len(plot_df)):
        o = plot_df["open"].iloc[i]
        h = plot_df["high"].iloc[i]
        l = plot_df["low"].iloc[i]
        c = plot_df["close"].iloc[i]
        color = UP_COLOR if c >= o else DOWN_COLOR

        ax.plot([i, i], [l, h], color=color, linewidth=1)
        body_height = abs(c - o) if abs(c - o) > 1e-9 else (h - l) * 0.01
        rect = Rectangle((i - 0.3, min(o, c)), 0.6, body_height, facecolor=color, edgecolor=color)
        ax.add_patch(rect)

    x_range = range(len(plot_df))
    ax.plot(x_range, sma_short_plot, color=SMA_SHORT_COLOR, linewidth=1.2, label="SMA 20")
    ax.plot(x_range, sma_long_plot, color=SMA_LONG_COLOR, linewidth=1.2, label="SMA 50")
    ax.plot(x_range, upper_plot, color=BAND_COLOR, linewidth=0.8, linestyle="--", alpha=0.7, label="Bollinger Band")
    ax.plot(x_range, lower_plot, color=BAND_COLOR, linewidth=0.8, linestyle="--", alpha=0.7)

    ax.set_xlim(-1, len(plot_df))
    ax.tick_params(colors=TEXT_COLOR)
    for spine_name in ("bottom", "left"):
        ax.spines[spine_name].set_color(TEXT_COLOR)
    for spine_name in ("top", "right"):
        ax.spines[spine_name].set_color(BG_COLOR)

    ax.legend(facecolor="#1c1f26", edgecolor="none", labelcolor=TEXT_COLOR, loc="upper left", fontsize=9)

    # عنوان فقط با سیمبل لاتین/تایم‌فریم (بدون متن فارسی) برای رندر صحیح
    ax.set_title(f"{symbol} | {interval}", color=TEXT_COLOR, fontsize=14)
    ax.set_xticks([])

    plt.tight_layout()

    safe_symbol = symbol.replace("/", "")
    filepath = os.path.join(CHARTS_DIR, f"{safe_symbol}_{interval}.png")
    plt.savefig(filepath, dpi=120, facecolor=BG_COLOR)
    plt.close(fig)

    return filepath
