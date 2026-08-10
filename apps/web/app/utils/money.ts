/**
 * Money and quantity handling on the client.
 *
 * The API sends amounts as strings and this module keeps them that way for as
 * long as possible. Where arithmetic is unavoidable — a quantity stepper, a
 * subtotal preview — it happens in integer cents, because floating-point
 * arithmetic on prices produces the classic `19.99 * 3 = 59.97000000000001`.
 *
 * The authoritative totals always come from the backend; anything computed here
 * is a preview (spec §41: never trust the frontend for money).
 */

/** Parse an API amount into integer cents. Invalid input yields 0. */
export function toCents(value: string | number | null | undefined): number {
  if (value === null || value === undefined || value === '') return 0

  const text = String(value).trim().replace(',', '.')
  const match = /^-?\d+(\.\d+)?$/.exec(text)
  if (!match) return 0

  const negative = text.startsWith('-')
  const [whole, fraction = ''] = text.replace('-', '').split('.')
  const cents = Number(whole) * 100 + Number((fraction + '00').slice(0, 2))

  return negative ? -cents : cents
}

/** Render integer cents back as a plain `"12.34"` string. */
export function fromCents(cents: number): string {
  const negative = cents < 0
  const absolute = Math.abs(Math.round(cents))
  const text = `${Math.floor(absolute / 100)}.${String(absolute % 100).padStart(2, '0')}`
  return negative ? `-${text}` : text
}

/** Multiply an amount by a quantity without floating-point drift. */
export function multiply(amount: string | number, quantity: string | number): string {
  const cents = toCents(amount)
  const units = Number(String(quantity).replace(',', '.')) || 0
  return fromCents(Math.round(cents * units))
}

/** Sum a list of API amounts. */
export function sum(amounts: Array<string | number | null | undefined>): string {
  return fromCents(amounts.reduce<number>((total, amount) => total + toCents(amount), 0))
}

/**
 * Format an amount for display in the given locale and currency.
 *
 * Falls back to a plain string when `Intl` rejects the currency code, so a
 * misconfigured tenant shows an unformatted number rather than crashing the
 * page.
 */
export function formatCurrency(
  value: string | number | null | undefined,
  currency = 'BRL',
  locale = 'pt-BR',
): string {
  const amount = toCents(value) / 100
  try {
    return new Intl.NumberFormat(locale, {
      style: 'currency',
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount)
  }
  catch {
    return `${currency} ${amount.toFixed(2)}`
  }
}

/**
 * Format a quantity with its unit, trimming meaningless trailing zeros.
 *
 * `1.350 kg` stays as typed, while `2.000 un` reads as `2 un` — nobody writes
 * "2.000 loaves".
 */
export function formatQuantity(
  quantity: string | number,
  unitCode = '',
  locale = 'pt-BR',
): string {
  const numeric = Number(String(quantity).replace(',', '.')) || 0
  const isWhole = Number.isInteger(numeric)

  const formatted = new Intl.NumberFormat(locale, {
    minimumFractionDigits: isWhole ? 0 : 1,
    maximumFractionDigits: 3,
  }).format(numeric)

  return unitCode ? `${formatted} ${unitCode}` : formatted
}

/** Percentage difference between a list price and what is charged. */
export function discountPercentage(
  basePrice: string | number | null | undefined,
  salePrice: string | number | null | undefined,
): number {
  const base = toCents(basePrice)
  const sale = toCents(salePrice)
  if (base <= 0 || sale >= base) return 0
  return Math.round(((base - sale) / base) * 100)
}

/** Amount still needed to reach a free-delivery threshold, or `null`. */
export function amountToFreeDelivery(
  subtotal: string | number,
  threshold: string | number | null | undefined,
): string | null {
  if (!threshold) return null
  const missing = toCents(threshold) - toCents(subtotal)
  return missing > 0 ? fromCents(missing) : null
}

/** Clamp a quantity to a unit's step and precision. */
export function normalizeQuantity(
  quantity: number,
  { step = 1, precision = 0, min = 0, max }: { step?: number, precision?: number, min?: number, max?: number },
): number {
  const stepped = step > 0 ? Math.round(quantity / step) * step : quantity
  const bounded = Math.min(Math.max(stepped, min), max ?? Number.MAX_SAFE_INTEGER)
  return Number(bounded.toFixed(precision))
}
