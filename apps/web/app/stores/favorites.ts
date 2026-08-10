/**
 * Favourites store.
 *
 * Keeps the set of favourited product ids so a heart icon renders correctly
 * anywhere without another request. Toggling is optimistic — the icon responds
 * immediately and rolls back if the server disagrees.
 */
import { defineStore } from 'pinia'
import type { Paginated, Product } from '~/types/api'
import { useApiClient } from '~/utils/api-registry'

interface FavoriteRow {
  id: string
  product: Product
  created_at: string
}

export const useFavoritesStore = defineStore('favorites', {
  state: (): { ids: string[], items: FavoriteRow[], loading: boolean, error: string | null } => ({
    ids: [],
    items: [],
    loading: false,
    error: null,
  }),

  getters: {
    count: state => state.ids.length,
    isFavorite: state => (productId: string): boolean => state.ids.includes(productId),
  },

  actions: {
    async fetch(): Promise<void> {
      this.loading = true
      this.error = null
      try {
        const page = await useApiClient().get<Paginated<FavoriteRow>>('/customers/me/favorites/', {
          query: { page_size: 100 },
        })
        this.items = page.results
        this.ids = page.results.map(row => row.product.id)
      }
      catch {
        this.error = 'FAVORITES_UNAVAILABLE'
      }
      finally {
        this.loading = false
      }
    },

    /**
     * Add or remove a favourite.
     *
     * @returns whether the product is favourited after the call.
     */
    async toggle(productId: string): Promise<boolean> {
      const wasFavorite = this.isFavorite(productId)

      // Optimistic: a heart that waits for a round trip feels broken.
      this.applyLocal(productId, !wasFavorite)

      try {
        await useApiClient().post('/customers/me/favorites/', { product: productId })
        return !wasFavorite
      }
      catch (error) {
        this.applyLocal(productId, wasFavorite)
        throw error
      }
    },

    applyLocal(productId: string, favorite: boolean): void {
      if (favorite) {
        if (!this.ids.includes(productId)) this.ids.push(productId)
      }
      else {
        this.ids = this.ids.filter(id => id !== productId)
        this.items = this.items.filter(row => row.product.id !== productId)
      }
    },

    reset(): void {
      this.ids = []
      this.items = []
    },
  },
})
