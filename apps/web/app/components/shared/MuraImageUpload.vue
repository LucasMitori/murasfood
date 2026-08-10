<template lang="pug">
div
  span.text-body-2.d-block.mb-1(v-if="label") {{ label }}

  .d-flex.flex-wrap.ga-3
    v-card.mura-image-upload__item(
      v-for="item in previews"
      :key="item.id"
      variant="outlined"
    )
      v-img(:src="item.url" :alt="item.alt" :aspect-ratio="1" cover)
      v-btn.mura-image-upload__remove(
        :aria-label="t('form.removeFile')"
        icon="mdi-close"
        size="x-small"
        variant="flat"
        color="surface"
        :disabled="disabled"
        @click="remove(item.id)"
      )

    v-card.mura-image-upload__item.mura-image-upload__drop(
      v-if="canAddMore"
      :class="{ 'mura-image-upload__drop--over': dragging }"
      variant="outlined"
      :disabled="disabled"
      @click="pick"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
    )
      .d-flex.flex-column.align-center.justify-center.fill-height.ga-1.pa-2.text-center
        v-progress-circular(v-if="uploading" indeterminate color="primary" size="24")
        v-icon(v-else icon="mdi-image-plus" color="on-surface-variant")
        span.text-caption.text-medium-emphasis {{ uploading ? t('form.uploading') : t('form.selectFile') }}

  .text-caption.text-error.mt-1(v-for="message in allErrors" :key="message" role="alert") {{ message }}

  input.d-none(
    ref="inputRef"
    type="file"
    accept="image/jpeg,image/png,image/webp,image/avif"
    :multiple="multiple"
    @change="onSelect"
  )
</template>

<script setup lang="ts">
/**
 * Image upload with previews.
 *
 * Handles one image or many; the value is an asset id (or an array of them).
 * Derivatives are generated asynchronously by the API, so a freshly uploaded
 * image briefly has only its original — the preview uses whichever is present.
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { MediaAsset } from '~/types/api'
import { useApiError } from '~/composables/useApiError'

const props = withDefaults(defineProps<{
  /** Asset id, or an array of ids when `multiple`. */
  modelValue?: string | string[] | null
  label?: string
  folder?: string
  multiple?: boolean
  max?: number
  disabled?: boolean
  errorMessages?: string[]
}>(), {
  modelValue: null,
  label: '',
  folder: 'products',
  multiple: false,
  max: 8,
  disabled: false,
  errorMessages: () => [],
})

const emit = defineEmits<{
  'update:modelValue': [value: string | string[] | null]
  uploaded: [asset: MediaAsset]
}>()

const { t } = useI18n()
const { messageFor } = useApiError()

const inputRef = ref<HTMLInputElement | null>(null)
const dragging = ref(false)
const uploading = ref(false)
const localError = ref('')

/** Assets uploaded in this session, so previews render without another fetch. */
const known = ref(new Map<string, MediaAsset>())

const ids = computed<string[]>(() => {
  if (!props.modelValue) return []
  return Array.isArray(props.modelValue) ? props.modelValue : [props.modelValue]
})

const previews = computed(() =>
  ids.value.map((id) => {
    const asset = known.value.get(id)
    return {
      id,
      url: asset?.variants?.small ?? asset?.url ?? '',
      alt: asset?.alt_text || asset?.original_filename || '',
    }
  }),
)

const canAddMore = computed(() =>
  props.multiple ? ids.value.length < props.max : ids.value.length === 0,
)

const allErrors = computed(() =>
  localError.value ? [...props.errorMessages, localError.value] : props.errorMessages,
)

// Fetch metadata for ids the parent supplied that we have not seen, so an edit
// form shows the images already attached to the record.
watch(ids, async (next) => {
  const missing = next.filter(id => !known.value.has(id))
  if (missing.length === 0) return

  await Promise.all(missing.map(async (id) => {
    try {
      const asset = await useNuxtApp().$api.get<MediaAsset>(`/media/assets/${id}/`)
      known.value.set(id, asset)
      // Reassign so the computed preview list re-evaluates.
      known.value = new Map(known.value)
    }
    catch {
      // A missing asset simply renders without a preview.
    }
  }))
}, { immediate: true })

function pick(): void {
  if (!props.disabled && !uploading.value) inputRef.value?.click()
}

function onSelect(event: Event): void {
  const files = (event.target as HTMLInputElement).files
  if (files?.length) void uploadAll(Array.from(files))
}

function onDrop(event: DragEvent): void {
  dragging.value = false
  const files = event.dataTransfer?.files
  if (files?.length && !props.disabled) void uploadAll(Array.from(files))
}

async function uploadAll(files: File[]): Promise<void> {
  localError.value = ''
  uploading.value = true

  try {
    const room = props.multiple ? props.max - ids.value.length : 1
    for (const file of files.slice(0, Math.max(0, room))) {
      const body = new FormData()
      body.append('file', file)
      body.append('folder', props.folder)

      const asset = await useNuxtApp().$api.post<MediaAsset>('/media/upload/', body)
      known.value.set(asset.id, asset)
      known.value = new Map(known.value)

      emit('update:modelValue', props.multiple ? [...ids.value, asset.id] : asset.id)
      emit('uploaded', asset)
    }
  }
  catch (error) {
    localError.value = messageFor(error)
  }
  finally {
    uploading.value = false
    if (inputRef.value) inputRef.value.value = ''
  }
}

function remove(id: string): void {
  if (props.multiple) emit('update:modelValue', ids.value.filter(current => current !== id))
  else emit('update:modelValue', null)
}
</script>

<style scoped>
.mura-image-upload__item {
  position: relative;
  width: 104px;
  height: 104px;
  overflow: hidden;
}

.mura-image-upload__drop {
  cursor: pointer;
  border-style: dashed;
  transition: border-color var(--mura-transition), background-color var(--mura-transition);
}

.mura-image-upload__drop--over {
  border-color: rgb(var(--v-theme-primary));
  background-color: rgb(var(--v-theme-surface-variant));
}

.mura-image-upload__remove {
  position: absolute;
  top: 4px;
  right: 4px;
}
</style>
