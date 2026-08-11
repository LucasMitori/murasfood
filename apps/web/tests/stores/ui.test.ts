/**
 * UI store — theme preference.
 *
 * The behaviour under test is survival across a page load. On a
 * server-rendered page the store is built on the server, where `localStorage`
 * does not exist, and Pinia then hydrates the client from that payload — so a
 * store that only reads storage in its initialiser silently loses the
 * visitor's choice on every reload.
 */
import { beforeEach, describe, expect, it } from 'vitest'
import { useUiStore } from '../../app/stores/ui'
import { StorageKeys, writeStorage } from '../../app/utils/storage'
import { THEME_DARK, THEME_LIGHT } from '../../app/utils/theme'

beforeEach(() => {
  localStorage.clear()
})

describe('theme preference', () => {
  it('starts light when nothing is stored', () => {
    expect(useUiStore().theme).toBe(THEME_LIGHT)
  })

  it('restores the stored choice after hydration', () => {
    const ui = useUiStore()
    // Simulates hydration having overwritten the store with the server's state.
    ui.theme = THEME_LIGHT
    writeStorage(StorageKeys.theme, THEME_DARK)

    ui.restoreFromStorage()

    expect(ui.theme).toBe(THEME_DARK)
    expect(ui.isDark).toBe(true)
  })

  it('ignores a corrupted stored value rather than rendering an unknown theme', () => {
    const ui = useUiStore()
    writeStorage(StorageKeys.theme, 'not-a-theme')

    ui.restoreFromStorage()

    expect(ui.theme).toBe(THEME_LIGHT)
  })

  it('follows the system while the visitor has expressed no preference', () => {
    const ui = useUiStore()

    ui.applySystemPreference(true)

    expect(ui.theme).toBe(THEME_DARK)
  })

  it('never lets the system override an explicit choice', () => {
    const ui = useUiStore()
    ui.setTheme(THEME_LIGHT)

    ui.applySystemPreference(true)

    expect(ui.theme).toBe(THEME_LIGHT)
  })

  it('persists a toggle so the next load can restore it', () => {
    const ui = useUiStore()

    expect(ui.toggleTheme()).toBe(THEME_DARK)
    expect(localStorage.getItem(StorageKeys.theme)).toBe(THEME_DARK)
  })
})
