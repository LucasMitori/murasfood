/**
 * Tenant store.
 *
 * The storefront's first request fetches this. Everything merchant-specific —
 * name, colours, opening hours, currency, delivery rules — comes from here, so
 * the same build serves any merchant (spec §66).
 */
import { defineStore } from 'pinia'
import type { Tenant } from '~/types/api'
import { useApiClient } from '~/utils/api-registry'

export const useTenantStore = defineStore('tenant', {
  state: (): { tenant: Tenant | null, loading: boolean, error: string | null } => ({
    tenant: null,
    loading: false,
    error: null,
  }),

  getters: {
    isLoaded: state => state.tenant !== null,
    /** Falls back to the product name until the tenant has loaded. */
    storeName: state => state.tenant?.trade_name ?? 'MurasFood',
    currency: state => state.tenant?.currency ?? 'BRL',
    locale: state => state.tenant?.locale ?? 'pt-BR',
    branding: state => state.tenant?.branding ?? null,
    delivery: state => state.tenant?.delivery ?? null,
    isOpenNow: state => state.tenant?.is_open_now ?? true,

    logoUrl(): string | null {
      return this.branding?.logo?.url ?? null
    },

    darkLogoUrl(): string | null {
      return this.branding?.logo_dark?.url ?? this.branding?.logo?.url ?? null
    },

    /** Opening hours grouped by weekday, for the footer and store page. */
    hoursByWeekday: (state) => {
      const grouped = new Map<number, Array<{ opens_at: string, closes_at: string }>>()
      for (const row of state.tenant?.business_hours ?? []) {
        if (row.is_closed) continue
        const list = grouped.get(row.weekday) ?? []
        list.push({ opens_at: row.opens_at, closes_at: row.closes_at })
        grouped.set(row.weekday, list)
      }
      return grouped
    },
  },

  actions: {
    async fetch(force = false): Promise<Tenant | null> {
      if (this.tenant && !force) return this.tenant

      this.loading = true
      this.error = null
      try {
        this.tenant = await useApiClient().get<Tenant>('/tenants/current/', { anonymous: true })
        return this.tenant
      }
      catch {
        // Without a tenant the storefront has no catalog to show; the layout
        // renders an explicit error state rather than an empty shell.
        this.error = 'TENANT_NOT_RESOLVED'
        return null
      }
      finally {
        this.loading = false
      }
    },
  },
})
