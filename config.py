"""
Конфигурация проекта Футбольный Прогнозист Pro
Все секреты загружаются из переменных окружения (.env)
"""
from dotenv import load_dotenv
import os
import logging

logger = logging.getLogger(__name__)

# Загрузка переменных из .env
load_dotenv()

# ==================== ОБЯЗАТЕЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")

if not BOT_TOKEN:
    raise RuntimeError("❌ Не задан BOT_TOKEN в переменных окружения!")
if not CHANNEL_USERNAME:
    raise RuntimeError("❌ Не задан CHANNEL_USERNAME!")

# ==================== ОПЦИОНАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
# Redis для хранения состояний FSM (если не задан — будет использоваться localhost)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ЮKassa (обязательны для приёма платежей)
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
    raise RuntimeError("❌ YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY обязательны")

# ==================== СЛОВАРЬ ЛИГ ====================
LEAGUES = {
    # === Топ-лиги ===
    "rpl": "🇷🇺 РПЛ",
    "epl": "🇬🇧 Англия: Премьер-лига",
    "bundesliga": "🇩🇪 Бундеслига",
    "seriaA": "🇮🇹 Серия A",
    "laLiga": "🇪🇸 Ла Лига",
    "ligue1": "🇫🇷 Лига 1",
    "champions_league": "Лига чемпионов 🏆",
    "eredivisise": "🇳🇱 Эредивизи",
    "portugueseLiga": "🇵🇹 Португальская Лига",
    
    # === Дополнительные лиги ===
    "argentina": "🇦🇷 Аргентина: Примера Дивисьон",     
    "austria": "🇦🇹 Австрия: Бундеслига",                
    "brazil": "🇧🇷 Бразилия: Серия А",                   
    "china": "🇨🇳 Китай: Суперлига",
    "dania": "🇩🇰 Дания: Суперлига",
    "finland": "🇫🇮 Финляндия: Вейккауслига",
    "greece": "🇬🇷 Греция: Суперлига",                  
    "japan": "🇯🇵 Япония: Джей-лига",
    "mexico": "🇲🇽 Мексика: Лига МХ",
    "norway": "🇳🇴 Норвегия: Элитсерия",
    "poland": "🇵🇱 Польша: Экстракласа",
    "romania": "🇷🇴 Румыния: Лига I",
    "scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿 Шотландия: Премьершип",       
    "turkey": "🇹🇷 Турция: Суперлига",                    
    "usa": "🇺🇸 США: МЛС"
}

# ==================== ДАТЫ СЕЗОНОВ 2025-2026 ====================
# Формат: "ключ_лиги": "ГГГГ-ММ-ДД"
SEASON_2025_START = {
    "rpl": "2026-07-24",
    "epl": "2026-08-22",
    "bundesliga": "2026-08-28",
    "seriaA": "2026-08-22",
    "laLiga": "2026-08-16",
    "ligue1": "2026-08-21",
    "champions_league": "2026-09-17",
    "eredivisise": "2026-08-07",
    "portugueseLiga": "2026-08-08",
    "argentina": "2026-07-24",
    "austria": "2026-10-16",
    "belgium": "2026-08-07",
    "brazil": "2026-01-28",
    "china": "2026-02-28",
    "dania": "2026-07-24",
    "finland": "2026-04-04",
    "greece": "2026-08-22",
    "japan": "2026-08-07",
    "mexico": "2026-07-16",
    "norway": "2026-03-14",
    "poland": "2026-07-24",
    "romania": "2026-07-17",
    "scotland": "2026-07-31",
    "turkey": "2026-08-14",
    "usa": "2026-02-21", 
}

def get_season_start(league_key: str, default: str = "2025-08-01") -> str:
    """Возвращает дату начала сезона для лиги"""
    return SEASON_2025_START.get(league_key, default)

# ==================== ТАРИФЫ ПОДПИСКИ ====================
SUBSCRIPTION_PRICES = {
    'trial': {'days': 3, 'price': 0, 'name': 'Пробный'},
    'weekly': {'days': 7, 'price': 149, 'name': 'Неделя'},
    'monthly': {'days': 30, 'price': 399, 'name': 'Месяц'},
    'quarter': {'days': 90, 'price': 999, 'name': 'Квартал'},
    'lifetime': {'days': 3650, 'price': 3990, 'name': 'Навсегда'}
}

# ==================== РЕФЕРАЛЬНАЯ ПРОГРАММА ====================
REFERRAL_BONUS_PERCENT = 15  # 15% от первой оплаты реферала
REFERRAL_FREE_DAYS = 1       # 1 день бесплатно за каждого реферала

