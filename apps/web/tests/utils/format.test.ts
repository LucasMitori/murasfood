/**
 * Display formatting helpers.
 */
import { describe, expect, it } from 'vitest'
import {
  buildSrcSet,
  formatMinutes,
  formatPhone,
  formatPostalCode,
  initials,
  orderStatusColor,
  orderStatusIcon,
  truncate,
} from '../../app/utils/format'

describe('formatMinutes', () => {
  it('renders minutes under an hour', () => {
    expect(formatMinutes(45)).toBe('45 min')
  })

  it('renders whole hours', () => {
    expect(formatMinutes(120)).toBe('2 h')
  })

  it('renders hours and minutes', () => {
    expect(formatMinutes(75)).toBe('1 h 15 min')
  })

  it('renders a dash for missing values', () => {
    expect(formatMinutes(null)).toBe('—')
    expect(formatMinutes(0)).toBe('—')
  })
})

describe('formatPostalCode', () => {
  it('masks eight digits', () => {
    expect(formatPostalCode('01001000')).toBe('01001-000')
  })

  it('strips existing punctuation before masking', () => {
    expect(formatPostalCode('01001-000')).toBe('01001-000')
  })

  it('returns the input unchanged when it is not a CEP', () => {
    expect(formatPostalCode('123')).toBe('123')
  })
})

describe('formatPhone', () => {
  it('masks a mobile number', () => {
    expect(formatPhone('11987654321')).toBe('(11) 98765-4321')
  })

  it('masks a landline', () => {
    expect(formatPhone('1133334444')).toBe('(11) 3333-4444')
  })

  it('leaves other lengths alone', () => {
    expect(formatPhone('12345')).toBe('12345')
  })
})

describe('truncate', () => {
  it('leaves short text alone', () => {
    expect(truncate('curto', 20)).toBe('curto')
  })

  it('cuts at a word boundary', () => {
    expect(truncate('um texto bastante longo para caber', 20)).toBe('um texto bastante…')
  })
})

describe('initials', () => {
  it('takes the first and last name', () => {
    expect(initials('Carlos Cliente')).toBe('CC')
  })

  it('takes two letters from a single name', () => {
    expect(initials('Carlos')).toBe('CA')
  })

  it('falls back for empty input', () => {
    expect(initials('   ')).toBe('?')
  })
})

describe('buildSrcSet', () => {
  it('orders variants by width', () => {
    const srcset = buildSrcSet({
      medium: 'https://cdn.test/m.webp',
      thumbnail: 'https://cdn.test/t.webp',
      large: 'https://cdn.test/l.webp',
    })

    expect(srcset).toBe(
      'https://cdn.test/t.webp 160w, https://cdn.test/m.webp 640w, https://cdn.test/l.webp 1280w',
    )
  })

  it('returns an empty string when processing has not run yet', () => {
    expect(buildSrcSet(undefined)).toBe('')
    expect(buildSrcSet({})).toBe('')
  })

  it('ignores unknown variant names', () => {
    expect(buildSrcSet({ mystery: 'https://cdn.test/x.webp' })).toBe('')
  })
})

describe('order status presentation', () => {
  it('pairs each status with a colour and an icon', () => {
    // Colour is never the only signal, so both must resolve (spec §57).
    for (const status of ['PAID', 'CANCELLED', 'PREPARING', 'DELIVERED']) {
      expect(orderStatusColor(status)).not.toBe('')
      expect(orderStatusIcon(status)).toMatch(/^mdi-/)
    }
  })

  it('falls back for an unknown status', () => {
    expect(orderStatusColor('SOMETHING_NEW')).toBe('secondary')
    expect(orderStatusIcon('SOMETHING_NEW')).toBe('mdi-information-outline')
  })

  it('distinguishes success from failure', () => {
    expect(orderStatusColor('COMPLETED')).toBe('success')
    expect(orderStatusColor('CANCELLED')).toBe('error')
  })
})
