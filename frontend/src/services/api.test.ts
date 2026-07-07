import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { apiFetch, ApiTimeoutError, ApiNetworkError } from './api'

describe('apiFetch — timeout + error tipado de red (Fase 3 F4)', () => {
  beforeEach(() => {
    // El timeout es un setTimeout real: si otro test dejó fake timers activos, colgaría.
    vi.useRealTimers()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('respuesta OK pasa intacta (apiFetch es transparente)', async () => {
    const response = { ok: true, status: 200, json: async () => ({ hola: true }) }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
    await expect(apiFetch('http://x/api')).resolves.toBe(response)
  })

  it('un 400 del backend NO se convierte en error de red — pasa como Response', async () => {
    const response = { ok: false, status: 400, json: async () => ({ error: {} }) }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
    const res = await apiFetch('http://x/api')
    expect(res).toBe(response)
    expect(res.status).toBe(400)
  })

  it('backend colgado → aborta al timeout y tira ApiTimeoutError con mensaje claro', async () => {
    // fetch que nunca responde pero respeta la signal (como un backend que acepta TCP y se cuelga)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener('abort', () => reject(init.signal!.reason))
        }),
      ),
    )
    const err = await apiFetch('http://x/api', undefined, { timeoutMs: 20 }).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiTimeoutError)
    expect((err as Error).message).toContain('El servidor no respondió')
    expect((err as ApiTimeoutError).code).toBe('TIMEOUT')
    expect((err as Error).cause).toBeInstanceOf(DOMException)
    expect(((err as Error).cause as DOMException).name).toBe('TimeoutError')
  })

  it('caller signal presente pero NO abortado cuando vence el timeout → ApiTimeoutError igual', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener('abort', () => reject(init.signal!.reason))
        }),
      ),
    )
    const controller = new AbortController()
    const err = await apiFetch('http://x/api', { signal: controller.signal }, { timeoutMs: 20 }).catch(
      (e: unknown) => e,
    )
    expect(err).toBeInstanceOf(ApiTimeoutError)
    expect((err as ApiTimeoutError).code).toBe('TIMEOUT')
  })

  it('red caída (fetch rechaza) → ApiNetworkError distinguible de un 4xx/5xx', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const err = await apiFetch('http://x/api').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiNetworkError)
    expect((err as Error).message).toBe('Sin conexión con el servidor')
  })

  it('abort del caller se propaga tal cual (cancelación deliberada, no error de red/timeout)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener('abort', () => reject(init.signal!.reason))
        }),
      ),
    )
    const controller = new AbortController()
    const pending = apiFetch('http://x/api', { signal: controller.signal }).catch((e: unknown) => e)
    controller.abort()
    const err = await pending
    expect(err).not.toBeInstanceOf(ApiTimeoutError)
    expect(err).not.toBeInstanceOf(ApiNetworkError)
    expect((err as { name?: string }).name).toBe('AbortError')
  })
})
