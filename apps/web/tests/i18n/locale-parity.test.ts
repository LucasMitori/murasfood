// @vitest-environment node
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

/**
 * The three locales must carry exactly the same keys.
 *
 * A key added to `pt-BR` but not `en` does not fail the build or the types —
 * it renders as the raw key path in the interface, in production, only for the
 * users on that language. Comparing the key sets is the only thing that
 * notices.
 */

const localesDir = fileURLToPath(new URL('../../i18n/locales', import.meta.url))
const LOCALES = ['pt-BR', 'en', 'es'] as const
const REFERENCE = 'pt-BR'

type Messages = { [key: string]: string | Messages }

function load(locale: string): Messages {
  return JSON.parse(fs.readFileSync(path.join(localesDir, `${locale}.json`), 'utf8'))
}

/** Flatten to dotted paths so the comparison reports a usable location. */
function keyPaths(messages: Messages, prefix = ''): string[] {
  return Object.entries(messages).flatMap(([key, value]) => {
    const full = prefix ? `${prefix}.${key}` : key
    return typeof value === 'string' ? [full] : keyPaths(value, full)
  })
}

const reference = keyPaths(load(REFERENCE)).sort()

describe('locale parity', () => {
  it('has a meaningful number of keys', () => {
    expect(reference.length).toBeGreaterThan(200)
  })

  for (const locale of LOCALES.filter(l => l !== REFERENCE)) {
    describe(locale, () => {
      const keys = keyPaths(load(locale)).sort()

      it(`defines every key ${REFERENCE} defines`, () => {
        expect(reference.filter(key => !keys.includes(key))).toEqual([])
      })

      it(`defines no key ${REFERENCE} lacks`, () => {
        expect(keys.filter(key => !reference.includes(key))).toEqual([])
      })

      it('leaves no value blank', () => {
        const messages = load(locale)
        const blank = keys.filter((key) => {
          const value = key.split('.').reduce<unknown>(
            (node, part) => (node as Messages | undefined)?.[part],
            messages,
          )
          return typeof value !== 'string' || value.trim() === ''
        })

        expect(blank).toEqual([])
      })
    })
  }
})
