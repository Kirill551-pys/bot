import { useEffect, useState } from 'react';
import { useTelegram } from '../hooks/useTelegram';

// ==================== ТИПЫ ====================
interface BacktestMetric {
  accuracy: number;
  roi?: number;
  n_predictions: number;
  label: string;
}

interface ResultAgg {
  avg_accuracy: number;
  avg_roi: number;
  total_samples: number;
  n_leagues: number;
}

interface SimpleAgg {
  avg_accuracy: number;
  total_samples: number;
}

interface AggregatedMetrics {
  result: ResultAgg;
  total?: SimpleAgg;
  btts?: SimpleAgg;
  backtest: Record<string, BacktestMetric>;
  last_updated: string;
  disclaimer: string;
}

interface LeagueResult {
  accuracy: number;
  roi: number;
  n_samples: number;
  n_with_odds: number;
}

interface LeagueMetrics {
  league_name: string;
  result: LeagueResult;
  total: { accuracy: number; n_samples: number };
  btts: { accuracy: number; n_samples: number };
  training_date: string;
  n_matches: number;
}

interface MetricsResponse {
  aggregated: AggregatedMetrics;
  by_league: Record<string, LeagueMetrics>;
}

// ==================== КОНСТАНТЫ ====================
// 🔥 ВАЖНО: Явно указываем адрес бэкенда!
// Без этого Vite (порт 5173) вернёт index.html вместо JSON,
// и мы получим ошибку: Unexpected token '<', "<!doctype "... is not valid JSON
// Для продакшена замени на реальный домен, например https://tactika-bot.ru
const API_BASE_URL = ''; 

// ==================== КОМПОНЕНТ ====================
export function ModelMetrics() {
  // ✅ ПРАВИЛЬНО: деструктуризируем initData и isReady напрямую (не через tg)
  const { initData, isReady } = useTelegram();
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Защита: ждём готовности Telegram SDK
    if (!isReady) return;

    const fetchMetrics = async () => {
      try {
        setLoading(true);
        const res = await fetch(`${API_BASE_URL}/api/model/metrics`, {
          headers: {
            'X-Telegram-Init-Data': initData || '',
            'Content-Type': 'application/json',
          },
        });

        if (!res.ok) {
          throw new Error(`Сервер вернул ошибку ${res.status}`);
        }

        // 🔥 КРИТИЧНО: проверяем, что ответ действительно JSON
        const contentType = res.headers.get('content-type') || '';
        if (!contentType.includes('application/json')) {
          throw new Error(
            'Сервер вернул не-JSON (получил HTML). Проверь, что бэкенд запущен на ' + API_BASE_URL
          );
        }

        const data: MetricsResponse = await res.json();
        setMetrics(data);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Неизвестная ошибка');
      } finally {
        setLoading(false);
      }
    };

    fetchMetrics();
  }, [initData, isReady]);

  // ==================== СОСТОЯНИЕ: ЗАГРУЗКА ====================
  if (loading) {
    return (
      <div className="min-h-screen bg-linear-to-b from-slate-900 to-slate-800 p-4">
        <div className="max-w-2xl mx-auto space-y-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-32 bg-slate-800/50 rounded-2xl animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  // ==================== СОСТОЯНИЕ: ОШИБКА ====================
  if (error || !metrics) {
    return (
      <div className="min-h-screen bg-linear-to-b from-slate-900 to-slate-800 p-4 flex items-center justify-center">
        <div className="text-center text-red-400 px-6">
          <p className="text-4xl mb-2">⚠️</p>
          <p className="font-bold mb-2">Не удалось загрузить метрики</p>
          <p className="text-sm text-slate-400">{error || 'Нет данных'}</p>
          <p className="text-xs text-slate-500 mt-4">
            Убедись, что бэкенд запущен: <code className="text-orange-400">python main.py</code>
          </p>
        </div>
      </div>
    );
  }

  const { aggregated, by_league } = metrics;
  const leaguesList = Object.entries(by_league).sort(
    ([, a], [, b]) => b.result.accuracy - a.result.accuracy
  );

  // ==================== ОСНОВНОЙ РЕНДЕР ====================
  return (
    <div className="min-h-screen bg-linear-to-b from-slate-900 to-slate-800 p-4 pb-24">
      <div className="max-w-2xl mx-auto space-y-6">
        
        {/* 🎯 ЗАГОЛОВОК */}
        <div className="text-center space-y-2 fade-up">
          <h1 className="text-3xl font-bold text-white">
            📊 Качество модели
          </h1>
          <p className="text-slate-400 text-sm">
            Реальные метрики на основе{' '}
            {aggregated.result.total_samples.toLocaleString('ru-RU')} матчей
          </p>
        </div>

        {/* 💎 ГЛАВНЫЕ ЦИФРЫ */}
        <div className="grid grid-cols-3 gap-3 fade-up-1">
          <div className="bg-linear-to-br from-blue-500/20 to-blue-600/10 border border-blue-500/30 rounded-2xl p-4 text-center">
            <p className="text-3xl font-bold text-blue-400">
              {aggregated.result.avg_accuracy}%
            </p>
            <p className="text-xs text-slate-400 mt-1">Точность исходов</p>
          </div>
          <div className="bg-linear-to-br from-green-500/20 to-green-600/10 border border-green-500/30 rounded-2xl p-4 text-center">
            <p className="text-3xl font-bold text-green-400">
              {aggregated.result.avg_roi > 0 ? '+' : ''}
              {aggregated.result.avg_roi}%
            </p>
            <p className="text-xs text-slate-400 mt-1">ROI</p>
          </div>
          <div className="bg-linear-to-br from-purple-500/20 to-purple-600/10 border border-purple-500/30 rounded-2xl p-4 text-center">
            <p className="text-3xl font-bold text-purple-400">
              {aggregated.result.n_leagues}
            </p>
            <p className="text-xs text-slate-400 mt-1">Лиг в базе</p>
          </div>
        </div>

        {/* 🔥 МЕТРИКИ ИЗ БЭКТЕСТА */}
        {aggregated.backtest && Object.keys(aggregated.backtest).length > 0 && (
          <div className="bg-slate-800/50 border border-slate-700 rounded-2xl p-5 fade-up-2">
            <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
              🎯 Точность по рынкам
              <span className="text-xs font-normal text-slate-400">(бэктест)</span>
            </h2>
            <div className="space-y-3">
              {Object.entries(aggregated.backtest).map(([key, metric]) => (
                <div
                  key={key}
                  className="flex items-center justify-between py-2 border-b border-slate-700/50 last:border-0"
                >
                  <div className="flex-1">
                    <p className="text-sm text-white font-medium">{metric.label}</p>
                    <p className="text-xs text-slate-500">
                      {metric.n_predictions.toLocaleString('ru-RU')} прогнозов
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-lg font-bold text-blue-400">{metric.accuracy}%</p>
                    {metric.roi !== undefined && (
                      <p
                        className={`text-xs font-medium ${
                          metric.roi > 0 ? 'text-green-400' : 'text-red-400'
                        }`}
                      >
                        ROI {metric.roi > 0 ? '+' : ''}
                        {metric.roi}%
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 📈 ПО ЛИГАМ (топ-10) */}
        <div className="bg-slate-800/50 border border-slate-700 rounded-2xl p-5 fade-up-3">
          <h2 className="text-lg font-bold text-white mb-4">🏆 По лигам</h2>
          {leaguesList.length === 0 ? (
            <p className="text-slate-400 text-sm">Нет данных по лигам</p>
          ) : (
            <div className="space-y-2">
              {leaguesList.slice(0, 10).map(([key, league]) => (
                <div
                  key={key}
                  className="flex items-center justify-between py-2 border-b border-slate-700/50 last:border-0"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-white font-medium truncate">
                      {league.league_name}
                    </p>
                    <p className="text-xs text-slate-500">
                      {league.result.n_samples.toLocaleString('ru-RU')} матчей
                    </p>
                  </div>
                  <div className="flex gap-3">
                    <div className="text-right">
                      <p className="text-xs text-slate-400">Исход</p>
                      <p className="text-sm font-bold text-blue-400">
                        {league.result.accuracy}%
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-slate-400">ТБ 2.5</p>
                      <p className="text-sm font-bold text-green-400">
                        {league.total?.accuracy ?? 0}%
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-slate-400">ОЗ</p>
                      <p className="text-sm font-bold text-purple-400">
                        {league.btts?.accuracy ?? 0}%
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ⚠️ ДИСКЛЕЙМЕР */}
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl p-4 fade-up-3">
          <p className="text-xs text-amber-200/80 leading-relaxed">
            ⚠️ {aggregated.disclaimer}
          </p>
        </div>

        {/* 📅 ДАТА ОБНОВЛЕНИЯ */}
        <p className="text-center text-xs text-slate-500">
          Обновлено:{' '}
          {aggregated.last_updated
            ? new Date(aggregated.last_updated).toLocaleString('ru-RU')
            : '—'}
        </p>
      </div>
    </div>
  );
}