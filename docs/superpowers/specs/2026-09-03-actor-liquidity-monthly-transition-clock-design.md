# Actor, Liquidity & Monthly Transition Clock — W1 Design

Date: 2026-09-03  
Status: **FORWARD-REPAIRED DESIGN / HOLD-FOR-SOL / SPEC_ONLY**  
Parent program: Policy Transmission & Pre-Turn Command  
Organizational owner: `WS:RATES-INFLATION-COMMAND`  
Implementation carrier: Macro issue #6787  
Operation: `policy-preturn-actor-liquidity-calendar-clock-20260903-sol-001`  
Architecture carrier: Macro PR #6788  
Protected procedure at forward repair: `mastermindx-market-intelligence/Mastermind@da6af515c95301377fb5fd8748e374a8948a3540`, `mastermind.sol_skillpack.v1` 1.0.1, bootstrap major 1 compatible.  
Macro source observation at repair START: `main@9c7d23e4efc9a5fef52d51b935a635a89774055f`; action-time current main controls reconciliation.

This document consolidates the binding W1 contract. The VIX-futures and executable-CI amendments in the same PR remain provenance and must agree with this design. The six-finding forward repair on operation `policy-preturn-pr6788-six-finding-forward-repair-20260903-sol-001` adds no implementation or runtime effect; it closes pre-implementation worktree, machine-consumer, design-evidence, prospective-ledger, per-source no-regress, and axis-composition gaps identified by independent review.

---

## 1. Outcome

Before a macro turn becomes obvious in a retrospective regime label, a user can open Policy Watch and answer:

1. What official Fed, Treasury and TreasuryDirect events or liquidity operations are next?
2. Which actor appearance is merely scheduled, which is actually occurring, and what physical location—if any—is officially supported now?
3. Is monthly market support building, stable, pinned, rolling off, replaced, contradicted, or overwhelmed by a catalyst?
4. Are the relevant futures mechanics a quarterly equity-index/Treasury roll, a weekly VX expiry, a standard monthly VX settlement, or not applicable?
5. What Treasury/TGA, broad-market flow, month-end duration, rebalance, volatility, breadth and credit evidence confirms or invalidates the proposed transition?
6. Which facts are stale, unavailable, conflicting or corrected?
7. Why is the read context and decision support rather than a hidden buy/sell instruction?

The same machine-readable `policy_turn_clock.v1` payload feeds Policy Watch and the existing Neural Web world-state plane. HTML is never the machine API.

The end state is not a calendar card. It is a correction-safe transition diagnosis:

```text
support formation
→ support stability / pinning
→ expiration / rolloff
→ replacement or failure to replace
→ month-end / Treasury / futures / catalyst override
→ confirmation, contradiction or unknown
```

## 2. Empirical and authority law

The Chairman’s observed early-month/pre-OPEX rally and post-OPEX/late-month volatility pattern is treated as a conditional compound clock, not a universal seasonal trade.

- Long-gamma/pin inventory may damp movement into expiration.
- Short-gamma inventory may amplify movement and its expiration may stabilize the tape.
- Replacement inventory may rebuild support after expiration or may remain unknown.
- Broad ETF flows, systematic re-risking, Treasury/TGA movement, index/pension flows, bond-index extension, futures rolls and macro releases can reinforce or contradict one another.
- Standard monthly VX settlement occurs every month; major equity-index and Treasury futures rolls are quarterly.
- Calendar proximity alone does not establish dealer sign, flow direction, realized volatility, equity direction or actor intent.

Every W1 payload publishes:

```json
{
  "can_rank": false,
  "can_gate": false,
  "can_size": false,
  "can_trade": false
}
```

No W1 state may enter Prophet, portfolio sizing, risk limits, orders, alerts that imply action, or trade origination. A later promotion requires point-in-time replay, prospective evidence, a separate Sol/Chairman authority decision and the existing governed promotion path.

## 3. Capability ledger at repaired design

| Capability | State | W1 implication |
|---|---|---|
| Canonical upcoming U.S. event calendar | `PROVEN_LIVE` as existing context owner | extend/consume, never replace |
| OPEX calendar and phase | `PROVEN_LIVE` | consume exact phase and clocks |
| Options surface / OPEX risk | built with real history and explicit caveats | consume availability, OI timing and dealer-sign passport |
| Rebalance calendar / Rebalance Pulse | built context owners | scheduled eligibility and observed pulse remain separate |
| Treasury Watch / TGA / net liquidity | existing canonical owner | consume mechanics and freshness; never infer rescue intent |
| Broad ETF flow proxy | forward-accruing, T+1, display-only | use as lagged context, not intraday cash flow |
| Standard monthly VX M1–M6 curve | forward-accruing, shallow | use current context; no deep historical efficacy claim |
| Neural Web world state | existing durable machine projection | add one read-only `policy_turn_clock` lobe; do not create a new machine API |
| RIC F3 yield momentum | `BUILT_NOT_PROVEN`, PR #6721 | do not rebuild; consume only after accepted availability |
| Policy turn clock | `NOT_BUILT` | W1 target |
| Prospective policy-turn evidence | `NOT_BUILT` | eligible-trigger-only nightly receipt begins in W1 |
| Monthly transition evidence lab | `SPEC_ONLY`, issue #6794 | dependency-gated; no outcome computation in W1 |

## 4. Canonical owners and no-rebuild boundaries

W1 composes these owners:

```text
engine/event_calendar.py
engine/event_window.py
engine/opex.py
engine/options_surface.py
engine/opex_risk.py
engine/rebalance_calendar.py
engine/rebalance_pulse.py
engine/etf_flows.py
engine/treasury_watch.py
engine/ledger_lane.py
collectors/_first_seen_store.py
collectors/cboe_vix_futures.py
engine/neuralweb/world_state.py
data/flows/broad_flow_proxy.parquet
data/cboe/vix_futures.parquet
data/cboe/vix_curve.parquet
data/market_structure/latest.json
data/regime/latest.json
site/vol/regime.json
```

W1 may not create another:

- event or release truth store;
- OPEX or options surface;
- TGA or Treasury-liquidity owner;
- broad ETF flow collector;
- VIX futures collector/store;
- market-state or volatility engine;
- world-state/machine-context bus;
- lifecycle, queue, scheduler, lock service, retry ledger or publisher plane;
- CI planner, logical-job registry or trusted-executor plane;
- score, recommendation or trade authority.

Unconditional no-edit paths:

```text
engine/yield_momentum.py
engine/rates_inflation_command.py
scripts/build_rates_command.py
agentos/workstreams/WS-RATES-INFLATION-COMMAND.md
collectors/cboe_vix_futures.py
```

`.github/ci/legacy-jobs.yml` is conditionally shared. No W1 source effect may begin until a fresh census proves every active owner of that path is released or a later Sol ruling provides a collision-free composition. At the forward-repair census, open owners still included #6721, #6706, #6651, #6625, #6514, #6389 and #6296; `.github/workflows/ci.yml` also remained owned by open #6628. PR #6791 had merged and was no longer a live owner. START-time GitHub truth, not this historical list, controls.

Fresh open-PR search at the forward repair found no active owner for the newly named machine-consumer paths `engine/neuralweb/world_state.py` or `tests/test_world_state.py`; this is an observation, not a durable lock.

## 5. Exact expected implementation surface

### New source files

```text
collectors/policy_event_clock.py
engine/futures_roll_calendar.py
engine/policy_turn_clock.py
scripts/build_policy_turn_clock.py
templates/partials/_policy_turn_clock.html.j2
tests/test_policy_event_clock.py
tests/test_futures_roll_calendar.py
tests/test_policy_turn_clock.py
tests/test_build_policy_turn_clock.py
```

### Existing files modified

```text
engine/event_calendar.py
engine/neuralweb/world_state.py
scripts/build_policy_watch.py
templates/policy_watch.html.j2
tests/test_policy_watch_ui.py
tests/test_world_state.py
config/dag.yml
.github/workflows/whitehouse-sentinel.yml
scripts/ci/daily_engine_regional_desk_builders.sh
.github/workflows/ci.yml
.github/ci/legacy-jobs.yml
```

`tests/test_dag_conformance.py` may enter only when current source proves an exact expectation must change. The worker must declare it before edit.

### Generated/evidence outputs

```text
data/policy_events/official_events.parquet
data/policy_events/collector_status.json
data/policy_turn_clock/forward_log.jsonl
site/policy_turn_clock.json
site/policy_watch.html
mockups/refs/policy-turn-clock/**
```

Generated outputs are never hand-edited.

### Sparse-worktree precondition

Session worktrees are sparse by repository law. Before any read/write/build that touches planned `data/`, `site/`, or `mockups/` paths, the implementation worker must use the current checked-in worktree helper from the already assigned session-root worktree:

```bash
python3 scripts/worktree_sparse.py status
python3 scripts/worktree_sparse.py add data
python3 scripts/worktree_sparse.py add site
python3 scripts/worktree_sparse.py add mockups
```

A worker may use `python3 scripts/worktree_sparse.py full` instead when the operation genuinely needs the full checkout. It may not infer path absence from a sparse omission, write into an omitted tree, or stage an unexpected broad `git add -A` delta. The implementation plan carries the full session-root procedure.

## 6. Official evidence contract

### 6.1 Collection sources

W1 normalizes bounded official-public observations from:

- Federal Reserve Board calendar and event detail pages;
- U.S. Treasury press release/event surfaces;
- TreasuryDirect buyback index, tentative schedule, linked preliminary/final/results XML and published XSD;
- existing canonical scheduled-event and Treasury auction owners where already available.

The collector does not scrape social media, infer private schedules, infer travel from photographs, or use the Treasury auction endpoint as a buyback source.

### 6.2 Evidence row schema

Every stored row carries:

```text
schema_version              int = 1
source_key                  string
source_event_id             string
source_revision             string
canonical_semantic_sha256   lowercase hex
record_kind                 actor_event | treasury_operation
actor_id                    string | null
actor_name                  string | null
actor_role                  string | null
organization                string
event_kind                  speech | interview | meeting | testimony | release | other | null
operation_kind              auction | buyback | cash_management_operation | settlement |
                            tga_release | tga_build | other | null
operation_purpose           cash_management | liquidity_support | funding | market_function |
                            debt_management | other | null
headline                    string
summary                     string | null
scheduled_start             offset-aware ISO timestamp | null
scheduled_end               offset-aware ISO timestamp | null
source_status               scheduled | active | completed | revised | cancelled | unknown
phase_at_observation        future | active | past | unknown
event_location_label        string | null
event_location_precision    venue | city | country | unknown
attendance_mode             in_person | virtual | hybrid | prerecorded | unknown
presence_basis              source_explicit | format_and_venue | unsupported
announced_max_usd_bn        float | null
offered_usd_bn              float | null
submitted_usd_bn            float | null
accepted_usd_bn             float | null
instrument_scope            string | null
settlement_date             ISO date | null
source_url                  string
source_published_at         offset-aware ISO timestamp | null
observed_at                 offset-aware ISO timestamp
available_at                offset-aware ISO timestamp
first_seen                  offset-aware ISO timestamp
supersedes_revision         string | null
evidence_class              FACT | INFERENCE | PRIOR | THEORY
rights_class                official_public
parser_version              string
null_reason                 string | null
```

All money is USD billions. Inapplicable or unpublished values are null. Maximum, offered, submitted and accepted amounts are never inferred from one another.

### 6.3 Stable identity and silent revisions

The immutable storage key is:

```text
(source_key, source_event_id, source_revision, canonical_semantic_sha256)
```

`source_event_id` identifies the real event/operation independently of page order. `source_revision` uses an explicit source publication/revision identity when available. When the source provides no revision token, derive a stable revision identity from normalized semantic fields plus publication/availability evidence—not from raw HTML bytes.

A reused explicit revision with a different canonical semantic digest produces:

```text
REVISION_ID_COLLISION
```

Both receipts survive. The current projection selects the latest valid row by `available_at`, then `observed_at`, then digest, while preserving the conflict. Whitespace, navigation and formatting-only page changes do not create a semantic vintage.

A source may still label an event `scheduled` after its time has passed. `source_status` remains immutable source evidence; `phase_at_observation` and current phase are derived separately from the clock.

### 6.4 Event venue versus actor presence

An event venue is not automatically the actor’s current physical location. A virtual appearance, hybrid broadcast, pre-recorded video, named host venue, or “Watch Live” link may provide event context without proving physical presence.

The actor projection is:

```json
{
  "actor_id": "...",
  "current_physical_location": null,
  "current_location_status": "publicly_confirmed|active_unverified|conflicting|unknown",
  "last_verified_location": null,
  "last_verified_at": null,
  "attendance_mode": "...",
  "presence_basis": "...",
  "candidate_receipts": [],
  "gaps": []
}
```

`current_physical_location` may be non-null only during the official event window when the source explicitly supports live physical presence. Merely scheduled, virtual, prerecorded, cancelled, ended or ambiguous records leave current physical location unknown. Conflicting simultaneous official receipts remain visible.

## 7. Futures-roll contract

`engine/futures_roll_calendar.py` is pure date/input arithmetic and exposes:

```python
def equity_roll_window(d: date) -> dict[str, object]: ...
def treasury_roll_window(d: date) -> dict[str, object]: ...
def vix_settlement_window(
    d: date,
    *,
    front: Mapping[str, object] | None = None,
    curve: Mapping[str, object] | None = None,
    source_asof: date | None = None,
) -> dict[str, object]: ...
def snapshot(
    asof: date,
    *,
    live_progress: Mapping[str, object] | None = None,
    vix_front: Mapping[str, object] | None = None,
    vix_curve: Mapping[str, object] | None = None,
    vix_source_asof: date | None = None,
) -> dict[str, object]: ...
```

Output preserves independent families:

```json
{
  "schema": "futures_roll_calendar.v1",
  "as_of": "YYYY-MM-DD",
  "equity_index": {},
  "treasury": {},
  "volatility": {},
  "gaps": [],
  "authority": {"can_rank": false, "can_gate": false, "can_size": false, "can_trade": false}
}
```

Equity-index and Treasury rolls are quarterly. Calendar windows are `scheduled`; they become `active` only with source-owned current-contract/next-contract volume or open-interest progress. Ordinary months are `not_applicable` for those two families.

Standard VX settlement is monthly. Weekly front contracts remain distinct from the standard monthly M1. The helper validates the standard Wednesday/SOQ/holiday rule against fresh canonical M1 DTE when available. A disagreement is `VX_EXPIRY_SOURCE_CONFLICT`, not silent preference.

The standard curve is rank-based. When former M2 becomes new M1 across settlement, raw M1-to-M1 change is not same-contract repricing. `same_contract_change_available=false` unless an existing owner supplies contract identity. Missing/stale M2 produces `curve_state=unknown`, never flat.

VX settlement proximity alone cannot select `VOLATILITY_WINDOW_OPEN` or any direction.

## 8. Pure transition composer

### 8.1 Interface

`engine/policy_turn_clock.py` performs no network, filesystem, model, ledger or wall-clock I/O beyond the injected aware datetime:

```python
def compose(
    *,
    now: datetime,
    events: Sequence[Mapping[str, object]],
    official_treasury_operations: Sequence[Mapping[str, object]],
    opex: Mapping[str, object] | None,
    opex_risk: Mapping[str, object] | None,
    option_surface: Sequence[Mapping[str, object]] | None,
    broad_market_flow: Mapping[str, object] | None,
    rebalance_calendar: Mapping[str, object] | None,
    rebalance_pulse: Mapping[str, object] | None,
    duration_extension_context: Mapping[str, object] | None,
    treasury_tga: Mapping[str, object] | None,
    futures_roll: Mapping[str, object] | None,
    market_confirmation: Mapping[str, object] | None,
    prior_clock: Mapping[str, object] | None = None,
) -> dict[str, object]: ...
```

Input order does not affect output. Hidden reads are forbidden.

### 8.2 Decision timezone and semantic identity

Normalize `now` once to `America/New_York` for the U.S. decision date/session. Preserve source-native timestamps on evidence rows. Equivalent instants represented with different offsets must produce identical `as_of`, phase, countdown, state and semantic digest.

Required top-level fields:

```json
{
  "schema": "policy_turn_clock.v1",
  "method_version": "policy_turn_clock.v1.0.0",
  "input_digest": "lowercase sha256",
  "source_versions": {},
  "source_watermarks": {},
  "as_of": "YYYY-MM-DD",
  "generated_at": "offset-aware timestamp",
  "evidence_cutoff": "offset-aware timestamp",
  "state": "...",
  "state_basis": [],
  "change_from_prior": {},
  "calendar": {},
  "actor_clock": {},
  "treasury_liquidity": {},
  "option_support": {},
  "broad_market_flow": {},
  "support_composition": {},
  "futures_roll": {},
  "rebalance": {},
  "market_confirmation": {},
  "catalysts": [],
  "confirmation": [],
  "invalidation": [],
  "disagreements": [],
  "gaps": [],
  "freshness": {},
  "authority": {"can_rank": false, "can_gate": false, "can_size": false, "can_trade": false}
}
```

`generated_at` is excluded from `input_digest` and semantic change detection. Identical semantic inputs with a later wall clock do not create `change_from_prior.changed=true` or a new receipt. A method-version mismatch refuses direct prior-state comparison unless an explicit bridge is supplied. Correction rows link to the original method/input/cutoff identity.

### 8.3 Independent axes and composition

#### Options support

`option_support` contains only options/OPEX-owner evidence:

```text
stabilizing | destabilizing | transition | unavailable | stale | ambiguous
```

Carry OI timing, dealer-sign assumption, root class, source as-of and stale reason. Replacement book is:

```text
building | present | weak | absent | unknown | incomparable
```

Only comparable current/prior rows from the same canonical owner/root class can establish replacement. Missing evidence is unknown.

`option_support` MUST NOT contain broad-flow state, Treasury support, breadth/credit confirmation, a cross-axis `applicable_support_count`, or any K-of-N result. It is an evidence axis, not the support composer.

#### Broad-market flow

`broad_market_flow` consumes only the canonical SPY/QQQ/IWM/RSP/DIA creation/redemption proxy with its true publication lag, coverage depth, jump guard and display-only authority. It may expose descriptive status such as `supportive|draining|mixed|neutral|unavailable|stale`, but it cannot be copied into `option_support`, described as intraday cash, or treated as a complete institutional-flow measure.

#### Support composition

`support_composition` is the only place that compares independent support families. It receives already-composed axis states and records, without weights:

```json
{
  "applicable_support_count": 0,
  "supporting_mechanisms": [],
  "contradicting_mechanisms": [],
  "unavailable_mechanisms": [],
  "predicate_results": []
}
```

The eligible support families are separately sourced mechanisms such as option replacement, broad-market flow, Treasury/TGA, current systematic re-risking, and fresh breadth/credit confirmation. A family contributes at most one vote. Stale/unavailable evidence contributes no supportive vote and remains visible. Options and broad flow therefore stay separate even when both contribute to a top-level state.

#### Treasury liquidity

```text
supportive | draining | mixed | neutral | unavailable | stale
```

Compose TGA/net-liquidity mechanics with official Treasury operations. Buybacks/auctions/settlements retain mechanism, purpose, clocks and separate amounts. A TGA decline is mechanically supportive all else equal; it is not evidence of deliberate equity rescue.

#### Rebalance and duration

Preserve:

```text
scheduled_unconfirmed
pressure_estimate_context
observed_mechanical_pulse
```

Only a fresh non-quiet Rebalance Pulse may support `MONTH_END_REBALANCE_DOMINANT`. A relative-performance estimate remains context. Bond-index extension is an asset-specific duration-calendar/measured-prior context; it cannot establish current equity flow or direction.

#### Market confirmation

Consume existing current volatility, breadth, credit and market-structure owners with source watermarks. `VOLATILITY_WINDOW_OPEN` requires at least one fresh independent confirmation beyond calendar, OPEX and VX settlement. Stale confirmation is unavailable, not neutral.

### 8.4 Closed top-level state vocabulary

```text
SUPPORT_BUILDING
SUPPORT_STABLE
PINNED
SUPPORT_ROLLOFF_IMMINENT
VOLATILITY_WINDOW_OPEN
MONTH_END_REBALANCE_DOMINANT
CATALYST_DOMINANT
MIXED
UNKNOWN
```

### 8.5 Deterministic precedence

1. `UNKNOWN` when the current calendar is unavailable or fewer than two applicable core mechanism families are fresh enough to interpret safely.
2. `CATALYST_DOMINANT` when a valid high-impact event/operation is inside 24 hours or active and at least one mechanism-specific collision is present.
3. `MONTH_END_REBALANCE_DOMINANT` only with a valid late-month/quarter-end window and a fresh observed non-quiet mechanical pulse, absent catalyst dominance.
4. `VOLATILITY_WINDOW_OPEN` only when previously observed stabilizing support has rolled off and a fresh independent volatility/breadth/credit/market-structure confirmation is present.
5. `SUPPORT_ROLLOFF_IMMINENT` when expiry is near/recent, prior stabilizing support is valid and replacement is weak/unknown, without independent confirmation sufficient for an open volatility window.
6. `PINNED` when long-gamma context, valid pin proximity and compressed-range context are all fresh.
7. `SUPPORT_BUILDING` only when `support_composition` records at least two independent applicable supporting mechanism families and no higher-precedence contradiction exists. Literal K-of-N only; no weights. `option_support` alone, broad flow alone, or any cross-axis count stored inside either axis is insufficient.
8. `SUPPORT_STABLE` when current stabilizing support is fresh and no higher-precedence override exists.
9. `MIXED` otherwise.

Every state lists exact predicates, values, sources, cutoffs and applicable counts in `state_basis` and `support_composition`. No hidden scalar score is permitted.

## 9. Builder and runtime ownership

### 9.1 Builder modes

`scripts/build_policy_turn_clock.py` exposes:

```python
def gather_inputs(*, root: Path, now: datetime) -> dict[str, object]: ...
def build_payload(*, root: Path, now: datetime) -> dict[str, object]: ...
def write_payload(payload: Mapping[str, object], *, root: Path) -> Path: ...
def append_forward_receipt(payload: Mapping[str, object], *, root: Path) -> int: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```

CLI modes:

```text
--mode publish-current
--mode ledger-only
--mode verify
```

The builder never performs network I/O.

### 9.2 Hourly single writer / current publisher

Reuse `.github/workflows/whitehouse-sentinel.yml`.

Hourly owns:

```text
data/policy_events/official_events.parquet
data/policy_events/collector_status.json
site/policy_turn_clock.json
```

Sequence:

```text
collect official evidence
→ persist semantic changes/status transitions only
→ build current clock with COLLECT_LANE=hourly
→ reconcile every source watermark against the fresh published artifact
→ validate
→ publish owned event/status/current JSON paths
```

A healthy quiet rerun with no semantic source/status/input change preserves bytes and creates no commit. `last_attempt_at` may appear in ephemeral logs but must not force a tracked status rewrite. A real failure, recovery, parser-shape change, stale transition, correction or source watermark advance publishes a new status/current artifact.

### 9.3 Per-source no-regress publication law

Whole-payload cutoff comparison is necessary but not sufficient. Before hourly publication, reconcile each incoming source independently with the currently published artifact after a fresh read.

Each `source_watermarks[source_key]` entry carries enough owner-native identity to compare the source monotonically: accepted source/revision identity, `available_at`/observation watermark as applicable, semantic digest, correction lineage, and last-good evidence reference.

For every source independently:

- **advance:** a newer valid source identity replaces that source’s current/last-good block;
- **equal semantic identity:** preserve bytes for that source;
- **regression:** an older source identity can never lower the published watermark or replace last-good evidence; retain the published source block and emit `SOURCE_WATERMARK_REGRESSION:<source_key>`;
- **failure/staleness transition:** publish the truthful degraded status while retaining the source’s last-good evidence and watermark; a failure clock is not a data watermark;
- **valid correction:** a correction with explicit lineage may change semantic content without pretending the prior row never existed; preserve the original receipt, record `supersedes_revision`/correction identity, and accept only when the correction identity is not a time/source regression;
- **mixed candidate:** if source A advances while source B regresses, publish A’s advance plus B’s preserved last-good block and a B regression gap when the reconciled payload is semantically new. Do not reject A merely because B regressed, and do not regress B merely because A advanced.

After source-level reconciliation, recompute `input_digest`, `evidence_cutoff`, freshness, gaps and state from the accepted evidence set. `evidence_cutoff` itself must not move backward. If every attempted change is regressive or semantically equal, publication is refused/no-op as appropriate.

Because nightly is ledger-only, it cannot regress the current machine/UI artifact. No cross-lane lock service is introduced.

### 9.4 Policy Watch consumption

`scripts/build_policy_watch.py` and the template provide the static shell and fallback. The dynamic turn-clock component loads the same-origin `policy_turn_clock.json` at runtime so nightly HTML rebuilds cannot embed an older clock than the machine artifact. The page has a keyboard-accessible noscript/unavailable state and does not silently reuse stale embedded data.

### 9.5 Durable direct machine consumer — Neural Web world state

The W1 direct machine consumer is not an ad-hoc proof script. It is the existing Neural Web N1 producer/reader plane:

```text
owner:       existing Neural Web N1 world-state composition
source path: engine/neuralweb/world_state.py
input:       site/policy_turn_clock.json
output:      data/neuralweb/world_state.json -> top-level policy_turn_clock lobe
call site:   build_world_state() / build_and_write(), invoked by existing scripts/build_world_state.py
proof owner: tests/test_world_state.py
```

`engine/neuralweb/world_state.py` reads the exact JSON directly—never Policy Watch HTML—and projects a read-only/display-only `policy_turn_clock` lobe. The lobe preserves `schema`, `method_version`, `input_digest`, `as_of`, `evidence_cutoff`, `state`, independent axes, gaps and all-false authority. It may add Neural-Web envelope metadata but may not recompute a second policy-turn state.

Missing, corrupt, wrong-schema or authority-violating input follows the existing world-state fail-open contract: the lobe is absent/null-shaped with a typed gap; it never silently substitutes stale HTML, zeroes missing axes, or treats an invalid payload as current. A changed policy-turn `input_digest` must change world-state semantic input identity; an unchanged policy-turn digest must remain deterministic under the existing world-state single-clock law.

No new machine API, bus, store or consumer registry is created.

### 9.6 Nightly ledger-only advancer

The real existing nightly owner is:

```text
scripts/ci/daily_engine_regional_desk_builders.sh
```

Immediately before its existing Policy Watch invocation, run:

```text
python -m scripts.build_policy_turn_clock --mode ledger-only
```

under the existing `COLLECT_LANE=nightly` environment.

Ledger-only mode:

- does not collect official evidence;
- does not write/stage `site/policy_turn_clock.json` or Policy Watch HTML;
- reads current official evidence and fresh after-close canonical market inputs;
- appends **zero** rows unless an explicit eligible first-seen trigger is present;
- appends at most one keep-FIRST prospective receipt per invocation by frozen trigger precedence;
- reruns idempotently.

`config/dag.yml` mirrors the actual hourly and nightly execution paths; it is not an executor.

## 10. Prospective ledger

Path:

```text
data/policy_turn_clock/forward_log.jsonl
```

Advance gate:

```python
engine.ledger_lane.nightly_advance_enabled()
```

Canonical environment is `COLLECT_LANE=nightly`; `US_LANE=nightly` is a legacy alias. The lane check must live inside the append seam itself; calling `append_forward_receipt()` directly off-lane is refused. Hourly never appends.

Receipt identity:

```text
(as_of, trigger_kind, trigger_id, method_version, input_digest)
```

Eligible first-seen trigger families, in deterministic selection order when several occur in one build:

1. `material_state_change` — material semantic top-level transition first appears;
2. `high_impact_event_t24` — high-impact event first enters 24 hours;
3. `opex_t_minus_2` — OPEX first enters T−2;
4. `post_opex_t_plus_1` — post-OPEX first enters T+1;
5. `month_or_quarter_end_pulse` — observed month/quarter-end pulse first appears;
6. `vx_t_minus_2` — standard VX settlement first enters T−2;
7. `vx_rank_roll_boundary` — rank-roll boundary first appears.

Nightly eligibility alone is never a trigger. If no first-seen trigger exists, return a semantic no-op and append zero rows.

The receipt freezes method/input/source identity, evidence cutoff, state/basis, all independent axes, support composition, gaps, expected mechanism, confirmation/invalidation and predeclared outcome horizons.

Corrections never rewrite the original prospective receipt. A correction row must carry its own new receipt identity plus `record_kind=correction`, `correction_of_receipt_id`, original method/input/cutoff identity, source correction lineage, and corrected semantic fields. It is appendable only when the referenced original receipt exists and the correction passes the same nightly lane and source no-regress laws.

## 11. CI ownership

After every active owner of `.github/ci/legacy-jobs.yml` is released, W1 may make the smallest additive existing-job composition:

- extend one compatible policy/front-facing logical job;
- name all four new test suites in executable pytest command(s);
- include `tests/test_world_state.py` in its existing Neural Web owner rather than duplicating the full suite when possible, while adding the exact policy-turn consumer test to executable ownership;
- include each new suite and exact source subject in the appropriate job path closure;
- add matching `.github/workflows/ci.yml` triggers;
- include `scripts/ci/daily_engine_regional_desk_builders.sh` and workflow/DAG subjects in the appropriate conformance closure;
- run the selected logical job(s) through the canonical pack runner;
- preserve unrelated current-main lines;
- do not add a job, workflow, runner, planner, permission, trusted-executor, secret, concurrency or merge-control plane;
- do not use `config/unrun_test_baseline.json` as an escape hatch.

START-time collision census must inspect all open PRs and active branches/worktrees. A list frozen in this document is not sufficient.

## 12. Policy Watch binding design packet

The design packet is implementation law, not optional taste guidance.

### Baseline and invariant semantics

Baseline/reference:

```text
research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md
research/DESIGN_DOCTRINE.md
mockups/design_system/specimen.html
existing Policy Watch route/composition
```

The two themes share information architecture, component semantics, ordering, density, spacing/type scales, interactions, keyboard behavior, state meanings, evidence hierarchy and EN/ZH meaning. They intentionally differ in material treatment. Token substitution alone is not an accepted light design.

No parallel token root or opaque runtime stylesheet system may be introduced. Use canonical theme tokens/components and governed presentation sources.

### DARK TREATMENT — command center

- Near-black/luminance-depth canvas with restrained instrument layering rather than large flat fills.
- Fresh/current state uses a narrow luminous edge or restrained local glow only where it improves scanability; glow never encodes a meaning unavailable to text/icon/shape.
- Evidence rows sit in calm layered instrument wells with crisp typography and subdued separators.
- Catalyst/conflict/warning emphasis uses restrained semantic rails and precise text, not saturated full-card alarm color.
- Countdown and source freshness are high-information, compact instrument readouts.

**Dark degraded:** remove fresh-state glow, reduce material lift, use a segmented/dashed warning rail plus explicit `DEGRADED`/stale clock and named gap. Do not dim the whole panel into apparent disabled state.

**Dark unknown:** neutral graphite/charcoal surface, no implied directional tint, explicit `UNKNOWN`, missing-evidence list and last-good timestamps when lawful. Unknown never looks like calm/neutral market confirmation.

### LIGHT TREATMENT — research workspace

- Cool neutral canvas with white research material, graphite text, disciplined hairline rules and modest spatial shadow instead of glow.
- State emphasis uses restrained semantic tint/ink in labels and rails; the card body remains readable white/cool material.
- Evidence detail reads like an analyst worksheet: clean tabular alignment, precise timestamps, visible source/provenance affordances and low visual noise.
- Countdowns and freshness use crisp ink/hairline hierarchy rather than a dark-theme glow translated onto white.

**Light degraded:** white/cool material remains present; use a warning hairline/hatched or otherwise mechanically distinct caution rail, explicit `DEGRADED`, stale clock and named gap. A low-contrast gray wash that makes data disappear is forbidden.

**Light unknown:** no pale-green or low-contrast neutral that could read as “fine.” Use a neutral research sheet with explicit `UNKNOWN`, a distinct missing-evidence treatment, preserved last-good references when lawful and no directional tint.

### Intentional differences and why

Dark depth is created by luminance layering and restrained glow because the command-center environment needs fast instrument separation. Light depth is created by white material, hairlines and modest shadow because glow on a bright research surface reduces precision. Degraded/unknown mechanisms therefore differ materially by theme while preserving the exact same semantic text, status icons/shapes and interaction behavior.

### Binding evidence matrix

A W1 UI proof is incomplete unless every required cell is captured from real rendered bytes and human-reviewed for hierarchy/material/state meaning:

| Theme | Language | 1440 desktop | 390 mobile | Required state coverage |
|---|---|---:|---:|---|
| dark | EN | required | required | fresh/support, rolloff, catalyst, degraded, unknown, conflict |
| dark | ZH | required | required | fresh/support, rolloff, catalyst, degraded, unknown, conflict |
| light | EN | required | required | fresh/support, rolloff, catalyst, degraded, unknown, conflict |
| light | ZH | required | required | fresh/support, rolloff, catalyst, degraded, unknown, conflict |

Also run 768 CSS-pixel functional/geometry checks in both themes and both languages. The committed evidence lives under `mockups/refs/policy-turn-clock/**` using the repository’s governed visual-evidence format. Before creating or reading those files in a sparse session, opt into `mockups/` explicitly.

Automated tests prove state identity, source/freshness text, no hidden color-only meaning, keyboard behavior, EN/ZH parity and evidence-manifest completeness. `scripts/check_design_system.py --mode enforce-added`, `scripts/check_runtime_style_injection.py`, and `scripts/check_ui_visual_evidence.py` must run where applicable. Human review owns whether dark and light are genuinely distinct art directions.

## 13. Failure behavior

Explicitly represent:

```text
SOURCE_UNAVAILABLE
SOURCE_SHAPE_CHANGED
REVISION_ID_COLLISION
EVENT_IDENTITY_AMBIGUOUS
ACTOR_PRESENCE_UNSUPPORTED
ACTOR_LOCATION_CONFLICT
TIMEZONE_OR_DST_INVALID
MARKET_CALENDAR_UNAVAILABLE
TREASURY_AMOUNT_INCOMPLETE
BUYBACK_PURPOSE_UNKNOWN
OPTIONS_SURFACE_UNAVAILABLE
OPTIONS_SURFACE_STALE
DEALER_SIGN_AMBIGUOUS
REPLACEMENT_INCOMPARABLE
BROAD_FLOW_STALE
BROAD_FLOW_SHORT_HISTORY
REBALANCE_SCHEDULED_UNCONFIRMED
VX_EXPIRY_SOURCE_CONFLICT
VX_CURVE_STALE
VX_RANK_ROLL_BOUNDARY
MARKET_CONFIRMATION_UNAVAILABLE
METHOD_VERSION_MISMATCH
INPUT_DIGEST_MISMATCH
SOURCE_WATERMARK_REGRESSION
NO_REGRESS_REFUSAL
LEDGER_LANE_REFUSED
LEDGER_TRIGGER_INELIGIBLE
LEDGER_CORRECTION_TARGET_MISSING
MACHINE_CONSUMER_SCHEMA_INVALID
PATH_COLLISION
```

One failed axis does not erase healthy axes, but required missing/stale evidence may force top-level `UNKNOWN`. No failure becomes zero, false, quiet, current or no-event.

## 14. Acceptance

Minimum source/contract proof:

1. RED-before-GREEN tests for every schema, time, correction, null and failure family.
2. Real official Fed/Treasury/TreasuryDirect source run with source/shape/freshness receipts.
3. Buyback preliminary/final/extended/cancelled/results fixtures preserving purpose and separate amounts.
4. Virtual, prerecorded, in-person, conflicting and ended actor-presence fixtures.
5. Same-instant UTC/ET and DST/session invariance.
6. Weekly VX vs standard monthly VX and rank-roll suppression.
7. Quarterly roll scheduled vs active-with-progress distinction.
8. OPEX long/short gamma and replacement unknown/incomparable behavior.
9. Explicit market-confirmation requirement for `VOLATILITY_WINDOW_OPEN`.
10. Options and broad-flow axis separation: broad flow never appears inside `option_support`; K-of-N exists only in `support_composition`.
11. Broad-flow lag/short-history disclosure and no option-replacement-as-cash shortcut.
12. Month-end scheduled/estimated/observed separation and asset-specific duration context.
13. Quiet healthy hourly rerun produces byte-identical tracked outputs and no commit candidate.
14. Per-source no-regress: mixed-source advance/regression keeps the advanced source and preserves the regressed source’s last-good watermark/evidence; all-regressive input cannot overwrite current state.
15. Real source failure/recovery transition updates status without erasing last-good evidence/watermark.
16. Valid source correction preserves original lineage and cannot masquerade as a watermark regression or rewrite history.
17. Hourly append is refused; nightly with **no eligible trigger** appends zero; each frozen trigger family can append its first-seen receipt; reruns are idempotent.
18. Receipt identity deduplication, correction-link append, and direct off-lane append refusal are executable tests.
19. All new suites execute through canonical logical owners and pack runner; the Neural Web consumer test executes through its existing owner.
20. Browser proof satisfies the binding dark/light × EN/ZH × 1440/390 evidence matrix plus 768 geometry checks and all required states.
21. `engine/neuralweb/world_state.py` directly reads the exact JSON, emits the governed lobe, fails open on invalid input, and never scrapes HTML.
22. One prospective receipt freezes before a real eligible event/transition.
23. Static/mutation proof keeps every authority field false and kills duplicate-plane attempts.

CI green is necessary but is not product or production acceptance.

## 15. Stop condition

The W1 worker stops at one immutable Draft/HOLD-FOR-SOL implementation PR proving the complete official-source → deterministic artifact → Policy Watch → existing Neural Web machine consumer → eligible-trigger prospective receipt vertical.

Do not absorb:

- RIC F3 yield implementation;
- yield-cause decomposition;
- actor reaction-function forecasting;
- commodity delivery-month calendars;
- Prophet/risk/portfolio wiring;
- capital authority;
- evaluation-lab outcome computation;
- merge or deployment.

Return exact receiver, carrier receipts, pickup base/current main, head/tree/parents, changed paths, collision census, RED→GREEN evidence, selected logical CI job/executed-suite proof, hosted checks, official-source receipts, artifact digest, browser/machine proof, prospective receipt identity, per-source no-regress/quiet-no-op proof, authority diff and remaining gaps.