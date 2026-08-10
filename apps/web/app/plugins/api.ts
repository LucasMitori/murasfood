/**
 * Wires the API client into the Nuxt app.
 *
 * Runs before other plugins that need it (stores resolve the client lazily, so
 * ordering only matters for plugins that call the API during setup).
 */
import { ApiClient } from '~/utils/api-client'
import { setApiClient } from '~/utils/api-registry'
import { StorageKeys, readStorage, writeStorage } from '~/utils/storage'
import { useAuthStore } from '~/stores/auth'

export default defineNuxtPlugin({
  name: 'murasfood-api',
  enforce: 'pre',
  setup(nuxtApp) {
    const config = useRuntimeConfig()

    const client = new ApiClient({
      // The browser and the render server can sit on different networks; see
      // `apiBaseUrlServer` in nuxt.config.
      baseUrl: (import.meta.server && config.apiBaseUrlServer) || config.public.apiBaseUrl,

      getAccessToken: () => readStorage(StorageKeys.accessToken),
      getRefreshToken: () => readStorage(StorageKeys.refreshToken),

      onTokensRefreshed: (tokens) => {
        writeStorage(StorageKeys.accessToken, tokens.access)
        writeStorage(StorageKeys.refreshToken, tokens.refresh)
        // Keep the store in step so `isAuthenticated` does not flap.
        const auth = useAuthStore(nuxtApp.$pinia as never)
        auth.accessToken = tokens.access
        auth.refreshToken = tokens.refresh
      },

      onAuthenticationLost: () => {
        const auth = useAuthStore(nuxtApp.$pinia as never)
        auth.clearTokens()
      },

      // A single-merchant deployment resolves its tenant server-side; the
      // header is only needed when one deployment serves several merchants.
      getTenant: () => config.public.defaultTenant || readStorage(StorageKeys.tenant),

      getCartToken: () => readStorage(StorageKeys.cartToken),
      setCartToken: token => writeStorage(StorageKeys.cartToken, token),
    })

    setApiClient(client)

    return {
      provide: { api: client },
    }
  },
})
