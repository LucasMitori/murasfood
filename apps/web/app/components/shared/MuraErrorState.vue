<template lang="pug">
.text-center.py-12(role="alert")
  v-icon.mb-4(icon="mdi-alert-circle-outline" size="56" color="error")
  h3.text-h6.mb-2 {{ title || t('states.errorTitle') }}
  p.text-body-2.text-medium-emphasis.mx-auto(style="max-width: 42ch") {{ description || t('states.errorDescription') }}
  v-btn.mt-6(
    v-if="onRetry"
    color="primary"
    variant="tonal"
    prepend-icon="mdi-refresh"
    @click="onRetry"
  ) {{ t('common.retry') }}
</template>

<script setup lang="ts">
/**
 * Failure state with a retry affordance.
 *
 * Shows a translated message, never a raw backend exception.
 */
import { useI18n } from 'vue-i18n'

defineProps<{
  title?: string
  description?: string
  onRetry?: () => void
}>()

const { t } = useI18n()
</script>
