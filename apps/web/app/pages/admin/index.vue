<template lang="pug">
div
  .d-flex.flex-wrap.align-center.justify-space-between.ga-3.mb-6
    h1.text-h5 {{ t('admin.dashboard') }}
    v-select(
      v-model="period"
      :items="periodOptions"
      item-title="label"
      item-value="value"
      density="compact"
      hide-details
      style="max-width: 220px"
    )

  v-progress-linear(v-if="pending" indeterminate color="primary")

  mura-error-state(v-else-if="error" :on-retry="() => refresh()")

  template(v-else-if="data")
    v-row.mb-2
      v-col(cols="12" sm="6" lg="3")
        mura-stat-card(
          :label="t('admin.revenuePeriod')"
          :value="money.format(data.revenue.period)"
          :change="data.revenue.change_percentage"
          show-no-comparison
          icon="mdi-cash-multiple"
        )
      v-col(cols="12" sm="6" lg="3")
        mura-stat-card(
          :label="t('admin.ordersCount')"
          :value="String(data.orders.count)"
          :change="data.orders.change_percentage"
          show-no-comparison
          icon="mdi-receipt-text-outline"
          color="accent"
        )
      v-col(cols="12" sm="6" lg="3")
        mura-stat-card(
          :label="t('admin.averageTicket')"
          :value="money.format(data.orders.average_ticket)"
          icon="mdi-chart-bell-curve"
          color="info"
        )
      v-col(cols="12" sm="6" lg="3")
        mura-stat-card(
          :label="t('admin.pendingOrders')"
          :value="String(data.counters.pending_orders)"
          icon="mdi-clock-alert-outline"
          color="warning"
        )

    v-row
      v-col(cols="12" lg="8")
        mura-chart-card(:title="t('admin.salesChart')" :is-empty="!salesChart.labels.length")
          line-chart(:data="salesChartData" :options="lineOptions")

      v-col(cols="12" lg="4")
        mura-chart-card(:title="t('admin.categoryChart')" :is-empty="!data.charts.categories.length")
          doughnut-chart(:data="categoryChartData" :options="doughnutOptions")

    v-row
      v-col(cols="12" lg="7")
        v-card.mura-card.pa-4(flat)
          h3.text-subtitle-1.mb-3 {{ t('admin.recentOrders') }}
          v-table(density="comfortable")
            thead
              tr
                th {{ t('order.orderNumber') }}
                th {{ t('order.status') }}
                th.text-right {{ t('common.total') }}
            tbody
              tr(v-for="order in data.recent_orders" :key="order.id")
                td
                  //- The orders screen opens the detail as a side sheet rather than a
                    //- page, so the link carries the id as a query and that screen
                    //- opens it. Pointing at `/admin/orders/<id>` matched no route
                    //- at all, and every order number on this dashboard was dead.
                  nuxt-link.text-decoration-none(:to="`/admin/orders?order=${order.id}`") {{ order.number }}
                td
                  mura-status-badge(:status="order.status" size="x-small")
                td.text-right.mura-price {{ money.format(order.total) }}
          mura-empty-state(
            v-if="!data.recent_orders.length"
            :title="t('states.noOrders')"
            icon="mdi-receipt-text-outline"
          )

      v-col(cols="12" lg="5")
        v-card.mura-card.pa-4(flat)
          h3.text-subtitle-1.mb-3 {{ t('admin.topProducts') }}
          v-list(density="compact" bg-color="transparent")
            v-list-item.px-0(v-for="row in data.charts.top_products.slice(0, 6)" :key="row.name")
              v-list-item-title.text-body-2 {{ row.name }}
              v-list-item-subtitle.text-caption {{ row.units }} · {{ money.format(row.revenue) }}
          mura-empty-state(
            v-if="!data.charts.top_products.length"
            :title="t('states.noProducts')"
            icon="mdi-package-variant"
          )

    v-alert.mt-4(
      v-if="data.alerts.low_stock_count > 0"
      type="warning"
      variant="tonal"
      :title="`${t('admin.lowStock')} (${data.alerts.low_stock_count})`"
    )
      ul.mt-2
        li(v-for="item in data.alerts.low_stock" :key="item.sku") {{ item.product }} — {{ item.available }}
</template>

<script setup lang="ts">
/**
 * Merchant dashboard.
 *
 * Every figure and series is aggregated by PostgreSQL and arrives ready to
 * render: the browser plots, it does not compute (spec §31).
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  ArcElement,
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
} from 'chart.js'
import { Doughnut as DoughnutChart, Line as LineChart } from 'vue-chartjs'
import type { DashboardSummary } from '~/types/api'
import { useMoney } from '~/composables/useMoney'
import { useUiStore } from '~/stores/ui'
import { formatDate } from '~/utils/format'

definePageMeta({ layout: 'admin', middleware: 'merchant', permission: 'perm.admin.dashboard' })

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, ArcElement, Filler, Tooltip, Legend)

const { t, locale } = useI18n()
const money = useMoney()
const ui = useUiStore()

const period = ref('last_30')

const { data, pending, error, refresh } = await useAsyncData<DashboardSummary>(
  'admin-dashboard',
  () => useNuxtApp().$api.get<DashboardSummary>('/admin/dashboard/', { query: { period: period.value } }),
)

watch(period, () => refresh())

useSeoMeta({ title: () => t('admin.dashboard'), robots: 'noindex' })

const periodOptions = computed(() =>
  ['today', 'yesterday', 'last_7', 'last_30', 'month', 'previous_month'].map(value => ({
    value,
    // `admin.period` is the field's own label ("Period"); the options live
    // under `admin.periods`. Reading them from the label treated a string as a
    // namespace, so none of the six ever resolved.
    label: t(`admin.periods.${value}`),
  })),
)

const salesChart = computed(() => {
  const points = data.value?.charts.revenue_by_day ?? []
  return {
    labels: points.map(point => formatDate(point.date, locale.value)),
    values: points.map(point => Number(point.revenue)),
  }
})

const gridColor = computed(() => (ui.isDark ? 'rgba(255,255,255,0.08)' : 'rgba(46,42,43,0.08)'))
const textColor = computed(() => (ui.isDark ? '#F5F2F2' : '#2E2A2B'))

const salesChartData = computed(() => ({
  labels: salesChart.value.labels,
  datasets: [{
    label: t('admin.revenue'),
    data: salesChart.value.values,
    borderColor: '#A64253',
    backgroundColor: 'rgba(166,66,83,0.16)',
    fill: true,
    tension: 0.35,
    pointRadius: 2,
  }],
}))

const lineOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  scales: {
    x: { grid: { color: gridColor.value }, ticks: { color: textColor.value, maxTicksLimit: 8 } },
    y: { grid: { color: gridColor.value }, ticks: { color: textColor.value }, beginAtZero: true },
  },
}))

const categoryChartData = computed(() => {
  const rows = data.value?.charts.categories ?? []
  return {
    labels: rows.map(row => row.category),
    datasets: [{
      data: rows.map(row => Number(row.revenue)),
      backgroundColor: ['#7B2D3B', '#A64253', '#C96A7A', '#E8C9CF', '#5C5254', '#2E7D5B'],
      borderWidth: 0,
    }],
  }
})

const doughnutOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { position: 'bottom' as const, labels: { color: textColor.value, boxWidth: 12 } } },
}))
</script>
