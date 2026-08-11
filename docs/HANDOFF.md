# Handoff — state of MurasFood

Written 2026-08-10, at commit `eb71380`. Read this first in a new session.

---

## 1. Running it

The stack is **already built and running**. To bring it back up after a reboot:

```bash
docker compose up -d
```

| Service | URL | Notes |
| --- | --- | --- |
| Storefront + dashboard | http://localhost:3000 | Nuxt 4, hot reload from `apps/web` |
| API | http://localhost:8000/api/v1/ | Django, hot reload from `apps/api` |
| API docs | http://localhost:8000/api/docs/ | Swagger, generated from the code |
| Mail catcher | http://localhost:8025 | Every outgoing email lands here |
| Object storage | http://localhost:9001 | MinIO console |
| Django admin | http://localhost:8000/django-admin/ | Emergency back-office only |

**Sign in:** `devmitori@gmail.com` / `Admin@Market2026`

If containers are missing, the cause is almost always a missing `.env` — it is
gitignored by design. Recreate it with `cp .env.example .env` and generate a
`DJANGO_SECRET_KEY`.

### Rebuilding from nothing

```bash
docker compose down -v && docker compose up -d --build
```

```bash
docker compose exec api python manage.py migrate
```

```bash
docker compose exec api python manage.py create_admin --only-user
```

```bash
docker compose exec api python manage.py seed_catalog
```

`create_admin` is idempotent and also provisions the tenant, roles, permissions,
units, delivery config and email templates. `--only-user` deletes every other
account, which is what makes the admin the *only* user.

---

## 2. What exists and works

**Backend** — 16 domain modules, 251 tests passing, Ruff clean, 227 documented
API operations. Tenancy, permission codes, catalog, pricing with append-only
history, inventory as a movement ledger, cart, promotions, delivery, the order
state machine, PIX payments with replay-safe webhooks, media, notifications,
the finance ledger, reports with PDF export, and a write-once audit log.

**Frontend** — Nuxt 4 + Vuetify 3 + Pug + Pinia + i18n (pt-BR/en/es), 181 tests
passing, ESLint and `vue-tsc` clean, production build green. Storefront (home,
catalog, product, cart, checkout, PIX, orders, login) and the dashboard
overview.

**Component library** — 24 components. The two that matter most for what comes
next:

- `MuraFormBuilder` — declare a `FormSchema`, get a validated form with API
  error mapping and conditional fields. See `app/types/ui.ts`.
- `MuraDataTable` + `useServerTable` — server pagination with the hazards
  handled (feedback loops, stale responses, vanishing pages, `itemsPerPage: -1`).
  Worked example: `app/pages/admin/produtos/index.vue`.

**Data** — one tenant (`demo`), one user (the admin), 51 products across eight
sections, each with a backdated price history so a price chart has a real series
to plot.

---

## 3. What was asked for and is NOT built

Five features from the last request remain. Nothing below is started; the notes
are the design work so the next session can go straight to implementation.

### 3.1 Admin users page with drag-and-drop permissions

**Wanted:** `/admin/usuarios` with a server table, toolbar, "New" top-right, and
per-row view/edit/delete. Edit and create open `/admin/usuarios/novo` and
`/admin/usuarios/:id/editar` as real pages with tabs; one tab holds two
side-by-side drag-and-drop lists (assigned vs available) for **permissions**,
and another pair for **roles**.

**Backend is ready.** `/admin/users/` and `/admin/roles/` exist with
`users.view` / `users.manage` enforcement. `StaffUserSerializer` already accepts
`roles` as a list of slugs.

**Two gaps to close first:**

1. There is no endpoint listing the permission catalogue. Add
   `GET /admin/permissions/` returning `{code, description}` from
   `PERMISSION_CATALOGUE` — a `ListAPIView` over `Permission`, gated on
   `users.view`.
2. Permissions are currently attached to *roles*, not directly to users
   (`User.permission_codes()` unions role permissions). Direct per-user
   permissions need either a new `UserPermission` through-model or a decision to
   drag permissions onto a *role*. **Ask which is wanted** — it changes the
   schema.

**Drag-and-drop:** `vuedraggable@next` is the usual choice; it is not yet a
dependency. Provide a keyboard-accessible fallback (select + move buttons) —
drag-only lists are unusable without a mouse.

### 3.2 Permission guards across every page

**Wanted:** pages gated on codes such as `perm.admin.profile`, with the sweep
applied to all existing pages.

**Naming mismatch to resolve.** The backend catalogue uses `catalog.view`,
`orders.refund`, `users.manage` — not a `perm.` prefix. Either the frontend maps
onto the existing codes, or the catalogue is renamed in
`apps/api/apps/accounts/constants.py` (one edit, plus a migration-free reseed).
**Decide before writing guards**, or the two halves will disagree.

**What exists:** `app/middleware/merchant.ts` checks "is staff". `auth.can(code)`
already works client-side.

**What to add:** a `permission.ts` middleware reading
`definePageMeta({ permission: 'orders.view' })`, applied to every admin page,
plus a `usePermission()` composable for hiding UI within a page. The API already
enforces every code, so this is affordance and routing, not the security
boundary.

### 3.3 Login/register as one flip-card page

**Wanted:** a single centred page; the card flips to reveal registration.

`app/pages/auth/login.vue` and the registration flow exist separately. The work
is one page with `transform: rotateY(180deg)`, `backface-visibility: hidden`, a
`perspective` wrapper, and `prefers-reduced-motion` respected (the global rule
in `main.scss` already disables transitions there — verify the flip degrades to
a plain swap rather than getting stuck mid-rotation).

### 3.4 Shopping lists

**Wanted:** reusable lists ("monthly shop") that bulk-add to the cart.

Entirely new. Needs a `ShoppingList` + `ShoppingListItem` model in a new app (or
inside `cart`), tenant-owned and customer-scoped, plus
`POST /shopping-lists/{id}/add-to-cart/` that reuses `cart.services.add_item`
so stock and quantity rules are enforced once. Frontend: a list manager and a
"save cart as list" action.

### 3.5 Product page charts

**Wanted:** price variation and product analysis on each product page.

Data already exists — `PriceHistory` is populated, including by the seed. The
gap is a **public** endpoint: the current one
(`/admin/prices/history/{product_id}/`) requires `pricing.view`, which a shopper
does not have. Add a public, cost-free projection returning only
`{date, price}` — never `cost_price` or margin, which must not leak to
customers. Then render with `vue-chartjs`, already a dependency and already used
on the dashboard.

### 3.6 Checkout, wishlist and favourites review

Requested as a review; not done. Favourites and checkout are implemented and
covered by backend tests, but I have not walked the flows in the browser. Worth
doing before building on them.

---

## 3.7 Progress since this document was written

- **Permissions foundation — done.** Hierarchical `perm.*` page codes, direct
  user grants alongside roles, `GET /admin/permissions/`,
  `PUT /admin/users/{id}/permissions/`, `PUT /admin/users/{id}/roles/`, the
  `permission.global.ts` route guard and `usePermission`. §3.1 and §3.2 are
  closed.
- **Admin users screen — done.** `/admin/usuarios` (table, toolbar, New button,
  view/edit/deactivate row actions), `/admin/usuarios/novo`,
  `/admin/usuarios/:id` (read-only) and `/admin/usuarios/:id/editar` with tabs
  and two drag-and-drop transfer lists.
- **Favourites page — added.** The header linked to `/favoritos`, which did not
  exist; the link was dead in shipped UI.

- **Flip-card auth — done.** `/auth/login` and `/auth/cadastro` render one
  `MuraAuthPanel`; the card rotates in place and rewrites the URL rather than
  navigating. `/auth/recuperar-senha` added (both halves of the reset flow).
- **Customer account area — added.** `/conta` and `/conta/enderecos`. Both were
  linked from the header and from checkout without existing.

**Two app-wide bugs were found and fixed while verifying the above. Both had
been present since the first commit.**

1. **The client-side app never booted.** `bootstrap.client.ts` called Vuetify's
   `useTheme()`, which resolves by injection and throws outside a component
   setup. Every page server-rendered correctly and then blanked on hydration —
   so every URL returned HTTP 200 while the site was unusable in a browser. The
   theme now comes from the instance the Vuetify plugin provides. *Checking
   status codes did not catch this and cannot; a page has to be opened.*
2. **Server-side rendering could not reach the API.** Both halves of Nuxt used
   `http://localhost:8000`, which inside the web container is the web container.
   `NUXT_API_BASE_URL_SERVER` now points SSR at `http://api:8000/api/v1`.

- **Product price charts — done.** Public
  `GET /catalog/products/{slug}/price-history/?days=` plus `MuraPriceChart` on
  the product page.

**Three more pre-existing bugs surfaced while building the chart:**

3. **Storefront search returned 500 on PostgreSQL.** `TrigramSimilarity` was
   imported from `django.contrib.postgres.trigram`, which does not exist, and
   the `pg_trgm` extension it needs was never installed. Both fixed; migration
   `catalog.0003`.
4. **The backend suite ran under development settings inside Docker.** The API
   container exports `DJANGO_SETTINGS_MODULE=config.settings.development`, and
   that overrides pytest's ini key. `--ds=config.settings.test` is now in
   `addopts`, which takes precedence over the environment.
5. Both of the above were masked: the suite reported failures that looked
   environmental, so the search bug behind them went unread.

- **Shopping lists — done.** `ShoppingList`/`ShoppingListItem`,
  `/shopping-lists/` CRUD, `add-to-cart/`, `from-cart/`, and `/conta/listas`.

**Two more app-wide bugs, both found while testing the lists page signed in:**

6. **The session did not survive a page load.** Tokens live in `localStorage`,
   and the store reads them in its state initialiser — but on a server-rendered
   page that runs on the server, and Pinia then hydrates the client from the
   server's payload, overwriting it with `null`. Every reload signed the user
   out. `auth.restoreFromStorage()` now runs in `bootstrap.client.ts`.
7. **Auth guards ran server-side, where they can never pass.** The server
   cannot read `localStorage`, so `middleware/auth.ts` and
   `permission.global.ts` redirected every signed-in visitor to sign-in on a
   hard load. Both now return early on the server, and `/conta/**` and
   `/favoritos` joined `/admin/**` as `ssr: false`.

- **Checkout, cart and favourites — walked end to end.** Anonymous browse →
  add to cart → sign in (cart merges) → checkout → PIX → paid → order history.
  Order `MF-260811-ALWC6C` was placed and confirmed against the running stack.

**Three more bugs, all of which made the storefront unusable in a browser while
every API test passed:**

8. **The anonymous cart never worked.** `X-Cart-Token` was missing from
   `CORS_EXPOSE_HEADERS`, so the browser hid it and the token was never stored;
   and missing from `CORS_ALLOW_HEADERS`, so once a token *was* stored the
   preflight rejected every cart request. Both fixed, with
   `apps/common/tests/test_cors_contract.py` guarding them.
9. **No order could ever be placed.** `checkout.vue` passed a closure to
   `useAsyncData` that read a `computed` declared *below* it. The handler runs
   immediately, so it threw `ReferenceError` inside the fetch, leaving delivery
   options empty and "Confirm order" permanently disabled. Declaration moved
   above the fetch; `@typescript-eslint/no-use-before-define` now catches the
   whole class, and found a second latent instance in `MuraFormBuilder`.

All six requested features are built. Nothing from the original request is
outstanding.

## 4. Things worth knowing before editing

- **File watching does not always cross the Windows bind mount.** A newly
  *created* page can 404 until `docker compose restart web`. Edits to existing
  files hot-reload normally.
- **Adding an npm dependency needs the web image rebuilt**, because
  `node_modules` lives in a named volume:
  `docker compose down web && docker volume rm murasfood_web_node_modules && docker compose up -d --build web`.
- **Never run `npm run build` on the host while the dev container is up.**
  `apps/web` is bind-mounted, so the build overwrites the `.nuxt` the dev server
  is serving from and the browser starts 404ing on chunks. Stop `web` first,
  and delete `.nuxt`/`.output` before starting it again.
- **HTTP 200 does not mean a page works.** Nuxt server-renders, so a page whose
  client-side app is broken still answers 200 with complete HTML and only fails
  once hydration runs. Open pages in a browser and check the console.

- **`.env` is gitignored.** Container startup depends on it existing.
- **`seed_catalog` archives rather than deletes** products referenced by an
  order — deleting them would break order history (invariant #3).
- **The payment provider is a sandbox.** It produces valid BR Codes and
  exercises the real webhook path but moves no money. To simulate payment:
  `POST /api/v1/payments/{id}/simulate/`.
- **Money crosses the wire as strings.** Never do arithmetic on them in JS; use
  `app/utils/money.ts`.
- **Frontend tests cover the logic layer only** — stores, API client, money,
  formatters, theme, table pagination. No component rendering is asserted; the
  production build and `vue-tsc` are what catch template breakage.
- **`mypy` is advisory** in CI, not blocking.

## 5. Suggested order for the next session

1. Settle the two open questions (§3.1 direct-vs-role permissions, §3.2 code
   naming). Both block work that is otherwise mechanical.
2. Permission middleware sweep — small, and everything else inherits it.
3. Admin users page — the builders make this mostly schema.
4. Flip-card auth — self-contained.
5. Product charts — needs one new endpoint.
6. Shopping lists — the largest, entirely new.
