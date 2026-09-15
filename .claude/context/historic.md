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

### M10 - Fixing a CSS bug from a plausible cause instead of a measured one

**The symptom.** Collapsed, the admin rail's icons sat left of centre with dead
space on their right.

**The first explanation, and why it was wrong.** The nav list overflowed a
720px-tall window, a 15px scrollbar appeared, and the scrollbar's width came out
of the content box. Icons centred within 56px instead of 72px: exactly 8px off.
The numbers agreed and the story was complete.

Then the same page was measured at 900px tall, where nothing overflows:

```
contentScrollbarPx: 0      overflows: false
drawerCentreX: 36          iconCentreX: 28          offBy: 8
```

Same 8px, no scrollbar. The theory had matched the arithmetic and still been
wrong.

**The real cause.** Vuetify sizes a list item's first grid track as
`icon + --v-list-prepend-gap` - 24px + 16px. That gap separates an icon from a
title, and in a rail there is no title, so it became 16px of dead space on the
right of every icon. Half of 16 is the 8.

**And it took three attempts to fix**, each one measured:

| Attempt | Result |
|---|---|
| Zero the gap, `justify-content: center` | icons 35.5 OK - but `scrollbar-gutter: stable both-edges` ate 20px of a 72px rail and pushed the bottom button 5px off |
| Hide the rail's scrollbar instead | button 0.5 OK, icons back to **8 off** - with the gap gone, the title track claimed the 15px it freed |
| Pin the tracks: `grid-template-columns: 24px 0 0` | icons, avatar and button all **0.5 off** OK |

**The lesson.** Arithmetic that matches is not a diagnosis. The scrollbar theory
predicted the exact observed offset and was still the wrong mechanism - because
8 is half of 16 for more than one reason. A cause is confirmed by varying the
thing it depends on, not by the size of the number it explains. Changing the
viewport height took thirty seconds and would have saved the first two fixes.

---

### M11 - A silent catch hid a URL that had never once worked

`useAdminPulse` fetches a stock count for the header badge. Its `catch` was
empty on purpose: a badge that cannot load must not put an error toast on every
screen in the dashboard.

The path was `/inventory/health/`. Every inventory route in this project is
mounted under `admin/`. It had been 404ing on every admin page since the moment
it was written, and the badge simply rendered nothing - which is also what it
renders when there is nothing to report.

Found only by reading the network log while checking something else.

**The fix is not to remove the catch** - the reasoning for it still holds. It is
that *silent* and *invisible* are different things:

```ts
catch (error) {
  if (import.meta.dev) console.warn('[admin-pulse] stock health unavailable', error)
}
```

**The lesson.** Every swallowed error is a place a feature can be completely
dead and look merely quiet. This is P1 wearing a different coat: the code was
reachable, the endpoint was not, and nothing in lint, typecheck or the test
suite compares a string in a composable against the URL conf. When you write a
catch that does nothing, make it say so where a developer will see it.

---

### M12 - Writing a test that asserted my assumption rather than the contract

Two of the tests written this round failed against correct code:

- **The DRE comparison window.** The test asserted April 1-30 as the comparison
  for May. The implementation returns March 31 - April 30 - *equal length*,
  which is what its docstring promises and what stops February reading as a
  collapse every year. The test had encoded "previous calendar month", which is
  a different rule I had not thought about carefully.
- **The diagnostics secret check.** It asserted the string `SECRET_KEY` never
  appears in the payload. But the warning *"SECRET_KEY is shorter than 50
  characters"* is exactly what an operator needs to read. Naming a setting is
  not leaking it.

Both were rewritten to assert the property rather than a literal: same length
and ending the day before, across three parametrised ranges; and that the key's
*value* - not its name, and not even its first eight characters - is absent.

**The lesson.** When a new test fails, the code is not automatically wrong. Both
of these would have been "fixed" into worse behaviour by someone in a hurry: the
first into a comparison that lies every February, the second into a diagnostics
page that cannot tell you which setting is misconfigured.

---

### M13 - Calling a change done without measuring the thing it was supposed to produce

The seam between the two header rows was `v-divider(absolute)` inside the
toolbar extension. It was written, it looked plausible, and the commit message
said the two rows now read as two bands.

It had never rendered:

```
seam: { top: 89.5, width: 0 }   position: static
```

A zero-width stub sitting 25px *down* the tools row, dividing nothing. `absolute`
is not a `VDivider` prop that does what the name suggests in that context, and
the element was a flex child of a row it was never meant to participate in.

**What made it invisible.** A 1px line against a 1px border is not something the
eye flags as missing, and the screenshot I took after the change was at 0.3
scale. The user saw it immediately on a real screen.

**The lesson, which is the same one as M1 and M9 in a new costume.** Every other
claim in that commit carried a number. This one carried a description. When a
change's whole purpose is to put a specific thing at a specific place, the
check is `getBoundingClientRect()`, not a glance — and the cost of asking is
about fifteen seconds.

The fix was also the simpler thing I should have reached for first: a
`border-top` on the extension is the row's own edge, so it spans the bar by
construction and cannot be knocked out of place by the layout inside it.

---

### M14 - Removing the duplicate instead of the duplication

The admin footer showed a breadcrumb trail. `MuraPageHeader` already renders
that trail at the top of every page. The diagnosis was right: the bar was 40px
of every viewport spent saying something twice.

The remedy was wrong. I deleted the footer.

A dashboard still needs somewhere to say which shop and which environment you
are operating on - an operator with staging and production open in two tabs has
no other way to tell them apart, and that confusion is how test data ends up in
a real catalogue. Removing the whole element to remove the repetition threw that
away, and the user noticed within a day: *"in admin space there is no footer ????
where the footer go ?"*

**The lesson.** When something is redundant, the redundancy is the defect - not
the container. The question to ask is "what should be here instead", and only
"should anything be here at all" once that has no answer. The footer came back
carrying the store, the environment, a live status dot and links; it is in the
content flow rather than pinned, which also answers the *original* complaint
that it felt "static and weird".

---

### M15 - Two designs that lost a merchant's data quietly, both mine

Within the same phase, twice:

**The gallery filtered instead of refusing.** `_sync_gallery` dropped any asset
id it did not recognise and rebuilt the rows from what was left. One bad id -
a stale client, a copy-paste, another shop's asset - and a product's photos were
gone, with a 200 and no message.

**The threshold echoed a stale value.** `get_or_create_item` returns a different
Python object from the one `product.inventory` already holds, so the response
serialised the *pre-save* values: the API said 5.000 while the database said
12.000. A merchant sets a threshold, sees the old number come back, and sets it
again.

Both were found by driving the real endpoint and reading the response, not by
reading the code - and both had passed review in my own head as obviously fine.

**The lesson.** "Ignore what you cannot handle" is a reasonable default for a
*read* and a data-loss bug for a *write*. A write that cannot do what was asked
must say so; a write that succeeded must report what it stored, not what it was
holding. Both now have a test that asserts the failure mode directly - the
gallery survives a refused id, and the PATCH echoes the value that was saved.

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

### H9 - "The black flash on table pages is the skeleton rendering unstyled"

**The claim.** Navigating to `/admin/customers` showed a dark block where the
data belongs. Vuetify's `v-skeleton-loader` ships its CSS in its own chunk, so
the obvious story was that the chunk lands late and the skeleton paints naked.

**What the measurement showed.** A `MutationObserver` on the content region
(`requestAnimationFrame` is paused while the browser pane is hidden, so rAF
sampling returned zero frames and was useless here):

```
t=114  route is /admin/inventory/expiry   no skeleton, no table
t=245  skeleton appears
t=274  skeleton gone, rows rendered
```

The skeleton was only on screen for **29 ms**. The gap that actually reads as a
fault is the **130 ms before it**, where the route has changed and the table
component has not mounted at all - its chunk is still loading. The unstyled
skeleton was a real hazard but a minor part of what the user was seeing.

**What was done anyway.** `MuraTableSkeleton` is plain HTML with scoped CSS in
one file, so there is no second chunk and no frame where it can render naked;
the card holds a 420px minimum through the first load so the page cannot jump
between the three states. Measured after: skeleton present at 461px for the
whole load, then rows.

**What remains, honestly.** The ~130 ms chunk-load gap is a dev-server artifact -
in a production build the component is in the route's bundle. It has not been
measured against a production build, and that is the open question here.

---

### H10 - "The products table is ragged because some products have no image"

The reported symptom was product names starting at different horizontal
positions, and the guess - the user's, and mine on reading it - was that rows
without a photo laid out differently from rows with one, or that photos of
different aspect ratios pushed the text around by different amounts.

Measuring five rows killed it:

```
thumb 146x0  name at 471
thumb 133x0  name at 458
thumb 134x0  name at 459
thumb 130x0  name at 455
thumb 117x0  name at 442
```

Every row *had* an image. Every thumbnail was **zero pixels tall**. And no two
were the same width.

**The actual cause.** `MuraImage` was given `width="40" height="40"` in a Pug
template, which passes *strings*. Its `unit()` helper appended `px` only to
numbers, so `width: 40` and `height: 40` were invalid CSS, silently dropped by
the browser - leaving the frame at its base `width: 100%` with no height at all.
The widths that came out were whatever the flex row happened to allocate after
the name beside it.

So it was a units bug wearing a layout bug's clothes, and no amount of adjusting
flex properties would have fixed it.

**What the measurement was worth.** Two numbers - `0` height and five different
widths - pointed straight at "these dimensions are not being applied" rather
than "these dimensions are being applied badly". The hypothesis about missing
images would have led to a wrapper that papered over it while every other caller
of `MuraImage` passing a string kept the same silent bug.

---

### H11 - "The parallax needs more overscan"

The blank strip above and below the parallax bands looked like a case of the
image not being tall enough, and the obvious fix was to raise the 12% overhang
until it stopped happening.

It would not have stopped happening. The two numbers involved were never in a
relationship at all:

* travel was `scrollOffset x 0.4` - a fraction of the **scroll distance**;
* overscan was 12% - a fraction of the **element height**.

A band is on screen across roughly `viewport + height` of scrolling, so at
860/602 the image travelled `0.4 x (860 + 602) / 2 = 303px` inside 72px of
slack. Raising the overscan to cover that would need ~50% on a 602px band at
that viewport - and a different number at every other viewport, since one side
of the mismatch scales with the window and the other does not.

**The real fix was to make them one number.** Travel is now a share of the
*measured* slack, so `|shift| <= slack` holds by construction: the image's edge
can at most exactly meet the band's, at any viewport, any band height, any
overscan. The overscan became the only knob, and raising it now strengthens the
effect rather than papering over a leak.

**Why this is worth recording.** "Increase the constant until the symptom stops"
would have worked on the developer's monitor and failed on a phone. Two magic
numbers that must agree and have no stated relationship are a bug waiting for a
different screen size - and the fix is usually to derive one from the other, not
to tune both.

---

### M8 — Concluding the app does not scroll the window, from a scroll that was blocked

**What happened.** The band parallax did not move. `window.scrollY` read 0 after
`window.scrollBy(0, 300)` and after setting `document.documentElement.scrollTop`
directly, so I concluded the app scrolls an inner container and that a `window`
scroll listener could never fire. The band was rewritten around a frame loop on
that basis, with a comment saying so.

**What was actually true.** *Scripted* scrolling is blocked in this browser
automation. A real scroll event moved the page immediately — `scrollTop: 500`,
`window.scrollY: 500` — and the hero's plain `window` scroll listener had been
working the whole time, translating its image 200 px and its title 70 px.

**Outcome.** The frame loop was kept, because it is the right mechanism for an
element in the middle of a page: its position changes for reasons a scroll event
does not report, such as an image above it finishing loading. But the *comment*
was wrong and was corrected — a true fix resting on a false explanation will
mislead whoever reads it next.

**Rule adopted.** When a browser probe returns a surprising zero, first test
whether the probe itself worked.

---

### M9 — A healthcheck that killed the thing it was checking

**What happened.** The dev server began answering every route with
`Worker terminated due to reaching memory limit: JS heap out of memory`. The
user hit it in the browser; nothing rendered at all.

**Cause — mine.** The healthcheck added in phase 4 warmed five routes *and every
asset they reference* (~350 modules through Vite's dev transform pipeline), and
Docker ran it on `interval: 15s` **forever**. Measured: the Nitro worker grew
about 150 MB per minute and reached Node's 2 GB ceiling in roughly four
minutes.

Warming is a **startup** job. A health probe runs for the life of the process
and has to be cheap enough to do so. Conflating the two meant the thing meant to
prove the server was healthy was steadily making it less so.

**Second mistake inside the fix.** Making it warm "once per container" used a
marker file in `/tmp`. But `docker compose restart` keeps the filesystem and
replaces the process, so the marker would skip the warm-up at exactly the moment
it was needed — every restart during development. The marker now counts only if
it was written after the current process booted, which `/_health` reports.

**Third:** even the cheap path hit `/`, which is a full SSR render — about 30 MB
per probe. It now hits `/_health`, a Nitro route that renders nothing.

**Measured, before and after**

| | growth |
|---|---|
| before | ~150 MB/min → dead in ~4 min |
| warm-once, probing `/` | ~64 MB/min |
| warm-once, probing `/_health` | **612 → 614 MB over 3 min** |

The dev heap limit was also raised from 2 GB to 4 GB — a project this size
legitimately needs the headroom, and the failure mode is opaque when it runs
out.

**Rule adopted.** Anything that runs on a timer forever must be measured over
time, not just observed to work once. "It passes" and "it is safe to repeat
every fifteen seconds until the heat death of the universe" are different
claims.

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
| `checksum` on `MediaAsset` | computed and indexed since day one, read by nothing |
| `Cache-Control` on uploads | never set, so every derivative was re-fetched on every visit |
| `inventory.restocked` template | added to `DEFAULT_TEMPLATES`; templates are seeded per tenant *at creation*, so it existed for nobody |
| `useAdminPulse` | called `/inventory/health/`; every inventory route is under `admin/` (M11) |
| `table-columns.test.ts` | could not be *collected* in the container - `docs/` was not mounted - so the one guard on column drift had silently stopped running |
| `product_count` on `/admin/categories/` | serializer declared it, queryset never annotated it - every category read 0 |
| the header seam | rendered at `width: 0` and divided nothing (M13) |
| `MuraImage` width/height as strings | invalid CSS, silently dropped - thumbnails 0px tall (H10) |

Two of these are a distinct sub-species worth naming: **seed-time
initialisation**. `sync_permissions` and `seed_default_templates` run when a
tenant is *created*. Anything added to their source lists afterwards reaches new
tenants only, and a feature that works on a fresh database and 403s or silently
does nothing on an existing one is among the most expensive bugs to diagnose.
Both now have a deploy-time command - `sync_roles`, `sync_email_templates` -
and both were written because the feature they belonged to was found dead in
exactly this way.

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

---

### P4 - A number on screen must be driven by something

Three times now a figure has been displayed that nothing computed:

| Figure | What it actually showed |
|---|---|
| `product_count` on the categories screen | always 0 - the admin queryset never annotated it, and the serializer declared a default of `0` |
| `low_stock` on the stock screens | one shared tenant-wide threshold, so it was either noisy or silent for every product |
| the stock badge in the header | nothing - the endpoint 404'd (M11) |

Each rendered plausibly. A zero is a number; a quiet badge looks like good news.

**The rule adopted.** When adding a figure to a screen, follow it back to the
query that produces it and forward to the decision it should change. If either
end is missing, the figure is decoration - and decoration that looks like data
is worse than a blank space, because someone will act on it.

`low_stock` now has a test asserting that changing the threshold changes what
`is_low_stock` reports at the same quantity. That is the shape of guard this
pattern needs: not "the field saves" but "the field does something".

---

## Part IV — Decisions deliberately left open

| Item | Position |
|---|---|
| `deactivate_price` | Unreachable, but `set_price` updates one row in place and reactivates it, so this is dead code rather than a missing feature. Deleting a documented, audit-correct service helper is the user's call. Not deleted. |
| mypy's ~219 errors | Pre-existing baseline (lazy translation strings passed to exceptions, nullable tenants). Not enforced in CI. Do not add to it; do not undertake the cleanup without asking. |
| Destroying uploaded originals | Deliberate: 90% of storage was never read. Reversible per-deployment via `MEDIA_IMAGE_MAX_DIMENSION=0`. A shop needing print masters should set it. |
| Import auto-creating categories | Off by default. Silently creating them is how a typo becomes a second category; the switch exists for onboarding from a fresh sheet. |
