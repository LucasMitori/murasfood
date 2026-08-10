/**
 * Server-side table state.
 *
 * `v-data-table-server` is easy to get subtly wrong, and every failure mode is
 * user-visible. This composable exists to handle them in one place:
 *
 * **Feedback loops.** The table emits `update:options` on mount, and again
 * whenever its bound items change. Fetching on every emission means a fetch
 * triggers an emission triggers a fetch. Requests are therefore keyed by a
 * *signature* of what they would ask for, and an identical signature never
 * fetches twice.
 *
 * **Stale responses.** Page 3 requested, then page 4 before page 3 returns —
 * without sequencing, the slower response wins and the table shows page 3 while
 * the pager says 4. Each request carries a monotonic id and late responses are
 * dropped.
 *
 * **Pages that stop existing.** Filtering from 200 rows to 8 while on page 5
 * leaves an empty table that looks broken. The page is clamped to the last real
 * one and re-fetched exactly once.
 *
 * **Deleting the last row on a page.** Same symptom, different cause; handled
 * the same way.
 *
 * **"All" items per page.** Vuetify sends `-1`, which as `page_size=-1` is
 * either an error or an unbounded query. It is clamped to the API's maximum.
 */
import { computed, ref, shallowRef, watch } from 'vue'
import type { DataTableOptions, SortItem } from '~/types/ui'
import type { Paginated } from '~/types/api'
import { ApiRequestError } from '~/utils/api-client'
import { useApiClient } from '~/utils/api-registry'

/** Default page size across every admin table. */
export const DEFAULT_ITEMS_PER_PAGE = 25

/** Page sizes offered in the footer. "All" is deliberately absent. */
export const ITEMS_PER_PAGE_OPTIONS = [10, 25, 50, 100]

/**
 * Hard ceiling, matching `LargePagination.max_page_size` on the API.
 * Asking for more returns fewer rows than requested, which breaks paging maths.
 */
export const MAX_ITEMS_PER_PAGE = 100

/** How long to wait before searching as the user types. */
const SEARCH_DEBOUNCE_MS = 350

export interface ServerTableConfig<TRow> {
  /** API path, or a getter for one that depends on route params. */
  endpoint: string | (() => string)

  /** Page size. Defaults to 25. */
  itemsPerPage?: number

  /** Initial sort, in Vuetify's shape. */
  defaultSort?: SortItem[]

  /**
   * Column key -> API ordering field, for when they differ.
   * Unmapped keys are sent as-is.
   */
  sortMap?: Record<string, string>

  /** Extra query parameters. Re-read on every request; changes reset to page 1. */
  filters?: () => Record<string, string | number | boolean | undefined | null>

  /** Query parameter carrying the search term. Defaults to `search`. */
  searchParam?: string

  /** Map each API row before it reaches the table. */
  transform?: (row: unknown) => TRow

  /** Fetch immediately. Off when the table waits for the user to filter first. */
  immediate?: boolean
}

export function useServerTable<TRow = Record<string, unknown>>(config: ServerTableConfig<TRow>) {
  const items = shallowRef<TRow[]>([])
  const total = ref(0)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const page = ref(1)
  const itemsPerPage = ref(clampPageSize(config.itemsPerPage ?? DEFAULT_ITEMS_PER_PAGE))
  const sortBy = ref<SortItem[]>(config.defaultSort ? [...config.defaultSort] : [])
  const search = ref('')

  /** Signature of the last request actually issued; guards the feedback loop. */
  let lastSignature = ''
  /** Monotonic request id; anything older than `latestRequestId` is discarded. */
  let latestRequestId = 0
  /** Set while a clamp is pending so it cannot recurse. */
  let clampingPage = false
  let searchTimer: ReturnType<typeof setTimeout> | null = null
  let inFlight: AbortController | null = null

  const totalPages = computed(() =>
    Math.max(1, Math.ceil(total.value / Math.max(1, itemsPerPage.value))),
  )

  const isEmpty = computed(() => !loading.value && items.value.length === 0)

  /** Index range shown, for a "showing 26–50 of 312" label. */
  const range = computed(() => {
    if (total.value === 0) return { from: 0, to: 0 }
    const from = (page.value - 1) * itemsPerPage.value + 1
    return { from, to: Math.min(from + items.value.length - 1, total.value) }
  })

  function resolveEndpoint(): string {
    return typeof config.endpoint === 'function' ? config.endpoint() : config.endpoint
  }

  /** Build the query the API will receive. */
  function buildQuery(): Record<string, string | number | boolean> {
    const query: Record<string, string | number | boolean> = {
      page: page.value,
      page_size: clampPageSize(itemsPerPage.value),
    }

    const ordering = buildOrdering(sortBy.value, config.sortMap)
    if (ordering) query.ordering = ordering

    if (search.value.trim()) query[config.searchParam ?? 'search'] = search.value.trim()

    for (const [key, value] of Object.entries(config.filters?.() ?? {})) {
      if (value !== undefined && value !== null && value !== '') query[key] = value
    }

    return query
  }

  /** Stable string identity of a request, used to suppress duplicates. */
  function signatureOf(query: Record<string, string | number | boolean>): string {
    return `${resolveEndpoint()}?${Object.keys(query)
      .sort()
      .map(key => `${key}=${String(query[key])}`)
      .join('&')}`
  }

  /**
   * Fetch a page.
   *
   * @param force Bypass the duplicate-signature guard. Used by `refresh()` and
   *   after a mutation, where the same query must genuinely run again.
   */
  async function load(force = false): Promise<void> {
    const query = buildQuery()
    const signature = signatureOf(query)

    if (!force && signature === lastSignature) return
    lastSignature = signature

    // Cancel whatever is still in flight; its answer is already obsolete.
    inFlight?.abort()
    const controller = new AbortController()
    inFlight = controller

    const requestId = ++latestRequestId
    loading.value = true
    error.value = null

    try {
      const response = await useApiClient().get<Paginated<unknown>>(resolveEndpoint(), {
        query,
        signal: controller.signal,
      })

      // A newer request has started; this answer is stale.
      if (requestId !== latestRequestId) return

      items.value = config.transform
        ? response.results.map(config.transform)
        : (response.results as TRow[])
      total.value = response.count ?? 0

      await clampPageIfNeeded()
    }
    catch (thrown) {
      if (requestId !== latestRequestId || isAbort(thrown)) return

      error.value = thrown instanceof ApiRequestError ? thrown.code : 'ERROR'
      items.value = []
      total.value = 0
    }
    finally {
      if (requestId === latestRequestId) {
        loading.value = false
        inFlight = null
      }
    }
  }

  /**
   * Pull the page back into range when the result set shrank underneath it.
   *
   * Runs at most once per response: after clamping, the re-fetch lands on a page
   * that exists, so the condition cannot hold again.
   */
  async function clampPageIfNeeded(): Promise<void> {
    if (clampingPage) {
      clampingPage = false
      return
    }

    const lastPage = totalPages.value
    if (page.value > lastPage) {
      clampingPage = true
      page.value = lastPage
      await load(true)
    }
  }

  /** Handle `@update:options` from `v-data-table-server`. */
  function onOptionsUpdate(options: DataTableOptions): void {
    page.value = Math.max(1, options.page || 1)
    itemsPerPage.value = clampPageSize(options.itemsPerPage)
    sortBy.value = options.sortBy ?? []
    void load()
  }

  /** Re-run the current query, ignoring the duplicate guard. */
  async function refresh(): Promise<void> {
    await load(true)
  }

  /**
   * Reload after a row was removed.
   *
   * When the deleted row was the only one on its page, stepping back avoids the
   * empty table a plain refresh would leave behind.
   */
  async function refreshAfterDelete(): Promise<void> {
    if (items.value.length <= 1 && page.value > 1) page.value -= 1
    await load(true)
  }

  /** Jump to a page, clamped to what exists. */
  function goToPage(target: number): void {
    page.value = Math.min(Math.max(1, target), totalPages.value)
    void load()
  }

  /** Apply a search term, debounced, always restarting at page 1. */
  function setSearch(term: string): void {
    if (searchTimer) clearTimeout(searchTimer)
    searchTimer = setTimeout(() => {
      search.value = term
      page.value = 1
      void load()
    }, SEARCH_DEBOUNCE_MS)
  }

  /** Call after changing anything the `filters` getter reads. */
  function applyFilters(): void {
    page.value = 1
    void load()
  }

  /** Back to the initial page, sort and search. */
  function reset(): void {
    page.value = 1
    itemsPerPage.value = clampPageSize(config.itemsPerPage ?? DEFAULT_ITEMS_PER_PAGE)
    sortBy.value = config.defaultSort ? [...config.defaultSort] : []
    search.value = ''
    void load(true)
  }

  // Changing the page size mid-browse should not strand the user on a page that
  // no longer exists.
  watch(itemsPerPage, () => {
    page.value = 1
  })

  if (config.immediate !== false) void load()

  return {
    // State
    items,
    total,
    totalPages,
    loading,
    error,
    page,
    itemsPerPage,
    sortBy,
    search,
    isEmpty,
    range,

    // Actions
    load,
    refresh,
    refreshAfterDelete,
    onOptionsUpdate,
    goToPage,
    setSearch,
    applyFilters,
    reset,
  }
}

/**
 * Convert Vuetify's `sortBy` into a DRF `ordering` value.
 *
 * Vuetify represents descending as `order: 'desc'`; DRF wants a `-` prefix.
 */
export function buildOrdering(sortBy: SortItem[], sortMap?: Record<string, string>): string {
  return sortBy
    .filter(item => Boolean(item?.key))
    .map((item) => {
      const field = sortMap?.[item.key] ?? item.key
      const descending = item.order === 'desc' || item.order === false
      return descending ? `-${field}` : field
    })
    .join(',')
}

/**
 * Keep a page size within what the API will honour.
 *
 * Vuetify sends `-1` for "All"; passing that through produces either a 400 or an
 * unbounded query, and either way the paging maths stop working.
 */
export function clampPageSize(value: number): number {
  if (!Number.isFinite(value) || value <= 0) return MAX_ITEMS_PER_PAGE
  return Math.min(Math.trunc(value), MAX_ITEMS_PER_PAGE)
}

function isAbort(thrown: unknown): boolean {
  return thrown instanceof DOMException
    ? thrown.name === 'AbortError'
    : (thrown as { name?: string })?.name === 'AbortError'
}
