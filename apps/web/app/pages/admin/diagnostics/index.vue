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
    //- The headline: one word, large, coloured. Somebody opening this page is
      //- usually answering "is it us?" and should not have to read a table to
      //- find out.
    v-card.mura-diag__banner.mb-4(:class="`mura-diag__banner--${data.status}`" flat)
      v-icon.mura-diag__banner-icon(:icon="statusIcon(data.status)" size="40")
      div
        h2.text-h6.mb-0 {{ statusLabel(data.status) }}
        p.text-caption.text-medium-emphasis.mb-0 {{ t('diagnostics.checkedAt', { time: checkedAt }) }}
      v-spacer
      v-chip(size="small" variant="tonal") {{ t('diagnostics.environment') }}: {{ data.application.environment }}

    v-row
      v-col(
        v-for="check in data.checks"
        :key="check.key"
        cols="12"
        sm="6"
        lg="4"
      )
        v-card.mura-diag__check(flat :class="`mura-diag__check--${check.status}`")
          .d-flex.align-center.ga-2.mb-1
            v-icon(:icon="statusIcon(check.status)" :color="statusColor(check.status)" size="18")
            h3.text-subtitle-2.mb-0.flex-grow-1 {{ check.label }}
            span.text-caption.text-medium-emphasis(v-if="check.latency_ms !== null") {{ check.latency_ms }} ms

          p.text-body-2.text-medium-emphasis.mb-2 {{ check.detail }}

          //- The structured extras, when there are any. Rendered generically
            //- rather than per check: the API decides what is worth knowing
            //- about each dependency, and a hard-coded layout here would mean
            //- a new field is collected and never shown.
          .mura-diag__meta(v-if="metaRows(check).length")
            .mura-diag__meta-row(v-for="row in metaRows(check)" :key="row.key")
              span.text-caption.text-medium-emphasis {{ row.key }}
              span.text-caption.font-weight-medium {{ row.value }}

    v-row.mt-1
      v-col(cols="12" md="6")
        mura-card(:title="t('diagnostics.application')" icon="mdi-application-outline")
          .mura-diag__meta
            .mura-diag__meta-row(v-for="row in applicationRows" :key="row.key")
              span.text-caption.text-medium-emphasis {{ row.key }}
              span.text-caption.font-weight-medium {{ row.value }}

      v-col(cols="12" md="6")
        mura-card(:title="t('diagnostics.snapshot')" icon="mdi-storefront-outline")
          .mura-diag__meta
            .mura-diag__meta-row
              span.text-caption.text-medium-emphasis {{ t('diagnostics.ordersToday') }}
              span.text-caption.font-weight-medium {{ data.tenant.orders_today ?? '—' }}
            .mura-diag__meta-row
              span.text-caption.text-medium-emphasis {{ t('admin.products') }}
              span.text-caption.font-weight-medium {{ data.tenant.products ?? '—' }}
            .mura-diag__meta-row
              span.text-caption.text-medium-emphasis {{ t('diagnostics.outOfStock') }}
              span.text-caption.font-weight-medium {{ data.tenant.out_of_stock ?? '—' }}
</template>

<script setup lang="ts">
/**
 * Is anything wrong right now, and where?
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

interface Check {
  key: string
  label: string
  status: 'ok' | 'degraded' | 'down' | 'unknown'
  detail: string
  latency_ms: number | null
  meta: Record<string, unknown>
}

interface Diagnostics {
  status: 'ok' | 'degraded' | 'down' | 'unknown'
  generated_at: string
  application: Record<string, unknown>
  checks: Check[]
  tenant: Record<string, number | string>
}

const { t, locale } = useI18n()

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

const STATUS_ICONS: Record<string, string> = {
  ok: 'mdi-check-circle',
  degraded: 'mdi-alert-circle',
  down: 'mdi-close-circle',
  unknown: 'mdi-help-circle',
}

const STATUS_COLORS: Record<string, string> = {
  ok: 'success',
  degraded: 'warning',
  down: 'error',
  unknown: 'on-surface-variant',
}

function statusIcon(status: string): string {
  return STATUS_ICONS[status] ?? STATUS_ICONS.unknown!
}

function statusColor(status: string): string {
  return STATUS_COLORS[status] ?? STATUS_COLORS.unknown!
}

function statusLabel(status: string): string {
  const key = `diagnostics.status${status.replace(/^./, character => character.toUpperCase())}`
  return t(key)
}

/**
 * Flatten a check's extras into printable rows.
 *
 * Lists are joined and empty values dropped, so a check with nothing to add
 * renders no table rather than a row of dashes.
 */
function metaRows(check: Check): { key: string, value: string }[] {
  return Object.entries(check.meta ?? {})
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([key, value]) => ({
      key,
      value: Array.isArray(value) ? value.join(', ') : String(value),
    }))
    .filter(row => row.value.length > 0)
}

const applicationRows = computed(() =>
  Object.entries(data.value?.application ?? {}).map(([key, value]) => ({
    key,
    value: String(value),
  })),
)
</script>

<style scoped>
.mura-diag__banner {
  display: flex;
  align-items: center;
  padding: 20px 24px;
  border: 1px solid rgba(var(--v-border-color), 0.6);
  border-radius: var(--mura-radius-md, 10px);
  gap: 1rem;
}

/* Colour carries the verdict, so it is stated on the surface as well as on the
   icon — an operator glancing at this from across a desk reads the block. */
.mura-diag__banner--ok {
  border-color: rgba(var(--v-theme-success), 0.4);
  background: rgba(var(--v-theme-success), 0.08);
}

.mura-diag__banner--degraded {
  border-color: rgba(var(--v-theme-warning), 0.5);
  background: rgba(var(--v-theme-warning), 0.1);
}

.mura-diag__banner--down {
  border-color: rgba(var(--v-theme-error), 0.5);
  background: rgba(var(--v-theme-error), 0.1);
}

.mura-diag__banner--ok .mura-diag__banner-icon { color: rgb(var(--v-theme-success)); }
.mura-diag__banner--degraded .mura-diag__banner-icon { color: rgb(var(--v-theme-warning)); }
.mura-diag__banner--down .mura-diag__banner-icon { color: rgb(var(--v-theme-error)); }
.mura-diag__banner--unknown .mura-diag__banner-icon { color: rgb(var(--v-theme-on-surface-variant)); }

.mura-diag__check {
  height: 100%;
  padding: 16px;
  border: 1px solid rgba(var(--v-border-color), 0.6);
  border-radius: var(--mura-radius-md, 10px);
  /* A failing dependency should be findable by scanning the left edge. */
  border-inline-start-width: 3px;
}

.mura-diag__check--ok { border-inline-start-color: rgb(var(--v-theme-success)); }
.mura-diag__check--degraded { border-inline-start-color: rgb(var(--v-theme-warning)); }
.mura-diag__check--down { border-inline-start-color: rgb(var(--v-theme-error)); }

.mura-diag__meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.mura-diag__meta-row {
  display: flex;
  justify-content: space-between;
  padding-block: 4px;
  gap: 1rem;
}

.mura-diag__meta-row + .mura-diag__meta-row {
  border-top: 1px solid rgba(var(--v-border-color), 0.35);
}

/* A key is machine vocabulary; keeping it monospaced stops it reading as prose. */
.mura-diag__meta-row span:first-child {
  font-family: ui-monospace, "SFMono-Regular", "Menlo", monospace;
}
</style>
