<template lang="pug">
.mura-container.mura-section
  mura-page-header(
    :title="order?.number || t('order.title')"
    :subtitle="order ? formatDateTime(order.placed_at, locale) : ''"
    back-to="/account/orders"
  )
    template(#actions)
      mura-status-badge(v-if="order" :status="order.status")

  mura-loading(v-if="pending" skeleton="article")

  mura-error-state(v-else-if="error" :on-retry="() => refresh()")

  template(v-else-if="order")
    v-row
      v-col(cols="12" md="7")
        //- Where the order has got to. The server sends which steps are done,
        //- so a cancelled order shows the steps it actually reached rather
        //- than a hopeful line to "delivered".
        mura-card(:title="t('order.progress')" icon="mdi-progress-check")
          v-timeline(side="end" density="compact" truncate-line="both")
            v-timeline-item(
              v-for="step in order.timeline"
              :key="step.status"
              :dot-color="step.completed ? 'primary' : 'surface-variant'"
              :icon="step.completed ? 'mdi-check' : 'mdi-circle-small'"
              size="small"
            )
              .d-flex.flex-wrap.align-baseline.ga-2
                span.text-body-2(:class="{ 'text-medium-emphasis': !step.completed }") {{ t(step.label_key, step.status) }}
                span.text-caption.text-medium-emphasis(v-if="step.timestamp") {{ formatDateTime(step.timestamp, locale) }}
              p.text-caption.text-medium-emphasis.mb-0(v-if="step.reason") {{ step.reason }}

        mura-card.mt-4(:title="t('order.items', { count: order.items.length })" icon="mdi-basket-outline" :padded="false")
          v-list(lines="two" bg-color="transparent")
            template(v-for="(line, index) in order.items" :key="line.id")
              v-divider(v-if="index > 0")
              v-list-item.py-3
                template(#prepend)
                  v-avatar(rounded="lg" size="56")
                    v-img(
                      :src="line.image?.variants?.thumbnail || line.image?.url"
                      :alt="line.image?.alt_text || line.product_name"
                      cover
                    )

                v-list-item-title
                  nuxt-link.text-decoration-none.text-high-emphasis(:to="`/products/${line.product_slug}`") {{ line.product_name }}
                v-list-item-subtitle {{ money.quantity(line.quantity, line.unit_code) }} × {{ money.format(line.unit_price) }}

                template(#append)
                  span.mura-price {{ money.format(line.line_total) }}

      v-col(cols="12" md="5")
        mura-card(:title="t('cart.summary')" icon="mdi-receipt-text-outline")
          .d-flex.justify-space-between.mb-2
            span.text-body-2 {{ t('common.subtotal') }}
            span.text-body-2 {{ money.format(order.subtotal) }}

          .d-flex.justify-space-between.mb-2(v-if="Number(order.discount_total) > 0")
            span.text-body-2 {{ t('common.discount') }}
            span.text-body-2.text-success -{{ money.format(order.discount_total) }}

          .d-flex.justify-space-between.mb-2(v-if="Number(order.delivery_fee) > 0")
            span.text-body-2 {{ t('common.deliveryFee') }}
            span.text-body-2 {{ money.format(order.delivery_fee) }}

          v-divider.my-3
          .d-flex.justify-space-between
            span.text-subtitle-1.font-weight-bold {{ t('common.total') }}
            span.text-subtitle-1.font-weight-bold.mura-price {{ money.format(order.total) }}

          //- Only shown once money has actually gone back, so a zero does not
          //- suggest a refund is in progress.
          .d-flex.justify-space-between.mt-2(v-if="Number(order.refunded_total) > 0")
            span.text-body-2 {{ t('order.refunded') }}
            span.text-body-2.text-warning {{ money.format(order.refunded_total) }}

        mura-card.mt-4(:title="t('checkout.deliveryMethod')" icon="mdi-truck-outline")
          p.text-body-2.mb-2 {{ t(`checkout.${order.delivery_method.toLowerCase()}`, order.delivery_method) }}

          p.text-body-2.text-medium-emphasis.mb-0(v-if="order.address")
            | {{ [order.address.street, order.address.number, order.address.neighborhood, order.address.city].filter(Boolean).join(', ') }}

          p.text-caption.text-medium-emphasis.mb-0(v-if="order.estimated_ready_at")
            | {{ t('order.estimatedReady', { at: formatDateTime(order.estimated_ready_at, locale) }) }}

        mura-card.mt-4(v-if="order.payment" :title="t('checkout.payment')" icon="mdi-credit-card-outline")
          .d-flex.align-center.justify-space-between.mb-3
            span.text-body-2 {{ order.payment.method }}
            v-chip(:color="order.payment.status === 'PAID' ? 'success' : 'warning'" size="small" variant="tonal") {{ order.payment.status_label }}

          //- The way back to an unfinished payment. Without it an order that
          //- was left mid-checkout has no route to completion from here.
          v-btn(
            v-if="order.payment.status !== 'PAID'"
            :to="`/account/orders/${order.number}/payment`"
            color="primary"
            variant="flat"
            block
            rounded="lg"
            prepend-icon="mdi-cash-fast"
          ) {{ t('order.completePayment') }}

        .d-flex.flex-wrap.ga-2.mt-4
          v-btn(
            variant="tonal"
            rounded="lg"
            prepend-icon="mdi-cart-plus"
            :loading="reordering"
            @click="reorder"
          ) {{ t('order.reorder') }}

          v-btn(
            v-if="order.can_cancel"
            variant="text"
            color="error"
            rounded="lg"
            prepend-icon="mdi-close-circle-outline"
            @click="confirmingCancel = true"
          ) {{ t('order.cancel') }}

    mura-confirm-dialog(
      v-model="confirmingCancel"
      :title="t('order.cancel')"
      :message="t('order.cancelConfirm')"
      :confirm-label="t('order.cancel')"
      :loading="cancelling"
      danger
      @confirm="cancel"
    )
</template>

<script setup lang="ts">
/**
 * One order, in full.
 *
 * The list says an order exists; this says what happened to it. Reached from
 * the list, from the confirmation email, and from the dashboard — which is why
 * it is keyed by the order *number* rather than its id: the number is what the
 * customer has in front of them.
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMoney } from '~/composables/useMoney'
import { useApiError } from '~/composables/useApiError'
import { useCartStore } from '~/stores/cart'
import { useUiStore } from '~/stores/ui'
import { formatDateTime } from '~/utils/format'

definePageMeta({ middleware: 'auth', permission: 'perm.account.orders' })

interface OrderLine {
  id: string
  product: string
  product_slug: string
  product_name: string
  unit_code: string
  quantity: string
  unit_price: string
  line_total: string
  image?: { url?: string, alt_text?: string, variants?: Record<string, string> }
}

interface TimelineStep {
  status: string
  label_key: string
  completed: boolean
  timestamp: string | null
  reason: string
}

interface OrderDetail {
  id: string
  number: string
  status: string
  status_label: string
  delivery_method: string
  subtotal: string
  discount_total: string
  delivery_fee: string
  total: string
  refunded_total: string
  items: OrderLine[]
  address: Record<string, string> | null
  timeline: TimelineStep[]
  payment: { method: string, status: string, status_label: string } | null
  can_cancel: boolean
  estimated_ready_at: string | null
  placed_at: string
}

const { t, locale } = useI18n()
const route = useRoute()
const money = useMoney()
const cart = useCartStore()
const ui = useUiStore()
const { messageFor } = useApiError()

const number = computed(() => String(route.params.number ?? ''))

const { data: order, pending, error, refresh } = await useAsyncData<OrderDetail>(
  () => `order-${number.value}`,
  () => useNuxtApp().$api.get(`/orders/${number.value}/`),
  { watch: [number] },
)

useSeoMeta({
  title: () => order.value?.number ?? t('order.title'),
  robots: 'noindex',
})

const reordering = ref(false)
const cancelling = ref(false)
const confirmingCancel = ref(false)

/**
 * Put the same products back in the cart.
 *
 * Added one by one through the cart store rather than restored wholesale: a
 * product may have gone out of stock or changed price since, and the cart is
 * what knows how to refuse it.
 */
async function reorder(): Promise<void> {
  if (!order.value) return

  reordering.value = true
  let added = 0
  let skipped = 0

  try {
    for (const line of order.value.items) {
      try {
        await cart.addItem(line.product, Number(line.quantity))
        added += 1
      }
      catch {
        skipped += 1
      }
    }

    if (added) ui.success(t('order.reordered', { count: added }))
    if (skipped) ui.notify(t('order.reorderSkipped', { count: skipped }))
    if (added) await navigateTo('/cart')
  }
  finally {
    reordering.value = false
  }
}

async function cancel(): Promise<void> {
  cancelling.value = true
  try {
    await useNuxtApp().$api.post(`/orders/${number.value}/cancel/`, {})
    await refresh()
    ui.success(t('order.cancelled'))
  }
  catch (error_) {
    ui.error(messageFor(error_))
  }
  finally {
    cancelling.value = false
    confirmingCancel.value = false
  }
}
</script>
