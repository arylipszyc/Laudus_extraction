import { api } from '@/services/api'
import type { UserSession } from '@/types'

export async function getMe(): Promise<UserSession> {
  const response = await fetch(`${api.baseUrl}/api/v1/auth/me`, {
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error('Not authenticated')
  }
  return response.json() as Promise<UserSession>
}

export async function logout(): Promise<void> {
  await fetch(`${api.baseUrl}/api/v1/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  })
}
