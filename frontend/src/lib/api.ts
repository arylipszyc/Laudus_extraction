// Cliente API mínimo contra el backend (espejo de Laudus).
// Auth: HTTP Basic. Las credenciales se guardan en sessionStorage (las setea el
// login cuando exista) y se adjuntan como header Authorization en cada request.

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? '/api/v1'
const STORAGE_KEY = 'basicAuth'

export function setBasicAuth(username: string, password: string): void {
  sessionStorage.setItem(STORAGE_KEY, btoa(`${username}:${password}`))
}

export function clearBasicAuth(): void {
  sessionStorage.removeItem(STORAGE_KEY)
}

export function hasBasicAuth(): boolean {
  return sessionStorage.getItem(STORAGE_KEY) !== null
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = sessionStorage.getItem(STORAGE_KEY)
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Basic ${token}`)

  const res = await fetch(`${BASE_URL}${path}`, { ...init, headers })
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${res.statusText}`)
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
}
