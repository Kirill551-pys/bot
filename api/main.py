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
    calculate_team_statistics, get_league_rankings,
    HOME_WIN, DRAW, AWAY_WIN, OVER_25, UNDER_25, BTTS_YES, BTTS_NO
)
from database import (
    create_user, get_user_subscription, activate_subscription,
    is_trial_available, use_trial, add_referral, get_referral_count,
    init_db
)
from config import LEAGUES, SUBSCRIPTION_PRICES, REFERRAL_FREE_DAYS
from auth import verify_telegram_init_data

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
    result: dict
    total_goals: Optional[dict] = None
    both_scored: Optional[dict] = None
    corners: Optional[dict] = None  
    cards: Optional[dict] = None 
    recommendation: Optional[str] = None
    trust_signal: Optional[str] = None
    is_hot: bool = False
    hot_confidence: float = 0.0
    hot_bet: Optional[str] = None

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
    
    return PredictionResponse(**prediction)

@app.get("/api/predictions/hot")
def get_hot_prediction(user: dict = Depends(get_current_user)):
    best_match, best_prob = None, 0
    
    for league_key, model_info in MODELS.items():
        df = model_info.get('df')
        if df is None or len(df) < 10:
            continue
        
        for _, match in df.tail(5).iterrows():
            team1, team2 = match['home_team'], match['away_team']
            
            try:
                prediction = predict_match(
                    team1=team1,
                    team2=team2,
                    model_data=model_info['model_data'],
                    ratings_dict=model_info.get('ratings', {}),
                    all_matches_df=df
                )
                
                if 'error' not in prediction and 'result' in prediction:
                    max_prob = max(prediction['result'].values())
                    if max_prob > best_prob and max_prob > 0.65:
                        best_prob = max_prob
                        best_match = {
                            **prediction,
                            'league': league_key,
                            'league_name': model_info['name']
                        }
            except Exception as e:
                continue
    
    if not best_match:
        raise HTTPException(status_code=404, detail="No hot predictions available")
    
    return best_match

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