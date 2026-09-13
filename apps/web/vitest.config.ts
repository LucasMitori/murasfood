import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'

/**
 * Vitest configuration.
 *
 * The suite targets the logic layer — stores, the API client, money handling,
 * formatters and the theme — as plain TypeScript modules. They deliberately
 * avoid Nuxt auto-imports, so the whole suite runs in a second without booting
 * a Nuxt server or compiling single-file components.
 *
 * Rendering is covered by `nuxt build` in CI plus the backend's own end-to-end
 * assertions; adding a full component runtime here would buy little and cost a
 * heavy toolchain.
 */
export default defineConfig({
  resolve: {
    alias: {
      '~': fileURLToPath(new URL('./app', import.meta.url)),
      '@': fileURLToPath(new URL('./app', import.meta.url)),
      '~~': fileURLToPath(new URL('.', import.meta.url)),
    },
  },
  test: {
    globals: true,
    environment: 'happy-dom',
    // The shop's timezone, not the machine's. Date handling that is only ever
    // exercised in UTC hides exactly the bug this project had: a date-only
    // value parsed as UTC midnight renders a day early everywhere west of it,
    // which is all of Brazil.
    env: { TZ: 'America/Sao_Paulo' },
    include: ['tests/**/*.{test,spec}.ts'],
    setupFiles: ['./tests/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json-summary'],
      include: ['app/stores/**', 'app/utils/**', 'app/composables/**'],
    },
  },
})
