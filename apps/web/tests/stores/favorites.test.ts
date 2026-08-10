/**
 * Favourites store — optimistic toggling with rollback.
 */
import { describe, expect, it, vi } from 'vitest'
import { setApiClient } from '../../app/utils/api-registry'
import { useFavoritesStore } from '../../app/stores/favorites'

function stubClient(overrides: Record<string, unknown> = {}) {
  const client = {
    get: vi.fn().mockResolvedValue({ results: [] }),
    post: vi.fn().mockResolvedValue({}),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    request: vi.fn(),
    ...overrides,
  }
  setApiClient(client as never)
  return client
}

describe('toggling', () => {
  it('adds a favourite immediately, before the request resolves', async () => {
    let resolveRequest: (() => void) | undefined
    stubClient({
      post: vi.fn(() => new Promise<void>((resolve) => { resolveRequest = resolve })),
    })
    const favorites = useFavoritesStore()

    const pending = favorites.toggle('product-1')
    // The heart must respond before the round trip completes.
    expect(favorites.isFavorite('product-1')).toBe(true)

    resolveRequest?.()
    await pending
    expect(favorites.isFavorite('product-1')).toBe(true)
  })

  it('removes an existing favourite', async () => {
    stubClient()
    const favorites = useFavoritesStore()
    favorites.applyLocal('product-1', true)

    const result = await favorites.toggle('product-1')

    expect(result).toBe(false)
    expect(favorites.isFavorite('product-1')).toBe(false)
  })

  it('rolls back when the request fails', async () => {
    stubClient({ post: vi.fn().mockRejectedValue(new Error('offline')) })
    const favorites = useFavoritesStore()

    await expect(favorites.toggle('product-1')).rejects.toThrow()
    expect(favorites.isFavorite('product-1')).toBe(false)
  })

  it('rolls back a removal too', async () => {
    stubClient({ post: vi.fn().mockRejectedValue(new Error('offline')) })
    const favorites = useFavoritesStore()
    favorites.applyLocal('product-1', true)

    await expect(favorites.toggle('product-1')).rejects.toThrow()
    expect(favorites.isFavorite('product-1')).toBe(true)
  })
})

describe('fetching', () => {
  it('loads ids from the API', async () => {
    stubClient({
      get: vi.fn().mockResolvedValue({
        results: [
          { id: 'f1', product: { id: 'p1' }, created_at: '' },
          { id: 'f2', product: { id: 'p2' }, created_at: '' },
        ],
      }),
    })
    const favorites = useFavoritesStore()

    await favorites.fetch()

    expect(favorites.ids).toEqual(['p1', 'p2'])
    expect(favorites.count).toBe(2)
  })

  it('records a failure without throwing', async () => {
    stubClient({ get: vi.fn().mockRejectedValue(new Error('offline')) })
    const favorites = useFavoritesStore()

    await favorites.fetch()

    expect(favorites.error).toBe('FAVORITES_UNAVAILABLE')
    expect(favorites.loading).toBe(false)
  })
})

describe('reset', () => {
  it('clears state on sign-out', () => {
    stubClient()
    const favorites = useFavoritesStore()
    favorites.applyLocal('product-1', true)

    favorites.reset()

    expect(favorites.ids).toEqual([])
    expect(favorites.count).toBe(0)
  })
})
