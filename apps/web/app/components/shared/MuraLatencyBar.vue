<template lang="pug">
.mura-latency(:title="t('diagnostics.latency')")
  .mura-latency__track
    .mura-latency__fill(:class="`mura-latency__fill--${band}`" :style="{ width: `${width}%` }")
  span.mura-latency__value {{ label }}
</template>

<script setup lang="ts">
/**
 * How long a probe took, as a bar rather than a number in a list.
 *
 * A column of millisecond figures all looks the same until one of them is
 * enormous; a bar makes "this one is different" pre-attentive — you see it
 * before you read it.
 *
 * The scale is logarithmic. Latencies here span three orders of magnitude — a
 * 0.7 ms database round trip beside a 2100 ms broker broadcast — and on a linear
 * scale every healthy probe would render as an invisible sliver against the one
 * slow one. Log scale keeps the fast end readable while still making the slow
 * end obviously slow.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{ ms: number }>()

const { t } = useI18n()

/** The top of the scale. Past a second, exactly how slow stops mattering. */
const CEILING_MS = 3000

const width = computed(() => {
  const value = Math.max(props.ms, 0.1)
  const scaled = Math.log10(value / 0.1) / Math.log10(CEILING_MS / 0.1)
  return Math.min(100, Math.max(3, Math.round(scaled * 100)))
})

/**
 * Three bands, matching how the API grades a probe.
 *
 * `SLOW_MS` on the backend is 1000, so anything over that is already reported
 * as degraded; the amber band starts well below it so a dependency that is
 * drifting is visible before it trips.
 */
const band = computed(() => {
  if (props.ms < 250) return 'fast'
  return props.ms < 1000 ? 'medium' : 'slow'
})

/**
 * Precision that follows the magnitude.
 *
 * Rounding to whole milliseconds printed a 0.3 ms database round trip as
 * "0 ms", which reads as a broken probe rather than a fast one. Below 10 ms a
 * decimal is the information; above it, it is noise; past a second, seconds.
 */
const label = computed(() => {
  if (props.ms >= 1000) return `${(props.ms / 1000).toFixed(1)} s`
  if (props.ms < 10) return `${props.ms.toFixed(1)} ms`
  return `${Math.round(props.ms)} ms`
})
</script>

<style scoped>
.mura-latency {
  display: flex;
  align-items: center;
  margin-top: auto;
  gap: 0.6rem;
}

.mura-latency__track {
  overflow: hidden;
  height: 4px;
  flex: 1 1 auto;
  border-radius: 999px;
  background: rgba(var(--v-theme-on-surface), 0.08);
}

.mura-latency__fill {
  height: 100%;
  border-radius: 999px;
  transition: width 400ms ease;
}

.mura-latency__fill--fast { background: rgb(var(--v-theme-success)); }
.mura-latency__fill--medium { background: rgb(var(--v-theme-info)); }
.mura-latency__fill--slow { background: rgb(var(--v-theme-warning)); }

.mura-latency__value {
  flex: 0 0 auto;
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.7rem;
  font-variant-numeric: tabular-nums;
  min-width: 46px;
  text-align: end;
}

@media (prefers-reduced-motion: reduce) {
  .mura-latency__fill {
    transition: none;
  }
}
</style>
