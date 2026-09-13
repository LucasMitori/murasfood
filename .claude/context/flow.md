# flow.md — how it works, drawn

> Diagrams over prose. Mermaid renders on GitHub and in most editors.
> Update when a flow changes shape, not when a field is added.

**Last updated:** 2026-09-13

---

## 1. System, today

```mermaid
graph TB
    subgraph Browser
        SF[Storefront<br/>Nuxt SSR + hydration]
        AD[Dashboard<br/>client-only]
    end

    subgraph Edge
        NX[Nitro server<br/>renders, proxies nothing]
    end

    subgraph API["Django + DRF"]
        V[ViewSets<br/>tenant-scoped]
        S[Services<br/>all business rules]
        SEL[Selectors<br/>read models]
    end

    subgraph Async["Celery"]
        W[worker]
        B[beat<br/>11 schedules]
    end

    subgraph Stores
        PG[(PostgreSQL<br/>shared schema + tenant_id)]
        RD[(Redis<br/>broker + cache)]
        S3[(MinIO / S3<br/>media + documents)]
    end

    SF --> NX
    NX -.SSR fetch.-> V
    SF -.hydrated fetch.-> V
    AD --> V
    V --> S
    V --> SEL
    S --> PG
    SEL --> PG
    S -. on_commit .-> RD
    RD --> W
    B --> RD
    W --> PG
    W --> S3
    V --> S3
    W --> MAIL[SMTP / Mailpit]
```

**Rule:** views never contain business rules. A view validates, calls a service,
serialises. This is why a bug is almost always in `services.py`.

---

## 2. Checkout — the money path

```mermaid
sequenceDiagram
    autonumber
    actor C as Customer
    participant W as Storefront
    participant A as API
    participant DB as PostgreSQL
    participant Q as Celery

    C->>W: Finalizar compra
    W->>A: POST /orders/checkout/ (Idempotency-Key)

    rect rgb(245, 235, 235)
    note over A,DB: one transaction
    A->>DB: price from server, never the client
    A->>DB: reserve stock (TTL 30 min)
    A->>DB: create order → PENDING_PAYMENT
    A->>DB: queue order.created + staff alert
    end

    A->>DB: create PIX charge (separate transaction)
    A-->>W: 201 + order
    W->>C: redirect /account/orders/{number}/payment

    note over A,Q: on commit
    A-)Q: send_email × 2
    Q->>C: "Pedido recebido"

    C->>C: pays in bank app
    Note over A: provider webhook (signature verified)
    A->>DB: payment PAID → order PAID
    A->>DB: commit reservation → stock decremented
    A-)Q: order.payment_confirmed

    Note over Q: beat, every 5 min
    Q->>DB: expire_stale_payments → PAYMENT_FAILED
    Note over Q: beat, every 15 min
    Q->>DB: expire_unpaid_orders (backstop: no payment row)
```

> **Why the backstop exists.** `_checkout` is not atomic end to end: the order
> commits, then the charge is created. If the provider is down, the order exists
> with no payment row and nothing in the payments layer can ever resolve it.

---

## 3. Order state machine

```mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PENDING_PAYMENT: checkout
    PENDING_PAYMENT --> PAYMENT_PROCESSING
    PENDING_PAYMENT --> PAID
    PENDING_PAYMENT --> PAYMENT_FAILED: PIX window closes
    PENDING_PAYMENT --> CANCELLED: expire_unpaid_orders
    PAYMENT_PROCESSING --> PAID
    PAYMENT_PROCESSING --> PAYMENT_FAILED
    PAID --> CONFIRMED
    CONFIRMED --> PREPARING
    PREPARING --> READY_FOR_PICKUP
    PREPARING --> OUT_FOR_DELIVERY
    READY_FOR_PICKUP --> COMPLETED
    OUT_FOR_DELIVERY --> DELIVERED
    DELIVERED --> COMPLETED
    PAID --> REFUNDED
    CONFIRMED --> CANCELLED
    CANCELLED --> [*]
    COMPLETED --> [*]
    REFUNDED --> [*]

    note right of PENDING_PAYMENT
        Born here, not moved here.
        That is why order.created
        had no caller for so long.
    end note
```

---

## 4. Stock — a ledger, not a number

```mermaid
graph LR
    A[Add to cart] --> R[StockReservation<br/>HELD, expires_at]
    R -->|checkout| O[attached to order]
    O -->|paid| C[COMMITTED<br/>quantity decremented]
    O -->|cancelled| X[released]
    R -->|TTL passes| E[EXPIRED<br/>released, every 60 s]

    C --> M[(StockMovement<br/>append-only)]
    X --> M
    E --> M

    style M fill:#f5ede7
```

`available = quantity − reserved`. That is the number a shopkeeper acts on, and
the one the storefront shows as "Indisponível".

---

## 5. Media pipeline — before and after

```mermaid
graph TB
    subgraph Before["Before — 7.6 MB per photo"]
        U1[6.9 MB JPEG<br/>4000×3000] --> K1[kept as uploaded<br/>never rendered]
        U1 --> D1[4 × WebP<br/>753 KB total]
    end

    subgraph After["After — ~1.5 MB per photo"]
        U2[6.9 MB JPEG] --> M2[master<br/>2048px WebP]
        U2 --> W2[4 × WebP]
        U2 --> A2[4 × AVIF<br/>~35% smaller]
        M2 -.original deleted.-> G[ ]
    end

    style K1 fill:#f8d7d7
    style G fill:none,stroke:none
```

Render side:

```mermaid
graph LR
    P["&lt;picture&gt;"] --> S1["&lt;source type=avif&gt;<br/>srcset 160/320/640/1280w"]
    P --> S2["&lt;source type=webp&gt;<br/>same widths"]
    P --> I["&lt;img&gt; fallback<br/>lazy + async decode"]
    S1 -->|browser picks| B[one file, right size,<br/>right format]
    S2 --> B
    I --> B
```

---

## 6. Spreadsheet import — three gates

```mermaid
flowchart TD
    T[Download template] --> F[Merchant fills it in Excel]
    F --> U[Upload]
    U --> P[parse CSV or XLSX<br/>headers matched leniently]
    P --> V{validate every row}

    V -->|any error| R[report: line, SKU, reason<br/>NOTHING WRITTEN]
    R --> F

    V -->|all clean| DR{dry run?}
    DR -->|yes| PRE[preview counts only]
    PRE --> AP[merchant confirms]
    AP --> W
    DR -->|no| W[one transaction]

    W --> SKU{SKU known?}
    SKU -->|no| CR[create + price + stock]
    SKU -->|yes| UP[update + price + stock]

    style R fill:#f8d7d7
    style W fill:#e7f0e7
```

---

## 7. Home page — now vs next

**Now** — bands in the merchant's order, each toggleable:

```mermaid
graph TD
    H[hero carousel<br/>banners] --> L{home_layout}
    L --> C[categories]
    L --> O[on_sale]
    L --> F[featured]
    L --> B[best_sellers]
    L --> N[new_arrivals]
    L -.each has.-> P[enabled · title · limit · order]
```

**Next** — parallax bands between the content (phase 5):

```mermaid
graph TD
    A[100vh v-parallax<br/>image + parallaxed title] --> B[categories + offers]
    B --> C[70vh v-parallax<br/>admin-authored content]
    C --> D[same-day delivery card<br/>+ featured]
    D --> E[70vh v-parallax<br/>admin-authored]
    E --> F[best sellers]
    F --> G[…alternating]

    style A fill:#f0e6e6
    style C fill:#f0e6e6
    style E fill:#f0e6e6
```

Each parallax band becomes a configurable section: image, heading, body, CTA,
and an on/off switch in `/admin/storefront`. A shop that wants a short page
turns them all off and loses nothing.

---

## 8. Data model — the core

```mermaid
erDiagram
    TENANT ||--|| TENANT_SETTINGS : configures
    TENANT ||--|| TENANT_BRANDING : styles
    TENANT ||--o{ PRODUCT : owns
    TENANT ||--o{ ORDER : owns
    TENANT ||--o{ USER : scopes

    PRODUCT ||--|| INVENTORY_ITEM : "1:1 stock"
    PRODUCT ||--o{ PRODUCT_PRICE : "history"
    PRODUCT ||--o{ PRODUCT_IMAGE : shows
    PRODUCT }o--|| CATEGORY : "in"
    PRODUCT }o--o| BRAND : "by"
    PRODUCT }o--|| UNIT_OF_MEASURE : "sold by"

    PRODUCT_IMAGE }o--|| MEDIA_ASSET : references
    MEDIA_ASSET ||--o{ DERIVATIVE : "webp + avif"

    ORDER ||--o{ ORDER_ITEM : contains
    ORDER ||--o{ ORDER_TRANSITION : "audited"
    ORDER ||--o| PAYMENT : "settles"
    ORDER }o--o| USER : "placed by"

    INVENTORY_ITEM ||--o{ STOCK_MOVEMENT : "append-only"
    INVENTORY_ITEM ||--o{ STOCK_RESERVATION : holds
    INVENTORY_ITEM ||--o{ STOCK_BATCH : "expiry"

    ORDER ||--o{ FINANCIAL_TRANSACTION : "projected to"
```

`ORDER_ITEM` stores a **snapshot** — name, SKU, unit price, unit cost — so a
later price change cannot rewrite history.

---

## 9. Scheduled work

```mermaid
gantt
    title Celery beat — 11 entries
    dateFormat X
    axisFormat %s

    section Seconds
    release_expired_reservations (60s)   :0, 60
    section Minutes
    expire_stale_payments (5m)           :0, 300
    project_paid_orders_to_ledger (5m)   :0, 300
    reconcile_pending_payments (10m)     :0, 600
    retry_failed_emails (10m)            :0, 600
    expire_unpaid_orders (15m)           :0, 900
    section Hourly / daily
    purge_expired_tokens (1h)            :0, 3600
    cleanup_orphaned_assets (03:30)      :0, 3600
    cleanup_old_report_jobs (03:45)      :0, 3600
    cleanup_old_notifications (04:00)    :0, 3600
    notify_low_stock (07:00)             :0, 3600
```

Seven of these were added in phase 2. They existed as code and were never
scheduled — see `historic.md`.

---

## 10. Request lifecycle

```mermaid
flowchart LR
    R[Request] --> TEN[resolve tenant<br/>user · X-Tenant · subdomain]
    TEN --> AUTH[JWT or session]
    AUTH --> PERM[HasTenantPermission<br/>per action]
    PERM --> FILT[DjangoFilter · Ordering · Search]
    FILT --> V[view]
    V --> SVC[service]
    SVC --> AUD[audit log]
    SVC --> DB[(scoped query)]
    V --> SER[serializer]
    SER --> RESP[JSON envelope]

    style FILT fill:#f0e6d8
```

> `SearchFilter` sat outside that chain until phase 2, which is why `?search=`
> answered 200 and filtered nothing on seven tables.
