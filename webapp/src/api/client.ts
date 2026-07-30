import axios from 'axios';
import type { AxiosInstance, AxiosError } from 'axios';

// ==================== ТИПЫ ДАННЫХ ====================

export interface TelegramUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  language_code?: string;
}

export interface Prediction {
  home_team: string;
  away_team: string;
  timestamp: string;
  risk_level: string;
  result: {
    'Home Win': number;
    'Draw': number;
    'Away Win': number;
  };
  total_goals: {
    'Over 2.5': number;
    'Under 2.5': number;
  };
  both_scored: {
    'Yes': number;
    'No': number;
  };
  corners?: {
    'Over 9.5': number;
    'Under 9.5': number;
    'Over 10.5': number;
    'Under 10.5': number;
  };
  cards?: {
    'Over 3.5': number;
    'Under 3.5': number;
    'Over 4.5': number;
    'Under 4.5': number;
  };
   first_half_result?: {
    'Home Win': number;
    'Draw': number;
    'Away Win': number;
  };
  total_shots?: {
    'Over 22.5': number;
    'Under 22.5': number;
  };
  total_shots_on_target?: {
    'Over 8.5': number;
    'Under 8.5': number;
  };
  total_fouls?: {
    'Over 23.5': number;
    'Under 23.5': number;
  };
  btts_first_half?:{
    'Yes': number;
    'No': number;
  };
  individual_totals?: Record<string, number>; 

  recommendation: string;
  trust_signal: string;
  is_hot: boolean;
  hot_confidence: number;
  hot_bet: string;
}

export interface League {
  key: string;
  name: string;
  teams_count: number;
  matches_count: number;
}

export interface TeamStats {
  matches_played: number;
  home_matches: number;
  away_matches: number;
  avg_goals_for: number;
  avg_goals_against: number;
  total_goals_avg: number;
  over_2_5_pct: number;
  over_3_5_pct: number;
  under_2_5_pct: number;
  btts_yes_pct: number;
  btts_no_pct: number;
  avg_corners_for?: number;
  avg_corners_against?: number;
  total_corners_avg?: number;
  corners_over_9_5_pct?: number;
  corners_over_10_5_pct?: number;
  avg_yellows_for?: number;
  avg_yellows_against?: number;
  total_yellows_avg?: number;
  yellows_over_3_5_pct?: number;
  yellows_over_4_5_pct?: number;
  form_points: number;
  form_pct: number;
}

export interface HotPrediction extends Prediction {
  league: string;
  league_name: string;
  confidence: number;
}

export interface UserSubscription {
  user_id: number;
  username?: string;
  first_name?: string;
  subscription_type: string;
  subscription_start?: string;
  subscription_end?: string;
  trial_used: boolean;
  is_active: boolean;
  created_at: string;
}

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

// ==================== API КЛИЕНТ ====================

class ApiClient {
  private client: AxiosInstance;
  private initData: string = '';

  constructor() {
    const baseURL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

    this.client = axios.create({
      baseURL,
      timeout: 15000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Интерцептор для добавления initData в каждый запрос
    this.client.interceptors.request.use(
      (config) => {
        if (this.initData) {
          config.headers['X-Telegram-Init-Data'] = this.initData;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Интерцептор для обработки ошибок
    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        console.error('API Error:', error.response?.data || error.message);
        return Promise.reject(error);
      }
    );
  }

  // Устанавливает initData от Telegram для авторизации
  setInitData(initData: string) {
    this.initData = initData;
  }

  // ==================== ЛИГИ ====================

  async getLeagues(): Promise<League[]> {
    try {
      const response = await this.client.get<League[]>('/api/leagues');
      return response.data;
    } catch (error) {
      console.error('Ошибка получения лиг:', error);
      throw new Error('Не удалось загрузить список лиг');
    }
  }

  async getTeams(leagueKey: string): Promise<string[]> {
    try {
      const response = await this.client.get<string[]>(`/api/leagues/${leagueKey}/teams`);
      return response.data;
    } catch (error) {
      console.error('Ошибка получения команд:', error);
      throw new Error('Не удалось загрузить список команд');
    }
  }

  // ==================== ПРОГНОЗЫ ====================

  async getMatchPrediction(
    team1: string,
    team2: string,
    league: string
  ): Promise<Prediction> {
    try {
      const response = await this.client.post<Prediction>('/api/predictions/match', {
        team1,
        team2,
        league,
      });
      return response.data;
    } catch (error) {
      console.error('Ошибка получения прогноза:', error);
      throw new Error('Не удалось получить прогноз');
    }
  }

  async getHotPrediction(): Promise<HotPrediction | null> {
    try {
      const response = await this.client.get<HotPrediction>('/api/predictions/hot');
      return response.data;
    } catch (error) {
      console.error('Ошибка получения горячего прогноза:', error);
      return null;
    }
  }

  // ==================== СТАТИСТИКА ====================

  async getTeamStats(leagueKey: string, teamName: string): Promise<TeamStats> {
    try {
      const response = await this.client.get<TeamStats>(
        `/api/stats/${leagueKey}/${encodeURIComponent(teamName)}`
      );
      return response.data;
    } catch (error) {
      console.error('Ошибка получения статистики:', error);
      throw new Error('Не удалось загрузить статистику');
    }
  }

  async getTopTeams(
    leagueKey: string,
    statType: string = 'corners'
  ): Promise<Array<{ team: string; value: number; label: string }>> {
    try {
      const response = await this.client.get<
        Array<{ team: string; value: number; label: string }>
      >(`/api/stats/${leagueKey}/top?stat_type=${statType}`);
      return response.data;
    } catch (error) {
      console.error('Ошибка получения ТОП-3:', error);
      throw new Error('Не удалось загрузить рейтинг');
    }
  }

  // ==================== ПОЛЬЗОВАТЕЛЬ ====================

  async getUserSubscription(): Promise<UserSubscription> {
    try {
      const response = await this.client.get<UserSubscription>('/api/user/subscription');
      return response.data;
    } catch (error) {
      console.error('Ошибка получения подписки:', error);
      throw new Error('Не удалось загрузить информацию о подписке');
    }
  }

  /**
   * Активировать пробный период (3 дня бесплатно)
   */
  async activateTrial(): Promise<{ success: boolean; message: string }> {
    try {
      const response = await this.client.post<{ success: boolean; message: string }>(
        '/api/user/trial'
      );
      return response.data;
    } catch (error) {
      console.error('Ошибка активации trial:', error);
      throw error;
    }
  }

  async checkSubscription(): Promise<{ is_active: boolean; days_left: number }> {
    try {
      const response = await this.client.get<{ is_active: boolean; days_left: number }>(
        '/api/user/check-subscription'
      );
      return response.data;
    } catch (error) {
      console.error('Ошибка проверки подписки:', error);
      return { is_active: false, days_left: 0 };
    }
  }

  async getPredictionHistory(limit: number = 10): Promise<Prediction[]> {
    try {
      const response = await this.client.get<Prediction[]>(
        `/api/user/history?limit=${limit}`
      );
      return response.data;
    } catch (error) {
      console.error('Ошибка получения истории:', error);
      return [];
    }
  }
}

export const api = new ApiClient();

// Утилита для инициализации клиента с initData от Telegram
export function initApiClient(initData: string) {
  api.setInitData(initData);
}

// 🔥 НОВАЯ ФУНКЦИЯ — для совместимости с App.tsx
export function setupAuth(initData: string) {
  api.setInitData(initData);
}

