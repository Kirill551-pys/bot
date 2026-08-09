import { Component, type ErrorInfo, type ReactNode } from 'react';

// Интерфейсы пропсов и состояния
interface Props { 
  children: ReactNode; 
}

interface State { 
  hasError: boolean; 
  error: Error | null; 
}

/**
 * 🛡️ Error Boundary
 * Защищает приложение от "белого экрана" при падении React.
 * Перехватывает ошибки в дочерних компонентах и показывает фоллбэк UI.
 */
export class ErrorBoundary extends Component<Props, State> {
  public state: State = { hasError: false, error: null };

  // Обновляем состояние при возникновении ошибки
  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  // Логируем ошибку (здесь можно добавить отправку в Sentry/Telegram)
  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("🔥 Критическая ошибка приложения:", error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      // UI-заглушка при ошибке
      return (
        <div className="min-h-screen flex flex-col items-center justify-center p-6 text-center bg-tg-bg">
          <div className="text-6xl mb-4">⚠️</div>
          <h1 className="text-xl font-bold text-tg-text mb-2">Произошла ошибка</h1>
          <p className="text-tg-hint text-sm mb-6 max-w-xs">
            Не удалось загрузить данные. Возможно, сервер перегружен или ML-модель обновляется.
          </p>
          <button
            onClick={() => window.location.reload()}
            className="px-6 py-3 bg-tg-button text-white rounded-xl font-semibold active:scale-95 transition-transform"
          >
            🔄 Перезапустить приложение
          </button>
        </div>
      );
    }

    // Если ошибок нет, рендерим дочерние компоненты
    return this.props.children;
  }
}