/**
 * Shopping lists store.
 *
 * The behaviour worth pinning down is what happens around a *partial* copy
 * into the cart, since that is the normal outcome for a list kept for months.
 */
import { describe, expect, it, vi } from 'vitest'
import { setApiClient } from '../../app/utils/api-registry'
import { useShoppingListsStore } from '../../app/stores/shoppingLists'

function stubClient(overrides: Record<string, unknown> = {}) {
  const client = {
    get: vi.fn().mockResolvedValue([]),
    post: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
    put: vi.fn(),
    delete: vi.fn().mockResolvedValue({}),
    request: vi.fn(),
    ...overrides,
  }
  setApiClient(client as never)
  return client
}

const detail = (items: unknown[] = []) => ({
  id: 'list-1',
  name: 'Mensal',
  note: '',
  items,
  item_count: items.length,
  estimated_total: '0.00',
  updated_at: '2026-08-10T00:00:00Z',
})

describe('loading', () => {
  it('reads the index as a plain array, not a paginated envelope', async () => {
    const client = stubClient({
      get: vi.fn().mockResolvedValue([{ id: 'a', name: 'Mensal', note: '', item_count: 3, updated_at: '' }]),
    })
    const store = useShoppingListsStore()

    await store.fetch()

    expect(client.get).toHaveBeenCalledWith('/shopping-lists/')
    expect(store.count).toBe(1)
    expect(store.hasLists).toBe(true)
  })

  it('clears the loading flag even when the request fails', async () => {
    stubClient({ get: vi.fn().mockRejectedValue(new Error('offline')) })
    const store = useShoppingListsStore()

    await expect(store.fetch()).rejects.toThrow('offline')
    expect(store.loading).toBe(false)
  })
})

describe('items', () => {
  it('keeps the index count in step without refetching', async () => {
    stubClient({ post: vi.fn().mockResolvedValue(detail([{ id: 'i1' }, { id: 'i2' }])) })
    const store = useShoppingListsStore()
    store.lists = [{ id: 'list-1', name: 'Mensal', note: '', item_count: 0, updated_at: '' }]

    await store.setItem('list-1', 'product-1', 2)

    // A second round trip just to refresh a number would be wasteful.
    expect(store.lists[0]?.item_count).toBe(2)
    expect(store.current?.items).toHaveLength(2)
  })

  it('sends the quantity as a string so decimals survive the wire', async () => {
    const client = stubClient({ post: vi.fn().mockResolvedValue(detail()) })
    const store = useShoppingListsStore()

    await store.setItem('list-1', 'product-1', 1.5)

    expect(client.post).toHaveBeenCalledWith(
      '/shopping-lists/list-1/items/',
      { product: 'product-1', quantity: '1.5' },
    )
  })

  it('takes the refreshed list back from a delete', async () => {
    stubClient({ delete: vi.fn().mockResolvedValue(detail([{ id: 'i1' }])) })
    const store = useShoppingListsStore()
    store.lists = [{ id: 'list-1', name: 'Mensal', note: '', item_count: 2, updated_at: '' }]

    await store.removeItem('list-1', 'i1')

    expect(store.lists[0]?.item_count).toBe(1)
  })
})

describe('copying into the cart', () => {
  it('surfaces both halves of a partial result', async () => {
    stubClient({
      post: vi.fn().mockResolvedValue({
        added: [{ product_id: 'p1', product: 'Arroz' }],
        skipped: [{ product_id: 'p2', product: 'Feijão', reason: 'OUT_OF_STOCK', detail: 'Sem estoque' }],
        added_count: 1,
        skipped_count: 1,
      }),
    })
    const store = useShoppingListsStore()

    const result = await store.addToCart('list-1')

    // Silently dropping the skipped line would leave the customer short.
    expect(result.added_count).toBe(1)
    expect(result.skipped_count).toBe(1)
    expect(result.skipped[0]?.product).toBe('Feijão')
  })
})

describe('removing a list', () => {
  it('drops the open list when it is the one deleted', async () => {
    stubClient({ get: vi.fn().mockResolvedValue([]) })
    const store = useShoppingListsStore()
    store.current = detail() as never

    await store.remove('list-1')

    expect(store.current).toBeNull()
  })

  it('leaves a different open list alone', async () => {
    stubClient({ get: vi.fn().mockResolvedValue([]) })
    const store = useShoppingListsStore()
    store.current = { ...detail(), id: 'other' } as never

    await store.remove('list-1')

    expect(store.current?.id).toBe('other')
  })
})
