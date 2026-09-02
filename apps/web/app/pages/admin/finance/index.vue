<template lang="pug">
div
  mura-page-header(
    :title="t('admin.finance')"
    :subtitle="t('admin.financeSubtitle')"
    :breadcrumbs="[{ title: 'admin.dashboard', to: '/admin' }, { title: 'admin.finance' }]"
  )

  mura-loading(v-if="pending" skeleton="card@2")

  mura-error-state(v-else-if="error" :on-retry="() => refresh()")

  template(v-else)
    v-row
      v-col(cols="12" sm="4")
        mura-stat-card(
          :label="t('admin.revenue')"
          :value="money.format(statement.revenue)"
          icon="mdi-trending-up"
          color="success"
        )
      v-col(cols="12" sm="4")
        mura-stat-card(
          :label="t('admin.expenses')"
          :value="money.format(statement.total_expenses)"
          icon="mdi-trending-down"
          color="warning"
        )
      v-col(cols="12" sm="4")
        mura-stat-card(
          :label="t('admin.result')"
          :value="money.format(statement.net_result)"
          icon="mdi-scale-balance"
          :color="Number(statement.net_result) >= 0 ? 'primary' : 'error'"
        )

    v-row.mt-1
      v-col(cols="12" md="7")
        mura-chart-card(
          :title="t('admin.revenue')"
          :is-empty="!monthlySeries.labels.length"
        )
          line-chart(:data="monthlyData" :options="chartOptions")

      v-col(cols="12" md="5")
        mura-card(:title="t('admin.expenses')" icon="mdi-chart-donut")
          mura-empty-state(
            v-if="!byCategory.length"
            :title="t('admin.noExpenses')"
            :description="t('admin.noExpensesHint')"
            icon="mdi-receipt-text-outline"
          )
          v-list(v-else density="compact" bg-color="transparent")
            v-list-item.px-0(v-for="row in byCategory" :key="row.category")
              v-list-item-title.text-body-2 {{ row.category }}
              template(#append)
                span.text-body-2.font-weight-medium {{ money.format(row.total) }}

    mura-data-table.mt-4(
      :table="table"
      :columns="columns"
      :title="t('admin.finance')"
      searchable
    )
      template(#item.direction="{ item }")
        v-chip(
          :color="item.direction === 'INFLOW' ? 'success' : 'warning'"
          :prepend-icon="item.direction === 'INFLOW' ? 'mdi-arrow-down-left' : 'mdi-arrow-up-right'"
          size="x-small"
          variant="tonal"
        ) {{ item.direction === 'INFLOW' ? t('admin.inflow') : t('admin.outflow') }}
</template>

<script setup lang="ts">
/**
 * Money in, money out, and what is left.
 *
 * The statement comes from the API's own profit-and-loss endpoint rather than
 * being summed here: the same figures appear on reports and in exports, and
 * two implementations of one calculation eventually disagree.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  CategoryScale,
  Chart as ChartJS,
  Filler,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
} from 'chart.js'
import { Line as LineChart } from 'vue-chartjs'
import type { TableColumn } from '~/types/ui'
import { useServerTable } from '~/composables/useServerTable'
import { useMoney } from '~/composables/useMoney'
import { useUiStore } from '~/stores/ui'

definePageMeta({ layout: 'admin', middleware: 'merchant', permission: 'perm.admin.finance' })

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip)

interface Statement {
  revenue: string
  total_expenses: string
  net_result: string
  gross_profit: string
}

interface FinanceSummary {
  statement: Statement
  monthly: { month: string, revenue: string, expenses: string }[]
  expenses_by_category: { category: string, total: string }[]
}

interface TransactionRow {
  id: string
  description: string
  category_name?: string
  amount: string
  direction: string
  occurred_on: string
  [key: string]: unknown
}

const { t } = useI18n()
const money = useMoney()
const ui = useUiStore()

useSeoMeta({ title: () => t('admin.finance') })

const { data, pending, error, refresh } = await useAsyncData<FinanceSummary>(
  'admin-finance-summary',
  () => useNuxtApp().$api.get<FinanceSummary>('/admin/finance/summary/'),
  {
    default: () => ({
      statement: { revenue: '0.00', total_expenses: '0.00', net_result: '0.00', gross_profit: '0.00' },
      monthly: [],
      expenses_by_category: [],
    }),
  },
)

const statement = computed(() => data.value?.statement ?? {
  revenue: '0.00', total_expenses: '0.00', net_result: '0.00', gross_profit: '0.00',
})

const byCategory = computed(() => data.value?.expenses_by_category ?? [])

const monthlySeries = computed(() => {
  const rows = data.value?.monthly ?? []
  return {
    labels: rows.map(row => row.month),
    revenue: rows.map(row => Number(row.revenue)),
    expenses: rows.map(row => Number(row.expenses)),
  }
})

const gridColor = computed(() => (ui.isDark ? 'rgba(255,255,255,0.08)' : 'rgba(31,28,29,0.08)'))
const textColor = computed(() => (ui.isDark ? '#F3F0F0' : '#1F1C1D'))

const monthlyData = computed(() => ({
  labels: monthlySeries.value.labels,
  datasets: [
    {
      label: t('admin.revenue'),
      data: monthlySeries.value.revenue,
      borderColor: '#2E7D5B',
      backgroundColor: 'rgba(46,125,91,0.16)',
      fill: true,
      tension: 0.35,
    },
    {
      label: t('admin.expenses'),
      data: monthlySeries.value.expenses,
      borderColor: '#B02233',
      backgroundColor: 'rgba(176,34,51,0.14)',
      fill: true,
      tension: 0.35,
    },
  ],
}))

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: true, labels: { color: textColor.value, boxWidth: 12 } } },
  scales: {
    x: { grid: { color: gridColor.value }, ticks: { color: textColor.value, maxTicksLimit: 8 } },
    y: {
      grid: { color: gridColor.value },
      ticks: { color: textColor.value, callback: (value: string | number) => money.format(String(value)) },
      beginAtZero: true,
    },
  },
}))

const table = useServerTable<TransactionRow>({
  endpoint: '/admin/finance/transactions/',
  defaultSort: [{ key: 'occurred_on', order: 'desc' }],
  searchParam: 'search',
})

const columns: TableColumn<TransactionRow>[] = [
  { key: 'occurred_on', title: 'admin.entryDate', sortable: true, format: 'date' },
  { key: 'description', title: 'admin.description', sortable: false },
  { key: 'category_name', title: 'admin.category', sortable: false, hideBelow: 'md', value: row => row.category_name ?? '—' },
  { key: 'amount', title: 'admin.amount', sortable: true, format: 'money', align: 'end' },
  { key: 'direction', title: 'admin.direction', sortable: false, align: 'center' },
]
</script>
