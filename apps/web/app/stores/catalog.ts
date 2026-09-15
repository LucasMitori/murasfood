/**
 * Catalog store.
 *
 * Holds *filter state*, not server data. Product lists are fetched per page and
 * kept there; caching every product in a global store would grow without bound
 * and go stale against prices that change (spec §69).
 */
import { defineStore } from 'pinia'

export type ProductSort = 'relevance' | 'name' | '-name' | 'price' | '-price' | 'newest' | 'best_sellers'

interface CatalogFilters {
  search: string
  category: string
  brand: string
  tag: string
  minPrice: string
  maxPrice: string
  onSale: boolean
  inStock: boolean
  /**
   * `''` — everything; `in` — buyable now; `out` — the shelf gaps.
   *
   * Separate from `inStock` because a boolean has no third state: `false`
   * means "do not filter", so there was no way to ask for what is *missing* —
   * which is exactly the view where the "tell me when it's back" button lives.
   */
  availability: '' | 'in' | 'out'
  /** Minimum discount percentage, as a string so an empty field is empty. */
  minDiscount: string
  sort: ProductSort
  page: number
}

const DEFAULT_FILTERS: CatalogFilters = {
  search: '',
  category: '',
  brand: '',
  tag: '',
  minPrice: '',
  maxPrice: '',
  onSale: false,
  inStock: false,
  availability: '',
  minDiscount: '',
  sort: 'relevance',
  page: 1,
}

export const useCatalogStore = defineStore('catalog', {
  state: (): { filters: CatalogFilters, recentSearches: string[] } => ({
    filters: { ...DEFAULT_FILTERS },
    recentSearches: [],
  }),

  getters: {
    /** Filters that actually narrow the list, for the "clear filters" chip row. */
    activeFilterCount: (state): number => {
      let count = 0
      if (state.filters.category) count += 1
      if (state.filters.brand) count += 1
      if (state.filters.tag) count += 1
      if (state.filters.minPrice) count += 1
      if (state.filters.maxPrice) count += 1
      if (state.filters.onSale) count += 1
      if (state.filters.inStock) count += 1
      if (state.filters.availability) count += 1
      if (state.filters.minDiscount) count += 1
      return count
    },

    hasActiveFilters(): boolean {
      return this.activeFilterCount > 0
    },

    /** Query parameters for `GET /catalog/products/`. */
    queryParams: (state): Record<string, string | number | boolean> => {
      const query: Record<string, string | number | boolean> = {
        page: state.filters.page,
        sort: state.filters.sort,
      }
      if (state.filters.search) query.q = state.filters.search
      if (state.filters.category) query.category = state.filters.category
      if (state.filters.brand) query.brand = state.filters.brand
      if (state.filters.tag) query.tag = state.filters.tag
      if (state.filters.minPrice) query.min_price = state.filters.minPrice
      if (state.filters.maxPrice) query.max_price = state.filters.maxPrice
      if (state.filters.onSale) query.on_sale = true
      if (state.filters.inStock) query.in_stock = true
      if (state.filters.availability) query.availability = state.filters.availability
      if (state.filters.minDiscount) query.min_discount = state.filters.minDiscount
      return query
    },
  },

  actions: {
    /** Apply a partial filter change, resetting pagination.
     *
     * Staying on page 4 after narrowing to a handful of results is a classic
     * way to show an empty list to someone who has just filtered.
     */
    setFilters(patch: Partial<CatalogFilters>): void {
      const keepPage = 'page' in patch
      this.filters = { ...this.filters, ...patch }
      if (!keepPage) this.filters.page = 1
    },

    setSearch(term: string): void {
      this.setFilters({ search: term })
      this.rememberSearch(term)
    },

    setPage(page: number): void {
      this.filters.page = Math.max(1, page)
    },

    reset(): void {
      this.filters = { ...DEFAULT_FILTERS }
    },

    clearFilters(): void {
      const { search, sort } = this.filters
      this.filters = { ...DEFAULT_FILTERS, search, sort }
    },

    rememberSearch(term: string): void {
      const cleaned = term.trim()
      if (cleaned.length < 2) return
      this.recentSearches = [cleaned, ...this.recentSearches.filter(item => item !== cleaned)].slice(0, 8)
    },
  },
})
