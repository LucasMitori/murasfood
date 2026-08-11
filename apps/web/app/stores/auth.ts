/**
 * Authentication store.
 *
 * Holds the token pair and the signed-in profile. Permission checks here drive
 * *affordances only* — hiding a button the user cannot use. The API re-checks
 * every request regardless, so a tampered client gains nothing.
 */
import { defineStore } from 'pinia'
import type { AuthTokens, User } from '~/types/api'
import { useApiClient } from '~/utils/api-registry'
import { ApiRequestError } from '~/utils/api-client'
import { StorageKeys, clearAppStorage, readStorage, removeStorage, writeStorage } from '~/utils/storage'

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  user: User | null
  loading: boolean
  error: string | null
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    accessToken: readStorage(StorageKeys.accessToken),
    refreshToken: readStorage(StorageKeys.refreshToken),
    user: null,
    loading: false,
    error: null,
  }),

  getters: {
    isAuthenticated: state => Boolean(state.accessToken),
    isVerified: state => Boolean(state.user?.is_verified),

    /** Merchant staff see the dashboard; customers do not. */
    isMerchantUser: state =>
      Boolean(state.user && ['STAFF', 'MANAGER', 'ADMINISTRATOR', 'PLATFORM_ADMIN'].includes(state.user.user_type)),

    displayName: state => state.user?.full_name || state.user?.email || '',

    permissions: (state): Set<string> => new Set(state.user?.permissions ?? []),
  },

  actions: {
    /** Whether the signed-in user holds a permission code. */
    can(code: string): boolean {
      return this.permissions.has(code)
    },

    /** Whether the user holds every code in the list. */
    canAll(codes: string[]): boolean {
      return codes.every(code => this.can(code))
    },

    /**
     * Re-read the token pair from storage after hydration.
     *
     * The state initialiser above already reads storage, but on a
     * server-rendered page that runs on the *server*, where there is none — and
     * Pinia then hydrates the client from the server's payload, overwriting
     * whatever the browser would have read. Without this the visitor is signed
     * out by every page load.
     */
    restoreFromStorage(): void {
      this.accessToken = readStorage(StorageKeys.accessToken)
      this.refreshToken = readStorage(StorageKeys.refreshToken)
    },

    setTokens(tokens: { access: string, refresh: string }): void {
      this.accessToken = tokens.access
      this.refreshToken = tokens.refresh
      writeStorage(StorageKeys.accessToken, tokens.access)
      writeStorage(StorageKeys.refreshToken, tokens.refresh)
    },

    clearTokens(): void {
      this.accessToken = null
      this.refreshToken = null
      this.user = null
      removeStorage(StorageKeys.accessToken)
      removeStorage(StorageKeys.refreshToken)
    },

    async login(email: string, password: string): Promise<User> {
      this.loading = true
      this.error = null
      try {
        const tokens = await useApiClient().post<AuthTokens>(
          '/auth/login/',
          { email, password },
          { anonymous: true },
        )
        this.setTokens(tokens)
        this.user = tokens.user
        return tokens.user
      }
      catch (error) {
        this.error = errorCode(error)
        throw error
      }
      finally {
        this.loading = false
      }
    },

    async register(payload: {
      email: string
      password: string
      first_name?: string
      last_name?: string
      phone?: string
      marketing_opt_in?: boolean
      accepted_terms?: boolean
    }): Promise<User> {
      this.loading = true
      this.error = null
      try {
        return await useApiClient().post<User>('/auth/register/', payload, { anonymous: true })
      }
      catch (error) {
        this.error = errorCode(error)
        throw error
      }
      finally {
        this.loading = false
      }
    },

    async fetchProfile(): Promise<User | null> {
      if (!this.accessToken) return null
      try {
        this.user = await useApiClient().get<User>('/customers/me/')
        return this.user
      }
      catch (error) {
        // A dead token should not leave the UI in a half-signed-in state.
        if (error instanceof ApiRequestError && error.status === 401) this.clearTokens()
        return null
      }
    },

    async logout(): Promise<void> {
      const refresh = this.refreshToken
      this.clearTokens()

      if (refresh) {
        // Best effort: the local session is already gone either way.
        try {
          await useApiClient().post('/auth/logout/', { refresh })
        }
        catch {
          // Ignored deliberately.
        }
      }
      clearAppStorage()
    },

    async requestPasswordReset(email: string): Promise<void> {
      await useApiClient().post('/auth/password-reset/', { email }, { anonymous: true })
    },

    async confirmPasswordReset(token: string, password: string, uid?: string): Promise<void> {
      await useApiClient().post(
        '/auth/password-reset/confirm/',
        { token, password, uid },
        { anonymous: true },
      )
    },

    async verifyEmail(token: string, uid?: string): Promise<void> {
      await useApiClient().post('/auth/verify-email/', { token, uid }, { anonymous: true })
      await this.fetchProfile()
    },

    async changePassword(currentPassword: string, newPassword: string): Promise<void> {
      await useApiClient().post('/customers/me/change-password/', {
        current_password: currentPassword,
        new_password: newPassword,
      })
      // Every session is revoked server-side, so this one is over too.
      this.clearTokens()
    },
  },
})

function errorCode(error: unknown): string {
  return error instanceof ApiRequestError ? error.code : 'ERROR'
}
