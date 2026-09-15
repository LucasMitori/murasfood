<template lang="pug">
div
  mura-card(:title="t('finance.forecastTitle')" :subtitle="t('finance.forecastHint')" icon="mdi-chart-timeline-variant")
    template(#actions)
      v-chip(:color="confidenceColor" size="small" variant="tonal") {{ confidenceLabel }}

    mura-loading(v-if="pending" skeleton="card")

    mura-error-state(v-else-if="error" :on-retry="() => refresh()")

    mura-empty-state(
      v-else-if="!data || data.confidence === 'insufficient'"
      :title="t('finance.confidenceInsufficient')"
      :description="data?.note || ''"
      icon="mdi-chart-timeline-variant"
    )

    template(v-else)
      v-row.mb-2
        v-col(cols="12" sm="4")
          .mura-forecast__figure
            span.text-caption.text-medium-emphasis {{ t('finance.forecastBasis', data.basis_months, { count: data.basis_months }) }}
        v-col(cols="12" sm="4")
          .mura-forecast__figure
            span.text-caption.text-medium-emphasis {{ t('finance.trendRevenue') }}
            strong(:class="Number(data.monthly_revenue_change) >= 0 ? 'text-success' : 'text-error'")
              | {{ Number(data.monthly_revenue_change) > 0 ? '+' : '' }}{{ money.format(data.monthly_revenue_change) }}/{{ t('finance.budgetMonth').toLowerCase() }}
        v-col(cols="12" sm="4")
          .mura-forecast__figure
            span.text-caption.text-medium-emphasis {{ t('finance.trendExpenses') }}
            strong(:class="Number(data.monthly_expense_change) <= 0 ? 'text-success' : 'text-warning'")
              | {{ Number(data.monthly_expense_change) > 0 ? '+' : '' }}{{ money.format(data.monthly_expense_change) }}/{{ t('finance.budgetMonth').toLowerCase() }}

      .mura-forecast__chart
        line-chart(:data="chartData" :options="chartOptions")

  mura-card.mt-4(:title="t('finance.tabCashFlow')" icon="mdi-cash-sync")
    mura-loading(v-if="cashPending" skeleton="card")

    template(v-else-if="cash")
      v-row.mb-3
        v-col(cols="12" sm="4")
          .mura-forecast__figure
            span.text-caption.text-medium-emphasis {{ t('finance.cashBalance') }}
            strong.text-h6(:class="Number(cash.closing_balance) >= 0 ? 'text-success' : 'text-error'") {{ money.format(cash.closing_balance) }}
        v-col(cols="12" sm="4")
          .mura-forecast__figure
            span.text-caption.text-medium-emphasis {{ t('finance.pendingIn') }}
            strong {{ money.format(cash.pending_in) }}
        v-col(cols="12" sm="4")
          .mura-forecast__figure
            span.text-caption.text-medium-emphasis {{ t('finance.pendingOut') }}
            strong {{ money.format(cash.pending_out) }}

      mura-empty-state(
        v-if="!cash.periods.length"
        :title="t('states.noData')"
        icon="mdi-cash-remove"
      )

      .mura-forecast__scroll(v-else)
        table.mura-forecast__table
          thead
            tr
              th {{ t('finance.budgetMonth') }}
              th.text-end {{ t('finance.cashIn') }}
              th.text-end {{ t('finance.cashOut') }}
              th.text-end {{ t('finance.cashNet') }}
              th.text-end {{ t('finance.cashBalance') }}
          tbody
            tr(v-for="row in cash.periods" :key="row.month")
              td {{ monthLabel(row.month) }}
              td.text-end.text-success {{ money.format(row.inflow) }}
              td.text-end.text-error {{ money.format(row.outflow) }}
              td.text-end(:class="Number(row.net) >= 0 ? 'text-success' : 'text-error'") {{ money.format(row.net) }}
              td.text-end.font-weight-medium {{ money.format(row.balance) }}
</template>

<script setup lang="ts">
/**
 * Where the money is going, and where it is likely to go next.
 *
 * Two questions that look alike and are not. The forecast asks whether the shop
 * is trending up; the cash flow asks whether it will have money in the till.
 * A business can pass the first and fail the second — which is the usual way
 * a profitable small shop dies — so they sit together and are labelled apart.
 *
 * The projection is an extrapolation and never pretends otherwise: the
 * confidence chip and the caption both say how many months it was fitted to,
 * and the projected series is drawn dashed so it cannot be mistaken for
 * history at a glance.
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
import { useMoney } from '~/composables/useMoney'
import { useUiStore } from '~/stores/ui'
import { formatMonth } from '~/utils/format'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip)

interface Point { month: string, revenue: string, expenses: string, result?: string }

interface Forecast {
  basis_months: number
  confidence: 'insufficient' | 'low' | 'medium' | 'good'
  monthly_revenue_change: string
  monthly_expense_change: string
  history: Point[]
  projection: Point[]
  note: string
}

interface CashFlow {
  periods: { month: string, inflow: string, outflow: string, net: string, balance: string }[]
  closing_balance: string
  pending_in: string
  pending_out: string
}

const { t, locale } = useI18n()
const money = useMoney()
const ui = useUiStore()

const { data, pending, error, refresh } = await useAsyncData<Forecast>(
  'admin-finance-forecast',
  () => useNuxtApp().$api.get<Forecast>('/admin/finance/forecast/', { query: { months: 3 } }),
)

const { data: cash, pending: cashPending } = await useAsyncData<CashFlow>(
  'admin-finance-cashflow',
  () => useNuxtApp().$api.get<CashFlow>('/admin/finance/cash-flow/', {
    query: { period: 'custom', start: yearAgo(), end: today() },
  }),
)

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

function yearAgo(): string {
  const date = new Date()
  date.setFullYear(date.getFullYear() - 1)
  return date.toISOString().slice(0, 10)
}

function monthLabel(value: string): string {
  return formatMonth(value, locale.value)
}

const confidenceLabel = computed(() => {
  const key = `finance.confidence${(data.value?.confidence ?? 'insufficient').replace(/^./, c => c.toUpperCase())}`
  return t(key)
})

const confidenceColor = computed(() => ({
  insufficient: 'secondary',
  low: 'warning',
  medium: 'info',
  good: 'success',
}[data.value?.confidence ?? 'insufficient']))

const gridColor = computed(() => (ui.isDark ? 'rgba(255,255,255,0.08)' : 'rgba(31,28,29,0.08)'))
const textColor = computed(() => (ui.isDark ? '#F3F0F0' : '#1F1C1D'))

/**
 * History and projection on one continuous axis.
 *
 * The projected series repeats the final historical point so the dashed line
 * starts where the solid one ends. Without that the two look like unrelated
 * charts sharing an axis, and the reader loses the join that is the whole
 * point of showing them together.
 */
const chartData = computed(() => {
  const history = data.value?.history ?? []
  const projection = data.value?.projection ?? []
  const labels = [...history, ...projection].map(point => monthLabel(point.month))

  const pad = (values: number[], before: number) =>
    [...Array(before).fill(null), ...values]

  const lastRevenue = history.length ? Number(history[history.length - 1]!.revenue) : null
  const lastExpenses = history.length ? Number(history[history.length - 1]!.expenses) : null

  return {
    labels,
    datasets: [
      {
        label: t('admin.revenue'),
        data: [...history.map(p => Number(p.revenue)), ...Array(projection.length).fill(null)],
        borderColor: '#2E7D5B',
        backgroundColor: 'rgba(46,125,91,0.14)',
        fill: true,
        tension: 0.35,
      },
      {
        label: t('finance.projected'),
        data: pad(
          [lastRevenue, ...projection.map(p => Number(p.revenue))].filter(v => v !== null) as number[],
          Math.max(0, history.length - 1),
        ),
        borderColor: '#2E7D5B',
        borderDash: [6, 4],
        pointStyle: 'circle',
        fill: false,
        tension: 0.35,
      },
      {
        label: t('admin.expenses'),
        data: [...history.map(p => Number(p.expenses)), ...Array(projection.length).fill(null)],
        borderColor: '#B02233',
        backgroundColor: 'rgba(176,34,51,0.12)',
        fill: true,
        tension: 0.35,
      },
      {
        label: `${t('admin.expenses')} · ${t('finance.projected')}`,
        data: pad(
          [lastExpenses, ...projection.map(p => Number(p.expenses))].filter(v => v !== null) as number[],
          Math.max(0, history.length - 1),
        ),
        borderColor: '#B02233',
        borderDash: [6, 4],
        fill: false,
        tension: 0.35,
      },
    ],
  }
})

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: 'index' as const, intersect: false },
  plugins: { legend: { labels: { color: textColor.value, boxWidth: 12, usePointStyle: true } } },
  scales: {
    x: { grid: { color: gridColor.value }, ticks: { color: textColor.value, maxTicksLimit: 10 } },
    y: {
      grid: { color: gridColor.value },
      ticks: {
        color: textColor.value,
        callback: (value: string | number) => money.format(String(value)),
      },
      beginAtZero: true,
    },
  },
}))
</script>

<style scoped>
.mura-forecast__chart {
  height: 320px;
}

.mura-forecast__figure {
  display: flex;
  flex-direction: column;
  padding: 12px 16px;
  border: 1px solid rgba(var(--v-border-color), 0.6);
  border-radius: var(--mura-radius-md, 10px);
  gap: 2px;
}

.mura-forecast__scroll {
  overflow-x: auto;
}

.mura-forecast__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.mura-forecast__table th {
  padding: 8px 12px;
  border-bottom: 1px solid rgba(var(--v-border-color), 0.8);
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-align: start;
  text-transform: uppercase;
  white-space: nowrap;
}

.mura-forecast__table td {
  padding: 8px 12px;
  border-bottom: 1px solid rgba(var(--v-border-color), 0.4);
  white-space: nowrap;
}
</style>
