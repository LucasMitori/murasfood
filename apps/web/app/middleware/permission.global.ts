/**
 * Page-level permission guard.
 *
 * Applied globally, so a page opts in by declaring what it needs rather than by
 * remembering to add middleware:
 *
 * ```ts
 * definePageMeta({ permission: 'perm.admin.users' })
 * ```
 *
 * Pages with no `permission` are public. This is routing, not security — the
 * API enforces the same codes on every request — but it keeps a user from
 * landing on a screen whose every call will 403.
 */
import { useAuthStore } from '~/stores/auth'
import { grants } from '~/composables/usePermission'

export default defineNuxtRouteMiddleware(async (to) => {
  const required = to.meta.permission as string | string[] | undefined
  if (!required) return

  // Permissions come from the profile, which is fetched with a token the
  // server cannot see. Deciding here would deny every signed-in visitor.
  if (import.meta.server) return

  const codes = Array.isArray(required) ? required : [required]
  const auth = useAuthStore()

  if (!auth.isAuthenticated) {
    return navigateTo({ path: '/auth/login', query: { redirect: to.fullPath } })
  }

  // A hard refresh deep inside the app has a token but no profile yet, so the
  // permission set is empty until it is fetched.
  if (!auth.user) await auth.fetchProfile()

  // The session died while the tab was open.
  if (!auth.user) {
    return navigateTo({ path: '/auth/login', query: { redirect: to.fullPath } })
  }

  const held = auth.permissions
  const allowed = codes.every(code => grants(held, code))

  if (!allowed) {
    // 403 rather than a redirect: silently bouncing someone to the home page
    // leaves them unable to tell a missing permission from a broken link.
    throw createError({
      statusCode: 403,
      statusMessage: 'Forbidden',
      data: { required: codes },
      fatal: true,
    })
  }
})
