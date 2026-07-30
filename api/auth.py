import hashlib
import hmac
import urllib.parse
from datetime import datetime
from fastapi import HTTPException
import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# 🔥 ВАЖНО: Если DEV_MODE=true, мы пропускаем строгую проверку
DEV_MODE = os.getenv("DEV_MODE", "true").lower() == "true"


def verify_telegram_init_data(init_data: str = None) -> dict:
    """Проверяет подпись initData от Telegram или возвращает тестового пользователя"""
    
    # 🔥 ГЛАВНОЕ ИСПРАВЛЕНИЕ: если включен DEV_MODE или initData пустая/None
    if DEV_MODE or not init_data or str(init_data).strip() == "":
        return {
            "id": 123456789,
            "first_name": "Test",
            "last_name": "User",
            "username": "test_user",
            "language_code": "ru"
        }

    # Если мы здесь, значит DEV_MODE=false и мы ждем реальные данные от Telegram
    parsed = urllib.parse.parse_qs(init_data)
    received_hash = parsed.get('hash', [None])[0]
    
    if not received_hash:
        raise HTTPException(status_code=401, detail="No hash")

    items = []
    for key, values in parsed.items():
        if key == 'hash':
            continue
        items.append(f"{key}={values[0]}")
    items.sort()
    data_check_string = "\n".join(items)

    secret_key = hmac.new(
        b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256
    ).digest()
    calculated_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(status_code=401, detail="Invalid signature")

    auth_date = int(parsed.get('auth_date', [0])[0])
    if datetime.now().timestamp() - auth_date > 86400:
        raise HTTPException(status_code=401, detail="InitData expired")

    import json
    user_json = parsed.get('user', [None])[0]
    if not user_json:
        raise HTTPException(status_code=401, detail="No user")

    return json.loads(user_json)