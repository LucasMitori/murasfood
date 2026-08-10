/**
 * API client behaviour.
 *
 * The security-relevant properties: tokens and tenant headers are attached, a
 * 401 refreshes once and replays *only* safe requests, and a non-idempotent
 * POST is never blindly retried.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiClient, ApiRequestError, newIdempotencyKey } from '../../app/utils/api-client'

interface StubOptions {
  status?: number
  body?: unknown
  headers?: Record<string, string>
}

function jsonResponse({ status = 200, body = {}, headers = {} }: StubOptions = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: '',
    headers: { get: (key: string) => headers[key] ?? null },
    text: async () => (body === undefined ? '' : JSON.stringify(body)),
  } as unknown as Response
}

function makeClient(fetchImpl: ReturnType<typeof vi.fn>, overrides: Record<string, unknown> = {}) {
  const state = { access: 'access-1', refresh: 'refresh-1', cartToken: '' }
  const onTokensRefreshed = vi.fn((tokens: { access: string, refresh: string }) => {
    state.access = tokens.access
    state.refresh = tokens.refresh
  })
  const onAuthenticationLost = vi.fn()
  const setCartToken = vi.fn((token: string) => (state.cartToken = token))

  const client = new ApiClient({
    baseUrl: 'https://api.test/api/v1',
    getAccessToken: () => state.access,
    getRefreshToken: () => state.refresh,
    onTokensRefreshed,
    onAuthenticationLost,
    getTenant: () => 'alfa',
    getCartToken: () => state.cartToken,
    setCartToken,
    fetchImpl: fetchImpl as unknown as typeof fetch,
    ...overrides,
  })

  return { client, state, onTokensRefreshed, onAuthenticationLost, setCartToken }
}

describe('request building', () => {
  let fetchImpl: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ body: { ok: true } }))
  })

  it('joins the base URL and path without doubling slashes', async () => {
    const { client } = makeClient(fetchImpl)
    await client.get('/catalog/products/')

    expect(fetchImpl.mock.calls[0][0]).toBe('https://api.test/api/v1/catalog/products/')
  })

  it('serialises query parameters and drops empty ones', async () => {
    const { client } = makeClient(fetchImpl)
    await client.get('/catalog/products/', { query: { page: 2, q: 'pão', empty: '', missing: undefined } })

    const url = String(fetchImpl.mock.calls[0][0])
    expect(url).toContain('page=2')
    expect(url).toContain('q=p%C3%A3o')
    expect(url).not.toContain('empty=')
    expect(url).not.toContain('missing=')
  })

  it('attaches the bearer token and tenant header', async () => {
    const { client } = makeClient(fetchImpl)
    await client.get('/customers/me/')

    const headers = fetchImpl.mock.calls[0][1].headers
    expect(headers.Authorization).toBe('Bearer access-1')
    expect(headers['X-Tenant']).toBe('alfa')
  })

  it('omits the token for anonymous requests', async () => {
    const { client } = makeClient(fetchImpl)
    await client.get('/tenants/current/', { anonymous: true })

    expect(fetchImpl.mock.calls[0][1].headers.Authorization).toBeUndefined()
  })

  it('sends the idempotency key when supplied', async () => {
    const { client } = makeClient(fetchImpl)
    await client.post('/orders/checkout/', { delivery_method: 'PICKUP' }, { idempotencyKey: 'key-1' })

    expect(fetchImpl.mock.calls[0][1].headers['Idempotency-Key']).toBe('key-1')
  })

  it('captures the cart token from the response', async () => {
    fetchImpl.mockResolvedValue(jsonResponse({ headers: { 'X-Cart-Token': 'cart-abc' } }))
    const { client, setCartToken } = makeClient(fetchImpl)

    await client.get('/cart/')
    expect(setCartToken).toHaveBeenCalledWith('cart-abc')
  })
})

describe('error handling', () => {
  it('unwraps the API error envelope', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({
      status: 409,
      body: { error: { code: 'INSUFFICIENT_STOCK', message: 'Sem estoque', details: { product: 'Arroz' } } },
    }))
    const { client } = makeClient(fetchImpl)

    await expect(client.post('/cart/items/', {})).rejects.toMatchObject({
      status: 409,
      code: 'INSUFFICIENT_STOCK',
      message: 'Sem estoque',
      details: { product: 'Arroz' },
    })
  })

  it('falls back to a code derived from the status', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ status: 500, body: undefined }))
    const { client } = makeClient(fetchImpl)

    await expect(client.get('/anything/')).rejects.toMatchObject({ code: 'SERVER_ERROR' })
  })

  it('exposes field errors for a validation failure', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({
      status: 400,
      body: { error: { code: 'VALIDATION_ERROR', message: 'Inválido', details: { email: ['Já existe'] } } },
    }))
    const { client } = makeClient(fetchImpl)

    try {
      await client.post('/auth/register/', {})
      expect.unreachable('should have thrown')
    }
    catch (error) {
      expect(error).toBeInstanceOf(ApiRequestError)
      expect((error as ApiRequestError).fieldErrors).toEqual({ email: ['Já existe'] })
    }
  })

  it('returns undefined for 204 responses', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ status: 204 }))
    const { client } = makeClient(fetchImpl)

    await expect(client.delete('/cart/items/1/')).resolves.toBeUndefined()
  })
})

describe('token refresh', () => {
  it('refreshes once and replays a GET', async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ status: 401, body: { error: { code: 'UNAUTHENTICATED', message: '' } } }))
      .mockResolvedValueOnce(jsonResponse({ body: { access: 'access-2', refresh: 'refresh-2' } }))
      .mockResolvedValueOnce(jsonResponse({ body: { id: 'user-1' } }))

    const { client, onTokensRefreshed } = makeClient(fetchImpl)
    const result = await client.get<{ id: string }>('/customers/me/')

    expect(result).toEqual({ id: 'user-1' })
    expect(onTokensRefreshed).toHaveBeenCalledWith({ access: 'access-2', refresh: 'refresh-2' })
    expect(fetchImpl).toHaveBeenCalledTimes(3)
  })

  it('does not replay a POST without an idempotency key', async () => {
    // Replaying "create payment" is how a customer gets charged twice.
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ status: 401, body: { error: { code: 'UNAUTHENTICATED', message: '' } } }))
      .mockResolvedValueOnce(jsonResponse({ body: { access: 'access-2', refresh: 'refresh-2' } }))

    const { client } = makeClient(fetchImpl)

    await expect(client.post('/payments/', { order: '1' })).rejects.toMatchObject({ status: 401 })
    expect(fetchImpl).toHaveBeenCalledTimes(2)
  })

  it('replays a POST that carries an idempotency key', async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ status: 401, body: { error: { code: 'UNAUTHENTICATED', message: '' } } }))
      .mockResolvedValueOnce(jsonResponse({ body: { access: 'access-2', refresh: 'refresh-2' } }))
      .mockResolvedValueOnce(jsonResponse({ status: 201, body: { number: 'MF-1' } }))

    const { client } = makeClient(fetchImpl)
    const order = await client.post<{ number: string }>('/orders/checkout/', {}, { idempotencyKey: 'k' })

    expect(order).toEqual({ number: 'MF-1' })
  })

  it('reports the session as lost when refreshing fails', async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ status: 401, body: { error: { code: 'UNAUTHENTICATED', message: '' } } }))
      .mockResolvedValueOnce(jsonResponse({ status: 401, body: {} }))

    const { client, onAuthenticationLost } = makeClient(fetchImpl)

    await expect(client.get('/customers/me/')).rejects.toBeInstanceOf(ApiRequestError)
    expect(onAuthenticationLost).toHaveBeenCalledOnce()
  })

  it('coalesces parallel refreshes into one', async () => {
    let refreshCalls = 0
    const fetchImpl = vi.fn(async (url: string) => {
      if (String(url).includes('/auth/refresh/')) {
        refreshCalls += 1
        return jsonResponse({ body: { access: 'access-2', refresh: 'refresh-2' } })
      }
      // Both initial calls fail; the replays succeed.
      return refreshCalls === 0
        ? jsonResponse({ status: 401, body: { error: { code: 'UNAUTHENTICATED', message: '' } } })
        : jsonResponse({ body: { ok: true } })
    })

    const { client } = makeClient(fetchImpl as never)
    await Promise.all([client.get('/a/'), client.get('/b/')])

    expect(refreshCalls).toBe(1)
  })
})

describe('newIdempotencyKey', () => {
  it('produces distinct keys', () => {
    expect(newIdempotencyKey()).not.toBe(newIdempotencyKey())
  })
})
