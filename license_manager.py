"""
license_manager.py
-------------------
مدیریت کامل لایسنس‌ها، کاربران، و آمار سیستم.
داده‌ها به صورت فایل JSON در پوشه data/ ذخیره می‌شوند.

نکته: برای حجم کاربر بالا (چند هزار کاربر فعال)، بهتر است به
SQLite یا PostgreSQL مهاجرت شود. این پیاده‌سازی برای پروژه‌های
کوچک تا متوسط کاملاً کافی و قابل اعتماد است.
"""

import json
import os
import random
import string
from datetime import datetime, timedelta

DATA_DIR = "data"
LICENSES_FILE = os.path.join(DATA_DIR, "licenses.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
STATS_FILE = os.path.join(DATA_DIR, "stats.json")


# ============================================================
# توابع کمکی داخلی
# ============================================================

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
# ساخت و فعال‌سازی لایسنس
# ============================================================

def generate_license_key():
    """کد لایسنس به فرمت XXXX-XXXX-XXXX-XXXX می‌سازد."""
    chars = string.ascii_uppercase + string.digits
    return "-".join("".join(random.choices(chars, k=4)) for _ in range(4))


def create_license(days_valid=30, created_by=None, note="", max_uses=1):
    """
    ساخت یک لایسنس جدید توسط ادمین.

    days_valid: تعداد روز اعتبار پس از فعال‌سازی
    max_uses: چند کاربر مختلف می‌توانند همین کد را فعال کنند (پیش‌فرض 1)
    """
    licenses = _load_json(LICENSES_FILE)

    key = generate_license_key()
    while key in licenses:
        key = generate_license_key()

    licenses[key] = {
        "days_valid": days_valid,
        "created_by": created_by,
        "created_at": _now().isoformat(),
        "note": note,
        "max_uses": max_uses,
        "used_count": 0,
        "used_by": [],          # لیست آیدی کاربرانی که فعالش کرده‌اند
        "revoked": False,
    }
    _save_json(LICENSES_FILE, licenses)
    _increment_stat("licenses_created")
    return key


def activate_license(key, user_id, username=None, full_name=None):
    """فعال‌سازی لایسنس برای یک کاربر. خروجی: (موفقیت: bool, پیام: str)"""
    key = key.strip().upper()
    licenses = _load_json(LICENSES_FILE)

    if key not in licenses:
        return False, "❌ کد لایسنس نامعتبر است."

    lic = licenses[key]

    if lic.get("revoked"):
        return False, "❌ این لایسنس باطل شده است."

    if user_id in lic["used_by"]:
        return False, "⚠️ شما قبلاً همین لایسنس را فعال کرده‌اید."

    if lic["used_count"] >= lic["max_uses"]:
        return False, "❌ ظرفیت استفاده از این لایسنس تمام شده است."

    now = _now()
    expires = now + timedelta(days=lic["days_valid"])

    lic["used_count"] += 1
    lic["used_by"].append(user_id)
    licenses[key] = lic
    _save_json(LICENSES_FILE, licenses)

    users = _load_json(USERS_FILE)
    users[str(user_id)] = {
        "username": username,
        "full_name": full_name,
        "license_key": key,
        "activated_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "joined_at": users.get(str(user_id), {}).get("joined_at", now.isoformat()),
        "analysis_count": users.get(str(user_id), {}).get("analysis_count", 0),
        "banned": False,
    }
    _save_json(USERS_FILE, users)
    _increment_stat("licenses_activated")

    return True, (
        f"✅ لایسنس با موفقیت فعال شد!\n"
        f"📅 اعتبار تا: {expires.strftime('%Y-%m-%d')}\n"
        f"⏳ مدت: {lic['days_valid']} روز"
    )


# ============================================================
# بررسی وضعیت کاربر
# ============================================================

def is_user_licensed(user_id):
    """آیا کاربر لایسنس معتبر (فعال و منقضی‌نشده) دارد؟"""
    users = _load_json(USERS_FILE)
    user_data = users.get(str(user_id))

    if not user_data:
        return False
    if user_data.get("banned"):
        return False

    expires_at = datetime.fromisoformat(user_data["expires_at"])
    return _now() < expires_at


def get_user_license_info(user_id):
    users = _load_json(USERS_FILE)
    return users.get(str(user_id))


def register_user_seen(user_id, username=None, full_name=None):
    """هر بار کاربر با ربات تعامل می‌کند، این تابع او را در سیستم ثبت می‌کند
    (حتی اگر لایسنس فعال نکرده باشد) تا در آمار و لیست کاربران دیده شود."""
    users = _load_json(USERS_FILE)
    uid = str(user_id)
    if uid not in users:
        users[uid] = {
            "username": username,
            "full_name": full_name,
            "license_key": None,
            "activated_at": None,
            "expires_at": datetime(1970, 1, 1).isoformat(),
            "joined_at": _now().isoformat(),
            "analysis_count": 0,
            "banned": False,
        }
        _save_json(USERS_FILE, users)
        _increment_stat("total_starts")


def increment_analysis_count(user_id):
    users = _load_json(USERS_FILE)
    uid = str(user_id)
    if uid in users:
        users[uid]["analysis_count"] = users[uid].get("analysis_count", 0) + 1
        _save_json(USERS_FILE, users)
    _increment_stat("total_analyses")


# ============================================================
# مدیریت ادمین
# ============================================================

def list_all_licenses():
    return _load_json(LICENSES_FILE)


def revoke_license(key):
    """باطل کردن یک کد لایسنس (دیگر قابل فعال‌سازی یا استفاده نیست)."""
    key = key.strip().upper()
    licenses = _load_json(LICENSES_FILE)
    if key not in licenses:
        return False
    licenses[key]["revoked"] = True
    _save_json(LICENSES_FILE, licenses)
    return True


def ban_user(user_id):
    """مسدود کردن دسترسی یک کاربر (لایسنسش غیرفعال می‌شود ولی حذف نمی‌شود)."""
    users = _load_json(USERS_FILE)
    uid = str(user_id)
    if uid not in users:
        return False
    users[uid]["banned"] = True
    _save_json(USERS_FILE, users)
    return True


def unban_user(user_id):
    users = _load_json(USERS_FILE)
    uid = str(user_id)
    if uid not in users:
        return False
    users[uid]["banned"] = False
    _save_json(USERS_FILE, users)
    return True


def get_all_users():
    return _load_json(USERS_FILE)


def get_active_users_count():
    users = _load_json(USERS_FILE)
    count = 0
    for uid, data in users.items():
        if data.get("banned"):
            continue
        try:
            if _now() < datetime.fromisoformat(data["expires_at"]):
                count += 1
        except (KeyError, ValueError):
            continue
    return count


# ============================================================
# آمار سیستم
# ============================================================

def _increment_stat(key, amount=1):
    stats = _load_json(STATS_FILE)
    stats[key] = stats.get(key, 0) + amount
    _save_json(STATS_FILE, stats)


def get_stats():
    """خلاصه‌ی آمار کلی سیستم برای نمایش در پنل ادمین."""
    stats = _load_json(STATS_FILE)
    users = _load_json(USERS_FILE)
    licenses = _load_json(LICENSES_FILE)

    total_users = len(users)
    active_licenses = get_active_users_count()
    total_licenses = len(licenses)
    unused_licenses = sum(1 for lic in licenses.values() if lic["used_count"] < lic["max_uses"] and not lic.get("revoked"))
    banned_users = sum(1 for u in users.values() if u.get("banned"))

    return {
        "total_users": total_users,
        "active_licenses": active_licenses,
        "total_licenses_created": total_licenses,
        "unused_licenses": unused_licenses,
        "banned_users": banned_users,
        "total_analyses": stats.get("total_analyses", 0),
        "total_starts": stats.get("total_starts", 0),
    }
