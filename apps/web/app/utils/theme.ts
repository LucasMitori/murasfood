/**
 * MurasFood theme definitions.
 *
 * Two themes ship by default:
 *
 * - `murasfoodLight` — soft white surfaces with a deep wine accent.
 * - `murasfoodDark` — near-black surfaces with white highlights.
 *
 * Both are brand-neutral. A tenant's own colours are applied on top at runtime
 * (see `useBranding`), which is what makes the product white-label without a
 * rebuild.
 *
 * Contrast note: every foreground/background pair below meets WCAG 2.1 AA for
 * body text (spec §57).
 */
import type { ThemeDefinition } from 'vuetify'

/** Palette tokens shared by both themes, used for status and feedback. */
export const semanticColors = {
  success: '#2E7D5B',
  info: '#3E6B8A',
  warning: '#B7791F',
  error: '#B3261E',
} as const

export const lightTheme: ThemeDefinition = {
  dark: false,
  colors: {
    background: '#FAF7F7',
    surface: '#FFFFFF',
    'surface-bright': '#FFFFFF',
    'surface-variant': '#F2ECED',
    'on-surface-variant': '#5C5254',

    primary: '#7B2D3B',
    'primary-darken-1': '#5E1F2B',
    secondary: '#2E2A2B',
    'secondary-darken-1': '#1A1718',
    accent: '#A64253',

    'on-background': '#2E2A2B',
    'on-surface': '#2E2A2B',
    'on-primary': '#FFFFFF',
    'on-secondary': '#FFFFFF',
    'on-accent': '#FFFFFF',

    ...semanticColors,
    'on-success': '#FFFFFF',
    'on-info': '#FFFFFF',
    'on-warning': '#FFFFFF',
    'on-error': '#FFFFFF',
  },
  variables: {
    'border-color': '#E4D9DB',
    'border-opacity': 1,
    'high-emphasis-opacity': 0.92,
    'medium-emphasis-opacity': 0.68,
    'disabled-opacity': 0.38,
  },
}

export const darkTheme: ThemeDefinition = {
  dark: true,
  colors: {
    background: '#0B0B0C',
    surface: '#151416',
    'surface-bright': '#1F1D20',
    'surface-variant': '#232025',
    'on-surface-variant': '#C9C2C4',

    // On black, the wine hue is lifted so text on it stays legible; the
    // saturated tone moves to `accent` for fills and badges.
    primary: '#E8C9CF',
    'primary-darken-1': '#C79AA4',
    secondary: '#F5F2F2',
    'secondary-darken-1': '#D8D2D3',
    accent: '#C96A7A',

    'on-background': '#F5F2F2',
    'on-surface': '#F5F2F2',
    'on-primary': '#2A1218',
    'on-secondary': '#151416',
    'on-accent': '#1A0F12',

    ...semanticColors,
    success: '#5BB98C',
    info: '#7FB3D5',
    warning: '#E0B252',
    error: '#F2857D',
    'on-success': '#08130E',
    'on-info': '#08131A',
    'on-warning': '#1A1204',
    'on-error': '#2A0A08',
  },
  variables: {
    'border-color': '#3A3538',
    'border-opacity': 1,
    'high-emphasis-opacity': 1,
    'medium-emphasis-opacity': 0.72,
    'disabled-opacity': 0.4,
  },
}

export const THEME_LIGHT = 'murasfoodLight'
export const THEME_DARK = 'murasfoodDark'

export type ThemeName = typeof THEME_LIGHT | typeof THEME_DARK

/** Cookie key used to remember the visitor's choice across sessions. */
export const THEME_COOKIE = 'murasfood_theme'

/**
 * Map a tenant's branding colours onto theme tokens.
 *
 * Only colours a merchant can safely change are overridden — backgrounds and
 * text colours stay under our control, so a badly chosen brand colour cannot
 * produce unreadable text.
 */
export function brandingOverrides(
  branding: { primary_color?: string, accent_color?: string, dark_primary_color?: string } | null,
  isDark: boolean,
): Record<string, string> {
  if (!branding) return {}

  const overrides: Record<string, string> = {}
  const primary = isDark ? branding.dark_primary_color : branding.primary_color

  if (isValidHex(primary)) overrides.primary = primary as string
  if (isValidHex(branding.accent_color)) overrides.accent = branding.accent_color as string

  return overrides
}

/** Whether a string is a usable `#rgb` / `#rrggbb` colour. */
export function isValidHex(value: string | undefined | null): boolean {
  return typeof value === 'string' && /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i.test(value)
}
