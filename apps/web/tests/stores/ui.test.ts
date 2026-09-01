/**
 * UI store — theme preference.
 *
 * The preference lives in a *cookie*, not `localStorage`, and that is the whole
 * point of these tests. Server rendering has to pick the theme before the
 * browser runs anything, and the server can only read cookies. When the two
 * disagreed, every themed element in the page produced a hydration mismatch.
 */
import { beforeEach, describe, expect, it } from 'vitest'
import { useUiStore } from '../../app/stores/ui'
import { StorageKeys, writeStorage } from '../../app/utils/storage'
import { THEME_COOKIE, THEME_DARK, THEME_LIGHT } from '../../app/utils/theme'

function clearCookie(): void {
  document.cookie = `${THEME_COOKIE}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`
}

beforeEach(() => {
  localStorage.clear()
  clearCookie()
})

describe('theme preference', () => {
  it('starts light so the server has something deterministic to render', () => {
    expect(useUiStore().theme).toBe(THEME_LIGHT)
  })

  it('adopts the theme the server rendered with', () => {
    const ui = useUiStore()

    ui.hydrateTheme(THEME_DARK)

    expect(ui.theme).toBe(THEME_DARK)
    expect(ui.isDark).toBe(true)
  })

  it('persists a choice as a cookie, which is what the server can read', () => {
    const ui = useUiStore()

    ui.setTheme(THEME_DARK)

    expect(document.cookie).toContain(`${THEME_COOKIE}=${THEME_DARK}`)
  })

  it('does not keep the theme in storage the server cannot see', () => {
    const ui = useUiStore()

    ui.setTheme(THEME_DARK)

    expect(localStorage.getItem(StorageKeys.theme)).toBeNull()
  })

  it('toggles and reports the new theme', () => {
    const ui = useUiStore()

    expect(ui.toggleTheme()).toBe(THEME_DARK)
    expect(ui.toggleTheme()).toBe(THEME_LIGHT)
  })
})

describe('migrating a pre-cookie preference', () => {
  it('moves a stored choice into the cookie and clears the old key', () => {
    const ui = useUiStore()
    writeStorage(StorageKeys.theme, THEME_DARK)

    expect(ui.migrateStoredTheme()).toBe(THEME_DARK)
    expect(ui.theme).toBe(THEME_DARK)
    expect(document.cookie).toContain(`${THEME_COOKIE}=${THEME_DARK}`)
    // Left behind, it would keep re-applying and mismatching on every load.
    expect(localStorage.getItem(StorageKeys.theme)).toBeNull()
  })

  it('leaves an existing cookie alone', () => {
    const ui = useUiStore()
    ui.setTheme(THEME_LIGHT)
    writeStorage(StorageKeys.theme, THEME_DARK)

    expect(ui.migrateStoredTheme()).toBeNull()
    expect(ui.theme).toBe(THEME_LIGHT)
  })

  it('ignores a corrupted stored value', () => {
    const ui = useUiStore()
    writeStorage(StorageKeys.theme, 'not-a-theme')

    expect(ui.migrateStoredTheme()).toBeNull()
    expect(ui.theme).toBe(THEME_LIGHT)
  })
})

describe('system preference', () => {
  it('is followed while the visitor has expressed none', () => {
    const ui = useUiStore()

    ui.applySystemPreference(true)

    expect(ui.theme).toBe(THEME_DARK)
    // Written through, so the next request renders the same thing and the
    // first visit is the only one that can mismatch.
    expect(document.cookie).toContain(`${THEME_COOKIE}=${THEME_DARK}`)
  })

  it('never overrides an explicit choice', () => {
    const ui = useUiStore()
    ui.setTheme(THEME_LIGHT)

    ui.applySystemPreference(true)

    expect(ui.theme).toBe(THEME_LIGHT)
  })
})
