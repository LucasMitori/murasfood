/**
 * Client-side startup.
 *
 * Loads the tenant's white-label configuration, applies the visitor's theme,
 * and restores their session. Runs only in the browser: the theme depends on a
 * stored preference and the session on a stored token, neither of which exists
 * during SSR.
 */
import type { ThemeInstance } from 'vuetify'
import { useAuthStore } from '~/stores/auth'
import { useCartStore } from '~/stores/cart'
import { useFavoritesStore } from '~/stores/favorites'
import { useTenantStore } from '~/stores/tenant'
import { useUiStore } from '~/stores/ui'
import { brandingOverrides } from '~/utils/theme'

export default defineNuxtPlugin({
  name: 'murasfood-bootstrap',
  // Vuetify must be installed before `useTheme()` below can resolve, and the
  // API client before any store fetches. Plugins are otherwise ordered by
  // filename, which ran this one first and left the app unable to hydrate.
  dependsOn: ['murasfood-api', 'murasfood-vuetify'],
  async setup(nuxtApp) {
    const ui = useUiStore()
    const tenant = useTenantStore()
    const auth = useAuthStore()
    const cart = useCartStore()
    const favorites = useFavoritesStore()

    // Before anything reads `isAuthenticated`: hydration has just replaced the
    // store with the server's state, which never has tokens.
    auth.restoreFromStorage()

    // --- Theme --------------------------------------------------------------
    const media = window.matchMedia?.('(prefers-color-scheme: dark)')
    if (media) {
      ui.applySystemPreference(media.matches)
      // Follow the system while the visitor has expressed no preference.
      media.addEventListener?.('change', event => ui.applySystemPreference(event.matches))
    }

    // Taken from the instance the Vuetify plugin provides rather than
    // `useTheme()`: that composable injects, and injection outside a component
    // setup throws — which killed hydration for the whole app.
    const theme = (nuxtApp.$vuetify as { theme: ThemeInstance }).theme
    theme.global.name.value = ui.theme

    watch(
      () => ui.theme,
      (next) => {
        theme.global.name.value = next
        applyBranding()
      },
    )

    // --- Tenant configuration ----------------------------------------------
    function applyBranding(): void {
      const overrides = brandingOverrides(tenant.branding, ui.isDark)
      const active = theme.themes.value[ui.theme]
      if (!active) return
      Object.assign(active.colors, overrides)
    }

    await tenant.fetch()
    applyBranding()

    if (tenant.tenant) {
      const i18n = nuxtApp.$i18n as { locale: { value: string }, availableLocales: string[] } | undefined
      if (i18n?.availableLocales?.includes(tenant.locale)) i18n.locale.value = tenant.locale
    }

    // --- Session ------------------------------------------------------------
    if (auth.isAuthenticated) {
      const profile = await auth.fetchProfile()
      if (profile) await favorites.fetch()
    }

    // The cart is loaded for everyone: anonymous visitors have one too.
    await cart.fetch()
  },
})
