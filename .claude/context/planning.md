# planning.md — the map

> Where the code lives, which phase we are in, what is likely to bite.
> Update when the shape of the project changes, not on every commit.

**Last updated:** 2026-09-13

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
│   │       ├── audit/              append-only action log
│   │       ├── cart/               carts, shopping lists
│   │       ├── catalog/            products, categories, brands, units
│   │       │   └── importexport.py ← spreadsheet round trip
│   │       ├── common/             shared services + cross-cutting tests
│   │       │   ├── money.py        money_str (wire) vs money_display (prose)
│   │       │   ├── spreadsheets.py CSV + XLSX read/write
│   │       │   └── exports.py      inventory / customers / orders columns
│   │       ├── delivery/           zones, fees
│   │       ├── finance/            ledger, categories, P&L
│   │       ├── inventory/          stock, reservations, batches, expiry
│   │       ├── media/              uploads, derivatives, storage backends
│   │       ├── notifications/      email templates, logs, delivery
│   │       ├── orders/             checkout, state machine, transitions
│   │       ├── payments/           PIX, providers, webhooks
│   │       ├── pricing/            prices, history
│   │       ├── promotions/         coupons, discounts
│   │       ├── reports/            dashboard, sales/stock/customer reports
│   │       └── tenants/            tenant, branding, settings, hours
│   └── web/                        Nuxt 4
│       ├── app/
│       │   ├── components/
│       │   │   ├── catalog/        product card, hero, price chart
│       │   │   ├── dashboard/      stat card, chart card
│       │   │   ├── navigation/     header, footer
│       │   │   └── shared/         Mura* — the design system
│       │   ├── composables/        useServerTable, useMoney, usePermission…
│       │   ├── layouts/            default, admin
│       │   ├── pages/              file-based routes
│       │   ├── stores/             Pinia
│       │   └── utils/              api-client, format, theme, validation
│       ├── i18n/locales/           pt-BR · en · es  (parity is enforced)
│       ├── scripts/healthcheck.mjs warms the dev server
│       └── tests/                  vitest — contracts, i18n, routes, stores
├── docs/api/openapi.yaml           generated; `make openapi-check` guards drift
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
| Add a storefront band | `HOME_SECTION_KEYS` + `default_home_layout()` + `pages/index.vue` |
| Expose a tenant setting to the storefront | **both** `TenantSettingsSerializer.Meta.fields` **and** `TenantPublicSerializer.get_settings()` |
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

---

## 4. Phases

| Phase | State |
|---|---|
| 0 — Platform foundation | ✅ done (tenancy, catalog, cart, checkout, payments, inventory) |
| 1 — Admin dashboard | ✅ done (orders, products, stock, customers, finance, users, emails) |
| 2 — Correctness sweep | ✅ done — see `historic.md`; the dominant finding was unreachable code |
| 3 — Merchant tooling | ✅ done (import/export, reports, configurable home, pickers) |
| 4 — Performance & media | ✅ done (image pipeline, dev-server fix, healthcheck) |
| **5 — Storefront experience** | **◀ current** — parallax home, filters, animations, sale treatment |
| 6 — Security hardening | queued — `maruth.security` skill written; first full run pending |
| 7 — Production readiness | not started — real payment provider, backups, monitoring, load test |

---

## 5. Risks

### Live

| Risk | Why it matters | Mitigation |
|---|---|---|
| **Unreachable code is the norm, not the exception** | Two thirds of this session's findings. A green suite proves nothing about whether a feature is *reached*. | Contract tests that compare the two sides; verify against the running app |
| **Pug hides type errors** | A cast in a template is a runtime `SyntaxError`; the page never renders | `table-action-contract.test.ts` scans Pug for casts |
| **Two serializers for one model** | `TenantPublicSerializer.get_settings()` has its own allow-list; adding a field to the model is not enough | Test asserts the public tenant carries it |
| **Worker/web do not reload** | Fixes look like they failed | Documented in `handoff.md`; restart before concluding anything |
| **No admin browser session available** | Several admin screens are unverified visually | Endpoints exercised directly; flagged in PR |
| **Parallax + SSR** | `v-parallax` measures the viewport; the server cannot | Gate on hydration, as with the header |

### Accepted

| Risk | Why accepted |
|---|---|
| mypy reports ~219 pre-existing errors | Baseline predates this work; not enforced in CI. Do not add to it. |
| Sandbox payment provider only | Real PIX provider is phase 7 |
| `/admin/customers` is read-only | CRUD needs backend work; no merchant has asked |
| Originals are destroyed on upload | Deliberate — 90% of storage was never read. Switchable via `MEDIA_IMAGE_MAX_DIMENSION=0` |

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
docker compose exec api python manage.py reprocess_images
```
