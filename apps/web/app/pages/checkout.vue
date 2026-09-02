<template lang="pug">
.mura-container.mura-section
  h1.text-h5.mb-4 {{ t('checkout.title') }}

  v-row
    v-col(cols="12" md="7")
      v-card.mura-card.pa-4.mb-4(flat)
        h2.text-subtitle-1.mb-3 {{ t('checkout.deliveryMethod') }}
        v-radio-group(v-model="deliveryMethod" hide-details @update:model-value="onDeliveryChange")
          v-radio(
            v-for="option in deliveryOptions"
            :key="option.method"
            :value="option.method"
            :disabled="!option.available"
          )
            template(#label)
              div
                .d-flex.align-center.ga-2
                  span.font-weight-medium {{ option.method === 'PICKUP' ? t('checkout.pickup') : t('checkout.delivery') }}
                  v-chip(v-if="option.available && option.is_free" size="x-small" color="success" variant="tonal") {{ t('common.free') }}
                  v-chip(v-else-if="option.available" size="x-small" variant="tonal") {{ money.format(option.fee) }}
                p.text-caption.text-medium-emphasis.mb-0(v-if="option.available") {{ t('checkout.estimatedTime', { time: formatMinutes(option.estimated_minutes) }) }}
                p.text-caption.text-error.mb-0(v-else) {{ option.message }}

      v-card.mura-card.pa-4.mb-4(v-if="deliveryMethod === 'DELIVERY'" flat)
        .d-flex.align-center.justify-space-between.mb-3
          h2.text-subtitle-1 {{ t('checkout.address') }}
          v-btn(to="/account/addresses" variant="text" size="small") {{ t('checkout.newAddress') }}

        mura-empty-state(
          v-if="!addresses?.length"
          :title="t('checkout.selectAddress')"
          :description="t('account.addAddress')"
          icon="mdi-map-marker-outline"
        )
          template(#action)
            v-btn(to="/account/addresses" color="primary" variant="tonal") {{ t('account.addAddress') }}

        v-radio-group(v-else v-model="addressId" hide-details @update:model-value="refreshDelivery")
          v-radio(v-for="address in addresses" :key="address.id" :value="address.id")
            template(#label)
              div
                span.font-weight-medium {{ address.label || address.recipient_name }}
                p.text-caption.text-medium-emphasis.mb-0 {{ formatAddress(address) }}

      v-card.mura-card.pa-4.mb-4(flat)
        h2.text-subtitle-1.mb-3 {{ t('checkout.payment') }}
        v-list(density="compact" bg-color="transparent")
          v-list-item.px-0(prepend-icon="mdi-qrcode")
            v-list-item-title {{ t('checkout.paymentPix') }}
            v-list-item-subtitle {{ t('checkout.paymentPixDescription') }}

      v-card.mura-card.pa-4(flat)
        h2.text-subtitle-1.mb-3 {{ t('checkout.notes') }}
        v-textarea(
          v-model="customerNote"
          :placeholder="t('checkout.notesPlaceholder')"
          rows="2"
          counter="500"
          maxlength="500"
        )

    v-col(cols="12" md="5")
      v-card.mura-card.pa-4(flat)
        h2.text-subtitle-1.mb-3 {{ t('checkout.reviewOrder') }}

        v-list(density="compact" bg-color="transparent")
          v-list-item.px-0(v-for="item in cart.items" :key="item.id")
            v-list-item-title.text-body-2 {{ money.quantity(item.quantity, item.product.unit.code) }} × {{ item.product.name }}
            template(#append)
              span.text-body-2 {{ money.format(item.line_total) }}

        v-divider.my-3

        .d-flex.justify-space-between.mb-2
          span.text-body-2 {{ t('common.subtotal') }}
          span.text-body-2 {{ money.format(cart.totals.subtotal) }}
        .d-flex.justify-space-between.mb-2(v-if="Number(cart.totals.discount) > 0")
          span.text-body-2 {{ t('common.discount') }}
          span.text-body-2.text-success -{{ money.format(cart.totals.discount) }}
        .d-flex.justify-space-between.mb-2(v-if="deliveryMethod === 'DELIVERY'")
          span.text-body-2 {{ t('common.deliveryFee') }}
          span.text-body-2 {{ Number(cart.totals.delivery_fee) > 0 ? money.format(cart.totals.delivery_fee) : t('common.free') }}

        v-divider.my-3
        .d-flex.justify-space-between.mb-4
          span.text-subtitle-1.font-weight-bold {{ t('common.total') }}
          span.text-subtitle-1.font-weight-bold.mura-price {{ money.format(cart.totals.total) }}

        v-alert.mb-3(v-if="submitError" type="error" variant="tonal" density="compact") {{ submitError }}

        v-btn(
          block
          color="primary"
          variant="flat"
          size="large"
          :loading="submitting"
          :disabled="!canSubmit"
          @click="placeOrder"
        ) {{ t('checkout.placeOrder') }}
</template>

<script setup lang="ts">
/**
 * Checkout.
 *
 * The client sends *intent* only — delivery method, address, note. Prices,
 * discounts and fees are recomputed server-side (invariant #2), and the request
 * carries an idempotency key so a double-tap cannot create two orders.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Address, DeliveryOption, Order } from '~/types/api'
import { useCartStore } from '~/stores/cart'
import { useMoney } from '~/composables/useMoney'
import { useApiError } from '~/composables/useApiError'
import { newIdempotencyKey } from '~/utils/api-client'
import { formatMinutes } from '~/utils/format'

definePageMeta({ middleware: 'auth' })

const { t } = useI18n()
const router = useRouter()
const cart = useCartStore()
const money = useMoney()
const { messageFor } = useApiError()

useSeoMeta({ title: () => t('checkout.title'), robots: 'noindex' })

const deliveryMethod = ref<'PICKUP' | 'DELIVERY'>('PICKUP')
const addressId = ref<string | null>(null)
const customerNote = ref('')
const submitting = ref(false)
const submitError = ref('')

// Generated once per visit to the page: retrying the same order must reuse it,
// while a genuinely new order gets a fresh key.
const idempotencyKey = ref(newIdempotencyKey())

const { data: addresses } = await useAsyncData<Address[]>(
  'checkout-addresses',
  async () => {
    const page = await useNuxtApp().$api.get<{ results: Address[] }>('/customers/me/addresses/')
    return page.results
  },
  { default: () => [] },
)

addressId.value = addresses.value?.find(address => address.is_default)?.id ?? addresses.value?.[0]?.id ?? null

// Declared before the fetch below, which reads it. A `const` is in its
// temporal dead zone until this line runs, and the `useAsyncData` handler runs
// immediately — so declaring it afterwards threw `ReferenceError` inside the
// handler, leaving the delivery options permanently empty and the Confirm
// button permanently disabled.
const selectedAddress = computed(() =>
  addresses.value?.find(address => address.id === addressId.value) ?? null,
)

const { data: deliveryOptions } = await useAsyncData<DeliveryOption[]>(
  'checkout-delivery-options',
  () => cart.loadDeliveryOptions(selectedAddress.value?.postal_code ?? ''),
  { default: () => [] },
)

const canSubmit = computed(() => {
  if (cart.isEmpty || cart.hasBlockingIssues || submitting.value) return false
  if (deliveryMethod.value === 'DELIVERY' && !addressId.value) return false
  return deliveryOptions.value?.find(option => option.method === deliveryMethod.value)?.available ?? false
})

await cart.setDelivery(deliveryMethod.value)

function formatAddress(address: Address): string {
  return [address.street, address.number, address.neighborhood, address.city].filter(Boolean).join(', ')
}

async function onDeliveryChange(): Promise<void> {
  await refreshDelivery()
}

async function refreshDelivery(): Promise<void> {
  await cart.setDelivery(deliveryMethod.value, selectedAddress.value?.postal_code ?? '')
  deliveryOptions.value = await cart.loadDeliveryOptions(selectedAddress.value?.postal_code ?? '')
}

async function placeOrder(): Promise<void> {
  submitting.value = true
  submitError.value = ''

  try {
    const order = await useNuxtApp().$api.post<Order>(
      '/orders/checkout/',
      {
        delivery_method: deliveryMethod.value,
        address: deliveryMethod.value === 'DELIVERY' ? addressId.value : null,
        customer_note: customerNote.value,
        payment_method: 'PIX',
      },
      { idempotencyKey: idempotencyKey.value },
    )

    await cart.fetch()
    await router.push(`/account/orders/${order.number}/pagamento`)
  }
  catch (error) {
    submitError.value = messageFor(error)
    // A failed attempt must not reuse the key: the payload may change before
    // the customer retries.
    idempotencyKey.value = newIdempotencyKey()
  }
  finally {
    submitting.value = false
  }
}
</script>
