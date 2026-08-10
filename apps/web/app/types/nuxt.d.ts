/**
 * Ambient types for values injected by our plugins.
 *
 * Without this, `useNuxtApp().$api` is `any` and every call site silently loses
 * its types.
 */
import type { ApiClient } from '~/utils/api-client'

declare module '#app' {
  interface NuxtApp {
    $api: ApiClient
  }
}

declare module 'vue' {
  interface ComponentCustomProperties {
    $api: ApiClient
  }
}

export {}
