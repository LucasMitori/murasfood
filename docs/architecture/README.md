# MurasFood — Architecture

## 1. Summary

A multi-tenant **modular monolith** with an API-first contract. One Django
process serves every domain; one PostgreSQL database holds every tenant's data,
partitioned by `tenant_id` and guarded at the query layer.

Microservices were rejected for this stage (ADR-001): the whole platform fits in
one transaction boundary, and checkout — the most correctness-sensitive flow —
touches pricing, promotions, delivery, inventory and orders in a single atomic
block. Splitting that across services would trade a real guarantee for
distributed-transaction complexity nobody needs at this scale.

## 2. Domain map

| Module          | Owns                                                        | Key invariants |
| --------------- | ----------------------------------------------------------- | -------------- |
| `common`        | Base models, error envelope, middleware, idempotency         | UUID PKs, tenant scoping, `Decimal` money |
| `tenants`       | Merchant identity, branding, settings, opening hours         | Nothing merchant-specific lives in code |
| `accounts`      | Users, roles, permission codes, tokens, addresses            | Email unique per tenant; tokens stored hashed |
| `catalog`       | Products, categories, brands, units, tags, favourites, search | Slug/SKU unique per tenant; archived, never deleted |
| `pricing`       | Prices, tiers, schedules, price history                      | History is append-only |
| `inventory`     | Stock levels, movements, reservations                        | Never overwritten; row-locked; non-negative |
| `promotions`    | Promotions, coupons, redemptions                             | Discounts computed server-side only |
| `cart`          | Anonymous and authenticated carts                            | Stores intent, not prices |
| `delivery`      | Delivery settings and zones                                  | Fees quoted server-side |
| `orders`        | Orders, items, status history, checkout                      | Immutable snapshots; explicit state machine |
| `payments`      | Payments, provider abstraction, webhooks, refunds            | Only a verified webhook confirms payment |
| `media`         | Assets, documents, banners, object storage                   | Signed URLs; upload signature validation |
| `notifications` | Email templates, delivery log, notifications                 | Async, retried, de-duplicated |
| `finance`       | Ledger, chart of accounts, P&L                               | Entries voided, never deleted |
| `reports`       | Dashboard aggregates, reports, PDF jobs                      | Aggregated in SQL, in tenant time |
| `audit`         | Audit log                                                    | Write-once |

Modules talk through `services.py` (write) and `selectors.py` (read). No module
reaches into another's ORM internals.

## 3. Request lifecycle

```
Request
  → RequestIDMiddleware        correlation id for logs, audit and errors
  → SecurityMiddleware / CORS
  → TenantMiddleware           preliminary tenant from header/host
  → DRF authentication         JWT
  → TenantScopedMixin.initial  AUTHORITATIVE tenant; user's tenant always wins
  → Permission classes         permission codes, not role names
  → View                       thin; delegates to services/selectors
  → api_exception_handler      one error envelope, never a stack trace
  → AccessLogMiddleware        structured line, secrets redacted
```

The two-phase tenant resolution matters: middleware runs before JWT
authentication, so its answer is a guess. `TenantScopedMixin` re-resolves once
the user is known and pins an authenticated non-platform user to their own
tenant, which is what makes header spoofing useless.

## 4. Data model highlights

Every domain table carries `id` (UUID), `tenant_id`, `created_at`, `updated_at`.
Uniqueness is scoped per tenant (`(tenant, slug)`, `(tenant, sku)`,
`(tenant, code)`), so two merchants can both sell "pao-frances".

```
Tenant ─┬─ TenantBranding / TenantSettings / BusinessHours
        ├─ User ─── UserRole ─── Role ─── Permission
        │     └─ Address, Cart, Favorite, Order
        ├─ Category ─┬─ CategoryTranslation
        │            └─ Product ─┬─ ProductImage → MediaAsset
        │                        ├─ ProductBarcode / ProductTranslation
        │                        ├─ ProductPrice ─ PriceHistory  (append-only)
        │                        └─ InventoryItem ─┬─ StockMovement (append-only)
        │                                          └─ StockReservation
        ├─ Promotion ─ Coupon ─ CouponRedemption
        ├─ Order ─┬─ OrderItem        (price + cost snapshots)
        │         ├─ OrderAddress     (address snapshot)
        │         ├─ OrderStatusHistory (append-only)
        │         └─ Payment ─┬─ PaymentEvent  (webhook ledger, unique event id)
        │                     └─ PaymentRefund
        ├─ FinancialTransaction ─ FinancialCategory / FinancialAccount
        └─ AuditLog                    (write-once)
```

Composite indexes follow the query patterns that actually exist:
`(tenant, status, -created_at)` for order lists, `(tenant, category, is_active)`
for catalog browsing, `(tenant, -placed_at)` for reporting windows.

## 5. Checkout — the critical path

Ordering is deliberate and each step is covered by tests:

1. Validate the cart — products purchasable, prices resolvable, stock available.
2. **Re-price every line** from the pricing engine. Client amounts are ignored.
3. Recompute discounts from the promotion rules currently in force.
4. Quote delivery server-side from the tenant's zones and thresholds.
5. Reserve stock under `SELECT … FOR UPDATE`, re-checking availability inside the lock.
6. Write the order with immutable snapshots (name, SKU, unit, price, cost).
7. Leave it `PENDING_PAYMENT` and open a payment.

The whole thing runs in one transaction and behind an `Idempotency-Key`, so a
double-tapped button returns the first order instead of creating a second.

Payment then follows its own path: the provider calls back, the signature is
verified *before* the body is trusted, the event id is recorded (unique
constraint), the amount is compared against what was charged, and only then does
the order move to `PAID` and the stock reservation become a sale.

## 6. Security model

| Concern              | Approach                                                          |
| -------------------- | ----------------------------------------------------------------- |
| Tenant isolation     | `for_tenant()` + post-auth resolution + 404 (not 403) on cross-tenant reads |
| Authorization        | Permission codes (`orders.refund`), never role-name checks         |
| Authentication       | JWT, 15-minute access tokens, rotating and blacklisted refresh tokens |
| Credential storage   | Hashed passwords; auth tokens stored as SHA-256 digests            |
| Brute force          | Login attempts recorded; lockout on repeated failure               |
| Webhooks             | HMAC signature required; missing secret fails closed               |
| Idempotency          | Stored responses keyed by scope + key + tenant; payload mismatch rejected |
| Uploads              | Size, allow-list, and **file-signature** validation; filename sanitised |
| Private files        | Signed, expiring URLs; buckets never public                        |
| Logging              | Secrets redacted by a filter; bodies never logged                  |
| Errors               | One envelope, stable codes, no stack traces                        |
| LGPD                 | Anonymisation instead of deletion; data export; audited access     |

## 7. Frontend architecture

Nuxt 4 with SSR for the storefront (products must be indexable) and client-only
rendering for the dashboard (authenticated, personalised, nothing to pre-render).

- **State**: Pinia holds session, cart, favourites, filters and UI state. Server
  data is fetched per page rather than mirrored into a global store.
- **Money**: amounts stay strings; unavoidable arithmetic happens in integer
  cents. Totals always come from the API.
- **i18n**: pt-BR, en, es. No user-facing string is hard-coded — including error
  messages, which map from the API's stable error codes.
- **Theming**: two brand-neutral themes (soft white with a wine accent; near
  black with white highlights). A tenant's colours override only `primary` and
  `accent` — backgrounds and text stay under our control so a merchant cannot
  make their own storefront unreadable.
- **Accessibility**: skip link, visible focus ring, semantic headings, labelled
  controls, and status never signalled by colour alone.

## 8. Background work

| Task                          | Cadence   | Why it exists                              |
| ----------------------------- | --------- | ------------------------------------------ |
| Release expired reservations  | 1 min     | An abandoned checkout must not hold stock  |
| Expire stale payments         | 5 min     | Closes the PIX window and frees the order  |
| Reconcile pending payments    | on demand | Webhooks get lost; the provider is the truth |
| Retry failed emails           | 10 min    | An SMTP outage should self-heal            |
| Purge expired tokens          | hourly    | Bounded tables, smaller leak blast radius  |
| Project orders to the ledger  | scheduled | Keeps a ledger hiccup out of checkout      |
| Generate reports / PDFs       | on demand | Long work never blocks an HTTP worker      |

## 9. Deferred deliberately

Recorded so they read as decisions rather than oversights:

- Product variants (size/colour) — units and package size cover the current market.
- Elasticsearch — PostgreSQL full-text plus trigram is sufficient until it is not.
- Multi-branch inventory — the schema keeps the door open (ADR-002).
- Marketplace/multi-merchant checkout — the tenant model already anticipates it.
- Machine-learning recommendations — the rule-based selector is behind an
  interface a smarter implementation can replace.
