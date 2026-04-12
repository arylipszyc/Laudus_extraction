import { api } from './api'
import type { SyncStatus } from '@/types'

export async function getSyncStatus(): Promise<SyncStatus> {
  const res = await fetch(`${api.baseUrl}/api/v1/sync/status`, { credentials: 'include' })
  if (!res.ok) throw new Error('Failed to fetch sync status')
  return res.json()
}

export async function triggerSync(
  mode: 'normal' | 'backfill' = 'normal',
  from_date?: string,
): Promise<{ status: string; job_id: string }> {
  const body: Record<string, string> = { mode }
  if (mode === 'backfill' && from_date) body.from_date = from_date
  const res = await fetch(`${api.baseUrl}/api/v1/sync/trigger`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`Trigger failed: ${res.status}`)
  return res.json()
}
