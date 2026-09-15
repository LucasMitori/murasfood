<template lang="pug">
div
  mura-card(:title="t('finance.budgets')" icon="mdi-wallet-outline")
    template(#actions)
      v-select.mura-budget__picker(
        v-if="budgets.length"
        :model-value="selectedId"
        :items="budgetOptions"
        item-title="label"
        item-value="value"
        density="compact"
        variant="outlined"
        hide-details
        :aria-label="t('finance.budgets')"
        @update:model-value="select"
      )
      v-btn(
        color="primary"
        variant="flat"
        size="small"
        prepend-icon="mdi-plus"
        @click="openCreate"
      ) {{ t('finance.budgetNew') }}

    mura-loading(v-if="pending" skeleton="card")

    mura-empty-state(
      v-else-if="!budgets.length"
      :title="t('finance.budgetEmpty')"
      :description="t('finance.budgetEmptyHint')"
      icon="mdi-wallet-outline"
    )
      template(#action)
        v-btn(color="primary" variant="tonal" @click="openCreate") {{ t('finance.budgetNew') }}

    template(v-else-if="variance")
      v-row.mb-3
        v-col(cols="12" sm="6" md="3")
          .mura-budget__figure
            span.text-caption.text-medium-emphasis {{ t('finance.budgetPlanned') }} · {{ t('admin.revenue') }}
            strong {{ money.format(variance.summary.planned_revenue) }}
        v-col(cols="12" sm="6" md="3")
          .mura-budget__figure
            span.text-caption.text-medium-emphasis {{ t('finance.budgetActual') }} · {{ t('admin.revenue') }}
            strong {{ money.format(variance.summary.actual_revenue) }}
        v-col(cols="12" sm="6" md="3")
          .mura-budget__figure
            span.text-caption.text-medium-emphasis {{ t('finance.budgetPlanned') }} · {{ t('admin.expenses') }}
            strong {{ money.format(variance.summary.planned_expenses) }}
        v-col(cols="12" sm="6" md="3")
          .mura-budget__figure
            span.text-caption.text-medium-emphasis {{ t('finance.budgetActual') }} · {{ t('admin.expenses') }}
            strong(:class="overspent ? 'text-error' : 'text-success'") {{ money.format(variance.summary.actual_expenses) }}

      .mura-budget__scroll
        table.mura-budget__table
          thead
            tr
              th {{ t('admin.category') }}
              th.text-end {{ t('finance.budgetPlanned') }}
              th.text-end {{ t('finance.budgetActual') }}
              th.text-end {{ t('finance.budgetDifference') }}
              th {{ t('finance.budgetUsage') }}
          tbody
            tr(v-for="row in variance.rows" :key="row.category_id")
              td
                .d-flex.align-center.ga-2
                  span {{ row.category }}
                  v-chip(
                    v-if="row.unplanned"
                    size="x-small"
                    color="warning"
                    variant="tonal"
                  ) {{ t('finance.budgetUnplanned') }}
              td.text-end {{ money.format(row.planned) }}
              td.text-end {{ money.format(row.actual) }}
              td.text-end(:class="row.favourable ? 'text-success' : 'text-error'")
                | {{ Number(row.difference) > 0 ? '+' : '' }}{{ money.format(row.difference) }}
              td
                .d-flex.align-center.ga-2
                  v-progress-linear.mura-budget__bar(
                    :model-value="Math.min(Number(row.usage_percentage), 100)"
                    :color="row.favourable ? 'success' : 'error'"
                    height="6"
                    rounded
                  )
                  span.text-caption.text-medium-emphasis.mura-budget__pct {{ row.usage_percentage }}%

      .d-flex.justify-end.mt-4.ga-2
        v-btn(variant="text" size="small" prepend-icon="mdi-content-copy" :loading="copying" @click="copyToNext") {{ t('finance.budgetCopy') }}
        v-btn(variant="tonal" size="small" prepend-icon="mdi-pencil" @click="openEdit") {{ t('common.edit') }}

  //- One dialog for creating and editing: a budget is a small sheet of numbers,
    //- and the merchant is doing the same thing either way.
  mura-dialog(
    v-model="formOpen"
    :title="editing ? t('common.edit') : t('finance.budgetNew')"
    max-width="620"
  )
    v-row
      v-col(cols="6" sm="3")
        v-text-field(
          v-model.number="draft.month"
          :label="t('finance.budgetMonth')"
          type="number"
          min="1"
          max="12"
          density="comfortable"
          variant="outlined"
          :disabled="Boolean(editing)"
          hide-details
        )
      v-col(cols="6" sm="3")
        v-text-field(
          v-model.number="draft.year"
          :label="t('finance.budgetYear')"
          type="number"
          min="2000"
          max="2100"
          density="comfortable"
          variant="outlined"
          :disabled="Boolean(editing)"
          hide-details
        )
      v-col(cols="12" sm="6")
        v-text-field(
          v-model="draft.name"
          :label="t('common.name')"
          density="comfortable"
          variant="outlined"
          hide-details
        )

    v-divider.my-4

    //- Every category, always. A blank line is a category the merchant chose
      //- not to plan, and it still needs to be reachable — the alternative is
      //- an "add a line" flow to say nothing.
    .mura-budget__lines
      .mura-budget__line(v-for="category in categories" :key="category.id")
        span.mura-budget__line-name {{ category.name }}
        v-text-field.mura-budget__line-input(
          v-model="draft.amounts[category.id]"
          type="number"
          min="0"
          step="0.01"
          density="compact"
          variant="outlined"
          hide-details
          prefix="R$"
          :aria-label="category.name"
        )

    template(#actions)
      v-spacer
      v-btn(variant="text" @click="formOpen = false") {{ t('common.cancel') }}
      v-btn(color="primary" variant="flat" :loading="saving" @click="save") {{ t('common.save') }}
</template>

<script setup lang="ts">
/**
 * Plan a month, then watch it go.
 *
 * A budget is the one place in this dashboard where the merchant writes down an
 * *intention* rather than recording a fact. That difference drives two design
 * choices:
 *
 * The whole month is edited as one sheet and saved once. Budgeting is an
 * afternoon's thinking about twelve numbers at once, not twelve separate
 * decisions — and a per-line save would let three of the twelve land and leave
 * a plan nobody intended.
 *
 * Every category is always on screen, including the ones with nothing in them.
 * An empty line is information: it says this shop expects no marketing spend
 * this month. Hiding it behind an "add a line" button would make the plan look
 * complete when it was merely unfinished.
 *
 * Variance colouring never uses the sign alone. Spending less than planned is
 * good; earning less than planned is not, and both are negative numbers.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useApiError } from '~/composables/useApiError'
import { useMoney } from '~/composables/useMoney'
import { useUiStore } from '~/stores/ui'

interface Category { id: string, name: string, kind: string, code: string }

interface BudgetLine { category: string, planned_amount: string }

interface Budget {
  id: string
  name: string
  year: number
  month: number
  lines: BudgetLine[]
}

interface VarianceRow {
  category_id: string
  category: string
  planned: string
  actual: string
  difference: string
  usage_percentage: string
  favourable: boolean
  unplanned: boolean
}

interface Variance {
  rows: VarianceRow[]
  summary: {
    planned_revenue: string
    actual_revenue: string
    planned_expenses: string
    actual_expenses: string
    planned_result: string
    actual_result: string
    expense_usage_percentage: string
  }
}

const { t } = useI18n()
const money = useMoney()
const ui = useUiStore()
const { notify } = useApiError()

const selectedId = ref<string | null>(null)
const formOpen = ref(false)
const editing = ref<string | null>(null)
const saving = ref(false)
const copying = ref(false)

const now = new Date()
const draft = ref<{ year: number, month: number, name: string, amounts: Record<string, string> }>({
  year: now.getFullYear(),
  month: now.getMonth() + 1,
  name: '',
  amounts: {},
})

const { data: categoryData } = await useAsyncData<Category[]>(
  'admin-finance-categories',
  () => useNuxtApp().$api.get<Category[]>('/admin/finance/categories/'),
  { default: () => [] },
)

const categories = computed(() => categoryData.value ?? [])

const { data: budgetData, pending, refresh } = await useAsyncData<{ results: Budget[] }>(
  'admin-finance-budgets',
  () => useNuxtApp().$api.get<{ results: Budget[] }>('/admin/finance/budgets/', {
    query: { page_size: 36 },
  }),
  { default: () => ({ results: [] }) },
)

const budgets = computed(() => budgetData.value?.results ?? [])

// The most recent budget is the one a merchant means when they open the tab.
if (!selectedId.value && budgets.value.length) selectedId.value = budgets.value[0]!.id

const budgetOptions = computed(() =>
  budgets.value.map(budget => ({
    value: budget.id,
    label: budget.name || `${String(budget.month).padStart(2, '0')}/${budget.year}`,
  })),
)

const { data: variance, refresh: refreshVariance } = await useAsyncData<Variance | null>(
  () => `admin-budget-variance-${selectedId.value ?? 'none'}`,
  () => (selectedId.value
    ? useNuxtApp().$api.get<Variance>(`/admin/finance/budgets/${selectedId.value}/variance/`)
    : Promise.resolve(null)),
  { watch: [selectedId] },
)

const overspent = computed(() => {
  const summary = variance.value?.summary
  if (!summary) return false
  return Number(summary.actual_expenses) > Number(summary.planned_expenses)
})

function select(id: string): void {
  selectedId.value = id
}

function openCreate(): void {
  editing.value = null
  draft.value = {
    year: now.getFullYear(),
    month: now.getMonth() + 1,
    name: '',
    amounts: {},
  }
  formOpen.value = true
}

function openEdit(): void {
  const budget = budgets.value.find(row => row.id === selectedId.value)
  if (!budget) return

  editing.value = budget.id
  draft.value = {
    year: budget.year,
    month: budget.month,
    name: budget.name,
    amounts: Object.fromEntries(
      budget.lines.map(line => [line.category, line.planned_amount]),
    ),
  }
  formOpen.value = true
}

async function save(): Promise<void> {
  saving.value = true
  try {
    // Only the lines with a number on them. Sending zeroes for every untouched
    // category would turn "I did not plan this" into "I planned nothing here",
    // and the variance report treats those differently.
    const lines = Object.entries(draft.value.amounts)
      .filter(([, amount]) => amount !== '' && amount !== null && Number(amount) > 0)
      .map(([category, amount]) => ({ category, planned_amount: String(amount) }))

    const payload = {
      year: draft.value.year,
      month: draft.value.month,
      name: draft.value.name,
      lines,
    }

    const saved = editing.value
      ? await useNuxtApp().$api.patch<Budget>(`/admin/finance/budgets/${editing.value}/`, payload)
      : await useNuxtApp().$api.post<Budget>('/admin/finance/budgets/', payload)

    formOpen.value = false
    ui.success(t('finance.budgetSaved'))
    await refresh()
    selectedId.value = saved.id
    await refreshVariance()
  }
  catch (error) {
    notify(error)
  }
  finally {
    saving.value = false
  }
}

async function copyToNext(): Promise<void> {
  if (!selectedId.value) return

  copying.value = true
  try {
    const copy = await useNuxtApp().$api.post<Budget>(
      `/admin/finance/budgets/${selectedId.value}/copy-to-next/`,
    )
    await refresh()
    selectedId.value = copy.id
    ui.success(t('finance.budgetSaved'))
  }
  catch (error) {
    notify(error)
  }
  finally {
    copying.value = false
  }
}
</script>

<style scoped>
.mura-budget__picker {
  max-width: 180px;
}

.mura-budget__figure {
  display: flex;
  flex-direction: column;
  padding: 12px 16px;
  border: 1px solid rgba(var(--v-border-color), 0.6);
  border-radius: var(--mura-radius-md, 10px);
  gap: 2px;
}

.mura-budget__scroll {
  overflow-x: auto;
}

.mura-budget__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.mura-budget__table th {
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

.mura-budget__table td {
  padding: 8px 12px;
  border-bottom: 1px solid rgba(var(--v-border-color), 0.4);
  white-space: nowrap;
}

.mura-budget__bar {
  min-width: 80px;
}

.mura-budget__pct {
  min-width: 52px;
  text-align: end;
}

.mura-budget__lines {
  display: flex;
  max-height: 46vh;
  flex-direction: column;
  padding-inline-end: 4px;
  gap: 8px;
  overflow-y: auto;
}

.mura-budget__line {
  display: flex;
  align-items: center;
  gap: 12px;
}

.mura-budget__line-name {
  flex: 1 1 auto;
  font-size: 0.875rem;
}

.mura-budget__line-input {
  max-width: 180px;
  flex: 0 0 auto;
}
</style>
