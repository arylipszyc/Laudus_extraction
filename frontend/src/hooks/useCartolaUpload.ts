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

/** Polls GET /cartolas/{batch_id} every 3s while status === 'processing'. */
export function useCartolaStatus(batchId: string | null) {
  return useQuery<CartolaStatus, CartolaError>({
    queryKey: ['cartolas', 'status', batchId],
    queryFn: () => getCartolaStatus(batchId!),
    enabled: batchId !== null,
    refetchInterval: (query) => {
      const data = query.state.data
      return data && data.status === 'processing' ? POLL_INTERVAL_MS : false
    },
    retry: false,
  })
}
