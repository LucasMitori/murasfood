import vuetify, { transformAssetUrls } from 'vite-plugin-vuetify'

/**
 * Nuxt configuration.
 *
 * The storefront is server-rendered so product pages are indexable (spec §56);
 * everything under `/admin` is explicitly excluded from crawling instead.
 */
export default defineNuxtConfig({
  compatibilityDate: '2025-01-01',
  devtools: { enabled: true },
  ssr: true,

  future: { compatibilityVersion: 4 },

  modules: ['@pinia/nuxt', '@nuxtjs/i18n', '@nuxt/eslint'],

  css: ['vuetify/styles', '~/assets/styles/main.scss'],

  // Components are organised by domain but referenced by their own name, so
  // `components/catalog/MuraProductCard.vue` is `<MuraProductCard>` rather than
  // `<CatalogMuraProductCard>`.
  components: [{ path: '~/components', pathPrefix: false }],

  build: {
    // Vuetify ships untranspiled ESM.
    transpile: ['vuetify'],
  },

  vite: {
    vue: {
      template: { transformAssetUrls },
    },
  },

  hooks: {
    // `vite-plugin-vuetify` must be registered after Nuxt builds its own Vite
    // config so tree-shaking sees every component the app references. The
    // plugin list is readonly in the hook's type, so it is appended to rather
    // than replaced.
    'vite:extendConfig': (config) => {
      config.plugins?.push(
        vuetify({
          autoImport: true,
          // Resolved relative to Nuxt's srcDir, which is `app/` in Nuxt 4.
          styles: { configFile: 'assets/styles/settings.scss' },
        }),
      )
    },
  },

  /**
   * Runtime configuration.
   *
   * Nothing merchant-specific is baked into the bundle: branding, colours and
   * copy all arrive from `GET /tenants/current/` at runtime (spec §66).
   */
  runtimeConfig: {
    public: {
      apiBaseUrl: process.env.NUXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api/v1',
      defaultTenant: process.env.NUXT_PUBLIC_DEFAULT_TENANT || '',
      defaultLocale: process.env.NUXT_PUBLIC_DEFAULT_LOCALE || 'pt-BR',
      appName: 'MurasFood',
    },
  },

  i18n: {
    strategy: 'no_prefix',
    defaultLocale: 'pt-BR',
    langDir: 'locales',
    lazy: false,
    locales: [
      { code: 'pt-BR', language: 'pt-BR', name: 'Português (Brasil)', file: 'pt-BR.json' },
      { code: 'en', language: 'en-US', name: 'English', file: 'en.json' },
      { code: 'es', language: 'es-ES', name: 'Español', file: 'es.json' },
    ],
    detectBrowserLanguage: {
      useCookie: true,
      cookieKey: 'murasfood_locale',
      redirectOn: 'root',
      alwaysRedirect: false,
    },
    bundle: { optimizeTranslationDirective: false },
  },

  app: {
    head: {
      htmlAttrs: { lang: 'pt-BR' },
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        { name: 'theme-color', content: '#7B2D3B' },
      ],
      link: [{ rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' }],
    },
  },

  routeRules: {
    // Admin and account pages must never be indexed (spec §56). An
    // `X-Robots-Tag` header is more reliable than a meta tag: it applies to
    // every response, not only rendered HTML.
    '/admin/**': {
      headers: { 'X-Robots-Tag': 'noindex, nofollow' },
      // The dashboard is behind authentication and personalised, so there is
      // nothing for the server to usefully pre-render.
      ssr: false,
    },
    '/conta/**': { headers: { 'X-Robots-Tag': 'noindex, nofollow' } },
    '/checkout': { headers: { 'X-Robots-Tag': 'noindex, nofollow' }, ssr: false },
    '/pedidos/**': { headers: { 'X-Robots-Tag': 'noindex, nofollow' }, ssr: false },
  },

  typescript: {
    strict: true,
    typeCheck: false, // run explicitly via `npm run typecheck`
  },

  eslint: {
    config: { stylistic: false },
  },
})
