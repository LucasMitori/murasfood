/**
 * Form validation rules.
 *
 * Rules must fail *closed* on genuinely empty input and stay quiet on values
 * that only look empty — zero and `false` are answers, not omissions.
 */
import { describe, expect, it } from 'vitest'
import type { FormField } from '../../app/types/ui'
import {
  accepted,
  email,
  hexColor,
  isBlank,
  matches,
  maxLength,
  maxValue,
  minLength,
  minValue,
  numeric,
  phone,
  postalCode,
  required,
  rulesForField,
  toNumber,
  url,
} from '../../app/utils/validation'

/** Echoes the key so assertions can identify which rule fired. */
const t = (key: string, params?: Record<string, unknown>): string =>
  params ? `${key}:${JSON.stringify(params)}` : key

describe('isBlank', () => {
  it('treats null, undefined and whitespace as blank', () => {
    expect(isBlank(null)).toBe(true)
    expect(isBlank(undefined)).toBe(true)
    expect(isBlank('')).toBe(true)
    expect(isBlank('   ')).toBe(true)
    expect(isBlank([])).toBe(true)
  })

  it('does not treat zero or false as blank', () => {
    // A price of 0 and a switch set to "no" are real answers.
    expect(isBlank(0)).toBe(false)
    expect(isBlank(false)).toBe(false)
  })
})

describe('required', () => {
  const rule = required(t)

  it('rejects empty input', () => {
    expect(rule('')).toBe('validation.required')
    expect(rule(null)).toBe('validation.required')
    expect(rule([])).toBe('validation.required')
  })

  it('accepts zero', () => {
    expect(rule(0)).toBe(true)
  })

  it('rejects an unticked required switch', () => {
    expect(rule(false)).toBe('validation.required')
  })

  it('accepts real values', () => {
    expect(rule('Arroz')).toBe(true)
    expect(rule(['a'])).toBe(true)
  })
})

describe('format rules', () => {
  it('validates email addresses', () => {
    expect(email(t)('cliente@example.test')).toBe(true)
    expect(email(t)('not-an-email')).toBe('validation.email')
    // Empty is the `required` rule's business, not this one's.
    expect(email(t)('')).toBe(true)
  })

  it('requires an absolute http(s) URL', () => {
    expect(url(t)('https://example.test/a')).toBe(true)
    expect(url(t)('example.test')).toBe('validation.url')
  })

  it('validates Brazilian postal codes with or without punctuation', () => {
    expect(postalCode(t)('01001000')).toBe(true)
    expect(postalCode(t)('01001-000')).toBe(true)
    expect(postalCode(t)('123')).toBe('validation.postalCode')
  })

  it('validates phone numbers by digit count', () => {
    expect(phone(t)('(11) 98765-4321')).toBe(true)
    expect(phone(t)('123')).toBe('validation.phone')
  })

  it('validates hexadecimal colours', () => {
    expect(hexColor(t)('#7B2D3B')).toBe(true)
    expect(hexColor(t)('#fff')).toBe(true)
    expect(hexColor(t)('wine')).toBe('validation.hexColor')
  })

  it('validates numbers, accepting a comma separator', () => {
    expect(numeric(t)('12.50')).toBe(true)
    expect(numeric(t)('12,50')).toBe(true)
    expect(numeric(t)('abc')).toBe('validation.numeric')
  })
})

describe('bounds', () => {
  it('checks string length', () => {
    expect(minLength(t, 8)('short')).toContain('validation.minLength')
    expect(minLength(t, 8)('long enough')).toBe(true)
    expect(maxLength(t, 5)('too long')).toContain('validation.maxLength')
  })

  it('checks numeric bounds', () => {
    expect(minValue(t, 0)('-1')).toContain('validation.minValue')
    expect(minValue(t, 0)('0')).toBe(true)
    expect(maxValue(t, 100)('101')).toContain('validation.maxValue')
  })

  it('ignores blank values so bounds do not double as required', () => {
    expect(minValue(t, 10)('')).toBe(true)
    expect(maxLength(t, 3)('')).toBe(true)
  })
})

describe('cross-field rules', () => {
  it('confirms a value matches another field', () => {
    expect(matches(t, () => 'secret')('secret')).toBe(true)
    expect(matches(t, () => 'secret')('different')).toBe('validation.passwordMismatch')
  })

  it('requires a terms checkbox to be ticked', () => {
    expect(accepted(t)(true)).toBe(true)
    expect(accepted(t)(false)).toBe('validation.acceptTerms')
  })
})

describe('rulesForField', () => {
  function run(field: FormField, value: unknown): Array<true | string> {
    return rulesForField(field, t).map(rule => rule(value))
  }

  it('derives a required rule', () => {
    const results = run({ name: 'name', type: 'text', required: true }, '')
    expect(results).toContain('validation.required')
  })

  it('derives a format rule from the field type', () => {
    expect(run({ name: 'email', type: 'email' }, 'nope')).toContain('validation.email')
  })

  it('uses the accepted rule for a required checkbox', () => {
    // A required checkbox means "must be ticked", not "must have a value".
    expect(run({ name: 'terms', type: 'checkbox', required: true }, false))
      .toContain('validation.acceptTerms')
  })

  it('derives bounds from min, max and maxLength', () => {
    const field: FormField = { name: 'price', type: 'money', min: 0, max: 10, maxLength: 4 }
    expect(run(field, '-1').some(result => String(result).startsWith('validation.minValue'))).toBe(true)
    expect(run(field, '11').some(result => String(result).startsWith('validation.maxValue'))).toBe(true)
  })

  it('appends custom rules after the derived ones', () => {
    const custom = () => 'custom.error' as const
    const results = run({ name: 'x', type: 'text', rules: [custom] }, 'anything')
    expect(results).toContain('custom.error')
  })

  it('adds no rules to a plain optional text field', () => {
    expect(rulesForField({ name: 'note', type: 'text' }, t)).toHaveLength(0)
  })
})

describe('toNumber', () => {
  it('parses both decimal separators', () => {
    expect(toNumber('12.5')).toBe(12.5)
    expect(toNumber('12,5')).toBe(12.5)
    expect(toNumber(12.5)).toBe(12.5)
  })

  it('returns null for anything unparsable', () => {
    expect(toNumber('abc')).toBeNull()
    expect(toNumber('')).toBeNull()
    expect(toNumber(null)).toBeNull()
    expect(toNumber(Number.NaN)).toBeNull()
  })
})
