/**
 * Typed API client.
 *
 * Deliberately framework-agnostic: it takes a `fetch`-shaped function so the
 * same code runs under Nuxt (`$fetch`), in tests (a stub), and in the mobile
 * app. Responsibilities:
 *
 * - attach the access token, tenant and cart headers,
 * - refresh an expired access token once and replay the request,
 * - normalise every failure into an `ApiError` the UI can branch on,
 * - never retry a non-idempotent payment operation (spec §68).
 */
import type { ApiError } from '~/types/api'

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  query?: Record<string, string | number | boolean | undefined | null>
  headers?: Record<string, string>
  /** Sent as `Idempotency-Key`; required for checkout and payment creation. */
  idempotencyKey?: string
  /** Skip the Authorization header even when a token exists. */
  anonymous?: boolean
  signal?: AbortSignal
}

export interface ApiClientOptions {
  baseUrl: string
  /** Reads the current access token, or `null` when signed out. */
  getAccessToken: () => string | null
  getRefreshToken: () => string | null
  /** Persists a refreshed token pair. */
  onTokensRefreshed: (tokens: { access: string, refresh: string }) => void
  /** Called when refreshing fails and the session is definitively over. */
  onAuthenticationLost: () => void
  getTenant: () => string | null
  getCartToken: () => string | null
  setCartToken: (token: string) => void
  fetchImpl?: typeof globalThis.fetch
}

/** A failed request, carrying the API's error envelope. */
export class ApiRequestError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>
  readonly requestId?: string

  constructor(status: number, error: ApiError) {
    super(error.message)
    this.name = 'ApiRequestError'
    this.status = status
    this.code = error.code
    this.details = error.details ?? {}
    this.requestId = error.request_id
  }

  /** Field-level validation messages, keyed by field name. */
  get fieldErrors(): Record<string, string[]> {
    if (this.code !== 'VALIDATION_ERROR') return {}

    const result: Record<string, string[]> = {}
    for (const [field, messages] of Object.entries(this.details)) {
      if (Array.isArray(messages)) result[field] = messages.map(String)
      else if (typeof messages === 'string') result[field] = [messages]
    }
    return result
  }
}

/** Requests that may safely be replayed after a token refresh. */
const REPLAYABLE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS', 'PUT', 'DELETE', 'PATCH'])

export class ApiClient {
  private readonly options: ApiClientOptions
  private readonly fetchImpl: typeof globalThis.fetch
  /** In-flight refresh, shared so parallel 401s trigger only one. */
  private refreshPromise: Promise<boolean> | null = null

  constructor(options: ApiClientOptions) {
    this.options = options
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis)
  }

  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const response = await this.send(path, options)

    if (response.status === 401 && !options.anonymous && this.options.getRefreshToken()) {
      const refreshed = await this.refreshOnce()
      // A POST is only replayed when the caller supplied an idempotency key;
      // blindly retrying "create payment" would be how a customer gets charged
      // twice.
      const method = options.method ?? 'GET'
      const replayable = REPLAYABLE_METHODS.has(method) || Boolean(options.idempotencyKey)

      if (refreshed && replayable) {
        return this.unwrap<T>(await this.send(path, options))
      }
      if (!refreshed) this.options.onAuthenticationLost()
    }

    return this.unwrap<T>(response)
  }

  /**
   * Fetch a file rather than JSON.
   *
   * `request` parses every response body as JSON, which a spreadsheet is not.
   * This keeps the same authentication and token-refresh behaviour and hands
   * back the bytes together with the name the server chose.
   *
   * The filename is only readable because the export endpoints expose
   * `Content-Disposition` across origins; without that the browser would save
   * every download as "export".
   */
  async download(
    path: string,
    options: Omit<RequestOptions, 'method' | 'body'> = {},
  ): Promise<{ blob: Blob, filename: string }> {
    let response = await this.send(path, { ...options, method: 'GET' })

    if (response.status === 401 && !options.anonymous && this.options.getRefreshToken()) {
      if (await this.refreshOnce()) {
        response = await this.send(path, { ...options, method: 'GET' })
      }
      else {
        this.options.onAuthenticationLost()
      }
    }

    if (!response.ok) {
      // Errors still come back as JSON, so the normal unwrapping raises the
      // usual ApiRequestError and the caller shows the usual message.
      return this.unwrap(response)
    }

    return {
      blob: await response.blob(),
      filename: filenameFrom(response.headers.get('Content-Disposition')),
    }
  }

  get<T>(path: string, options: Omit<RequestOptions, 'method' | 'body'> = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: 'GET' })
  }

  post<T>(path: string, body?: unknown, options: Omit<RequestOptions, 'method'> = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: 'POST', body })
  }

  patch<T>(path: string, body?: unknown, options: Omit<RequestOptions, 'method'> = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: 'PATCH', body })
  }

  put<T>(path: string, body?: unknown, options: Omit<RequestOptions, 'method'> = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: 'PUT', body })
  }

  delete<T>(path: string, options: Omit<RequestOptions, 'method'> = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: 'DELETE' })
  }

  // --- Internals -----------------------------------------------------------
  private buildUrl(path: string, query?: RequestOptions['query']): string {
    const base = this.options.baseUrl.replace(/\/+$/, '')
    const suffix = path.startsWith('/') ? path : `/${path}`
    const url = `${base}${suffix}`

    if (!query) return url

    const params = new URLSearchParams()
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== '') params.append(key, String(value))
    }
    const queryString = params.toString()
    return queryString ? `${url}?${queryString}` : url
  }

  private buildHeaders(options: RequestOptions): Record<string, string> {
    const headers: Record<string, string> = {
      Accept: 'application/json',
      ...options.headers,
    }

    if (options.body !== undefined && !(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json'
    }

    const token = options.anonymous ? null : this.options.getAccessToken()
    if (token) headers.Authorization = `Bearer ${token}`

    const tenant = this.options.getTenant()
    if (tenant) headers['X-Tenant'] = tenant

    const cartToken = this.options.getCartToken()
    if (cartToken) headers['X-Cart-Token'] = cartToken

    if (options.idempotencyKey) headers['Idempotency-Key'] = options.idempotencyKey

    return headers
  }

  private async send(path: string, options: RequestOptions): Promise<Response> {
    const body = options.body instanceof FormData
      ? options.body
      : options.body !== undefined
        ? JSON.stringify(options.body)
        : undefined

    const response = await this.fetchImpl(this.buildUrl(path, options.query), {
      method: options.method ?? 'GET',
      headers: this.buildHeaders(options),
      body: body as BodyInit | undefined,
      signal: options.signal,
      credentials: 'omit',
    })

    // The cart endpoints hand anonymous visitors a token to come back with.
    const cartToken = response.headers?.get?.('X-Cart-Token')
    if (cartToken) this.options.setCartToken(cartToken)

    return response
  }

  private async unwrap<T>(response: Response): Promise<T> {
    if (response.status === 204) return undefined as T

    const text = await response.text()
    const payload = text ? safeParse(text) : null

    if (!response.ok) {
      const envelope = (payload as { error?: ApiError } | null)?.error
      throw new ApiRequestError(
        response.status,
        envelope ?? {
          code: httpFallbackCode(response.status),
          message: response.statusText || 'Request failed',
        },
      )
    }

    return payload as T
  }

  private refreshOnce(): Promise<boolean> {
    // Coalesce: several requests failing at once must not each burn a refresh
    // token, which rotation would immediately invalidate.
    this.refreshPromise ??= this.performRefresh().finally(() => {
      this.refreshPromise = null
    })
    return this.refreshPromise
  }

  private async performRefresh(): Promise<boolean> {
    const refresh = this.options.getRefreshToken()
    if (!refresh) return false

    try {
      const response = await this.fetchImpl(this.buildUrl('/auth/refresh/'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ refresh }),
      })
      if (!response.ok) return false

      const tokens = safeParse(await response.text()) as { access?: string, refresh?: string } | null
      if (!tokens?.access) return false

      this.options.onTokensRefreshed({ access: tokens.access, refresh: tokens.refresh ?? refresh })
      return true
    }
    catch {
      return false
    }
  }
}

function safeParse(text: string): unknown {
  try {
    return JSON.parse(text)
  }
  catch {
    return null
  }
}

function httpFallbackCode(status: number): string {
  if (status === 401) return 'UNAUTHENTICATED'
  if (status === 403) return 'FORBIDDEN'
  if (status === 404) return 'NOT_FOUND'
  if (status === 429) return 'RATE_LIMITED'
  if (status >= 500) return 'SERVER_ERROR'
  return 'ERROR'
}

/** Random idempotency key for a money-moving request. */
export function newIdempotencyKey(): string {
  const cryptoObj = globalThis.crypto
  if (cryptoObj?.randomUUID) return cryptoObj.randomUUID()
  return `idem-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`
}

/**
 * Pull the filename out of a `Content-Disposition` header.
 *
 * Falls back to a generic name rather than failing: a download with an
 * awkward name is still a download, and the header is the server's courtesy
 * rather than something the client can insist on.
 */
function filenameFrom(header: string | null): string {
  const match = header?.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i)
  return match?.[1] ? decodeURIComponent(match[1]) : 'download'
}
