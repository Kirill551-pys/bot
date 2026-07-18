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

  const { data: topTeams } = useQuery({
    queryKey: ['top-teams', selectedLeague, statType],
    queryFn: () => api.getTopTeams(selectedLeague, statType),
    enabled: !!selectedLeague,
  });

  const { data: teamStats } = useQuery<TeamStats>({
    queryKey: ['team-stats', selectedLeague, selectedTeam],
    queryFn: () => api.getTeamStats(selectedLeague, selectedTeam),
    enabled: !!selectedLeague && !!selectedTeam,
  });

  const statTypes = [
    { value: 'corners', label: '🎯 Угловые' },
    { value: 'total_corners', label: '📊 Всего угловых' },
    { value: 'corners_over_10_5', label: '🔼 ТБ 10.5 угл.' },
    { value: 'yellows', label: '🟨 Карточки' },
    { value: 'over_2_5', label: '⚽ ТБ 2.5' },
    { value: 'btts', label: '🔄 Обе забьют' },
    { value: 'form', label: '📈 Форма' },
  ];

  return (
    <div className="p-4 space-y-4">
      <h1 className="text-2xl font-bold">📊 Статистика</h1>

      <div className="card">
        <label className="block text-sm font-semibold mb-2">🏆 Выберите лигу:</label>
        <select
          value={selectedLeague}
          onChange={(e) => {
            setSelectedLeague(e.target.value);
            setSelectedTeam('');
            hapticFeedback('light');
          }}
          className="w-full p-2 rounded-lg bg-tg-secondary border border-gray-300"
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
        <div className="card">
          <label className="block text-sm font-semibold mb-2">📈 Тип статистики:</label>
          <div className="grid grid-cols-2 gap-2">
            {statTypes.map((type) => (
              <button
                key={type.value}
                onClick={() => {
                  setStatType(type.value);
                  hapticFeedback('light');
                }}
                className={`p-2 rounded-lg text-sm font-semibold transition-all ${
                  statType === type.value
                    ? 'bg-tg-button text-white'
                    : 'bg-tg-secondary text-tg-text'
                }`}
              >
                {type.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {selectedLeague && topTeams && (
        <div className="card">
          <h2 className="text-lg font-bold mb-3">
            🏆 ТОП-3 по: {statTypes.find(t => t.value === statType)?.label}
          </h2>
          <div className="space-y-2">
            {topTeams.map((team, idx) => (
              <div
                key={team.team}
                className="flex items-center justify-between p-3 bg-tg-secondary rounded-lg"
              >
                <div className="flex items-center gap-3">
                  <span className="text-2xl">
                    {idx === 0 ? '🥇' : idx === 1 ? '🥈' : '🥉'}
                  </span>
                  <span className="font-semibold">{team.team}</span>
                </div>
                <span className="text-tg-hint font-semibold">{team.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {selectedLeague && teams && (
        <div className="card">
          <label className="block text-sm font-semibold mb-2">🔍 Статистика команды:</label>
          <select
            value={selectedTeam}
            onChange={(e) => {
              setSelectedTeam(e.target.value);
              hapticFeedback('light');
            }}
            className="w-full p-2 rounded-lg bg-tg-secondary border border-gray-300"
          >
            <option value="">-- Выберите команду --</option>
            {teams.map((team: string) => (
              <option key={team} value={team}>{team}</option>
            ))}
          </select>
        </div>
      )}

      {teamStats && (
        <div className="card space-y-3">
          <h2 className="text-lg font-bold">{selectedTeam}</h2>
          
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="bg-tg-secondary p-2 rounded">
              <div className="text-tg-hint">Матчей</div>
              <div className="font-bold text-lg">{teamStats.matches_played}</div>
            </div>
            <div className="bg-tg-secondary p-2 rounded">
              <div className="text-tg-hint">Форма</div>
              <div className="font-bold text-lg">{teamStats.form_pct}%</div>
            </div>
            <div className="bg-tg-secondary p-2 rounded">
              <div className="text-tg-hint">Забито в ср.</div>
              <div className="font-bold text-lg">{teamStats.avg_goals_for}</div>
            </div>
            <div className="bg-tg-secondary p-2 rounded">
              <div className="text-tg-hint">Пропущено</div>
              <div className="font-bold text-lg">{teamStats.avg_goals_against}</div>
            </div>
            <div className="bg-tg-secondary p-2 rounded">
              <div className="text-tg-hint">ТБ 2.5</div>
              <div className="font-bold text-lg">{teamStats.over_2_5_pct}%</div>
            </div>
            <div className="bg-tg-secondary p-2 rounded">
              <div className="text-tg-hint">Обе забьют</div>
              <div className="font-bold text-lg">{teamStats.btts_yes_pct}%</div>
            </div>
          </div>

          {(teamStats.avg_corners_for ?? 0) > 0 && (
            <div className="bg-tg-secondary p-3 rounded-lg">
              <h3 className="font-semibold mb-2">🎯 Угловые</h3>
              <div className="text-sm">
                В среднем: <b>{teamStats.avg_corners_for}</b> за матч
              </div>
              <div className="text-sm">
                ТБ 9.5: <b>{teamStats.corners_over_9_5_pct ?? 0}%</b>
              </div>
            </div>
          )}

          {(teamStats.avg_yellows_for ?? 0) > 0 && (
            <div className="bg-tg-secondary p-3 rounded-lg">
              <h3 className="font-semibold mb-2">🟨 Карточки</h3>
              <div className="text-sm">
                В среднем: <b>{teamStats.avg_yellows_for}</b> за матч
              </div>
              <div className="text-sm">
                ТБ 3.5: <b>{teamStats.yellows_over_3_5_pct ?? 0}%</b>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}