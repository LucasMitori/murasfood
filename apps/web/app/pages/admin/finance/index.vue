<template lang="pug">
div
  mura-page-header(
    :title="t('admin.finance')"
    :subtitle="t('admin.financeSubtitle')"
    :breadcrumbs="[{ title: 'admin.dashboard', to: '/admin' }, { title: 'admin.finance' }]"
  )

  v-tabs.mb-4(v-model="tab" color="primary" show-arrows)
    v-tab(value="overview" prepend-icon="mdi-view-dashboard-outline") {{ t('finance.tabOverview') }}
    v-tab(value="statement" prepend-icon="mdi-file-document-outline") {{ t('finance.tabStatement') }}
    v-tab(value="budget" prepend-icon="mdi-wallet-outline") {{ t('finance.tabBudget') }}
    v-tab(value="forecast" prepend-icon="mdi-chart-timeline-variant") {{ t('finance.tabForecast') }}
    v-tab(value="pricing" prepend-icon="mdi-tag-arrow-up-outline") {{ t('finance.tabPricing') }}
    v-tab(value="entries" prepend-icon="mdi-format-list-bulleted") {{ t('finance.tabEntries') }}

  v-window(v-model="tab")
    v-window-item(value="overview")
      mura-loading(v-if="pending" skeleton="card@2")

      mura-error-state(v-else-if="error" :on-retry="() => refresh()")

      template(v-else)
        //- Four figures, not three: revenue minus cost of goods minus expenses is
          //- the result. `total_expenses` counts operating costs only — rent, fees,
          //- delivery — so leaving cost of goods out of the row made the tiles
          //- contradict each other. A shop with R$ 313,50 of sales and R$ 221,00 of
          //- goods read "Receita 313,50 / Despesas 0,00 / Resultado 92,50", with
          //- nothing on screen accounting for the missing 221.
        v-row
          v-col(cols="12" sm="6" lg="3")
            mura-stat-card(
              :label="t('admin.revenue')"
              :value="money.format(statement.revenue)"
              icon="mdi-trending-up"
              color="success"
            )
          v-col(cols="12" sm="6" lg="3")
            mura-stat-card(
              :label="t('admin.cogs')"
              :value="money.format(statement.cogs)"
              icon="mdi-package-variant-closed"
              color="warning"
            )
          v-col(cols="12" sm="6" lg="3")
            mura-stat-card(
              :label="t('admin.expenses')"
              :value="money.format(statement.total_expenses)"
              icon="mdi-trending-down"
              color="warning"
            )
          v-col(cols="12" sm="6" lg="3")
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


    v-window-item(value="statement")
      mura-statement-panel

    v-window-item(value="budget")
      mura-budget-panel

    v-window-item(value="forecast")
      mura-forecast-panel

    v-window-item(value="pricing")
      mura-pricing-panel

    v-window-item(value="entries")
      mura-data-table(
        :table="table"
        :columns="columns"
        :title="t('finance.tabEntries')"
        searchable
        exportable
        export-name="lancamentos"
      )
        //- Keyed on `transaction_type`, which is what the API actually sends.
          //- This read `item.direction` — a field no endpoint has ever returned —
          //- so every row took the else branch and revenue was labelled as money
          //- going out. The table was empty until the ledger projection was
          //- scheduled, so nobody had seen a row to notice.
        template(#item.transaction_type="{ item }")
          v-chip(
            :color="item.transaction_type === 'REVENUE' ? 'success' : 'warning'"
            :prepend-icon="item.transaction_type === 'REVENUE' ? 'mdi-arrow-down-left' : 'mdi-arrow-up-right'"
            size="x-small"
            variant="tonal"
          ) {{ item.transaction_type === 'REVENUE' ? t('admin.inflow') : t('admin.outflow') }}
</template>

<script setup lang="ts">
/**
 * Money in, money out, and what is left.
 *
 * The statement comes from the API's own profit-and-loss endpoint rather than
 * being summed here: the same figures appear on reports and in exports, and
 * two implementations of one calculation eventually disagree.
 */
import { computed, ref, watch } from 'vue'
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
  cogs: string
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
  transaction_type: string
  occurred_on: string
  [key: string]: unknown
}

const { t } = useI18n()
const money = useMoney()
const ui = useUiStore()
const route = useRoute()
const router = useRouter()

useSeoMeta({ title: () => t('admin.finance') })

/**
 * Which panel is open, mirrored into the URL.
 *
 * So a merchant can bookmark the DRE, and so the dashboard's quick-create menu
 * can link straight at the ledger instead of dropping someone on the overview
 * to hunt for the tab themselves.
 */
const TABS = ['overview', 'statement', 'budget', 'forecast', 'pricing', 'entries']

const tab = ref(TABS.includes(String(route.query.tab)) ? String(route.query.tab) : 'overview')

watch(tab, (value) => {
  router.replace({ query: value === 'overview' ? {} : { tab: value } })
})

const { data, pending, error, refresh } = await useAsyncData<FinanceSummary>(
  'admin-finance-summary',
  () => useNuxtApp().$api.get<FinanceSummary>('/admin/finance/summary/'),
  {
    default: () => ({
      statement: {
        revenue: '0.00', cogs: '0.00', total_expenses: '0.00',
        net_result: '0.00', gross_profit: '0.00',
      },
      monthly: [],
      expenses_by_category: [],
    }),
  },
)

const statement = computed(() => data.value?.statement ?? {
  revenue: '0.00', cogs: '0.00', total_expenses: '0.00',
  net_result: '0.00', gross_profit: '0.00',
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
  { key: 'transaction_type', title: 'admin.direction', sortable: false, align: 'center' },
]
</script>
