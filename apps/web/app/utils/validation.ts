/**
 * Validation rule factories.
 *
 * Rules return `true` or a message, which is what Vuetify's `rules` prop
 * expects. Every message arrives already translated — the factories take a
 * translator so no copy lives in this module and every form speaks the user's
 * language.
 *
 * Client validation is a courtesy, not a control. The API validates everything
 * again, and its field errors are merged into the same display slots.
 */
import type { FormField, ValidationRule } from '~/types/ui'

/** Minimal shape of vue-i18n's `t`, so this module does not import the runtime. */
export type Translate = (key: string, params?: Record<string, unknown>) => string

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/
const URL_PATTERN = /^https?:\/\/\S+$/i
const HEX_COLOR_PATTERN = /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i

/** Whether a value counts as "not filled in". */
export function isBlank(value: unknown): boolean {
  if (value === null || value === undefined) return true
  if (typeof value === 'string') return value.trim() === ''
  if (Array.isArray(value)) return value.length === 0
  return false
}

export function required(t: Translate): ValidationRule {
  return (value) => {
    // `false` is a legitimate answer for a switch, but not for a required one.
    if (value === false) return t('validation.required')
    // Zero is a real value; only genuinely empty input fails.
    return isBlank(value) ? t('validation.required') : true
  }
}

export function email(t: Translate): ValidationRule {
  return value => (isBlank(value) || EMAIL_PATTERN.test(String(value)) ? true : t('validation.email'))
}

export function url(t: Translate): ValidationRule {
  return value => (isBlank(value) || URL_PATTERN.test(String(value)) ? true : t('validation.url'))
}

export function minLength(t: Translate, min: number): ValidationRule {
  return value =>
    isBlank(value) || String(value).length >= min ? true : t('validation.minLength', { min })
}

export function maxLength(t: Translate, max: number): ValidationRule {
  return value =>
    isBlank(value) || String(value).length <= max ? true : t('validation.maxLength', { max })
}

export function minValue(t: Translate, min: number): ValidationRule {
  return (value) => {
    if (isBlank(value)) return true
    const numeric = toNumber(value)
    return numeric === null || numeric >= min ? true : t('validation.minValue', { min })
  }
}

export function maxValue(t: Translate, max: number): ValidationRule {
  return (value) => {
    if (isBlank(value)) return true
    const numeric = toNumber(value)
    return numeric === null || numeric <= max ? true : t('validation.maxValue', { max })
  }
}

export function numeric(t: Translate): ValidationRule {
  return value => (isBlank(value) || toNumber(value) !== null ? true : t('validation.numeric'))
}

/** Brazilian postal code: eight digits, punctuation optional. */
export function postalCode(t: Translate): ValidationRule {
  return (value) => {
    if (isBlank(value)) return true
    return String(value).replace(/\D/g, '').length === 8 ? true : t('validation.postalCode')
  }
}

export function phone(t: Translate): ValidationRule {
  return (value) => {
    if (isBlank(value)) return true
    const digits = String(value).replace(/\D/g, '').length
    return digits >= 10 && digits <= 13 ? true : t('validation.phone')
  }
}

export function hexColor(t: Translate): ValidationRule {
  return value =>
    isBlank(value) || HEX_COLOR_PATTERN.test(String(value)) ? true : t('validation.hexColor')
}

/** Confirms a value matches another field, for password confirmation. */
export function matches(t: Translate, other: () => unknown): ValidationRule {
  return value => (value === other() ? true : t('validation.passwordMismatch'))
}

export function accepted(t: Translate): ValidationRule {
  return value => (value === true ? true : t('validation.acceptTerms'))
}

/**
 * Build the rule list for a field from its own definition.
 *
 * Deriving rules from `required`, `min`, `max` and `type` keeps a schema
 * declarative: a field says what it is, not how to police it.
 */
export function rulesForField(field: FormField, t: Translate): ValidationRule[] {
  const rules: ValidationRule[] = []

  if (field.required) {
    rules.push(field.type === 'checkbox' ? accepted(t) : required(t))
  }

  switch (field.type) {
    case 'email':
      rules.push(email(t))
      break
    case 'url':
      rules.push(url(t))
      break
    case 'tel':
      rules.push(phone(t))
      break
    case 'color':
      rules.push(hexColor(t))
      break
    case 'number':
    case 'money':
    case 'quantity':
    case 'percent':
      rules.push(numeric(t))
      break
    default:
      break
  }

  if (typeof field.min === 'number') rules.push(minValue(t, field.min))
  if (typeof field.max === 'number') rules.push(maxValue(t, field.max))
  if (typeof field.maxLength === 'number') rules.push(maxLength(t, field.maxLength))

  return [...rules, ...(field.rules ?? [])]
}

/** Parse a number from user input, tolerating a comma decimal separator. */
export function toNumber(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value !== 'string') return null

  const normalised = value.trim().replace(',', '.')
  if (normalised === '') return null

  const parsed = Number(normalised)
  return Number.isFinite(parsed) ? parsed : null
}
