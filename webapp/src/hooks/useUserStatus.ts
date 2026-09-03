import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';

export function useUserStatus() {
  const { data: me, isLoading } = useQuery({
    queryKey: ['me'],
    queryFn: () => api.getMe(),
    staleTime: 5 * 60 * 1000,  // 5 минут — админ не меняется часто
    retry: 2,
  });

  return {
    is_admin: me?.is_admin ?? false,
    has_access: me?.has_access ?? false,
    subscription: me?.subscription,
    user_id: me?.id,
    isLoading,
  };
}