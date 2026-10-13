"""
Сервис расписания матчей и коэффициентов из The Odds API.
Документация: https://the-odds-api.com/liveapi/guides/v4/

⚠️ Бесплатный тариф: 500 кредитов/мес (1 кредит = 1 API запрос)
Поэтому используем агрессивный кэш.
"""
import httpx
import logging
import time
from datetime import datetime, timedelta, timezone  
from typing import Dict, List, Optional

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception, RetryCallState

from config import ODDS_API_KEY, FIXTURES_CACHE_TTL, ODDS_LEAGUES_MAP

logger = logging.getLogger(__name__)

# Кэш в памяти: {league_key: {"data": [...], "ts": timestamp}}
_cache: Dict[str, dict] = {}

# Счётчик API вызовов (для мониторинга)
_api_calls_count = 0


# Кэш в памяти: {league_key: {"data": [...], "ts": timestamp}}
_cache: Dict[str, dict] = {}

# Счётчик API вызовов (для мониторинга)
_api_calls_count = 0

def _should_retry_httpx_error(retry_state: RetryCallState) -> bool:
    """
    Определяет, стоит ли повторять запрос при ошибке httpx.
    Мы повторяем ТОЛЬКО при таймаутах или ошибках сервера (5xx).
    Ошибки 4xx (401, 404, 429) НЕ повторяем, чтобы не тратить попытки впустую.
    """
    exc = retry_state.outcome.exception()
    
    # 1. Повторяем при таймауте
    if isinstance(exc, httpx.TimeoutException):
        return True
        
    # 2. Повторяем при ошибках сервера (500, 502, 503, 504)
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
        
    # Во всех остальных случаях (включая 4xx) не повторяем
    return False

@retry(
    stop=stop_after_attempt(3),  # Максимум 3 попытки
    wait=wait_exponential(multiplier=1, min=2, max=10),  # Задержка: 2с → 4с → 8с (макс 10с)
    retry=retry_if_exception(_should_retry_httpx_error),  # Умный фильтр ошибок
    reraise=True,  # После 3 неудач пробрасываем ошибку дальше
    before_sleep=lambda retry_state: logger.warning(
        f"⚠️ Сбой The Odds API (попытка {retry_state.attempt_number}/3). "
        f"Повтор через {retry_state.next_action.sleep:.1f}с... "
        f"Причина: {retry_state.outcome.exception()}"
    )
)
def get_fixtures(league_key: str, force_refresh: bool = False) -> List[dict]:
    """
    Получить расписание будущих матчей с коэффициентами для лиги.
    Использует кэш, чтобы не тратить кредиты API.
    """
    global _api_calls_count

    # 1. Проверяем кэш
    if not force_refresh and league_key in _cache:
        cached = _cache[league_key]
        if time.time() - cached["ts"] < FIXTURES_CACHE_TTL:
            logger.info(f"📦 Кэш: {league_key} → {len(cached['data'])} матчей")
            return cached["data"]

    # 2. Проверяем маппинг
    sport_key = ODDS_LEAGUES_MAP.get(league_key)
    if not sport_key:
        logger.warning(f"⚠️ Нет маппинга для лиги '{league_key}'")
        return []

    # 3. Проверяем ключ
    if not ODDS_API_KEY:
        logger.warning("⚠️ ODDS_API_KEY не задан в .env")
        return []

    # 4. Делаем запрос к API
    try:
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "eu",
            "markets": "h2h,totals",
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        }

        response = httpx.get(url, params=params, timeout=15)
        _api_calls_count += 1

        # Логируем остаток кредитов
        remaining = response.headers.get("x-requests-remaining", "?")
        logger.info(f"📡 API запрос #{_api_calls_count} | Осталось кредитов: {remaining}")

        # 🔥 ОБРАБОТКА ОШИБОК 4xx (ИХ НЕ НАДО РЕТРАИТЬ)
        if response.status_code == 401:
            logger.error("❌ Неверный API ключ. Проверь ODDS_API_KEY в .env")
            return []
        elif response.status_code == 429:
            logger.error("❌ Лимит запросов исчерпан. Подожди до следующего месяца.")
            return []
        elif response.status_code == 404:
            logger.warning(f"⚠️ Спорт '{sport_key}' не найден в The Odds API")
            return []
            
        # 🔥 КРИТИЧЕСКИЙ МОМЕНТ: Если код 5xx (500, 502, 503, 504), 
        # мы заставляем httpx выбросить исключение. 
        # Декоратор @retry перехватит его и сделает повторную попытку!
        response.raise_for_status()

        events = response.json()

        # 5. Обрабатываем каждый матч с ФИЛЬТРАЦИЕЙ ПО ДАТЕ
        fixtures = []
        now_utc = datetime.now(timezone.utc)
        max_date_utc = now_utc + timedelta(days=4)

        for event in events:
            try:
                commence_time_str = event.get("commence_time", "")
                if not commence_time_str:
                    continue
                
                commence_time = datetime.fromisoformat(commence_time_str.replace('Z', '+00:00'))
                
                if now_utc <= commence_time <= max_date_utc:
                    fixture = _process_event(event, league_key)
                    if fixture:
                        fixtures.append(fixture)
            except ValueError as e:
                logger.warning(f"⚠️ Ошибка парсинга даты матча: {e}")
                continue

        # 6. Сохраняем в кэш
        _cache[league_key] = {
            "data": fixtures,
            "ts": time.time(),
        }
        logger.info(f"✅ Загружено {len(fixtures)} матчей для {league_key}")
        return fixtures

    except httpx.TimeoutException:
        # Это исключение будет перехвачено tenacity для повтора. 
        # Если мы здесь, значит 3 попытки исчерпаны.
        logger.error(f"❌ Таймаут при загрузке расписания для {league_key} после 3 попыток")
        return []
    except httpx.HTTPStatusError as e:
        # Это исключение будет перехвачено tenacity для повтора (если 5xx).
        # Если мы здесь, значит 3 попытки исчерпаны.
        logger.error(f"❌ Ошибка сервера The Odds API для {league_key} после 3 попыток: {e}")
        return []
    except Exception as e:
        logger.error(f"❌ Критическая ошибка загрузки расписания для {league_key}: {e}")
        return []

def _process_event(event: dict, league_key: str) -> Optional[dict]:
    """Обрабатывает один матч из ответа API"""
    home_team = event.get("home_team", "")
    away_team = event.get("away_team", "")

    if not home_team or not away_team:
        return None

    # Извлекаем лучшие коэффициенты из всех букмекеров
    odds = _extract_best_odds(event.get("bookmakers", []), home_team, away_team)

    return {
        "id": event.get("id"),
        "home_team": home_team,
        "away_team": away_team,
        "commence_time": event.get("commence_time", ""),
        "league_key": league_key,
        "odds": odds,
    }


def _extract_best_odds(bookmakers: list, home_team: str, away_team: str) -> dict:
    """
    Извлекает ЛУЧШИЕ коэффициенты по каждому исходу из всех букмекеров.
    
    Почему лучшие? Потому что для value-беттинга важен максимальный кэф —
    чем выше кэф при той же вероятности, тем выше выгода.
    """
    best = {
        "home_win": None,
        "draw": None,
        "away_win": None,
        "over_2_5": None,
        "under_2_5": None,
    }

    for bookmaker in bookmakers:
        for market in bookmaker.get("markets", []):

            # Исход матча (П1 / X / П2)
            if market.get("key") == "h2h":
                for outcome in market.get("outcomes", []):
                    name = outcome.get("name", "")
                    price = outcome.get("price", 0)

                    if name == home_team:
                        if best["home_win"] is None or price > best["home_win"]:
                            best["home_win"] = price
                    elif name == away_team:
                        if best["away_win"] is None or price > best["away_win"]:
                            best["away_win"] = price
                    elif name == "Draw":
                        if best["draw"] is None or price > best["draw"]:
                            best["draw"] = price

            # Тоталы (больше/меньше 2.5)
            elif market.get("key") == "totals":
                for outcome in market.get("outcomes", []):
                    if outcome.get("point") == 2.5:
                        if outcome.get("name") == "Over":
                            if best["over_2_5"] is None or outcome["price"] > best["over_2_5"]:
                                best["over_2_5"] = outcome["price"]
                        elif outcome.get("name") == "Under":
                            if best["under_2_5"] is None or outcome["price"] > best["under_2_5"]:
                                best["under_2_5"] = outcome["price"]

    return best


def calc_value(model_prob: float, odds: float, min_prob: float = 0.40) -> float:
    """
    Считает Value (ценность ставки) с фильтром минимальной уверенности.
    
    Args:
        model_prob: вероятность модели (0.0 - 1.0)
        odds: коэффициент букмекера
        min_prob: минимальная уверенность модели для учёта (по умолчанию 40%)
    
    Логика:
        - Если уверенность модели < min_prob → value = 0 (ложные сигналы на андердогов)
        - Если value > 0 → ставка выгодна
    """
    # 🔥 ФИЛЬТР: отсекаем ложные сигналы с низкой уверенностью
    if model_prob < min_prob:
        return 0.0
    
    if odds is None or odds <= 1.0 or model_prob <= 0:
        return 0.0
    
    value = (model_prob * odds) - 1.0
    
    # Ограничиваем адекватными пределами (Value не может быть > 100%)
    # Если value > 1.0 — это либо ошибка в кэфе, либо аномалия
    value = min(value, 1.0)
    
    return round(value, 4)

def calc_fair_odds(probability: float) -> float:
    """
    Считает "справедливый коэффициент" на основе вероятности модели.
    
    Формула: fair_odds = 1 / probability
    
    Пример:
        Модель: ТБ 9.5 угловые = 65% (0.65)
        fair_odds = 1 / 0.65 = 1.54
        
    Это значит:
        - Если букмекер даёт кэф > 1.54 → ставка ВЫГОДНА
        - Если букмекер даёт кэф < 1.54 → ставка НЕВЫГОДНА
        
    Пользователь сам сравнивает с кэфом в своём букмекерском приложении.
    """
    if probability <= 0 or probability >= 1:
        return 0.0
    return round(1.0 / probability, 2)

def get_available_sports() -> List[dict]:
    """
    Возвращает список доступных видов спорта из The Odds API.
    Тратит 1 кредит. Используй только для проверки доступных лиг.
    """
    if not ODDS_API_KEY:
        return []

    try:
        response = httpx.get(
            "https://api.the-odds-api.com/v4/sports",
            params={"apiKey": ODDS_API_KEY},
            timeout=10,
        )
        if response.status_code == 200:
            sports = response.json()
            return [s for s in sports if s.get("key", "").startswith("soccer_")]
        return []
    except Exception as e:
        logger.error(f"Ошибка получения списка спорта: {e}")
        return []