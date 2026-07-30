"""
МОДЕЛЬ ДЛЯ ПРОГНОЗИРОВАНИЯ ФУТБОЛЬНЫХ МАТЧЕЙ — ПРОФЕССИОНАЛЬНАЯ ВЕРСИЯ 2.2
✅ Добавлены все новые рынки: 1-й тайм, Удары, Удары в створ, Фолы, ИТБ, ОЗ в 1-м тайме
✅ Полная совместимость с форматом Football-Data.co.uk
"""
import pandas as pd
import numpy as np
import os
import joblib
import logging
from datetime import datetime
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import TimeSeriesSplit
from xgboost import XGBClassifier
from difflib import get_close_matches
import warnings
from typing import Dict, List, Tuple, Optional

warnings.filterwarnings('ignore')

# ==================== НАСТРОЙКИ ====================
DEFAULT_RATING = 1500
HOME_ADVANTAGE = 100
MIN_TRAINING_MATCHES = 50
K_FACTOR = 32

HOME_WIN = "Home Win"
DRAW = "Draw"
AWAY_WIN = "Away Win"
OVER_25 = "Over 2.5"
UNDER_25 = "Under 2.5"
BTTS_YES = "Yes"
BTTS_NO = "No"

RISK_CONSERVATIVE = "conservative"
RISK_MEDIUM = "medium"
RISK_AGGRESSIVE = "aggressive"

RISK_THRESHOLDS = {
    RISK_CONSERVATIVE: {'min_confidence': 0.75, 'min_gap': 0.30, 'min_trust_score': 0.80},
    RISK_MEDIUM: {'min_confidence': 0.68, 'min_gap': 0.22, 'min_trust_score': 0.70},
    RISK_AGGRESSIVE: {'min_confidence': 0.60, 'min_gap': 0.15, 'min_trust_score': 0.60}
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def safe_convert_goals(col):
    if col.dtype == 'object':
        col = col.astype(str).str.strip().str.replace(',', '.').str.replace('–', '-').str.replace('—', '-')
        col = col.replace(['', '-', '–', '—', 'nan', 'NaN', 'None', ' ', 'null', 'NULL'], '0')
    return pd.to_numeric(col, errors='coerce').fillna(0).astype(int)

def validate_training_data(df: pd.DataFrame) -> tuple:
    issues = []
    if df is None or len(df) < MIN_TRAINING_MATCHES:
        issues.append(f"❌ Мало данных: {len(df) if df is not None else 0} матчей")
        return False, issues
    
    required_cols = ['home_team', 'away_team', 'home_goals', 'away_goals', 'date']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        issues.append(f"❌ Отсутствуют колонки: {', '.join(missing_cols)}")
        return False, issues
    
    return len([i for i in issues if i.startswith('❌')]) == 0, issues

# ==================== ЗАГРУЗКА ДАННЫХ ====================
def load_matches_data(data_path: str) -> Optional[pd.DataFrame]:
    logger.info(f"📥 Загрузка данных из {data_path}")
    if not os.path.exists(data_path):
        logger.error(f"❌ Файл не найден: {data_path}")
        return None
    
    encodings = ['utf-8', 'cp1252', 'latin1', 'cp1251', 'utf-8-sig']
    df = None
    
    for enc in encodings:
        try:
            with open(data_path, 'r', encoding=enc) as f:
                first_lines = [f.readline() for _ in range(5)]
            skip_rows = sum(1 for line in first_lines if line.strip().startswith('#') or line.strip() == '')
            
            df = pd.read_csv(data_path, encoding=enc, skiprows=skip_rows, on_bad_lines='warn', engine='python')
            logger.info(f"✅ Файл прочитан (кодировка: {enc})")
            break
        except Exception:
            continue
    
    if df is None:
        return None
    
    date_col = next((col for col in df.columns if 'date' in col.lower()), None)
    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce', dayfirst=True)
        df = df.rename(columns={date_col: 'date'})
    else:
        return None
    
    df = df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)
    
    # 🔥 ПОЛНЫЙ МАППИНГ КОЛОНОК
    mappings = {
        'HomeTeam': 'home_team', 'AwayTeam': 'away_team',
        'FTHG': 'home_goals', 'FTAG': 'away_goals',
        'HG': 'home_goals', 'AG': 'away_goals',
        'HS': 'home_shots', 'AS': 'away_shots',
        'HST': 'home_shots_on_target', 'AST': 'away_shots_on_target',
        'HC': 'home_corners', 'AC': 'away_corners',
        'HY': 'home_yellows', 'AY': 'away_yellows',
        'HF': 'home_fouls', 'AF': 'away_fouls',
        'HTHG': 'ht_home_goals', 'HTAG': 'ht_away_goals',
        'HTR': 'ht_result'
    }
    
    column_mapping = {src: dst for src, dst in mappings.items() if src in df.columns and dst not in df.columns}
    if column_mapping:
        df = df.rename(columns=column_mapping)
    
    df['home_goals'] = safe_convert_goals(df.get('home_goals', 0))
    df['away_goals'] = safe_convert_goals(df.get('away_goals', 0))
    df = df[(df['home_goals'] <= 15) & (df['away_goals'] <= 15)]
    
    df = calculate_rest_days(df)
    logger.info(f"✅ Загружено {len(df)} матчей")
    return df

def calculate_rest_days(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values('date').copy()
    df['home_rest_days'] = 7
    df['away_rest_days'] = 7
    
    all_teams = set(df['home_team'].dropna()) | set(df['away_team'].dropna())
    for team in all_teams:
        team_matches = df[(df['home_team'] == team) | (df['away_team'] == team)].sort_values('date')
        if len(team_matches) < 2:
            continue
        
        prev_date = None
        for idx in team_matches.index:
            if prev_date is not None:
                rest_days = (team_matches.loc[idx, 'date'] - prev_date).days
                if team_matches.loc[idx, 'home_team'] == team:
                    df.loc[idx, 'home_rest_days'] = rest_days
                else:
                    df.loc[idx, 'away_rest_days'] = rest_days
            prev_date = team_matches.loc[idx, 'date']
    return df

def find_similar_team(team_name: str, all_teams: List[str], threshold: float = 0.65) -> Optional[str]:
    if not all_teams or not team_name:
        return None
    if team_name.lower() in [t.lower() for t in all_teams]:
        return next(t for t in all_teams if t.lower() == team_name.lower())
    matches = get_close_matches(team_name, list(all_teams), n=1, cutoff=threshold)
    return matches[0] if matches else None

# ==================== ELO РЕЙТИНГИ ====================
def calculate_elo_ratings_incremental(df: pd.DataFrame, k_factor: int = 32, initial_rating: int = 1500, home_advantage: int = 100) -> Tuple[pd.DataFrame, Dict]:
    if df is None or len(df) == 0:
        return df, {}
    
    all_teams = set(df['home_team'].dropna()) | set(df['away_team'].dropna())
    ratings = {team: initial_rating for team in all_teams}
    df_sorted = df.sort_values('date').copy()
    df_sorted['home_rating_pre'] = initial_rating
    df_sorted['away_rating_pre'] = initial_rating
    
    def expected_score(rating_a, rating_b):
        return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))
    
    def result_score(home_goals, away_goals):
        if home_goals > away_goals: return 1.0
        elif home_goals < away_goals: return 0.0
        return 0.5
    
    for idx in range(len(df_sorted)):
        row = df_sorted.iloc[idx]
        home, away = row['home_team'], row['away_team']
        if pd.isna(home) or pd.isna(away) or home not in ratings or away not in ratings:
            continue
        
        df_sorted.at[idx, 'home_rating_pre'] = ratings[home]
        df_sorted.at[idx, 'away_rating_pre'] = ratings[away]
        
        rating_home, rating_away = ratings[home], ratings[away]
        expected_home = expected_score(rating_home + home_advantage, rating_away)
        actual_home = result_score(row['home_goals'], row['away_goals'])
        
        ratings[home] = rating_home + k_factor * (actual_home - expected_home)
        ratings[away] = rating_away + k_factor * ((1 - actual_home) - (1 - expected_home))
    
    return df_sorted, {team: round(rating, 2) for team, rating in ratings.items()}

# ==================== МЕТРИКИ КОМАНД ====================
def calculate_team_metrics(df: pd.DataFrame, team_name: str, current_date: datetime, window_size: int = 10) -> Dict:
    if df is None or len(df) == 0 or not team_name:
        return {}
    
    team_mask = ((df['home_team'] == team_name) | (df['away_team'] == team_name))
    date_mask = (df['date'] < current_date)
    team_matches = df[team_mask & date_mask].sort_values('date', ascending=False).head(window_size)
    
    if len(team_matches) == 0:
        return {}
    
    metrics = {}
    home_mask = team_matches['home_team'] == team_name
    goals_scored = np.where(home_mask, team_matches['home_goals'].values, team_matches['away_goals'].values)
    goals_conceded = np.where(home_mask, team_matches['away_goals'].values, team_matches['home_goals'].values)
    
    metrics['avg_scored'] = float(np.mean(goals_scored)) if len(goals_scored) > 0 else 1.2
    metrics['avg_conceded'] = float(np.mean(goals_conceded)) if len(goals_conceded) > 0 else 1.2
    
    recent = team_matches.head(5)
    points = 0
    for _, match in recent.iterrows():
        if match['home_team'] == team_name:
            if match['home_goals'] > match['away_goals']: points += 3
            elif match['home_goals'] == match['away_goals']: points += 1
        else:
            if match['away_goals'] > match['home_goals']: points += 3
            elif match['away_goals'] == match['home_goals']: points += 1
    metrics['form_avg'] = points / min(5, len(recent)) if len(recent) > 0 else 1.5
    
    if 'home_rest_days' in df.columns:
        last_match = team_matches.iloc[0] if len(team_matches) > 0 else None
        if last_match is not None:
            metrics['rest_days'] = last_match.get('home_rest_days' if last_match['home_team'] == team_name else 'away_rest_days', 7)
        else:
            metrics['rest_days'] = 7
    else:
        metrics['rest_days'] = 7
    
    # Удары
    if 'home_shots' in team_matches.columns:
        shots = np.where(home_mask, team_matches['home_shots'].values, team_matches['away_shots'].values)
        metrics['avg_shots'] = float(np.mean(shots)) if len(shots) > 0 else 10.0
    
    # Удары в створ
    if 'home_shots_on_target' in team_matches.columns:
        sot = np.where(home_mask, team_matches['home_shots_on_target'].values, team_matches['away_shots_on_target'].values)
        metrics['avg_shots_on_target'] = float(np.mean(sot)) if len(sot) > 0 else 4.0
    
    # Фолы
    if 'home_fouls' in team_matches.columns:
        fouls = np.where(home_mask, team_matches['home_fouls'].values, team_matches['away_fouls'].values)
        metrics['avg_fouls'] = float(np.mean(fouls)) if len(fouls) > 0 else 12.0
        
    # 1-й тайм
    if 'ht_home_goals' in team_matches.columns:
        ht_goals = np.where(home_mask, team_matches['ht_home_goals'].values, team_matches['ht_away_goals'].values)
        metrics['avg_ht_goals'] = float(np.mean(ht_goals)) if len(ht_goals) > 0 else 0.5
        
        ht_btts = sum(1 for _, m in team_matches.iterrows() if m.get('ht_home_goals', 0) > 0 and m.get('ht_away_goals', 0) > 0)
        metrics['ht_btts_pct'] = ht_btts / len(team_matches) if len(team_matches) > 0 else 0.3

    metrics['avg_xG'] = float(metrics.get('avg_shots', 10.0) * 0.12)
    return metrics

def prepare_features_for_match(home_metrics: Dict, away_metrics: Dict, home_rating: float, away_rating: float) -> np.ndarray:
    features = [
        float(home_rating), float(away_rating), float(home_rating - away_rating + HOME_ADVANTAGE),
        float(home_metrics.get('avg_scored', 1.2)), float(away_metrics.get('avg_scored', 1.0)),
        float(home_metrics.get('avg_conceded', 1.0)), float(away_metrics.get('avg_conceded', 1.2)),
        float(home_metrics.get('avg_shots', 10.0)), float(away_metrics.get('avg_shots', 8.0)),
        float(home_metrics.get('avg_shots_on_target', 4.0)), float(away_metrics.get('avg_shots_on_target', 3.0)),
        float(home_metrics.get('form_avg', 1.8)), float(away_metrics.get('form_avg', 1.5)),
        float(home_metrics.get('avg_xG', 1.35)), float(away_metrics.get('avg_xG', 1.05)),
        float(home_metrics.get('rest_days', 7)), float(away_metrics.get('rest_days', 7)),
        float(home_metrics.get('rest_days', 7) - away_metrics.get('rest_days', 7)),
        # Новые фичи
        float(home_metrics.get('avg_fouls', 12.0)), float(away_metrics.get('avg_fouls', 12.0)),
        float(home_metrics.get('avg_ht_goals', 0.5)), float(away_metrics.get('avg_ht_goals', 0.5))
    ]
    return np.array(features).reshape(1, -1)

# ==================== ОБУЧЕНИЕ МОДЕЛЕЙ ====================
def train_models(df: pd.DataFrame) -> Optional[Dict]:
    logger.info("🚀 Начало обучения моделей...")
    is_valid, issues = validate_training_data(df)
    if not is_valid:
        for issue in issues: logger.error(issue)
        return None
    
    all_teams = list(set(df['home_team'].dropna()) | set(df['away_team'].dropna()))
    le_home, le_away = LabelEncoder(), LabelEncoder()
    le_home.fit(all_teams)
    le_away.fit(all_teams)
    
    feature_names = [
        'home_rating', 'away_rating', 'rating_diff', 'home_avg_scored', 'away_avg_scored',
        'home_avg_conceded', 'away_avg_conceded', 'home_avg_shots', 'away_avg_shots',
        'home_avg_shots_on_target', 'away_avg_shots_on_target', 'home_form', 'away_form',
        'home_xG', 'away_xG', 'home_rest_days', 'away_rest_days', 'rest_days_diff',
        'home_avg_fouls', 'away_avg_fouls', 'home_avg_ht_goals', 'away_avg_ht_goals'
    ]
    
    logger.info("⚡ Расчёт ELO рейтингов...")
    df_with_ratings, final_ratings = calculate_elo_ratings_incremental(df)
    
    X_list, y_result, y_total, y_btts = [], [], [], []
    current_date = datetime.now()
    
    for idx in range(len(df_with_ratings)):
        match = df_with_ratings.iloc[idx]
        home_metrics = calculate_team_metrics(df_with_ratings, match['home_team'], match['date'])
        away_metrics = calculate_team_metrics(df_with_ratings, match['away_team'], match['date'])
        
        X_list.append(prepare_features_for_match(home_metrics, away_metrics, match['home_rating_pre'], match['away_rating_pre'])[0])
        
        if match['home_goals'] > match['away_goals']: y_result.append(2)
        elif match['home_goals'] < match['away_goals']: y_result.append(0)
        else: y_result.append(1)
        
        y_total.append(1 if (match['home_goals'] + match['away_goals']) > 2.5 else 0)
        y_btts.append(1 if (match['home_goals'] > 0 and match['away_goals'] > 0) else 0)
    
    X = np.nan_to_num(np.array(X_list))
    y_result, y_total, y_btts = np.array(y_result), np.array(y_total), np.array(y_btts)
    
    train_size = int(len(X) * 0.8)
    scaler = StandardScaler()
    scaler.fit(X[:train_size])
    X_scaled = scaler.transform(X)
    
    models = {}
    tscv = TimeSeriesSplit(n_splits=5)
    
    # 1. Исход
    logger.info("🎯 Обучение модели исхода...")
    models['result'] = CalibratedClassifierCV(XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.08, objective='multi:softprob', num_class=3, random_state=42), method='isotonic', cv=tscv)
    models['result'].fit(X_scaled, y_result)
    
    # 2. Тотал 2.5
    logger.info("⚽ Обучение модели тотала...")
    models['total'] = CalibratedClassifierCV(XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.08, objective='binary:logistic', random_state=42), method='isotonic', cv=tscv)
    models['total'].fit(X_scaled, y_total)
    
    # 3. ОЗ
    logger.info("🔄 Обучение модели BTTS...")
    models['btts'] = CalibratedClassifierCV(XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.08, objective='binary:logistic', random_state=42), method='isotonic', cv=tscv)
    models['btts'].fit(X_scaled, y_btts)
    
    # 🔥 4. Исход 1-го тайма
    if 'ht_result' in df.columns:
        logger.info("⏱️ Обучение модели исхода 1-го тайма...")
        y_ht = df_with_ratings['ht_result'].map({'H': 2, 'D': 1, 'A': 0}).fillna(1).astype(int).values
        models['ht_result'] = CalibratedClassifierCV(XGBClassifier(n_estimators=80, max_depth=3, learning_rate=0.1, objective='multi:softprob', num_class=3, random_state=42), method='isotonic', cv=tscv)
        models['ht_result'].fit(X_scaled, y_ht)
    
    # 🔥 5. Тотал ударов
    if 'home_shots' in df.columns:
        logger.info("🎯 Обучение модели тотала ударов...")
        y_shots = ((df_with_ratings['home_shots'] + df_with_ratings['away_shots']) > 22.5).astype(int).values
        models['shots_over_22_5'] = CalibratedClassifierCV(XGBClassifier(n_estimators=80, max_depth=3, learning_rate=0.1, random_state=42), method='sigmoid', cv=tscv)
        models['shots_over_22_5'].fit(X_scaled, y_shots)
    
    # 🔥 6. Тотал ударов в створ
    if 'home_shots_on_target' in df.columns:
        logger.info("🎯 Обучение модели тотала ударов в створ...")
        y_sot = ((df_with_ratings['home_shots_on_target'] + df_with_ratings['away_shots_on_target']) > 8.5).astype(int).values
        models['sot_over_8_5'] = CalibratedClassifierCV(XGBClassifier(n_estimators=80, max_depth=3, learning_rate=0.1, random_state=42), method='sigmoid', cv=tscv)
        models['sot_over_8_5'].fit(X_scaled, y_sot)
    
    # 🔥 7. Тотал фолов
    if 'home_fouls' in df.columns:
        logger.info("🟨 Обучение модели тотала фолов...")
        y_fouls = ((df_with_ratings['home_fouls'] + df_with_ratings['away_fouls']) > 23.5).astype(int).values
        models['fouls_over_23_5'] = CalibratedClassifierCV(XGBClassifier(n_estimators=80, max_depth=3, learning_rate=0.1, random_state=42), method='sigmoid', cv=tscv)
        models['fouls_over_23_5'].fit(X_scaled, y_fouls)
    
    # 🔥 8. ОЗ в 1-м тайме
    if 'ht_home_goals' in df.columns:
        logger.info("🔄 Обучение модели BTTS 1-го тайма...")
        y_btts_ht = ((df_with_ratings['ht_home_goals'] > 0) & (df_with_ratings['ht_away_goals'] > 0)).astype(int).values
        models['btts_ht'] = CalibratedClassifierCV(XGBClassifier(n_estimators=80, max_depth=3, learning_rate=0.1, random_state=42), method='sigmoid', cv=tscv)
        models['btts_ht'].fit(X_scaled, y_btts_ht)

    logger.info(f"✅ Обучение завершено! Моделей: {len(models)}")
    return {
        'models': models, 'le_home': le_home, 'le_away': le_away, 'scaler': scaler,
        'feature_names': feature_names, 'n_matches': len(df), 'final_ratings': final_ratings,
        'training_date': datetime.now().isoformat(), 'version': '2.2'
    }

# ==================== ПРОГНОЗИРОВАНИЕ ====================
def get_trust_signal(prediction: dict) -> str:
    if "error" in prediction or 'result' not in prediction: return "❓ Нет данных"
    probs = prediction['result']
    max_prob = max(probs.values())
    trust_score = max_prob * 0.6 + 0.4 # Упрощенная формула для стабильности
    if trust_score >= 0.80: return "💎 АЛМАЗНЫЙ | Максимальная уверенность"
    elif trust_score >= 0.70: return "🥇 ЗОЛОТОЙ | Высокая уверенность"
    elif trust_score >= 0.60: return "🥈 СЕРЕБРЯНЫЙ | Средняя уверенность"
    return "🥉 БРОНЗОВЫЙ | Низкая уверенность"

def predict_match(team1: str, team2: str, model_data: dict, ratings_dict: dict = None, all_matches_df: pd.DataFrame = None, risk_level: str = RISK_MEDIUM) -> dict:
    try:
        if model_data is None: return {"error": "Модель не загружена"}
        
        models = model_data['models']
        le_home, le_away = model_data['le_home'], model_data['le_away']
        scaler, final_ratings = model_data['scaler'], model_data.get('final_ratings', {})
        all_teams = list(le_home.classes_)
        
        for team, var_name in [(team1, "team1"), (team2, "team2")]:
            if team not in all_teams:
                found = find_similar_team(team, all_teams, threshold=0.65)
                if found:
                    if var_name == "team1": team1 = found
                    else: team2 = found
                else:
                    return {"error": f"Команда не найдена: '{team}'"}
        
        current_date = datetime.now()
        home_metrics = calculate_team_metrics(all_matches_df, team1, current_date) if all_matches_df is not None else {}
        away_metrics = calculate_team_metrics(all_matches_df, team2, current_date) if all_matches_df is not None else {}
        
        home_rating = ratings_dict.get(team1, final_ratings.get(team1, DEFAULT_RATING)) if ratings_dict else final_ratings.get(team1, DEFAULT_RATING)
        away_rating = ratings_dict.get(team2, final_ratings.get(team2, DEFAULT_RATING)) if ratings_dict else final_ratings.get(team2, DEFAULT_RATING)
        
        features_scaled = scaler.transform(prepare_features_for_match(home_metrics, away_metrics, home_rating, away_rating))
        
        prediction = {'home_team': team1, 'away_team': team2, 'timestamp': datetime.now().isoformat(), 'risk_level': risk_level}
        
        # Основной исход
        if 'result' in models:
            probs = models['result'].predict_proba(features_scaled)[0]
            prediction['result'] = {HOME_WIN: float(probs[2]), DRAW: float(probs[1]), AWAY_WIN: float(probs[0])}
        
        # Тотал 2.5
        if 'total' in models:
            prob = models['total'].predict_proba(features_scaled)[0][1]
            prediction['total_goals'] = {OVER_25: float(prob), UNDER_25: float(1 - prob)}
        
        # ОЗ
        if 'btts' in models:
            prob = models['btts'].predict_proba(features_scaled)[0][1]
            prediction['both_scored'] = {BTTS_YES: float(prob), BTTS_NO: float(1 - prob)}
            
        # 🔥 НОВЫЕ РЫНКИ
        if 'ht_result' in models:
            probs = models['ht_result'].predict_proba(features_scaled)[0]
            prediction['first_half_result'] = {'Home Win': float(probs[2]), 'Draw': float(probs[1]), 'Away Win': float(probs[0])}
        
        if 'shots_over_22_5' in models:
            prob = models['shots_over_22_5'].predict_proba(features_scaled)[0][1]
            prediction['total_shots'] = {'Over 22.5': float(prob), 'Under 22.5': float(1 - prob)}
            
        if 'sot_over_8_5' in models:
            prob = models['sot_over_8_5'].predict_proba(features_scaled)[0][1]
            prediction['total_shots_on_target'] = {'Over 8.5': float(prob), 'Under 8.5': float(1 - prob)}
            
        if 'fouls_over_23_5' in models:
            prob = models['fouls_over_23_5'].predict_proba(features_scaled)[0][1]
            prediction['total_fouls'] = {'Over 23.5': float(prob), 'Under 23.5': float(1 - prob)}
            
        if 'btts_ht' in models:
            prob = models['btts_ht'].predict_proba(features_scaled)[0][1]
            prediction['btts_first_half'] = {'Yes': float(prob), 'No': float(1 - prob)}
            
        # Индивидуальные тоталы
        prediction['individual_totals'] = {
            f'{team1} Over 1.5': round(min(0.85, home_metrics.get('avg_scored', 1.2) / 2.2), 3),
            f'{team1} Under 1.5': round(1 - min(0.85, home_metrics.get('avg_scored', 1.2) / 2.2), 3),
            f'{team2} Over 1.5': round(min(0.85, away_metrics.get('avg_scored', 1.0) / 2.2), 3),
            f'{team2} Under 1.5': round(1 - min(0.85, away_metrics.get('avg_scored', 1.0) / 2.2), 3)
        }
        
        # Рекомендация
        rec = []
        if 'result' in prediction:
            if prediction['result'][HOME_WIN] > 0.48: rec.append(f"🔴 Фаворит: {team1}")
            elif prediction['result'][AWAY_WIN] > 0.48: rec.append(f"🔵 Фаворит: {team2}")
        if 'total_goals' in prediction and prediction['total_goals'][OVER_25] > 0.65:
            rec.append("⚽ Ожидается ТБ 2.5")
            
        prediction['recommendation'] = "\n".join(rec) if rec else "📊 Тактически сложный матч"
        prediction['trust_signal'] = get_trust_signal(prediction)
        
        max_prob = max(prediction.get('result', {HOME_WIN: 0.33, DRAW: 0.34, AWAY_WIN: 0.33}).values())
        prediction['is_hot'] = max_prob > 0.65
        prediction['hot_confidence'] = round(max_prob * 100, 1)
        prediction['hot_bet'] = f"П1/П2 ({round(max_prob*100)}%)"
        
        return prediction
    except Exception as e:
        logger.error(f"❌ Ошибка в predict_match: {e}")
        return {"error": f"Внутренняя ошибка: {str(e)[:100]}"}

def save_model(model_data: dict, filepath: str) -> bool:
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        joblib.dump(model_data, filepath)
        logger.info(f"✅ Модель сохранена: {filepath}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения: {e}")
        return False

def load_model(filepath: str) -> Optional[dict]:
    if not os.path.exists(filepath): return None
    try:
        return joblib.load(filepath)
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки: {e}")
        return None

# ==================== СТАТИСТИКА ДЛЯ UI ====================
def calculate_team_statistics(df: pd.DataFrame, team_name: str, max_matches: int = 50, season_start_date: str = "2025-08-01") -> dict:
    if df is None or len(df) == 0 or not team_name: return {}
    
    if 'date' in df.columns and season_start_date:
        df = df[df['date'] >= pd.to_datetime(season_start_date)].copy()
    
    team_matches = df[(df['home_team'] == team_name) | (df['away_team'] == team_name)].sort_values('date', ascending=False).head(max_matches)
    if len(team_matches) == 0: return {}
    
    stats = {
        'matches_played': len(team_matches),
        'home_matches': len(team_matches[team_matches['home_team'] == team_name]),
        'away_matches': len(team_matches[team_matches['away_team'] == team_name]),
    }
    
    goals_for, goals_against = [], []
    for _, m in team_matches.iterrows():
        if m['home_team'] == team_name:
            goals_for.append(m.get('home_goals', 0)); goals_against.append(m.get('away_goals', 0))
        else:
            goals_for.append(m.get('away_goals', 0)); goals_against.append(m.get('home_goals', 0))
            
    stats['avg_goals_for'] = round(np.mean(goals_for), 2) if goals_for else 0
    stats['avg_goals_against'] = round(np.mean(goals_against), 2) if goals_against else 0
    stats['total_goals_avg'] = round(np.mean([a+b for a,b in zip(goals_for, goals_against)]), 2)
    
    totals = [a+b for a,b in zip(goals_for, goals_against)]
    stats['over_2_5_pct'] = round(sum(1 for t in totals if t > 2.5) / len(totals) * 100, 1) if totals else 0
    stats['over_3_5_pct'] = round(sum(1 for t in totals if t > 3.5) / len(totals) * 100, 1) if totals else 0
    stats['under_2_5_pct'] = round(100 - stats['over_2_5_pct'], 1)
    
    btts_yes = sum(1 for gf, ga in zip(goals_for, goals_against) if gf > 0 and ga > 0)
    stats['btts_yes_pct'] = round(btts_yes / len(totals) * 100, 1) if totals else 0
    stats['btts_no_pct'] = round(100 - stats['btts_yes_pct'], 1)
    
    # Угловые
    if 'home_corners' in df.columns:
        c_for, c_ag = [], []
        for _, m in team_matches.iterrows():
            if m['home_team'] == team_name: c_for.append(m.get('home_corners', 0)); c_ag.append(m.get('away_corners', 0))
            else: c_for.append(m.get('away_corners', 0)); c_ag.append(m.get('home_corners', 0))
        stats['avg_corners_for'] = round(np.mean(c_for), 1) if c_for else 0
        stats['total_corners_avg'] = round(np.mean([a+b for a,b in zip(c_for, c_ag)]), 1)
        ct = [a+b for a,b in zip(c_for, c_ag)]
        stats['corners_over_9_5_pct'] = round(sum(1 for c in ct if c > 9.5) / len(ct) * 100, 1) if ct else 0
        stats['corners_over_10_5_pct'] = round(sum(1 for c in ct if c > 10.5) / len(ct) * 100, 1) if ct else 0

    # Карточки
    if 'home_yellows' in df.columns:
        y_for, y_ag = [], []
        for _, m in team_matches.iterrows():
            if m['home_team'] == team_name: y_for.append(m.get('home_yellows', 0)); y_ag.append(m.get('away_yellows', 0))
            else: y_for.append(m.get('away_yellows', 0)); y_ag.append(m.get('home_yellows', 0))
        stats['avg_yellows_for'] = round(np.mean(y_for), 1) if y_for else 0
        stats['total_yellows_avg'] = round(np.mean([a+b for a,b in zip(y_for, y_ag)]), 1)
        yt = [a+b for a,b in zip(y_for, y_ag)]
        stats['yellows_over_3_5_pct'] = round(sum(1 for y in yt if y > 3.5) / len(yt) * 100, 1) if yt else 0
        stats['yellows_over_4_5_pct'] = round(sum(1 for y in yt if y > 4.5) / len(yt) * 100, 1) if yt else 0

    # 🔥 Удары
    if 'home_shots' in df.columns:
        s_for, s_ag = [], []
        for _, m in team_matches.iterrows():
            if m['home_team'] == team_name: s_for.append(m.get('home_shots', 0)); s_ag.append(m.get('away_shots', 0))
            else: s_for.append(m.get('away_shots', 0)); s_ag.append(m.get('home_shots', 0))
        stats['avg_shots_for'] = round(np.mean(s_for), 1) if s_for else 0
        stats['total_shots_avg'] = round(np.mean([a+b for a,b in zip(s_for, s_ag)]), 1)

    # 🔥 Удары в створ
    if 'home_shots_on_target' in df.columns:
        sot_for, sot_ag = [], []
        for _, m in team_matches.iterrows():
            if m['home_team'] == team_name: sot_for.append(m.get('home_shots_on_target', 0)); sot_ag.append(m.get('away_shots_on_target', 0))
            else: sot_for.append(m.get('away_shots_on_target', 0)); sot_ag.append(m.get('home_shots_on_target', 0))
        stats['avg_sot_for'] = round(np.mean(sot_for), 1) if sot_for else 0
        stats['total_sot_avg'] = round(np.mean([a+b for a,b in zip(sot_for, sot_ag)]), 1)

    # 🔥 Фолы
    if 'home_fouls' in df.columns:
        f_for, f_ag = [], []
        for _, m in team_matches.iterrows():
            if m['home_team'] == team_name: f_for.append(m.get('home_fouls', 0)); f_ag.append(m.get('away_fouls', 0))
            else: f_for.append(m.get('away_fouls', 0)); f_ag.append(m.get('home_fouls', 0))
        stats['avg_fouls_for'] = round(np.mean(f_for), 1) if f_for else 0
        stats['total_fouls_avg'] = round(np.mean([a+b for a,b in zip(f_for, f_ag)]), 1)

    # Форма
    recent = team_matches.head(5)
    points = 0
    for _, m in recent.iterrows():
        if m['home_team'] == team_name:
            if m['home_goals'] > m['away_goals']: points += 3
            elif m['home_goals'] == m['away_goals']: points += 1
        else:
            if m['away_goals'] > m['home_goals']: points += 3
            elif m['away_goals'] == m['home_goals']: points += 1
    stats['form_points'] = points
    stats['form_pct'] = round(points / 15 * 100, 1)
    
    return stats

def get_league_rankings(df: pd.DataFrame, stat_type: str = 'corners', top_n: int = 3, season_start_date: str = "2025-08-01") -> list:
    if 'date' in df.columns and season_start_date:
        df = df[df['date'] >= pd.to_datetime(season_start_date)].copy()
    if df is None or len(df) == 0: return []
    
    teams = list(set(df['home_team'].dropna()) | set(df['away_team'].dropna()))
    rankings = []
    
    for team in teams:
        stats = calculate_team_statistics(df, team, max_matches=50, season_start_date=season_start_date)
        if not stats or stats.get('matches_played', 0) < 5: continue
        
        val_map = {
            'corners': (stats.get('avg_corners_for', 0), f"{stats.get('avg_corners_for', 0):.1f} угл./матч"),
            'total_corners': (stats.get('total_corners_avg', 0), f"{stats.get('total_corners_avg', 0):.1f} всего"),
            'corners_over_10_5': (stats.get('corners_over_10_5_pct', 0), f"{stats.get('corners_over_10_5_pct', 0):.1f}%"),
            'yellows': (stats.get('avg_yellows_for', 0), f"{stats.get('avg_yellows_for', 0):.1f} жёлтых/матч"),
            'total_yellows': (stats.get('total_yellows_avg', 0), f"{stats.get('total_yellows_avg', 0):.1f} всего"),
            'yellows_over_4_5': (stats.get('yellows_over_4_5_pct', 0), f"{stats.get('yellows_over_4_5_pct', 0):.1f}%"),
            'over_2_5': (stats.get('over_2_5_pct', 0), f"{stats.get('over_2_5_pct', 0):.1f}%"),
            'btts': (stats.get('btts_yes_pct', 0), f"{stats.get('btts_yes_pct', 0):.1f}%"),
            'form': (stats.get('form_pct', 0), f"{stats.get('form_pct', 0):.1f}%"),
            # 🔥 НОВЫЕ
            'shots': (stats.get('total_shots_avg', 0), f"{stats.get('total_shots_avg', 0):.1f} ударов"),
            'sot': (stats.get('total_sot_avg', 0), f"{stats.get('total_sot_avg', 0):.1f} в створ"),
            'fouls': (stats.get('total_fouls_avg', 0), f"{stats.get('total_fouls_avg', 0):.1f} фолов")
        }
        
        value, label = val_map.get(stat_type, (0, "N/A"))
        rankings.append({'team': team, 'value': value, 'label': label, 'matches': stats.get('matches_played', 0)})
    
    rankings.sort(key=lambda x: x['value'], reverse=True)
    return rankings[:top_n]