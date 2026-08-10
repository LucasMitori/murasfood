# MurasFood

A white-label local commerce platform for supermarkets, bakeries, grocers and
neighbourhood markets. One deployment serves many merchants: every name, colour,
logo, price rule, opening hour and legal link lives in the database, so
onboarding a new merchant is a row, not a fork.

**The codebase contains no real merchant's data.** Demo content is obviously
fictitious by design.

---

## What is here

| Path                    | What it is                                                        |
| ----------------------- | ----------------------------------------------------------------- |
| `apps/api`              | Django 5 + DRF modular monolith. The whole domain and the API.     |
| `apps/web`              | Nuxt 4 storefront **and** merchant dashboard (Vuetify 3, Pug, TS). |
| `apps/mobile`           | React Native (Expo) scaffold — see its README for status.          |
| `infrastructure/`       | Dockerfiles, reverse proxy, backup/restore scripts.                |
| `docs/`                 | Architecture, ADRs, database, API, deployment, security.           |
| `docker-compose.yml`    | Development stack.                                                 |
| `docker-compose.prod.yml` | Production stack (no dev servers, non-root, health checks).      |

## Current state

| Area                | State                                                              |
| ------------------- | ------------------------------------------------------------------ |
| Backend             | Complete for MVP release 1. **251 tests passing**, Ruff clean.      |
| API surface         | 227 documented operations, OpenAPI generated with 0 errors.         |
| Web                 | Storefront + dashboard core flows. **129 tests passing**, ESLint and `vue-tsc` clean, production build green. |
| Mobile              | Scaffold and contract only — not implemented.                       |
| Deployment          | Compose files and scripts written; **not yet exercised on a server**.|

See [Known gaps](#known-gaps) for what is deliberately not done.

---

## Quick start

Prerequisites: Docker and Docker Compose.

```bash
cp .env.example .env
```

```bash
make up
```

```bash
make migrate && make seed
```

Then:

| Service            | URL                             |
| ------------------ | ------------------------------- |
| Storefront         | http://localhost:3000           |
| API                | http://localhost:8000/api/v1/   |
| API docs (Swagger) | http://localhost:8000/api/docs/ |
| Mail catcher       | http://localhost:8025           |
| Object storage     | http://localhost:9001           |
| Django admin       | http://localhost:8000/django-admin/ |

Demo accounts created by `make seed` (all with the password `demo1234`):

- `admin@demo.test` — administrator, every permission
- `gerente@demo.test` — manager
- `atendente@demo.test` — staff, deliberately limited
- `cliente@demo.test` — customer

### Without Docker

The backend runs against SQLite with no services at all, which is how the test
suite stays fast:

```bash
cd apps/api && python -m venv .venv && ./.venv/Scripts/pip install -r requirements/development.txt
```

```bash
cd apps/api && pytest
```

```bash
cd apps/web && npm install && npm run dev
```

---

## Quality gates

```bash
make test
```

Individually:

| Command                                | Checks                                  |
| -------------------------------------- | --------------------------------------- |
| `cd apps/api && pytest`                | 251 backend tests                       |
| `cd apps/api && ruff check . && ruff format --check .` | Lint and formatting     |
| `cd apps/api && python manage.py makemigrations --check --dry-run` | No drifted migrations |
| `cd apps/web && npm run test`          | 129 frontend tests                      |
| `cd apps/web && npm run lint`          | ESLint (Pug-aware)                      |
| `cd apps/web && npm run typecheck`     | `vue-tsc`, strict                       |
| `cd apps/web && npm run build`         | Production build                        |

CI runs all of these on every pull request against real PostgreSQL and Redis.

---

## Architecture in one page

A **multi-tenant modular monolith** with an API-first contract. Not
microservices: the boundaries are Django applications with explicit
service/selector layers, so a domain can be extracted later if load ever
justifies it — and until then there is one deployable, one database and one
transaction boundary.

```
                    ┌──────────────┐
   Storefront ─────▶│              │
   Dashboard  ─────▶│  Django API  │──▶ PostgreSQL   (tenant_id on every row)
   Mobile     ─────▶│   /api/v1    │──▶ Redis        (cache + Celery broker)
                    │              │──▶ Object store (S3-compatible, signed URLs)
                    └──────┬───────┘──▶ SMTP
                           │
                    Celery worker + beat
                    (email, images, PDFs, reconciliation, expiry)
```

Each domain module owns its data and exposes behaviour through services:

`tenants` · `accounts` · `catalog` · `pricing` · `inventory` · `promotions` ·
`cart` · `delivery` · `orders` · `payments` · `media` · `notifications` ·
`finance` · `reports` · `audit` · `common`

Full detail: [`docs/architecture/README.md`](docs/architecture/README.md).
Decisions and their trade-offs: [`docs/architecture/adr/`](docs/architecture/adr/).

---

## The rules this codebase is built around

These are enforced by code and covered by tests, not by convention:

1. **Tenant isolation.** Every tenant-owned query goes through `for_tenant()`,
   and `TenantScopedMixin` re-resolves the tenant *after* authentication — a
   client-supplied `X-Tenant` header can never move an authenticated user.
2. **The server owns money.** Prices, discounts and delivery fees are recomputed
   at checkout. The client sends intent, never amounts.
3. **Orders are snapshots.** Line items freeze name, SKU, unit, price and cost.
   A later price change cannot rewrite history.
4. **Only a verified webhook confirms payment.** Signature checked before the
   body is read; the event id makes replays no-ops.
5. **Stock is a ledger.** Nothing overwrites a quantity — every change writes a
   movement, and reservations are taken under `SELECT … FOR UPDATE`.
6. **`Decimal` everywhere.** No float touches money, on either side of the wire
   (amounts cross as strings).
7. **History is append-only.** Price history, order status history and the audit
   log reject updates at the model level.
8. **Nothing merchant-specific in code.** Branding, hours, currency, legal links
   and email copy are all rows.

---

## Known gaps

Stated plainly so nobody discovers them at the wrong moment:

- **Mobile app is a scaffold.** Contract and structure only.
- **Deployment is untested on a real host.** The compose files, Caddyfile and
  backup scripts are written and internally consistent, but nothing has been run
  on a Hetzner box. A backup is not implemented until a restore has been
  exercised — `infrastructure/scripts/restore-db.sh` exists and has not been.
- **The payment provider is a sandbox.** It produces genuinely valid PIX BR
  Codes and exercises the real webhook path, but moves no money. Production
  settings emit a warning if it is still configured.
- **Dashboard pages beyond the overview** (products, orders, inventory, finance
  screens) have routes and permissions but not full UIs; the APIs behind them
  are complete and tested.
- **Product variants** are not modelled. Products carry a unit and a package
  size, which covers weighed and packaged goods; size/colour variants are a
  Phase 2 schema addition (recorded in ADR-011).
- **`mypy` is advisory** in CI rather than blocking, pending full annotation
  coverage.
- **Frontend tests cover the logic layer** — stores, API client, money,
  formatters, theme — not rendered components. The production build plus
  `vue-tsc` cover compilation; component rendering is not asserted.

## Next steps

1. Exercise a deployment end to end on a staging host, including a restore drill.
2. Integrate a real Brazilian PSP behind the existing `PaymentProvider` interface.
3. Build out the remaining dashboard screens against the finished APIs.
4. Extract `packages/` shared modules, then implement the mobile app.

---

## Licence and attribution

Internal project. Demo data is fictitious and must never be seeded into a
production database — `seed_demo` refuses to run with `DEBUG=False` unless
explicitly forced.
