<template lang="pug">
div
  mura-page-header(
    :title="t('reports.title')"
    :subtitle="t('reports.subtitle')"
    :breadcrumbs="[{ title: 'admin.dashboard', to: '/admin' }, { title: 'reports.title' }]"
  )
    template(#actions)
      v-btn(
        color="primary"
        variant="flat"
        rounded="lg"
        prepend-icon="mdi-file-download-outline"
        @click="exportOpen = true"
      ) {{ t('reports.export') }}

  //- The period belongs above the tabs, not inside one: it applies to every
    //- report, and a merchant comparing sales to customers for the same month
    //- should not have to set it twice.
  v-card.mura-card.mb-4(flat)
    .d-flex.flex-wrap.align-center.ga-3.pa-4
      v-icon(icon="mdi-calendar-range" color="primary" size="20")
      span.text-subtitle-2 {{ t('admin.period') }}

      v-chip-group.flex-grow-1(v-model="period" mandatory selected-class="text-primary")
        v-chip(
          v-for="option in periodOptions"
          :key="option.value"
          :value="option.value"
          size="small"
          variant="tonal"
        ) {{ option.label }}

      span.text-caption.text-medium-emphasis(v-if="rangeLabel") {{ rangeLabel }}

  v-tabs.mb-4(v-model="tab" color="primary")
    v-tab(value="sales" prepend-icon="mdi-chart-line") {{ t('reports.sales') }}
    v-tab(value="inventory" prepend-icon="mdi-package-variant-closed") {{ t('reports.inventory') }}
    v-tab(value="customers" prepend-icon="mdi-account-group-outline") {{ t('reports.customers') }}

  mura-loading(v-if="pending" skeleton="card@2")

  mura-error-state(v-else-if="error" :on-retry="() => refresh()")

  template(v-else)
    //- --- Sales ------------------------------------------------------------
    template(v-if="tab === 'sales'")
      v-row
        v-col(v-for="tile in salesTiles" :key="tile.label" cols="12" sm="6" lg="3")
          mura-stat-card(
            :label="tile.label"
            :value="tile.value"
            :icon="tile.icon"
            :color="tile.color"
          )

      v-row.mt-1
        v-col(cols="12" lg="7")
          mura-chart-card(:title="t('reports.revenueOverTime')" :is-empty="!dailySeries.labels.length")
            line-chart(:data="dailyChart" :options="chartOptions")

        v-col(cols="12" lg="5")
          mura-card(:title="t('reports.byCategory')" icon="mdi-shape-outline" :padded="false")
            v-table(density="compact")
              thead
                tr
                  th {{ t('admin.category') }}
                  th.text-end {{ t('reports.units') }}
                  th.text-end {{ t('admin.revenue') }}
              tbody
                tr(v-for="entry in sales?.categories ?? []" :key="entry.category")
                  td {{ entry.category }}
                  td.text-end {{ entry.units }}
                  td.text-end {{ money.format(entry.revenue) }}

            .pa-6.text-center(v-if="!sales?.categories?.length")
              p.text-body-2.text-medium-emphasis.mb-0 {{ t('reports.noneInPeriod') }}

      mura-card.mt-4(:title="t('reports.topProducts')" icon="mdi-trophy-outline" :padded="false")
        v-table(density="comfortable")
          thead
            tr
              th {{ t('admin.productName') }}
              th SKU
              th.text-end {{ t('reports.units') }}
              th.text-end {{ t('admin.revenue') }}
              th.text-end {{ t('reports.margin') }}
          tbody
            tr(v-for="entry in sales?.products ?? []" :key="entry.sku")
              td {{ entry.name }}
              td.text-medium-emphasis {{ entry.sku }}
              td.text-end {{ entry.units }}
              td.text-end {{ money.format(entry.revenue) }}
              td.text-end {{ money.format(entry.estimated_margin) }}

        .pa-6.text-center(v-if="!sales?.products?.length")
          p.text-body-2.text-medium-emphasis.mb-0 {{ t('reports.noneInPeriod') }}

    //- --- Inventory --------------------------------------------------------
    template(v-else-if="tab === 'inventory'")
      v-row
        v-col(v-for="tile in inventoryTiles" :key="tile.label" cols="12" sm="6" lg="3")
          mura-stat-card(
            :label="tile.label"
            :value="tile.value"
            :icon="tile.icon"
            :color="tile.color"
          )

      mura-card.mt-4(:title="t('reports.stockValue')" icon="mdi-warehouse" :padded="false")
        v-table(density="comfortable" fixed-header height="520")
          thead
            tr
              th {{ t('admin.productName') }}
              th SKU
              th.text-end {{ t('admin.onHand') }}
              th.text-end {{ t('admin.available') }}
              th.text-end {{ t('reports.unitCost') }}
              th.text-end {{ t('reports.value') }}
          tbody
            tr(v-for="item in inventory?.items ?? []" :key="item.sku")
              td
                .d-flex.align-center.ga-2
                  //- Flagged here rather than in a separate list: the number a
                    //- shopkeeper acts on is the value, and the warning is only
                    //- useful beside it.
                  v-icon(v-if="item.low_stock" icon="mdi-alert" size="14" color="warning")
                  span {{ item.product }}
              td.text-medium-emphasis {{ item.sku }}
              td.text-end {{ item.quantity }}
              td.text-end {{ item.available }}
              td.text-end {{ item.unit_cost ? money.format(item.unit_cost) : '—' }}
              td.text-end {{ money.format(item.stock_value) }}

    //- --- Customers --------------------------------------------------------
    template(v-else)
      v-row
        v-col(v-for="tile in customerTiles" :key="tile.label" cols="12" sm="6" lg="3")
          mura-stat-card(
            :label="tile.label"
            :value="tile.value"
            :icon="tile.icon"
            :color="tile.color"
          )

      mura-card.mt-4(:title="t('reports.repeatExplainer')" icon="mdi-information-outline")
        p.text-body-2.text-medium-emphasis.mb-0 {{ t('reports.repeatHint') }}

  mura-report-export-dialog(v-model="exportOpen" :period="period")
</template>

<script setup lang="ts">
/**
 * The reports a shopkeeper reads on a Monday morning.
 *
 * Every number here was already computed by the API — sales, stock value,
 * customer retention, and a queued export of any of them — and none of it had
 * a screen. The backend has had these endpoints since the start; this is the
 * first thing to call them.
 *
 * Three tabs share one period, because the questions are asked together: how
 * did last month sell, what is sitting on the shelf, and did anyone come back.
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
} from 'chart.js'
import { Line as LineChart } from 'vue-chartjs'
import { useMoney } from '~/composables/useMoney'
import { useUiStore } from '~/stores/ui'
import { formatDate } from '~/utils/format'

definePageMeta({ layout: 'admin', middleware: 'merchant', permission: 'perm.admin.reports' })

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip, Legend)

interface SalesReport {
  period: { start: string, end: string }
  summary: Record<string, string | number>
  daily: { date: string, revenue: string, orders: number, average_ticket: string }[]
  products: { name: string, sku: string, units: string, revenue: string, estimated_margin: string }[]
  categories: { category: string, revenue: string, units: string }[]
}

interface InventoryReport {
  total_stock_value: string
  items_tracked: number
  low_stock_count: number
  recorded_losses: string
  items: {
    product: string
    sku: string
    quantity: string
    available: string
    unit_cost: string | null
    stock_value: string
    low_stock: boolean
  }[]
}

interface CustomerReport {
  new_customers: number
  active_customers: number
  repeat_customers: number
  repeat_rate: string
}

const { t, locale } = useI18n()
const money = useMoney()
const ui = useUiStore()

useSeoMeta({ title: () => t('reports.title'), robots: 'noindex' })

const tab = ref<'sales' | 'inventory' | 'customers'>('sales')
const period = ref('last_30')
const exportOpen = ref(false)

const periodOptions = computed(() =>
  ['today', 'yesterday', 'last_7', 'last_30', 'month', 'previous_month'].map(value => ({
    value,
    label: t(`admin.periods.${value}`),
  })),
)

/**
 * All three reports in one request each, refetched when the period changes.
 *
 * Fetched together rather than per tab so switching tabs is instant — the
 * merchant is comparing them, and a spinner between each defeats that.
 */
const { data, pending, error, refresh } = await useAsyncData(
  'admin-reports',
  async () => {
    const api = useNuxtApp().$api
    const query = { period: period.value }

    const [sales, inventory, customers] = await Promise.all([
      api.get<SalesReport>('/admin/reports/sales/', { query }),
      api.get<InventoryReport>('/admin/reports/inventory/'),
      api.get<CustomerReport>('/admin/reports/customers/', { query }),
    ])

    return { sales, inventory, customers }
  },
)

watch(period, () => refresh())

const sales = computed(() => data.value?.sales)
const inventory = computed(() => data.value?.inventory)
const customers = computed(() => data.value?.customers)

const rangeLabel = computed(() => {
  const range = sales.value?.period
  if (!range) return ''
  return `${formatDate(range.start, locale.value)} – ${formatDate(range.end, locale.value)}`
})

const salesTiles = computed(() => {
  const summary = sales.value?.summary ?? {}
  return [
    { label: t('admin.revenue'), value: money.format(String(summary.net_revenue ?? '0')), icon: 'mdi-trending-up', color: 'success' },
    { label: t('reports.orders'), value: String(summary.order_count ?? 0), icon: 'mdi-receipt-text-outline', color: 'primary' },
    { label: t('reports.averageTicket'), value: money.format(String(summary.average_ticket ?? '0')), icon: 'mdi-cart-outline', color: 'primary' },
    { label: t('reports.discounts'), value: money.format(String(summary.discount_total ?? '0')), icon: 'mdi-sale', color: 'warning' },
  ]
})

const inventoryTiles = computed(() => [
  { label: t('reports.stockValue'), value: money.format(inventory.value?.total_stock_value ?? '0'), icon: 'mdi-cash-multiple', color: 'success' },
  { label: t('reports.itemsTracked'), value: String(inventory.value?.items_tracked ?? 0), icon: 'mdi-package-variant-closed', color: 'primary' },
  { label: t('admin.lowStock'), value: String(inventory.value?.low_stock_count ?? 0), icon: 'mdi-alert-outline', color: 'warning' },
  { label: t('reports.losses'), value: String(inventory.value?.recorded_losses ?? 0), icon: 'mdi-trash-can-outline', color: 'error' },
])

const customerTiles = computed(() => [
  { label: t('reports.newCustomers'), value: String(customers.value?.new_customers ?? 0), icon: 'mdi-account-plus-outline', color: 'success' },
  { label: t('reports.activeCustomers'), value: String(customers.value?.active_customers ?? 0), icon: 'mdi-account-check-outline', color: 'primary' },
  { label: t('reports.repeatCustomers'), value: String(customers.value?.repeat_customers ?? 0), icon: 'mdi-repeat', color: 'primary' },
  { label: t('reports.repeatRate'), value: `${customers.value?.repeat_rate ?? 0}%`, icon: 'mdi-percent-outline', color: 'success' },
])

const dailySeries = computed(() => {
  const points = sales.value?.daily ?? []
  return {
    labels: points.map(point => formatDate(point.date, locale.value)),
    values: points.map(point => Number(point.revenue)),
  }
})

const gridColor = computed(() => (ui.isDark ? 'rgba(255,255,255,0.08)' : 'rgba(46,42,43,0.08)'))

const dailyChart = computed(() => ({
  labels: dailySeries.value.labels,
  datasets: [{
    data: dailySeries.value.values,
    borderColor: 'rgb(var(--v-theme-primary))',
    backgroundColor: 'rgba(var(--v-theme-primary), 0.12)',
    fill: true,
    tension: 0.35,
    pointRadius: 2,
  }],
}))

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  scales: {
    x: { grid: { display: false } },
    y: { beginAtZero: true, grid: { color: gridColor.value } },
  },
}))
</script>
