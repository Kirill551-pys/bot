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
from config import BOT_TOKEN, ADMIN_ID

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
            [KeyboardButton(text="❓ Помощь")]
        ],
        resize_keyboard=True
    )


# ==================== ОБРАБОТЧИКИ ====================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "⚽ <b>Добро пожаловать в Тактику Ставок!</b>\n\n"
        "📱 <b>Весь функционал доступен в приложении:</b>\n"
        "🔥 Горячие прогнозы с высокой уверенностью\n"
        "📊 Расширенная статистика по 20+ лигам\n"
        "🎯 Прогнозы на угловые, карточки, удары и фолы\n"
        "💎 Удобное управление подпиской\n\n"
        "Нажмите кнопку ниже, чтобы начать 👇",
        reply_markup=get_main_menu(),
        parse_mode="HTML"
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Обработчик команды /help"""
    await message.answer(
        "📚 <b>Как пользоваться:</b>\n\n"
        "1️⃣ Нажмите кнопку <b>🚀 Открыть приложение</b>\n"
        "2️⃣ Выберите интересующую лигу и матч\n"
        "3️⃣ Получите детальный прогноз с вероятностями\n\n"
        "💡 <i>Все данные обновляются в реальном времени.</i>\n\n"
        "⚠️ <i>Прогнозы носят информационный характер. Ставьте ответственно!</i>\n\n"
        "📄 <a href='https://telegra.ph/Oferta-Taktika-Stavok-09-01'>Публичная оферта</a>\n"
        "🔐 <a href='https://telegra.ph/Politika-PDn-Taktika-Stavok-09-01'>Политика ПДн</a>\n"
        "💬 <a href='https://t.me/Tactika_Stavok_bot'>Поддержка</a>",
        parse_mode="HTML",
        disable_web_page_preview=True
    )


@dp.message(F.text == "❓ Помощь")
async def help_button_handler(message: types.Message):
    """Обработчик кнопки помощи из клавиатуры"""
    await cmd_help(message)


@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Обработчик команды /stats — открывает статистику в Web App"""
    stats_url = f"{WEBAPP_URL}/stats"
    await message.answer(
        "📊 <b>Статистика</b>\n\n"
        "Откройте приложение для просмотра расширенной статистики:\n"
        "• Топ-3 команды по угловым, карточкам, ударам\n"
        "• Детальная статистика каждой команды\n"
        "• Форма, голы, xG и многое другое\n\n"
        "Нажмите кнопку ниже 👇",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(
                    text=" Открыть статистику",
                    web_app=WebAppInfo(url=stats_url)
                )]
            ],
            resize_keyboard=True
        ),
        parse_mode="HTML"
    )


@dp.message(Command("channel_stats"))
async def cmd_channel_stats(message: types.Message):
    """Обработчик команды /channel_stats — только для админа"""
    # Проверка прав администратора
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещён. Эта команда только для администратора.")
        return
    
    # Пытаемся получить количество подписчиков канала
    try:
        # Замени на username своего канала (без @)
        channel_username = "Tactika_Stavok"
        member_count = await bot.get_chat_member_count(f"@{channel_username}")
        await message.answer(
            f"📢 <b>Подписчиков в канале @{channel_username}:</b> <b>{member_count}</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(
            f"⚠️ Не удалось получить статистику канала.\n"
            f"Убедись, что бот добавлен в канал @{channel_username} как администратор.\n\n"
            f"Ошибка: {e}"
        )


# ==================== ЗАПУСК ====================

async def main():
    print("\n" + "="*50)
    print("🤖 БОТ-ЛАУНЧЕР ЗАПУЩЕН")
    print(f"🔗 Web App URL: {WEBAPP_URL}")
    print(f"👑 Admin ID: {ADMIN_ID}")
    print("="*50 + "\n")
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())