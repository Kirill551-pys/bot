"""
МИГРАЦИЯ: Исправление is_active для пользователей с subscription_type = 'free'
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'subscribers.db')

def migrate():
    print(f" Подключаюсь к базе: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Находим всех пользователей с subscription_type = 'free' и is_active = 1
    cursor.execute("""
        SELECT user_id, username, first_name 
        FROM subscribers 
        WHERE subscription_type = 'free' AND is_active = 1
    """)
    free_users = cursor.fetchall()
    
    print(f"📊 Найдено {len(free_users)} пользователей с free-статусом и is_active=1")
    
    # 2. Обновляем их is_active на 0
    updated = 0
    for user_id, username, first_name in free_users:
        cursor.execute("""
            UPDATE subscribers 
            SET is_active = 0 
            WHERE user_id = ? AND subscription_type = 'free'
        """, (user_id,))
        updated += 1
        print(f"   ✅ Обновлен user {user_id} ({username or first_name or 'unknown'})")
    
    conn.commit()
    print(f"\n✅ Миграция завершена! Обновлено записей: {updated}")
    
    # 3. Проверяем результат
    cursor.execute("""
        SELECT subscription_type, is_active, COUNT(*) 
        FROM subscribers 
        GROUP BY subscription_type, is_active
    """)
    print("\n📈 Текущее распределение:")
    for sub_type, is_active, count in cursor.fetchall():
        print(f"   {sub_type} (is_active={is_active}): {count} пользователей")
    
    conn.close()

if __name__ == "__main__":
    migrate()