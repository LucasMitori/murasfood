# actual_step.md — one phase at a time

> **Exactly one phase lives here.** What is confirmed, and the measurement that
> confirms it. When the phase closes, its findings move to `historic.md` and
> this file is rewritten for the next one.
>
> **Rule: nothing enters "Confirmed" without an observation.** Not "the code
> looks right" — a number, a status code, a screenshot, a failing test that
> passes after the change.

**Last updated:** 2026-09-13

---

## PHASE 5 — Storefront experience

### Goal

Make the shop *feel* like a product a market owner would pay for: a home page
with depth and rhythm, filters that survive a real catalogue, and motion that
reads as considered rather than decorative.

### Scope

| # | Item | State |
|---|---|---|
| 5.1 | Parallax home — alternating bands and content, titles parallaxed, admin-toggleable | ✅ done |
| 5.2 | `/products` filters — richer, with a search input | ◀ next |
| 5.3 | Categories as clickable cards under the title, rendering below dynamically | not started |
| 5.4 | Animations — gentle, modern, professional | not started |
| 5.5 | Sale/discount card and dedicated product page treatment | not started |

### Out of scope

Security hardening (phase 6 — the `maruth.security` skill is written and will
drive it), production readiness (phase 7), `/admin/customers` CRUD.

---

## Confirmed — with evidence

Everything below was observed, not inferred.

### From phase 4, carried in as the baseline

| Claim | Evidence |
|---|---|
| Dev server no longer 404s its stylesheets | First-load failed requests **50 → 0**, measured in the browser on a cold container |
| Cold start signals readiness honestly | Healthy at **34 s**; before, the container reported "Up" immediately while unusable |
| Client-side navigation works without a hard reload | `/` → `/products` → `/cart` → `/` by clicking; 0 failed resources |
| Image storage cut | Realistic photo **505,333 → 98,258 B**; existing library masters **9,357,525 → 4,275,570 B** across 89 images |
| AVIF actually served | `..._small.avif` in `currentSrc`, natural width 244, 8/8 visible frames at opacity 1 |
| Spreadsheet round trip is lossless | Real 51-product catalogue exported and re-imported: **51 updated, 0 created, 0 errors** |
| Import is all-or-nothing | Broke one row of the real export → category unchanged, no category invented, 51 products intact |
| CSV reports are really CSV | Queued job → `vendas-2026-08-05-2026-09-03.csv` with real rows |
| Private downloads reachable | Report downloaded from the host: `200`, correct content |
| Order emails reach both parties | Two `EmailLog` rows, both **SENT**, distinct idempotency keys, correct per-audience links |

### From 5.1, confirmed on the running storefront

| Claim | Evidence |
|---|---|
| The page has the requested rhythm | `HERO (720px) → Categorias → BAND (504px) → Ofertas → Destaques → BAND (504px) → Mais vendidos → Novidades`, read from the live DOM |
| 70vh and 100vh are real | 504 px is 70% of the 720 px viewport |
| Band layers move at different rates | media `translate3d(0, 194.5px, 0)` vs text `77.8px` — the 0.4/0.16 ratio exactly |
| The hero moves its title too | media `200px`, content `70px` at 500 px of scroll — 0.4/0.14 |
| No hydration mismatch | zero console errors on first paint with bands and hero parallax on |
| The API resolves band images server-side | `image=yes` on both bands in `/catalog/home/`, no extra round trip |
| A scripted link is refused | `javascript:`, `data:`, `vbscript:` all 400 |
| Bands are optional | a layout with no bands validates and renders a short page |

19 new backend tests cover the band shape, the hero settings, and that the
public serializer carries `hero` — the allow-list that has now been forgotten
twice.

### Suite state

```
458 API tests · 242 web tests
ruff check · ruff format · eslint · vue-tsc — all clean
OpenAPI schema regenerated and deterministic
```

---

## Not confirmed — explicitly

Recording these matters as much as the confirmations.

| Item | Why not | How it would be confirmed |
|---|---|---|
| Admin screens render correctly | The browser session available has no merchant login; token injection is blocked | A merchant logs in and looks |
| — `/admin/reports` three tabs | endpoints verified directly, page compiles and typechecks | " |
| — `/admin/storefront` Layout + Appearance tabs | backend proven end to end | " |
| — cost-of-goods tile on `/admin/finance` | `cogs` present in payload and in all three locales | " |
| — export menu in the table toolbar | all four endpoints return 200 with correct content type | " |
| The band editor in `/admin/storefront` | no merchant session in the browser available to me | a merchant opens the Layout tab and adds a band |
| Real-world import at scale | tested at 51 rows | a merchant's own 400-row sheet |

---

## Working notes for 5.1

**The shape requested**

```
100vh v-parallax  (image + title, both parallaxed)
  ↓
categories + offers
  ↓
70vh v-parallax   (admin-authored content)
  ↓
same-day delivery card + featured
  ↓
70vh v-parallax   (admin-authored)
  ↓
best sellers
  ↓
…alternating
```

**Constraints already known**

1. **SSR** — `v-parallax` measures the viewport, which the server cannot. Gate on hydration, the same way the header does. A hydration mismatch here would be visible on every first paint.
2. **The layout is already configurable** — `home_layout` on `TenantSettings` handles order, title, limit and enabled per band. Parallax bands should extend that structure rather than invent a second one.
3. **Bands need an image each** — that means a media asset per band, chosen in `/admin/storefront`, which the Layout tab can already host.
4. **A shop must be able to turn them all off** and keep a short page. The switch is the feature, not an afterthought.
5. **Motion must respect `prefers-reduced-motion`.** A parallax that ignores it is an accessibility failure, not a style choice.

**Open question for the merchant screen**

Does a parallax band belong in `home_layout` as another section kind, or as its
own list interleaved by position? Leaning to the former: one ordered list is
easier to reason about and reuses the drag-to-reorder UI that exists.

---

## Definition of done for phase 5

- [x] Parallax bands render without hydration mismatch, verified in the browser
- [x] Bands are configurable and switchable off from `/admin/storefront` *(built; the screen itself is unverified — see above)*
- [x] `prefers-reduced-motion` honoured throughout
- [ ] `/products` filters usable against a 400-product catalogue
- [ ] Categories render as cards and filter in place
- [ ] Sale treatment visible on card and product page
- [ ] Both suites green, all linters clean, schema regenerated
- [ ] Every claim in this file carries a measurement
