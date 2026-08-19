from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import sys
import os


# Добавляем корневую папку в путь (для импорта model.py, database.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from model import (
    load_matches_data, train_models, predict_match,
    load_model, save_model,
    find_similar_team,
    calculate_team_statistics, get_league_rankings,
    HOME_WIN, DRAW, AWAY_WIN, OVER_25, UNDER_25, BTTS_YES, BTTS_NO
)
from database import (
    create_user, get_user_subscription, activate_subscription,
    is_trial_available, use_trial, add_referral, get_referral_count,
    init_db
)
from config import (LEAGUES, SUBSCRIPTION_PRICES, REFERRAL_FREE_DAYS,
                    LEAGUE_TIERS, HOT_MIN_CONFIDENCE)
from auth import verify_telegram_init_data

from fixtures_service import get_fixtures, calc_value, calc_fair_odds, get_available_sports
import logging  # ← ДОБАВЛЕНО
logger = logging.getLogger(__name__) 

# ==================== ЗАГРУЗКА МОДЕЛЕЙ ====================
MODELS = {}
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')

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
            
            # Финальная загрузка DataFrame для словаря MODELS
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
    # === ЭТО ВЫПОЛНЯЕТСЯ ПРИ ЗАПУСКЕ (STARTUP) ===
    print("\n" + "="*80, flush=True)
    print("🚀 ЗАПУСК ФУНКЦИИ LIFESPAN (STARTUP)", flush=True)
    print(f"📁 Текущая рабочая директория: {os.getcwd()}", flush=True)
    print("="*80 + "\n", flush=True)
    
    init_db()
    print("🗄️ База данных инициализирована", flush=True)
    
    load_all_models()
    
    print("\n🎉 ВСЕ ПРОЦЕДУРЫ STARTUP ЗАВЕРШЕНЫ УСПЕШНО 🎉\n", flush=True)
    
    yield  # <-- Здесь приложение работает и принимает запросы
    
    # === ЭТО ВЫПОЛНЯЕТСЯ ПРИ ОСТАНОВКЕ (SHUTDOWN) ===
    print("🛑 Завершение работы приложения...", flush=True)

# ⚠️ ВАЖНО: Создаем приложение ЗДЕСЬ, до всех маршрутов (@app.get)
app = FastAPI(title="Football Predictor API", version="2.0", lifespan=lifespan)

# ==================== MIDDLEWARE ====================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://*.onrender.com",
        "https://web.telegram.org",
        "https://t.me",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== ENDPOINTS ====================
@app.get("/")
def root():
    return {"status": "ok", "message": "Football Predictor API is running"}

# ==================== АВТОРИЗАЦИЯ ====================
def get_current_user(x_telegram_init_data: str = Header(None, alias="X-Telegram-Init-Data")) -> dict:
    return verify_telegram_init_data(x_telegram_init_data)

# ==================== МОДЕЛИ ДАННЫХ ====================
class MatchRequest(BaseModel):
    team1: str
    team2: str
    league: str

class PredictionResponse(BaseModel):
    home_team: str
    away_team: str
    timestamp: str
    risk_level: str
    
    # Основные рынки
    result: dict
    total_goals: Optional[dict] = None
    both_scored: Optional[dict] = None
    
    # 🔥 НОВЫЕ РЫНКИ (добавь эти строки!)
    first_half_result: Optional[dict] = None
    total_shots: Optional[dict] = None
    total_shots_on_target: Optional[dict] = None
    total_fouls: Optional[dict] = None
    btts_first_half: Optional[dict] = None
    individual_totals: Optional[dict] = None
    
    # Старые поля (угловые/карточки — если модель их не возвращает, можно убрать)
    corners: Optional[dict] = None
    cards: Optional[dict] = None
    
    # Метаданные
    recommendation: Optional[str] = None
    trust_signal: Optional[str] = None
    is_hot: bool = False
    hot_confidence: float = 0.0
    hot_bet: Optional[str] = None
    hot_bet_tier: Optional[str] = None
    # 🆕 Новые поля для Этапа 2
    commence_time: Optional[str] = None
    odds: Optional[dict] = None
    value: Optional[dict] = None
    best_value: Optional[float] = None
    additional_markets: Optional[List[dict]] = None  # ← ДОБАВЛЕНО

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

# ==================== ENDPOINTS: ПРОГНОЗЫ ====================
@app.post("/api/predictions/match", response_model=PredictionResponse)
def get_match_prediction(req: MatchRequest, user: dict = Depends(get_current_user)):
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

def _extract_additional_markets(prediction: dict) -> List[dict]:
    """
    Извлекает дополнительные рынки (угловые, карточки) из прогноза.
    Возвращает список рынков с уверенностью и справедливым кэфом.
    
    Используются только рынки тира S и B из MARKET_TIERS:
        S: corners_over_9_5, yellows_over_3_5
        B: yellows_over_4_5
    """
    from config import CONF_THRESHOLD
    
    markets = []

    # 🎯 УГЛОВЫЕ
    corners = prediction.get('corners')
    if corners:
        # ТБ 9.5 (тир S)
        prob_95 = corners.get('Over 9.5', 0)
        if prob_95 >= CONF_THRESHOLD:
            markets.append({
                'market': 'corners_over_9_5',
                'label': '🎯 Угловые ТБ 9.5',
                'probability': round(prob_95, 3),
                'fair_odds': calc_fair_odds(prob_95),
                'tier': 'S',
                'hint': f"Ищите кэф выше {calc_fair_odds(prob_95)}",
            })

    # 🟨 КАРТОЧКИ
    cards = prediction.get('cards')
    if cards:
        # ТБ 3.5 (тир S)
        prob_35 = cards.get('Over 3.5', 0)
        if prob_35 >= CONF_THRESHOLD:
            markets.append({
                'market': 'yellows_over_3_5',
                'label': '🟨 Карточки ТБ 3.5',
                'probability': round(prob_35, 3),
                'fair_odds': calc_fair_odds(prob_35),
                'tier': 'S',
                'hint': f"Ищите кэф выше {calc_fair_odds(prob_35)}",
            })

        # ТБ 4.5 (тир B)
        prob_45 = cards.get('Over 4.5', 0)
        if prob_45 >= CONF_THRESHOLD:
            markets.append({
                'market': 'yellows_over_4_5',
                'label': '🟨 Карточки ТБ 4.5',
                'probability': round(prob_45, 3),
                'fair_odds': calc_fair_odds(prob_45),
                'tier': 'B',
                'hint': f"Ищите кэф выше {calc_fair_odds(prob_45)}",
            })

    # Сортируем по уверенности (от высокой к низкой)
    markets.sort(key=lambda x: x['probability'], reverse=True)
    
    return markets


def _set_hot_bet(best_match: dict) -> dict:
    """
    Определяет hot_bet на основе value, а не просто уверенности.
    Выбирает исход с максимальной ценностью.
    """
    value_map = best_match.get('value', {})
    outcome_names = {
        'home_win': 'Home Win',
        'draw': 'Draw',
        'away_win': 'Away Win',
    }
    
    best_outcome_key = None
    best_outcome_value = 0.0
    
    for key, value in value_map.items():
        if value > best_outcome_value:
            best_outcome_value = value
            best_outcome_key = key
    
    # Если есть value > 0 — показываем этот исход
    if best_outcome_key and best_outcome_value > 0:
        team1 = best_match.get('home_team', '')
        team2 = best_match.get('away_team', '')
        bet_labels = {
            'home_win': f'П1 ({team1})',
            'draw': 'Ничья',
            'away_win': f'П2 ({team2})',
        }
        outcome_prob = best_match.get('result', {}).get(outcome_names[best_outcome_key], 0)
        confidence_pct = round(outcome_prob * 100, 1)
        best_match['hot_bet'] = f"{bet_labels[best_outcome_key]} ({confidence_pct}%)"
        best_match['hot_confidence'] = confidence_pct
    # Если value нет, но есть доп. рынки — показываем лучший доп. рынок
    elif best_match.get('additional_markets'):
        top_market = best_match['additional_markets'][0]
        prob_pct = round(top_market['probability'] * 100, 1)
        best_match['hot_bet'] = f"{top_market['label']} ({prob_pct}%)"
        best_match['hot_confidence'] = prob_pct
    
    return best_match

@app.get("/api/predictions/hot")
def get_hot_prediction(user: dict = Depends(get_current_user)):
    """
    🔥 Горячий прогноз на основе БУДУЩИХ матчей с коэффициентами.
    
    Этап 1: Исход матча (П1/Х/П2) с реальными кэфами из The Odds API
    Этап 2: Угловые и карточки со "справедливым кэфом" от модели
    """
    best_match = None
    best_score = 0

    for league_key, model_info in MODELS.items():
        tier = LEAGUE_TIERS.get(league_key, 'C')
        if tier == 'C':
            continue

        min_conf = HOT_MIN_CONFIDENCE.get(tier, 60)

        # Получаем расписание с коэффициентами
        fixtures = get_fixtures(league_key)
        if not fixtures:
            continue

        df = model_info.get('df')
        if df is None:
            continue
        all_teams = list(set(df['home_team']) | set(df['away_team']))

        for fixture in fixtures:
            try:
                # Нечёткий поиск команд
                home_team = find_similar_team(fixture['home_team'], all_teams, threshold=0.6)
                away_team = find_similar_team(fixture['away_team'], all_teams, threshold=0.6)

                if not home_team or not away_team:
                    continue

                # Прогноз модели
                prediction = predict_match(
                    team1=home_team,
                    team2=away_team,
                    model_data=model_info['model_data'],
                    ratings_dict=model_info.get('ratings', {}),
                    all_matches_df=df,
                )

                if 'error' in prediction or 'result' not in prediction:
                    continue

                # ========== ЭТАП 1: Value для исхода (П1/Х/П2) ==========
                odds = fixture.get('odds', {})
                result_probs = prediction.get('result', {})

                value_home = calc_value(result_probs.get('Home Win', 0), odds.get('home_win'), min_prob=0.40)
                value_draw = calc_value(result_probs.get('Draw', 0), odds.get('draw'), min_prob=0.25)
                value_away = calc_value(result_probs.get('Away Win', 0), odds.get('away_win'), min_prob=0.40)

                best_value = max(value_home, value_draw, value_away)
                confidence = prediction.get('hot_confidence', 0)

                # ========== ЭТАП 2: Дополнительные рынки (угловые, карточки) ==========
                additional_markets = _extract_additional_markets(prediction)

                # Score = уверенность исхода + бонус за value + бонус за доп. рынки
                score = confidence + (best_value * 100 if best_value > 0 else 0)
                score += len(additional_markets) * 5  # бонус за каждый доп. рынок

                # Условия Hot: уверенность >= порога И (value > 0 ИЛИ есть доп. рынки)
                has_value = best_value > 0
                has_extra = len(additional_markets) > 0

                if score > best_score and confidence >= min_conf and (has_value or has_extra):
                    best_score = score
                    best_match = {
                        **prediction,
                        'league': league_key,
                        'league_name': model_info['name'],
                        'tier': tier,
                        'commence_time': fixture['commence_time'],
                        'odds': odds,
                        'value': {
                            'home_win': value_home,
                            'draw': value_draw,
                            'away_win': value_away,
                        },
                        'best_value': best_value,
                        'additional_markets': additional_markets,
                        'is_hot': True,
                    }

            except Exception as e:
                logger.warning(f"⚠️ Ошибка обработки матча {fixture.get('home_team')} vs {fixture.get('away_team')}: {e}")
                continue

    if not best_match:
        raise HTTPException(status_code=404, detail="No hot predictions available")

    # Определяем hot_bet на основе value
    best_match = _set_hot_bet(best_match)

    return best_match

# ==================== ENDPOINTS: РАСПИСАНИЕ МАТЧЕЙ ====================

@app.get("/api/fixtures")
def get_all_fixtures(user: dict = Depends(get_current_user)):
    """Возвращает расписание матчей для активных лиг"""
    from config import ODDS_ACTIVE_LEAGUES
    
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
    """Возвращает расписание матчей для конкретной лиги"""
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
    """
    Показывает доступные лиги в The Odds API.
    ⚠️ Тратит 1 кредит! Используй только для проверки.
    """
    sports = get_available_sports()
    return {"soccer_sports": sports, "count": len(sports)}

# ==================== ENDPOINTS: СТАТИСТИКА ====================
# 🚨 ВАЖНО: Статический путь /top ОБЯЗАН быть объявлен ПЕРВЫМ!
@app.get("/api/stats/{league}/top")
def get_top_teams(
    league: str,
    stat_type: str = "corners",
    top_n: int = 3,
    user: dict = Depends(get_current_user)
):
    if league not in MODELS:
        raise HTTPException(status_code=404, detail="League not found")
    df = MODELS[league].get('df')
    if df is None:
        return []
    # Передаем None вместо жесткой даты 2025-08-01
    rankings = get_league_rankings(df, stat_type, top_n=top_n, season_start_date=None)
    return rankings

@app.get("/api/stats/{league}/{team}", response_model=TeamStatsResponse)
def get_team_stats(league: str, team: str, user: dict = Depends(get_current_user)):
    if league not in MODELS:
        raise HTTPException(status_code=404, detail="League not found")
    df = MODELS[league].get('df')
    if df is None:
        raise HTTPException(status_code=404, detail="No data")
    
    # Передаем None вместо жесткой даты
    stats = calculate_team_statistics(df, team, season_start_date=None)
    
    if not stats:
        raise HTTPException(status_code=404, detail=f"Team '{team}' not found in {league}")
    return TeamStatsResponse(**stats)

@app.get("/api/leagues/{league}/seasons", response_model=List[str])
def get_available_seasons(league: str, user: dict = Depends(get_current_user)):
    """Возвращает список сезонов для лиги"""
    if league not in MODELS:
        raise HTTPException(status_code=404, detail="League not found")
    df = MODELS[league].get('df')
    if df is None or 'season' not in df.columns:
        return []
    return sorted(df['season'].unique().tolist())

# ==================== ENDPOINTS: ПОЛЬЗОВАТЕЛЬ ====================
@app.get("/api/user/subscription")
def get_subscription(user: dict = Depends(get_current_user)):
    user_id = user['id']
    create_user(user_id, user.get('username'), user.get('first_name'))
    
    sub = get_user_subscription(user_id)
    if not sub:
        return {'subscription_type': 'free', 'is_active': False}
    
    return sub

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