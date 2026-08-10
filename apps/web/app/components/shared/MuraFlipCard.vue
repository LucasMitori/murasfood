<template lang="pug">
.mura-flip(:style="{ height: containerHeight }")
  .mura-flip__inner(:class="{ 'mura-flip__inner--flipped': modelValue }")
    .mura-flip__face.mura-flip__face--front(
      :inert="modelValue"
      :aria-hidden="modelValue"
    )
      .mura-flip__content(ref="frontRef")
        slot(name="front")

    .mura-flip__face.mura-flip__face--back(
      :inert="!modelValue"
      :aria-hidden="!modelValue"
    )
      .mura-flip__content(ref="backRef")
        slot(name="back")
</template>

<script setup lang="ts">
/**
 * Two-sided card that rotates between its faces.
 *
 * Three details make the difference between a flip that works and one that
 * merely looks like it does:
 *
 * **Height.** The faces are stacked, so the container has no natural height and
 * the taller face would be clipped. It is measured and animated instead, which
 * also keeps the card centred as it grows.
 *
 * **The hidden face still exists.** `backface-visibility` hides it visually but
 * leaves its inputs focusable and readable by a screen reader — tab from the
 * last visible field and you land in an invisible form. `inert` takes the
 * whole subtree out of the accessibility tree and the tab order.
 *
 * **Reduced motion.** A 3D rotation is exactly the kind of movement that
 * triggers vestibular symptoms, so it degrades to a plain cross-fade.
 */
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  /** `false` shows the front, `true` the back. */
  modelValue: boolean
  /** Extra breathing room under the card. */
  padding?: number
}>(), { padding: 0 })

defineEmits<{ 'update:modelValue': [value: boolean] }>()

const frontRef = ref<HTMLElement | null>(null)
const backRef = ref<HTMLElement | null>(null)
const containerHeight = ref<string>('auto')

let observer: ResizeObserver | null = null

/**
 * Trim the container to whichever face is showing.
 *
 * The measured elements are the content wrappers, not the faces themselves: a
 * face is stretched to the grid cell, so asking it for a height asks the
 * container for the height it is in the middle of deriving. The wrapper inside
 * reports the real content height.
 *
 * Failing to run leaves the card at its CSS height — the taller of the two
 * faces — which is untidy but never clips anything.
 */
function measure(): void {
  const active = props.modelValue ? backRef.value : frontRef.value
  if (!active) return

  const height = active.offsetHeight + props.padding
  if (height > 0) containerHeight.value = `${height}px`
}

watch(() => props.modelValue, () => {
  measure()
  // Measure again next frame, once the incoming face has been laid out. Both
  // calls matter: frames stop in a background tab, and the first call keeps the
  // height correct there even though the second never runs.
  requestAnimationFrame(measure)
})

onMounted(async () => {
  // Hydration finishes before styles necessarily have; measuring straight away
  // can read zero and leave the card stuck at its fallback height.
  await nextTick()
  measure()
  requestAnimationFrame(measure)

  // A face can change height after mount — a validation message appears, or a
  // font finishes loading — and the card must grow with it.
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(measure)
    if (frontRef.value) observer.observe(frontRef.value)
    if (backRef.value) observer.observe(backRef.value)
  }
})

onBeforeUnmount(() => observer?.disconnect())
</script>

<style scoped>
.mura-flip {
  perspective: 2000px;
  width: 100%;
  transition: height 420ms cubic-bezier(0.4, 0, 0.2, 1);
}

/*
 * The faces are stacked in one grid cell rather than positioned absolutely.
 * That makes the container's natural height the taller of the two, so neither
 * face can ever be clipped — including before the first measurement, during
 * SSR, and if the script never runs at all. The measured height below is then
 * only an enhancement that trims the container to the face on show.
 */
.mura-flip__inner {
  display: grid;
  width: 100%;
  height: 100%;
  transform-style: preserve-3d;
  transition: transform 620ms cubic-bezier(0.4, 0, 0.2, 1);
}

.mura-flip__inner--flipped {
  transform: rotateY(180deg);
}

.mura-flip__face {
  grid-area: 1 / 1;
  width: 100%;
  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
}

.mura-flip__face--back {
  transform: rotateY(180deg);
}

/* Keep each face pinned to the top as the container height animates. */
.mura-flip__content {
  align-self: start;
}

/*
 * Without motion, rotating is replaced by a fade. `backface-visibility` is
 * disabled too, since with no rotation both faces would otherwise be painted
 * on top of each other.
 */
@media (prefers-reduced-motion: reduce) {
  .mura-flip,
  .mura-flip__inner {
    transition: none;
  }

  .mura-flip__inner--flipped {
    transform: none;
  }

  .mura-flip__face {
    backface-visibility: visible;
    transition: opacity 160ms linear;
  }

  .mura-flip__face--back {
    transform: none;
  }

  .mura-flip__face[aria-hidden='true'] {
    opacity: 0;
    pointer-events: none;
  }
}
</style>
