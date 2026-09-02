<template lang="pug">
div
  //- `order="0"` puts the drawer ahead of the app bar in Vuetify's layout
  //- stack, so the sidebar runs the full height of the window and the header
  //- starts beside it rather than spanning across the top.
  v-navigation-drawer.mura-admin-nav(
    v-model="drawer"
    :permanent="mdAndUp"
    :order="0"
    width="272"
  )
    //- Who is signed in, at the top where an operator looks to confirm which
    //- account they are acting as before changing anything.
    .mura-admin-nav__identity
      v-avatar(color="primary" size="42")
        span.text-subtitle-2.font-weight-bold {{ initials(auth.displayName) }}
      .mura-admin-nav__who
        p.mura-admin-nav__name {{ auth.displayName || t('nav.account') }}
        p.mura-admin-nav__email {{ auth.user?.email }}

    v-divider

    v-list.flex-grow-1.py-2(nav density="comfortable")
      v-list-item(
        v-for="entry in visibleEntries"
        :key="entry.to"
        :to="entry.to"
        :prepend-icon="entry.icon"
        color="primary"
        rounded="lg"
      )
        v-list-item-title {{ t(entry.labelKey) }}

    //- Pinned to the bottom: leaving the dashboard is a different kind of
    //- action from navigating inside it, so it does not belong in the list.
    template(#append)
      v-divider
      .pa-3
        v-btn(
          to="/"
          block
          variant="tonal"
          color="primary"
          prepend-icon="mdi-storefront-outline"
        ) {{ t('admin.viewStorefront') }}

  v-app-bar.mura-admin-bar(flat :height="64")
    v-app-bar-nav-icon.d-md-none(:aria-label="t('common.menu')" @click="drawer = !drawer")

    .mura-admin-bar__title
      h1.text-subtitle-1.font-weight-bold.mb-0 {{ t('nav.admin') }}
      p.text-caption.text-medium-emphasis.mb-0 {{ tenant.storeName }}

    v-spacer

    v-btn(
      :icon="ui.isDark ? 'mdi-white-balance-sunny' : 'mdi-weather-night'"
      :aria-label="ui.isDark ? t('common.themeLight') : t('common.themeDark')"
      variant="text"
      @click="ui.toggleTheme()"
    )

    v-menu
      template(#activator="{ props: menuProps }")
        v-btn(v-bind="menuProps" icon variant="text" :aria-label="t('nav.account')")
          v-avatar(color="primary" size="32")
            span.text-caption {{ initials(auth.displayName) }}
      v-list(density="compact")
        v-list-item(to="/account" prepend-icon="mdi-account-outline") {{ t('nav.account') }}
        v-list-item(to="/" prepend-icon="mdi-storefront-outline") {{ t('admin.viewStorefront') }}
        v-divider
        v-list-item(prepend-icon="mdi-logout" @click="signOut") {{ t('nav.signOut') }}

  v-main
    #main-content.mura-container.py-6(tabindex="-1")
      slot

  //- Where am I, and how do I get back?
  //-
  //- Derived from the route rather than declared per page, so a new screen gets
  //- its trail without remembering to add one, and a page that moves cannot
  //- leave a stale path behind.
  //-
  //- A sibling of `v-main`, not a child of it: Vuetify's layout system only
  //- reserves space for `app` components it owns directly, and nesting this one
  //- inside the main region took the whole dashboard down.
  v-footer.mura-admin-foot(app)
    .mura-container.d-flex.align-center.flex-wrap.ga-1
      v-icon.mr-1(icon="mdi-map-marker-path" size="16" color="primary")
      template(v-for="(crumb, index) in trail" :key="crumb.to")
        v-icon(v-if="index > 0" icon="mdi-chevron-right" size="14" class="text-medium-emphasis")
        nuxt-link.mura-admin-foot__crumb(v-if="index < trail.length - 1" :to="crumb.to") {{ crumb.label }}
        span.mura-admin-foot__crumb.mura-admin-foot__crumb--current(v-else) {{ crumb.label }}

      v-spacer

      span.text-caption.text-medium-emphasis.d-none.d-sm-inline {{ tenant.storeName }}

  mura-floating-tools
</template>

<script setup lang="ts">
/**
 * Merchant dashboard layout.
 *
 * Navigation entries are filtered by permission code, so a staff member never
 * sees a link to a page the API would refuse. The API re-checks regardless —
 * this only avoids offering a dead end.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDisplay } from 'vuetify'
import { useAuthStore } from '~/stores/auth'
import { useTenantStore } from '~/stores/tenant'
import { useUiStore } from '~/stores/ui'
import { usePermission } from '~/composables/usePermission'
import { initials } from '~/utils/format'

const { t } = useI18n()
const auth = useAuthStore()
const tenant = useTenantStore()
const ui = useUiStore()
const router = useRouter()
const { mdAndUp } = useDisplay()

const drawer = ref(true)

// Navigation is driven by *page* permissions, the same codes the route guard
// enforces — so a visible link never leads to a 403. Every entry here has a
// page behind it; the link test fails the build if one stops being true.
const entries = [
  { to: '/admin', icon: 'mdi-view-dashboard-outline', labelKey: 'admin.dashboard', permission: 'perm.admin.dashboard' },
  { to: '/admin/orders', icon: 'mdi-receipt-text-outline', labelKey: 'admin.orders', permission: 'perm.admin.orders' },
  { to: '/admin/products', icon: 'mdi-package-variant-closed', labelKey: 'admin.products', permission: 'perm.admin.products' },
  { to: '/admin/inventory', icon: 'mdi-warehouse', labelKey: 'admin.inventory', permission: 'perm.admin.inventory' },
  { to: '/admin/inventory/alerts', icon: 'mdi-alert-decagram-outline', labelKey: 'admin.stockHealth', permission: 'perm.admin.inventory' },
  { to: '/admin/inventory/expiry', icon: 'mdi-calendar-clock', labelKey: 'admin.expiry', permission: 'perm.admin.inventory' },
  { to: '/admin/customers', icon: 'mdi-account-group-outline', labelKey: 'admin.customers', permission: 'perm.admin.customers' },
  { to: '/admin/finance', icon: 'mdi-finance', labelKey: 'admin.finance', permission: 'perm.admin.finance' },
  { to: '/admin/users', icon: 'mdi-shield-account-outline', labelKey: 'admin.users', permission: 'perm.admin.users' },
  { to: '/admin/storefront', icon: 'mdi-home-edit-outline', labelKey: 'admin.homeConfig', permission: 'perm.admin.settings' },
]

const { can } = usePermission()
const visibleEntries = computed(() => entries.filter(entry => can(entry.permission)))

const route = useRoute()

/**
 * The path back out of wherever we are.
 *
 * Built from the URL and matched against the navigation entries, so a page
 * inherits its trail from where it sits rather than declaring one. A segment
 * with no matching entry (an id, say) falls back to a readable form of itself.
 */
const trail = computed(() => {
  const segments = route.path.split('/').filter(Boolean)
  const crumbs: { to: string, label: string }[] = []
  let path = ''

  for (const segment of segments) {
    path += `/${segment}`
    const entry = entries.find(candidate => candidate.to === path)

    if (entry) {
      crumbs.push({ to: path, label: t(entry.labelKey) })
      continue
    }

    // An id or an unlisted leaf. A raw uuid tells the reader nothing, so it is
    // shown as the action it represents where we know one, and otherwise as
    // the segment with its separators softened.
    const known: Record<string, string> = {
      novo: t('common.create'),
      editar: t('common.edit'),
    }
    const label = known[segment]
      ?? (segment.length > 20 ? t('admin.details') : segment.replace(/[-_]/g, ' '))

    crumbs.push({ to: path, label })
  }

  return crumbs
})

async function signOut(): Promise<void> {
  await auth.logout()
  await router.push('/')
}
</script>

<style scoped>
/*
 * Matched to the app bar's 64px so the divider under this block lines up with
 * the bottom of the header beside it. Left as free padding the two edges
 * disagreed by a few pixels, which reads as a misaligned seam across the top.
 */
.mura-admin-nav__identity {
  display: flex;
  min-height: 64px;
  box-sizing: border-box;
  align-items: center;
  gap: 0.75rem;
  padding: 0 1rem;
}

/* The title was hard against the sidebar's edge; this gives it the same
   breathing room the drawer's own content has. */
.mura-admin-bar__title {
  padding-inline-start: 0.5rem;
}

@media (min-width: 960px) {
  .mura-admin-bar__title {
    padding-inline-start: 1rem;
  }
}

.mura-admin-foot {
  min-height: 40px;
  padding-block: 0;
  border-top: 1px solid rgba(var(--v-border-color), 0.6);
  background: rgb(var(--v-theme-surface));
  font-size: 0.75rem;
}

.mura-admin-foot__crumb {
  padding-inline: 0.25rem;
  color: rgb(var(--v-theme-on-surface-variant));
  text-decoration: none;
  white-space: nowrap;
}

.mura-admin-foot__crumb:hover {
  color: rgb(var(--v-theme-primary));
  text-decoration: underline;
}

.mura-admin-foot__crumb--current {
  color: rgb(var(--v-theme-on-surface));
  font-weight: 600;
}

.mura-admin-nav__who {
  min-width: 0;
}

.mura-admin-nav__name {
  overflow: hidden;
  margin-bottom: 0;
  font-size: 0.875rem;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mura-admin-nav__email {
  overflow: hidden;
  margin-bottom: 0;
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.75rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mura-admin-bar {
  border-bottom: 1px solid rgba(var(--v-border-color), 0.6);
  background: rgb(var(--v-theme-surface));
}
</style>
