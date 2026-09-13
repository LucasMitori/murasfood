<template lang="pug">
v-card.mura-card(flat)
  //- Toolbar: title, search, custom filters, refresh.
  .d-flex.flex-wrap.align-center.ga-3.pa-4(v-if="title || searchable || $slots.filters || $slots.actions")
    div(v-if="title || subtitle")
      h2.text-subtitle-1.font-weight-medium {{ title }}
      p.text-caption.text-medium-emphasis.mb-0(v-if="subtitle") {{ subtitle }}

    v-spacer

    slot(name="filters")

    v-text-field.mura-data-table__search(
      v-if="searchable"
      :model-value="searchDraft"
      :placeholder="t('table.searchPlaceholder')"
      :aria-label="t('common.search')"
      prepend-inner-icon="mdi-magnify"
      density="compact"
      hide-details
      clearable
      @update:model-value="onSearchInput"
    )

    v-btn(
      :aria-label="t('table.refresh')"
      icon="mdi-refresh"
      variant="text"
      density="comfortable"
      :loading="table.loading.value"
      @click="table.refresh()"
    )

    //- Exports what is on screen, filters and search included, because a
      //- merchant who narrowed to "sem estoque" means that list rather than all
      //- four hundred rows.
    v-menu(v-if="exportable" location="bottom end")
      template(#activator="{ props: menuProps }")
        v-btn(
          v-bind="menuProps"
          :aria-label="t('table.export')"
          icon="mdi-tray-arrow-down"
          variant="text"
          density="comfortable"
          :loading="exporting"
        )
      v-list(density="compact")
        v-list-subheader {{ t('table.export') }}
        v-list-item(prepend-icon="mdi-file-excel-outline" @click="download('xlsx')")
          v-list-item-title Excel (.xlsx)
        v-list-item(prepend-icon="mdi-file-delimited-outline" @click="download('csv')")
          v-list-item-title CSV

    slot(name="actions")

  v-divider

  //- The error state replaces the table entirely: a stale grid under an error
  //- banner invites the reader to trust numbers that failed to refresh.
  mura-error-state(
    v-if="table.error.value"
    :description="errorMessage"
    :on-retry="() => table.refresh()"
  )

  v-data-table-server(
    v-else
    :items="table.items.value"
    :items-length="table.total.value"
    :headers="headers"
    :loading="table.loading.value"
    :page="table.page.value"
    :items-per-page="table.itemsPerPage.value"
    :sort-by="table.sortBy.value"
    :items-per-page-options="itemsPerPageOptions"
    :item-value="itemValue"
    :hover="Boolean(clickable)"
    :density="density"
    :show-select="selectable"
    :model-value="selected"
    :class="['mura-data-table', { 'mura-data-table--sticky-actions': actions.length }]"
    @update:options="table.onOptionsUpdate"
    @update:model-value="value => emit('update:selected', value)"
    @click:row="onRowClick"
  )
    //- Forward every `item.<key>` slot the parent defined, so a caller can
    //- override any cell without this component knowing about it.
    template(v-for="name in passthroughSlots" :key="name" #[name]="slotProps")
      slot(:name="name" v-bind="slotProps")

    //- Default cell rendering for columns the caller did not override.
    template(
      v-for="column in formattedColumns"
      :key="`cell-${column.key}`"
      #[`item.${column.key}`]="{ item }"
    )
      slot(:name="`item.${column.key}`" :item="item" :value="cellValue(column, item)")
        mura-status-badge(v-if="column.format === 'status'" :status="String(cellValue(column, item))" size="x-small")
        v-icon(
          v-else-if="column.format === 'boolean'"
          :icon="cellValue(column, item) ? 'mdi-check-circle' : 'mdi-minus-circle-outline'"
          :color="cellValue(column, item) ? 'success' : 'on-surface-variant'"
          size="small"
        )
        span(v-else :class="{ 'mura-price': isNumericFormat(column) }") {{ renderCell(column, item) }}

    template(v-if="actions.length" #item.__actions="{ item }")
      .d-flex.justify-end.ga-1
        v-btn.mura-data-table__action(
          v-for="action in visibleActionsFor(item)"
          :key="action.key"
          :icon="action.icon"
          :color="action.color"
          :aria-label="t(action.label)"
          :title="t(action.label)"
          variant="text"
          size="small"
          density="comfortable"
          @click.stop="triggerAction(action, item)"
        )

    template(#no-data)
      mura-empty-state(
        :title="emptyTitle || t('table.noData')"
        :description="emptyDescription || t('table.noDataHint')"
        :icon="emptyIcon"
      )
        template(v-if="$slots['empty-action']" #action)
          slot(name="empty-action")

    //- Skeletons only when there is nothing on screen yet.
      //- Overriding this slot replaces the whole body, so on every refresh the
      //- rows vanished and were rebuilt — which read as the table rebooting
      //- itself. With rows already present Vuetify's own progress bar runs
      //- along the top instead and the data stays put until the new page
      //- arrives.
    template(v-if="!table.items.value.length" #loading)
      v-skeleton-loader(type="table-row@5")

    template(#footer.prepend)
      span.text-caption.text-medium-emphasis.ml-4(v-if="table.total.value > 0") {{ rangeLabel }}
      v-spacer

  mura-confirm-dialog(
    v-model="confirmOpen"
    :message="confirmMessage"
    @confirm="runPendingAction"
    @cancel="pendingAction = null"
  )
</template>

<script setup lang="ts">
/**
 * Server-paginated data table.
 *
 * Declare columns and hand it a `useServerTable` instance; the composable owns
 * every pagination hazard (loops, stale responses, vanishing pages) and this
 * component owns presentation.
 *
 * ```ts
 * const table = useServerTable({ endpoint: '/admin/products/' })
 * const columns: TableColumn[] = [
 *   { key: 'name', title: 'admin.products', sortable: true },
 *   { key: 'price', title: 'common.total', format: 'money', align: 'end' },
 * ]
 * ```
 *
 * Any cell can be overridden with an `#item.<key>` slot, exactly as on
 * `v-data-table-server` — the slots are forwarded through.
 */
import { computed, ref, useSlots } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDisplay } from 'vuetify'
import type { TableAction, TableColumn } from '~/types/ui'
import type { useServerTable } from '~/composables/useServerTable'
import { ITEMS_PER_PAGE_OPTIONS } from '~/composables/useServerTable'
import { useAuthStore } from '~/stores/auth'
import { useMoney } from '~/composables/useMoney'
import { formatDate, formatDateTime, saveFile } from '~/utils/format'
import { useUiStore } from '~/stores/ui'

type TableInstance = ReturnType<typeof useServerTable<Record<string, unknown>>>
type Row = Record<string, unknown>

const props = withDefaults(defineProps<{
  /** The `useServerTable` instance backing this table. */
  table: TableInstance
  columns: TableColumn<Row>[]
  actions?: TableAction<Row>[]

  title?: string
  subtitle?: string
  searchable?: boolean
  /** Offer a download of the current view. The endpoint gains `/export/`. */
  exportable?: boolean
  /** Filename stem, before the date. */
  exportName?: string
  clickable?: boolean
  selectable?: boolean
  selected?: unknown[]

  /** Row property used as the selection key. */
  itemValue?: string
  density?: 'default' | 'comfortable' | 'compact'

  emptyTitle?: string
  emptyDescription?: string
  emptyIcon?: string
}>(), {
  actions: () => [],
  title: '',
  subtitle: '',
  searchable: false,
  exportable: false,
  exportName: 'export',
  clickable: false,
  selectable: false,
  selected: () => [],
  itemValue: 'id',
  density: 'comfortable',
  emptyTitle: '',
  emptyDescription: '',
  emptyIcon: 'mdi-table-off',
})

const ui = useUiStore()

const emit = defineEmits<{
  /**
   * One object, not two positional arguments.
   *
   * Every screen consuming this reads `payload.key` and `payload.row`. Emitted
   * as `(key, row)` the handler received the *string* as its only argument, so
   * `payload.key` was `undefined` and not one row action in the dashboard did
   * anything. Pug templates are not type-checked, so nothing caught it.
   */
  action: [payload: { key: string, row: Row }]
  'row-click': [row: Row]
  'update:selected': [value: unknown[]]
}>()

const { t, te, locale } = useI18n()
const slots = useSlots()
const display = useDisplay()
const auth = useAuthStore()
const money = useMoney()

const searchDraft = ref('')
const confirmOpen = ref(false)
const pendingAction = ref<{ action: TableAction<Row>, row: Row } | null>(null)

const itemsPerPageOptions = ITEMS_PER_PAGE_OPTIONS.map(value => ({
  value,
  title: String(value),
}))

/**
 * Columns visible at the current breakpoint.
 *
 * A phone showing twelve columns is unreadable; `hideBelow` lets a schema say
 * which ones are essential.
 */
const visibleColumns = computed(() =>
  props.columns.filter((column) => {
    if (!column.hideBelow) return true
    if (column.hideBelow === 'sm') return display.smAndUp.value
    if (column.hideBelow === 'md') return display.mdAndUp.value
    return display.lgAndUp.value
  }),
)

const headers = computed(() => {
  const mapped = visibleColumns.value.map(column => ({
    key: column.key,
    title: te(column.title) ? t(column.title) : column.title,
    sortable: Boolean(column.sortable),
    align: column.align ?? 'start',
    width: column.width,
    nowrap: column.nowrap,
  }))

  if (props.actions.length) {
    mapped.push({
      key: '__actions',
      title: t('table.actions'),
      sortable: false,
      align: 'end',
      width: 56 * Math.min(props.actions.length, 3),
      nowrap: true,
    })
  }

  return mapped
})

/** Columns this component renders itself (everything but action cells). */
const formattedColumns = computed(() => visibleColumns.value)

/**
 * Slots the caller passed that are not per-cell overrides.
 *
 * Per-cell slots are handled by the default-rendering template, which falls
 * back to the caller's slot when one exists. Forwarding them twice would render
 * the cell twice.
 */
const passthroughSlots = computed(() =>
  Object.keys(slots).filter(
    name =>
      !name.startsWith('item.')
      && !['filters', 'actions', 'empty-action', 'default'].includes(name),
  ),
)

const rangeLabel = computed(() =>
  t('table.showingRange', {
    from: props.table.range.value.from,
    to: props.table.range.value.to,
    total: props.table.total.value,
  }),
)

const errorMessage = computed(() => {
  const code = props.table.error.value
  const key = `errors.${code}`
  return te(key) ? t(key) : t('table.loadError')
})

const confirmMessage = computed(() => {
  const key = pendingAction.value?.action.confirm
  return key ? (te(key) ? t(key) : key) : ''
})

/** Resolve a cell's raw value: an explicit getter, else the row property. */
function cellValue(column: TableColumn<Row>, row: Row): unknown {
  if (column.value) return column.value(row)
  return column.key.split('.').reduce<unknown>(
    (accumulator, part) => (accumulator as Row | undefined)?.[part],
    row,
  )
}

function isNumericFormat(column: TableColumn<Row>): boolean {
  return ['money', 'quantity', 'number', 'percent'].includes(column.format ?? '')
}

/** Format a cell for display according to its declared format. */
function renderCell(column: TableColumn<Row>, row: Row): string {
  const value = cellValue(column, row)
  if (value === null || value === undefined || value === '') return '—'

  switch (column.format) {
    case 'money':
      return money.format(value as string)
    case 'quantity':
      return money.quantity(value as string)
    case 'percent':
      return `${value}%`
    case 'number':
      return new Intl.NumberFormat(locale.value).format(Number(value))
    case 'date':
      return formatDate(String(value), locale.value)
    case 'datetime':
      return formatDateTime(String(value), locale.value)
    default:
      return String(value)
  }
}

/** Actions this user may perform on this row. */
function visibleActionsFor(row: Row): TableAction<Row>[] {
  return props.actions.filter((action) => {
    if (action.permission && !auth.can(action.permission)) return false
    return action.visibleWhen ? action.visibleWhen(row) : true
  })
}

function triggerAction(action: TableAction<Row>, row: Row): void {
  if (action.confirm) {
    pendingAction.value = { action, row }
    confirmOpen.value = true
    return
  }
  emit('action', { key: action.key, row })
}

function runPendingAction(): void {
  const pending = pendingAction.value
  confirmOpen.value = false
  pendingAction.value = null
  if (pending) emit('action', { key: pending.action.key, row: pending.row })
}

function onSearchInput(value: string | null): void {
  searchDraft.value = value ?? ''
  // Debounced inside the composable; page always resets to 1 there.
  props.table.setSearch(searchDraft.value)
}
/**
 * Download the current view.
 *
 * The same endpoint plus `/export/`, with the query the table is showing, so
 * the file matches the screen rather than the whole table. It goes through the
 * API client rather than a link because the export needs the access token, and
 * an `<a href>` cannot carry one.
 */
const exporting = ref(false)

async function download(fmt: 'csv' | 'xlsx'): Promise<void> {
  exporting.value = true
  try {
    const endpoint = `${props.table.resolveEndpoint().replace(/\/$/, '')}/export/`
    const { page: _page, page_size: _size, ...query } = props.table.buildQuery()

    const file = await useNuxtApp().$api.download(endpoint, { query: { ...query, fmt } })
    saveFile(file.blob, file.filename)
  }
  catch {
    ui.error(t('table.exportFailed'))
  }
  finally {
    exporting.value = false
  }
}


function onRowClick(_event: unknown, context: { item: Row }): void {
  if (props.clickable) emit('row-click', context.item)
}
</script>

<style scoped>
.mura-data-table__search {
  max-width: 280px;
}

/*
 * Table surfaces are expressed against theme tokens rather than fixed greys, so
 * the same rules give a soft near-white header on light and a gentle lift out
 * of near-black on dark.
 */
.mura-data-table :deep(th) {
  white-space: nowrap;
  background: rgb(var(--v-theme-surface-variant)) !important;
  color: rgb(var(--v-theme-on-surface-variant)) !important;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.mura-data-table :deep(tbody tr) {
  transition: background-color 140ms ease;
}

.mura-data-table :deep(tbody tr:hover) {
  background: rgba(var(--v-theme-primary), 0.06);
}

.mura-data-table :deep(td) {
  border-bottom: 1px solid rgba(var(--v-border-color), 0.5) !important;
}

/*
 * Row actions stay visible at rest.
 *
 * They were icon-only text buttons, which read as blank space until hovered —
 * the operator had to sweep the row to discover there were controls in it.
 */
.mura-data-table__action {
  background: rgba(var(--v-theme-on-surface), 0.06);
  opacity: 0.9;
  transition: background-color 140ms ease, opacity 140ms ease;
}

.mura-data-table__action:hover {
  background: rgba(var(--v-theme-primary), 0.16);
  opacity: 1;
}

/*
 * Pin the action column to the right edge.
 *
 * A table with more columns than fit scrolls horizontally, and the actions —
 * the controls an operator reaches for most — were the first thing pushed out
 * of sight. Sticky keeps them reachable without shrinking the data columns.
 */
/*
 * `!important` because Vuetify sets `position: relative` on every data-table
 * cell from a selector this cannot outrank without duplicating its internals.
 */
.mura-data-table--sticky-actions :deep(th:last-child),
.mura-data-table--sticky-actions :deep(td:last-child) {
  position: sticky !important;
  right: 0;
  z-index: 2;
}

.mura-data-table--sticky-actions :deep(th:last-child) {
  z-index: 3;
}

.mura-data-table--sticky-actions :deep(td:last-child) {
  background: rgb(var(--v-theme-surface));
  /* Marks the seam where the rest of the row scrolls underneath. */
  box-shadow: -8px 0 12px -10px rgba(var(--v-theme-on-surface), 0.5);
}

.mura-data-table--sticky-actions :deep(tbody tr:hover td:last-child) {
  background: rgb(var(--v-theme-surface-bright));
}

@media (prefers-reduced-motion: reduce) {
  .mura-data-table :deep(tbody tr),
  .mura-data-table__action {
    transition: none;
  }
}

/*
 * Banded rows.
 *
 * Built from the theme's own surface colour rather than fixed greys, so the
 * band is a slight lift in light mode and a slight lift in dark mode too —
 * hard-coded greys would turn the dark table into a light one. Kept under the
 * hover and selected states, which must still be able to show through.
 */
.mura-data-table :deep(tbody tr:nth-child(even) > td) {
  background: rgba(var(--v-theme-on-surface), 0.028);
}

.mura-data-table :deep(tbody tr:hover > td) {
  background: rgba(var(--v-theme-primary), 0.07);
}

.mura-data-table :deep(tbody tr.v-data-table__selected > td) {
  background: rgba(var(--v-theme-primary), 0.12);
}
</style>
