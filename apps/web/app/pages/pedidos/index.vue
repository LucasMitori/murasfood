<template lang="pug">
.mura-container.mura-section
  h1.text-h5.mb-4 {{ t('order.myOrders') }}

  v-progress-linear(v-if="pending" indeterminate color="primary")

  mura-error-state(v-else-if="error" :on-retry="() => refresh()")

  mura-empty-state(
    v-else-if="!data?.results.length"
    :title="t('states.noOrders')"
    :description="t('states.noOrdersHint')"
    icon="mdi-receipt-text-outline"
  )
    template(#action)
      v-btn(to="/produtos" color="primary" variant="flat") {{ t('cart.continueShopping') }}

  v-card.mura-card(v-else flat)
    v-list(lines="two")
      template(v-for="(order, index) in data.results" :key="order.id")
        v-divider(v-if="index > 0")
        v-list-item(:to="`/pedidos/${order.number}`")
          v-list-item-title.font-weight-medium {{ order.number }}
          v-list-item-subtitle
            span {{ formatDateTime(order.placed_at || order.created_at, locale) }}
            span.mx-1 ·
            span {{ t('common.results', order.item_count, { count: order.item_count }) }}
          template(#append)
            .d-flex.align-center.ga-3
              mura-status-badge(:status="order.status")
              span.mura-price.text-body-1 {{ money.format(order.total) }}
</template>

<script setup lang="ts">
/**
 * The customer's order history.
 */
import { useI18n } from 'vue-i18n'
import type { OrderSummary, Paginated } from '~/types/api'
import { useMoney } from '~/composables/useMoney'
import { formatDateTime } from '~/utils/format'

definePageMeta({ middleware: 'auth', permission: 'perm.account.orders' })

const { t, locale } = useI18n()
const money = useMoney()

const { data, pending, error, refresh } = await useAsyncData<Paginated<OrderSummary>>(
  'my-orders',
  () => useNuxtApp().$api.get<Paginated<OrderSummary>>('/orders/'),
)

useSeoMeta({ title: () => t('order.myOrders'), robots: 'noindex' })
</script>
