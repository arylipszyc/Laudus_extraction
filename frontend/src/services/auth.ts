import { api } from '@/services/api'
import type { UserSession } from '@/types'

/** Backend caído o arrancando (5xx / red) — distinto de un 401 real (fix 6a Fase 1). */
export class ServerUnavailableError extends Error {
  constructor(message = 'Servidor no disponible') {
    super(message)
    this.name = 'ServerUnavailableError'
  }
}

export async function getMe(): Promise<UserSession> {
  let response: Response
  try {
    response = await fetch(`${api.baseUrl}/api/v1/auth/me`, {
      credentials: 'include',
    })
  } catch (err) {
    // fetch rechaza = red caída o backend inalcanzable (cold start de Render).
    // Log del error real: un TypeError de config (baseUrl malformada) también cae
    // acá y sin traza se disfrazaría de "servidor arrancando".
    console.error('getMe: fetch falló', err)
    throw new ServerUnavailableError()
  }
  if (response.status >= 500) {
    throw new ServerUnavailableError(`Servidor no disponible (${response.status})`)
  }
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
