// @vitest-environment node
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { parse } from 'yaml'
import { describe, expect, it } from 'vitest'

/**
 * Every column a table renders must be a field the API actually sends.
 *
 * The finance table had a column keyed `direction`, and no endpoint has ever
 * returned a field by that name. `item.direction` was `undefined`, the ternary
 * fell to its else branch, and revenue was labelled as money going *out* —
 * on the page a shopkeeper uses to read their own books.
 *
 * Nothing could catch it. The row interface declared `direction: string`, so
 * TypeScript was satisfied; the response is cast at the fetch boundary, so the
 * declaration was never checked against reality; and the template is Pug, which
 * `vue-tsc` does not read. The table was also empty until the ledger projection
 * was scheduled, so there was never a row on screen to look wrong.
 *
 * The OpenAPI schema is the contract both sides claim to honour, so this
 * compares them directly. Regenerate it with:
 *
 *     docker compose exec api python manage.py spectacular --fail-on-warn \
 *       > docs/api/openapi.yaml
 */

const webRoot = fileURLToPath(new URL('../..', import.meta.url))
const repoRoot = path.resolve(webRoot, '../..')
const schemaPath = path.join(repoRoot, 'docs/api/openapi.yaml')

interface Schema {
  paths: Record<string, Record<string, { responses?: Record<string, unknown> }>>
  components: { schemas: Record<string, { properties?: Record<string, unknown> }> }
}

const schema = parse(fs.readFileSync(schemaPath, 'utf8')) as Schema

/** Follow a `$ref` to the component it names. */
function deref(node: unknown): Record<string, unknown> | null {
  if (!node || typeof node !== 'object') return null
  const ref = (node as { $ref?: string }).$ref
  if (!ref) return node as Record<string, unknown>

  const name = ref.replace('#/components/schemas/', '')
  return (schema.components.schemas[name] as Record<string, unknown>) ?? null
}

/**
 * The properties of one row returned by a list endpoint.
 *
 * A paginated list wraps its rows in `results`, so the row shape is one level
 * further down than the response schema.
 */
function rowPropertiesFor(endpoint: string): Set<string> | null {
  const full = `/api/v1${endpoint}`
  const get = schema.paths[full]?.get
  if (!get) return null

  const content = (get.responses?.['200'] as { content?: Record<string, { schema?: unknown }> })
    ?.content
  const body = deref(content?.['application/json']?.schema)
  if (!body) return null

  const props = body.properties as Record<string, unknown> | undefined
  const results = props?.results as { items?: unknown } | undefined
  const row = deref(results?.items ?? body)

  return row?.properties ? new Set(Object.keys(row.properties as object)) : null
}

/** Pull `endpoint: '...'` and the `columns` keys out of a page. */
function readPage(file: string): { endpoint: string, columns: string[] } | null {
  const source = fs.readFileSync(file, 'utf8')

  const endpoint = /endpoint:\s*'([^']+)'/.exec(source)?.[1]
  if (!endpoint) return null

  const block = /const columns[^=]*=\s*\[([\s\S]*?)\n\]/.exec(source)?.[1]
  if (!block) return null

  return {
    endpoint,
    columns: [...block.matchAll(/\{\s*key:\s*'([^']+)'/g)].map(match => match[1]!),
  }
}

function adminPages(): string[] {
  const out: string[] = []
  const walk = (dir: string): void => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name)
      if (entry.isDirectory()) walk(full)
      else if (entry.name.endsWith('.vue')) out.push(full)
    }
  }
  walk(path.join(webRoot, 'app/pages/admin'))
  return out
}

/**
 * Columns the table computes rather than reads straight from the row.
 *
 * `actions` is a button cell with no data behind it. Anything else added here
 * needs a reason: the whole point is that a key which is neither a real field
 * nor a deliberate exception is a bug.
 */
const COMPUTED_COLUMNS = new Set(['actions'])

describe('admin table columns', () => {
  const pages = adminPages().map(file => ({ file, page: readPage(file) }))
    .filter((entry): entry is { file: string, page: NonNullable<ReturnType<typeof readPage>> } =>
      entry.page !== null)

  it('finds tables to check', () => {
    expect(pages.length).toBeGreaterThan(4)
  })

  it('every endpoint exists in the schema', () => {
    // Also catches the schema going stale, which is how it got a month behind.
    const missing = pages
      .filter(({ page }) => rowPropertiesFor(page.endpoint) === null)
      .map(({ file, page }) => `${page.endpoint} <- ${path.relative(webRoot, file)}`)

    expect(missing, `Endpoints absent from docs/api/openapi.yaml:\n${missing.join('\n')}`)
      .toEqual([])
  })

  it('every column is a field the API returns', () => {
    const offenders: string[] = []

    for (const { file, page } of pages) {
      const fields = rowPropertiesFor(page.endpoint)
      if (!fields) continue

      for (const key of page.columns) {
        if (COMPUTED_COLUMNS.has(key) || fields.has(key)) continue
        offenders.push(`${path.relative(webRoot, file)}: '${key}' not in ${page.endpoint}`)
      }
    }

    expect(offenders, `Columns reading fields the API never sends:\n${offenders.join('\n')}`)
      .toEqual([])
  })
})
