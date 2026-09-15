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


---

## 11. Back-in-stock — turning a lost sale into a signal

The only view this platform has onto demand that produced **no order**. A sales
report cannot show it, because nothing was sold.

```mermaid
flowchart TD
    V["visitor finds an empty shelf"] --> B{"account?"}
    B -- no --> E["types an email"]
    B -- yes --> A["account address is used;<br/>any email in the body is ignored"]
    E --> S["POST /catalog/products/:slug/restock-alert/<br/>throttled 20/hour"]
    A --> S
    S --> R[("RestockAlert<br/>one row per person per product")]

    R -.->|"ranked by count"| D["/admin/inventory/restock-demand/<br/><b>what to reorder next</b>"]

    P["merchant receives stock"] --> ADJ["adjust_stock()"]
    ADJ --> T{"available was 0<br/>and is now > 0?"}
    T -- no --> X["nothing"]
    T -- yes --> Q["transaction.on_commit →<br/>notify_restocked.delay()"]
    Q --> C{"still in stock<br/>when the task runs?"}
    C -- no --> X2["skip — it sold again"]
    C -- yes --> TPL{"template seeded<br/>for this tenant?"}
    TPL -- no --> ERR["log loudly, stamp nobody"]
    TPL -- yes --> M["stamp notified_at, then queue the email<br/>(same transaction, so a crash cannot double-send)"]
    M --> R

    style T fill:#f0e6d8
    style TPL fill:#f0e6d8
    style D fill:#d8e8d8
```

Three guards, each for a failure that actually happened or would have:

- **the transition, not the increase** — receiving more of something already in
  stock is not news;
- **re-check availability in the task** — it is queued on commit and runs later;
  the two units that arrived may already be gone;
- **check the template exists before stamping anyone** —
  `queue_transactional_email` returns `None` both for "already queued" and "no
  such template", and the first run of this stamped a waiting shopper as
  notified and sent them nothing.

---

## 12. Finance — one ledger, four questions

`services.py` writes. `analysis.py` only reads. Nothing recomputes a figure the
other already produces, because two implementations of "revenue" eventually
disagree and the one on screen is never the one someone checked.

```mermaid
flowchart LR
    O["paid order"] --> PROJ["project_order_to_ledger()"]
    PAY["payment"] --> FEE["project_payment_fee()"]
    MAN["merchant types an expense"] --> REC["record_expense()"]

    PROJ --> L[("FinancialTransaction<br/>one ledger, soft-delete only")]
    FEE --> L
    REC --> L

    L --> DRE["income_statement()<br/><b>fact</b>"]
    L --> VAR["budget_variance()<br/><b>fact about a plan</b>"]
    L --> FC["forecast()<br/><i>extrapolation</i>"]
    L --> CF["cash_flow()<br/><b>fact</b>"]

    OI[("OrderItem<br/>units · price · cost")] --> SIM["price_simulation()<br/><i>assumption</i>"]

    B[("Budget + BudgetLine<br/>editable, unlike the ledger")] --> VAR

    style DRE fill:#d8e8d8
    style VAR fill:#d8e8d8
    style CF fill:#d8e8d8
    style FC fill:#f0e6d8
    style SIM fill:#f0e6d8
```

Green is arithmetic over recorded rows. Amber is a guess, and says so on screen:
the forecast carries its basis in months and a confidence band; the simulation
carries the elasticity it used.

**Why the simulation reads order lines and not the ledger.** The ledger has no
units in it, and a margin without units cannot be re-priced.

### The DRE, in the order it is read

```mermaid
flowchart TD
    GR["Receita bruta"] --> NR["= Receita líquida"]
    TX["(-) Impostos sobre vendas"] --> NR
    NR --> GP["= Lucro bruto"]
    CM["(-) CMV"] --> GP
    GP --> OR["= Resultado operacional"]
    OP["(-) Despesas operacionais"] --> OR
    DL["(-) Custos de entrega"] --> OR
    OR --> NET["= Resultado líquido"]
    PF["(-) Taxas de pagamento"] --> NET

    style NR fill:#e8e8f0
    style GP fill:#e8e8f0
    style OR fill:#e8e8f0
    style NET fill:#d8e8d8
```

> Tax on sales is a **deduction from revenue**, above the gross-profit line —
> not an operating cost beside rent. Putting it below would overstate gross
> margin on every statement.

Each line also carries **AV** (its share of net revenue) and **AH** (change
against the previous period *of the same length* — comparing 31 days against 28
makes February read as a collapse every year).

---

## 13. Images at ten thousand products

Before this phase the conversion was already right. What was missing was
everything that decides whether the shop is *fast*.

```mermaid
flowchart TD
    U["upload"] --> CK["sha-256"]
    CK --> DUP{"same bytes,<br/>same tenant, folder<br/>and visibility?"}
    DUP -- yes --> REUSE["reuse the row<br/><b>no storage, no re-encode</b>"]
    DUP -- no --> ST["store + queue on the <b>media</b> queue"]

    ST --> W["worker: -Q celery,media"]
    W --> MASTER["master capped at 2048px, WebP"]
    W --> DERIV["4 widths × WebP + AVIF"]
    W --> LQIP["24px blurred WebP → data URI on the row"]

    DERIV --> S3[("object storage<br/>Cache-Control:<br/>public, max-age=31536000, immutable")]
    MASTER --> S3

    LQIP --> JSON["arrives in the product card's JSON<br/>~120 bytes, no extra request"]
    S3 --> PIC["&lt;picture&gt; AVIF → WebP → src"]

    JSON --> PAINT["blurred shape immediately"]
    PIC --> PAINT2["real photo fades in over it"]

    style DUP fill:#f0e6d8
    style S3 fill:#d8e8d8
    style LQIP fill:#d8e8d8
```

| Fix | Why it matters at 10k products |
|---|---|
| `Cache-Control … immutable` | ~240,000 objects were being re-fetched on every return visit. Keys embed the asset UUID and a reprocess writes a *new* key, so `immutable` is honest |
| checksum dedupe | a supplier catalogue repeats one photo across a dozen flavours; each copy was stored and re-encoded eight times |
| `media` queue | 10,000 imports queued ahead of the order confirmation a customer is waiting for |
| LQIP | a grey rectangle reads as broken; a blurred shape reads as loading |

---

## 14. Diagnostics — reporting on a system that may be broken

```mermaid
flowchart TD
    REQ["GET /admin/system/diagnostics/"] --> CAP{"holds<br/>system.diagnostics?"}
    CAP -- no --> F["403"]
    CAP -- yes --> RUN["run_diagnostics()"]

    RUN --> P1["database + migrations"]
    RUN --> P2["cache round trip"]
    RUN --> P3["celery ping"]
    RUN --> P4["queue depth (broker directly)"]
    RUN --> P5["storage head_bucket"]
    RUN --> P6["email: 24h outcomes"]
    RUN --> P7["scheduler: overdue reservations"]
    RUN --> P8["configuration warnings"]

    P1 & P2 & P3 & P4 & P5 & P6 & P7 & P8 --> AGG["status = worst of all"]
    AGG --> SAFE["_safe_error(): a DSN carries a password,<br/>so anything credential-shaped<br/>is reduced to the exception type"]
    SAFE --> OUT["JSON, Cache-Control: no-store"]

    style CAP fill:#f0e6d8
    style SAFE fill:#d8e8d8
```

Three rules this page is built on:

1. **Never a secret.** Not even masked — a masked secret still discloses length
   and shape. `secret_key_set: true`, never the key.
2. **Never another tenant's data.** Infrastructure checks report *liveness only*;
   the counts are tenant-scoped.
3. **Never block.** Every probe has a timeout and every failure is caught. A
   diagnostics page that dies with its dependency removes the one screen that
   would have said so.

**Why a capability and not a page code.** Page codes here are hierarchical —
holding `perm.admin` grants everything under it. Expressing this as
`perm.admin.diagnostics` alone would hand queue depth, storage state and
configuration warnings to every staff member who can open the dashboard.
`system.diagnostics` is granted only where it is listed, and it is listed only
for administrators.

---

## 15. Where a new permission or template actually goes

The shape of a bug this project has now hit three times.

```mermaid
flowchart LR
    ADD["add a code to<br/>PERMISSION_CATALOGUE"] --> ROW["Permission row created<br/>by sync_permissions()"]
    ROW --> Q{"who is granted it?"}
    Q --> NEW["a tenant created <b>after</b> the deploy<br/>✅ has it"]
    Q --> OLD["a tenant created <b>before</b><br/>❌ does not"]
    OLD --> CMD["manage.py sync_roles"]
    CMD --> FIXED["✅ has it"]

    style OLD fill:#f0d8d8
    style CMD fill:#d8e8d8
```

Identical for `DEFAULT_TEMPLATES` → `sync_email_templates`. The failure mode is
the worst kind: it works on a fresh database and on every test run, and is dead
in the one place that matters.


---

## 16. Parallax — why the strip was blank, and why it cannot be again

The bug was not a missing pixel count. It was two numbers that had to agree and
never did: travel was a fraction of the **scroll distance**, overscan a fraction
of the **element height**.

```mermaid
flowchart TD
    subgraph BEFORE["before — two unrelated constants"]
        S1["scroll distance<br/>viewport + height ≈ 1462px"] --> T1["travel = 0.4 × distance/2<br/><b>≈ 303px</b>"]
        H1["element height<br/>602px"] --> O1["overscan = 12%<br/><b>≈ 72px</b>"]
        T1 --> X["303 &gt; 72<br/><b>231px of empty band</b>"]
        O1 --> X
    end

    subgraph AFTER["after — one number, derived"]
        M["measure the slack<br/>(mediaHeight − height) / 2"] --> P["progress ∈ −1..1<br/>clamped"]
        P --> T2["shift = progress × slack<br/><b>|shift| ≤ slack, always</b>"]
        M --> T2
        T2 --> OK["edge meets edge<br/>at the extremes"]
    end

    style X fill:#f0d8d8
    style OK fill:#d8e8d8
```

Raising the overscan would have papered over it at one viewport and failed at
the next — one side of the mismatch scales with the window and the other does
not. Deriving travel from the measured slack makes the failure *impossible*
rather than unlikely, and leaves the overscan as the only knob: raising it now
strengthens the effect and can never expose an edge.

Shared by the hero and the bands as `parallaxShift()`, and tested across 5
viewports × 6 heights × 5 overscans × every position. One test encodes the old
formula and asserts it breaches, so the guard cannot quietly stop guarding.

---

## 17. FAQs — draft, published, and what a visitor sees

```mermaid
flowchart LR
    W["merchant writes"] --> D[("FaqEntry<br/>status = DRAFT")]
    D -->|"POST …/publish/"| P[("status = PUBLISHED<br/>published_at stamped")]
    P -->|"POST …/unpublish/"| D

    D -.->|"never"| V["GET /tenants/faq/"]
    P --> V

    V --> Q{"any published<br/>entries at all?"}
    Q -- yes --> OWN["the shop's own answers"]
    Q -- no --> SHIP["the shipped copy<br/><i>(so a new shop's help page<br/>is never blank on day one)</i>"]

    style D fill:#f0e6d8
    style P fill:#d8e8d8
    style SHIP fill:#e8e8f0
```

Three decisions worth keeping:

- **Two states, not a visibility flag.** The useful thing is writing an answer
  over several sittings without it being live in between. An `is_active`
  boolean gives you that too, but names it so badly that people use it as
  "temporarily hidden" and lose track of which is which.
- **Unpublishing keeps the copy.** It is hiding, not deleting.
- **Merchant copy replaces the shipped copy wholesale.** Interleaving would put
  their delivery window beside ours on the same page, with no way to remove the
  one they disagree with.

---

## 18. Where a product's photos and stock rules live

Both are edited on the product form and neither is stored on `Product`.

```mermaid
flowchart TD
    F["product dialog"] --> G["gallery: ordered list<br/>of {id, caption}"]
    F --> S["thresholds:<br/>low · minimum · track"]

    G --> SER["ProductAdminSerializer"]
    S --> SER

    SER --> CHK{"every asset<br/>owned by this tenant?"}
    CHK -- no --> ERR["<b>400</b> — refuse.<br/>Filtering silently turned one bad id<br/>into &quot;all my photos vanished&quot;"]
    CHK -- yes --> ROWS[("ProductImage rows rebuilt<br/>position = index<br/>is_primary = index 0")]

    SER --> INV[("InventoryItem<br/>reorder_threshold · minimum_stock · track_stock")]
    INV --> CACHE["product.inventory = item<br/><i>or the response echoes pre-save values</i>"]

    INV --> FLAG["is_low_stock"]
    FLAG --> SCREENS["Estoque · Saúde do estoque"]

    style ERR fill:#f0d8d8
    style CACHE fill:#f0e6d8
    style SCREENS fill:#d8e8d8
```

**Why the rows are rebuilt rather than diffed.** Position and primacy are
properties of the *list*, not of any one row — dragging the third photo to the
front changes two rows, and reconciling that is more code than writing four rows
again.

**Why thresholds do not go through `adjust_stock`.** They are a rule *about* the
stock, not a change *to* it. Routing them through the ledger would write a
movement row saying nothing moved.

**Why `product.inventory = item` is not incidental.** `get_or_create_item`
returns a different Python object from the one the product's relation cache
holds, so without it the API answered `5.000` while the database held `12.000`.

---

## 19. Counting a category's products

```mermaid
flowchart LR
    C["category row"] --> OWN["own_products<br/>Count(products, active)"]
    C --> KIDS["child_products<br/>Count(children__products, active)"]
    OWN --> SUM["product_count = own + children"]
    KIDS --> SUM

    SUM --> UI["&quot;10 produtos&quot;"]
    FILT["ProductFilter.filter_category<br/><i>includes descendants</i>"] -.->|"must agree"| SUM

    style SUM fill:#d8e8d8
```

The count includes descendants because **tapping the category in the shop shows
them**. A root reading "0 produtos" while a tap on it lists forty is a number
that teaches people to distrust the screen.

It read 0 for everything before this: the serializer declared `product_count`
with a default of `0` and the admin queryset never annotated it. Verified by
reconciliation — all 8 roots now sum to exactly the 51 products that exist.

---

## 20. The admin chrome, as it now stands

```mermaid
flowchart TD
    subgraph BAR["v-app-bar"]
        R1["row 1 · 64px — identity, store, language, theme, account"]
        SEAM["border-top on the extension<br/><i>a v-divider here rendered at width: 0</i>"]
        R2["row 2 · 52px — search ⌘K · quick create · alerts · storefront · fullscreen"]
    end

    RAIL["rail · 72px<br/>grid-template-columns: 24px 0 0<br/>--v-list-prepend-gap: 0"]

    MAIN["v-main → page content"]
    FOOT["footer, in the flow<br/>store · environment · live status · links"]

    BAR --> MAIN
    RAIL --> MAIN
    MAIN --> FOOT

    PULSE[("useAdminPulse")] --> R2
    PULSE --> FOOT

    style SEAM fill:#f0e6d8
    style PULSE fill:#e8e8f0
```

The footer reads the same `useAdminPulse` the header badge does, so the two
cannot disagree about whether anything needs attention — and it sits in the
content flow rather than pinned, so it never covers a table's last row.
