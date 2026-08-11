/**
 * UI state: theme preference and transient notifications.
 *
 * Kept separate from domain stores so a snackbar never lives next to a price.
 */
import { defineStore } from 'pinia'
import { THEME_COOKIE, THEME_DARK, THEME_LIGHT, type ThemeName } from '~/utils/theme'
import { StorageKeys, readStorage, writeCookie, writeStorage } from '~/utils/storage'

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
    theme: (readStorage(StorageKeys.theme) as ThemeName | null) ?? THEME_LIGHT,
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
      writeStorage(StorageKeys.theme, theme)
      // Also as a cookie: the server reads this to render the first paint in
      // the right theme instead of flashing light and correcting itself.
      writeCookie(THEME_COOKIE, theme)
    },

    toggleTheme(): ThemeName {
      this.setTheme(this.theme === THEME_DARK ? THEME_LIGHT : THEME_DARK)
      return this.theme
    },

    /**
     * Adopt the operating system's colour preference.
     *
     * Only applied when the visitor has not chosen for themselves — an explicit
     * choice outranks the system setting.
     */
    /**
     * Re-read the saved theme after hydration.
     *
     * The state initialiser reads storage, but on a server-rendered page that
     * runs on the server where there is none — and Pinia then hydrates the
     * client from the server's payload, overwriting it. Without this the
     * visitor's choice is discarded by every page load.
     */
    restoreFromStorage(): void {
      const stored = readStorage(StorageKeys.theme) as ThemeName | null
      if (stored === THEME_DARK || stored === THEME_LIGHT) this.theme = stored
    },

    /** Follows the system only while the visitor has expressed no preference. */
    applySystemPreference(prefersDark: boolean): void {
      if (readStorage(StorageKeys.theme)) return
      this.theme = prefersDark ? THEME_DARK : THEME_LIGHT
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
