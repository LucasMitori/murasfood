/**
 * Theme definitions and tenant branding overrides.
 *
 * The contrast assertions guard the promise in the palette's docstring: a
 * merchant's brand colour may change the accent, but never make text
 * unreadable.
 */
import { describe, expect, it } from 'vitest'
import { brandingOverrides, darkTheme, isValidHex, lightTheme } from '../../app/utils/theme'

/** Relative luminance per WCAG 2.1. */
function luminance(hex: string): number {
  const value = hex.replace('#', '')
  const full = value.length === 3 ? value.split('').map(c => c + c).join('') : value
  const channels = [0, 2, 4].map((offset) => {
    const channel = Number.parseInt(full.slice(offset, offset + 2), 16) / 255
    return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * channels[0]! + 0.7152 * channels[1]! + 0.0722 * channels[2]!
}

function contrastRatio(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (light! + 0.05) / (dark! + 0.05)
}

describe('light theme', () => {
  it('is a light theme', () => {
    expect(lightTheme.dark).toBe(false)
  })

  it('uses a soft grey-white ground under a deep red wine', () => {
    expect(lightTheme.colors?.background).toBe('#F6F4F3')
    expect(lightTheme.colors?.primary).toBe('#8C1425')
  })

  it('meets AA contrast for body text on the background', () => {
    const ratio = contrastRatio(lightTheme.colors!['on-background']!, lightTheme.colors!.background!)
    expect(ratio).toBeGreaterThanOrEqual(4.5)
  })

  it('meets AA contrast for text on the primary colour', () => {
    const ratio = contrastRatio(lightTheme.colors!['on-primary']!, lightTheme.colors!.primary!)
    expect(ratio).toBeGreaterThanOrEqual(4.5)
  })

  it('meets AA contrast for primary-coloured text on the page', () => {
    // `primary` is used for links and text, not only for filled buttons, so it
    // has to clear AA against the background as well as against `on-primary`.
    const ratio = contrastRatio(lightTheme.colors!.primary!, lightTheme.colors!.background!)
    expect(ratio).toBeGreaterThanOrEqual(4.5)
  })

  it('meets AA contrast for muted text on tinted surfaces', () => {
    const ratio = contrastRatio(
      lightTheme.colors!['on-surface-variant']!,
      lightTheme.colors!['surface-variant']!,
    )
    expect(ratio).toBeGreaterThanOrEqual(4.5)
  })
})

describe('dark theme', () => {
  it('is a dark theme on near-black surfaces', () => {
    expect(darkTheme.dark).toBe(true)
    expect(darkTheme.colors?.background).toBe('#0A0A0B')
  })

  it('highlights in near-white', () => {
    expect(darkTheme.colors?.secondary).toBe('#F5F2F2')
    expect(darkTheme.colors?.['on-background']).toBe('#F3F0F0')
  })

  it('keeps the red readable against near-black', () => {
    // The dark theme lifts the wine rather than darkening it: a colour deep
    // enough for white paper disappears against black, and `primary` is used
    // for text here too.
    const ratio = contrastRatio(darkTheme.colors!.primary!, darkTheme.colors!.background!)
    expect(ratio).toBeGreaterThanOrEqual(4.5)
  })

  it('keeps the red readable on raised surfaces too', () => {
    const ratio = contrastRatio(darkTheme.colors!.primary!, darkTheme.colors!.surface!)
    expect(ratio).toBeGreaterThanOrEqual(4.5)
  })

  it('meets AA contrast for body text on the background', () => {
    const ratio = contrastRatio(darkTheme.colors!['on-background']!, darkTheme.colors!.background!)
    expect(ratio).toBeGreaterThanOrEqual(4.5)
  })

  it('meets AA contrast for text on the primary colour', () => {
    const ratio = contrastRatio(darkTheme.colors!['on-primary']!, darkTheme.colors!.primary!)
    expect(ratio).toBeGreaterThanOrEqual(4.5)
  })
})

describe('isValidHex', () => {
  it('accepts three- and six-digit hex', () => {
    expect(isValidHex('#fff')).toBe(true)
    expect(isValidHex('#7B2D3B')).toBe(true)
  })

  it('rejects anything else', () => {
    expect(isValidHex('7B2D3B')).toBe(false)
    expect(isValidHex('rgb(0,0,0)')).toBe(false)
    expect(isValidHex('')).toBe(false)
    expect(isValidHex(undefined)).toBe(false)
  })
})

describe('brandingOverrides', () => {
  const branding = {
    primary_color: '#123456',
    accent_color: '#654321',
    dark_primary_color: '#ABCDEF',
  }

  it('uses the light primary in light mode', () => {
    expect(brandingOverrides(branding, false)).toEqual({ primary: '#123456', accent: '#654321' })
  })

  it('uses the dark primary in dark mode', () => {
    expect(brandingOverrides(branding, true)).toEqual({ primary: '#ABCDEF', accent: '#654321' })
  })

  it('ignores invalid colours instead of breaking the theme', () => {
    expect(brandingOverrides({ primary_color: 'not-a-colour', accent_color: '#000' }, false))
      .toEqual({ accent: '#000' })
  })

  it('never overrides background or text tokens', () => {
    // A merchant cannot make their own storefront unreadable.
    const overrides = brandingOverrides(branding, false)
    expect(Object.keys(overrides)).toEqual(['primary', 'accent'])
  })

  it('returns nothing without branding', () => {
    expect(brandingOverrides(null, false)).toEqual({})
  })
})
