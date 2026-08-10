/**
 * Restricts the dashboard to merchant staff.
 *
 * A convenience gate only: every dashboard endpoint enforces its own permission
 * codes server-side, so bypassing this reveals nothing.
 */
import { useAuthStore } from '~/stores/auth'

export default defineNuxtRouteMiddleware(async (to) => {
  const auth = useAuthStore()

  if (!auth.isAuthenticated) {
    return navigateTo({ path: '/auth/login', query: { redirect: to.fullPath } })
  }

  // A hard refresh inside /admin has tokens but no profile yet.
  if (!auth.user) await auth.fetchProfile()

  if (!auth.isMerchantUser) {
    return navigateTo('/')
  }
})
