# planning.md — the map

> Where the code lives, which phase we are in, what is likely to bite.
> Update when the shape of the project changes, not on every commit.

**Last updated:** 2026-09-15

---

## 1. Repository map

```
murasfood/
├── apps/
│   ├── api/                        Django 5.2 + DRF
│   │   ├── config/
│   │   │   ├── settings/base.py    ← all tunables live here
│   │   │   ├── celery.py
│   │   │   └── urls.py
│   │   └── apps/
│   │       ├── accounts/           users, staff, roles, permissions, addresses
│   │       │   └── management/commands/sync_roles.py   ← run on every deploy
│   │       ├── audit/              append-only action log
│   │       ├── cart/               carts, shopping lists
│   │       ├── catalog/            products, categories, brands, units
│   │       │   ├── filters.py      availability, min_discount, price, category
│   │       │   ├── serializers.py  + gallery (order + captions), stock thresholds
│   │       │   └── importexport.py spreadsheet round trip
│   │       ├── common/             shared services + cross-cutting tests
│   │       │   ├── diagnostics.py  ← system health probes (admin-only)
│   │       │   ├── money.py        money_str (wire) vs money_display (prose)
│   │       │   ├── spreadsheets.py CSV + XLSX read/write
│   │       │   └── exports.py      inventory / customers / orders columns
│   │       ├── delivery/           zones, fees
│   │       ├── finance/            ledger, categories, P&L
│   │       │   ├── services.py     writes the ledger
│   │       │   └── analysis.py     ← DRE, budget variance, forecast, cash flow,
│   │       │                         price simulation. Reads only.
│   │       ├── inventory/          stock, reservations, batches, expiry
│   │       │   └── models.py       + RestockAlert (back-in-stock demand)
│   │       ├── media/              uploads, derivatives, storage backends
│   │       ├── notifications/      email templates, logs, delivery
│   │       │   └── management/commands/sync_email_templates.py  ← every deploy
│   │       ├── orders/             checkout, state machine, transitions
│   │       ├── payments/           PIX, providers, webhooks
│   │       ├── pricing/            prices, history
│   │       ├── promotions/         coupons, discounts
│   │       ├── reports/            dashboard, sales/stock/customer reports
│   │       └── tenants/            tenant, branding, settings, hours
│   │           └── models.py       + FaqCategory / FaqEntry (draft · published)
│   └── web/                        Nuxt 4
│       ├── app/
│       │   ├── components/
│       │   │   ├── catalog/        product card, hero, parallax band, restock alert,
│       │   │   │                   product gallery (drag order + captions)
│       │   │   ├── dashboard/      stat card, chart card
│       │   │   ├── finance/        ← statement, budget, forecast, pricing panels
│       │   │   ├── navigation/     header, footer
│       │   │   └── shared/         Mura* — the design system
│       │   ├── composables/        useServerTable, useMoney, usePermission,
│       │   │                       useAdminPulse (header badge)
│       │   ├── layouts/            default, admin
│       │   ├── pages/              file-based routes
│       │   │   └── admin/            + categories/ · faq/ · diagnostics/
│       │   ├── stores/             Pinia
│       │   └── utils/              api-client, format (incl. parallaxShift), theme,
│       │                           validation
│       ├── i18n/locales/           pt-BR · en · es  (parity is enforced)
│       ├── scripts/healthcheck.mjs warms the dev server, once per process
│       └── tests/                  vitest — contracts, i18n, routes, stores
├── docs/api/openapi.yaml           generated; mounted into the web container
├── infrastructure/docker/
└── .claude/context/                planning · flow · actual_step · historic
```

---

## 2. Where to change what

| Task | Start here |
|---|---|
| Add a tunable | `apps/api/config/settings/base.py` |
| Add a scheduled job | task in `apps/<app>/tasks.py` + entry in `CELERY_BEAT_SCHEDULE` + `test_schedule_contract.py` |
| Add an admin table column | page's `columns` array — the contract test checks it against the schema |
| Add a form field type | `app/types/ui.ts` union → renderer in `MuraFormField.vue` |
| Add a storefront rail | `HOME_SECTION_KEYS` + `default_home_layout()` + a **data migration** for existing tenants + `pages/index.vue` |
| Add a permission code | `PERMISSION_CATALOGUE` → **`python manage.py sync_roles`** |
| Add an email template | `DEFAULT_TEMPLATES` → **`python manage.py sync_email_templates`** |
| Expose a tenant setting to the storefront | **both** `TenantSettingsSerializer.Meta.fields` **and** `TenantPublicSerializer.get_settings()` |
| Add a finance figure | `analysis.py` (never `services.py` — that writes) |
| Add a parallax layer | give it overscan in CSS and travel via `parallaxShift()` — never a second magic number |
| Add a figure to a screen | follow it back to the query and forward to the decision it changes (P4) |
| Add an image to a table cell | wrap it in a fixed box; `MuraImage` alone does not guarantee a column edge |
| Change the API surface | code → `make openapi` → commit `docs/api/openapi.yaml` |
| Add a translated string | all three locales, or `locale-parity.test.ts` fails |

---

## 3. Invariants

Breaking one of these is a bug regardless of what the tests say.

1. **Money** — strings on the wire, integer cents in JS. `money_str` is the machine format; `money_display` is for prose. Never mix.
2. **Tenancy** — every query is scoped by `tenant_id`. Fixtures create two tenants so isolation tests mean something.
3. **Orders are append-only** — state changes through audited transitions, never a generic PATCH that could rewrite a total.
4. **Stock is a ledger** — absolute counts write a delta; reservations expire on a TTL.
5. **Imports are all-or-nothing** — a half-applied catalogue is worse than none.
6. **Emails queue inside the caller's transaction** and dispatch on commit, so a rollback emails nobody.
7. **Private media is signed for the host it will be requested on** — SigV4 covers the Host header.
8. **Dates without a time are not instants** — never round-trip them through UTC.
9. **The public product payload carries no quantity** — `in_stock`, `low_stock`, `waiting`; never a number of units.
10. **Diagnostics reports facts, never values** — a probe may say a key is set; it may never say what it is, not even masked.
11. **An estimate is labelled as one** — the forecast carries its basis and confidence; the price simulation carries its elasticity. A number a merchant will act on must say what kind of number it is.
12. **A write that cannot do what was asked must refuse** — never filter the unrecognised part and succeed. Twice this phase that would have deleted a merchant's photos silently.
13. **A write's response reports what was stored** — not what the instance was holding. Django's relation cache will happily echo pre-save values.
14. **Parallax travel is a share of measured overscan** — never a share of scroll distance. Two constants that must agree and have no stated relationship break on a different screen.
15. **A figure on screen is driven by something** — a query behind it and a decision in front of it, or it is decoration that looks like data (P4).

---

## 4. Phases

| Phase | State |
|---|---|
| 0 — Platform foundation | ✅ done (tenancy, catalog, cart, checkout, payments, inventory) |
| 1 — Admin dashboard | ✅ done (orders, products, stock, customers, finance, users, emails) |
| 2 — Correctness sweep | ✅ done — see `historic.md`; the dominant finding was unreachable code |
| 3 — Merchant tooling | ✅ done (import/export, reports, configurable home, pickers) |
| 4 — Performance & media | ✅ done (image pipeline, dev-server fix, healthcheck) |
| 5 — Storefront experience | ◑ partial — parallax home ✅, `/products` filters ✅, categories ✅; **animations and sale treatment still open** |
| 6 — Dashboard, money and scale | ✅ done — chrome, finance analysis, diagnostics, images at 10k |
| **7 — Merchant authoring and chrome** | **✅ done** — FAQs, categories, product gallery, stock rules, parallax, table alignment |
| 8 — Security hardening | queued — `maruth.security` skill written; **first full run still pending** |
| 9 — Production readiness | not started — real payment provider, backups, monitoring, load test |

> Security and production were 7 and 8; they moved down one when phase 7 was
> inserted. Neither had started, so nothing refers to the old numbers.

---

## 5. Risks

### Live

| Risk | Why it matters | Mitigation |
|---|---|---|
| **Unreachable code is the norm, not the exception** | Still the dominant defect. This phase alone found five more, including an endpoint that had never once resolved | Contract tests comparing two sides; read the network log, not just the screen |
| **Seed-time initialisation** | `sync_permissions` and `seed_default_templates` run at tenant *creation*. Anything added later reaches new tenants only — works on a fresh DB, dead on an existing one | `sync_roles` and `sync_email_templates`, on every deploy |
| **A silent catch hides a dead feature** | `useAdminPulse` 404'd invisibly for its whole life | Every swallowed error warns in dev |
| **Pug hides type errors** | A cast in a template is a runtime `SyntaxError`; the page never renders | `table-action-contract.test.ts` scans Pug for casts |
| **Two serializers for one model** | `TenantPublicSerializer.get_settings()` has its own allow-list; forgotten three times now | Test asserts the public tenant carries each field |
| **Worker/web do not reload** | Fixes look like they failed | Restart before concluding anything. This bit again this phase |
| **Vuetify's internals are load-bearing** | The rail fix depends on `--v-list-prepend-gap` and an explicit `grid-template-columns` | A Vuetify upgrade should re-measure the rail; the numbers are in `actual_step.md` |
| **A component prop can do nothing and look fine** | `v-divider absolute` rendered at `width: 0` for a whole release (M13) | Measure what a layout change was supposed to produce, not whether the page still looks alright |
| **Silent filtering on a write** | Two near-misses this phase, both would have destroyed merchant data | Refuse and say why; test the refusal leaves the old state intact |
| **Adding a home rail needs a data migration** | Existing tenants keep a stored layout; the serializer requires every known key | `0009_backfill_back_soon_section` is the worked example |

### Accepted

| Risk | Why accepted |
|---|---|
| mypy reports ~219 pre-existing errors | Baseline predates this work; not enforced in CI. Do not add to it. |
| Sandbox payment provider only | Real PIX provider is phase 8 |
| `/admin/customers` is read-only | CRUD needs backend work; no merchant has asked |
| Originals are destroyed on upload | Deliberate — 90% of storage was never read. Switchable via `MEDIA_IMAGE_MAX_DIMENSION=0` |
| Price elasticity is an assumption | It cannot be derived from this data. It is the merchant's input and is echoed back with every result |
| The ~130 ms pre-mount gap on table pages | A dev-server artifact; unmeasured against a production build |
| Scripted scrolling is blocked here | The parallax bound is proven by construction and by test rather than by watching it scroll |
| The FAQ falls back to shipped copy | A shop that writes nothing gets the platform's answers; merchant copy replaces them wholesale rather than merging, so the page never contradicts itself |

---

## 6. Commands

```bash
make up                 # start everything
make test               # both suites
make lint               # ruff + eslint
make openapi            # regenerate the schema
make openapi-check      # fail if it has drifted

docker compose restart web      # after ANY frontend change
docker compose restart worker   # after ANY task change

docker compose exec api python manage.py sync_roles             # every deploy
docker compose exec api python manage.py sync_email_templates   # every deploy
docker compose exec api python manage.py reprocess_images

# Admin screens are driven through a dev-only account. Delete before deploying.
#   qa.claude@murasfood.local  (ADMINISTRATOR, demo tenant)
```
