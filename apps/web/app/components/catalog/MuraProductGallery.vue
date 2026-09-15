<template lang="pug">
div
  span.text-body-2.d-block.mb-1(v-if="label") {{ label }}
  p.text-caption.text-medium-emphasis.mb-3 {{ t('admin.galleryHint') }}

  //- Drag to order. The first image is the one on the product card, in search
    //- results and in the cart — so "which photo comes first" is a merchandising
    //- decision, not a technicality, and it deserves to be a drag rather than a
    //- radio button labelled "primary".
  draggable.mura-gallery(
    :list="items"
    item-key="id"
    handle=".mura-gallery__grip"
    @end="emitChange"
  )
    template(#item="{ element, index }")
      article.mura-gallery__item(:class="{ 'mura-gallery__item--primary': index === 0 }")
        v-icon.mura-gallery__grip(icon="mdi-drag" size="18" color="on-surface-variant")

        .mura-gallery__thumb
          mura-image(
            :asset="element.asset"
            :alt="element.caption || ''"
            variant="thumbnail"
            :aspect-ratio="1"
            cover
          )
          span.mura-gallery__badge(v-if="index === 0") {{ t('admin.galleryPrimary') }}

        v-text-field.mura-gallery__caption(
          :model-value="element.caption"
          :placeholder="t('admin.galleryCaption')"
          :aria-label="t('admin.galleryCaption')"
          variant="outlined"
          density="compact"
          hide-details
          maxlength="160"
          @update:model-value="value => setCaption(element, value)"
        )

        v-btn(
          icon="mdi-close"
          variant="text"
          size="small"
          density="comfortable"
          color="error"
          :aria-label="t('form.removeFile')"
          @click="remove(element)"
        )

  //- The uploader adds to the end of the list rather than replacing it, so a
    //- merchant adding a seventh photo does not lose the order of the first six.
  mura-image-upload.mt-3(
    v-if="items.length < max"
    :model-value="null"
    :folder="folder"
    multiple
    :max="max - items.length"
    @update:model-value="onUploaded"
  )

  p.text-caption.text-medium-emphasis.mt-2(v-if="items.length >= max") {{ t('admin.galleryFull', { max }) }}
</template>

<script setup lang="ts">
/**
 * A product's photos: which ones, in what order, and what each one shows.
 *
 * Replaces a plain multi-upload, which could express only "these files" —
 * losing the two things that actually matter on a product page. Order decides
 * which photo represents the product everywhere else in the shop, and a caption
 * is what lets a gallery of four near-identical shots mean something ("rótulo",
 * "porção servida") instead of looking like duplicates.
 *
 * The first image is primary, implicitly. A separate "primary" control would be
 * a second way to say the same thing, and the two would eventually disagree.
 */
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import draggable from 'vuedraggable'
import type { MediaAsset } from '~/types/api'

export interface GalleryItem {
  id: string
  caption: string
  asset?: MediaAsset | null
}

const props = withDefaults(defineProps<{
  modelValue?: GalleryItem[]
  label?: string
  folder?: string
  max?: number
}>(), {
  modelValue: () => [],
  label: '',
  folder: 'products',
  max: 8,
})

const emit = defineEmits<{ 'update:modelValue': [value: GalleryItem[]] }>()

const { t } = useI18n()

/**
 * A local, mutable copy.
 *
 * `draggable` reorders the array it is given *in place*, which a prop cannot
 * be. Kept in step with the parent by the watch below, and pushed back on every
 * change.
 */
const items = ref<GalleryItem[]>([...props.modelValue])

watch(() => props.modelValue, (value) => {
  // Only when the parent genuinely differs, or reordering would fight the watch.
  const incoming = value.map(item => `${item.id}:${item.caption}`).join('|')
  const current = items.value.map(item => `${item.id}:${item.caption}`).join('|')
  if (incoming !== current) items.value = [...value]
})

function emitChange(): void {
  emit('update:modelValue', items.value.map(item => ({ ...item })))
}

function setCaption(item: GalleryItem, caption: string): void {
  const found = items.value.find(candidate => candidate.id === item.id)
  if (!found) return
  found.caption = caption
  emitChange()
}

function remove(item: GalleryItem): void {
  items.value = items.value.filter(candidate => candidate.id !== item.id)
  emitChange()
}

/**
 * Append whatever the uploader just stored.
 *
 * It reports asset ids; the full asset arrives with the next save, so until
 * then the thumbnail falls back to its placeholder rather than a broken frame.
 */
function onUploaded(value: string | string[] | null): void {
  const ids = (Array.isArray(value) ? value : [value]).filter(Boolean) as string[]
  const known = new Set(items.value.map(item => item.id))

  for (const id of ids) {
    if (!known.has(id) && items.value.length < props.max) {
      items.value.push({ id, caption: '', asset: null })
    }
  }
  emitChange()
}
</script>

<style scoped>
.mura-gallery {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mura-gallery__item {
  display: flex;
  align-items: center;
  padding: 8px 10px;
  border: 1px solid rgba(var(--v-border-color), 0.55);
  border-radius: 10px;
  background: rgb(var(--v-theme-surface));
  gap: 10px;
}

/* The first one is what represents this product everywhere else, so it is
   marked rather than merely being at the top of a list. */
.mura-gallery__item--primary {
  border-color: rgba(var(--v-theme-primary), 0.55);
  background: rgba(var(--v-theme-primary), 0.04);
}

.mura-gallery__grip {
  cursor: grab;
}

.mura-gallery__grip:active {
  cursor: grabbing;
}

.mura-gallery__thumb {
  position: relative;
  width: 52px;
  height: 52px;
  flex: 0 0 52px;
  overflow: hidden;
  border-radius: 8px;
}

.mura-gallery__thumb :deep(.mura-image) {
  width: 100%;
  height: 100%;
  border-radius: 0;
}

.mura-gallery__badge {
  position: absolute;
  bottom: 0;
  left: 0;
  width: 100%;
  padding: 1px 0;
  background: rgba(var(--v-theme-primary), 0.9);
  color: rgb(var(--v-theme-on-primary));
  font-size: 0.55rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-align: center;
  text-transform: uppercase;
}

.mura-gallery__caption {
  flex: 1 1 auto;
}
</style>
