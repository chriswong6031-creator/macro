# P0 Phase 1 — BioCatalyst production hydration diagnosis

**Date:** 2026-08-16  
**Probe window:** 07:45Z–08:02Z  
**Scope:** classify the first failing layer. No repair. No collector/source/soak change. No validator weakening.

## Conclusion

**FIRST FAILING LAYER: API Trial Screen caller-binding (`app/biocatalyst.py::_peer_set_caller_binding` requires `user["tier"]`; production `require_site_full_user` never attaches it)**

An entitled browser reaches FastAPI (auth + `site_full` succeed). Trial Screen then raises a generic HTTP 503 *before* opening the public projection, because `_trial_screen_query_binding` → `_peer_set_caller_binding` demands a string `user["tier"]`. `require_user` returns the raw Supabase `/auth/v1/user` record (`id`, `email`, `user_metadata`, …). `enforce_site_full(..., always=True)` returns that same dict unchanged. The GoTrue user object has no `tier`.

That 503 is classified by the client as generic unavailable (`handleUnavailable` → “Registry page unavailable”), not locked.

API tests hide the defect: `tests/test_biocatalyst_api.py` overrides `require_site_full_user` with `{"id": "paid-user", "tier": "pro"}`.

Positive control (same production generation, same `/opt/macro` code, no JWT printed):

| `_user` shape | `_peer_set_caller_binding` | `trial_screen(...)` |
|---|---|---|
| `{"id": "<uuid>"}` (production-shaped) | HTTP 503 `trial intelligence temporarily unavailable` | HTTP 503 |
| `{"id": "paid-user", "tier": "pro"}` (test-shaped) | OK | HTTP 200, `contract_id=trial_screen_read_model.v1`, `row_count=4` |

The public projection itself is readable. Health and Milestones do not use this binding and return 200.

## Identity freeze (B0)

Recorded 2026-08-16T07:45:57Z unless noted.

| Item | Value |
|---|---|
| `origin/main` at probe start | `f8201036c1397f1b1cf34d1cfc00c46a0d55bf34` |
| `origin/main` after #5788 (report base) | `7420e6208ea1d7a35b42b18dea22321b61c12ff4` |
| production `/opt/macro` HEAD | `f8201036c1397f1b1cf34d1cfc00c46a0d55bf34` |
| `GET /api/health` | HTTP 200 `application/json` `{"status":"ok","commit":"1a170f9ceba","checkout":"f8201036c13"}` |
| `macro-api` | active / running since 2026-08-16 03:15:10 UTC; `ExecStart=/opt/macro-api/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000` |
| `BIOCATALYST_PUBLIC_ROOT` (unit `Environment=`) | `/var/lib/macro-biocatalyst/public` |
| timers | `macro-biocatalyst.timer` active; `macro-biocatalyst-history.timer` active; `macro-biocatalyst-fixed-cohort.timer` active |
| public pointer | `generation_id=ctgov_run_20260816T070131705732Z_e679bb3d2518` |
| pointer `manifest_sha256` | `e48c0544f0bbf39c765315d2428b0393d94e1df268157b3e6b0fab1b012b8aea` |
| `published_at` | `2026-08-16T07:01:32.191239Z` |
| publisher read (macro-api venv) | `READ_OK` schema `1.6.0` trials=4 configured=4 observed=4 health_state=`fresh` last_error=`null` |
| operational health.json | `state=fresh` `coverage_class=current_only` `source_dataset_timestamp_raw=2026-08-14T09:00:05` |

Served production assets (all HTTP 200; SHA-256 of body):

| Path | Content-Type | Bytes | SHA-256 | vs `origin/main` `site/` |
|---|---|---|---|---|
| `/biocatalyst.html` | `text/html; charset=utf-8` | 69913 | `c6494e8d8dde3560cbe86bd0baeeb6bfb05ac698594cf9b3b03dbd4ee1372de1` | MATCH |
| `/biocatalyst.css` | `text/css; charset=utf-8` | 55580 | `e36dc31fdc19ad25c0ee127c735604766f0da9cee56dcc30ee2dd318bdac8034` | MATCH |
| `/biocatalyst.js` | `text/javascript; charset=utf-8` | 180536 | `e7200305da4863de5e9650022fd1d05ead5659ccb3f3c76764e1ff0b4cf6f607` | MATCH |
| `/theme.js` | `text/javascript; charset=utf-8` | 362340 | `948020b9e66a500e7dd38d66b16c8867aea6ea5b7a76edb344fb9972dde796c3` | MATCH |
| `/supabase.js` | `text/javascript; charset=utf-8` | 110797 | `8596965fe918e656600a1b568d3a168f5c0d3d22a600886bb6f44a6555db01e7` | MATCH |

Served `theme.js` `window.SUPABASE_CFG`: present, non-null. `ref=fsldfzlxyavsuwqbceod`, host `fsldfzlxyavsuwqbceod.supabase.co`, anon key present (length 46). `MDXAuth` present. Template `templates/theme.js` DIFFS the served/baked `site/theme.js` (expected: baked config vs null placeholder).

Open BioCatalyst PR at probe time: #5788 (docs masterplan v2). Merged 2026-08-16T08:02:41Z as `7420e6208ea1`. No other open BioCatalyst code PRs.

## Layer table

| Layer | Result | Evidence |
|---|---|---|
| Production checkout vs `origin/main` (probe SHA) | PASS | `/opt/macro` = `f8201036…` = `origin/main` at probe; `/api/health.checkout` = `f8201036c13` |
| Static shell assets | PASS | all five paths HTTP 200; hashes match `site/` |
| Served Supabase config | PASS | non-null `SUPABASE_CFG.ref`; SDK file 200 |
| `MDXAuth.enabled()` / `client()` (anonymous Cursor browser) | PASS | `mdxEnabled=true`, `clientResolved=true` |
| Anonymous `getSession()` | PASS (no session) | `hasSession=false`, `tokenPresent=false` |
| Anonymous `GET /api/biocatalyst/v1/health` (public) | PASS | HTTP **401** `application/json` `{"detail":"missing bearer token"}` `Cache-Control: private, no-store` `Vary: Authorization` |
| Anonymous `GET` same path on VPS `127.0.0.1:8000` | PASS | HTTP **401** `application/json` `{"detail":"missing bearer token"}` |
| Anonymous browser paint | PASS | `data-state=locked` on `#bci-workspace`; copy is full-access/locked, **not** “Registry page unavailable” |
| Public projection reader | PASS | `PublicGenerationPublisher.read_trial_projection()` OK; 4 trials; health `fresh` |
| `_read_bundle()` / `health()` after auth dependency | PASS | HTTP **200** `application/json` `schema_version=biocatalyst_api.v1` coverage configured=4 observed=4 health.state=`fresh` |
| Milestones after auth dependency | PASS (empty window) | HTTP **200** `application/json`; `milestones_len=0`; `query.window=next_90d`; `effective_window=2026-08-16..2026-11-13`. Valid empty, not 503. |
| **Trial Screen after auth, production-shaped user (`id` only)** | **FAIL** | HTTP **503** `detail=trial intelligence temporarily unavailable`. Raised by `_peer_set_caller_binding` **before** `_read_bundle()`. No `BioCatalyst public projection unavailable` journal line (the 503 is unlogged: `_unavailable()` with no exception). |
| Trial Screen after auth, test-shaped user (`id`+`tier`) | PASS | HTTP **200**; `trial_screen_read_model.v1`; 4 rows |
| Live entitled JWT curl to `127.0.0.1:8000` and public domain | NOT TESTED as a printed bearer | No operator token was supplied interactively; cookies were not harvested. Substituted: (1) historical live edge traffic below; (2) in-process route functions against the production generation. |
| Live edge entitled traffic (journal) | FAIL at Trial Screen | 2026-08-16 05:56:46Z `GET /api/me` **200** (token valid). 05:57:11/13/21Z `GET /api/biocatalyst/v1/trials%3Ascreen?limit=50` **503** ×3. 48h BioCatalyst histogram: 9×401, 3×503, 2×404; **zero 200s**. |
| Edge Authorization strip | PASS | those 503s are past `require_site_full_user`; a stripped bearer would be 401 |
| Frontend contract validator on Trial Screen 200 | NOT TESTED (no 200 in production) | Builder/payload with `tier` attached is `trial_screen_read_model.v1` with 4 rows; not the incident path |
| Frontend `withAuth` silent downgrade | NOT THE INCIDENT | If it had dropped the bearer, the API would 401 and the UI would lock. Screenshots + 05:57 503s are the unavailable branch |
| Source soak / collectors / freshness / cohort | NOT TOUCHED | timers still active; generation published 07:01Z |

## Why this is not projection, not anonymous auth, and not a client schema miss

1. **Not anonymous auth.** Anonymous health is 401 and the anonymous browser paints `locked`. The incident paint is unavailable, which is `status ∉ {401,402,403}`.
2. **Not public-projection read.** Publisher + `_read_bundle()` + `health()` succeed on the current generation. Journal has **zero** `BioCatalyst public projection unavailable (...)` lines in 7 days.
3. **Not a 200 + `validate*Envelope` miss on the failing request.** The failing live request never returned 200. It returned 503. Client `fetchJson` throws `HTTP 503` → `handleUnavailable` → unavailable.
4. **Auth succeeded.** `/api/me` 200 at 05:56:46Z; screen 503 25 seconds later. `require_site_full_user` had already accepted the bearer.
5. **Exact field.** `_peer_set_caller_binding` (`app/biocatalyst.py` ~950–963) requires `user.get("tier")` to be a non-empty string. Production user dict is `dict(data)` from GoTrue `/auth/v1/user` (`app/paywall.py::_fetch_supabase_user`). That object has `id` and does not have `tier`. Missing/non-string `tier` → `_unavailable()` → 503 `trial intelligence temporarily unavailable`.

Peer Matrix uses the same `_peer_set_caller_binding` and will 503 the same way. Facets, Health, and Milestones do not.

## What Phase 2 may repair (not done here)

Attach the entitlement `tier` already resolved by `enforce_site_full` / `_entitled` onto the user dict returned to BioCatalyst routes, **or** stop requiring `tier` in `_peer_set_caller_binding` and bind only the authenticated subject. Preserve fail-closed validators. Do not make the API public. Do not skip `site_full`. Do not edit the generation.

Optional follow-on, not this incident’s first fail: default Milestones `next_90d` currently returns **zero** rows on a 4-trial current-only cut (valid empty). That paints empty, not unavailable.

## Rollback

This report is documentation only. No production bytes, collectors, or contracts were changed.
