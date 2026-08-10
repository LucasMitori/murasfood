/**
 * Cart store.
 *
 * Every mutation round-trips to the API and the response replaces local state.
 * The client never computes a total: prices, discounts and delivery fees are
 * the server's business (invariant #2), and a cart that disagrees with the
 * order it produces is worse than a slightly slower one.
 */
import { defineStore } from 'pinia'
import type { Cart, CartTotals, DeliveryOption } from '~/types/api'
import { ApiRequestError } from '~/utils/api-client'
import { useApiClient } from '~/utils/api-registry'

interface CartState {
  cart: Cart | null
  loading: boolean
  mutating: boolean
  error: string | null
  deliveryMethod: 'PICKUP' | 'DELIVERY' | null
  postalCode: string
  deliveryOptions: DeliveryOption[]
}

const EMPTY_TOTALS: CartTotals = {
  subtotal: '0.00',
  discount: '0.00',
  delivery_fee: '0.00',
  total: '0.00',
  item_count: 0,
  free_delivery: false,
  discounts: [],
  delivery: null,
}

export const useCartStore = defineStore('cart', {
  state: (): CartState => ({
    cart: null,
    loading: false,
    mutating: false,
    error: null,
    deliveryMethod: null,
    postalCode: '',
    deliveryOptions: [],
  }),

  getters: {
    items: state => state.cart?.items ?? [],
    totals: (state): CartTotals => state.cart?.totals ?? EMPTY_TOTALS,
    itemCount: (state): number => state.cart?.totals.item_count ?? 0,
    isEmpty: (state): boolean => (state.cart?.items.length ?? 0) === 0,
    couponCode: state => state.cart?.coupon_code ?? '',

    /** Lines that would block checkout, surfaced on the cart page. */
    issues: state => state.cart?.issues ?? [],
    hasBlockingIssues: (state): boolean => (state.cart?.issues.length ?? 0) > 0,

    /** Quantity of one product currently in the cart. */
    quantityFor: state => (productId: string): number => {
      const item = state.cart?.items.find(row => row.product.id === productId)
      return item ? Number(item.quantity) : 0
    },
  },

  actions: {
    async fetch(): Promise<Cart | null> {
      this.loading = true
      this.error = null
      try {
        this.cart = await useApiClient().get<Cart>('/cart/', { query: this.deliveryQuery() })
        return this.cart
      }
      catch (error) {
        // An anonymous visitor with no cart yet is not an error worth showing.
        if (error instanceof ApiRequestError && error.status === 404) {
          this.cart = null
          return null
        }
        this.error = describe(error)
        return null
      }
      finally {
        this.loading = false
      }
    },

    async addItem(productId: string, quantity: number | string = 1, note = ''): Promise<void> {
      await this.mutate(() =>
        useApiClient().post<Cart>('/cart/items/', {
          product: productId,
          quantity: String(quantity),
          note,
        }),
      )
    },

    async setQuantity(itemId: string, quantity: number | string): Promise<void> {
      await this.mutate(() =>
        useApiClient().patch<Cart>(`/cart/items/${itemId}/`, { quantity: String(quantity) }),
      )
    },

    async removeItem(itemId: string): Promise<void> {
      await this.mutate(() => useApiClient().delete<Cart>(`/cart/items/${itemId}/`))
    },

    async clear(): Promise<void> {
      await this.mutate(() => useApiClient().delete<Cart>('/cart/'))
    },

    async applyCoupon(code: string): Promise<void> {
      await this.mutate(() => useApiClient().post<Cart>('/cart/coupon/', { code }))
    },

    async removeCoupon(): Promise<void> {
      await this.mutate(() => useApiClient().delete<Cart>('/cart/coupon/'))
    },

    /**
     * Fold an anonymous cart into the account cart after signing in.
     *
     * Called once at login; failures are non-fatal because the customer still
     * has their account cart.
     */
    async mergeAfterLogin(cartToken: string): Promise<void> {
      if (!cartToken) {
        await this.fetch()
        return
      }
      try {
        this.cart = await useApiClient().post<Cart>('/cart/merge/', { cart_token: cartToken })
      }
      catch {
        await this.fetch()
      }
    },

    /** Set the delivery method and re-quote the fee server-side. */
    async setDelivery(method: 'PICKUP' | 'DELIVERY' | null, postalCode = ''): Promise<void> {
      this.deliveryMethod = method
      this.postalCode = postalCode
      await this.fetch()
    },

    async loadDeliveryOptions(postalCode = ''): Promise<DeliveryOption[]> {
      try {
        const response = await useApiClient().post<{ options: DeliveryOption[] }>(
          '/delivery/options/',
          { postal_code: postalCode || this.postalCode },
        )
        this.deliveryOptions = response.options
        return response.options
      }
      catch (error) {
        this.error = describe(error)
        return []
      }
    },

    // --- Internals ---------------------------------------------------------
    async mutate(operation: () => Promise<Cart>): Promise<void> {
      this.mutating = true
      this.error = null
      try {
        this.cart = await operation()
      }
      catch (error) {
        this.error = describe(error)
        throw error
      }
      finally {
        this.mutating = false
      }
    },

    deliveryQuery(): Record<string, string> {
      const query: Record<string, string> = {}
      if (this.deliveryMethod) query.delivery_method = this.deliveryMethod
      if (this.postalCode) query.postal_code = this.postalCode
      return query
    },
  },
})

function describe(error: unknown): string {
  return error instanceof ApiRequestError ? error.code : 'ERROR'
}
