/**
 * UI state: theme preference and transient notifications.
 *
 * Kept separate from domain stores so a snackbar never lives next to a price.
 */
import { defineStore } from 'pinia'
import { THEME_DARK, THEME_LIGHT, type ThemeName } from '~/utils/theme'
import { StorageKeys, readStorage, writeStorage } from '~/utils/storage'

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
