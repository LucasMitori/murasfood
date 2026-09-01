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

    div
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
        v-list-item(to="/conta" prepend-icon="mdi-account-outline") {{ t('nav.account') }}
        v-list-item(to="/" prepend-icon="mdi-storefront-outline") {{ t('admin.viewStorefront') }}
        v-divider
        v-list-item(prepend-icon="mdi-logout" @click="signOut") {{ t('nav.signOut') }}

  v-main
    #main-content.mura-container.py-6(tabindex="-1")
      slot

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
  { to: '/admin/pedidos', icon: 'mdi-receipt-text-outline', labelKey: 'admin.orders', permission: 'perm.admin.orders' },
  { to: '/admin/produtos', icon: 'mdi-package-variant-closed', labelKey: 'admin.products', permission: 'perm.admin.products' },
  { to: '/admin/estoque', icon: 'mdi-warehouse', labelKey: 'admin.inventory', permission: 'perm.admin.inventory' },
  { to: '/admin/clientes', icon: 'mdi-account-group-outline', labelKey: 'admin.customers', permission: 'perm.admin.customers' },
  { to: '/admin/financeiro', icon: 'mdi-finance', labelKey: 'admin.finance', permission: 'perm.admin.finance' },
  { to: '/admin/usuarios', icon: 'mdi-shield-account-outline', labelKey: 'admin.users', permission: 'perm.admin.users' },
  { to: '/admin/home', icon: 'mdi-home-edit-outline', labelKey: 'admin.homeConfig', permission: 'perm.admin.settings' },
]

const { can } = usePermission()
const visibleEntries = computed(() => entries.filter(entry => can(entry.permission)))

async function signOut(): Promise<void> {
  await auth.logout()
  await router.push('/')
}
</script>

<style scoped>
.mura-admin-nav__identity {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
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
