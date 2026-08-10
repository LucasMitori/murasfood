/**
 * Restricts the dashboard area to accounts with at least one admin page.
 *
 * Page-level access is enforced by `permission.global.ts`; this is only the
 * area gate, so someone holding a single screen still gets in to reach it.
 * Both are affordances — every dashboard endpoint enforces its own codes.
 */
import { useAuthStore } from '~/stores/auth'

export default defineNuxtRouteMiddleware(async (to) => {
  const auth = useAuthStore()

  if (!auth.isAuthenticated) {
    return navigateTo({ path: '/auth/login', query: { redirect: to.fullPath } })
  }

  // A hard refresh inside /admin has a token but no profile yet.
  if (!auth.user) await auth.fetchProfile()

  const reachesAdmin = [...auth.permissions].some(code => code.startsWith('perm.admin'))
  if (!reachesAdmin) {
    return navigateTo('/')
  }
})
