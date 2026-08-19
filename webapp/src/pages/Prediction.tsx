import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { useTelegram } from '../hooks/useTelegram';
import { useSearchParams } from 'react-router-dom';
import type { League, Prediction } from '../api/client';

export function Prediction() {

// ---- Тиры лиг по данным бэктеста ----
// S — уверенные прогнозы заходят ≥58%, B — средне, C — не рекомендуем как ставку
  const LEAGUE_TIERS: Record<string, 'S' | 'B' | 'C'> = {
    greece: 'S', scotland: 'S', portugueseLiga: 'S', laLiga: 'S',
    china: 'S', finland: 'S', dania: 'S', epl: 'S',
    seriaA: 'S', poland: 'S', eredivisise: 'S', rpl: 'S',
    norway: 'B', brazil: 'B', turkey: 'B', belgium: 'B',
    bundesliga: 'B', mexico: 'B', romania: 'B',
    argentina: 'C', usa: 'C', japan: 'C', austria: 'C', ligue1: 'C',
  };

  const TIER_STYLES = {
    S: { border: 'border-l-emerald-500', badge: 'bg-emerald-500/15 text-emerald-400', label: '⭐ S-тир' },
    B: { border: 'border-l-blue-500',   badge: 'bg-blue-500/15 text-blue-400',   label: '👍 B-тир' },
    C: { border: 'border-l-yellow-500', badge: 'bg-yellow-500/15 text-yellow-400', label: '⚠️ C-тир' },
  } as const;

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

  const tier = LEAGUE_TIERS[selectedLeague] ?? 'C';          // champions_league и новые лиги → 'C'
  const tierStyle = TIER_STYLES[tier];

  const filteredTeams = useMemo(() => {
    if (!teams) return [];
    if (!teamSearch) return teams;
    const q = teamSearch.toLowerCase();
    return teams.filter(t => t.toLowerCase().includes(q));
  }, [teams, teamSearch]);

  const swapTeams = () => {
    setTeam1(team2);
    setTeam2(team1);
    hapticFeedback('medium');
  };

  // Получаем название выбранной лиги для отображения
  const selectedLeagueName = leagues?.find(l => l.key === selectedLeague)?.name;

  return (
    <div className="p-3 sm:p-4 space-y-3 sm:space-y-4 pb-28 max-w-lg mx-auto">
      {/* Заголовок с градиентом */}
      <h1 className="text-[20px] sm:text-[22px] font-extrabold text-white animate-fade-up">
        ⚽ Выбор матча
      </h1>

      {/* ===== 1. ВЫБОР ЛИГИ ===== */}
      <div className="card animate-fade-up delay-1">
        <label className="block text-[12px] font-bold mb-2 text-[#8b9baa]">
          🏆 ЛИГА
        </label>
        <div className="select-wrapper">
          <span className="select-icon">🏆</span>
          <select
            value={selectedLeague}
            onChange={(e) => {
              setSelectedLeague(e.target.value);
              setTeam1('');
              setTeam2('');
              hapticFeedback('light');
            }}
            className="select-modern has-icon"
          >
            <option value="" disabled>
              — Выберите лигу —
            </option>
            {leagues?.map((league: League) => (
              <option key={league.key} value={league.key}>
                {league.name} • {league.teams_count} команд • {league.matches_count} матчей
              </option>
            ))}
          </select>
        </div>

        {/* Краткая информация о выбранной лиге */}
        {selectedLeague && selectedLeagueName && (
          <div className={`mt-3 flex items-center gap-2 px-3 py-2 rounded-lg border-l-4 ${tierStyle.border} bg-white/5 animate-fade-in`}>
            <span className={`px-2 py-0.5 rounded-md text-[11px] font-bold ${tierStyle.badge}`}>
              {tierStyle.label}
            </span>
            <p className="text-[13px] text-white/80 font-medium">
              <b>{selectedLeagueName}</b>
            </p>
          </div>
        )}
        </div>

      {/* ===== 2. ВЫБОР КОМАНД ===== */}
      {selectedLeague && teams && (
        <div className="card animate-fade-up delay-2">
          <label className="block text-[12px] font-bold mb-3 text-[#8b9baa]">
            🔍 КОМАНДЫ
          </label>

          {/* Поиск */}
          <div className="relative mb-3">
            <span className="absolute left-4 top-1/2 -translate-y-1/2 text-[#8b9baa] text-sm">
              🔍
            </span>
            <input
              type="text"
              value={teamSearch}
              onChange={(e) => setTeamSearch(e.target.value)}
              placeholder="Поиск команды..."
              className="search-input"
            />
          </div>

          {/* АДАПТИВНАЯ СЕТКА:
              На мобильных — вертикальный стек
              На десктопе (md+) — grid с кнопкой посередине */}
          <div className="flex flex-col gap-3 md:grid md:grid-cols-[1fr_auto_1fr] md:gap-2 md:items-end">
            {/* ХОЗЯЕВА */}
            <div className="w-full">
              <label className="block text-[11px] sm:text-[12px] font-bold mb-1.5 text-[#8b9baa]">
                🏠 ХОЗЯЕВА
              </label>
              <div className="select-wrapper">
                <span className="select-icon">🔴</span>
                <select
                  value={team1}
                  onChange={(e) => { setTeam1(e.target.value); hapticFeedback('light'); }}
                  className="select-modern has-icon text-sm"
                >
                  <option value="" disabled>— Выбор —</option>
                  {filteredTeams.map((team: string) => (
                    <option key={team} value={team}>{team}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* КНОПКА СВОПА */}
            <button
              onClick={swapTeams}
              className="swap-btn self-center md:self-auto md:mb-1"
              title="Поменять местами"
              aria-label="Поменять команды местами"
            >
              ⇄
            </button>

            {/* ГОСТИ */}
            <div className="w-full">
              <label className="block text-[11px] sm:text-[12px] font-bold mb-1.5 text-[#8b9baa]">
                🚌 ГОСТИ
              </label>
              <div className="select-wrapper">
                <span className="select-icon">🔵</span>
                <select
                  value={team2}
                  onChange={(e) => { setTeam2(e.target.value); hapticFeedback('light'); }}
                  className="select-modern has-icon text-sm"
                >
                  <option value="" disabled>— Выбор —</option>
                  {filteredTeams.filter((t: string) => t !== team1).map((team: string) => (
                    <option key={team} value={team}>{team}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Превью выбранного матча */}
          {team1 && team2 && (
            <div className="mt-4 p-3 rounded-xl bg-gradient-to-r from-blue-500/10 to-purple-500/10 border border-white/10 animate-fade-in">
              <p className="text-[11px] text-[#8b9baa] font-bold uppercase tracking-wider mb-1">
                Выбранный матч
              </p>
              <p className="text-[15px] font-extrabold text-white">
                {team1} <span className="text-[#8b9baa] font-normal mx-1">vs</span> {team2}
              </p>
            </div>
          )}
        </div>
      )}

      {/* ===== 3. ЗАГРУЗКА ===== */}
      {isPredicting && (
        <div className="card text-center py-8 sm:py-10 animate-scale-in">
          <div className="relative w-12 h-12 sm:w-14 sm:h-14 mx-auto mb-4">
            <div className="absolute inset-0 rounded-full border-4 border-blue-500/20" />
            <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-blue-500 animate-spin" />
          </div>
          <p className="text-[#8b9baa] font-medium text-sm px-4">
            Анализируем статистику и генерируем прогноз...
          </p>
        </div>
      )}

      {/* ===== 4. РЕЗУЛЬТАТ ===== */}
      {prediction && !isPredicting && (
        <div className="space-y-3 sm:space-y-4">
          {/* Заголовок матча */}
          <div className="card text-center relative overflow-hidden animate-fade-up border-t-2 border-t-blue-500">
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-24 h-1 bg-gradient-to-r from-transparent via-blue-500 to-transparent rounded-full" />
  
            {/* 🆕 Название лиги + тир-бейдж */}
            {prediction.league_name && (
              <div className="flex items-center justify-center gap-2 mt-3 mb-2">
                <p className="text-white/60 text-[12px] font-medium">🏆 {prediction.league_name}</p>
                {prediction.tier && <TierBadge tier={prediction.tier} />}
              </div>
            )}
  
            <h2 className="text-lg sm:text-xl font-extrabold text-white leading-tight">
              {prediction.home_team}
              <span className="text-[#8b9baa] font-normal text-base mx-1">vs</span>
              {prediction.away_team}
            </h2>
            <p className="text-[11px] sm:text-[12px] text-[#8b9baa] mt-2 flex items-center justify-center gap-1.5 flex-wrap">
              <span className="badge badge-blue">🤖 AI v2.2</span>
              {prediction.is_hot && (
                <span className="badge badge-gold animate-live">🔥 HOT</span>
              )}
            </p>
          </div>

          <Section title="🏆 Победитель матча" delay={1}>
            <ProbabilityBar label={prediction.home_team} value={prediction.result['Home Win']} color="blue" isFavorite={prediction.result['Home Win'] >= 0.5} />
            <ProbabilityBar label="Ничья" value={prediction.result['Draw']} color="gray" />
            <ProbabilityBar label={prediction.away_team} value={prediction.result['Away Win']} color="orange" isFavorite={prediction.result['Away Win'] >= 0.5} />
          </Section>

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

          <div className="card animate-fade-up delay-5 relative overflow-hidden border-l-4 border-l-blue-500">
            {prediction.recommendation && (
              <div className="mb-4">
                <h3 className="font-extrabold text-white text-[15px] sm:text-[16px] mb-2">
                  💡 Рекомендация модели
                </h3>
                <p className="text-[13px] sm:text-[14px] leading-relaxed whitespace-pre-line text-white/75">
                  {prediction.recommendation}
                </p>
              </div>
            )}
            <div className="pt-3 border-t border-white/10 text-center">
              <p className="text-[10px] sm:text-[11px] uppercase tracking-widest text-[#8b9baa] font-bold mb-1">
                🛡️ Уровень доверия
              </p>
              <p className="text-base sm:text-lg font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-purple-400">
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
      <h3 className="font-extrabold text-[14px] sm:text-[15px] text-white border-b border-white/8 pb-2.5">
        {title}
      </h3>
      {children}
    </div>
  );
}

function SubSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2.5">
      <h4 className="text-[12px] sm:text-[13px] font-bold text-[#8b9baa]">{title}</h4>
      {children}
    </div>
  );
}

// ==================== КОМПОНЕНТ БЕЙДЖА ТИРА ====================
function TierBadge({ tier }: { tier: string }) {
  const config: Record<string, { label: string; bg: string; text: string }> = {
    S: {
      label: '🔥 S-ТИР',
      bg: 'bg-gradient-to-r from-yellow-400 to-orange-500',
      text: 'text-white',
    },
    B: {
      label: '⭐ B-ТИР',
      bg: 'bg-gradient-to-r from-blue-400 to-indigo-500',
      text: 'text-white',
    },
    C: {
      label: '⚠️ C-ТИР',
      bg: 'bg-gray-400',
      text: 'text-white',
    },
  };

  const c = config[tier] || config.C;

  return (
    <span
      className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-extrabold shadow-md ${c.bg} ${c.text}`}
    >
      {c.label}
    </span>
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
      <div className="flex justify-between text-[12px] sm:text-[13px] mb-1.5">
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