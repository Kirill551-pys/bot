import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';

// ==================== ЛИГИ ====================

export function useLeagues() {
  return useQuery({
    queryKey: ['leagues'],
    queryFn: () => api.getLeagues(),
    staleTime: 5 * 60 * 1000, // 5 минут
  });
}

export function useTeams(leagueKey: string) {
  return useQuery({
    queryKey: ['teams', leagueKey],
    queryFn: () => api.getTeams(leagueKey),
    enabled: !!leagueKey, // Запрашиваем только если leagueKey есть
    staleTime: 5 * 60 * 1000,
  });
}

// ==================== ПРОГНОЗЫ ====================

export function useMatchPrediction(team1: string, team2: string, league: string) {
  return useQuery({
    queryKey: ['prediction', team1, team2, league],
    queryFn: () => api.getMatchPrediction(team1, team2, league),
    enabled: !!team1 && !!team2 && !!league,
  });
}

export function useHotPrediction() {
  return useQuery({
    queryKey: ['hot-prediction'],
    queryFn: () => api.getHotPrediction(),
    refetchInterval: 60 * 1000, // Обновляем каждую минуту
  });
}

// ==================== СТАТИСТИКА ====================

export function useTeamStats(leagueKey: string, teamName: string) {
  return useQuery({
    queryKey: ['team-stats', leagueKey, teamName],
    queryFn: () => api.getTeamStats(leagueKey, teamName),
    enabled: !!leagueKey && !!teamName,
  });
}

export function useTopTeams(leagueKey: string, statType: string = 'corners') {
  return useQuery({
    queryKey: ['top-teams', leagueKey, statType],
    queryFn: () => api.getTopTeams(leagueKey, statType),
    enabled: !!leagueKey,
  });
}

// ==================== ПОЛЬЗОВАТЕЛЬ ====================

export function useUserSubscription() {
  return useQuery({
    queryKey: ['user-subscription'],
    queryFn: () => api.getUserSubscription(),
    staleTime: 60 * 1000, // 1 минута
  });
}

export function useCheckSubscription() {
  return useQuery({
    queryKey: ['check-subscription'],
    queryFn: () => api.checkSubscription(),
    refetchInterval: 5 * 60 * 1000, // Каждые 5 минут
  });
}

export function usePredictionHistory(limit: number = 10) {
  return useQuery({
    queryKey: ['prediction-history', limit],
    queryFn: () => api.getPredictionHistory(limit),
  });
}