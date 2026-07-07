import { useQuery } from '@tanstack/react-query'
import { getMe, ServerUnavailableError } from '@/services/auth'

export function useAuth() {
  return useQuery({
    queryKey: ['auth', 'me'],
    queryFn: getMe,
    // Reintenta solo si el backend no responde (5xx/red); un 401 real no se reintenta.
    retry: (failureCount, error) =>
      error instanceof ServerUnavailableError && failureCount < 3,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
    // Los 3 retries se agotan en ~7s pero un cold start de Render tarda 30-60s:
    // mientras el error sea "servidor no disponible", seguir sondeando cada 5s
    // (esto es lo que hace verdadero el "Reintentando automáticamente" de la UI).
    refetchInterval: (query) =>
      query.state.error instanceof ServerUnavailableError ? 5000 : false,
    staleTime: 5 * 60 * 1000, // 5 min
  })
}
