<template lang="pug">
mura-card(:title="t('finance.statementTitle')" :subtitle="t('finance.statementHint')" icon="mdi-file-document-outline")
  template(#actions)
    v-select.mura-statement__period(
      v-model="period"
      :items="periodOptions"
      item-title="label"
      item-value="value"
      density="compact"
      variant="outlined"
      hide-details
      :aria-label="t('admin.period')"
    )

  mura-loading(v-if="pending" skeleton="card")

  mura-error-state(v-else-if="error" :on-retry="() => refresh()")

  template(v-else-if="data")
    v-alert.mb-4(
      v-if="!data.expenses_recorded"
      type="info"
      variant="tonal"
      density="compact"
      icon="mdi-information-outline"
    ) {{ t('finance.noExpensesRecorded') }}

    v-row.mb-2
      v-col(cols="12" sm="4")
        .mura-statement__margin
          span.text-caption.text-medium-emphasis {{ t('finance.grossMargin') }}
          strong.text-h6 {{ data.margins.gross }}%
      v-col(cols="12" sm="4")
        .mura-statement__margin
          span.text-caption.text-medium-emphasis {{ t('finance.operatingMargin') }}
          strong.text-h6 {{ data.margins.operating }}%
      v-col(cols="12" sm="4")
        .mura-statement__margin
          span.text-caption.text-medium-emphasis {{ t('finance.netMargin') }}
          strong.text-h6(:class="Number(data.margins.net) < 0 ? 'text-error' : 'text-success'") {{ data.margins.net }}%

    .mura-statement__scroll
      table.mura-statement__table
        thead
          tr
            th {{ t('admin.description') }}
            th.text-end {{ t('admin.amount') }}
            th.text-end
              abbr(:title="t('finance.statementHint')") {{ t('finance.vertical') }}
            th.text-end(v-if="data.comparison")
              abbr(:title="t('finance.statementHint')") {{ t('finance.horizontal') }}
        tbody
          tr(
            v-for="line in data.lines"
            :key="line.key"
            :class="`mura-statement__row--${line.level}`"
          )
            td {{ label(line) }}
            td.text-end.mura-price {{ money.format(line.amount) }}
            td.text-end.text-medium-emphasis {{ line.vertical }}%
            td.text-end(v-if="data.comparison")
              span(
                v-if="line.horizontal !== null"
                :class="trendClass(line)"
              ) {{ Number(line.horizontal) > 0 ? '+' : '' }}{{ line.horizontal }}%
              span.text-medium-emphasis(v-else) —
</template>

<script setup lang="ts">
/**
 * The DRE, in the shape a Brazilian accountant reads.
 *
 * Two columns beyond the amounts, because a column of money tells a shopkeeper
 * very little on its own:
 *
 * * **AV** (análise vertical) — the line as a percentage of net revenue. This
 *   is what makes "R$ 6.500 of rent" comparable between a good month and a bad
 *   one.
 * * **AH** (análise horizontal) — the change against the previous period of the
 *   same length. Equal length matters; comparing 31 days against 28 makes
 *   February look like a collapse every year.
 *
 * Whether a change is *good* depends on the line. Expenses rising is bad;
 * revenue rising is good; and the arithmetic sign is identical for both. So the
 * colour comes from the row's meaning, not from the number.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMoney } from '~/composables/useMoney'

interface StatementLineRow {
  key: string
  label: string
  amount: string
  level: 'item' | 'subtotal' | 'total'
  vertical: string
  horizontal: string | null
}

interface Statement {
  period: { start: string, end: string }
  comparison: { start: string, end: string } | null
  lines: StatementLineRow[]
  margins: { gross: string, operating: string, net: string }
  expenses_recorded: boolean
}

const { t, te } = useI18n()
const money = useMoney()

const period = ref('last_30')

const periodOptions = computed(() => [
  { value: 'last_7', label: t('admin.periods.last_7') },
  { value: 'last_30', label: t('admin.periods.last_30') },
  { value: 'month', label: t('admin.periods.month') },
  { value: 'previous_month', label: t('admin.periods.previous_month') },
])

const { data, pending, error, refresh } = await useAsyncData<Statement>(
  'admin-finance-statement',
  () => useNuxtApp().$api.get<Statement>('/admin/finance/statement/', {
    query: { period: period.value },
  }),
  { watch: [period] },
)

/**
 * Translate where we can, fall back to the server's label.
 *
 * The API ships a Portuguese label so the payload is readable on its own, but
 * this dashboard runs in three languages — so the key wins when a translation
 * exists.
 */
function label(line: StatementLineRow): string {
  const key = `finance.dre.${line.key}`
  return te(key) ? t(key) : line.label
}

/**
 * Green for better, red for worse — judged per line, not per sign.
 *
 * Revenue lines and result lines improve as they rise. Cost lines improve as
 * they fall. Colouring by the sign alone would paint a month where costs rose
 * 40% in reassuring green.
 */
const RISING_IS_GOOD = new Set([
  'gross_revenue',
  'sales',
  'other_revenue',
  'net_revenue',
  'gross_profit',
  'operating_result',
  'net_result',
])

function trendClass(line: StatementLineRow): string {
  const change = Number(line.horizontal)
  if (!change) return 'text-medium-emphasis'

  const good = RISING_IS_GOOD.has(line.key) ? change > 0 : change < 0
  return good ? 'text-success' : 'text-error'
}
</script>

<style scoped>
.mura-statement__period {
  max-width: 200px;
}

/* Four columns of numbers do not fit a phone; the table scrolls inside its own
   box rather than pushing the page sideways. */
.mura-statement__scroll {
  overflow-x: auto;
}

.mura-statement__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.mura-statement__table th {
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

.mura-statement__table td {
  padding: 8px 12px;
  border-bottom: 1px solid rgba(var(--v-border-color), 0.4);
  white-space: nowrap;
}

/* A statement is read by its subtotals; the detail between them is support. */
.mura-statement__row--item td:first-child {
  padding-inline-start: 28px;
  color: rgb(var(--v-theme-on-surface-variant));
}

.mura-statement__row--subtotal td {
  background: rgba(var(--v-theme-on-surface), 0.03);
  font-weight: 600;
}

.mura-statement__row--total td {
  border-top: 1px solid rgba(var(--v-border-color), 0.9);
  background: rgba(var(--v-theme-primary), 0.06);
  font-size: 0.95rem;
  font-weight: 700;
}

.mura-statement__margin {
  display: flex;
  flex-direction: column;
  padding: 12px 16px;
  border: 1px solid rgba(var(--v-border-color), 0.6);
  border-radius: var(--mura-radius-md, 10px);
  gap: 2px;
}
</style>
