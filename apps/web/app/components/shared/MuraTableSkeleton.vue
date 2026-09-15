<template lang="pug">
.mura-table-skeleton(role="status" :aria-label="t('states.loading')")
  table.mura-table-skeleton__table(aria-hidden="true")
    thead
      tr
        th(v-for="index in columns" :key="`h-${index}`")
          span.mura-table-skeleton__bar(:style="headWidth(index)")
    tbody
      tr(v-for="row in rows" :key="`r-${row}`")
        td(v-for="index in columns" :key="`c-${row}-${index}`")
          span.mura-table-skeleton__bar(:style="cellWidth(row, index)")

  span.mura-table-skeleton__label {{ t('states.loading') }}
</template>

<script setup lang="ts">
/**
 * The table's shape, before the table has any data.
 *
 * Replaces Vuetify's `v-skeleton-loader`, for a reason that only shows up on a
 * real dashboard: that component's styles arrive with its own chunk, and on the
 * first navigation to a table screen the chunk lands a frame or two after the
 * markup. For those frames the skeleton renders unstyled — a bare block of the
 * page's surface colour, which on the dark theme is a black rectangle where the
 * data should be. Measured on `/admin/inventory/expiry`: roughly 130 ms with no
 * table at all, then a ~30 ms skeleton, then the rows. Three states, two
 * visible transitions, and the middle one looked like a fault.
 *
 * Everything here is plain HTML and scoped CSS in this file, so there is no
 * second chunk to wait for and no frame where it can render naked.
 *
 * The widths are deterministic rather than random: a skeleton that reshuffles
 * on every re-render draws the eye to itself, which is the opposite of the job.
 */
import { useI18n } from 'vue-i18n'

withDefaults(defineProps<{
  /** How many columns to mimic. Match the real table so nothing jumps. */
  columns?: number
  rows?: number
}>(), {
  columns: 5,
  rows: 6,
})

const { t } = useI18n()

/**
 * Varied but stable bar widths.
 *
 * Uniform bars read as a progress bar rather than as text; a cheap hash of the
 * coordinates gives each cell a width that looks like content and is identical
 * on every render.
 */
function width(seed: number, min: number, span: number): string {
  const noise = (Math.sin(seed) + 1) / 2
  return `${Math.round(min + noise * span)}%`
}

function headWidth(index: number): Record<string, string> {
  return { width: width(index * 7.13, 45, 35) }
}

function cellWidth(row: number, index: number): Record<string, string> {
  // The first column is usually a name and reads longer than the rest.
  const min = index === 1 ? 60 : 35
  return { width: width(row * 3.7 + index * 11.9, min, 30) }
}
</script>

<style scoped>
.mura-table-skeleton {
  position: relative;
  width: 100%;
  overflow: hidden;
}

.mura-table-skeleton__table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}

/*
 * Matched to the real table's own header treatment, so the swap to live data
 * changes the text and nothing else.
 */
.mura-table-skeleton__table th {
  height: 44px;
  padding: 0 16px;
  background: rgb(var(--v-theme-surface-variant));
  text-align: start;
}

.mura-table-skeleton__table td {
  height: 52px;
  padding: 0 16px;
  border-bottom: 1px solid rgba(var(--v-border-color), 0.5);
}

/* The banding the real table has, so the two do not differ in density. */
.mura-table-skeleton__table tbody tr:nth-child(even) > td {
  background: rgba(var(--v-theme-on-surface), 0.028);
}

.mura-table-skeleton__bar {
  display: block;
  height: 10px;
  border-radius: 999px;
  /* Built from the theme's own foreground, so it is a soft grey on light and a
     soft grey on dark — a fixed colour would be invisible in one of them. */
  background: rgba(var(--v-theme-on-surface), 0.11);
}

.mura-table-skeleton__table th .mura-table-skeleton__bar {
  height: 8px;
  background: rgba(var(--v-theme-on-surface-variant), 0.28);
}

/*
 * A sheen that crosses the whole block once per cycle.
 *
 * On the container rather than per bar: one animation instead of forty, and the
 * light passes across the table as a single movement rather than each cell
 * pulsing on its own clock.
 */
.mura-table-skeleton::after {
  position: absolute;
  animation: mura-table-skeleton-sweep 1.4s ease-in-out infinite;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(var(--v-theme-on-surface), 0.05) 50%,
    transparent 100%
  );
  content: "";
  inset: 0;
  pointer-events: none;
}

@keyframes mura-table-skeleton-sweep {
  from { transform: translateX(-100%); }
  to { transform: translateX(100%); }
}

/* Announced to a screen reader, hidden from everyone else — the bars carry no
   meaning, so the only useful thing to say is that something is loading. */
.mura-table-skeleton__label {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

/* A sweeping highlight is exactly the kind of motion this setting is about. */
@media (prefers-reduced-motion: reduce) {
  .mura-table-skeleton::after {
    animation: none;
  }
}
</style>
