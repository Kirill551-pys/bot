import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { useTelegram } from '../hooks/useTelegram';
import { Link } from 'react-router-dom';

export function Home() {
  const { user, hapticFeedback } = useTelegram();
  const { data: hot, isLoading, isError, refetch } = useQuery({
    queryKey: ['hot-prediction'],
    queryFn: () => api.getHotPrediction(),
    refetchInterval: 60_000,
    retry: 3,  // 3 попытки
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 10000), // 1с, 2с, 4с, макс 10с
    staleTime: 5 * 60 * 1000, // кэш на 5 минут
  });

  const confidence = Math.round(hot?.hot_confidence ?? 0);

  return (
    <div className="px-4 pt-5 pb-28 space-y-5 max-w-lg mx-auto">
      {/* ===== Шапка ===== */}
      <header className="animate-fade-up flex items-center justify-between">
        <div>
          <p className="text-[13px] font-medium text-[#8b9baa]">⚽ Тактика Ставок</p>
          <h1 className="text-[22px] leading-tight font-extrabold text-white mt-0.5">
            Привет, {user?.first_name ?? 'друг'}! 👋
          </h1>
        </div>
        <div className="w-11 h-11 shrink-0 rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600 text-white text-lg font-extrabold flex items-center justify-center shadow-lg shadow-blue-500/20">
          {(user?.first_name?.[0] ?? '⚽').toUpperCase()}
        </div>
      </header>

      {/* ===== Горячий прогноз ===== */}
      <section className="card-hot animate-fade-up delay-1 relative overflow-hidden rounded-2xl p-5">
        {/* Декоративные круги */}
        <div className="pointer-events-none absolute -top-12 -right-12 w-40 h-40 rounded-full bg-white/10" />
        <div className="pointer-events-none absolute -bottom-16 -left-10 w-44 h-44 rounded-full bg-black/10" />

        <div className="relative">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-[17px] font-extrabold text-white">🔥 Горячий прогноз</h2>
            <span className="live-badge">LIVE</span>
          </div>

          {/* 🆕 БЛОК ОШИБКИ — когда сервер спит */}
          {isError ? (
            <>
              <div className="flex items-center gap-2 mb-3">
                <span className="text-2xl">😴</span>
                <p className="text-white/90 text-[14px] font-bold">
                  Сервер просыпается...
                </p>
              </div>
              <p className="text-white/70 text-[13px] mb-4 leading-relaxed">
                Это займёт до 30 секунд при первом открытии.
                Попробуйте обновить через пару секунд.
              </p>
              <button
                onClick={() => refetch()}
                className="block w-full rounded-xl bg-white text-orange-600 text-center text-[15px] font-extrabold py-3 active:scale-[.96] transition-transform shadow-lg"
              >
                🔄 Попробовать снова
              </button>
            </>
          ) : isLoading ? (
            <div className="space-y-3">
              <div className="skeleton h-5 w-2/3" />
              <div className="skeleton h-6 w-3/4" />
              <div className="flex items-center gap-3 mt-3">
                <div className="skeleton w-16 h-16 rounded-full" />
                <div className="space-y-2 flex-1">
                  <div className="skeleton h-4 w-32" />
                  <div className="skeleton h-3 w-24" />
                </div>
              </div>
            </div>
          ) : hot ? (
            <>
              <p className="text-white/70 text-[13px] mb-1 font-medium">🏆 {hot.league_name}</p>
              <p className="text-white text-lg font-extrabold leading-snug">
                {hot.home_team} — {hot.away_team}
              </p>

              {/* Время матча */}
              {hot.commence_time && (
                <p className="text-white/50 text-[11px] mt-1">
                  ⏰ {new Date(hot.commence_time).toLocaleString('ru-RU', {
                    day: 'numeric',
                    month: 'short',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </p>
              )}

              <div className="mt-4 flex items-center gap-4">
                {/* Кольцо уверенности */}
                <div className="relative w-[72px] h-[72px] shrink-0">
                  <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
                    <circle cx="18" cy="18" r="15.5" fill="none" stroke="rgba(255,255,255,.2)" strokeWidth="3" />
                    <circle
                      cx="18" cy="18" r="15.5" fill="none" stroke="#fff" strokeWidth="3"
                      strokeLinecap="round"
                      strokeDasharray={`${confidence * 0.974} 100`}
                      style={{ transition: 'stroke-dasharray 1s ease' }}
                    />
                  </svg>
                  <span className="absolute inset-0 flex items-center justify-center text-white text-[16px] font-extrabold">
                    {confidence}%
                  </span>
                </div>

                <div className="min-w-0 flex-1">
                  <p className="text-white text-[15px] font-bold truncate">💎 {hot.hot_bet}</p>
                  <p className="text-white/70 text-[12px] mt-1 leading-snug">{hot.trust_signal}</p>

                  {/* Кэфы букмекеров (если есть) */}
                  {hot.odds && hot.odds.home_win && (
                    <div className="flex gap-2 mt-2">
                      <span className="bg-white/15 rounded px-2 py-0.5 text-[11px] font-bold text-white">
                        П1 {hot.odds.home_win}
                      </span>
                      <span className="bg-white/15 rounded px-2 py-0.5 text-[11px] font-bold text-white">
                        X {hot.odds.draw}
                      </span>
                      <span className="bg-white/15 rounded px-2 py-0.5 text-[11px] font-bold text-white">
                        П2 {hot.odds.away_win}
                      </span>
                    </div>
                  )}
                </div>
              </div>

              {/* 🆕 Дополнительные рынки (угловые, карточки) */}
              {hot.additional_markets && hot.additional_markets.length > 0 && (
                <div className="mt-3 pt-3 border-t border-white/15 space-y-2">
                  <p className="text-white/60 text-[11px] font-bold uppercase tracking-wider">
                    📊 Дополнительные рынки
                  </p>
                  {hot.additional_markets.map((market: any) => (
                    <div key={market.market} className="flex items-center justify-between bg-white/8 rounded-lg px-3 py-2">
                      {/* СЛЕВА: название + модель + букмекер */}
                      <div>
                        <p className="text-white text-[13px] font-bold">{market.label}</p>
                        <p className="text-white/50 text-[11px]">
                          Модель: {Math.round(market.probability * 100)}%
                        </p>
                        {/* 🆕 Реальный кэф и Value, если есть */}
                        {market.bookmaker_odds && (
                          <p className={`text-[10px] font-bold mt-0.5 ${market.value > 0 ? 'text-emerald-300' : 'text-white/40'}`}>
                            Букмекер: {market.bookmaker_odds}
                            {market.value > 0 && ` · Value +${Math.round(market.value * 100)}%`}
                          </p>
                        )}
                      </div>
                      {/* СПРАВА: справедливый кэф */}
                      <div className="text-right">
                        <p className="text-white text-[14px] font-extrabold">{market.fair_odds}</p>
                        <p className="text-white/50 text-[10px]">справедл. кэф</p>
                      </div>
                    </div>
                  ))}
                  <p className="text-white/40 text-[10px] italic mt-1">
                    💡 Ищите кэф выше справедливого в вашем букмекере
                  </p>
                </div>
              )}

              <Link
                to={`/prediction?team1=${encodeURIComponent(hot.home_team)}&team2=${encodeURIComponent(hot.away_team)}&league=${hot.league}`}
                onClick={() => hapticFeedback('medium')}
                className="mt-4 block w-full rounded-xl bg-white text-orange-600 text-center text-[15px] font-extrabold py-3 active:scale-[.96] transition-transform shadow-lg"
              >
                Смотреть прогноз →
              </Link>
            </>
          ) : (
            <>
              <p className="text-white/85 text-[14px] mb-4 leading-relaxed">
                Сейчас нет матчей с высокой уверенностью — выбери матч вручную.
              </p>
              <Link
                to="/prediction"
                onClick={() => hapticFeedback('medium')}
                className="block w-full rounded-xl bg-white text-orange-600 text-center text-[15px] font-extrabold py-3 active:scale-[.96] transition-transform shadow-lg"
              >
                Выбрать матч →
              </Link>
            </>
          )}
        </div>
      </section>

      {/* ===== Быстрые действия ===== */}
      <div className="grid grid-cols-2 gap-3 animate-fade-up delay-2">
        <Link to="/prediction" onClick={() => hapticFeedback('light')} className="card action-card">
          <span className="action-icon bg-blue-500/15">⚽</span>
          <p className="font-bold text-[15px] text-white mt-3">Выбрать матч</p>
          <p className="text-[12px] text-[#8b9baa] mt-0.5">AI-прогноз на матч</p>
        </Link>
        <Link to="/stats" onClick={() => hapticFeedback('light')} className="card action-card">
          <span className="action-icon bg-emerald-500/15">📊</span>
          <p className="font-bold text-[15px] text-white mt-3">Статистика</p>
          <p className="text-[12px] text-[#8b9baa] mt-0.5">Цифры и тренды</p>
        </Link>
      </div>

      {/* ===== Преимущества ===== */}
      <section className="card animate-fade-up delay-3 space-y-4">
        <h3 className="font-extrabold text-[15px] text-white">Почему нам доверяют</h3>
        <Benefit icon="🤖" text="Модель v2.3: 12 рынков, включая угловые и карточки" />
        <Benefit icon="📈" text="ELO-рейтинги и форма команд в реальном времени" />
        <Benefit icon="⚡" text="Мгновенная статистика без ожидания" />
      </section>

      {/* ===== CTA подписка ===== */}
      <Link
        to="/subscribe"
        onClick={() => hapticFeedback('light')}
        className="animate-fade-up delay-4 block card relative overflow-hidden border border-purple-500/20"
        style={{ background: 'linear-gradient(135deg, rgba(139,92,246,0.1), rgba(59,130,246,0.05))' }}
      >
        <div className="flex items-center gap-4">
          <span className="text-3xl animate-float">💎</span>
          <div>
            <p className="font-bold text-white text-[15px]">Открой все прогнозы</p>
            <p className="text-[13px] text-[#8b9baa] mt-0.5">Подписка от 149₽/нед</p>
          </div>
          <span className="ml-auto text-purple-400 text-xl">→</span>
        </div>
      </Link>
    </div>
  );
}

function Benefit({ icon, text }: { icon: string; text: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-10 h-10 shrink-0 rounded-xl bg-blue-500/10 flex items-center justify-center text-lg">
        {icon}
      </span>
      <p className="text-[13px] text-white/80 font-medium leading-snug">{text}</p>
    </div>
  );
}