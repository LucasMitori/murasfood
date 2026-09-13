/**
 * Is the dev server actually usable yet — and make it so.
 *
 * Nuxt answers `/` about two seconds after boot, but the page it returns names
 * ~50 stylesheets that `vite-plugin-vuetify` compiles from SASS on demand, and
 * those took another twenty seconds to appear. Anyone who opened the browser
 * inside that window got a page whose CSS 404'd; a `<link>` that 404s is never
 * retried, so it stayed unstyled, and because a failed module request is cached
 * per tab the next client-side navigation failed too. Only a hard reload
 * cleared it.
 *
 * So "healthy" cannot mean "answers on port 3000". This requests the pages and
 * everything they reference, which both measures readiness and *causes* it —
 * the request is what makes Vite compile them. By the time Docker calls the
 * container healthy, that cost has been paid against this script instead of
 * against the first person to open the site.
 *
 * Several routes are warmed, not just the home page. A virtual stylesheet only
 * resolves once something has pulled that component into the client's module
 * graph, and the head Nuxt emits is broader than the page it belongs to — the
 * storefront's own HTML links `VSwitch` and `VTextField`, which nothing on it
 * uses. Warming one route therefore leaves the forms and the dashboard cold,
 * and the first person to open those pays the same cost again.
 *
 * Readiness is judged on the routes rendering and their assets being served.
 * Requiring *every* linked stylesheet would be wrong by construction, since
 * that list includes components the page never renders.
 */

const ORIGIN = process.env.HEALTHCHECK_ORIGIN ?? 'http://127.0.0.1:3000'
const TIMEOUT_MS = 20_000

/** The routes worth paying for up front: the storefront, the catalogue with its
 *  filters, the cart, a form-heavy page, and the dashboard shell. Between them
 *  they pull in nearly every component the app uses. */
const ROUTES = ['/', '/products', '/cart', '/auth/login', '/admin']

async function get(url) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  try {
    return await fetch(url, { signal: controller.signal })
  }
  finally {
    clearTimeout(timer)
  }
}

async function warm(route) {
  const page = await get(`${ORIGIN}${route}`)
  if (!page.ok) return { route, ok: false, status: page.status, warmed: 0, total: 0 }

  const html = await page.text()
  const assets = [...html.matchAll(/(?:href|src)="(\/_nuxt\/[^"]+)"/g)].map(match => match[1])

  /*
   * One at a time, which is the whole point.
   *
   * Vite answers 404 for a virtual module that is still compiling rather than
   * waiting for it, so a burst of fifty parallel requests mostly loses its own
   * races — which is exactly what a browser does when it parses the page, and
   * exactly what this script did when it warmed with `Promise.all`: it reported
   * 312 of 352 warmed and left the first real visitor to hit the rest cold.
   *
   * Sequentially every request either compiles the module or finds it already
   * compiled. It is slower, but this is startup time in a container rather than
   * someone waiting at a screen.
   */
  let warmed = 0
  const missed = []
  for (const href of assets) {
    const response = await get(`${ORIGIN}${href}`).catch(() => ({ status: 0 }))
    if (response.status === 200) warmed += 1
    else missed.push(href)
  }

  // A second pass for anything that lost a race against the page's own load.
  for (const href of missed) {
    const response = await get(`${ORIGIN}${href}`).catch(() => ({ status: 0 }))
    if (response.status === 200) warmed += 1
  }

  return { route, ok: true, status: 200, warmed, total: assets.length }
}

try {
  const results = []
  for (const route of ROUTES) {
    // Sequential across routes on purpose: each compiles a slice of the
    // component set, and five cold renders at once only contend for the same
    // single-threaded transform.
    results.push(await warm(route))
  }

  const failed = results.filter(result => !result.ok)
  if (failed.length) {
    console.error(`not ready: ${failed.map(f => `${f.route} ${f.status}`).join(', ')}`)
    process.exit(1)
  }

  const warmed = results.reduce((sum, result) => sum + result.warmed, 0)
  const total = results.reduce((sum, result) => sum + result.total, 0)
  // Docker shows this line in `docker inspect`'s health log, which is the only
  // place a healthcheck can say how much it actually did.
  // eslint-disable-next-line no-console
  console.log(`ready: ${results.length} routes, ${warmed}/${total} assets warmed`)
  process.exit(0)
}
catch (error) {
  console.error(`not ready: ${error.message}`)
  process.exit(1)
}
