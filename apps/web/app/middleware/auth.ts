/**
 * Requires a signed-in customer.
 *
 * Redirects to sign-in carrying the intended destination, so the visitor lands
 * where they were going rather than on the home page.
 */
import { useAuthStore } from '~/stores/auth'

export default defineNuxtRouteMiddleware((to) => {
  // The session lives in localStorage, which the server cannot read, so a
  // server-side check would bounce every signed-in visitor to sign-in. The
  // client runs this again immediately after hydration, where the answer is
  // knowable.
  if (import.meta.server) return

  const auth = useAuthStore()

  if (!auth.isAuthenticated) {
    return navigateTo({ path: '/auth/login', query: { redirect: to.fullPath } })
  }
})
