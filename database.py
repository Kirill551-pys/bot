import sqlite3
import logging
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))  # ← один dirname!
DB_PATH = os.path.join(_PROJECT_ROOT, 'subscribers.db')

logger.info(f"📂 Путь к БД: {DB_PATH}")  # ← чтобы видеть в логах

_db_lock = threading.Lock()

@contextmanager
def _get_connection():
    """Безопасное подключение к SQLite с поддержкой FK и WAL"""
    conn = sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")  # Уменьшает блокировки при чтении/записи
    conn.execute("PRAGMA foreign_keys = ON;") # Включает проверку связей
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Инициализация БД. Вызывать ТОЛЬКО один раз при старте бота (в main())."""
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
                    is_active INTEGER DEFAULT 1,
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
            ''')

            cursor = conn.cursor()
            new_columns = {
                'last_paid_end_date': 'TEXT',
                'promo_first_month_used': 'INTEGER DEFAULT 0'
            }

            for col_name, col_type in new_columns.items():
                try:
                    cursor.execute(f"ALTER TABLE subscribers ADD COLUMN {col_name} {col_type}")
                    logger.info(f"✅ Миграция БД: добавлена колонка {col_name}")
                except sqlite3.OperationalError:
                    pass
            conn.commit()
        logger.info("✅ База данных инициализирована")

def get_all_users_count() -> int:
    """Общее количество пользователей в базе"""
    with _get_connection() as conn:
        row = conn.execute('SELECT COUNT(*) FROM subscribers').fetchone()
        return row[0] if row else 0


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
    with _get_connection() as conn:
        row = conn.execute(
            'SELECT * FROM subscribers WHERE user_id = ? AND is_active = 1',
            (user_id,)
        ).fetchone()
    return dict(row) if row else None

def create_user(user_id: int, username: str = None, first_name: str = None) -> None:
    with _db_lock:
        with _get_connection() as conn:
            conn.execute('''
                INSERT OR IGNORE INTO subscribers (user_id, username, first_name, created_at)
                VALUES (?, ?, ?, datetime('now'))
            ''', (user_id, username, first_name))
            conn.commit()

def activate_subscription(user_id: int, tariff: str, days: int) -> None:
    """Активирует подписку. Для платных тарифов сохраняет дату окончания для Win-back."""
    now = datetime.now(timezone.utc)
    end_date = now + timedelta(days=days)
    
    with _db_lock:
        with _get_connection() as conn:
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
                    
                    # Если подписка еще активна, продлеваем от текущей даты окончания
                    if current_end > now:
                        end_date = current_end + timedelta(days=days)
                except ValueError:
                    logger.warning(f"⚠️ Неверный формат даты подписки для user {user_id}")
            
            # Обновляем основные данные подписки
            conn.execute('''
                UPDATE subscribers
                SET subscription_type = ?, subscription_start = ?, subscription_end = ?, is_active = 1
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

def cancel_subscription(user_id: int) -> bool:
    """
    Отменяет подписку пользователя.
    Сбрасывает статус на 'free', деактивирует доступ и очищает даты.
    """
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
    with _db_lock:
        with _get_connection() as conn:
            conn.execute('UPDATE subscribers SET trial_used = 1 WHERE user_id = ?', (user_id,))
            conn.commit()

def is_trial_available(user_id: int) -> bool:
    with _get_connection() as conn:
        row = conn.execute('SELECT trial_used FROM subscribers WHERE user_id = ?', (user_id,)).fetchone()
        if row is None:
            return True
    return bool(row and row[0] == 0)

def add_referral(referrer_id: int, referred_id: int) -> None:
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
    with _get_connection() as conn:
        row = conn.execute(
            'SELECT COUNT(*) FROM referrals WHERE referrer_id = ?',
            (user_id,)
        ).fetchone()
    return row[0] if row else 0

def check_subscription_expired() -> int:
    # ✅ Используем тот же формат, что и datetime('now') в SQLite
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    with _db_lock:
        with _get_connection() as conn:
            cursor = conn.execute('''
                UPDATE subscribers
                SET is_active = 0, subscription_type = 'free'
                WHERE subscription_end < ? AND is_active = 1
                  AND subscription_type NOT IN ('free', 'trial')
            ''', (now,))
            conn.commit()
            return cursor.rowcount

def add_payment(user_id: int, amount: float, payment_method: str, 
                transaction_id: str, status: str = 'pending') -> bool:
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
                logger.error(f"❌ Ошибка добавления платежа: {e}")
                conn.rollback()
                return False

def get_payment_status(transaction_id: str) -> Optional[str]:
    with _get_connection() as conn:
        row = conn.execute(
            'SELECT status FROM payments WHERE transaction_id = ?',
            (transaction_id,)
        ).fetchone()
    return row[0] if row else None

def update_payment_status(transaction_id: str, new_status: str) -> bool:
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
    Проверяет, есть ли у пользователя активная подписка ИЛИ trial.
    Администратор (ADMIN_ID) всегда имеет полный доступ.
    """
    from config import ADMIN_ID
    
    #  АДМИН ВСЕГДА ИМЕЕТ ДОСТУП
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
    
    if not is_active:
        return False
    
    if sub_end:
        try:
            from datetime import datetime, timezone
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S%z']:
                try:
                    end_dt = datetime.strptime(sub_end, fmt)
                    if end_dt.tzinfo is None:
                        end_dt = end_dt.replace(tzinfo=timezone.utc)
                    if end_dt < datetime.now(timezone.utc):
                        return False
                    break
                except ValueError:
                    continue
        except Exception:
            pass
    
    return True


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
        
        # 🆕 ПРОВЕРКА ДОСТУПНОСТИ ПРОМО (499₽)
        # Промо доступно, если пользователь еще ни разу его не использовал
        sub['is_promo_available'] = not bool(sub.get('promo_first_month_used', 0))
        
        # 🆕 ПРОВЕРКА ДОСТУПНОСТИ WIN-BACK (990₽)
        # Win-back доступен, если:
        # 1. У пользователя сейчас нет активной подписки (или она free)
        # 2. У него есть история платных подписок (last_paid_end_date)
        # 3. С момента окончания последней платной подписки прошло > 30 дней
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
                        
                        # Импортируем порог из конфига
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
    """
    Возвращает список user_id, у которых подписка заканчивается в ближайшие N часов.
    """
    with _get_connection() as conn:
        rows = conn.execute('''
            SELECT user_id FROM subscribers 
            WHERE is_active = 1 
            AND subscription_end IS NOT NULL
            AND subscription_end BETWEEN datetime('now') AND datetime('now', '+? hours')
        ''', (hours,)).fetchall()
        return [row[0] for row in rows]

def get_winback_users() -> List[int]:
    """
    Возвращает список user_id, у которых платная подписка закончилась 
    ровно от 30 до 31 дня назад (чтобы не спамить каждый час).
    """
    with _get_connection() as conn:
        rows = conn.execute('''
            SELECT user_id FROM subscribers 
            WHERE is_active = 0 
            AND subscription_type = 'free'
            AND last_paid_end_date IS NOT NULL
            AND last_paid_end_date BETWEEN datetime('now', '-31 days') AND datetime('now', '-30 days')
        ''').fetchall()
        return [row[0] for row in rows]
