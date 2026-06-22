"""
bot.py
------
فایل اصلی ربات تلگرام.

نحوه اجرا:
1. متغیرهای محیطی BOT_TOKEN و ADMIN_ID را در Railway تنظیم کنید (نه در کد!)
2. pip install -r requirements.txt
3. python bot.py

دستورات کاربر عادی:
/start - شروع و راهنما
/activate <کد لایسنس> - فعال‌سازی لایسنس
/analyze - دریافت تحلیل تکنیکال (نیاز به لایسنس فعال دارد)
/myinfo - مشاهده وضعیت لایسنس خودم

دستورات ادمین:
/genlicense <روز اعتبار> - ساخت لایسنس جدید
/listlicenses - لیست همه لایسنس‌های ساخته‌شده
/revoke <user_id> - لغو دسترسی یک کاربر
"""

import os
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

import license_manager as lm
import analysis

# ============================================================
# تنظیمات (از Environment Variables خوانده می‌شود — هرگز در کد ننویسید)
# ============================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

# کلید API برای داده فارکس (اختیاری - اگر نداری، فقط بخش کریپتو کار می‌کند)
TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY", None)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# ============================================================
# دستورات کاربر عادی
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 سلام! به ربات تحلیل تکنیکال خوش آمدید.\n\n"
        "📌 دستورات:\n"
        "/activate <کد لایسنس> — فعال‌سازی اشتراک\n"
        "/analyze — دریافت تحلیل تکنیکال\n"
        "/myinfo — وضعیت لایسنس شما\n\n"
        "⚠️ توجه: این ربات صرفاً یک ابزار تحلیل تکنیکال بر اساس "
        "اندیکاتورهای آماری است و سود قطعی تضمین نمی‌کند. تصمیمات "
        "مالی خود را با مسئولیت خودتان بگیرید."
    )
    await update.message.reply_text(welcome_text)


async def activate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text(
            "❗ لطفاً کد لایسنس را وارد کنید.\nمثال:\n/activate XXXX-XXXX-XXXX-XXXX"
        )
        return

    key = context.args[0]
    success, message = lm.activate_license(key, user.id, user.username)
    await update.message.reply_text(message)


async def myinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    info = lm.get_user_license_info(user.id)

    if not info:
        await update.message.reply_text("❌ شما هنوز لایسنسی فعال نکرده‌اید.\nاز /activate استفاده کنید.")
        return

    is_valid = lm.is_user_licensed(user.id)
    status = "✅ فعال" if is_valid else "❌ منقضی شده"
    text = (
        f"📋 وضعیت اشتراک شما:\n"
        f"وضعیت: {status}\n"
        f"تاریخ انقضا: {info['expires_at'][:10]}\n"
    )
    await update.message.reply_text(text)


async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not lm.is_user_licensed(user.id):
        await update.message.reply_text(
            "🔒 برای استفاده از تحلیل، نیاز به لایسنس فعال دارید.\n"
            "از دستور /activate برای فعال‌سازی استفاده کنید."
        )
        return

    # نمایش دکمه‌های انتخاب بازار
    keyboard = [
        [
            InlineKeyboardButton("₿ کریپتو (BTC/USDT)", callback_data="analyze_crypto_BTCUSDT"),
            InlineKeyboardButton("Ξ کریپتو (ETH/USDT)", callback_data="analyze_crypto_ETHUSDT"),
        ],
        [
            InlineKeyboardButton("💱 فارکس (EUR/USD)", callback_data="analyze_forex_EURUSD"),
            InlineKeyboardButton("💱 فارکس (GBP/USD)", callback_data="analyze_forex_GBPUSD"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📊 لطفاً بازار مورد نظر را انتخاب کنید:", reply_markup=reply_markup)


async def handle_analysis_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """وقتی کاربر روی یکی از دکمه‌های انتخاب بازار کلیک می‌کند."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if not lm.is_user_licensed(user_id):
        await query.edit_message_text("🔒 لایسنس شما معتبر نیست.")
        return

    data = query.data  # مثلا: analyze_crypto_BTCUSDT
    parts = data.split("_")
    market_type = parts[1]   # crypto یا forex
    symbol = parts[2]        # BTCUSDT یا EURUSD

    await query.edit_message_text(f"⏳ در حال دریافت داده و تحلیل {symbol} ...")

    try:
        if market_type == "crypto":
            df = analysis.get_crypto_data(symbol=symbol, interval="1h", limit=200)
        else:  # forex
            if not TWELVE_DATA_API_KEY:
                await query.edit_message_text(
                    "❌ برای تحلیل فارکس باید کلید API از twelvedata.com تنظیم شود.\n"
                    "(متغیر محیطی TWELVE_DATA_API_KEY در Railway را تنظیم کنید)"
                )
                return
            df = analysis.get_forex_data(symbol=symbol, api_key=TWELVE_DATA_API_KEY)

        result = analysis.generate_signal(df)

        if "error" in result:
            await query.edit_message_text(f"❌ {result['error']}")
            return

        text = (
            f"📊 تحلیل تکنیکال {symbol}\n"
            f"💰 قیمت فعلی: {result['price']}\n\n"
            f"🔹 {result['rsi_comment']}\n"
            f"🔹 {result['macd_comment']}\n"
            f"🔹 {result['ma_comment']}\n\n"
            f"{result['final_verdict']}\n\n"
            f"{result['disclaimer']}"
        )
        await query.edit_message_text(text)

    except Exception as e:
        logger.error(f"خطا در تحلیل: {e}")
        await query.edit_message_text(f"❌ خطا در دریافت داده: {str(e)}")


# ============================================================
# دستورات ادمین
# ============================================================

async def gen_license(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ شما دسترسی ادمین ندارید.")
        return

    days = 30  # پیش‌فرض
    if context.args:
        try:
            days = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❗ تعداد روز باید عدد باشد. مثال: /genlicense 30")
            return

    key = lm.create_license(days_valid=days, created_by=user.id)
    await update.message.reply_text(
        f"✅ لایسنس جدید ساخته شد:\n\n`{key}`\n\n"
        f"⏳ اعتبار: {days} روز پس از فعال‌سازی\n\n"
        f"این کد را به کاربر بدهید تا با /activate فعالش کند.",
        parse_mode="Markdown",
    )


async def list_licenses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ شما دسترسی ادمین ندارید.")
        return

    licenses = lm.list_all_licenses()
    if not licenses:
        await update.message.reply_text("📭 هیچ لایسنسی ساخته نشده است.")
        return

    lines = ["📋 لیست لایسنس‌ها:\n"]
    for key, info in licenses.items():
        status = "✅ استفاده شده" if info["used"] else "⬜ استفاده نشده"
        lines.append(f"`{key}` — {status} — {info['days_valid']} روز")

    # تلگرام محدودیت طول پیام دارد، اگر زیاد بود قطعش می‌کنیم
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n... (لیست بیشتر از حد نمایش است)"

    await update.message.reply_text(text, parse_mode="Markdown")


async def revoke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ شما دسترسی ادمین ندارید.")
        return

    if not context.args:
        await update.message.reply_text("❗ آیدی کاربر را وارد کنید. مثال: /revoke 123456789")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❗ آیدی باید عدد باشد.")
        return

    success = lm.revoke_user_license(target_id)
    if success:
        await update.message.reply_text(f"✅ دسترسی کاربر {target_id} لغو شد.")
    else:
        await update.message.reply_text("❌ این کاربر در سیستم پیدا نشد.")


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
    app.add_handler(CommandHandler("activate", activate))
    app.add_handler(CommandHandler("myinfo", myinfo))
    app.add_handler(CommandHandler("analyze", analyze))
    app.add_handler(CallbackQueryHandler(handle_analysis_button, pattern="^analyze_"))

    # دستورات ادمین
    app.add_handler(CommandHandler("genlicense", gen_license))
    app.add_handler(CommandHandler("listlicenses", list_licenses))
    app.add_handler(CommandHandler("revoke", revoke))

    logger.info("🤖 ربات در حال اجراست...")
    app.run_polling()


if __name__ == "__main__":
    main()
