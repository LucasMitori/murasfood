<template lang="pug">
v-row(dense)
  v-col(cols="12" md="6")
    v-card.mura-transfer(variant="outlined")
      .d-flex.align-center.ga-2.pa-3.pb-2
        v-icon(icon="mdi-tray-arrow-down" size="small" color="on-surface-variant")
        span.text-subtitle-2 {{ availableLabel }}
        v-chip.ml-1(size="x-small" variant="tonal") {{ availableItems.length }}
        v-spacer
        mura-button(
          v-if="availableItems.length"
          :label="t('transfer.addAll')"
          variant="text"
          size="small"
          :disabled="disabled"
          @click="addAll"
        )

      v-text-field.px-3.mura-transfer__search(
        v-model="availableSearch"
        :placeholder="t('table.searchPlaceholder')"
        :aria-label="t('common.search')"
        prepend-inner-icon="mdi-magnify"
        density="compact"
        variant="outlined"
        hide-details
        clearable
      )

      v-divider.mt-3

      draggable.mura-transfer__list(
        :list="availableItems"
        :group="groupName"
        :disabled="disabled"
        item-key="value"
        :aria-label="availableLabel"
        role="listbox"
        @change="onAvailableChange"
      )
        template(#item="{ element }")
          .mura-transfer__item(
            :key="element.value"
            tabindex="0"
            role="option"
            :aria-selected="false"
            @dblclick="assign(element)"
            @keydown.enter.prevent="assign(element)"
            @keydown.space.prevent="assign(element)"
          )
            .min-width-0
              p.text-body-2.mb-0.text-truncate {{ element.label }}
              p.text-caption.text-medium-emphasis.mb-0.text-truncate(v-if="element.description") {{ element.description }}
            v-btn(
              :aria-label="`${t('transfer.add')}: ${element.label}`"
              icon="mdi-chevron-right"
              variant="text"
              size="x-small"
              :disabled="disabled"
              @click.stop="assign(element)"
            )

      .pa-6.text-center(v-if="!availableItems.length")
        p.text-caption.text-medium-emphasis.mb-0 {{ t('transfer.allAssigned') }}

  v-col(cols="12" md="6")
    v-card.mura-transfer.mura-transfer--assigned(variant="outlined")
      .d-flex.align-center.ga-2.pa-3.pb-2
        v-icon(icon="mdi-check-circle-outline" size="small" color="primary")
        span.text-subtitle-2 {{ assignedLabel }}
        v-chip.ml-1(size="x-small" color="primary" variant="tonal") {{ assignedItems.length }}
        v-spacer
        mura-button(
          v-if="assignedItems.length"
          :label="t('transfer.removeAll')"
          variant="text"
          size="small"
          :disabled="disabled"
          @click="removeAll"
        )

      v-text-field.px-3.mura-transfer__search(
        v-model="assignedSearch"
        :placeholder="t('table.searchPlaceholder')"
        :aria-label="t('common.search')"
        prepend-inner-icon="mdi-magnify"
        density="compact"
        variant="outlined"
        hide-details
        clearable
      )

      v-divider.mt-3

      draggable.mura-transfer__list(
        :list="assignedItems"
        :group="groupName"
        :disabled="disabled"
        item-key="value"
        :aria-label="assignedLabel"
        role="listbox"
        @change="onAssignedChange"
      )
        template(#item="{ element }")
          .mura-transfer__item(
            :key="element.value"
            tabindex="0"
            role="option"
            :aria-selected="true"
            @dblclick="unassign(element)"
            @keydown.enter.prevent="unassign(element)"
            @keydown.space.prevent="unassign(element)"
          )
            v-btn(
              :aria-label="`${t('transfer.remove')}: ${element.label}`"
              icon="mdi-chevron-left"
              variant="text"
              size="x-small"
              :disabled="disabled || element.locked"
              @click.stop="unassign(element)"
            )
            .min-width-0.flex-grow-1
              p.text-body-2.mb-0.text-truncate {{ element.label }}
              p.text-caption.text-medium-emphasis.mb-0.text-truncate(v-if="element.description") {{ element.description }}
            v-chip(
              v-if="element.locked"
              size="x-small"
              variant="tonal"
              :title="t('transfer.inheritedHint')"
            ) {{ t('transfer.inherited') }}

      .pa-6.text-center(v-if="!assignedItems.length")
        p.text-caption.text-medium-emphasis.mb-0 {{ t('transfer.noneAssigned') }}
</template>

<script setup lang="ts">
/**
 * Two-list transfer control with drag and drop.
 *
 * Items move between "available" and "assigned" by dragging, by double-click,
 * or with Enter/Space when focused. The keyboard paths are not decoration:
 * a drag-only control is unusable without a mouse, and this one assigns
 * permissions (spec §57).
 *
 * `locked` items render in the assigned column but cannot be removed — used for
 * permissions a user inherits from a role, which this control does not own.
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import draggable from 'vuedraggable'

export interface TransferItem {
  value: string
  label: string
  description?: string
  /** Shown as assigned but not removable here (inherited from elsewhere). */
  locked?: boolean
}

interface DraggableChange {
  added?: { element: TransferItem }
  removed?: { element: TransferItem }
}

const props = withDefaults(defineProps<{
  /** Every item that could be assigned. */
  options: TransferItem[]
  /** Currently assigned values, `v-model`. */
  modelValue: string[]
  /** Assigned but not removable here, e.g. inherited from a role. */
  lockedValues?: string[]
  availableLabel?: string
  assignedLabel?: string
  disabled?: boolean
  /** Distinguishes drag groups when several transfer lists share a page. */
  group?: string
}>(), {
  lockedValues: () => [],
  availableLabel: '',
  assignedLabel: '',
  disabled: false,
  group: 'transfer',
})

const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()

const { t } = useI18n()

const availableSearch = ref('')
const assignedSearch = ref('')

const groupName = computed(() => props.group)

const availableLabel = computed(() => props.availableLabel || t('transfer.available'))
const assignedLabel = computed(() => props.assignedLabel || t('transfer.assigned'))

const lockedSet = computed(() => new Set(props.lockedValues))
const assignedSet = computed(() => new Set(props.modelValue))

/**
 * Local copies, because vuedraggable mutates the arrays it is given.
 *
 * Handing it a computed would mean fighting it for control of the source of
 * truth; instead it edits these and `@change` reports the intent back up.
 */
const availableItems = ref<TransferItem[]>([])
const assignedItems = ref<TransferItem[]>([])

function matches(item: TransferItem, term: string): boolean {
  if (!term) return true
  const needle = term.toLowerCase()
  return (
    item.label.toLowerCase().includes(needle)
    || item.value.toLowerCase().includes(needle)
    || (item.description ?? '').toLowerCase().includes(needle)
  )
}

/** Rebuild both columns from the props. */
function sync(): void {
  const assigned: TransferItem[] = []
  const available: TransferItem[] = []

  for (const option of props.options) {
    const isLocked = lockedSet.value.has(option.value)
    const isAssigned = assignedSet.value.has(option.value) || isLocked

    if (isAssigned) assigned.push({ ...option, locked: isLocked })
    else available.push(option)
  }

  availableItems.value = available.filter(item => matches(item, availableSearch.value))
  assignedItems.value = assigned.filter(item => matches(item, assignedSearch.value))
}

watch(
  [() => props.options, () => props.modelValue, () => props.lockedValues, availableSearch, assignedSearch],
  sync,
  { immediate: true, deep: true },
)

function commit(values: string[]): void {
  // Locked values are inherited, never part of what this control owns.
  emit('update:modelValue', [...new Set(values)].filter(value => !lockedSet.value.has(value)))
}

function assign(item: TransferItem): void {
  if (props.disabled) return
  commit([...props.modelValue, item.value])
}

function unassign(item: TransferItem): void {
  if (props.disabled || item.locked) return
  commit(props.modelValue.filter(value => value !== item.value))
}

function addAll(): void {
  if (props.disabled) return
  commit([...props.modelValue, ...availableItems.value.map(item => item.value)])
}

function removeAll(): void {
  if (props.disabled) return
  const removable = new Set(
    assignedItems.value.filter(item => !item.locked).map(item => item.value),
  )
  commit(props.modelValue.filter(value => !removable.has(value)))
}

/** An item dropped into the assigned column. */
function onAvailableChange(event: DraggableChange): void {
  if (event.removed) assign(event.removed.element)
}

/** An item dropped back into the available column. */
function onAssignedChange(event: DraggableChange): void {
  if (event.added) assign(event.added.element)
  if (event.removed) unassign(event.removed.element)
}
</script>

<style scoped>
.mura-transfer {
  display: flex;
  flex-direction: column;
  height: 420px;
}

.mura-transfer--assigned {
  border-color: rgb(var(--v-theme-primary));
}

/* Vuetify gives `.v-input` `flex: 1 1 auto`. Inside this fixed-height flex
   column that made the search box grow to swallow the free space, so the list
   underneath collapsed towards its 80px minimum and the permissions were
   barely visible. The field should take the height it needs and no more. */
.mura-transfer__search {
  flex: 0 0 auto;
}

.mura-transfer__list {
  flex: 1;
  overflow-y: auto;
  padding: 4px;
  min-height: 80px;
}

.mura-transfer__item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: var(--mura-radius-sm);
  cursor: grab;
  transition: background-color var(--mura-transition);
}

.mura-transfer__item:hover,
.mura-transfer__item:focus-visible {
  background-color: rgb(var(--v-theme-surface-variant));
}

.mura-transfer__item:active {
  cursor: grabbing;
}

.min-width-0 {
  min-width: 0;
}
</style>
