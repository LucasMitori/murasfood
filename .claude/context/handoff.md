# Handoff — session compaction

> Compressed record of the work so far, so a new session can pick up without
> re-reading the transcript. Facts only; reasoning lives in `historic.md`.

**Last updated:** 2026-09-13
**Branch:** `feat/merchant-tooling-and-platform-fixes` (pushed, PR not yet opened — `gh` is not installed on this machine)
**Baseline:** 429 API tests · 242 web tests · ruff + format · eslint · vue-tsc — all clean

---

## 1. The project

**MurasFood** — white-label multi-tenant e-commerce for small and mid-size
markets. Sold per merchant; the buyer is a shop owner, not a developer.

| | |
|---|---|
| Frontend | Nuxt 4 (`app/` srcDir), Vue 3 `<script setup>`, **Pug templates**, TypeScript strict, Vuetify 3.13, Pinia, `@nuxtjs/i18n` (pt-BR / en / es) |
| Backend | Django 5.2 + DRF, Celery + Redis, PostgreSQL, MinIO (S3-compatible) |
| Tenancy | Shared schema with `tenant_id`; every query scoped |
| Infra | Docker Compose (`api`, `web`, `worker`, `beat`, `postgres`, `redis`, `minio`, `mailpit`) |

---

## 2. Hard-won environment facts

These cost real time to discover. Do not re-learn them.

| Fact | Consequence |
|---|---|
| **Pug templates are not type-checked** by `vue-tsc`, nor parsed by ESLint's Vue plugin | A TypeScript cast in a template (`x as string[]`) reaches the browser verbatim and throws `SyntaxError`. A whole page can never have rendered and nothing reports it. |
| **The web container does not see host file changes** | Every frontend edit needs `docker compose restart web`. This has caused false "my fix didn't work" conclusions twice. |
| **Celery workers do not autoreload** | Backend changes to task code need `docker compose restart worker`. Bit us on the order emails *and* the CSV reports. |
| **Git Bash rewrites container paths** | `/app/x.yaml` becomes `C:/Program Files/Git/app/x.yaml`. Fixed centrally via `COMPOSE ?= MSYS_NO_PATHCONV=1 docker compose` in the Makefile. |
| **`gh` CLI is not installed** | PRs must be opened through the web UI. |
| **DRF reserves `?format=`** for content negotiation | Our download endpoints use `?fmt=` instead; `?format=csv` returns 404 for a renderer that does not exist. |
| **Vite 404s a virtual module that is still compiling** | Parallel bursts lose their own races; warming must be sequential. |
| **A failed dynamic import is cached per tab** | After a transient failure, only a fresh tab or hard reload recovers. |
| **`<component :is="'v-card'">` with a string does not resolve** | Vuetify components are imported per-usage by `vite-plugin-vuetify`; a dynamic string renders a literal unknown element. |
| **`v-row` has `margin: -12px`** | `v-card-text`'s 16px padding is what cancels it. Removing the padding collapses form gutters. |
| Money is **strings on the wire, integer cents in JS** | The calculator uses integers scaled by 10⁴. |

---

## 3. The dominant failure mode

Roughly two thirds of everything found in this session was the same shape:

> **Code written, tested, merged — and never connected to anything.**

Not regressions. Features that had *never once run*. Invisible to lint,
typecheck and a green suite, because none of those can see a caller that does
not exist.

Instances found and fixed:

- every dashboard row action (emit signature mismatch)
- `/admin/users` (never rendered — TS cast in Pug)
- the checkout → payment redirect
- product image attachment
- order confirmation emails (no caller)
- staff new-order alerts (no caller, behind a setting defaulting to on)
- `?search=` on 7 of 8 admin tables (`SearchFilter` not installed)
- 6 periodic jobs (never scheduled)
- the branding endpoint (no UI)
- the whole reports subsystem (no UI)
- CSV report format (ignored, then unsettable)
- `MuraImage` (built, then not used by the storefront)
- `perm.admin.reports` (declared, never used)
- `deactivate_price` (unreachable — deliberately left, see `historic.md`)

**Method that works:** verify against the running application. Reading proves
nothing here.

---

## 4. Work completed

### 4.1 Correctness sweep

| Area | Fix |
|---|---|
| Row actions | `MuraDataTable` emitted `(key, row)`; five of six screens destructured one object. Emit is now one object. |
| Order emails | `_notify_order_placed()` in `create_order_from_cart`, queued in-transaction, dispatched on commit. |
| Admin search | `SearchFilter` added to `DEFAULT_FILTER_BACKENDS`; `search_fields` added to inventory, orders, staff users, finance; hand-rolled customer search removed. |
| Scheduling | Beat went 4 → 11 entries. New `apps/orders/tasks.py`; `notify_low_stock_all_tenants` fan-out (the original takes a `tenant_id`, so it *could not* be scheduled). |
| Orphan cleanup | Relations now derived from `_meta` (the hand list had fallen 2 behind — would have deleted live brand logos and reports). |
| Money display | `money_display()` in `apps/common/money.py`, used by emails and the PDF receipt. Emails said `BRL 24.90` while the admin preview said `R$ 128,40`. |
| Finance table | Read `item.direction` — **a field no endpoint returns** — so revenue was labelled as money going out. |
| Dates | `formatDate('2026-08-10')` parsed as UTC midnight → displayed the 9th. All date-only fields were a day early. |
| Signed URLs | Private downloads presigned against internal `minio:9000`; now signed for `S3_PUBLIC_ENDPOINT`. |

### 4.2 Features added

- **Spreadsheet import/export** — `apps/common/spreadsheets.py` (CSV + XLSX), `apps/common/exports.py` (inventory, customers, orders), `apps/catalog/importexport.py` (products, both directions). Template → dry-run preview → apply. All-or-nothing. Matched on SKU.
- **Reports page** — `/admin/reports`, three tabs over one period, queued PDF/CSV export with polling.
- **Configurable home** — `home_layout` on `TenantSettings`; reorder / rename / cap / disable the storefront bands.
- **Storefront tabs** — `/admin/storefront` gained Layout and Appearance (the branding endpoint finally has a UI).
- **Picker inputs** — `MuraColorField`, `MuraDateTimeField` for the `color` / `date` / `time` / `datetime` field types.
- **Image pipeline** — master capped at 2048px + re-encoded, AVIF beside WebP, `<picture>` rendering, `manage.py reprocess_images`.

### 4.3 Platform

- **Vite dev fix** — dev serves Vuetify precompiled CSS; build keeps SASS. First-load failures 50 → 0, cold start 56s → 34s.
- **Web healthcheck** — `apps/web/scripts/healthcheck.mjs` warms five routes; the service had none before.
- **OpenAPI** — schema was a month stale and generation was non-deterministic. `SORT_OPERATIONS: True`, `make openapi-check`, clean under `--fail-on-warn`.

### 4.4 Guards (each proven by reintroducing the bug)

| File | Catches |
|---|---|
| `apps/web/tests/components/table-action-contract.test.ts` | emit signature drift; TS casts in Pug |
| `apps/web/tests/routes/internal-links.test.ts` | dead links incl. template literals; orphaned route rules |
| `apps/web/tests/i18n/locale-parity.test.ts` | keys used in source that resolve in no locale |
| `apps/web/tests/contracts/table-columns.test.ts` | admin columns vs OpenAPI schema (8 tables, 38 columns) |
| `apps/api/apps/common/tests/test_search_contract.py` | `?search=` actually filtering |
| `apps/api/apps/common/tests/test_schedule_contract.py` | required periodic jobs scheduled |
| `apps/api/apps/media/tests/test_cleanup.py` | every relation guarded before orphan deletion |
| `apps/api/apps/media/tests/test_signed_urls.py` | private URLs signed for the public host |
| `apps/web/tests/utils/format.test.ts` | date-only drift (suite pinned to `America/Sao_Paulo`) |

---

## 5. Numbers worth keeping

| Metric | Before | After |
|---|---|---|
| Storage per 4000×3000 phone photo | 7,612,621 B | ~1,500,000 B |
| Realistic photo, total stored | 505,333 B | 98,258 B |
| Existing library masters (89 images) | 9,357,525 B | 4,275,570 B |
| Dev first-load failed requests | 50 | 0 |
| Cold start to healthy | never signalled | 34 s |
| Beat schedule entries | 4 | 11 |
| Finance ledger rows | 0 | populated |
| API tests | 368 | 429 |
| Web tests | 231 | 242 |

---

## 6. Phase 6 — dashboard, money and scale

Seven requests, all delivered. Measured evidence for each is in
`actual_step.md`; the mistakes made getting there are in `historic.md`.

| # | Asked for | Built |
|---|---|---|
| 1 | Rail icons off-centre, blank "Ver a loja", odd footer | Icons/avatar/button all within **0.5px** of the drawer axis (was 8px); the button renders its icon; the duplicate bottom bar removed |
| 2 | Identity block → user editor, richer "Dados" tab | Whole block is a link to `/admin/users/<id>/edit`; `User.avatar` FK, tenant-checked on write, cleared and deleted on anonymisation |
| 3 | More in the second header row, a divider, compact | 52px row: search + ⌘K, quick-create, live stock badge, storefront, fullscreen, seam divider |
| 4 | Table shows a black flash before data | `MuraTableSkeleton` — self-contained CSS, no second chunk to wait for. **Partially fixed**, see below |
| 5 | Hide out-of-stock, or offer "notify me" | Both, merchant's choice. `RestockAlert`, guest-friendly, one email per restock, plus a demand report ranking what to reorder |
| 6 | Finance as the second beating heart | `analysis.py`: DRE with AV/AH, budget vs actual, linear forecast, cash flow, price-change simulator |
| 7 | Diagnostics page, admin only | 8 live probes, gated on a *capability* (page codes are hierarchical and would have leaked it to all staff) |

Plus two later asks in the same pass:

- **Images at 10k products.** WebP/AVIF already existed; what was missing was
  `Cache-Control` (absent entirely), checksum dedupe (computed since day one,
  read by nothing), a separate `media` queue, and a blurred LQIP placeholder.
- **Finance depth.** The whole of `analysis.py` above.

### What is NOT finished

1. **The table flash is only partly fixed.** The skeleton is verified; the
   ~130 ms before it — route changed, component chunk still loading — is a
   dev-server artifact and has **not** been measured against a production build.
2. Animations — gentle, modern, professional *(carried from phase 5)*
3. Sale/discount card and dedicated product page treatment *(carried)*
4. `hide_out_of_stock` has no switch in `/admin/storefront` yet
5. `/admin/customers` CRUD — needs backend work (currently `ReadOnlyModelViewSet`)
6. `deactivate_price` — unreachable; left deliberately, decision pending
7. The `maruth.security` skill has still never been run as a full audit
8. PR not yet opened — `gh` missing; branch is pushed and the body is written

### Two things that must run on every deploy

```bash
python manage.py sync_roles            # new permission codes reach existing tenants
python manage.py sync_email_templates  # new templates reach existing tenants
```

Both exist because a feature was found completely dead without them. A code
added to `PERMISSION_CATALOGUE` or `DEFAULT_TEMPLATES` reaches tenants created
*after* the deploy and nobody else — it works on a fresh database and on every
test run, and is dead in the one place that matters.

### A dev account was created

`qa.claude@murasfood.local` (ADMINISTRATOR, `demo` tenant) exists in the dev
database so admin screens could actually be driven — "no merchant browser
session" had blocked visual verification for several phases. **Delete it before
any deployment.**

---

## 7. Working agreement

Four files in `.claude/context/` divide the state deliberately:

| File | Holds |
|---|---|
| `planning.md` | the map — where code lives, phases, risks |
| `flow.md` | diagrams — how the system works now and next |
| `actual_step.md` | **one** phase: what is confirmed, with measured evidence |
| `historic.md` | hypotheses that died, method errors — **never deleted** |

Read `actual_step.md` first. Write to `historic.md` whenever something turns out
to be wrong — that file is the reason the same mistake is not made twice.
