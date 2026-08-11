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
    // A soft grey-white rather than a pink-tinted one. The wine below is
    // saturated enough that a warm background would fight it; a near-neutral
    // grey lets the red be the only colour on the page that raises its voice.
    background: '#F6F4F3',
    surface: '#FFFFFF',
    'surface-bright': '#FFFFFF',
    'surface-variant': '#EDE9E8',
    'on-surface-variant': '#57504F',

    // Deep and unmistakably red. The previous tone was desaturated far enough
    // to read brown against white.
    primary: '#8C1425',
    'primary-darken-1': '#6D0E1B',
    secondary: '#211E1F',
    'secondary-darken-1': '#131111',
    accent: '#B02233',

    'on-background': '#1F1C1D',
    'on-surface': '#1F1C1D',
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
    'border-color': '#E2DBDA',
    'border-opacity': 1,
    'high-emphasis-opacity': 0.92,
    'medium-emphasis-opacity': 0.68,
    'disabled-opacity': 0.38,
  },
}

export const darkTheme: ThemeDefinition = {
  dark: true,
  colors: {
    background: '#0A0A0B',
    surface: '#141315',
    'surface-bright': '#1C1A1D',
    'surface-variant': '#221F22',
    'on-surface-variant': '#C6BFC1',

    /*
     * The same red, raised in value rather than kept dark.
     *
     * A wine as deep as the light theme's would be nearly invisible against
     * near-black, and `primary` is used for text as well as fills. Lifting it
     * keeps the brand hue while clearing AA against the background; the dark
     * `on-primary` below then clears AA in the other direction, on buttons.
     */
    primary: '#E2495D',
    'primary-darken-1': '#C22A3C',
    secondary: '#F5F2F2',
    'secondary-darken-1': '#D8D2D3',
    accent: '#F2637A',

    'on-background': '#F3F0F0',
    'on-surface': '#F3F0F0',
    'on-primary': '#1F060B',
    'on-secondary': '#141315',
    'on-accent': '#1F060B',

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
    'border-color': '#332E31',
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
