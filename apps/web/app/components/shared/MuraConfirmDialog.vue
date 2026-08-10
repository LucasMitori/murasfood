<template lang="pug">
v-dialog(
  :model-value="modelValue"
  :max-width="440"
  persistent
  role="alertdialog"
  @update:model-value="value => emit('update:modelValue', value)"
)
  v-card
    v-card-title.d-flex.align-center.ga-2
      v-icon(:icon="icon" :color="danger ? 'error' : 'primary'")
      span {{ title || t('common.confirm') }}

    v-card-text
      p.mb-0 {{ message }}
      slot

    v-card-actions
      v-spacer
      v-btn(variant="text" :disabled="loading" @click="cancel") {{ cancelLabel || t('common.cancel') }}
      v-btn(
        :color="danger ? 'error' : 'primary'"
        variant="flat"
        :loading="loading"
        @click="confirm"
      ) {{ confirmLabel || t('common.confirm') }}
</template>

<script setup lang="ts">
/**
 * Confirmation dialog for destructive or irreversible actions.
 *
 * `persistent` on purpose: clicking the backdrop should not be able to
 * accidentally answer a question about deleting something.
 */
import { useI18n } from 'vue-i18n'

withDefaults(defineProps<{
  modelValue: boolean
  message?: string
  title?: string
  confirmLabel?: string
  cancelLabel?: string
  icon?: string
  /** Style the confirm button as destructive. */
  danger?: boolean
  loading?: boolean
}>(), {
  message: '',
  title: '',
  confirmLabel: '',
  cancelLabel: '',
  icon: 'mdi-help-circle-outline',
  danger: false,
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: []
  cancel: []
}>()

const { t } = useI18n()

function confirm(): void {
  emit('confirm')
}

function cancel(): void {
  emit('update:modelValue', false)
  emit('cancel')
}
</script>
