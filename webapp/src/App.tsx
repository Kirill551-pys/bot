import { HashRouter, Routes, Route, Navigate, useLocation, Link } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useTelegram } from './hooks/useTelegram';
import { setupAuth } from './api/client';
import { Home } from './pages/Home';
import { Prediction } from './pages/Prediction';
import { Stats } from './pages/Stats';
import { Subscribe } from './pages/Subscribe';
import './styles/globals.css';

const queryClient = new QueryClient({
  defaultOptions: { 
    queries: { 
      retry: 1, 
      staleTime: 30000,
      refetchOnWindowFocus: false,
    } 
  }
});

function App() {
  const { initData, isReady } = useTelegram();

  if (initData) setupAuth(initData);

  if (!isReady) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-tg-bg">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-4 border-tg-button border-t-transparent mx-auto mb-4" />
          <p className="text-tg-hint">Загрузка...</p>
        </div>
      </div>
    );
  }

  return (
    <QueryClientProvider client={queryClient}>
      <HashRouter>
        <div className="min-h-screen bg-tg-bg pb-20">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/prediction" element={<Prediction />} />
            <Route path="/stats" element={<Stats />} />
            <Route path="/subscribe" element={<Subscribe />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          <BottomNav />
        </div>
      </HashRouter>
    </QueryClientProvider>
  );
}

function BottomNav() {
  const location = useLocation();
  const navItems = [
    { path: '/', icon: '🏠', label: 'Главная' },
    { path: '/prediction', icon: '⚽', label: 'Прогноз' },
    { path: '/stats', icon: '📊', label: 'Стата' },
    { path: '/subscribe', icon: '💎', label: 'VIP' },
  ];

  return (
    <nav 
      className="fixed bottom-0 left-0 right-0 bg-tg-secondary border-t border-tg-border flex justify-around px-4 z-50 shadow-lg"
      style={{ 
        paddingTop: '0.5rem',
        paddingBottom: 'calc(0.5rem + env(safe-area-inset-bottom))' 
      }}
    >
      {navItems.map((item) => {
        const isActive = location.pathname === item.path;
        return (
          <Link
            key={item.path}
            to={item.path}
            className={`flex flex-col items-center px-3 py-1.5 transition-all duration-200 ${
              isActive 
                ? 'text-tg-button scale-110 -translate-y-1' 
                : 'text-tg-hint hover:text-tg-text'
            }`}
          >
            <span className="text-2xl">{item.icon}</span>
            <span className={`text-xs mt-1 font-semibold ${isActive ? 'text-tg-button' : ''}`}>
              {item.label}
            </span>
          </Link>
        );
      })}
    </nav>
  );
}

export default App;