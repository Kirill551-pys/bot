from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import sys
import os
import logging
import time

# Добавляем корневую папку в путь (для импорта model.py, database.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ==================== ИМПОРТЫ ====================
from model import (
    load_matches_data, train_models, predict_match,
    load_model, save_model,
    calculate_team_statistics, get_league_rankings,
    find_similar_team,
    HOME_WIN, DRAW, AWAY_WIN, OVER_25, UNDER_25, BTTS_YES, BTTS_NO
)
from database import (
    create_user, get_user_subscription, activate_subscription,
    is_trial_available, use_trial, add_referral, get_referral_count,
    init_db, get_subscription_info 
)
from config import (
    LEAGUES, SUBSCRIPTION_PRICES, REFERRAL_FREE_DAYS,
    LEAGUE_TIERS, HOT_MIN_CONFIDENCE, ODDS_ACTIVE_LEAGUES, CONF_THRESHOLD,
    ADMIN_ID
)
from auth import verify_telegram_init_data
from team_aliases import normalize_team_name
from fixtures_service import get_fixtures, calc_value, calc_fair_odds, get_available_sports

logger = logging.getLogger(__name__)

# ==================== ЗАГРУЗКА МОДЕЛЕЙ ====================
MODELS = {}
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')

HOT_CACHE: dict = {
    'data': None,           # Здесь хранится список из 5 hot-прогнозов (или None если кэш пуст)
    'expires_at': 0.0,      # Время, когда кэш устареет (timestamp в секундах)
    'lock': False,          # Флаг блокировки: True если кто-то уже пересчитывает кэш
}
HOT_CACHE_TTL = 30 * 60     # 30 минут в секундах    # Время жизни кэша: 5 минут (300 секунд)


def get_hot_cached() -> list:
    """
    Возвращает кэшированные hot-прогнозы или пересчитывает их если кэш устарел.
    
    ЛОГИКА РАБОТЫ:
    1. Проверяем, есть ли валидный кэш (data не None И время не вышло)
    2. Если да → возвращаем сразу (мгновенно!)
    3. Если нет → проверяем, не пересчитывает ли кто-то уже (lock)
    4. Если lock=True → возвращаем старый кэш (даже если устарел), чтобы не было гонки
    5. Если lock=False → блокируем, пересчитываем, сохраняем, разблокируем
    
    ВОЗВРАЩАЕТ:
    - Список из 0-5 hot-прогнозов (dict)
    """
    now = time.time()  # Текущее время в секундах (например, 1693564800.123)
    
    # ПРОВЕРКА 1: Кэш валиден?
    # Условие: data не None (что-то есть) И сейчас < времени истечения
    if HOT_CACHE['data'] is not None and now < HOT_CACHE['expires_at']:
        # Кэш свежий → отдаём сразу
        return HOT_CACHE['data']
    
    # ПРОВЕРКА 2: Кто-то уже пересчитывает?
    # Это защита от "гонки": если 10 пользователей одновременно запросили hot,
    # и кэш устарел, мы не хотим чтобы все 10 начали пересчитывать одновременно.
    # Первый начинает пересчёт (lock=True), остальные 9 ждут и получают старый кэш.
    if HOT_CACHE['lock']:
        # Кто-то уже пересчитывает → возвращаем старый кэш (даже если устарел)
        # Лучше старый кэш 5-минутной давности, чем 30-секундное ожидание
        return HOT_CACHE['data'] if HOT_CACHE['data'] else []
    
    # ПРОВЕРКА 3: Нужно пересчитать
    # Блокируем кэш (lock=True), чтобы другие запросы не начали пересчёт
    HOT_CACHE['lock'] = True
    
    try:
        # Логируем начало пересчёта (для отладки)
        print(f"🔄 Пересчёт hot-прогнозов...", flush=True)
        start = time.time()  # Засекаем время начала
        
        # Вызываем тяжёлую функцию пересчёта
        hot_list = _collect_hot_predictions(limit=5)
        
        # Считаем сколько времени заняло
        elapsed = time.time() - start
        print(f"✅ Hot пересчитан за {elapsed:.1f}с, найдено {len(hot_list)}", flush=True)
        
        # СОХРАНЯЕМ В КЭШ:
        HOT_CACHE['data'] = hot_list  # Сохраняем список прогнозов
        HOT_CACHE['expires_at'] = now + HOT_CACHE_TTL  # Устанавливаем время истечения (сейчас + 5 минут)
        
    except Exception as e:
        # Если произошла ошибка — логируем, но не роняем сервер
        print(f"❌ Ошибка пересчёта hot: {e}", flush=True)
        # Возвращаем старый кэш если есть
        return HOT_CACHE['data'] if HOT_CACHE['data'] else []
        
    finally:
        # РАЗБЛОКИРУЕМ кэш в любом случае (даже если была ошибка)
        # Это важно: если не разблокировать, все последующие запросы будут ждать вечно
        HOT_CACHE['lock'] = False
    
    # Возвращаем свежий кэш
    return HOT_CACHE['data']

def load_all_models():
    print("\n" + "="*80, flush=True)
    print("🔍 НАЧАЛО ЗАГРУЗКИ МОДЕЛЕЙ", flush=True)
    print(f"📂 Путь к данным: {DATA_DIR}", flush=True)
    print(f"📂 Папка существует: {os.path.exists(DATA_DIR)}", flush=True)
    if os.path.exists(DATA_DIR):
        print(f"📂 Содержимое папки data: {os.listdir(DATA_DIR)}", flush=True)
    print(f"⚙️ Список лиг из config (LEAGUES): {LEAGUES}", flush=True)
    print("="*80 + "\n", flush=True)

    if not LEAGUES:
        print("❌ ОШИБКА: Словарь LEAGUES пуст! Проверьте файл config.py", flush=True)
        return

    for folder, display_name in LEAGUES.items():
        try:
            data_path = os.path.join(DATA_DIR, folder, 'matches.csv')
            model_path = os.path.join(DATA_DIR, folder, 'model.pkl')
            
            print(f"➡️ Обрабатываю лигу: {display_name} ({folder})", flush=True)
            print(f"   Файл CSV существует: {os.path.exists(data_path)}", flush=True)
            
            if not os.path.exists(data_path):
                print(f"   ⚠️ Пропуск: файл {data_path} не найден!", flush=True)
                continue
            
            model_data = None
            if os.path.exists(model_path):
                print(f"   📥 Пытаюсь загрузить модель...", flush=True)
                model_data = load_model(model_path)
            
            if model_data is None:
                print(f"   🔄 Модели нет или она устарела. Загружаю CSV для обучения...", flush=True)
                df = load_matches_data(data_path)
                
                if df is not None and len(df) > 50:
                    print(f"   🧠 Начинаю обучение (это может занять время)...", flush=True)
                    model_data = train_models(df)
                    if model_data is not None:
                        save_model(model_data, model_path)
                        print(f"   ✅ Модель успешно обучена и сохранена!", flush=True)
                    else:
                        print(f"   ❌ Ошибка: train_models вернула None. Проверьте колонки в CSV!", flush=True)
                        continue
                else:
                    print(f"   ❌ Ошибка: данных недостаточно ({len(df) if df is not None else 0} матчей).", flush=True)
                    continue
            
            df = load_matches_data(data_path)
            MODELS[folder] = {
                'model_data': model_data,
                'df': df,
                'ratings': model_data.get('final_ratings', {}),
                'name': display_name
            }
            print(f"   🎉 Успешно добавлено в память: {display_name}", flush=True)
            
        except Exception as e:
            print(f"   💥 КРИТИЧЕСКАЯ ОШИБКА для {folder}: {e}", flush=True)
            import traceback
            traceback.print_exc()

    print(f"\n✅ ЗАГРУЗКА ЗАВЕРШЕНА. Всего моделей в памяти: {len(MODELS)}", flush=True)
    print("="*80 + "\n", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n" + "="*80, flush=True)
    print("🚀 ЗАПУСК ФУНКЦИИ LIFESPAN (STARTUP)", flush=True)
    print(f"📁 Текущая рабочая директория: {os.getcwd()}", flush=True)
    print("="*80 + "\n", flush=True)
    
    init_db()
    print("🗄️ База данных инициализирована", flush=True)
    
    load_all_models()
    
    print("\n🎉 ВСЕ ПРОЦЕДУРЫ STARTUP ЗАВЕРШЕНЫ УСПЕШНО 🎉\n", flush=True)
    
    yield
    
    print("🛑 Завершение работы приложения...", flush=True)


app = FastAPI(title="Football Predictor API", version="2.4", lifespan=lifespan)

# ==================== MIDDLEWARE ====================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://bot1-m0bm.onrender.com",
        "https://bot-lkx5.onrender.com",
        "https://web.telegram.org",
        "https://t.me",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== БАЗОВЫЕ ENDPOINTS ====================
@app.get("/")
def root():
    return {"status": "ok", "message": "Football Predictor API is running"}


@app.get("/debug")
def debug_info():
    """Диагностика: какая версия кода на сервере"""
    endpoints = []
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            endpoints.append(f"{list(route.methods)} {route.path}")
    
    return {
        "status": "OK",
        "version": "2.4-hot-list-diversified",
        "models_count": len(MODELS),
        "leagues_loaded": list(MODELS.keys()),
        "endpoints": endpoints[:25],
        "has_hot_list_endpoint": any("/api/predictions/hot/list" in ep for ep in endpoints),
        "hot_endpoint_count": sum(1 for ep in endpoints if "/api/predictions/hot" in ep and "/list" not in ep),
        "hot_endpoint_methods": next(
            (list(r.methods) for r in app.routes
             if hasattr(r, 'path') and r.path == '/api/predictions/hot'),
            None
        )
    }


# ==================== АВТОРИЗАЦИЯ ====================
def get_current_user(x_telegram_init_data: str = Header(None, alias="X-Telegram-Init-Data")) -> dict:
    return verify_telegram_init_data(x_telegram_init_data)

# ==================== ЗАЩИТА ПОДПИСКОЙ (PAYWALL) ====================

def require_subscription(user: dict = Depends(get_current_user)) -> dict:
    """
    Dependency-функция для защиты эндпоинтов подпиской.
     Администратор (ADMIN_ID) всегда имеет полный доступ.
    """
    from database import is_subscription_active
    
    user_id = user.get('id')
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found")
    
    # 👑 АДМИН ВСЕГДА ПРОХОДИТ (даже если DEV_MODE=false)
    if user_id == ADMIN_ID:
        return user
    
    # В режиме разработки пропускаем всех остальных
    if os.getenv("DEV_MODE", "true").lower() == "true":
        return user
    
    # Проверяем подписку
    if not is_subscription_active(user_id):
        raise HTTPException(
            status_code=403,
            detail="Subscription required. Please activate trial or subscription."
        )
    
    return user

# ==================== PYDANTIC МОДЕЛИ ====================
class MatchRequest(BaseModel):
    team1: str
    team2: str
    league: str


class PredictionResponse(BaseModel):
    home_team: str
    away_team: str
    timestamp: str
    risk_level: str
    
    result: dict
    total_goals: Optional[dict] = None
    both_scored: Optional[dict] = None
    
    first_half_result: Optional[dict] = None
    total_shots: Optional[dict] = None
    total_shots_on_target: Optional[dict] = None
    total_fouls: Optional[dict] = None
    btts_first_half: Optional[dict] = None
    individual_totals: Optional[dict] = None
    
    corners: Optional[dict] = None
    cards: Optional[dict] = None
    
    recommendation: Optional[str] = None
    trust_signal: Optional[str] = None
    is_hot: bool = False
    hot_confidence: float = 0.0
    hot_bet: Optional[str] = None
    hot_bet_tier: Optional[str] = None
    
    commence_time: Optional[str] = None
    odds: Optional[dict] = None
    value: Optional[dict] = None
    best_value: Optional[float] = None
    additional_markets: Optional[List[dict]] = None
    
    class Config:
        extra = "allow"


class LeagueResponse(BaseModel):
    key: str
    name: str
    teams_count: int
    matches_count: int


class TeamStatsResponse(BaseModel):
    matches_played: int
    home_matches: int
    away_matches: int
    avg_goals_for: float
    avg_goals_against: float
    total_goals_avg: float
    over_2_5_pct: float
    over_3_5_pct: float
    under_2_5_pct: float
    btts_yes_pct: float
    btts_no_pct: float
    avg_corners_for: Optional[float] = None
    avg_corners_against: Optional[float] = None
    total_corners_avg: Optional[float] = None
    corners_over_9_5_pct: Optional[float] = None
    corners_over_10_5_pct: Optional[float] = None
    avg_yellows_for: Optional[float] = None
    avg_yellows_against: Optional[float] = None
    total_yellows_avg: Optional[float] = None
    yellows_over_3_5_pct: Optional[float] = None
    yellows_over_4_5_pct: Optional[float] = None
    form_points: int
    form_pct: float


# ==================== ENDPOINTS: ЛИГИ ====================
@app.get("/api/leagues", response_model=List[LeagueResponse])
def get_leagues(user: dict = Depends(get_current_user)):
    result = []
    for key, name in LEAGUES.items():
        if key in MODELS:
            df = MODELS[key].get('df')
            if df is not None:
                teams = set(df['home_team']) | set(df['away_team'])
                result.append(LeagueResponse(
                    key=key,
                    name=name,
                    teams_count=len(teams),
                    matches_count=len(df)
                ))
    return result


@app.get("/api/leagues/{league}/teams", response_model=List[str])
def get_teams(league: str, user: dict = Depends(get_current_user)):
    if league not in MODELS:
        raise HTTPException(status_code=404, detail="League not found")
    
    df = MODELS[league].get('df')
    if df is None:
        return []
    
    teams = sorted(set(df['home_team']) | set(df['away_team']))
    return teams


# ==================== ENDPOINTS: ПРОГНОЗ МАТЧА ====================
@app.post("/api/predictions/match", response_model=PredictionResponse)
def get_match_prediction(req: MatchRequest, user: dict = Depends(require_subscription)):
    if req.league not in MODELS:
        raise HTTPException(status_code=404, detail="League not found")
    
    model_info = MODELS[req.league]
    
    prediction = predict_match(
        team1=req.team1,
        team2=req.team2,
        model_data=model_info['model_data'],
        ratings_dict=model_info.get('ratings', {}),
        all_matches_df=model_info['df']
    )
    
    if 'error' in prediction:
        raise HTTPException(status_code=400, detail=prediction['error'])
    
    prediction['league_tier'] = LEAGUE_TIERS.get(req.league, 'C')
    return PredictionResponse(**prediction)


# ==================== HOT: ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def _extract_additional_markets(prediction: dict, odds: dict = None) -> List[dict]:
    """Извлекает доп. рынки всех типов: тоталы, ОЗ, угловые, карточки, удары, фолы."""
    odds = odds or {}
    markets = []

    def add_market(key, label, prob, tier, real_odds=None):
        if prob < CONF_THRESHOLD or tier == 'C':
            return
        item = {
            'market': key,
            'label': label,
            'probability': round(prob, 3),
            'fair_odds': calc_fair_odds(prob),
            'tier': tier,
            'hint': f"Ищите кэф выше {calc_fair_odds(prob)}",
        }
        if real_odds and real_odds > 1.0:
            item['bookmaker_odds'] = real_odds
            item['value'] = calc_value(prob, real_odds, min_prob=0.50)
        markets.append(item)

    # ⚽ ТОТАЛ 2.5 (реальные кэфы из API!)
    tg = prediction.get('total_goals') or {}
    add_market('total_over_2_5', '⚽ ТБ 2.5', tg.get('Over 2.5', 0), 'S', odds.get('over_2_5'))
    add_market('total_under_2_5', '⚽ ТМ 2.5', tg.get('Under 2.5', 0), 'S', odds.get('under_2_5'))

    # 🔄 ОБЕ ЗАБЬЮТ
    bs = prediction.get('both_scored') or {}
    add_market('btts_yes', '🔄 ОЗ — Да', bs.get('Yes', 0), 'S')
    add_market('btts_no', '🔄 ОЗ — Нет', bs.get('No', 0), 'S')

    # 🎯 УГЛОВЫЕ
    corners = prediction.get('corners') or {}
    add_market('corners_over_9_5', '🎯 Угловые ТБ 9.5', corners.get('Over 9.5', 0), 'S')

    # 🟨 КАРТОЧКИ
    cards = prediction.get('cards') or {}
    add_market('yellows_over_3_5', '🟨 Карточки ТБ 3.5', cards.get('Over 3.5', 0), 'S')
    add_market('yellows_over_4_5', '🟨 Карточки ТБ 4.5', cards.get('Over 4.5', 0), 'B')

    # 📊 УДАРЫ И ФОЛЫ
    shots = prediction.get('total_shots') or {}
    add_market('shots_over_22_5', '📊 Удары ТБ 22.5', shots.get('Over 22.5', 0), 'S')

    sot = prediction.get('total_shots_on_target') or {}
    add_market('sot_over_8_5', '🎯 Удары в створ ТБ 8.5', sot.get('Over 8.5', 0), 'S')

    fouls = prediction.get('total_fouls') or {}
    add_market('fouls_over_23_5', '⚠️ Фолы ТБ 23.5', fouls.get('Over 23.5', 0), 'B')

    markets.sort(key=lambda x: x['probability'], reverse=True)
    return markets[:4]


def _set_hot_bet(best_match: dict) -> dict:
    """Выбирает hot_bet на основе VALUE (исход/тотал с value → доп. рынок → фаворит)."""
    result_probs = best_match.get('result', {})
    odds = best_match.get('odds', {}) or {}
    candidates = []

    # 1. ИСХОДЫ 1X2
    for res_key, odds_key, label in [
        ('Home Win', 'home_win', f"П1 ({best_match.get('home_team', '')})"),
        ('Draw', 'draw', 'Ничья'),
        ('Away Win', 'away_win', f"П2 ({best_match.get('away_team', '')})"),
    ]:
        prob = result_probs.get(res_key, 0)
        val = calc_value(prob, odds.get(odds_key), min_prob=0.55)
        if prob >= 0.55 and val > 0:
            candidates.append((val, prob, label))

    # 2. ТОТАЛ 2.5
    total_goals = best_match.get('total_goals', {}) or {}
    for res_key, odds_key, label in [
        ('Over 2.5', 'over_2_5', 'ТБ 2.5'),
        ('Under 2.5', 'under_2_5', 'ТМ 2.5'),
    ]:
        prob = total_goals.get(res_key, 0)
        val = calc_value(prob, odds.get(odds_key), min_prob=0.50)
        if prob >= 0.50 and val > 0:
            candidates.append((val, prob, label))

    if candidates:
        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        val, prob, label = candidates[0]
        best_match['hot_bet'] = f"{label} ({round(prob * 100, 1)}%)"
        best_match['hot_confidence'] = round(prob * 100, 1)
        best_match['hot_bet_type'] = 'value'
        return best_match

    # 3. ЛУЧШИЙ ДОП. РЫНОК
    if best_match.get('additional_markets'):
        top = best_match['additional_markets'][0]
        prob_pct = round(top['probability'] * 100, 1)
        best_match['hot_bet'] = f"{top['label']} ({prob_pct}%)"
        best_match['hot_confidence'] = prob_pct
        best_match['hot_bet_type'] = 'market'
        return best_match

    # 4. ФАВОРИТ МОДЕЛИ (фолбэк)
    if result_probs:
        fav_key, fav_prob = max(result_probs.items(), key=lambda kv: kv[1])
        fav_labels = {
            'Home Win': f"П1 ({best_match.get('home_team', '')})",
            'Draw': 'Ничья',
            'Away Win': f"П2 ({best_match.get('away_team', '')})",
        }
        best_match['hot_bet'] = f"{fav_labels.get(fav_key, fav_key)} ({round(fav_prob * 100, 1)}%)"
        best_match['hot_confidence'] = round(fav_prob * 100, 1)
        best_match['hot_bet_type'] = 'favorite'

    return best_match


def _diversify_by_league(candidates: list, limit: int = 5, penalty: float = 15) -> list:
    """Обеспечивает разнообразие лиг в топ-N с минимальным порогом качества 80."""
    if not candidates:
        return []
    
    sorted_candidates = sorted(candidates, key=lambda x: x['score'], reverse=True)
    result = []
    league_count = {}
    
    for c in sorted_candidates:
        league = c['league']
        count = league_count.get(league, 0)
        adjusted_score = c['score'] - count * penalty
        
        if adjusted_score >= 80 and len(result) < limit:
            result.append(c)
            league_count[league] = count + 1
    
    if len(result) < limit:
        remaining = [c for c in sorted_candidates if c not in result]
        for c in remaining:
            if len(result) < limit:
                result.append(c)
    
    return result


def _process_league(league_key: str, model_info: dict, tier: str, min_conf: float) -> tuple:
    """
    Обрабатывает ОДНУ лигу и возвращает список кандидатов + статистику.
    Вызывается параллельно через ThreadPoolExecutor.
    
    ВОЗВРАЩАЕТ: (candidates_list, debug_stats_dict)
    """
    candidates = []
    debug = {
        'total_fixtures': 0,
        'teams_found': 0,
        'teams_not_found': 0,
        'prediction_errors': 0,
        'low_confidence': 0,
        'no_value_no_markets': 0,
        'passed': 0,
    }
    
    fixtures = get_fixtures(league_key)
    if not fixtures:
        return candidates, debug
    
    df = model_info.get('df')
    if df is None:
        return candidates, debug
    
    all_teams = list(set(df['home_team']) | set(df['away_team']))
    debug['total_fixtures'] = len(fixtures)
    
    for fixture in fixtures:
        try:
            # Нормализуем имена через словарь алиасов
            home_normalized = normalize_team_name(fixture['home_team'])
            away_normalized = normalize_team_name(fixture['away_team'])
            
            home_team = find_similar_team(home_normalized, all_teams, threshold=0.6)
            away_team = find_similar_team(away_normalized, all_teams, threshold=0.6)
            
            if not home_team or not away_team:
                debug['teams_not_found'] += 1
                continue
            
            # Критическая проверка: команды не должны совпадать
            if home_team == away_team:
                debug['teams_not_found'] += 1
                continue
            
            debug['teams_found'] += 1
            
            prediction = predict_match(
                team1=home_team, team2=away_team,
                model_data=model_info['model_data'],
                ratings_dict=model_info.get('ratings', {}),
                all_matches_df=df,
            )
            if 'error' in prediction or 'result' not in prediction:
                debug['prediction_errors'] += 1
                continue
            
            odds = fixture.get('odds', {}) or {}
            result_probs = prediction.get('result', {})
            
            # Sanity-check кэфов (защита от битых данных)
            bk_home_fav = (odds.get('home_win') or 99) < (odds.get('away_win') or 99)
            md_home_fav = result_probs.get('Home Win', 0) > result_probs.get('Away Win', 0)
            extreme = max(odds.get('home_win') or 0, odds.get('away_win') or 0) > 3.5
            odds_suspicious = (bk_home_fav != md_home_fav) and extreme
            
            value_home = calc_value(result_probs.get('Home Win', 0), odds.get('home_win'), min_prob=0.50)
            value_draw = calc_value(result_probs.get('Draw', 0), odds.get('draw'), min_prob=0.30)
            value_away = calc_value(result_probs.get('Away Win', 0), odds.get('away_win'), min_prob=0.50)
            
            # Если кэфы подозрительные — обнуляем value по исходам
            if odds_suspicious:
                value_home = 0.0
                value_away = 0.0
            
            tg_probs = prediction.get('total_goals') or {}
            value_over = calc_value(tg_probs.get('Over 2.5', 0), odds.get('over_2_5'), min_prob=0.50)
            value_under = calc_value(tg_probs.get('Under 2.5', 0), odds.get('under_2_5'), min_prob=0.50)
            
            best_value = max(value_home, value_draw, value_away, value_over, value_under)
            additional_markets = _extract_additional_markets(prediction, odds)
            confidence = prediction.get('hot_confidence', 0)
            
            if confidence < min_conf:
                debug['low_confidence'] += 1
                continue
            
            if not (best_value > 0 or additional_markets):
                debug['no_value_no_markets'] += 1
                continue
            
            value_bonus = min(best_value, 0.30) * 100 if best_value > 0 else 0
            score = confidence + value_bonus + len(additional_markets) * 5
            
            candidate = {
                **prediction,
                'league': league_key,
                'league_name': model_info['name'],
                'tier': tier,
                'commence_time': fixture['commence_time'],
                'odds': odds,
                'value': {
                    'home_win': value_home, 'draw': value_draw,
                    'away_win': value_away, 'over_2_5': value_over,
                    'under_2_5': value_under,
                },
                'best_value': best_value,
                'additional_markets': additional_markets,
                'is_hot': True,
                'score': round(score, 1),
            }
            candidate = _set_hot_bet(candidate)
            
            # Пересчёт trust_signal на основе hot_confidence
            hc = candidate.get('hot_confidence', 0)
            if hc >= 70:
                candidate['trust_signal'] = "💎 АЛМАЗНЫЙ | Максимальная уверенность"
            elif hc >= 60:
                candidate['trust_signal'] = "🥇 ЗОЛОТОЙ | Высокая уверенность"
            elif hc >= 55:
                candidate['trust_signal'] = " СЕРЕБРЯНЫЙ | Средняя уверенность"
            else:
                candidate['trust_signal'] = "🥉 БРОНЗОВЫЙ | Низкая уверенность"
            
            candidates.append(candidate)
            debug['passed'] += 1
            
        except Exception as e:
            debug['prediction_errors'] += 1
            logger.warning(f"⚠️ Ошибка обработки матча {fixture.get('home_team')} vs {fixture.get('away_team')}: {e}")
            continue
    
    return candidates, debug

def _collect_hot_predictions(limit: int = 5) -> List[dict]:
    """Собирает ТОП-N hot-прогнозов из БУДУЩИХ матчей с кэфами."""
    candidates = []
    debug_stats = {}
    
    for league_key in ODDS_ACTIVE_LEAGUES:
        debug_stats[league_key] = {
            'total_fixtures': 0,
            'teams_found': 0,
            'teams_not_found': 0,
            'prediction_errors': 0,
            'low_confidence': 0,
            'no_value_no_markets': 0,
            'passed': 0,
        }
        
        if league_key not in MODELS:
            continue
        model_info = MODELS[league_key]
        
        tier = LEAGUE_TIERS.get(league_key, 'C')
        if tier == 'C':
            continue
        
        min_conf = HOT_MIN_CONFIDENCE.get(tier, 60)
        fixtures = get_fixtures(league_key)
        if not fixtures:
            continue
        
        df = model_info.get('df')
        if df is None:
            continue
        all_teams = list(set(df['home_team']) | set(df['away_team']))
        debug_stats[league_key]['total_fixtures'] = len(fixtures)
        
        for fixture in fixtures:
            try:
                # Нормализуем имена через словарь алиасов
                home_normalized = normalize_team_name(fixture['home_team'])
                away_normalized = normalize_team_name(fixture['away_team'])
                
                home_team = find_similar_team(home_normalized, all_teams, threshold=0.60)
                away_team = find_similar_team(away_normalized, all_teams, threshold=0.60)
                
                if not home_team or not away_team:
                    if not home_team:
                        print(f"   ⚠️ {league_key}: НЕ НАЙДЕНА '{fixture['home_team']}'", flush=True)
                    if not away_team:
                        print(f"   ⚠️ {league_key}: НЕ НАЙДЕНА '{fixture['away_team']}'", flush=True)
                    debug_stats[league_key]['teams_not_found'] += 1
                    continue


                if home_team == away_team:
                    print(f"   ⚠️ {league_key}: КОМАНДЫ СОВПАЛИ! '{fixture['home_team']}' vs '{fixture['away_team']}' → оба = '{home_team}'", flush=True)
                    debug_stats[league_key]['teams_not_found'] += 1
                    continue
                
                debug_stats[league_key]['teams_found'] += 1
                
                prediction = predict_match(
                    team1=home_team, team2=away_team,
                    model_data=model_info['model_data'],
                    ratings_dict=model_info.get('ratings', {}),
                    all_matches_df=df,
                )
                if 'error' in prediction or 'result' not in prediction:
                    debug_stats[league_key]['prediction_errors'] += 1
                    continue
                
                odds = fixture.get('odds', {}) or {}
                result_probs = prediction.get('result', {})
            
            # 🛡️ ЗАЩИТА от битых/перепутанных кэфов:
            # если букмекер и модель НЕ согласны, кто фаворит,
            # и кэфы экстремальные — не доверяем value по исходам
                bk_home_fav = (odds.get('home_win') or 99) < (odds.get('away_win') or 99)
                md_home_fav = result_probs.get('Home Win', 0) > result_probs.get('Away Win', 0)
                extreme = max(odds.get('home_win') or 0, odds.get('away_win') or 0) > 3.5
                odds_suspicious = (bk_home_fav != md_home_fav) and extreme
            
                if odds_suspicious:
                    print(f"   🛡️ {league_key}: подозрительные кэфы ({fixture['home_team']}: {odds.get('home_win')} / {odds.get('away_win')}) — value по исходам обнулён", flush=True)
            
                value_home = calc_value(result_probs.get('Home Win', 0), odds.get('home_win'), min_prob=0.50)
                value_draw = calc_value(result_probs.get('Draw', 0), odds.get('draw'), min_prob=0.30)
                value_away = calc_value(result_probs.get('Away Win', 0), odds.get('away_win'), min_prob=0.50)
            
                # 🛡️ Если кэфы подозрительные — обнуляем value по исходам
                if odds_suspicious:
                    value_home = 0.0
                    value_away = 0.0
                
                tg_probs = prediction.get('total_goals') or {}
                value_over = calc_value(tg_probs.get('Over 2.5', 0), odds.get('over_2_5'), min_prob=0.50)
                value_under = calc_value(tg_probs.get('Under 2.5', 0), odds.get('under_2_5'), min_prob=0.50)
                
                best_value = max(value_home, value_draw, value_away, value_over, value_under)
                additional_markets = _extract_additional_markets(prediction, odds)
                confidence = prediction.get('hot_confidence', 0)
                
                if confidence < min_conf:
                    debug_stats[league_key]['low_confidence'] += 1
                    continue
                
                if not (best_value > 0 or additional_markets):
                    debug_stats[league_key]['no_value_no_markets'] += 1
                    continue
                
                value_bonus = min(best_value, 0.30) * 100 if best_value > 0 else 0
                score = confidence + value_bonus + len(additional_markets) * 5
                
                candidate = {
                    **prediction,
                    'league': league_key,
                    'league_name': model_info['name'],
                    'tier': tier,
                    'commence_time': fixture['commence_time'],
                    'odds': odds,
                    'value': {
                        'home_win': value_home, 'draw': value_draw,
                        'away_win': value_away, 'over_2_5': value_over,
                        'under_2_5': value_under,
                    },
                    'best_value': best_value,
                    'additional_markets': additional_markets,
                    'is_hot': True,
                    'score': round(score, 1),
                }
                candidate = _set_hot_bet(candidate)
                
                # Пересчёт trust_signal на основе hot_confidence
                hc = candidate.get('hot_confidence', 0)
                if hc >= 70:
                    candidate['trust_signal'] = "💎 АЛМАЗНЫЙ | Максимальная уверенность"
                elif hc >= 60:
                    candidate['trust_signal'] = "🥇 ЗОЛОТОЙ | Высокая уверенность"
                elif hc >= 55:
                    candidate['trust_signal'] = "🥈 СЕРЕБРЯНЫЙ | Средняя уверенность"
                else:
                    candidate['trust_signal'] = "🥉 БРОНЗОВЫЙ | Низкая уверенность"
                
                candidates.append(candidate)
                debug_stats[league_key]['passed'] += 1
                
            except Exception as e:
                debug_stats[league_key]['prediction_errors'] += 1
                logger.warning(f"⚠️ Ошибка обработки матча: {e}")
                continue


    # 🆕 ОТЛАДКА: ВСЕ кандидаты до диверсификации
    print("\n" + "="*60, flush=True)
    print(f"🔍 ВСЕГО КАНДИДАТОВ ДО ДИВЕРСИФИКАЦИИ: {len(candidates)}", flush=True)
    if candidates:
        for i, c in enumerate(candidates[:10], 1):
            print(f"   {i}. {c['league']} | {c['home_team']} vs {c['away_team']} | score={c['score']} | {c['hot_bet']}", flush=True)
    print("="*60, flush=True)
    
    # Диагностика
    print("\n" + "="*60, flush=True)
    print("🔍 ДИАГНОСТИКА HOT-ПРОГНОЗОВ ПО ЛИГАМ", flush=True)
    print("="*60, flush=True)
    for league, stats in debug_stats.items():
        if stats['total_fixtures'] == 0:
            continue
        print(f"\n🏆 {league.upper()}:", flush=True)
        print(f"   📊 Матчей в расписании: {stats['total_fixtures']}", flush=True)
        print(f"   ✅ Команд найдено: {stats['teams_found']}", flush=True)
        print(f"   ❌ Команд НЕ найдено: {stats['teams_not_found']}", flush=True)
        print(f"   ⚠️ Ошибок прогноза: {stats['prediction_errors']}", flush=True)
        print(f"   📉 Низкая уверенность: {stats['low_confidence']}", flush=True)
        print(f"   🚫 Нет value/рынков: {stats['no_value_no_markets']}", flush=True)
        print(f"   🎯 ПРОШЛО ФИЛЬТР: {stats['passed']}", flush=True)
    print("="*60 + "\n", flush=True)
    
    candidates = _diversify_by_league(candidates, limit=limit, penalty=15)
    return candidates[:limit]


# ==================== ENDPOINTS: HOT ====================

@app.get("/api/predictions/hot")
def get_hot_prediction(user: dict = Depends(get_current_user)):
    """
    Лучший hot-прогноз (главная карточка) — с кэшем.
    
    ПЕРВЫЙ ЗАПРОС: 30-40 сек (пересчёт)
    ПОВТОРНЫЕ ЗАПРОСЫ (в течение 5 мин): <100 мс (из кэша)
    """
    hot_list = get_hot_cached()  # ← Используем кэш вместо прямого вызова
    if not hot_list:
        raise HTTPException(status_code=404, detail="No hot predictions available")
    return hot_list[0]


@app.get("/api/predictions/hot/list")
def get_hot_prediction_list(user: dict = Depends(get_current_user)):
    """
    ТОП-5 hot-прогнозов для кнопки «Следующий» — с кэшем.
    
    ПЕРВЫЙ ЗАПРОС: 30-40 сек (пересчёт)
    ПОВТОРНЫЕ ЗАПРОСЫ (в течение 5 мин): <100 мс (из кэша)
    """
    hot_list = get_hot_cached()  # ← Используем кэш вместо прямого вызова
    if not hot_list:
        raise HTTPException(status_code=404, detail="No hot predictions available")
    return hot_list

# ==================== ENDPOINTS: РАСПИСАНИЕ МАТЧЕЙ ====================

@app.get("/api/fixtures")
def get_all_fixtures(user: dict = Depends(get_current_user)):
    """Возвращает расписание матчей для активных лиг"""
    result = []
    for league_key in ODDS_ACTIVE_LEAGUES:
        if league_key in MODELS:
            fixtures = get_fixtures(league_key)
            if fixtures:
                result.append({
                    "league": league_key,
                    "league_name": MODELS[league_key]['name'],
                    "matches": fixtures,
                })
    return result


@app.get("/api/fixtures/{league}")
def get_league_fixtures(league: str, user: dict = Depends(get_current_user)):
    if league not in MODELS:
        raise HTTPException(status_code=404, detail="League not found")
    fixtures = get_fixtures(league)
    return {
        "league": league,
        "league_name": MODELS[league]['name'],
        "matches": fixtures,
    }


@app.get("/api/odds/available-sports")
def get_sports(user: dict = Depends(get_current_user)):
    """⚠️ Тратит 1 кредит! Используй только для проверки."""
    sports = get_available_sports()
    return {"soccer_sports": sports, "count": len(sports)}


# ==================== ENDPOINTS: СТАТИСТИКА ====================
# 🚨 ВАЖНО: /top ОБЯЗАН быть объявлен ПЕРЫМ!
@app.get("/api/stats/{league}/top")
def get_top_teams(
    league: str,
    stat_type: str = "corners",
    top_n: int = 3,
    user: dict = Depends(require_subscription)
):
    if league not in MODELS:
        raise HTTPException(status_code=404, detail="League not found")
    df = MODELS[league].get('df')
    if df is None:
        return []
    rankings = get_league_rankings(df, stat_type, top_n=top_n, season_start_date=None)
    return rankings


@app.get("/api/stats/{league}/{team}", response_model=TeamStatsResponse)
def get_team_stats(league: str, team: str, user: dict = Depends(require_subscription)):
    if league not in MODELS:
        raise HTTPException(status_code=404, detail="League not found")
    df = MODELS[league].get('df')
    if df is None:
        raise HTTPException(status_code=404, detail="No data")
    
    stats = calculate_team_statistics(df, team, season_start_date=None)
    if not stats:
        raise HTTPException(status_code=404, detail=f"Team '{team}' not found in {league}")
    return TeamStatsResponse(**stats)


@app.get("/api/leagues/{league}/seasons", response_model=List[str])
def get_available_seasons(league: str, user: dict = Depends(get_current_user)):
    if league not in MODELS:
        raise HTTPException(status_code=404, detail="League not found")
    df = MODELS[league].get('df')
    if df is None or 'season' not in df.columns:
        return []
    return sorted(df['season'].unique().tolist())


@app.get("/api/user/subscription")
def get_subscription(user: dict = Depends(get_current_user)):
    """Возвращает информацию о подписке. НЕ требует активной подписки."""
    from database import is_subscription_active
    
    user_id = user['id']
    create_user(user_id, user.get('username'), user.get('first_name'))
    
    sub_info = get_subscription_info(user_id)
    
    # 🆕 АВТОАКТИВАЦИЯ TRIAL при первом входе
    # Если trial доступен и подписки нет — активируем автоматически
    if (sub_info.get('trial_available') and 
        not sub_info.get('is_active') and
        sub_info.get('subscription_type') == 'free'):
        
        try:
            activate_subscription(user_id, 'trial', 3)
            use_trial(user_id)
            # Перечитываем информацию после активации
            sub_info = get_subscription_info(user_id)
            sub_info['trial_just_activated'] = True
        except Exception as e:
            logger.warning(f"️ Не удалось активировать trial для user {user_id}: {e}")
    
    return sub_info

@app.get("/api/user/me")
def get_current_user_info(user: dict = Depends(get_current_user)):
    """
    Возвращает информацию о текущем пользователе.
    Используется фронтом для определения: админ ли это, показывать ли кнопку оплаты.
    """
    user_id = user.get('id')
    
    # Создаём пользователя в БД если его ещё нет
    create_user(user_id, user.get('username'), user.get('first_name'))
    
    # Получаем статус подписки
    from database import is_subscription_active, get_subscription_info
    sub_info = get_subscription_info(user_id)
    
    return {
        'id': user_id,
        'first_name': user.get('first_name'),
        'username': user.get('username'),
        'is_admin': user_id == ADMIN_ID,  # 👑 КЛЮЧЕВОЕ ПОЛЕ
        'subscription': sub_info,
        'has_access': is_subscription_active(user_id),
    }

@app.get("/api/user/check-access")
def check_access(user: dict = Depends(get_current_user)):
    """
    Быстрая проверка доступа. Используется фронтендом для paywall.
    Возвращает статус без полной информации о подписке.
    """
    from database import is_subscription_active
    
    user_id = user['id']
    create_user(user_id, user.get('username'), user.get('first_name'))
    
    is_active = is_subscription_active(user_id)
    
    return {
        'has_access': is_active,
        'user_id': user_id
    }

@app.post("/api/user/trial")
def activate_trial(user: dict = Depends(get_current_user)):
    user_id = user['id']
    if not is_trial_available(user_id):
        raise HTTPException(status_code=400, detail="Trial already used")
    activate_subscription(user_id, 'trial', 3)
    use_trial(user_id)
    return {'success': True, 'message': 'Trial activated for 3 days'}


@app.get("/api/user/referrals")
def get_referrals(user: dict = Depends(get_current_user)):
    user_id = user['id']
    ref_count = get_referral_count(user_id)
    bonus_days = ref_count * REFERRAL_FREE_DAYS
    return {
        'ref_count': ref_count,
        'bonus_days': bonus_days,
        'ref_link': f"https://t.me/your_bot_username?start=ref_{user_id}"
    }


# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)