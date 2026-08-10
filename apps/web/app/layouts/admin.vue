<template lang="pug">
div
  v-app-bar(flat border)
    v-app-bar-nav-icon(:aria-label="t('common.menu')" @click="rail = !rail")
    span.text-h6.font-weight-bold {{ t('nav.admin') }}
    v-spacer
    v-btn(
      :icon="ui.isDark ? 'mdi-weather-sunny' : 'mdi-weather-night'"
      :aria-label="ui.isDark ? t('common.themeLight') : t('common.themeDark')"
      variant="text"
      @click="ui.toggleTheme()"
    )
    v-btn(to="/" variant="text" prepend-icon="mdi-storefront-outline") {{ t('nav.home') }}
    v-menu
      template(#activator="{ props: menuProps }")
        v-btn(v-bind="menuProps" icon variant="text" :aria-label="t('nav.account')")
          v-avatar(color="primary" size="32")
            span.text-caption {{ initials(auth.displayName) }}
      v-list(density="compact")
        v-list-item(disabled)
          v-list-item-title.text-caption {{ auth.displayName }}
        v-divider
        v-list-item(@click="signOut") {{ t('nav.signOut') }}

  v-navigation-drawer(v-model="rail" :permanent="mdAndUp")
    v-list(nav density="comfortable")
      v-list-item(
        v-for="entry in visibleEntries"
        :key="entry.to"
        :to="entry.to"
        :prepend-icon="entry.icon"
      ) {{ t(entry.labelKey) }}

  v-main
    #main-content.mura-container.py-6(tabindex="-1")
      slot
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
import { useUiStore } from '~/stores/ui'
import { initials } from '~/utils/format'

const { t } = useI18n()
const auth = useAuthStore()
const ui = useUiStore()
const router = useRouter()
const { mdAndUp } = useDisplay()

const rail = ref(true)

const entries = [
  { to: '/admin', icon: 'mdi-view-dashboard-outline', labelKey: 'admin.dashboard', permission: 'reports.view' },
  { to: '/admin/pedidos', icon: 'mdi-receipt-text-outline', labelKey: 'admin.orders', permission: 'orders.view' },
  { to: '/admin/produtos', icon: 'mdi-package-variant-closed', labelKey: 'admin.products', permission: 'catalog.view' },
  { to: '/admin/estoque', icon: 'mdi-warehouse', labelKey: 'admin.inventory', permission: 'inventory.view' },
  { to: '/admin/clientes', icon: 'mdi-account-group-outline', labelKey: 'admin.customers', permission: 'customers.view' },
  { to: '/admin/financeiro', icon: 'mdi-finance', labelKey: 'admin.finance', permission: 'finance.view' },
]

const visibleEntries = computed(() => entries.filter(entry => auth.can(entry.permission)))

async function signOut(): Promise<void> {
  await auth.logout()
  await router.push('/')
}
</script>
