<template lang="pug">
v-skeleton-loader(v-if="skeleton" :type="skeleton" :loading="true")

.d-flex.flex-column.align-center.justify-center.ga-3(
  v-else
  :style="{ minHeight: height }"
  role="status"
  aria-live="polite"
)
  v-progress-circular(indeterminate color="primary" :size="size")
  p.text-body-2.text-medium-emphasis.mb-0(v-if="label !== ''") {{ label || t('common.loading') }}
</template>

<script setup lang="ts">
/**
 * Loading indicator.
 *
 * Pass `skeleton` to show a content-shaped placeholder instead of a spinner —
 * a skeleton that matches the eventual layout reads as faster than a spinner,
 * because nothing jumps when the data lands.
 */
import { useI18n } from 'vue-i18n'

withDefaults(defineProps<{
  /** A Vuetify skeleton type, e.g. `card`, `table-row@5`, `list-item-two-line@3`. */
  skeleton?: string
  /** Explicit label, or an empty string to show the spinner alone. */
  label?: string
  size?: number | string
  height?: string
}>(), {
  skeleton: '',
  label: undefined,
  size: 36,
  height: '160px',
})

const { t } = useI18n()
</script>
