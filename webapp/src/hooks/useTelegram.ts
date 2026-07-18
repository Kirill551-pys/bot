import { useEffect, useState } from 'react';

export interface TelegramUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  language_code?: string;
}

export function useTelegram() {
  const [user, setUser] = useState<TelegramUser | null>(null);
  const [initData, setInitData] = useState<string>('');
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    
    if (!tg) {
      // 🔥 FALLBACK: если SDK не загружен (браузер) — используем тестовые данные
      console.warn('⚠️ Telegram WebApp SDK not loaded — using mock data');
      setUser({
        id: 123456789,
        first_name: 'Test',
        last_name: 'User',
        username: 'test_user'
      });
      setInitData('mock_init_data');
      setIsReady(true);
      return;
    }

    tg.ready();
    tg.expand();

    if (tg.initDataUnsafe?.user) {
      setUser(tg.initDataUnsafe.user);
    }
    setInitData(tg.initData || '');
    setIsReady(true);

    // Настраиваем тему
    document.documentElement.style.setProperty('--tg-theme-bg-color', tg.themeParams.bg_color || '#ffffff');
    document.documentElement.style.setProperty('--tg-theme-text-color', tg.themeParams.text_color || '#000000');
    document.documentElement.style.setProperty('--tg-theme-button-color', tg.themeParams.button_color || '#3390ec');
    document.documentElement.style.setProperty('--tg-theme-secondary-bg-color', tg.themeParams.secondary_bg_color || '#f0f0f0');
  }, []);

  const showPopup = (message: string) => {
    if (window.Telegram?.WebApp) {
      window.Telegram.WebApp.showAlert(message);
    } else {
      alert(message); // Fallback для браузера
    }
  };

  const hapticFeedback = (type: 'light' | 'medium' | 'heavy' = 'light') => {
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred(type);
  };

  const backButton = {
    show: () => window.Telegram?.WebApp?.BackButton.show(),
    hide: () => window.Telegram?.WebApp?.BackButton.hide(),
    onClick: (cb: () => void) => {
      window.Telegram?.WebApp?.BackButton.onClick(cb);
    },
    offClick: (cb: () => void) => {
      window.Telegram?.WebApp?.BackButton.offClick(cb);
    }
  };

  return { user, initData, isReady, showPopup, hapticFeedback, backButton, tg: window.Telegram?.WebApp };
}