"""
ФУТБОЛЬНЫЙ ПРОГНОЗИСТ PRO — БОТ-ЛАУНЧЕР TELEGRAM
✅ Минималистичный бот, который служит шлюзом в Web App
✅ Весь функционал (прогнозы, статистика, подписки) находится в Web App
✅ Мгновенный запуск без загрузки тяжелых ML-моделей
"""
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters.command import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from database import (
    init_db,
    get_all_users_count,
    get_active_subscriptions_count,
    get_trials_count,
    get_payments_count
)

from config import BOT_TOKEN, ADMIN_ID, CHANNEL_USERNAME


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# URL твоего Web App (используем переменную окружения или дефолтный с Render)
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://bot1-m0bm.onrender.com")

def get_main_menu():
    """Главное меню только с кнопкой Web App"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(
                text="🚀 Открыть приложение",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )],
            [KeyboardButton(text="❓ Помощь /help")]
        ],
        resize_keyboard=True
    )

# ==================== ОБРАБОТЧИКИ ====================

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Статистика бота (только для администратора)"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещён")
        return
    
    users = get_all_users_count()
    active_subs = get_active_subscriptions_count()
    trials = get_trials_count()
    payments = get_payments_count()
    
    await message.answer(
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: <b>{users}</b>\n"
        f"💎 Активных подписок: <b>{active_subs}</b>\n"
        f"🎁 Использовано trial: <b>{trials}</b>\n"
        f"💰 Платежей: <b>{payments}</b>",
        parse_mode="HTML"
    )

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "⚽ <b>Добро пожаловать в Футбольный Прогнозист Pro!</b>\n\n"
        "📱 <b>Весь функционал доступен в нашем приложении:</b>\n"
        "🔥 Горячие прогнозы с высокой уверенностью\n"
        "📊 Расширенная статистика по 20+ лигам\n"
        "🎯 Прогнозы на угловые, карточки, удары и фолы\n"
        "💎 Удобное управление подпиской\n\n"
        "Нажмите кнопку ниже, чтобы начать 👇",
        reply_markup=get_main_menu(),
        parse_mode="HTML"
        # Отключаем удаление клавиатуры, чтобы кнопка всегда была под рукой
    )


@dp.message(Command("channel_stats"))
async def cmd_channel_stats(message: types.Message):
    """Количество подписчиков канала"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещён")
        return
    
    try:
        member_count = await bot.get_chat_member_count(CHANNEL_USERNAME)
        await message.answer(
            f"📢 Подписчиков в канале <b>{CHANNEL_USERNAME}</b>: <b>{member_count}</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("help"))
@dp.message(F.text == "❓ Помощь /help")
async def cmd_help(message: types.Message):
    await message.answer(
        "📚 <b>Как пользоваться:</b>\n\n"
        "1️⃣ Нажмите кнопку <b>🚀 Открыть приложение</b>\n"
        "2️⃣ Выберите интересующую лигу и матч\n"
        "3️⃣ Получите детальный прогноз с вероятностями\n\n"
        "💡 <i>Все данные обновляются в реальном времени. Для доступа ко всем функциям оформите подписку внутри приложения.</i>\n\n"
        "⚠️ <i>Прогнозы носят информационный характер. Ставьте ответственно!</i>",
        parse_mode="HTML"
    )

# ==================== ЗАПУСК ====================
async def main():
    init_db()  # ← ДОБАВЬ ЭТУ СТРОКУ
    print("\n" + "="*50)
    print("🤖 БОТ-ЛАУНЧЕР ЗАПУЩЕН")
    print(f"🔗 Web App URL: {WEBAPP_URL}")
    print(f"👑 Admin ID: {ADMIN_ID}")  # ← для проверки
    print("="*50 + "\n")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())