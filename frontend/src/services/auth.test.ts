import { describe, it, expect, vi, afterEach } from 'vitest'
import { getMe, ServerUnavailableError } from './auth'

function mockFetchResponse(status: number, body: unknown = {}) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      json: async () => body,
    }),
  )
}

describe('getMe distingue 5xx de 401 (fix 6a Fase 1)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('503 (backend arrancando) → ServerUnavailableError', async () => {
    mockFetchResponse(503)
    await expect(getMe()).rejects.toBeInstanceOf(ServerUnavailableError)
  })

  it('401 (no autenticado) → error genérico, NO ServerUnavailableError', async () => {
    mockFetchResponse(401)
    const err = await getMe().catch((e: unknown) => e)
    expect(err).toBeInstanceOf(Error)
    expect(err).not.toBeInstanceOf(ServerUnavailableError)
    expect((err as Error).message).toBe('Not authenticated')
  })

  it('fetch rechaza (red caída) → ServerUnavailableError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(getMe()).rejects.toBeInstanceOf(ServerUnavailableError)
  })

  it('200 → devuelve la sesión', async () => {
    const session = { email: 'contador@test.com', role: 'contador' }
    mockFetchResponse(200, session)
    await expect(getMe()).resolves.toEqual(session)
  })
})
