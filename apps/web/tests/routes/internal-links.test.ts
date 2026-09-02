// @vitest-environment node
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

/**
 * Every internal link must point at a page that exists.
 *
 * This is here because dead links kept shipping: the header linked to
 * `/favorites`, sign-in linked to `/auth/register` and `/auth/reset-password`,
 * and checkout sent customers to `/account/addresses` to add the address they
 * needed in order to finish paying. None of those pages existed. Nothing caught
 * it — a missing route is not a type error, and the build compiles a broken
 * link happily.
 */

const webRoot = fileURLToPath(new URL('../..', import.meta.url))
const pagesDir = path.join(webRoot, 'app/pages')

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) walk(full, out)
    else out.push(full)
  }
  return out
}

/** Derive the route table from the pages directory the way Nuxt does. */
function buildRoutes(): { staticRoutes: Set<string>, dynamicRoutes: RegExp[] } {
  const routes = walk(pagesDir)
    .filter(file => file.endsWith('.vue'))
    .map((file) => {
      const relative = path.relative(pagesDir, file).replace(/\\/g, '/').replace(/\.vue$/, '')
      const withIndex = relative.replace(/\/index$/, '').replace(/^index$/, '')
      const withParams = withIndex.replace(/\[([^\]]+)\]/g, ':$1')
      return `/${withParams}`.replace(/\/+$/, '') || '/'
    })

  return {
    staticRoutes: new Set(routes),
    dynamicRoutes: routes
      .filter(route => route.includes(':'))
      .map(route => new RegExp(`^${route.replace(/:[^/]+/g, '[^/]+')}$`)),
  }
}

const { staticRoutes, dynamicRoutes } = buildRoutes()

function resolves(link: string): boolean {
  const clean = link.split('?')[0]!.split('#')[0]!.replace(/\/+$/, '') || '/'
  if (staticRoutes.has(clean)) return true
  return dynamicRoutes.some(pattern => pattern.test(clean))
}

/** Literal internal links, ignoring anything built from a template string. */
function collectLinks(): { file: string, line: number, link: string }[] {
  const patterns = [
    /\bto=["'](\/[^"'`]*)["']/g,
    /\bback-to=["'](\/[^"'`]*)["']/g,
    /(?:router\.push|navigateTo)\(\s*["'](\/[^"'`]*)["']/g,
    // Navigation defined as data rather than markup — the admin sidebar builds
    // its menu from an array, and four entries in it led to pages that had
    // never been written.
    /\bto:\s*["'](\/[^"'`]*)["']/g,
  ]

  /*
   * Paths built as template literals, which the quoted patterns cannot see.
   *
   * Skipping them let five dead links through the rename to English: three
   * `/admin/users/${id}/editar`, and — worse — the redirect checkout makes
   * after placing an order, to `/account/orders/${number}/pagamento`. Each was
   * a path split by an interpolation, so a segment-wise replacement never
   * matched it and no test looked.
   *
   * Every `${...}` becomes one placeholder segment, which the resolver already
   * matches against a dynamic route exactly as a real id would.
   */
  const templatePatterns = [
    /:to="`(\/[^`]*)`"/g,
    /(?:router\.push|navigateTo)\(\s*`(\/[^`]*)`/g,
  ]

  const found: { file: string, line: number, link: string }[] = []

  for (const file of walk(path.join(webRoot, 'app')).filter(f => /\.(vue|ts)$/.test(f))) {
    fs.readFileSync(file, 'utf8').split('\n').forEach((line, index) => {
      for (const pattern of patterns) {
        pattern.lastIndex = 0
        let match: RegExpExecArray | null
        while ((match = pattern.exec(line))) {
          const link = match[1]!
          // `/api/...` is the backend, not a page; `${...}` is built at runtime.
          if (link.startsWith('/api') || link.includes('${')) continue
          found.push({ file: path.relative(webRoot, file), line: index + 1, link })
        }
      }

      for (const pattern of templatePatterns) {
        pattern.lastIndex = 0
        let match: RegExpExecArray | null
        while ((match = pattern.exec(line))) {
          const raw = match[1]!
          if (raw.startsWith('/api')) continue

          // One interpolation stands for one segment; a query string is not
          // part of the route.
          const link = raw.replace(/\$\{[^}]*\}/g, 'x').replace(/\?.*$/, '')
          if (link.includes('${')) continue
          found.push({ file: path.relative(webRoot, file), line: index + 1, link })
        }
      }
    })
  }

  return found
}

describe('internal links', () => {
  const links = collectLinks()

  it('finds links to check', () => {
    expect(links.length).toBeGreaterThan(10)
  })

  it('every link points at a page that exists', () => {
    const broken = links
      .filter(entry => !resolves(entry.link))
      .map(entry => `${entry.link} <- ${entry.file}:${entry.line}`)

    expect(broken).toEqual([])
  })

  it('resolves dynamic routes by shape', () => {
    // Guards the matcher itself: if this stopped working every link would
    // "pass" by accident and the test above would prove nothing.
    expect(resolves('/products/arroz-branco-5kg')).toBe(true)
    expect(resolves('/products/anything/deeper/still')).toBe(false)
  })

  it('rejects a route that does not exist', () => {
    expect(resolves('/definitely-not-a-page')).toBe(false)
  })
})

/**
 * Route rules in `nuxt.config.ts` must name pages that exist.
 *
 * These sit outside `app/`, so the link scan above never saw them — and when
 * the routes were renamed to English the rules kept pointing at the Portuguese
 * paths. That is worse than a dead link: `/account/**` silently lost both its
 * `noindex` header and its client-only rendering, so personalised pages became
 * server-rendered and indexable, and `/conta` answered 200 with an empty shell
 * instead of a 404.
 */
describe('route rules', () => {
  const config = fs.readFileSync(path.join(webRoot, 'nuxt.config.ts'), 'utf8')

  /** The keys of `routeRules`, e.g. `'/admin/**'` or `'/checkout'`. */
  function ruleGlobs(): string[] {
    const block = config.match(/routeRules:\s*\{([\s\S]*?)\n {2}\},/)
    if (!block) return []

    return [...block[1]!.matchAll(/'([^']+)':\s*\{/g)].map(match => match[1]!)
  }

  it('finds rules to check', () => {
    expect(ruleGlobs().length).toBeGreaterThan(0)
  })

  it('every rule matches at least one real page', () => {
    const orphaned = ruleGlobs().filter((glob) => {
      // A `/x/**` rule is satisfied by the section existing at all, which is
      // what `/x` itself resolving proves.
      const probe = glob.replace(/\/\*\*$/, '')
      return !resolves(probe) && !resolves(`${probe}/index`)
    })

    expect(orphaned, `Route rules naming pages that do not exist: ${orphaned.join(', ')}`)
      .toEqual([])
  })
})
