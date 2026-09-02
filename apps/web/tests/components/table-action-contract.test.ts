// @vitest-environment node
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

/**
 * `MuraDataTable` emits its row action as one object; every handler must take
 * one object.
 *
 * This is here because the component emitted `(key, row)` while five of the six
 * screens declared `onAction(payload: { key, row })`. Their `payload` was the
 * *string*, `payload.key` was `undefined`, and not one row action in the
 * dashboard did anything — for as long as the dashboard has existed.
 *
 * Nothing caught it. Templates are written in Pug, which `vue-tsc` does not
 * type-check, so the emit signature and the handler signature were free to
 * disagree. Comparing them as text is crude, but it is the only thing standing
 * between this contract and the next silent drift.
 */

const webRoot = fileURLToPath(new URL('../..', import.meta.url))

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) walk(full, out)
    else if (entry.name.endsWith('.vue')) out.push(full)
  }
  return out
}

describe('row action contract', () => {
  const table = fs.readFileSync(
    path.join(webRoot, 'app/components/shared/MuraDataTable.vue'),
    'utf8',
  )

  it('the table emits a single object', () => {
    // `action: [payload: { key: string, row: Row }]` — one argument.
    expect(table).toMatch(/action:\s*\[payload:\s*\{[^\]]*key[^\]]*row[^\]]*\}\]/)

    for (const call of table.matchAll(/emit\(\s*'action'\s*,([^\n]*)\)/g)) {
      expect(call[1], `emit('action', ...) must pass one object: ${call[0]}`)
        .toMatch(/^\s*\{/)
    }
  })

  it('every handler destructures that object', () => {
    const offenders: string[] = []

    for (const file of walk(path.join(webRoot, 'app/pages'))) {
      const source = fs.readFileSync(file, 'utf8')
      if (!source.includes('@action=')) continue

      const handler = source.match(/function\s+onAction\s*\(([^)]*)\)/)
      if (!handler) {
        offenders.push(`${path.relative(webRoot, file)}: no onAction found`)
        continue
      }

      // One parameter, and it must be an object — either destructured inline
      // or typed as `{ key, row }`.
      const params = handler[1]!
      // The braces are emptied before counting parameters: a type annotation
      // like `{ key: string, row: Row }` carries its own commas, and reading
      // one of those as a second parameter flags every correct handler.
      const looksLikeObject = /^\s*(\{|payload\s*:\s*\{)/.test(params)
      const singleParam = !params.replace(/\{[^}]*\}/g, '').includes(',')

      if (!looksLikeObject || !singleParam) {
        offenders.push(`${path.relative(webRoot, file)}: onAction(${params.trim()})`)
      }
    }

    expect(offenders, `Handlers disagreeing with the emit:\n${offenders.join('\n')}`)
      .toEqual([])
  })
})
