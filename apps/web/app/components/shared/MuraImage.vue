<template lang="pug">
v-img(
  :src="src"
  :srcset="srcset"
  :sizes="sizes"
  :alt="alt"
  :aspect-ratio="aspectRatio"
  :cover="cover"
  :height="height"
  :width="width"
  :rounded="rounded"
  :eager="eager"
)
  template(#placeholder)
    .d-flex.align-center.justify-center.fill-height.bg-surface-variant
      v-icon(:icon="placeholderIcon" size="32" color="on-surface-variant")

  template(#error)
    .d-flex.align-center.justify-center.fill-height.bg-surface-variant
      v-icon(icon="mdi-image-broken-variant" size="32" color="on-surface-variant")
</template>

<script setup lang="ts">
/**
 * Responsive image for a media asset.
 *
 * Picks the right derivative for the layout and emits a `srcset`, so a phone
 * does not download a 1280 px photo to show it at 160 px. Falls back to the
 * original while derivatives are still being generated.
 *
 * `alt` is required: an unlabelled product image is invisible to a screen
 * reader, and product names make good alt text (spec §57).
 */
import { computed } from 'vue'
import type { MediaAsset } from '~/types/api'
import { buildSrcSet } from '~/utils/format'

const props = withDefaults(defineProps<{
  asset?: MediaAsset | null
  alt: string
  /** Preferred derivative when the browser has no better information. */
  variant?: 'thumbnail' | 'small' | 'medium' | 'large'
  /** `sizes` attribute describing how wide the image renders. */
  sizes?: string
  aspectRatio?: number | string
  cover?: boolean
  height?: number | string
  width?: number | string
  rounded?: string | boolean
  /** Skip lazy loading for above-the-fold images. */
  eager?: boolean
  placeholderIcon?: string
}>(), {
  asset: null,
  variant: 'medium',
  sizes: '(max-width: 600px) 50vw, 320px',
  aspectRatio: 1,
  cover: true,
  height: undefined,
  width: undefined,
  rounded: 'lg',
  eager: false,
  placeholderIcon: 'mdi-image-outline',
})

const src = computed(() => props.asset?.variants?.[props.variant] ?? props.asset?.url ?? '')
const srcset = computed(() => buildSrcSet(props.asset?.variants))
</script>
