<template lang="pug">
div
  mura-page-header(
    :title="t('admin.inventory')"
    :subtitle="t('admin.inventorySubtitle')"
    :breadcrumbs="[{ title: 'admin.dashboard', to: '/admin' }, { title: 'admin.inventory' }]"
  )

  mura-data-table(
    :table="table"
    :columns="columns"
    :actions="rowActions"
    :title="t('admin.inventory')"
    searchable
    @action="onAction"
  )
    template(#filters)
      v-switch.mura-admin-filter(
        v-model="lowStockOnly"
        :label="t('admin.lowStockOnly')"
        color="primary"
        density="compact"
        hide-details
        @update:model-value="table.applyFilters()"
      )

    template(#item.product_name="{ item }")
      div
        p.text-body-2.mb-0 {{ item.product_name }}
        p.text-caption.text-medium-emphasis.mb-0 {{ item.product_sku }}

    template(#item.available_quantity="{ item }")
      v-chip(:color="levelColor(item)" size="x-small" variant="tonal") {{ money.quantity(String(item.available_quantity), String(item.unit || '')) }}

  mura-dialog(
    v-model="adjustOpen"
    :title="t('admin.adjust')"
    icon="mdi-scale-balance"
    :max-width="460"
  )
    p.text-body-2.text-medium-emphasis.mb-3(v-if="adjusting") {{ adjusting.product_name }}

    //- Two genuinely different operations, not two spellings of one. A count
    //- replaces the balance with what is on the shelf; an adjustment records a
    //- movement of a known size. Collapsing them would make the ledger lie
    //- about which of the two happened.
    v-btn-toggle.mb-4(v-model="mode" mandatory divided density="comfortable" variant="outlined")
      v-btn(value="count" prepend-icon="mdi-clipboard-list-outline") {{ t('admin.stockCount') }}
      v-btn(value="delta" prepend-icon="mdi-plus-minus-variant") {{ t('admin.stockDelta') }}

    v-text-field.mb-3(
      v-model="quantityInput"
      :label="mode === 'count' ? t('admin.countedQuantity') : t('admin.quantityDelta')"
      :hint="mode === 'count' ? t('admin.countedQuantityHint') : t('admin.quantityDeltaHint')"
      :suffix="adjusting?.unit"
      type="number"
      variant="outlined"
      density="comfortable"
      persistent-hint
      autofocus
    )

    v-select.mb-3(
      v-if="mode === 'delta'"
      v-model="movementType"
      :items="movementTypes"
      :label="t('admin.movementType')"
      item-title="label"
      item-value="value"
      variant="outlined"
      density="comfortable"
      hide-details
    )

    v-text-field(
      v-model="note"
      :label="t('admin.adjustReason')"
      variant="outlined"
      density="comfortable"
      hide-details
    )

    template(#actions)
      v-btn(variant="text" @click="adjustOpen = false") {{ t('common.cancel') }}
      v-btn(color="primary" variant="flat" :loading="saving" @click="submitAdjust") {{ t('common.save') }}
</template>

<script setup lang="ts">
/**
 * Stock levels.
 *
 * Corrections go through `inventory/adjust/`, which writes a movement rather
 * than overwriting a number. Stock is a ledger in this system — the balance is
 * derived from movements — so an edit that set the quantity directly would
 * leave a balance nothing accounts for.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { TableAction, TableColumn } from '~/types/ui'
import { useServerTable } from '~/composables/useServerTable'
import { useMoney } from '~/composables/useMoney'
import { useUiStore } from '~/stores/ui'
import { useApiError } from '~/composables/useApiError'

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
  [key: string]: unknown
}

const { t } = useI18n()
const money = useMoney()
const ui = useUiStore()
const { messageFor } = useApiError()

useSeoMeta({ title: () => t('admin.inventory') })

const lowStockOnly = ref(false)
const adjustOpen = ref(false)
const adjusting = ref<StockRow | null>(null)
const mode = ref<'count' | 'delta'>('count')
const quantityInput = ref('')
const movementType = ref('ADJUSTMENT')
const note = ref('')
const saving = ref(false)

const movementTypes = computed(() =>
  ['ADJUSTMENT', 'PURCHASE', 'RETURN', 'LOSS', 'EXPIRATION'].map(value => ({
    value,
    label: t(`admin.movementTypes.${value}`, value),
  })),
)

const table = useServerTable<StockRow>({
  endpoint: '/admin/inventory/',
  defaultSort: [{ key: 'product_name', order: 'asc' }],
  sortMap: { product_name: 'product__name', available_quantity: 'quantity' },
  filters: () => ({ low_stock: lowStockOnly.value || undefined }),
  searchParam: 'search',
})

const columns: TableColumn<StockRow>[] = [
  { key: 'product_name', title: 'admin.productName', sortable: true },
  { key: 'quantity', title: 'admin.onHand', sortable: true, align: 'end', hideBelow: 'md' },
  { key: 'reserved_quantity', title: 'admin.reserved', sortable: false, align: 'end', hideBelow: 'lg' },
  { key: 'available_quantity', title: 'admin.available', sortable: true, align: 'end' },
  { key: 'minimum_stock', title: 'admin.reorderPoint', sortable: false, align: 'end', hideBelow: 'lg' },
]

const rowActions: TableAction<StockRow>[] = [
  { key: 'adjust', label: 'admin.adjust', icon: 'mdi-scale-balance', permission: 'inventory.adjust' },
]

const minimumOf = computed(() => (row: StockRow) => Number(row.minimum_stock ?? 0))

function levelColor(row: StockRow): string {
  const available = Number(row.available_quantity ?? 0)
  if (available <= 0) return 'error'
  if (available <= minimumOf.value(row)) return 'warning'
  return 'success'
}

function onAction(payload: { key: string, row: StockRow }): void {
  if (payload.key !== 'adjust') return

  adjusting.value = payload.row
  mode.value = 'count'
  quantityInput.value = String(payload.row.quantity ?? '')
  movementType.value = 'ADJUSTMENT'
  note.value = ''
  adjustOpen.value = true
}

async function submitAdjust(): Promise<void> {
  if (!adjusting.value) return

  saving.value = true
  try {
    const api = useNuxtApp().$api
    if (mode.value === 'count') {
      await api.post('/admin/inventory/count/', {
        product: adjusting.value.product,
        quantity: quantityInput.value,
        note: note.value,
      })
    }
    else {
      await api.post('/admin/inventory/adjust/', {
        product: adjusting.value.product,
        quantity_delta: quantityInput.value,
        movement_type: movementType.value,
        note: note.value,
      })
    }
    adjustOpen.value = false
    await table.refresh()
    ui.success(t('admin.stockAdjusted'))
  }
  catch (error) {
    ui.error(messageFor(error))
  }
  finally {
    saving.value = false
  }
}
</script>
