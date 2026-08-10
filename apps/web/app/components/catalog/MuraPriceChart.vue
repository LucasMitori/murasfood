<template lang="pug">
mura-card(:title="t('product.priceHistory')" icon="mdi-chart-line")
  template(#actions)
    v-btn-toggle(
      v-model="days"
      density="compact"
      variant="outlined"
      mandatory
      divided
      @update:model-value="refresh()"
    )
      v-btn(v-for="option in windows" :key="option" :value="option" size="small") {{ t('product.lastDays', { days: option }) }}

  .d-flex.align-center.justify-center(v-if="pending" style="height: 240px")
    v-progress-circular(indeterminate color="primary")

  .d-flex.flex-column.align-center.justify-center.text-center(
    v-else-if="!hasSeries"
    style="height: 240px"
    role="status"
  )
    v-icon.mb-2(icon="mdi-chart-line-variant" size="36" color="on-surface-variant")
    p.text-body-2.text-medium-emphasis.mb-0 {{ t('product.priceHistoryEmpty') }}

  template(v-else)
    v-row.mb-2(dense)
      v-col(v-for="stat in stats" :key="stat.key" cols="6" sm="3")
        .text-caption.text-medium-emphasis {{ stat.label }}
        .text-subtitle-2.font-weight-medium(:class="stat.class") {{ stat.value }}

    .mura-price-chart(style="height: 240px")
      line-chart(:data="chartData" :options="chartOptions")

    p.text-caption.text-medium-emphasis.mt-2.mb-0 {{ t('product.priceHistoryNote') }}
</template>

<script setup lang="ts">
/**
 * Shelf-price movement for one product.
 *
 * Reads the public projection, which carries dated shelf prices and nothing
 * else — no cost, no margin. See `catalog_price_history` on the API.
 */
import { computed, ref } from 'vue'
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
import { formatDate } from '~/utils/format'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip)

const props = defineProps<{ slug: string }>()

interface PricePoint { date: string, price: string }
interface PriceSeries {
  days: number
  points: PricePoint[]
  summary: {
    current: string | null
    lowest: string | null
    highest: string | null
    average: string | null
    change_percentage: string | null
  }
}

const { t, locale } = useI18n()
const money = useMoney()
const ui = useUiStore()

const windows = [30, 90, 365]
const days = ref(90)

const { data, pending, refresh } = await useAsyncData<PriceSeries>(
  () => `price-history-${props.slug}-${days.value}`,
  () => useNuxtApp().$api.get<PriceSeries>(
    `/catalog/products/${props.slug}/price-history/`,
    { query: { days: days.value } },
  ),
  {
    watch: [days],
    // A chart is not worth failing the page over: an error leaves it empty.
    default: () => ({
      days: 90,
      points: [],
      summary: { current: null, lowest: null, highest: null, average: null, change_percentage: null },
    }),
  },
)

/** One point draws nothing meaningful — a line needs somewhere to go. */
const hasSeries = computed(() => (data.value?.points.length ?? 0) > 1)

const change = computed(() => Number(data.value?.summary.change_percentage ?? 0))

const stats = computed(() => {
  const summary = data.value?.summary
  if (!summary) return []

  return [
    { key: 'current', label: t('product.currentPrice'), value: money.format(summary.current ?? '0'), class: '' },
    { key: 'lowest', label: t('product.lowestPrice'), value: money.format(summary.lowest ?? '0'), class: 'text-success' },
    { key: 'highest', label: t('product.highestPrice'), value: money.format(summary.highest ?? '0'), class: '' },
    {
      key: 'change',
      label: t('product.priceChange'),
      value: `${change.value > 0 ? '+' : ''}${change.value.toFixed(1)}%`,
      // Rising prices are bad news for a shopper, so the colours are inverted
      // relative to a merchant's revenue chart.
      class: change.value > 0 ? 'text-error' : change.value < 0 ? 'text-success' : '',
    },
  ]
})

const gridColor = computed(() => (ui.isDark ? 'rgba(255,255,255,0.08)' : 'rgba(46,42,43,0.08)'))
const textColor = computed(() => (ui.isDark ? '#F5F2F2' : '#2E2A2B'))

const chartData = computed(() => ({
  labels: (data.value?.points ?? []).map(point => formatDate(point.date, locale.value)),
  datasets: [{
    label: t('product.price'),
    data: (data.value?.points ?? []).map(point => Number(point.price)),
    borderColor: '#A64253',
    backgroundColor: 'rgba(166,66,83,0.16)',
    fill: true,
    // Stepped, not smoothed: a price holds until it is changed. A curve would
    // draw a gradual drift between two points that never happened.
    stepped: 'before' as const,
    pointRadius: 3,
    pointHoverRadius: 5,
  }],
}))

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    tooltip: {
      callbacks: {
        label: (context: { parsed: { y: number } }) => money.format(String(context.parsed.y)),
      },
    },
  },
  scales: {
    x: { grid: { color: gridColor.value }, ticks: { color: textColor.value, maxTicksLimit: 6 } },
    y: {
      grid: { color: gridColor.value },
      ticks: {
        color: textColor.value,
        callback: (value: string | number) => money.format(String(value)),
      },
      // Not zero-based: price movement is the story, and anchoring to zero
      // flattens a real 10% swing into a straight line.
      beginAtZero: false,
    },
  },
}))
</script>
