# P0-C2 entitled production acceptance — BioCatalyst hydration

**Date:** 2026-08-18  
**Probe window:** 12:38:16Z–12:50:30Z (acceptance bound to this window)  
**Scope:** evidence only. Production BioCatalyst entitled journey through the actual browser and the actual public API. No application-code change. No collector, roster, soak, freshness, Capital Structure, Market Memory, Prophet, UI, `withAuth()`, or contract work. No JWT minting, printing, reconstruction, or persistence.

Historical context from an earlier same-day probe (not this acceptance): checkout `cbb4fadf278`, live `biocatalyst.js` already byte-equal to #5810, signed-out locked paint already observed, entitled session not then driveable.

## Conclusion

The operator’s live Google Chrome session is an entitled production session. Page-world `MDXAuth` is enabled, a session is present, and `GET /api/me` returns HTTP **200** in ~1s with `tier=unlimited` (operator allowlist) and `Cache-Control: private, no-store`. That same session’s bearer is attached to BioCatalyst private routes.

Every entitled BioCatalyst private request then fails the same way: Tencent EdgeOne HTTP **524**, empty body, no `Cache-Control` / `Content-Type`, elapsed **~30.4s**. The running `macro-api` access log never records those authenticated requests completing. Unsigned BioCatalyst requests to the same public URLs and to origin `127.0.0.1:8000` return HTTP **401** `missing bearer token` in **<1s** with `Cache-Control: private, no-store` and `Vary: Authorization`.

The production browser paints the typed outage contract, not a lock and not “Registry page unavailable”: `#bci-workspace data-state=source_outage`, status “Temporarily unavailable.” That paint is the correct client classification of HTTP 5xx. It is not a hydration-state bug.

Trial Screen therefore never returned a valid HTTP 200 envelope and never rendered a nonzero row set. Peer Matrix, Milestones, Change Tape, First-seen Tape, and dossier were not independently accepted: the same authenticated private-API hang is the first remaining layer, already visible on `/api/biocatalyst/v1/health`.

P0-C2 FAILED — FIRST REMAINING PRODUCTION LAYER: authenticated BioCatalyst `require_site_full_user` origin hang (Tencent EdgeOne HTTP 524 ~30s; uvicorn never completes `/api/biocatalyst/v1/*` including `/health`; unsigned 401 and entitled `/api/me` succeed)

## Serving identity (this acceptance)

Recorded 2026-08-18T12:38:16Z unless noted. Main moved underfoot after the probe; this packet is bound to the serving state actually tested, not to a later `origin/main`.

| Item | Value |
|---|---|
| `origin/main` at probe start | `ab8b3293243b5e57e2e2aa595d79bbb35f43bd2f` (`research_vault: catalog 2026-08-18T12:24Z`) |
| `origin/main` after probe (not tested) | `47aaa6036846900767c48e23bb06ef43ac8bdb84` |
| production `/opt/macro` HEAD | `ab8b3293243b5e57e2e2aa595d79bbb35f43bd2f` |
| public `GET /api/health` | HTTP 200 `{"status":"ok","commit":"5a59dc7bb06","checkout":"ab8b3293243"}` `Cache-Control: private, no-store` |
| VPS `127.0.0.1:8000/api/health` | same JSON |
| `/api/health.commit` | `5a59dc7bb06b62cdf8f0129f2e398299b9e55af9` (`press-wire: tick 2026-08-18T08:28Z [skip ci]`) |
| `/api/health.checkout` | `ab8b3293243` |
| `macro-api` MainPID | **3374604**, `ActiveState=active`, InvocationID `52146294b31a4f73b8d663264ff78a66` (unchanged across this session’s earlier probe) |
| #5810 squash | `9d91bf877da428b96741c80c20f5a1c2a2b5ccc1` is an ancestor of the tested checkout |
| public pointer | `generation_id=ctgov_run_20260818T120028129041Z_e679bb3d2518` `published_at=2026-08-18T12:00:28.811854Z` |
| publisher health | `coverage_class=current_only` `state=fresh` configured/observed NCT count **4** `source_dataset_timestamp_raw=2026-08-17T09:00:05` |

`commit` ≠ `checkout`. The process loaded at 08:28Z did not restart for later main. This packet does not treat that drift as a pass. It also does not require a restart to name the hang already observed on the running process.

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
| `GET /api/me` | HTTP **200** 990ms `private, no-store` JSON; `tierIsUnlimited=true` `tierIsSiteFull=false` (identity fields redacted) |
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

`journalctl -u macro-api` 12:40Z–12:50:30Z lists only the unsigned **401**s from this packet. No authenticated `/api/biocatalyst/v1/*` completion appears. Uvicorn writes that line when the request finishes. The entitled calls did not finish.

`/api/biocatalyst/v1/health` is `Depends(require_site_full_user)` then a small JSON body. An entitled hang on health, with `/api/me` succeeding on the same bearer, places the first remaining layer in the BioCatalyst site-full dependency path on the running origin process, not in the five-mode readers, not in #5810 client hydration, and not in anonymous auth.

## What this is not

This is not closed-beta acceptance, D0b design acceptance, launch-soak completion, predictive intelligence, or Prophet readiness. Those gates stay closed.

This is not a client hydration-state fail. The entitled browser did the typed outage paint required for HTTP 524.

This is not an anonymous-access fail. Signed-out remains HTTP 401 / `locked`.

Checkout-interpreter positive controls were not used.

## Rollback

None. Evidence-only. Production bytes were not changed by this session.

P0-C2 FAILED — FIRST REMAINING PRODUCTION LAYER: authenticated BioCatalyst `require_site_full_user` origin hang (Tencent EdgeOne HTTP 524 ~30s; uvicorn never completes `/api/biocatalyst/v1/*` including `/health`; unsigned 401 and entitled `/api/me` succeed)
