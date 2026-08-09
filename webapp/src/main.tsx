import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import './styles/globals.css';
import App from './App.tsx';
import { ErrorBoundary } from './components/ErrorBoundary';

// Инициализация Telegram WebApp
const tg = (window as any).Telegram?.WebApp;

if (tg) {
  tg.ready();
  tg.expand();
  
  // 🛡️ 1. Защита от случайного закрытия свайпом вниз
  // Пользователь увидит нативный попап "Вы действительно хотите закрыть?"
  tg.enableClosingConfirmation();

  // 🎨 2. Установка начальной темы
  applyTheme(tg.colorScheme);

  // 🔄 3. Подписка на изменение темы в реальном времени
  tg.onEvent('themeChanged', () => applyTheme(tg.colorScheme));
}

/**
 * Применяет CSS-переменные в зависимости от темы Telegram
 */
function applyTheme(scheme: string) {
  const root = document.documentElement;
  if (scheme === 'dark') {
    root.style.setProperty('--tg-bg', '#17212b');
    root.style.setProperty('--tg-secondary', '#232e3c');
    root.style.setProperty('--tg-text', '#f5f5f5');
    root.style.setProperty('--tg-hint', '#708499');
    root.style.setProperty('--tg-button', '#5288c1');
    root.style.setProperty('--tg-border', '#2b3a4a');
  } else {
    root.style.setProperty('--tg-bg', '#ffffff');
    root.style.setProperty('--tg-secondary', '#f4f4f5');
    root.style.setProperty('--tg-text', '#000000');
    root.style.setProperty('--tg-hint', '#707579');
    root.style.setProperty('--tg-button', '#40a7e3');
    root.style.setProperty('--tg-border', '#e0e0e0');
  }
}

// 🚨 4. Глобальный отлов необработанных ошибок (защита от белого экрана)
window.addEventListener('unhandledrejection', (event) => {
  console.error('🔥 Unhandled Promise Rejection:', event.reason);
  // Можно добавить отправку алерта админу
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
);