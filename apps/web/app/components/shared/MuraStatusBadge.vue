<template lang="pug">
v-chip(
  :color="color"
  :size="size"
  variant="tonal"
  :prepend-icon="icon"
) {{ label }}
</template>

<script setup lang="ts">
/**
 * Order status chip.
 *
 * Carries an icon and a translated label alongside the colour: colour alone is
 * never the only indicator of state (spec §57).
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { orderStatusColor, orderStatusIcon } from '~/utils/format'

const props = withDefaults(defineProps<{
  status: string
  size?: 'x-small' | 'small' | 'default' | 'large'
}>(), { size: 'small' })

const { t, te } = useI18n()

const color = computed(() => orderStatusColor(props.status))
const icon = computed(() => orderStatusIcon(props.status))

const label = computed(() => {
  const key = `order.status_labels.${props.status}`
  return te(key) ? t(key) : props.status
})
</script>
