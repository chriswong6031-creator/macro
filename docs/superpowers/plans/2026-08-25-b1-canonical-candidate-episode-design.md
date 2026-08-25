# B1 Canonical Candidate Episode Design

**Status:** Chairman-ratified implementation design for V4-B1
**Authority:** the direct 2026-08-25 Chairman commission, the B1 build-pack handoff,
`research/prophet_v4/ARCHITECTURE_FREEZE.md`, and
`research/prophet_v4/PROPHET_US_V4_RECOVERY_AND_INTELLIGENCE_GRAPH_OS_MASTERPLAN_BY_SOL_2026-08-17.md`
**Dependency:** A1 accepted by PR #6399; B1 may execute. D5 runtime remains blocked until
B1 is accepted from a natural nightly receipt.

## 1. Outcome

Build one durable `prophet.candidate_episode/v1` plane at the grain frozen by the V4
architecture:

> one Data OS security identity epoch x one structural anchor x one lifecycle; many expert
> events; many candidate observations; zero-or-one active plan lineage.

The immutable event ledger is the sole source of episode history. `current.parquet` and
`all_candidates.json` are deterministic projections rebuilt from that ledger. Existing
candidate snapshots, TURN WATCH, Doors, Entry Radar, plan ledgers, board ledgers, graders,
and V3 remain separate owners and are consumed read-only.

## 2. Binding non-goals

- No `(ticker,date)` identity and no expert identifier in `episode_id`.
- No aliasing of `mastermind.live_entry_episode.v1` to a B1 episode.
- No alternate board, candidate snapshot, plan, origination, Availability, ranking, sizing,
  grading, identity, Radar, or graph authority.
- No historical first-surface timestamp unless an actual source receipt proves one.
- No backfill from present-day issuer state. Natural B1 production admission is current and
  prospective.
- No producer cap. Every registered source observation is mapped to an episode relation or
  produces an enumerated suppression.
- No B2/B3/B4 lifecycle or Availability expansion. B1 carries only the frozen episode-state
  field and explicit lifecycle references required to identify and correct an episode.
- No direct writes during replay, intraday, weekly, or ad-hoc execution.
- No edits to Radar-owned event or runtime-ledger code.

## 3. Ratified B1 rulings

### R1 — exact identity values

The frozen field names remain `security_id` and `company_id`. Their values are consumed
without translation from the Data OS identity spine:

- `security_id = SEC:<listing-key>`
- `company_id = ISS:<issuer-key>`

The misleading `co:` example in the masterplan is not an authority to mint a Prophet company
identifier. `company_id` is a schema-name compatibility field whose value is the exact Data OS
`issuer_id`.

Natural intake resolves the observation-date membership symbol through
`VendorAliasTable.resolve("membership", ticker, on=session_date)` and then reads the current
issuer through `IssuerMaster.issuer_of_security(security_id)`. A historical/replay intake is
admitted only when its identity was pinned in the input receipt; it may not project current
issuer state backward.

### R2 — provisional identity epoch and supersession

Until Stock Identity W4 ships a behavioral epoch detector, B1 consumes the current canonical
fingerprint contract exactly:

- `identity_epoch = "epoch_0"`
- `identity_epoch_state = "provisional"`
- `identity_spec_schema = "stock_identity.fingerprint_spec.v1"`
- `identity_spec_hash = engine.stock_identity.fingerprint.spec_hash()`

`epoch_0` is never represented as final. When a real epoch is later available, the ledger
appends `IDENTITY_SUPERSEDED`; it never edits the provisional episode or recycles its ID. The
derived current view may point to the successor while the old episode stays auditable.

### R3 — direct Radar relationship

Radar expert relations use the exact content-addressed `mastermind.entry_event.v1.event_id`.
The B1 ledger stores it in `expert_events` and in the immutable source relation. B1 does not
reconstruct the lossy `(ticker, detector_id, signal_ts)` triple and does not use Radar's
ephemeral runtime `episode_id` as a B1 identifier.

A Radar event without a structural anchor may attach to an already-active B1 episode for the
same resolved security. If no active episode exists, it is suppressed as
`MISSING_STRUCTURAL_ANCHOR`; B1 never guesses an anchor.

### R4 — structural anchor owner

B1 owns canonicalization, not discovery, of structural anchors supplied by registered
intakes. For this wave the only source allowed to open a natural episode is the full uncapped
TURN WATCH candidate row:

```json
{
  "kind": "turn_watch_reset_low",
  "time": "<NYSE close in UTC for reset.reset_low_date>",
  "price": "<decimal-normalized reset.reset_low>",
  "basis": "adjusted_close",
  "source_receipt": "sha256:<TURN WATCH input-sidecar digest>"
}
```

The canonical anchor token is `sa:<first-24-hex-of-sha256(canonical-anchor-json)>`. The
source receipt is provenance but is excluded from anchor equivalence so a byte-identical
anchor observed in a later receipt still attaches to the same episode. Equivalence is exact
on `kind`, UTC `time`, normalized decimal `price`, and `basis`; there is no price tolerance,
fuzzy date, ticker fallback, or writer-clock fallback.

The episode can open only when at least one fired TURN WATCH trigger is evaluated and has a
lawful `last_date`, and `reset_low` plus `reset_low_date` are non-null. `opened_at` is the
later of the structural-anchor session close and the earliest qualifying trigger session
close. That is the earliest point when all opening predicates were knowable from the EOD
tape. `opened_session` is its NYSE date.

Existing candidate-store and Door rows do not carry a complete structural anchor. They may
attach `OBSERVED` relations to an active episode after exact identity resolution; otherwise
they are suppressed as `MISSING_STRUCTURAL_ANCHOR`. Door R is not a re-arm authority in B1.

### R5 — deterministic event identity and clocks

Every event has schema `prophet.candidate_episode_event/v1`. Its `event_id` is a SHA-256
address over this semantic identity tuple:

```text
(event_type, episode_id, source_system, source_schema, source_event_id,
 occurred_at, known_at, definition_era, correction_of, canonical payload)
```

`recorded_at` is retained as a factual materialization clock but does not create a new
semantic event. If an event with the same semantic address already exists, a later rerun is a
no-op and retains the original bytes. If the address collides with different semantic bytes,
the writer fails closed.

Clock meanings:

- `occurred_at`: source-domain event time.
- `known_at`: earliest PIT time the opening/relationship fact was knowable.
- `recorded_at`: actual nightly materialization time, supplied by the writer.
- `opened_at`: earliest PIT time all opening predicates were knowable.
- `first_surface_at`: nullable and absent from the required B1 projection unless proven by a
  separate source receipt.

Replay may read and produce a dry-run receipt. It never advances the durable ledger and never
changes any clock.

## 4. Data contracts

### 4.1 Immutable event envelope

Required fields:

```json
{
  "schema": "prophet.candidate_episode_event/v1",
  "event_id": "pee:<sha256>",
  "episode_id": "pe:<security>:<epoch>:<anchor>:<generation>",
  "event_type": "OPENED|OBSERVED|EXPERT_EVENT_ATTACHED|STATE_TRANSITIONED|REARM_SUPPRESSED|CORRECTED|RETRACTED|IDENTITY_SUPERSEDED",
  "occurred_at": "RFC3339 UTC",
  "known_at": "RFC3339 UTC",
  "recorded_at": "RFC3339 UTC",
  "source_system": "closed producer identifier",
  "source_schema": "versioned source schema",
  "source_event_id": "stable source address",
  "source_receipt": "path or sha256 receipt",
  "definition_era": "candidate-episode-v1-2026-08-25",
  "correction_of": null,
  "payload": {},
  "content_sha256": "sha256 over all preceding canonical fields"
}
```

Raw events are never overwritten or deleted. `CORRECTED`, `RETRACTED`, and
`IDENTITY_SUPERSEDED` append new events that reference earlier immutable state.

### 4.2 Current episode projection

Each current row preserves the frozen fields:

```text
schema, episode_id, security_id, company_id, ticker_at_observation,
identity_epoch, opened_at, opened_session, intake_classes,
structural_anchor, expert_events, episode_state, terminal_reason,
rearm_of, definition_era, created_by, correction_state
```

B1 adds provenance-only fields:

```text
identity_epoch_state, identity_spec_schema, identity_spec_hash,
observation_count, last_observed_at, source_event_ids, superseded_by
```

Rows sort by `(opened_at, episode_id)`. Lists are sorted and de-duplicated. JSON values in
Parquet are canonical JSON strings so the schema cannot drift with nested inference.

### 4.3 All Candidates projection

`all_candidates.json` is:

```json
{
  "schema": "prophet.all_candidates/v1",
  "definition_era": "candidate-episode-v1-2026-08-25",
  "generated_from": {"event_count": 0, "ledger_sha256": "..."},
  "coverage": {"episodes": 0, "active": 0, "suppressed_inputs": 0},
  "episodes": []
}
```

It is uncapped and contains every non-retracted episode, including terminal episodes. It is a
machine projection, not a rank, gate, or UI lane.

### 4.4 Suppression ledger

Every unmapped registered input produces an idempotent
`prophet.candidate_episode_suppression/v1` row with a content-addressed `suppression_id`,
source identity, observation session, ticker, resolved security when available, and one closed
reason:

```text
MISSING_STRUCTURAL_ANCHOR
IDENTITY_UNRESOLVED
ISSUER_UNRESOLVED
HISTORICAL_IDENTITY_UNPROVEN
ACTIVE_EPISODE_DIFFERENT_ANCHOR
NO_EVALUATED_TRIGGER
INVALID_STRUCTURAL_ANCHOR
REARM_REQUIRES_TERMINAL_STATE
SOURCE_SCHEMA_UNSUPPORTED
SOURCE_RECEIPT_INVALID
```

Suppression is evidence, not an episode and not a market verdict.

## 5. Stores and ownership

```text
data/us_prophet_rank/episode_inputs/turn_watch/YYYY-MM-DD.json
data/us_prophet_rank/episodes/HEAD.json
data/us_prophet_rank/episodes/generations/<generation_id>/events/YYYY-MM.jsonl
data/us_prophet_rank/episodes/generations/<generation_id>/suppressions/YYYY-MM.jsonl
data/us_prophet_rank/episodes/generations/<generation_id>/current.parquet
data/us_prophet_rank/episodes/generations/<generation_id>/all_candidates.json
data/us_prophet_rank/episodes/generations/<generation_id>/latest_receipt.json
```

- TURN WATCH owns the input sidecar and writes it once in the existing engine job from the
  same in-memory uncapped rows used to build the capped display artifact.
- B1 owns everything below `data/us_prophet_rank/episodes/`.
- The event and suppression ledgers inside the generation named by `HEAD.json` are truth. All
  other B1 files are projections/receipts. A generation directory is immutable after it becomes
  visible.
- Production data files are created only by a natural nightly after code merges; sparse build
  worktrees do not author or truncate tracked `data/` artifacts.

## 6. Reconciliation algorithm

1. Refuse durable mode unless both `--nightly` and
   `engine.ledger_lane.nightly_advance_enabled()` are true. This check runs before any source
   or ledger read.
2. Load the immutable ledger and validate every event hash, schema, enum, clock ordering,
   source address, and episode-id derivation. Fail closed on corrupt truth.
3. Derive current state solely by replaying the ledger in deterministic `(known_at,event_id)`
   order.
4. Load the latest TURN WATCH sidecar, current candidate snapshot, Doors flags, and Radar
   forward rows through source-specific normalizers. A missing optional source yields a named
   suppression/receipt degradation; it never manufactures an empty-success claim.
5. Resolve identity through Data OS. Historical input without pinned identity is refused.
6. For each canonical observation in `(known_at, source_system, source_event_id)` order:
   - attach to an equivalent active episode;
   - open generation 1 when a valid anchor exists and no active episode exists;
   - after a terminal episode, open the next generation only for a new valid anchor and set
     `rearm_of`;
   - suppress an alternate anchor while an episode is active;
   - attach Radar by exact `event_id`; or
   - emit an enumerated suppression.
7. Apply explicit correction commands as immutable events. A command refers to an existing
   event/episode and carries a deterministic source address. Corrections never use
   last-write-wins.
8. Merge by content address. Existing identical semantic addresses are no-ops.
9. Build all projections from the merged ledger.
10. Stage one complete immutable generation under `generations/`, fsync and validate every
    byte plus every cross-target invariant, then atomically replace `HEAD.json` as the single
    visibility boundary. A crash before the pointer swap leaves the old generation canonical;
    a crash after it exposes the already-complete new generation. An orphan staged/generation
    directory is never readable without a matching valid HEAD. Unchanged inputs reuse the
    existing generation and do not rewrite HEAD or any target byte.
11. Emit a receipt with exact once-read source hashes, input/mapped/suppressed counts, old/new event
    counts, projection hashes, gate/mode, and definition era.

### 6.1 Atomic publication amendment (2026-08-25 review ruling)

The earlier draft described sequential `os.replace` calls over top-level output files. That
cannot be crash-atomic: a process or machine death between renames exposes a split generation.
The immutable-generation plus atomic-HEAD layout above supersedes that wording. Canonical
readers resolve and validate `HEAD.json` before opening a generation; direct reconstruction or
selection of an unreferenced generation is forbidden. First publication may create empty
container directories, but no generation is current until the single HEAD swap succeeds.

## 7. TURN WATCH seam

`engine.us_turn_watch` exposes a new result that contains both:

- the existing public capped artifact, byte/contract compatible; and
- the full sorted triggered rows used by B1.

`scripts.build_turn_watch` calls the engine once, writes the existing public JSON unchanged,
then writes a deterministic private input sidecar containing every full triggered row. The
sidecar includes the data session, selection/anchor eras, trigger registry, source artifact
hash, and an input content hash. It carries no rank/gate/size/origination authority.

The public `site/turn_watch/turn_watch.json` must not gain the uncapped full rows.

## 8. Read path

`engine.us_candidate_episode.load_all_candidates(path)` is the sole B1 downstream reader. It
validates `prophet.all_candidates/v1`, rejects duplicates and malformed identity/episode IDs,
and returns rows in canonical order. The downstream fixture reads this function; it does not
reconstruct episodes from TURN WATCH, Doors, Radar, or ticker/date snapshots.

## 9. Workflow and CI

- The engine job's existing TURN WATCH step writes the input sidecar; the existing broad
  engine `git add data/` lands it.
- `us_prophet_ledgers` runs `python -m scripts.reconcile_us_candidate_episodes --nightly`
  after Doors and before grades/W3.
- Its commit allowlist adds exactly `data/us_prophet_rank/episodes`; it does not broaden to
  all `data/us_prophet_rank/`.
- B1 suites join the existing `prophet-us-context-and-grades` CI owner so contract-delta sees
  the new tests and source paths.
- Registry entries declare all six source/output datasets, schemas, owners, clocks, PIT law,
  and failure behavior.

## 10. Acceptance

Pre-merge synthetic proof must demonstrate:

1. a current TURN WATCH row opens a `SEC:`/`ISS:` episode with pinned provisional epoch;
2. repeated appearance preserves ID and adds only one observation relation;
3. the same ticker has two sequential episodes only after terminal state plus a new anchor,
   with different IDs and `rearm_of`;
4. equivalent experts attach to one episode and Radar uses exact `event_id`;
5. every registered input maps or emits an enumerated suppression, without a cap;
6. correction/retraction append new bytes and deterministically change only the projection;
7. replay and off-lane attempts write nothing;
8. same-input rerun is byte-stable;
9. canonical downstream loader consumes the All Candidates fixture;
10. V3 board/population and plan-selection artifacts remain byte-unchanged.

Post-merge acceptance requires a natural scheduled nightly at a main descendant of the B1
merge, with:

- a lawful current episode in committed outputs;
- engine sidecar production and B1 ledger advancement both successful;
- exact input/output hashes and no duplicate episode/event/source identities;
- private/current downstream read proof if a protected reader exists; otherwise exact
  committed canonical-loader proof and an explicit statement that no separate private B1
  reader exists yet;
- no replay, manual dispatch, rerun, or fabricated surface clock.

Only that packet may mark B1 accepted and release D5 runtime.
