# actual_step.md — one phase at a time

> **Exactly one phase lives here.** What is confirmed, and the measurement that
> confirms it. When the phase closes, its findings move to `historic.md` and
> this file is rewritten for the next one.
>
> **Rule: nothing enters "Confirmed" without an observation.** Not "the code
> looks right" — a number, a status code, a screenshot, a failing test that
> passes after the change.

**Last updated:** 2026-09-15

---

## PHASE 7 — Merchant authoring and chrome

### Goal

Give the shopkeeper control of the things that were hard-coded, and stop the
dashboard's own furniture from looking broken. Two threads: content a merchant
can write for themselves (FAQs, categories, product galleries, stock rules), and
the chrome around it (the header seam, the footer, the parallax, the tables).

### Scope

| # | Item | State |
|---|---|---|
| 7.1 | Header seam between the two bar rows | ✅ done |
| 7.2 | Admin footer — restored, not a duplicate | ✅ done |
| 7.3 | Email template row actions side by side | ✅ done |
| 7.4 | Diagnostics page — readable rather than a data dump | ✅ done |
| 7.5 | Parallax blank strip | ✅ done |
| 7.6 | FAQs editable, with draft/published | ✅ done |
| 7.7 | Categories screen (products, brands, tags, finance) | ✅ done |
| 7.8 | Products table alignment | ✅ done |
| 7.9 | Per-product stock thresholds | ✅ done |
| 7.10 | Product image gallery — order and captions | ✅ done |

### Out of scope

Animations and sale-card treatment (carried from phase 5, still open), the
security audit (phase 8 — the `maruth.security` skill has still never been run),
production readiness (phase 9).

---

## Confirmed — with evidence

Everything below was observed, not inferred.

### 7.1 — The seam

| Claim | Evidence |
|---|---|
| The divider was doing nothing at all | `{ top: 89.5, width: 0 }`, `position: static` — a 1px stub 25px down the tools row |
| It now separates the two rows | `border-top: 1px solid` on the extension, **1153px** wide, at the row boundary |
| The old element is gone | `.mura-admin-bar__seam` absent from the DOM |

Why a `v-divider absolute` failed there: **M13** in `historic.md`.

### 7.2 — The footer

| Claim | Evidence |
|---|---|
| It exists again | `.mura-admin-foot` present on every admin screen |
| It is in the flow, not pinned | `position: static`, width 1153, below the content |
| It says something the page does not | store, environment, live stock status, links |
| The status cannot contradict the header | both read `useAdminPulse`; footer showed "7 itens precisam de atenção" while the header badge showed the same count |

### 7.3 — Email actions

| Claim | Evidence |
|---|---|
| Before: stacked | both buttons at `left: 535`, tops **488 / 528** — one above the other |
| After: side by side | same `top: 370`, lefts **948 / 980** |
| The row stopped being double height | **81px → 44px** |

### 7.4 — Diagnostics

| Claim | Evidence |
|---|---|
| Problems are separated from the rest | groups render as `Precisa de atenção (1)` and `Todas as verificações (8)` |
| Latency is comparable at a glance | log scale: 0.3 ms → 11%, 2.9 ms → 33%, **2.1 s → 96% and amber** |
| Sub-millisecond reads as fast, not broken | `0.3 ms`, not the `0 ms` that rounding produced |
| Machine keys read as words | `pending_migrations` → "Migrações pendentes"; 8 meta labels translated |
| The shop snapshot renders | `0 Pedidos hoje · 51 Produtos · 2 Sem estoque` |

### 7.5 — Parallax

| Claim | Evidence |
|---|---|
| The old travel exceeded the picture | `0.4 × (860 + 602) / 2 ≈ 303px` of travel against `0.12 × 602 ≈ 72px` of slack |
| Travel is now bounded by the slack | measured on the live page: slack **108.4px**, max shift **108.4px**, overscan 18% |
| It cannot expose an edge at any size | 8 tests over 5 viewports × 6 heights × 5 overscans × every position |
| The guard guards | one test encodes the *old* formula and asserts it breaches |

Scripted scrolling is blocked in this environment (M8), so this is proven by
construction and by test rather than by watching it scroll. Stated plainly.

### 7.6 — FAQs

| Claim | Evidence |
|---|---|
| A draft never reaches a visitor | `GET /tenants/faq/` → `[]` while the entry exists |
| Publishing makes it live | same endpoint returns the question; `published_at` stamped |
| Unpublishing keeps the copy | entry hidden, `answer` unchanged |
| An empty section is not rendered | a heading with only drafts under it is absent |
| One shop cannot file under another's section | cross-tenant `category` → **400** |
| The public page needs no account | **200** anonymous |

14 tests in `apps/tenants/tests/test_faq.py`.

### 7.7 — Categories

| Claim | Evidence |
|---|---|
| The tree renders | Padaria/Hortifruti/Açougue with their children, from the live page |
| Counts were always zero | the admin queryset never annotated `product_count`; the serializer defaulted it to 0 |
| Counts are now real and complete | all 8 roots sum to **51 of 51** products |
| A root includes its children | matches `ProductFilter.filter_category`, which is what a tap on it shows |

### 7.8 — Products table

| Claim | Evidence |
|---|---|
| Before: every row a different width | thumbs **0px tall**, widths 146/133/134/130/117; names at 471/458/459/455/442 |
| The cause was units, not layout | `width="40"` is a *string*; `unit()` only appended `px` to numbers |
| After: one left edge | every thumb **40×40**, every name at **365**, every row **49px** |

### 7.9 — Stock thresholds

| Claim | Evidence |
|---|---|
| They save | `reorder_threshold` 12.000, `minimum_stock` 5.000 on the item |
| The response echoes the new values | was `5.000` while the database said `12.000` — a stale relation cache |
| They drive the flag | threshold 3 → `is_low_stock False`; threshold 15 → `True`, at the same quantity |
| Setting one does not move stock | movement count and quantity both unchanged |

### 7.10 — Gallery

| Claim | Evidence |
|---|---|
| Order and captions persist | two images stored as `["Rótulo", "Porção servida"]` in that order |
| The first is primary | `is_primary True`, `position 0` |
| An unknown id is refused | **400**, and the existing gallery still has its image |
| A foreign shop's asset is refused | **400** |
| Not mentioning it leaves it alone | a `name`-only PATCH keeps the images |

13 tests in `apps/catalog/tests/test_product_stock_gallery.py`.

### Suite state

```
551 API tests (was 524)  ·  250 web tests (was 242)
ruff check · ruff format · eslint · vue-tsc — all clean
OpenAPI regenerated with --fail-on-warn, 0 warnings
locale parity: 1111 keys × 3 locales, 0 missing
```

---

## Not confirmed — explicitly

Recording these matters as much as the confirmations.

| Item | Why not | How it would be confirmed |
|---|---|---|
| **The parallax looks right while scrolling** | Scripted scroll is blocked here; the geometry is proven by construction and by test, not by eye | Scroll the home page and watch the bands |
| **The table flash is fully fixed** | The skeleton is verified; the ~130 ms before it (component chunk loading) is unaddressed and is a dev-server artifact | Measure the same navigation against a production build |
| The gallery's drag-to-reorder | The component renders with its item and caption; the drag itself was not performed | Drag a photo in the product dialog |
| The FAQ drag-to-reorder | The endpoint is tested; the drag was not performed | Reorder two questions on `/admin/faq` |
| Behaviour at 10,000 products | Measured at 51 products / 84 assets | A merchant's real catalogue |
| `hide_out_of_stock` | Backend and both serializers covered; still no switch in `/admin/storefront` | Add the control, then flip it |
| Price elasticity as a *predictor* | It is the merchant's assumption, echoed back. Not validatable from this data | Nothing — this is a property of the model, stated on screen |

---

## Working notes

**The QA account.** `qa.claude@murasfood.local` (ADMINISTRATOR, `demo` tenant)
exists in the dev database so admin screens can be driven. Every admin claim
above was measured through it. **Delete it before any deployment.**

**Three deploy-time commands now exist and must all run:**

```bash
python manage.py sync_roles             # new permission codes reach existing tenants
python manage.py sync_email_templates   # new templates reach existing tenants
python manage.py migrate                # includes the back_soon layout backfill
```

**A new-rail checklist**, learned the hard way this phase: adding a section to
`HOME_SECTION_KEYS` needs a **data migration** for existing tenants, or their
stored layout fails validation on the next save.

---

## Definition of done for phase 7

- [x] Every chrome fix measured before and after, not eyeballed
- [x] The parallax bound proven by construction and by an adversarial test
- [x] FAQ draft/published proven invisible then visible
- [x] Category counts reconciled against the real product total
- [x] Table alignment measured to a single pixel column
- [x] Stock thresholds proven to change what the stock screens report
- [x] Both silent-data-loss paths found and closed
- [x] Both suites green, all linters clean, schema regenerated
- [ ] A merchant drags a photo, a question, and scrolls the home page
