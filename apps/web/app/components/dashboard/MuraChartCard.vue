<template lang="pug">
v-card.mura-card.pa-4.h-100(flat)
  .d-flex.align-center.justify-space-between.mb-3
    h3.text-subtitle-1 {{ title }}
    slot(name="actions")

  .d-flex.align-center.justify-center(v-if="loading" style="height: 260px")
    v-progress-circular(indeterminate color="primary")

  .d-flex.flex-column.align-center.justify-center.text-center(
    v-else-if="isEmpty"
    style="height: 260px"
    role="status"
  )
    v-icon.mb-2(icon="mdi-chart-line" size="36" color="on-surface-variant")
    p.text-body-2.text-medium-emphasis.mb-0 {{ t('states.emptyDescription') }}

  .mura-chart(v-else style="height: 260px")
    slot
</template>

<script setup lang="ts">
/**
 * Chart container with the loading, empty and error states every chart needs
 * (spec §96). The chart itself is passed in through the default slot.
 */
import { useI18n } from 'vue-i18n'

withDefaults(defineProps<{
  title: string
  loading?: boolean
  isEmpty?: boolean
}>(), { loading: false, isEmpty: false })

const { t } = useI18n()
</script>
