<template lang="pug">
.mura-container.mura-section
  h1.text-h5.mb-4 {{ t('cart.title') }}

  v-progress-linear(v-if="cart.loading" indeterminate color="primary")

  mura-empty-state(
    v-else-if="cart.isEmpty"
    :title="t('states.cartEmpty')"
    :description="t('states.cartEmptyHint')"
    icon="mdi-cart-outline"
  )
    template(#action)
      v-btn(to="/produtos" color="primary" variant="flat") {{ t('cart.continueShopping') }}

  v-row(v-else)
    v-col(cols="12" md="8")
      v-alert.mb-4(
        v-if="cart.hasBlockingIssues"
        type="warning"
        variant="tonal"
        :title="t('cart.issuesTitle')"
      )
        ul.mt-2
          li(v-for="issue in cart.issues" :key="issue.item_id") {{ issue.product }} — {{ issueLabel(issue.reason) }}

      v-card.mura-card(flat)
        v-list(lines="two")
          template(v-for="(item, index) in cart.items" :key="item.id")
            v-divider(v-if="index > 0")
            v-list-item.py-3
              template(#prepend)
                v-avatar(rounded="lg" size="64")
                  v-img(
                    :src="item.product.image?.variants?.thumbnail || item.product.image?.url"
                    :alt="item.product.image?.alt_text || item.product.name"
                    cover
                  )

              v-list-item-title
                nuxt-link.text-decoration-none.text-high-emphasis(:to="`/produtos/${item.product.slug}`") {{ item.product.name }}
              v-list-item-subtitle
                span {{ money.format(item.unit_price) }} · {{ money.quantity(item.quantity, item.product.unit.code) }}
                v-chip.ml-2(v-if="!item.is_available" size="x-small" color="warning" variant="tonal") {{ t('cart.itemUnavailable') }}

              template(#append)
                .d-flex.align-center.ga-3
                  mura-quantity-input(
                    :model-value="Number(item.quantity)"
                    :step-size="Number(item.product.unit.step)"
                    :precision="item.product.unit.precision"
                    :min="0"
                    :unit="item.product.unit.code"
                    @update:model-value="value => onQuantityChange(item.id, value)"
                  )
                  span.mura-price.text-body-1.d-none.d-sm-inline {{ money.format(item.line_total) }}
                  v-btn(
                    icon="mdi-delete-outline"
                    variant="text"
                    size="small"
                    :aria-label="t('common.remove')"
                    @click="removeFromCart(item.id, item.product.name)"
                  )

      .d-flex.justify-space-between.mt-4
        v-btn(to="/produtos" variant="text" prepend-icon="mdi-arrow-left") {{ t('cart.continueShopping') }}
        v-btn(variant="text" color="error" @click="confirmClear = true") {{ t('cart.clearCart') }}

    v-col(cols="12" md="4")
      v-card.mura-card.pa-4(flat)
        h2.text-subtitle-1.mb-3 {{ t('cart.summary') }}

        v-alert.mb-3(
          v-if="freeDeliveryMessage"
          type="info"
          variant="tonal"
          density="compact"
          icon="mdi-truck-outline"
        ) {{ freeDeliveryMessage }}

        .d-flex.justify-space-between.mb-2
          span.text-body-2 {{ t('common.subtotal') }}
          span.text-body-2 {{ money.format(cart.totals.subtotal) }}

        .d-flex.justify-space-between.mb-2(v-if="hasDiscount")
          span.text-body-2 {{ t('common.discount') }}
          span.text-body-2.text-success -{{ money.format(cart.totals.discount) }}

        v-divider.my-3
        .d-flex.justify-space-between.mb-4
          span.text-subtitle-1.font-weight-bold {{ t('common.total') }}
          span.text-subtitle-1.font-weight-bold.mura-price {{ money.format(cart.totals.total) }}

        v-form.mb-4(v-if="auth.isAuthenticated" @submit.prevent="applyCoupon")
          .d-flex.ga-2
            v-text-field(
              v-model="couponInput"
              :label="t('cart.coupon')"
              :placeholder="t('cart.couponPlaceholder')"
              density="compact"
            )
            v-btn(type="submit" variant="tonal" :loading="couponLoading") {{ t('cart.couponApply') }}
          v-chip.mt-2(
            v-if="cart.couponCode"
            closable
            color="success"
            variant="tonal"
            size="small"
            @click:close="removeCoupon"
          ) {{ cart.couponCode }}

        v-btn(
          block
          color="primary"
          variant="flat"
          size="large"
          :disabled="cart.hasBlockingIssues"
          @click="goToCheckout"
        ) {{ t('cart.checkout') }}

  v-dialog(v-model="confirmClear" max-width="420")
    v-card
      v-card-title {{ t('cart.clearCart') }}
      v-card-text {{ t('cart.clearConfirm') }}
      v-card-actions
        v-spacer
        v-btn(variant="text" @click="confirmClear = false") {{ t('common.cancel') }}
        v-btn(color="error" variant="flat" @click="clearCart") {{ t('common.confirm') }}
</template>

<script setup lang="ts">
/**
 * Cart page.
 *
 * Totals are read from the server response on every change — the page shows
 * what checkout will charge, not a locally computed guess.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '~/stores/auth'
import { useCartStore } from '~/stores/cart'
import { useMoney } from '~/composables/useMoney'
import { useApiError } from '~/composables/useApiError'
import { useCartActions } from '~/composables/useCartActions'
import { useUiStore } from '~/stores/ui'

const { t } = useI18n()
const router = useRouter()

const cart = useCartStore()
const auth = useAuthStore()
const ui = useUiStore()
const money = useMoney()
const { notify } = useApiError()
const { updateQuantity, removeFromCart } = useCartActions()

const couponInput = ref('')
const couponLoading = ref(false)
const confirmClear = ref(false)

useSeoMeta({ title: () => t('cart.title'), robots: 'noindex' })

await cart.fetch()

const hasDiscount = computed(() => Number(cart.totals.discount) > 0)

const freeDeliveryMessage = computed(() => {
  if (cart.totals.free_delivery) return t('cart.freeDeliveryReached')
  const remaining = money.remainingForFreeDelivery(cart.totals.subtotal)
  return remaining ? t('cart.freeDeliveryProgress', { amount: remaining }) : ''
})

function issueLabel(reason: string): string {
  const map: Record<string, string> = {
    UNAVAILABLE: t('cart.itemUnavailable'),
    OUT_OF_STOCK: t('cart.itemOutOfStock'),
    NO_PRICE: t('cart.itemNoPrice'),
  }
  return map[reason] ?? reason
}

async function onQuantityChange(itemId: string, quantity: number): Promise<void> {
  await updateQuantity(itemId, quantity)
}

async function applyCoupon(): Promise<void> {
  const code = couponInput.value.trim()
  if (!code) return

  couponLoading.value = true
  try {
    await cart.applyCoupon(code)
    ui.success(t('cart.couponApplied', { code: code.toUpperCase() }))
    couponInput.value = ''
  }
  catch (error) {
    notify(error)
  }
  finally {
    couponLoading.value = false
  }
}

async function removeCoupon(): Promise<void> {
  await cart.removeCoupon()
  ui.notify(t('cart.couponRemoved'))
}

async function clearCart(): Promise<void> {
  confirmClear.value = false
  await cart.clear()
}

function goToCheckout(): void {
  router.push(auth.isAuthenticated ? '/checkout' : { path: '/auth/login', query: { redirect: '/checkout' } })
}
</script>
