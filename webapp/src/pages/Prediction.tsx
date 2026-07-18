import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { useTelegram } from '../hooks/useTelegram';
import { useSearchParams } from 'react-router-dom';
import type { League } from '../api/client';

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

  // 🔥 ИСПРАВЛЕНО: убран .then(r => r.data)
  const { data: leagues } = useQuery<League[]>({
    queryKey: ['leagues'],
    queryFn: () => api.getLeagues(),
  });

  const { data: teams } = useQuery<string[]>({
    queryKey: ['teams', selectedLeague],
    queryFn: () => api.getTeams(selectedLeague),
    enabled: !!selectedLeague,
  });

  const { data: prediction, isLoading: isPredicting } = useQuery({
    queryKey: ['prediction', team1, team2, selectedLeague],
    queryFn: () => api.getMatchPrediction(team1, team2, selectedLeague),
    enabled: !!team1 && !!team2 && !!selectedLeague,
  });

  return (
    <div className="p-4 space-y-4">
      <h1 className="text-2xl font-bold">⚽ Выбор матча</h1>

      {/* Выбор лиги */}
      <div className="card">
        <label className="block text-sm font-semibold mb-2">🏆 Выберите лигу:</label>
        <select
          value={selectedLeague}
          onChange={(e) => {
            setSelectedLeague(e.target.value);
            setTeam1('');
            setTeam2('');
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

      {/* Выбор команд */}
      {selectedLeague && teams && (
        <div className="card space-y-3">
          <div>
            <label className="block text-sm font-semibold mb-2">🏠 Команда хозяев:</label>
            <select
              value={team1}
              onChange={(e) => {
                setTeam1(e.target.value);
                hapticFeedback('light');
              }}
              className="w-full p-2 rounded-lg bg-tg-secondary border border-gray-300"
            >
              <option value="">-- Выберите --</option>
              {teams.map((team: string) => (
                <option key={team} value={team}>{team}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-semibold mb-2">🚌 Команда гостей:</label>
            <select
              value={team2}
              onChange={(e) => {
                setTeam2(e.target.value);
                hapticFeedback('light');
              }}
              className="w-full p-2 rounded-lg bg-tg-secondary border border-gray-300"
            >
              <option value="">-- Выберите --</option>
              {teams.filter((t: string) => t !== team1).map((team: string) => (
                <option key={team} value={team}>{team}</option>
              ))}
            </select>
          </div>
        </div>
      )}

      {/* Прогноз */}
      {isPredicting && (
        <div className="card text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-4 border-tg-button border-t-transparent mx-auto" />
          <p className="mt-3 text-tg-hint">Генерирую прогноз...</p>
        </div>
      )}

      {prediction && !isPredicting && (
        <div className="card space-y-4">
          <h2 className="text-xl font-bold text-center">
            {prediction.home_team} vs {prediction.away_team}
          </h2>

          {/* Вероятности */}
          <div className="space-y-2">
            <h3 className="font-semibold">🏆 Победитель:</h3>
            <ProbabilityBar label={prediction.home_team} value={prediction.result['Home Win']} />
            <ProbabilityBar label="Ничья" value={prediction.result['Draw']} />
            <ProbabilityBar label={prediction.away_team} value={prediction.result['Away Win']} />
          </div>

          {/* Тоталы */}
          {prediction.total_goals && (
            <div className="space-y-2">
              <h3 className="font-semibold">⚽ Тотал 2.5:</h3>
              <ProbabilityBar label="Больше" value={prediction.total_goals['Over 2.5']} />
              <ProbabilityBar label="Меньше" value={prediction.total_goals['Under 2.5']} />
            </div>
          )}

          {/* Обе забьют */}
          {prediction.both_scored && (
            <div className="space-y-2">
              <h3 className="font-semibold">🔄 Обе забьют:</h3>
              <ProbabilityBar label="Да" value={prediction.both_scored['Yes']} />
              <ProbabilityBar label="Нет" value={prediction.both_scored['No']} />
            </div>
          )}

          {/* Рекомендация */}
          {prediction.recommendation && (
            <div className="bg-tg-secondary p-3 rounded-lg">
              <h3 className="font-semibold mb-2">💡 Рекомендация:</h3>
              <p className="text-sm whitespace-pre-line">{prediction.recommendation}</p>
            </div>
          )}

          {/* Доверие */}
          <div className="bg-tg-secondary p-3 rounded-lg text-center">
            <p className="text-sm text-tg-hint">🛡️ Доверие к прогнозу:</p>
            <p className="font-semibold">{prediction.trust_signal}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function ProbabilityBar({ label, value }: { label: string; value: number }) {
  const percentage = (value * 100).toFixed(0);
  
  return (
    <div>
      <div className="flex justify-between text-sm mb-1">
        <span>{label}</span>
        <span className="font-semibold">{percentage}%</span>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-2">
        <div
          className="bg-tg-button h-2 rounded-full transition-all"
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}