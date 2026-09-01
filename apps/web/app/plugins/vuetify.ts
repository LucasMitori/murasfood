/**
 * Vuetify plugin.
 *
 * Registered manually rather than through a module so the theme definitions
 * stay in ordinary TypeScript that tests can import directly.
 */
import { createVuetify } from 'vuetify'
import { md3 } from 'vuetify/blueprints'
import { THEME_COOKIE, THEME_DARK, THEME_LIGHT, darkTheme, lightTheme } from '~/utils/theme'
import { useUiStore } from '~/stores/ui'

export default defineNuxtPlugin({
  // Named so other plugins can declare a dependency on it. Without a name the
  // only ordering is alphabetical by filename, which put this last — after the
  // bootstrap plugin that needs `useTheme()`.
  name: 'murasfood-vuetify',
  setup(nuxtApp) {
    /*
     * The visitor's theme has to be known *here*, before the first render.
     *
     * It is kept in a cookie rather than only in `localStorage` precisely so
     * this line can read it during server rendering. Deciding later, in a
     * client plugin, means the server always emits the light theme and the
     * browser repaints — a flash of the wrong colours, and a hydration
     * mismatch on every themed element.
     */
    const stored = useCookie<string | null>(THEME_COOKIE).value
    const initialTheme = stored === THEME_DARK ? THEME_DARK : THEME_LIGHT

    const vuetify = createVuetify({
      blueprint: md3,
      ssr: true,
      theme: {
        defaultTheme: initialTheme,
        themes: {
          [THEME_LIGHT]: lightTheme,
          [THEME_DARK]: darkTheme,
        },
      },
      defaults: {
        VBtn: { rounded: 'lg', class: 'text-none', style: 'letter-spacing:normal' },
        VCard: { rounded: 'lg' },
        VTextField: { variant: 'outlined', density: 'comfortable', hideDetails: 'auto' },
        VSelect: { variant: 'outlined', density: 'comfortable', hideDetails: 'auto' },
        VTextarea: { variant: 'outlined', density: 'comfortable', hideDetails: 'auto' },
        VAutocomplete: { variant: 'outlined', density: 'comfortable', hideDetails: 'auto' },
        VChip: { rounded: 'md' },
        VAlert: { rounded: 'md', variant: 'tonal' },
      },
    })

    // Seed the store from the very same value, on both the server and the
    // client, so the two halves cannot render different themes.
    useUiStore(nuxtApp.$pinia as never).hydrateTheme(initialTheme)

    nuxtApp.vueApp.use(vuetify)

    // Exposed so other plugins can reach the theme without `useTheme()`, which
    // resolves through injection and therefore needs a component context that a
    // plugin does not reliably have.
    return { provide: { vuetify } }
  },
})
