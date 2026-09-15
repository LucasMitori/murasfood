# Security audit — MurasFood

**Date:** 2026-09-15
**Scope:** `github.com/LucasMitori/murasfood`, branch `feat/merchant-tooling-and-platform-fixes`, commit `04b656e` — 499 tracked files. Live probing limited to the owner's own `localhost` containers.
**Method:** stack profiling, automated scanning (secrets, git history, dependencies, static anti-patterns, header probe), manual review by layer, and live exploit verification against a throwaway two-tenant fixture created and removed during the audit.
**Not covered:** no deployed production host exists to probe, so production headers, TLS configuration and the Caddy proxy rules are reviewed as code only. No load or DoS testing. No review of the `maruth-security` skill's own scripts. The MinIO bucket policy was not inspected from the storage side.

---

## Verdict

One critical flaw: **a merchant whose account has been suspended can read and write any other merchant's data** by sending a single HTTP header. It is exploitable today, needs no special tooling, and I confirmed it end to end — a suspended tenant's administrator renamed a product belonging to a different tenant and got `HTTP 200`. Everything else found is hardening.

The rest of the codebase is in genuinely good shape: no SQL injection, no raw SQL, no `__all__` serializers, no secrets in the repository or its history, correctly signed payment webhooks with constant-time comparison, thorough production transport hardening, and object-level ownership enforced on every customer-facing queryset I read.

**Blast radius if the application were fully compromised:** every merchant's product catalogue, pricing and cost data, customer names/emails/phones/addresses, full order and payment history, the financial ledger, and staff accounts — across all tenants on the deployment. Payments themselves are sandboxed, so no real money moves yet.

| Severity | Count |
|---|---|
| Critical | 1 |
| High | 1 |
| Medium | 3 |
| Low | 4 |

---

## Do these first

1. **Close the tenant fall-through** — `apps/api/apps/tenants/resolver.py:118`. A non-platform user must be pinned to `user.tenant` unconditionally; a non-operational tenant must produce a refusal, never a fall-through to the header.
2. **Refuse login when the tenant is not operational** — `apps/api/apps/accounts/serializers.py:263`. Today only `user.is_active` is checked.
3. **Add the missing isolation test** — the guard that should have caught this (`test_header_cannot_move_an_authenticated_user`) exists and passes; it only ever runs against a healthy tenant.

Everything else can wait for the next sprint.

---

## Findings

### [CRITICAL-1] A suspended tenant's staff can read and write every other tenant's data

**Where:** `apps/api/apps/tenants/resolver.py:105-123`

**What it is**

`resolve_tenant_for_request()` is the authoritative tenant resolution, and the
file's own docstring states the rule it exists to enforce:

> an authenticated non-platform user is **always** pinned to their own tenant. A
> client-supplied `X-Tenant` header can never move them, otherwise cross-tenant
> access would be one header away.

The implementation does not hold to that in one branch:

```python
tenant = getattr(user, "tenant", None)
if tenant is not None and tenant.is_operational:
    return tenant
# a user whose tenant is suspended falls past the guard entirely
return resolve_tenant_from_request(django_request)   # <-- honours X-Tenant
```

`is_operational` is `is_active and status == ACTIVE`. So the moment a merchant is
**suspended or deactivated**, every one of their staff accounts stops being
pinned and starts choosing its own tenant by header.

This is the worst possible timing: suspension is what happens when a merchant
stops paying or is removed for cause — precisely the population you least want
holding a key to a competitor's catalogue.

**How it is exploited**

1. Merchant A is suspended (`status = SUSPENDED`), which is a routine billing action.
2. A staff user of merchant A logs in normally — `POST /api/v1/auth/login/` with no `X-Tenant` header at all. Login succeeds; it checks `user.is_active`, never the tenant.
3. They call any merchant endpoint with `X-Tenant: <victim-slug>`.
4. They now hold read **and write** access to that merchant's catalogue, customers, orders, finance ledger and staff list.

**Evidence**

Reproduced against two throwaway tenants created for this audit and deleted
afterwards. Baseline first — while tenant A is healthy, the guard works:

```
=== BASELINE: tenant A healthy, asking for tenant B ===
  products returned: 0
  leaked B secret?  False
```

Then tenant A is suspended and nothing else changes:

```
A status: SUSPENDED | operational: False

=== can the user still authenticate? ===
  eyJhbGciOiJIUzI1NiIs... (len 408)

=== EXPLOIT: suspended-tenant user asks for tenant B ===
  products returned: 1 ['SEGREDO DO TENANT B']
  >>> CROSS-TENANT READ: True
```

It is not read-only:

```
=== WRITE probe: rename another tenant's product ===
  HTTP 200
  name now: ALTERADO POR TENANT A
```

And it reaches the whole admin surface — every one of these answered `200`
scoped to the victim tenant:

```
  admin/customers                    200
  admin/orders                       200
  admin/finance/transactions         200
  admin/users                        200
  admin/system/diagnostics           200
  admin/finance/summary              200
```

**Why nothing stops it**

Three controls look like they should, and none does:

- **`TenantScopedMixin.get_queryset()`** filters by `self.tenant` — but `self.tenant` *is* the attacker-chosen tenant. It is filtering correctly to the wrong answer.
- **`TenantScopedMixin.get_object()`** raises `CrossTenantAccessError` when an object's tenant differs from `self.tenant_id` — same problem; both sides agree.
- **`HasTenantPermission.has_permission()`** (`apps/api/apps/common/permissions.py:60`) checks only that the actor *holds the permission code*. It never checks that the resolved tenant is the actor's own. Their `administrator` role in tenant A satisfies a code check performed while scoped to tenant B.

A contributing factor sits in `apps/api/apps/accounts/backends.py:70`: when the
tenant resolves to `None` (which is what a suspended tenant produces, since
`_active_tenants()` excludes it), `_candidates()` falls back to a **global**
email lookup — `return list(base[:2])` — so the suspended merchant's staff can
still authenticate with no header at all.

**Fix**

```python
# apps/api/apps/tenants/resolver.py — after
if user is not None and getattr(user, "is_authenticated", False):
    if getattr(user, "is_platform_admin", False):
        header_value = django_request.META.get(TENANT_HEADER_KEY, "")
        selected = tenant_by_identifier(header_value) if header_value else None
        return selected or getattr(user, "tenant", None) or _sole_tenant()

    # A non-platform user is pinned to their own tenant, full stop. A tenant
    # that is not operational is a *refusal*, never a fall-through: falling
    # through hands the choice to a client header, which is the one thing this
    # function exists to prevent.
    tenant = getattr(user, "tenant", None)
    if tenant is not None:
        return tenant if tenant.is_operational else None

return resolve_tenant_from_request(django_request)
```

Returning `None` makes `TenantScopedMixin` raise `TenantResolutionError`, so a
suspended merchant's staff get a clean refusal rather than someone else's shop.

**Trade-off:** a user with `tenant = None` who is *not* a platform admin still
falls through to the header. That case is currently only reachable for
platform-level staff mid-setup, but it should be tightened at the same time — a
non-platform user with no tenant has no business resolving one from a header.

Pair it with the login check in [HIGH-1], so the credential stops working at the
door as well as at the queryset.

**Effort:** minutes for the change; the test is the real work — see the
recommendation on a two-tenant matrix below.

---

### [HIGH-1] A suspended merchant's staff can still authenticate

**Where:** `apps/api/apps/accounts/serializers.py:263`

**What it is**

`TokenObtainPairSerializer.validate()` rejects an inactive *user*:

```python
if not user.is_active:
    ...
    raise InvalidCredentialsError()
```

It never asks whether the user's **tenant** is still operational. A merchant
suspended for non-payment, fraud, or contract termination keeps every staff
credential live and keeps issuing 15-minute access tokens and 14-day refresh
tokens.

**How it is exploited**

1. Merchant is suspended.
2. Staff user authenticates as normal and receives a refresh token valid for 14 days.
3. Independently of [CRITICAL-1], they retain API access to whatever the platform still serves them.

Chained with [CRITICAL-1] this is the entry step of the cross-tenant compromise;
on its own it is still wrong — suspension that does not revoke access is not
suspension.

**Evidence**

```
A status: SUSPENDED | operational: False
=== can the user still authenticate? ===
  eyJhbGciOiJIUzI1NiIs... (len 408)
```

**Why nothing stops it**

Nothing else in the login path consults the tenant. `is_locked_out` handles
brute force; `user.is_active` handles individual deactivation. Tenant
suspension has no enforcement point at authentication.

**Fix**

```python
# after `if not user.is_active:` in TokenObtainPairSerializer.validate
# A suspended merchant's staff must lose access at the door, not merely be
# scoped oddly once inside.
user_tenant = getattr(user, "tenant", None)
if user_tenant is not None and not user_tenant.is_operational:
    record_login_attempt(
        email=email, tenant=tenant, successful=False,
        ip=ip, user_agent=user_agent, failure_reason="tenant_suspended",
    )
    raise InvalidCredentialsError()
```

**Trade-off:** existing refresh tokens stay valid until they expire. If
suspension needs to take effect immediately, also blacklist the tenant's
outstanding refresh tokens — `revoke_all_refresh_tokens` already exists per
user in `apps/api/apps/accounts/services.py`.

**Effort:** minutes.

---

### [MEDIUM-1] Tenant isolation is tested, but never on the branch that fails

**Where:** `apps/api/apps/tenants/tests/test_isolation.py:60`

**What it is**

The project has a dedicated isolation test file, and it contains exactly the
right test:

```
def test_header_cannot_move_an_authenticated_user
```

It passes. It has always passed. It only ever runs against an **operational**
tenant, which is the branch where the guard works — so it proves the guard
exists without proving it covers anything.

Across the whole suite, 22 of 532 test functions take the `other_tenant`
fixture, about 4%. For a shared-schema multi-tenant product where a single
missed filter is a breach of every customer at once, that is thin.

**Why this is a finding rather than an observation**

[CRITICAL-1] was reachable for as long as the resolver has had that shape, and
the suite grew to 551 tests without noticing. The absence is what allowed the
Critical to exist.

**Fix**

Add the negative case directly:

```python
def test_a_suspended_tenants_user_cannot_use_the_header(
    self, staff_client: Any, tenant: Any, other_tenant: Any, ...
) -> None:
    """Suspension must revoke reach, not merely scope it oddly."""
    Tenant.objects.filter(pk=tenant.pk).update(status=TenantStatus.SUSPENDED)

    response = staff_client.get(
        "/api/v1/admin/products/", HTTP_X_TENANT=other_tenant.slug
    )

    assert response.status_code in {401, 403}
```

And parametrise it over every non-operational state (`SUSPENDED`,
`is_active=False`) rather than just one.

**Effort:** an hour for the case above; see the recommendations for the broader
matrix.

---

### [MEDIUM-2] Database, cache and object storage are published on all interfaces in development

**Where:** `docker-compose.yml:18, 31, 48-49, 80-81`

**What it is**

The development compose publishes backing services to `0.0.0.0`:

```
postgres   0.0.0.0:5432->5432/tcp
redis      0.0.0.0:6379->6379/tcp
minio      0.0.0.0:9000-9001->9000-9001/tcp
mailpit    0.0.0.0:1025->1025/tcp, 0.0.0.0:8025->8025/tcp
```

The credentials are the documented defaults from `.env.example`
(`murasfood:murasfood`), and Redis has no password at all. Anyone on the same
network as a developer's laptop — an office LAN, a café, a conference — reaches
the full database read-write, the cache, and the object store.

**Scope, honestly:** this is a **development-only** exposure.
`docker-compose.prod.yml` publishes only `80` and `443` through a Caddy proxy
and does not expose the data services at all. The deployed product is not
affected.

**Fix**

```yaml
# docker-compose.yml — bind to the loopback interface only
ports:
  - "127.0.0.1:5432:5432"
  - "127.0.0.1:6379:6379"
```

Everything that needs these reaches them over the compose network by service
name; the published port exists only for a developer's own tooling, which lives
on the same host.

**Effort:** minutes.

---

### [MEDIUM-3] No Content-Security-Policy or Permissions-Policy

**Where:** `apps/api/config/settings/production.py:22-30`, and no CSP anywhere in `apps/web/nuxt.config.ts`

**What it is**

Production sets HSTS, `nosniff`, `X-Frame-Options: DENY`, a referrer policy and
secure cookies — a careful list. It has no `Content-Security-Policy` and no
`Permissions-Policy`. Confirmed live against the running API:

```
  MISSING  content-security-policy
  present  x-content-type-options: nosniff
  present  x-frame-options: DENY
  present  referrer-policy: same-origin
  MISSING  permissions-policy
```

**Why it matters here specifically**

This platform renders merchant-authored content to shoppers — FAQ answers,
parallax band titles and CTA URLs, product descriptions, image captions. I found
no working XSS sink today (see *Checked and clean*), but CSP is the control that
limits the damage of the one that gets introduced later, and the access tokens
sit in `localStorage` where a script can read them ([LOW-1]).

**Fix**

Start in report-only mode so a policy can be tuned without breaking the
storefront:

```python
# production.py
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = ("'self'",)          # no unsafe-inline, no unsafe-eval
CSP_IMG_SRC = ("'self'", "data:", env("S3_PUBLIC_ENDPOINT", default=""))
CSP_CONNECT_SRC = ("'self'", *CORS_ALLOWED_ORIGINS)
CSP_FRAME_ANCESTORS = ("'none'",)
CSP_REPORT_ONLY = True                 # flip to False once the reports are clean
```

**Trade-off:** the JSON-LD block on the product page is an inline `<script>`; a
strict `script-src 'self'` needs a nonce or a hash for it. That is the work — the
header itself is a one-liner.

**Effort:** hours, mostly spent watching report-only violations.

---

### [LOW-1] Access and refresh tokens live in `localStorage`

**Where:** `apps/web/app/utils/storage.ts:19-21`

**What it is**

```ts
export const StorageKeys = {
  accessToken: 'murasfood.access_token',
  refreshToken: 'murasfood.refresh_token',
```

Tokens in `localStorage` are readable by any script running on the origin. An
httpOnly cookie is not. The refresh token is valid for 14 days.

**Why this is Low and not High**

I looked for an XSS sink and did not find a working one: no `v-html` anywhere in
the application, Vue escapes interpolation by default, the email renderer
escapes by default, and the one `innerHTML` use is escaped by the framework
(verified — see *Checked and clean*). Without an XSS, this is not exploitable.
It is a defence-in-depth gap, and it is why [MEDIUM-3] is worth doing.

**Fix**

Moving to httpOnly cookies means adopting CSRF protection on every mutating
request and reworking the refresh flow — real work, and a legitimate thing to
schedule rather than rush. The cheaper mitigation is CSP plus a shorter refresh
lifetime; `JWT_REFRESH_TOKEN_LIFETIME_DAYS` is already an environment variable.

**Effort:** needs design.

---

### [LOW-2] Passwords hashed with PBKDF2 rather than Argon2

**Where:** `apps/api/config/settings/base.py:247-250`

```python
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]
```

Django's default at its current iteration count is not broken, and this is not a
vulnerability. Argon2id is memory-hard and materially better against GPU
cracking of a stolen hash dump.

**Fix:** add `argon2-cffi` and put `Argon2PasswordHasher` first in the list;
Django rehashes each password transparently on next login, so no migration or
forced reset is needed.

**Effort:** minutes, plus one dependency.

---

### [LOW-3] Dependency CVEs, none reachable from the application

Detailed in the table below. Every finding is in build or development tooling;
no runtime dependency of either application is vulnerable.

---

### [LOW-4] GitHub Actions pinned to mutable tags

**Where:** `.github/workflows/ci.yml:57, 59, 85, 101, 103, 137, 139, 142, 152`

`actions/checkout@v4`, `docker/build-push-action@v6` and six others resolve a
moving tag. If one of those repositories is compromised, the next CI run
executes the attacker's code with whatever secrets the workflow holds.

**Fix:** pin to a commit SHA — `actions/checkout@8f4b7f8...  # v4.2.2`.
Dependabot updates SHA pins as readily as tags.

**Effort:** minutes.

---

## Checked and clean

This is what makes the findings above credible: these were examined and found
sound, not merely unexamined.

| Area | Result |
|---|---|
| **SQL injection** | No `.raw()`, `.extra()`, `RawSQL` or string-built SQL anywhere outside one `cursor.execute("SELECT 1")` liveness probe. Everything goes through the ORM. |
| **Mass-assignment filtering** | No `filter(**request.GET)` pattern; no dynamic `order_by` from user input. Sorting goes through a whitelist (`PRODUCT_SORT_OPTIONS`) with a comment explaining that an arbitrary field would let a caller sort by `cost_price`. |
| **Serializer exposure** | No `fields = "__all__"` and no `exclude =` in any application serializer. Every one is an explicit allow-list. Customer and admin product serializers are deliberately separate so cost and margin cannot leak. |
| **Payment webhook** | Unauthenticated by necessity, but HMAC-SHA256 verified before the body is parsed, compared with `hmac.compare_digest` (constant time) — `apps/api/apps/payments/providers/sandbox.py:144`. Replays are no-ops via event id. |
| **Object-level ownership** | Customer-facing querysets filter by `customer=request.user` *and* tenant — orders, addresses, shopping lists, favourites, notifications. `PaymentDetailView` additionally checks `payment.order.customer_id != request.user.pk`. |
| **Secrets in the repository** | None. `.env` has never been committed and is covered by `.gitignore` (`.env`, `.env.*`, `!.env.example`). All 7 scanner hits verified as false positives — see below. |
| **Secrets in git history** | The fallback history scan over 800 commits surfaced only `.env.example` and the deliberate fixtures in `test_diagnostics.py`. |
| **XSS via JSON-LD** | `apps/web/app/pages/products/[slug].vue:197` puts a merchant-authored product name into `innerHTML` via `JSON.stringify`, which does not escape `<` or `/`. **Tested with a live breakout payload** — unhead serialises it as `</script>`, so the tag never terminates. Not exploitable. |
| **XSS sinks generally** | No `v-html`, no `dangerouslySetInnerHTML`, no direct `innerHTML` assignment outside the JSON-LD case above. |
| **Email template injection** | `render_template` does literal `{{ }}` substitution with `html.escape` by default and no expression evaluation — merchant-editable templates cannot reach into objects or execute code. |
| **Tenant header for anonymous traffic** | An anonymous visitor choosing `X-Tenant` is the intended storefront routing and exposes only public catalogue data. Not a finding. |
| **CORS** | Explicit origin allow-list, no wildcard, does not reflect an arbitrary `Origin` — confirmed live. |
| **Auth rate limiting** | `login` 10/min, `register` 10/hour, `password_reset` 5/hour, `email_verification` 10/hour, plus account lockout after 10 failures for 900s. The restock-alert endpoint I reviewed carries its own 20/hour scope. |
| **Account enumeration** | The login backend hashes a dummy password on the miss path to equalise response time — `backends.py:26`. |
| **Production transport** | SSL redirect, HSTS 1 year with `includeSubDomains` and `preload`, nosniff, `X-Frame-Options: DENY`, referrer policy, secure + httpOnly + SameSite session cookies. Fails fast on a missing `DJANGO_SECRET_KEY`. |
| **Production port exposure** | `docker-compose.prod.yml` publishes only 80/443 via Caddy; no data service is reachable from outside. |
| **Diagnostics endpoint** | Gated on a non-hierarchical `system.diagnostics` capability specifically so `perm.admin` does not grant it; redacts anything credential-shaped (`_safe_error`), asserts the secret key, DB password and S3 secret are absent from the payload, and sets `Cache-Control: no-store`. 20 tests. |
| **Stock and money races** | `select_for_update` inside `transaction.atomic` on every stock write; reservations expire on a TTL; ledger entries carry a unique constraint per reference so projection is idempotent. |

### The seven "secrets" the scanner flagged — all false positives

| Location | What it actually is |
|---|---|
| `.env:15` | The real local file — **never committed**, gitignored, absent from history |
| `.env.example:15` | Placeholder `murasfood:murasfood@postgres` in a documented example |
| `.github/workflows/ci.yml:52` | Ephemeral CI service container, plus `DJANGO_SECRET_KEY: ci-secret-key-not-used-in-production` |
| `apps/api/apps/common/tests/test_diagnostics.py:76` | `postgres://user:hunter2@db:5432/app` — a deliberate fixture proving redaction works |
| `apps/api/apps/common/tests/test_diagnostics.py:90` | `AKIAIOSFODNN7EXAMPLE` — AWS's own published example key, same purpose |
| `apps/api/config/settings/base.py:124` | Local dev default for `DATABASE_URL`, overridden by environment |
| `apps/web/app/utils/storage.ts:20` | A `localStorage` **key name**, not a token |

---

## Dependencies

| Package | Version | Advisory | Reachable? | Severity here |
|---|---|---|---|---|
| `pip` | 25.0.1 | PYSEC-2026-1795/1796/196/2875/2876/3721 (6 distinct) | **No** — build-time installer, not in the request path | Low |
| `svgo` and 10 others | dev tree | incl. 1 "critical" by npm's rating | **No** — `npm audit --omit=dev` reports **0 vulnerabilities** | Low |

Both applications' runtime dependencies are clean. Django, DRF, Celery, boto3,
Pillow and the Nuxt/Vue production tree have no known advisories at these
versions. The npm "critical" is in build tooling that never ships to a browser,
and saying so is what should make the Critical above believable.

---

## Not verified

| Item | Why | What would settle it |
|---|---|---|
| Production security headers and TLS | No deployed host exists | Run `scripts/headers_probe.py` against it once deployed |
| Caddy proxy configuration | Reviewed as code only | Probe the running proxy |
| MinIO bucket policy | Checked from the application side (public ACL on derivatives, signed URLs for private) but not from the storage side | `mc anonymous get` against the bucket |
| Database role privileges | The app connects as `murasfood`; whether that role is a superuser was not checked | `SELECT rolsuper FROM pg_roles WHERE rolname = current_user;` |
| Backup encryption and restore | No backup system exists yet (phase 9) | Revisit when it does |
| Real payment provider | Only the sandbox provider is implemented | Re-audit the webhook when a real PSP is wired |
| Non-platform user with `tenant = None` | The code path exists but I could not construct the state through any endpoint | Try to create such a user via the admin API |

---

## Recommendations beyond the findings

Structural changes that prevent classes of problem rather than instances.

**1. Make the permission check tenant-aware.** `HasTenantPermission` today asks
"does this actor hold the code?" It should also ask "is the resolved tenant this
actor's own?" That single addition would have blocked [CRITICAL-1] even with the
resolver bug present — defence in depth against exactly the mistake that was
made:

```python
# apps/api/apps/common/permissions.py
if not getattr(user, "is_platform_admin", False):
    resolved = getattr(request, "tenant_id", None)
    if resolved is not None and user.tenant_id != resolved:
        return False
```

**2. A two-tenant matrix, not a two-tenant fixture.** The `other_tenant` fixture
exists and 22 tests use it. What is missing is a *systematic* assertion: for
every tenant-scoped viewset, a test that an actor from tenant A gets 403/404 on
tenant B's rows. Written once as a parametrised test over the router's
registered viewsets, it would cover the surface as it grows rather than as
someone remembers.

**3. Every non-operational tenant state needs a named consequence.** Suspension
currently means "excluded from `_active_tenants()`", and everything else is
emergent — which is how both [CRITICAL-1] and [HIGH-1] arose. Decide explicitly:
can staff log in? can the storefront be browsed? do webhooks still process? Then
test each answer.

**4. Pre-commit secret scanning.** The repository is clean today. `gitleaks` in a
pre-commit hook keeps it that way for a cost of seconds per commit, and is far
cheaper than the rotation that follows a single mistake.

**5. Install `semgrep` and `gitleaks` in CI.** The bundled scanners found little
here partly because the codebase is disciplined and partly because they are
pattern-based fallbacks. `semgrep --config=p/django` would add real coverage to
the existing CI pipeline.

---

## Method note

Findings were verified by exploitation, not by reading. The cross-tenant flaw
was reproduced against two throwaway tenants (`audit-a`, `audit-b`) created for
the audit, and the JSON-LD XSS candidate was tested with a live breakout payload
and **dropped** when the framework turned out to escape it. All fixtures created
during the audit were removed; the `demo` tenant and its 51 products were
verified intact afterwards.
