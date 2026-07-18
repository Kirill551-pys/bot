# yookassa_payment.py
from yookassa import Configuration, Payment
import uuid
from datetime import datetime
from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, SUBSCRIPTION_PRICES
from database import activate_subscription, add_payment

# Настройка ЮKassa
Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_SECRET_KEY

async def create_payment(user_id: int, tariff: str, username: str = None) -> dict:
    """Создать платёж в ЮKassa"""
    if tariff not in SUBSCRIPTION_PRICES:
        return {'error': 'Неверный тариф'}
    
    tariff_info = SUBSCRIPTION_PRICES[tariff]
    amount = tariff_info['price']
    
    if amount == 0:  # Пробный период
        return {'error': 'Для пробного периода платёж не требуется'}
    
    # Создаём платёж
    payment = Payment.create({
        "amount": {
            "value": str(amount),
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": f"https://t.me/FootPrognosticBot?start=payment_success_{tariff}_{user_id}"
        },
        "capture": True,
        "description": f"Подписка '{tariff_info['name']}' для бота FootPrognosticBot",
        "metadata": {
            "user_id": str(user_id),
            "tariff": tariff,
            "username": username or ''
        },
        "idempotence_key": str(uuid.uuid4())
    })
    
    add_payment(user_id, amount, 'yookassa', payment.id, 'pending')
    
    return {
        'success': True,
        'payment_url': payment.confirmation_url,
        'payment_id': payment.id,
        'amount': amount
    }

async def confirm_payment(payment_id: str, user_id: int, tariff: str):
    """Подтвердить платёж после возврата из ЮKassa"""
    try:
        payment = Payment.find_one(payment_id)
        
        if payment.status == 'succeeded':
            # Активируем подписку
            days = SUBSCRIPTION_PRICES[tariff]['days']
            activate_subscription(user_id, tariff, days)
            
            update_payment_status(payment_id, 'completed')
            
            return {'success': True, 'days': days}
        else:
            return {'success': False, 'error': f'Платёж не завершён: {payment.status}'}
    
    except Exception as e:
        return {'success': False, 'error': str(e)}