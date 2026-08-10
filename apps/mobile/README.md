# MurasFood Mobile

React Native (Expo) client for the MurasFood platform.

> **Status: scaffold.** The directory layout, API contract and screen map below
> are defined and agreed; the screens themselves are not implemented. Nothing in
> this folder is wired to a build yet, and `apps/mobile` is deliberately absent
> from CI. Treat this as the Phase 9 starting point, not a shippable app.

## Why React Native

ADR-009 records the decision. In short: the storefront's audience is
overwhelmingly on mid-range Android devices, the team's existing strength is
TypeScript, and the mobile app consumes the **same** `/api/v1` contract as the
web app — no business logic is duplicated across platforms (spec §34).

## Planned structure

```
apps/mobile/
  app/                    # expo-router file-based routes
    (tabs)/
      index.tsx           # home
      search.tsx
      cart.tsx
      account.tsx
    product/[slug].tsx
    checkout/
      index.tsx
      payment.tsx         # PIX QR + copia e cola
    orders/
      index.tsx
      [number].tsx
    auth/
      login.tsx
      register.tsx
      verify-email.tsx
  src/
    api/                  # thin wrapper over the shared client
    components/
    hooks/
    stores/               # same store shapes as the web app
    i18n/                 # pt-BR, en, es — same message keys as apps/web
    theme/                # mirrors apps/web/app/utils/theme.ts
  assets/
  app.json
  package.json
```

## What is already reusable

The web app's non-visual layer was written to be portable and should move here
mostly unchanged:

| From `apps/web`                | Reuse                                      |
| ------------------------------ | ------------------------------------------ |
| `app/utils/api-client.ts`      | Framework-agnostic; takes a `fetch` impl.   |
| `app/utils/money.ts`           | Integer-cent arithmetic, no DOM dependency. |
| `app/types/api.ts`             | The API contract types.                     |
| `i18n/locales/*.json`          | Identical message keys.                     |
| `app/utils/theme.ts`           | Colour tokens for a React Native theme.     |

Extracting these into `packages/` is the first task of Phase 9 so both clients
import one copy rather than drifting.

## Screens (spec §34)

Splash · Onboarding · Login · Register · Email verification · Home · Search ·
Categories · Product · Favourites · Cart · Checkout · PIX payment · Orders ·
Order detail · Profile · Addresses · Settings · Notifications

## Platform notes

- **Storage.** Access and refresh tokens belong in `expo-secure-store`, not
  `AsyncStorage` — the latter is plain text on a rooted device.
- **Push notifications.** Architect the token registration and the
  `Notification` model integration from the start even if the first release only
  sends order updates (spec §34).
- **PIX.** The QR image and the copy-and-paste payload both come from the API.
  The app renders them; it never generates a BR Code itself, so there is exactly
  one implementation of that format to keep correct.
- **Store submission.** Do not submit until the merchant's own privacy policy,
  terms and account-deletion flow are configured (spec §60). Account deletion
  must be reachable in-app — both stores reject apps where it is not.

## Getting started (once implemented)

```bash
npx create-expo-app@latest . --template blank-typescript
```

Then point `EXPO_PUBLIC_API_URL` at the API and reuse the modules listed above.
