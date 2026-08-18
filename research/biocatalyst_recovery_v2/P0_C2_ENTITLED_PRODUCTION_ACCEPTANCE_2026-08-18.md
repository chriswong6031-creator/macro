# P0-C2 entitled production acceptance — BioCatalyst hydration

**Date:** 2026-08-18  
**Probe window:** 12:38:16Z–12:50:30Z (original 524 matrix); 13:15:47Z–13:15:53Z (Sol causal discriminator)  
**Scope:** evidence only. Production BioCatalyst entitled journey through the actual browser and the actual public API. No application-code change. No collector, roster, soak, freshness, Capital Structure, Market Memory, Prophet, UI, `withAuth()`, or contract work. No JWT minting, printing, reconstruction, or persistence. No `macro-api` restart.

Historical context from an earlier same-day probe (not this acceptance): checkout `cbb4fadf278`, live `biocatalyst.js` already byte-equal to #5810, signed-out locked paint already observed, entitled session not then driveable.

## Conclusion

The operator’s live Google Chrome session is a valid P0-C2 test principal: `GET /api/me` HTTP **200**, `authenticated=true`, `featuresContainsSiteFull=true`, entitlement `status=active`. Display `tier=unlimited` is **not** used as site_full proof; `/api/me` can overwrite that field from the Brain operator allowlist.

The original packet’s 524 matrix remains true for every entitled BioCatalyst route that calls `_read_bundle()` (health, screen, milestones, change-tape, prospective-changes): Tencent EdgeOne HTTP **524** at ~30.4s, empty body, no uvicorn completion line.

That matrix does **not** isolate `require_site_full_user`. `GET /api/biocatalyst/v1/health` runs `require_site_full_user` → `_read_bundle()` → `_meta()`. The Sol discriminator is `GET /api/biocatalyst/v1/trials?sort=__P0C2_INVALID__`, which runs `require_site_full_user` then rejects invalid sort with HTTP 400 **before** `_read_bundle()`.

Observed: HTTP **400** in **298ms**, body `{"detail":"invalid sort"}`, `Cache-Control: private, no-store`, `Vary: Authorization`. Origin access log completed: `GET /api/biocatalyst/v1/trials?sort=__P0C2_INVALID__ HTTP/1.1" 400 Bad Request` at 13:15:52Z on PID **3374604**. Unsigned control of the same URL remains HTTP **401** in 0.61s.

Binding interpretation: `require_site_full_user` completed. The hang is in the pointer-bound `_read_bundle()` / public-generation serving path. Entitlement-store timing and sibling paid-surface probes were **not** run (those fire only if Probe 2 is HTTP 524). `macro-api` was **not** restarted.

P0-C2 FAILED — PUBLIC BIOCATALYST GENERATION READ HANG PROVEN

## Serving identity (this acceptance)

Recorded 2026-08-18T12:38:16Z unless noted. GitHub `origin/main` moved after the original 524 matrix and again before the discriminator. Those later SHAs are **not** the production process under test. The process is identified by `/api/health.commit` + MainPID; the tree on disk is `/api/health.checkout`.

| Item | Value |
|---|---|
| `origin/main` at original 524 matrix | `ab8b3293243b5e57e2e2aa595d79bbb35f43bd2f` (`research_vault: catalog 2026-08-18T12:24Z`) |
| `origin/main` after that matrix (not tested) | `47aaa6036846900767c48e23bb06ef43ac8bdb84` |
| `origin/main` at Sol discriminator 13:13Z | `3d12412e561ef77c0a9618c9d9b18871d7344209` (`docs(agentos): complete the W1-A1 tripwire handoff… (#5904)`) |
| production `/opt/macro` HEAD at original matrix | `ab8b3293243b5e57e2e2aa595d79bbb35f43bd2f` |
| production `/opt/macro` HEAD at discriminator | `3d12412e561ef77c0a9618c9d9b18871d7344209` (checkout advanced; process did not) |
| public `GET /api/health` at original 12:38Z matrix | HTTP 200 `{"status":"ok","commit":"5a59dc7bb06","checkout":"ab8b3293243"}` `Cache-Control: private, no-store` |
| VPS `127.0.0.1:8000/api/health` at original matrix | same JSON |
| `/api/health.commit` | `5a59dc7bb06b62cdf8f0129f2e398299b9e55af9` (`press-wire: tick 2026-08-18T08:28Z [skip ci]`) |
| `/api/health.checkout` at original matrix | `ab8b3293243` |
| `/api/health` at discriminator 13:15Z | `{"status":"ok","commit":"5a59dc7bb06","checkout":"3d12412e561"}` |
| `macro-api` MainPID | **3374604**, `ActiveState=active`, InvocationID `52146294b31a4f73b8d663264ff78a66` (unchanged across this session’s earlier probe) |
| #5810 squash | `9d91bf877da428b96741c80c20f5a1c2a2b5ccc1` is an ancestor of the tested checkout |
| public pointer | `generation_id=ctgov_run_20260818T120028129041Z_e679bb3d2518` `published_at=2026-08-18T12:00:28.811854Z` |
| publisher health | `coverage_class=current_only` `state=fresh` configured/observed NCT count **4** `source_dataset_timestamp_raw=2026-08-17T09:00:05` |

`commit` ≠ `checkout`. The process loaded at 08:28Z did not restart for later main. Sol verified `app/biocatalyst.py`, `app/paywall.py`, and `app/billing.py` are byte-identical between that running commit and later audited code; this amendment does **not** restart `macro-api` on SHA drift. The discriminator 400 completed on the same MainPID **3374604**.

Live `GET https://www.mastermind-x.com/biocatalyst.js` HTTP 200, 190054 bytes, sha256 `4b52db109e7deb6469764491d01874b04c1602d254145d9c3b04ef769aa3650b`, Last-Modified `Mon, 17 Aug 2026 06:00:03 GMT`. Byte-equal to origin `templates/biocatalyst.js` and `site/biocatalyst.js` at the tested checkout. Contains `handleHydrationFailure` and the #5810 dossier client-fault copy. Live `theme.js` sha256 prefix `948020b9e66a500e`, baked `SUPABASE_CFG` present, byte-equal to `site/theme.js`.

## Signed-out control (repeated on this serving state)

Clean Playwright Chromium, no storage state, `https://www.mastermind-x.com/biocatalyst.html`:

| Probe | Result |
|---|---|
| `#bci-workspace data-state` | `locked` |
| `#bci-decision data-state` | `locked` |
| status | “Full access required” |
| “Registry page unavailable” | absent |
| `GET /api/biocatalyst/v1/trials/milestones` | HTTP **401** `application/json` `Cache-Control: private, no-store` `Vary: Authorization` |
| `pageerror` | none |
| console | one expected `Failed to load resource: … 401` |

Unsigned curl, same window:

| URL | HTTP | time | body | headers |
|---|---|---|---|---|
| public `GET /api/biocatalyst/v1/trials:screen?…` | **401** | 0.70s | `{"detail":"missing bearer token"}` | `private, no-store` `Vary: Authorization` `via: 1.1 Caddy` `server: TencentEdgeOne` |
| public `GET /api/biocatalyst/v1/trials/milestones?…` | **401** | 0.61s | same | `private, no-store` `Vary: Authorization` |
| origin `127.0.0.1:8000` screen, Host `www.mastermind-x.com` | **401** | 0.22s | same | `private, no-store` `Vary: Authorization` |
| origin `GET /api/biocatalyst/v1/health` | **401** | 0.31s | same | — |

Authorization boundary for anonymous callers remains intact.

## Entitled browser / API matrix

Drive method: operator Chrome with Apple Events JavaScript enabled. Isolated-world `execute javascript` cannot see page `MDXAuth`. A page-world `<script>` injection used the tab’s existing `MDXAuth.client().auth.getSession()` and returned only statuses, timings, boolean session flags, and envelope shapes. No access token, cookie value, email, name, or user id was printed, persisted, or committed.

| Surface | Entitled result |
|---|---|
| Session | `authEnabled=true` `hasSession=true` `userPresent=true` `cfgPresent=true` |
| `GET /api/me` (original matrix) | HTTP **200** 990ms `private, no-store`; display `tier=unlimited` recorded then, **not** used as site_full proof |
| Trial Screen `GET /api/biocatalyst/v1/trials:screen` | HTTP **524** 30543ms empty body; workspace `source_outage`; row count 0 |
| BioCatalyst health `GET /api/biocatalyst/v1/health` | HTTP **524** 30428ms empty body |
| Milestones `GET /api/biocatalyst/v1/trials/milestones` | HTTP **524** 30552ms empty body |
| Change Tape `GET /api/biocatalyst/v1/trials/change-tape` | HTTP **524** 30385ms empty body |
| First-seen Tape `GET /api/biocatalyst/v1/trials/prospective-changes` | HTTP **524** 30549ms empty body |
| Peer Matrix | not a valid 200 comparison; first layer already failed on health/screen |
| Dossier | inspector remained empty (“Choose a matching trial when the current page is available”); no HTTP 200 verified record |
| “Registry page unavailable” | absent on entitled outage paint |
| Validator / schema / stack-trace leak | absent |
| `pageerror` from AppleScript isolated world | not a substitute for page-world errors; entitled failure is the 524, not a client throw |

`journalctl -u macro-api` 12:40Z–12:50:30Z lists only the unsigned **401**s from the original matrix. No authenticated `_read_bundle()` route completed. Uvicorn writes that line when the request finishes. Those entitled calls did not finish.

The original isolation that treated `/api/biocatalyst/v1/health` as “dependency then tiny JSON” is **withdrawn**. That handler is `require_site_full_user` → `_read_bundle()` → `_meta()`.

## Sol discriminator (13:15:47Z–13:15:53Z)

Same live Chrome page-world session. No bearer, cookie, user id, email, or name printed or committed.

### Probe 1 — actual BioCatalyst entitlement (`GET /api/me`)

| Field | Value |
|---|---|
| authenticated | **true** |
| HTTP | 200 in 1604ms `Cache-Control: private, no-store` |
| tokenPresent (boolean only) | true |
| featuresContainsSiteFull | **true** |
| featureCount | 3 |
| entitlementStatus | **active** |

Display tier was not recorded on this probe. The original matrix’s `tier=unlimited` remains an allowlist overlay on `/api/me` and is not site_full proof. This principal has `site_full` in `features` and is a valid P0-C2 test principal.

### Probe 2 — dependency vs publication (`GET /api/biocatalyst/v1/trials?sort=__P0C2_INVALID__`)

Current code: `require_site_full_user` first, then HTTP 400 `invalid sort` before `_read_bundle()`.

| Field | Value |
|---|---|
| HTTP | **400** |
| elapsed | **298ms** |
| body | `{"detail":"invalid sort"}` (25 bytes) |
| headers | `Cache-Control: private, no-store` `Vary: Authorization` `Content-Type: application/json` `X-Robots-Tag: noindex, noarchive` |
| origin access log | `13:15:52Z` uvicorn PID 3374604 `GET /api/biocatalyst/v1/trials?sort=__P0C2_INVALID__ HTTP/1.1" 400 Bad Request` from EdgeOne `43.175.104.231` |
| unsigned same URL | HTTP **401** 0.61s `missing bearer token` `private, no-store` `Vary: Authorization` |

HTTP 400 quickly → `require_site_full_user` completed. First remaining production layer is the pointer-bound `_read_bundle()` / public-generation serving path.

Not run (binding stop on 400): `_store_entitlement` timing, off-process `_entitled(user_id, "site_full")`, sibling `enforce_site_full(..., always=True)` paid-surface discriminator, `macro-api` restart.

## What this is not

This is not closed-beta acceptance, D0b design acceptance, launch-soak completion, predictive intelligence, or Prophet readiness. Those gates stay closed.

This is not a client hydration-state fail. The entitled browser did the typed outage paint required for HTTP 524.

This is not an anonymous-access fail. Signed-out remains HTTP 401 / `locked`.

Checkout-interpreter positive controls were not used.

## Rollback

None. Evidence-only. Production bytes were not changed by this session.

P0-C2 FAILED — PUBLIC BIOCATALYST GENERATION READ HANG PROVEN
