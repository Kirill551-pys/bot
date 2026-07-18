"""
МОДЕЛЬ ДЛЯ ПРОГНОЗИРОВАНИЯ ФУТБОЛЬНЫХ МАТЧЕЙ — ПРОФЕССИОНАЛЬНАЯ ВЕРСИЯ 2.1
✅ Исправлены синтаксические ошибки
✅ Добавлены дни отдыха команд
✅ Добавлены уровни риска
✅ Готово для VPS
"""
import pandas as pd
import numpy as np
import os
import joblib
import logging
from datetime import datetime, timedelta
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import TimeSeriesSplit
from xgboost import XGBClassifier
from difflib import get_close_matches
import warnings
import json
from typing import Dict, List, Tuple, Optional
warnings.filterwarnings('ignore')

# ==================== НАСТРОЙКИ ====================
DEFAULT_RATING = 1500
HOME_ADVANTAGE = 100
MIN_TRAINING_MATCHES = 100
K_FACTOR = 32

# Типы ставок
HOME_WIN = "Home Win"
DRAW = "Draw"
AWAY_WIN = "Away Win"
OVER_25 = "Over 2.5"
UNDER_25 = "Under 2.5"
BTTS_YES = "Yes"
BTTS_NO = "No"

# Уровни риска
RISK_CONSERVATIVE = "conservative"
RISK_MEDIUM = "medium"
RISK_AGGRESSIVE = "aggressive"

RISK_THRESHOLDS = {
    RISK_CONSERVATIVE: {'min_confidence': 0.75, 'min_gap': 0.30, 'min_trust_score': 0.80},
    RISK_MEDIUM: {'min_confidence': 0.68, 'min_gap': 0.22, 'min_trust_score': 0.70},
    RISK_AGGRESSIVE: {'min_confidence': 0.60, 'min_gap': 0.15, 'min_trust_score': 0.60}
}

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('bot_predictions.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def safe_convert_goals(col):
    if col.dtype == 'object':
        col = col.astype(str).str.strip()
        col = col.str.replace(',', '.').str.replace('–', '-').str.replace('—', '-').str.replace('−', '-')
        col = col.replace(['', '-', '–', '—', '−', 'nan', 'NaN', 'None', ' ', 'null', 'NULL'], '0')
    return pd.to_numeric(col, errors='coerce').fillna(0).astype(int)

def validate_training_data(df: pd.DataFrame) -> tuple:
    issues = []
    if df is None or len(df) < MIN_TRAINING_MATCHES:
        issues.append(f"❌ Мало данных: {len(df) if df is not None else 0} матчей (минимум {MIN_TRAINING_MATCHES})")
        return False, issues
    
    required_cols = ['home_team', 'away_team', 'home_goals', 'away_goals', 'date']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        issues.append(f"❌ Отсутствуют колонки: {', '.join(missing_cols)}")
        return False, issues
    
    home_wins = (df['home_goals'] > df['away_goals']).sum()
    away_wins = (df['home_goals'] < df['away_goals']).sum()
    draws = (df['home_goals'] == df['away_goals']).sum()
    total = len(df)
    
    if home_wins == 0 or away_wins == 0:
        issues.append(f"❌ Нет побед хозяев ({home_wins}) или гостей ({away_wins})")
    if draws / total > 0.7:
        issues.append(f"⚠️ Слишком много ничьих: {draws} из {total} ({draws/total*100:.1f}%)")
    
    df = df[(df['home_goals'] <= 15) & (df['away_goals'] <= 15)]
    unique_teams = len(set(df['home_team'].dropna()) | set(df['away_team'].dropna()))
    if unique_teams < 6:
        issues.append(f"⚠️ Слишком мало уникальных команд: {unique_teams}")
    
    is_valid = len([i for i in issues if i.startswith('❌')]) == 0
    return is_valid, issues

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
            
            df = pd.read_csv(data_path, encoding=enc, skiprows=skip_rows, 
                           on_bad_lines='warn', engine='python')
            logger.info(f"✅ Файл прочитан (кодировка: {enc})")
            break
        except Exception as e:
            logger.debug(f"   Кодировка {enc} не подошла: {str(e)[:100]}")
            continue
    
    if df is None:
        logger.error(f"❌ Не удалось прочитать файл")
        return None
    
    date_col = None
    for col in df.columns:
        if any(candidate.lower() in str(col).lower() 
               for candidate in ['Date', 'date', 'DATE', 'Datum', 'fecha', 'match_date']):
            date_col = col
            break
    
    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce', dayfirst=True)
        df = df.rename(columns={date_col: 'date'})
    else:
        logger.error("❌ Колонка с датой не найдена!")
        return None
    
    df = df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)
    
    column_mapping = {}
    mappings = {
        'HomeTeam': 'home_team', 'AwayTeam': 'away_team',
        'Home': 'home_team',        
        'Away': 'away_team', 
        'FTHG': 'home_goals', 'FTAG': 'away_goals',
        'HG': 'home_goals',         # ← 🔥 ДОБАВИТЬ: РПЛ формат
        'AG': 'away_goals',
        'HS': 'home_shots', 'AS': 'away_shots',
        'HST': 'home_shots_on_target', 'AST': 'away_shots_on_target',
        'HC': 'home_corners', 'AC': 'away_corners',
        'HY': 'home_yellows', 'AY': 'away_yellows'
    }
    for src, dst in mappings.items():
        if src in df.columns and dst not in df.columns:
            column_mapping[src] = dst
    
    if column_mapping:
        df = df.rename(columns=column_mapping)
    
    if 'home_goals' not in df.columns:
        df['home_goals'] = 0
    if 'away_goals' not in df.columns:
        df['away_goals'] = 0
    
    df['home_goals'] = safe_convert_goals(df['home_goals'])
    df['away_goals'] = safe_convert_goals(df['away_goals'])
    df = df[(df['home_goals'] <= 15) & (df['away_goals'] <= 15)]
    
    # 🔥 Расчёт дней отдыха
    df = calculate_rest_days(df)
    
    logger.info(f"✅ Загружено {len(df)} матчей")
    return df

def calculate_rest_days(df: pd.DataFrame) -> pd.DataFrame:
    """Расчёт дней отдыха между матчами"""
    df = df.sort_values('date').copy()
    df['home_rest_days'] = 7
    df['away_rest_days'] = 7
    
    all_teams = set(df['home_team'].dropna()) | set(df['away_team'].dropna())
    
    for team in all_teams:
        team_matches = df[
            (df['home_team'] == team) | (df['away_team'] == team)
        ].sort_values('date')
        
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
    
    logger.info("✅ Дни отдыха рассчитаны")
    return df

def find_similar_team(team_name: str, all_teams: List[str], threshold: float = 0.65) -> Optional[str]:
    if not all_teams or not team_name:
        return None
    
    for team in all_teams:
        if team.lower() == team_name.lower():
            return team
    
    matches = get_close_matches(team_name, list(all_teams), n=1, cutoff=threshold)
    return matches[0] if matches else None

# ==================== ELO РЕЙТИНГИ ====================
def calculate_elo_ratings_incremental(df: pd.DataFrame, k_factor: int = 32, 
                                      initial_rating: int = 1500, 
                                      home_advantage: int = 100) -> Tuple[pd.DataFrame, Dict]:
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
        if home_goals > away_goals:
            return 1.0
        elif home_goals < away_goals:
            return 0.0
        return 0.5
    
    for idx in range(len(df_sorted)):
        try:
            row = df_sorted.iloc[idx]
            home = row['home_team']
            away = row['away_team']
            
            if pd.isna(home) or pd.isna(away) or home not in ratings or away not in ratings:
                continue
            
            df_sorted.at[idx, 'home_rating_pre'] = ratings[home]
            df_sorted.at[idx, 'away_rating_pre'] = ratings[away]
            
            rating_home = ratings[home]
            rating_away = ratings[away]
            expected_home = expected_score(rating_home + home_advantage, rating_away)
            actual_home = result_score(row['home_goals'], row['away_goals'])
            
            ratings[home] = rating_home + k_factor * (actual_home - expected_home)
            ratings[away] = rating_away + k_factor * ((1 - actual_home) - (1 - expected_home))
        except Exception as e:
            logger.warning(f"⚠️ Ошибка в строке {idx} при расчёте ELO: {e}")
            continue
    
    return df_sorted, {team: round(rating, 2) for team, rating in ratings.items()}

# ==================== МЕТРИКИ КОМАНД ====================
def calculate_team_metrics(df: pd.DataFrame, team_name: str, 
                          current_date: datetime, window_size: int = 10) -> Dict:
    if df is None or len(df) == 0 or not team_name:
        return {}
    
    team_mask = ((df['home_team'] == team_name) | (df['away_team'] == team_name))
    date_mask = (df['date'] < current_date)
    team_matches = df[team_mask & date_mask].sort_values('date', ascending=False).head(window_size)
    
    if len(team_matches) == 0:
        return {}
    
    metrics = {}
    
    home_mask = team_matches['home_team'] == team_name
    goals_scored = np.where(home_mask, 
                           team_matches['home_goals'].values, 
                           team_matches['away_goals'].values)
    goals_conceded = np.where(home_mask, 
                             team_matches['away_goals'].values, 
                             team_matches['home_goals'].values)
    
    metrics['avg_scored'] = float(np.mean(goals_scored)) if len(goals_scored) > 0 else 1.2
    metrics['avg_conceded'] = float(np.mean(goals_conceded)) if len(goals_conceded) > 0 else 1.2
    
    recent = team_matches.head(5)
    points = 0
    for _, match in recent.iterrows():
        if match['home_team'] == team_name:
            if match['home_goals'] > match['away_goals']:
                points += 3
            elif match['home_goals'] == match['away_goals']:
                points += 1
        else:
            if match['away_goals'] > match['home_goals']:
                points += 3
            elif match['away_goals'] == match['home_goals']:
                points += 1
    
    metrics['form_avg'] = points / min(5, len(recent)) if len(recent) > 0 else 1.5
    
    if 'home_rest_days' in df.columns:
        last_match = team_matches.iloc[0] if len(team_matches) > 0 else None
        if last_match is not None:
            if last_match['home_team'] == team_name:
                metrics['rest_days'] = last_match.get('home_rest_days', 7)
            else:
                metrics['rest_days'] = last_match.get('away_rest_days', 7)
        else:
            metrics['rest_days'] = 7
    else:
        metrics['rest_days'] = 7
    
    if 'home_shots' in team_matches.columns:
        shots_for = np.where(home_mask, 
                            team_matches['home_shots'].values, 
                            team_matches['away_shots'].values)
        metrics['avg_shots'] = float(np.mean(shots_for)) if len(shots_for) > 0 else 10.0
    
    if 'home_shots_on_target' in team_matches.columns:
        shots_ot = np.where(home_mask, 
                           team_matches['home_shots_on_target'].values, 
                           team_matches['away_shots_on_target'].values)
        metrics['avg_shots_on_target'] = float(np.mean(shots_ot)) if len(shots_ot) > 0 else 4.0
    
    if 'home_corners' in team_matches.columns:
        corners = np.where(home_mask, 
                          team_matches['home_corners'].values, 
                          team_matches['away_corners'].values)
        metrics['avg_corners'] = float(np.mean(corners)) if len(corners) > 0 else 5.0
    
    metrics['avg_xG'] = float(metrics.get('avg_shots', 10.0) * 0.12)
    
    return metrics

def prepare_features_for_match(home_metrics: Dict, away_metrics: Dict, 
                               home_rating: float, away_rating: float) -> np.ndarray:
    features = [
        float(home_rating),
        float(away_rating),
        float(home_rating - away_rating + HOME_ADVANTAGE),
        float(home_metrics.get('avg_scored', 1.2)),
        float(away_metrics.get('avg_scored', 1.0)),
        float(home_metrics.get('avg_conceded', 1.0)),
        float(away_metrics.get('avg_conceded', 1.2)),
        float(home_metrics.get('avg_shots', 10.0)),
        float(away_metrics.get('avg_shots', 8.0)),
        float(home_metrics.get('avg_shots_on_target', 4.0)),
        float(away_metrics.get('avg_shots_on_target', 3.0)),
        float(home_metrics.get('avg_corners', 5.0)),
        float(away_metrics.get('avg_corners', 4.0)),
        float(home_metrics.get('form_avg', 1.8)),
        float(away_metrics.get('form_avg', 1.5)),
        float(home_metrics.get('avg_xG', 1.35)),
        float(away_metrics.get('avg_xG', 1.05)),
        float(home_metrics.get('rest_days', 7)),
        float(away_metrics.get('rest_days', 7)),
        float(home_metrics.get('rest_days', 7) - away_metrics.get('rest_days', 7))
    ]
    return np.array(features).reshape(1, -1)

# ==================== ОБУЧЕНИЕ МОДЕЛЕЙ ====================
def train_models(df: pd.DataFrame) -> Optional[Dict]:
    logger.info("🚀 Начало обучения моделей...")
    
    is_valid, issues = validate_training_data(df)
    if not is_valid:
        logger.error("❌ ДАННЫЕ НЕ ПРИГОДНЫ:")
        for issue in issues:
            logger.error(f"   {issue}")
        return None
    
    le_home = LabelEncoder()
    le_away = LabelEncoder()
    all_teams = list(set(df['home_team'].dropna()) | set(df['away_team'].dropna()))
    le_home.fit(all_teams)
    le_away.fit(all_teams)
    
    feature_names = [
        'home_rating', 'away_rating', 'rating_diff',
        'home_avg_scored', 'away_avg_scored',
        'home_avg_conceded', 'away_avg_conceded',
        'home_avg_shots', 'away_avg_shots',
        'home_avg_shots_on_target', 'away_avg_shots_on_target',
        'home_avg_corners', 'away_avg_corners',
        'home_form', 'away_form',
        'home_xG', 'away_xG',
        'home_rest_days', 'away_rest_days', 'rest_days_diff'
    ]
    
    logger.info("⚡ Расчёт ELO рейтингов...")
    df_with_ratings, final_ratings = calculate_elo_ratings_incremental(df)
    
    X_list = []
    y_result = []
    y_total = []
    y_btts = []
    
    current_date = datetime.now()
    for idx in range(len(df_with_ratings)):
        match = df_with_ratings.iloc[idx]
        home_rating = match['home_rating_pre']
        away_rating = match['away_rating_pre']
        
        home_metrics = calculate_team_metrics(df_with_ratings, match['home_team'], match['date'])
        away_metrics = calculate_team_metrics(df_with_ratings, match['away_team'], match['date'])
        
        features = prepare_features_for_match(home_metrics, away_metrics, home_rating, away_rating)
        X_list.append(features[0])
        
        if match['home_goals'] > match['away_goals']:
            y_result.append(2)
        elif match['home_goals'] < match['away_goals']:
            y_result.append(0)
        else:
            y_result.append(1)
        
        total = match['home_goals'] + match['away_goals']
        y_total.append(1 if total > 2.5 else 0)
        y_btts.append(1 if (match['home_goals'] > 0 and match['away_goals'] > 0) else 0)
    
    X = np.array(X_list)
    y_result = np.array(y_result)
    y_total = np.array(y_total)
    y_btts = np.array(y_btts)
    
    if np.isnan(X).any():
        X = np.nan_to_num(X)
    
    train_size = int(len(X) * 0.8)
    X_train = X[:train_size]
    
    scaler = StandardScaler()
    scaler.fit(X_train)
    X_scaled = scaler.transform(X)
    
    models = {}
    tscv = TimeSeriesSplit(n_splits=5)
    
    logger.info("🎯 Обучение модели исхода...")
    base_result = XGBClassifier(
        n_estimators=100, max_depth=4, learning_rate=0.08,
        objective='multi:softprob', num_class=3,
        eval_metric='mlogloss', random_state=42, use_label_encoder=False
    )
    models['result'] = CalibratedClassifierCV(base_result, method='isotonic', cv=tscv)
    models['result'].fit(X_scaled, y_result)
    
    logger.info("⚽ Обучение модели тотала...")
    base_total = XGBClassifier(
        n_estimators=100, max_depth=4, learning_rate=0.08,
        objective='binary:logistic', eval_metric='logloss',
        random_state=42, use_label_encoder=False
    )
    models['total'] = CalibratedClassifierCV(base_total, method='isotonic', cv=tscv)
    models['total'].fit(X_scaled, y_total)
    
    logger.info("🔄 Обучение модели BTTS...")
    base_btts = XGBClassifier(
        n_estimators=100, max_depth=4, learning_rate=0.08,
        objective='binary:logistic', eval_metric='logloss',
        random_state=42, use_label_encoder=False
    )
    models['btts'] = CalibratedClassifierCV(base_btts, method='isotonic', cv=tscv)
    models['btts'].fit(X_scaled, y_btts)
    
    if 'home_corners' in df.columns:
        logger.info("🎯 Обучение моделей угловых...")
        y_corners = ((df_with_ratings['home_corners'] + df_with_ratings['away_corners']) > 9.5).astype(int)
        base_corners = XGBClassifier(n_estimators=80, max_depth=3, learning_rate=0.1, random_state=42)
        models['corners_over_9_5'] = CalibratedClassifierCV(base_corners, method='sigmoid', cv=tscv)
        models['corners_over_9_5'].fit(X_scaled, y_corners)
    
    model_data = {
        'models': models,
        'le_home': le_home,
        'le_away': le_away,
        'scaler': scaler,
        'feature_names': feature_names,
        'n_matches': len(df),
        'final_ratings': final_ratings,
        'training_date': datetime.now().isoformat(),
        'version': '2.1'
    }
    
    logger.info(f"✅ Обучение завершено! Моделей: {len(models)}")
    return model_data

# ==================== ПРОГНОЗ С УРОВНЯМИ РИСКА ====================
def get_trust_signal(prediction: dict) -> str:
    if "error" in prediction:
        return "❓ Нет данных"
    
    probs = prediction.get('result', {})
    if not probs:
        return "❓ Нет данных"
    
    max_prob = max(probs.values())
    total_conf = prediction.get('total_goals', {}).get(OVER_25, 0.5)
    btts_conf = prediction.get('both_scored', {}).get(BTTS_YES, 0.5)
    
    trust_score = (max_prob * 0.6 + (abs(total_conf - 0.5) * 2) * 0.2 + (abs(btts_conf - 0.5) * 2) * 0.2)
    
    if trust_score >= 0.80:
        return "💎 АЛМАЗНЫЙ | Максимальная уверенность"
    elif trust_score >= 0.70:
        return "🥇 ЗОЛОТОЙ | Высокая уверенность"
    elif trust_score >= 0.60:
        return "🥈 СЕРЕБРЯНЫЙ | Средняя уверенность"
    else:
        return "🥉 БРОНЗОВЫЙ | Низкая уверенность"

def is_hot_prediction(prediction: dict, risk_level: str = RISK_MEDIUM) -> tuple:
    if "error" in prediction or 'result' not in prediction:
        return False, 0.0, None
    
    thresholds = RISK_THRESHOLDS.get(risk_level, RISK_THRESHOLDS[RISK_MEDIUM])
    
    probs = prediction['result']
    max_prob = max(probs[HOME_WIN], probs[DRAW], probs[AWAY_WIN])
    max_outcome = max(probs, key=probs.get)
    
    sorted_probs = sorted(probs.values(), reverse=True)
    gap = sorted_probs[0] - sorted_probs[1] if len(sorted_probs) > 1 else 0
    
    total_conf = prediction.get('total_goals', {}).get(OVER_25, 0.5)
    btts_conf = prediction.get('both_scored', {}).get(BTTS_YES, 0.5)
    
    is_hot = (
        max_prob >= thresholds['min_confidence'] and
        gap > thresholds['min_gap']
    )
    
    confidence_score = max_prob * 50 + gap * 30 + (0.2 if total_conf > 0.70 or total_conf < 0.30 else 0) * 10
    
    home_team = prediction.get('home_team', 'Хозяева')
    away_team = prediction.get('away_team', 'Гости')
    
    if max_outcome == HOME_WIN:
        bet = f"{home_team} Победа"
    elif max_outcome == AWAY_WIN:
        bet = f"{away_team} Победа"
    else:
        bet = "Ничья"
    
    if total_conf > 0.75:
        bet += " + ТБ 2.5"
    elif total_conf < 0.25:
        bet += " + ТМ 2.5"
    
    return is_hot, min(99.9, confidence_score), bet

def predict_match(team1: str, team2: str, model_data: dict, 
                  ratings_dict: dict = None, all_matches_df: pd.DataFrame = None,
                  risk_level: str = RISK_MEDIUM,
                  lineups: dict = None) -> dict:
    try:
        if model_data is None:
            return {"error": "Модель не загружена"}
        
        models = model_data['models']
        le_home = model_data['le_home']
        le_away = model_data['le_away']
        scaler = model_data['scaler']
        final_ratings = model_data.get('final_ratings', {})
        
        all_teams = list(le_home.classes_)
        
        for team, var_name in [(team1, "team1"), (team2, "team2")]:
            if team not in all_teams:
                found = find_similar_team(team, all_teams, threshold=0.65)
                if found:
                    logger.info(f"🔍 '{team}' → '{found}'")
                    if var_name == "team1":
                        team1 = found
                    else:
                        team2 = found
                else:
                    similar = get_close_matches(team, all_teams, n=3, cutoff=0.3)
                    suggestions = ", ".join(similar) if similar else "нет похожих команд"
                    # ✅ ИСПРАВЛЕНО: перенос строки убран
                    return {"error": f"Команда не найдена: '{team}'. Возможно: {suggestions}"}
        
        current_date = datetime.now()
        home_metrics = calculate_team_metrics(all_matches_df, team1, current_date) if all_matches_df is not None else {}
        away_metrics = calculate_team_metrics(all_matches_df, team2, current_date) if all_matches_df is not None else {}
        
        if lineups:
            home_metrics = adjust_metrics_by_lineups(home_metrics, lineups.get('home', []))
            away_metrics = adjust_metrics_by_lineups(away_metrics, lineups.get('away', []))
        
        home_rating = ratings_dict.get(team1, final_ratings.get(team1, DEFAULT_RATING)) if ratings_dict else final_ratings.get(team1, DEFAULT_RATING)
        away_rating = ratings_dict.get(team2, final_ratings.get(team2, DEFAULT_RATING)) if ratings_dict else final_ratings.get(team2, DEFAULT_RATING)
        
        features = prepare_features_for_match(home_metrics, away_metrics, home_rating, away_rating)
        features_scaled = scaler.transform(features)
        
        prediction = {
            'home_team': team1,
            'away_team': team2,
            'timestamp': datetime.now().isoformat(),
            'risk_level': risk_level
        }
        
        if 'result' in models:
            result_probs = models['result'].predict_proba(features_scaled)[0]
            if len(result_probs) == 3:
                prediction['result'] = {HOME_WIN: float(result_probs[2]), DRAW: float(result_probs[1]), AWAY_WIN: float(result_probs[0])}
            else:
                prediction['result'] = {HOME_WIN: 0.33, DRAW: 0.34, AWAY_WIN: 0.33}
        
        if 'total' in models:
            total_prob = models['total'].predict_proba(features_scaled)[0][1]
            prediction['total_goals'] = {OVER_25: float(total_prob), UNDER_25: float(1 - total_prob)}
        
        if 'btts' in models:
            btts_prob = models['btts'].predict_proba(features_scaled)[0][1]
            prediction['both_scored'] = {BTTS_YES: float(btts_prob), BTTS_NO: float(1 - btts_prob)}
        
        rec = []
        if 'result' in prediction:
            home_win = prediction['result'][HOME_WIN]
            away_win = prediction['result'][AWAY_WIN]
            if home_win > 0.48 and home_win > away_win + 0.18:
                rec.append(f"🔴 Фаворит: {team1}")
            elif away_win > 0.48 and away_win > home_win + 0.18:
                rec.append(f"🔵 Фаворит: {team2}")
        
        if 'total_goals' in prediction:
            total_prob = prediction['total_goals'][OVER_25]
            if total_prob > 0.68:
                rec.append("⚽ Ожидается ТБ 2.5")
            elif total_prob < 0.32:
                rec.append("🛡️ Ожидается ТМ 2.5")
        
        # ✅ ИСПРАВЛЕНО: перенос строки в join
        prediction['recommendation'] = "\n".join(rec) if rec else "📊 Тактически сложный матч"
        prediction['trust_signal'] = get_trust_signal(prediction)
        prediction['is_hot'], prediction['hot_confidence'], prediction['hot_bet'] = is_hot_prediction(prediction, risk_level)
        
        return prediction
    except Exception as e:
        logger.error(f"❌ Ошибка в predict_match: {e}")
        return {"error": f"Внутренняя ошибка: {str(e)[:100]}"}

def adjust_metrics_by_lineups(metrics: dict, lineup_players: list) -> dict:
    if not lineup_players:
        return metrics
    
    key_players = ['нападающий', 'форвард', 'striker', 'forward']
    has_key_player = any(any(kp in player.lower() for kp in key_players) for player in lineup_players)
    
    if not has_key_player:
        metrics['avg_xG'] = metrics.get('avg_xG', 1.35) * 0.85
    
    return metrics

# ==================== СОХРАНЕНИЕ/ЗАГРУЗКА ====================
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
    if not os.path.exists(filepath):
        logger.error(f"❌ Файл не найден: {filepath}")
        return None
    try:
        model_data = joblib.load(filepath)
        logger.info(f"✅ Модель загружена: {filepath}")
        return model_data
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки: {e}")
        return None

# ==================== КОНФИГУРАЦИЯ ====================
class BotConfig:
    def __init__(self):
        self.data_path = "data/matches.csv"
        self.model_path = "models/football_model_v2.joblib"
        self.log_path = "logs/bot_predictions.log"
        self.update_frequency_days = 7
        self.risk_level = RISK_MEDIUM
        self.min_confidence = 0.68
        self.enable_backtest = True
    
    def save_config(self, filepath: str = "config.json"):
        config = {
            'data_path': self.data_path,
            'model_path': self.model_path,
            'update_frequency_days': self.update_frequency_days,
            'risk_level': self.risk_level,
            'min_confidence': self.min_confidence
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    
    def load_config(self, filepath: str = "config.json"):
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self.data_path = config.get('data_path', self.data_path)
                self.model_path = config.get('model_path', self.model_path)
                self.update_frequency_days = config.get('update_frequency_days', self.update_frequency_days)
                self.risk_level = config.get('risk_level', self.risk_level)
# ==================== СТАТИСТИКА КОМАНД ДЛЯ ТОП-3 ====================

def calculate_team_statistics(df: pd.DataFrame, team_name: str, 
                              max_matches: int = 50,
                              season_start_date: str = "2025-08-01") -> dict:
    """
    Расширенная статистика команды для рейтингов
    Возвращает: угловые, карточки, тоталы, BTTS и др.
    """
    if df is None or len(df) == 0 or not team_name:
        return {}
    
    if 'date' in df.columns and season_start_date:
        start_date = pd.to_datetime(season_start_date)
        df = df[df['date'] >= start_date].copy()

    # Фильтруем матчи команды
    team_matches = df[
        (df['home_team'] == team_name) | (df['away_team'] == team_name)
    ].sort_values('date', ascending=False).head(max_matches)
    
    if len(team_matches) == 0:
        return {}
    
    stats = {
        'matches_played': len(team_matches),
        'home_matches': len(team_matches[team_matches['home_team'] == team_name]),
        'away_matches': len(team_matches[team_matches['away_team'] == team_name]),
    }
    
    # 🔹 ГОЛЫ
    goals_for, goals_against = [], []
    for _, match in team_matches.iterrows():
        if match['home_team'] == team_name:
            goals_for.append(match.get('home_goals', 0))
            goals_against.append(match.get('away_goals', 0))
        else:
            goals_for.append(match.get('away_goals', 0))
            goals_against.append(match.get('home_goals', 0))
    
    stats['avg_goals_for'] = round(np.mean(goals_for), 2) if goals_for else 0
    stats['avg_goals_against'] = round(np.mean(goals_against), 2) if goals_against else 0
    stats['total_goals_avg'] = round(np.mean([a+b for a,b in zip(goals_for, goals_against)]), 2)
    
    # 🔹 ТОТАЛЫ
    totals = [a+b for a,b in zip(goals_for, goals_against)]
    stats['over_2_5_pct'] = round(sum(1 for t in totals if t > 2.5) / len(totals) * 100, 1) if totals else 0
    stats['over_3_5_pct'] = round(sum(1 for t in totals if t > 3.5) / len(totals) * 100, 1) if totals else 0
    stats['under_2_5_pct'] = round(100 - stats['over_2_5_pct'], 1)
    
    # 🔹 ОБЕ ЗАБЬЮТ (BTTS)
    btts_yes = sum(1 for gf, ga in zip(goals_for, goals_against) if gf > 0 and ga > 0)
    stats['btts_yes_pct'] = round(btts_yes / len(totals) * 100, 1) if totals else 0
    stats['btts_no_pct'] = round(100 - stats['btts_yes_pct'], 1)
    
    # 🔹 УГЛОВЫЕ
    if 'home_corners' in df.columns and 'away_corners' in df.columns:
        corners_for, corners_against = [], []
        for _, match in team_matches.iterrows():
            if match['home_team'] == team_name:
                corners_for.append(match.get('home_corners', 0))
                corners_against.append(match.get('away_corners', 0))
            else:
                corners_for.append(match.get('away_corners', 0))
                corners_against.append(match.get('home_corners', 0))
        
        stats['avg_corners_for'] = round(np.mean(corners_for), 1) if corners_for else 0
        stats['avg_corners_against'] = round(np.mean(corners_against), 1) if corners_against else 0
        stats['total_corners_avg'] = round(np.mean([a+b for a,b in zip(corners_for, corners_against)]), 1)
        
        corner_totals = [a+b for a,b in zip(corners_for, corners_against)]
        stats['corners_over_9_5_pct'] = round(sum(1 for c in corner_totals if c > 9.5) / len(corner_totals) * 100, 1) if corner_totals else 0
        stats['corners_over_10_5_pct'] = round(sum(1 for c in corner_totals if c > 10.5) / len(corner_totals) * 100, 1) if corner_totals else 0
    
    # 🔹 ЖЁЛТЫЕ КАРТОЧКИ
    if 'home_yellows' in df.columns and 'away_yellows' in df.columns:
        yellows_for, yellows_against = [], []
        for _, match in team_matches.iterrows():
            if match['home_team'] == team_name:
                yellows_for.append(match.get('home_yellows', 0))
                yellows_against.append(match.get('away_yellows', 0))
            else:
                yellows_for.append(match.get('away_yellows', 0))
                yellows_against.append(match.get('home_yellows', 0))
        
        stats['avg_yellows_for'] = round(np.mean(yellows_for), 1) if yellows_for else 0
        stats['avg_yellows_against'] = round(np.mean(yellows_against), 1) if yellows_against else 0
        stats['total_yellows_avg'] = round(np.mean([a+b for a,b in zip(yellows_for, yellows_against)]), 1)
        
        yellow_totals = [a+b for a,b in zip(yellows_for, yellows_against)]
        stats['yellows_over_3_5_pct'] = round(sum(1 for y in yellow_totals if y > 3.5) / len(yellow_totals) * 100, 1) if yellow_totals else 0
        stats['yellows_over_4_5_pct'] = round(sum(1 for y in yellow_totals if y > 4.5) / len(yellow_totals) * 100, 1) if yellow_totals else 0
    
    # 🔹 ФОРМА (последние 5)
    recent = team_matches.head(5)
    points = 0
    for _, match in recent.iterrows():
        if match['home_team'] == team_name:
            if match['home_goals'] > match['away_goals']: points += 3
            elif match['home_goals'] == match['away_goals']: points += 1
        else:
            if match['away_goals'] > match['home_goals']: points += 3
            elif match['away_goals'] == match['home_goals']: points += 1
    stats['form_points'] = points
    stats['form_pct'] = round(points / 15 * 100, 1)
    
    return stats


def get_league_rankings(df: pd.DataFrame, stat_type: str = 'corners', 
                        top_n: int = 3, season_start_date: str = "2025-08-01") -> list:
    """
    Рейтинг ТОП-3 команд лиги по выбранному показателю
    stat_type: 'corners', 'yellows', 'over_2_5', 'btts', 'total_corners', 'total_yellows'
    """
    if 'date' in df.columns and season_start_date:
        start_date = pd.to_datetime(season_start_date)
        df = df[df['date'] >= start_date].copy()
    
    if df is None or len(df) == 0:
        return []
    
    teams = list(set(df['home_team'].dropna()) | set(df['away_team'].dropna()))
    rankings = []
    
    for team in teams:
        stats = calculate_team_statistics(df, team, max_matches= 50,
                                          season_start_date=season_start_date)
        if not stats or stats.get('matches_played', 0) < 5:  # Минимум 5 матчей
            continue
        
        if stat_type == 'corners':
            value = stats.get('avg_corners_for', 0)
            label = f"{value:.1f} угл./матч"
        elif stat_type == 'yellows':
            value = stats.get('avg_yellows_for', 0)
            label = f"{value:.1f} жёлтых/матч"
        elif stat_type == 'over_2_5':
            value = stats.get('over_2_5_pct', 0)
            label = f"{value:.1f}%"
        elif stat_type == 'btts':
            value = stats.get('btts_yes_pct', 0)
            label = f"{value:.1f}%"
        elif stat_type == 'total_corners':
            value = stats.get('total_corners_avg', 0)
            label = f"{value:.1f} всего"
        elif stat_type == 'total_yellows':
            value = stats.get('total_yellows_avg', 0)
            label = f"{value:.1f} всего"
        elif stat_type == 'over_3_5':  # ← НОВОЕ
            value = stats.get('over_3_5_pct', 0)
            label = f"{value:.1f}%"
            
        elif stat_type == 'corners_over_10_5':  # ← НОВОЕ
            value = stats.get('corners_over_10_5_pct', 0)
            label = f"{value:.1f}%"
            
        elif stat_type == 'yellows_over_4_5':  # ← НОВОЕ
            value = stats.get('yellows_over_4_5_pct', 0)
            label = f"{value:.1f}%"
            
        elif stat_type == 'form':  # ← НОВОЕ
            value = stats.get('form_pct', 0)
            label = f"{value:.1f}%"
        else:
            value = 0
            label = "N/A"
        
        rankings.append({
            'team': team, 
            'value': value, 
            'label': label,
            'matches': stats.get('matches_played', 0)
        })
    
    # Сортируем по убыванию и берём ТОП-3
    rankings.sort(key=lambda x: x['value'], reverse=True)
    return rankings[:top_n]

# ==================== ПРИМЕР ИСПОЛЬЗОВАНИЯ ====================
if __name__ == "__main__":
    config = BotConfig()
    df = load_matches_data(config.data_path)
    
    if df is not None:
        model_data = train_models(df)
        
        if model_data:
            save_model(model_data, config.model_path)
            
            prediction = predict_match("Зенит", "Спартак", model_data, 
                                      all_matches_df=df, risk_level=config.risk_level)
            print(f"\n🔮 Прогноз: {prediction.get('hot_bet', 'Нет прогноза')}")
            print(f"💎 Доверие: {prediction.get('trust_signal', 'Нет данных')}")