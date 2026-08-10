/**
 * Permission checks for the UI.
 *
 * Mirrors the backend's hierarchy so navigation and page guards agree with what
 * the API will actually allow: page codes under `perm.` are hierarchical
 * (holding `perm.admin` grants `perm.admin.users`), capability codes are not.
 *
 * This drives **affordances only**. Every endpoint re-checks the same codes, so
 * a tampered client gains nothing but a broken-looking screen.
 */
import { computed } from 'vue'
import { useAuthStore } from '~/stores/auth'

/** Prefix marking a page-access permission, matching the backend catalogue. */
export const PAGE_PERMISSION_PREFIX = 'perm'

/** Whether a code addresses a page rather than a capability. */
export function isPagePermission(code: string): boolean {
  return code === PAGE_PERMISSION_PREFIX || code.startsWith(`${PAGE_PERMISSION_PREFIX}.`)
}

/**
 * A code and every parent that would also grant it, most specific first.
 *
 * `perm.admin.users` -> `['perm.admin.users', 'perm.admin', 'perm']`.
 * Capability codes have no hierarchy and yield only themselves.
 */
export function permissionAncestors(code: string): string[] {
  if (!isPagePermission(code)) return [code]

  const parts = code.split('.')
  return parts.map((_, index) => parts.slice(0, index + 1).join('.')).reverse()
}

/** Whether a held set satisfies a code, honouring the page hierarchy. */
export function grants(held: Set<string>, code: string): boolean {
  return permissionAncestors(code).some(ancestor => held.has(ancestor))
}

export function usePermission() {
  const auth = useAuthStore()

  const held = computed(() => auth.permissions)

  /** Whether the signed-in user holds `code`. */
  function can(code: string): boolean {
    if (!auth.isAuthenticated) return false
    return grants(held.value, code)
  }

  /** Whether the user holds every code listed. */
  function canAll(codes: string[]): boolean {
    return codes.every(code => can(code))
  }

  /** Whether the user holds at least one of the codes. */
  function canAny(codes: string[]): boolean {
    return codes.some(code => can(code))
  }

  /**
   * Whether any dashboard screen is reachable.
   *
   * Deliberately not `can('perm.admin')`: that code means the *whole*
   * dashboard, and a staff member holding only `perm.admin.orders` must still
   * get past the area gate to reach the one screen they are entitled to.
   */
  const canAccessAdmin = computed(() =>
    auth.isAuthenticated && [...held.value].some(code => code.startsWith('perm.admin')),
  )

  return { can, canAll, canAny, canAccessAdmin, held }
}
