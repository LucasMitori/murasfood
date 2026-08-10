// @vitest-environment node
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

/**
 * Every internal link must point at a page that exists.
 *
 * This is here because dead links kept shipping: the header linked to
 * `/favoritos`, sign-in linked to `/auth/cadastro` and `/auth/recuperar-senha`,
 * and checkout sent customers to `/conta/enderecos` to add the address they
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
    expect(resolves('/produtos/arroz-branco-5kg')).toBe(true)
    expect(resolves('/produtos/anything/deeper/still')).toBe(false)
  })

  it('rejects a route that does not exist', () => {
    expect(resolves('/definitely-not-a-page')).toBe(false)
  })
})
