<template lang="pug">
div
  mura-page-header(
    :title="t('admin.expiry')"
    :subtitle="t('admin.expirySubtitle')"
    :breadcrumbs="[{ title: 'admin.dashboard', to: '/admin' }, { title: 'admin.inventory', to: '/admin/inventory' }, { title: 'admin.expiry' }]"
  )
    template(#actions)
      v-btn(
        color="primary"
        variant="flat"
        rounded="lg"
        prepend-icon="mdi-plus"
        @click="openCreate"
      ) {{ t('admin.batchNew') }}

  //- The morning summary. Expired first and in error colour because it is the
  //- only one of the two that is losing money right now.
  v-row.mb-2
    v-col(cols="12" sm="6" md="3")
      mura-stat-card(
        :label="t('admin.expiredCount')"
        :value="String(report?.expired_count ?? 0)"
        icon="mdi-alert-octagon-outline"
        color="error"
      )
    v-col(cols="12" sm="6" md="3")
      mura-stat-card(
        :label="t('admin.expiredValue')"
        :value="money.format(report?.expired_value ?? '0')"
        icon="mdi-cash-remove"
        color="error"
      )
    v-col(cols="12" sm="6" md="3")
      mura-stat-card(
        :label="t('admin.expiringCount', { days: windowDays })"
        :value="String(report?.expiring_count ?? 0)"
        icon="mdi-clock-alert-outline"
        color="warning"
      )
    v-col(cols="12" sm="6" md="3")
      mura-stat-card(
        :label="t('admin.expiringValue')"
        :value="money.format(report?.expiring_value ?? '0')"
        icon="mdi-cash-clock"
        color="warning"
      )

  mura-data-table(
    :table="table"
    :columns="columns"
    :actions="rowActions"
    :title="t('admin.batches')"
    :empty-title="t('admin.batchesEmpty')"
    :empty-description="t('admin.batchesEmptyHint')"
    empty-icon="mdi-calendar-check-outline"
    searchable
    @action="onAction"
  )
    template(#filters)
      v-select.mura-admin-filter(
        v-model="view"
        :items="viewOptions"
        :label="t('admin.show')"
        item-title="label"
        item-value="value"
        density="compact"
        hide-details
        @update:model-value="table.applyFilters()"
      )

    template(#item.product_name="{ item }")
      div
        p.text-body-2.mb-0 {{ item.product_name }}
        p.text-caption.text-medium-emphasis.mb-0 {{ item.product_sku }}{{ item.code ? ` · ${item.code}` : '' }}

    //- The number of days left carries the urgency, so the date alone is not
    //- enough — "12/03" means nothing at a glance, "in 2 days" does.
    template(#item.expiry_date="{ item }")
      .d-flex.align-center.ga-2
        v-chip(:color="urgency(item).color" size="x-small" variant="flat") {{ urgency(item).label }}
        span.text-caption.text-medium-emphasis {{ formatDate(item.expiry_date, locale) }}

    template(#item.quantity="{ item }")
      span {{ money.quantity(String(item.quantity), String(item.unit || '')) }}

    template(#item.write_off_value="{ item }")
      span(v-if="item.write_off_value !== null") {{ money.format(String(item.write_off_value)) }}
      span.text-medium-emphasis(v-else) {{ t('common.unknown') }}

  mura-dialog(
    v-model="formOpen"
    :title="editing ? t('admin.batchEdit') : t('admin.batchNew')"
    icon="mdi-calendar-clock"
    :max-width="560"
  )
    mura-form-builder(
      ref="formRef"
      v-model:values="values"
      :schema="schema"
      :card="false"
      :loading="saving"
      hide-actions
      @submit="save"
    )

    template(#actions)
      v-btn(variant="text" @click="formOpen = false") {{ t('common.cancel') }}
      v-btn(color="primary" variant="flat" :loading="saving" @click="formRef?.submit()") {{ t('common.save') }}

  mura-confirm-dialog(
    v-model="confirmingDelete"
    :title="t('admin.batchDelete')"
    :message="t('admin.batchDeleteConfirm')"
    :confirm-label="t('common.delete')"
    :loading="deleting"
    danger
    @confirm="destroy"
  )
</template>

<script setup lang="ts">
/**
 * Shelf life.
 *
 * Stock is tracked as one balance per product, which cannot express that two
 * crates of the same milk bought a week apart go off a week apart. A batch is
 * that missing dimension: a lot, a quantity, and the date it stops being
 * sellable.
 *
 * The two states are kept apart deliberately. What has expired must come off
 * the shelf now; what is about to expire is a pricing decision. Showing them
 * as one list buries the first under the second.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { FormFieldOption, FormSchema, FormValues, TableAction, TableColumn } from '~/types/ui'
import { useServerTable } from '~/composables/useServerTable'
import { useMoney } from '~/composables/useMoney'
import { useApiError } from '~/composables/useApiError'
import { useUiStore } from '~/stores/ui'
import { formatDate } from '~/utils/format'

definePageMeta({ layout: 'admin', middleware: 'merchant', permission: 'perm.admin.inventory' })

interface BatchRow {
  id: string
  product: string
  product_name: string
  product_sku: string
  unit: string
  code: string
  quantity: string
  expiry_date: string
  received_date: string
  supplier: string
  cost_price: string | null
  note: string
  days_remaining: number
  is_expired: boolean
  write_off_value: string | null
  [key: string]: unknown
}

interface ExpiryReport {
  days: number
  expired_count: number
  expired_value: string
  expiring_count: number
  expiring_value: string
}

interface FormHandle {
  applyApiError: (error: unknown) => void
  submit: () => void
}

const { t, locale } = useI18n()
const money = useMoney()
const ui = useUiStore()
const { messageFor } = useApiError()

useSeoMeta({ title: () => t('admin.expiry'), robots: 'noindex' })

const windowDays = 7
const view = ref<'all' | 'expired' | 'soon'>('soon')

const viewOptions = computed(() => [
  { value: 'soon', label: t('admin.expiringSoon', { days: windowDays }) },
  { value: 'expired', label: t('admin.expired') },
  { value: 'all', label: t('admin.showAll') },
])

const { data: report, refresh: refreshReport } = await useAsyncData<ExpiryReport>(
  'admin-expiry-report',
  () => useNuxtApp().$api.get(`/admin/inventory/expiry/?days=${windowDays}`),
)

/**
 * Products to attach a batch to.
 *
 * Loaded once rather than searched per keystroke: a small shop's catalog fits
 * in one response, and a picker that pauses on every character is worse than
 * one that is ready when the dialog opens.
 */
const { data: products } = await useAsyncData<{ results: { id: string, name: string, sku: string }[] }>(
  'admin-expiry-products',
  () => useNuxtApp().$api.get('/admin/products/?page_size=200&ordering=name'),
)

const productOptions = computed<FormFieldOption[]>(() =>
  (products.value?.results ?? []).map(item => ({
    value: item.id,
    label: `${item.name} · ${item.sku}`,
  })),
)

const table = useServerTable<BatchRow>({
  endpoint: '/admin/stock-batches/',
  defaultSort: [{ key: 'expiry_date', order: 'asc' }],
  sortMap: { product_name: 'product__name' },
  filters: () => ({
    // `remaining` on every view: a spent batch is history, not a warning.
    remaining: 'true',
    expired: view.value === 'expired' ? 'true' : undefined,
    expiring_days: view.value === 'soon' ? windowDays : undefined,
  }),
  searchParam: 'search',
})

const columns: TableColumn<BatchRow>[] = [
  { key: 'product_name', title: 'admin.productName', sortable: true },
  { key: 'expiry_date', title: 'admin.expiryDate', sortable: true },
  { key: 'quantity', title: 'admin.available', sortable: false, align: 'end' },
  { key: 'supplier', title: 'admin.supplier', sortable: false, hideBelow: 'lg' },
  { key: 'write_off_value', title: 'admin.writeOffValue', sortable: false, align: 'end', hideBelow: 'md' },
]

const rowActions: TableAction<BatchRow>[] = [
  { key: 'edit', label: 'common.edit', icon: 'mdi-pencil-outline', permission: 'inventory.manage' },
  { key: 'delete', label: 'common.delete', icon: 'mdi-delete-outline', permission: 'inventory.manage', color: 'error' },
]

/**
 * How close to the edge this batch is.
 *
 * Three bands rather than a raw count: an operator scanning a list needs to
 * know which rows to act on today, not to compare 9 days against 11.
 */
function urgency(row: BatchRow): { color: string, label: string } {
  const days = row.days_remaining

  if (days < 0) return { color: 'error', label: t('admin.expiredAgo', { days: Math.abs(days) }) }
  if (days === 0) return { color: 'error', label: t('admin.expiresToday') }
  if (days <= 3) return { color: 'warning', label: t('admin.expiresInDays', { days }) }
  return { color: 'success', label: t('admin.expiresInDays', { days }) }
}

const formOpen = ref(false)
const editing = ref<BatchRow | null>(null)
const saving = ref(false)
const values = ref<FormValues>({})
const formRef = ref<FormHandle | null>(null)

const confirmingDelete = ref(false)
const deleting = ref(false)
const pendingDelete = ref<BatchRow | null>(null)

const schema = computed<FormSchema>(() => ({
  sections: [{
    fields: [
      {
        name: 'product',
        type: 'autocomplete',
        label: 'admin.productName',
        required: true,
        options: productOptions.value,
      },
      { name: 'expiry_date', type: 'date', label: 'admin.expiryDate', required: true, md: 6 },
      { name: 'received_date', type: 'date', label: 'admin.receivedDate', md: 6 },
      { name: 'quantity', type: 'quantity', label: 'admin.available', required: true, md: 6 },
      { name: 'cost_price', type: 'money', label: 'admin.costPrice', md: 6 },
      { name: 'code', type: 'text', label: 'admin.batchCode', md: 6 },
      { name: 'supplier', type: 'text', label: 'admin.supplier', md: 6 },
      { name: 'note', type: 'text', label: 'admin.adjustReason' },
    ],
  }],
}))

function openCreate(): void {
  editing.value = null
  values.value = {
    quantity: '',
    expiry_date: '',
    received_date: new Date().toISOString().slice(0, 10),
  }
  formOpen.value = true
}

function onAction(payload: { key: string, row: BatchRow }): void {
  if (payload.key === 'edit') {
    editing.value = payload.row
    values.value = {
      product: payload.row.product,
      code: payload.row.code,
      quantity: payload.row.quantity,
      expiry_date: payload.row.expiry_date,
      received_date: payload.row.received_date,
      supplier: payload.row.supplier,
      cost_price: payload.row.cost_price ?? '',
      note: payload.row.note,
    }
    formOpen.value = true
    return
  }

  if (payload.key === 'delete') {
    pendingDelete.value = payload.row
    confirmingDelete.value = true
  }
}

async function save(payload: FormValues): Promise<void> {
  saving.value = true
  try {
    const api = useNuxtApp().$api
    if (editing.value) await api.patch(`/admin/stock-batches/${editing.value.id}/`, payload)
    else await api.post('/admin/stock-batches/', payload)

    formOpen.value = false
    await Promise.all([table.refresh(), refreshReport()])
    ui.success(t('admin.batchSaved'))
  }
  catch (error) {
    // Server-side rules — an expiry before the receipt date, say — belong on
    // the field that broke them, not in a toast.
    formRef.value?.applyApiError(error)
  }
  finally {
    saving.value = false
  }
}

async function destroy(): Promise<void> {
  if (!pendingDelete.value) return

  deleting.value = true
  try {
    await useNuxtApp().$api.delete(`/admin/stock-batches/${pendingDelete.value.id}/`)
    await Promise.all([table.refresh(), refreshReport()])
    ui.success(t('admin.batchDeleted'))
  }
  catch (error) {
    ui.error(messageFor(error))
  }
  finally {
    deleting.value = false
    confirmingDelete.value = false
    pendingDelete.value = null
  }
}
</script>
