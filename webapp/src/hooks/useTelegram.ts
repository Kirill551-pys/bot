import { useCallback, useEffect, useState } from 'react';

/* ---------- Типизация Telegram WebApp ---------- */
interface TelegramUser {
  id: number;
  first_name?: string;
  last_name?: string;
  username?: string;
}

interface TelegramWebApp {
  ready: () => void;
  expand: () => void;
  initData: string;
  initDataUnsafe: { user?: TelegramUser };
  setHeaderColor?: (color: string) => void;
  setBackgroundColor?: (color: string) => void;
  HapticFeedback?: {
    impactOccurred: (style: string) => void;
    notificationOccurred: (type: string) => void;
  };
  showPopup?: (params: { title: string; message: string }) => void;
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}

/* ---------- Хук ---------- */
export function useTelegram() {
  const [isReady, setIsReady] = useState(false);
  const [initData, setInitData] = useState('');
  const [user, setUser] = useState<TelegramUser | null>(null);

  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready();
      tg.expand(); // 📱 раскрываем на всю высоту
      //  тёмная тема в интерфейсе Telegram (шапка + фон при pull-down)
      tg.setHeaderColor?.('#0f1923');
      tg.setBackgroundColor?.('#0f1923');
      setInitData(tg.initData || '');
      setUser(tg.initDataUnsafe?.user ?? null);
    }
    setIsReady(true);
  }, []);

  /* Вибро-отклик */
  const hapticFeedback = useCallback(
    (type: 'light' | 'medium' | 'heavy' | 'success' | 'error' = 'light') => {
      const haptic = window.Telegram?.WebApp?.HapticFeedback;
      if (!haptic) return;
      if (type === 'success' || type === 'error') {
        haptic.notificationOccurred(type);
      } else {
        haptic.impactOccurred(type);
      }
    },
    []
  );

  /* Всплывающее окно */
  const showPopup = useCallback((message: string) => {
    const tg = window.Telegram?.WebApp;
    if (tg?.showPopup) {
      tg.showPopup({ title: 'Тактика Ставок', message });
    } else {
      alert(message);
    }
  }, []);

  return { user, initData, isReady, hapticFeedback, showPopup };
}