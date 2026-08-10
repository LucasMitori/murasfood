/**
 * Catalog filter state.
 */
import { describe, expect, it } from 'vitest'
import { useCatalogStore } from '../../app/stores/catalog'

describe('filters', () => {
  it('starts on page 1 with no active filters', () => {
    const catalog = useCatalogStore()

    expect(catalog.filters.page).toBe(1)
    expect(catalog.hasActiveFilters).toBe(false)
    expect(catalog.activeFilterCount).toBe(0)
  })

  it('resets pagination when a filter changes', () => {
    const catalog = useCatalogStore()
    catalog.setPage(4)

    catalog.setFilters({ category: 'padaria' })

    // Staying on page 4 after narrowing the result set shows an empty page.
    expect(catalog.filters.page).toBe(1)
  })

  it('keeps the page when the page itself is what changed', () => {
    const catalog = useCatalogStore()
    catalog.setFilters({ page: 3 })

    expect(catalog.filters.page).toBe(3)
  })

  it('counts the filters that narrow the list', () => {
    const catalog = useCatalogStore()
    catalog.setFilters({ category: 'padaria', onSale: true, minPrice: '10' })

    expect(catalog.activeFilterCount).toBe(3)
    expect(catalog.hasActiveFilters).toBe(true)
  })

  it('does not count sort or search as filters', () => {
    const catalog = useCatalogStore()
    catalog.setFilters({ search: 'pão', sort: 'price' })

    expect(catalog.activeFilterCount).toBe(0)
  })
})

describe('query parameters', () => {
  it('sends only what is set', () => {
    const catalog = useCatalogStore()

    expect(catalog.queryParams).toEqual({ page: 1, sort: 'relevance' })
  })

  it('maps filters to the API contract', () => {
    const catalog = useCatalogStore()
    catalog.setFilters({
      search: 'pão',
      category: 'padaria',
      minPrice: '5',
      maxPrice: '20',
      onSale: true,
      inStock: true,
      sort: 'price',
    })

    expect(catalog.queryParams).toMatchObject({
      q: 'pão',
      category: 'padaria',
      min_price: '5',
      max_price: '20',
      on_sale: true,
      in_stock: true,
      sort: 'price',
    })
  })
})

describe('clearing', () => {
  it('keeps the search term and sort order', () => {
    const catalog = useCatalogStore()
    catalog.setFilters({ search: 'pão', sort: 'price', category: 'padaria', onSale: true })

    catalog.clearFilters()

    expect(catalog.filters.search).toBe('pão')
    expect(catalog.filters.sort).toBe('price')
    expect(catalog.filters.category).toBe('')
    expect(catalog.filters.onSale).toBe(false)
  })

  it('reset returns everything to defaults', () => {
    const catalog = useCatalogStore()
    catalog.setFilters({ search: 'pão', category: 'padaria' })

    catalog.reset()

    expect(catalog.filters.search).toBe('')
    expect(catalog.filters.category).toBe('')
  })
})

describe('recent searches', () => {
  it('remembers terms most recent first without duplicates', () => {
    const catalog = useCatalogStore()

    catalog.setSearch('pão')
    catalog.setSearch('leite')
    catalog.setSearch('pão')

    expect(catalog.recentSearches).toEqual(['pão', 'leite'])
  })

  it('ignores terms that are too short to be useful', () => {
    const catalog = useCatalogStore()
    catalog.setSearch('a')

    expect(catalog.recentSearches).toEqual([])
  })

  it('caps the history', () => {
    const catalog = useCatalogStore()
    for (let index = 0; index < 12; index += 1) catalog.setSearch(`termo-${index}`)

    expect(catalog.recentSearches).toHaveLength(8)
  })
})
