/**
 * Display formatting helpers.
 *
 * None of these produce user-facing *copy* — every label goes through i18n.
 * They format values that the translation layer then places into a sentence.
 */

/** Format an ISO timestamp as a short local date. */
export function formatDate(value: string | null | undefined, locale = 'pt-BR'): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat(locale, { dateStyle: 'short' }).format(date)
}

/** Format an ISO timestamp as a local date and time. */
export function formatDateTime(value: string | null | undefined, locale = 'pt-BR'): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat(locale, { dateStyle: 'short', timeStyle: 'short' }).format(date)
}

/** Format a duration in minutes as `45 min` or `1 h 15 min`. */
export function formatMinutes(minutes: number | null | undefined): string {
  if (!minutes || minutes <= 0) return '—'
  if (minutes < 60) return `${minutes} min`

  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest ? `${hours} h ${rest} min` : `${hours} h`
}

/** Mask a Brazilian postal code as `01001-000`. */
export function formatPostalCode(value: string | null | undefined): string {
  const digits = (value ?? '').replace(/\D/g, '')
  return digits.length === 8 ? `${digits.slice(0, 5)}-${digits.slice(5)}` : (value ?? '')
}

/** Mask a Brazilian phone number for display. */
export function formatPhone(value: string | null | undefined): string {
  const digits = (value ?? '').replace(/\D/g, '')
  if (digits.length === 11) return `(${digits.slice(0, 2)}) ${digits.slice(2, 7)}-${digits.slice(7)}`
  if (digits.length === 10) return `(${digits.slice(0, 2)}) ${digits.slice(2, 6)}-${digits.slice(6)}`
  return value ?? ''
}

/** Truncate text at a word boundary, appending an ellipsis. */
export function truncate(value: string, maxLength = 80): string {
  if (value.length <= maxLength) return value
  const cut = value.slice(0, maxLength)
  const lastSpace = cut.lastIndexOf(' ')
  return `${(lastSpace > maxLength * 0.6 ? cut.slice(0, lastSpace) : cut).trimEnd()}…`
}

/** Initials for an avatar placeholder. */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase()
  return `${parts[0]![0]}${parts[parts.length - 1]![0]}`.toUpperCase()
}

/**
 * Build a responsive `srcset` from an asset's generated variants.
 *
 * Returns an empty string when no variants exist yet — image processing runs
 * asynchronously, so a freshly uploaded photo briefly has only its original.
 */
export function buildSrcSet(variants: Record<string, string> | undefined): string {
  if (!variants) return ''

  const widths: Record<string, number> = { thumbnail: 160, small: 320, medium: 640, large: 1280 }
  return Object.entries(variants)
    .filter(([name]) => name in widths)
    .sort((a, b) => widths[a[0]]! - widths[b[0]]!)
    .map(([name, url]) => `${url} ${widths[name]}w`)
    .join(', ')
}

/** Vuetify colour token for an order status chip. */
export function orderStatusColor(status: string): string {
  const map: Record<string, string> = {
    PENDING_PAYMENT: 'warning',
    PAYMENT_PROCESSING: 'info',
    PAID: 'success',
    CONFIRMED: 'success',
    PREPARING: 'info',
    READY_FOR_PICKUP: 'info',
    OUT_FOR_DELIVERY: 'info',
    DELIVERED: 'success',
    COMPLETED: 'success',
    CANCELLED: 'error',
    PAYMENT_FAILED: 'error',
    REFUNDED: 'error',
    PARTIALLY_REFUNDED: 'warning',
  }
  return map[status] ?? 'secondary'
}

/**
 * Icon paired with an order status.
 *
 * Colour alone is never the only indicator of state (spec §57) — the icon and
 * the translated label carry the same information.
 */
export function orderStatusIcon(status: string): string {
  const map: Record<string, string> = {
    PENDING_PAYMENT: 'mdi-clock-outline',
    PAYMENT_PROCESSING: 'mdi-progress-clock',
    PAID: 'mdi-check-circle-outline',
    CONFIRMED: 'mdi-check-decagram-outline',
    PREPARING: 'mdi-chef-hat',
    READY_FOR_PICKUP: 'mdi-package-variant-closed',
    OUT_FOR_DELIVERY: 'mdi-truck-delivery-outline',
    DELIVERED: 'mdi-home-check-outline',
    COMPLETED: 'mdi-check-all',
    CANCELLED: 'mdi-close-circle-outline',
    PAYMENT_FAILED: 'mdi-alert-circle-outline',
    REFUNDED: 'mdi-cash-refund',
    PARTIALLY_REFUNDED: 'mdi-cash-minus',
  }
  return map[status] ?? 'mdi-information-outline'
}
