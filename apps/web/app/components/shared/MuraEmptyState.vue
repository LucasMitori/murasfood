<template lang="pug">
.text-center.py-12(role="status")
  v-icon.mb-4(:icon="icon" size="56" color="on-surface-variant")
  h3.text-h6.mb-2 {{ title }}
  p.text-body-2.text-medium-emphasis.mx-auto(style="max-width: 42ch") {{ description }}
  .mt-6(v-if="$slots.action")
    slot(name="action")
</template>

<script setup lang="ts">
/**
 * The "nothing here" state.
 *
 * Every list in the app has one: an empty page with no explanation reads as a
 * bug (spec §70).
 */
withDefaults(defineProps<{
  title: string
  description?: string
  icon?: string
}>(), {
  description: '',
  icon: 'mdi-package-variant',
})
</script>
