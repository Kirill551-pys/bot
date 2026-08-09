import { useState, useMemo } from 'react';
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
  const [team1, setTeam1] = useState<string>(searchParams.get('team1') || '');
  const [team2, setTeam2] = useState<string>(searchParams.get('team2') || '');
  const [teamSearch, setTeamSearch] = useState('');

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

  // Фильтрация команд по поиску
  const filteredTeams = useMemo(() => {
    if (!teams) return [];
    if (!teamSearch) return teams;
    const q = teamSearch.toLowerCase();
    return teams.filter(t => t.toLowerCase().includes(q));
  }, [teams, teamSearch]);

  // Своп команд
  const swapTeams = () => {
    setTeam1(team2);
    setTeam2(team1);
    hapticFeedback('medium');
  };

  return (
    <div className="p-4 space-y-4 pb-28 max-w-lg mx-auto">
      <h1 className="text-[22px] font-extrabold text-white animate-fade-up">⚽ Выбор матча</h1>

      {/* ===== 1. ВЫБОР ЛИГИ ===== */}
      <div className="card space-y-4 animate-fade-up delay-1">
        <div>
          <label className="block text-[13px] font-bold mb-2 text-[#8b9baa] uppercase tracking-wide">
            🏆 Лига
          </label>
          <select
            value={selectedLeague}
            onChange={(e) => {
              setSelectedLeague(e.target.value);
              setTeam1('');
              setTeam2('');
              hapticFeedback('light');
            }}
            className="select-modern"
          >
            <option value="">-- Выберите лигу --</option>
            {leagues?.map((league: League) => (
              <option key={league.key} value={league.key}>
                {league.name} ({league.teams_count} команд)
              </option>
            ))}
          </select>
        </div>

        {/* ===== 2. ВЫБОР КОМАНД ===== */}
        {selectedLeague && teams && (
          <div className="space-y-3 animate-fade-in">
            {/* Поиск */}
            <div className="relative">
              <span className="absolute left-4 top-1/2 -translate-y-1/2 text-[#8b9baa]">🔍</span>
              <input
                type="text"
                value={teamSearch}
                onChange={(e) => setTeamSearch(e.target.value)}
                placeholder="Поиск команды..."
                className="search-input"
              />
            </div>

            {/* Команды с кнопкой свопа */}
            <div className="grid grid-cols-[1fr_auto_1fr] gap-2 items-end">
              <div>
                <label className="block text-[12px] font-bold mb-1.5 text-[#8b9baa]">🏠 Хозяева</label>
                <select
                  value={team1}
                  onChange={(e) => { setTeam1(e.target.value); hapticFeedback('light'); }}
                  className="select-modern text-sm"
                >
                  <option value="">--</option>
                  {filteredTeams.map((team: string) => (
                    <option key={team} value={team}>{team}</option>
                  ))}
                </select>
              </div>

              {/* Кнопка свопа */}
              <button onClick={swapTeams} className="swap-btn mb-1" title="Поменять местами">
                ⇄
              </button>

              <div>
                <label className="block text-[12px] font-bold mb-1.5 text-[#8b9baa]">🚌 Гости</label>
                <select
                  value={team2}
                  onChange={(e) => { setTeam2(e.target.value); hapticFeedback('light'); }}
                  className="select-modern text-sm"
                >
                  <option value="">--</option>
                  {filteredTeams.filter((t: string) => t !== team1).map((team: string) => (
                    <option key={team} value={team}>{team}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ===== 3. ЗАГРУЗКА ===== */}
      {isPredicting && (
        <div className="card text-center py-10 animate-scale-in">
          <div className="relative w-14 h-14 mx-auto mb-4">
            <div className="absolute inset-0 rounded-full border-4 border-blue-500/20" />
            <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-blue-500 animate-spin" />
          </div>
          <p className="text-[#8b9baa] font-medium text-sm">
            Анализируем статистику и генерируем прогноз...
          </p>
        </div>
      )}

      {/* ===== 4. РЕЗУЛЬТАТ ===== */}
      {prediction && !isPredicting && (
        <div className="space-y-4">
          {/* Заголовок матча */}
          <div className="card text-center relative overflow-hidden animate-fade-up border-t-2 border-t-blue-500">
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-24 h-1 bg-gradient-to-r from-transparent via-blue-500 to-transparent rounded-full" />
            <h2 className="text-xl font-extrabold text-white leading-tight mt-2">
              {prediction.home_team} <span className="text-[#8b9baa] font-normal text-base mx-1">vs</span> {prediction.away_team}
            </h2>
            <p className="text-[12px] text-[#8b9baa] mt-2 flex items-center justify-center gap-1.5">
              <span className="badge badge-blue">🤖 AI v2.2</span>
              {prediction.is_hot && <span className="badge badge-gold animate-live">🔥 HOT</span>}
            </p>
          </div>

          {/* Победитель матча */}
          <Section title="🏆 Победитель матча" delay={1}>
            <ProbabilityBar label={prediction.home_team} value={prediction.result['Home Win']} color="blue" isFavorite={prediction.result['Home Win'] >= 0.5} />
            <ProbabilityBar label="Ничья" value={prediction.result['Draw']} color="gray" />
            <ProbabilityBar label={prediction.away_team} value={prediction.result['Away Win']} color="orange" isFavorite={prediction.result['Away Win'] >= 0.5} />
          </Section>

          {/* Голы */}
          <Section title="⚽ Голы" delay={2}>
            <SubSection title="Тотал 2.5">
              <ProbabilityBar label="Больше (ТБ)" value={prediction.total_goals['Over 2.5']} color="green" />
              <ProbabilityBar label="Меньше (ТМ)" value={prediction.total_goals['Under 2.5']} color="gray" />
            </SubSection>
            <div className="divider" />
            <SubSection title="Обе забьют (ОЗ)">
              <ProbabilityBar label="Да" value={prediction.both_scored['Yes']} color="green" />
              <ProbabilityBar label="Нет" value={prediction.both_scored['No']} color="gray" />
            </SubSection>
          </Section>

          {/* 1-й тайм */}
          {(prediction.first_half_result || prediction.btts_first_half) && (
            <Section title="⏱️ 1-й тайм" delay={3}>
              {prediction.first_half_result && (
                <>
                  <SubSection title="Исход">
                    <ProbabilityBar label={`${prediction.home_team} (П1)`} value={prediction.first_half_result['Home Win']} color="blue" />
                    <ProbabilityBar label="Ничья" value={prediction.first_half_result['Draw']} color="gray" />
                    <ProbabilityBar label={`${prediction.away_team} (П2)`} value={prediction.first_half_result['Away Win']} color="orange" />
                  </SubSection>
                  <div className="divider" />
                </>
              )}
              {prediction.btts_first_half && (
                <SubSection title="Обе забьют в 1-м тайме">
                  <ProbabilityBar label="Да" value={prediction.btts_first_half['Yes']} color="green" />
                  <ProbabilityBar label="Нет" value={prediction.btts_first_half['No']} color="gray" />
                </SubSection>
              )}
            </Section>
          )}

          {/* Статистика матча */}
          {(prediction.total_shots || prediction.total_shots_on_target || prediction.total_fouls) && (
            <Section title="📊 Статистика матча" delay={3}>
              <div className="grid grid-cols-1 gap-4">
                {prediction.total_shots && (
                  <SubSection title="Всего ударов (ТБ 22.5)">
                    <ProbabilityBar label="Больше" value={prediction.total_shots['Over 22.5']} color="blue" />
                    <ProbabilityBar label="Меньше" value={prediction.total_shots['Under 22.5']} color="gray" />
                  </SubSection>
                )}
                {prediction.total_shots_on_target && (
                  <>
                    <div className="divider" />
                    <SubSection title="Удары в створ (ТБ 8.5)">
                      <ProbabilityBar label="Больше" value={prediction.total_shots_on_target['Over 8.5']} color="blue" />
                      <ProbabilityBar label="Меньше" value={prediction.total_shots_on_target['Under 8.5']} color="gray" />
                    </SubSection>
                  </>
                )}
                {prediction.total_fouls && (
                  <>
                    <div className="divider" />
                    <SubSection title="Всего фолов (ТБ 23.5)">
                      <ProbabilityBar label="Больше" value={prediction.total_fouls['Over 23.5']} color="orange" />
                      <ProbabilityBar label="Меньше" value={prediction.total_fouls['Under 23.5']} color="gray" />
                    </SubSection>
                  </>
                )}
              </div>
            </Section>
          )}

          {/* Индивидуальные тоталы */}
          {prediction.individual_totals && (
            <Section title="⚽ Индивидуальные тоталы (ТБ 1.5)" delay={4}>
              <div className="grid grid-cols-1 gap-3">
                {Object.entries(prediction.individual_totals)
                  .filter(([key]) => key.includes('Over 1.5'))
                  .map(([key, value]) => (
                    <ProbabilityBar
                      key={key}
                      label={key.replace(' Over 1.5', '')}
                      value={value}
                      color="green"
                    />
                  ))}
              </div>
            </Section>
          )}

          {/* Угловые и карточки */}
          {(prediction.corners || prediction.cards) && (
            <Section title="🎯 Стандарты и дисциплина" delay={4}>
              {prediction.corners && (
                <>
                  <SubSection title="Угловые">
                    <ProbabilityBar label="ТБ 9.5" value={prediction.corners['Over 9.5']} color="blue" />
                    <ProbabilityBar label="ТБ 10.5" value={prediction.corners['Over 10.5']} color="blue" />
                  </SubSection>
                  <div className="divider" />
                </>
              )}
              {prediction.cards && (
                <SubSection title="Жёлтые карточки">
                  <ProbabilityBar label="ТБ 3.5" value={prediction.cards['Over 3.5']} color="orange" />
                  <ProbabilityBar label="ТБ 4.5" value={prediction.cards['Over 4.5']} color="orange" />
                </SubSection>
              )}
            </Section>
          )}

          {/* Рекомендация */}
          <div className="card animate-fade-up delay-5 relative overflow-hidden border-l-4 border-l-blue-500">
            {prediction.recommendation && (
              <div className="mb-4">
                <h3 className="font-extrabold text-white text-[16px] mb-2">💡 Рекомендация модели</h3>
                <p className="text-[14px] leading-relaxed whitespace-pre-line text-white/75">
                  {prediction.recommendation}
                </p>
              </div>
            )}
            <div className="pt-3 border-t border-white/10 text-center">
              <p className="text-[11px] uppercase tracking-widest text-[#8b9baa] font-bold mb-1">
                🛡️ Уровень доверия
              </p>
              <p className="text-lg font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-purple-400">
                {prediction.trust_signal}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ==================== ВСПОМОГАТЕЛЬНЫЕ КОМПОНЕНТЫ ====================

function Section({ title, children, delay = 0 }: { title: string; children: React.ReactNode; delay?: number }) {
  return (
    <div className={`card space-y-3 animate-fade-up delay-${Math.min(delay, 5)}`}>
      <h3 className="font-extrabold text-[15px] text-white border-b border-white/8 pb-2.5">
        {title}
      </h3>
      {children}
    </div>
  );
}

function SubSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2.5">
      <h4 className="text-[13px] font-bold text-[#8b9baa]">{title}</h4>
      {children}
    </div>
  );
}

function ProbabilityBar({
  label,
  value,
  color = 'blue',
  isFavorite = false
}: {
  label: string;
  value: number;
  color?: 'blue' | 'orange' | 'green' | 'gray';
  isFavorite?: boolean;
}) {
  const percentage = (value * 100).toFixed(0);

  return (
    <div className="group">
      <div className="flex justify-between text-[13px] mb-1.5">
        <span className={`font-semibold ${isFavorite ? 'text-blue-400' : 'text-white/80'}`}>
          {label}
          {isFavorite && <span className="ml-1.5 text-[10px]">⭐</span>}
        </span>
        <span className={`font-extrabold ${isFavorite ? 'text-blue-400' : 'text-white/60'}`}>
          {percentage}%
        </span>
      </div>
      <div className="prob-bar-track">
        <div
          className={`prob-bar-fill ${color}`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}