import hashlib
import hmac
import urllib.parse
from datetime import datetime
from fastapi import HTTPException, Header
import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# 🔥 РЕЖИМ РАЗРАБОТКИ: отключаем проверку initData
DEV_MODE = os.getenv("DEV_MODE", "true").lower() == "true"


def verify_telegram_init_data(init_data: str) -> dict:
    """Проверяет подпись initData от Telegram"""
    
    # 🔥 В режиме разработки — возвращаем тестового пользователя
    if DEV_MODE:
        return {
            "id": 123456789,
            "first_name": "Test",
            "last_name": "User",
            "username": "test_user",
            "language_code": "ru"
        }
    
    if not init_data:
        raise HTTPException(status_code=401, detail="No initData")

    parsed = urllib.parse.parse_qs(init_data)
    received_hash = parsed.get('hash', [None])[0]
    if not received_hash:
        raise HTTPException(status_code=401, detail="No hash")

    # Собираем data-check-string
    items = []
    for key, values in parsed.items():
        if key == 'hash':
            continue
        items.append(f"{key}={values[0]}")
    items.sort()
    data_check_string = "\n".join(items)

    # HMAC-SHA256
    secret_key = hmac.new(
        b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256
    ).digest()
    calculated_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Проверяем срок (не старше 24 часов)
    auth_date = int(parsed.get('auth_date', [0])[0])
    if datetime.now().timestamp() - auth_date > 86400:
        raise HTTPException(status_code=401, detail="InitData expired")

    # Парсим пользователя
    import json
    user_json = parsed.get('user', [None])[0]
    if not user_json:
        raise HTTPException(status_code=401, detail="No user")

    return json.loads(user_json)