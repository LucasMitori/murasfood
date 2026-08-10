/**
 * Cart interactions with their user feedback attached.
 *
 * Pages call these instead of the store directly, so "added to cart" is
 * confirmed the same way everywhere and every failure is reported rather than
 * silently swallowed.
 */
import { useI18n } from 'vue-i18n'
import type { Product } from '~/types/api'
import { useCartStore } from '~/stores/cart'
import { useFavoritesStore } from '~/stores/favorites'
import { useAuthStore } from '~/stores/auth'
import { useUiStore } from '~/stores/ui'
import { useApiError } from '~/composables/useApiError'

export function useCartActions() {
  const cart = useCartStore()
  const favorites = useFavoritesStore()
  const auth = useAuthStore()
  const ui = useUiStore()
  const { t } = useI18n()
  const { notify } = useApiError()

  const busyProductId = ref<string | null>(null)

  async function addToCart(product: Product, quantity: number | string = 1): Promise<boolean> {
    busyProductId.value = product.id
    try {
      await cart.addItem(product.id, quantity)
      ui.success(t('product.addedToCart', { name: product.name }))
      return true
    }
    catch (error) {
      notify(error)
      return false
    }
    finally {
      busyProductId.value = null
    }
  }

  async function updateQuantity(itemId: string, quantity: number): Promise<boolean> {
    try {
      await cart.setQuantity(itemId, quantity)
      return true
    }
    catch (error) {
      notify(error)
      return false
    }
  }

  async function removeFromCart(itemId: string, productName?: string): Promise<boolean> {
    try {
      await cart.removeItem(itemId)
      if (productName) ui.notify(t('product.removedFromCart', { name: productName }))
      return true
    }
    catch (error) {
      notify(error)
      return false
    }
  }

  /**
   * Toggle a favourite, sending anonymous visitors to sign in first.
   *
   * Favourites are stored server-side per customer, so there is nowhere to keep
   * them before an account exists.
   */
  async function toggleFavorite(product: Product): Promise<void> {
    if (!auth.isAuthenticated) {
      await navigateTo({ path: '/auth/login', query: { redirect: useRoute().fullPath } })
      return
    }

    try {
      const isFavorite = await favorites.toggle(product.id)
      ui.success(t(isFavorite ? 'product.favoriteAdded' : 'product.favoriteRemoved'))
    }
    catch (error) {
      notify(error)
    }
  }

  return {
    busyProductId,
    addToCart,
    updateQuantity,
    removeFromCart,
    toggleFavorite,
  }
}
