import sqlite3
import logging
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

# ✅ АБСОЛЮТНЫЙ ПУТЬ: БД всегда в корне проекта
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
                    if current_end > now:
                        end_date = current_end + timedelta(days=days)
                except ValueError:
                    logger.warning(f"⚠️ Неверный формат даты подписки для user {user_id}")

            conn.execute('''
                UPDATE subscribers
                SET subscription_type = ?, subscription_start = ?, subscription_end = ?, is_active = 1
                WHERE user_id = ?
            ''', (tariff, now.isoformat(), end_date.isoformat(), user_id))
            conn.commit()

def use_trial(user_id: int) -> None:
    with _db_lock:
        with _get_connection() as conn:
            conn.execute('UPDATE subscribers SET trial_used = 1 WHERE user_id = ?', (user_id,))
            conn.commit()

def is_trial_available(user_id: int) -> bool:
    with _get_connection() as conn:
        row = conn.execute('SELECT trial_used FROM subscribers WHERE user_id = ?', (user_id,)).fetchone()
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