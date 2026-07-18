"""
Middleware для проверки подписки пользователей
Работает с aiogram 3.x
"""
import logging
from datetime import datetime
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, User

from database import get_user_subscription, create_user

logger = logging.getLogger(__name__)


class SubscriptionMiddleware(BaseMiddleware):
    """
    Проверка подписки для ограничения доступа к премиум-функциям.
    
    Использование:
        # Для всех хендлеров:
        dp.message.middleware(SubscriptionMiddleware(premium_only=False))
        
        # Только для премиум-хендлеров:
        premium_router.message.middleware(SubscriptionMiddleware(premium_only=True))
    """
    
    def __init__(self, premium_only: bool = False):
        """
        :param premium_only: Если True — блокировать пользователей без активной подписки
        """
        self.premium_only = premium_only
    
    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        # Получаем пользователя из события
        user: User = getattr(event, 'from_user', None)
        if not user:
            logger.warning("⚠️ Не удалось получить пользователя из события")
            return await handler(event, data)
        
        user_id = user.id
        username = user.username
        first_name = user.first_name
        
        # Создаём пользователя в БД, если нет
        sub = get_user_subscription(user_id)
        if not sub:
            create_user(user_id, username, first_name)
            sub = get_user_subscription(user_id)
        
        # Проверяем истёкшие подписки
        if sub and sub.get('subscription_end'):
            try:
                end_date = datetime.fromisoformat(sub['subscription_end'])
                if datetime.now() > end_date:
                    # Подписка истекла — обновляем статус в БД
                    from database import activate_subscription
                    activate_subscription(user_id, 'free', 0)  # Сброс на free
                    sub['subscription_type'] = 'free'
                    sub['subscription_end'] = None
            except (ValueError, TypeError) as e:
                logger.error(f"❌ Ошибка парсинга даты подписки: {e}")
                sub['subscription_type'] = 'free'
        
        # Если режим премиум — блокируем доступ
        if self.premium_only:
            is_premium = (
                sub 
                and sub.get('subscription_type', 'free') != 'free' 
                and sub.get('is_active', False)
            )
            
            if not is_premium:
                # Формируем ответ в зависимости от типа события
                if isinstance(event, CallbackQuery):
                    await event.answer(
                        "⚠️ Эта функция доступна только по подписке\n💎 /subscribe",
                        show_alert=True
                    )
                elif isinstance(event, Message):
                    await event.answer(
                        "⚠️ Эта функция доступна только по подписке\n\n"
                        "💎 <b>Преимущества подписки:</b>\n"
                        "• Безлимитные прогнозы\n"
                        "• Горячие матчи с высокой уверенностью\n"
                        "• Расширенная статистика по лигам\n"
                        "• Приоритетная поддержка\n\n"
                        "Активировать: /subscribe",
                        parse_mode="HTML"
                    )
                # Прерываем цепочку — хендлер не выполнится
                return None
        
        # Сохраняем информацию о подписке в контекст для хендлеров
        data['subscription'] = sub
        data['user_id'] = user_id
        
        # Передаём управление дальше
        return await handler(event, data)