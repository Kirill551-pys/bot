import { BrowserRouter, Routes, Route, Navigate, useLocation, Link } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useTelegram } from './hooks/useTelegram';
import { setupAuth } from './api/client';
import { Home } from './pages/Home';
import { Prediction } from './pages/Prediction';
import { Stats } from './pages/Stats';
import { Subscribe } from './pages/Subscribe';
import './styles/globals.css';

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000, refetchOnWindowFocus: false } },
});

function App() {
  const { initData, isReady } = useTelegram();
  if (initData) setupAuth(initData);

  if (!isReady) {
    return (
      <div className="h-full flex items-center justify-center bg-tg-bg">
        <div className="text-center">
          <div className="mx-auto mb-4 h-14 w-14 animate-spin rounded-full border-4 border-tg-button border-t-transparent" />
          <p className="text-tg-hint text-sm font-medium">Загрузка…</p>
        </div>
      </div>
    );
  }

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="min-h-full bg-tg-bg">
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
  );
}

function BottomNav() {
  const location = useLocation();
  const { hapticFeedback } = useTelegram();

  const items = [
    { path: '/', icon: '🏠', label: 'Главная' },
    { path: '/prediction', icon: '⚽', label: 'Прогноз' },
    { path: '/stats', icon: '📊', label: 'Стата' },
    { path: '/subscribe', icon: '💎', label: 'VIP' },
  ];

  return (
    <nav className="nav-glass fixed inset-x-0 bottom-0 z-50">
      <div className="grid grid-cols-4">
        {items.map((item) => {
          const active = location.pathname === item.path;
          return (
            <Link
              key={item.path}
              to={item.path}
              onClick={() => hapticFeedback('light')}
              className="relative flex flex-col items-center pt-2.5 pb-2"
            >
              {active && <span className="nav-pill" />}
              <span className={`text-[21px] leading-none transition-all duration-200 ${active ? 'scale-110' : 'opacity-55'}`}>
                {item.icon}
              </span>
              <span className={`mt-1 text-[11px] font-semibold ${active ? 'text-tg-button' : 'text-tg-hint'}`}>
                {item.label}
              </span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

export default App;