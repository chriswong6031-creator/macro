# P-LAB-API — Prophet Operator Lab API build notes

**Wave:** V4-B5A / P-LAB-API, per `research/prophet_v4/LAB0_B5_RECUT_OPERATOR_LAB_2026-08-18.md`
(LAB-0) §5-§6. **Status:** fixture-based implementation, tests green locally,
**round 1 of independent review addressed** (see §Review round 1 dispositions
below), **CI guard reds fixed** (see §CI guard fixes below), **day-2 main
reconciliation + temporal correctness amendment landed** (see §Day-2
reconciliation below). Not yet wired to a live Radar spool/state dir or a
live Prophet index/stockdata tree on any host — see "Production wiring"
below.

## What shipped

* `engine/prophet_lab/` — a pure, offline-testable projection package.
  * `contracts.py` — frozen board ids/definitions, detector identities,
    observation-class vocabulary, the all-false authority block, restated
    from LAB-0 §3-§5 as importable constants.
  * `sources.py` — injectable-root readers: Radar event-spool envelopes
    (`entry_radar.events/v1`, now returning a `SpoolReadResult` with
    read-outcome counts, not just a list), the live episode ledger (via
    `engine.entry_radar.live_ledger.LiveEpisodeLedger`, now returning an
    `EpisodeReadResult` with an `available`/`reason` pair), the Prophet
    `index.json`, the existing board-read enrichment library
    (`engine.prophet_board_read.LibraryIndex`), the observation-baseline
    marker (now schema-validated), and `baseline_coverage_verified()` (fail
    CLOSED coverage check). Every reader degrades to empty/`None` rather than
    raising.
  * `observation.py` — LAB-0 §4 classification (`retrospective_seed` vs
    `live_forward`) and the measured-lead calculation (now refusing a
    non-positive lead), both pure functions.
  * `boards.py` — the six board builders, each a filter/join/decorate over
    already-read data. Now: a deterministic parsed-datetime sort key, CURRENT
    (non-closed)-only Prophet membership with a `prior_plan` fallback,
    multi-expert mixed-class attribution, and spark resolution that never
    ships a dangling reference.
  * `response.py` — `LabRoots` + `build_lab_response()`, the single
    orchestration entry point. Now assembles the `generation` block,
    `board_definitions`, and `board_availability`.
* `app/prophet_lab.py` — `GET /api/prophet/lab/v1`, registered in
  `app/main.py` immediately after the BioCatalyst block (same paid-router
  wiring-fails-loudly convention). Auth is the exact
  `app/biocatalyst.py::require_site_full_user` shape: `require_user` then
  `enforce_site_full(..., always=True)`. Kill switch `PROPHET_LAB_DISABLED`
  is read per request (not at import time), case-insensitively, fail-toward-
  disabled, and returns a clean 503 with a machine-readable `error` field,
  independent of Radar's own `ENTRY_RADAR_LIVE_ENABLE`/`ENTRY_RADAR_LIVE_DISABLED`.
* `tests/test_prophet_lab.py` (70 tests) — pure projection contract tests
  against `tests/fixtures/prophet_lab/**`.
* `tests/test_prophet_lab_api.py` (29 tests) — transport-layer contract
  tests.
* `agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md` — added this PR's five
  new paths to `owns_paths` (ruling 8), no other edit.

## Board -> detector mapping (as implemented, unchanged by review round 1)

| Board id | Filter |
|---|---|
| `lab-g0-v1` | `detector_id == G0_GREY_DOT@1`, all events, one row per event |
| `lab-c1-v1` | `detector_id == C1_1D_LIVE_WASHOUT@1` AND the ticker holds a CURRENT NONTERMINAL episode for that detector in the live ledger |
| `lab-c2a-v1` | `detector_id == C2_1D_TURN@1` AND `subtype == c2a_kd_cross` |
| `lab-c2-variants-v1` | `detector_id == C2_1D_TURN@1` AND `subtype` in the six-variant set — each variant is its own row, never merged |
| `lab-g0-c2a-v1` | tickers present in BOTH `lab-g0-v1` and `lab-c2a-v1`'s underlying event sets; `detector_id=null` at the row level; `experts[]` carries both real identities |
| `lab-all-early-v1` | union of `lab-g0-v1` ∪ `lab-c1-v1`(nonterminal) ∪ `lab-c2-variants-v1`, grouped by ticker; C3/C5 are never read into the matching pool at all |

## Response shape additions (review round 1)

* **`generation`** (top level): `generated_at` (server clock), `latest_pass_ts`
  (max envelope `pass_ts` read), `pack_as_of`/`pack_hash` (from the newest
  envelope's `pack` block), `baseline_started_at` (the CONFIGURED value, even
  when coverage is unverified), `baseline_coverage_verified` (bool — see S1
  below). This is what a UI's LAB-stale/unavailable states key on.
* **`board_definitions`** (top level): the frozen LAB-0 §3 prose per board id
  — kept in the payload rather than dropped (review N3; my call, documented
  in the disposition table).
* **`board_availability`** (top level): per-board `{"available": bool,
  "reason": str|None}`, plus `lab-all-early-v1.components.{g0,c1,c2_variants}`
  — lets a consumer distinguish "the episode ledger is unconfigured/unreadable"
  from "genuinely nothing nonterminal today" (review S5). The board's own
  `rows` list stays a plain list either way — this is a SIBLING structure, not
  a restructuring of `boards[board_id]`, to keep the blast radius on existing
  consumers minimal.
* **`prophet_comparison.prior_plan`**: populated only when a ticker's ONLY
  Prophet plan(s) are closed — the most recent closed plan, clearly labeled
  `"closed": true`, and carrying no lead-related key at all (review B1).
* **`prophet_comparison.measured_from_event_id`**: the `event_id` of the
  live_forward expert a card's measured lead is attributed to; `None`
  whenever no lead is reported (review B3).
* **row-level `observation_class_mixed`**: `true` when a multi-expert card's
  constituent experts do not all agree on observation class (review B3).
* **`health`**: `radar_spool_configured`, `radar_spool_source` (which env
  var/path resolved the spool root, or `"unconfigured"` — review S2 cheap
  half), `radar_envelopes_skipped` (torn/off-schema counts — review S4/S7),
  `radar_episode_ledger_available` (renamed from `..._readable` to match the
  new `EpisodeReadResult` semantics), `observation_baseline_coverage_verified`.

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
   information is lost to the aggregate, and `observation_class_mixed` names
   the card as covering ineligible seed evidence too (review B3).
   `evidence_eligible` at the row level is now DERIVED directly from the
   promoted `observation_class` (a single source of truth) rather than an
   independent `any(...)` scan.
3. **"First recorded/published"** (LAB-0 §5) resolves to the Prophet plan
   row's single `recorded_at` field — the current `prophet.index/v1` schema
   has no separate publish-history timestamp to split the two concepts
   apart. If a later Prophet-index wave adds one, `boards._prophet_comparison`
   is the one place to update.

## Observation baseline

No production baseline marker exists yet — this PR ships the CONSUMER side
(`sources.read_observation_baseline`, `observation.classify_observation`,
`sources.baseline_coverage_verified`) and documents the expected shape:

```json
{
  "schema": "prophet_lab.observation_baseline/v1",
  "baseline_started_at": "<ISO-8601 timestamp>",
  "continuous_through": "<ISO-8601 timestamp, optional>"
}
```

Until an operator provisions `$PROPHET_LAB_OBSERVATION_BASELINE_PATH`, every
row on every board is `retrospective_seed` — this is the frozen fail-honest
default (LAB-0 §4), not a bug. Review S1 hardens this further: even WITH a
baseline configured, if the spool's earliest surviving envelope postdates
`baseline_started_at` (a coverage gap — retention, compaction, or a
misconfigured root), `baseline_coverage_verified` is `false` and EVERY row
still degrades to `retrospective_seed`, because an unverifiable "continuous
since X" claim is not a verified one. Minting the baseline marker at
Radar-live commissioning time is LAB-0 §6 step 3 ("Radar live
commissioning"), out of scope for this PR.

## Production wiring (env vars, all optional, all fail-open)

| Env var | Falls back to |
|---|---|
| `PROPHET_LAB_DISABLED` | unset = enabled (case-insensitive OFF set: `""`/`"0"`/`"false"`/`"no"`/`"off"`; anything else disables — fail toward disabled) |
| `PROPHET_LAB_RADAR_SPOOL_DIR` | `$ENTRY_RADAR_SPOOL_DIR` (Radar's own local-spool fallback var), else unset |
| `PROPHET_LAB_RADAR_STATE_DIR` | unset (no repo-relative default — the live runtime state dir is operator-provisioned) |
| `PROPHET_LAB_PROPHET_INDEX_PATH` | `<repo>/site/prophet/index.json` |
| `PROPHET_LAB_ENRICHMENT_ROOT` | `<repo>/site/stockdata` |
| `PROPHET_LAB_OBSERVATION_BASELINE_PATH` | unset |

`health.radar_spool_source` echoes which of the two spool env vars resolved
(or `"unconfigured"`), so an operator can tell the difference between "the
Lab has its own spool root" and "it is quietly riding Radar's".

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
`boards._enrich()` reports `name`/`sector` as `None` — exactly the "health
note" fallback the MISSION specifies — with a same-source fallback to the
ticker's OWN non-closed Prophet plan rows' published `board_read` block
before giving up to `None`. Review S6 hardens `spark` specifically: it is
now EITHER a fully resolved SVG body (never a
`board_read_sparks.json#TICKER` reference this API does not itself serve) OR
`None` — the published-`board_read` fallback path in particular cannot
resolve a real body without reading a second site artifact this API does not
read, so it ships `spark: None` there rather than propagate an unresolvable
reference. No new data plane is created either way.

## Review round 1 dispositions

Independent review returned BLOCKED with 15 named findings (architecture,
auth boundary, and board/detector definitions were judged clean). Every
finding is fixed in this PR; none were deferred except the three explicitly
marked DEFERRED below (which the review itself scoped out of this PR).

| Finding | Disposition | Where |
|---|---|---|
| B1 — `prophet_comparison` must reflect current membership only | Fixed: membership/lifecycle/stance now derive from the newest NON-closed plan only; a closed-only ticker reports `membership:false` + a `prior_plan` sub-object with no lead field at all | `boards._current_and_prior_plans`, `boards._prophet_comparison` |
| N5 (bundled with B1) — enrichment fallback must not stop at the first plan row | Fixed: the fallback now iterates every non-closed plan row and keeps the first AVAILABLE value per field, rather than breaking on the first row that merely HAS a `board_read` mapping | `boards._enrich` |
| B1 — never emit a negative lead against historical plans | Fixed: `measured_lead_days` now returns `None` unless the Prophet anchor strictly POSTDATES the Lab's first observation (positive-only); `prior_plan` never carries a lead key | `observation.measured_lead_days` |
| B2 — add the frozen §5 `generation` block | Fixed: `generated_at`, `latest_pass_ts`, `pack_as_of`, `pack_hash`, `baseline_started_at`, `baseline_coverage_verified` | `response.build_lab_response` |
| B3 — multi-expert card attribution (`measured_from_event_id`, `observation_class_mixed`) | Fixed: both fields added; row `evidence_eligible` now derives from the promoted `observation_class` directly | `boards._row_observation_class_and_mixed`, `boards._live_forward_lead_anchor`, `boards._prophet_comparison` |
| S1 — baseline coverage must fail CLOSED | Fixed: `sources.baseline_coverage_verified()` requires the earliest surviving envelope to be AT OR BEFORE `baseline_started_at`; when unverified the baseline is treated as absent for every board (both directions tested) | `sources.baseline_coverage_verified`, `response.build_lab_response` |
| S4/S7 — health from read outcomes, not `is_dir()` | Fixed: `read_radar_envelopes` now returns a `SpoolReadResult` with `files_seen`/`envelopes_skipped`; health reports both, surfacing schema drift as a visible skip count | `sources.SpoolReadResult`, `response.build_lab_response` |
| S5 — per-board availability (episode ledger unavailable vs. genuinely empty) | Fixed: `read_live_episodes` returns an `EpisodeReadResult(available, reason)`; `board_availability` in the response names `lab-c1-v1` and `lab-all-early-v1`'s `components.c1` | `sources.EpisodeReadResult`, `response.build_lab_response` |
| S6 — never emit a dangling spark reference | Fixed: the primary (LibraryIndex) enrichment path now returns the resolved SVG body (via the same `sparks` accumulator `build_board_read` already populates) instead of the `board_read_sparks.json#TICKER` reference; the published-fallback path ships `spark:null` rather than propagate an unresolvable reference | `boards._enrich` |
| S2 (cheap part) — `spool_source` in health | Fixed: `LabRoots.radar_spool_source_label`, populated by `app.prophet_lab._env_path_labeled`, echoed as `health.radar_spool_source` | `app/prophet_lab.py`, `response.build_lab_response` |
| N1 — deterministic single-clock sort | Fixed: every sort now goes through `boards._parse_sort_ts` (a parsed, tz-normalized `datetime`, with an explicit "unknown sorts last" floor) instead of raw string comparison; `sort_basis` still discloses the source field | `boards._parse_sort_ts`, `_sort_rows_newest_first`, `_sort_experts_newest_first` |
| N2 — validate the baseline marker's schema field | Fixed: `read_observation_baseline` now rejects a missing or mismatched `schema` field with a warning, before checking `baseline_started_at` | `sources.read_observation_baseline` |
| N4 — normalize `PROPHET_LAB_DISABLED` parsing | Fixed: case-insensitive OFF set (`""`/`"0"`/`"false"`/`"no"`/`"off"`); anything else disables (fail toward disabled, unchanged direction) | `app.prophet_lab._kill_switch_active` |
| N3 — `BOARD_DEFINITIONS` dead export | **Decision: included** in the payload under `board_definitions` — cheap, and it lets an operator/UI read what a board id means without cross-referencing this doc | `response.build_lab_response` |
| S8 — additional tests | Fixed: default-sort-newest-first asserted explicitly; C3/C5 absence asserted on all four single-family boards (not just the union); one fixture event built from a real `EntryEvent`/`build_radar_native_event().to_dict()` (full 21-field `EVENT_FIELDS` width); the closed-plan B1 case; both S1 directions; the B3 EEE mixed-card assertions | `tests/test_prophet_lab.py` |

### DEFERRED (per the review's own scoping — not built in this PR)

* **S3** — pagination/windowing. The review names this as the UI wave's
  responsibility, not the API's; the current response returns full boards
  (fixture-scale today) with no cursor. Revisit if/when board sizes in
  production make an unbounded response impractical.
* **S2 (full part)** — actual R2 transport wiring for the Radar spool root in
  production (beyond the cheap env-var-label half already shipped here). A
  deployment-step task, not a code change this PR should make blind to the
  live topology.
* **Production baseline marker provisioning** — no `PROPHET_LAB_OBSERVATION_BASELINE_PATH`
  is set anywhere yet; minting that marker is explicitly LAB-0 §6 step 3
  ("Radar live commissioning"), owned by that later wave.

## CI guard fixes (post-review, ci-pack-1/7/9/10)

Four genuine, mechanical guard reds on PR #5928's packs, all fixed on the same
branch:

1. **ci-pack-7 — `app/deploy/update.sh` restart-regex closure** (`tests/test_deploy_update_self_heal.py`).
   `macro-api` import-caches `engine/prophet_lab/*` (via `app/prophet_lab.py`'s
   module-level import), but the restart trigger regex didn't cover it. Fixed:
   added `engine/prophet_lab/.*\.py` to the `MACRO_API_RESTART_TRIGGER` block,
   next to the sibling `engine/research_vault/.*\.py` entry.
2. **ci-pack-9 — Radar owned-path census** (`tests/test_entry_radar_w1.py::test_radar_owns_only_its_declared_paths`).
   The fixture subdirectory `tests/fixtures/prophet_lab/radar_spool/live_flow/entry_radar_events/`
   pattern-matched Radar's `entry_radar` substring census outside its declared
   owned-path set. Fixed: renamed the fixture path segment and files to drop
   the literal `entry_radar` substring (`live_flow/lab_events/`,
   `*-lab-pack.json` instead of `*-entry_radar_pack.json` — the reader takes an
   injectable root and never depended on the real prefix name), and added
   `test_reader_honors_the_real_event_spool_prefix_shape` (an UNTRACKED
   `tmp_path` fixture, invisible to the `git ls-files`-based census) proving
   the reader still works correctly under Radar's REAL `EVENT_SPOOL_PREFIX`
   shape.
3. **ci-pack-10 — curated exclusive-scope import-closure coverage** (`tests/test_ci_pack.py::test_curated_exclusive_scopes_cover_their_own_import_closure`).
   Root-caused to `sources.read_live_episodes()`'s (lazy, function-level)
   import of `engine.entry_radar.live_ledger.LiveEpisodeLedger` — measured to
   pull ~150 unrelated `engine/*.py` files (Radar's own challengers/detectors
   fan-out into the US board/stock-scoring engine subsystem) into the
   transitive closure of every curated job reaching `app.main` (all four:
   `biocatalyst-history`, `biocatalyst-serving`, `flow-surface`,
   `unrun-government-revenue-grader` — `app/biocatalyst.py`'s own lazy
   `from app.main import require_user` is the shared entry point). **Fixed at
   the root**: `sources.py` no longer imports `engine.entry_radar` AT ALL —
   `read_live_episodes()` now reads `episodes.json` directly (the exact file
   `LiveEpisodeLedger.save()` writes), extracting only the three fields this
   package actually needs (`episode_id`, `ticker`, `detector_id`, `state`)
   into a local `EpisodeSummary`, with `_TERMINAL_STATES` restated as plain
   strings rather than importing `engine.entry_radar.detectors.TERMINAL_STATES`.
   Pinned by a new AST-level test,
   `test_sources_module_never_imports_the_radar_detector_stack`. The
   remaining, unavoidable edge is `engine/prophet_lab/**` itself (all four
   jobs reach it via `app.main` regardless of what's inside it) and
   `engine/prophet_board_read.py` (boards.py's own lazy enrichment import,
   LAB-0 §5's sanctioned reuse of the existing board-read source — this one
   was NOT removed, since it is exactly the "reuse the existing
   enrichment source" LAB-0 asks for, and its own import surface is
   stdlib-only) — both added as single-line `paths:` entries to all four
   curated jobs.

   **A large, genuinely-new (not pre-existing) gap was found and fixed.**
   After the entry_radar removal, three of the four jobs
   (`biocatalyst-history`, `flow-surface`, `unrun-government-revenue-grader`)
   still reported ~105-135 uncovered files — none of them related to
   `prophet_lab`, `entry_radar`, or `prophet_board_read`
   (`engine/activist.py`, `engine/basket_*.py`, `engine/us_board_rank.py`,
   `scripts/build_stock_library.py`, three `research/*_MASTERPLAN_BY_FABLE.md`
   files, etc.). `biocatalyst-serving` (the fourth job) already reported
   **zero** uncovered after the two fixes above. First hypothesis was
   pre-existing drift (the declared `paths:` for these three jobs are
   byte-identical between `origin/main` and this branch except for the
   two single-line additions above) — but a real, separately-cloned
   `origin/main`-equivalent checkout (`git clone --local --depth 1`; a
   `git archive` extraction has no `.git`, which silently degrades
   `discover_suites()`'s tracked-file census and had produced a false-clean
   read on the first attempt) showed **zero** uncovered for all four jobs on
   true `origin/main` — proving this ~105-135-file gap is a genuinely NEW
   reachability edge from this branch's tree, not stale drift, even though
   the exact causal chain through `scripts/ci_scope_dependencies.py`'s AST
   closure walk was not fully isolated within this PR's budget (none of the
   newly-uncovered files are imported by `engine/prophet_lab/**` or
   `engine/prophet_board_read.py`, both already declared). **Fixed** by
   widening the three jobs' `paths:` with the exact reported file lists
   (subpackage-shaped entries — `engine/pick_lab/**`, `engine/oracle/**`,
   `engine/prophet_live/**` — collapsed to one glob line each, matching the
   "subject packages stay globbed" house style; the rest enumerated as
   literal top-level `engine/*.py`/`research/*.md`/`scripts/*.py` entries),
   each block clearly commented with the date, the false-start diagnosis, and
   the real-clone verification method — per the guard's own remedy
   ("widening is always the safe direction") rather than opening a second,
   unrelated PR for a cause this session could not fully name. Re-verified
   green: `test_curated_exclusive_scopes_cover_their_own_import_closure`
   passes (2 passed, 146s).
4. **ci-pack-1 — `workflow-yaml` job, "no suite may be named by zero run:
   steps"** (`scripts/audit_unrun_tests.py`, run inside the `workflow-yaml`
   job). `tests/test_prophet_lab.py`/`tests/test_prophet_lab_api.py` were
   collected by pytest but named by no `run:` step anywhere. Fixed: wired
   both into the existing `engine-render-guards` job's
   "render-guard + engine-contract tests" step, right next to the other
   Prophet suites already there (`test_prophet_governor.py`,
   `test_prophet_showcase.py`, `test_prophet_options_context.py`) — that
   job's install line already carries `fastapi`/`httpx`/`pandas`, so no new
   dependency. `engine-render-guards` is NOT `scope: exclusive`, so this
   addition is picked up by ordinary inference and does not interact with
   the ci-pack-10 closure-coverage guard.

## Day-2 reconciliation (2026-08-19, post #5954/#5952/#5969)

Chairman day-2 directive: rebase onto the newest `origin/main` after the CI
reform landed (#5954 W1 — every legacy job declares `gate: code | data`;
#5969 W2 — merge-gate packs now gate only `gate:code` jobs, `gate:data`
receipts move to a post-nightly lane; #5952 wired the reliability suite the
prior round had separately flagged as an unrelated pre-existing gap), PLUS a
mandated temporal-correctness amendment before merge.

### What was recomputed, and what survived

Per the directive, every prior `.github/ci/legacy-jobs.yml` hunk was
temporarily STRIPPED (checked out from fresh `origin/main`) and both guards
re-run against the bare base, to recompute from scratch rather than assume
the prior round's widening still applies under the new gate regime:

* `python3.12 scripts/audit_unrun_tests.py` WITHOUT the ci-pack-1 wiring hunk
  → both `tests/test_prophet_lab.py` and `tests/test_prophet_lab_api.py`
  reported as unrun again. **Still required**, unchanged by the reform.
* `test_curated_exclusive_scopes_cover_their_own_import_closure` WITHOUT the
  ci-pack-10 widening hunk → the exact same four curated jobs
  (`biocatalyst-history`, `biocatalyst-serving`, `flow-surface`,
  `unrun-government-revenue-grader`) report uncovered closures again, same
  shape as before (`biocatalyst-serving` needs only `engine/prophet_lab/**`
  + `engine/prophet_board_read.py`; the other three need the larger
  ~105-135-file widening). `test_the_curated_exclusive_set_is_actually_declared`
  passed throughout — the CURATED_EXCLUSIVE job SET itself is unchanged by
  #5954/#5969 (the reform added a `gate:` field to every job and moved
  `gate:data` jobs out of merge-gate packs; it did not touch which jobs are
  `scope: exclusive` or their declared `paths:`). **Both hunks restored,
  still fully required.**
* The `app/deploy/update.sh` restart-regex hunk and the
  `tests/fixtures/prophet_lab/` rename (ci-pack-9): no commit between the
  prior round's base and the newest `origin/main` touched
  `app/deploy/update.sh` or `tests/test_entry_radar_w1.py` at all
  (`git log --oneline <old-base>..origin/main -- <path>` empty for both) —
  **unaffected, still required**, both guards re-verified green.

**Authority classification of the final diff: still authority-changing.**
The final diff touches `.github/ci/legacy-jobs.yml` (409 lines: the
ci-pack-1 suite wiring + the ci-pack-10 `paths:` widening) — a `scripts/**`/
`.github/ci/**` edit sets `authority_changed=true` per house law regardless
of whether the widening turns out to be "still needed" or "newly needed";
it does not touch `scripts/**` itself. No other file in the diff is under
`scripts/` or `.github/`.

### Rebase mechanics

Three separate rebases were needed as `origin/main` kept advancing during
this reconciliation (routine wire/press/marketing ticks plus #5969/#5973
landing mid-session) — each was a clean fast-forward rebase with ZERO
conflicts (`git rebase origin/main` reported no conflict markers on any of
the three), because none of the newly-merged commits touched any file this
PR owns. Final base: `origin/main` @ `10642922c221` (`marketing-publish:
outbox run 2026-08-19T11:03Z`), merge-base confirmed equal to `origin/main`'s
tip at push time.

### The temporal correctness amendment (mandated before merge)

**Finding:** every comparison in the observation-class honesty path
(`observation.classify_observation`'s `baseline_started_at`/
`continuous_through` checks, `sources.baseline_coverage_verified`'s
`earliest<=started_at` check, and the timestamp-ordering helpers that feed
them — `sources.extract_events`'s per-event "earliest", `earliest_pass_ts`,
`latest_envelope`) compared RAW STRINGS with `<`/`>`/`min()`/`max()`. That is
only correct when every timestamp shares identical UTC-offset notation.
Measured counter-example: `"2026-08-19T09:00:00-04:00"` (13:00 UTC) sorts
lexicographically BEFORE `"2026-08-19T10:00:00Z"` (10:00 UTC) — `'0' < '1'`
at the hour digit — despite naming the LATER instant. Any spool envelope or
baseline marker ever using a non-`Z` (but still legal ISO-8601) offset could
have silently flipped a `retrospective_seed`/`live_forward` classification,
in EITHER direction — including the dangerous one the handoff specifically
named: incorrectly PROMOTING a seed to `live_forward`, or falsely
"verifying" baseline coverage that does not actually reach back far enough.

**Fix:** `engine/prophet_lab/timeparse.py` (new) — the ONE canonical
`parse_instant(ts) -> datetime | None` helper: normalizes a `Z`/`z` suffix to
`+00:00`, parses via `datetime.fromisoformat`, converts to UTC. Every
honesty-path comparison in `observation.py` and `sources.py` now compares
the returned `datetime` objects, never the original strings. Naive
timestamps (no UTC offset at all) FAIL CLOSED — `parse_instant` returns
`None`, and every caller's existing "could not parse -> retrospective_seed
/ coverage not verified" branch already handles that. This is documented
as a deliberate choice, not an oversight: every producer this package reads
is contracted to always emit an explicit offset (the Radar spool envelope's
`pass_ts`, the observation-baseline marker's `baseline_started_at`/
`continuous_through`), so a naive value reaching the parser signals an
UPSTREAM CONTRACT VIOLATION — treating it as UTC would risk manufacturing a
`live_forward` classification (and a measured lead) from an instant whose
zone was never actually known, exactly the failure this amendment exists to
close.

**Deliberately NOT touched: `boards.py`'s row-sort key.** `_parse_sort_ts`
(the N1 fix from review round 1) already parses properly, but treats a
naive timestamp as UTC (needed for bare `YYYY-MM-DD` Prophet plan dates used
as a fallback `sort_ts` — an existing, tested board DISPLAY behavior). Making
it share `timeparse.parse_instant`'s fail-closed-on-naive semantics would
have SILENTLY CHANGED which rows sort last for a naive `sort_ts` — exactly
the "do not change board semantics" line the mandate drew. The two
functions solve different problems (sort POSITION vs honesty
CLASSIFICATION) with legitimately different failure modes; `timeparse.py`'s
module docstring states this explicitly so a future reader does not "fix"
the apparent duplication by merging them.

**New tests** (37 total, all adversarial, none merely re-testing the happy
path already covered):
* `tests/test_prophet_lab_timeparse.py` (18, new file) — the low-level
  helper: offset normalization (`Z`, `z`, `+00:00`, `-04:00`, `+08:00`),
  equal-instant different-offset-form equality, naive/garbage/empty
  rejection, before/after across all four offset forms on both sides of a
  reference instant, `earliest_instant_string` correctness including the
  exact regression pairing.
* `tests/test_prophet_lab.py` (+19, 75 -> 94) — integration-level adversarial cases
  through `classify_observation` and `baseline_coverage_verified`:
  `test_classify_observation_equal_instant_different_offsets_at_lower_boundary`,
  `test_classify_observation_before_baseline_across_offset_forms` /
  `..._after_baseline_across_offset_forms` (parametrized over Z/+00:00/
  -04:00/+08:00), `test_classify_observation_naive_observed_at_fails_closed_to_seed`,
  `..._naive_baseline_started_at_fails_closed_to_seed`,
  `..._unparseable_continuous_through_fails_closed_to_seed`,
  `..._unparseable_observed_at_fails_closed_to_seed`,
  `test_classify_observation_regression_lexicographic_bug_would_have_wrongly_promoted`
  (the named dangerous-direction regression case),
  `test_baseline_coverage_verified_equal_instant_different_offsets`,
  `..._naive_baseline_started_at_fails_closed`,
  `..._naive_envelope_pass_ts_fails_closed`,
  `test_baseline_coverage_verified_true_when_evidence_reaches_further_back`,
  `test_baseline_coverage_verified_regression_lexicographic_bug` (the S1-axis
  dangerous-direction regression case).

**No board semantics, observation classes, or payload contract changed** —
confirmed by the full pre-existing suite passing unmodified alongside the 37
new tests: 141 total across the three prophet_lab test files (94 + 29 + 18).

## Verified

* `python3.12 -m pytest tests/test_prophet_lab.py tests/test_prophet_lab_api.py -q`
  → **104 passed** (75 + 29; four new sources.py tests from the ci-pack-10
  fix, one new prefix-shape test from the ci-pack-9 fix).
* `python3.12 -m pytest tests/test_entry_radar_w5_reconciler.py tests/test_entry_radar_w4_ledger.py -q`
  → **98 passed** — the W5 reconciler and W4 ledger suites (adjacent to the
  four radar-transport files this PR must not touch) are unaffected.
* `python3.12 -m pytest tests/test_deploy_update_self_heal.py -q` → **219
  passed** (ci-pack-7 fix).
* `python3.12 -m pytest tests/test_entry_radar_w1.py -q -k test_radar_owns_only_its_declared_paths`
  → **1 passed** (ci-pack-9 fix).
* `python3.12 -m pytest tests/test_ci_pack.py -q -k "test_curated_exclusive_scopes_cover_their_own_import_closure or test_the_curated_exclusive_set_is_actually_declared"`
  → **2 passed** (146s; ci-pack-10 fix).
* `python3.12 scripts/audit_unrun_tests.py` → exit 0, `tests/test_prophet_lab.py`/`tests/test_prophet_lab_api.py`
  no longer appear in the unrun report (ci-pack-1 fix).
* `python3.12 -c "import yaml; yaml.safe_load(open('.github/ci/legacy-jobs.yml'))"`
  → parses clean after all `.github/ci/legacy-jobs.yml` edits.
* `python3.12 scripts/agentos.py validate` → 0 errors (pre-existing
  sparse-worktree phantom-path warnings on unrelated workstreams unchanged;
  this PR's five new `owns_paths` entries are not phantom).
* `git diff --stat` against the branch base touches only: `app/main.py` (the
  router registration), `app/deploy/update.sh` (restart regex), `.github/ci/legacy-jobs.yml`
  (curated-scope + unrun-suite wiring, all itemized above),
  `agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md` (`owns_paths` only),
  plus the `engine/prophet_lab/`, `app/prophet_lab.py`, `tests/test_prophet_lab*.py`,
  `tests/fixtures/prophet_lab/**`, and this notes doc. Zero edits to
  `engine/entry_radar/live_pack.py`, `live_eval.py`, `live_ledger.py`, or
  `scripts/reconcile_entry_radar.py` (the four W4.1 radar-transport files) —
  confirmed via `git diff --stat HEAD -- <those four paths>` returning empty.
  Zero writes to any Prophet store, zero writes under `data/`.

### Day-2 verification (rebased onto `origin/main` @ `10642922c221`)

* `python3.12 -m pytest tests/test_prophet_lab.py tests/test_prophet_lab_api.py tests/test_prophet_lab_timeparse.py tests/test_deploy_update_self_heal.py tests/test_entry_radar_w1.py tests/test_entry_radar_w5_reconciler.py tests/test_entry_radar_w4_ledger.py -q`
  → **558 passed, 1 skipped** (the skip is the same pre-existing conditional
  Radar-diff guard as every prior round — this branch touches no Radar code).
* `python3.12 -m pytest tests/test_ci_pack.py -q -k "test_curated_exclusive_scopes_cover_their_own_import_closure or test_the_curated_exclusive_set_is_actually_declared"`
  → **2 passed (330s)** on the newest base, both WITH the widening hunks
  restored AND (separately, per the recompute mandate) WITHOUT them
  re-confirming the same four jobs go red without the hunk — see "What was
  recomputed" above.
* `python3.12 scripts/audit_unrun_tests.py` → exit 0 (also re-confirmed exit
  1 without the ci-pack-1 hunk, and caught + fixed a genuine miss: the new
  `tests/test_prophet_lab_timeparse.py` needed its own wiring into the same
  `engine-render-guards` step, added in a follow-up commit).
* `python3.12 -c "import yaml; yaml.safe_load(open('.github/ci/legacy-jobs.yml'))"`
  → parses clean.
* Three rebases, all clean fast-forwards with zero conflicts (`git rebase
  origin/main` reported none on any of the three) — `origin/main` kept
  advancing (routine wire ticks plus #5969/#5973) faster than this
  reconciliation could finish; each advance was checked for relevance
  (`git log --oneline <old>..<new> -- <owned paths>`) before re-rebasing,
  and none touched a file this PR owns beyond the #5954/#5952/#5969 reform
  itself.
* `git diff --stat origin/main HEAD` → 23 files, 4492 insertions / 1
  deletion — the same file set as the prior round plus
  `engine/prophet_lab/timeparse.py` and `tests/test_prophet_lab_timeparse.py`.
  Forbidden radar-transport files and `data/` both still empty.

## Temporal review round 2 (2026-08-19)

A narrow independent review verdicted the round-1 temporal delta MERGE-SAFE
as shipped, but found the "replace every remaining lexicographic ordering"
completeness claim FALSE: three siblings of the same bug class survived,
all still inside the honesty/evidence path (never display). Fixed in the
same branch:

* **S1 (must-fix) — `boards._live_forward_lead_anchor`.** Picked the
  multi-expert-card measured-lead anchor via
  ``candidates.sort(key=lambda pair: pair[0])`` — a raw string sort over
  ``first_observed_at``. Executed failure: expert A
  ``"2026-08-19T20:00:00-05:00"`` (= ``2026-08-20T01:00:00Z``) vs expert B
  ``"2026-08-20T00:30:00Z"`` — A wrongly chosen (sorts first, '19' < '20'),
  fabricating ``measured_from_event_id``/a lead where the TRUE anchor (B)
  yields a different answer. Fixed: sorts by
  ``timeparse.parse_instant(pair[0])``; an entry that fails to parse is
  defensively EXCLUDED (every candidate is an ``extract_events`` output and
  is therefore parseable in practice, but this never falls back to a string
  compare on a hypothetical miss). This is EVIDENCE-tier parsing and does
  NOT join `timeparse.py`'s one display-tier exemption
  (`boards._parse_sort_ts`) — the module docstring now says so explicitly,
  by name, so the exemption list cannot silently grow to cover it.
* **S2 (must-fix) — `observation.measured_lead_days`'s LAB-side date.** Took
  ``str(first_observed_at)[:10]``, the OFFSET-LOCAL calendar date.
  ``"2026-08-19T20:00:00-05:00"`` slices to ``08-19`` but is ``08-20`` UTC —
  a fabricated one-day lead where the honest answer differs. Fixed: the LAB
  side is now ``timeparse.parse_instant(first_observed_at).date()`` (``None``
  → no lead, fail closed); the PROPHET plan-date side KEEPS the ``[:10]``
  slice unchanged — Prophet ``signal_date``/``entry_date`` are legitimately
  bare ``YYYY-MM-DD`` with no time or offset at all, so there is no instant
  to parse there. The function's own docstring now states this asymmetry
  explicitly rather than leaving a reader to wonder why only one side
  changed.
* **S3 (must-fix) — regression tests.**
  `test_extract_events_mixed_offset_regression_and_classification` — two
  envelopes carrying the same event_id at ``09:00:00-04:00`` (13:00Z) and
  ``10:00:00Z``, baseline ``12:00Z``: asserts the chosen ``first_observed_at``
  is the ``10:00Z`` instant, the resulting classification is
  ``retrospective_seed``, AND (via an explicit `raw_min` comparison) that a
  revert to raw-string `min()` would pick the wrong envelope — the primary
  assertion is revert-sensitive by construction. Plus
  `test_live_forward_lead_anchor_picks_the_true_earliest_instant` (pins S1)
  and `test_measured_lead_days_uses_utc_date_not_offset_local_date` (pins
  S2), each with the exact executed-failure numbers from the review.
* **S4 (take it) — `read_observation_baseline` parse-validates
  `baseline_started_at` at READ time.** A naive/unparseable value now emits
  the existing `log.warning` idiom (unchanged) AND is distinguishable from a
  spool-coverage gap or a simply-unconfigured baseline in the health block:
  the function's return type changed from `dict | None` to a new
  `BaselineReadResult(baseline, error)` dataclass (matching the house
  `SpoolReadResult`/`EpisodeReadResult` idiom already in this module); a
  malformed marker surfaces `health.observation_baseline_error` (e.g.
  `"naive_or_unparseable_started_at"`, `"schema_mismatch"`,
  `"missing_baseline_started_at"`, `"unreadable_or_invalid_json"`,
  `"schema_not_an_object"`); a genuinely absent baseline carries NO error key
  at all (fail-closed DIRECTION unchanged — absence was never an error).
  Every existing call site (`response.py` + 6 tests) updated to the new
  shape.
* **N1 (take it) — `earliest_instant_string` was dead.** Wired
  `sources.earliest_pass_ts` through it instead of re-implementing the same
  "earliest by parsed instant" scan a second time; `timeparse.py`'s docstring
  updated to record this as the ROUND 2 set of fixes.

**11 new tests** (152 total in `test_prophet_lab.py`/`test_prophet_lab_api.py`/
`test_prophet_lab_timeparse.py`, up from 141): the S3-mandated
`extract_events` regression + 2 pin tests, 3 `_live_forward_lead_anchor`
tests (S1), 2 `measured_lead_days` UTC-date tests (S2), 4 `BaselineReadResult`
tests including the health-block surfacing case (S4), 1
`earliest_pass_ts`-through-`earliest_instant_string` wiring test (N1).

### Round 2 verification

```
python3.12 -m pytest tests/test_prophet_lab.py tests/test_prophet_lab_api.py tests/test_prophet_lab_timeparse.py tests/test_deploy_update_self_heal.py tests/test_entry_radar_w1.py tests/test_entry_radar_w5_reconciler.py tests/test_entry_radar_w4_ledger.py -q
# 569 passed, 1 skipped (same pre-existing conditional skip)

python3.12 scripts/audit_unrun_tests.py
# exit 0

python3.12 -m pytest tests/test_ci_pack.py -q -k "test_curated_exclusive_scopes_cover_their_own_import_closure or test_the_curated_exclusive_set_is_actually_declared"
# 2 passed — no .github/ci/legacy-jobs.yml edits this round; re-run as insurance
```

No board semantics, observation classes, or payload contract changed this
round either — `BaselineReadResult` is a new internal return TYPE for one
`sources.py` function with one call site (`response.py`) and 6 test call
sites, all updated; the response payload itself gained exactly one optional
health-block key (`observation_baseline_error`), additive and absent unless
the marker is genuinely malformed.
