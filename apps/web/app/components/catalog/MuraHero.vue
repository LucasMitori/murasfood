<template lang="pug">
section.mura-hero(:aria-label="t('home.heroLabel')")
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

        .mura-hero__content(:class="`mura-hero__content--${alignOf(banner)}`")
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
}>(), { autoplay: true })

const { t } = useI18n()

const active = ref(0)
const offset = ref(0)
const scrolled = ref(false)
const reducedMotion = ref(false)

const cycle = computed(() => props.autoplay && props.banners.length > 1 && !reducedMotion.value)
const showScrollHint = computed(() => !scrolled.value)

/**
 * Move the image at 40% of scroll speed.
 *
 * Zero when the visitor asked for reduced motion: parallax is the textbook
 * trigger for vestibular discomfort, and the hero reads fine without it.
 */
const mediaStyle = computed(() => ({
  transform: reducedMotion.value ? 'none' : `translate3d(0, ${offset.value * 0.4}px, 0)`,
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
    case 'CATEGORY': return `/produtos?category=${banner.link_target}`
    case 'PRODUCT': return `/produtos/${banner.link_target}`
    case 'SEARCH': return `/produtos?q=${encodeURIComponent(banner.link_target)}`
    case 'PROMOTION': return '/produtos?on_sale=true'
    case 'EXTERNAL': return banner.link_target
    default: return '/produtos'
  }
}

function scrollPast(): void {
  window.scrollTo({
    top: window.innerHeight,
    behavior: reducedMotion.value ? 'auto' : 'smooth',
  })
}

let frame = 0

function onScroll(): void {
  // Coalesce to one read per frame: `scrollY` forces a style recalculation,
  // and the scroll event can fire far more often than the screen repaints.
  if (frame) return
  frame = requestAnimationFrame(() => {
    frame = 0
    const y = window.scrollY
    offset.value = Math.min(y, window.innerHeight)
    scrolled.value = y > 80
  })
}

onMounted(() => {
  reducedMotion.value = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  window.addEventListener('scroll', onScroll, { passive: true })
  onScroll()
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScroll)
  if (frame) cancelAnimationFrame(frame)
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
