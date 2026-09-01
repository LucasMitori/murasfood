import { useTenantStore } from '~/stores/tenant'

/**
 * Loads the merchant's configuration on both the server and the client.
 *
 * Universal on purpose. The tenant record drives the store name, opening
 * hours, contact details and the footer's legal links — all public, all worth
 * having in the server-rendered HTML for search engines, and all of it
 * previously fetched in a client-only plugin. That left the server rendering a
 * footer with no legal links and the browser rendering one with them, which
 * Vue reported as a hydration mismatch on every load.
 *
 * Pinia serialises the result into the payload, so the client does not refetch.
 */
export default defineNuxtPlugin({
  name: 'murasfood-tenant',
  dependsOn: ['murasfood-api'],
  async setup() {
    await useTenantStore().fetch()
  },
})
