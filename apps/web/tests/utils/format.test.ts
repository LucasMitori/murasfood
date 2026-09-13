/**
 * Display formatting helpers.
 */
import { describe, expect, it } from 'vitest'
import {
  buildSrcSet,
  formatDate,
  formatDateTime,
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

  it('separates the AVIF variants from the WebP ones', () => {
    /*
     * Both formats live in one `variants` map, AVIF under a prefix, so that
     * anything reading it the old way keeps working. The two `<source>` tags
     * must therefore never mix: offering a WebP file under `type="image/avif"`
     * would make a browser decode it as AVIF and fail.
     */
    const variants = {
      small: 'https://cdn.test/s.webp',
      large: 'https://cdn.test/l.webp',
      avif_small: 'https://cdn.test/s.avif',
      avif_large: 'https://cdn.test/l.avif',
    }

    expect(buildSrcSet(variants)).toBe(
      'https://cdn.test/s.webp 320w, https://cdn.test/l.webp 1280w',
    )
    expect(buildSrcSet(variants, 'avif_')).toBe(
      'https://cdn.test/s.avif 320w, https://cdn.test/l.avif 1280w',
    )
  })

  it('ignores derivative names it does not know', () => {
    // A format added to the API later must not leak into an existing srcset
    // with an invented width.
    expect(buildSrcSet({ jxl_small: 'https://cdn.test/s.jxl' })).toBe('')
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

/**
 * Dates that arrive without a time.
 *
 * `new Date('2026-08-10')` is parsed as UTC midnight, so under any timezone
 * west of Greenwich it formats as the *previous* day. The suite runs in
 * America/Sao_Paulo (UTC-3), which is where the shops are, so these would fail
 * against the old implementation.
 *
 * It was visible in two places at once: a ledger entry from the 10th shown as
 * the 9th, and a stock batch expiring today shown as expiring yesterday.
 */
describe('formatDate', () => {
  it('keeps the day of a date-only value', () => {
    expect(formatDate('2026-08-10')).toBe('10/08/2026')
  })

  it('keeps the day at the start of a month', () => {
    // The worst case: the shift moves the month and, in January, the year.
    expect(formatDate('2026-01-01')).toBe('01/01/2026')
  })

  it('still renders a real timestamp in local time', () => {
    // 12:00 UTC is 09:00 in Sao Paulo, and stays the same day.
    expect(formatDate('2026-08-10T12:00:00Z')).toBe('10/08/2026')
  })

  it('renders a dash for missing or unparseable values', () => {
    expect(formatDate(null)).toBe('—')
    expect(formatDate('not a date')).toBe('—')
  })
})

describe('formatDateTime', () => {
  it('converts a UTC instant to local time', () => {
    expect(formatDateTime('2026-08-10T12:00:00Z')).toBe('10/08/2026, 09:00')
  })

  it('does not shift a date-only value across midnight', () => {
    expect(formatDateTime('2026-08-10')).toBe('10/08/2026, 00:00')
  })
})
