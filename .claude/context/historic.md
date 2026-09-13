# historic.md — hypotheses that died, and method errors

> **Append only. Nothing is ever removed from this file.**
>
> A wrong idea that was investigated and discarded is worth more than a right
> idea nobody wrote down — it stops the next session paying for the same
> detour. Method errors matter more than technical ones: a bad technique
> produces wrong answers indefinitely.

---

## Part I — Method errors

*Mistakes in how conclusions were reached. These are the expensive ones.*

### M1 — Reporting work as done because lint passed

**What happened.** Edits were made, `ruff` and `eslint` passed, and the work was
reported complete. The user replied: *"you are not doing your job right"* — they
were looking at the same page, unchanged.

**Cause.** Docker had hung; the WSL `docker-desktop` distro was Stopped, so Vite
never reloaded. The files on disk were correct and the running application was
untouched.

**Rule adopted.** *A change is not done until it has been observed working in
the running application.* Lint and typecheck prove syntax, never reachability.

This single rule is responsible for most of what phase 2 found.

---

### M2 — Concluding from a measurement taken on the wrong element

**What happened.** Claimed `rail-width` was being overridden by Vuetify and
wrote a workaround for it.

**Cause.** The click that produced the measurement had landed on the *hidden
mobile menu button*, not the rail toggle.

**Correction.** Re-measured: 272 → 72 px, exactly as configured. The workaround
was removed and the plain form restored.

**Rule adopted.** Before drawing a conclusion from a UI measurement, confirm
which element was actually measured.

---

### M3 — Chasing a bug that was a misread number

**What happened.** Spent several turns investigating "the add-to-cart button
does nothing".

**Cause.** `cart.itemCount` counts distinct **lines**, not units. The quantity
had gone 1 → 3 and the badge correctly stayed at 1.

**Rule adopted.** Before investigating, state precisely what the number means.

---

### M4 — Two false alarms caught before reporting

1. *"Protected routes don't redirect"* — `localStorage` was cleared without reloading, so Pinia still held the session.
2. *"`/api/v1/tenants/current/` 404s"* — the probe used a relative fetch from the wrong origin.

**Rule adopted.** Reproduce a suspected bug twice, by different means, before
reporting it.

---

### M5 — Browser coordinates are not CSS pixels

**What happened.** Repeated failed clicks on overlays and menus; several turns
lost concluding components were broken when they were not.

**Cause.** The screenshot coordinate frame (800×455) is scaled from the actual
viewport (1280×720). Element coordinates read from the DOM need × 0.625.

**Rule adopted.** For a DOM-derived position, scale to the screenshot frame — or
dispatch the event in JavaScript, which also tests the binding rather than the
automation's arithmetic.

---

### M6 — Warming a cache in parallel reproduces the race it was meant to avoid

**What happened.** The healthcheck warmed assets with `Promise.all` and reported
`312/352 warmed`, leaving the first visitor to hit the rest cold.

**Cause.** Vite answers 404 for a virtual module that is still compiling. A
fifty-way parallel burst loses its own races — exactly what a browser does.

**Rule adopted.** When warming a lazily-compiled resource, go sequentially.
Startup slowness in a container is free; a cold first visit is not.

---

### M7 — Shipping a "fix" without checking what it broke

**What happened.** Stripped the Vuetify stylesheet links from the SSR head,
reasoning that the styles also arrive via ESM imports (10 components sampled,
all present).

**Result.** The page rendered **completely unstyled**. The sampled rules had
come from those very links on warm loads. Reverted immediately.

**Rule adopted.** When removing something believed redundant, verify the system
*without* it before concluding it was redundant.

---

## Part II — Hypotheses that died

*Technical theories investigated and disproved. Each one is a road not to walk again.*

### H1 — "The `.sass` 404s are a cold-start race that warming will fix"

**Evidence for.** HTML served at ~2 s; stylesheets unavailable for ~21 s more.
Warming did turn 48 of 50 green.

**Why it died.** After a full warm and a healthy container, a fresh browser load
still produced **50 failures**. The head Nuxt emits is also broader than the
page — the storefront links `VSwitch` and `VTextField`, which it never renders,
so some entries cannot resolve until another page pulls that component in.

**What was true instead.** The per-component SASS compilation was the wrong
strategy for dev. Serving Vuetify's precompiled CSS removed the problem
entirely: **50 → 0**.

**Kept anyway.** The healthcheck — a dev server that reports ready before it is
usable is worth fixing on its own.

---

### H2 — "`features.inlineStyles` will stop the links racing"

**Why it died.** Set it; the count stayed at 50. The setting does not reach
`vite-plugin-vuetify`'s virtual modules. Reverted rather than left as config
that does nothing.

---

### H3 — "`expire_unpaid_orders` is redundant dead code"

**Evidence for.** `expire_stale_payments` runs every 5 min, expires the PIX
charge, and transitions the order to `PAYMENT_FAILED`. Every order in the
database had a payment row.

**Why it died.** `_checkout` is **not atomic end to end**. `create_order_from_cart`
commits, *then* `create_payment_for_order` runs. If the provider fails, the
order is committed with no payment row — and nothing in the payments layer can
resolve it. It sits in `PENDING_PAYMENT` forever.

**Outcome.** Genuine backstop. Scheduled at 60 min, deliberately outside the
30-minute PIX window so it never races the payments layer.

---

### H4 — "The storefront styles arrive via ESM, so the `<link>` tags are redundant"

Covered as M7. Sampling ten components and finding their rules present did not
distinguish *which* mechanism delivered them.

---

### H5 — "Only `VCarousel` and `VWindow` can never resolve"

**Why it died.** After a browser had loaded the page, both returned 200 — and
`VSwitch` did not. The set that fails is not fixed; it depends on which
components are currently in the client module graph.

**What was true instead.** Resolution follows the client's imports, and the SSR
head is broader than any one page.

---

### H6 — "The signed download URL just has the wrong host; rewrite it"

**Why it died.** SigV4 signs the `Host` header. Swapping the host after signing
invalidates the signature.

**What was true instead.** It must be *signed* for the host it will be requested
on — a second boto client bound to `S3_PUBLIC_ENDPOINT`.

---

### H7 — "The image pipeline is already fine"

**Evidence for.** WebP derivatives at four sizes, never upscaled, with `srcset`
on the frontend. Average stored asset: 6.8 KB.

**Why it died.** The 6.8 KB average was **seeded demo placeholders**. A real
4000×3000 phone photo cost **6,859,127 B** for an original that nothing renders
— 90% of the upload, write-only.

**Rule reinforced.** Measure the real case, not the fixture. Seed data flatters.

---

### H8 — "AVIF will cost too much encode time"

**Why it died.** Measured: 0.20 s vs 0.15 s at 1280px, for ~35% fewer bytes —
and it runs in a worker nobody waits on.

---

## Part III — The pattern

Recorded separately because it shaped how everything since has been
investigated.

### P1 — Unreachable code is this project's dominant defect

Roughly two thirds of phase 2's findings were not regressions. They were
features that had **never once run**:

| Feature | Why it never ran |
|---|---|
| Every dashboard row action | emit passed `(key, row)`; handlers destructured one object |
| `/admin/users` | two TS casts in a Pug template → `SyntaxError` on import |
| Checkout → payment redirect | route renamed, link not updated |
| Order confirmation emails | fires on transition; the order is *born* in that state |
| Staff new-order alerts | no caller at all, behind a setting defaulting to on |
| `?search=` on 7 of 8 tables | `SearchFilter` not in `DEFAULT_FILTER_BACKENDS` |
| 6 periodic jobs | never added to `CELERY_BEAT_SCHEDULE` |
| Branding endpoint | no UI, from the start |
| Reports subsystem | no UI at all |
| CSV report format | ignored by the renderer, then unsettable by any client |
| `MuraImage` | built, then not used by the storefront |
| `perm.admin.reports` | declared, never referenced |

**Why lint, typecheck and tests all missed them.** None can see a caller that
does not exist. A function with no callers is valid code. A setting nobody reads
is a valid setting.

**What works instead:**

1. **Contract tests that compare two sides.** Emit vs handler. Column vs schema. Template key vs locale file. Query param vs backend filter. Task vs schedule.
2. **Scanning for absence.** "Which public service functions have no references?" found `expire_unpaid_orders` and `deactivate_price` in one query.
3. **Driving the real thing.** The checkout flow end to end found what no unit test had.

**Every guard added was proven by reintroducing the original bug** and
confirming the test fails. A guard that has never failed has never been shown to
guard anything.

---

### P2 — A declared capability is not a working one

Repeatedly, a field, setting or choice existed and nothing honoured it:

- `ReportFormat.CSV` — a valid choice; `run_report_job` always rendered PDF
- `output_format` — on the model, in the serializer's model, never passed by the view
- `search_fields` — valid on any viewset, read only through a backend that was not installed
- `notify_on_new_order` — a real setting gating a function with no callers
- `S3_PUBLIC_ENDPOINT` — used for public assets only; private ones ignored it
- `color`, `date`, `time`, `datetime` — in the field-type union; colour rendered a plain text box

**Rule adopted.** When a feature is "configurable", follow the value from where
it is set to where it is *used*. If the trail stops, the feature does not exist.

---

### P3 — One model, two serializers, one allow-list forgotten

`TenantPublicSerializer.get_settings()` carries its own explicit allow-list.
Adding a field to the model and the admin serializer is **not enough** — this
was hit twice, with `floating_tools` and again with `home_layout`.

Both times the symptom was identical: the admin screen saves successfully and
then shows the default, because it reads the tenant through the *public*
serializer.

There is now a test for it.

---

## Part IV — Decisions deliberately left open

| Item | Position |
|---|---|
| `deactivate_price` | Unreachable, but `set_price` updates one row in place and reactivates it, so this is dead code rather than a missing feature. Deleting a documented, audit-correct service helper is the user's call. Not deleted. |
| mypy's ~219 errors | Pre-existing baseline (lazy translation strings passed to exceptions, nullable tenants). Not enforced in CI. Do not add to it; do not undertake the cleanup without asking. |
| Destroying uploaded originals | Deliberate: 90% of storage was never read. Reversible per-deployment via `MEDIA_IMAGE_MAX_DIMENSION=0`. A shop needing print masters should set it. |
| Import auto-creating categories | Off by default. Silently creating them is how a typo becomes a second category; the switch exists for onboarding from a fresh sheet. |
