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

/**
 * Every translation key the source actually asks for must exist.
 *
 * Parity between the locale files says they agree with each other; it says
 * nothing about whether they agree with the code. `admin.period` shipped as a
 * string label while the dashboard called `t('admin.period.today')` on it,
 * treating a string as a namespace — identical in all three files, wrong in all
 * three, and invisible to a parity check. The interface rendered the raw key
 * path and only a console warning said so.
 *
 * Only statically analysable calls are checked: a key built at runtime cannot
 * be resolved from the source, so those are skipped rather than guessed at.
 */
describe('translation keys used in source', () => {
  const srcDir = fileURLToPath(new URL('../../app', import.meta.url))

  function sourceFiles(dir: string): string[] {
    return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
      const full = path.join(dir, entry.name)
      if (entry.isDirectory()) return sourceFiles(full)
      return /\.(vue|ts)$/.test(entry.name) ? [full] : []
    })
  }

  /** `t('a.b.c')` and `$t("a.b.c")` with a plain literal argument. */
  const CALL = /\$?\bt\(\s*(['"])([A-Za-z][\w.]*)\1/g

  it('resolve in every locale', () => {
    const messages = Object.fromEntries(LOCALES.map(l => [l, load(l)]))
    const known = Object.fromEntries(
      LOCALES.map(l => [l, new Set(keyPaths(messages[l]!))]),
    )

    const missing: string[] = []

    for (const file of sourceFiles(srcDir)) {
      const source = fs.readFileSync(file, 'utf8')
      const relative = path.relative(srcDir, file)

      for (const match of source.matchAll(CALL)) {
        const key = match[2]!

        // Keys with no dot are usually a local variable named `t`, not a
        // namespace path; and a bare word is rarely a real key.
        if (!key.includes('.')) continue

        for (const locale of LOCALES) {
          if (!known[locale]!.has(key)) missing.push(`${relative}: ${key} (${locale})`)
        }
      }
    }

    expect(missing, `Translation keys used in source but absent:\n${missing.join('\n')}`)
      .toEqual([])
  })
})
