/**
 * Access to the shared API client.
 *
 * Stores need the client but must not construct it — the Nuxt plugin owns its
 * configuration, and tests substitute a stub. This registry is the seam between
 * the two.
 */
import type { ApiClient } from '~/utils/api-client'

let client: ApiClient | null = null

export function setApiClient(instance: ApiClient): void {
  client = instance
}

/**
 * Return the configured client.
 *
 * @throws When called before the plugin has run, which means a store was used
 *   outside the Nuxt app or a test forgot to install a stub.
 */
export function useApiClient(): ApiClient {
  if (!client) {
    throw new Error(
      'API client not initialised. The Nuxt plugin sets it at startup; '
      + 'tests should call setApiClient() with a stub.',
    )
  }
  return client
}

/** Drop the registered client. Used between tests. */
export function resetApiClient(): void {
  client = null
}
