import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { useTelegram } from '../hooks/useTelegram';
import { Link } from 'react-router-dom';

export function Home() {
  const { user, hapticFeedback } = useTelegram();

  const { data: hot, isLoading } = useQuery({
    queryKey: ['hot-prediction'],
    queryFn: () => api.getHotPrediction(),
    refetchInterval: 60_000,
    retry: 0,
  });

  const confidence = Math.round(hot?.hot_confidence ?? 0);

  return (
    <div className="px-4 pt-4 pb-28 space-y-4">
      {/* ===== Шапка ===== */}
      <header className="fade-up flex items-center justify-between">
        <div>
          <p className="text-[13px] font-medium text-tg-hint">⚽ Тактика Ставок</p>
          <h1 className="text-[22px] leading-tight font-extrabold text-tg-text">
            Привет, {user?.first_name ?? 'друг'}! 👋
          </h1>
        </div>
        <div className="w-11 h-11 shrink-0 rounded-2xl bg-gradient-to-br from-tg-button to-accent-2 text-white text-lg font-extrabold flex items-center justify-center shadow-lg">
          {(user?.first_name?.[0] ?? '').toUpperCase()}
        </div>
      </header>

      {/* ===== Горячий прогноз ===== */}
      <section className="card card-hot fade-up-1 relative overflow-hidden">
        <div className="pointer-events-none absolute -top-12 -right-12 w-40 h-40 rounded-full bg-white/10" />
        <div className="pointer-events-none absolute -bottom-16 -left-10 w-44 h-44 rounded-full bg-black/10" />

        <div className="relative">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-[17px] font-extrabold text-white">🔥 Горячий прогноз</h2>
            <span className="live-badge">LIVE</span>
          </div>

          {isLoading ? (
            <div className="space-y-2.5">
              <div className="skeleton h-6 w-3/4" />
              <div className="skeleton h-4 w-1/2" />
              <div className="skeleton h-11 w-full rounded-xl" />
            </div>
          ) : hot ? (
            <>
              <p className="text-white/80 text-[13px] mb-1">🏆 {hot.league_name}</p>
              <p className="text-white text-lg font-extrabold leading-snug">
                {hot.home_team} — {hot.away_team}
              </p>

              <div className="mt-3 flex items-center gap-3">
                {/* Кольцо уверенности */}
                <div className="relative w-16 h-16 shrink-0">
                  <svg viewBox="0 0 36 36" className="w-16 h-16 -rotate-90">
                    <circle cx="18" cy="18" r="15.5" fill="none" stroke="rgba(255,255,255,.25)" strokeWidth="3.5" />
                    <circle cx="18" cy="18" r="15.5" fill="none" stroke="#fff" strokeWidth="3.5"
                      strokeLinecap="round" strokeDasharray={`${confidence * 0.974} 100`} />
                  </svg>
                  <span className="absolute inset-0 flex items-center justify-center text-white text-[15px] font-extrabold">
                    {confidence}%
                  </span>
                </div>
                <div className="min-w-0">
                  <p className="text-white text-[15px] font-bold truncate">💎 {hot.hot_bet}</p>
                  <p className="text-white/75 text-[12px] mt-0.5">{hot.trust_signal}</p>
                </div>
              </div>

              <Link
                to={`/prediction?team1=${encodeURIComponent(hot.home_team)}&team2=${encodeURIComponent(hot.away_team)}&league=${hot.league}`}
                onClick={() => hapticFeedback('medium')}
                className="mt-4 block w-full rounded-xl bg-white text-orange-600 text-center text-[15px] font-extrabold py-2.5 active:scale-[.97] transition-transform"
              >
                Подробнее →
              </Link>
            </>
          ) : (
            <>
              <p className="text-white/85 text-[14px] mb-3">
                Сейчас нет матчей с высокой уверенностью — выбери матч вручную.
              </p>
              <Link
                to="/prediction"
                onClick={() => hapticFeedback('medium')}
                className="block w-full rounded-xl bg-white text-orange-600 text-center text-[15px] font-extrabold py-2.5 active:scale-[.97] transition-transform"
              >
                Выбрать матч →
              </Link>
            </>
          )}
        </div>
      </section>

      {/* ===== Быстрые действия ===== */}
      <div className="grid grid-cols-2 gap-3 fade-up-2">
        <Link to="/prediction" onClick={() => hapticFeedback('light')} className="card action-card">
          <span className="action-icon bg-blue-500/15">⚽</span>
          <p className="font-bold text-[15px] text-tg-text mt-3">Выбрать матч</p>
          <p className="text-[12px] text-tg-hint mt-0.5">AI-прогноз на матч</p>
        </Link>
        <Link to="/stats" onClick={() => hapticFeedback('light')} className="card action-card">
          <span className="action-icon bg-emerald-500/15">📊</span>
          <p className="font-bold text-[15px] text-tg-text mt-3">Статистика</p>
          <p className="text-[12px] text-tg-hint mt-0.5">Цифры и тренды</p>
        </Link>
      </div>

      {/* ===== Преимущества ===== */}
      <section className="card fade-up-3 space-y-3">
        <h3 className="font-extrabold text-[15px] text-tg-text">Почему нам доверяют</h3>
        <Benefit icon="🤖" text="Модель v2.2: 12 рынков, включая угловые и карточки" />
        <Benefit icon="📈" text="ELO-рейтинги и форма команд в реальном времени" />
        <Benefit icon="🛡️" text="Уровень доверия к каждому прогнозу" />
      </section>
    </div>
  );
}

function Benefit({ icon, text }: { icon: string; text: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-9 h-9 shrink-0 rounded-xl bg-tg-button/10 flex items-center justify-center text-lg">{icon}</span>
      <p className="text-[13px] text-tg-text font-medium leading-snug">{text}</p>
    </div>
  );
}