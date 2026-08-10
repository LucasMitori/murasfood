<template lang="pug">
div
  span.text-body-2.d-block.mb-1(v-if="label") {{ label }}

  v-card.mura-upload(
    v-if="!modelValue"
    :class="{ 'mura-upload--over': dragging, 'mura-upload--error': errorMessages.length > 0 }"
    variant="outlined"
    :disabled="disabled"
    @click="pick"
    @dragover.prevent="dragging = true"
    @dragleave.prevent="dragging = false"
    @drop.prevent="onDrop"
  )
    .d-flex.flex-column.align-center.justify-center.text-center.pa-6.ga-2
      v-progress-circular(v-if="uploading" indeterminate color="primary" size="28")
      v-icon(v-else :icon="icon" size="32" color="on-surface-variant")
      p.text-body-2.mb-0 {{ uploading ? t('form.uploading') : t('form.dropFile') }}
      p.text-caption.text-medium-emphasis.mb-0(v-if="maxSizeLabel") {{ maxSizeLabel }}

  v-card.pa-3(v-else variant="outlined")
    .d-flex.align-center.ga-3
      v-icon(:icon="icon" color="primary")
      .flex-grow-1.min-width-0
        p.text-body-2.mb-0.text-truncate {{ fileName }}
        p.text-caption.text-medium-emphasis.mb-0(v-if="fileSize") {{ fileSize }}
      v-btn(
        :aria-label="t('form.removeFile')"
        icon="mdi-close"
        variant="text"
        size="small"
        :disabled="disabled"
        @click="clear"
      )

  .text-caption.text-error.mt-1(v-for="message in errorMessages" :key="message" role="alert") {{ message }}

  input.d-none(
    ref="inputRef"
    type="file"
    :accept="accept"
    @change="onSelect"
  )
</template>

<script setup lang="ts">
/**
 * File upload backed by the media API.
 *
 * Uploads immediately and stores the returned **asset id** as its value, so a
 * form submits an id rather than binary data. Validation is repeated on the
 * server, which checks the file's actual signature rather than trusting its
 * extension (spec §88).
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { MediaAsset } from '~/types/api'
import { useApiError } from '~/composables/useApiError'

const props = withDefaults(defineProps<{
  /** The uploaded asset id, or `null`. */
  modelValue?: string | null
  label?: string
  accept?: string
  folder?: string
  icon?: string
  maxSizeBytes?: number
  disabled?: boolean
  errorMessages?: string[]
}>(), {
  modelValue: null,
  label: '',
  accept: 'application/pdf',
  folder: 'documents',
  icon: 'mdi-file-document-outline',
  maxSizeBytes: 10 * 1024 * 1024,
  disabled: false,
  errorMessages: () => [],
})

const emit = defineEmits<{
  'update:modelValue': [value: string | null]
  uploaded: [asset: MediaAsset]
}>()

const { t } = useI18n()
const { messageFor } = useApiError()

const inputRef = ref<HTMLInputElement | null>(null)
const dragging = ref(false)
const uploading = ref(false)
const localError = ref('')
const asset = ref<MediaAsset | null>(null)

const errorMessages = computed(() =>
  localError.value ? [...props.errorMessages, localError.value] : props.errorMessages,
)

const fileName = computed(() => asset.value?.original_filename ?? String(props.modelValue ?? ''))
const fileSize = computed(() =>
  asset.value?.size_bytes ? formatBytes(asset.value.size_bytes) : '',
)
const maxSizeLabel = computed(() =>
  props.maxSizeBytes ? t('form.maxFileSize', { size: formatBytes(props.maxSizeBytes) }) : '',
)

function pick(): void {
  if (!props.disabled && !uploading.value) inputRef.value?.click()
}

function onSelect(event: Event): void {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) void upload(file)
}

function onDrop(event: DragEvent): void {
  dragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file && !props.disabled) void upload(file)
}

async function upload(file: File): Promise<void> {
  localError.value = ''

  // Checked here for a fast answer; the API enforces the real limit.
  if (props.maxSizeBytes && file.size > props.maxSizeBytes) {
    localError.value = t('form.maxFileSize', { size: formatBytes(props.maxSizeBytes) })
    return
  }

  uploading.value = true
  try {
    const body = new FormData()
    body.append('file', file)
    body.append('folder', props.folder)

    const uploaded = await useNuxtApp().$api.post<MediaAsset>('/media/upload/', body)
    asset.value = uploaded
    emit('update:modelValue', uploaded.id)
    emit('uploaded', uploaded)
  }
  catch (error) {
    localError.value = messageFor(error)
  }
  finally {
    uploading.value = false
    if (inputRef.value) inputRef.value.value = ''
  }
}

function clear(): void {
  asset.value = null
  localError.value = ''
  emit('update:modelValue', null)
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
</script>

<style scoped>
.mura-upload {
  cursor: pointer;
  border-style: dashed;
  transition: border-color var(--mura-transition), background-color var(--mura-transition);
}

.mura-upload--over {
  border-color: rgb(var(--v-theme-primary));
  background-color: rgb(var(--v-theme-surface-variant));
}

.mura-upload--error {
  border-color: rgb(var(--v-theme-error));
}

.min-width-0 {
  min-width: 0;
}
</style>
