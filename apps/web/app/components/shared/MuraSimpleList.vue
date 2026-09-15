<template lang="pug">
div
  mura-empty-state(
    v-if="!items.length"
    :title="emptyTitle"
    :icon="icon"
  )

  .mura-simple-list(v-else)
    article.mura-simple-row(v-for="item in items" :key="item.id")
      span.mura-simple-row__swatch(
        v-if="item.color"
        :style="{ background: item.color }"
        :aria-hidden="true"
      )
      v-icon(v-else :icon="icon" size="18" color="on-surface-variant")

      span.mura-simple-row__name {{ item.name }}

      v-chip(v-if="item.kind" size="x-small" variant="tonal") {{ item.kind }}
      v-chip(
        v-if="item.is_active === false"
        size="x-small"
        variant="tonal"
        color="secondary"
      ) {{ t('admin.inactive') }}

      v-spacer

      template(v-if="!readonly")
        v-btn(
          icon="mdi-pencil-outline"
          variant="text"
          size="small"
          density="comfortable"
          :aria-label="t('common.edit')"
          @click="emit('edit', item)"
        )
        v-btn(
          icon="mdi-delete-outline"
          variant="text"
          size="small"
          density="comfortable"
          color="error"
          :aria-label="t('common.delete')"
          @click="emit('delete', item)"
        )
</template>

<script setup lang="ts">
/**
 * A flat list of named things, with edit and delete.
 *
 * Brands, tags and the chart of accounts are the same shape and the same three
 * interactions, so they share one renderer rather than three near-identical
 * blocks that drift apart the first time one of them gets a tweak.
 *
 * `readonly` exists for the chart of accounts: renaming a finance category
 * retroactively changes what every past ledger entry means, so it is shown here
 * for reference and edited where that consequence is visible.
 */
import { useI18n } from 'vue-i18n'

export interface SimpleListItem {
  id: string
  name: string
  color?: string
  kind?: string
  is_active?: boolean
}

withDefaults(defineProps<{
  items: SimpleListItem[]
  emptyTitle: string
  icon?: string
  readonly?: boolean
}>(), {
  icon: 'mdi-label-outline',
  readonly: false,
})

const emit = defineEmits<{
  edit: [item: SimpleListItem]
  delete: [item: SimpleListItem]
}>()

const { t } = useI18n()
</script>

<style scoped>
.mura-simple-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.mura-simple-row {
  display: flex;
  align-items: center;
  padding: 10px 14px;
  border: 1px solid rgba(var(--v-border-color), 0.5);
  border-radius: 10px;
  background: rgb(var(--v-theme-surface));
  gap: 10px;
  transition: border-color 140ms ease;
}

.mura-simple-row:hover {
  border-color: rgba(var(--v-theme-primary), 0.4);
}

.mura-simple-row__swatch {
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
  border: 1px solid rgba(var(--v-border-color), 0.9);
  border-radius: 5px;
}

.mura-simple-row__name {
  font-size: 0.875rem;
  font-weight: 500;
}

@media (prefers-reduced-motion: reduce) {
  .mura-simple-row {
    transition: none;
  }
}
</style>
