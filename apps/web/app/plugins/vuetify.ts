/**
 * Vuetify plugin.
 *
 * Registered manually rather than through a module so the theme definitions
 * stay in ordinary TypeScript that tests can import directly.
 */
import { createVuetify } from 'vuetify'
import { md3 } from 'vuetify/blueprints'
import { THEME_DARK, THEME_LIGHT, darkTheme, lightTheme } from '~/utils/theme'

export default defineNuxtPlugin((nuxtApp) => {
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
})
