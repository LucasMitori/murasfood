# API

Base path: `/api/v1/`. The schema in [`openapi.yaml`](openapi.yaml) is generated
from the code, so it cannot drift from the implementation. Regenerate it with:

```bash
make openapi
```

Interactive documentation runs alongside the API at `/api/docs/` (Swagger) and
`/api/redoc/`.

## Conventions

**Tenant.** Every request is scoped to one merchant. Anonymous callers may send
`X-Tenant: <slug>`; an authenticated non-platform user is always pinned to their
own tenant, and the header is ignored for them.

**Money.** Amounts are **strings** (`"12.90"`), never JSON numbers. Parse them
with a decimal-safe helper; JavaScript numbers cannot represent them exactly.

**Errors.** One envelope, always:

```json
{
  "error": {
    "code": "INSUFFICIENT_STOCK",
    "message": "There is not enough stock for one or more items.",
    "details": { "product_name": "Arroz", "available": "2.000" },
    "request_id": "1f2e3d…"
  }
}
```

Branch on `code` — it is stable. `message` is localised for display. `request_id`
matches the `X-Request-ID` response header and the server logs.

**Pagination.** `{ count, page, pages, page_size, next, previous, results }`.
Append-only feeds (audit log, order history) use cursor pagination instead.

**Idempotency.** Send `Idempotency-Key` on checkout, payment creation and
refunds. Replaying the key with the same payload returns the original response;
replaying it with a *different* payload is rejected with
`IDEMPOTENCY_KEY_REUSED`.

**Cart token.** Anonymous carts are addressed by an opaque token returned in the
`X-Cart-Token` response header. Send it back on later requests, and pass it to
`POST /cart/merge/` after signing in.

## Endpoint map

| Area | Endpoints |
| ---- | --------- |
| Auth | `POST /auth/register/` · `login/` · `refresh/` · `logout/` · `verify-email/` · `resend-verification/` · `password-reset/` · `password-reset/confirm/` |
| Tenant | `GET /tenants/current/` · `GET|PATCH /tenants/admin/` · `admin/branding/` · `admin/settings/` · `admin/business-hours/` |
| Catalog (public) | `GET /catalog/home/` · `products/` · `products/{slug}/` · `products/{slug}/related/` · `categories/` · `brands/` · `search/suggestions/` · `barcode/{code}/` |
| Cart | `GET|DELETE /cart/` · `summary/` · `POST /cart/items/` · `PATCH|DELETE /cart/items/{id}/` · `coupon/` · `merge/` |
| Delivery | `GET /delivery/config/` · `POST /delivery/options/` · `GET|PATCH /delivery/settings/` · `zones/` |
| Checkout & orders | `POST /orders/checkout/` · `GET /orders/` · `GET /orders/{number}/` · `POST /orders/{number}/cancel/` · `GET /orders/{number}/receipt/` |
| Payments | `POST /payments/` · `GET /payments/{id}/` · `POST /payments/webhooks/` (provider) |
| Customer | `GET|PATCH|DELETE /customers/me/` · `change-password/` · `data-export/` · `me/addresses/` · `me/favorites/` |
| Promotions | `GET /promotions/active/` · `POST /promotions/coupons/validate/` |
| Media | `POST /media/upload/` · `GET /media/assets/` · `documents/` · `banners/` · `banners/live/` |
| Admin — catalog | `/admin/products/` · `categories/` · `brands/` · `tags/` · `units/` |
| Admin — operations | `/admin/orders/` · `/admin/inventory/` · `/admin/prices/` · `/admin/promotions/` |
| Admin — insight | `/admin/dashboard/` · `/admin/reports/*` · `/admin/finance/*` · `/admin/audit-logs/` |

## Notes that save debugging time

- `POST /customers/me/favorites/` **toggles**: `201` when added, `204` when
  removed. One endpoint for one heart button.
- Checkout accepts no monetary fields. Sending `total` changes nothing — the
  server recomputes it, and a test asserts exactly that.
- The payment webhook returns `200` for duplicates and unknown references so a
  provider stops retrying events that are already handled or never will be.
- Public product responses expose only `in_stock` and `low_stock`, never exact
  quantities, and never cost or margin.
