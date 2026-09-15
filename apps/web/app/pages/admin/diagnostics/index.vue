<template lang="pug">
div
  mura-page-header(
    :title="t('diagnostics.title')"
    :subtitle="t('diagnostics.subtitle')"
    :breadcrumbs="[{ title: 'admin.dashboard', to: '/admin' }, { title: 'admin.diagnostics' }]"
  )
    template(#actions)
      v-btn(
        variant="tonal"
        color="primary"
        prepend-icon="mdi-refresh"
        :loading="pending"
        @click="refresh()"
      ) {{ t('diagnostics.refresh') }}

  mura-error-state(v-if="error" :on-retry="() => refresh()")

  template(v-else-if="data")
    //- The verdict, at the size of the question being asked.
      //- Someone opening this page is answering "is it us?" and should not have
      //- to read a table to find out.
    section.mura-diag__verdict(:class="`mura-diag__verdict--${data.status}`")
      .mura-diag__verdict-mark
        v-icon(:icon="statusIcon(data.status)" size="28")

      .mura-diag__verdict-text
        h2.mura-diag__verdict-title {{ statusLabel(data.status) }}
        p.mura-diag__verdict-sub.mb-0 {{ summary }}

      .mura-diag__verdict-meta
        span.mura-diag__pill(:class="`mura-diag__pill--${envTone}`") {{ data.application.environment }}
        span.text-caption.text-medium-emphasis {{ t('diagnostics.checkedAt', { time: checkedAt }) }}

    //- Anything wrong, first and on its own. On a healthy system this is empty
      //- and the page is a wall of green; on a broken one it is the only thing
      //- worth reading.
    section.mura-diag__group(v-if="problems.length")
      h3.mura-diag__group-title
        v-icon(icon="mdi-alert-circle-outline" size="18" color="warning")
        | {{ t('diagnostics.needsAttention') }}
        span.mura-diag__count {{ problems.length }}

      .mura-diag__grid
        article.mura-diag__check(
          v-for="check in problems"
          :key="check.key"
          :class="`mura-diag__check--${check.status}`"
        )
          header.mura-diag__check-head
            span.mura-diag__check-icon(:class="`mura-diag__check-icon--${check.status}`")
              v-icon(:icon="checkIcon(check.key)" size="18")
            .flex-grow-1.min-width-0
              h4.mura-diag__check-name {{ check.label }}
              p.mura-diag__check-detail.mb-0 {{ check.detail }}
            span.mura-diag__pill(:class="`mura-diag__pill--${check.status}`") {{ statusLabel(check.status) }}

          .mura-diag__meta(v-if="metaRows(check).length")
            .mura-diag__meta-row(v-for="row in metaRows(check)" :key="row.key")
              span.mura-diag__meta-key {{ row.label }}
              span.mura-diag__meta-value {{ row.value }}

          mura-latency-bar(v-if="check.latency_ms !== null" :ms="check.latency_ms")

    section.mura-diag__group
      h3.mura-diag__group-title
        v-icon(icon="mdi-check-circle-outline" size="18" color="success")
        | {{ t('diagnostics.allChecks') }}
        span.mura-diag__count {{ data.checks.length }}

      .mura-diag__grid
        article.mura-diag__check(
          v-for="check in healthy"
          :key="check.key"
          :class="`mura-diag__check--${check.status}`"
        )
          header.mura-diag__check-head
            span.mura-diag__check-icon(:class="`mura-diag__check-icon--${check.status}`")
              v-icon(:icon="checkIcon(check.key)" size="18")
            .flex-grow-1.min-width-0
              h4.mura-diag__check-name {{ check.label }}
              p.mura-diag__check-detail.mb-0 {{ check.detail }}
            span.mura-diag__pill(:class="`mura-diag__pill--${check.status}`") {{ statusLabel(check.status) }}

          .mura-diag__meta(v-if="metaRows(check).length")
            .mura-diag__meta-row(v-for="row in metaRows(check)" :key="row.key")
              span.mura-diag__meta-key {{ row.label }}
              span.mura-diag__meta-value {{ row.value }}

          mura-latency-bar(v-if="check.latency_ms !== null" :ms="check.latency_ms")

    v-row.mt-2
      v-col(cols="12" md="7")
        section.mura-diag__panel
          h3.mura-diag__group-title
            v-icon(icon="mdi-application-outline" size="18" color="primary")
            | {{ t('diagnostics.application') }}

          .mura-diag__facts
            .mura-diag__fact(v-for="row in applicationRows" :key="row.key")
              span.mura-diag__fact-key {{ row.label }}
              span.mura-diag__fact-value {{ row.value }}

      v-col(cols="12" md="5")
        section.mura-diag__panel
          h3.mura-diag__group-title
            v-icon(icon="mdi-storefront-outline" size="18" color="primary")
            | {{ t('diagnostics.snapshot') }}

          .mura-diag__tiles
            .mura-diag__tile
              span.mura-diag__tile-value {{ data.tenant.orders_today ?? '—' }}
              span.mura-diag__tile-label {{ t('diagnostics.ordersToday') }}
            .mura-diag__tile
              span.mura-diag__tile-value {{ data.tenant.products ?? '—' }}
              span.mura-diag__tile-label {{ t('admin.products') }}
            .mura-diag__tile(:class="{ 'mura-diag__tile--warn': Number(data.tenant.out_of_stock) > 0 }")
              span.mura-diag__tile-value {{ data.tenant.out_of_stock ?? '—' }}
              span.mura-diag__tile-label {{ t('diagnostics.outOfStock') }}
</template>

<script setup lang="ts">
/**
 * Is anything wrong right now, and where?
 *
 * The layout follows the question. A verdict band answers it in one word, a
 * group of *problems* answers "where" — and on a healthy system that group is
 * absent entirely, so the page has nothing urgent-looking on it. Everything
 * else is reference material, below.
 *
 * Restricted to administrators through the `system.diagnostics` *capability*,
 * not a `perm.admin.*` page code. Page codes in this system are hierarchical —
 * holding `perm.admin` grants everything beneath it — so a page code would have
 * handed queue depth, storage state and configuration warnings to every staff
 * member who can open the dashboard. The API enforces the same capability
 * regardless of what this guard does; this only avoids offering a dead end.
 *
 * Deliberately not polled. A page that re-asks every few seconds is how the
 * previous healthcheck exhausted the dev server's heap: the probe becomes the
 * load. The button is the refresh, and the timestamp says how stale the answer
 * is.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

definePageMeta({
  layout: 'admin',
  middleware: 'merchant',
  permission: 'perm.admin.diagnostics',
})

type Status = 'ok' | 'degraded' | 'down' | 'unknown'

interface Check {
  key: string
  label: string
  status: Status
  detail: string
  latency_ms: number | null
  meta: Record<string, unknown>
}

interface Diagnostics {
  status: Status
  generated_at: string
  application: Record<string, unknown>
  checks: Check[]
  tenant: Record<string, number | string>
}

const { t, te, locale } = useI18n()

useSeoMeta({ title: () => t('diagnostics.title') })

const { data, error, pending, refresh } = await useAsyncData<Diagnostics>(
  'admin-diagnostics',
  () => useNuxtApp().$api.get<Diagnostics>('/admin/system/diagnostics/'),
)

const checkedAt = computed(() => {
  const stamp = data.value?.generated_at
  if (!stamp) return '—'
  return new Intl.DateTimeFormat(locale.value, { timeStyle: 'medium' }).format(new Date(stamp))
})

/** Anything not green, so it can be shown first and on its own. */
const problems = computed(() =>
  (data.value?.checks ?? []).filter(check => check.status !== 'ok'),
)

const healthy = computed(() => data.value?.checks ?? [])

const summary = computed(() => {
  const checks = data.value?.checks ?? []
  const passing = checks.filter(check => check.status === 'ok').length
  return t('diagnostics.summary', { passing, total: checks.length })
})

/** Production in red-adjacent tones, anything else muted — the point is to be
 *  able to tell two open tabs apart without reading. */
const envTone = computed(() =>
  String(data.value?.application.environment ?? '').startsWith('prod') ? 'down' : 'ok',
)

const STATUS_ICONS: Record<Status, string> = {
  ok: 'mdi-check-circle',
  degraded: 'mdi-alert-circle',
  down: 'mdi-close-circle',
  unknown: 'mdi-help-circle',
}

/** A recognisable mark per dependency: a wall of identical ticks is unreadable
 *  at a glance, and the thing you are hunting for has a shape. */
const CHECK_ICONS: Record<string, string> = {
  database: 'mdi-database',
  cache: 'mdi-lightning-bolt',
  workers: 'mdi-account-hard-hat',
  queue: 'mdi-tray-full',
  storage: 'mdi-folder-multiple-image',
  email: 'mdi-email-fast-outline',
  scheduler: 'mdi-clock-outline',
  configuration: 'mdi-cog-outline',
}

function statusIcon(status: Status): string {
  return STATUS_ICONS[status] ?? STATUS_ICONS.unknown
}

function checkIcon(key: string): string {
  return CHECK_ICONS[key] ?? 'mdi-shield-check-outline'
}

function statusLabel(status: Status): string {
  const key = `diagnostics.status${status.replace(/^./, character => character.toUpperCase())}`
  return t(key)
}

/**
 * Flatten a check's extras into printable rows, with readable labels.
 *
 * The keys are machine vocabulary — `pending_migrations`, `sent_24h` — and
 * printing them raw made the page look like a log dump. Translated where a key
 * is known, humanised where it is not, so a new field the API starts sending
 * still renders as words rather than as a variable name.
 */
function metaRows(check: Check): { key: string, label: string, value: string }[] {
  return Object.entries(check.meta ?? {})
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([key, value]) => ({
      key,
      label: metaLabel(key),
      value: Array.isArray(value)
        ? (value.length ? value.join(', ') : '—')
        : String(value),
    }))
    .filter(row => row.value.length > 0 && row.value !== '—')
}

function metaLabel(key: string): string {
  const translation = `diagnostics.meta.${key}`
  if (te(translation)) return t(translation)
  return key.replace(/_/g, ' ').replace(/^./, character => character.toUpperCase())
}

const applicationRows = computed(() =>
  Object.entries(data.value?.application ?? {}).map(([key, value]) => ({
    key,
    label: metaLabel(key),
    value: String(value),
  })),
)
</script>

<style scoped>
.min-width-0 {
  min-width: 0;
}

/* --- The verdict ---------------------------------------------------------- */
.mura-diag__verdict {
  display: flex;
  align-items: center;
  margin-bottom: 2rem;
  padding: 20px 24px;
  border: 1px solid rgba(var(--v-border-color), 0.6);
  border-radius: 14px;
  gap: 1rem;
}

/* Tinted from the theme rather than fixed colours, so the band is a soft wash
   on light and a soft wash on dark. */
.mura-diag__verdict--ok {
  border-color: rgba(var(--v-theme-success), 0.35);
  background: rgba(var(--v-theme-success), 0.07);
}

.mura-diag__verdict--degraded {
  border-color: rgba(var(--v-theme-warning), 0.4);
  background: rgba(var(--v-theme-warning), 0.08);
}

.mura-diag__verdict--down {
  border-color: rgba(var(--v-theme-error), 0.4);
  background: rgba(var(--v-theme-error), 0.08);
}

.mura-diag__verdict-mark {
  display: grid;
  width: 52px;
  height: 52px;
  flex: 0 0 auto;
  border-radius: 50%;
  place-items: center;
}

.mura-diag__verdict--ok .mura-diag__verdict-mark {
  background: rgba(var(--v-theme-success), 0.16);
  color: rgb(var(--v-theme-success));
}

.mura-diag__verdict--degraded .mura-diag__verdict-mark {
  background: rgba(var(--v-theme-warning), 0.18);
  color: rgb(var(--v-theme-warning));
}

.mura-diag__verdict--down .mura-diag__verdict-mark {
  background: rgba(var(--v-theme-error), 0.18);
  color: rgb(var(--v-theme-error));
}

.mura-diag__verdict-text {
  min-width: 0;
  flex: 1 1 auto;
}

.mura-diag__verdict-title {
  margin-bottom: 2px;
  font-size: 1.15rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  line-height: 1.2;
}

.mura-diag__verdict-sub {
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.85rem;
}

.mura-diag__verdict-meta {
  display: flex;
  flex: 0 0 auto;
  flex-direction: column;
  align-items: flex-end;
  gap: 5px;
}

/* --- Groups --------------------------------------------------------------- */
.mura-diag__group {
  margin-bottom: 2rem;
}

.mura-diag__group-title {
  display: flex;
  align-items: center;
  margin-bottom: 0.9rem;
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.7rem;
  font-weight: 700;
  gap: 0.5rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.mura-diag__count {
  padding: 1px 8px;
  border-radius: 999px;
  background: rgba(var(--v-theme-on-surface), 0.08);
  font-size: 0.7rem;
  letter-spacing: 0;
}

/*
 * `auto-fit` rather than fixed breakpoints: the cards are self-describing and
 * a merchant's laptop, an ultrawide and a tablet all get whatever number fits
 * without three media queries that disagree with each other.
 */
.mura-diag__grid {
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
}

/* --- One check ------------------------------------------------------------ */
.mura-diag__check {
  display: flex;
  flex-direction: column;
  padding: 16px;
  border: 1px solid rgba(var(--v-border-color), 0.55);
  border-radius: 12px;
  background: rgb(var(--v-theme-surface));
  gap: 12px;
  transition: border-color 160ms ease, box-shadow 160ms ease;
}

.mura-diag__check:hover {
  border-color: rgba(var(--v-theme-primary), 0.4);
  box-shadow: 0 10px 26px -20px rgba(var(--v-theme-on-surface), 0.7);
}

/* A failing dependency is findable by scanning one edge. */
.mura-diag__check--degraded { border-inline-start: 3px solid rgb(var(--v-theme-warning)); }
.mura-diag__check--down { border-inline-start: 3px solid rgb(var(--v-theme-error)); }
.mura-diag__check--unknown { border-inline-start: 3px solid rgb(var(--v-theme-on-surface-variant)); }

.mura-diag__check-head {
  display: flex;
  align-items: flex-start;
  gap: 0.7rem;
}

.mura-diag__check-icon {
  display: grid;
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  border-radius: 9px;
  place-items: center;
}

.mura-diag__check-icon--ok {
  background: rgba(var(--v-theme-success), 0.12);
  color: rgb(var(--v-theme-success));
}

.mura-diag__check-icon--degraded {
  background: rgba(var(--v-theme-warning), 0.14);
  color: rgb(var(--v-theme-warning));
}

.mura-diag__check-icon--down {
  background: rgba(var(--v-theme-error), 0.14);
  color: rgb(var(--v-theme-error));
}

.mura-diag__check-icon--unknown {
  background: rgba(var(--v-theme-on-surface), 0.08);
  color: rgb(var(--v-theme-on-surface-variant));
}

.mura-diag__check-name {
  margin-bottom: 1px;
  font-size: 0.9rem;
  font-weight: 600;
  line-height: 1.25;
}

.mura-diag__check-detail {
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.78rem;
  line-height: 1.4;
}

/* --- Status pill ---------------------------------------------------------- */
.mura-diag__pill {
  flex: 0 0 auto;
  padding: 2px 9px;
  border-radius: 999px;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  white-space: nowrap;
}

.mura-diag__pill--ok {
  background: rgba(var(--v-theme-success), 0.14);
  color: rgb(var(--v-theme-success));
}

.mura-diag__pill--degraded {
  background: rgba(var(--v-theme-warning), 0.16);
  color: rgb(var(--v-theme-warning));
}

.mura-diag__pill--down {
  background: rgba(var(--v-theme-error), 0.16);
  color: rgb(var(--v-theme-error));
}

.mura-diag__pill--unknown {
  background: rgba(var(--v-theme-on-surface), 0.08);
  color: rgb(var(--v-theme-on-surface-variant));
}

/* --- Meta ----------------------------------------------------------------- */
.mura-diag__meta {
  display: flex;
  flex-direction: column;
  padding: 10px 12px;
  border-radius: 9px;
  background: rgba(var(--v-theme-on-surface), 0.035);
  gap: 1px;
}

.mura-diag__meta-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding-block: 3px;
  gap: 1rem;
}

.mura-diag__meta-key {
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.74rem;
}

/* Tabular figures so a column of counts lines up on the decimal. */
.mura-diag__meta-value {
  font-size: 0.76rem;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  text-align: end;
  word-break: break-word;
}

/* --- Panels --------------------------------------------------------------- */
.mura-diag__panel {
  height: 100%;
  padding: 18px 20px;
  border: 1px solid rgba(var(--v-border-color), 0.55);
  border-radius: 12px;
  background: rgb(var(--v-theme-surface));
}

.mura-diag__facts {
  display: flex;
  flex-direction: column;
}

.mura-diag__fact {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding-block: 7px;
  gap: 1rem;
}

.mura-diag__fact + .mura-diag__fact {
  border-top: 1px solid rgba(var(--v-border-color), 0.35);
}

.mura-diag__fact-key {
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.78rem;
}

.mura-diag__fact-value {
  font-size: 0.8rem;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  text-align: end;
  word-break: break-word;
}

/* --- Tiles ---------------------------------------------------------------- */
.mura-diag__tiles {
  display: grid;
  gap: 0.6rem;
  grid-template-columns: repeat(3, 1fr);
}

.mura-diag__tile {
  display: flex;
  flex-direction: column;
  padding: 12px 10px;
  border: 1px solid rgba(var(--v-border-color), 0.5);
  border-radius: 10px;
  gap: 2px;
  text-align: center;
}

.mura-diag__tile--warn {
  border-color: rgba(var(--v-theme-warning), 0.5);
  background: rgba(var(--v-theme-warning), 0.07);
}

.mura-diag__tile-value {
  font-size: 1.35rem;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  line-height: 1.1;
}

.mura-diag__tile-label {
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.68rem;
  line-height: 1.2;
}

@media (prefers-reduced-motion: reduce) {
  .mura-diag__check {
    transition: none;
  }
}
</style>
