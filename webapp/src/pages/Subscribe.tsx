import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { useTelegram } from '../hooks/useTelegram';
import type { UserSubscription } from '../api/client';

export function Subscribe() {
  const { showPopup, hapticFeedback } = useTelegram();
  const queryClient = useQueryClient();
  
  const { data: subscription } = useQuery<UserSubscription>({
    queryKey: ['subscription'],
    queryFn: () => api.getUserSubscription(),
  });

  const trialMutation = useMutation({
    mutationFn: () => api.activateTrial(),
    onSuccess: () => {
      showPopup('✅ Пробный период активирован на 3 дня!');
      hapticFeedback('medium');
      // Обновляем данные подписки
      queryClient.invalidateQueries({ queryKey: ['subscription'] });
    },
    onError: (error: any) => {
      showPopup('❌ ' + (error.response?.data?.detail || 'Ошибка'));
    }
  });

  const tariffs = [
    { key: 'weekly', name: 'Неделя', price: 149, days: 7, icon: '📅' },
    { key: 'monthly', name: 'Месяц', price: 399, days: 30, icon: '📆', popular: true },
    { key: 'quarter', name: 'Квартал', price: 999, days: 90, icon: '📆' },
    { key: 'lifetime', name: 'Навсегда', price: 3990, days: 3650, icon: '♾️' },
  ];

  const handlePayment = (tariffKey: string) => {
    hapticFeedback('medium');
    showPopup(`💳 Оплата ${tariffKey} — скоро будет доступна!`);
  };

  return (
    <div className="p-4 space-y-4">
      <h1 className="text-2xl font-bold">💎 Подписка</h1>

      {/* Статус */}
      <div className="card">
        <h2 className="font-semibold mb-2">📊 Ваш статус:</h2>
        {subscription ? (
          <div>
            {subscription.subscription_type === 'free' ? (
              <p className="text-tg-hint">❌ Нет активной подписки</p>
            ) : (
              <div>
                <p className="font-semibold text-green-600">
                  ✅ {subscription.subscription_type}
                </p>
                {subscription.subscription_end && (
                  <p className="text-sm text-tg-hint">
                    До {new Date(subscription.subscription_end).toLocaleDateString('ru-RU')}
                  </p>
                )}
              </div>
            )}
          </div>
        ) : (
          <p className="text-tg-hint">Загрузка...</p>
        )}
      </div>

      {/* Пробный период */}
      {subscription?.subscription_type === 'free' && (
        <button
          onClick={() => trialMutation.mutate()}
          disabled={trialMutation.isPending}
          className="btn-primary w-full"
        >
          {trialMutation.isPending ? 'Активируем...' : '🎁 Пробный период (3 дня) — Бесплатно'}
        </button>
      )}

      {/* Тарифы */}
      <div className="card space-y-3">
        <h2 className="font-semibold">📋 Тарифы:</h2>
        
        {tariffs.map((tariff) => (
          <div
            key={tariff.key}
            className={`p-4 rounded-xl border-2 transition-all ${
              tariff.popular
                ? 'border-tg-button bg-tg-button/10 shadow-lg'
                : 'border-gray-300 bg-tg-secondary'
            }`}
          >
            <div className="flex justify-between items-center mb-2">
              <div>
                <div className="font-bold text-lg">
                  {tariff.icon} {tariff.name}
                  {tariff.popular && <span className="ml-2 text-xs bg-tg-button text-white px-2 py-1 rounded-full">⭐ ПОПУЛЯРНЫЙ</span>}
                </div>
                <div className="text-sm text-tg-hint">{tariff.days} дней доступа</div>
              </div>
              <div className="text-2xl font-bold">{tariff.price}₽</div>
            </div>
            <button
              onClick={() => handlePayment(tariff.key)}
              className="w-full mt-2 py-2 rounded-lg bg-tg-button text-white font-semibold active:scale-95 transition-transform"
            >
              💳 Оплатить
            </button>
          </div>
        ))}
      </div>

      {/* Преимущества */}
      <div className="card">
        <h2 className="font-semibold mb-3">✨ Что даёт подписка:</h2>
        <ul className="space-y-2 text-sm">
          <li className="flex items-start gap-2">
            <span>✅</span>
            <span>Безлимитные прогнозы на любые матчи</span>
          </li>
          <li className="flex items-start gap-2">
            <span>🔥</span>
            <span>Горячие прогнозы с высокой уверенностью</span>
          </li>
          <li className="flex items-start gap-2">
            <span>📊</span>
            <span>Расширенная статистика по всем лигам</span>
          </li>
          <li className="flex items-start gap-2">
            <span>🎯</span>
            <span>Прогнозы на угловые и карточки</span>
          </li>
          <li className="flex items-start gap-2">
            <span>👥</span>
            <span>Приоритетная поддержка</span>
          </li>
        </ul>
      </div>
    </div>
  );
}