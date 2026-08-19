# P-LAB-API — Prophet Operator Lab API build notes

**Wave:** V4-B5A / P-LAB-API, per `research/prophet_v4/LAB0_B5_RECUT_OPERATOR_LAB_2026-08-18.md`
(LAB-0) §5-§6. **Status at this PR:** fixture-based implementation, tests green
locally. Not yet wired to a live Radar spool/state dir or a live Prophet
index/stockdata tree on any host — see "Production wiring" below.

## What shipped

* `engine/prophet_lab/` — a pure, offline-testable projection package.
  * `contracts.py` — frozen board ids/definitions, detector identities,
    observation-class vocabulary, the all-false authority block, restated
    from LAB-0 §3-§5 as importable constants.
  * `sources.py` — injectable-root readers: Radar event-spool envelopes
    (`entry_radar.events/v1`), the live episode ledger (via
    `engine.entry_radar.live_ledger.LiveEpisodeLedger`), the Prophet
    `index.json`, the existing board-read enrichment library
    (`engine.prophet_board_read.LibraryIndex`), and the observation-baseline
    marker. Every reader degrades to empty/`None` rather than raising.
  * `observation.py` — LAB-0 §4 classification (`retrospective_seed` vs
    `live_forward`) and the measured-lead calculation, both pure functions.
  * `boards.py` — the six board builders, each a filter/join/decorate over
    already-read data.
  * `response.py` — `LabRoots` + `build_lab_response()`, the single
    orchestration entry point.
* `app/prophet_lab.py` — `GET /api/prophet/lab/v1`, registered in
  `app/main.py` immediately after the BioCatalyst block (same paid-router
  wiring-fails-loudly convention). Auth is the exact
  `app/biocatalyst.py::require_site_full_user` shape: `require_user` then
  `enforce_site_full(..., always=True)`. Kill switch `PROPHET_LAB_DISABLED`
  is read per request (not at import time) and returns a clean 503 with a
  machine-readable `error` field, independent of Radar's own
  `ENTRY_RADAR_LIVE_ENABLE`/`ENTRY_RADAR_LIVE_DISABLED`.
* `tests/test_prophet_lab.py` (32 tests) — pure projection contract tests
  against `tests/fixtures/prophet_lab/**`: all six boards, observation-class
  honesty (including the null-baseline fail-honest case), null
  `signal_known_ts` preservation, expert-identity preservation, the
  intersection board minting nothing, the union board excluding C3/C5,
  enrichment precedence (library -> published board_read -> null).
* `tests/test_prophet_lab_api.py` (14 tests) — transport-layer contract
  tests: anonymous->401, free-tier->403, paid->200, the kill switch (on/off
  values, independence from Radar's switches), a projection failure
  degrading to 503 (never 500), and `app.main` route registration with the
  paid dependency declared.
* `agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md` — added this PR's five
  new paths to `owns_paths` (ruling 8), no other edit.

## Board -> detector mapping (as implemented)

| Board id | Filter |
|---|---|
| `lab-g0-v1` | `detector_id == G0_GREY_DOT@1`, all events, one row per event |
| `lab-c1-v1` | `detector_id == C1_1D_LIVE_WASHOUT@1` AND the ticker holds a CURRENT NONTERMINAL episode for that detector in the live ledger |
| `lab-c2a-v1` | `detector_id == C2_1D_TURN@1` AND `subtype == c2a_kd_cross` |
| `lab-c2-variants-v1` | `detector_id == C2_1D_TURN@1` AND `subtype` in the six-variant set — each variant is its own row, never merged |
| `lab-g0-c2a-v1` | tickers present in BOTH `lab-g0-v1` and `lab-c2a-v1`'s underlying event sets; `detector_id=null` at the row level; `experts[]` carries both real identities |
| `lab-all-early-v1` | union of `lab-g0-v1` ∪ `lab-c1-v1`(nonterminal) ∪ `lab-c2-variants-v1`, grouped by ticker; C3/C5 are never read into the matching pool at all |

## Row shape (disclosed design choices, not frozen-spec changes)

The frozen spec (§3/§5) leaves two shapes underspecified; both are resolved
here and documented rather than silently decided:

1. **Single-family vs multi-family rows.** `lab-g0-v1`/`lab-c1-v1`/`lab-c2a-v1`/
   `lab-c2-variants-v1` are event-level rows (one row per qualifying event,
   `experts` holding that one identity for schema uniformity). The
   intersection and union boards are ticker-level cards (`experts[]` may
   hold 2+ entries). This reading follows the literal LAB-0 §3 text: only the
   intersection board's text says `detector_id = null`, and only the union
   board's text says "one ticker card may carry multiple experts[]" — implying
   the other four normally carry a real row-level `detector_id`.
2. **Row-level `observation_class` on a multi-expert card.** LAB-0 §5 lists
   `observation_class` as a per-row field, but a multi-expert card can mix
   classes (see `EEE` in the fixture: a retrospective C2a event and a
   live_forward G0 event on the same ticker). Resolved as: **any live_forward
   expert promotes the whole row** to `live_forward`; every entry inside
   `experts[]` still carries its OWN true per-event `observation_class`, so no
   information is lost to the aggregate. `evidence_eligible` follows the same
   rule at the row level.
3. **"First recorded/published"** (LAB-0 §5) resolves to the Prophet plan
   row's single `recorded_at` field — the current `prophet.index/v1` schema
   has no separate publish-history timestamp to split the two concepts
   apart. If a later Prophet-index wave adds one, `boards._prophet_comparison`
   is the one place to update.

## Observation baseline

No production baseline marker exists yet — this PR ships the CONSUMER side
(`sources.read_observation_baseline`, `observation.classify_observation`) and
documents the expected shape:

```json
{
  "schema": "prophet_lab.observation_baseline/v1",
  "baseline_started_at": "<ISO-8601 timestamp>",
  "continuous_through": "<ISO-8601 timestamp, optional>"
}
```

Until an operator provisions `$PROPHET_LAB_OBSERVATION_BASELINE_PATH`, every
row on every board is `retrospective_seed` — this is the frozen fail-honest
default (LAB-0 §4), not a bug. Minting the baseline marker at Radar-live
commissioning time is LAB-0 §6 step 3 ("Radar live commissioning"), out of
scope for this PR.

## Production wiring (env vars, all optional, all fail-open)

| Env var | Falls back to |
|---|---|
| `PROPHET_LAB_DISABLED` | unset = enabled |
| `PROPHET_LAB_RADAR_SPOOL_DIR` | `$ENTRY_RADAR_SPOOL_DIR` (Radar's own local-spool fallback var), else unset |
| `PROPHET_LAB_RADAR_STATE_DIR` | unset (no repo-relative default — the live runtime state dir is operator-provisioned) |
| `PROPHET_LAB_PROPHET_INDEX_PATH` | `<repo>/site/prophet/index.json` |
| `PROPHET_LAB_ENRICHMENT_ROOT` | `<repo>/site/stockdata` |
| `PROPHET_LAB_OBSERVATION_BASELINE_PATH` | unset |

**STOP-CONDITION note, resolved rather than escalated:** the enrichment
source (`engine.prophet_board_read.LibraryIndex` over `site/stockdata/`) is
the exact module `scripts/build_prophet.py` already uses to join
name/sector/spark onto every Prophet plan row — so it is reused, not
reinvented, per the MISSION's instruction. Whether the live API server
process has `site/stockdata/` mounted next to it at request time is
UNVERIFIED (this worktree cannot reach the VPS layout). The design therefore
degrades gracefully either way: `LibraryIndex(None)` (or a root that does not
exist) reports `available=False`, every enrichment field resolves to a
disclosed `BLOCKED_DATA` state inside `engine.prophet_board_read`, and
`boards._enrich()` reports `name`/`sector`/`spark` as `None` — exactly the
"spark=null + health note" fallback the MISSION specifies, via the
`health.enrichment_library_available` flag on every response, with a
same-source fallback to the ticker's own published `board_read` block on its
Prophet plan row (also already-published data) before giving up to `None`.
No new data plane is created either way.

## Verified

* `python3.12 -m pytest tests/test_prophet_lab.py tests/test_prophet_lab_api.py -q`
  → 46 passed.
* `python3.12 scripts/agentos.py validate` → 0 errors (pre-existing
  sparse-worktree phantom-path warnings on unrelated workstreams unchanged;
  this PR's five new `owns_paths` entries are not phantom).
* `git diff --stat` against the branch base touches only: `app/main.py` (7
  lines, the router registration), `agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md`
  (5 lines, `owns_paths` only), plus the new files listed above. Zero edits to
  `engine/entry_radar/live_pack.py`, `live_eval.py`, `live_ledger.py`, or
  `scripts/reconcile_entry_radar.py` (the four W4.1 radar-transport files).
  Zero writes to any Prophet store, zero writes under `data/`.
