/**
 * Client-side persistence.
 *
 * A thin wrapper so stores never touch `localStorage` directly: during SSR
 * there is no such object, and reading it would crash the render. On the server
 * this falls back to an in-memory map that lives for one request.
 *
 * Security note: access tokens are short-lived (15 minutes) and refresh tokens
 * rotate and are blacklisted on use, which limits what a stolen token is worth.
 * A stricter deployment can move refresh tokens to an httpOnly cookie set by
 * the API — the store interface below does not change.
 */

const memory = new Map<string, string>()

const isBrowser = (): boolean =>
  typeof window !== 'undefined' && typeof window.localStorage !== 'undefined'

export const StorageKeys = {
  accessToken: 'murasfood.access_token',
  refreshToken: 'murasfood.refresh_token',
  cartToken: 'murasfood.cart_token',
  theme: 'murasfood.theme',
  tenant: 'murasfood.tenant',
  recentlyViewed: 'murasfood.recently_viewed',
  /** Whether the dashboard's navigation is collapsed to its rail. */
  adminRail: 'murasfood.admin_rail',
} as const

export function readStorage(key: string): string | null {
  if (!isBrowser()) return memory.get(key) ?? null
  try {
    return window.localStorage.getItem(key)
  }
  catch {
    // Private browsing modes can throw on access.
    return memory.get(key) ?? null
  }
}

export function writeStorage(key: string, value: string): void {
  memory.set(key, value)
  if (!isBrowser()) return
  try {
    window.localStorage.setItem(key, value)
  }
  catch {
    // Quota or privacy restrictions: the in-memory copy still serves this session.
  }
}

export function removeStorage(key: string): void {
  memory.delete(key)
  if (!isBrowser()) return
  try {
    window.localStorage.removeItem(key)
  }
  catch {
    // Nothing further to do.
  }
}

/** Read and parse a JSON value, returning `fallback` on any problem. */
export function readJson<T>(key: string, fallback: T): T {
  const raw = readStorage(key)
  if (!raw) return fallback
  try {
    return JSON.parse(raw) as T
  }
  catch {
    return fallback
  }
}

export function writeJson(key: string, value: unknown): void {
  writeStorage(key, JSON.stringify(value))
}

/** Clear every key this app owns. Used on sign-out. */
export function clearAppStorage(): void {
  for (const key of Object.values(StorageKeys)) removeStorage(key)
}

/**
 * Persist a value the *server* also needs to see.
 *
 * `localStorage` is invisible to server rendering, so anything that changes
 * what the first paint looks like — the theme — has to travel as a cookie or
 * the server renders one thing and the client corrects it a moment later.
 *
 * Written with `document.cookie` rather than `useCookie` so a Pinia action can
 * call it without needing a Nuxt context.
 */
export function writeCookie(name: string, value: string, days = 365): void {
  if (!isBrowser()) return

  const expires = new Date(Date.now() + days * 864e5).toUTCString()
  document.cookie = `${name}=${encodeURIComponent(value)};expires=${expires};path=/;SameSite=Lax`
}

/** Read a cookie set by {@link writeCookie}. Client-only; `null` on the server. */
export function readCookie(name: string): string | null {
  if (!isBrowser()) return null

  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match?.[1] ? decodeURIComponent(match[1]) : null
}
