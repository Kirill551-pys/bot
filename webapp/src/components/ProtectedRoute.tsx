import { Navigate } from 'react-router-dom';
import { useUserStatus } from '../hooks/useUserStatus';

interface ProtectedRouteProps {
  children: React.ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { has_access, is_admin, isLoading } = useUserStatus();

  // Пока загружается статус — показываем спиннер
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // Если нет доступа и не админ — редирект на подписку
  if (!has_access && !is_admin) {
    return <Navigate to="/subscribe" replace />;
  }

  // Иначе показываем контент
  return <>{children}</>;
}