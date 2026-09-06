"""
ФУТБОЛЬНЫЙ ПРОГНОЗИСТ PRO — БОТ-ЛАУНЧЕР TELEGRAM
✅ Минималистичный и стабильный бот-шлюз в Web App
✅ Весь функционал (прогнозы, статистика, подписки) находится внутри приложения
✅ Мгновенный запуск без риска ошибок импорта
"""
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters.command import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

# Импортируем только то, что точно есть в config.py
from config import BOT_TOKEN, ADMIN_ID

# ==================== НАСТРОЙКА ЛОГИРОВАНИЯ ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# URL твоего Web App (берём из переменных окружения или используем дефолтный)
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://bot1-m0bm.onrender.com")


def get_main_menu() -> ReplyKeyboardMarkup:
    """Главное меню с кнопкой открытия Web App"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(
                text="🚀 Открыть приложение",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )],
            [KeyboardButton(text="❓ Помощь")]
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие..."
    )


# ==================== ОБРАБОТЧИКИ КОМАНД ====================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    logger.info(f"✅ Команда /start от пользователя {message.from_user.id}")
    await message.answer(
        "⚽ <b>Добро пожаловать в Тактику Ставок!</b>\n\n"
        "📱 <b>Весь функционал доступен в нашем приложении:</b>\n"
        "🔥 Горячие прогнозы с высокой уверенностью\n"
        "📊 Расширенная статистика по 20+ лигам\n"
        "🎯 Прогнозы на угловые, карточки, удары и фолы\n"
        "💎 Удобное управление подпиской\n\n"
        "Нажмите кнопку ниже, чтобы начать 👇",
        reply_markup=get_main_menu(),
        parse_mode="HTML"
    )


@dp.message(Command("help"))
@dp.message(F.text == "❓ Помощь")
async def cmd_help(message: types.Message):
    """Обработчик команды /help и кнопки помощи"""
    logger.info(f"✅ Команда /help от пользователя {message.from_user.id}")
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


@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Обработчик команды /stats — открывает статистику прямо в Web App"""
    logger.info(f"✅ Команда /stats от пользователя {message.from_user.id}")
    stats_url = f"{WEBAPP_URL}/stats"
    
    await message.answer(
        "📊 <b>Статистика</b>\n\n"
        "Откройте приложение для просмотра расширенной аналитики:\n"
        "• Топ-3 команды по угловым, карточкам, ударам\n"
        "• Детальная статистика любой команды\n"
        "• Форма, голы, xG и многое другое\n\n"
        "Нажмите кнопку ниже 👇",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(
                    text="📊 Открыть статистику",
                    web_app=WebAppInfo(url=stats_url)
                )]
            ],
            resize_keyboard=True
        ),
        parse_mode="HTML"
    )

@dp.message(Command("bot_stats"))
async def cmd_bot_stats(message: types.Message):
    """Статистика бота — только для админа. Считает напрямую через SQL."""
    if message.from_user.id != ADMIN_ID:
        logger.warning(f"⛔ Попытка доступа к /bot_stats от не-админа: {message.from_user.id}")
        await message.answer("⛔ Доступ запрещён. Эта команда только для администратора.")
        return
    
    logger.info(f"✅ Команда /bot_stats от админа {message.from_user.id}")
    
    # Считаем статистику напрямую через SQL — без импорта функций из database.py
    try:
        from database import _get_connection
        
        with _get_connection() as conn:
            # 1. Всего пользователей
            users_row = conn.execute("SELECT COUNT(*) FROM subscribers").fetchone()
            total_users = users_row[0] if users_row else 0
            
            # 2. Активных подписок (is_active=1 И subscription_end > сейчас)
            active_row = conn.execute(
                "SELECT COUNT(*) FROM subscribers WHERE is_active = 1 AND subscription_end > datetime('now')"
            ).fetchone()
            active_subs = active_row[0] if active_row else 0
            
            # 3. Trial-пользователей
            trial_row = conn.execute(
                "SELECT COUNT(*) FROM subscribers WHERE subscription_type = 'trial' AND is_active = 1"
            ).fetchone()
            trials = trial_row[0] if trial_row else 0
            
            # 4. Платных подписчиков (не trial, не free)
            paid_row = conn.execute(
                "SELECT COUNT(*) FROM subscribers WHERE subscription_type NOT IN ('free', 'trial') AND is_active = 1"
            ).fetchone()
            paid_subs = paid_row[0] if paid_row else 0
            
            # 5. Всего платежей
            payments_row = conn.execute("SELECT COUNT(*) FROM payments").fetchone()
            total_payments = payments_row[0] if payments_row else 0
            
            # 6. Сумма оплат (если есть колонка amount)
            try:
                revenue_row = conn.execute(
                    "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'succeeded'"
                ).fetchone()
                total_revenue = revenue_row[0] if revenue_row else 0
            except Exception:
                total_revenue = 0
    
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        await message.answer(f"⚠️ Не удалось получить статистику. Ошибка: {e}")
        return
    
    # Форматируем и отправляем
    await message.answer(
        "📊 <b>Статистика бота «Тактика Ставок»</b>\n\n"
        f"👥 <b>Всего пользователей:</b> {total_users:,}\n"
        f"💎 <b>Активных подписок:</b> {active_subs:,}\n"
        f" <b>На trial:</b> {trials:,}\n"
        f"💰 <b>Платных VIP:</b> {paid_subs:,}\n"
        f"💳 <b>Всего платежей:</b> {total_payments:,}\n"
        f" <b>Выручка:</b> {total_revenue:,.0f} ₽\n\n"
        f"🤖 <b>Бот:</b> @Tactika_Stavok_bot\n"
        f" <b>Web App:</b> {WEBAPP_URL}\n"
        f" <b>Админ:</b> {message.from_user.id}",
        parse_mode="HTML"
    )
    
# 🪤 ЛОВУШКА: логирует любые другие сообщения, чтобы мы видели, что бот жив
@dp.message()
async def catch_all_messages(message: types.Message):
    logger.info(f"⚠️ Получено текстовое сообщение: '{message.text}' от {message.from_user.id}")


# ==================== ЗАПУСК ====================
async def main():
    print("\n" + "="*60)
    print("🤖 БОТ-ЛАУНЧЕР УСПЕШНО ЗАПУЩЕН")
    print(f"🔗 Web App URL: {WEBAPP_URL}")
    print(f"👑 Admin ID: {ADMIN_ID}")
    print("="*60 + "\n")
    
    # Запускаем поллинг (прослушивание сообщений)
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    # Отлавливаем Ctrl+C для корректного завершения
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем.")