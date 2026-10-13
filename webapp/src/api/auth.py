import hashlib
import hmac
import urllib.parse
import json
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, Header, status, Depends
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# Настройка логгера для безопасности
logger = logging.getLogger("security")

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN не найден в переменных окружения!")

# 🔥 DEV_MODE: Включаем ТОЛЬКО локально. 
# В продакшене эта переменная должна быть строго удалена или равна false.
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"
if DEV_MODE:
    logger.warning("⚠️ ВНИМАНИЕ: Сервер запущен в DEV_MODE! Безопасность Telegram отключена.")


class TelegramUser(BaseModel):
    """Строгая модель пользователя Telegram"""
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    language_code: Optional[str] = "ru"
    is_premium: Optional[bool] = False


def _verify_init_data_strict(init_data: str) -> TelegramUser:
    """
    Внутренняя функция строгой криптографической проверки initData.
    """
    parsed = urllib.parse.parse_qs(init_data)
    received_hash = parsed.get('hash', [None])[0]
    
    if not received_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Hash отсутствует")
    
    # 1. Собираем data-check-string (исключаем hash, сортируем по алфавиту)
    items = []
    for key, values in parsed.items():
        if key == 'hash':
            continue
        items.append(f"{key}={values[0]}")
    items.sort()
    data_check_string = "\n".join(items)
    
    # 2. Вычисляем HMAC-SHA256
    secret_key = hmac.new(
        b"WebAppData", BOT_TOKEN.encode('utf-8'), hashlib.sha256
    ).digest()
    
    calculated_hash = hmac.new(
        secret_key, data_check_string.encode('utf-8'), hashlib.sha256
    ).hexdigest()
    
    # 3. Безопасное сравнение (защита от timing attacks)
    if not hmac.compare_digest(calculated_hash, received_hash):
        # 🔥 ЛОГИРУЕМ ПОПЫТКУ ВЗЛОМА
        logger.error(f"⛔ ПОДЕЛКА INIT DATA! Неверная подпись. Данные: {init_data[:100]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Неверная криптографическая подпись"
        )
    
    # 4. Проверка актуальности (не старше 24 часов)
    auth_date = int(parsed.get('auth_date', [0])[0])
    if datetime.now().timestamp() - auth_date > 86400:
        logger.warning(f"⏳ Истекший initData. auth_date: {auth_date}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Сессия Telegram устарела, обновите страницу"
        )
    
    # 5. Парсим и валидируем пользователя через Pydantic
    user_json = parsed.get('user', [None])[0]
    if not user_json:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Данные пользователя отсутствуют")
    
    try:
        user_data = json.loads(user_json)
        return TelegramUser(**user_data)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"❌ Ошибка парсинга user JSON: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный формат данных пользователя")


async def get_current_user(
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data")
) -> TelegramUser:
    """
    FastAPI Dependency. Автоматически извлекает initData из заголовка и возвращает пользователя.
    Использование в роутерах: user: TelegramUser = Depends(get_current_user)
    """
    # 🔥 Обход для локальной разработки
    if DEV_MODE:
        logger.info("🛠 DEV_MODE: Возвращаем тестового пользователя")
        return TelegramUser(
            id=123456789,
            first_name="Test",
            last_name="User",
            username="test_user",
            language_code="ru"
        )

    # Если заголовок не передан
    if not x_telegram_init_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Заголовок X-Telegram-Init-Data отсутствует"
        )

    # Запускаем строгую проверку
    return _verify_init_data_strict(x_telegram_init_data)