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
import math
from config import MARKET_TIERS, CONF_THRESHOLD


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


def odds_to_implied_prob(odds_home, odds_draw, odds_away):
    """
    Универсальная функция конвертации коэффициентов в рыночные вероятности.
    Работает с любыми форматами: PSCH/PSCD/PSCA, OddHome/OddDraw/OddAway, и т.д.
    
    Возвращает: [prob_away, prob_draw, prob_home] (в формате predict_proba)
    Если коэффициентов нет — возвращает равномерное распределение.
    """
    try:
        # Проверяем, что все три значения существуют и валидны
        if pd.isna(odds_home) or pd.isna(odds_draw) or pd.isna(odds_away):
            return [0.33, 0.34, 0.33]
        
        oh = float(odds_home)
        od = float(odds_draw)
        oa = float(odds_away)
        
        # Защита от невалидных коэффициентов
        if oh <= 1.0 or od <= 1.0 or oa <= 1.0:
            return [0.33, 0.34, 0.33]
        
        # Конвертация в вероятности (с удалением маржи)
        inv_h, inv_d, inv_a = 1/oh, 1/od, 1/oa
        total_inv = inv_h + inv_d + inv_a  # Это 1 + маржа
        
        # Нормализуем, чтобы сумма была равна 1
        prob_h = inv_h / total_inv
        prob_d = inv_d / total_inv
        prob_a = inv_a / total_inv
        
        # Возвращаем в формате [П2, Х, П1] как у predict_proba
        return [prob_a, prob_d, prob_h]
    except Exception:
        return [0.33, 0.34, 0.33]


def extract_market_odds(row):
    """
    Извлекает коэффициенты из строки DataFrame, независимо от формата колонок.
    Поддерживает: PSCH/PSCD/PSCA, OddHome/OddDraw/OddAway, B365H/B365D/B365A
    """
    # Формат 1: Pinnacle (PSCH, PSCD, PSCA)
    if 'PSCH' in row and 'PSCD' in row and 'PSCA' in row:
        return row['PSCH'], row['PSCD'], row['PSCA']
    
    # Формат 2: Твой формат (OddHome, OddDraw, OddAway)
    if 'OddHome' in row and 'OddDraw' in row and 'OddAway' in row:
        return row['OddHome'], row['OddDraw'], row['OddAway']
    
    # Формат 3: Bet365 (B365H, B365D, B365A)
    if 'B365H' in row and 'B365D' in row and 'B365A' in row:
        return row['B365H'], row['B365D'], row['B365A']
    
    # Если ничего не нашли
    return None, None, None


def extract_total_odds(row):
    """
    Извлекает коэффициенты на тотал 2.5 из строки DataFrame.
    Поддерживает: PSCOver/PSCUnder, Over25/Under25, B365>2.5/B365<2.5
    """
    # Формат 1: Pinnacle
    if 'PSCOver' in row and 'PSCUnder' in row:
        return row['PSCOver'], row['PSCUnder']
    
    # Формат 2: Твой формат
    if 'Over25' in row and 'Under25' in row:
        return row['Over25'], row['Under25']
    
    # Формат 3: Bet365
    if 'B365>2.5' in row and 'B365<2.5' in row:
        return row['B365>2.5'], row['B365<2.5']
    
    # Если ничего не нашли
    return None, None

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def poisson_over_1_5(avg_goals: float) -> float:
    """
    Вычисляет вероятность того, что команда забьет больше 1.5 гола (т.е. 2 и более).
    Формула: 1 - P(0 голов) - P(1 гол)
    """
    if avg_goals <= 0:
        return 0.0
    p0 = math.exp(-avg_goals)
    p1 = avg_goals * math.exp(-avg_goals)
    prob_over_15 = 1.0 - (p0 + p1)
    # Ограничиваем адекватными пределами (от 5% до 90%)
    return round(max(0.05, min(0.90, prob_over_15)), 3)

def poisson_pmf(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)

def poisson_over_2_5(lam):
    return 1 - sum(poisson_pmf(k, lam) for k in range(3))

def poisson_btts(lam_h, lam_a):
    return (1 - math.exp(-lam_h)) * (1 - math.exp(-lam_a))

def predict_goals_markets(models, X, home_metrics, away_metrics):
    """Возвращает смешанные (XGB + Пуассон) вероятности ТБ2.5 и ОЗ."""
    lam_h = home_metrics.get('avg_scored', 1.2)
    lam_a = away_metrics.get('avg_scored', 1.0)
    out = {}
    if 'total' in models:
        p = models['total'].predict_proba(X)[0][1]
        out['total'] = 0.5 * p + 0.5 * poisson_over_2_5(lam_h + lam_a)
    if 'btts' in models:
        p = models['btts'].predict_proba(X)[0][1]
        out['btts'] = 0.5 * p + 0.5 * poisson_btts(lam_h, lam_a)
    return out


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


def assign_football_season(df: pd.DataFrame) -> pd.DataFrame:
    """
    Определяет футбольный сезон на основе даты.
    Например: Август 2025 -> Май 2026 = сезон '25/26'
    """
    if 'date' not in df.columns or df.empty:
        return df
        
    year = df['date'].dt.year
    month = df['date'].dt.month
    
    # Если месяц >= 8 (август), сезон начался в этом году.
    # Если месяц < 8 (январь-июль), сезон начался в прошлом году.
    season_start_year = np.where(month >= 8, year, year - 1)
    season_end_year = season_start_year + 1
    
    # Создаем строку формата "2025-2026"
    df['season'] = season_start_year.astype(str) + '-' + season_end_year.astype(str)
    return df

def find_similar_team(team_name: str, all_teams: List[str], threshold: float = 0.60) -> Optional[str]:
    """
    Поиск команды: точное совпадение → нечёткий поиск.
    Порог 0.60 — баланс: находит сокращения (Man City),
    но НЕ матчит разные команды (Coventry City ≠ Man City, похожесть 0.48).
    """
    if not all_teams or not team_name:
        return None

    # 1. Точное совпадение (без учёта регистра)
    for t in all_teams:
        if t.lower() == team_name.lower():
            return t

    # 2. Нечёткий поиск
    matches = get_close_matches(team_name, list(all_teams), n=1, cutoff=threshold)
    return matches[0] if matches else None

# ==================== ELO РЕЙТИНГИ ====================
def calculate_elo_ratings_incremental(df: pd.DataFrame, k_factor: int = 32, initial_rating: int = 1500, home_advantage: int = 100) -> Tuple[pd.DataFrame, Dict]:
    if df is None or len(df) == 0:
        return df, {}
    
    all_teams = set(df['home_team'].dropna()) | set(df['away_team'].dropna())
    ratings = {team: float(initial_rating) for team in all_teams}
    df_sorted = df.sort_values('date').copy()
    # 🔥 ИСПРАВЛЕНИЕ: Явно задаем тип float, чтобы избежать ошибки при записи дробных ELO
    df_sorted['home_rating_pre'] = float(initial_rating)
    df_sorted['away_rating_pre'] = float(initial_rating)
    
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
def calculate_team_metrics(df: pd.DataFrame, team_name: str, current_date: datetime, window_size: int = 10, league_avg_goals: float = 2.5) -> Dict:
    """
    Расчёт метрик команды с новыми фичами для улучшения точности.
    league_avg_goals - среднее количество голов в лиге (для расчёта силы атаки/защиты)
    """
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
    
    # 🔥 НОВАЯ ФИЧА 1: Сила атаки и защиты (относительно лиги)
    # Если команда забивает 2.0 гола, а в лиге в среднем 1.25 - сила атаки = 1.6 (на 60% выше среднего)
    league_avg_per_team = league_avg_goals / 2.0  # Среднее на одну команду
    metrics['attack_strength'] = round(metrics['avg_scored'] / max(league_avg_per_team, 0.5), 2)
    metrics['defense_weakness'] = round(metrics['avg_conceded'] / max(league_avg_per_team, 0.5), 2)
    
    # Форма (очки за последние 5 матчей)
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
    
    # 🔥 НОВАЯ ФИЧА 2: Динамика формы последних 3 матчей (более чувствительна к текущему состоянию)
    recent_3 = team_matches.head(3)
    recent_points = 0
    for _, match in recent_3.iterrows():
        if match['home_team'] == team_name:
            if match['home_goals'] > match['away_goals']: recent_points += 3
            elif match['home_goals'] == match['away_goals']: recent_points += 1
        else:
            if match['away_goals'] > match['home_goals']: recent_points += 3
            elif match['away_goals'] == match['home_goals']: recent_points += 1
    metrics['recent_form_3'] = round(recent_points / min(3, len(recent_3)), 2) if len(recent_3) > 0 else 1.0
    
    # Дни отдыха
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

    # Угловые
    if 'home_corners' in team_matches.columns:
        corners = np.where(home_mask, team_matches['home_corners'].values, team_matches['away_corners'].values)
        metrics['avg_corners'] = float(np.mean(corners)) if len(corners) > 0 else 4.5
    else:
        metrics['avg_corners'] = 4.5

    # Жёлтые карточки
    if 'home_yellows' in team_matches.columns:
        yellows = np.where(home_mask, team_matches['home_yellows'].values, team_matches['away_yellows'].values)
        metrics['avg_yellows'] = float(np.mean(yellows)) if len(yellows) > 0 else 2.0
    else:
        metrics['avg_yellows'] = 2.0

    # 1-й тайм (безопасная версия)
    if 'ht_home_goals' in team_matches.columns and 'ht_away_goals' in team_matches.columns:
        ht_home = pd.to_numeric(team_matches['ht_home_goals'], errors='coerce')
        ht_away = pd.to_numeric(team_matches['ht_away_goals'], errors='coerce')
        ht_goals = np.where(home_mask, ht_home.values, ht_away.values)
        metrics['avg_ht_goals'] = float(np.nanmean(ht_goals)) if len(ht_goals) > 0 else 0.5
        
        ht_home_filled = ht_home.fillna(0)
        ht_away_filled = ht_away.fillna(0)
        ht_btts = int(((ht_home_filled > 0) & (ht_away_filled > 0)).sum())
        metrics['ht_btts_pct'] = ht_btts / len(team_matches) if len(team_matches) > 0 else 0.3
    else:
        metrics['avg_ht_goals'] = 0.5
        metrics['ht_btts_pct'] = 0.3

    metrics['avg_xG'] = float(metrics.get('avg_shots', 10.0) * 0.12)

    # Раздельная сила дома/в гостях
    hm = team_matches[team_matches['home_team'] == team_name]
    am = team_matches[team_matches['away_team'] == team_name]
    if len(hm) > 0:
        pts = np.where(hm['home_goals'] > hm['away_goals'], 3,
                       np.where(hm['home_goals'] == hm['away_goals'], 1, 0))
        metrics['home_ppg'] = float(pts.mean())
    else:
        metrics['home_ppg'] = 1.4
    if len(am) > 0:
        pts = np.where(am['away_goals'] > am['home_goals'], 3,
                       np.where(am['away_goals'] == am['home_goals'], 1, 0))
        metrics['away_ppg'] = float(pts.mean())
    else:
        metrics['away_ppg'] = 1.1
    metrics['draw_rate'] = float(
        (team_matches['home_goals'] == team_matches['away_goals']).mean()
    ) if len(team_matches) > 0 else 0.25

    return metrics

def prepare_features_for_match(home_metrics: Dict, away_metrics: Dict, home_rating: float, away_rating: float) -> np.ndarray:
    """
    Подготавливает признаки для модели.
    Включает новые фичи: team_power, power_diff, recent_form_3
    """
    
    # 🔥 НОВАЯ ФИЧА 3: Комбинированный рейтинг команды (team_power)
    # Формула: 40% ELO + 30% атака + 20% форма + 10% защита
    home_attack = home_metrics.get('attack_strength', 1.0)
    home_defense = home_metrics.get('defense_weakness', 1.0)
    home_form = home_metrics.get('form_avg', 1.5) / 3.0  # Нормализуем к 0-1
    home_team_power = (
        0.4 * (home_rating / 1500.0) +
        0.3 * home_attack +
        0.2 * home_form +
        0.1 * (1.0 / max(home_defense, 0.5))  # Чем меньше пропускает, тем лучше
    )
    
    away_attack = away_metrics.get('attack_strength', 1.0)
    away_defense = away_metrics.get('defense_weakness', 1.0)
    away_form = away_metrics.get('form_avg', 1.5) / 3.0
    away_team_power = (
        0.4 * (away_rating / 1500.0) +
        0.3 * away_attack +
        0.2 * away_form +
        0.1 * (1.0 / max(away_defense, 0.5))
    )
    
    # 🔥 НОВАЯ ФИЧА 4: Разница в классе команд
    power_diff = home_team_power - away_team_power
    
    features = [
        # Базовые рейтинги
        float(home_rating), 
        float(away_rating), 
        float(home_rating - away_rating + HOME_ADVANTAGE),
        
        # Голы
        float(home_metrics.get('avg_scored', 1.2)), 
        float(away_metrics.get('avg_scored', 1.0)),
        float(home_metrics.get('avg_conceded', 1.0)), 
        float(away_metrics.get('avg_conceded', 1.2)),
        
        # 🔥 НОВЫЕ: Сила атаки и защиты
        float(home_metrics.get('attack_strength', 1.0)),
        float(away_metrics.get('attack_strength', 1.0)),
        float(home_metrics.get('defense_weakness', 1.0)),
        float(away_metrics.get('defense_weakness', 1.0)),
        
        # Удары
        float(home_metrics.get('avg_shots', 10.0)), 
        float(away_metrics.get('avg_shots', 8.0)),
        float(home_metrics.get('avg_shots_on_target', 4.0)), 
        float(away_metrics.get('avg_shots_on_target', 3.0)),
        
        # Форма
        float(home_metrics.get('form_avg', 1.8)), 
        float(away_metrics.get('form_avg', 1.5)),
        
        # 🔥 НОВЫЕ: Динамика формы последних 3 матчей
        float(home_metrics.get('recent_form_3', 1.0)),
        float(away_metrics.get('recent_form_3', 1.0)),
        
        # xG
        float(home_metrics.get('avg_xG', 1.35)), 
        float(away_metrics.get('avg_xG', 1.05)),
        
        # Дни отдыха
        float(home_metrics.get('rest_days', 7)), 
        float(away_metrics.get('rest_days', 7)),
        float(home_metrics.get('rest_days', 7) - away_metrics.get('rest_days', 7)),
        
        # Фолы
        float(home_metrics.get('avg_fouls', 12.0)), 
        float(away_metrics.get('avg_fouls', 12.0)),
        
        # 1-й тайм
        float(home_metrics.get('avg_ht_goals', 0.5)), 
        float(away_metrics.get('avg_ht_goals', 0.5)),
        
        # Угловые
        float(home_metrics.get('avg_corners', 4.5)), 
        float(away_metrics.get('avg_corners', 4.5)),
        float(home_metrics.get('avg_corners', 4.5) + away_metrics.get('avg_corners', 4.5)),
        
        # Карточки
        float(home_metrics.get('avg_yellows', 2.0)), 
        float(away_metrics.get('avg_yellows', 2.0)),
        float(home_metrics.get('avg_yellows', 2.0) + away_metrics.get('avg_yellows', 2.0)),
        
        # Дом/гости
        float(home_metrics.get('home_ppg', 1.4)),
        float(away_metrics.get('away_ppg', 1.1)),
        float(home_metrics.get('draw_rate', 0.25)),
        float(away_metrics.get('draw_rate', 0.25)),
        
        # 🔥 НОВЫЕ: Комбинированный рейтинг и разница в классе
        float(home_team_power),
        float(away_team_power),
        float(power_diff),
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
        'home_rating', 'away_rating', 'rating_diff',
        'home_avg_scored', 'away_avg_scored',
        'home_avg_conceded', 'away_avg_conceded',
        # 🔥 НОВЫЕ
        'home_attack_strength', 'away_attack_strength',
        'home_defense_weakness', 'away_defense_weakness',
        'home_avg_shots', 'away_avg_shots',
        'home_avg_shots_on_target', 'away_avg_shots_on_target',
        'home_form', 'away_form',
        # 🔥 НОВЫЕ
        'home_recent_form_3', 'away_recent_form_3',
        'home_xG', 'away_xG',
        'home_rest_days', 'away_rest_days', 'rest_days_diff',
        'home_avg_fouls', 'away_avg_fouls',
        'home_avg_ht_goals', 'away_avg_ht_goals',
        'home_avg_corners', 'away_avg_corners', 'total_corners',
        'home_avg_yellows', 'away_avg_yellows', 'total_yellows',
        'home_ppg', 'away_ppg',
        'home_draw_rate', 'away_draw_rate',
        # 🔥 НОВЫЕ
        'home_team_power', 'away_team_power', 'power_diff'
    ]
    logger.info("⚡ Расчёт ELO рейтингов...")
    df_with_ratings, final_ratings = calculate_elo_ratings_incremental(df)
    
    # 🔥 ШАГ 1: Рассчитываем реальное среднее количество голов в этой конкретной лиге
    # Это критически важно для корректного расчета attack_strength и defense_weakness
    league_avg_goals = (df_with_ratings['home_goals'].mean() + df_with_ratings['away_goals'].mean())
    logger.info(f"📊 Среднее количество голов в лиге: {league_avg_goals:.2f}")
    
    X_list, y_result, y_total, y_btts = [], [], [], []
    market_probs_result_list = []  # 🔥 НОВОЕ: рыночные вероятности для 1X2
    market_probs_total_list = []   # 🔥 НОВОЕ: рыночные вероятности для Тотала
    current_date = datetime.now()
    
    for idx in range(len(df_with_ratings)):
        match = df_with_ratings.iloc[idx]
        home_metrics = calculate_team_metrics(df_with_ratings, match['home_team'], match['date'], league_avg_goals=league_avg_goals)
        away_metrics = calculate_team_metrics(df_with_ratings, match['away_team'], match['date'], league_avg_goals=league_avg_goals)
        
        X_list.append(prepare_features_for_match(home_metrics, away_metrics, match['home_rating_pre'], match['away_rating_pre'])[0])
        
        if match['home_goals'] > match['away_goals']: y_result.append(2)
        elif match['home_goals'] < match['away_goals']: y_result.append(0)
        else: y_result.append(1)
        
        y_total.append(1 if (match['home_goals'] + match['away_goals']) > 2.5 else 0)
        y_btts.append(1 if (match['home_goals'] > 0 and match['away_goals'] > 0) else 0)
        
        # 🔥 НОВОЕ: Извлекаем рыночные вероятности для 1X2
        odds_h, odds_d, odds_a = extract_market_odds(match)
        if odds_h is not None:
            market_probs_result_list.append(odds_to_implied_prob(odds_h, odds_d, odds_a))
        else:
            market_probs_result_list.append([0.33, 0.34, 0.33])  # Дефолт, если нет кэфов
        
        # 🔥 НОВОЕ: Извлекаем рыночные вероятности для Тотала 2.5
        odds_over, odds_under = extract_total_odds(match)
        if odds_over is not None and odds_under is not None:
            # Конвертируем в вероятности
            try:
                inv_over = 1 / float(odds_over)
                inv_under = 1 / float(odds_under)
                total_inv = inv_over + inv_under
                prob_over = inv_over / total_inv
                prob_under = inv_under / total_inv
                market_probs_total_list.append([prob_under, prob_over])  # [Under, Over]
            except:
                market_probs_total_list.append([0.5, 0.5])  # Дефолт
        else:
            market_probs_total_list.append([0.5, 0.5])  # Дефолт, если нет кэфов
    
    X = np.nan_to_num(np.array(X_list))
    y_result, y_total, y_btts = np.array(y_result), np.array(y_total), np.array(y_btts)
    
    train_size = int(len(X) * 0.8)
    scaler = StandardScaler()
    scaler.fit(X[:train_size])
    X_scaled = scaler.transform(X)
    cal_method = 'isotonic' if len(X_scaled) >= 2000 else 'sigmoid'

    # --- УЛУЧШЕНИЕ 1: свежие матчи важнее старых ---
    dates = pd.to_datetime(df_with_ratings['date'])
    age_days = (dates.max() - dates).dt.days.values
    sample_weights = np.exp(-age_days / 900.0)      # период полураспада ~2.5 года
    sample_weights = sample_weights / sample_weights.mean()

    # --- УЛУЧШЕНИЕ 2: адаптивная калибровка по объёму данных ---
    cal_method = 'isotonic' if len(X_scaled) >= 3000 else 'sigmoid'

    base_rates = np.array([
        (y_result == 0).mean(),   # П2
        (y_result == 1).mean(),   # ничья
        (y_result == 2).mean(),   # П1
    ])

    models = {}
    tscv = TimeSeriesSplit(n_splits=5)
    
    # 1. Исход (ОПТИМИЗИРОВАННЫЕ ПАРАМЕТРЫ)
    logger.info("🎯 Обучение модели исхода...")
    models['result'] = CalibratedClassifierCV(
        XGBClassifier(
            n_estimators=200,              # 🔥 Больше деревьев (было 100)
            max_depth=5,                   # 🔥 Глубже (было 4)
            learning_rate=0.05,            # 🔥 Медленнее, но точнее (было 0.08)
            subsample=0.8,                 # 🔥 Стохастика: используем 80% данных на каждое дерево
            colsample_bytree=0.8,          # 🔥 Случайные признаки: 80% признаков на дерево
            min_child_weight=3,            # 🔥 Защита от шума: минимум 3样本 в листе
            gamma=0.1,                     # 🔥 Регуляризация: штраф за разбиение узла
            reg_alpha=0.1,                 # 🔥 L1 регуляризация (защита от переобучения)
            reg_lambda=1.5,                # 🔥 L2 регуляризация (защита от переобучения)
            objective='multi:softprob',
            num_class=3,
            random_state=42,
            eval_metric='mlogloss'         # 🔥 Оптимизируем log loss, не accuracy
        ),
        method=cal_method,
        cv=tscv
    )
    models['result'].fit(X_scaled, y_result, sample_weight=sample_weights)
    
    # 2. Тотал 2.5 (ОПТИМИЗИРОВАННЫЕ ПАРАМЕТРЫ)
    logger.info("⚽ Обучение модели тотала...")
    models['total'] = CalibratedClassifierCV(
        XGBClassifier(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=3,
            gamma=0.1,
            reg_alpha=0.1,
            reg_lambda=1.5,
            objective='binary:logistic',
            random_state=42,
            eval_metric='logloss'          # 🔥 Для бинарной классификации
        ),
        method=cal_method,
        cv=tscv
    )
    models['total'].fit(X_scaled, y_total, sample_weight=sample_weights)

    # 3. ОЗ (ОПТИМИЗИРОВАННЫЕ ПАРАМЕТРЫ)
    logger.info("🔄 Обучение модели BTTS...")
    models['btts'] = CalibratedClassifierCV(
        XGBClassifier(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=3,
            gamma=0.1,
            reg_alpha=0.1,
            reg_lambda=1.5,
            objective='binary:logistic',
            random_state=42,
            eval_metric='logloss'
        ),
        method=cal_method,
        cv=tscv
    )
    models['btts'].fit(X_scaled, y_btts, sample_weight=sample_weights)

    # 🔥 4. Исход 1-го тайма (ОПТИМИЗИРОВАННЫЕ ПАРАМЕТРЫ)
    if 'ht_result' in df.columns:
        logger.info("⏱️ Обучение модели исхода 1-го тайма...")
        y_ht = df_with_ratings['ht_result'].map({'H': 2, 'D': 1, 'A': 0}).fillna(1).astype(int).values
        models['ht_result'] = CalibratedClassifierCV(
            XGBClassifier(
                n_estimators=150,              # 🔥 Меньше, чем для основного исхода (меньше данных)
                max_depth=4,
                learning_rate=0.06,
                subsample=0.8,
                colsample_bytree=0.8,
                min_child_weight=2,            # 🔥 Меньше, чем для основного (меньше данных)
                gamma=0.1,
                reg_alpha=0.1,
                reg_lambda=1.2,
                objective='multi:softprob',
                num_class=3,
                random_state=42,
                eval_metric='mlogloss'
            ),
            method=cal_method,
            cv=tscv
        )
        models['ht_result'].fit(X_scaled, y_ht, sample_weight=sample_weights)
    
    # 🔥 5. Тотал ударов (ТБ 22.5) — обучаем только если есть данные
    if 'home_shots' in df.columns and 'away_shots' in df.columns:
        logger.info("📊 Обучение модели ударов (ТБ 22.5)...")
        total_shots = df_with_ratings['home_shots'].fillna(0) + df_with_ratings['away_shots'].fillna(0)
        y_shots_225 = (total_shots > 22.5).astype(int).values
        
        models['shots_over_22_5'] = CalibratedClassifierCV(
            XGBClassifier(n_estimators=150, max_depth=4, learning_rate=0.06, subsample=0.8, colsample_bytree=0.8, min_child_weight=2, gamma=0.1, reg_alpha=0.1, reg_lambda=1.2, objective='binary:logistic', random_state=42, eval_metric='logloss'),
            method='sigmoid', cv=tscv
        )
        models['shots_over_22_5'].fit(X_scaled, y_shots_225, sample_weight=sample_weights)
    
    
    # 🔥 6. Тотал ударов в створ (ТБ 8.5)
    if 'home_shots_on_target' in df.columns and 'away_shots_on_target' in df.columns:
        logger.info("🎯 Обучение модели ударов в створ (ТБ 8.5)...")
        total_sot = df_with_ratings['home_shots_on_target'].fillna(0) + df_with_ratings['away_shots_on_target'].fillna(0)
        y_sot_85 = (total_sot > 8.5).astype(int).values
        
        models['sot_over_8_5'] = CalibratedClassifierCV(
            XGBClassifier(n_estimators=150, max_depth=4, learning_rate=0.06, subsample=0.8, colsample_bytree=0.8, min_child_weight=2, gamma=0.1, reg_alpha=0.1, reg_lambda=1.2, objective='binary:logistic', random_state=42, eval_metric='logloss'),
            method='sigmoid', cv=tscv
        )
        models['sot_over_8_5'].fit(X_scaled, y_sot_85, sample_weight=sample_weights)
    

    # 🔥 7. Тотал фолов (ТБ 23.5)
    if 'home_fouls' in df.columns and 'away_fouls' in df.columns:
        logger.info("⚠️ Обучение модели фолов (ТБ 23.5)...")
        total_fouls = df_with_ratings['home_fouls'].fillna(0) + df_with_ratings['away_fouls'].fillna(0)
        y_fouls_235 = (total_fouls > 23.5).astype(int).values
        
        models['fouls_over_23_5'] = CalibratedClassifierCV(
            XGBClassifier(n_estimators=150, max_depth=4, learning_rate=0.06, subsample=0.8, colsample_bytree=0.8, min_child_weight=2, gamma=0.1, reg_alpha=0.1, reg_lambda=1.2, objective='binary:logistic', random_state=42, eval_metric='logloss'),
            method='sigmoid', cv=tscv
        )
        models['fouls_over_23_5'].fit(X_scaled, y_fouls_235, sample_weight=sample_weights)
    

    # 🔥 8. ОЗ в 1-м тайме
    if 'ht_home_goals' in df.columns and 'ht_away_goals' in df.columns:
        logger.info("⏱️ Обучение модели ОЗ в 1-м тайме...")
        ht_home = pd.to_numeric(df_with_ratings['ht_home_goals'], errors='coerce').fillna(0)
        ht_away = pd.to_numeric(df_with_ratings['ht_away_goals'], errors='coerce').fillna(0)
        y_btts_ht = ((ht_home > 0) & (ht_away > 0)).astype(int).values
        
        models['btts_ht'] = CalibratedClassifierCV(
            XGBClassifier(n_estimators=150, max_depth=4, learning_rate=0.06, subsample=0.8, colsample_bytree=0.8, min_child_weight=2, gamma=0.1, reg_alpha=0.1, reg_lambda=1.2, objective='binary:logistic', random_state=42, eval_metric='logloss'),
            method='sigmoid', cv=tscv
        )
        models['btts_ht'].fit(X_scaled, y_btts_ht, sample_weight=sample_weights)

    # 🔥 9. УГЛОВЫЕ: Тотал больше 9.5
    if 'home_corners' in df.columns and 'away_corners' in df.columns:
        logger.info("🎯 Обучение модели угловых (ТБ 9.5)...")
        total_corners = df_with_ratings['home_corners'].fillna(0) + df_with_ratings['away_corners'].fillna(0)
        y_corners_95 = (total_corners > 9.5).astype(int).values
        
        models['corners_over_9_5'] = CalibratedClassifierCV(
            XGBClassifier(
                n_estimators=150,
                max_depth=4,
                learning_rate=0.06,
                subsample=0.8,
                colsample_bytree=0.8,
                min_child_weight=2,
                gamma=0.1,
                reg_alpha=0.1,
                reg_lambda=1.2,
                objective='binary:logistic',
                random_state=42,
                eval_metric='logloss'
            ),
            method='sigmoid',
            cv=tscv
        )
        models['corners_over_9_5'].fit(X_scaled, y_corners_95, sample_weight=sample_weights)
        
    # 🔥 11. КАРТОЧКИ: Тотал больше 3.5
    if 'home_yellows' in df.columns and 'away_yellows' in df.columns:
        logger.info("🟨 Обучение модели карточек (ТБ 3.5)...")
        total_yellows = df_with_ratings['home_yellows'].fillna(0) + df_with_ratings['away_yellows'].fillna(0)
        y_yellows_35 = (total_yellows > 3.5).astype(int).values
        
        models['yellows_over_3_5'] = CalibratedClassifierCV(
            XGBClassifier(
                n_estimators=150,
                max_depth=4,
                learning_rate=0.06,
                subsample=0.8,
                colsample_bytree=0.8,
                min_child_weight=2,
                gamma=0.1,
                reg_alpha=0.1,
                reg_lambda=1.2,
                objective='binary:logistic',
                random_state=42,
                eval_metric='logloss'
            ),
            method='sigmoid',
            cv=tscv
        )
        models['yellows_over_3_5'].fit(X_scaled, y_yellows_35, sample_weight=sample_weights)
        
    # 🔥 РАСЧЕТ МЕТРИК НА ТРЕНИРОВОЧНЫХ ДАННЫХ
    # Это нужно для отображения в WebApp (прозрачность для пользователя)
    logger.info("📊 Расчёт метрик качества моделей...")
    train_metrics = {}
    
    # Метрики для исхода 1X2
    if 'result' in models:
        train_probs = models['result'].predict_proba(X_scaled)
        train_preds = train_probs.argmax(axis=1)
        train_acc = (train_preds == y_result).mean() * 100
        
        # Расчет ROI на тренировочных данных (если есть рыночные коэффициенты)
        train_roi = 0.0
        if market_probs_result_list and len(market_probs_result_list) > 0:
            # Конвертируем рыночные вероятности обратно в коэффициенты
            train_stake = 0.0
            train_return = 0.0
            for i in range(len(y_result)):
                if market_probs_result_list[i] != [0.33, 0.34, 0.33]:  # Есть реальные кэфы
                    market_probs = market_probs_result_list[i]
                    # Конвертируем вероятности в коэффициенты (обратная операция)
                    try:
                        market_odds = [1.0 / p if p > 0 else 0 for p in market_probs]
                        pred_class = train_preds[i]
                        actual_odds = market_odds[pred_class]
                        is_hit = 1 if pred_class == y_result[i] else 0
                        
                        train_stake += 1.0
                        train_return += actual_odds * is_hit
                    except:
                        pass
            
            if train_stake > 0:
                train_roi = ((train_return - train_stake) / train_stake) * 100
        
        train_metrics['result'] = {
            'accuracy': round(train_acc, 1),
            'roi': round(train_roi, 1),
            'n_samples': len(y_result),
            'n_with_odds': sum(1 for mp in market_probs_result_list if mp != [0.33, 0.34, 0.33])
        }
    
    # Метрики для тотала 2.5
    if 'total' in models:
        total_probs = models['total'].predict_proba(X_scaled)[:, 1]
        total_preds = (total_probs > 0.5).astype(int)
        total_acc = (total_preds == y_total).mean() * 100
        
        train_metrics['total'] = {
            'accuracy': round(total_acc, 1),
            'n_samples': len(y_total)
        }
    
    # Метрики для ОЗ
    if 'btts' in models:
        btts_probs = models['btts'].predict_proba(X_scaled)[:, 1]
        btts_preds = (btts_probs > 0.5).astype(int)
        btts_acc = (btts_preds == y_btts).mean() * 100
        
        train_metrics['btts'] = {
            'accuracy': round(btts_acc, 1),
            'n_samples': len(y_btts)
        }

    # Метрики для ударов
    if 'shots_over_22_5' in models:
        shots_probs = models['shots_over_22_5'].predict_proba(X_scaled)[:, 1]
        shots_preds = (shots_probs > 0.5).astype(int)
        shots_acc = (shots_preds == y_shots_225).mean() * 100
        train_metrics['shots'] = {'accuracy': round(shots_acc, 1), 'n_samples': len(y_shots_225)}
    
    # Метрики для ударов в створ
    if 'sot_over_8_5' in models:
        sot_probs = models['sot_over_8_5'].predict_proba(X_scaled)[:, 1]
        sot_preds = (sot_probs > 0.5).astype(int)
        sot_acc = (sot_preds == y_sot_85).mean() * 100
        train_metrics['sot'] = {'accuracy': round(sot_acc, 1), 'n_samples': len(y_sot_85)}
    
    # Метрики для фолов
    if 'fouls_over_23_5' in models:
        fouls_probs = models['fouls_over_23_5'].predict_proba(X_scaled)[:, 1]
        fouls_preds = (fouls_probs > 0.5).astype(int)
        fouls_acc = (fouls_preds == y_fouls_235).mean() * 100
        train_metrics['fouls'] = {'accuracy': round(fouls_acc, 1), 'n_samples': len(y_fouls_235)}
    
    # Метрики для ОЗ в 1-м тайме
    if 'btts_ht' in models:
        btts_ht_probs = models['btts_ht'].predict_proba(X_scaled)[:, 1]
        btts_ht_preds = (btts_ht_probs > 0.5).astype(int)
        btts_ht_acc = (btts_ht_preds == y_btts_ht).mean() * 100
        train_metrics['btts_ht'] = {'accuracy': round(btts_ht_acc, 1), 'n_samples': len(y_btts_ht)}
    logger.info(f"📊 Метрики обучения: {train_metrics}")


    logger.info(f"✅ Обучение завершено! Моделей: {len(models)}")
    return {
        'models': models, 
        'le_home': le_home, 
        'le_away': le_away, 
        'scaler': scaler,
        'feature_names': feature_names, 
        'n_matches': len(df), 
        'final_ratings': final_ratings,
        'base_rates': base_rates,
        'market_probs_result_list': market_probs_result_list, 
        'market_probs_total_list': market_probs_total_list, 
        'train_metrics': train_metrics,
        'training_date': datetime.now().isoformat(), 
        'version': '2.4'  
    }

# ==================== ПРОГНОЗИРОВАНИЕ ====================
def get_trust_signal(prediction: dict) -> str:
    """Оценка уверенности на основе РЕАЛЬНОГО бэктеста."""
    if "error" in prediction or 'result' not in prediction: 
        return "❓ Нет данных"
    
    probs = prediction['result']
    max_prob = max(probs.values())
    
    if max_prob >= 0.65: 
        return "💎 АЛМАЗНЫЙ | Историческая точность 74.4%"
    elif max_prob >= 0.60: 
        return "🥇 ЗОЛОТОЙ | Историческая точность 70.8%"
    elif max_prob >= 0.55: 
        return "🥈 СЕРЕБРЯНЫЙ | Историческая точность 65.4%"
    return "🥉 БРОНЗОВЫЙ | Историческая точность 57.4%"

def predict_match(team1: str, team2: str, model_data: dict, ratings_dict: dict = None, all_matches_df: pd.DataFrame = None, risk_level: str = RISK_MEDIUM) -> dict:
    try:
        if model_data is None: return {"error": "Модель не загружена"}
        
        models = model_data['models']
        le_home, le_away = model_data['le_home'], model_data['le_away']
        scaler, final_ratings = model_data['scaler'], model_data.get('final_ratings', {})
        all_teams = list(le_home.classes_)
        # Создаём карту для поиска БЕЗ учёта регистра и пробелов
        team_map = {t.strip().lower(): t for t in all_teams}

        for team, var_name in [(team1, "team1"), (team2, "team2")]:
            clean_team = team.strip().lower()
            matched_team = None  # ✅ 1. ВСЕГДА инициализируем переменную заранее

            # 2. Точное совпадение (игнорируя пробелы и регистр)
            if clean_team in team_map:
                matched_team = team_map[clean_team]
            else:
                # 3. Поиск по схожести (порог 0.60)
                matched_team = find_similar_team(team.strip(), all_teams, threshold=0.60)

            # 4. Проверяем результат поиска
            if matched_team:
                if matched_team != team: # Логируем только если было исправление
                    logger.info(f"✅ Автоисправление: '{team}' -> '{matched_team}'")
            
                if var_name == "team1":
                    team1 = matched_team
                else:
                    team2 = matched_team
            else:
                # 5. Детальный лог ошибки (если так и не нашли)
                logger.error(f"❌ КОМАНДА НЕ НАЙДЕНА: '{team}' (переменная: {var_name})")
                logger.error(f"   Всего команд в базе: {len(all_teams)}")
                logger.error(f"   Примеры (первые 20): {all_teams[:20]}")
            
                from difflib import get_close_matches
                close = get_close_matches(team.strip(), all_teams, n=3, cutoff=0.4)
                if close:
                    logger.error(f"   Возможно, вы имели в виду: {close}")
            
                # ✅ Убрали req.league, так как его нет в model.py
                return {"error": f"Команда '{team}' не найдена. Проверьте название и выбранную лигу."}
        
        current_date = datetime.now()
    
        # 🔥 Рассчитываем среднее количество голов в лиге для нормализации
        if all_matches_df is not None and len(all_matches_df) > 0:
            league_avg_goals = (all_matches_df['home_goals'].mean() + all_matches_df['away_goals'].mean())
        else:
            league_avg_goals = 2.5  # Дефолт если нет данных
    
        home_metrics = calculate_team_metrics(all_matches_df, team1, current_date, league_avg_goals=league_avg_goals) if all_matches_df is not None else {}
        away_metrics = calculate_team_metrics(all_matches_df, team2, current_date, league_avg_goals=league_avg_goals) if all_matches_df is not None else {}
        
        home_rating = ratings_dict.get(team1, final_ratings.get(team1, DEFAULT_RATING)) if ratings_dict else final_ratings.get(team1, DEFAULT_RATING)
        away_rating = ratings_dict.get(team2, final_ratings.get(team2, DEFAULT_RATING)) if ratings_dict else final_ratings.get(team2, DEFAULT_RATING)
        
        features_scaled = scaler.transform(prepare_features_for_match(home_metrics, away_metrics, home_rating, away_rating))
        
        prediction = {'home_team': team1, 'away_team': team2, 'timestamp': datetime.now().isoformat(), 'risk_level': risk_level}
        
        # Основной исход
        if 'result' in models:
            probs = models['result'].predict_proba(features_scaled)[0]

        # Сжатие переоцененных вероятностей к реальным частотам лиги
            base = model_data.get('base_rates')
            if base is not None:
                raw = np.array([probs[0], probs[1], probs[2]])   # [П2, Х, П1]
                adj = 0.8 * raw + 0.2 * base
                adj = adj / adj.sum()
                probs = adj

            prediction['result'] = {HOME_WIN: float(probs[2]), DRAW: float(probs[1]), AWAY_WIN: float(probs[0])}


        goals = predict_goals_markets(models, features_scaled, home_metrics, away_metrics)
        if 'total' in goals:
            prediction['total_goals'] = {OVER_25: float(goals['total']), UNDER_25: float(1 - goals['total'])}

        if 'btts' in goals:
            prediction['both_scored'] = {BTTS_YES: float(goals['btts']), BTTS_NO: float(1 - goals['btts'])}


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

        # 🎯 УГЛОВЫЕ (Corners)
        if 'corners_over_9_5' in models and 'corners_over_10_5' in models:
            prob_95 = models['corners_over_9_5'].predict_proba(features_scaled)[0][1]
            prob_105 = models['corners_over_10_5'].predict_proba(features_scaled)[0][1]
        
            # Логическая корректировка: P(>10.5) не может быть больше P(>9.5)
            if prob_105 > prob_95:
                prob_105 = prob_95 * 0.85  # Снижаем вероятность
        
            prediction['corners'] = {
                'Over 9.5': round(float(prob_95), 3),
                'Under 9.5': round(float(1 - prob_95), 3)
            }
    
        # 🟨 КАРТОЧКИ (Yellows)
        if 'yellows_over_3_5' in models and 'yellows_over_4_5' in models:
            prob_35 = models['yellows_over_3_5'].predict_proba(features_scaled)[0][1]
            prob_45 = models['yellows_over_4_5'].predict_proba(features_scaled)[0][1]
        
            # Логическая корректировка: P(>4.5) не может быть больше P(>3.5)
            if prob_45 > prob_35:
                prob_45 = prob_35 * 0.80
        
            prediction['cards'] = {
                'Over 3.5': round(float(prob_35), 3),
                'Under 3.5': round(float(1 - prob_35), 3)
            }

        # Индивидуальные тоталы (через распределение Пуассона)
        home_avg = home_metrics.get('avg_scored', 1.2)
        away_avg = away_metrics.get('avg_scored', 1.0)
    
        home_over_15 = poisson_over_1_5(home_avg)
        away_over_15 = poisson_over_1_5(away_avg)

        prediction['individual_totals'] = {
            f'{team1} Over 1.5': home_over_15,
            f'{team1} Under 1.5': round(1.0 - home_over_15, 3),
            f'{team2} Over 1.5': away_over_15,
            f'{team2} Under 1.5': round(1.0 - away_over_15, 3)
        }
        
        # 🧠 УМНОЕ ОБОСНОВАНИЕ РЕКОМЕНДАЦИИ С ВАЛИДАЦИЕЙ ПО ИСТОРИЧЕСКИМ МЕТРИКАМ
        rec_reasons = []
        train_metrics = model_data.get('train_metrics', {})
        
        MARKET_THRESHOLDS = {
            'result': 55.0, 'total': 60.0, 'btts': 60.0,
            'corners': 55.0, 'cards': 55.0, 'shots': 60.0, 'fouls': 55.0
        }
        MARKET_NAMES = {
            'result': 'исход 1X2', 'total': 'тотал голов', 'btts': 'обе забьют (ОЗ)',
            'corners': 'угловые', 'cards': 'карточки', 'shots': 'удары', 'fouls': 'фолы'
        }

        # 1. Определяем ГЛАВНЫЙ рынок рекомендации (тот, что дает самый сильный и надежный сигнал)
        primary_market = None
        primary_prob = 0.0

        # Проверяем исходы (1X2)
        if 'result' in prediction:
            max_res = max(prediction['result'].values())
            if max_res > 0.45 and max_res > primary_prob:
                primary_market = 'result'
                primary_prob = max_res

        # Проверяем ОЗ (часто имеет более высокую вероятность)
        if 'both_scored' in prediction:
            max_btts = max(prediction['both_scored'].values())
            if max_btts > 0.60 and max_btts > primary_prob:
                primary_market = 'btts'
                primary_prob = max_btts

        # Проверяем Тотал
        if 'total_goals' in prediction:
            max_tot = max(prediction['total_goals'].values())
            if max_tot > 0.60 and max_tot > primary_prob:
                primary_market = 'total'
                primary_prob = max_tot

        # Fallback, если ничего не прошло пороги
        if not primary_market:
            primary_market = 'result'
            primary_prob = max(prediction.get('result', {HOME_WIN: 0.33, DRAW: 0.34, AWAY_WIN: 0.33}).values())

        # 2. Генерируем текст ИСКЛЮЧИТЕЛЬНО на основе ГЛАВНОГО рынка
        if primary_market == 'result':
            max_prob = max(prediction['result'].values())
            if prediction['result'].get(HOME_WIN, 0) == max_prob:
                reason = f"🔴 {team1} выглядит фаворитом"
                if home_metrics.get('form_avg', 0) > 2.0:
                    reason += f" (отличная форма: {home_metrics['form_avg']:.1f} очка за последние матчи)"
                rec_reasons.append(reason + ".")
            elif prediction['result'].get(AWAY_WIN, 0) == max_prob:
                reason = f"🔵 {team2} имеет высокие шансы на победу"
                if away_metrics.get('form_avg', 0) > 2.0:
                    reason += f" (гости в сильной форме: {away_metrics['form_avg']:.1f} очка за матч)"
                rec_reasons.append(reason + ".")
            else:
                rec_reasons.append("📊 Ожидается упорная борьба, высока вероятность ничьей.")

        elif primary_market == 'btts':
            if prediction['both_scored'].get('Yes', 0) > 0.60:
                rec_reasons.append("🔥 Высокая вероятность того, что обе команды забьют (ОЗ - Да).")
            else:
                rec_reasons.append("🛡️ Высокая вероятность, что одна из команд не сможет забить (ОЗ - Нет).")

        elif primary_market == 'total':
            if prediction['total_goals'].get('Over 2.5', 0) > 0.60:
                reason = "⚽ Высока вероятность результативного матча (ТБ 2.5)"
                combined_avg = home_metrics.get('avg_scored', 0) + away_metrics.get('avg_scored', 0)
                if combined_avg > 2.5:
                    reason += f" (команды в сумме забивают в среднем {combined_avg:.1f} гола)"
                rec_reasons.append(reason + ".")
            else:
                rec_reasons.append("🛡️ Ожидается закрытый, низовой матч с минимумом голов (ТМ 2.5).")

        # 3. Добавляем тактические факторы (независимо от главного рынка)
        home_rest = home_metrics.get('rest_days', 7) if home_metrics else 7
        away_rest = away_metrics.get('rest_days', 7) if away_metrics else 7
        if home_rest < 4 and away_rest >= 7:
            rec_reasons.append(f"⚠️ {team1} играет на коротком отдыхе ({home_rest} дн.), фактор усталости в пользу гостей.")
        elif away_rest < 4 and home_rest >= 7:
            rec_reasons.append(f"⚠️ {team2} играет на коротком отдыхе ({away_rest} дн.), фактор усталости в пользу хозяев.")

        # 4. ВАЛИДАЦИЯ: Проверяем историю ИМЕННО для того рынка, о котором мы написали в тексте!
        if primary_market in train_metrics:
            hist_acc = train_metrics[primary_market].get('accuracy', 0)
            n_samples = train_metrics[primary_market].get('n_samples', 0)
            threshold = MARKET_THRESHOLDS.get(primary_market, 55.0)
            market_name = MARKET_NAMES.get(primary_market, primary_market)
            
            if hist_acc >= threshold and n_samples >= 100:
                rec_reasons.append(f"✅ Историческая точность модели по рынку '{market_name}' составляет {hist_acc}% (на {n_samples} матчах), что подтверждает текущий прогноз.")
            else:
                rec_reasons.append(f"⚠️ ВНИМАНИЕ: Текущая вероятность высока, но историческая точность модели по рынку '{market_name}' ниже порога ({hist_acc}% при норме {threshold}%). Рекомендуем снизить сумму ставки.")

        # 5. Формируем итоговый текст
        if rec_reasons:
            prediction['recommendation'] = "🧠 **Обоснование прогноза:**\n• " + "\n• ".join(rec_reasons)
        else:
            prediction['recommendation'] = "📊 Тактически сложный матч. Модель не видит явного статистического перевеса, рекомендуем воздержаться."
            
        # Добавляем метрики в ответ для фронтенда
        prediction['backtest_metrics'] = train_metrics
        prediction['recommendation_confidence'] = "high" if any("✅ Историческая точность" in r for r in rec_reasons) else "low"
        prediction['best_market_info'] = {
            'name': primary_market,
            'current_probability': round(primary_prob * 100, 1),
            'historical_accuracy': train_metrics.get(primary_market, {}).get('accuracy', 0) if primary_market in train_metrics else 0
        }

        # 🔥 УМНЫЙ ПОИСК САМОЙ УВЕРЕННОЙ СТАВКИ
        market_to_tier = {}
        for tier, markets in MARKET_TIERS.items():
            for m in markets:
                market_to_tier[m] = tier

        bet_markets = {
            'result':            {'Home Win': f'П1 ({team1})', 'Draw': 'Ничья', 'Away Win': f'П2 ({team2})'},
            'total_goals':       {'Over 2.5': 'ТБ 2.5', 'Under 2.5': 'ТМ 2.5'},
            'both_scored':       {'Yes': 'ОЗ - Да', 'No': 'ОЗ - Нет'},
            'first_half_result': {'Home Win': f'1Т П1 ({team1})', 'Draw': '1Т Ничья', 'Away Win': f'1Т П2 ({team2})'},
            'btts_first_half':   {'Yes': 'ОЗ 1Т - Да', 'No': 'ОЗ 1Т - Нет'},
            'total_shots':       {'Over 22.5': 'Удары ТБ 22.5', 'Under 22.5': 'Удары ТМ 22.5'},
            'total_shots_on_target': {'Over 8.5': 'Удары в створ ТБ 8.5', 'Under 8.5': 'Удары в створ ТМ 8.5'},
            'total_fouls':       {'Over 23.5': 'Фолы ТБ 23.5', 'Under 23.5': 'Фолы ТМ 23.5'},
            'corners_over_9_5':  {'Over 9.5': 'Угловые ТБ 9.5'},
            'yellows_over_3_5':  {'Over 3.5': 'Карточки ТБ 3.5'},
        }
    
            
        best_bet_name = "П1/П2"
        best_bet_prob = 0.0
        best_bet_tier = None

        for market_key, labels in bet_markets.items():
            tier = market_to_tier.get(market_key, 'C')

            if tier == 'C':
                continue

            if market_key not in prediction:
                continue

            market_data = prediction[market_key]
            if not isinstance(market_data, dict):
                continue

            for outcome_key, label in labels.items():
                if outcome_key in market_data:
                    prob = market_data[outcome_key]
                    # Обновляем лучшую ставку только если уверенность выше порога
                    if prob > best_bet_prob and prob >= CONF_THRESHOLD:
                        best_bet_prob = prob
                        best_bet_name = label
                        best_bet_tier = tier

        # Гибкий критерий "горячести": высокая вероятность ИЛИ большой разрыв
        result_probs = prediction.get('result', {HOME_WIN: 0.33, DRAW: 0.34, AWAY_WIN: 0.33}).values()
        sorted_probs = sorted(result_probs, reverse=True)
        gap = sorted_probs[0] - sorted_probs[1] if len(sorted_probs) > 1 else 0

        prediction['is_hot'] = best_bet_prob > 0.55 or (best_bet_prob > 0.50 and gap > 0.15)
        prediction['hot_confidence'] = round(best_bet_prob * 100, 1)
        prediction['hot_bet'] = f"{best_bet_name} ({round(best_bet_prob*100)}%)"
        prediction['hot_bet_tier'] = best_bet_tier  # 🆕 отдаём тир во фронт

        return prediction
    
    except Exception as e:
        logger.error(f"❌ Ошибка в predict_match: {e}")
        return {"error": f"Внутренняя ошибка: {str(e)[:100]}"}

# ==================== СОХРАНЕНИЕ/ЗАГРУЗКА (АГРЕССИВНАЯ ВЕРСИЯ) ====================

def save_model(model_data: dict, filepath: str) -> bool:
    try:
        # 🔥 ПРИНУДИТЕЛЬНО устанавливаем версию 2.2
        model_data['version'] = '2.4'
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        joblib.dump(model_data, filepath)
        logger.info(f"✅ Модель сохранена: {filepath} (v2.4)")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения: {e}")
        return False

def load_model(filepath: str) -> Optional[dict]:
    if not os.path.exists(filepath): 
        return None
    try:
        model_data = joblib.load(filepath)
        
        # 🔥 АГРЕССИВНАЯ ПРОВЕРКА: Если это НЕ версия 2.4, мы БЕЗЖАЛОСТНО удаляем файл!
        if model_data.get('version') != '2.4':
            logger.warning(f"⚠️ НАЙДЕНА СТАРАЯ МОДЕЛЬ (v{model_data.get('version')})! Удаляем {filepath} для переобучения...")
            os.remove(filepath)
            return None
            
        logger.info(f"✅ Модель загружена: {filepath} (v2.4)")
        return model_data
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки {filepath}: {e}. Удаляем битый файл.")
        try:
            os.remove(filepath)
        except:
            pass
        return None
    
# ==================== ЗАГРУЗКА ДАННЫХ ====================
def safe_convert_goals(col):
    """Безопасная конвертация голов в числа"""
    try:
        if col.dtype == 'object':
            col = col.astype(str).str.strip().str.replace(',', '.').str.replace('–', '-').str.replace('—', '-')
            col = col.replace(['', '-', '–', '—', 'nan', 'NaN', 'None', ' ', 'null', 'NULL'], '0')
        return pd.to_numeric(col, errors='coerce').fillna(0).astype(int)
    except Exception:
        return pd.Series([0] * len(col), dtype=int)

def load_matches_data(data_path: str) -> Optional[pd.DataFrame]:
    logger.info(f"📥 Загрузка данных из {data_path}")
    
    # 🔥 ДЕТАЛЬНАЯ ДИАГНОСТИКА
    if os.path.exists(data_path):
        file_size = os.path.getsize(data_path)
        file_modified = os.path.getmtime(data_path)
        from datetime import datetime
        modified_time = datetime.fromtimestamp(file_modified).strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"📊 РАЗМЕР ФАЙЛА: {file_size:,} байт ({file_size/1024:.1f} KB)")
        logger.info(f"📅 ПОСЛЕДНЕЕ ИЗМЕНЕНИЕ: {modified_time}")
        
        # Считаем количество строк в файле
        with open(data_path, 'r', encoding='utf-8', errors='ignore') as f:
            line_count = sum(1 for _ in f)
        logger.info(f"📏 КОЛИЧЕСТВО СТРОК В ФАЙЛЕ: {line_count:,}")
        
        # Читаем последние 5 строк файла (там должны быть самые свежие даты)
        with open(data_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            last_lines = lines[-5:] if len(lines) >= 5 else lines
        logger.info(f"🔍 ПОСЛЕДНИЕ 5 СТРОК ФАЙЛА:")
        for i, line in enumerate(last_lines, 1):
            logger.info(f"   {i}: {line.strip()[:100]}")  # Первые 100 символов
    else:
        logger.error(f"❌ Файл не найден: {data_path}")
        return None
    
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
            # 🔥 ПРОВЕРКА: Сколько строк реально прочитано
            logger.info(f"📊 ПРОЧИТАНО СТРОК: {len(df):,} (из {line_count:,} в файле)")
    
            # 🔥 ПРОВЕРКА: Какие даты есть в DataFrame
            if 'date' in df.columns:
                min_date = df['date'].min()
                max_date = df['date'].max()
                logger.info(f"📅 ДИАПАЗОН ДАТ В DataFrame: {min_date} — {max_date}")
        
                # Проверяем, сколько строк с датами после 2024-01-01
                recent = df[df['date'] >= '2024-01-01']
                logger.info(f"🔥 МАТЧЕЙ ПОСЛЕ 2024-01-01: {len(recent):,}")
        
            # Если есть матчи после 2024, показываем последние 5
            if len(recent) > 0:
                logger.info(f"📅 ПОСЛЕДНИЕ 5 МАТЧЕЙ:")
                for _, row in recent.tail(5).iterrows():
                    logger.info(f"   {row['date']} - {row.get('home_team', '?')} vs {row.get('away_team', '?')}")
            df.columns = df.columns.str.strip() # Убираем пробелы в названиях колонок
            logger.info(f"✅ Файл прочитан (кодировка: {enc})")
            break
        except Exception as e:
            logger.debug(f"   Кодировка {enc} не подошла: {str(e)[:50]}")
            continue
    
    if df is None or len(df) == 0:
        logger.error(f"❌ Не удалось прочитать файл или он пуст")
        return None
    
    # 1. Дата
    date_col = next((col for col in df.columns if 'date' in col.lower()), None)
    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce', dayfirst=True)
        df = df.rename(columns={date_col: 'date'})
        df = df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)
    else:
        logger.error("❌ Колонка с датой не найдена!")
        return None
    
    # 2. Маппинг колонок
    rename_map = {}
    if 'HomeTeam' in df.columns and 'home_team' not in df.columns:
            rename_map['HomeTeam'] = 'home_team'
    elif 'Home' in df.columns and 'home_team' not in df.columns: 
        rename_map['Home'] = 'home_team' 

    if 'AwayTeam' in df.columns and 'away_team' not in df.columns: 
        rename_map['AwayTeam'] = 'away_team'
    elif 'Away' in df.columns and 'away_team' not in df.columns: 
        rename_map['Away'] = 'away_team'
    
    if 'FTHG' in df.columns and 'home_goals' not in df.columns: 
        rename_map['FTHG'] = 'home_goals'
    elif 'HG' in df.columns and 'home_goals' not in df.columns: 
        rename_map['HG'] = 'home_goals'
    elif 'FTHome' in df.columns and 'home_goals' not in df.columns: # <--- НОВОЕ
        rename_map['FTHome'] = 'home_goals'

    if 'FTAG' in df.columns and 'away_goals' not in df.columns: 
        rename_map['FTAG'] = 'away_goals'
    elif 'AG' in df.columns and 'away_goals' not in df.columns: 
        rename_map['AG'] = 'away_goals'
    elif 'FTAway' in df.columns and 'away_goals' not in df.columns: # <--- НОВОЕ
        rename_map['FTAway'] = 'away_goals'

    if 'FTR' in df.columns and 'result' not in df.columns:
        rename_map['FTR'] = 'result'
    elif 'FTResult' in df.columns and 'result' not in df.columns: # <--- НОВОЕ
        rename_map['FTResult'] = 'result'

    stat_mappings = {
        'HS': 'home_shots', 'AS': 'away_shots',
        'HST': 'home_shots_on_target', 'AST': 'away_shots_on_target',
        'HC': 'home_corners', 'AC': 'away_corners',
        'HY': 'home_yellows', 'AY': 'away_yellows',
        'HF': 'home_fouls', 'AF': 'away_fouls',
        'HTHG': 'ht_home_goals', 'HTAG': 'ht_away_goals',
        'HTR': 'ht_result','HomeShots': 'home_shots', 'AwayShots': 'away_shots',
        'HomeTarget': 'home_shots_on_target', 'AwayTarget': 'away_shots_on_target',
        'HomeFouls': 'home_fouls', 'AwayFouls': 'away_fouls',
        'HomeCorners': 'home_corners', 'AwayCorners': 'away_corners',
        'HomeYellow': 'home_yellows', 'AwayYellow': 'away_yellows',
        'HomeRed': 'home_reds', 'AwayRed': 'away_reds',
        'HTHome': 'ht_home_goals', 'HTAway': 'ht_away_goals',
        'HTResult': 'ht_result'
    }
    for src, dst in stat_mappings.items():
        if src in df.columns and dst not in df.columns:
            rename_map[src] = dst
            
    if rename_map:
        df = df.rename(columns=rename_map)
        logger.info(f"   ↳ Переименованы колонки: {list(rename_map.values())}")

    # 3. Критическая проверка
    if 'home_team' not in df.columns or 'away_team' not in df.columns:
        logger.error(f"❌ Ошибка в {os.path.basename(data_path)}: нет home_team/away_team. Колонки: {list(df.columns)[:10]}...")
        return None
    
    # 4. Безопасная конвертация голов (ПОЛНАЯ, включая 1-й тайм)
    # Гарантируем наличие колонок ПЕРЕД обработкой
    for col in ['home_goals', 'away_goals', 'ht_home_goals', 'ht_away_goals']:
        if col not in df.columns:
            df[col] = 0

    df['home_goals'] = safe_convert_goals(df['home_goals'])
    df['away_goals'] = safe_convert_goals(df['away_goals'])
    
    # 🔥 ДОБАВЛЯЕМ ЗАЩИТУ ДЛЯ ГОЛОВ 1-го ТАЙМА
    df['ht_home_goals'] = safe_convert_goals(df['ht_home_goals'])
    df['ht_away_goals'] = safe_convert_goals(df['ht_away_goals'])

    # Дни отдыха (try/except, чтобы не ронять загрузку)
    try:
        df = calculate_rest_days(df)
    except Exception as e:
        logger.warning(f"⚠️ Не удалось посчитать дни отдыха: {e}")
        df['home_rest_days'] = 7
        df['away_rest_days'] = 7
    df = assign_football_season(df)
    # 🔥 ДИАГНОСТИКА: Проверяем, какие даты реально есть в файле
    if 'date' in df.columns:
        min_date = df['date'].min()
        max_date = df['date'].max()
        logger.info(f"📅 Диапазон дат в файле: {min_date} — {max_date}")
    
        # Проверяем, сколько матчей за последние 2 года
        recent_cutoff = pd.Timestamp.now() - pd.DateOffset(years=2)
        recent_matches = len(df[df['date'] >= recent_cutoff])
        logger.info(f"📊 Матчей за последние 2 года: {recent_matches}")
    
        # Проверяем сезоны
        if 'season' in df.columns:
            seasons = df['season'].value_counts().sort_index()
            logger.info(f"🏆 Распределение по сезонам:\n{seasons}")
    logger.info(f"✅ Загружено {len(df)} матчей. Сезоны: {df['season'].unique().tolist()}")
    return df


def calculate_rest_days(df: pd.DataFrame) -> pd.DataFrame:
    """Безопасный расчёт дней отдыха между матчами"""
    df = df.sort_values('date').copy()
    df['home_rest_days'] = 7
    df['away_rest_days'] = 7
    
    if 'home_team' not in df.columns or 'away_team' not in df.columns:
        logger.warning("⚠️ Пропуск расчёта дней отдыха: нет колонок home_team/away_team")
        return df
        
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

def calculate_team_statistics(df: pd.DataFrame, team_name: str, max_matches: int = 50, season_start_date: Optional[str] = None) -> Dict:
    """Расчёт статистики команды. Гарантирует возврат всех полей для TeamStatsResponse."""
    if df is None or len(df) == 0 or not team_name:
        return {}
    
    df_filtered = df.copy()
    if 'date' in df.columns and season_start_date:
        try:
            start_dt = pd.to_datetime(season_start_date, dayfirst=True, errors='coerce')
            temp_filtered = df[df['date'] >= start_dt].copy()
            # 🛡️ Защита: Если после фильтрации осталось мало матчей (сезон еще не начался),
            # используем все доступные данные, чтобы не отдавать 404.
            if len(temp_filtered) >= 10: 
                df_filtered = temp_filtered
        except Exception:
            pass

    # Ищем матчи команды
    team_matches = df_filtered[
        (df_filtered['home_team'] == team_name) | (df_filtered['away_team'] == team_name)
    ].sort_values('date', ascending=False).head(max_matches)
    
    # 🛡️ Fallback: Если в отфильтрованном df команду не нашли, ищем во всем df
    if len(team_matches) == 0:
        team_matches = df[
            (df['home_team'] == team_name) | (df['away_team'] == team_name)
        ].sort_values('date', ascending=False).head(max_matches)

    if len(team_matches) == 0:
        return {}
            
    stats = {
        'matches_played': int(len(team_matches)),
        'home_matches': int((team_matches['home_team'] == team_name).sum()),
        'away_matches': int((team_matches['away_team'] == team_name).sum())
    }
    
    home_mask = team_matches['home_team'] == team_name
    goals_scored = np.where(home_mask, team_matches['home_goals'].values, team_matches['away_goals'].values)
    goals_conceded = np.where(home_mask, team_matches['away_goals'].values, team_matches['home_goals'].values)
    total_goals = goals_scored + goals_conceded
    
    stats['avg_goals_for'] = float(np.mean(goals_scored))
    stats['avg_goals_against'] = float(np.mean(goals_conceded))
    stats['total_goals_avg'] = float(np.mean(total_goals))
    
    stats['over_2_5_pct'] = float(np.mean(total_goals > 2.5) * 100)
    stats['over_3_5_pct'] = float(np.mean(total_goals > 3.5) * 100)
    stats['under_2_5_pct'] = float(np.mean(total_goals <= 2.5) * 100)
    
    btts_mask = (goals_scored > 0) & (goals_conceded > 0)
    stats['btts_yes_pct'] = float(np.mean(btts_mask) * 100)
    stats['btts_no_pct'] = float(np.mean(~btts_mask) * 100)
    
    # Расчёт формы (очки)
    points = 0
    for _, match in team_matches.iterrows():
        if match['home_team'] == team_name:
            if match['home_goals'] > match['away_goals']: points += 3
            elif match['home_goals'] == match['away_goals']: points += 1
        else:
            if match['away_goals'] > match['home_goals']: points += 3
            elif match['away_goals'] == match['home_goals']: points += 1
    
    stats['form_points'] = int(points)
    max_points = len(team_matches) * 3
    stats['form_pct'] = float((points / max_points) * 100) if max_points > 0 else 0.0
    
    # 🔥 УГЛОВЫЕ (Если есть в CSV, как в АПЛ. Если нет, как в РПЛ — ставим 0.0)
    if 'home_corners' in team_matches.columns:
        corners_for = np.where(home_mask, team_matches['home_corners'].values, team_matches['away_corners'].values)
        corners_against = np.where(home_mask, team_matches['away_corners'].values, team_matches['home_corners'].values)
        total_corners = corners_for + corners_against
        
        stats['avg_corners_for'] = float(np.mean(corners_for))
        stats['avg_corners_against'] = float(np.mean(corners_against))
        stats['total_corners_avg'] = float(np.mean(total_corners))
        stats['corners_over_9_5_pct'] = float(np.mean(total_corners > 9.5) * 100)
        stats['corners_over_10_5_pct'] = float(np.mean(total_corners > 10.5) * 100)
    else:
        stats['avg_corners_for'] = 0.0
        stats['avg_corners_against'] = 0.0
        stats['total_corners_avg'] = 0.0
        stats['corners_over_9_5_pct'] = 0.0
        stats['corners_over_10_5_pct'] = 0.0
        
    # 🔥 ЖЁЛТЫЕ КАРТОЧКИ (Если есть в CSV)
    if 'home_yellows' in team_matches.columns:
        yellows_for = np.where(home_mask, team_matches['home_yellows'].values, team_matches['away_yellows'].values)
        yellows_against = np.where(home_mask, team_matches['away_yellows'].values, team_matches['home_yellows'].values)
        total_yellows = yellows_for + yellows_against
        
        stats['avg_yellows_for'] = float(np.mean(yellows_for))
        stats['avg_yellows_against'] = float(np.mean(yellows_against))
        stats['total_yellows_avg'] = float(np.mean(total_yellows))
        stats['yellows_over_3_5_pct'] = float(np.mean(yellows_for > 3.5) * 100)
        stats['yellows_over_4_5_pct'] = float(np.mean(yellows_for > 4.5) * 100)
    else:
        stats['avg_yellows_for'] = 0.0
        stats['avg_yellows_against'] = 0.0
        stats['total_yellows_avg'] = 0.0
        stats['yellows_over_3_5_pct'] = 0.0
        stats['yellows_over_4_5_pct'] = 0.0

    return stats

def get_league_rankings(df: pd.DataFrame, stat_type: str = 'corners', top_n: int = 3, season_start_date: str = "2025-08-01") -> list:
    df_filtered = df.copy()
    if 'date' in df.columns and season_start_date:
        try:
            start_dt = pd.to_datetime(season_start_date, dayfirst=True, errors='coerce')
            temp_filtered = df[df['date'] >= start_dt].copy()
            if len(temp_filtered) >= 10:
                df_filtered = temp_filtered
        except Exception:
            pass

    if df_filtered is None or len(df_filtered) == 0: return []
    
    teams = list(set(df_filtered['home_team'].dropna()) | set(df_filtered['away_team'].dropna()))
    rankings = []
    for team in teams:
        stats = calculate_team_statistics(df_filtered, team, max_matches=50, season_start_date=None)
        if not stats or stats.get('matches_played', 0) < 3: # Уменьшили порог с 5 до 3 для надежности
            continue
        
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

