# Actor, Liquidity & Monthly Transition Clock — W1 Design

Date: 2026-09-03  
Status: **DESIGN ACCEPTED / IMPLEMENTATION NOT STARTED**  
Parent architecture: `docs/superpowers/specs/2026-09-03-policy-transmission-preturn-command-design.md`  
Canonical implementation carrier: GitHub issue #6787  
Operation key: `policy-preturn-actor-liquidity-calendar-clock-20260903-sol-001`  
Protected Sol procedure at freeze: `mastermindx-market-intelligence/Mastermind@793e75639911f21dae9c90a77c3a5dbf4b37cbb0`, Skillpack 1.0.1, bootstrap major 1 compatible.  
Macro design base: `931870b1feccb91b5122d92b07995e9749566aae`.

## 1. One useful vertical

This wave builds one independently useful capability:

> Before a scheduled policy/liquidity event or a monthly market-structure transition, one deterministic machine artifact and one visible Policy Watch composition tell the user what support is present, what is expiring, what event can override it, what is unknown, and what observations confirm or invalidate the proposed transition.

The wave is successful only when this journey works with current official sources and current Macro inputs:

```text
official source observations
+ canonical event/OPEX/options/rebalance/TGA owners
+ quarterly futures-roll context
              |
              v
      policy_turn_clock.v1
              |
       +------+-------+
       |              |
Policy Watch UI   machine consumer
       |
prospective receipt frozen before a real event/window
```

The vertical is deterministic and useful without any LLM. It is display/context authority only. It never ranks, gates, sizes or originates a trade.

## 2. Scope and path ceiling

### 2.1 Source and computation paths

The implementation may create or modify only these source paths unless a same-carrier Sol ruling changes the ceiling before `START`:

```text
collectors/policy_event_clock.py
engine/futures_roll_calendar.py
engine/policy_turn_clock.py
engine/event_calendar.py
scripts/build_policy_turn_clock.py
scripts/build_policy_watch.py
templates/partials/_policy_turn_clock.html.j2
templates/policy_watch.html.j2
tests/test_policy_event_clock.py
tests/test_futures_roll_calendar.py
tests/test_policy_turn_clock.py
tests/test_build_policy_turn_clock.py
tests/test_policy_watch_ui.py
config/dag.yml
.github/workflows/whitehouse-sentinel.yml
.github/workflows/ci.yml
```

Generated or evidence paths owned by this wave:

```text
data/policy_events/official_events.parquet
data/policy_events/collector_status.json
data/policy_turn_clock/forward_log.jsonl
site/policy_turn_clock.json
site/policy_watch.html
mockups/refs/policy-turn-clock/**
```

Generated artifacts are not hand-edited. A worker may add one `.gitkeep` only when the repository’s existing tracked-directory convention requires it; that addition must be declared before commit and remain inside the same evidence directory.

### 2.2 Protected/no-edit paths

This operation must not edit:

```text
engine/yield_momentum.py
engine/rates_inflation_command.py
scripts/build_rates_command.py
.github/ci/legacy-jobs.yml
agentos/workstreams/WS-RATES-INFLATION-COMMAND.md
```

The first four are bound by RIC F3 PR #6721 and its current CI-manifest collision with PR #6658. The workstream record is separately owned by open PR #6593. Any discovered need to touch a protected path is `DECISION_REQUEST / PATH_CEILING`, not permission to widen.

### 2.3 Explicit non-goals

This wave does not build:

- yield-cause decomposition;
- cross-asset contradiction resolution;
- model-generated speech interpretation;
- regional-Fed, BOJ/MOF, White House, State, Energy or Iran source breadth beyond records already consumed through existing canonical owners;
- a private-location inference system;
- a new event database, scheduler, queue, watcher, lifecycle or notification transport;
- a new options, market-data, release, TGA, rebalancing or futures-price store;
- a universal turn-of-month or post-OPEX directional signal;
- Prophet integration, portfolio ranking, entry timing, sizing or execution.

Regional and international source breadth is PTC-W2. Yield/cross-asset work is PTC-W3 and remains gated on canonical reconciliation of PR #6721.

## 3. Canonical inputs

### 3.1 Existing owners consumed unchanged

| Input | Canonical owner | W1 use |
|---|---|---|
| Upcoming CPI/PPI/NFP/GDP/PCE/FOMC/claims/ISM/OPEX/Treasury auctions | `engine/event_calendar.py` | exact scheduled catalysts |
| Event collision/window context | `engine/event_window.py` | optional current context; no duplicate statistics |
| OPEX phase | `engine/opex.py` | `td_to_opex`, `td_since_opex`, `in_opex_week`, quad-cycle context |
| Dealer surface | `engine/options_surface.py` aggregates | support inventory and replacement-book evidence |
| OPEX holdability | `engine/opex_risk.py` | pin, concentration, dealer-load and vanna/charm context |
| Rebalance calendar | `engine/rebalance_calendar.py` | month-/quarter-end, Russell and S&P windows |
| Rebalance observation | `engine/rebalance_pulse.py` | absorbed/distributed/mixed mechanical volume |
| TGA/net-liquidity | `engine/treasury_watch.py` and current liquidity artifacts | mechanical liquidity state |
| Release truth/corrections | existing Macro Release Intelligence | released/revised state when available |
| Official hourly transport | `.github/workflows/whitehouse-sentinel.yml` | reuse schedule and commit lane; no new scheduler |
| PIT append contract | `collectors/_first_seen_store.py` | keep-FIRST official-event vintages |

Every consumer carries the owner’s units, clocks, caveats and null semantics. This wave does not normalize away disagreement between owners.

### 3.2 First-wave official sources

The official-source collector is deliberately bounded to sources needed for the first complete journey:

1. **Federal Reserve Board** public calendar and speech/event pages for Board members and the Chair.
2. **U.S. Treasury** press releases and event/statement pages for the Secretary and named Treasury officials when the official source provides an explicit event, speech or location.
3. **TreasuryDirect** buyback operation schedule and results in machine-readable XML/CSV when available.
4. Existing TreasuryDirect upcoming-auction owner through `engine/event_calendar.py`; do not refetch or duplicate its auction truth.
5. Existing TGA owner through `engine/treasury_watch.py`; do not create a second TGA collector.

A source not in this list appears in `gaps[]` rather than being silently scraped from media. The collector may ingest a source-discovered official canonical URL, but it must not broaden into an unbounded web crawler.

## 4. Official-event evidence contract

### 4.1 Store

Canonical W1 event evidence is accrued at:

```text
data/policy_events/official_events.parquet
```

It uses the existing `collectors._first_seen_store.accrue_keep_first` contract. A present-but-unreadable store aborts the append and remains untouched. Writes use the existing atomic sibling/replace discipline.

The immutable evidence identity is:

```text
(source_key, source_event_id, source_revision)
```

The first observed bytes for one identity win. A correction or cancellation creates a new `source_revision`; it never replaces the prior row. The current projection selects the latest valid revision by `available_at`, then `observed_at`, then stable digest ordering.

### 4.2 Row schema

Each row contains exactly these logical fields; physical nullable types follow existing parquet conventions:

```text
schema_version              int = 1
source_key                  string
source_event_id             string
source_revision             string
record_kind                 actor_event | treasury_operation
actor_id                    string | null
actor_name                  string | null
actor_role                  string | null
organization                string
operation_kind              auction | buyback | cash_management | speech | interview |
                            meeting | testimony | release | settlement | other
headline                    string
summary                     string | null
scheduled_start             offset-aware ISO timestamp | null
scheduled_end               offset-aware ISO timestamp | null
status                      scheduled | active | completed | revised | cancelled | unknown
location_label              string | null
location_precision          venue | city | country | unknown
announced_max_usd_bn        float | null
submitted_usd_bn            float | null
accepted_usd_bn             float | null
instrument_scope            string | null
settlement_date             ISO date | null
source_url                  string
source_published_at         offset-aware ISO timestamp | null
observed_at                 offset-aware ISO timestamp
available_at                offset-aware ISO timestamp
first_seen                  offset-aware ISO timestamp
content_sha256              lowercase hex
supersedes_revision         string | null
evidence_class              FACT | INFERENCE | PRIOR | THEORY
rights_class                official_public
parser_version              string
null_reason                 string | null
```

Money is USD billions. Source-native amounts are converted only when the unit is explicit. An absent amount remains null; it is never coerced to zero.

### 4.3 Collector status

`data/policy_events/collector_status.json` is an overwrite status artifact, not an event store. It contains per-source:

```json
{
  "schema": "policy_event_collector_status.v1",
  "generated_at": "offset-aware timestamp",
  "sources": {
    "fed_board": {
      "last_attempt_at": "...",
      "last_success_at": "...",
      "status": "healthy|partial|failed|never_succeeded",
      "records_seen": 0,
      "records_added": 0,
      "http_status": null,
      "error_code": null,
      "error_summary": null
    }
  }
}
```

A quiet fetch with zero new records can be healthy. An HTTP or parser failure is not “no events.”

### 4.4 Collector interfaces

`collectors/policy_event_clock.py` exposes pure parser seams and one bounded I/O entry point:

```python
@dataclass(frozen=True)
class CollectionResult:
    rows_seen: int
    rows_added: int
    status: dict[str, object]
    gaps: tuple[str, ...]


def normalize_fed_board_event(
    raw: Mapping[str, object], *, observed_at: datetime
) -> dict[str, object] | None: ...


def normalize_treasury_event(
    raw: Mapping[str, object], *, observed_at: datetime
) -> dict[str, object] | None: ...


def normalize_buyback_record(
    raw: Mapping[str, object], *, observed_at: datetime
) -> dict[str, object] | None: ...


def current_records(
    rows: Sequence[Mapping[str, object]], *, now: datetime
) -> list[dict[str, object]]: ...


def collect(
    *, now: datetime, session: requests.Session | None = None,
    root: Path | None = None
) -> CollectionResult: ...
```

All public datetime inputs must be timezone-aware. A naive datetime raises `ValueError` in pure seams and is converted into a typed collector failure at the CLI boundary.

### 4.5 Actor location law

The current actor view is computed, never stored as a second fact:

```python
def actor_presence(
    records: Sequence[Mapping[str, object]], *, actor_id: str, now: datetime
) -> dict[str, object]: ...
```

Rules:

1. `current_location` is non-null only when a latest valid official record has `scheduled_start <= now <= scheduled_end` and location precision is not `unknown`.
2. An event without an end time uses a source-kind-specific bounded window declared in code and tests: two hours for a speech/interview/testimony; calendar day only for an explicitly all-day meeting; never indefinite.
3. After the supported window, move the label to `last_verified_location` and set `current_location_status="unknown"`.
4. A cancelled event never supports current location.
5. Multiple overlapping official records produce `current_location_status="conflicting"`, both receipts and a gap; the composer must not pick one silently.

## 5. Futures-roll helper

### 5.1 Ownership boundary

`engine/futures_roll_calendar.py` is a pure schedule/progress helper consumed by the canonical event view. It is not a second event calendar and does not collect futures prices or open interest.

### 5.2 Interfaces

```python
def equity_roll_window(d: date) -> dict[str, object]: ...

def treasury_roll_window(d: date) -> dict[str, object]: ...

def snapshot(
    asof: date, *, live_progress: Mapping[str, object] | None = None
) -> dict[str, object]: ...
```

Output:

```json
{
  "schema": "futures_roll_calendar.v1",
  "as_of": "YYYY-MM-DD",
  "equity_index": {
    "status": "not_applicable|scheduled|active|completed|unknown",
    "lead_contract": "...",
    "next_contract": "...",
    "roll_start": "YYYY-MM-DD|null",
    "expiry": "YYYY-MM-DD|null",
    "progress": null,
    "progress_basis": "not_provided|volume|open_interest|both"
  },
  "treasury": {"status": "..."},
  "authority": {"can_rank": false, "can_gate": false, "can_size": false, "can_trade": false}
}
```

Rules:

- Major equity-index and U.S. Treasury futures rolls are quarterly: March, June, September and December.
- An ordinary month returns `not_applicable`, not `quiet` and not `unknown`.
- A quarterly date inside the declared roll window but without live progress is `scheduled`, never `active`.
- `active` requires valid same-window volume/open-interest progress supplied by an existing owner or explicit input.
- A contract-symbol mapping is deterministic and tested across year boundaries.
- Holiday-adjusted expiry uses the repository’s accepted market calendar where available; any fallback is labeled.

## 6. Canonical event-calendar extension

`engine/event_calendar.py` remains the single upcoming-event view. Add:

```python
def policy_turn_events(
    today: date | None = None,
    horizon_days: int = 14,
    *,
    official_records: Sequence[Mapping[str, object]] | None = None,
    futures_roll: Mapping[str, object] | None = None,
) -> list[dict[str, object]]: ...
```

The function:

1. starts with `us_macro_events(...)` rather than rebuilding its rows;
2. appends latest valid official actor/Treasury-operation records inside the horizon;
3. appends futures-roll window rows only when applicable;
4. deduplicates exact owner-equivalent rows by stable event identity while preserving source disagreement;
5. sorts by offset-aware scheduled time where available;
6. marks every row context-only;
7. leaves existing `us_macro_events`, `high_impact_strip` and current consumers behaviorally unchanged except for backward-compatible fields explicitly tested.

An official record that revises an existing static event may annotate it but cannot silently replace the canonical release owner. Contradictory official records remain two rows plus `conflict_group`.

## 7. Monthly transition composer

### 7.1 Pure interface

`engine/policy_turn_clock.py` contains no network, filesystem, model or ledger I/O:

```python
def compose(
    *,
    now: datetime,
    events: Sequence[Mapping[str, object]],
    opex: Mapping[str, object] | None,
    opex_risk: Mapping[str, object] | None,
    option_surface: Sequence[Mapping[str, object]] | None,
    rebalance_calendar: Mapping[str, object] | None,
    rebalance_pulse: Mapping[str, object] | None,
    treasury: Mapping[str, object] | None,
    futures_roll: Mapping[str, object] | None,
    prior_clock: Mapping[str, object] | None = None,
) -> dict[str, object]: ...
```

`now` must be offset-aware. Input order must not affect output or digest.

### 7.2 Output contract

```json
{
  "schema": "policy_turn_clock.v1",
  "as_of": "YYYY-MM-DD",
  "generated_at": "offset-aware timestamp",
  "evidence_cutoff": "offset-aware timestamp",
  "state": "SUPPORT_BUILDING|SUPPORT_STABLE|PINNED|SUPPORT_ROLLOFF_IMMINENT|VOLATILITY_WINDOW_OPEN|MONTH_END_REBALANCE_DOMINANT|CATALYST_DOMINANT|MIXED|UNKNOWN",
  "state_basis": [
    {"predicate": "string", "value": true, "source": "owner", "as_of": "..."}
  ],
  "change_from_prior": {
    "changed": true,
    "prior_state": "...|null",
    "changed_axes": []
  },
  "calendar": {},
  "actor_clock": {},
  "treasury_liquidity": {},
  "option_support": {},
  "futures_roll": {},
  "rebalance": {},
  "catalysts": [],
  "confirmation": [],
  "invalidation": [],
  "gaps": [],
  "freshness": {},
  "authority": {"can_rank": false, "can_gate": false, "can_size": false, "can_trade": false}
}
```

No score, probability, target, size, order, recommendation or hidden scalar authority is permitted.

### 7.3 Independent axes

The composer first derives independent states:

#### Calendar

- OPEX phase and business-day distance;
- post-OPEX window;
- month-/quarter-end window;
- applicable futures-roll windows;
- catalyst collision count and next high-impact event.

#### Option support

```text
status:
  stabilizing
  destabilizing
  transition
  unavailable
  stale
  ambiguous
```

Inputs include current gamma regime, pin proximity, front-seven-day concentration, dealer-load magnitude, vanna relief/drag and replacement-book evidence. The dealer-sign passport and vanna symmetry caveat are always present.

#### Replacement book

Replacement evidence is derived only when the same canonical option-surface owner supplies comparable prior and current observations with availability clocks. Candidate fields:

- change in `fm_oi_frac`;
- change in `fm_gex_bn` and `bk_gex_bn`;
- post-expiry front-week reset;
- freshness and root-class match.

Output:

```text
building | present | weak | absent | unknown | incomparable
```

Missing surface data produces `unknown`, never “no replacement.”

#### Treasury liquidity

```text
supportive | draining | mixed | neutral | unavailable | stale
```

The state exposes TGA episode, net-liquidity context, upcoming/observed buyback and auction/settlement details separately. Announcement maximum and accepted amount never share one field.

#### Rebalance

Uses calendar eligibility and `rebalance_pulse.class`. A calendar date without an observed pulse is `scheduled_unconfirmed`; it cannot become dominant.

#### Catalyst

High-impact event dominance requires a valid scheduled event inside 24 hours or an active/released official event plus at least one mechanism-specific collision (OPEX, auction/settlement, futures roll, or event-window evidence). Event proximity alone adds context but cannot change position authority.

### 7.4 State precedence

State is the glance-level summary over axes. Apply this deterministic order:

1. **`UNKNOWN`** when no valid current calendar plus at least two of the three core mechanism families—options, Treasury liquidity, rebalance/catalyst—are available, or when a required current timestamp is stale beyond its owner budget.
2. **`CATALYST_DOMINANT`** when a valid high-impact event is inside 24 hours and a collision/override predicate is true.
3. **`MONTH_END_REBALANCE_DOMINANT`** when a valid late-month/quarter-end window and an observed non-quiet rebalance pulse are present, unless a catalyst is dominant.
4. **`VOLATILITY_WINDOW_OPEN`** only when stabilizing support was previously observed, has rolled off, and at least one independent realized confirmation is supplied by existing owners. In W1, when the required independent confirmation is unavailable, stop at `SUPPORT_ROLLOFF_IMMINENT`; never invent a volatility-open state from the date.
5. **`SUPPORT_ROLLOFF_IMMINENT`** when expiry is at most two business days away or occurred within one business day, stabilizing/pinning inventory is present or recently observed, and replacement-book evidence is weak/unknown.
6. **`PINNED`** when long-gamma context, valid pin proximity and compressed-range context are all present, with no higher-precedence override.
7. **`SUPPORT_BUILDING`** when replacement-book evidence is `building` and Treasury/rebalance/catalyst axes do not contradict it.
8. **`SUPPORT_STABLE`** when stabilizing support is current and no higher-precedence override exists.
9. **`MIXED`** otherwise.

Every selected state must list exact predicates in `state_basis`. A worker may refine threshold names only by preserving these semantic gates and recording the numeric values in code/tests; no unreviewed weighted score is allowed.

### 7.5 Confirmation and invalidation

The composer emits observable conditions, not advice. W1’s deterministic library includes:

- support confirmation: replacement book builds, stable long-gamma/pin context, supportive TGA/liquidity, absorbed rebalance pulse, catalyst passes without adverse realized response;
- rolloff confirmation: support inventory falls after expiry plus existing owner reports volatility/breadth/credit deterioration;
- invalidation of rolloff: replacement book rebuilds, short-gamma expiration removes destabilizing inventory, or realized tape remains absorbed;
- catalyst invalidation: cancellation/revision, event passes without expected mechanism, or owner freshness fails;
- month-end invalidation: no observed mechanical pulse or pulse classified quiet.

The text is produced from a frozen bilingual phrase registry; no LLM is needed.

## 8. Builder and evidence ledger

### 8.1 Builder

`scripts/build_policy_turn_clock.py` owns bounded I/O and exposes:

```python
def gather_inputs(*, root: Path, now: datetime) -> dict[str, object]: ...

def build_payload(*, root: Path, now: datetime) -> dict[str, object]: ...

def write_payload(payload: Mapping[str, object], *, root: Path) -> Path: ...

def main(argv: Sequence[str] | None = None) -> int: ...
```

It reads the current official-event store/status and canonical owner artifacts. It never performs network I/O. Collector and builder remain separately testable.

The artifact is written atomically to:

```text
site/policy_turn_clock.json
```

The JSON is deterministic for fixed inputs except `generated_at`; tests inject the clock. The builder always writes a schema-shaped artifact, including `UNKNOWN`, rather than disappearing.

### 8.2 Forward receipt

On the existing nightly ledger lane only, the builder appends one keep-FIRST prospective receipt when:

- the glance state changes materially; or
- a high-impact event enters 24 hours; or
- OPEX enters T−2; or
- post-OPEX enters T+1; or
- a month-/quarter-end observed pulse first appears.

Path:

```text
data/policy_turn_clock/forward_log.jsonl
```

Identity:

```text
(as_of, trigger_kind, trigger_id, method_version)
```

The original receipt is immutable. A correction can create a linked correction row but cannot rewrite the original evidence cutoff. W1 records rulers but does not claim a mature track record:

- warning lead time to realized transition;
- realized 1d/5d volatility versus trailing regime;
- max adverse/favorable path over 5d and 10d;
- mechanism correctness;
- state persistence;
- false alarm/miss classification when maturity arrives.

Backfilled descriptive studies and prospective receipts never share one badge.

## 9. Policy Watch product composition

### 9.1 Builder integration

`scripts/build_policy_watch.py` reads `site/policy_turn_clock.json` defensively and passes `turn_clock` to the template. It does not recompute or reinterpret the contract.

### 9.2 Partial

`templates/partials/_policy_turn_clock.html.j2` owns one focused component. `templates/policy_watch.html.j2` includes it near the top decision layer.

### 9.3 Required glance hierarchy

1. **Now** — state, what changed, and one plain-language mechanism sentence.
2. **Support inventory** — present, building, expiring or unknown; includes OPEX/futures/month-end phase.
3. **Next 72 hours** — at most five highest-information official events/operations with exact ET time, status, actor, amount where applicable and source freshness.
4. **Confirm / invalidate** — at most three concise conditions each.
5. **Coverage** — stale/unavailable/conflicting source chips; always visible when nonempty.
6. **Evidence detail** — expandable receipts, source links, exact clocks, dealer-sign/OI caveats and raw axes.

The UI must not show “bullish,” “bearish,” “buy,” “sell,” position sizes or a master score. `SUPPORT_BUILDING` describes observed market structure, not a recommendation.

### 9.4 Responsive and bilingual requirements

- 1440, 768 and 390 CSS-pixel viewports;
- dark and light themes;
- English and Simplified Chinese;
- no clipped event times, amounts or source-status labels;
- state meaning cannot rely on color alone;
- Chinese market-direction colors follow the existing house convention where direction is actually displayed;
- unknown/stale/cancelled/conflicting states get first-class layouts, not empty gaps;
- evidence detail remains keyboard-accessible.

Browser receipts live under `mockups/refs/policy-turn-clock/` and are evidence only, not a new product asset plane.

## 10. Existing scheduler and workflow integration

### 10.1 No new scheduler

Reuse `.github/workflows/whitehouse-sentinel.yml` for the official-source poll. The existing hourly cron is best-effort, not exact real-time.

The workflow sequence is:

```text
collect official policy-event records
→ build policy_turn_clock.json
→ rebuild policy_watch.html
→ run focused validation
→ commit only changed owned data/site/status paths
```

A quiet hour creates no commit. A collector failure updates the status artifact and rebuilds the UI to show the gap without erasing last good event evidence.

Nightly remains the sole advancer of the forward ledger. The hourly lane must set/retain the existing environment that makes `engine.ledger_lane.nightly_advance_enabled()` false.

### 10.2 DAG and CI

`config/dag.yml` registers collector, builder and consumer in the existing pipeline vocabulary. `.github/workflows/ci.yml` adds the exact focused tests/paths without editing `.github/ci/legacy-jobs.yml`.

The worker must run the repository’s DAG conformance tests and ensure the live workflow and DAG declaration agree. No new required check or merge authority is created.

## 11. Failure behavior

The following behaviors are binding:

| Failure | Required result |
|---|---|
| Official page unavailable | preserve prior evidence, mark source failed/stale, expose gap |
| Markup changed | typed parser failure; never reinterpret random text |
| Duplicate publication | zero new evidence rows, stable current view |
| Revision/cancellation | append new vintage; current view projects latest valid revision |
| Actor role ambiguity | record null/ambiguous role and gap; no guessed identity |
| Location window expired | current unknown, last verified retained |
| Overlapping locations | conflicting, both receipts retained |
| Naive datetime/DST ambiguity | fail pure seam; typed collector error at CLI |
| Event passed but source still scheduled | status conflict exposed; no silent completion |
| Buyback max confused with accepted amount | contract/test failure |
| TGA stale | Treasury axis stale, not neutral |
| Ordinary month | futures roll `not_applicable` |
| Quarterly roll without progress | `scheduled`, not `active` |
| Options surface absent | option axis unavailable; no inferred support absence |
| Wrong root class or incomparable observations | replacement book `incomparable` |
| Dealer-sign caveat missing | contract/test failure |
| Positive support expires without confirmation | rolloff imminent, not volatility-open |
| Short-gamma expires | no automatic volatility-rise conclusion |
| Rebalance date without observed pulse | scheduled-unconfirmed, not dominant |
| Contradictory axes | `MIXED` plus disagreement list |
| Fixed-input rerun changes semantics | determinism test failure |
| Output stale | stale badge and gap; never current-looking |
| Score/rank/gate/size/trade field appears | static/contract test failure |
| Path collision | stop before edit with exact competing owner |

## 12. Acceptance tests

### 12.1 Hermetic tests

Required RED-before-GREEN cases:

1. Fed event normalization with exact timezone and location expiry.
2. Treasury event and buyback normalization separating announced, submitted and accepted amounts.
3. Duplicate, revised and cancelled event vintages using keep-FIRST storage.
4. Present-but-unreadable event store refuses replacement.
5. Non-quarterly futures month returns `not_applicable`.
6. Quarterly scheduled roll without progress never reports active.
7. Year-boundary contract mapping and holiday/expiry behavior.
8. Canonical event view composes existing rows plus official/roll rows without replacing owner truth.
9. OPEX calendar alone cannot produce support or direction.
10. Positive-gamma/pin support near expiry plus weak/unknown replacement produces `SUPPORT_ROLLOFF_IMMINENT`.
11. Short-gamma expiration refuses a volatility-rise assertion.
12. `VOLATILITY_WINDOW_OPEN` requires independent realized confirmation.
13. Observed month-end mechanical pulse can dominate; mere calendar eligibility cannot.
14. High-impact event collision produces `CATALYST_DOMINANT`.
15. Missing core evidence produces `UNKNOWN` with exact gaps.
16. Input-order invariance and fixed-clock determinism.
17. Authority fields remain all false and forbidden fields are absent.
18. Builder writes schema-shaped fresh, partial, stale and unknown artifacts.
19. Forward receipt keep-FIRST and correction lineage.
20. UI renders fresh, partial, stale, cancelled, conflicting and unknown states in EN/ZH.

### 12.2 Static boundaries

Tests or repository scans must prove:

- no import from `policy_turn_clock` into ranking, risk sizing, conditions, Prophet or order paths;
- no new scheduler, lifecycle, queue, event database or model call;
- no edit to protected paths;
- existing event/OPEX/options/rebalance/TGA owner semantics remain intact;
- generated JSON is the machine contract; templates do not become a second semantic implementation.

### 12.3 Real proof

Acceptance requires all of:

1. Real official Fed and Treasury source run with source receipts and timestamps.
2. Real TreasuryDirect buyback schedule/results record if a current operation is available; otherwise a real official schedule plus a typed absence of results.
3. Real current Macro owner inputs through the builder.
4. `site/policy_turn_clock.json` digest and inspection.
5. Policy Watch browser proof at 1440/768/390, dark/light, EN/ZH.
6. At least fresh, partial/stale and unknown/cancelled/conflicting states demonstrated with real or source-faithful fixtures.
7. One real machine consumer reads and validates the JSON without scraping HTML.
8. One prospective receipt frozen before a real upcoming event or transition window.
9. Hosted CI on the immutable PR head.
10. Independent adversarial review and explicit Sol acceptance.

A manual one-off source fetch, green CI, merged code or a screenshot alone is not production proof.

## 13. Stop condition

The worker stops at one immutable `HOLD-FOR-SOL` PR that proves this W1 vertical. It must not merge, deploy, start W2/W3, alter Prophet authority or extend the path ceiling. The return packet includes exact base/head/tree, paths, collision census, ACK/START receipts, tests/CI, source receipts, artifact digest, browser/machine proof, prospective receipt ID, unresolved gaps and the next bounded recommendation.
