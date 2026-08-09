import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { useTelegram } from '../hooks/useTelegram';
import type { League, TeamStats } from '../api/client';

export function Stats() {
  const { hapticFeedback } = useTelegram();
  const [selectedLeague, setSelectedLeague] = useState<string>('');
  const [selectedTeam, setSelectedTeam] = useState<string>('');
  const [statType, setStatType] = useState<string>('corners');

  const { data: leagues } = useQuery<League[]>({
    queryKey: ['leagues'],
    queryFn: () => api.getLeagues(),
  });

  const { data: teams } = useQuery<string[]>({
    queryKey: ['teams', selectedLeague],
    queryFn: () => api.getTeams(selectedLeague),
    enabled: !!selectedLeague,
  });

  const { data: topTeams, isLoading: isLoadingTop } = useQuery({
    queryKey: ['top-teams', selectedLeague, statType],
    queryFn: () => api.getTopTeams(selectedLeague, statType),
    enabled: !!selectedLeague,
  });

  const { data: teamStats, isLoading: isLoadingStats } = useQuery<TeamStats>({
    queryKey: ['team-stats', selectedLeague, selectedTeam],
    queryFn: () => api.getTeamStats(selectedLeague, selectedTeam),
    enabled: !!selectedLeague && !!selectedTeam,
  });

  const statTypes = [
    { value: 'corners', label: '🎯 Угловые' },
    { value: 'total_corners', label: '📊 Всего угл.' },
    { value: 'corners_over_10_5', label: '🔼 ТБ 10.5' },
    { value: 'yellows', label: '🟨 Карточки' },
    { value: 'over_2_5', label: '⚽ ТБ 2.5' },
    { value: 'btts', label: '🔄 Обе забьют' },
    { value: 'form', label: '📈 Форма' },
  ];

  const medals = ['🥇', '🥈', '🥉'];

  return (
    <div className="p-4 space-y-4 max-w-lg mx-auto pb-28">
      <h1 className="text-[22px] font-extrabold text-white animate-fade-up">📊 Статистика</h1>

      {/* Выбор лиги */}
      <div className="card animate-fade-up delay-1">
        <label className="block text-[13px] font-bold mb-2 text-[#8b9baa] uppercase tracking-wide">
          🏆 Лига
        </label>
        <select
          value={selectedLeague}
          onChange={(e) => {
            setSelectedLeague(e.target.value);
            setSelectedTeam('');
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

      {selectedLeague && (
        <>
          {/* Тип статистики — горизонтальный скролл */}
          <div className="animate-fade-up delay-2">
            <div className="flex gap-2 overflow-x-auto pb-2 -mx-4 px-4" style={{ scrollbarWidth: 'none' }}>
              {statTypes.map((type) => (
                <button
                  key={type.value}
                  onClick={() => { setStatType(type.value); hapticFeedback('light'); }}
                  className={`tab-btn shrink-0 ${statType === type.value ? 'active' : ''}`}
                >
                  {type.label}
                </button>
              ))}
            </div>
          </div>

          {/* ТОП-3 */}
          <div className="card animate-fade-up delay-3">
            <h2 className="text-[15px] font-extrabold text-white mb-4">
              🏆 ТОП-3: {statTypes.find(t => t.value === statType)?.label}
            </h2>

            {isLoadingTop ? (
              <div className="space-y-3">
                {[1, 2, 3].map(i => (
                  <div key={i} className="flex items-center gap-3">
                    <div className="skeleton w-10 h-10 rounded-xl" />
                    <div className="flex-1 space-y-1.5">
                      <div className="skeleton h-4 w-2/3" />
                      <div className="skeleton h-3 w-1/3" />
                    </div>
                  </div>
                ))}
              </div>
            ) : topTeams && topTeams.length > 0 ? (
              <div className="space-y-2.5">
                {topTeams.map((team: any, idx: number) => (
                  <div
                    key={team.team}
                    className="flex items-center justify-between p-3.5 rounded-xl transition-all"
                    style={{
                      background: idx === 0
                        ? 'linear-gradient(135deg, rgba(251,191,36,0.1), transparent)'
                        : 'rgba(255,255,255,0.03)'
                    }}
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-2xl">{medals[idx] || '🏅'}</span>
                      <span className="font-bold text-white text-[14px]">{team.team}</span>
                    </div>
                    <span className="text-[13px] text-[#8b9baa] font-semibold">{team.label}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-center text-[#8b9baa] text-sm py-4">Нет данных для этого типа</p>
            )}
          </div>

          {/* Выбор команды */}
          {teams && (
            <div className="card animate-fade-up delay-4">
              <label className="block text-[13px] font-bold mb-2 text-[#8b9baa] uppercase tracking-wide">
                🔍 Команда
              </label>
              <select
                value={selectedTeam}
                onChange={(e) => { setSelectedTeam(e.target.value); hapticFeedback('light'); }}
                className="select-modern"
              >
                <option value="">-- Выберите команду --</option>
                {teams.map((team: string) => (
                  <option key={team} value={team}>{team}</option>
                ))}
              </select>
            </div>
          )}

          {/* Статистика команды */}
          {isLoadingStats && selectedTeam && (
            <div className="card space-y-3 animate-fade-in">
              <div className="skeleton h-6 w-40" />
              <div className="grid grid-cols-2 gap-2">
                {[...Array(6)].map((_, i) => (
                  <div key={i} className="skeleton h-16 rounded-xl" />
                ))}
              </div>
            </div>
          )}

          {teamStats && !isLoadingStats && (
            <div className="card space-y-4 animate-scale-in">
              <div className="flex items-center justify-between">
                <h2 className="text-[17px] font-extrabold text-white">{selectedTeam}</h2>
                <span className="badge badge-blue">{teamStats.matches_played} матчей</span>
              </div>

              {/* Основная сетка */}
              <div className="grid grid-cols-2 gap-2.5">
                <StatCard label="Форма" value={`${teamStats.form_pct.toFixed(0)}%`} icon="📈" />
                <StatCard label="Забито/матч" value={teamStats.avg_goals_for.toFixed(1)} icon="⚽" />
                <StatCard label="Пропущено/матч" value={teamStats.avg_goals_against.toFixed(1)} icon="🥅" />
                <StatCard label="ТБ 2.5" value={`${teamStats.over_2_5_pct.toFixed(0)}%`} icon="🔼" />
                <StatCard label="Обе забьют" value={`${teamStats.btts_yes_pct.toFixed(0)}%`} icon="🔄" />
                <StatCard label="ТМ 2.5" value={`${teamStats.under_2_5_pct.toFixed(0)}%`} icon="🔽" />
              </div>

              {/* Угловые */}
              {(teamStats.avg_corners_for ?? 0) > 0 && (
                <div className="rounded-xl p-4 bg-blue-500/5 border border-blue-500/10">
                  <h3 className="font-bold text-white text-[14px] mb-2.5">🎯 Угловые</h3>
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div>
                      <p className="text-lg font-extrabold text-blue-400">{teamStats.avg_corners_for?.toFixed(1)}</p>
                      <p className="text-[11px] text-[#8b9baa]">за матч</p>
                    </div>
                    <div>
                      <p className="text-lg font-extrabold text-blue-400">{teamStats.corners_over_9_5_pct?.toFixed(0)}%</p>
                      <p className="text-[11px] text-[#8b9baa]">ТБ 9.5</p>
                    </div>
                    <div>
                      <p className="text-lg font-extrabold text-blue-400">{teamStats.corners_over_10_5_pct?.toFixed(0)}%</p>
                      <p className="text-[11px] text-[#8b9baa]">ТБ 10.5</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Карточки */}
              {(teamStats.avg_yellows_for ?? 0) > 0 && (
                <div className="rounded-xl p-4 bg-yellow-500/5 border border-yellow-500/10">
                  <h3 className="font-bold text-white text-[14px] mb-2.5">🟨 Карточки</h3>
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div>
                      <p className="text-lg font-extrabold text-yellow-400">{teamStats.avg_yellows_for?.toFixed(1)}</p>
                      <p className="text-[11px] text-[#8b9baa]">за матч</p>
                    </div>
                    <div>
                      <p className="text-lg font-extrabold text-yellow-400">{teamStats.yellows_over_3_5_pct?.toFixed(0)}%</p>
                      <p className="text-[11px] text-[#8b9baa]">ТБ 3.5</p>
                    </div>
                    <div>
                      <p className="text-lg font-extrabold text-yellow-400">{teamStats.yellows_over_4_5_pct?.toFixed(0)}%</p>
                      <p className="text-[11px] text-[#8b9baa]">ТБ 4.5</p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// Мини-карточка статистики
function StatCard({ label, value, icon }: { label: string; value: string; icon: string }) {
  return (
    <div className="rounded-xl p-3.5 bg-white/[0.03] border border-white/5">
      <div className="flex items-center gap-1.5 mb-1">
        <span className="text-[12px]">{icon}</span>
        <span className="text-[11px] text-[#8b9baa] font-medium">{label}</span>
      </div>
      <p className="text-[18px] font-extrabold text-white">{value}</p>
    </div>
  );
}