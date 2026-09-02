<template lang="pug">
div
  mura-page-header(
    :title="t('admin.orders')"
    :subtitle="t('admin.ordersSubtitle')"
    :breadcrumbs="[{ title: 'admin.dashboard', to: '/admin' }, { title: 'admin.orders' }]"
  )

  mura-data-table(
    :table="table"
    :columns="columns"
    :actions="rowActions"
    :title="t('admin.orders')"
    searchable
    clickable
    @action="onAction"
    @row-click="openOrder"
  )
    template(#filters)
      v-select.mura-admin-filter(
        v-model="statusFilter"
        :items="statusOptions"
        :label="t('order.status')"
        item-title="label"
        item-value="value"
        density="compact"
        hide-details
        clearable
        @update:model-value="table.applyFilters()"
      )

    template(#item.number="{ item }")
      div
        p.text-body-2.font-weight-medium.mb-0 {{ item.number }}
        p.text-caption.text-medium-emphasis.mb-0 {{ t('admin.items', { count: item.items?.length ?? 0 }) }}

    template(#item.status="{ item }")
      v-chip(:color="statusColor(String(item.status))" size="x-small" variant="tonal") {{ item.status_label || item.status }}

  //- Detail as a side sheet rather than a page: an operator working a queue
  //- checks one order and moves to the next, and a full navigation would lose
  //- their filters and scroll position each time.
  v-navigation-drawer(
    v-model="detailOpen"
    location="right"
    temporary
    :width="440"
  )
    template(v-if="selected")
      .pa-4
        .d-flex.align-center.justify-space-between.mb-1
          h2.text-h6.mb-0 {{ selected.number }}
          v-btn(icon="mdi-close" variant="text" size="small" :aria-label="t('common.close')" @click="detailOpen = false")
        v-chip(:color="statusColor(selected.status)" size="small" variant="tonal") {{ selected.status_label || selected.status }}

      v-divider

      v-list(density="compact" bg-color="transparent")
        v-list-item.px-4
          v-list-item-title.text-body-2 {{ t('admin.placedAt') }}
          template(#append)
            span.text-body-2.text-medium-emphasis {{ formatDateTime(selected.created_at, locale) }}
        v-list-item.px-4
          v-list-item-title.text-body-2 {{ t('checkout.deliveryMethod') }}
          template(#append)
            span.text-body-2.text-medium-emphasis {{ selected.delivery_method }}
        v-list-item.px-4
          v-list-item-title.text-body-2 {{ t('common.total') }}
          template(#append)
            span.text-body-2.font-weight-bold {{ money.format(selected.total) }}

      v-divider

      .pa-4
        p.text-subtitle-2.font-weight-bold.mb-2 {{ t('admin.items', { count: selected.items?.length ?? 0 }) }}
        v-list(density="compact" bg-color="transparent")
          v-list-item.px-0(v-for="line in selected.items" :key="line.id")
            v-list-item-title.text-body-2 {{ line.product_name }}
            v-list-item-subtitle.text-caption {{ money.quantity(line.quantity) }} × {{ money.format(line.unit_price) }}
            template(#append)
              span.text-body-2 {{ money.format(line.line_total) }}

      v-divider

      .pa-4
        p.text-subtitle-2.font-weight-bold.mb-2 {{ t('order.status') }}
        v-btn.mb-2(
          v-for="next in selected.allowed_transitions || []"
          :key="next"
          :prepend-icon="statusIcon(next)"
          :color="next === 'CANCELLED' ? 'error' : undefined"
          :loading="updating === next"
          block
          variant="tonal"
          @click="advance(next)"
        ) {{ t(`order.statuses.${next}`, next) }}

        p.text-caption.text-medium-emphasis.mb-0(v-if="!selected.allowed_transitions?.length") {{ t('admin.noTransitions') }}
</template>

<script setup lang="ts">
/**
 * Order queue.
 *
 * Status changes go through the API's own transition endpoints rather than a
 * generic patch, so the server's state machine stays the only thing that
 * decides which move is legal. This screen only offers the moves it believes
 * are available; the API is what enforces them.
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { TableAction, TableColumn } from '~/types/ui'
import { useServerTable } from '~/composables/useServerTable'
import { useMoney } from '~/composables/useMoney'
import { useUiStore } from '~/stores/ui'
import { useApiError } from '~/composables/useApiError'
import { formatDateTime } from '~/utils/format'

definePageMeta({ layout: 'admin', middleware: 'merchant', permission: 'perm.admin.orders' })

interface OrderLine {
  id: string
  product_name: string
  quantity: string
  unit_price: string
  line_total: string
}

interface OrderRow {
  id: string
  number: string
  status: string
  status_label: string
  delivery_method: string
  total: string
  created_at: string
  customer_name?: string
  allowed_transitions?: string[]
  items: OrderLine[]
  [key: string]: unknown
}

const { t, locale } = useI18n()
const money = useMoney()
const ui = useUiStore()
const { messageFor } = useApiError()

useSeoMeta({ title: () => t('admin.orders') })

const route = useRoute()

const statusFilter = ref<string | null>(null)
const detailOpen = ref(false)
const selected = ref<OrderRow | null>(null)
const updating = ref('')

const table = useServerTable<OrderRow>({
  endpoint: '/admin/orders/',
  defaultSort: [{ key: 'created_at', order: 'desc' }],
  filters: () => ({ status: statusFilter.value ?? undefined }),
  searchParam: 'q',
})

const statusOptions = computed(() =>
  ['PENDING_PAYMENT', 'PAID', 'CONFIRMED', 'PREPARING', 'READY_FOR_PICKUP',
    'OUT_FOR_DELIVERY', 'DELIVERED', 'COMPLETED', 'CANCELLED']
    .map(value => ({ value, label: t(`order.statuses.${value}`, value) })),
)

const columns: TableColumn<OrderRow>[] = [
  { key: 'number', title: 'admin.orderNumber', sortable: true },
  { key: 'created_at', title: 'admin.placedAt', sortable: true, format: 'datetime', hideBelow: 'md' },
  { key: 'delivery_method', title: 'checkout.deliveryMethod', sortable: false, hideBelow: 'lg' },
  { key: 'total', title: 'common.total', sortable: true, format: 'money', align: 'end' },
  { key: 'status', title: 'order.status', sortable: true, align: 'center' },
]

const rowActions: TableAction<OrderRow>[] = [
  { key: 'view', label: 'admin.view', icon: 'mdi-eye-outline' },
]

function statusColor(status: string): string {
  switch (status) {
    case 'DELIVERED': return 'success'
    case 'CANCELLED': return 'error'
    case 'PENDING_PAYMENT': return 'warning'
    default: return 'primary'
  }
}

/**
 * Icon per destination status. The *set* of destinations is not decided here:
 * the serializer sends `allowed_transitions` straight from the state machine,
 * so this screen cannot drift out of step with what the API will accept.
 */
function statusIcon(status: string): string {
  const icons: Record<string, string> = {
    PREPARING: 'mdi-chef-hat',
    READY_FOR_PICKUP: 'mdi-check-circle-outline',
    OUT_FOR_DELIVERY: 'mdi-truck-outline',
    DELIVERED: 'mdi-package-variant-closed-check',
    COMPLETED: 'mdi-flag-checkered',
    CANCELLED: 'mdi-close-circle-outline',
    REFUNDED: 'mdi-cash-refund',
    CONFIRMED: 'mdi-check',
  }
  return icons[status] ?? 'mdi-arrow-right'
}

/**
 * Open the order named in `?order=`, once the table has it.
 *
 * The dashboard links here rather than to a detail page, so arriving with that
 * query has to land on the same side sheet a click would open. It runs when the
 * rows arrive because the id alone is not enough to render the sheet — the row
 * carries the items and the transitions the server allows.
 */
watch(
  () => [route.query.order, table.items.value] as const,
  ([wanted]) => {
    if (!wanted || detailOpen.value) return
    const match = table.items.value.find(row => row.id === wanted)
    if (match) openOrder(match)
  },
  { immediate: true },
)

function openOrder(row: OrderRow): void {
  selected.value = row
  detailOpen.value = true
}

function onAction(payload: { key: string, row: OrderRow }): void {
  if (payload.key === 'view') openOrder(payload.row)
}

async function advance(status: string): Promise<void> {
  if (!selected.value) return

  updating.value = status
  try {
    const api = useNuxtApp().$api
    // Cancelling has its own endpoint because it releases reserved stock; the
    // generic transition would only move the status.
    const updated = status === 'CANCELLED'
      ? await api.post<OrderRow>(`/admin/orders/${selected.value.id}/cancel/`, { reason: '' })
      : await api.post<OrderRow>(`/admin/orders/${selected.value.id}/status/`, { status, reason: '' })

    selected.value = updated
    await table.refresh()
    ui.success(t('admin.orderUpdated'))
  }
  catch (error) {
    ui.error(messageFor(error))
  }
  finally {
    updating.value = ''
  }
}
</script>
