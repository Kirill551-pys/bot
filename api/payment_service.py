"""
СЕРВИС ПЛАТЕЖЕЙ ЮKASSA
✅ Создание платежей
✅ Обработка webhook уведомлений
"""
import os
import logging
from yookassa import Configuration, Payment
from yookassa.domain.notification import WebhookNotification, WebhookNotificationEventType

logger = logging.getLogger(__name__)

# Инициализация ЮKassa при импорте
Configuration.account_id = os.getenv("YOOKASSA_SHOP_ID")
Configuration.secret_key = os.getenv("YOOKASSA_SECRET_KEY")

# Маппинг тарифов на дни подписки
TARIFF_DAYS = {
    'promo_month': 30,
    'regular_month': 30,
    'winback_month': 30,
    'quarter': 90,
}

def create_payment(user_id: int, tariff: str, amount: float, description: str) -> dict:
    """Создаёт платёж в ЮKassa и возвращает ссылку на оплату."""
    try:
        if tariff not in TARIFF_DAYS:
            raise ValueError(f"Неизвестный тариф: {tariff}")
        
        payment = Payment.create({
            "amount": {
                "value": f"{amount:.2f}",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": os.getenv("YOOKASSA_RETURN_URL", "https://tactika-bot.ru/payment-success")
            },
            "capture": True,  # Автоматическое списание (не холдирование)
            "description": description,
            "metadata": {
                "user_id": str(user_id),
                "tariff": tariff,
                "days": str(TARIFF_DAYS[tariff])
            }
        })
        
        logger.info(f"✅ Платёж создан: {payment.id} для user {user_id}, тариф {tariff}, сумма {amount}₽")
        
        return {
            "payment_id": payment.id,
            "confirmation_url": payment.confirmation.confirmation_url,
            "amount": amount,
            "tariff": tariff
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания платежа: {e}")
        raise


def handle_webhook(event: dict) -> dict:
    """Обрабатывает webhook уведомление от ЮKassa."""
    try:
        notification = WebhookNotification(event)
        
        if notification.event != WebhookNotificationEventType.PAYMENT_SUCCEEDED:
            logger.info(f"⚠️ Игнорируем событие: {notification.event}")
            return {"status": "ignored", "event": notification.event}
        
        payment = notification.object
        user_id = int(payment.metadata.get("user_id", 0))
        tariff = payment.metadata.get("tariff", "regular_month")
        days = int(payment.metadata.get("days", 30))
        
        logger.info(f"💰 Оплата успешна! user_id={user_id}, tariff={tariff}, days={days}, payment_id={payment.id}")
        
        return {
            "status": "success",
            "user_id": user_id,
            "tariff": tariff,
            "days": days,
            "payment_id": payment.id,
            "amount": payment.amount.value
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки webhook: {e}")
        return {"status": "error", "error": str(e)}