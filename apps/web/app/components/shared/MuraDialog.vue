<template lang="pug">
v-dialog(
  :model-value="modelValue"
  :max-width="maxWidth"
  :fullscreen="fullscreen || mobile"
  :persistent="persistent"
  :scrollable="scrollable"
  role="dialog"
  :aria-label="title"
  @update:model-value="value => emit('update:modelValue', value)"
)
  v-card
    v-card-title.d-flex.align-center.ga-2
      v-icon(v-if="icon" :icon="icon" color="primary")
      span.text-truncate {{ title }}
      v-spacer
      v-btn(
        :aria-label="t('common.close')"
        icon="mdi-close"
        variant="text"
        density="comfortable"
        @click="close"
      )

    v-card-subtitle(v-if="subtitle") {{ subtitle }}

    v-divider

    v-card-text
      slot

    template(v-if="$slots.actions")
      v-divider
      v-card-actions
        v-spacer
        slot(name="actions")
</template>

<script setup lang="ts">
/**
 * Generic modal.
 *
 * Goes fullscreen on phones automatically — a fixed-width dialog on a 375 px
 * screen is a form nobody can complete.
 */
import { useI18n } from 'vue-i18n'
import { useDisplay } from 'vuetify'

withDefaults(defineProps<{
  modelValue: boolean
  title?: string
  subtitle?: string
  icon?: string
  maxWidth?: number | string
  fullscreen?: boolean
  persistent?: boolean
  scrollable?: boolean
}>(), {
  title: '',
  subtitle: '',
  icon: '',
  maxWidth: 720,
  fullscreen: false,
  persistent: false,
  scrollable: true,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  close: []
}>()

const { t } = useI18n()
const { mobile } = useDisplay()

function close(): void {
  emit('update:modelValue', false)
  emit('close')
}
</script>
