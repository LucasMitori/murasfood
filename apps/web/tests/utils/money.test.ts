/**
 * Money handling on the client.
 *
 * The point of these tests is that prices never go through binary floating
 * point: `19.99 * 3` must be `59.97`, not `59.97000000000001`.
 */
import { describe, expect, it } from 'vitest'
import {
  amountToFreeDelivery,
  discountPercentage,
  formatCurrency,
  formatQuantity,
  fromCents,
  multiply,
  normalizeQuantity,
  sum,
  toCents,
} from '../../app/utils/money'

describe('toCents', () => {
  it('parses a two-decimal amount', () => {
    expect(toCents('12.34')).toBe(1234)
  })

  it('pads a single decimal', () => {
    expect(toCents('12.5')).toBe(1250)
  })

  it('handles a whole number', () => {
    expect(toCents('12')).toBe(1200)
  })

  it('accepts a comma as the decimal separator', () => {
    expect(toCents('12,34')).toBe(1234)
  })

  it('handles negative amounts', () => {
    expect(toCents('-12.34')).toBe(-1234)
  })

  it('returns zero for junk rather than NaN', () => {
    expect(toCents('abc')).toBe(0)
    expect(toCents(null)).toBe(0)
    expect(toCents(undefined)).toBe(0)
    expect(toCents('')).toBe(0)
  })

  it('truncates beyond two decimals', () => {
    expect(toCents('12.999')).toBe(1299)
  })
})

describe('fromCents', () => {
  it('renders a two-decimal string', () => {
    expect(fromCents(1234)).toBe('12.34')
  })

  it('pads a single cent', () => {
    expect(fromCents(5)).toBe('0.05')
  })

  it('keeps the sign', () => {
    expect(fromCents(-1234)).toBe('-12.34')
  })

  it('round-trips through toCents', () => {
    for (const amount of ['0.01', '9.99', '1234.56']) {
      expect(fromCents(toCents(amount))).toBe(amount)
    }
  })
})

describe('multiply', () => {
  it('avoids floating-point drift', () => {
    // 19.99 * 3 in IEEE-754 is 59.97000000000001.
    expect(multiply('19.99', 3)).toBe('59.97')
  })

  it('handles fractional weight', () => {
    expect(multiply('16.50', '1.350')).toBe('22.28')
  })

  it('returns zero for a zero quantity', () => {
    expect(multiply('10.00', 0)).toBe('0.00')
  })
})

describe('sum', () => {
  it('adds amounts exactly', () => {
    expect(sum(['0.10', '0.20'])).toBe('0.30')
  })

  it('ignores null entries', () => {
    expect(sum(['1.00', null, undefined, '2.50'])).toBe('3.50')
  })

  it('returns zero for an empty list', () => {
    expect(sum([])).toBe('0.00')
  })
})

describe('formatCurrency', () => {
  it('formats Brazilian reais', () => {
    // Intl separates the symbol from the number with U+00A0; normalise it so
    // the assertion does not hinge on an invisible character.
    const formatted = formatCurrency('12.90', 'BRL', 'pt-BR').replace(/\s/g, ' ')
    expect(formatted).toBe('R$ 12,90')
  })

  it('formats US dollars', () => {
    expect(formatCurrency('12.90', 'USD', 'en-US')).toBe('$12.90')
  })

  it('falls back gracefully on an unknown currency', () => {
    expect(formatCurrency('12.90', 'NOT-A-CURRENCY', 'pt-BR')).toContain('12.90')
  })

  it('renders null as zero rather than crashing', () => {
    expect(formatCurrency(null, 'BRL', 'pt-BR')).toContain('0,00')
  })
})

describe('formatQuantity', () => {
  it('drops decimals for whole units', () => {
    expect(formatQuantity(2, 'un', 'pt-BR')).toBe('2 un')
  })

  it('keeps fractional weight', () => {
    expect(formatQuantity('1.35', 'kg', 'pt-BR')).toBe('1,35 kg')
  })

  it('omits the unit when none is given', () => {
    expect(formatQuantity(3, '', 'pt-BR')).toBe('3')
  })
})

describe('discountPercentage', () => {
  it('computes a whole percentage', () => {
    expect(discountPercentage('100.00', '80.00')).toBe(20)
  })

  it('returns zero when there is no discount', () => {
    expect(discountPercentage('100.00', '100.00')).toBe(0)
    expect(discountPercentage('100.00', '120.00')).toBe(0)
  })

  it('returns zero for a missing base price', () => {
    expect(discountPercentage(null, '80.00')).toBe(0)
  })
})

describe('amountToFreeDelivery', () => {
  it('reports what is still missing', () => {
    expect(amountToFreeDelivery('80.00', '120.00')).toBe('40.00')
  })

  it('returns null once the threshold is reached', () => {
    expect(amountToFreeDelivery('120.00', '120.00')).toBeNull()
  })

  it('returns null when no threshold is configured', () => {
    expect(amountToFreeDelivery('80.00', null)).toBeNull()
  })
})

describe('normalizeQuantity', () => {
  it('rounds to the unit step', () => {
    expect(normalizeQuantity(1.37, { step: 0.1, precision: 3 })).toBe(1.4)
  })

  it('keeps whole units whole', () => {
    expect(normalizeQuantity(2.6, { step: 1, precision: 0 })).toBe(3)
  })

  it('clamps to the minimum', () => {
    expect(normalizeQuantity(-5, { step: 1, precision: 0, min: 1 })).toBe(1)
  })

  it('clamps to the maximum', () => {
    expect(normalizeQuantity(50, { step: 1, precision: 0, max: 10 })).toBe(10)
  })
})
