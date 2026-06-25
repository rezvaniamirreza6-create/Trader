"""
bot.py
------
ربات تلگرامی تحلیل تکنیکال با سیستم لایسنس و پنل مدیریت.

نحوه اجرا:
1. متغیرهای محیطی BOT_TOKEN ، ADMIN_ID و TWELVE_DATA_API_KEY را در
   Railway بخش Variables تنظیم کنید (هرگز در کد ننویسید).
2. pip install -r requirements.txt
3. python bot.py

دستورات کاربر عادی (همچنین از طریق دکمه‌های کیبورد پایین صفحه):
/start      - شروع و نمایش کیبورد اصلی
/activate   - فعال‌سازی لایسنس
/analyze    - دریافت تحلیل تکنیکال
/myinfo     - وضعیت اشتراک من
/help       - راهنما

دستورات ادمین (فقط برای ADMIN_ID):
/admin          - باز کردن پنل مدیریت
/genlicense     - ساخت لایسنس جدید (با دکمه‌های تعاملی)
/listlicenses   - لیست لایسنس‌ها
/revoke <کد>    - باطل کردن یک کد لایسنس
/ban <user_id>  - مسدود کردن کاربر
/unban <user_id>- رفع مسدودیت کاربر
/stats          - آمار کامل سیستم
/broadcast <متن>- ارسال پیام همگانی به همه کاربران
"""

import os
import logging

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import license_manager as lm
import analysis
import performance_tracker as pt
import news_calendar as nc
import chart_generator as cg
import backtest_engine as bte
import user_strategies as us

# ============================================================
# تنظیمات (از Environment Variables — هرگز در کد ننویسید)
# ============================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY", None)
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", None)

# نام نمایشی فارسی برای هر سیمبل (در پیام تحلیل استفاده می‌شود)
SYMBOL_DISPLAY_NAMES = {
    "BTC/USD": "بیت‌کوین (BTC/USD)",
    "ETH/USD": "اتریوم (ETH/USD)",
    "SOL/USD": "سولانا (SOL/USD)",
    "EUR/USD": "یورو/دلار (EUR/USD)",
    "GBP/USD": "پوند/دلار (GBP/USD)",
    "USD/JPY": "دلار/ین (USD/JPY)",
    "USD/CHF": "دلار/فرانک (USD/CHF)",
    "AUD/USD": "دلار استرالیا (AUD/USD)",
    "USD/CAD": "دلار کانادا (USD/CAD)",
    "XAU/USD": "طلا (XAU/USD)",
    "XAG/USD": "نقره (XAG/USD)",
    "WTI/USD": "نفت خام (WTI/USD)",
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# منتظرِ ساخت لایسنس با چه تعداد روز هستیم؟ (state ساده در حافظه)
PENDING_GENLICENSE_DAYS = {}
# منتظرِ متن broadcast از طرف ادمین هستیم؟
PENDING_BROADCAST = set()


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# ============================================================
# کیبوردهای دائمی (پایین صفحه) و شیشه‌ای (inline)
# ============================================================

def main_keyboard():
    """کیبورد دائمی کاربر عادی — همیشه پایین صفحه دیده می‌شود."""
    buttons = [
        [KeyboardButton("📊 تحلیل تکنیکال"), KeyboardButton("🔑 فعال‌سازی لایسنس")],
        [KeyboardButton("👤 وضعیت اشتراک من"), KeyboardButton("📈 داشبورد عملکرد")],
        [KeyboardButton("📰 اخبار اقتصادی"), KeyboardButton("🧪 استراتژی شخصی من")],
        [KeyboardButton("ℹ️ راهنما")],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def admin_keyboard():
    """کیبورد دائمی ادمین — شامل دکمه‌های مدیریتی اضافه."""
    buttons = [
        [KeyboardButton("📊 تحلیل تکنیکال"), KeyboardButton("🔑 فعال‌سازی لایسنس")],
        [KeyboardButton("👤 وضعیت اشتراک من"), KeyboardButton("📈 داشبورد عملکرد")],
        [KeyboardButton("📰 اخبار اقتصادی"), KeyboardButton("🧪 استراتژی شخصی من")],
        [KeyboardButton("ℹ️ راهنما"), KeyboardButton("🛠 پنل مدیریت")],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def keyboard_for(user_id):
    return admin_keyboard() if is_admin(user_id) else main_keyboard()


def market_selection_inline_keyboard():
    """
    دکمه‌های شیشه‌ای انتخاب بازار - مرحله ۱ (بعدش تایم‌فریم پرسیده می‌شود).

    نکته: دکمه‌های شاخص‌های سهام (داوجونز/اس‌اندپی/نزدک) حذف شدند چون
    Twelve Data رسماً اعلام کرده پشتیبانی از شاخص‌ها هنوز "به‌زودی"
    است و در دسترس نیست (نه در پلن رایگان، نه حتی پولی) - این دلیل
    خطای 404 قبلی بود، نه مشکل فرمت سیمبل.
    """
    keyboard = [
        [
            InlineKeyboardButton("₿ بیت‌کوین", callback_data="selectsym_BTC/USD"),
            InlineKeyboardButton("Ξ اتریوم", callback_data="selectsym_ETH/USD"),
            InlineKeyboardButton("◎ سولانا", callback_data="selectsym_SOL/USD"),
        ],
        [
            InlineKeyboardButton("💶 یورو/دلار", callback_data="selectsym_EUR/USD"),
            InlineKeyboardButton("💷 پوند/دلار", callback_data="selectsym_GBP/USD"),
            InlineKeyboardButton("💴 دلار/ین", callback_data="selectsym_USD/JPY"),
        ],
        [
            InlineKeyboardButton("🇨🇭 دلار/فرانک", callback_data="selectsym_USD/CHF"),
            InlineKeyboardButton("🇦🇺 دلار استرالیا", callback_data="selectsym_AUD/USD"),
            InlineKeyboardButton("🇨🇦 دلار کانادا", callback_data="selectsym_USD/CAD"),
        ],
        [
            InlineKeyboardButton("🪙 طلا", callback_data="selectsym_XAU/USD"),
            InlineKeyboardButton("🥈 نقره", callback_data="selectsym_XAG/USD"),
            InlineKeyboardButton("🛢 نفت خام", callback_data="selectsym_WTI/USD"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


# تایم‌فریم‌های پشتیبانی‌شده توسط Twelve Data، با نام نمایشی فارسی
TIMEFRAME_DISPLAY_NAMES = {
    "15min": "۱۵ دقیقه",
    "30min": "۳۰ دقیقه",
    "1h": "۱ ساعت",
    "4h": "۴ ساعت",
    "1day": "۱ روزه",
}


def timeframe_selection_inline_keyboard(symbol):
    """
    دکمه‌های شیشه‌ای انتخاب تایم‌فریم - مرحله ۲ (بعد از انتخاب بازار).
    سیمبل در callback_data تعبیه می‌شود تا در مرحله بعد بازیابی شود.
    """
    keyboard = [
        [
            InlineKeyboardButton("۱۵ دقیقه", callback_data=f"analyze_{symbol}_15min"),
            InlineKeyboardButton("۳۰ دقیقه", callback_data=f"analyze_{symbol}_30min"),
        ],
        [
            InlineKeyboardButton("۱ ساعت", callback_data=f"analyze_{symbol}_1h"),
            InlineKeyboardButton("۴ ساعت", callback_data=f"analyze_{symbol}_4h"),
        ],
        [
            InlineKeyboardButton("۱ روزه", callback_data=f"analyze_{symbol}_1day"),
        ],
        [
            InlineKeyboardButton("🔙 بازگشت به انتخاب بازار", callback_data="backtomarkets"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)



def admin_panel_inline_keyboard():
    """منوی شیشه‌ای پنل مدیریت ادمین."""
    keyboard = [
        [InlineKeyboardButton("➕ ساخت لایسنس جدید", callback_data="admin_genlicense")],
        [InlineKeyboardButton("📋 لیست لایسنس‌ها", callback_data="admin_listlicenses")],
        [InlineKeyboardButton("📈 آمار کامل سیستم", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 لیست کاربران", callback_data="admin_listusers")],
        [InlineKeyboardButton("📐 بک‌تست Walk-Forward", callback_data="admin_backtest")],
        [InlineKeyboardButton("🏆 رتبه‌بندی استراتژی‌های کاربران", callback_data="admin_strategyrank")],
        [InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data="admin_broadcast")],
    ]
    return InlineKeyboardMarkup(keyboard)


def genlicense_days_inline_keyboard():
    """انتخاب سریع مدت اعتبار لایسنس با دکمه."""
    keyboard = [
        [
            InlineKeyboardButton("۱ روز", callback_data="genlic_days_1"),
            InlineKeyboardButton("۷ روز", callback_data="genlic_days_7"),
            InlineKeyboardButton("۱۵ روز", callback_data="genlic_days_15"),
        ],
        [
            InlineKeyboardButton("۳۰ روز", callback_data="genlic_days_30"),
            InlineKeyboardButton("۹۰ روز", callback_data="genlic_days_90"),
            InlineKeyboardButton("۳۶۵ روز", callback_data="genlic_days_365"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def backtest_market_inline_keyboard():
    """انتخاب بازار برای اجرای بک‌تست Walk-Forward توسط ادمین."""
    keyboard = [
        [
            InlineKeyboardButton("₿ بیت‌کوین", callback_data="runbacktest_BTC/USD"),
            InlineKeyboardButton("Ξ اتریوم", callback_data="runbacktest_ETH/USD"),
        ],
        [
            InlineKeyboardButton("💶 یورو/دلار", callback_data="runbacktest_EUR/USD"),
            InlineKeyboardButton("💷 پوند/دلار", callback_data="runbacktest_GBP/USD"),
        ],
        [
            InlineKeyboardButton("🪙 طلا", callback_data="runbacktest_XAU/USD"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


# نام نمایشی فارسی برای هر اندیکاتور قابل‌شخصی‌سازی
INDICATOR_DISPLAY_NAMES = {
    "rsi": "RSI (اشباع خرید/فروش)",
    "macd": "MACD (مومنتوم)",
    "ma": "میانگین متحرک (روند)",
    "bollinger": "باندهای بولینگر",
    "stochastic": "استوکاستیک",
}

# ترتیب پرسش وزن هر اندیکاتور از کاربر (state machine ساده)
STRATEGY_BUILD_STEPS = ["rsi", "macd", "ma", "bollinger", "stochastic"]


def strategy_menu_inline_keyboard():
    """منوی اصلی بخش استراتژی شخصی کاربر."""
    keyboard = [
        [InlineKeyboardButton("➕ ساخت استراتژی جدید", callback_data="strategy_new")],
        [InlineKeyboardButton("📋 استراتژی‌های من", callback_data="strategy_list")],
    ]
    return InlineKeyboardMarkup(keyboard)


def weight_selection_inline_keyboard(indicator_key):
    """دکمه‌های انتخاب ضریب وزن برای یک اندیکاتور خاص، در فرآیند ساخت استراتژی."""
    keyboard = [
        [
            InlineKeyboardButton("غیرفعال (۰)", callback_data=f"stratw_{indicator_key}_0.0"),
            InlineKeyboardButton("کم (۰.۵×)", callback_data=f"stratw_{indicator_key}_0.5"),
        ],
        [
            InlineKeyboardButton("عادی (۱×)", callback_data=f"stratw_{indicator_key}_1.0"),
            InlineKeyboardButton("زیاد (۱.۵×)", callback_data=f"stratw_{indicator_key}_1.5"),
        ],
        [
            InlineKeyboardButton("خیلی زیاد (۲×)", callback_data=f"stratw_{indicator_key}_2.0"),
            InlineKeyboardButton("غالب (۳×)", callback_data=f"stratw_{indicator_key}_3.0"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def strategy_backtest_market_inline_keyboard(strategy_id):
    """انتخاب بازار برای بک‌تست استراتژی شخصی تازه‌ساخته‌شده."""
    keyboard = [
        [
            InlineKeyboardButton("₿ بیت‌کوین", callback_data=f"stratbt_{strategy_id}_BTC/USD"),
            InlineKeyboardButton("Ξ اتریوم", callback_data=f"stratbt_{strategy_id}_ETH/USD"),
        ],
        [
            InlineKeyboardButton("💶 یورو/دلار", callback_data=f"stratbt_{strategy_id}_EUR/USD"),
            InlineKeyboardButton("🪙 طلا", callback_data=f"stratbt_{strategy_id}_XAU/USD"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


# ============================================================
# دستورات و پیام‌های کاربر عادی
# ============================================================

WELCOME_TEXT = (
    "👋 سلام و خوش آمدید!\n\n"
    "این ربات یک ابزار تحلیل تکنیکال برای بازار کریپتو و فارکس است.\n\n"
    "⚠️ توجه مهم: این ربات صرفاً بر اساس اندیکاتورهای آماری "
    "(RSI, MACD, میانگین متحرک، باندهای بولینگر، استوکاستیک و ATR) "
    "تحلیل ارائه می‌دهد و سود قطعی تضمین نمی‌کند. تصمیمات مالی خود "
    "را با مسئولیت خودتان بگیرید.\n\n"
    "از دکمه‌های پایین صفحه استفاده کنید 👇"
)

HELP_TEXT = (
    "📖 راهنمای استفاده از ربات:\n\n"
    "🔑 فعال‌سازی لایسنس — کد لایسنسی که از ادمین گرفتید را وارد کنید\n"
    "📊 تحلیل تکنیکال — انتخاب بازار و دریافت تحلیل (نیاز به لایسنس فعال)\n"
    "👤 وضعیت اشتراک من — مشاهده تاریخ انقضای لایسنس شما\n\n"
    "برای دریافت لایسنس به مدیر ربات پیام دهید."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lm.register_user_seen(user.id, user.username, user.full_name)
    await update.message.reply_text(WELCOME_TEXT, reply_markup=keyboard_for(user.id))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)


async def activate_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """وقتی کاربر دکمه «فعال‌سازی لایسنس» را می‌زند یا /activate بدون آرگومان می‌فرستد."""
    if context.args:
        await activate_with_key(update, context, context.args[0])
        return
    await update.message.reply_text(
        "🔑 لطفاً کد لایسنس خود را به همین صورت ارسال کنید:\n\n"
        "`XXXX-XXXX-XXXX-XXXX`",
        parse_mode="Markdown",
    )


async def activate_with_key(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str):
    user = update.effective_user
    success, message = lm.activate_license(key, user.id, user.username, user.full_name)
    await update.message.reply_text(message)


async def myinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    info = lm.get_user_license_info(user.id)

    if not info or not info.get("license_key"):
        await update.message.reply_text("❌ شما هنوز لایسنسی فعال نکرده‌اید.\n🔑 از دکمه «فعال‌سازی لایسنس» استفاده کنید.")
        return

    is_valid = lm.is_user_licensed(user.id)
    status = "✅ فعال" if is_valid else "❌ منقضی شده"
    text = (
        f"📋 وضعیت اشتراک شما:\n\n"
        f"وضعیت: {status}\n"
        f"تاریخ انقضا: {info['expires_at'][:10]}\n"
        f"تعداد تحلیل‌های انجام‌شده: {info.get('analysis_count', 0)}"
    )
    await update.message.reply_text(text)


async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    داشبورد عملکرد واقعی — برخلاف هر ادعای دقت ثابت، این عدد از
    سیگنال‌هایی که واقعاً ثبت و با قیمت واقعی بازار ارزیابی شده‌اند
    به‌دست می‌آید. اگر هنوز داده‌ی کافی نباشد، صادقانه همین را می‌گوید.
    """
    dashboard = pt.get_performance_dashboard()
    short = dashboard["short_term"]
    long_ = dashboard["long_term"]

    text = "📈 *داشبورد عملکرد واقعی ربات*\n\n"
    text += f"تعداد کل سیگنال‌های ثبت‌شده: {dashboard['total_signals_logged']}\n\n"

    if short["total"] == 0:
        text += "⏳ هنوز هیچ سیگنالی به مرحله ارزیابی کوتاه‌مدت (۵ کندل) نرسیده است.\n"
    else:
        text += (
            f"🕐 *کوتاه‌مدت (۵ کندل بعد):*\n"
            f"   تعداد ارزیابی‌شده: {short['total']}\n"
            f"   درست: {short['correct']} از {short['total']}\n"
            f"   دقت واقعی: {short['accuracy_pct']}%\n\n"
        )

    if long_["total"] == 0:
        text += "⏳ هنوز هیچ سیگنالی به مرحله ارزیابی بلندمدت (۲۴ ساعت) نرسیده است.\n"
    else:
        text += (
            f"🕓 *بلندمدت (۲۴ ساعت بعد):*\n"
            f"   تعداد ارزیابی‌شده: {long_['total']}\n"
            f"   درست: {long_['correct']} از {long_['total']}\n"
            f"   دقت واقعی: {long_['accuracy_pct']}%\n\n"
        )

    text += (
        "\nℹ️ این اعداد از نتایج واقعی سیگنال‌های گذشته به‌دست آمده‌اند "
        "(نه ادعا یا تخمین). هر چه تعداد نمونه بیشتر شود، این آمار "
        "معتبرتر می‌شود. اعداد نزدیک به ۵۰٪ طبیعی و مطابق با ماهیت "
        "آماری بازارهای مالی است."
    )

    await update.message.reply_text(text, parse_mode="Markdown")


async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    ⚠️ این بخش موقتاً غیرفعال است.
    Finnhub اندپوینت تقویم اقتصادی رایگان (/calendar/economic) را به
    مشتریان Enterprise (پولی) محدود کرده و دیگر برای پلن رایگان در
    دسترس نیست (خطای HTTP 403). تا زمانی که یک منبع رایگان و معتبر
    جایگزین پیدا شود، این بخش غیرفعال می‌ماند تا خطای خام به کاربر
    نشان داده نشود.
    """
    await update.message.reply_text(
        "📰 بخش اخبار اقتصادی موقتاً غیرفعال است.\n\n"
        "دلیل: سرویس Finnhub دسترسی رایگان به تقویم اقتصادی را قطع کرده "
        "و این قابلیت اکنون فقط برای مشتریان پولی (Enterprise) در دسترس "
        "است. تحلیل تکنیکال و سایر بخش‌های ربات بدون مشکل کار می‌کنند."
    )
    return

    try:
        upcoming = nc.get_upcoming_high_impact(FINNHUB_API_KEY, within_hours=48)
        recent = nc.get_recent_released(FINNHUB_API_KEY, within_hours=24)
    except Exception as e:
        logger.error(f"خطا در دریافت اخبار اقتصادی: {e}")
        await update.message.reply_text(f"❌ خطا در دریافت اخبار:\n{str(e)}")
        return

    text = "📰 *اخبار اقتصادی*\n"

    if upcoming:
        text += "\n🔴 *رویدادهای پرریسک پیش رو (۴۸ ساعت آینده):*\n"
        for ev in upcoming[:8]:
            time_str = ev["time"].strftime("%Y-%m-%d %H:%M UTC")
            text += f"• {time_str} | {ev['country']} | {ev['event']}\n"
    else:
        text += "\n✅ در ۴۸ ساعت آینده رویداد پرریسک شناخته‌شده‌ای ثبت نشده است.\n"

    if recent:
        text += "\n📊 *اخیراً منتشرشده (مقایسه با پیش‌بینی بازار):*\n"
        for ev in recent[:5]:
            comparison = nc.compare_actual_vs_forecast(ev)
            text += f"• {ev['event']} ({ev['country']})\n  {comparison}\n"

    text += (
        "\nℹ️ این هشدار فقط زمان احتمالی نوسان شدید را نشان می‌دهد و "
        "جهت حرکت بازار را پیش‌بینی نمی‌کند. در بازه‌های پرریسک، احتیاط "
        "بیشتری در مدیریت حجم و Stop Loss توصیه می‌شود."
    )

    await update.message.reply_text(text, parse_mode="Markdown")


async def strategy_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش منوی اصلی بخش استراتژی شخصی کاربر."""
    user = update.effective_user
    if not lm.is_user_licensed(user.id):
        await update.message.reply_text(
            "🔒 برای استفاده از این بخش، نیاز به لایسنس فعال دارید.\n"
            "🔑 از دکمه «فعال‌سازی لایسنس» استفاده کنید."
        )
        return

    text = (
        "🧪 *استراتژی شخصی شما*\n\n"
        "می‌توانید برای ۵ اندیکاتور اصلی (RSI، MACD، میانگین متحرک، "
        "بولینگر، استوکاستیک) یک ضریب وزن شخصی انتخاب کنید. هر استراتژی "
        "فوراً با بک‌تست Walk-Forward روی داده‌ی واقعی ارزیابی می‌شود و "
        "نتیجه‌ی *واقعی* (نه ادعا) به شما نشان داده می‌شود."
    )
    await update.message.reply_text(text, reply_markup=strategy_menu_inline_keyboard(), parse_mode="Markdown")


async def handle_strategy_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت دکمه‌های منوی اصلی استراتژی (ساخت جدید / لیست استراتژی‌ها)."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    action = query.data

    if action == "strategy_new":
        # شروع فرآیند ساخت استراتژی - state را در user_data ذخیره می‌کنیم
        context.user_data["strategy_build"] = {"weights": {}, "step_index": 0}
        first_indicator = STRATEGY_BUILD_STEPS[0]
        await query.edit_message_text(
            f"⚙️ مرحله ۱ از {len(STRATEGY_BUILD_STEPS)}:\n"
            f"ضریب وزن *{INDICATOR_DISPLAY_NAMES[first_indicator]}* را انتخاب کنید:",
            reply_markup=weight_selection_inline_keyboard(first_indicator),
            parse_mode="Markdown",
        )

    elif action == "strategy_list":
        await send_user_strategy_list(query, user_id)


async def handle_strategy_weight_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    وقتی کاربر ضریب وزن یک اندیکاتور را در فرآیند ساخت استراتژی انتخاب می‌کند.
    این تابع کاربر را به مرحله بعد می‌برد، یا اگر آخرین مرحله بود، نام
    استراتژی را می‌پرسد و سپس بک‌تست را شروع می‌کند.
    """
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not lm.is_user_licensed(user_id):
        await query.edit_message_text("🔒 لایسنس شما معتبر نیست.")
        return

    # فرمت: stratw_{indicator}_{multiplier}
    payload = query.data.split("_", 1)[1]
    indicator_key, multiplier_str = payload.rsplit("_", 1)
    multiplier = float(multiplier_str)

    build_state = context.user_data.get("strategy_build")
    if not build_state:
        await query.edit_message_text("❌ فرآیند ساخت استراتژی منقضی شده. دوباره از منو شروع کنید.")
        return

    build_state["weights"][indicator_key] = multiplier
    build_state["step_index"] += 1

    if build_state["step_index"] < len(STRATEGY_BUILD_STEPS):
        next_indicator = STRATEGY_BUILD_STEPS[build_state["step_index"]]
        await query.edit_message_text(
            f"⚙️ مرحله {build_state['step_index'] + 1} از {len(STRATEGY_BUILD_STEPS)}:\n"
            f"ضریب وزن *{INDICATOR_DISPLAY_NAMES[next_indicator]}* را انتخاب کنید:",
            reply_markup=weight_selection_inline_keyboard(next_indicator),
            parse_mode="Markdown",
        )
    else:
        # همه‌ی وزن‌ها انتخاب شدند - یک نام پیش‌فرض می‌سازیم و وارد بک‌تست می‌شویم
        weights = build_state["weights"]
        strategy_name = "استراتژی " + "/".join(f"{k}:{v}x" for k, v in weights.items())
        strategy_id = us.create_strategy(user_id, name=strategy_name, weights=weights)
        context.user_data.pop("strategy_build", None)

        await query.edit_message_text(
            f"✅ استراتژی شما ساخته شد!\n\n"
            f"وزن‌ها: {weights}\n\n"
            f"📐 حالا یک بازار برای بک‌تست Walk-Forward انتخاب کنید:",
            reply_markup=strategy_backtest_market_inline_keyboard(strategy_id),
        )


async def handle_strategy_backtest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اجرای بک‌تست Walk-Forward واقعی روی استراتژی شخصی کاربر، روی بازار انتخاب‌شده."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # فرمت: stratbt_{strategy_id}_{symbol}
    payload = query.data.split("_", 1)[1]
    strategy_id, symbol = payload.rsplit("_", 1)
    display_name = SYMBOL_DISPLAY_NAMES.get(symbol, symbol)

    user_strategies = us.get_user_strategies(user_id)
    if strategy_id not in user_strategies:
        await query.edit_message_text("❌ استراتژی پیدا نشد.")
        return

    weights = user_strategies[strategy_id]["weights"]

    await query.edit_message_text(
        f"⏳ در حال اجرای بک‌تست Walk-Forward استراتژی شما روی {display_name} ...\n"
        f"این عملیات ممکن است ۳۰ تا ۶۰ ثانیه طول بکشد."
    )

    if not TWELVE_DATA_API_KEY:
        await query.edit_message_text("❌ کلید API تنظیم نشده است.")
        return

    try:
        df = analysis.get_market_data(symbol=symbol, api_key=TWELVE_DATA_API_KEY, interval="1h", outputsize=2000)
        result = bte.run_walk_forward_backtest(df, n_windows=6, horizon=5, user_weight_multipliers=weights)
        us.save_backtest_result(user_id, strategy_id, result)
        report = bte.format_backtest_report(result, symbol=f"استراتژی شخصی شما روی {display_name}")
        await query.edit_message_text(report, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"خطا در بک‌تست استراتژی {strategy_id}: {e}")
        await query.edit_message_text(f"❌ خطا در اجرای بک‌تست:\n{str(e)}")


async def send_user_strategy_list(query, user_id):
    """نمایش لیست استراتژی‌های ساخته‌شده‌ی کاربر همراه با نتیجه بک‌تست (اگر موجود باشد)."""
    strategies = us.get_user_strategies(user_id)
    if not strategies:
        await query.edit_message_text("📭 شما هنوز هیچ استراتژی‌ای نساخته‌اید.")
        return

    lines = ["📋 *استراتژی‌های شما:*\n"]
    for sid, data in strategies.items():
        lines.append(f"🔹 {data['name']}")
        result = data.get("backtest_result")
        if result and "error" not in result:
            lines.append(
                f"   📊 دقت واقعی: {result['mean_accuracy']}% "
                f"(از {result['total_signals']} سیگنال, نوسان بین پنجره‌ها: {result['std_accuracy']}%)"
            )
        else:
            lines.append("   ⏳ هنوز بک‌تست نشده")
        lines.append("")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n... (لیست بیشتر از حد نمایش است)"
    await query.edit_message_text(text, parse_mode="Markdown")


async def analyze_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not lm.is_user_licensed(user.id):
        await update.message.reply_text(
            "🔒 برای استفاده از تحلیل، نیاز به لایسنس فعال دارید.\n"
            "🔑 از دکمه «فعال‌سازی لایسنس» استفاده کنید."
        )
        return

    await update.message.reply_text(
        "📊 لطفاً بازار مورد نظر خود را انتخاب کنید:",
        reply_markup=market_selection_inline_keyboard(),
    )


async def handle_symbol_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """وقتی کاربر یک بازار را انتخاب می‌کند - حالا باید تایم‌فریم را بپرسیم."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if not lm.is_user_licensed(user_id):
        await query.edit_message_text("🔒 لایسنس شما معتبر نیست.")
        return

    symbol = query.data.split("_", 1)[1]  # مثلا: BTC/USD یا EUR/USD
    display_name = SYMBOL_DISPLAY_NAMES.get(symbol, symbol)

    await query.edit_message_text(
        f"📊 بازار انتخاب‌شده: *{display_name}*\n⏱ لطفاً تایم‌فریم مورد نظر را انتخاب کنید:",
        reply_markup=timeframe_selection_inline_keyboard(symbol),
        parse_mode="Markdown",
    )


async def handle_back_to_markets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دکمه بازگشت از مرحله تایم‌فریم به مرحله انتخاب بازار."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📊 لطفاً بازار مورد نظر خود را انتخاب کنید:",
        reply_markup=market_selection_inline_keyboard(),
    )


async def handle_analysis_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """وقتی کاربر تایم‌فریم را هم انتخاب کرد - حالا تحلیل واقعی اجرا می‌شود."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if not lm.is_user_licensed(user_id):
        await query.edit_message_text("🔒 لایسنس شما معتبر نیست.")
        return

    # فرمت: analyze_{symbol}_{interval} — سیمبل ممکن است / داشته باشد اما interval هرگز _ ندارد
    payload = query.data.split("_", 1)[1]      # حذف پیشوند "analyze"، مثلا: "BTC/USD_15min"
    symbol, interval = payload.rsplit("_", 1)   # جدا کردن از آخر، مثلا: ("BTC/USD", "15min")

    display_name = SYMBOL_DISPLAY_NAMES.get(symbol, symbol)
    timeframe_name = TIMEFRAME_DISPLAY_NAMES.get(interval, interval)

    await query.edit_message_text(f"⏳ در حال دریافت داده و تحلیل {display_name} (تایم‌فریم {timeframe_name}) ...")

    if not TWELVE_DATA_API_KEY:
        await query.edit_message_text(
            "❌ کلید API تنظیم نشده است.\n"
            "ادمین باید متغیر TWELVE_DATA_API_KEY را در Railway تنظیم کند."
        )
        return

    try:
        df = analysis.get_market_data(symbol=symbol, api_key=TWELVE_DATA_API_KEY, interval=interval, outputsize=200)
        result = analysis.generate_signal(df)

        if "error" in result:
            await query.edit_message_text(f"❌ {result['error']}")
            return

        lm.increment_analysis_count(user_id)

        # هشدار ریسک خبری: موقتاً غیرفعال - Finnhub اندپوینت رایگان تقویم
        # اقتصادی را قطع کرده است (نیاز به پلن Enterprise). به‌جای تلاش
        # بیهوده برای فراخوانی API، مستقیماً None در نظر گرفته می‌شود.
        news_warning = None

        details_text = "\n".join(result["details"])
        text = ""
        if news_warning:
            text += f"{news_warning}\n\n"

        text += (
            f"📊 *تحلیل تکنیکال {display_name}*\n"
            f"💰 قیمت فعلی: `{result['price']}`\n"
            f"{details_text}\n"
            f"{result['final_verdict']} (امتیاز {result['score']}/{result['max_score']})\n"
            f"{result['risk_level']} (ATR: {result['atr_percent']}%)"
        )

        if result["trade_plan"]:
            tp_plan = result["trade_plan"]
            text += (
                f"\n📐 *پلن معاملاتی (برای ثبت دستی در متاتریدر):*\n"
                f"جهت: `{tp_plan['direction']}`\n"
                f"ورود: `{tp_plan['entry']}`\n"
                f"حد ضرر: `{tp_plan['stop_loss']}`\n"
                f"حد سود: `{tp_plan['take_profit']}`\n"
                f"ریسک به ریوارد: ۱:{tp_plan['risk_reward_ratio']} | فاصله ریسک: {tp_plan['sl_distance_pct']}%"
            )

            # ثبت سیگنال برای ارزیابی واقعی بعدی (داشبورد عملکرد)
            direction_short = "BUY" if "BUY" in tp_plan["direction"] else "SELL"
            pt.log_signal(
                symbol=symbol,
                direction=direction_short,
                score=result["score"],
                entry_price=result["price"],
                interval=interval,
                user_id=user_id,
            )
            text += "\n📊 این سیگنال ثبت شد و نتیجه‌اش در «داشبورد عملکرد» قابل مشاهده خواهد بود."
        else:
            text += "\n➖ سیگنال خنثی — پلن معاملاتی پیشنهاد نمی‌شود."

        text += f"\n{result['disclaimer']}"

        await query.edit_message_text(text, parse_mode="Markdown")

        # ارسال نمودار تصویری به‌صورت پیام جدا (بعد از متن تحلیل)
        try:
            chart_path = cg.generate_chart(df, symbol=symbol, interval=interval)
            with open(chart_path, "rb") as chart_file:
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=chart_file,
                    caption=f"📈 نمودار {display_name} | تایم‌فریم {timeframe_name}",
                )
            os.remove(chart_path)  # پاک‌سازی فایل موقت بعد از ارسال - جلوگیری از پر شدن دیسک سرور
        except Exception as chart_err:
            # شکست در رسم نمودار نباید کل تحلیل را خراب کند - فقط لاگ می‌شود
            logger.warning(f"خطا در ساخت/ارسال نمودار {symbol}: {chart_err}")

    except Exception as e:
        logger.error(f"خطا در تحلیل {symbol}: {e}")
        await query.edit_message_text(f"❌ خطا در دریافت داده:\n{str(e)}")


# ============================================================
# پنل مدیریت ادمین
# ============================================================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ شما دسترسی ادمین ندارید.")
        return

    stats = lm.get_stats()
    text = (
        "🛠 *پنل مدیریت ربات*\n\n"
        f"👥 کل کاربران: {stats['total_users']}\n"
        f"✅ اشتراک‌های فعال: {stats['active_licenses']}\n"
        f"🎫 کل لایسنس‌های ساخته‌شده: {stats['total_licenses_created']}\n"
        f"📊 کل تحلیل‌های انجام‌شده: {stats['total_analyses']}\n\n"
        "یک گزینه را انتخاب کنید:"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=admin_panel_inline_keyboard())


async def handle_admin_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت کلیک روی دکمه‌های پنل ادمین."""
    query = update.callback_query
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.answer("⛔ دسترسی ادمین ندارید.", show_alert=True)
        return

    await query.answer()
    action = query.data

    if action == "admin_genlicense":
        await query.edit_message_text(
            "⏳ مدت اعتبار لایسنس را انتخاب کنید:",
            reply_markup=genlicense_days_inline_keyboard(),
        )

    elif action == "admin_listlicenses":
        await send_license_list(query)

    elif action == "admin_stats":
        await send_full_stats(query)

    elif action == "admin_listusers":
        await send_user_list(query)

    elif action == "admin_broadcast":
        PENDING_BROADCAST.add(user_id)
        await query.edit_message_text(
            "📢 متن پیامی که می‌خواهید به همه کاربران ارسال شود را در پیام بعدی بنویسید.\n"
            "برای انصراف /cancel را بفرستید."
        )

    elif action == "admin_backtest":
        await query.edit_message_text(
            "📐 لطفاً بازاری که می‌خواهید روی آن بک‌تست Walk-Forward اجرا شود را انتخاب کنید:\n"
            "(این عملیات ممکن است تا ۱ دقیقه طول بکشد)",
            reply_markup=backtest_market_inline_keyboard(),
        )

    elif action == "admin_strategyrank":
        await send_strategy_ranking(query)


async def handle_genlicense_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """وقتی ادمین مدت اعتبار لایسنس را از دکمه‌ها انتخاب می‌کند."""
    query = update.callback_query
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.answer("⛔ دسترسی ادمین ندارید.", show_alert=True)
        return

    await query.answer()
    days = int(query.data.split("_")[-1])

    key = lm.create_license(days_valid=days, created_by=user_id)
    await query.edit_message_text(
        f"✅ لایسنس جدید ساخته شد:\n\n"
        f"`{key}`\n\n"
        f"⏳ اعتبار: {days} روز پس از فعال‌سازی\n\n"
        f"این کد را برای کاربر ارسال کنید تا با دکمه «فعال‌سازی لایسنس» فعالش کند.",
        parse_mode="Markdown",
    )


async def handle_run_backtest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    اجرای واقعی بک‌تست Walk-Forward روی بازار انتخاب‌شده توسط ادمین.
    این عملیات سنگین است (صدها/هزاران فراخوانی محاسباتی)، پس پیام
    «در حال اجرا» نشان داده می‌شود تا تجربه کاربر گیج‌کننده نباشد.
    """
    query = update.callback_query
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.answer("⛔ دسترسی ادمین ندارید.", show_alert=True)
        return

    await query.answer()
    symbol = query.data.split("_", 1)[1]
    display_name = SYMBOL_DISPLAY_NAMES.get(symbol, symbol)

    await query.edit_message_text(
        f"⏳ در حال اجرای بک‌تست Walk-Forward روی {display_name} ...\n"
        f"این عملیات ممکن است ۳۰ تا ۶۰ ثانیه طول بکشد."
    )

    if not TWELVE_DATA_API_KEY:
        await query.edit_message_text("❌ کلید API تنظیم نشده است.")
        return

    try:
        # برای بک‌تست معنادار، حداکثر داده‌ی ممکن (تا سقف outputsize پلن رایگان) می‌گیریم
        df = analysis.get_market_data(symbol=symbol, api_key=TWELVE_DATA_API_KEY, interval="1h", outputsize=2000)
        result = bte.run_walk_forward_backtest(df, n_windows=6, horizon=5)
        report = bte.format_backtest_report(result, symbol=display_name)
        await query.edit_message_text(report, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"خطا در اجرای بک‌تست {symbol}: {e}")
        await query.edit_message_text(f"❌ خطا در اجرای بک‌تست:\n{str(e)}")


async def send_license_list(query):
    licenses = lm.list_all_licenses()
    if not licenses:
        await query.edit_message_text("📭 هیچ لایسنسی ساخته نشده است.")
        return

    lines = ["📋 *لیست لایسنس‌ها:*\n"]
    for key, info in list(licenses.items())[-30:]:  # آخرین ۳۰ مورد
        if info.get("revoked"):
            status = "🚫 باطل‌شده"
        elif info["used_count"] >= info["max_uses"]:
            status = "✅ استفاده‌شده"
        else:
            status = "⬜ استفاده‌نشده"
        lines.append(f"`{key}` — {status} — {info['days_valid']} روز")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n... (لیست بیشتر از حد نمایش است)"
    await query.edit_message_text(text, parse_mode="Markdown")


async def send_full_stats(query):
    stats = lm.get_stats()
    text = (
        "📈 *آمار کامل سیستم*\n\n"
        f"👥 کل کاربران ثبت‌شده: {stats['total_users']}\n"
        f"✅ اشتراک‌های فعال فعلی: {stats['active_licenses']}\n"
        f"🚫 کاربران مسدود: {stats['banned_users']}\n\n"
        f"🎫 کل لایسنس‌های ساخته‌شده: {stats['total_licenses_created']}\n"
        f"⬜ لایسنس‌های استفاده‌نشده: {stats['unused_licenses']}\n\n"
        f"📊 کل تحلیل‌های انجام‌شده: {stats['total_analyses']}\n"
        f"🚀 کل دفعات اجرای /start: {stats['total_starts']}"
    )
    await query.edit_message_text(text, parse_mode="Markdown")


async def send_user_list(query):
    users = lm.get_all_users()
    if not users:
        await query.edit_message_text("📭 هیچ کاربری ثبت نشده است.")
        return

    lines = ["👥 *لیست کاربران (۳۰ مورد آخر):*\n"]
    for uid, info in list(users.items())[-30:]:
        is_valid = lm.is_user_licensed(int(uid))
        status = "✅" if is_valid else "❌"
        ban_mark = " 🚫" if info.get("banned") else ""
        username = f"@{info['username']}" if info.get("username") else "بدون‌یوزرنیم"
        lines.append(f"{status} `{uid}` — {username}{ban_mark}")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n... (لیست بیشتر از حد نمایش است)"
    await query.edit_message_text(text, parse_mode="Markdown")


async def send_strategy_ranking(query):
    """
    نمایش رتبه‌بندی استراتژی‌های کاربران بر اساس نتیجه‌ی واقعی بک‌تست،
    به همراه الگوهای مشترک بین استراتژی‌های برتر.

    ⚠️ فقط استراتژی‌هایی با حداقل ۳۰ سیگنال بک‌تست‌شده رتبه‌بندی می‌شوند
    تا از نتیجه‌گیری بر اساس نمونه‌ی آماری کوچک (که می‌تواند تصادفی
    باشد) جلوگیری شود.
    """
    ranked = us.rank_strategies_by_performance(min_signals=30)

    if not ranked:
        await query.edit_message_text(
            "📭 هنوز هیچ استراتژی‌ای با تعداد سیگنال کافی (حداقل ۳۰) برای "
            "رتبه‌بندی معتبر بک‌تست نشده است."
        )
        return

    lines = ["🏆 *رتبه‌بندی استراتژی‌های کاربران (واقعی، بر اساس بک‌تست):*\n"]
    for i, strat in enumerate(ranked[:10], start=1):
        lines.append(
            f"{i}. کاربر `{strat['user_id']}` — دقت {strat['mean_accuracy']}% "
            f"({strat['total_signals']} سیگنال, نوسان {strat['std_accuracy']}%)"
        )

    patterns = us.get_common_patterns_in_top_strategies(top_n=10, min_signals=30)
    if patterns:
        lines.append(f"\n📊 *میانگین وزن اندیکاتورها در {patterns['n_strategies_analyzed']} استراتژی برتر:*")
        for indicator, avg_weight in patterns["average_weights"].items():
            display = INDICATOR_DISPLAY_NAMES.get(indicator, indicator)
            lines.append(f"   {display}: میانگین ضریب {avg_weight}×")

    lines.append(
        "\nℹ️ این مشاهده‌ی آماری از داده‌ی موجود است، نه یک قانون قطعی. "
        "با تعداد کم استراتژی، الگوهای مشترک می‌توانند تصادفی باشند و "
        "نباید به‌عنوان توصیه قطعی در نظر گرفته شوند."
    )

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n... (لیست بیشتر از حد نمایش است)"
    await query.edit_message_text(text, parse_mode="Markdown")


async def cmd_revoke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ شما دسترسی ادمین ندارید.")
        return
    if not context.args:
        await update.message.reply_text("❗ کد لایسنس را وارد کنید.\nمثال: /revoke XXXX-XXXX-XXXX-XXXX")
        return

    success = lm.revoke_license(context.args[0])
    if success:
        await update.message.reply_text(f"✅ لایسنس `{context.args[0].upper()}` باطل شد.", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ این کد لایسنس پیدا نشد.")


async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ شما دسترسی ادمین ندارید.")
        return
    if not context.args:
        await update.message.reply_text("❗ آیدی کاربر را وارد کنید.\nمثال: /ban 123456789")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❗ آیدی باید عدد باشد.")
        return

    success = lm.ban_user(target_id)
    if success:
        await update.message.reply_text(f"✅ کاربر {target_id} مسدود شد.")
    else:
        await update.message.reply_text("❌ این کاربر در سیستم پیدا نشد.")


async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ شما دسترسی ادمین ندارید.")
        return
    if not context.args:
        await update.message.reply_text("❗ آیدی کاربر را وارد کنید.\nمثال: /unban 123456789")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❗ آیدی باید عدد باشد.")
        return

    success = lm.unban_user(target_id)
    if success:
        await update.message.reply_text(f"✅ مسدودیت کاربر {target_id} رفع شد.")
    else:
        await update.message.reply_text("❌ این کاربر در سیستم پیدا نشد.")


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    PENDING_BROADCAST.discard(user.id)
    await update.message.reply_text("عملیات لغو شد.", reply_markup=keyboard_for(user.id))


# ============================================================
# مسیریابی پیام‌های متنی (دکمه‌های کیبورد دائمی + ورودی‌های آزاد)
# ============================================================

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    تمام پیام‌های متنی غیر-دستوری از اینجا رد می‌شوند:
    - دکمه‌های کیبورد دائمی
    - کد لایسنس (وقتی فرمت XXXX-XXXX-XXXX-XXXX دارد)
    - متن broadcast ادمین (وقتی در حالت انتظار است)
    """
    user = update.effective_user
    text = update.message.text.strip()
    lm.register_user_seen(user.id, user.username, user.full_name)

    # حالت: ادمین در انتظار وارد کردن متن broadcast است
    if user.id in PENDING_BROADCAST:
        PENDING_BROADCAST.discard(user.id)
        await send_broadcast(update, context, text)
        return

    # دکمه‌های کیبورد دائمی
    if text == "📊 تحلیل تکنیکال":
        await analyze_prompt(update, context)
        return
    if text == "🔑 فعال‌سازی لایسنس":
        await activate_prompt(update, context)
        return
    if text == "👤 وضعیت اشتراک من":
        await myinfo(update, context)
        return
    if text == "📈 داشبورد عملکرد":
        await dashboard_command(update, context)
        return
    if text == "📰 اخبار اقتصادی":
        await news_command(update, context)
        return
    if text == "🧪 استراتژی شخصی من":
        await strategy_menu_command(update, context)
        return
    if text == "ℹ️ راهنما":
        await help_command(update, context)
        return
    if text == "🛠 پنل مدیریت":
        await admin_panel(update, context)
        return

    # اگر فرمت شبیه کد لایسنس بود (مثل XXXX-XXXX-XXXX-XXXX)، فعال‌سازی را امتحان کن
    cleaned = text.upper().replace(" ", "")
    if len(cleaned) == 19 and cleaned.count("-") == 3:
        await activate_with_key(update, context, cleaned)
        return

    # هیچ‌کدام نبود → راهنمایی کلی
    await update.message.reply_text(
        "متوجه نشدم 🤔 لطفاً از دکمه‌های پایین صفحه استفاده کنید.",
        reply_markup=keyboard_for(user.id),
    )


async def send_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """ارسال پیام همگانی به تمام کاربران ثبت‌شده."""
    users = lm.get_all_users()
    sent, failed = 0, 0

    await update.message.reply_text(f"📢 شروع ارسال به {len(users)} کاربر...")

    for uid in users:
        try:
            await context.bot.send_message(chat_id=int(uid), text=f"📢 پیام از مدیریت:\n\n{text}")
            sent += 1
        except Exception as e:
            logger.warning(f"ارسال به {uid} ناموفق: {e}")
            failed += 1

    await update.message.reply_text(f"✅ ارسال کامل شد.\nموفق: {sent} | ناموفق: {failed}")


# ============================================================
# Job دوره‌ای پشت‌صحنه: ارزیابی خودکار سیگنال‌های سررسیدشده
# ============================================================

async def evaluate_pending_signals_job(context: ContextTypes.DEFAULT_TYPE):
    """
    هر چند دقیقه یک‌بار اجرا می‌شود (توسط JobQueue). برای هر سیگنالی
    که زمان ارزیابی کوتاه‌مدت یا بلندمدتش رسیده، قیمت واقعی فعلی را
    از Twelve Data می‌گیرد و نتیجه‌ی واقعی سیگنال را ثبت می‌کند.
    """
    if not TWELVE_DATA_API_KEY:
        return

    pending = pt.get_pending_evaluations()
    if not pending:
        return

    # برای کم‌کردن تعداد درخواست API، قیمت هر سیمبل را فقط یک‌بار می‌گیریم
    symbols_needed = {info["symbol"] for _, info, _ in pending}
    current_prices = {}

    for symbol in symbols_needed:
        try:
            df = analysis.get_market_data(symbol=symbol, api_key=TWELVE_DATA_API_KEY, interval="1h", outputsize=2)
            current_prices[symbol] = df["close"].iloc[-1]
        except Exception as e:
            logger.warning(f"دریافت قیمت برای ارزیابی {symbol} ناموفق: {e}")

    evaluated_count = 0
    for signal_id, info, horizon in pending:
        symbol = info["symbol"]
        if symbol not in current_prices:
            continue
        pt.record_evaluation_result(signal_id, horizon, current_prices[symbol])
        evaluated_count += 1

    if evaluated_count:
        logger.info(f"📊 {evaluated_count} سیگنال ارزیابی شد.")


# ============================================================
# اجرای اصلی ربات
# ============================================================

def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "❌ متغیر محیطی BOT_TOKEN تنظیم نشده است. "
            "آن را در پنل Railway بخش Variables اضافه کنید."
        )
    if ADMIN_ID == 0:
        logger.warning("⚠️ ADMIN_ID تنظیم نشده — دستورات ادمین برای هیچکس کار نمی‌کند.")

    app = Application.builder().token(BOT_TOKEN).build()

    # دستورات کاربر عادی
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("activate", activate_prompt))
    app.add_handler(CommandHandler("myinfo", myinfo))
    app.add_handler(CommandHandler("analyze", analyze_prompt))
    app.add_handler(CommandHandler("dashboard", dashboard_command))
    app.add_handler(CommandHandler("news", news_command))
    app.add_handler(CommandHandler("cancel", cmd_cancel))

    # دستورات ادمین
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("revoke", cmd_revoke))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))

    # دکمه‌های شیشه‌ای (inline)
    app.add_handler(CallbackQueryHandler(handle_symbol_selection, pattern="^selectsym_"))
    app.add_handler(CallbackQueryHandler(handle_back_to_markets, pattern="^backtomarkets$"))
    app.add_handler(CallbackQueryHandler(handle_analysis_button, pattern="^analyze_"))
    app.add_handler(CallbackQueryHandler(handle_genlicense_days, pattern="^genlic_days_"))
    app.add_handler(CallbackQueryHandler(handle_run_backtest, pattern="^runbacktest_"))
    app.add_handler(CallbackQueryHandler(handle_strategy_menu_button, pattern="^strategy_"))
    app.add_handler(CallbackQueryHandler(handle_strategy_weight_selection, pattern="^stratw_"))
    app.add_handler(CallbackQueryHandler(handle_strategy_backtest, pattern="^stratbt_"))
    app.add_handler(CallbackQueryHandler(handle_admin_button, pattern="^admin_"))

    # پیام‌های متنی (دکمه‌های کیبورد دائمی + کد لایسنس + broadcast)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    # Job دوره‌ای: هر ۱۵ دقیقه سیگنال‌های سررسیدشده را ارزیابی می‌کند
    app.job_queue.run_repeating(evaluate_pending_signals_job, interval=900, first=60)

    logger.info("🤖 ربات در حال اجراست...")
    app.run_polling()


if __name__ == "__main__":
    main()
