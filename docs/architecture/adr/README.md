# Architecture Decision Records

Each record states the context, the decision, what was rejected and what it
costs. They are kept in one file because they were all taken together at the
start of the project and read better as a set; individual files are appropriate
once decisions start arriving one at a time.

---

## ADR-001 — Modular monolith, not microservices

**Context.** The platform spans catalog, pricing, inventory, promotions, cart,
orders, payments, reporting and finance. The initial deployment is one merchant
on one small server.

**Decision.** One Django process, one database, domain boundaries expressed as
Django applications with explicit `services`/`selectors` layers.

**Alternatives.** Microservices per domain; a service mesh; separate read/write
services.

**Consequences.** Checkout — which touches five domains — stays in a single
transaction, so "stock reserved but order not written" is impossible by
construction. The cost is that scaling is coarse-grained: a busy catalog scales
the order code with it. The service/selector boundaries mean a domain can be
extracted later without rewriting its callers.

---

## ADR-002 — Shared-schema multi-tenancy with `tenant_id`

**Context.** One deployment must serve many merchants, and a merchant may later
want multiple branches.

**Decision.** A single schema. Every tenant-owned table carries `tenant_id`;
uniqueness constraints are scoped per tenant; queries go through `for_tenant()`
and a post-authentication resolver.

**Alternatives.** A database per tenant; a PostgreSQL schema per tenant; row-level
security policies.

**Consequences.** Migrations run once, connection pooling stays simple, and
cross-tenant reporting is a query rather than a pipeline. The risk is that one
missing filter leaks data, which is why isolation is enforced in a base mixin
and covered by tests that attack it from several directions. RLS remains
available as defence in depth if the threat model tightens.

---

## ADR-003 — PostgreSQL with UUID primary keys

**Context.** The domain is relational and money-bearing.

**Decision.** PostgreSQL, UUIDv4 primary keys, `Decimal` for every monetary
column, check constraints for domain invariants.

**Alternatives.** Sequential integer keys; a document store; keeping integrity
checks only in application code.

**Consequences.** Identifiers are non-guessable in URLs and safe to generate
before insert, which the order and payment flows rely on. UUID indexes are wider
than integers — acceptable at this scale. Database-level constraints mean a bug
in a service cannot write a negative total.

---

## ADR-004 — S3-compatible object storage behind an interface

**Context.** Product photos, banners, invoices and generated PDFs.

**Decision.** Binary data never enters PostgreSQL. An abstract `StorageBackend`
with a local-filesystem implementation for development and an S3-compatible one
for production; private objects served through signed, expiring URLs.

**Alternatives.** Database blobs; the container filesystem; a hard dependency on
one vendor's SDK.

**Consequences.** The API stays stateless and horizontally scalable, and
switching from MinIO to Cloudflare R2 is an environment variable. Tests run
against the local backend with no network.

---

## ADR-005 — Payment provider abstraction

**Context.** PIX first, cards later; the Brazilian PSP market changes and
merchants negotiate their own rates.

**Decision.** The application depends on a `PaymentProvider` interface
(`create_payment`, `get_payment`, `cancel_payment`, `refund_payment`,
`validate_webhook`, `parse_webhook`). The shipped implementation is an offline
sandbox that produces genuinely valid BR Codes and exercises the real webhook
path.

**Alternatives.** Integrating one PSP's SDK directly; a hosted checkout redirect.

**Consequences.** Swapping acquirers is a new module plus an environment
variable, and the entire payment flow is testable offline. The interface has to
be general enough for providers with different capabilities, which costs some
expressiveness. Production settings warn loudly if the sandbox is still
configured.

---

## ADR-006 — JWT with rotating refresh tokens

**Context.** Three clients — web, dashboard and a future mobile app — against
one API.

**Decision.** Short-lived (15-minute) access tokens carrying tenant and user-type
claims; refresh tokens that rotate on use and are blacklisted; every session
revoked on password change or reset.

**Alternatives.** Session cookies; long-lived tokens without rotation;
OAuth2 with an external identity provider.

**Consequences.** A mobile client needs no cookie handling, and revocation
actually works. The cost is a blacklist table to prune and tokens living in
client storage — mitigated by their short lifetime and by rotation, with an
httpOnly-cookie variant available if the threat model demands it.

---

## ADR-007 — Celery with Redis

**Context.** Email, image derivatives, PDF rendering, reconciliation and expiry
must not block HTTP workers.

**Decision.** Celery for tasks and beat for schedules, Redis as broker and cache.

**Alternatives.** Database-backed queues; cron plus management commands;
in-process threads.

**Consequences.** A merchant's checkout never waits on an SMTP handshake, and
retries with backoff are declarative. It adds a broker to operate. Tasks run
eagerly in tests, and `transaction.on_commit` ensures a worker never picks up a
row that was rolled back.

---

## ADR-008 — REST, versioned, OpenAPI-generated

**Context.** Three first-party clients and possible third-party integrations.

**Decision.** REST under `/api/v1/`, schema generated from the code with
drf-spectacular, one error envelope with stable machine-readable codes.

**Alternatives.** GraphQL; RPC; hand-written API documentation.

**Consequences.** Caching, debugging and client generation are straightforward,
and documentation cannot drift from the implementation because it is derived
from it. Clients sometimes over-fetch relative to GraphQL, which the composite
endpoints (`/catalog/home/`, `/admin/dashboard/`) address where it matters.

---

## ADR-009 — React Native for mobile

**Context.** Android-first audience, a TypeScript-strong team, and an existing
web client whose non-visual layer is already framework-agnostic.

**Decision.** React Native with Expo, consuming the same `/api/v1` contract.

**Alternatives.** Flutter; native Kotlin and Swift; a PWA only.

**Consequences.** The API client, money handling, types and translations move
across with little change, so business rules are not reimplemented per platform.
Vue on web and React on mobile means component code is not shared — an accepted
trade, since the logic is what matters and the spec forbids React in the web
frontend.

---

## ADR-010 — `Decimal` end to end, strings on the wire

**Context.** JavaScript numbers are IEEE-754 doubles. `0.1 + 0.2 !== 0.3`.

**Decision.** `Decimal` in Python with explicit `ROUND_HALF_UP` quantisation;
amounts serialised as **strings**; the frontend parses to integer cents for the
rare local arithmetic; authoritative totals always come from the backend.

**Alternatives.** Floats; integer cents in the database; JSON numbers.

**Consequences.** Rounding is defined and testable, and a total never drifts by
a cent between the cart and the invoice. Clients must remember not to do
arithmetic on the strings, which the `money` module and its tests enforce.
Database aggregates are normalised through one helper so the API returns
`"25.00"` regardless of which backend produced it.

---

## ADR-011 — Deferrals: variants, Caddy, and search

Three smaller decisions worth recording:

**Product variants are not modelled.** A product carries a sale unit and a
package size, which covers weighed goods (`1.350 kg`) and packaged goods
(`1 kg pack`) — the actual requirement for a market or bakery. Size/colour
variants would add a dimension to inventory, pricing, cart and order items for a
case that does not yet exist. Adding them later is an additive migration; getting
them wrong now would touch every one of those modules.

**Caddy rather than nginx** as the reverse proxy, because it provisions and
renews TLS automatically. One less thing to forget on a single-merchant
deployment. Nginx remains a drop-in replacement.

**PostgreSQL full-text plus trigram** for search, not Elasticsearch. It handles
accent-insensitive matching and typos for a catalog of this size with no extra
service to run. The search module degrades to `icontains` on non-PostgreSQL
backends so the test suite needs no database server, and the interface is a
single function to replace when scale justifies it.
