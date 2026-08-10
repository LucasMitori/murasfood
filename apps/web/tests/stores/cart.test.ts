/**
 * Cart store.
 *
 * The property under test throughout: the store mirrors the server's numbers
 * and never invents its own.
 */
import { describe, expect, it, vi } from 'vitest'
import type { Cart } from '../../app/types/api'
import { ApiRequestError } from '../../app/utils/api-client'
import { setApiClient } from '../../app/utils/api-registry'
import { useCartStore } from '../../app/stores/cart'

function makeCart(overrides: Partial<Cart> = {}): Cart {
  return {
    id: 'cart-1',
    token: 'token-1',
    status: 'ACTIVE',
    coupon_code: '',
    items: [],
    totals: {
      subtotal: '25.00',
      discount: '0.00',
      delivery_fee: '0.00',
      total: '25.00',
      item_count: 1,
      free_delivery: false,
      discounts: [],
      delivery: null,
    },
    issues: [],
    updated_at: new Date().toISOString(),
    ...overrides,
  }
}

function stubClient(overrides: Record<string, unknown> = {}) {
  const client = {
    get: vi.fn().mockResolvedValue(makeCart()),
    post: vi.fn().mockResolvedValue(makeCart()),
    patch: vi.fn().mockResolvedValue(makeCart()),
    delete: vi.fn().mockResolvedValue(makeCart()),
    put: vi.fn(),
    request: vi.fn(),
    ...overrides,
  }
  setApiClient(client as never)
  return client
}

describe('fetching', () => {
  it('stores the cart returned by the API', async () => {
    stubClient()
    const cart = useCartStore()

    await cart.fetch()
    expect(cart.cart?.id).toBe('cart-1')
    expect(cart.itemCount).toBe(1)
  })

  it('treats a missing cart as empty rather than an error', async () => {
    stubClient({
      get: vi.fn().mockRejectedValue(new ApiRequestError(404, { code: 'NOT_FOUND', message: '' })),
    })
    const cart = useCartStore()

    await cart.fetch()
    expect(cart.cart).toBeNull()
    expect(cart.error).toBeNull()
    expect(cart.isEmpty).toBe(true)
  })

  it('records other failures', async () => {
    stubClient({
      get: vi.fn().mockRejectedValue(new ApiRequestError(500, { code: 'SERVER_ERROR', message: '' })),
    })
    const cart = useCartStore()

    await cart.fetch()
    expect(cart.error).toBe('SERVER_ERROR')
  })

  it('passes the delivery method to the API so the fee is quoted server-side', async () => {
    const client = stubClient()
    const cart = useCartStore()

    await cart.setDelivery('DELIVERY', '01001000')

    expect(client.get).toHaveBeenCalledWith('/cart/', {
      query: { delivery_method: 'DELIVERY', postal_code: '01001000' },
    })
  })
})

describe('mutations', () => {
  it('adds an item and replaces state with the response', async () => {
    const updated = makeCart({ totals: { ...makeCart().totals, item_count: 3, total: '75.00' } })
    const client = stubClient({ post: vi.fn().mockResolvedValue(updated) })
    const cart = useCartStore()

    await cart.addItem('product-1', 3)

    expect(client.post).toHaveBeenCalledWith('/cart/items/', {
      product: 'product-1',
      quantity: '3',
      note: '',
    })
    expect(cart.itemCount).toBe(3)
    expect(cart.totals.total).toBe('75.00')
  })

  it('surfaces an insufficient-stock failure to the caller', async () => {
    stubClient({
      post: vi.fn().mockRejectedValue(
        new ApiRequestError(409, { code: 'INSUFFICIENT_STOCK', message: 'Sem estoque' }),
      ),
    })
    const cart = useCartStore()

    await expect(cart.addItem('product-1', 999)).rejects.toBeInstanceOf(ApiRequestError)
    expect(cart.error).toBe('INSUFFICIENT_STOCK')
    expect(cart.mutating).toBe(false)
  })

  it('sends a quantity change as a string to preserve decimals', async () => {
    const client = stubClient()
    const cart = useCartStore()

    await cart.setQuantity('item-1', 1.35)
    expect(client.patch).toHaveBeenCalledWith('/cart/items/item-1/', { quantity: '1.35' })
  })

  it('removes an item', async () => {
    const client = stubClient()
    const cart = useCartStore()

    await cart.removeItem('item-1')
    expect(client.delete).toHaveBeenCalledWith('/cart/items/item-1/')
  })

  it('applies a coupon', async () => {
    const client = stubClient({ post: vi.fn().mockResolvedValue(makeCart({ coupon_code: 'PROMO10' })) })
    const cart = useCartStore()

    await cart.applyCoupon('promo10')
    expect(client.post).toHaveBeenCalledWith('/cart/coupon/', { code: 'promo10' })
    expect(cart.couponCode).toBe('PROMO10')
  })
})

describe('getters', () => {
  it('reports zeroed totals before the cart loads', () => {
    stubClient()
    const cart = useCartStore()

    expect(cart.totals.total).toBe('0.00')
    expect(cart.itemCount).toBe(0)
    expect(cart.isEmpty).toBe(true)
  })

  it('flags blocking issues', async () => {
    stubClient({
      get: vi.fn().mockResolvedValue(makeCart({
        issues: [{ item_id: 'item-1', product: 'Arroz', reason: 'OUT_OF_STOCK' }],
      })),
    })
    const cart = useCartStore()

    await cart.fetch()
    expect(cart.hasBlockingIssues).toBe(true)
  })

  it('reports the quantity of a product already in the cart', async () => {
    stubClient({
      get: vi.fn().mockResolvedValue(makeCart({
        items: [{
          id: 'item-1',
          product: { id: 'product-1' } as never,
          quantity: '2.000',
          unit_price: '12.50',
          base_unit_price: '12.50',
          line_total: '25.00',
          is_available: true,
          note: '',
        }],
      })),
    })
    const cart = useCartStore()

    await cart.fetch()
    expect(cart.quantityFor('product-1')).toBe(2)
    expect(cart.quantityFor('product-2')).toBe(0)
  })
})

describe('merging after sign-in', () => {
  it('posts the anonymous token', async () => {
    const client = stubClient()
    const cart = useCartStore()

    await cart.mergeAfterLogin('anon-token')
    expect(client.post).toHaveBeenCalledWith('/cart/merge/', { cart_token: 'anon-token' })
  })

  it('falls back to a plain fetch when merging fails', async () => {
    const client = stubClient({ post: vi.fn().mockRejectedValue(new Error('boom')) })
    const cart = useCartStore()

    await cart.mergeAfterLogin('anon-token')
    expect(client.get).toHaveBeenCalled()
  })

  it('just fetches when there is no anonymous cart', async () => {
    const client = stubClient()
    const cart = useCartStore()

    await cart.mergeAfterLogin('')
    expect(client.post).not.toHaveBeenCalled()
    expect(client.get).toHaveBeenCalled()
  })
})
