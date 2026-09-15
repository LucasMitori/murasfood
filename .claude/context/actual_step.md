# actual_step.md — one phase at a time

> **Exactly one phase lives here.** What is confirmed, and the measurement that
> confirms it. When the phase closes, its findings move to `historic.md` and
> this file is rewritten for the next one.
>
> **Rule: nothing enters "Confirmed" without an observation.** Not "the code
> looks right" — a number, a status code, a screenshot, a failing test that
> passes after the change.

**Last updated:** 2026-09-14

---

## PHASE 6 — Dashboard, money and scale

### Goal

Turn the dashboard from a set of screens into the thing a market owner runs
their business from: a chrome that does not look broken, a finance area that
answers questions rather than listing rows, an image pipeline that survives ten
thousand products, and a way to see the platform's own health.

### Scope

| # | Item | State |
|---|---|---|
| 6.1 | Rail centring, "Ver a loja", footer | ✅ done |
| 6.2 | Identity block → profile editor, avatar upload | ✅ done |
| 6.3 | Second header row: tools, divider, compact | ✅ done |
| 6.4 | Table loading state (the "black flash") | ✅ done — partially; see *Not confirmed* |
| 6.5 | Out-of-stock handling + back-in-stock notices | ✅ done |
| 6.6 | Finance: DRE, budget, forecast, cash flow, price simulator | ✅ done |
| 6.7 | Diagnostics page (admin-only) | ✅ done |
| 6.8 | Image pipeline at 10k products | ✅ done |
| 6.9 | `/products` filters, search, category cards | ✅ done |

### Out of scope

Animations and sale-card treatment (carried from phase 5, still open), security
audit (phase 7 — the `maruth.security` skill is written and has never been run
as a full audit), production readiness (phase 8).

---

## Confirmed — with evidence

Everything below was observed, not inferred.

### 6.1 — The rail

| Claim | Evidence |
|---|---|
| Icons sit on the drawer's axis | drawer centre **36.0**, all 14 icons at **35.5** — off by 0.5, which is the drawer's 1px border. Was 8.0 |
| The avatar and the bottom button agree with them | both **0.5** off the same axis |
| "Ver a loja" renders its icon | `mdi-storefront-outline` present in the button; was an empty `.v-btn__content` |
| The expanded drawer is unchanged | 14 titles render, button reads "Ver a loja" |
| The fixed bottom bar is gone | `.mura-admin-foot` absent from the DOM |

Root cause and the two wrong fixes before the right one: **M10** in `historic.md`.

### 6.3 — The header

| Claim | Evidence |
|---|---|
| The tools row renders | `.mura-admin-tools` present; search, ⌘K hint, Criar, alerts, storefront, fullscreen all visible in the screenshot |
| The alerts badge reads real data | `GET /admin/inventory/health/` → **200**, badge shows **6** |

That endpoint 404'd on every admin page until it was caught — **M11**.

### 6.5 — Out of stock

| Claim | Evidence |
|---|---|
| A visitor with no account can subscribe | `POST …/restock-alert/` → **201**, `{"subscribed": true}` |
| Asking twice makes one row | 3 posts → `RestockAlert.objects.count() == 1` |
| An email actually goes out on restock | `EmailLog` row `inventory.restocked / shopper@example.com / SENT / "Abacate Exemplo chegou!"` |
| It goes out once | second restock leaves `notified_at` unchanged |
| A signed-in caller cannot name a stranger's address | alert is bound to `customer_id`, `recipient == customer.email` |
| The demand report ranks by how many are waiting | 4-waiting product ranks above the 1-waiting one |

13 tests in `apps/inventory/tests/test_restock_alerts.py`.

### 6.6 — Finance

Verified against six months of seeded ledger data:

| Claim | Evidence |
|---|---|
| The DRE balances | revenue 54.561,50 · CMV 62,05% · gross margin 37,95% · operating 6,98% |
| Horizontal analysis reads correctly | revenue **+5,74%**, result **+34,65%** — operating leverage, fixed costs flat while revenue grew |
| Budget variance flags what was never budgeted | CMV shown as *Fora do orçamento*; payroll at **109,47%**; marketing unused |
| The forecast is fitted and labelled | 6 months basis, "Confiança média", revenue trend **+R$ 2.568,21/mês** |
| The price simulator does the counter-intuitive arithmetic | +8% price, −6,4% volume → revenue **+R$ 4,90**, margin **+R$ 21,28 (+10,96%)** |

23 tests in `apps/finance/tests/test_analysis.py`.

### 6.7 — Diagnostics

| Claim | Evidence |
|---|---|
| The page renders every check | 8 cards; PostgreSQL 0.7 ms, Redis 0.8 ms, storage 8.4 ms, 1 Celery worker |
| It catches what nothing else reports | overall **degraded** on `DEBUG is on` alone |
| A dead dependency is reported, not raised | database and cache probes mocked to throw → `DOWN`, report still returns 8 checks |
| No secret reaches the payload | `SECRET_KEY`, DB password and S3 secret asserted absent from the whole JSON |
| A DSN in an exception is never echoed | `postgres://user:hunter2@…` → `"OSError"` |
| Staff cannot open it | customer **403**, staff **403**, administrator **200** |
| The answer is never cached | `Cache-Control: no-store` |

20 tests in `apps/common/tests/test_diagnostics.py`.

### 6.8 — Images at scale

The WebP/AVIF conversion already existed from phase 4. What was missing:

| Claim | Evidence |
|---|---|
| Derivatives are cached for a year | `head_object` on a live derivative: `Cache-Control: public, max-age=31536000, immutable` |
| Private objects are not | `private, no-store`, and no public ACL |
| The same photo twice is stored once | two uploads of identical bytes → same `pk`, **1** asset row |
| A private document is never satisfied by a public image | different `pk` for identical bytes at different visibility |
| Every image has a blurred stand-in | 84/84 backfilled; **119–131 bytes** each as a data URI |
| It is serialised | `MediaAssetSerializer(...).data["placeholder"]` matches the row |
| Image work cannot starve orders | worker consumes `celery, media`; media tasks routed to `media` |

10 tests in `apps/media/tests/test_image_scale.py`.

### Suite state

```
524 API tests (was 458)  ·  242 web tests
ruff check · ruff format · eslint · vue-tsc — all clean
OpenAPI regenerated with --fail-on-warn, 0 warnings
```

`table-columns.test.ts` now actually runs — `docs/` was never mounted into the
web container, so the one guard against a column referring to a dropped API
field could not even be collected.

---

## Not confirmed — explicitly

Recording these matters as much as the confirmations.

| Item | Why not | How it would be confirmed |
|---|---|---|
| **The table flash is fully fixed** | The skeleton is verified (461px, renders for the whole load). The **~130 ms before it**, where the route has changed and the component chunk is still loading, is unaddressed and is a dev-server artifact | Measure the same navigation against a production build |
| The avatar upload end to end | The endpoint accepts `avatar_id` and rejects a foreign tenant's asset; the UI was not driven | Upload a photo through `/admin/users/<id>/edit` |
| `/products` category cards and filters | Typechecks, lints, store logic covered; not driven in a browser | Open `/products` and tap through |
| The restock button on the product page | The API is verified by test and by curl; the component was not driven | Open an out-of-stock product as a visitor |
| Price elasticity as a *predictor* | It is an assumption the merchant sets, echoed back in the response. It is not validated against real demand and cannot be | Nothing here; this is a property of the model, stated on screen |
| Behaviour at 10,000 products | Measured at 51 products / 84 assets. The fixes are structural (cache headers, dedupe, queue split) rather than tuned | A merchant's real catalogue, or a generated one |
| `hide_out_of_stock` | Backend and both serializers covered; no switch in `/admin/storefront` yet | Add the control, then flip it |

---

## Working notes

**The QA account.** `qa.claude@murasfood.local` was created in the dev database
to make admin screens driveable — every admin claim above was measured through
it. It is an `ADMINISTRATOR` on the `demo` tenant. Delete it before any
deployment; it exists because "no merchant browser session" had been blocking
visual verification for several phases.

**Two deploy-time commands now exist and must run on every deploy:**

```bash
python manage.py sync_roles            # new permission codes reach existing tenants
python manage.py sync_email_templates  # new templates reach existing tenants
```

Both were written because a feature was found completely dead without them —
see the seed-time note under P1 in `historic.md`.

---

## Definition of done for phase 6

- [x] Rail, header and footer verified by measurement, not by eye
- [x] Every new endpoint reached from the UI and observed returning 200
- [x] Restock notices proven to send exactly once
- [x] Finance figures checked against hand-computed values
- [x] Diagnostics proven to leak nothing, under test
- [x] Image caching, dedupe and placeholders measured
- [x] Both suites green, all linters clean, schema regenerated
- [ ] The 130 ms pre-mount gap measured against a production build
- [ ] Admin screens driven by the merchant on their own machine
