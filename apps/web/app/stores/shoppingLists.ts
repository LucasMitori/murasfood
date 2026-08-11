/**
 * Shopping lists.
 *
 * Reusable sets of products — "the monthly shop" — that a customer copies into
 * the cart instead of picking every item again. Lists are planning, so they
 * hold no prices and are unaffected by stock: what is available is decided
 * when the list is copied, not when it is written.
 */
import { defineStore } from 'pinia'
import type { Product } from '~/types/api'
import { useApiClient } from '~/utils/api-registry'

export interface ShoppingListItem {
  id: string
  product: Product
  quantity: string
  unit_price: string
  line_total: string
  is_available: boolean
  note: string
}

export interface ShoppingListSummary {
  id: string
  name: string
  note: string
  item_count: number
  updated_at: string
}

export interface ShoppingListDetail extends Omit<ShoppingListSummary, 'item_count'> {
  items: ShoppingListItem[]
  item_count: number
  estimated_total: string
}

/** What `add-to-cart` reports back: partial success is the normal case. */
export interface AddToCartResult {
  added: { product_id: string, product: string }[]
  skipped: { product_id: string, product: string, reason: string, detail: string }[]
  added_count: number
  skipped_count: number
}

export const useShoppingListsStore = defineStore('shoppingLists', {
  state: (): {
    lists: ShoppingListSummary[]
    current: ShoppingListDetail | null
    loading: boolean
    saving: boolean
  } => ({
    lists: [],
    current: null,
    loading: false,
    saving: false,
  }),

  getters: {
    count: state => state.lists.length,
    hasLists: state => state.lists.length > 0,
  },

  actions: {
    async fetch(): Promise<void> {
      this.loading = true
      try {
        this.lists = await useApiClient().get<ShoppingListSummary[]>('/shopping-lists/')
      }
      finally {
        this.loading = false
      }
    },

    async open(id: string): Promise<ShoppingListDetail> {
      this.current = await useApiClient().get<ShoppingListDetail>(`/shopping-lists/${id}/`)
      return this.current
    },

    async create(name: string, note = ''): Promise<ShoppingListDetail> {
      this.saving = true
      try {
        const created = await useApiClient().post<ShoppingListDetail>('/shopping-lists/', { name, note })
        await this.fetch()
        return created
      }
      finally {
        this.saving = false
      }
    },

    async rename(id: string, name: string): Promise<void> {
      await useApiClient().patch(`/shopping-lists/${id}/`, { name })
      await this.fetch()
    },

    async remove(id: string): Promise<void> {
      await useApiClient().delete(`/shopping-lists/${id}/`)
      if (this.current?.id === id) this.current = null
      await this.fetch()
    },

    /** Add a product, or correct its quantity when already listed. */
    async setItem(listId: string, productId: string, quantity: string | number = 1): Promise<void> {
      this.current = await useApiClient().post<ShoppingListDetail>(
        `/shopping-lists/${listId}/items/`,
        { product: productId, quantity: String(quantity) },
      )
      this.syncCount(listId, this.current.items.length)
    },

    async removeItem(listId: string, itemId: string): Promise<void> {
      this.current = await useApiClient().delete<ShoppingListDetail>(
        `/shopping-lists/${listId}/items/${itemId}/`,
      )
      this.syncCount(listId, this.current.items.length)
    },

    async addToCart(listId: string): Promise<AddToCartResult> {
      return useApiClient().post<AddToCartResult>(`/shopping-lists/${listId}/add-to-cart/`)
    },

    async saveCartAs(name: string, note = ''): Promise<ShoppingListDetail> {
      this.saving = true
      try {
        const created = await useApiClient().post<ShoppingListDetail>(
          '/shopping-lists/from-cart/',
          { name, note },
        )
        await this.fetch()
        return created
      }
      finally {
        this.saving = false
      }
    },

    /** Keep the index in step without a second round trip. */
    syncCount(listId: string, itemCount: number): void {
      const row = this.lists.find(entry => entry.id === listId)
      if (row) row.item_count = itemCount
    },

    reset(): void {
      this.lists = []
      this.current = null
    },
  },
})
