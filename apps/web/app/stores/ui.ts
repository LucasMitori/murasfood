/**
 * UI state: theme preference and transient notifications.
 *
 * Kept separate from domain stores so a snackbar never lives next to a price.
 */
import { defineStore } from 'pinia'
import { THEME_COOKIE, THEME_DARK, THEME_LIGHT, type ThemeName } from '~/utils/theme'
import { StorageKeys, readCookie, readStorage, removeStorage, writeCookie } from '~/utils/storage'

export type NotificationLevel = 'success' | 'info' | 'warning' | 'error'

export interface Notification {
  id: number
  message: string
  level: NotificationLevel
  timeout: number
}

let nextId = 1

export const useUiStore = defineStore('ui', {
  state: (): {
    theme: ThemeName
    notifications: Notification[]
    navigationOpen: boolean
    searchOpen: boolean
  } => ({
    /*
     * Neutral default. The real value is pushed in by the Vuetify plugin,
     * which reads the theme cookie — the one store of the preference both the
     * server and the browser can see. Reading `localStorage` here instead is
     * what filled the console with hydration mismatches: the server rendered
     * light, the client then flipped to the saved dark, and every themed
     * element disagreed.
     */
    theme: THEME_LIGHT,
    notifications: [],
    navigationOpen: false,
    searchOpen: false,
  }),

  getters: {
    isDark: state => state.theme === THEME_DARK,
    currentNotification: state => state.notifications[0] ?? null,
  },

  actions: {
    setTheme(theme: ThemeName): void {
      this.theme = theme
      // A cookie rather than `localStorage`: the server has to read this to
      // render the first paint in the right theme, and it cannot see storage.
      writeCookie(THEME_COOKIE, theme)
    },

    /**
     * Adopt the theme the server rendered with.
     *
     * Called from the Vuetify plugin on both the server and the client with
     * the same cookie value, so the two halves cannot disagree.
     */
    hydrateTheme(theme: ThemeName): void {
      this.theme = theme
    },

    toggleTheme(): ThemeName {
      this.setTheme(this.theme === THEME_DARK ? THEME_LIGHT : THEME_DARK)
      return this.theme
    },

    /**
     * Carry a pre-cookie preference over to the cookie.
     *
     * Visitors who chose a theme before it moved into a cookie still have it
     * in `localStorage`, where the server cannot see it. Migrating costs one
     * hydration mismatch on the single load that does it, and none after.
     *
     * @returns the migrated theme, or `null` when there was nothing to migrate.
     */
    migrateStoredTheme(): ThemeName | null {
      if (readCookie(THEME_COOKIE)) return null

      const stored = readStorage(StorageKeys.theme) as ThemeName | null
      if (stored !== THEME_DARK && stored !== THEME_LIGHT) return null

      removeStorage(StorageKeys.theme)
      this.setTheme(stored)
      return stored
    },

    /**
     * Follows the system only while the visitor has expressed no preference.
     *
     * Writes the cookie as well as the state, so the server renders the same
     * thing next time; the first visit is the only one that can mismatch.
     */
    applySystemPreference(prefersDark: boolean): void {
      if (readCookie(THEME_COOKIE)) return
      this.setTheme(prefersDark ? THEME_DARK : THEME_LIGHT)
    },

    /**
     * Show a transient message.
     *
     * Messages are already-translated strings: the store never contains copy.
     */
    notify(message: string, level: NotificationLevel = 'info', timeout = 4000): number {
      const id = nextId++
      this.notifications.push({ id, message, level, timeout })
      return id
    },

    success(message: string): number {
      return this.notify(message, 'success')
    },

    error(message: string): number {
      // Errors linger: they usually need the reader to do something.
      return this.notify(message, 'error', 7000)
    },

    dismiss(id: number): void {
      this.notifications = this.notifications.filter(item => item.id !== id)
    },

    clearNotifications(): void {
      this.notifications = []
    },
  },
})
