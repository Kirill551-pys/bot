"""
МОДУЛЬ РАБОТЫ С БАЗОЙ ДАННЫХ ПОЛЬЗОВАТЕЛЕЙ И ПОДПИСОК
✅ Исправлены все дубликаты функций
✅ Новые пользователи создаются с is_active = 0
✅ Корректная логика активации подписок
"""
import sqlite3
import logging
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_PROJECT_ROOT, 'subscribers.db')
logger.info(f"📂 Путь к БД: {DB_PATH}")

_db_lock = threading.Lock()


@contextmanager
def _get_connection():
    """Безопасное подключение к SQLite с поддержкой FK и WAL"""
    conn = sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Инициализация БД. Вызывать ТОЛЬКО один раз при старте."""
    with _db_lock:
        with _get_connection() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS subscribers (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    subscription_type TEXT DEFAULT 'free',
                    subscription_start TEXT,
                    subscription_end TEXT,
                    trial_used INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                
                
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount REAL,
                    currency TEXT DEFAULT 'RUB',
                    payment_method TEXT,
                    transaction_id TEXT UNIQUE NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (user_id) REFERENCES subscribers(user_id) ON DELETE CASCADE
                );
                
                CREATE TABLE IF NOT EXISTS referrals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referrer_id INTEGER NOT NULL,
                    referred_id INTEGER UNIQUE NOT NULL,
                    bonus_earned REAL DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (referrer_id) REFERENCES subscribers(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (referred_id) REFERENCES subscribers(user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS prediction_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id TEXT NOT NULL,
                    market_type TEXT NOT NULL,          -- Например: '1X2_Home', 'Total_Over_2.5'
                    model_probability REAL NOT NULL,    -- Вероятность по твоей модели (0.0 - 1.0)
                    market_odds REAL NOT NULL,          -- Коэффициент букмекера на момент прогноза
                    stake REAL DEFAULT 1.0,             -- Условная ставка (например, 1 единица)
                    is_hit INTEGER DEFAULT NULL,        -- 1 = зашло, 0 = не зашло, NULL = матч еще не сыгран
                    predicted_at TEXT DEFAULT (datetime('now')),
                    resolved_at TEXT                    -- Дата, когда матч завершился и мы обновили is_hit
                );
            ''')
            # 🔥 НОВАЯ ТАБЛИЦА: Хранение прогнозов для статистики
            conn.execute('''
                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    league TEXT NOT NULL,
                    team1 TEXT NOT NULL,
                    team2 TEXT NOT NULL,
                    commence_time TEXT NOT NULL,
                    hot_bet TEXT NOT NULL,
                    hot_bet_type TEXT,
                    confidence REAL,
                    is_hit INTEGER DEFAULT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES subscribers(user_id)
                )
            ''')
            # Индекс для быстрого поиска незавершённых прогнозов
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_predictions_pending 
                ON predictions(is_hit, commence_time)
            ''')
        
            conn.commit()
            logger.info("✅ База данных инициализирована (включая таблицу predictions)")
            
            cursor = conn.cursor()
            new_columns = {
                'last_paid_end_date': 'TEXT',
                'promo_first_month_used': 'INTEGER DEFAULT 0',
                'is_legal_accepted': 'INTEGER DEFAULT 0',
                'legal_accepted_at': 'TEXT'
            }
            for col_name, col_type in new_columns.items():
                try:
                    cursor.execute(f"ALTER TABLE subscribers ADD COLUMN {col_name} {col_type}")
                    logger.info(f"✅ Миграция БД: добавлена колонка {col_name}")
                except sqlite3.OperationalError:
                    pass
            
            conn.commit()
    
    logger.info("✅ База данных инициализирована")


def save_prediction_to_history(match_id: str, market_type: str, model_prob: float, odds: float, stake: float = 1.0):
    """
    Сохраняет прогноз в историю ДО начала матча.
    is_hit по умолчанию NULL (матч еще не сыгран).
    """
    with _get_connection() as conn:
        conn.execute("""
            INSERT INTO prediction_history 
            (match_id, market_type, model_probability, market_odds, stake, is_hit)
            VALUES (?, ?, ?, ?, ?, NULL)
        """, (match_id, market_type, model_prob, odds, stake))
        conn.commit()

def resolve_prediction(match_id: str, market_type: str, is_hit: int):
    """
    Обновляет статус прогноза ПОСЛЕ окончания матча.
    is_hit: 1 = ставка зашла, 0 = ставка не зашла.
    """
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _get_connection() as conn:
        conn.execute("""
            UPDATE prediction_history 
            SET is_hit = ?, resolved_at = ? 
            WHERE match_id = ? AND market_type = ?
        """, (is_hit, now, match_id, market_type))
        conn.commit()

# И функции для Age Gate (на всякий случай, если ты их еще не добавил):
def get_user_legal_status(user_id: int) -> bool:
    """Проверяет, принял ли пользователь оферту и подтвердил 18+"""
    with _get_connection() as conn:
        cursor = conn.execute(
            "SELECT is_legal_accepted FROM subscribers WHERE user_id = ?", 
            (user_id,)
        )
        row = cursor.fetchone()
        return bool(row and row[0] == 1)

def accept_legal_agreement(user_id: int):
    """Записывает в БД факт согласия пользователя"""
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _get_connection() as conn:
        conn.execute(
            "UPDATE subscribers SET is_legal_accepted = 1, legal_accepted_at = ? WHERE user_id = ?",
            (now, user_id)
        )
        conn.commit()


def get_all_users_count() -> int:
    """Общее количество пользователей в базе"""
    with _get_connection() as conn:
        row = conn.execute('SELECT COUNT(*) FROM subscribers').fetchone()
        return row[0] if row else 0

def save_prediction(
    user_id: int,
    league: str,
    team1: str,
    team2: str,
    commence_time: str,
    hot_bet: str,
    hot_bet_type: str = None,
    confidence: float = None
) -> int:
    """
    Сохраняет прогноз в БД для последующей проверки результата.
    Возвращает ID сохранённой записи.
    """
    with _get_connection() as conn:
        cursor = conn.execute('''
            INSERT INTO predictions 
            (user_id, league, team1, team2, commence_time, hot_bet, hot_bet_type, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, league, team1, team2, commence_time, hot_bet, hot_bet_type, confidence))
        conn.commit()
        prediction_id = cursor.lastrowid
        logger.info(f"💾 Прогноз сохранён: ID={prediction_id}, {team1} vs {team2}, {hot_bet}")
        return prediction_id


def get_active_subscriptions_count() -> int:
    """Количество активных платных подписок"""
    with _get_connection() as conn:
        row = conn.execute('''
            SELECT COUNT(*) FROM subscribers
            WHERE is_active = 1
            AND subscription_type NOT IN ('free', 'trial')
            AND subscription_end > datetime('now')
        ''').fetchone()
        return row[0] if row else 0


def get_trials_count() -> int:
    """Количество использованных trial"""
    with _get_connection() as conn:
        row = conn.execute(
            'SELECT COUNT(*) FROM subscribers WHERE trial_used = 1'
        ).fetchone()
        return row[0] if row else 0


def get_payments_count() -> int:
    """Количество успешных платежей"""
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM payments WHERE status = 'succeeded'"
        ).fetchone()
        return row[0] if row else 0


def get_user_subscription(user_id: int) -> Optional[Dict]:
    """Получить информацию о подписке пользователя"""
    with _get_connection() as conn:
        row = conn.execute(
            'SELECT * FROM subscribers WHERE user_id = ? AND is_active = 1',
            (user_id,)
        ).fetchone()
        return dict(row) if row else None


def create_user(user_id: int, username: str = None, first_name: str = None) -> None:
    """
    Создаёт нового пользователя в БД.
    🆕 Явно устанавливает is_active = 0 для новых пользователей
    """
    with _db_lock:
        with _get_connection() as conn:
            conn.execute('''
                INSERT OR IGNORE INTO subscribers 
                (user_id, username, first_name, is_active, created_at)
                VALUES (?, ?, ?, 0, datetime('now'))
            ''', (user_id, username, first_name))
            conn.commit()


def activate_subscription(user_id: int, tariff: str, days: int) -> None:
    """
    Активирует подписку. 
    Для платных тарифов сохраняет дату окончания для Win-back.
    Для промо-тарифа устанавливает флаг promo_first_month_used.
    """
    now = datetime.now(timezone.utc)
    end_date = now + timedelta(days=days)

    with _db_lock:
        with _get_connection() as conn:
            # Проверяем текущую дату окончания подписки
            row = conn.execute(
                'SELECT subscription_end FROM subscribers WHERE user_id = ?',
                (user_id,)
            ).fetchone()
            
            if row and row[0]:
                try:
                    dt_str = row[0]
                    if dt_str.endswith('Z'):
                        dt_str = dt_str[:-1] + '+00:00'
                    current_end = datetime.fromisoformat(dt_str)
                    if current_end.tzinfo is None:
                        current_end = current_end.replace(tzinfo=timezone.utc)
                    # Если подписка ещё активна, продлеваем от текущей даты окончания
                    if current_end > now:
                        end_date = current_end + timedelta(days=days)
                except ValueError:
                    logger.warning(f"⚠️ Неверный формат даты подписки для user {user_id}")
            
            # Обновляем основные данные подписки
            conn.execute('''
                UPDATE subscribers
                SET subscription_type = ?, 
                    subscription_start = ?, 
                    subscription_end = ?, 
                    is_active = 1
                WHERE user_id = ?
            ''', (tariff, now.isoformat(), end_date.isoformat(), user_id))
            
            # 🆕 ЛОГИКА ДЛЯ МОНЕТИЗАЦИИ:
            # 1. Если это платная подписка (не trial и не free), фиксируем дату окончания
            if tariff not in ('trial', 'free'):
                conn.execute('''
                    UPDATE subscribers 
                    SET last_paid_end_date = ? 
                    WHERE user_id = ?
                ''', (end_date.isoformat(), user_id))
            
            # 2. Если пользователь оплатил промо-тариф, ставим флаг, что он использован
            if tariff == 'promo_month':
                conn.execute('''
                    UPDATE subscribers 
                    SET promo_first_month_used = 1 
                    WHERE user_id = ?
                ''', (user_id,))
            
            conn.commit()
            logger.info(f"✅ Подписка активирована: user {user_id}, тариф {tariff}, {days} дней")


def cancel_subscription(user_id: int) -> bool:
    """Отменяет подписку пользователя"""
    with _db_lock:
        with _get_connection() as conn:
            try:
                cursor = conn.execute('''
                    UPDATE subscribers
                    SET is_active = 0,
                        subscription_type = 'free',
                        subscription_start = NULL,
                        subscription_end = NULL
                    WHERE user_id = ?
                ''', (user_id,))
                conn.commit()
                logger.info(f"🛑 Подписка для юзера {user_id} успешно отменена")
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"❌ Ошибка отмены подписки для {user_id}: {e}")
                return False


def use_trial(user_id: int) -> None:
    """Отмечает, что пользователь использовал пробный период"""
    with _db_lock:
        with _get_connection() as conn:
            conn.execute(
                'UPDATE subscribers SET trial_used = 1 WHERE user_id = ?', 
                (user_id,)
            )
            conn.commit()


def is_trial_available(user_id: int) -> bool:
    """Проверяет, доступен ли пробный период для пользователя"""
    with _get_connection() as conn:
        row = conn.execute(
            'SELECT trial_used FROM subscribers WHERE user_id = ?', 
            (user_id,)
        ).fetchone()
        if row is None:
            return True
        return bool(row and row[0] == 0)


def add_referral(referrer_id: int, referred_id: int) -> None:
    """Добавляет реферальную связь"""
    with _db_lock:
        with _get_connection() as conn:
            try:
                conn.execute(
                    'INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)',
                    (referrer_id, referred_id)
                )
                conn.commit()
            except sqlite3.IntegrityError:
                pass  # Реферал уже существует


def get_referral_count(user_id: int) -> int:
    """Возвращает количество рефералов пользователя"""
    with _get_connection() as conn:
        row = conn.execute(
            'SELECT COUNT(*) FROM referrals WHERE referrer_id = ?',
            (user_id,)
        ).fetchone()
        return row[0] if row else 0


def check_subscription_expired() -> int:
    """
    Проверяет и деактивирует истёкшие подписки (включая trial!).
    Вызывается фоновой задачей или вручную.
    """
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    with _db_lock:
        with _get_connection() as conn:
            # 🆕 ИСПРАВЛЕНО: Теперь включаем 'trial' в список тех, кого нужно отключать
            cursor = conn.execute('''
                UPDATE subscribers
                SET is_active = 0, subscription_type = 'free'
                WHERE subscription_end < ? AND is_active = 1
                AND subscription_type IN ('trial', 'promo_month', 'regular_month', 'quarter', 'winback_month')
            ''', (now,))
            conn.commit()
            return cursor.rowcount
        


def add_payment(user_id: int, amount: float, payment_method: str,
                transaction_id: str, status: str = 'pending') -> bool:
    """Добавляет запись о платеже"""
    with _db_lock:
        with _get_connection() as conn:
            try:
                conn.execute('''
                    INSERT INTO payments (user_id, amount, payment_method, transaction_id, status)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, amount, payment_method, transaction_id, status))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                logger.warning(f"⚠️ Платёж {transaction_id} уже существует")
                return False
            except Exception as e:
                logger.error(f" Ошибка добавления платежа: {e}")
                conn.rollback()
                return False


def get_payment_status(transaction_id: str) -> Optional[str]:
    """Возвращает статус платежа"""
    with _get_connection() as conn:
        row = conn.execute(
            'SELECT status FROM payments WHERE transaction_id = ?',
            (transaction_id,)
        ).fetchone()
        return row[0] if row else None


def update_payment_status(transaction_id: str, new_status: str) -> bool:
    """Обновляет статус платежа"""
    with _db_lock:
        with _get_connection() as conn:
            try:
                cursor = conn.execute(
                    'UPDATE payments SET status = ? WHERE transaction_id = ?',
                    (new_status, transaction_id)
                )
                conn.commit()
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"❌ Ошибка обновления статуса платежа: {e}")
                conn.rollback()
                return False


def get_user_payments(user_id: int, limit: int = 10) -> List[Dict]:
    """Возвращает историю платежей пользователя"""
    with _get_connection() as conn:
        rows = conn.execute('''
            SELECT * FROM payments
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (user_id, limit)).fetchall()
        return [dict(r) for r in rows]


# ==================== ПРОВЕРКА ПОДПИСКИ (PAYWALL) ====================

def is_subscription_active(user_id: int) -> bool:
    """
    Проверяет, есть ли у пользователя активная платная подписка или trial.
    Администратор (ADMIN_ID) всегда имеет полный доступ.
    🆕 ДОБАВЛЕНО: Автоматическое закрытие доступа (self-healing), если дата истекла.
    """
    from config import ADMIN_ID

    # 👑 АДМИН ВСЕГДА ИМЕЕТ ДОСТУП
    if user_id == ADMIN_ID:
        return True

    with _get_connection() as conn:
        row = conn.execute(
            '''SELECT is_active, subscription_type, subscription_end
               FROM subscribers WHERE user_id = ?''',
            (user_id,)
        ).fetchone()
        
        if not row:
            return False
        
        is_active, sub_type, sub_end = row
        
        # 1. Если тип подписки 'free', доступа нет
        if sub_type == 'free':
            return False
        
        # 2. Проверка даты окончания
        if sub_end:
            try:
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S%z']:
                    try:
                        end_dt = datetime.strptime(sub_end, fmt)
                        if end_dt.tzinfo is None:
                            end_dt = end_dt.replace(tzinfo=timezone.utc)
                        
                        # 🚨 ЕСЛИ ПОДПИСКА ИСТЕКЛА
                        if end_dt < datetime.now(timezone.utc):
                            # 🛠️ САМОЛЕЧЕНИЕ: Немедленно обновляем БД, чтобы фронтенд тоже увидел 'free'
                            with _db_lock:
                                conn.execute('''
                                    UPDATE subscribers
                                    SET is_active = 0, subscription_type = 'free'
                                    WHERE user_id = ?
                                ''', (user_id,))
                                conn.commit()
                            return False # Возвращаем False, доступа больше нет
                        break
                    except ValueError:
                        continue
            except Exception:
                pass
        
        return bool(is_active)

def get_subscription_info(user_id: int) -> dict:
    """
    Возвращает подробную информацию о подписке для фронтенда.
    Включая флаги доступности промо и win-back скидки.
    """
    with _get_connection() as conn:
        row = conn.execute(
            '''SELECT user_id, username, first_name, subscription_type,
                      subscription_start, subscription_end, trial_used,
                      is_active, created_at, last_paid_end_date, promo_first_month_used
               FROM subscribers WHERE user_id = ?''',
            (user_id,)
        ).fetchone()
        
        if not row:
            return {
                'subscription_type': 'free',
                'is_active': False,
                'days_left': 0,
                'trial_available': True,
                'is_promo_available': True,
                'is_winback_eligible': False
            }
        
        sub = dict(row)
        
        # 🆕 ИСПРАВЛЕНИЕ: Если тип 'free', принудительно ставим is_active = False
        if sub.get('subscription_type') == 'free':
            sub['is_active'] = 0
        
        # Считаем дни до конца подписки
        days_left = 0
        if sub.get('subscription_end'):
            try:
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S%z']:
                    try:
                        end_dt = datetime.strptime(sub['subscription_end'], fmt)
                        if end_dt.tzinfo is None:
                            end_dt = end_dt.replace(tzinfo=timezone.utc)
                        delta = end_dt - datetime.now(timezone.utc)
                        days_left = max(0, delta.days)
                        break
                    except ValueError:
                        continue
            except Exception:
                pass
        sub['days_left'] = days_left
        
        # Проверяем, доступен ли trial
        sub['trial_available'] = not bool(sub.get('trial_used', 0))
        
        #  ПРОВЕРКА ДОСТУПНОСТИ ПРОМО (499₽)
        sub['is_promo_available'] = not bool(sub.get('promo_first_month_used', 0))
        
        # 🆕 ПРОВЕРКА ДОСТУПНОСТИ WIN-BACK (990₽)
        is_winback_eligible = False
        last_paid_end_str = sub.get('last_paid_end_date')
        
        if not sub.get('is_active', 0) and sub.get('subscription_type') == 'free' and last_paid_end_str:
            try:
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S%z']:
                    try:
                        last_end_dt = datetime.strptime(last_paid_end_str, fmt)
                        if last_end_dt.tzinfo is None:
                            last_end_dt = last_end_dt.replace(tzinfo=timezone.utc)
                        
                        days_since_expired = (datetime.now(timezone.utc) - last_end_dt).days
                        
                        from config import WINBACK_THRESHOLD_DAYS
                        if days_since_expired > WINBACK_THRESHOLD_DAYS:
                            is_winback_eligible = True
                        break
                    except ValueError:
                        continue
            except Exception:
                pass
        
        sub['is_winback_eligible'] = is_winback_eligible
        
        return sub


# ==================== ФУНКЦИИ ДЛЯ ФОНОВЫХ УВЕДОМЛЕНИЙ ====================

def get_expiring_users(hours: int = 24) -> List[int]:
    """Возвращает список user_id, у которых подписка заканчивается в ближайшие N часов"""
    with _get_connection() as conn:
        # 🔥 ИСПРАВЛЕНИЕ: Используем f-строку для hours (это безопасно, т.к. hours — целое число)
        # SQLite не умеет подставлять параметры внутрь строковых функций datetime()
        rows = conn.execute(f'''
            SELECT user_id FROM subscribers
            WHERE is_active = 1
            AND subscription_end IS NOT NULL
            AND subscription_end BETWEEN datetime('now') AND datetime('now', '+{int(hours)} hours')
        ''').fetchall()
        return [row[0] for row in rows]

def get_winback_users() -> List[int]:
    """Возвращает список user_id для win-back уведомлений"""
    with _get_connection() as conn:
        rows = conn.execute('''
            SELECT user_id FROM subscribers
            WHERE is_active = 0
            AND subscription_type = 'free'
            AND last_paid_end_date IS NOT NULL
            AND last_paid_end_date BETWEEN datetime('now', '-31 days') AND datetime('now', '-30 days')
        ''').fetchall()
        return [row[0] for row in rows]