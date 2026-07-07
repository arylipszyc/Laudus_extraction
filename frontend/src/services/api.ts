// Base API configuration — Story 3 adds feature-specific functions
const API_BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export const api = {
  baseUrl: API_BASE_URL,
}

const DEFAULT_TIMEOUT_MS = 30_000

/** El backend no respondió dentro del timeout (aceptó la conexión pero se colgó). */
export class ApiTimeoutError extends Error {
  readonly code = 'TIMEOUT'
  constructor(timeoutMs: number, cause?: unknown) {
    super(`El servidor no respondió en ${Math.round(timeoutMs / 1000)}s`, { cause })
    this.name = 'ApiTimeoutError'
  }
}

/** El fetch rechazó sin abort: red caída / backend inalcanzable (distinguible de un 4xx/5xx). */
export class ApiNetworkError extends Error {
  readonly code = 'NETWORK'
  constructor(cause?: unknown) {
    super('Sin conexión con el servidor', { cause })
    this.name = 'ApiNetworkError'
  }
}

/**
 * Drop-in de `fetch` con timeout (Fase 3 F4). Solo agrega la capa red/timeout:
 * las respuestas (OK o no-OK) pasan intactas — cada service conserva su `if (!res.ok)`.
 * Si el caller ya trae `init.signal`, se encadena a nuestro controller;
 * un abort del caller se propaga tal cual (cancelación deliberada, no error de red).
 */
export async function apiFetch(
  input: string,
  init?: RequestInit,
  opts?: { timeoutMs?: number },
): Promise<Response> {
  const timeoutMs = opts?.timeoutMs ?? DEFAULT_TIMEOUT_MS
  const ctrl = new AbortController()
  const timer = setTimeout(
    () => ctrl.abort(new DOMException(`timeout tras ${timeoutMs}ms`, 'TimeoutError')), timeoutMs)
  const callerSignal = init?.signal ?? undefined
  const onCallerAbort = () => ctrl.abort(callerSignal!.reason)
  if (callerSignal) {
    if (callerSignal.aborted) { clearTimeout(timer); throw callerSignal.reason }
    callerSignal.addEventListener('abort', onCallerAbort, { once: true })
  }
  try {
    return await fetch(input, { ...init, signal: ctrl.signal })
  } catch (err) {
    // Clasificación por IDENTIDAD del reason (race-free): nuestro timer aborta con
    // DOMException 'TimeoutError'; una cancelación del caller llega con SU reason
    // (típicamente 'AbortError') y se propaga cruda; el resto es red.
    // El `===` contra callerSignal.reason cubre reasons de otro realm (instanceof falla).
    if (err instanceof DOMException && err.name === 'TimeoutError')
      throw new ApiTimeoutError(timeoutMs, err)
    if (err instanceof DOMException || (callerSignal?.aborted && err === callerSignal.reason))
      throw err
    throw new ApiNetworkError(err)
  } finally {
    clearTimeout(timer)  // el timeout NO gobierna la lectura del body (res.json/blob) — a propósito
    callerSignal?.removeEventListener('abort', onCallerAbort)
  }
}
