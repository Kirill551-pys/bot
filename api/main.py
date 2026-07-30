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

app = FastAPI(title="Football Predictor API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",           # Для локальной разработки
        "https://*.onrender.com",          # Для Render
        "https://web.telegram.org",        # Для Telegram Web
        "https://t.me",                    # Для Telegram
        "*"                                # Временно для всех (потом уберём)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== ЗАГРУЗКА МОДЕЛЕЙ ====================
MODELS = {}
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')

def load_all_models():
    """Загружает все модели при старте"""
    for folder, display_name in LEAGUES.items():
        data_path = os.path.join(DATA_DIR, folder, 'matches.csv')
        model_path = os.path.join(DATA_DIR, folder, 'model.pkl')
        
        if not os.path.exists(data_path):
            continue
        
        try:
            if os.path.exists(model_path):
                model_data = load_model(model_path)
            else:
                df = load_matches_data(data_path)
                if df is not None and len(df) > 50:
                    model_data = train_models(df)
                    save_model(model_data, model_path)
                else:
                    continue
            
            df = load_matches_data(data_path)
            MODELS[folder] = {
                'model_data': model_data,
                'df': df,
                'ratings': model_data.get('final_ratings', {}),
                'name': display_name
            }
            print(f"✅ Загружена модель: {display_name}")
        except Exception as e:
            print(f"❌ Ошибка загрузки {folder}: {e}")

@app.on_event("startup")
def startup():
    init_db()
    load_all_models()

# ==================== АВТОРИЗАЦИЯ ====================
def get_current_user(x_telegram_init_data: str = Header(...)) -> dict:
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
    """Список всех доступных лиг"""
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
    """Список команд лиги"""
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
    """Прогноз конкретного матча"""
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
    """Горячий прогноз дня"""
    best_match, best_prob = None, 0
    
    for league_key, model_info in MODELS.items():
        df = model_info.get('df')
        if df is None or len(df) < 10:
            continue
        
        # Берём последние 5 матчей и ищем лучший
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
@app.get("/api/stats/{league}/{team}", response_model=TeamStatsResponse)
def get_team_stats(league: str, team: str, user: dict = Depends(get_current_user)):
    """Статистика команды"""
    if league not in MODELS:
        raise HTTPException(status_code=404, detail="League not found")
    
    df = MODELS[league].get('df')
    if df is None:
        raise HTTPException(status_code=404, detail="No data")
    
    stats = calculate_team_statistics(df, team, season_start_date="2025-08-01")
    if not stats:
        raise HTTPException(status_code=404, detail="Team not found")
    
    return TeamStatsResponse(**stats)

@app.get("/api/stats/{league}/top")
def get_top_teams(
    league: str,
    stat_type: str = "corners",
    top_n: int = 3,
    user: dict = Depends(get_current_user)
):
    """ТОП-3 команд по показателю"""
    if league not in MODELS:
        raise HTTPException(status_code=404, detail="League not found")
    
    df = MODELS[league].get('df')
    if df is None:
        return []
    
    rankings = get_league_rankings(df, stat_type, top_n=top_n, season_start_date="2025-08-01")
    return rankings

# ==================== ENDPOINTS: ПОЛЬЗОВАТЕЛЬ ====================
@app.get("/api/user/subscription")
def get_subscription(user: dict = Depends(get_current_user)):
    """Информация о подписке"""
    user_id = user['id']
    create_user(user_id, user.get('username'), user.get('first_name'))
    
    sub = get_user_subscription(user_id)
    if not sub:
        return {'subscription_type': 'free', 'is_active': False}
    
    return sub

@app.post("/api/user/trial")
def activate_trial(user: dict = Depends(get_current_user)):
    """Активировать пробный период"""
    user_id = user['id']
    
    if not is_trial_available(user_id):
        raise HTTPException(status_code=400, detail="Trial already used")
    
    activate_subscription(user_id, 'trial', 3)
    use_trial(user_id)
    
    return {'success': True, 'message': 'Trial activated for 3 days'}

@app.get("/api/user/referrals")
def get_referrals(user: dict = Depends(get_current_user)):
    """Реферальная статистика"""
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
    import os
    # Render передаёт порт через переменную окружения PORT
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)