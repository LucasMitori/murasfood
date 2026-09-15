<template lang="pug">
.mura-image(
  :class="{ 'mura-image--loaded': loaded, 'mura-image--rounded': rounded, 'mura-image--blurred': Boolean(placeholder) }"
  :style="frameStyle"
)
  //- A real `<picture>`, because AVIF needs a fallback and `v-img` renders a
    //- single `<img>`. Browsers that understand the first source take it; the
    //- rest never request it.
  picture(v-if="asset")
    source(v-if="avifSrcset" :srcset="avifSrcset" :sizes="sizes" type="image/avif")
    source(v-if="webpSrcset" :srcset="webpSrcset" :sizes="sizes" type="image/webp")
    img.mura-image__img(
      ref="imgRef"
      :src="src"
      :alt="alt"
      :sizes="sizes"
      :loading="eager ? 'eager' : 'lazy'"
      :fetchpriority="eager ? 'high' : 'auto'"
      decoding="async"
      :style="{ objectFit: cover ? 'cover' : 'contain' }"
      @load="loaded = true"
      @error="failed = true"
    )

  //- Underneath rather than instead: the placeholder is what shows through
    //- while the image decodes, so there is never an empty box and never a
    //- reflow when the picture arrives.
  .mura-image__state(v-if="failed || (!loaded && !placeholder) || !asset")
    v-icon(
      :icon="failed ? 'mdi-image-broken-variant' : placeholderIcon"
      size="32"
      color="on-surface-variant"
    )
</template>

<script setup lang="ts">
/**
 * Responsive image for a media asset.
 *
 * Emits AVIF with a WebP fallback and a `srcset` per format, so a phone does
 * not fetch a 1280px photo to show it at 160px, and a modern browser pays about
 * a third less for the one it does fetch.
 *
 * The frame reserves its space from the aspect ratio before anything loads.
 * That is what stops a grid of products shuffling as photos arrive, and it is
 * why the placeholder sits behind the image rather than in place of it.
 *
 * `alt` is required: an unlabelled product image is invisible to a screen
 * reader, and product names make good alt text.
 */
import { computed, onMounted, ref, watch } from 'vue'
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

const loaded = ref(false)
const failed = ref(false)
const imgRef = ref<HTMLImageElement | null>(null)

/**
 * Catch an image that arrived before the listener did.
 *
 * A cached image fires `load` while the element is being created, so the
 * handler binds too late and never runs. The fade-in then never starts and the
 * picture stays at zero opacity — invisible on exactly the second visit, which
 * is the one most people make.
 */
function syncLoaded(): void {
  const element = imgRef.value
  if (element?.complete && element.naturalWidth > 0) loaded.value = true
}

onMounted(syncLoaded)


/** The plain `src`, for browsers that ignore `srcset` entirely. */
const src = computed(() => props.asset?.variants?.[props.variant] ?? props.asset?.url ?? '')

/**
 * The blurred stand-in, inlined by the API as a data URI.
 *
 * Costs no request — it arrives in the same JSON as the rest of the card — and
 * is around 120 bytes, so a grid of forty products pays about 5 kB for having
 * something to look at instead of forty grey rectangles.
 */
const placeholder = computed(() => props.asset?.placeholder || '')

const webpSrcset = computed(() => buildSrcSet(props.asset?.variants))
const avifSrcset = computed(() => buildSrcSet(props.asset?.variants, 'avif_'))

// A new asset means a new file to wait for, so the fade starts again.
watch(src, () => {
  loaded.value = false
  failed.value = false
  requestAnimationFrame(syncLoaded)
})

/**
 * A CSS length from whatever the caller passed.
 *
 * A bare number string gets `px` too. In a template `width="40"` is a *string*,
 * and this used to return it untouched — `width: 40` is not valid CSS, so it
 * was silently dropped and the frame fell back to `width: 100%` with no height
 * at all. In the products table that produced thumbnails 0px tall and between
 * 117px and 146px wide, so every product name started at a different x. The
 * symptom looked like a layout problem and was a units problem.
 *
 * Anything that already carries a unit (`50%`, `4rem`, `calc(...)`) passes
 * through as written.
 */
function unit(value: number | string | undefined): string | undefined {
  if (value === undefined || value === '') return undefined
  if (typeof value === 'number') return `${value}px`
  return /^-?\d*\.?\d+$/.test(value.trim()) ? `${value.trim()}px` : value
}

const frameStyle = computed(() => ({
  aspectRatio: props.height ? undefined : String(props.aspectRatio),
  height: unit(props.height),
  width: unit(props.width),
  // A 24px image stretched over the frame is already soft; the blur filter on
  // the pseudo-element finishes the job. Set as a variable so the CSS owns how
  // it is drawn and this only supplies the pixels.
  '--mura-image-placeholder': placeholder.value ? `url("${placeholder.value}")` : undefined,
}))
</script>

<style scoped>
.mura-image {
  position: relative;
  display: block;
  width: 100%;
  overflow: hidden;
  background: rgb(var(--v-theme-surface-variant));
}

.mura-image--rounded {
  border-radius: var(--mura-radius-md, 10px);
}

/* Positioned rather than sized in percentages.
   `height: 100%` against a box whose height comes from `aspect-ratio` has no
   definite parent height to resolve against, so it computed to zero and the
   picture collapsed to nothing. Filling the frame absolutely sidesteps that. */
.mura-image picture {
  position: absolute;
  inset: 0;
  display: block;
}

.mura-image__img {
  display: block;
  width: 100%;
  height: 100%;
}

/* Faded in rather than snapped in: a grid of thumbnails popping into place one
   by one is more distracting than the same images arriving quietly. */
.mura-image__img {
  opacity: 0;
  transition: opacity 320ms ease;
}

.mura-image--loaded .mura-image__img {
  opacity: 1;
}

.mura-image__state {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  pointer-events: none;
}

/*
 * The blurred stand-in.
 *
 * Drawn on a pseudo-element rather than on the frame itself so the blur cannot
 * touch the real photo stacked above it — `filter` on a parent applies to every
 * descendant, which would leave the loaded image permanently soft.
 *
 * Scaled up slightly because blurring samples past the edges and would
 * otherwise leave a pale halo around the frame.
 */
.mura-image--blurred::before {
  position: absolute;
  z-index: 0;
  background-image: var(--mura-image-placeholder);
  background-position: center;
  background-size: cover;
  content: "";
  filter: blur(12px);
  inset: 0;
  transform: scale(1.1);
  transition: opacity 320ms ease;
}

/* Faded out once the real photo is up, so it is not left underneath a
   transparent PNG showing through as a smear. */
.mura-image--blurred.mura-image--loaded::before {
  opacity: 0;
}

.mura-image picture {
  z-index: 1;
}

@media (prefers-reduced-motion: reduce) {
  .mura-image__img,
  .mura-image--blurred::before {
    transition: none;
  }
}
</style>
