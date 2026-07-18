"""
ФУТБОЛЬНЫЙ ПРОГНОЗИСТ PRO — БОТ TELEGRAM
✅ Прогнозы на матчи с калиброванными вероятностями
✅ ТОП-3 статистика по лигам (сезон 2025-2026)
✅ Подписки через ЮKassa (самозанятый)
✅ Реферальная программа
✅ Кнопка «🔙 Назад» работает ВЕЗДЕ
✅ Прогнозы с угловыми, карточками и рекомендациями
"""
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters.command import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram import Router
import asyncio
import json
import os
import pandas as pd
from datetime import datetime, timedelta
from collections import deque
from scheduler import ModelScheduler
from model import BotConfig
from middleware import SubscriptionMiddleware

# Импорт настроек
from config import (
    BOT_TOKEN, LEAGUES, CHANNEL_USERNAME, SEASON_2025_START,
    SUBSCRIPTION_PRICES, REFERRAL_BONUS_PERCENT, REFERRAL_FREE_DAYS, REDIS_URL
)

# Импорт моделей и КОНСТАНТ
from model import (
    load_matches_data, train_models, predict_match,
    load_model, save_model,
    calculate_team_statistics, get_league_rankings,
    HOME_WIN, DRAW, AWAY_WIN, OVER_25, UNDER_25, BTTS_YES, BTTS_NO
)

# Импорт базы данных и платежей
from database import (
    create_user, get_user_subscription, activate_subscription,
    is_trial_available, use_trial, add_referral, get_referral_count,
    add_payment, get_payment_status, update_payment_status
)
from yookassa_payment import create_payment, confirm_payment

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ==================== СОСТОЯНИЯ (FSM) ====================
class MatchPrediction(StatesGroup):
    choosing_league = State()
    selecting_home_team = State()
    selecting_away_team = State()
    waiting_for_manual_input = State()

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
bot = Bot(token=BOT_TOKEN)
storage = RedisStorage.from_url(REDIS_URL)
dp = Dispatcher(storage=storage)
dp.message.middleware(SubscriptionMiddleware(premium_only=False))
callback_router = Router()

# Константы
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
LEAGUE_MAPPING_PATH = os.path.join(DATA_DIR, 'league_mapping.json')
HISTORY_PATH = os.path.join(DATA_DIR, 'prediction_history.json')
TEAMS_CACHE_PATH = os.path.join(DATA_DIR, 'teams_cache.json')
PREMIUM_CHANNEL = "@your_premium_channel"

# Кэш
MODELS = {}
ALL_MATCHES_DF = None
TEAMS_CACHE = {}
PREDICTION_HISTORY = deque(maxlen=100)
TEAMS_PER_PAGE = 10

# ==================== ВИЗУАЛЬНЫЕ УТИЛИТЫ ====================
def probability_bar(value: float, length: int = 10) -> str:
    value = max(0, min(1, value))
    filled = int(value * length)
    return "▰" * filled + "▱" * (length - filled)

def confidence_indicator(prob: float) -> str:
    if prob >= 0.70: return "🔴 HOT"
    elif prob >= 0.60: return "🟠 WARM"
    elif prob >= 0.50: return "🟡 NEUTRAL"
    else: return "🟢 COLD"

def risk_level_indicator(max_prob: float) -> tuple:
    if max_prob >= 0.75: return "⚡ НИЗКИЙ РИСК", "⭐⭐⭐⭐⭐"
    elif max_prob >= 0.65: return "⚠️ СРЕДНИЙ РИСК", "⭐⭐⭐⭐"
    elif max_prob >= 0.55: return "💣 ВЫСОКИЙ РИСК", "⭐⭐⭐"
    else: return "🧨 ОЧЕНЬ ВЫСОКИЙ РИСК", "⭐⭐"

def format_percentage(value: float) -> str:
    return f"{value * 100:.0f}%"

def team_form_emoji(results: list) -> str:
    if not results: return "❓❓❓❓❓"
    emojis = {"W": "✅", "D": "➖", "L": "❌"}.get
    result = ''.join(emojis(r, "❓") for r in results[-5:])
    return result + "❓" * (5 - len(result))

def calculate_team_form(df, team_name, current_date, n_matches=5):
    if df is None or len(df) == 0: return []
    team_matches = df[
        ((df['home_team'] == team_name) | (df['away_team'] == team_name)) &
        (df['date'] < current_date)
    ].sort_values('date', ascending=False).head(n_matches)
    results = []
    for _, match in team_matches.iterrows():
        if match['home_team'] == team_name:
            if match['home_goals'] > match['away_goals']: results.append('W')
            elif match['home_goals'] == match['away_goals']: results.append('D')
            else: results.append('L')
        else:
            if match['away_goals'] > match['home_goals']: results.append('W')
            elif match['away_goals'] == match['home_goals']: results.append('D')
            else: results.append('L')
    return results

async def is_manual_match_filter(message: types.Message, state: FSMContext) -> bool:
    if not message.text or "vs" not in message.text.lower(): return False
    current_state = await state.get_state()
    return current_state is None

# ==================== РАБОТА С КОМАНДАМИ ====================
def get_teams_from_df(df: pd.DataFrame) -> list:
    if df is None or 'home_team' not in df.columns: return []
    home_teams = set(df['home_team'].dropna().astype(str).str.strip())
    away_teams = set(df['away_team'].dropna().astype(str).str.strip())
    all_teams = sorted(list(home_teams | away_teams))
    return [t for t in all_teams if t and t.lower() not in ['nan', 'none', '']]

def get_teams_for_league(league_key: str) -> list:
    global TEAMS_CACHE
    if league_key in TEAMS_CACHE and TEAMS_CACHE[league_key]:
        return TEAMS_CACHE[league_key]
    if league_key not in MODELS: return []
    df = MODELS[league_key].get('df')
    teams = get_teams_from_df(df)
    TEAMS_CACHE[league_key] = teams
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(TEAMS_CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(TEAMS_CACHE, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"⚠️ Не удалось сохранить кэш команд: {e}")
    return teams

def load_teams_cache():
    global TEAMS_CACHE
    try:
        if os.path.exists(TEAMS_CACHE_PATH):
            with open(TEAMS_CACHE_PATH, 'r', encoding='utf-8') as f:
                TEAMS_CACHE = json.load(f)
            logger.info(f"✅ Загружен кэш команд: {len(TEAMS_CACHE)} лиг")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка загрузки кэша команд: {e}")
        TEAMS_CACHE = {}

def search_teams(teams: list, query: str, limit: int = 10) -> list:
    if not query: return teams[:limit]
    query_lower = query.lower()
    exact = [t for t in teams if query_lower == t.lower()]
    if exact: return exact[:limit]
    contains = [t for t in teams if query_lower in t.lower()]
    if contains: return contains[:limit]
    startswith = [t for t in teams if t.lower().startswith(query_lower)]
    return startswith[:limit] if startswith else teams[:limit]

# ==================== КЛАВИАТУРЫ ====================
def get_main_menu():
    """Главное меню с кнопкой Web App"""
    from aiogram.types import WebAppInfo
    
    # URL вашего Mini App (пока используем localhost для тестов)
    webapp_url = os.getenv("WEBAPP_URL", "http://localhost:5173")
    
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(
                text="🚀 Открыть приложение",
                web_app=WebAppInfo(url=webapp_url)
            )],
            [KeyboardButton(text="📌 Выбрать лигу"), KeyboardButton(text="🔥 Горячий прогноз")],
            [KeyboardButton(text="📈 ТОП-3 команд"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="/help")]
        ],
        resize_keyboard=True
    )

def get_league_keyboard():
    buttons = []
    league_items = list(LEAGUES.items())
    for i in range(0, len(league_items), 2):
        row = [KeyboardButton(text=display_name) for key, display_name in league_items[i:i+2]]
        buttons.append(row)
    buttons.append([KeyboardButton(text="🔙 Назад")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_teams_inline_keyboard(teams: list, page: int = 0, callback_prefix: str = "team"):
    total_pages = (len(teams) + TEAMS_PER_PAGE - 1) // TEAMS_PER_PAGE
    start_idx = page * TEAMS_PER_PAGE
    page_teams = teams[start_idx:start_idx + TEAMS_PER_PAGE]
    keyboard = [[InlineKeyboardButton(
        text=f"🏆 {team if len(team) <= 30 else team[:27]+'...'}",
        callback_data=f"{callback_prefix}:{team}"
    )] for team in page_teams]
    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"{callback_prefix}_page:{page-1}"))
    nav_row.append(InlineKeyboardButton(text=f"📄 {page+1}/{total_pages}", callback_data="ignore"))
    if page < total_pages - 1: nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"{callback_prefix}_page:{page+1}"))
    keyboard.append(nav_row)
    keyboard.append([
        InlineKeyboardButton(text="🔍 Поиск", callback_data=f"{callback_prefix}_search"),
        InlineKeyboardButton(text="🔙 Отмена", callback_data="cancel_selection")
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_search_keyboard(callback_prefix: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад к списку", callback_data=f"{callback_prefix}_list")],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="cancel_selection")]
    ])

def get_bet_keyboard(match_id: str):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 П1", callback_data=f"bet:{match_id}:1"),
         InlineKeyboardButton(text="🤝 X", callback_data=f"bet:{match_id}:X"),
         InlineKeyboardButton(text="🚌 П2", callback_data=f"bet:{match_id}:2")],
        [InlineKeyboardButton(text="⚽ ТБ 2.5", callback_data=f"bet:{match_id}:over"),
         InlineKeyboardButton(text="🛡️ ТМ 2.5", callback_data=f"bet:{match_id}:under")],
        [InlineKeyboardButton(text="🔄 Обе забьют", callback_data=f"bet:{match_id}:btts")]
    ])
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")
    ])
    return keyboard

# ==================== ИСТОРИЯ ПРОГНОЗОВ ====================
def load_prediction_history():
    global PREDICTION_HISTORY
    try:
        if os.path.exists(HISTORY_PATH):
            with open(HISTORY_PATH, 'r', encoding='utf-8') as f:
                PREDICTION_HISTORY = deque(json.load(f), maxlen=100)
            logger.info(f"✅ Загружена история из {len(PREDICTION_HISTORY)} прогнозов")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка загрузки истории: {e}")

def save_prediction_history():
    try:
        os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
        with open(HISTORY_PATH, 'w', encoding='utf-8') as f:
            json.dump(list(PREDICTION_HISTORY), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"⚠️ Ошибка сохранения истории: {e}")

def add_prediction_to_history(team1, team2, league, prediction):
    PREDICTION_HISTORY.appendleft({
        'timestamp': datetime.now().isoformat(),
        'team1': team1, 'team2': team2, 'league': league,
        'prediction': prediction, 'result_confirmed': False, 'actual_result': None
    })
    save_prediction_history()

def get_success_rate():
    now = datetime.now()
    last_24h = [p for p in PREDICTION_HISTORY 
                if (now - datetime.fromisoformat(p['timestamp'])).total_seconds() < 86400
                and p['result_confirmed']]
    if not last_24h: return None
    wins = sum(1 for p in last_24h if p['actual_result'] == 'WIN')
    return wins, len(last_24h), (wins / len(last_24h) * 100)

# ==================== ЗАГРУЗКА МОДЕЛЕЙ ====================
async def load_all_models():
    global MODELS, ALL_MATCHES_DF, TEAMS_CACHE
    logger.info("🔄 Загрузка моделей и команд...")
    load_teams_cache()
    all_matches_path = os.path.join(DATA_DIR, 'all_matches.csv')
    if os.path.exists(all_matches_path):
        try:
            ALL_MATCHES_DF = pd.read_csv(all_matches_path)
            if 'date' in ALL_MATCHES_DF.columns:
                ALL_MATCHES_DF['date'] = pd.to_datetime(ALL_MATCHES_DF['date'], errors='coerce')
            logger.info(f"✅ Загружено {len(ALL_MATCHES_DF)} матчей из всех турниров")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка загрузки all_matches.csv: {e}")
    for folder, display_name in LEAGUES.items():
        data_path = os.path.join(DATA_DIR, folder, 'matches.csv')
        model_path = os.path.join(DATA_DIR, folder, 'model.pkl')
        if not os.path.exists(data_path):
            logger.warning(f"⚠️ Нет данных для {display_name}")
            continue
        try:
            logger.info(f"📊 Загрузка {display_name}...")
            if os.path.exists(model_path):
                model_data = load_model(model_path)
                logger.info(f"   ↳ Модель загружена из кэша")
            else:
                df = load_matches_data(data_path)
                if df is not None and len(df) > 50:
                    model_data = train_models(df)
                    save_model(model_data, model_path)
                    logger.info(f"   ↳ Модель обучена и сохранена")
                else:
                    logger.warning(f"   ↳ Недостаточно данных для обучения")
                    continue
            df = load_matches_data(data_path)
            ratings = model_data.get('final_ratings', {}) if model_data else {}
            teams = get_teams_from_df(df)
            TEAMS_CACHE[folder] = teams
            MODELS[folder] = {
                'model_data': model_data, 'df': df, 'ratings': ratings,
                'name': display_name, 'teams': teams
            }
            logger.info(f"✅ {display_name} загружена ({len(df) if df is not None else 0} матчей, {len(teams)} команд)")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки {display_name}: {e}")
    logger.info(f"✅ Загружено {len(MODELS)} моделей, {sum(len(t) for t in TEAMS_CACHE.values())} уникальных команд")
    load_prediction_history()

# ==================== ПРОГНОЗЫ ====================
def get_hot_prediction():
    if not MODELS: return None
    best_match, best_prob = None, 0
    for league_key, model_info in MODELS.items():
        df = model_info['df']
        if df is None or len(df) < 10: continue
        latest_match = df.iloc[-1]
        team1, team2 = latest_match['home_team'], latest_match['away_team']
        try:
            prediction = predict_match(
                team1=team1, team2=team2,
                model_data=model_info['model_data'],
                ratings_dict=model_info.get('ratings', {}),
                all_matches_df=ALL_MATCHES_DF
            )
            if "error" not in prediction and 'result' in prediction:
                max_prob = max(prediction['result'].values())
                if max_prob > best_prob and max_prob > 0.65:
                    best_prob = max_prob
                    best_match = {
                        'team1': team1, 'team2': team2,
                        'league': model_info['name'],
                        'prediction': prediction, 'confidence': max_prob
                    }
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при поиске горячего прогноза: {e}")
    return best_match

async def cmd_hot_prediction(message: types.Message):
    hot = get_hot_prediction()
    if not hot:
        await message.answer(
            "🔥 <b>Горячий прогноз дня</b>\n\n"
            "Сегодня нет матчей с высокой уверенностью прогноза.\n"
            "Попробуйте позже или выберите матч вручную.",
            parse_mode="HTML", reply_markup=get_main_menu()
        )
        return
    team1, team2 = hot['team1'], hot['team2']
    pred = hot['prediction']
    max_prob = hot['confidence']
    risk_level, stars = risk_level_indicator(max_prob)
    probs = [
        ('🏠 ' + team1, pred['result']['Home Win']),
        ('🤝 Ничья', pred['result']['Draw']),
        ('🚌 ' + team2, pred['result']['Away Win'])
    ]
    probs.sort(key=lambda x: x[1], reverse=True)
    reply = (
        f"{'━' * 35}\n🔥 <b>ГОРЯЧИЙ ПРОГНОЗ ДНЯ</b>\n{'━' * 35}\n\n"
        f"🏠 {team1}  vs  {team2} 🚌\n🏆 {hot['league']}\n\n"
        f"{'━' * 35}\n📊 <b>ТОП ВЕРОЯТНОСТЬ</b>\n{'━' * 35}\n\n"
    )
    for label, prob in probs:
        bar = probability_bar(prob)
        indicator = " ← ФАВОРИТ" if prob == max_prob else ""
        reply += f"{label}\n{bar} {format_percentage(prob)}{indicator}\n\n"
    reply += (
        f"{'━' * 35}\n💡 <b>РЕКОМЕНДАЦИЯ</b>\n{'━' * 35}\n\n"
        f"{risk_level} | {stars}\n"
        f"✅ Ставка: {probs[0][0].replace('🏠 ', '').replace('🚌 ', '')}\n"
        f"💰 Ожидаемый коэффициент: ~{1.0 / max_prob:.2f}\n\n"
        f"{'━' * 35}\n⚠️ <i>Ставьте только то, что готовы потерять!</i>\n{'━' * 35}"
    )
    await message.answer(reply, parse_mode="HTML", reply_markup=get_main_menu())

async def cmd_stats(message: types.Message):
    stats = get_success_rate()
    if not stats:
        await message.answer(
            "📊 <b>Статистика последних 24ч</b>\n\n"
            "Ещё нет подтверждённых результатов.\n"
            "Делайте прогнозы — статистика обновится автоматически!",
            parse_mode="HTML"
        )
        return
    wins, total, rate = stats
    success_emojis = "✅" * wins + "❌" * (total - wins)
    reply = (
        f"📊 <b>СТАТИСТИКА ПОСЛЕДНИХ 24 ЧАСОВ</b>\n{'━' * 35}\n\n"
        f"📈 Успешно: {wins}/{total} ({rate:.1f}%)\n\n{success_emojis}\n\n"
        f"{'━' * 35}\n💡 Чем выше процент — тем точнее модель!\n"
        f"⚠️ Статистика обновляется после подтверждения результатов матчей."
    )
    await message.answer(reply, parse_mode="HTML")

# ==================== ТОП-3 СТАТИСТИКА ====================
@dp.message(Command("top3"))
@dp.message(lambda m: m.text == "📈 ТОП-3 команд")
async def cmd_top3_teams(message: types.Message, state: FSMContext):
    await state.clear()
    await state.update_data(flow="top3")
    keyboard = get_league_keyboard()
    await message.answer(
        "📊 <b>ТОП-3 команд по лигам</b>\n\n"
        "Выберите лигу для просмотра статистики:",
        reply_markup=keyboard, parse_mode="HTML"
    )
    await state.set_state(MatchPrediction.choosing_league)

@dp.message(MatchPrediction.choosing_league)
async def handle_league_selection(message: types.Message, state: FSMContext):
    data = await state.get_data()
    flow = data.get("flow", "prediction")
    reverse_leagues = {v: k for k, v in LEAGUES.items()}
    
    if message.text == "🔙 Назад":
        await state.clear()
        await message.answer("🏠 Главное меню", reply_markup=get_main_menu())
        return
    
    if message.text not in reverse_leagues:
        await message.reply("❌ Выберите лигу из списка", reply_markup=get_league_keyboard())
        return
    
    league_key = reverse_leagues[message.text]
    league_name = LEAGUES[league_key]
    
    if league_key not in MODELS:
        await message.reply(f"❌ Модель для {league_name} не загружена", reply_markup=get_league_keyboard())
        return
    
    df = MODELS[league_key].get('df')
    if df is None or len(df) < 10:
        await message.reply("⚠️ Недостаточно данных для статистики", reply_markup=get_league_keyboard())
        return
    
    if flow == "top3":
        await show_top3_stats(message, league_key, league_name, df, state)
    else:
        await start_prediction_flow(message, league_key, league_name, df, state)

async def show_top3_stats(message: types.Message, league_key: str, league_name: str, df: pd.DataFrame, state: FSMContext):
    """Показывает расширенную ТОП-3 статистику по лиге"""
    season_start = SEASON_2025_START.get(league_key, "2025-08-01")
    await bot.send_chat_action(message.chat.id, action="typing")
    
    def build_top_text(stat_type, title, emoji, suffix=""):
        top = get_league_rankings(df, stat_type, top_n=3, season_start_date=season_start)
        if not top:
            return f"{emoji} {title}: нет данных\n"
        text = f"{emoji} <b>{title}:</b>\n"
        for i, item in enumerate(top, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉"
            text += f"{medal} {i}. {item['team']}: {item['label']}{suffix}\n"
        return text + "\n"
    
    # 🔥 ОСНОВНЫЕ КАТЕГОРИИ
    reply = f"📊 <b>ТОП-3: {league_name}</b>\n{'━' * 35}\n\n"
    
    # Голы и тоталы
    reply += build_top_text('over_2_5', 'ТБ 2.5 (матчи)', '⚽', '%')
    reply += build_top_text('over_3_5', 'ТБ 3.5 (матчи)', '🎯', '%')
    reply += build_top_text('btts', 'Обе забьют', '🔄', '%')
    
    # 🔥 УГЛОВЫЕ (если есть данные)
    if 'home_corners' in df.columns:
        reply += f"{'━' * 35}\n🎯 <b>УГЛОВЫЕ</b>\n{'━' * 35}\n\n"
        reply += build_top_text('corners', 'Средние за команду', '📈', ' угл./матч')
        reply += build_top_text('total_corners', 'Всего в матче (ср.)', '📊', '')
        reply += build_top_text('corners_over_9_5', 'ТБ 9.5 угловых', '🔼', '%')
        reply += build_top_text('corners_over_10_5', 'ТБ 10.5 угловых', '🔺', '%')
    
    # 🔥 ЖЁЛТЫЕ КАРТОЧКИ (если есть данные)
    if 'home_yellows' in df.columns:
        reply += f"{'━' * 35}\n🟨 <b>ЖЁЛТЫЕ КАРТОЧКИ</b>\n{'━' * 35}\n\n"
        reply += build_top_text('yellows', 'Средние за команду', '📈', ' жёлтых/матч')
        reply += build_top_text('total_yellows', 'Всего в матче (ср.)', '📊', '')
        reply += build_top_text('yellows_over_3_5', 'ТБ 3.5 жёлтых', '🔼', '%')
        reply += build_top_text('yellows_over_4_5', 'ТБ 4.5 жёлтых', '🔺', '%')
    
    # 🔥 ДОПОЛНИТЕЛЬНО: форма команд
    reply += f"{'━' * 35}\n📈 <b>ЛУЧШАЯ ФОРМА (последние 5)</b>\n{'━' * 35}\n\n"
    form_top = get_league_rankings(df, 'form', top_n=3, season_start_date=season_start)
    if form_top:
        for i, item in enumerate(form_top, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉"
            reply += f"{medal} {i}. {item['team']}: {item['label']}\n"
    else:
        reply += "❓ Нет данных о форме команд\n"
    
    reply += f"\n💡 <i>Данные сезона с {season_start} • Мин. 5 игр</i>"
    
    # 🔥 КНОПКИ: детализация и назад
    teams_inline = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Статистика конкретной команды", callback_data=f"team_detail:{league_key}")],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")]
    ])
    
    await message.answer(reply, reply_markup=teams_inline, parse_mode="HTML")
    # 🔥 НЕ сбрасываем состояние — чтобы работала кнопка «🔙 Назад»

async def start_prediction_flow(message: types.Message, league_key: str, league_name: str, df: pd.DataFrame, state: FSMContext):
    teams = get_teams_for_league(league_key)
    if not teams:
        await message.reply(
            f"⚠️ В лиге <b>{league_name}</b> пока нет команд в базе.",
            parse_mode="HTML", reply_markup=get_league_keyboard()
        )
        return
    await state.update_data(league=league_key, league_name=league_name, teams=teams, flow="prediction")
    await state.set_state(MatchPrediction.selecting_home_team)
    keyboard = get_teams_inline_keyboard(teams, page=0, callback_prefix="home")
    await message.answer(
        f"🏠 <b>Выберите команду хозяев</b> в лиге <i>{league_name}</i>:",
        reply_markup=keyboard, parse_mode="HTML"
    )

# ==================== CALLBACK: ДЕТАЛЬНАЯ СТАТИСТИКА ====================
@callback_router.callback_query(lambda c: c.data.startswith("team_detail:"))
async def show_team_detail_selector(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    league_key = call.data.split(":")[1]
    if league_key not in MODELS:
        await call.message.edit_text("❌ Модель не загружена")
        return
    teams = get_teams_for_league(league_key)
    if not teams:
        await call.message.edit_text("⚠️ Нет команд в базе")
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🏆 {team[:30]}{'...' if len(team)>30 else ''}", 
                             callback_data=f"stats_team:{league_key}:{team}")]
        for team in teams[:10]
    ])
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="🔙 Назад к ТОП-3", callback_data=f"back_to_top3:{league_key}")
    ])
    await call.message.edit_text(
        "🔍 <b>Выберите команду для детальной статистики:</b>",
        reply_markup=keyboard, parse_mode="HTML"
    )

@callback_router.callback_query(lambda c: c.data.startswith("stats_team:"))
async def show_selected_team_stats(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    parts = call.data.split(":")
    if len(parts) != 3: return
    league_key, team_name = parts[1], parts[2]
    if league_key not in MODELS:
        await call.message.edit_text("❌ Модель не загружена")
        return
    df = MODELS[league_key].get('df')
    season_start = SEASON_2025_START.get(league_key, "2025-08-01")
    stats = calculate_team_statistics(df, team_name, season_start_date=season_start)
    if not stats:
        await call.message.edit_text(f"⚠️ Нет данных для {team_name} в сезоне 2025-2026")
        return
    reply = (
        f"📊 <b>СТАТИСТИКА: {team_name}</b>\n🏆 {MODELS[league_key]['name']}\n{'━' * 35}\n\n"
        f"📈 <b>Общая:</b>\n"
        f"• Матчей: {stats['matches_played']}\n"
        f"• Дома: {stats['home_matches']} | В гостях: {stats['away_matches']}\n"
        f"• Форма (последние 5): {stats['form_points']}/15 ({stats['form_pct']}%)\n\n"
        f"⚽ <b>Голы:</b>\n"
        f"• Забито в ср.: {stats['avg_goals_for']}\n"
        f"• Пропущено в ср.: {stats['avg_goals_against']}\n"
        f"• Тотал в ср.: {stats['total_goals_avg']}\n\n"
        f"🎯 <b>Тоталы:</b>\n"
        f"• ТБ 2.5: {stats['over_2_5_pct']}%\n"
        f"• ТМ 2.5: {stats['under_2_5_pct']}%\n"
        f"• ТБ 3.5: {stats['over_3_5_pct']}%\n\n"
        f"🔄 <b>Обе забьют:</b>\n"
        f"• Да: {stats['btts_yes_pct']}%\n"
        f"• Нет: {stats['btts_no_pct']}%\n"
    )
    if 'avg_corners_for' in stats and stats['avg_corners_for'] > 0:
        reply += f"\n🎯 <b>Угловые:</b>\n• В ср. за команду: {stats['avg_corners_for']}\n• В ср. всего в матче: {stats['total_corners_avg']}\n• ТБ 9.5: {stats['corners_over_9_5_pct']}%\n"
    if 'avg_yellows_for' in stats and stats['avg_yellows_for'] > 0:
        reply += f"\n🟨 <b>Жёлтые карточки:</b>\n• В ср. за команду: {stats['avg_yellows_for']}\n• В ср. всего в матче: {stats['total_yellows_avg']}\n• ТБ 3.5: {stats.get('yellows_over_3_5_pct', 0):.1f}%\n"
    reply += f"\n{'━' * 35}\n💡 <i>Данные сезона с {season_start}</i>"
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад к списку", callback_data=f"team_detail:{league_key}")]
    ])
    await call.message.edit_text(reply, reply_markup=back_keyboard, parse_mode="HTML")

@callback_router.callback_query(lambda c: c.data.startswith("back_to_top3:"))
async def back_to_top3(call: types.CallbackQuery):
    await call.answer()
    league_key = call.data.split(":")[1]
    league_name = LEAGUES.get(league_key, league_key)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Выбрать другую лигу", callback_data="change_league_stats")]
    ])
    await call.message.edit_text(
        f"📊 <b>ТОП-3: {league_name}</b>\n\n💡 Нажмите «Выбрать другую лигу» для смены",
        reply_markup=keyboard, parse_mode="HTML"
    )

@callback_router.callback_query(lambda c: c.data == "change_league_stats")
async def change_league_for_stats(call: types.CallbackQuery):
    await call.answer()
    # ✅ edit_text не принимает ReplyKeyboardMarkup → используем answer + delete
    await call.message.answer("🏆 <b>Выберите лигу:</b>", reply_markup=get_league_keyboard(), parse_mode="HTML")
    try:
        await call.message.delete()
    except:
        pass

# ==================== ПОДПИСКА И ПЛАТЕЖИ ====================
@dp.message(Command("subscribe"))
async def cmd_subscribe(message: types.Message):
    user_id = message.from_user.id
    create_user(user_id, message.from_user.username, message.from_user.first_name)
    sub = get_user_subscription(user_id)
    if sub and sub['subscription_type'] != 'free':
        end_date = datetime.fromisoformat(sub['subscription_end'])
        days_left = (end_date - datetime.now()).days
        status = f"✅ Активна до {end_date.strftime('%d.%m.%Y')} ({days_left} дн.)"
    else:
        status = "❌ Нет активной подписки"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🎁 Пробный (3 дня) — Бесплатно", callback_data="sub:trial")],
        [InlineKeyboardButton(text=f"📅 Неделя — {SUBSCRIPTION_PRICES['weekly']['price']}₽", callback_data="sub:weekly")],
        [InlineKeyboardButton(text=f"📆 Месяц — {SUBSCRIPTION_PRICES['monthly']['price']}₽ ⭐", callback_data="sub:monthly")],
        [InlineKeyboardButton(text=f"📆 Квартал — {SUBSCRIPTION_PRICES['quarter']['price']}₽", callback_data="sub:quarter")],
        [InlineKeyboardButton(text=f"♾️ Навсегда — {SUBSCRIPTION_PRICES['lifetime']['price']}₽", callback_data="sub:lifetime")],
        [InlineKeyboardButton(text="👥 Рефералы", callback_data="referrals")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])
    reply = (
        f"💎 <b>ПОДПИСКА НА ПРОГНОЗЫ</b>\n{'━' * 35}\n\n"
        f"📊 <b>Ваш статус:</b>\n{status}\n\n"
        f"📋 <b>Тарифы:</b>\n"
        f"• 🎁 Пробный: 3 дня бесплатно\n• 📅 Неделя: {SUBSCRIPTION_PRICES['weekly']['price']}₽\n"
        f"• 📆 Месяц: {SUBSCRIPTION_PRICES['monthly']['price']}₽ (выгодно!)\n• 📆 Квартал: {SUBSCRIPTION_PRICES['quarter']['price']}₽ (скидка 17%)\n"
        f"• ♾️ Навсегда: {SUBSCRIPTION_PRICES['lifetime']['price']}₽\n\n"
        f"🎁 <b>Бесплатно:</b> 3 прогноза в день\n💎 <b>Подписка:</b> безлимит + горячие прогнозы + статистика\n\n"
        f"{'━' * 35}\n⚠️ <i>Оплата через ЮKassa (карты РФ, СБП)</i>"
    )
    await message.answer(reply, reply_markup=keyboard, parse_mode="HTML")

@callback_router.callback_query(lambda c: c.data.startswith("sub:"))
async def process_subscription(call: types.CallbackQuery):
    user_id = call.from_user.id
    tariff = call.data.split(":")[1]
    if tariff == 'trial':
        if is_trial_available(user_id):
            activate_subscription(user_id, 'trial', 3)
            use_trial(user_id)
            await call.answer("✅ Пробный период активирован!", show_alert=True)
            await call.message.edit_text(
                "🎉 <b>Пробный период активирован!</b>\n\n"
                "✅ 3 дня полного доступа ко всем функциям\n✅ Горячие прогнозы + Расширенная статистика\n\n"
                "⏰ Подписка истекает через 3 дня\n💎 Продлите: /subscribe",
                parse_mode="HTML"
            )
        else:
            await call.answer("❌ Вы уже использовали пробный период", show_alert=True)
        return
    tariff_info = SUBSCRIPTION_PRICES.get(tariff)
    if not tariff_info or tariff_info['price'] == 0:
        await call.answer("❌ Неверный тариф", show_alert=True)
        return
    payment = await create_payment(user_id=user_id, tariff=tariff, username=call.from_user.username)
    if payment.get('success'):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=payment['payment_url'])],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="subscribe")]
        ])
        await call.message.edit_text(
            f"💳 <b>Оплата подписки</b>\n\n📦 Тариф: {tariff_info['name']}\n💰 Сумма: {payment['amount']}₽\n"
            f"⏱️ Доступ: {tariff_info['days']} дн.\n\n{'━' * 35}\n⚠️ <i>Нажмите «Оплатить» для перехода к оплате</i>",
            reply_markup=keyboard, parse_mode="HTML"
        )
    else:
        await call.answer(f"❌ Ошибка: {payment.get('error')}", show_alert=True)

@dp.message(lambda m: m.text.startswith("/start payment_success_"))
async def handle_payment_success(message: types.Message):
    try:
        parts = message.text.split("_")
        if len(parts) >= 4:
            tariff, user_id = parts[2], int(parts[3])
            tariff_info = SUBSCRIPTION_PRICES.get(tariff)
            if tariff_info:
                activate_subscription(user_id, tariff, tariff_info['days'])
                await message.answer(
                    "🎉 <b>Оплата успешна!</b>\n\n"
                    f"✅ Подписка '{tariff_info['name']}' активирована на {tariff_info['days']} дн.\n\n"
                    "Теперь доступны все функции бота!",
                    parse_mode="HTML"
                )
    except Exception as e:
        logger.error(f"Ошибка обработки оплаты: {e}")

@callback_router.callback_query(lambda c: c.data == "referrals")
async def show_referrals(call: types.CallbackQuery):
    user_id = call.from_user.id
    ref_count = get_referral_count(user_id)
    bonus_days = ref_count * REFERRAL_FREE_DAYS
    bot_username = (await call.bot.me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    reply = (
        f"👥 <b>РЕФЕРАЛЬНАЯ ПРОГРАММА</b>\n{'━' * 35}\n\n"
        f"📊 <b>Ваша статистика:</b>\n• Приглашено: {ref_count}\n• Бонусных дней: {bonus_days}\n\n"
        f"🎁 <b>Бонусы:</b>\n• +{REFERRAL_FREE_DAYS} день за каждого друга\n• +{REFERRAL_BONUS_PERCENT}% от первой оплаты друга\n\n"
        f"🔗 <b>Ваша ссылка:</b>\n<code>{ref_link}</code>\n\n"
        f"{'━' * 35}\n💡 <i>Отправьте ссылку друзьям!</i>"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="subscribe")]
    ])
    await call.message.edit_text(reply, reply_markup=keyboard, parse_mode="HTML")

# ==================== ГЛАВНЫЙ ОБРАБОТЧИК /start ====================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    create_user(user_id, message.from_user.username, message.from_user.first_name)
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        referrer_id = int(args[1].split("_")[1])
        if referrer_id != user_id:
            add_referral(referrer_id, user_id)
            try:
                await bot.send_message(referrer_id, f"🎉 Друг присоединился по вашей ссылке!\n+{REFERRAL_FREE_DAYS} день к подписке")
            except: pass
    await message.answer("🔄 Обновляю меню...", reply_markup=ReplyKeyboardRemove(remove_keyboard=True))
    await message.answer(
        "⚽ <b>Футбольный прогнозист Pro</b>\n\n"
        "✨ Красивые визуальные прогнозы\n🔥 Горячие матчи дня\n"
        "📊 Статистика успехов в реальном времени\n💎 Подписка: /subscribe\n\n"
        "Выберите действие 👇",
        reply_markup=get_main_menu(), parse_mode="HTML"
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📚 <b>Помощь</b>\n\n"
        "🎯 <b>Способ 1 — Выбор из списка:</b>\n"
        "1️⃣ Нажмите 📌 Выбрать лигу → выберите лигу\n"
        "2️⃣ Выберите команду хозяев из списка (или 🔍 Поиск)\n"
        "3️⃣ Выберите команду гостей из списка\n4️⃣ Получите прогноз!\n\n"
        "✍️ <b>Способ 2 — Ручной ввод:</b>\n• Напишите: <code>Команда1 vs Команда2</code>\n\n"
        "🔥 Горячий прогноз — лучший матч дня с высокой уверенностью\n"
        "📊 Статистика — успехи прогнозов за 24 часа\n\n"
        "💡 Совет: Используйте кнопки под прогнозом для быстрой публикации в канал!\n\n"
        "⚠️ <i>Прогнозы не гарантируют выигрыш. Ставки — это риск. Играйте ответственно!</i>",
        parse_mode="HTML"
    )

# ==================== МЕНЮ И ВЫБОР ЛИГИ ====================
@dp.message(lambda m: m.text == "📌 Выбрать лигу")
async def choose_league(message: types.Message, state: FSMContext):
    await state.clear()
    await state.update_data(flow="prediction")
    await state.set_state(MatchPrediction.choosing_league)
    await message.answer("🏆 <b>Выберите лигу:</b>", reply_markup=get_league_keyboard(), parse_mode="HTML")

@dp.message(lambda m: m.text == "🔥 Горячий прогноз")
async def hot_prediction_handler(message: types.Message, state: FSMContext):
    await state.clear()
    await cmd_hot_prediction(message)

@dp.message(lambda m: m.text == "📊 Статистика")
async def stats_handler(message: types.Message, state: FSMContext):
    await state.clear()
    await cmd_stats(message)

# ==================== ВЫБОР КОМАНД ДЛЯ ПРОГНОЗА ====================
@callback_router.callback_query(lambda c: c.data.startswith("home:") or c.data.startswith("away:"))
async def handle_team_selection(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    parts = call.data.split(":", 1)
    if len(parts) != 2: return
    selection_type, team_name = parts[0], parts[1]
    data = await state.get_data()
    league_key = data.get("league")
    if not league_key:
        await call.message.edit_text("❌ Ошибка: лига не выбрана")
        return
    if selection_type == "home":
        await state.update_data(home_team=team_name)
        await state.set_state(MatchPrediction.selecting_away_team)
        teams = data.get("teams", [])
        keyboard = get_teams_inline_keyboard(teams, page=0, callback_prefix="away")
        await call.message.edit_text(
            f"✅ Хозяева: <b>{team_name}</b>\n\n🚌 <b>Теперь выберите команду гостей</b>:",
            reply_markup=keyboard, parse_mode="HTML"
        )
    elif selection_type == "away":
        home_team = data.get("home_team")
        if not home_team:
            await call.message.edit_text("❌ Ошибка: команда хозяев не выбрана")
            return
        await call.message.edit_text("⏳ <b>Генерирую прогноз...</b>", parse_mode="HTML")
        await generate_and_send_prediction(call.message, home_team, team_name, league_key, state)

@callback_router.callback_query(lambda c: c.data.startswith("home_page:") or c.data.startswith("away_page:"))
async def handle_team_pagination(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    parts = call.data.split(":")
    if len(parts) != 2: return
    selection_type = parts[0].split("_")[0]
    page = int(parts[1])
    data = await state.get_data()
    teams = data.get("teams", [])
    keyboard = get_teams_inline_keyboard(teams, page=page, callback_prefix=selection_type)
    action_text = "хозяев" if selection_type == "home" else "гостей"
    await call.message.edit_text(
        f"🏆 <b>Выберите команду {action_text}</b> (стр. {page+1}):",
        reply_markup=keyboard, parse_mode="HTML"
    )

@callback_router.callback_query(lambda c: c.data.endswith("_search"))
async def handle_team_search_mode(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    selection_type = call.data.split("_")[0]
    await state.update_data(search_mode=True, search_type=selection_type)
    keyboard = get_search_keyboard(selection_type)
    action_text = "хозяев" if selection_type == "home" else "гостей"
    await call.message.edit_text(
        f"🔍 <b>Поиск команды {action_text}</b>\n\n📝 <i>Напишите название команды в чат:</i>",
        reply_markup=keyboard, parse_mode="HTML"
    )

@callback_router.callback_query(lambda c: c.data.endswith("_list"))
async def handle_team_list_mode(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await state.update_data(search_mode=False)
    data = await state.get_data()
    teams = data.get("teams", [])
    selection_type = data.get("search_type", "home")
    keyboard = get_teams_inline_keyboard(teams, page=0, callback_prefix=selection_type)
    action_text = "хозяев" if selection_type == "home" else "гостей"
    await call.message.edit_text(
        f"🏆 <b>Выберите команду {action_text}</b>:",
        reply_markup=keyboard, parse_mode="HTML"
    )

@callback_router.callback_query(lambda c: c.data == "cancel_selection")
async def handle_cancel_selection(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    # ✅ edit_text не принимает ReplyKeyboardMarkup → используем answer + delete
    await call.message.answer("❌ Выбор отменен", reply_markup=get_main_menu())
    try:
        await call.message.delete()
    except:
        pass  

# ==================== ПОИСК КОМАНД ====================
@dp.message(lambda m, state: state.get_state() in [MatchPrediction.selecting_home_team, MatchPrediction.selecting_away_team])
async def handle_team_search_input(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("search_mode"): return
    search_type = data.get("search_type")
    teams = data.get("teams", [])
    query = message.text.strip()
    results = search_teams(teams, query, limit=5)
    if not results:
        await message.reply(
            f"❌ Команды <b>«{query}»</b> не найдено в этой лиге.\n"
            f"💡 Попробуйте другое название или нажмите «Назад к списку»",
            parse_mode="HTML", reply_markup=get_search_keyboard(search_type)
        )
        return
    if len(results) == 1 and results[0].lower() == query.lower():
        team_name = results[0]
        if search_type == "home":
            await state.update_data(home_team=team_name, search_mode=False)
            await state.set_state(MatchPrediction.selecting_away_team)
            keyboard = get_teams_inline_keyboard(teams, page=0, callback_prefix="away")
            await message.answer(
                f"✅ Найдено: <b>{team_name}</b> (хозяева)\n\n🚌 <b>Теперь выберите команду гостей</b>:",
                reply_markup=keyboard, parse_mode="HTML"
            )
        else:
            home_team = data.get("home_team")
            await message.answer("⏳ <b>Генерирую прогноз...</b>", parse_mode="HTML")
            await generate_and_send_prediction(message, home_team, team_name, data.get("league"), state)
        return
    buttons = [[InlineKeyboardButton(text=f"🏆 {team}", callback_data=f"{search_type}:{team}")] for team in results]
    buttons.append([InlineKeyboardButton(text="🔙 Назад к поиску", callback_data=f"{search_type}_search")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.reply(
        f"🔍 <b>Найдено {len(results)} вариантов:</b>\n\nВыберите нужную команду:",
        reply_markup=keyboard, parse_mode="HTML"
    )

# ==================== ГЕНЕРАЦИЯ ПРОГНОЗА (ПОЛНАЯ ВЕРСИЯ) ====================
async def generate_and_send_prediction(message: types.Message, team1: str, team2: str, league_key: str, state: FSMContext):
    if league_key not in MODELS:
        await message.reply(f"❌ Модель для лиги не загружена")
        await state.clear()
        return
    
    model_info = MODELS[league_key]
    try:
        prediction = predict_match(
            team1=team1, team2=team2,
            model_data=model_info['model_data'],
            ratings_dict=model_info.get('ratings', {}),
            all_matches_df=model_info['df']
        )
        if "error" in prediction:
            await message.reply(f"❌ {prediction['error']}")
            await state.clear()
            return
        
        # Публикация горячего прогноза
        if prediction.get('is_hot', False):
            try:
                hot_bet = prediction.get('hot_bet', 'Ставка не определена')
                hot_conf = prediction.get('hot_confidence', 0.0)
                max_prob = max(prediction['result'].values())
                hot_msg = (
                    f"💎 <b>ПРЕМИУМ-ПРОГНОЗ</b> 💎\n\n"
                    f"🏠 {team1} vs {team2} 🚌\n🏆 {model_info['name']}\n\n"
                    f"🔥 УВЕРЕННОСТЬ: {hot_conf:.1f}%\n✅ Рекомендуемая ставка: {hot_bet}\n"
                    f"💰 Ожидаемый коэффициент: ~{1.0 / max_prob:.2f}\n\n"
                    f"⏰ {datetime.now().strftime('%d.%m %H:%M')}\n⚠️ Только для подписчиков премиум-канала!"
                )
                await bot.send_message(chat_id=PREMIUM_CHANNEL, text=hot_msg, parse_mode="HTML")
                logger.info(f"✅ Горячий прогноз опубликован в {PREMIUM_CHANNEL}")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка публикации в премиум-канал: {e}")
        
        # Форма команд
        current_date = datetime.now()
        home_form = calculate_team_form(model_info['df'], team1, current_date)
        away_form = calculate_team_form(model_info['df'], team2, current_date)
        probs = prediction['result']
        max_prob = max(probs[HOME_WIN], probs[DRAW], probs[AWAY_WIN])
        risk_level, stars = risk_level_indicator(max_prob)
        
        # 🔥 РЕКОМЕНДАЦИИ (снижены пороги)
        rec = []
        if 'result' in prediction:
            home_win = prediction['result'][HOME_WIN]
            away_win = prediction['result'][AWAY_WIN]
            draw = prediction['result'][DRAW]
            
            if home_win > 0.40 and home_win > away_win + 0.12 and home_win > draw + 0.12:
                rec.append(f"🔴 Фаворит: {team1} ({home_win*100:.0f}%)")
            elif away_win > 0.40 and away_win > home_win + 0.12 and away_win > draw + 0.12:
                rec.append(f"🔵 Фаворит: {team2} ({away_win*100:.0f}%)")
            elif draw > 0.35 and draw > home_win + 0.10 and draw > away_win + 0.10:
                rec.append(f"🤝 Вероятна ничья ({draw*100:.0f}%)")
        
        if 'total_goals' in prediction:
            total_prob = prediction['total_goals'][OVER_25]
            if total_prob > 0.60:
                rec.append(f"⚽ ТБ 2.5 ({total_prob*100:.0f}%)")
            elif total_prob < 0.40:
                rec.append(f"🛡️ ТМ 2.5 ({(1-total_prob)*100:.0f}%)")
        
        if 'both_scored' in prediction:
            btts_prob = prediction['both_scored'][BTTS_YES]
            if btts_prob > 0.60:
                rec.append(f"🔄 Обе забьют ({btts_prob*100:.0f}%)")
            elif btts_prob < 0.40:
                rec.append(f"🚫 Одна не забьёт ({(1-btts_prob)*100:.0f}%)")
        
        # 🔥 УГЛОВЫЕ И КАРТОЧКИ
        df = model_info['df']
        if df is not None and 'home_corners' in df.columns:
            home_stats = calculate_team_statistics(df, team1, season_start_date=SEASON_2025_START.get(league_key, "2025-08-01"))
            away_stats = calculate_team_statistics(df, team2, season_start_date=SEASON_2025_START.get(league_key, "2025-08-01"))
            if home_stats and away_stats:
                avg_corners = (home_stats.get('avg_corners_for', 0) + away_stats.get('avg_corners_for', 0)) / 2
                if avg_corners > 5.5:
                    rec.append(f"🎯 Много угловых (ср. {avg_corners:.1f})")
                elif avg_corners < 3.5:
                    rec.append(f"🎯 Мало угловых (ср. {avg_corners:.1f})")
        
        if df is not None and 'home_yellows' in df.columns:
            home_stats = calculate_team_statistics(df, team1, season_start_date=SEASON_2025_START.get(league_key, "2025-08-01"))
            away_stats = calculate_team_statistics(df, team2, season_start_date=SEASON_2025_START.get(league_key, "2025-08-01"))
            if home_stats and away_stats:
                avg_yellows = (home_stats.get('avg_yellows_for', 0) + away_stats.get('avg_yellows_for', 0)) / 2
                if avg_yellows > 3.0:
                    rec.append(f"🟨 Много жёлтых (ср. {avg_yellows:.1f})")
                elif avg_yellows < 1.5:
                    rec.append(f"🟨 Мало жёлтых (ср. {avg_yellows:.1f})")
        
        recommendation_text = "\n".join(rec) if rec else "📊 Тактически сложный матч — нет явного фаворита"
        
        # 🔥 ФОРМИРОВАНИЕ СООБЩЕНИЯ
        reply = (
            f"{'━' * 35}\n⚡ <b>ПРОГНОЗ МАТЧА</b>\n{'━' * 35}\n\n"
            f"🏠 {team1}  vs  {team2} 🚌\n🏆 {model_info['name']}\n\n"
            f"{'━' * 35}\n📊 <b>ВЕРОЯТНОСТИ</b>\n{'━' * 35}\n\n"
            f"🏆 <b>ПОБЕДИТЕЛЬ</b>\n🏠 {team1}\n"
            f"{probability_bar(probs[HOME_WIN])} {format_percentage(probs[HOME_WIN])} {confidence_indicator(probs[HOME_WIN])}\n\n"
            f"🤝 Ничья\n{probability_bar(probs[DRAW])} {format_percentage(probs[DRAW])} {confidence_indicator(probs[DRAW])}\n\n"
            f"🚌 {team2}\n{probability_bar(probs[AWAY_WIN])} {format_percentage(probs[AWAY_WIN])} {confidence_indicator(probs[AWAY_WIN])}\n\n"
            f"{'━' * 35}\n⚽ <b>ТОТАЛЫ И СПЕЦИАЛЬНЫЕ СТАВКИ</b>\n{'━' * 35}\n\n"
            f"🥅 Тотал 2.5\nБольше: {probability_bar(prediction['total_goals'][OVER_25])} {format_percentage(prediction['total_goals'][OVER_25])}\n"
            f"Меньше: {probability_bar(prediction['total_goals'][UNDER_25])} {format_percentage(prediction['total_goals'][UNDER_25])}\n\n"
            f"🔄 Обе забьют\nДа: {probability_bar(prediction['both_scored'][BTTS_YES])} {format_percentage(prediction['both_scored'][BTTS_YES])}\n"
            f"Нет: {probability_bar(prediction['both_scored'][BTTS_NO])} {format_percentage(prediction['both_scored'][BTTS_NO])}\n"
        )
        
        # 🔥 УГЛОВЫЕ
        if df is not None and 'home_corners' in df.columns:
            home_stats = calculate_team_statistics(df, team1, season_start_date=SEASON_2025_START.get(league_key, "2025-08-01"))
            away_stats = calculate_team_statistics(df, team2, season_start_date=SEASON_2025_START.get(league_key, "2025-08-01"))
            if home_stats and away_stats:
                h_c = home_stats.get('avg_corners_for', 0)
                a_c = away_stats.get('avg_corners_for', 0)
                total_c = h_c + a_c
                reply += (
                    f"\n{'━' * 35}\n🎯 <b>УГЛОВЫЕ</b>\n{'━' * 35}\n"
                    f"• {team1}: {h_c:.1f} угл./матч\n"
                    f"• {team2}: {a_c:.1f} угл./матч\n"
                    f"• Всего в матче: ~{total_c:.1f}\n"
                    f"• ТБ 9.5: {home_stats.get('corners_over_9_5_pct', 0):.0f}% / {away_stats.get('corners_over_9_5_pct', 0):.0f}%\n"
                )
        
        # 🔥 ЖЁЛТЫЕ КАРТОЧКИ
        if df is not None and 'home_yellows' in df.columns:
            home_stats = calculate_team_statistics(df, team1, season_start_date=SEASON_2025_START.get(league_key, "2025-08-01"))
            away_stats = calculate_team_statistics(df, team2, season_start_date=SEASON_2025_START.get(league_key, "2025-08-01"))
            if home_stats and away_stats:
                h_y = home_stats.get('avg_yellows_for', 0)
                a_y = away_stats.get('avg_yellows_for', 0)
                total_y = h_y + a_y
                reply += (
                    f"\n{'━' * 35}\n🟨 <b>ЖЁЛТЫЕ КАРТОЧКИ</b>\n{'━' * 35}\n"
                    f"• {team1}: {h_y:.1f} жёлтых/матч\n"
                    f"• {team2}: {a_y:.1f} жёлтых/матч\n"
                    f"• Всего в матче: ~{total_y:.1f}\n"
                    f"• ТБ 3.5: {home_stats.get('yellows_over_3_5_pct', 0):.0f}% / {away_stats.get('yellows_over_3_5_pct', 0):.0f}%\n"
                )
        
        # Форма и рекомендация
        reply += (
            f"\n{'━' * 35}\n📈 <b>ФОРМА КОМАНД</b>\n{'━' * 35}\n\n"
            f"🏠 {team1}\n{team_form_emoji(home_form)}\n\n"
            f"🚌 {team2}\n{team_form_emoji(away_form)}\n\n"
            f"{'━' * 35}\n💡 <b>РЕКОМЕНДАЦИЯ</b>\n{'━' * 35}\n\n"
            f"{risk_level} | {stars}\n"
            f"{recommendation_text}\n\n"
            f"💰 Ожидаемый коэффициент: ~{1.0 / max_prob:.2f}\n\n"
            f"{'━' * 35}\n🛡️ <b>ДОВЕРИЕ К ПРОГНОЗУ</b>\n{'━' * 35}\n\n"
            f"{prediction.get('trust_signal', '❓ Нет данных')}\n\n"
            f"{'━' * 35}\n⚠️ <i>Ставьте только то, что готовы потерять!</i>\n{'━' * 35}"
        )
        
        match_id = f"{team1.lower().replace(' ', '_')}_{team2.lower().replace(' ', '_')}_{int(datetime.now().timestamp())}"
        add_prediction_to_history(team1, team2, model_info['name'], prediction)
        await state.update_data(last_prediction={
            'team1': team1, 'team2': team2, 'league_name': model_info['name'],
            'reply_text': reply, 'match_id': match_id
        })
        
        await message.answer(reply, reply_markup=get_bet_keyboard(match_id), parse_mode="HTML")
        await state.clear()
        
    except Exception as e:
        logger.error(f"❌ Ошибка генерации прогноза: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await message.reply(f"❌ Ошибка генерации прогноза: {str(e)[:150]}")
        await state.clear()

# ==================== КНОПКИ СТАВОК ====================
@callback_router.callback_query(lambda c: c.data.startswith("bet:"))
async def handle_bet_button(call: types.CallbackQuery):
    await call.answer("📱 Откройте приложение букмекера для ставки", show_alert=True)

@callback_router.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main_menu(call: types.CallbackQuery):
    """Кнопка «🔙 Назад в меню» после прогноза"""
    await call.answer()
    
    # 🔥 ИСПРАВЛЕНО: используем answer() вместо edit_text()
    # потому что edit_text() не принимает ReplyKeyboardMarkup
    await call.message.answer(
        "🏠 <b>Главное меню</b>",
        reply_markup=get_main_menu(),  # ← Теперь работает!
        parse_mode="HTML"
    )
    
    # 🔥 Опционально: удаляем старое сообщение с прогнозом
    try:
        await call.message.delete()
    except:
        pass  # Если не удалось удалить — не страшно
# ==================== РУЧНОЙ ВВОД МАТЧА ====================
@dp.message(is_manual_match_filter)
async def handle_manual_match_input(message: types.Message, state: FSMContext):
    text = message.text.strip()
    parts = text.lower().split('vs')
    if len(parts) < 2:
        await message.reply(
            "❌ Укажите обе команды в формате: <code>Команда1 vs Команда2</code>",
            parse_mode="HTML"
        )
        return
    team1 = text[:text.lower().index('vs')].strip()
    team2 = text[text.lower().index('vs') + 2:].strip()
    league_key = None
    norm1, norm2 = team1.lower().replace(" ", ""), team2.lower().replace(" ", "")
    for lk, teams in TEAMS_CACHE.items():
        if any(norm1 in t.lower().replace(" ", "") or norm2 in t.lower().replace(" ", "") for t in teams):
            league_key = lk
            break
    if not league_key:
        await message.reply(
            "⚠️ Не удалось определить лигу автоматически.\n"
            "Пожалуйста, выберите лигу через меню 📌 Выбрать лигу",
            reply_markup=get_main_menu()
        )
        return
    await message.answer("⏳ <b>Генерирую прогноз...</b>", parse_mode="HTML")
    await generate_and_send_prediction(message, team1, team2, league_key, state)

# ==================== УНИВЕРСАЛЬНЫЙ ОБРАБОТЧИК (В КОНЦЕ!) ====================
@dp.message()
async def handle_all(message: types.Message, state: FSMContext):
    """Обработчик всех остальных сообщений — должен быть ПОСЛЕДНИМ!"""
    text = message.text.strip()
    
    # 🔥 КНОПКА «🔙 Назад» — работает ВЕЗДЕ
    if text == "🔙 Назад":
        await state.clear()
        await message.answer("🏠 Главное меню", reply_markup=get_main_menu())
        return
    
    if text.startswith("/"): 
        return
    
    current_state = await state.get_state()
    
    if current_state in [
        MatchPrediction.choosing_league,
        MatchPrediction.selecting_home_team,
        MatchPrediction.selecting_away_team
    ]:
        return
    
    await message.reply(
        "❓ Неизвестная команда...\n\n"
        "💡 Используйте:\n"
        "• Меню 📌 Выбрать лигу → выбор команд из списка\n"
        "• Или формат: <code>Команда1 vs Команда2</code>\n"
        "• Или /help для справки",
        parse_mode="HTML"
    )

# ==================== ЗАПУСК ====================
async def main():
    from database import init_db
    init_db() 
    await load_all_models()

    config = BotConfig()
    scheduler = ModelScheduler(config)
    scheduler.start()

    try:
        if MODELS:
            dp.include_router(callback_router)
            print("\n" + "="*60)
            print("🤖 БОТ ЗАПУЩЕН — ПРОФЕССИОНАЛЬНАЯ ВЕРСИЯ 2.0")
            print("="*60)
            print(f"✅ Загружено лиг: {len(MODELS)}")
            print(f"✅ Доступно команд: {sum(len(t) for t in TEAMS_CACHE.values())}")
            print(f"✅ История прогнозов: {len(PREDICTION_HISTORY)} записей")
            print(f"✅ Основной канал: {CHANNEL_USERNAME}")
            print(f"✅ Премиум-канал: {PREMIUM_CHANNEL}")
            print(f"✅ Пагинация: {TEAMS_PER_PAGE} команд на странице")
            print(f"✅ Поиск команд: ВКЛЮЧЁН")
            print("="*60 + "\n")
            await dp.start_polling(bot)
        else:
            print("❌ Нет моделей для работы. Проверьте папку data/")
            print("💡 Убедитесь, что в data/ есть папки с matches.csv")
    finally:
        scheduler.stop()
if __name__ == "__main__":
    asyncio.run(main())