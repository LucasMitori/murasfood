/**
 * Requires a signed-in customer.
 *
 * Redirects to sign-in carrying the intended destination, so the visitor lands
 * where they were going rather than on the home page.
 */
import { useAuthStore } from '~/stores/auth'

export default defineNuxtRouteMiddleware((to) => {
  const auth = useAuthStore()

  if (!auth.isAuthenticated) {
    return navigateTo({ path: '/auth/login', query: { redirect: to.fullPath } })
  }
})
