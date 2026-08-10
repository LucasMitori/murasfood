/**
 * Vitest setup.
 *
 * Installs a fresh Pinia before each test and clears the API client registry so
 * a stub from one test cannot leak into the next.
 */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, vi } from 'vitest'
import { resetApiClient } from '../app/utils/api-registry'

beforeEach(() => {
  setActivePinia(createPinia())
  resetApiClient()
  localStorage.clear()
  vi.restoreAllMocks()
})

// `navigateTo` and `useRoute` are Nuxt auto-imports; the units under test only
// need them to exist, not to navigate.
vi.stubGlobal('navigateTo', vi.fn())
vi.stubGlobal('useRoute', () => ({ fullPath: '/', params: {}, query: {} }))
