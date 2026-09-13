<template lang="pug">
section.mura-band(
  ref="root"
  :class="[`mura-band--${height}`, `mura-band--${section.align || 'center'}`, { 'mura-band--still': !motion }]"
  :style="{ '--band-overlay': overlayAlpha }"
  :aria-label="section.title || undefined"
)
  //- The image moves slower than the page. Rendered as an element rather than a
    //- CSS background so it can carry a srcset — a band is the largest picture
    //- on the page, and serving a 4000px file to a phone to blur past it is the
    //- most expensive thing a storefront can do.
  .mura-band__media(:style="mediaStyle")
    mura-image(
      v-if="section.image"
      :asset="section.image"
      :alt="''"
      variant="large"
      sizes="100vw"
      :aspect-ratio="undefined"
      :rounded="false"
      :eager="eager"
      cover
    )

  .mura-band__scrim

  //- The words move too, and slightly faster than the image. That difference is
    //- what reads as depth; moving them at the same rate reads as a bug.
  .mura-band__inner(:style="textStyle")
    .mura-container
      p.mura-band__eyebrow(v-if="section.eyebrow") {{ section.eyebrow }}
      h2.mura-band__title(v-if="section.title") {{ section.title }}
      p.mura-band__subtitle(v-if="section.subtitle") {{ section.subtitle }}

      v-btn.mt-4(
        v-if="section.cta_label && section.cta_url"
        :to="internal ? section.cta_url : undefined"
        :href="internal ? undefined : section.cta_url"
        :target="internal ? undefined : '_blank'"
        :rel="internal ? undefined : 'noopener noreferrer'"
        color="primary"
        size="large"
        variant="flat"
        rounded="lg"
        append-icon="mdi-arrow-right"
      ) {{ section.cta_label }}
</template>

<script setup lang="ts">
/**
 * A full-width band the merchant writes themselves.
 *
 * Sits between the product rails to break the page into chapters — image behind,
 * a heading and a line of copy over it, optionally a button.
 *
 * The parallax is done here rather than with `v-parallax` for two reasons: that
 * component measures the viewport, which the server cannot do, so it produces a
 * hydration mismatch on every first paint; and it takes a plain `src`, which
 * would mean shipping one enormous image to every device.
 *
 * Motion is opt-out at the operating-system level. `prefers-reduced-motion` is
 * not a preference to weigh against the design — for some readers parallax
 * causes nausea, and honouring it is the difference between a considered effect
 * and an inaccessible one.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { HomeSection } from '~/types/api'

const props = withDefaults(defineProps<{
  section: HomeSection
  /** Skip lazy loading — true only for a band above the fold. */
  eager?: boolean
}>(), {
  eager: false,
})

const offset = ref(0)
const motion = ref(false)

const height = computed(() => (props.section.height === 100 ? 'full' : 'tall'))

const overlayAlpha = computed(() => String((props.section.overlay ?? 45) / 100))

const internal = computed(() => (props.section.cta_url || '').startsWith('/'))

/** Image and text move at different rates; the gap between them is the depth. */
const mediaStyle = computed(() => (
  motion.value ? { transform: `translate3d(0, ${offset.value * 0.4}px, 0)` } : undefined
))

const textStyle = computed(() => (
  motion.value ? { transform: `translate3d(0, ${offset.value * 0.16}px, 0)` } : undefined
))

const root = ref<HTMLElement | null>(null)
let frame = 0
let observer: IntersectionObserver | null = null

/**
 * Measure on every frame the band is on screen, rather than on scroll.
 *
 * The hero can listen for `scroll` because it is pinned to the top: its offset
 * is `window.scrollY` and nothing else. A band sits anywhere in the page, so
 * what it needs is its own position in the viewport — and that changes for
 * reasons a scroll event does not report: an image above it finishing loading,
 * a rail growing when its data arrives, the address bar retracting on a phone.
 *
 * A frame loop asks the question directly and cannot fall out of step. It runs
 * only while the band is visible, so a page with six of them costs nothing for
 * the five that are not.
 */
function tick(): void {
  const element = root.value
  if (!element) return

  const rect = element.getBoundingClientRect()
  // Zero when the band is centred, so the effect is symmetrical about it.
  offset.value = rect.top + rect.height / 2 - window.innerHeight / 2

  frame = requestAnimationFrame(tick)
}

function start(): void {
  if (!frame) frame = requestAnimationFrame(tick)
}

function stop(): void {
  if (frame) cancelAnimationFrame(frame)
  frame = 0
}

onMounted(() => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

  // Only after hydration: the server cannot measure a viewport, so rendering a
  // transform there guarantees a mismatch.
  motion.value = true

  if (!root.value) return

  if ('IntersectionObserver' in window) {
    observer = new IntersectionObserver(
      ([entry]) => (entry?.isIntersecting ? start() : stop()),
      // Started a little early so the first frame on screen is already placed.
      { rootMargin: '200px' },
    )
    observer.observe(root.value)
  }
  else {
    start()
  }
})

onBeforeUnmount(() => {
  stop()
  observer?.disconnect()
})
</script>

<style scoped>
.mura-band {
  position: relative;
  display: flex;
  align-items: center;
  overflow: hidden;
  isolation: isolate;
  background: rgb(var(--v-theme-surface-variant));
}

.mura-band--tall { min-height: 70vh; }
.mura-band--full { min-height: 100vh; }

/* Taller than the band, so the image still covers it at the extremes of the
   translation. Without the overscan the top and bottom edges show through. */
.mura-band__media {
  position: absolute;
  inset: -12% 0;
  z-index: 0;
  will-change: transform;
}

.mura-band__media :deep(.mura-image) {
  height: 100%;
  border-radius: 0;
}

/* Darkened, because white type over an arbitrary photograph is a coin toss.
   The merchant sets how much. */
.mura-band__scrim {
  position: absolute;
  inset: 0;
  z-index: 1;
  background: linear-gradient(
    180deg,
    rgba(0, 0, 0, calc(var(--band-overlay) * 0.75)) 0%,
    rgba(0, 0, 0, var(--band-overlay)) 55%,
    rgba(0, 0, 0, calc(var(--band-overlay) * 1.1)) 100%
  );
}

.mura-band__inner {
  position: relative;
  z-index: 2;
  width: 100%;
  padding-block: clamp(3rem, 8vw, 7rem);
  color: #fff;
  will-change: transform;
}

.mura-band--start .mura-band__inner { text-align: start; }
.mura-band--center .mura-band__inner { text-align: center; }
.mura-band--end .mura-band__inner { text-align: end; }

.mura-band__eyebrow {
  margin-bottom: 0.75rem;
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  opacity: 0.85;
}

.mura-band__title {
  max-width: 22ch;
  margin-inline: auto;
  font-size: clamp(2rem, 5.5vw, 3.75rem);
  font-weight: 800;
  line-height: 1.06;
  text-wrap: balance;
  /* Legible even where the scrim is thin and the photograph is pale. */
  text-shadow: 0 2px 24px rgba(0, 0, 0, 0.45);
}

.mura-band--start .mura-band__title,
.mura-band--start .mura-band__subtitle { margin-inline: 0; }

.mura-band--end .mura-band__title,
.mura-band--end .mura-band__subtitle { margin-inline: auto 0; }

.mura-band__subtitle {
  max-width: 48ch;
  margin: 1rem auto 0;
  font-size: clamp(1rem, 1.6vw, 1.25rem);
  line-height: 1.55;
  opacity: 0.92;
  text-shadow: 0 1px 12px rgba(0, 0, 0, 0.4);
}

/* The reader asked for less motion; give them none, not less of it. */
.mura-band--still .mura-band__media,
.mura-band--still .mura-band__inner {
  transform: none !important;
  will-change: auto;
}

@media (prefers-reduced-motion: reduce) {
  .mura-band__media,
  .mura-band__inner {
    transform: none !important;
    will-change: auto;
  }
}
</style>
