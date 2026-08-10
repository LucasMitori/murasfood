<template lang="pug">
v-card.mura-card.pa-4.h-100(flat)
  .d-flex.align-start.justify-space-between
    div
      p.text-caption.text-medium-emphasis.mb-1 {{ label }}
      p.text-h5.font-weight-bold.mura-price.mb-1 {{ value }}
      .d-flex.align-center.ga-1(v-if="change !== null && change !== undefined")
        v-icon(:icon="trendIcon" :color="trendColor" size="16")
        span.text-caption(:class="`text-${trendColor}`") {{ formattedChange }}
        span.text-caption.text-medium-emphasis {{ t('admin.vsPrevious') }}
      span.text-caption.text-medium-emphasis(v-else-if="showNoComparison") {{ t('admin.noComparison') }}
    v-avatar(:color="color" variant="tonal" size="44")
      v-icon(:icon="icon")
</template>

<script setup lang="ts">
/**
 * Dashboard metric tile.
 *
 * When there is no previous period to compare against, it says so instead of
 * rendering "0%" — "no baseline" and "no change" are different facts.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = withDefaults(defineProps<{
  label: string
  value: string
  icon?: string
  color?: string
  /** Percentage change versus the previous period, or `null` when unavailable. */
  change?: string | null
  showNoComparison?: boolean
}>(), {
  icon: 'mdi-chart-line',
  color: 'primary',
  change: undefined,
  showNoComparison: false,
})

const { t } = useI18n()

const numericChange = computed(() => Number(props.change ?? 0))
const trendColor = computed(() => (numericChange.value >= 0 ? 'success' : 'error'))
const trendIcon = computed(() => (numericChange.value >= 0 ? 'mdi-trending-up' : 'mdi-trending-down'))

const formattedChange = computed(() => {
  const value = numericChange.value
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`
})
</script>
