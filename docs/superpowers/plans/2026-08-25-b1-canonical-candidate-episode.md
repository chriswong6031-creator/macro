# B1 Canonical Candidate Episode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the canonical append-only `prophet.candidate_episode/v1` registry, its
uncapped All Candidates projection, and one natural-nightly writer without creating a second
candidate lifecycle.

**Architecture:** A pure episode event/state module owns deterministic IDs, corrections,
replay, and the canonical reader. TURN WATCH exposes the full uncapped source rows through a
private input sidecar, and one nightly-only reconciler resolves Data OS identity, maps every
registered input to an episode relation or suppression, then atomically derives projections
from the immutable event ledger.

**Tech Stack:** Python 3.12, stdlib dataclasses/hashlib/json/tempfile, pandas/pyarrow for
existing Parquet stores, pytest, GitHub Actions YAML, Agent OS records.

**Spec:** `docs/superpowers/plans/2026-08-25-b1-canonical-candidate-episode-design.md`

## Global Constraints

- The exact episode schema is `prophet.candidate_episode/v1`; the immutable event schema is
  `prophet.candidate_episode_event/v1`.
- `episode_id = pe:<security_id>:<identity_epoch>:<structural_anchor>:<generation>`;
  expert identity is never part of the ID.
- `security_id` and the value in frozen `company_id` are exact Data OS `SEC:` and `ISS:` IDs.
- `identity_epoch="epoch_0"` is allowed only with `identity_epoch_state="provisional"`, the
  Stock Identity spec schema, and its exact `spec_hash()`.
- Radar attaches by exact `mastermind.entry_event.v1.event_id`; the ephemeral Radar runtime
  episode identifier remains separate.
- TURN WATCH's exact reset-low anchor is the only natural episode opener in B1. Candidate,
  Door, and unanchored Radar inputs may attach to an active episode or are suppressed.
- All registered inputs map or produce an enumerated suppression. No producer cap and no
  silent orphaning.
- The immutable ledgers in the generation named by atomic `HEAD.json` are truth.
  `current.parquet` and `all_candidates.json` in that same immutable generation are derived
  only by replaying them; canonical readers never select an unreferenced generation.
- Corrections, retractions, state transitions, re-arms, and identity supersession append
  events; no raw event is overwritten and no last-write-wins logic is permitted.
- Durable writes require both `--nightly` and
  `engine.ledger_lane.nightly_advance_enabled()` before any source/ledger read. Replay and
  off-lane modes write nothing.
- No change may grant rank, gate, size, plan, origination, Availability, grading, Radar,
  Stock Identity, graph, or V3 authority.
- Do not edit existing files below omitted sparse roots `data/`, `site/`, `mockups/`, or
  `verify_shots/`. Tests use `tmp_path`; natural production artifacts are created after merge.
- Use `apply_patch` for edits; stage exact files only; never use `git add -A` or `git add .`.
- Each task is test-first: observe the named failure before production implementation, then
  commit only after its focused tests pass.

---

### Task 1: Pure episode event model, lifecycle replay, corrections, and canonical reader

**Files:**
- Create: `engine/us_candidate_episode.py`
- Create: `tests/test_us_candidate_episode.py`
- Create: `tests/fixtures/us_candidate_episode/all_candidates.json`

**Interfaces:**
- Consumes: Data OS-formatted identity strings and already-normalized observation mappings.
- Produces:
  - `canonical_json(value: object) -> str`
  - `canonical_anchor(anchor: Mapping[str, object]) -> dict[str, object]`
  - `anchor_token(anchor: Mapping[str, object]) -> str`
  - `episode_id(security_id: str, identity_epoch: str, anchor: Mapping[str, object], generation: int) -> str`
  - `make_event(..., recorded_at: str) -> dict[str, object]`
  - `validate_events(events: Sequence[Mapping[str, object]]) -> list[dict[str, object]]`
  - `project_events(events: Sequence[Mapping[str, object]]) -> list[dict[str, object]]`
  - `reconcile_observations(events, observations, *, recorded_at, definition_era) -> ReconcileResult`
  - `apply_commands(events, commands, *, recorded_at, definition_era) -> ReconcileResult`
  - `build_all_candidates(events, *, suppression_count) -> dict[str, object]`
  - `load_all_candidates(path: Path) -> list[dict[str, object]]`
  - frozen dataclasses `ReconcileResult(events, new_events, suppressions, episodes)` and
    `EpisodeContractError`.

- [ ] **Step 1: Write the failing contract and event-identity tests**

Add tests that import the interfaces above and assert:

```python
anchor = {
    "kind": "turn_watch_reset_low",
    "time": "2026-08-24T20:00:00Z",
    "price": 42.1,
    "basis": "adjusted_close",
    "source_receipt": "sha256:receipt-a",
}
assert anchor_token(anchor) == anchor_token({**anchor, "source_receipt": "sha256:receipt-b"})
assert episode_id("SEC:US-XNAS-XYZ", "epoch_0", anchor, 1).startswith(
    "pe:SEC:US-XNAS-XYZ:epoch_0:sa:"
)
```

Assert invalid `SEC:`/`ISS:` IDs, naive timestamps, non-positive generation, missing anchor
fields, NaN/non-finite prices, and unknown event types raise `EpisodeContractError`.

- [ ] **Step 2: Run the focused import test and record the expected red**

Run:

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/test_us_candidate_episode.py -q
```

Expected: collection fails because `engine.us_candidate_episode` does not exist.

- [ ] **Step 3: Implement canonicalization, IDs, event envelopes, and validation**

Use canonical UTF-8 JSON (`sort_keys=True`, `separators=(",", ":")`, `allow_nan=False`).
Normalize prices with `Decimal(str(value)).normalize()` and serialize them as strings in the
anchor. Normalize all timestamps to RFC3339 UTC with a literal `Z`. Generate:

```python
semantic = {
    "event_type": event_type,
    "episode_id": episode_id,
    "source_system": source_system,
    "source_schema": source_schema,
    "source_event_id": source_event_id,
    "occurred_at": occurred_at,
    "known_at": known_at,
    "definition_era": definition_era,
    "correction_of": correction_of,
    "payload": payload,
}
event_id = "pee:" + sha256(canonical_json(semantic).encode()).hexdigest()
```

Then calculate `content_sha256` over the complete envelope excluding only
`content_sha256`. Validate `occurred_at <= known_at <= recorded_at`, except that an explicitly
identified delayed receipt may have `known_at < recorded_at`; it must never have
`known_at > recorded_at`.

- [ ] **Step 4: Write failing state-machine tests**

Construct normalized observations for one security and assert:

- first valid anchor opens generation 1;
- the next night's equivalent anchor preserves the episode ID and creates one idempotent
  `OBSERVED` event;
- two equivalent expert events attach to the same episode;
- a different anchor while active emits `ACTIVE_EPISODE_DIFFERENT_ANCHOR` and no episode;
- `STATE_TRANSITIONED` to `RESOLVED` plus a new anchor opens generation 2 with `rearm_of`;
- the same ticker may therefore have two sequential IDs, never two active IDs;
- unanchored input without an active episode emits `MISSING_STRUCTURAL_ANCHOR`;
- exact same inputs on rerun add zero events and return byte-identical projections.

- [ ] **Step 5: Implement reconciliation and event replay minimally**

Use deterministic order `(known_at, source_system, source_event_id)`. `OPENED.payload`
contains the entire frozen current-row seed plus provisional identity provenance.
`OBSERVED.payload` contains the intake class and observation/source relationship.
`EXPERT_EVENT_ATTACHED.payload.expert_event_id` must equal the exact source Radar event ID.
Projection replay de-duplicates/sorts list fields and rejects two active episodes for the same
`(security_id, identity_epoch)`.

- [ ] **Step 6: Write failing correction, retraction, supersession, and consumer tests**

Assert:

- `CORRECTED` references an existing event and applies only its explicit `patch` to the
  projection, sets `correction_state="corrected"`, and preserves original event bytes;
- `RETRACTED` references an existing relation/open event and deterministically removes its
  effect without deleting the original;
- `IDENTITY_SUPERSEDED` links a provisional episode to a different successor ID and sets
  `superseded_by` in the old current row;
- an unknown correction target fails closed;
- `build_all_candidates` is uncapped and includes terminal rows;
- the fixture at `tests/fixtures/us_candidate_episode/all_candidates.json` loads only through
  `load_all_candidates`, rejects duplicate episode IDs, and returns canonical order.

- [ ] **Step 7: Implement immutable command events and canonical All Candidates reader**

Allow correction patches only for the frozen/provenance projection fields; reject any patch
that changes `episode_id`, `security_id`, `identity_epoch`, or structural-anchor identity.
Require retraction/supersession reason and source receipt. The loader validates schema,
definition era, `SEC:`/`ISS:` identity, episode-id prefix, duplicate IDs, and ordering.

- [ ] **Step 8: Run focused tests and commit**

Run:

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/test_us_candidate_episode.py -q
git diff --check
```

Then stage exactly the three Task 1 files and commit:

```bash
git add engine/us_candidate_episode.py tests/test_us_candidate_episode.py tests/fixtures/us_candidate_episode/all_candidates.json
git commit -m "feat(prophet): add canonical candidate episode model"
```

---

### Task 2: Uncapped TURN WATCH source sidecar and Data OS intake normalization

**Files:**
- Modify: `engine/us_turn_watch.py`
- Modify: `scripts/build_turn_watch.py`
- Create: `engine/us_candidate_episode_intake.py`
- Create: `tests/test_us_candidate_episode_intake.py`
- Modify: `tests/test_us_turn_watch.py`

**Interfaces:**
- Consumes Task 1 `canonical_json`, `anchor_token`, and normalized observation contract.
- Produces:
  - `engine.us_turn_watch.compute_deck_with_candidates(...) -> tuple[dict, list[dict]]`
  - `scripts.build_turn_watch.write_candidate_episode_input(artifact, rows, data_root) -> Path`
  - `load_identity_spine(data_root: Path) -> IdentitySpine`
  - `turn_watch_observations(path: Path, spine: IdentitySpine) -> IntakeBatch`
  - `candidate_observations(data_root: Path, spine: IdentitySpine) -> IntakeBatch`
  - `door_observations(path: Path, spine: IdentitySpine) -> IntakeBatch`
  - `radar_observations(path: Path, spine: IdentitySpine) -> IntakeBatch`
  - frozen `IdentitySpine`, `IntakeBatch(observations, suppressions, source_receipts)`.

- [ ] **Step 1: Add the failing TURN WATCH seam test**

Using synthetic close series, assert `compute_deck_with_candidates` returns the unchanged
public artifact plus every full triggered row, including rows beyond the display cap. Assert
the public artifact still contains only reduced `beyond_cap` entries and never contains an
`all_triggered`/private full-row field.

- [ ] **Step 2: Run the focused seam test and record the expected red**

Run:

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/test_us_turn_watch.py -q
```

Expected: the new `compute_deck_with_candidates` import/assertion fails.

- [ ] **Step 3: Refactor TURN WATCH without recomputing the deck**

Move the existing `compute_deck` body into `compute_deck_with_candidates`; return
`(artifact, rows)` where `rows` is the already-sorted uncapped list. Keep `compute_deck` as a
compatibility wrapper returning only `artifact`. Update `build_turn_watch` to call the new
function once, preserve the existing site write, and write:

```text
data/us_prophet_rank/episode_inputs/turn_watch/<data_session>.json
```

The sidecar schema is `prophet.candidate_episode_input.turn_watch/v1`. Include all full rows,
`data_session`, selection/anchor eras, trigger registry, deterministic `known_at` derived from
`session_window_et(data_session)[1]` in UTC, `source_artifact_sha256`, and a canonical
`content_sha256`. Use temp-file + fsync + `os.replace`; do not put the full rows in `site/`.

- [ ] **Step 4: Write failing identity and anchor-normalizer tests**

Under `tmp_path/data/reference`, write synthetic `vendor_aliases.parquet` and
`security_master.parquet`. Prove:

- membership symbol resolves on observation date to exact `SEC:` and current exact `ISS:`;
- provisional epoch fields and real `spec_hash()` are present;
- TURN WATCH reset-low anchor time uses the NYSE close, including a known 13:00 ET early
  close, and `opened_at=max(trigger_close,anchor_close)`;
- missing/unevaluated trigger, reset low, alias, issuer, or malformed receipt yields the exact
  suppression enum;
- historical/replay input without pinned identity yields `HISTORICAL_IDENTITY_UNPROVEN`;
- current candidate, Door, and unanchored Radar observations do not open an episode;
- Radar's exact `event_id` is preserved as `expert_event_id` and its runtime episode ID is
  provenance only;
- every source row appears exactly once across normalized observations and suppressions.

- [ ] **Step 5: Implement source-specific normalizers**

Read only these canonical source shapes:

- TURN WATCH sidecar `prophet.candidate_episode_input.turn_watch/v1`;
- monthly `data/us_prophet_rank/candidates/*.parquet` current-session rows;
- `data/prophet_doors/flags.jsonl`;
- `data/entry_radar/forward.parquet` exact `event_id` rows.

Normalizers must not import or call producer-private ranking/gating functions. Source event IDs
are deterministic from producer keys/receipts; missing source files produce named degraded
source receipts, not fabricated empty-success claims.

- [ ] **Step 6: Run focused and adjacent tests and commit**

Run:

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/test_us_candidate_episode_intake.py tests/test_us_turn_watch.py -q
/opt/homebrew/bin/python3.12 -m pytest tests/test_entry_radar_events.py tests/test_us_candidate_lanes.py tests/test_stock_identity_fingerprint.py -q
git diff --check
```

Stage exactly the five Task 2 files and commit:

```bash
git add engine/us_turn_watch.py scripts/build_turn_watch.py engine/us_candidate_episode_intake.py tests/test_us_candidate_episode_intake.py tests/test_us_turn_watch.py
git commit -m "feat(prophet): expose uncapped episode intake"
```

---

### Task 3: Nightly-only atomic ledger writer and downstream projection proof

**Files:**
- Create: `scripts/reconcile_us_candidate_episodes.py`
- Create: `tests/test_us_candidate_episode_reconciler.py`
- Create: `tests/fixtures/us_candidate_episode/intake/turn_watch.json`
- Create: `tests/fixtures/us_candidate_episode/intake/vendor_aliases.json`
- Create: `tests/fixtures/us_candidate_episode/intake/security_master.json`

**Interfaces:**
- Consumes Task 1 event/projector APIs and Task 2 intake batch APIs.
- Produces:
  - `reconcile(*, repo_root: Path, nightly: bool, replay: bool, recorded_at: str | None,
    correction_path: Path | None) -> dict[str, object]`
  - CLI `python -m scripts.reconcile_us_candidate_episodes [--nightly] [--replay]
    [--recorded-at RFC3339] [--corrections PATH] [--repo-root PATH]`.

- [ ] **Step 1: Write failing gate and zero-write tests**

Monkeypatch source-reader functions to raise if called. Assert a durable request without
`--nightly`, or without `COLLECT_LANE=nightly`, raises/refuses before the patched reader is
called. Snapshot the entire temp tree and prove `--replay` and dry-run modes change zero bytes.

- [ ] **Step 2: Run the gate tests and record the expected red**

Run:

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/test_us_candidate_episode_reconciler.py -q
```

Expected: collection fails because the reconciler does not exist.

- [ ] **Step 3: Implement read/validate/reconcile without writes**

Load existing monthly event/suppression ledgers, validate every row, load all registered
intakes, reconcile deterministically, and build the receipt/projections in memory. In replay
or report mode return the receipt with `durable_write=false`; do not create directories.

- [ ] **Step 4: Write failing atomicity, correction, and idempotence tests**

Prove:

- a natural fixture writes one `OPENED` event, projections, and exact receipt;
- a repeat with identical sources changes zero file bytes and creates no event;
- a changed current observation appends one `OBSERVED`, not a new episode;
- explicit correction JSONL appends `CORRECTED` and preserves the original ledger line;
- a forced failure before the atomic HEAD swap leaves the prior HEAD/generation canonical;
- a forced failure after a generation is completely installed but before the HEAD swap leaves
  only an unreferenced generation, which the canonical reader cannot observe;
- first publication exposes no generation until HEAD exists, and a reader sees either the
  entire old generation or the entire new generation, never a mixed set;
- corrupt existing event hash aborts every output;
- output monthly ledgers are canonical newline-delimited JSON sorted by event address;
- `current.parquet` and `all_candidates.json` rederive to identical logical rows;
- downstream fixture reads only `load_all_candidates`;
- every input count equals mapped plus suppressed and no cap exists.

- [ ] **Step 5: Implement immutable-generation publication with one atomic HEAD swap**

Stage the complete prospective generation under
`data/us_prophet_rank/episodes/generations/`, fsync file contents and directories, validate
every staged byte and all cross-target invariants, then install the immutable generation under
its content-addressed `generation_id`. Publish it with one atomic temp+fsync+`os.replace` of
`data/us_prophet_rank/episodes/HEAD.json`. Canonical readers resolve and validate HEAD, and
must refuse an absent/malformed pointer or an unreferenced generation. Compare the complete
generation hash first: identical inputs reuse the existing generation and touch zero bytes.
Failure before the pointer swap leaves the old HEAD canonical; failure after the swap exposes
the already-complete generation, so no preimage rollback protocol or sequential target rename
is permitted.

The receipt schema is `prophet.candidate_episode_reconcile_receipt/v1` with exact source
hashes, gate/mode, definition era, input/mapped/suppressed counts, old/new event counts,
ledger hash, and projection hashes.

- [ ] **Step 6: Run focused tests, CLI smoke, and commit**

Run:

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/test_us_candidate_episode.py tests/test_us_candidate_episode_intake.py tests/test_us_candidate_episode_reconciler.py -q
COLLECT_LANE=nightly /opt/homebrew/bin/python3.12 -m scripts.reconcile_us_candidate_episodes --replay --repo-root tests/fixtures/us_candidate_episode
git diff --check
```

Stage exactly Task 3 files and commit:

```bash
git add scripts/reconcile_us_candidate_episodes.py tests/test_us_candidate_episode_reconciler.py tests/fixtures/us_candidate_episode/intake/turn_watch.json tests/fixtures/us_candidate_episode/intake/vendor_aliases.json tests/fixtures/us_candidate_episode/intake/security_master.json
git commit -m "feat(prophet): add nightly candidate episode reconciler"
```

---

### Task 4: Workflow, registry, CI ownership, and governed B1 delivery record

**Files:**
- Modify: `.github/workflows/daily.yml`
- Modify: `.github/ci/legacy-jobs.yml`
- Modify: `config/dataset_registry.yml`
- Create: `tests/test_us_candidate_episode_wiring.py`
- Create: `agentos/decisions/DEC-PROPHET-B1-CANONICAL-EPISODE-BINDINGS.md`
- Modify: `agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md`
- Modify: `research/prophet_v4/CAPABILITY_LEDGER.md`
- Create: `agentos/handoffs/PROPHET-US-V4-RECOVERY-2026-08-25-b1-built.md`

**Interfaces:**
- Consumes all Task 1-3 code and exact output paths.
- Produces a single natural-nightly B1 writer, explicit CI ownership, registered datasets, and
  an honest `BUILT_PENDING_NATURAL_ACCEPTANCE` record. D5 remains blocked.

- [ ] **Step 1: Write failing static wiring tests**

Assert from parsed/text workflow sources:

- `us_prophet_ledgers` runs `scripts.reconcile_us_candidate_episodes --nightly` after Doors
  and before grades/W3;
- its job retains `COLLECT_LANE: nightly`;
- the exact commit allowlist includes `data/us_prophet_rank/episodes` and does not broaden to
  `git add data/us_prophet_rank`;
- the engine TURN WATCH step remains before `us_prophet_ledgers` and its broad data commit
  owns the private sidecar;
- `prophet-us-context-and-grades` runs every B1 test file;
- the dataset registry contains every B1 input/output path, schema, owner, clock, and PIT law;
- no workflow dispatch/replay path invokes durable B1 writing;
- no source under Radar, plan selection, board ranking, Availability, or V3 imports B1 as
  authority.

- [ ] **Step 2: Run the wiring test and record the expected red**

Run:

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/test_us_candidate_episode_wiring.py -q
```

Expected: workflow, CI owner, and registry assertions fail.

- [ ] **Step 3: Wire the one nightly writer and exact commit owner**

Add a named B1 step to `us_prophet_ledgers`. Its non-zero exit is a genuine job failure; do
not add `continue-on-error` or `|| true`. Add only:

```bash
git add data/us_prophet_rank/episodes 2>/dev/null || true
```

to that job's exact staging list. Add the four B1 test files to the existing
`prophet-us-context-and-grades` pytest step or a sibling step in that same job.

- [ ] **Step 4: Register datasets and record the four rulings**

Register the TURN WATCH input sidecar, event ledger, suppression ledger, current projection,
All Candidates projection, and reconciliation receipt in `config/dataset_registry.yml`.
Create one Agent OS decision recording R1-R5 from the design spec, their alternatives, exact
source evidence, and reconsideration conditions. Update the workstream to mark B1
`in_progress`/`BUILT_PENDING_NATURAL_ACCEPTANCE`, add its owned paths, keep D5 `todo`, and name
the natural scheduled run as the next action. Update capability row 30 to the same bounded
status. The handoff must state that build/merge is not natural acceptance and must prohibit a
manual replay/rerun as substitute.

- [ ] **Step 5: Run focused, adjacent, structural, and pack validation**

Run:

```bash
/opt/homebrew/bin/python3.12 -m pytest tests/test_us_candidate_episode.py tests/test_us_candidate_episode_intake.py tests/test_us_candidate_episode_reconciler.py tests/test_us_candidate_episode_wiring.py tests/test_us_turn_watch.py -q
/opt/homebrew/bin/python3.12 -m pytest tests/test_us_context_vector.py tests/test_us_candidate_lanes.py tests/test_entry_radar_events.py tests/test_stock_identity_fingerprint.py tests/test_prophet_pit_replay.py -q
/opt/homebrew/bin/python3.12 -m pytest tests/test_prophet_off_engine_lane.py tests/test_dataos_registry.py -q
python3 scripts/agentos.py validate
python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --pack-index <resolve-with-validate-only> --pack-count 12 --validate-only
git diff --check
```

For sparse-only failures caused by absent `data/` or `site/`, rerun the exact synthetic/unit
subset and report the omitted-tree reason; do not interpret a missing tracked data artifact as
a B1 code failure and do not materialize/write an omitted tree without explicit need.

- [ ] **Step 6: Commit the integration and records**

Stage exactly the eight Task 4 files and commit:

```bash
git add .github/workflows/daily.yml .github/ci/legacy-jobs.yml config/dataset_registry.yml tests/test_us_candidate_episode_wiring.py agentos/decisions/DEC-PROPHET-B1-CANONICAL-EPISODE-BINDINGS.md agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md research/prophet_v4/CAPABILITY_LEDGER.md agentos/handoffs/PROPHET-US-V4-RECOVERY-2026-08-25-b1-built.md
git commit -m "ci(prophet): deliver B1 candidate episode lane"
```

---

### Task 5: Whole-branch verification and merge-ready evidence packet

**Files:**
- Modify only if final review finds a load-bearing defect; use one reviewed fix wave.

**Interfaces:**
- Consumes the complete branch diff and every task report/review.
- Produces a merge-ready B1 source SHA and exact pre-natural evidence packet.

- [ ] **Step 1: Re-pin current main and collision state**

Fetch `origin/main`, inspect PR #6275 and every open PR touching B1 paths, then compare the
branch against current main. Fast-forward or merge only when disjoint and safe; never reset,
rebase away foreign work, or overwrite the frozen D5 contract carrier.

- [ ] **Step 2: Run the complete verification matrix**

Run every focused/adjacent command from Task 4, resolve the actual owning CI pack, run the
pack locally, run `git diff --check`, inspect exact changed files, and prove no tracked
`data/`, `site/`, Radar, V3, board, plan, or generated Agent OS view changed.

- [ ] **Step 3: Final whole-branch review**

Generate a review package from the branch merge-base through `HEAD` and dispatch the most
capable reviewer. If findings exist, use exactly one fix subagent and one scoped re-review.
No load-bearing finding may be silently deferred.

- [ ] **Step 4: Push, open PR, wait for concluded checks, merge, and verify main**

Push the exact head, open the PR, arm `merge-on-green`, stay through all genuine checks,
resolve genuine failures, and verify the squash commit on `origin/main`. The designed
inactive-base merge-queue-pilot negative control is interpreted only from its machine receipt.
Do not claim natural B1 acceptance yet.

- [ ] **Step 5: Wait for natural B1 acceptance before D5 runtime**

Observe the next scheduled authoritative daily descendant of the B1 merge. Do not dispatch,
rerun, replay, or cancel it. Return an acceptance packet proving the exact natural sidecar,
episode ledger, current projection, All Candidates projection, source/output hashes,
idempotence/duplicate checks, workflow job conclusions, and canonical-reader output. Ship a
small records-only acceptance PR that marks B1 `done` and releases D5. Only after that merge
may the D5 runtime plan begin.
