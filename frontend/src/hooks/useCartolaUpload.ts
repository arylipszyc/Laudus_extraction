import { useMutation, useQuery } from '@tanstack/react-query'
import {
  type CartolaError,
  type CartolaStatus,
  type UploadAccepted,
  getCartolaStatus,
  uploadCartola,
} from '@/services/cartolas'

const POLL_INTERVAL_MS = 3000

export function useCartolaUploadMutation() {
  return useMutation<UploadAccepted, CartolaError, { pdfFile: File; bankAccountId: string }>({
    mutationFn: ({ pdfFile, bankAccountId }) => uploadCartola(pdfFile, bankAccountId),
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
