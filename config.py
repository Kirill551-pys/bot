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


# ==================== АДМИНИСТРАТОРЫ ====================
# Загружаем список ID из .env через запятую
_admin_ids_str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = set(map(int, _admin_ids_str.split(","))) if _admin_ids_str else set()

# ==================== ОБЯЗАТЕЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))      

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

# Тиры рынков по ACC при уверенности
MARKET_TIERS = {
    'S': ['shots_over_22_5', 'sot_over_8_5', 'yellows_over_3_5',
          'total_goals', 'corners_over_9_5', 'both_scored', 'result'],
    'B': ['fouls_over_23_5', 'yellows_over_4_5', 'individual_totals'],
    'C': ['first_half_result', 'btts_first_half', 'corners_over_10_5'],  # не показывать как ставку
}
CONF_THRESHOLD = 0.55  # показываем ставку только при уверенности >= 55%

# ==================== ТИРЫ ЛИГ ПО УВЕРЕННОСТИ ====================
# S — прогнозы заходят чаще, C — не рекомендуем как ставку
LEAGUE_TIERS = {
    'greece': 'S', 'scotland': 'S', 'portugueseLiga': 'S', 'laLiga': 'S',
    'china': 'S', 'finland': 'S', 'dania': 'S', 'epl': 'S',
    'seriaA': 'S', 'poland': 'S', 'eredivisise': 'S', 'rpl': 'S',
    'norway': 'B', 'brazil': 'B', 'turkey': 'B', 'belgium': 'B',
    'bundesliga': 'B', 'mexico': 'B', 'romania': 'B',
    'argentina': 'C', 'usa': 'C', 'japan': 'C', 'austria': 'C', 'ligue1': 'C',
}

# Минимальная уверенность для hot-прогнозов в зависимости от тира лиги
HOT_MIN_CONFIDENCE = {
    'S': 60,
    'B': 65,
    'C': 70,
}

# ==================== THE ODDS API ====================
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")

# Кэш расписания в секундах (по умолчанию 6 часов)
# Увеличь до 43200 (12 часов) если хочешь экономить кредиты
FIXTURES_CACHE_TTL = int(os.getenv("FIXTURES_CACHE_TTL", str(6 * 3600)))

# Маппинг наших лиг на sport_key из The Odds API
ODDS_LEAGUES_MAP = {
    "epl":              "soccer_epl",
    "laLiga":           "soccer_spain_la_liga",
    "bundesliga":       "soccer_germany_bundesliga",
    "seriaA":           "soccer_italy_serie_a",
    "ligue1":           "soccer_france_ligue_one",
    "champions_league": "soccer_uefa_champs_league",
    "eredivisise":      "soccer_netherlands_eredivisie",
    "portugueseLiga":   "soccer_portugal_primeira_liga",
    "turkey":           "soccer_turkey_super_league",
    "rpl":              "soccer_russia_premier_league",
    # "scotland":         "soccer_scotland_premiership",
    "greece":           "soccer_greece_super_league",
    "poland":           "soccer_poland_ekstraklasa",
    "argentina":        "soccer_argentina_primera_division",
    # "brazil":           "soccer_brazil_serie_a",
    "usa":              "soccer_usa_mls",
    # "mexico":           "soccer_mexico_liga_mx",
    "japan":            "soccer_japan_j_league",
    "china":            "soccer_china_superleague",
    "norway":           "soccer_norway_eliteserien",
    "finland":          "soccer_finland_veikkausliiga",
    "dania":            "soccer_denmark_superliga",
    "austria":          "soccer_austria_bundesliga",
    # "romania":          "soccer_romania_liga_1",
}

# Лиги, для которых запрашиваем коэффициенты (для экономии кредитов)
# Чем меньше лиг — тем меньше кредитов тратится
ODDS_ACTIVE_LEAGUES = [
    "epl", "laLiga", "bundesliga", "seriaA", "ligue1", "rpl", "usa", "japan", "turkey", "champions_league", "china", "eredivisise", "austria"
]