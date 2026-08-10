/**
 * Authentication store.
 *
 * Permission checks here only drive affordances; the tests assert they fail
 * closed, because a client-side check that defaults to "allow" quietly becomes
 * a security assumption.
 */
import { describe, expect, it, vi } from 'vitest'
import type { User } from '../../app/types/api'
import { ApiRequestError } from '../../app/utils/api-client'
import { setApiClient } from '../../app/utils/api-registry'
import { useAuthStore } from '../../app/stores/auth'
import { StorageKeys, readStorage } from '../../app/utils/storage'

function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: 'user-1',
    email: 'cliente@example.test',
    first_name: 'Carlos',
    last_name: 'Cliente',
    full_name: 'Carlos Cliente',
    phone: '',
    user_type: 'CUSTOMER',
    is_verified: true,
    marketing_opt_in: false,
    roles: [],
    permissions: [],
    created_at: new Date().toISOString(),
    ...overrides,
  }
}

function stubClient(overrides: Record<string, unknown> = {}) {
  const client = {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    request: vi.fn(),
    ...overrides,
  }
  setApiClient(client as never)
  return client
}

describe('login', () => {
  it('stores tokens and the profile', async () => {
    stubClient({
      post: vi.fn().mockResolvedValue({ access: 'a', refresh: 'r', user: makeUser() }),
    })
    const auth = useAuthStore()

    await auth.login('cliente@example.test', 'secret')

    expect(auth.isAuthenticated).toBe(true)
    expect(auth.user?.email).toBe('cliente@example.test')
    expect(readStorage(StorageKeys.accessToken)).toBe('a')
    expect(readStorage(StorageKeys.refreshToken)).toBe('r')
  })

  it('records the error code and rethrows', async () => {
    stubClient({
      post: vi.fn().mockRejectedValue(
        new ApiRequestError(401, { code: 'INVALID_CREDENTIALS', message: '' }),
      ),
    })
    const auth = useAuthStore()

    await expect(auth.login('a@b.test', 'wrong')).rejects.toBeInstanceOf(ApiRequestError)
    expect(auth.error).toBe('INVALID_CREDENTIALS')
    expect(auth.isAuthenticated).toBe(false)
    expect(auth.loading).toBe(false)
  })

  it('signs in anonymously so a stale token cannot break the attempt', async () => {
    const client = stubClient({
      post: vi.fn().mockResolvedValue({ access: 'a', refresh: 'r', user: makeUser() }),
    })
    const auth = useAuthStore()

    await auth.login('a@b.test', 'secret')
    expect(client.post).toHaveBeenCalledWith(
      '/auth/login/',
      { email: 'a@b.test', password: 'secret' },
      { anonymous: true },
    )
  })
})

describe('permissions', () => {
  it('denies everything when signed out', () => {
    stubClient()
    const auth = useAuthStore()

    expect(auth.can('orders.view')).toBe(false)
    expect(auth.canAll(['orders.view'])).toBe(false)
  })

  it('grants only the codes the profile carries', () => {
    stubClient()
    const auth = useAuthStore()
    auth.user = makeUser({ permissions: ['orders.view', 'catalog.view'] })

    expect(auth.can('orders.view')).toBe(true)
    expect(auth.can('orders.refund')).toBe(false)
    expect(auth.canAll(['orders.view', 'catalog.view'])).toBe(true)
    expect(auth.canAll(['orders.view', 'orders.refund'])).toBe(false)
  })

  it('recognises merchant users', () => {
    stubClient()
    const auth = useAuthStore()

    auth.user = makeUser({ user_type: 'CUSTOMER' })
    expect(auth.isMerchantUser).toBe(false)

    auth.user = makeUser({ user_type: 'MANAGER' })
    expect(auth.isMerchantUser).toBe(true)
  })
})

describe('profile', () => {
  it('clears tokens when the session is rejected', async () => {
    stubClient({
      get: vi.fn().mockRejectedValue(new ApiRequestError(401, { code: 'UNAUTHENTICATED', message: '' })),
    })
    const auth = useAuthStore()
    auth.setTokens({ access: 'a', refresh: 'r' })

    await auth.fetchProfile()

    expect(auth.isAuthenticated).toBe(false)
    expect(readStorage(StorageKeys.accessToken)).toBeNull()
  })

  it('skips the request when signed out', async () => {
    const client = stubClient()
    const auth = useAuthStore()

    await expect(auth.fetchProfile()).resolves.toBeNull()
    expect(client.get).not.toHaveBeenCalled()
  })
})

describe('logout', () => {
  it('clears local state even when the API call fails', async () => {
    stubClient({ post: vi.fn().mockRejectedValue(new Error('offline')) })
    const auth = useAuthStore()
    auth.setTokens({ access: 'a', refresh: 'r' })
    auth.user = makeUser()

    await auth.logout()

    expect(auth.isAuthenticated).toBe(false)
    expect(auth.user).toBeNull()
    expect(readStorage(StorageKeys.accessToken)).toBeNull()
  })
})
