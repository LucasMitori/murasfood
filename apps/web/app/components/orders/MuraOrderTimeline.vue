<template lang="pug">
v-timeline(side="end" align="start" density="compact" truncate-line="both")
  v-timeline-item(
    v-for="step in steps"
    :key="step.status"
    :dot-color="step.completed ? 'success' : 'surface-variant'"
    :icon="step.completed ? 'mdi-check' : 'mdi-circle-small'"
    :icon-color="step.completed ? 'on-success' : 'on-surface-variant'"
    size="small"
  )
    .d-flex.flex-column
      span.text-body-2(:class="step.completed ? 'font-weight-medium' : 'text-medium-emphasis'") {{ labelFor(step) }}
      span.text-caption.text-medium-emphasis(v-if="step.timestamp") {{ formatDateTime(step.timestamp, locale) }}
      span.text-caption.text-medium-emphasis(v-if="step.reason") {{ step.reason }}
</template>

<script setup lang="ts">
/**
 * Customer-facing order progress.
 *
 * Every step comes from the order's recorded status history — the client never
 * infers what "probably" happened (spec §94). Completion is shown with an icon
 * as well as a colour so it does not depend on colour vision.
 */
import { useI18n } from 'vue-i18n'
import type { OrderTimelineStep } from '~/types/api'
import { formatDateTime } from '~/utils/format'

defineProps<{ steps: OrderTimelineStep[] }>()

const { t, te, locale } = useI18n()

/** The backend sends a translation key; fall back to the status if it is unknown. */
function labelFor(step: OrderTimelineStep): string {
  const key = `order.${step.label_key.replace('order.', '')}`
  if (te(key)) return t(key)
  const statusKey = `order.status_labels.${step.status}`
  return te(statusKey) ? t(statusKey) : step.status
}
</script>
