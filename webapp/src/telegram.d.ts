// src/telegram.d.ts
export {};

declare global {
  interface Window {
    Telegram?: {
      WebApp: TelegramWebApp;
    };
  }

  interface TelegramWebApp {
    ready(): void;
    expand(): void;
    close(): void;
    
    initData: string;
    initDataUnsafe: {
      user?: {
        id: number;
        first_name: string;
        last_name?: string;
        username?: string;
        language_code?: string;
        photo_url?: string;
      };
      auth_date?: number;
      hash?: string;
    };
    
    themeParams: {
      bg_color?: string;
      text_color?: string;
      hint_color?: string;
      link_color?: string;
      button_color?: string;
      secondary_bg_color?: string;
    };
    
    HapticFeedback?: {
      impactOccurred(style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft'): void;
      notificationOccurred(type: 'error' | 'success' | 'warning'): void;
      selectionChanged(): void;
    };
    
    BackButton: {
      isVisible: boolean;
      show(): void;
      hide(): void;
      onClick(callback: () => void): void;
      offClick(callback: () => void): void;
    };
    
    MainButton: {
      text: string;
      color: string;
      textColor: string;
      isVisible: boolean;
      isActive: boolean;
      show(): void;
      hide(): void;
      enable(): void;
      disable(): void;
      setText(text: string): void;
      onClick(callback: () => void): void;
      offClick(callback: () => void): void;
    };
    
    showAlert(message: string, callback?: () => void): void;
    showConfirm(message: string, callback?: (ok: boolean) => void): void;
    showPopup(params: {
      title?: string;
      message: string;
      buttons?: Array<{id?: string; type?: 'default' | 'ok' | 'close' | 'cancel' | 'destructive'; text?: string}>;
    }, callback?: (buttonId: string) => void): void;
    
    version: string;
    platform: string;
    colorScheme: 'light' | 'dark';
  }
}