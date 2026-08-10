<template lang="pug">
v-snackbar(
  v-model="visible"
  :color="current?.level"
  :timeout="current?.timeout ?? 4000"
  location="bottom"
  role="status"
  aria-live="polite"
  @update:model-value="onVisibilityChange"
)
  | {{ current?.message }}
  template(#actions)
    v-btn(variant="text" :aria-label="t('common.close')" @click="dismissCurrent") {{ t('common.close') }}
</template>

<script setup lang="ts">
/**
 * Snackbar queue.
 *
 * One message shows at a time; the rest wait their turn rather than stacking
 * over each other.
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUiStore } from '~/stores/ui'

const ui = useUiStore()
const { t } = useI18n()

const visible = ref(false)
const current = computed(() => ui.currentNotification)

watch(current, (value) => {
  visible.value = Boolean(value)
}, { immediate: true })

function dismissCurrent(): void {
  if (current.value) ui.dismiss(current.value.id)
  visible.value = false
}

function onVisibilityChange(open: boolean): void {
  if (!open) dismissCurrent()
}
</script>
