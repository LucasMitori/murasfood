/**
 * Display formatting helpers.
 *
 * None of these produce user-facing *copy* — every label goes through i18n.
 * They format values that the translation layer then places into a sentence.
 */

/** Format an ISO timestamp as a short local date. */
export function formatDate(value: string | null | undefined, locale = 'pt-BR'): string {
  if (!value) return '—'
  const date = parseDate(value)
  if (!date) return '—'
  return new Intl.DateTimeFormat(locale, { dateStyle: 'short' }).format(date)
}

/**
 * Parse a value that may be a date *or* a timestamp.
 *
 * `new Date('2026-08-10')` is parsed as UTC midnight, which in Brazil is nine
 * in the evening on the 9th — so every date-only field rendered a day early.
 * A ledger entry from the 10th read as the 9th, and a batch expiring today
 * looked like it expired yesterday.
 *
 * A date-only string carries no timezone and is not meant to be shifted by one,
 * so it is built from its parts in local time. Anything with a time in it is a
 * real instant and is left to the normal parser.
 */
function parseDate(value: string): Date | null {
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  const date = dateOnly
    ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]))
    : new Date(value)

  return Number.isNaN(date.getTime()) ? null : date
}

/**
 * Format a date as a short month and year — "ago. 2026".
 *
 * Used wherever a series is bucketed by month. Goes through `parseDate` for the
 * same reason everything else does: the API sends `2026-08-01`, and letting the
 * platform parser treat that as UTC midnight renders it as July in Brazil.
 */
export function formatMonth(value: string | null | undefined, locale = 'pt-BR'): string {
  if (!value) return '—'
  const date = parseDate(value)
  if (!date) return '—'
  return new Intl.DateTimeFormat(locale, { month: 'short', year: 'numeric' }).format(date)
}

/** Format an ISO timestamp as a local date and time. */
export function formatDateTime(value: string | null | undefined, locale = 'pt-BR'): string {
  if (!value) return '—'
  const date = parseDate(value)
  if (!date) return '—'
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
export const DERIVATIVE_WIDTHS: Record<string, number> = {
  thumbnail: 160,
  small: 320,
  medium: 640,
  large: 1280,
}

/**
 * Build a `srcset` from an asset's derivatives.
 *
 * `prefix` selects a format. The API stores AVIF under `avif_medium` and the
 * like, beside the plain WebP names, so that anything reading `variants` the
 * old way keeps working and simply ignores the extra entries.
 */
export function buildSrcSet(
  variants: Record<string, string> | undefined,
  prefix = '',
): string {
  if (!variants) return ''

  return Object.entries(variants)
    .map(([name, url]) => ({ name, url, base: prefix ? name.replace(prefix, '') : name }))
    .filter(entry => entry.name.startsWith(prefix) && entry.base in DERIVATIVE_WIDTHS)
    .sort((a, b) => DERIVATIVE_WIDTHS[a.base]! - DERIVATIVE_WIDTHS[b.base]!)
    .map(entry => `${entry.url} ${DERIVATIVE_WIDTHS[entry.base]}w`)
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

/**
 * Hand a downloaded file to the browser.
 *
 * The bytes arrive through the API client rather than as a plain link, because
 * an export needs the access token and an `<a href>` cannot carry one. That
 * leaves the file in memory, so it has to be offered as an object URL — and
 * revoked afterwards, or every export a merchant runs in a session stays held
 * until they reload the page.
 */
export function saveFile(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')

  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()

  URL.revokeObjectURL(url)
}

/**
 * How far a parallax layer may travel, given how much picture it has to spare.
 *
 * Extracted from the two components that do this because the bug it prevents
 * was invisible in review and obvious on screen: the travel used to be a
 * fraction of the *scroll distance* while the overscan was a fraction of the
 * *element height*. Those are unrelated numbers, and they disagreed — a band on
 * screen across `viewport + height` of scrolling moved its image about 303px
 * while having 74px to move within, leaving a blank strip at one edge or the
 * other for most of the scroll.
 *
 * Expressing travel as a share of the measured slack makes that impossible
 * rather than unlikely: `|shift| <= slack` always holds, so the layer's edge
 * lands at most exactly on the frame's edge.
 *
 * @param top      the element's `getBoundingClientRect().top`
 * @param height   the element's height
 * @param viewport `window.innerHeight`
 * @param slack    `(mediaHeight - height) / 2`, measured from the DOM
 */
export function parallaxShift(
  top: number,
  height: number,
  viewport: number,
  slack: number,
): number {
  // The element is on screen across this much travel of its own centre.
  const span = (viewport + height) / 2
  if (span <= 0 || slack <= 0) return 0

  const centred = top + height / 2 - viewport / 2
  const progress = Math.max(-1, Math.min(1, centred / span))

  return progress * slack
}
