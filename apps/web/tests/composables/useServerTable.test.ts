/**
 * Server-side table pagination.
 *
 * These are the failure modes that make `v-data-table-server` unpleasant, each
 * pinned down so a refactor cannot quietly reintroduce one.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import {
  DEFAULT_ITEMS_PER_PAGE,
  MAX_ITEMS_PER_PAGE,
  buildOrdering,
  clampPageSize,
  useServerTable,
} from '../../app/composables/useServerTable'
import { setApiClient } from '../../app/utils/api-registry'
import { ApiRequestError } from '../../app/utils/api-client'

interface PageResponse {
  count: number
  results: Array<Record<string, unknown>>
}

function page(count: number, rows = 3): PageResponse {
  return {
    count,
    results: Array.from({ length: rows }, (_, index) => ({ id: `row-${index}` })),
  }
}

/** Install a stub client and return the `get` spy. */
function stubApi(get: ReturnType<typeof vi.fn>) {
  setApiClient({
    get,
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    request: vi.fn(),
  } as never)
  return get
}

/** Let every pending microtask settle. */
async function flush(): Promise<void> {
  await nextTick()
  await Promise.resolve()
  await Promise.resolve()
  await nextTick()
}

/** The query object of the nth call. */
function queryOf(get: ReturnType<typeof vi.fn>, index = 0): Record<string, unknown> {
  return get.mock.calls[index]?.[1]?.query ?? {}
}

describe('initial load', () => {
  it('requests page 1 with 25 items', async () => {
    const get = stubApi(vi.fn().mockResolvedValue(page(100)))
    useServerTable({ endpoint: '/admin/products/' })
    await flush()

    expect(get).toHaveBeenCalledTimes(1)
    expect(queryOf(get)).toMatchObject({ page: 1, page_size: DEFAULT_ITEMS_PER_PAGE })
  })

  it('can be told not to fetch immediately', async () => {
    const get = stubApi(vi.fn().mockResolvedValue(page(0)))
    useServerTable({ endpoint: '/admin/products/', immediate: false })
    await flush()

    expect(get).not.toHaveBeenCalled()
  })

  it('exposes total pages and the displayed range', async () => {
    stubApi(vi.fn().mockResolvedValue(page(100, 25)))
    const table = useServerTable({ endpoint: '/x/' })
    await flush()

    expect(table.total.value).toBe(100)
    expect(table.totalPages.value).toBe(4)
    expect(table.range.value).toEqual({ from: 1, to: 25 })
  })
})

describe('the feedback loop', () => {
  it('does not refetch when the table re-emits identical options', async () => {
    // `v-data-table-server` emits `update:options` whenever its items change,
    // so fetching on every emission is an infinite loop.
    const get = stubApi(vi.fn().mockResolvedValue(page(100)))
    const table = useServerTable({ endpoint: '/x/' })
    await flush()

    table.onOptionsUpdate({ page: 1, itemsPerPage: 25, sortBy: [] })
    await flush()
    table.onOptionsUpdate({ page: 1, itemsPerPage: 25, sortBy: [] })
    await flush()

    expect(get).toHaveBeenCalledTimes(1)
  })

  it('does fetch when the options genuinely change', async () => {
    const get = stubApi(vi.fn().mockResolvedValue(page(100)))
    const table = useServerTable({ endpoint: '/x/' })
    await flush()

    table.onOptionsUpdate({ page: 2, itemsPerPage: 25, sortBy: [] })
    await flush()

    expect(get).toHaveBeenCalledTimes(2)
    expect(queryOf(get, 1)).toMatchObject({ page: 2 })
  })

  it('refresh() bypasses the duplicate guard', async () => {
    const get = stubApi(vi.fn().mockResolvedValue(page(100)))
    const table = useServerTable({ endpoint: '/x/' })
    await flush()

    await table.refresh()
    expect(get).toHaveBeenCalledTimes(2)
  })
})

describe('stale responses', () => {
  it('ignores an earlier request that resolves last', async () => {
    // Page 2 requested, then page 3; page 2 answers second. Without sequencing
    // the table would show page 2 while the pager reads 3.
    const resolvers: Array<(value: PageResponse) => void> = []
    const get = stubApi(vi.fn(() => new Promise<PageResponse>((resolve) => {
      resolvers.push(resolve)
    })))

    const table = useServerTable({ endpoint: '/x/' })
    await flush()

    table.onOptionsUpdate({ page: 2, itemsPerPage: 25, sortBy: [] })
    await flush()
    table.onOptionsUpdate({ page: 3, itemsPerPage: 25, sortBy: [] })
    await flush()

    // Answer the newest request first, then the stale one.
    resolvers[2]?.({ count: 100, results: [{ id: 'from-page-3' }] })
    await flush()
    resolvers[1]?.({ count: 100, results: [{ id: 'from-page-2' }] })
    await flush()

    expect(table.items.value).toEqual([{ id: 'from-page-3' }])
    expect(get).toHaveBeenCalledTimes(3)
  })
})

describe('pages that stop existing', () => {
  it('clamps to the last page when the result set shrinks', async () => {
    // On page 5 of 8, then a filter cuts the set to 30 rows (2 pages).
    const get = stubApi(vi.fn()
      .mockResolvedValueOnce(page(200))
      .mockResolvedValueOnce(page(30))
      .mockResolvedValueOnce(page(30, 5)))

    const table = useServerTable({ endpoint: '/x/' })
    await flush()

    table.onOptionsUpdate({ page: 5, itemsPerPage: 25, sortBy: [] })
    await flush()

    expect(table.page.value).toBe(2)
    // One extra request to fetch the page that actually exists.
    expect(get).toHaveBeenCalledTimes(3)
    expect(queryOf(get, 2)).toMatchObject({ page: 2 })
  })

  it('clamps at most once, so it cannot recurse', async () => {
    const get = vi.fn().mockResolvedValue(page(10))
    stubApi(get)
    const table = useServerTable({ endpoint: '/x/' })
    await flush()

    table.onOptionsUpdate({ page: 9, itemsPerPage: 25, sortBy: [] })
    await flush()

    expect(table.page.value).toBe(1)
    // Initial load, the out-of-range request, and one clamped retry.
    expect(get.mock.calls.length).toBeLessThanOrEqual(3)
  })

  it('steps back a page when the last row on it is deleted', async () => {
    // 26 rows over two pages; the second holds a single row, which is deleted.
    stubApi(vi.fn()
      .mockResolvedValueOnce(page(26, 25))
      .mockResolvedValueOnce(page(26, 1))
      .mockResolvedValueOnce(page(25, 25)))

    const table = useServerTable({ endpoint: '/x/' })
    await flush()

    table.onOptionsUpdate({ page: 2, itemsPerPage: 25, sortBy: [] })
    await flush()
    expect(table.items.value).toHaveLength(1)

    await table.refreshAfterDelete()
    await flush()

    expect(table.page.value).toBe(1)
  })
})

describe('page size', () => {
  it('clamps "All" (-1) to the API maximum', () => {
    // Vuetify sends -1 for "All"; `page_size=-1` is either a 400 or an
    // unbounded query, and both break the paging maths.
    expect(clampPageSize(-1)).toBe(MAX_ITEMS_PER_PAGE)
    expect(clampPageSize(0)).toBe(MAX_ITEMS_PER_PAGE)
    expect(clampPageSize(500)).toBe(MAX_ITEMS_PER_PAGE)
    expect(clampPageSize(25)).toBe(25)
  })

  it('never sends a negative page size', async () => {
    const get = stubApi(vi.fn().mockResolvedValue(page(500)))
    const table = useServerTable({ endpoint: '/x/' })
    await flush()

    table.onOptionsUpdate({ page: 1, itemsPerPage: -1, sortBy: [] })
    await flush()

    expect(queryOf(get, 1).page_size).toBe(MAX_ITEMS_PER_PAGE)
  })

  it('returns to page 1 when the page size changes', async () => {
    stubApi(vi.fn().mockResolvedValue(page(500)))
    const table = useServerTable({ endpoint: '/x/' })
    await flush()

    table.onOptionsUpdate({ page: 4, itemsPerPage: 25, sortBy: [] })
    await flush()
    table.onOptionsUpdate({ page: 4, itemsPerPage: 50, sortBy: [] })
    await flush()

    expect(table.page.value).toBe(1)
  })
})

describe('sorting', () => {
  it('translates Vuetify sort into DRF ordering', () => {
    expect(buildOrdering([{ key: 'name', order: 'asc' }])).toBe('name')
    expect(buildOrdering([{ key: 'name', order: 'desc' }])).toBe('-name')
    expect(buildOrdering([])).toBe('')
  })

  it('applies the sort map for columns whose API field differs', () => {
    expect(buildOrdering([{ key: 'price', order: 'desc' }], { price: 'effective_price' }))
      .toBe('-effective_price')
  })

  it('supports multi-column sorting', () => {
    expect(buildOrdering([
      { key: 'status', order: 'asc' },
      { key: 'created_at', order: 'desc' },
    ])).toBe('status,-created_at')
  })

  it('sends the ordering parameter', async () => {
    const get = stubApi(vi.fn().mockResolvedValue(page(10)))
    const table = useServerTable({ endpoint: '/x/', sortMap: { price: 'effective_price' } })
    await flush()

    table.onOptionsUpdate({ page: 1, itemsPerPage: 25, sortBy: [{ key: 'price', order: 'desc' }] })
    await flush()

    expect(queryOf(get, 1).ordering).toBe('-effective_price')
  })
})

describe('search and filters', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('debounces typing into a single request', async () => {
    const get = stubApi(vi.fn().mockResolvedValue(page(10)))
    const table = useServerTable({ endpoint: '/x/' })
    await vi.advanceTimersByTimeAsync(0)

    table.setSearch('p')
    table.setSearch('pa')
    table.setSearch('pao')
    await vi.advanceTimersByTimeAsync(400)

    // One initial load plus one search.
    expect(get).toHaveBeenCalledTimes(2)
    expect(queryOf(get, 1).search).toBe('pao')
  })

  it('restarts at page 1 when the search changes', async () => {
    const get = stubApi(vi.fn().mockResolvedValue(page(500)))
    const table = useServerTable({ endpoint: '/x/' })
    await vi.advanceTimersByTimeAsync(0)

    table.onOptionsUpdate({ page: 5, itemsPerPage: 25, sortBy: [] })
    await vi.advanceTimersByTimeAsync(0)

    table.setSearch('pao')
    await vi.advanceTimersByTimeAsync(400)

    expect(table.page.value).toBe(1)
    expect(queryOf(get, get.mock.calls.length - 1)).toMatchObject({ page: 1 })
  })

  it('uses a custom search parameter name', async () => {
    const get = stubApi(vi.fn().mockResolvedValue(page(10)))
    const table = useServerTable({ endpoint: '/x/', searchParam: 'q' })
    await vi.advanceTimersByTimeAsync(0)

    table.setSearch('pao')
    await vi.advanceTimersByTimeAsync(400)

    expect(queryOf(get, 1).q).toBe('pao')
  })
})

describe('filters', () => {
  it('sends filter values and drops empty ones', async () => {
    const filters = { status: 'ACTIVE', category: '' as string | undefined }
    const get = stubApi(vi.fn().mockResolvedValue(page(10)))

    useServerTable({ endpoint: '/x/', filters: () => filters })
    await flush()

    expect(queryOf(get)).toMatchObject({ status: 'ACTIVE' })
    expect(queryOf(get)).not.toHaveProperty('category')
  })

  it('restarts at page 1 when filters are applied', async () => {
    const filters = { status: 'ACTIVE' }
    const get = stubApi(vi.fn().mockResolvedValue(page(500)))
    const table = useServerTable({ endpoint: '/x/', filters: () => filters })
    await flush()

    table.onOptionsUpdate({ page: 6, itemsPerPage: 25, sortBy: [] })
    await flush()

    filters.status = 'DRAFT'
    table.applyFilters()
    await flush()

    expect(table.page.value).toBe(1)
    expect(queryOf(get, get.mock.calls.length - 1)).toMatchObject({ page: 1, status: 'DRAFT' })
  })
})

describe('failures', () => {
  it('records the error code and empties the table', async () => {
    stubApi(vi.fn().mockRejectedValue(new ApiRequestError(500, { code: 'SERVER_ERROR', message: '' })))
    const table = useServerTable({ endpoint: '/x/' })
    await flush()

    expect(table.error.value).toBe('SERVER_ERROR')
    expect(table.items.value).toEqual([])
    expect(table.total.value).toBe(0)
    expect(table.loading.value).toBe(false)
  })

  it('clears a previous error on a successful reload', async () => {
    const get = stubApi(vi.fn()
      .mockRejectedValueOnce(new ApiRequestError(500, { code: 'SERVER_ERROR', message: '' }))
      .mockResolvedValueOnce(page(10)))

    const table = useServerTable({ endpoint: '/x/' })
    await flush()
    expect(table.error.value).toBe('SERVER_ERROR')

    await table.refresh()
    await flush()

    expect(table.error.value).toBeNull()
    expect(get).toHaveBeenCalledTimes(2)
  })
})

describe('transform and reset', () => {
  it('maps rows through the transform', async () => {
    stubApi(vi.fn().mockResolvedValue({ count: 1, results: [{ id: 'a', name: 'x' }] }))
    const table = useServerTable<{ label: string }>({
      endpoint: '/x/',
      transform: row => ({ label: String((row as { name: string }).name).toUpperCase() }),
    })
    await flush()

    expect(table.items.value).toEqual([{ label: 'X' }])
  })

  it('reset returns to the initial page, sort and search', async () => {
    stubApi(vi.fn().mockResolvedValue(page(500)))
    const table = useServerTable({ endpoint: '/x/', defaultSort: [{ key: 'name', order: 'asc' }] })
    await flush()

    table.onOptionsUpdate({ page: 4, itemsPerPage: 50, sortBy: [{ key: 'id', order: 'desc' }] })
    await flush()

    table.reset()
    await flush()

    expect(table.page.value).toBe(1)
    expect(table.itemsPerPage.value).toBe(DEFAULT_ITEMS_PER_PAGE)
    expect(table.sortBy.value).toEqual([{ key: 'name', order: 'asc' }])
    expect(table.search.value).toBe('')
  })
})

describe('endpoint', () => {
  it('accepts a getter for routes that depend on a parameter', async () => {
    let id = 'a'
    const get = stubApi(vi.fn().mockResolvedValue(page(1)))
    const table = useServerTable({ endpoint: () => `/admin/orders/${id}/items/` })
    await flush()

    expect(get.mock.calls[0][0]).toBe('/admin/orders/a/items/')

    id = 'b'
    await table.refresh()
    expect(get.mock.calls[1][0]).toBe('/admin/orders/b/items/')
  })
})
