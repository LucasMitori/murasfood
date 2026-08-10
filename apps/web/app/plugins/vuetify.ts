/**
 * Vuetify plugin.
 *
 * Registered manually rather than through a module so the theme definitions
 * stay in ordinary TypeScript that tests can import directly.
 */
import { createVuetify } from 'vuetify'
import { md3 } from 'vuetify/blueprints'
import { THEME_DARK, THEME_LIGHT, darkTheme, lightTheme } from '~/utils/theme'

export default defineNuxtPlugin({
  // Named so other plugins can declare a dependency on it. Without a name the
  // only ordering is alphabetical by filename, which put this last — after the
  // bootstrap plugin that needs `useTheme()`.
  name: 'murasfood-vuetify',
  setup(nuxtApp) {
    const vuetify = createVuetify({
      blueprint: md3,
      ssr: true,
      theme: {
        defaultTheme: THEME_LIGHT,
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

    nuxtApp.vueApp.use(vuetify)

    // Exposed so other plugins can reach the theme without `useTheme()`, which
    // resolves through injection and therefore needs a component context that a
    // plugin does not reliably have.
    return { provide: { vuetify } }
  },
})
