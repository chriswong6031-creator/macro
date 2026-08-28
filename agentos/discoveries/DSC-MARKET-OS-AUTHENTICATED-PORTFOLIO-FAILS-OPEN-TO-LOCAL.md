---
key: MARKET-OS-AUTHENTICATED-PORTFOLIO-FAILS-OPEN-TO-LOCAL
claim: >
  After an authenticated Macro Portfolio cloud read fails, the current adapter returns
  the anonymous local Portfolio and marks later Portfolio operations as local, creating
  a silent second authority rather than an explicit degraded cloud state.
falsifier: >
  Read templates/watchstore.js::portfolioList and _isLocalMode and show that an
  authenticated cloud error preserves cloud authority, never returns pfLocalList, and
  never routes a subsequent write through pfLocalUpsert.
so_what: >
  A1A must keep cloud Portfolio authority for authenticated users, preserve last-good
  cloud rows or show unavailability, and fail read-only until recovery instead of
  silently substituting or mutating the local anonymous store.
kind: architecture
verified_at: 2026-08-20
verified_by: "GitHub connector read of templates/watchstore.js::portfolioList, _isLocalMode, portfolioUpsert, and the one-shot local-to-cloud fold"
scope:
  - macro
  - terminal-user-services
  - "templates/watchstore.js"
  - "templates/portfolio.js"
confidence: verified
---

## Current transition

```text
authenticated cloud Portfolio read
        ↓ error
portfolioOk = false
        ↓
return pfLocalList()
        ↓
_isLocalMode() == true
        ↓
future upsert/remove/close use localStorage
```

The save-state surface does not clearly distinguish that authority switch. The one-shot
fold is not a general offline outbox and does not make this safe.

## Frozen authority

```text
anonymous     -> local Portfolio is canonical
authenticated -> cloud Portfolio is canonical
```

For an authenticated cloud failure, the minimum honest state is:

- last-good cloud rows, marked degraded and read-only; or
- explicit Portfolio unavailable when no last-good snapshot exists.

A durable authenticated offline outbox is a later capability. A local fallback is not
allowed to impersonate one.