import { Component, useEffect } from 'react';
import type { ReactNode } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation, Link } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useTelegram } from './hooks/useTelegram';
import { setupAuth } from './api/client';
import { Home } from './pages/Home';
import { Prediction } from './pages/Prediction';
import { Stats } from './pages/Stats';
import { Subscribe } from './pages/Subscribe';
import './styles/globals.css';

/* ============================================
   НАСТРОЙКА КЕШИРОВАНИЯ ЗАПРОСОВ
   ============================================ */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,                      // только 1 повтор при ошибке
      staleTime: 30000,              // данные свежие 30 сек
      refetchOnWindowFocus: false,   // не дёргать API лишний раз в Telegram
    }
  }
});

/* ============================================
   ЗАЩИТА ОТ «БЕЛОГО ЭКРАНА» ПРИ ОШИБКАХ
   ============================================ */
class ErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-[#0f1923] px-6">
          <div className="text-center animate-scale-in">
            <div className="text-5xl mb-4">😵</div>
            <h1 className="text-white text-lg font-extrabold mb-2">Что-то пошло не так</h1>
            <p className="text-[#8b9baa] text-sm mb-5">Попробуйте перезапустить приложение</p>
            <button className="btn-primary" onClick={() => window.location.reload()}>
              🔄 Перезагрузить
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

/* ============================================
   СКРОЛЛ ВВЕРХ ПРИ СМЕНЕ СТРАНИЦЫ
   ============================================ */
function ScrollToTop() {
  const { pathname } = useLocation();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return null;
}

/* ============================================
   ГЛАВНЫЙ КОМПОНЕНТ
   ============================================ */
function App() {
  const { initData, isReady } = useTelegram();

  // ✅ ИЗМЕНЕНИЕ 1: побочный эффект вынесен в useEffect
  useEffect(() => {
    if (initData) setupAuth(initData);
  }, [initData]);

  // Сплэш-экран, пока Telegram не готов
  if (!isReady) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#0f1923]">
        <div className="text-center animate-scale-in">
          <div className="relative w-20 h-20 mx-auto mb-5">
            <div className="absolute inset-0 rounded-3xl bg-gradient-to-br from-blue-500 to-orange-500 animate-float opacity-80" />
            <div className="absolute inset-0 flex items-center justify-center text-3xl">⚽</div>
          </div>
          <p className="text-white/60 text-sm font-medium">Тактика Ставок</p>
          <div className="mt-4 w-32 h-1 rounded-full bg-white/10 mx-auto overflow-hidden">
            <div className="h-full w-1/2 bg-blue-500 rounded-full animate-pulse" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <ScrollToTop />
          {/* ✅ ИЗМЕНЕНИЕ 2: pb-28 — запас под меню + safe-area */}
          <div className="min-h-screen bg-[#0f1923] pb-28">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/prediction" element={<Prediction />} />
              <Route path="/stats" element={<Stats />} />
              <Route path="/subscribe" element={<Subscribe />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
            <BottomNav />
          </div>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}

/* ============================================
   НИЖНЯЯ НАВИГАЦИЯ
   ============================================ */
function BottomNav() {
  const location = useLocation();

  const navItems = [
    { path: '/', icon: '🔥', label: 'Главная' },
    { path: '/prediction', icon: '⚽', label: 'Прогноз' },
    { path: '/stats', icon: '📊', label: 'Стата' },
    { path: '/subscribe', icon: '💎', label: 'VIP' },
  ];

  return (
    /* ✅ ИЗМЕНЕНИЕ 3: класс bottom-nav из globals.css —
       там уже есть blur и env(safe-area-inset-bottom) */
    <nav className="bottom-nav">
      <div className="flex justify-around py-2 px-3 max-w-lg mx-auto">
        {navItems.map((item) => {
          const isActive = location.pathname === item.path;
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`nav-item ${isActive ? 'active' : ''}`}
            >
              <span className="nav-icon">{item.icon}</span>
              <span className="nav-label">{item.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

export default App;