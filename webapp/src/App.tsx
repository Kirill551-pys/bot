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
      <div className="min-h-screen flex items-center justify-center bg-[#0f1923]">
        <div className="text-center animate-scale-in">
          {/* Анимированный логотип */}
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
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="min-h-screen bg-[#0f1923] pb-24">
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

  const navItems = [
    { path: '/', icon: '🔥', label: 'Главная' },
    { path: '/prediction', icon: '⚽', label: 'Прогноз' },
    { path: '/stats', icon: '📊', label: 'Стата' },
    { path: '/subscribe', icon: '💎', label: 'VIP' },
  ];

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50"
      style={{
        background: 'rgba(26, 39, 51, 0.85)',
        backdropFilter: 'blur(16px)',
        borderTop: '1px solid rgba(255,255,255,0.06)'
      }}
    >
      <div className="flex justify-around py-2 px-3 max-w-lg mx-auto">
        {navItems.map((item) => {
          const isActive = location.pathname === item.path;
          return (
            <Link key={item.path} to={item.path} className={`nav-item ${isActive ? 'active' : ''}`}>
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