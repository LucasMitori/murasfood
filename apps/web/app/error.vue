<template lang="pug">
v-app
  v-main
    .mura-container.d-flex.flex-column.align-center.justify-center.text-center(style="min-height: 70vh")
      v-icon.mb-4(:icon="icon" size="72" color="primary")
      h1.text-h4.mb-2 {{ title }}
      p.text-body-1.text-medium-emphasis.mb-6(style="max-width: 46ch") {{ description }}
      .d-flex.ga-3
        v-btn(color="primary" variant="flat" @click="goHome") {{ t('nav.home') }}
        v-btn(variant="tonal" @click="reload") {{ t('common.retry') }}
</template>

<script setup lang="ts">
/**
 * Error page.
 *
 * Shows a translated explanation, never the underlying exception — a stack
 * trace is neither useful nor safe for a customer (spec §36).
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { NuxtError } from '#app'

const props = defineProps<{ error: NuxtError }>()
const { t } = useI18n()

const isNotFound = computed(() => props.error?.statusCode === 404)

const icon = computed(() => (isNotFound.value ? 'mdi-map-search-outline' : 'mdi-alert-circle-outline'))
const title = computed(() => t(isNotFound.value ? 'errors.NOT_FOUND' : 'states.errorTitle'))
const description = computed(() =>
  t(isNotFound.value ? 'states.emptyDescription' : 'states.errorDescription'),
)

function goHome(): void {
  clearError({ redirect: '/' })
}

function reload(): void {
  clearError({ redirect: useRoute().fullPath })
}
</script>
