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
  dependsOn: ['murasfood-api', 'murasfood-vuetify', 'murasfood-tenant'],
  async setup(nuxtApp) {
    const ui = useUiStore()
    const tenant = useTenantStore()
    const auth = useAuthStore()
    const cart = useCartStore()
    const favorites = useFavoritesStore()

    // Hydration has just replaced the auth store with the server's state,
    // which can never have seen `localStorage`.
    auth.restoreFromStorage()

    // The theme is not restored here — it arrives with the page, from the
    // cookie the Vuetify plugin read. This only carries a pre-cookie choice
    // across, once.
    ui.migrateStoredTheme()

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

    // Usually a no-op now: the Vuetify plugin already rendered in the right
    // theme by reading the cookie. This catches the visitor whose cookie was
    // dropped but whose `localStorage` survived.
    if (theme.name.value !== ui.theme) theme.change(ui.theme)

    watch(
      () => ui.theme,
      (next) => {
        // `theme.change()` rather than `theme.global.name.value`, which
        // Vuetify 3.13 keeps only as a deprecated alias.
        theme.change(next)
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

    // The tenant itself is loaded by the universal `murasfood-tenant` plugin,
    // so the server renders the same footer and header the browser will.
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
