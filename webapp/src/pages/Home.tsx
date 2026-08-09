import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { useTelegram } from '../hooks/useTelegram';
import { Link } from 'react-router-dom';

export function Home() {
  const { user, hapticFeedback } = useTelegram();
  
  const { data: hot, isLoading, error } = useQuery({
    queryKey: ['hot-prediction'],
    queryFn: () => api.getHotPrediction(),
    refetchInterval: 60000,
  });

  return (
    <div className="p-4 space-y-4">
      {/* Приветствие */}
      <div className="card bg-gradient-to-br from-blue-500 to-purple-600 text-white shadow-xl">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">👋 Привет, {user?.first_name}!</h1>
            <p className="text-white/80 text-sm mt-1">Готов к прогнозам?</p>
          </div>
          <span className="text-4xl">⚽</span>
        </div>
      </div>

      {/* Горячий прогноз */}
      <div className="card bg-gradient-to-br from-orange-500 to-red-500 text-white">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xl font-bold">🔥 Горячий прогноз</h2>
          <span className="text-xs bg-white/20 px-2 py-1 rounded-full">LIVE</span>
        </div>

        {isLoading ? (
          <div className="animate-pulse space-y-2">
            <div className="h-6 bg-white/20 rounded" />
            <div className="h-4 bg-white/20 rounded w-3/4" />
          </div>
        ) : error || !hot ? (
          <div>
            <p className="opacity-90 mb-3">Сегодня нет матчей с высокой уверенностью</p>
            <Link
              to="/prediction"
              className="block w-full bg-white text-orange-500 text-center py-2 rounded-xl font-semibold active:scale-95 transition-transform"
              onClick={() => hapticFeedback('medium')}
            >
              Выбрать матч вручную →
            </Link>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="text-lg font-semibold">
              {hot.home_team} <span className="opacity-70">vs</span> {hot.away_team}
            </div>
            <div className="text-sm opacity-90">
              🏆 {hot.league_name}
            </div>
            <div className="text-3xl font-bold">
              {hot.hot_confidence.toFixed(0)}%
            </div>
            <div className="text-sm opacity-90">
              💎 {hot.hot_bet}
            </div>
            <Link
              to={`/prediction?team1=${encodeURIComponent(hot.home_team)}&team2=${encodeURIComponent(hot.away_team)}&league=${hot.league}`}
              className="block w-full bg-white text-orange-500 text-center py-2 rounded-xl font-semibold mt-3 active:scale-95 transition-transform"
              onClick={() => hapticFeedback('medium')}
            >
              Подробнее →
            </Link>
          </div>
        )}
      </div>

      {/* Быстрые действия */}
      <div className="grid grid-cols-2 gap-3">
        <Link to="/prediction" className="card text-center active:scale-95 transition-transform">
          <div className="text-3xl mb-2">⚽</div>
          <div className="font-semibold">Выбрать матч</div>
        </Link>
        <Link to="/stats" className="card text-center active:scale-95 transition-transform">
          <div className="text-3xl mb-2">📊</div>
          <div className="font-semibold">Статистика</div>
        </Link>
      </div>
    </div>
  );
}