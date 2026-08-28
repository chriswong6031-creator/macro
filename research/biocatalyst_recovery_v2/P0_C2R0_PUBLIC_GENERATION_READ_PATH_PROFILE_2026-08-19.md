# P0-C2R0 — public generation read-path profile

**Date:** 2026-08-19  
**Scope:** diagnosis only. No application-code change, no publication-contract change, no validator weakening, no cache implementation, no API restart, no EdgeOne timeout change, no B1S2c / P0-C3 / BPC-RECON work.  
**Authority:** #5906 / `P0_C2_ENTITLED_PRODUCTION_ACCEPTANCE_2026-08-18.md` remains the incident record. Auth/entitlement is not re-opened: the Sol discriminator on that packet (HTTP 400 in 298 ms before `_read_bundle()`) still stands.

P0-C2R0 PROFILED — PRIMARY MECHANISM: DEEP_VALIDATION_AMPLIFICATION

One entitled `_read_bundle()` fully JSON-Schema-validates the pointer-bound four-NCT generation three times, constructing a fresh `ContractRegistry` on every `validate_contract()` call. Isolated off-process wall time is 16–26 s of user CPU. Two concurrent reads become 38–42 s and cross the EdgeOne ~30 s ceiling. The generation itself is small (~1 MB, 23 files). I/O is not the cost.

## Serving identity under test

Recorded 2026-08-19T03:46Z–04:02Z. GitHub `origin/main` later moved to `4ae76e4700b6`; that later SHA is **not** the process under test.

| Item | Value |
|---|---|
| `origin/main` at start of this profile | `d772fbd6f88461e789701cb686fe83e28e3ddf4d` (`research_vault: catalog 2026-08-19T03:40Z`) |
| production `/opt/macro` HEAD / `/api/health.checkout` | `d772fbd6f88` (matches the tested `origin/main`) |
| `/api/health.commit` (loaded process) | `19b009fceca6bd86e0acd835860d174bd678e48a` (`D1.1F: PIT-safe Government Revenue agency labels (#5856)`) |
| `macro-api` MainPID | **4074512** since 2026-08-18 19:33:09 UTC, InvocationID `9849fe1c92f44fc693c38af43d257f49`, 10 threads |
| uvicorn invocation | `/opt/macro-api/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000` (one process, no `--workers`) |
| #5906 failed identity | MainPID **3374604**, process commit `5a59dc7bb06` — **this is a different live process** |
| current generation | `ctgov_run_20260819T030024939907Z_e679bb3d2518` published 2026-08-19T03:00:25.494863Z |

`commit` ≠ `checkout`. Reader/validator bytes are nevertheless identical between process commit `19b009fceca` and disk checkout `d772fbd6` for every file in the read stack (`app/biocatalyst.py`, `engine/biocatalyst/publication.py`, `trials.py`, `protocols.py`, `prospective.py`, `change_tape.py`, `history.py`, `storage.py`, `engine/sector_intelligence/contracts.py`). `git diff 19b009fceca HEAD -- <those paths>` is empty. Off-process timings therefore describe the running process's code, not a later generation of validators.

The API was **not** restarted.

## Step 1 — incident still exists on the current process

Because MainPID and process commit changed since #5906, one entitled `GET /api/biocatalyst/v1/health` was issued from the existing live Chrome `site_full` session (page-world `MDXAuth`, no token printed or persisted).

| Field | Value |
|---|---|
| `authEnabled` / `hasSession` / `tokenPresent` | true / true / true |
| HTTP | **524** |
| elapsed | **30519 ms** |
| body | empty |
| uvicorn completion line | absent (same signature as #5906) |

Unsigned `GET /api/biocatalyst/v1/health` on this same process remains HTTP **401** in well under 1 s (`03:49:00Z` origin access log). Auth is not the hang.

Because the entitled health call still 524s, the previously commissioned full P0-C2 journey was **not** re-run as an acceptance. #5906 stays the historical incident; this packet profiles the current failing state.

## Step 2 — pointer-bound generation census

Public root `/var/lib/macro-biocatalyst/public`. Current generation directory exists. 182 generation directories sit on disk; `_read_bundle()` opens only the pointer-bound current one. Source bodies were not printed.

| Field | Value |
|---|---|
| generation id | `ctgov_run_20260819T030024939907Z_e679bb3d2518` |
| schema | `1.6.0` / `biocatalyst_public_generation.v1` / `coverage_class=current_only` |
| configured / observed NCT count | **4 / 4** |
| health.state | `fresh` |
| files | **23** |
| total bytes | **991,714** (~0.95 MiB) |

Bytes and file counts by artifact family:

| Family | Files | Bytes |
|---|---:|---:|
| change_tapes | 4 | 591,172 |
| protocols | 4 | 176,667 |
| snapshots | 4 | 175,601 |
| history | 4 | 38,029 |
| manifest | 1 | 4,256 |
| trials | 4 | 3,632 |
| source_manifest | 1 | 1,923 |
| health | 1 | 434 |
| prospective | 0 | 0 (absent on 1.6.0) |

The supposedly four-NCT product generation is small and bounded. Change tapes are the largest family (60% of bytes) and are still well under a megabyte. This is not an exploded artifact.

## Step 3 — off-process read stack

Production Python: `/opt/macro-api/.venv/bin/python`, cwd `/opt/macro`, public root as above. One first-in-process observation, then three sequential repeats. Times are wall ms; user CPU ≈ wall in every row (sys CPU < 3%). This is CPU, not filesystem wait.

| Call | First wall / user CPU | Repeat 1 | Repeat 2 | Repeat 3 |
|---|---:|---:|---:|---:|
| `read_committed()` | 6056 / 5782 | 5454 / 5082 | 3895 / 3864 | 3967 / 3913 |
| `_load_generation_manifest(current)` | 3974 / 3914 | 4288 / 4178 | 3846 / 3816 | 3931 / 3886 |
| `read_trial_projection()` | 11064 / 10910 | 13217 / 13041 | 12729 / 12536 | 11252 / 11054 |
| `read_operational_health()` | 3970 / 3857 | 4434 / 4325 | 4171 / 4111 | 4378 / 4306 |
| `app.biocatalyst._read_bundle()` | **16062 / 15816** | **16203 / 15950** | **16554 / 16263** | **17221 / 16583** |

A later fresh-interpreter sequential `_read_bundle()` (no prior warm-up in that process) was **26527 ms** wall / 24793 ms user CPU. Isolated reads therefore sit at 16 s warm / 26 s cold — approaching, and in the cold case one scheduler stall from, the EdgeOne ~30 s ceiling. They do not need a hung running process to explain a 524 once a second `_read_bundle()` shares the GIL.

## Step 4 — amplification count

Ephemeral wrap of `PublicGenerationPublisher._load_generation_manifest` around exactly one `_read_bundle()`. Repository was not edited. Same generation id on every call.

| Invocation | generation_id | elapsed_ms | user_cpu_ms |
|---:|---|---:|---:|
| 1 | `ctgov_run_20260819T030024939907Z_e679bb3d2518` | 4250.8 | 4178.3 |
| 2 | same | 4119.9 | 3960.0 |
| 3 | same | 3778.9 | 3736.7 |
| **sum** | | **12149.6** | **11875.0** |

`_read_bundle()` wall for that wrapped call: 16223.9 ms. Three full `_load_generation_manifest` passes consume **75%** of it.

That matches the code shape, now measured rather than assumed:

1. `_read_bundle` → `read_trial_projection` → `read_committed` → `_load_generation_manifest`
2. `read_trial_projection` → `_load_generation_manifest` again
3. projection artifact reads (per-NCT snapshot / protocol / history / change-tape validation)
4. `read_operational_health` → `read_committed` → `_load_generation_manifest` a third time

cProfile of one `_read_bundle()` (instrumentation inflated wall to 43.7 s; use for *where* time goes, not the 16 s absolute):

| Function | File | ncalls | cumtime_s |
|---|---|---:|---:|
| `_read_bundle` | `biocatalyst.py` | 1 | 43.66 |
| `validate_contract` | `contracts.py` | **64** | 43.08 |
| `read_trial_projection` | `publication.py` | 1 | 32.62 |
| `_load_generation_manifest` | `publication.py` | **3** | 32.62 |
| `jsonschema.iter_errors` | `validators.py` | 162,804 | 31.34 |
| `jsonschema.descend` | `validators.py` | 984,660 | 31.33 |
| `$ref` | `_keywords.py` | 257,472 | 31.24 |
| `oneOf` | `_keywords.py` | 89,792 | 28.53 |
| `read_committed` | `publication.py` | **2** | 22.07 |
| `validate_trial_snapshot` | `trials.py` | **16** | 21.96 |
| `validate_trial_protocol_projection` | `protocols.py` | **16** | 13.75 |
| `read_operational_health` | `publication.py` | 1 | 11.04 |
| `ContractRegistry.__init__` | `contracts.py` | **64** | 10.61 |
| `_discover_records` | `contracts.py` | 64 | 4.44 |
| `_validate_trial_history_model_binding` | `publication.py` | 16 | 4.05 |

`validate_trial_snapshot` 16 = 4 NCT × (3 `_load_generation_manifest` snapshot bindings + 1 `read_trial_projection` binding). Same 16× pattern on protocols and history.

Every `validate_contract()` constructs a **new** `ContractRegistry` (`contracts.py` around the `registry = ContractRegistry(repo_root)` call). That rediscovers owned schemas 64 times per `_read_bundle()`. It is secondary to jsonschema `oneOf`/`$ref` walk time, but it is real (≈10 s of the profiled 43 s).

## Step 5 — classification

Off-process `_read_bundle()` itself approaches the edge timeout and repeated `_load_generation_manifest` / `validate_contract` dominate elapsed time.

**Label: `DEEP_VALIDATION_AMPLIFICATION`.**

Not used, with why:

- `RUNNING_PROCESS_STALL` — off-process CPU time already explains the seconds. User CPU ≈ wall. `py-spy` is not installed; a tracer was not attached; the API was not restarted. A stall in PID 4074512 is not required.
- `CONCURRENT_GENERATION_VALIDATION_AMPLIFICATION` — two concurrent `_read_bundle()` calls in one ephemeral process took **41731 ms** pair wall; each worker 41728 ms / 38606 ms. That *does* reproduce a 524, and the live BioCatalyst page fires Trial Screen plus facets on `init` (both call `_read_bundle()`), so concurrency is how a 16–26 s cost becomes a reliable EdgeOne 524. It is an aggravating multiplier of the same validation work, not a distinct hang. Isolated is not fast.

## Narrowest repair (not implemented)

Do not weaken validation. Do not delete artifact hashing. Do not trust the pointer. Do not raise the EdgeOne timeout. Do not swallow timeouts. Do not rewrite the API async. Do not suppress frontend requests. Do not restart `macro-api` because commit ≠ checkout.

One repair PR, two stacked levers in priority order:

1. **Intra-request reuse of one fully validated generation.** Memoize `_load_generation_manifest` (or the validated `CommittedTrialProjection`) for the lifetime of one `_read_bundle()` / one publisher instance used by that request. Three identical full validations become one. This is not a cross-request cache and is not a pointer shortcut: hashing and schema checks still run, once.
2. **Process-lifetime `ContractRegistry`.** `validate_contract()` today constructs a new registry on every call. Reuse one discovered/compiled registry so jsonschema still validates each document, but schema discovery and validator compile do not run 64 times per request.

Expected effect of (1) alone: drop `_read_bundle()` from ~16 s warm / ~26 s cold toward one `_load_generation_manifest` (~4 s) plus the leftover per-NCT projection work. Two concurrent page-init reads then stay under 30 s. Prove that with the same off-process table plus one entitled `GET /health` before calling P0-C2 accepted.

Do not ship (1) as a global LRU of generations. Do not skip `read_trial_projection`'s per-NCT snapshot binding unless that binding is shown to be a duplicate of work already done inside the memoized `_load_generation_manifest` *and* the duplicate is removed with tests, not by trusting the pointer.

## What this is not

Not closed-beta acceptance, D0b design acceptance, launch-soak completion, predictive intelligence, or Prophet readiness. Not a code fix. #5906 remains the incident. This packet only names the repair.

P0-C2R0 PROFILED — PRIMARY MECHANISM: DEEP_VALIDATION_AMPLIFICATION
