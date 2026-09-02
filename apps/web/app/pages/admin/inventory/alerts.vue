<template lang="pug">
div
  mura-page-header(
    :title="t('admin.stockHealth')"
    :subtitle="t('admin.stockHealthSubtitle')"
    :breadcrumbs="[{ title: 'admin.dashboard', to: '/admin' }, { title: 'admin.inventory', to: '/admin/inventory' }, { title: 'admin.stockHealth' }]"
  )

  //- Each tile is a filter, not just a number. Reading "7 out of stock" and
  //- then having to go and build that filter by hand is the slow half of the
  //- job, so the tile is the way in.
  v-row.mb-2
    v-col(v-for="band in bands" :key="band.value" cols="12" sm="6" md="3")
      v-card.mura-health(
        :class="{ 'mura-health--active': view === band.value }"
        flat
        border
        rounded="lg"
        role="button"
        :aria-pressed="view === band.value"
        @click="select(band.value)"
      )
        .d-flex.align-center.ga-3
          v-avatar(:color="band.color" size="40" variant="tonal")
            v-icon(:icon="band.icon" size="20")
          div
            p.text-caption.text-medium-emphasis.mb-0 {{ band.label }}
            p.text-h6.font-weight-bold.mb-0 {{ band.count }}

  mura-data-table(
    :table="table"
    :columns="columns"
    :actions="rowActions"
    :title="activeBand.label"
    :empty-title="t('admin.stockHealthEmpty')"
    :empty-description="t('admin.stockHealthEmptyHint')"
    empty-icon="mdi-check-circle-outline"
    searchable
    @action="onAction"
  )
    template(#item.product_name="{ item }")
      div
        p.text-body-2.mb-0 {{ item.product_name }}
        p.text-caption.text-medium-emphasis.mb-0 {{ item.product_sku }}

    template(#item.available_quantity="{ item }")
      v-chip(:color="levelColor(item)" size="x-small" variant="tonal") {{ money.quantity(String(item.available_quantity), String(item.unit || '')) }}

    template(#item.reorder_threshold="{ item }")
      span.text-medium-emphasis {{ money.quantity(String(item.reorder_threshold ?? '0'), String(item.unit || '')) }}
</template>

<script setup lang="ts">
/**
 * Stock health.
 *
 * The inventory table answers "how much of everything is there". This answers
 * the question a shopkeeper actually asks: *what needs doing today*. Out of
 * stock is lost sales happening now; below the reorder point is lost sales
 * later; untracked is neither, and is here only so it cannot be mistaken for
 * one of the other two.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { TableAction, TableColumn } from '~/types/ui'
import { useServerTable } from '~/composables/useServerTable'
import { useMoney } from '~/composables/useMoney'

definePageMeta({ layout: 'admin', middleware: 'merchant', permission: 'perm.admin.inventory' })

interface StockRow {
  id: string
  product: string
  product_name: string
  product_sku: string
  unit: string
  quantity: string
  reserved_quantity: string
  available_quantity: string
  minimum_stock: string
  reorder_threshold?: string
  track_stock: boolean
  [key: string]: unknown
}

type Band = 'out' | 'low' | 'healthy' | 'untracked'

const { t } = useI18n()
const money = useMoney()
const router = useRouter()

useSeoMeta({ title: () => t('admin.stockHealth'), robots: 'noindex' })

const view = ref<Band>('out')

/**
 * The four counts, from one request.
 *
 * The server decides which band a product is in, and the same rule filters the
 * list below — so a tile reading "0 out of stock" can never sit above a table
 * showing fifty. Counting on the client from a page of rows is what let those
 * two disagree.
 */
const { data: health } = await useAsyncData<Record<Band, number>>(
  'admin-stock-health',
  () => useNuxtApp().$api.get('/admin/inventory/health/'),
)

const bands = computed(() => [
  {
    value: 'out' as Band,
    label: t('admin.outOfStock'),
    icon: 'mdi-package-variant-remove',
    color: 'error',
    count: health.value?.out ?? 0,
  },
  {
    value: 'low' as Band,
    label: t('admin.belowReorder'),
    icon: 'mdi-trending-down',
    color: 'warning',
    count: health.value?.low ?? 0,
  },
  {
    value: 'healthy' as Band,
    label: t('admin.healthy'),
    icon: 'mdi-check-circle-outline',
    color: 'success',
    count: health.value?.healthy ?? 0,
  },
  {
    value: 'untracked' as Band,
    label: t('admin.untracked'),
    icon: 'mdi-help-circle-outline',
    color: 'secondary',
    count: health.value?.untracked ?? 0,
  },
])

const activeBand = computed(() =>
  bands.value.find(band => band.value === view.value) ?? bands.value[0]!,
)

const table = useServerTable<StockRow>({
  endpoint: '/admin/inventory/',
  defaultSort: [{ key: 'available_quantity', order: 'asc' }],
  sortMap: { product_name: 'product__name', available_quantity: 'quantity' },
  // One parameter for all four bands, resolved by the same code that produced
  // the counts above.
  filters: () => ({ stock_state: view.value }),
  searchParam: 'search',
})

function select(band: Band): void {
  view.value = band
  table.applyFilters()
}

const columns: TableColumn<StockRow>[] = [
  { key: 'product_name', title: 'admin.productName', sortable: true },
  { key: 'available_quantity', title: 'admin.available', sortable: true, align: 'end' },
  { key: 'reorder_threshold', title: 'admin.reorderPoint', sortable: false, align: 'end', hideBelow: 'md' },
]

const rowActions: TableAction<StockRow>[] = [
  { key: 'adjust', label: 'admin.adjust', icon: 'mdi-scale-balance', permission: 'inventory.adjust' },
  { key: 'batches', label: 'admin.expiry', icon: 'mdi-calendar-clock', permission: 'inventory.view' },
]

/**
 * Mirrors the server's bands for a row already on screen.
 *
 * Duplicated rather than shared because the two answer different questions:
 * the server decides which rows to return, this decides what colour one is.
 * They are kept in step by the partition test on the API.
 */
function isOut(row: StockRow): boolean {
  return row.track_stock && Number(row.available_quantity) <= 0
}

function isLow(row: StockRow): boolean {
  return row.track_stock
    && !isOut(row)
    && Number(row.available_quantity) <= Number(row.reorder_threshold ?? 0)
}

function levelColor(row: StockRow): string {
  if (isOut(row)) return 'error'
  if (isLow(row)) return 'warning'
  return 'success'
}

function onAction(payload: { key: string, row: StockRow }): void {
  // Both actions live on other screens; sending the product with them means
  // the operator does not have to find the row a second time.
  if (payload.key === 'adjust') {
    void router.push(`/admin/inventory?product=${payload.row.product}`)
    return
  }

  if (payload.key === 'batches') {
    void router.push(`/admin/inventory/expiry?product=${payload.row.product}`)
  }
}
</script>

<style scoped>
.mura-health {
  padding: 1rem;
  cursor: pointer;
  transition: border-color 160ms ease, background-color 160ms ease;
}

.mura-health:hover {
  border-color: rgba(var(--v-theme-primary), 0.4);
}

.mura-health--active {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.06);
}
</style>
