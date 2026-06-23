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

# ============================================================
# تنظیمات (از Environment Variables — هرگز در کد ننویسید)
# ============================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY", None)

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
        [KeyboardButton("👤 وضعیت اشتراک من"), KeyboardButton("ℹ️ راهنما")],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def admin_keyboard():
    """کیبورد دائمی ادمین — شامل دکمه‌های مدیریتی اضافه."""
    buttons = [
        [KeyboardButton("📊 تحلیل تکنیکال"), KeyboardButton("🔑 فعال‌سازی لایسنس")],
        [KeyboardButton("👤 وضعیت اشتراک من"), KeyboardButton("ℹ️ راهنما")],
        [KeyboardButton("🛠 پنل مدیریت")],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def keyboard_for(user_id):
    return admin_keyboard() if is_admin(user_id) else main_keyboard()


def market_selection_inline_keyboard():
    """دکمه‌های شیشه‌ای انتخاب بازار برای تحلیل."""
    keyboard = [
        [
            InlineKeyboardButton("₿ بیت‌کوین (BTC/USD)", callback_data="analyze_BTC/USD"),
            InlineKeyboardButton("Ξ اتریوم (ETH/USD)", callback_data="analyze_ETH/USD"),
        ],
        [
            InlineKeyboardButton("💶 یورو/دلار (EUR/USD)", callback_data="analyze_EUR/USD"),
            InlineKeyboardButton("💷 پوند/دلار (GBP/USD)", callback_data="analyze_GBP/USD"),
        ],
        [
            InlineKeyboardButton("💴 دلار/ین (USD/JPY)", callback_data="analyze_USD/JPY"),
            InlineKeyboardButton("🪙 طلا (XAU/USD)", callback_data="analyze_XAU/USD"),
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
        [InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data="admin_broadcast")],
    ]
    return InlineKeyboardMarkup(keyboard)


def genlicense_days_inline_keyboard():
    """انتخاب سریع مدت اعتبار لایسنس با دکمه."""
    keyboard = [
        [
            InlineKeyboardButton("۷ روز", callback_data="genlic_days_7"),
            InlineKeyboardButton("۱۵ روز", callback_data="genlic_days_15"),
            InlineKeyboardButton("۳۰ روز", callback_data="genlic_days_30"),
        ],
        [
            InlineKeyboardButton("۹۰ روز", callback_data="genlic_days_90"),
            InlineKeyboardButton("۳۶۵ روز", callback_data="genlic_days_365"),
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


async def handle_analysis_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """وقتی کاربر یکی از دکمه‌های شیشه‌ای انتخاب بازار را می‌زند."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if not lm.is_user_licensed(user_id):
        await query.edit_message_text("🔒 لایسنس شما معتبر نیست.")
        return

    symbol = query.data.split("_", 1)[1]  # مثلا: BTC/USD

    await query.edit_message_text(f"⏳ در حال دریافت داده و تحلیل {symbol} ...")

    if not TWELVE_DATA_API_KEY:
        await query.edit_message_text(
            "❌ کلید API تنظیم نشده است.\n"
            "ادمین باید متغیر TWELVE_DATA_API_KEY را در Railway تنظیم کند."
        )
        return

    try:
        df = analysis.get_market_data(symbol=symbol, api_key=TWELVE_DATA_API_KEY, interval="1h", outputsize=200)
        result = analysis.generate_signal(df)

        if "error" in result:
            await query.edit_message_text(f"❌ {result['error']}")
            return

        lm.increment_analysis_count(user_id)

        details_text = "\n".join(result["details"])
        text = (
            f"📊 *تحلیل تکنیکال {symbol}*\n"
            f"💰 قیمت فعلی: `{result['price']}`\n\n"
            f"{details_text}\n\n"
            f"{result['final_verdict']}  (امتیاز {result['score']}/{result['max_score']})\n"
            f"{result['risk_level']} (ATR: {result['atr_percent']}%)\n"
        )

        if result["trade_plan"]:
            tp_plan = result["trade_plan"]
            text += (
                f"\n📐 *پلن معاملاتی پیشنهادی (برای ثبت دستی در متاتریدر):*\n"
                f"جهت: `{tp_plan['direction']}`\n"
                f"نقطه ورود (Entry): `{tp_plan['entry']}`\n"
                f"حد ضرر (Stop Loss): `{tp_plan['stop_loss']}`\n"
                f"حد سود (Take Profit): `{tp_plan['take_profit']}`\n"
                f"نسبت ریسک به ریوارد: ۱:{tp_plan['risk_reward_ratio']}\n"
                f"فاصله ریسک از قیمت: {tp_plan['sl_distance_pct']}%\n"
            )
        else:
            text += "\n➖ سیگنال فعلی خنثی است — پلن معاملاتی پیشنهاد نمی‌شود.\n"

        text += f"\n{result['disclaimer']}"

        await query.edit_message_text(text, parse_mode="Markdown")

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
    app.add_handler(CommandHandler("cancel", cmd_cancel))

    # دستورات ادمین
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("revoke", cmd_revoke))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))

    # دکمه‌های شیشه‌ای (inline)
    app.add_handler(CallbackQueryHandler(handle_analysis_button, pattern="^analyze_"))
    app.add_handler(CallbackQueryHandler(handle_genlicense_days, pattern="^genlic_days_"))
    app.add_handler(CallbackQueryHandler(handle_admin_button, pattern="^admin_"))

    # پیام‌های متنی (دکمه‌های کیبورد دائمی + کد لایسنس + broadcast)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    logger.info("🤖 ربات در حال اجراست...")
    app.run_polling()


if __name__ == "__main__":
    main()
