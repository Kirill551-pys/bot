import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { useTelegram } from '../hooks/useTelegram';
import { useSearchParams } from 'react-router-dom';
import type { League, Prediction } from '../api/client';

export function Prediction() {
  const { hapticFeedback } = useTelegram();
  const [searchParams] = useSearchParams();
  
  const [selectedLeague, setSelectedLeague] = useState<string>(
    searchParams.get('league') || ''
  );
  const [team1, setTeam1] = useState<string>(
    searchParams.get('team1') || ''
  );
  const [team2, setTeam2] = useState<string>(
    searchParams.get('team2') || ''
  );

  const { data: leagues } = useQuery<League[]>({
    queryKey: ['leagues'],
    queryFn: () => api.getLeagues(),
  });

  const { data: teams } = useQuery<string[]>({
    queryKey: ['teams', selectedLeague],
    queryFn: () => api.getTeams(selectedLeague),
    enabled: !!selectedLeague,
  });

  const { data: prediction, isLoading: isPredicting } = useQuery<Prediction>({
    queryKey: ['prediction', team1, team2, selectedLeague],
    queryFn: () => api.getMatchPrediction(team1, team2, selectedLeague),
    enabled: !!team1 && !!team2 && !!selectedLeague,
  });

  return (
    <div className="p-4 space-y-4 pb-24">
      <h1 className="text-2xl font-bold text-center">⚽ Выбор матча</h1>

      {/* 1. ФИЛЬТРЫ */}
      <div className="card space-y-3">
        <div>
          <label className="block text-sm font-semibold mb-1.5 text-tg-hint">🏆 Лига</label>
          <select
            value={selectedLeague}
            onChange={(e) => {
              setSelectedLeague(e.target.value);
              setTeam1('');
              setTeam2('');
              hapticFeedback('light');
            }}
            className="w-full p-2.5 rounded-xl bg-tg-secondary border border-gray-300 dark:border-gray-700 focus:ring-2 focus:ring-tg-button outline-none transition-all"
          >
            <option value="">-- Выберите лигу --</option>
            {leagues?.map((league: League) => (
              <option key={league.key} value={league.key}>
                {league.name} ({league.teams_count} команд)
              </option>
            ))}
          </select>
        </div>

        {selectedLeague && teams && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-semibold mb-1.5 text-tg-hint">🏠 Хозяева</label>
              <select
                value={team1}
                onChange={(e) => { setTeam1(e.target.value); hapticFeedback('light'); }}
                className="w-full p-2.5 rounded-xl bg-tg-secondary border border-gray-300 dark:border-gray-700 focus:ring-2 focus:ring-tg-button outline-none transition-all"
              >
                <option value="">-- Выбор --</option>
                {teams.map((team: string) => (
                  <option key={team} value={team}>{team}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-semibold mb-1.5 text-tg-hint">🚌 Гости</label>
              <select
                value={team2}
                onChange={(e) => { setTeam2(e.target.value); hapticFeedback('light'); }}
                className="w-full p-2.5 rounded-xl bg-tg-secondary border border-gray-300 dark:border-gray-700 focus:ring-2 focus:ring-tg-button outline-none transition-all"
              >
                <option value="">-- Выбор --</option>
                {teams.filter((t: string) => t !== team1).map((team: string) => (
                  <option key={team} value={team}>{team}</option>
                ))}
              </select>
            </div>
          </div>
        )}
      </div>

      {/* 2. ЗАГРУЗКА */}
      {isPredicting && (
        <div className="card text-center py-8">
          <div className="animate-spin rounded-full h-12 w-12 border-4 border-tg-button border-t-transparent mx-auto mb-3" />
          <p className="text-tg-hint font-medium">Анализируем статистику и генерируем прогноз...</p>
        </div>
      )}

      {/* 3. РЕЗУЛЬТАТ ПРОГНОЗА */}
      {prediction && !isPredicting && (
        <div className="space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
          
          {/* Заголовок матча */}
          <div className="card text-center bg-gradient-to-br from-tg-secondary to-tg-bg border-t-4 border-tg-button">
            <h2 className="text-xl font-bold leading-tight">
              {prediction.home_team} <span className="text-tg-hint font-normal">vs</span> {prediction.away_team}
            </h2>
            <p className="text-sm text-tg-hint mt-1">Прогноз от AI-модели v2.2</p>
          </div>

          {/* Основной рынок */}
          <Section title="🏆 Победитель матча">
            <ProbabilityBar label={prediction.home_team} value={prediction.result['Home Win']} isFavorite={prediction.result['Home Win'] >= 0.5} />
            <ProbabilityBar label="Ничья" value={prediction.result['Draw']} />
            <ProbabilityBar label={prediction.away_team} value={prediction.result['Away Win']} isFavorite={prediction.result['Away Win'] >= 0.5} />
          </Section>

          {/* Голы */}
          <Section title="⚽ Голы">
            <SubSection title="Тотал 2.5">
              <ProbabilityBar label="Больше (ТБ)" value={prediction.total_goals['Over 2.5']} />
              <ProbabilityBar label="Меньше (ТМ)" value={prediction.total_goals['Under 2.5']} />
            </SubSection>
            <SubSection title="Обе забьют (ОЗ)">
              <ProbabilityBar label="Да" value={prediction.both_scored['Yes']} />
              <ProbabilityBar label="Нет" value={prediction.both_scored['No']} />
            </SubSection>
          </Section>

          {/* 1-й тайм */}
          {(prediction.first_half_result || prediction.btts_first_half) && (
            <Section title="⏱️ 1-й тайм">
              {prediction.first_half_result && (
                <SubSection title="Исход">
                  <ProbabilityBar label={`${prediction.home_team} (П1)`} value={prediction.first_half_result['Home Win']} />
                  <ProbabilityBar label="Ничья" value={prediction.first_half_result['Draw']} />
                  <ProbabilityBar label={`${prediction.away_team} (П2)`} value={prediction.first_half_result['Away Win']} />
                </SubSection>
          )}
          {prediction.btts_first_half && (
            <SubSection title="Обе забьют в 1-м тайме">
              <ProbabilityBar label="Да" value={prediction.btts_first_half['Yes']} />
              <ProbabilityBar label="Нет" value={prediction.btts_first_half['No']} />
            </SubSection> 
          )}
          </Section>
          )}    
          {/* Статистика матча (Сетка для компактности) */}
          {(prediction.total_shots || prediction.total_shots_on_target || prediction.total_fouls) && (
            <Section title="📊 Статистика матча">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {prediction.total_shots && (
                  <SubSection title="Всего ударов (ТБ 22.5)">
                    <ProbabilityBar label="Больше" value={prediction.total_shots['Over 22.5']} />
                    <ProbabilityBar label="Меньше" value={prediction.total_shots['Under 22.5']} />
                  </SubSection>
                )}
                {prediction.total_shots_on_target && (
                  <SubSection title="Удары в створ (ТБ 8.5)">
                    <ProbabilityBar label="Больше" value={prediction.total_shots_on_target['Over 8.5']} />
                    <ProbabilityBar label="Меньше" value={prediction.total_shots_on_target['Under 8.5']} />
                  </SubSection>
                )}
                {prediction.total_fouls && (
                  <SubSection title="Всего фолов (ТБ 23.5)">
                    <ProbabilityBar label="Больше" value={prediction.total_fouls['Over 23.5']} />
                    <ProbabilityBar label="Меньше" value={prediction.total_fouls['Under 23.5']} />
                  </SubSection>
                )}
              </div>
            </Section>
          )}

          {/* Индивидуальные тоталы */}
          {prediction.individual_totals && (
            <Section title="⚽ Индивидуальные тоталы (ТБ 1.5)">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {Object.entries(prediction.individual_totals)
                  .filter(([key]) => key.includes('Over 1.5'))
                  .map(([key, value]) => (
                    <ProbabilityBar 
                      key={key} 
                      label={key.replace(' Over 1.5', '')} 
                      value={value} 
                    />
                  ))}
              </div>
            </Section>
          )}

          {/* Угловые и Карточки (если есть в ответе) */}
          {(prediction.corners || prediction.cards) && (
            <Section title="🎯 Стандарты и дисциплина">
              {prediction.corners && (
                <SubSection title="Угловые (ТБ 9.5 / 10.5)">
                  <ProbabilityBar label="ТБ 9.5" value={prediction.corners['Over 9.5']} />
                  <ProbabilityBar label="ТБ 10.5" value={prediction.corners['Over 10.5']} />
                </SubSection>
              )}
              {prediction.cards && (
                <SubSection title="Желтые карточки (ТБ 3.5 / 4.5)">
                  <ProbabilityBar label="ТБ 3.5" value={prediction.cards['Over 3.5']} />
                  <ProbabilityBar label="ТБ 4.5" value={prediction.cards['Over 4.5']} />
                </SubSection>
              )}
            </Section>
          )}

          {/* Итоговая рекомендация */}
          <div className="card bg-tg-secondary/50 border-l-4 border-l-tg-button space-y-3">
            {prediction.recommendation && (
              <div>
                <h3 className="font-bold text-lg mb-1">💡 Рекомендация модели:</h3>
                <p className="text-sm leading-relaxed whitespace-pre-line text-tg-text">{prediction.recommendation}</p>
              </div>
            )}
            <div className="pt-3 border-t border-gray-200 dark:border-gray-700 text-center">
              <p className="text-xs uppercase tracking-wider text-tg-hint font-semibold mb-1">🛡️ Уровень доверия</p>
              <p className="text-lg font-bold text-tg-button">{prediction.trust_signal}</p>
            </div>
          </div>

        </div>
      )}
    </div>
  );
}

// ==================== ВСПОМОГАТЕЛЬНЫЕ КОМПОНЕНТЫ ====================

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card space-y-3">
      <h3 className="font-bold text-base border-b border-gray-200 dark:border-gray-700 pb-2 mb-1">{title}</h3>
      {children}
    </div>
  );
}

function SubSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <h4 className="text-sm font-semibold text-tg-hint">{title}</h4>
      {children}
    </div>
  );
}

function ProbabilityBar({ label, value, isFavorite = false }: { label: string; value: number; isFavorite?: boolean }) {
  const percentage = (value * 100).toFixed(0);
  
  return (
    <div className="group">
      <div className="flex justify-between text-sm mb-1.5">
        <span className={`font-medium ${isFavorite ? 'text-tg-button' : ''}`}>{label}</span>
        <span className={`font-bold ${isFavorite ? 'text-tg-button' : 'text-tg-text'}`}>{percentage}%</span>
      </div>
      <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2.5 overflow-hidden">
        <div
          className={`h-2.5 rounded-full transition-all duration-500 ease-out ${isFavorite ? 'bg-tg-button' : 'bg-tg-hint/60 group-hover:bg-tg-hint'}`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}