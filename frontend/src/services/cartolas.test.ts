import { describe, it, expect, vi, afterEach } from 'vitest'
import { validateBalance, type BalanceDiscrepancyError } from './cartolas'

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

const BODY = { opening: '0', closing: '-1000', override_justification: null }

describe('validateBalance — confirm async (Fase 3 batch 2)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('202 → devuelve ConfirmAccepted {status: confirming} (el resultado llega por el poll)', async () => {
    mockFetchResponse(202, { status: 'confirming', batch_id: 'b-1' })
    await expect(validateBalance('b-1', BODY)).resolves.toEqual({
      status: 'confirming',
      batch_id: 'b-1',
    })
  })

  it('400 VALIDATION_FAILED → sigue tirando el error tipado con diff/calculated/stated', async () => {
    mockFetchResponse(400, {
      error: {
        code: 'VALIDATION_FAILED',
        message: 'El balance no cuadra',
        diff: -500,
        calculated: -1500,
        stated: -1000,
      },
    })
    const err = (await validateBalance('b-1', BODY).catch((e: unknown) => e)) as BalanceDiscrepancyError
    expect(err.code).toBe('VALIDATION_FAILED')
    expect(err.message).toBe('El balance no cuadra')
    expect(err.diff).toBe(-500)
    expect(err.calculated).toBe(-1500)
    expect(err.stated).toBe(-1000)
  })

  it('200 sincrónico (contrato viejo) → devuelve el resultado tal cual', async () => {
    mockFetchResponse(200, { status: 'validated', git_sha: 'abc1234' })
    await expect(validateBalance('b-1', BODY)).resolves.toEqual({
      status: 'validated',
      git_sha: 'abc1234',
    })
  })
})
