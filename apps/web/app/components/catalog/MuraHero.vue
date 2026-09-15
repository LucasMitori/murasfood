<template lang="pug">
section.mura-hero(
  ref="root"
  :class="{ 'mura-hero--band': !fullHeight }"
  :aria-label="t('home.heroLabel')"
)
  v-carousel.mura-hero__carousel(
    v-model="active"
    :show-arrows="banners.length > 1 ? 'hover' : false"
    :hide-delimiters="banners.length < 2"
    :cycle="cycle"
    :interval="7000"
    height="100%"
    hide-delimiter-background
    progress="primary"
  )
    v-carousel-item(v-for="(banner, index) in banners" :key="banner.id")
      .mura-hero__slide
        //- The parallax layer. `translate3d` keeps it on the compositor, so the
        //- scroll handler never triggers layout.
        .mura-hero__media(:style="mediaStyle")
          //- Every slide loads eagerly. `v-img` lazy-loads on intersection,
          //- and a carousel slide that is merely off-screen never intersects —
          //- so advancing the carousel showed an empty panel. There are only a
          //- handful of banners, and the hero is the page's main image anyway.
          v-img(
            :src="imageFor(banner)"
            :srcset="srcsetFor(banner)"
            :alt="banner.image?.alt_text || banner.title"
            cover
            height="100%"
            eager
            sizes="100vw"
          )

        .mura-hero__scrim(:style="scrimStyle(banner)")

        .mura-hero__content(
          :class="`mura-hero__content--${alignOf(banner)}`"
          :style="textStyle"
        )
          .mura-hero__inner(:class="{ 'mura-hero__inner--in': index === active }")
            p.mura-hero__eyebrow(v-if="banner.subtitle") {{ banner.subtitle }}
            h1.mura-hero__title {{ banner.title }}
            v-btn.mura-hero__cta(
              v-if="banner.cta_label"
              :to="linkFor(banner)"
              color="primary"
              size="x-large"
              variant="flat"
              rounded="lg"
              append-icon="mdi-arrow-right"
            ) {{ banner.cta_label }}

  //- Scroll hint. Hidden once the visitor has started reading, since a cue to
  //- do the thing they are already doing is just noise.
  button.mura-hero__scroll(
    v-show="showScrollHint"
    type="button"
    :aria-label="t('home.scrollDown')"
    @click="scrollPast"
  )
    v-icon(icon="mdi-chevron-down" size="28")
</template>

<script setup lang="ts">
/**
 * Full-height storefront hero.
 *
 * Everything visible here is the merchant's: images, wording, button label,
 * text alignment and how heavy the scrim over the photo is. That last one is a
 * setting rather than a constant because how much darkening a photo needs to
 * carry white text depends entirely on the photo.
 *
 * The parallax is done here rather than with `v-parallax` because the images
 * live inside a carousel: `v-parallax` owns its own image and its own
 * container height, which does not compose with slides that have to fill the
 * viewport and cross-fade.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Banner } from '~/types/api'
import { buildSrcSet } from '~/utils/format'

const props = withDefaults(defineProps<{
  banners: Banner[]
  /** Advance automatically. Off for a single slide — nothing to advance to. */
  autoplay?: boolean
  /**
   * Move the image and the words as the page scrolls.
   *
   * Off by default: turning it on for every existing storefront on the day this
   * deploys is not a decision this component gets to make. `prefers-reduced-motion`
   * still wins over it.
   */
  parallax?: boolean
  /** Fill the viewport. Otherwise the hero is a band, not a screen. */
  fullHeight?: boolean
}>(), { autoplay: true, parallax: false, fullHeight: true })

const { t } = useI18n()

const active = ref(0)
/** How far through its exit the hero is, 0 at rest and 1 once scrolled past. */
const progress = ref(0)
/** Overscan available to move within, measured from the DOM. */
const slack = ref(0)
const scrolled = ref(false)
const root = ref<HTMLElement | null>(null)
const reducedMotion = ref(false)

const cycle = computed(() => props.autoplay && props.banners.length > 1 && !reducedMotion.value)
const showScrollHint = computed(() => !scrolled.value)

/**
 * Move the image at 40% of scroll speed.
 *
 * Zero when the visitor asked for reduced motion: parallax is the textbook
 * trigger for vestibular discomfort, and the hero reads fine without it.
 */
/** Nothing moves unless the merchant asked for it and the reader allows it. */
const moves = computed(() => props.parallax && !reducedMotion.value)

/**
 * Travel bounded by the picture, not by the scroll.
 *
 * It was `scrollOffset * 0.4` against a fixed 12% of overscan. Those numbers
 * are unrelated and did not agree: scrolling one viewport moved the image
 * `0.4 × 900 = 360px` while it had `0.12 × 720 ≈ 86px` to move within, so the
 * hero's top edge went blank after about 215px of scroll.
 *
 * `progress` is how far through its own exit the hero is, in 0..1. Multiplying
 * the measured slack by it means the image's edge lands exactly on the hero's
 * edge at the end and never past it — whatever the viewport or the overscan.
 */
const mediaStyle = computed(() => ({
  transform: moves.value ? `translate3d(0, ${(progress.value * slack.value).toFixed(2)}px, 0)` : 'none',
}))

/**
 * The words drift at a fraction of the image's rate.
 *
 * Same rate would read as the whole slide sliding — a bug. The difference
 * between the two speeds is the entire effect.
 */
const textStyle = computed(() => ({
  transform: moves.value
    ? `translate3d(0, ${(progress.value * slack.value * 0.35).toFixed(2)}px, 0)`
    : 'none',
}))

function scrimStyle(banner: Banner): Record<string, string> {
  const strength = (banner.overlay_opacity ?? 45) / 100
  const align = alignOf(banner)

  // The gradient leans away from the text so the type sits on the darkest part
  // of the image while the rest of the photo stays visible.
  const direction = align === 'left' ? 'to right' : align === 'right' ? 'to left' : 'to bottom'
  const strong = `rgba(10, 8, 9, ${strength})`
  const weak = `rgba(10, 8, 9, ${Math.max(strength - 0.3, 0.08)})`

  return {
    background:
      align === 'center'
        ? `linear-gradient(${direction}, ${weak}, ${strong})`
        : `linear-gradient(${direction}, ${strong} 0%, ${strong} 35%, ${weak} 100%)`,
  }
}

function alignOf(banner: Banner): string {
  return (banner.text_align ?? 'CENTER').toLowerCase()
}

function imageFor(banner: Banner): string {
  return banner.image?.variants?.large ?? banner.image?.url ?? ''
}

function srcsetFor(banner: Banner): string {
  return buildSrcSet(banner.image?.variants)
}

function linkFor(banner: Banner): string {
  switch (banner.link_type) {
    case 'CATEGORY': return `/products?category=${banner.link_target}`
    case 'PRODUCT': return `/products/${banner.link_target}`
    case 'SEARCH': return `/products?q=${encodeURIComponent(banner.link_target)}`
    case 'PROMOTION': return '/products?on_sale=true'
    case 'EXTERNAL': return banner.link_target
    default: return '/products'
  }
}

function scrollPast(): void {
  window.scrollTo({
    top: window.innerHeight,
    behavior: reducedMotion.value ? 'auto' : 'smooth',
  })
}

/**
 * Deliberately synchronous, for the same reason as the header: rAF does not
 * run when frames are not being produced, which would freeze the parallax and
 * the scroll hint rather than merely skipping a frame of them.
 */
function onScroll(): void {
  const y = window.scrollY
  const element = root.value
  if (!element) return

  const height = element.getBoundingClientRect().height

  // Measured rather than assumed, so changing the overscan in the CSS changes
  // the strength of the effect and can never expose an edge.
  //
  // Queried through the root rather than with a template ref: the media layer
  // lives inside the carousel's `v-for`, so `ref="media"` would collect an
  // *array* of them and `getBoundingClientRect` would not exist on it. Every
  // slide has identical geometry, so the first one answers for all.
  const mediaHeight = element
    .querySelector('.mura-hero__media')
    ?.getBoundingClientRect().height ?? height
  slack.value = Math.max(0, (mediaHeight - height) / 2)

  progress.value = height > 0 ? Math.min(1, Math.max(0, y / height)) : 0
  scrolled.value = y > 80
}

onMounted(() => {
  reducedMotion.value = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  window.addEventListener('scroll', onScroll, { passive: true })
  onScroll()
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScroll)
})
</script>

<style scoped>
.mura-hero {
  position: relative;
  /* `100svh` avoids the jump when a mobile browser's toolbar retracts. */
  height: 100svh;
  min-height: 32rem;
  overflow: hidden;
  background: rgb(var(--v-theme-secondary));
}

/* A shop that wants the catalogue visible without scrolling. */
.mura-hero--band {
  height: 62svh;
  min-height: 24rem;
}

.mura-hero__carousel {
  height: 100%;
}

.mura-hero__slide {
  position: relative;
  height: 100%;
  overflow: hidden;
}

.mura-hero__media {
  position: absolute;
  inset: -12% 0 0 0;
  /* Taller than the slide so the parallax shift never exposes the edge. */
  height: 124%;
  will-change: transform;
}

.mura-hero__scrim {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.mura-hero__content {
  will-change: transform;
  position: relative;
  display: flex;
  align-items: center;
  height: 100%;
  padding: 0 clamp(1.5rem, 6vw, 7rem);
}

.mura-hero__content--left { justify-content: flex-start; text-align: left; }
.mura-hero__content--center { justify-content: center; text-align: center; }
.mura-hero__content--right { justify-content: flex-end; text-align: right; }

.mura-hero__inner {
  max-width: 46rem;
  opacity: 0;
  transform: translateY(1.5rem);
  transition: opacity 700ms ease, transform 700ms cubic-bezier(0.16, 1, 0.3, 1);
}

.mura-hero__inner--in {
  opacity: 1;
  transform: none;
}

.mura-hero__eyebrow {
  margin-bottom: 0.75rem;
  color: rgba(255, 255, 255, 0.86);
  font-size: clamp(0.875rem, 1.4vw, 1.125rem);
  font-weight: 500;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.mura-hero__title {
  margin-bottom: 2rem;
  color: #fff;
  font-size: clamp(2.25rem, 6vw, 4.5rem);
  font-weight: 700;
  line-height: 1.05;
  letter-spacing: -0.02em;
  text-wrap: balance;
  text-shadow: 0 2px 24px rgba(0, 0, 0, 0.35);
}

.mura-hero__cta {
  padding-inline: 2rem !important;
  font-weight: 600;
}

.mura-hero__scroll {
  position: absolute;
  bottom: 1.75rem;
  left: 50%;
  z-index: 2;
  display: grid;
  place-items: center;
  width: 2.75rem;
  height: 2.75rem;
  margin-left: -1.375rem;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.14);
  color: #fff;
  backdrop-filter: blur(6px);
  animation: mura-hero-bob 2.4s ease-in-out infinite;
  transition: background 200ms ease;
}

.mura-hero__scroll:hover {
  background: rgba(255, 255, 255, 0.26);
}

@keyframes mura-hero-bob {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(6px); }
}

@media (prefers-reduced-motion: reduce) {
  .mura-hero__inner {
    opacity: 1;
    transform: none;
    transition: none;
  }

  .mura-hero__scroll {
    animation: none;
  }
}
</style>
