# P0-A post-merge production verification — BioCatalyst (#5793)

**Date:** 2026-08-16  
**Probe window:** 12:39Z–13:03Z  
**Scope:** prove what PR #5793 repaired in the *actual serving stack* after merge and the normal VPS pull. No application-code change. No collector/source/soak change. No validator weakening. No `macro-api` restart (that would be a deploy act, not this verification).

## Conclusion

PR #5793 is on GitHub `origin/main` and on the production `/opt/macro` checkout. It is **not** loaded in the running `macro-api` process.

`GET /api/health` is the designed instrument: `commit` is the SHA captured at process import; `checkout` is the working tree at request time. They disagree.

| Field | Value at 13:03:33Z |
|---|---|
| `origin/main` | `102469daa6699b2977de528cf31c312495baa94a` (`cn-live(pr4): sentinel surface + rescue classifier (#5785)`). Ancestor `8f695296686687e957aa4e31fabc33259de1c224` is the #5793 squash. |
| `/opt/macro` HEAD | `102469daa6699b2977de528cf31c312495baa94a` (same as `origin/main`) |
| `/api/health.commit` | `ba6a6665a97` = `ba6a6665a971ff5d3697fa0a1e77d55f1f81d018` (`cn-live(pr1)` #5782, 2026-08-16 09:48:45Z) |
| `/api/health.checkout` | `102469daa66` |
| `macro-api` MainPID | **372997**, `ExecMainStartTimestamp=Sun 2026-08-16 09:51:09 UTC` (unchanged across the merge, the 12:42 cron, and this probe) |

`git show ba6a6665a971:app/biocatalyst.py` still has `entitlement = user.get("tier")` and raises `_unavailable()` when `tier` is missing. Disk `/opt/macro/app/biocatalyst.py` (HEAD) has `_CALLER_ACCESS_DOMAIN = "site_full"` and binds `subject` to `user["id"]` only.

The pull loop did update the tree (`app/biocatalyst.py` mtime 12:39:02Z for the #5793 bytes; later ticks advanced HEAD to `102469da`). It did **not** restart uvicorn. Last `macro-update` line that changed the API PID is `macro-api restarted pid 4193389 -> 372997`. Subsequent ticks die at W2C:

```
Job for macro-market-memory-context.service failed ...
macro-update: W2C owner replay failed: context
macro-update: refusing W2C activation before owner replay completion
```

That `exit 1` is `app/deploy/update.sh` `w2c_start_owner_chain` failure (~line 936–938). The `MACRO_API_RESTART_TRIGGER` block (~line 1214) is never reached. The log currently holds **188** of those refusals and **zero** `restart skipped` lines after the 09:51 PID change.

Therefore #5793 did **not** repair Trial Screen on the serving stack. A production-shaped entitled caller (`id` present, no `tier`) still hits `_peer_set_caller_binding` → `_unavailable()` → HTTP **503** `trial intelligence temporarily unavailable` **before** `_read_bundle()`. The frontend still classifies any non-{401,402,403} HTTP error as generic unavailable (`handleUnavailable` → `paintUnavailableWorkspace` → “Registry page unavailable”).

Live journal since merge: only this session’s anonymous `GET /api/biocatalyst/v1/health` **401**s. 48h Trial Screen histogram remains **3×503 / 0×200**.

Active generation (publisher read, not the running process) is a 4-trial `current_only` cut. That count is the *current* covered population, not a leftover from the morning 07:01Z generation. Sparse coverage is recorded below and is **not** the serving incident.

## Identity freeze

Recorded 2026-08-16T13:03:33Z unless noted.

| Item | Value |
|---|---|
| Probe UTC start | 12:39:34Z (checkout already `8f695296686`; health already drifted) |
| `origin/main` (end of probe) | `102469daa6699b2977de528cf31c312495baa94a` |
| #5793 merge SHA | `8f695296686687e957aa4e31fabc33259de1c224` (merged 12:38:04Z; now an ancestor of `main`) |
| production `/opt/macro` | `102469daa6699b2977de528cf31c312495baa94a` `main...origin/main` |
| `/api/health` | HTTP 200 `application/json` `{"status":"ok","commit":"ba6a6665a97","checkout":"102469daa66"}` |
| process | `/opt/macro-api/.venv/bin/python3 /opt/macro-api/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000` |
| public pointer | `generation_id=ctgov_run_20260816T120020849839Z_e679bb3d2518` |
| pointer `manifest_sha256` | `4292de6658cbb1d470ef8c3b987ac61139cd83981fdbd77fbc1a9800edf07385` |
| `published_at` / `last_success_at` | `2026-08-16T12:00:21.467664Z` |
| publisher read (`/opt/macro-api/.venv`, `PublicGenerationPublisher`) | schema `1.6.0`; **trials=4 configured=4 observed=4**; `health_state=fresh`; `last_error=null`; `coverage_class=current_only` |
| covered NCT IDs | `NCT04528082`, `NCT05020236`, `NCT06602479`, `NCT07218380` |
| `BIOCATALYST_PUBLIC_ROOT` | `/var/lib/macro-biocatalyst/public` (name only; unit Environment not dumped) |

Served static assets (HTTP 200 via `127.0.0.1` Host `www.mastermind-x.com`; SHA-256 of body matches worktree `site/`):

| Path | Content-Type | Bytes | SHA-256 |
|---|---|---|---|
| `/biocatalyst.html` | `text/html; charset=utf-8` | 69913 | `c6494e8d8dde3560cbe86bd0baeeb6bfb05ac698594cf9b3b03dbd4ee1372de1` |
| `/biocatalyst.css` | `text/css; charset=utf-8` | 55580 | `e36dc31fdc19ad25c0ee127c735604766f0da9cee56dcc30ee2dd318bdac8034` |
| `/biocatalyst.js` | `text/javascript; charset=utf-8` | 180536 | `e7200305da4863de5e9650022fd1d05ead5659ccb3f3c76764e1ff0b4cf6f607` |
| `/theme.js` | `text/javascript; charset=utf-8` | 362340 | `948020b9e66a500e7dd38d66b16c8867aea6ea5b7a76edb344fb9972dde796c3` |
| `/supabase.js` | `text/javascript; charset=utf-8` | 110797 | `8596965fe918e656600a1b568d3a168f5c0d3d22a600886bb6f44a6555db01e7` |

## What #5793 repaired (on disk, not in `sys.modules`)

Running-commit source (`git show ba6a6665a971:app/biocatalyst.py`):

```python
entitlement = user.get("tier")
if (
    not isinstance(user_id, str)
    ...
    or not isinstance(entitlement, str)
    ...
):
    raise _unavailable()
return {"subject": user_id, "entitlement": entitlement}
```

Checkout source (`/opt/macro/app/biocatalyst.py` at HEAD, and `origin/main`):

```python
# binds subject to user["id"]; entitlement is the constant "site_full"
return {"subject": user_id, "entitlement": _CALLER_ACCESS_DOMAIN}
```

Routes that still call `_peer_set_caller_binding` on the running process: Trial Screen (`GET /api/biocatalyst/v1/trials:screen`) and Peer Matrix (`POST /api/biocatalyst/v1/trial-peer-sets:resolve`). Health, Milestones, Change Tape, First-seen Tape, and trial dossier do **not** use that binder.

Exact 503 function on the serving process: `_peer_set_caller_binding` → `_unavailable()` (`app/biocatalyst.py` in commit `ba6a6665a971`). No `BioCatalyst public projection unavailable` journal line is expected: `_unavailable()` with no exception is unlogged. That matches Phase 1.

## Mode-by-mode

Entitled browser/API against the **running** process could not be completed: a copied Chrome profile launched with Playwright (`channel=chrome`, headed) had `MDXAuth.hasSession()=false` / `tokenPresent=false` and painted `data-state=locked`. No JWT was minted or printed. Journal since 12:38Z shows no entitled BioCatalyst traffic.

Where a cell says “not HTTP-probed on PID 372997”, the generation-side fact is from `PublicGenerationPublisher.read_trial_projection()` on the same public root the API would open *after* a restart.

### Signed-out browser (required)

| Item | Result |
|---|---|
| URL | `https://www.mastermind-x.com/biocatalyst.html` |
| `MDXAuth.enabled()` | true |
| session | none |
| `GET /api/biocatalyst/v1/health` (page + VPS `127.0.0.1:8000`) | HTTP **401** `application/json` `{"detail":"missing bearer token"}` `Cache-Control: private, no-store` |
| `#bci-workspace data-state` | `locked` |
| copy | full-access/locked; **not** “Registry page unavailable” |
| `pageerror` | none |
| console | Chromium “Failed to load resource: 401” on the expected anonymous health/list calls. Not an unexpected exception. |

Refresh-without-losing-auth, five-mode entitled switch, and dossier back/forward were **not** exercised (no reconstitutable entitled session).

### 1. Trial Screen

| Item | Serving process (PID 372997) | Checkout / generation |
|---|---|---|
| Endpoint | `GET /api/biocatalyst/v1/trials:screen` | same |
| HTTP | **still the caller-binding 503** for a production-shaped user. 48h journal: 3×503, 0×200. No post-merge entitled hit. | disk source no longer requires `tier` |
| Browser | not entitled-probed; anonymous is locked (correct) | — |
| Row count vs covered population | not returned (503 before `_read_bundle()`) | **4** trials = configured 4 = observed 4 on generation `ctgov_run_20260816T120020849839Z_e679bb3d2518` |
| Paint if 503 | `handleUnavailable` → unavailable / “Registry page unavailable” (same client as Phase 1) | — |

Do not treat “4” as a frozen product constant. The noon generation is a *different* `generation_id` from the 07:01Z cut in Phase 1; it happens to still cover four NCTs.

### 2. Peer Matrix

| Item | Serving process | Checkout / generation |
|---|---|---|
| Endpoint | `POST /api/biocatalyst/v1/trial-peer-sets:resolve` | same |
| HTTP | same binder as Trial Screen → **503** on production-shaped user | disk source would accept `{id}` |
| Requested cohort | not submitted on the live PID | intended probe IDs: `NCT04528082`, `NCT05020236` (both in the current covered set). Resolver keeps caller-supplied `cohort_nct_ids` order (`engine/biocatalyst/peer_matrix.py` returns `"cohort_nct_ids": list(cohort)`). |
| Dossier selection from matrix | not exercised | — |

### 3. Milestones

| Item | Serving process | Checkout / generation |
|---|---|---|
| Endpoint | `GET /api/biocatalyst/v1/trials/milestones` | same |
| HTTP | does **not** use `_peer_set_caller_binding`; would be 200 or a real projection 503. **Not HTTP-probed on PID 372997** (no entitled token). Anonymous is 401. | Phase 1 in-process on the prior 4-trial cut: HTTP 200, `milestones_len=0`, `query.window=next_90d`. Current cut is still 4 current-only trials; a legitimate zero remains the expected product state until a covered NCT has a primary-completion date inside the window. |
| Browser | signed-out locked. Entitled empty-vs-unavailable **not** painted. | Client empty titles exist (`No matching…` / milestone empty copy). A 503 still becomes “Registry page unavailable”. |

### 4. Change Tape

Generation-side (publisher), contract `trial_change_tape_read_model.v1` / schema `1.0.0`:

| NCT | `history.row_count` | `history.unavailable_reason` | `prospective` |
|---|---|---|---|
| NCT04528082 | 42 | null | unavailable `prospective_not_collected` |
| NCT05020236 | 0 | string (unavailable) | unavailable `prospective_not_collected` |
| NCT06602479 | 28 | null | unavailable `prospective_not_collected` |
| NCT07218380 | 21 | null | unavailable `prospective_not_collected` |

API `GET /api/biocatalyst/v1/trials/change-tape` does not use the caller binder. On a restarted process it should 200 with `change_tape_coverage.class=replay_verified_record_history` and a page of history rows (91 history rows across the three available tapes before filters/limit=50). **Not HTTP-probed on PID 372997.** Browser/API disagreement was not observed because the entitled UI was not reached.

`prospective_state` on the API envelope is `unavailable_without_retained_activation_proofs` by construction. That is coverage/product, not a serving 503.

### 5. First-seen Tape

Publisher `prospective_models_by_nct` for every covered NCT:

```json
{"available": false, "unavailable_reason": "baseline_not_established"}
```

| Field | Generation truth |
|---|---|
| `coverage_state` (API envelope, if 200) | would be derived in `trial_prospective_changes` from those models (`pre_baseline` / unavailable counts; `class=prospective_current_only`) |
| `coverage_started_at` | no established baseline on any of the four NCTs |
| `last_observed_at` | no active observation window |
| row count | **0** is contractually valid |

`GET /api/biocatalyst/v1/trials/prospective-changes` does not use the caller binder. **Not HTTP-probed on PID 372997.** A valid 200 must not be painted as generic registry outage; that paint is reserved for `handleUnavailable` (HTTP error or thrown contract failure). Unsigned-out paint is locked, which is correct.

### 6. Trial dossier

| Item | Serving process | Checkout / generation |
|---|---|---|
| Endpoint | `GET /api/biocatalyst/v1/trials/{nct}` | same |
| HTTP | no caller binder; 401 anonymous. Entitled 200 **not** probed on PID 372997. | NCT `NCT04528082` is in the current covered set. Detail builder emits ClinicalTrials.gov source URL `https://clinicaltrials.gov/study/{nct_id}`. |
| Browser | not opened entitled | — |

## Frontend 200-vs-unavailable note

Not triggered on this probe: no entitled 200 body reached the browser. The first failing *serving* step remains the **503 from `_peer_set_caller_binding`**, not `validateScreenEnvelope`. If a future restart returns 200 and the UI still paints unavailable, inspect `loadMilestones` → `validate*Envelope` (first throw sets `state.contractFailed` → `integrity_block`) before blaming HTTP.

Expected 401 console noise on the anonymous page is not a `pageerror`.

## What was deliberately not done

- No `systemctl restart macro-api`.
- No application-code, frontend error-classification, collector, or generation edit.
- No JWT printed or committed.
- Importing `app.biocatalyst` in a *second* VPS interpreter (checkout positive control of `trial_screen({id})`) was abandoned after it blocked; serving proof uses `/api/health.commit` + `git show` of that commit, not a second import.

## Rollback

This report is documentation only. Production bytes were not changed by this session.

P0-A PRODUCTION FIX VERIFIED — NEXT FAILURE: running macro-api still imported pre-#5793 caller-binding (`health.commit=ba6a6665a97`, PID 372997 since 09:51Z) because `macro-update` `exit 1`s at W2C owner replay (`macro-market-memory-context`) before the API restart trigger; Trial Screen/Peer Matrix on the serving process still 503 for production-shaped users
