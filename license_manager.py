"""
license_manager.py
-------------------
این فایل مسئول مدیریت لایسنس‌ها و کاربرها است.
داده‌ها در یک فایل JSON ذخیره می‌شن (data/licenses.json و data/users.json)

نکته: این یک سیستم لایسنس ساده برای پروژه شخصی/آموزشی است.
اگر قصد فروش تجاری گسترده داری، بهتره از دیتابیس واقعی (PostgreSQL/SQLite) استفاده کنی.
"""

import json
import os
import random
import string
from datetime import datetime, timedelta

# مسیر فایل‌های داده
DATA_DIR = "data"
LICENSES_FILE = os.path.join(DATA_DIR, "licenses.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")


def _ensure_data_dir():
    """اگر پوشه data وجود نداشت، می‌سازیمش."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)


def _load_json(filepath):
    """یک فایل JSON رو می‌خونه. اگر وجود نداشت، دیکشنری خالی برمی‌گردونه."""
    _ensure_data_dir()
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def _save_json(filepath, data):
    """دیکشنری رو به صورت JSON توی فایل ذخیره می‌کنه."""
    _ensure_data_dir()
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def generate_license_key():
    """
    یک کد لایسنس تصادفی و یکتا می‌سازه.
    فرمت: XXXX-XXXX-XXXX-XXXX
    """
    chars = string.ascii_uppercase + string.digits
    parts = []
    for _ in range(4):
        part = "".join(random.choices(chars, k=4))
        parts.append(part)
    return "-".join(parts)


def create_license(days_valid=30, created_by=None, note=""):
    """
    ادمین با این تابع یک لایسنس جدید می‌سازه.
    days_valid: تعداد روزهایی که لایسنس بعد از فعال‌سازی معتبره
    created_by: آیدی عددی ادمینی که لایسنس رو ساخته
    note: یادداشت دلخواه (مثلاً برای چه کسی ساخته شده)

    خروجی: رشته‌ی کد لایسنس
    """
    licenses = _load_json(LICENSES_FILE)

    # تا کد یکتا پیدا نشه، تکرار می‌کنیم (احتمال تکرار خیلی کمه ولی برای اطمینان)
    key = generate_license_key()
    while key in licenses:
        key = generate_license_key()

    licenses[key] = {
        "days_valid": days_valid,
        "created_by": created_by,
        "created_at": datetime.utcnow().isoformat(),
        "note": note,
        "used": False,          # آیا تا الان فعال شده؟
        "used_by": None,        # آیدی تلگرام کاربری که فعالش کرده
        "activated_at": None,   # تاریخ فعال‌سازی
        "expires_at": None,     # تاریخ انقضا (بعد از فعال‌سازی محاسبه می‌شه)
    }
    _save_json(LICENSES_FILE, licenses)
    return key


def activate_license(key, user_id, username=None):
    """
    کاربر یک کد لایسنس وارد می‌کنه و این تابع چک می‌کنه که:
    1. کد وجود داره؟
    2. قبلاً استفاده نشده؟
    اگر همه چی اوکی بود، لایسنس رو برای اون کاربر فعال می‌کنه.

    خروجی: (موفقیت: bool, پیام: str)
    """
    key = key.strip().upper()
    licenses = _load_json(LICENSES_FILE)

    if key not in licenses:
        return False, "❌ کد لایسنس نامعتبر است."

    lic = licenses[key]

    if lic["used"]:
        return False, "❌ این لایسنس قبلاً استفاده شده است."

    now = datetime.utcnow()
    expires = now + timedelta(days=lic["days_valid"])

    lic["used"] = True
    lic["used_by"] = user_id
    lic["activated_at"] = now.isoformat()
    lic["expires_at"] = expires.isoformat()
    licenses[key] = lic
    _save_json(LICENSES_FILE, licenses)

    # ثبت کاربر در فایل users.json
    users = _load_json(USERS_FILE)
    users[str(user_id)] = {
        "username": username,
        "license_key": key,
        "expires_at": expires.isoformat(),
    }
    _save_json(USERS_FILE, users)

    return True, f"✅ لایسنس با موفقیت فعال شد!\nاعتبار تا: {expires.strftime('%Y-%m-%d')}"


def is_user_licensed(user_id):
    """
    چک می‌کنه که آیا کاربر لایسنس معتبر (و منقضی‌نشده) دارد یا نه.
    خروجی: True / False
    """
    users = _load_json(USERS_FILE)
    user_data = users.get(str(user_id))

    if not user_data:
        return False

    expires_at = datetime.fromisoformat(user_data["expires_at"])
    return datetime.utcnow() < expires_at


def get_user_license_info(user_id):
    """اطلاعات لایسنس یک کاربر خاص رو برمی‌گردونه (یا None اگر نداشت)."""
    users = _load_json(USERS_FILE)
    return users.get(str(user_id))


def list_all_licenses():
    """لیست همه‌ی لایسنس‌های ساخته‌شده رو برمی‌گردونه (برای ادمین)."""
    return _load_json(LICENSES_FILE)


def revoke_user_license(user_id):
    """دسترسی یک کاربر رو لغو می‌کنه (مثلاً اگر تخلف کرد)."""
    users = _load_json(USERS_FILE)
    user_id_str = str(user_id)
    if user_id_str in users:
        del users[user_id_str]
        _save_json(USERS_FILE, users)
        return True
    return False
