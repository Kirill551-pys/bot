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
      queryClient.invalidateQueries({ queryKey: ['subscription'] });
    },
    onError: (error: any) => {
      showPopup('❌ ' + (error.response?.data?.detail || 'Ошибка'));
    }
  });

  const tariffs = [
    { key: 'weekly', name: 'Неделя', price: 149, days: 7, icon: '📅', perDay: 21 },
    { key: 'monthly', name: 'Месяц', price: 399, days: 30, icon: '📆', popular: true, perDay: 13 },
    { key: 'quarter', name: 'Квартал', price: 999, days: 90, icon: '🗓️', perDay: 11 },
    { key: 'lifetime', name: 'Навсегда', price: 3990, days: 3650, icon: '♾️', perDay: 1 },
  ];

  const handlePayment = (tariffKey: string) => {
    hapticFeedback('medium');
    showPopup(`💳 Оплата «${tariffs.find(t => t.key === tariffKey)?.name}» — скоро будет доступна!`);
  };

  const isActive = subscription && subscription.subscription_type !== 'free';

  return (
    <div className="p-4 space-y-5 max-w-lg mx-auto pb-28">
      <h1 className="text-[22px] font-extrabold text-white animate-fade-up">💎 Подписка</h1>

      {/* ===== Статус ===== */}
      <div className="card animate-fade-up delay-1 relative overflow-hidden">
        {isActive && (
          <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-green-500/10 to-transparent rounded-bl-full" />
        )}
        <div className="flex items-center gap-4">
          <div className={`w-14 h-14 rounded-2xl flex items-center justify-center text-2xl ${
            isActive ? 'bg-green-500/15' : 'bg-white/5'
          }`}>
            {isActive ? '✅' : '🔒'}
          </div>
          <div>
            <p className="text-[13px] text-[#8b9baa] font-medium">Ваш статус</p>
            {subscription ? (
              subscription.subscription_type === 'free' ? (
                <p className="text-white font-bold text-[16px]">Бесплатный доступ</p>
              ) : (
                <div>
                  <p className="font-extrabold text-green-400 text-[16px]">
                    {subscription.subscription_type === 'trial' ? '🎁 Пробный период' : '💎 VIP'}
                  </p>
                  {subscription.subscription_end && (
                    <p className="text-[12px] text-[#8b9baa] mt-0.5">
                      до {new Date(subscription.subscription_end).toLocaleDateString('ru-RU')}
                    </p>
                  )}
                </div>
              )
            ) : (
              <div className="skeleton h-5 w-32" />
            )}
          </div>
        </div>
      </div>

      {/* ===== Пробный период ===== */}
      {subscription?.subscription_type === 'free' && (
        <button
          onClick={() => trialMutation.mutate()}
          disabled={trialMutation.isPending}
          className="btn-primary w-full animate-fade-up delay-2 flex items-center justify-center gap-2"
        >
          {trialMutation.isPending ? (
            <>
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Активируем...
            </>
          ) : (
            <>🎁 Пробный период (3 дня) — Бесплатно</>
          )}
        </button>
      )}

      {/* ===== Тарифы ===== */}
      <div className="space-y-3 animate-fade-up delay-3">
        <h2 className="font-extrabold text-[16px] text-white px-1">📋 Тарифы</h2>

        {tariffs.map((tariff, idx) => (
          <div
            key={tariff.key}
            className={`tariff-card animate-fade-up`}
            style={{ animationDelay: `${0.1 + idx * 0.05}s`, opacity: 0 }}
          >
            {tariff.popular && (
              <div className="absolute top-0 right-5 -translate-y-1/2">
                <span className="badge badge-blue bg-blue-500 text-white shadow-lg shadow-blue-500/30 px-3 py-1">
                  ⭐ ПОПУЛЯРНЫЙ
                </span>
              </div>
            )}

            <div className="flex justify-between items-start mb-3">
              <div className="flex items-center gap-3">
                <span className="text-2xl">{tariff.icon}</span>
                <div>
                  <p className="font-extrabold text-white text-[16px]">{tariff.name}</p>
                  <p className="text-[12px] text-[#8b9baa]">{tariff.days} дней доступа</p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-[22px] font-extrabold text-white">{tariff.price}₽</p>
                <p className="text-[11px] text-[#8b9baa]">≈{tariff.perDay}₽/день</p>
              </div>
            </div>

            <button
              onClick={() => handlePayment(tariff.key)}
              className={`w-full py-3 rounded-xl font-bold text-[14px] transition-all active:scale-[.96] ${
                tariff.popular
                  ? 'bg-gradient-to-r from-blue-500 to-blue-600 text-white shadow-lg shadow-blue-500/25'
                  : 'bg-white/5 text-white border border-white/10'
              }`}
            >
              💳 Оплатить
            </button>
          </div>
        ))}
      </div>

      {/* ===== Преимущества ===== */}
      <div className="card animate-fade-up delay-4">
        <h2 className="font-extrabold text-[15px] text-white mb-4">✨ Что даёт подписка</h2>
        <div className="space-y-3.5">
          <Perk icon="✅" text="Безлимитные прогнозы на любые матчи" />
          <Perk icon="🔥" text="Горячие прогнозы с высокой уверенностью" />
          <Perk icon="📊" text="Расширенная статистика по всем лигам" />
          <Perk icon="🎯" text="Прогнозы на угловые, карточки, удары" />
          <Perk icon="⚡" text="Приоритетная обработка запросов" />
          <Perk icon="👥" text="Приоритетная поддержка 24/7" />
        </div>
      </div>

      {/* ===== Гарантия ===== */}
      <div className="text-center animate-fade-up delay-5">
        <p className="text-[12px] text-[#8b9baa] leading-relaxed">
          🛡️ Гарантия возврата в течение 24 часов,<br />
          если сервис не оправдал ожиданий
        </p>
      </div>
    </div>
  );
}

function Perk({ icon, text }: { icon: string; text: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-8 h-8 shrink-0 rounded-lg bg-white/5 flex items-center justify-center text-[15px]">
        {icon}
      </span>
      <p className="text-[13px] text-white/80 font-medium">{text}</p>
    </div>
  );
}