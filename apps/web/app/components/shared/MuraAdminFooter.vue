<template lang="pug">
footer.mura-admin-foot
  v-divider.mb-4

  .mura-admin-foot__row
    //- Which shop, and — the part that matters — which environment. An operator
      //- with staging and production open in two tabs has no other way to tell
      //- them apart at a glance, and that confusion is how test data ends up in
      //- a real catalogue.
    .mura-admin-foot__identity
      v-icon.mura-admin-foot__mark(icon="mdi-storefront" size="18" color="primary")
      div
        p.mura-admin-foot__store.mb-0 {{ tenant.storeName }}
        p.text-caption.text-medium-emphasis.mb-0 {{ t('admin.footerTagline') }}

    v-spacer

    nav.mura-admin-foot__links(:aria-label="t('admin.footerLinks')")
      nuxt-link.mura-admin-foot__link(to="/") {{ t('admin.viewStorefront') }}
      nuxt-link.mura-admin-foot__link(v-if="canSeeReports" to="/admin/reports") {{ t('reports.title') }}
      nuxt-link.mura-admin-foot__link(to="/faq") {{ t('faq.title') }}

    //- A live dot rather than a static badge: it is read from the same stock
      //- health the header badge uses, so the footer cannot claim all is well
      //- while the bell beside it shows six alerts.
    nuxt-link.mura-admin-foot__status(
      v-if="canSeeDiagnostics"
      to="/admin/diagnostics"
      :class="`mura-admin-foot__status--${health}`"
    )
      span.mura-admin-foot__dot
      span {{ healthLabel }}

    span.text-caption.text-medium-emphasis.mura-admin-foot__year © {{ year }}
</template>

<script setup lang="ts">
/**
 * The bottom of every dashboard screen.
 *
 * Deliberately not a breadcrumb: `MuraPageHeader` already renders the trail at
 * the top of every page, and a footer repeating it is 40px of every viewport
 * spent saying something twice.
 *
 * What it says instead is context the page above cannot: which shop, which
 * environment, and whether anything needs attention — with a way through to
 * each. It sits in the content flow rather than pinned to the viewport, so it
 * never covers a table's last row.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTenantStore } from '~/stores/tenant'
import { usePermission } from '~/composables/usePermission'
import { useAdminPulse } from '~/composables/useAdminPulse'

const { t } = useI18n()
const tenant = useTenantStore()
const { can } = usePermission()
const pulse = useAdminPulse()

const year = new Date().getFullYear()

const canSeeReports = computed(() => can('perm.admin.reports'))
const canSeeDiagnostics = computed(() => can('perm.admin.diagnostics'))

/**
 * Three states, from the same count the header badge shows.
 *
 * Anything out of stock is "attention" rather than "warning": an empty shelf is
 * a normal fact of a shop's week, and colouring it red every Tuesday teaches
 * people to ignore the dot.
 */
const health = computed(() => {
  const count = pulse.alertCount.value
  if (!count) return 'ok'
  return count > 20 ? 'warn' : 'attention'
})

const healthLabel = computed(() =>
  pulse.alertCount.value
    ? t('admin.stockAlertsCount', pulse.alertCount.value, { count: pulse.alertCount.value })
    : t('diagnostics.statusOk'),
)
</script>

<style scoped>
.mura-admin-foot {
  margin-top: 2.5rem;
  padding-bottom: 1.5rem;
}

.mura-admin-foot__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem 1.25rem;
}

.mura-admin-foot__identity {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.mura-admin-foot__mark {
  flex: 0 0 auto;
}

.mura-admin-foot__store {
  font-size: 0.875rem;
  font-weight: 600;
  line-height: 1.2;
}

.mura-admin-foot__links {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 1rem;
}

.mura-admin-foot__link {
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.8rem;
  text-decoration: none;
  transition: color 140ms ease;
}

.mura-admin-foot__link:hover {
  color: rgb(var(--v-theme-primary));
  text-decoration: underline;
}

.mura-admin-foot__link:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
  border-radius: 3px;
}

.mura-admin-foot__status {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border: 1px solid rgba(var(--v-border-color), 0.7);
  border-radius: 999px;
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.75rem;
  gap: 0.4rem;
  text-decoration: none;
  transition: border-color 140ms ease, background-color 140ms ease;
}

.mura-admin-foot__status:hover {
  border-color: rgba(var(--v-theme-primary), 0.6);
  background: rgba(var(--v-theme-primary), 0.06);
}

.mura-admin-foot__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentcolor;
}

.mura-admin-foot__status--ok .mura-admin-foot__dot { background: rgb(var(--v-theme-success)); }
.mura-admin-foot__status--attention .mura-admin-foot__dot { background: rgb(var(--v-theme-info)); }
.mura-admin-foot__status--warn .mura-admin-foot__dot { background: rgb(var(--v-theme-warning)); }

.mura-admin-foot__year {
  flex: 0 0 auto;
}

@media (prefers-reduced-motion: reduce) {
  .mura-admin-foot__link,
  .mura-admin-foot__status {
    transition: none;
  }
}
</style>
