import { useMutation, useQuery } from '@tanstack/react-query'
import {
  type CartolaError,
  type CartolaStatus,
  type UploadAccepted,
  getCartolaStatus,
  uploadCartola,
} from '@/services/cartolas'

const POLL_INTERVAL_MS = 3000

// batch_id de la cartola en proceso: sobrevive a cambios de vista (el backend sigue extrayendo
// aunque la página se desmonte). Al volver a /upload se retoma el polling y el paso de confirmar.
export const ACTIVE_BATCH_KEY = 'cartola-active-batch'

export const UPLOAD_MUTATION_KEY = ['cartola-upload']

export function useCartolaUploadMutation() {
  return useMutation<UploadAccepted, CartolaError, { pdfFile: File; bankAccountId: string }>({
    mutationKey: UPLOAD_MUTATION_KEY,
    mutationFn: ({ pdfFile, bankAccountId }) => uploadCartola(pdfFile, bankAccountId),
    // A nivel de hook (no de mutate()) porque estos callbacks corren aunque la página ya se
    // haya desmontado — si el usuario navega durante el POST, el batch_id igual se persiste.
    onSuccess: (data) => sessionStorage.setItem(ACTIVE_BATCH_KEY, data.batch_id),
  })
}

/** El poll sigue mientras el backend trabaja: extracción ('processing') o confirm async ('confirming'). */
export function shouldKeepPolling(status: CartolaStatus['status'] | undefined): boolean {
  return status === 'processing' || status === 'confirming'
}

/** Polls GET /cartolas/{batch_id} every 3s while status === 'processing' | 'confirming'. */
export function useCartolaStatus(batchId: string | null) {
  return useQuery<CartolaStatus, CartolaError>({
    queryKey: ['cartolas', 'status', batchId],
    queryFn: () => getCartolaStatus(batchId!),
    enabled: batchId !== null,
    refetchInterval: (query) => (shouldKeepPolling(query.state.data?.status) ? POLL_INTERVAL_MS : false),
    retry: false,
  })
}
