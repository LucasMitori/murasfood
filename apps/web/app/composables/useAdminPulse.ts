/**
 * The numbers the dashboard chrome shows on every screen.
 *
 * One shared fetch, not one per page. The header badge is mounted by the layout
 * and therefore lives for the whole session; without sharing, every route change
 * that remounted the layout's children would have re-asked the API for a count
 * that changes on the scale of minutes.
 *
 * State goes through `useState` so the value survives navigation and is not
 * duplicated per component instance. The request itself is client-only: a badge
 * is not worth delaying server-rendered HTML for, and it needs the access token.
 */
import { computed } from 'vue'
import { useApiClient } from '~/utils/api-registry'
import { usePermission } from '~/composables/usePermission'

interface StockHealth {
  out: number
  low: number
  healthy: number
  untracked: number
}

/** How long a count may be trusted before it is worth asking again. */
const STALE_AFTER_MS = 2 * 60 * 1000

export function useAdminPulse() {
  const stock = useState<StockHealth | null>('admin-pulse-stock', () => null)
  const fetchedAt = useState<number>('admin-pulse-at', () => 0)
  const inFlight = useState<boolean>('admin-pulse-loading', () => false)

  const { can } = usePermission()

  /** Out of stock plus low stock: both need a buying decision today. */
  const alertCount = computed(() => (stock.value?.out ?? 0) + (stock.value?.low ?? 0))

  /** Three digits in a 20px circle is a smudge, so it stops at 99. */
  const alertBadge = computed(() =>
    alertCount.value > 99 ? '99+' : String(alertCount.value),
  )

  async function refresh(force = false): Promise<void> {
    if (!import.meta.client) return
    if (!can('perm.admin.inventory')) return
    if (inFlight.value) return
    if (!force && Date.now() - fetchedAt.value < STALE_AFTER_MS) return

    inFlight.value = true
    try {
      // Every inventory route is mounted under `admin/`. This said
      // `/inventory/health/` and 404'd on every admin page for as long as it
      // existed — invisibly, because the catch below is deliberately quiet.
      stock.value = await useApiClient().get<StockHealth>('/admin/inventory/health/')
      fetchedAt.value = Date.now()
    }
    catch (error) {
      // A badge that cannot be read is a badge that is not shown: failing loudly
      // here would put an error toast on every screen in the dashboard.
      //
      // But silent is not the same as invisible. This swallow is exactly what
      // let a typo'd path 404 on every page without anyone noticing, so in
      // development it still says so.
      if (import.meta.dev) console.warn('[admin-pulse] stock health unavailable', error)
    }
    finally {
      inFlight.value = false
    }
  }

  // Kick off on first use; subsequent callers get the cached value.
  if (import.meta.client) void refresh()

  return { stock, alertCount, alertBadge, refresh }
}
