# Actor, Liquidity & Monthly Transition Clock — W1 Design

Date: 2026-09-03  
Status: **REPAIRED DESIGN / HOLD-FOR-SOL / SPEC_ONLY**  
Parent program: Policy Transmission & Pre-Turn Command  
Organizational owner: `WS:RATES-INFLATION-COMMAND`  
Implementation carrier: Macro issue #6787  
Operation: `policy-preturn-actor-liquidity-calendar-clock-20260903-sol-001`  
Architecture carrier: Macro PR #6788  
Protected procedure at repair: `mastermindx-market-intelligence/Mastermind@c7fa5b43de6ca702f942fbf20cbe3ac45a02b0f6`, `mastermind.sol_skillpack.v1` 1.0.1, bootstrap major 1 compatible.  
Macro source observation at repair: `main@16aac3be6a7e8790af0aee75ab1d44ac43eecfab`.

This document replaces the prior contents of this path. The VIX-futures and executable-CI amendments in the same PR remain provenance and must agree with this consolidated contract.

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

The same machine-readable `policy_turn_clock.v1` payload feeds Policy Watch and at least one direct machine consumer. HTML is never the machine API.

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
| RIC F3 yield momentum | `BUILT_NOT_PROVEN`, PR #6721 | do not rebuild; consume only after accepted availability |
| Policy turn clock | `NOT_BUILT` | W1 target |
| Prospective policy-turn evidence | `NOT_BUILT` | nightly-only receipt begins in W1 |
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

`.github/ci/legacy-jobs.yml` is conditionally shared. No W1 source effect may begin until a fresh census proves every active owner of that path is released or a later Sol ruling provides a collision-free composition. Current review found open PR references beyond #6721, including #6791, #6706, #6651, #6625, #6514, #6389 and #6296. START-time GitHub truth, not this historical list, controls.

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
scripts/build_policy_watch.py
templates/policy_watch.html.j2
tests/test_policy_watch_ui.py
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

### 8.3 Independent axes

#### Options support

```text
stabilizing | destabilizing | transition | unavailable | stale | ambiguous
```

Carry OI timing, dealer-sign assumption, root class, source as-of and stale reason. Replacement book is:

```text
building | present | weak | absent | unknown | incomparable
```

Only comparable current/prior rows from the same canonical owner/root class can establish replacement. Missing evidence is unknown.

#### Treasury liquidity

```text
supportive | draining | mixed | neutral | unavailable | stale
```

Compose TGA/net-liquidity mechanics with official Treasury operations. Buybacks/auctions/settlements retain mechanism, purpose, clocks and separate amounts. A TGA decline is mechanically supportive all else equal; it is not evidence of deliberate equity rescue.

#### Broad-market flow

Consume the canonical SPY/QQQ/IWM/RSP/DIA creation/redemption proxy with its true publication lag, coverage depth, jump guard and display-only authority. Do not describe it as intraday cash or a complete institutional-flow measure.

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
7. `SUPPORT_BUILDING` only when at least two independent applicable support mechanisms agree—such as replacement building, supportive broad ETF flows, supportive Treasury/TGA, current systematic re-risking, or stable/improving breadth/credit—and no higher-precedence contradiction exists. Literal K-of-N only; no weights.
8. `SUPPORT_STABLE` when current stabilizing support is fresh and no higher-precedence override exists.
9. `MIXED` otherwise.

Every state lists exact predicates, values, sources, cutoffs and applicable counts in `state_basis`. No hidden scalar score is permitted.

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
→ no-regress compare against current published artifact
→ validate
→ publish owned event/status/current JSON paths
```

A healthy quiet rerun with no semantic source/status/input change preserves bytes and creates no commit. `last_attempt_at` may appear in ephemeral logs but must not force a tracked status rewrite. A real failure, recovery, parser-shape change, stale transition, correction or source watermark advance publishes a new status/current artifact.

### 9.3 Policy Watch consumption

`scripts/build_policy_watch.py` and the template provide the static shell and fallback. The dynamic turn-clock component loads the same-origin `policy_turn_clock.json` at runtime so nightly HTML rebuilds cannot embed an older clock than the machine artifact. The page has a keyboard-accessible noscript/unavailable state and does not silently reuse stale embedded data.

### 9.4 Nightly ledger-only advancer

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
- appends at most one keep-FIRST prospective receipt;
- reruns idempotently.

`config/dag.yml` mirrors the actual hourly and nightly execution paths; it is not an executor.

### 9.5 No-regress publication

Before hourly publication, compare incoming `method_version`, `input_digest`, source watermarks and `evidence_cutoff` with the currently published artifact after a fresh source read.

- older cutoff/watermarks: refuse current-artifact overwrite;
- equal semantic identity: no-op;
- newer valid identity: publish;
- source failure/staleness transition: publish a truthful degraded status while preserving last-good evidence and watermark.

Because nightly is ledger-only, it cannot regress the current machine/UI artifact. No cross-lane lock service is introduced.

## 10. Prospective ledger

Path:

```text
data/policy_turn_clock/forward_log.jsonl
```

Advance gate:

```python
engine.ledger_lane.nightly_advance_enabled()
```

Canonical environment is `COLLECT_LANE=nightly`; `US_LANE=nightly` is a legacy alias. Hourly never appends.

Receipt identity:

```text
(as_of, trigger_kind, trigger_id, method_version, input_digest)
```

Eligible first-seen triggers:

- material semantic state change;
- high-impact event enters 24 hours;
- OPEX enters T−2;
- post-OPEX enters T+1;
- observed month/quarter-end pulse first appears;
- standard VX settlement enters T−2 or rank-roll boundary first appears.

The receipt freezes method/input/source identity, evidence cutoff, state/basis, all axes, gaps, expected mechanism, confirmation/invalidation and predeclared outcome horizons. Corrections append linked rows and never rewrite the original.

## 11. CI ownership

After every active owner of `.github/ci/legacy-jobs.yml` is released, W1 may make the smallest additive existing-job composition:

- extend one compatible policy/front-facing logical job;
- name all four new test suites in executable pytest command(s);
- include each suite and exact source subject in the job path closure;
- add matching `.github/workflows/ci.yml` triggers;
- include `scripts/ci/daily_engine_regional_desk_builders.sh` and workflow/DAG subjects in the appropriate conformance closure;
- run the selected logical job through the canonical pack runner;
- preserve unrelated current-main lines;
- do not add a job, workflow, runner, planner, permission, trusted-executor, secret, concurrency or merge-control plane;
- do not use `config/unrun_test_baseline.json` as an escape hatch.

START-time collision census must inspect all open PRs and active branches/worktrees. A list frozen in this document is not sufficient.

## 12. User experience

Policy Watch hierarchy:

1. **Now** — state, what changed and one mechanism sentence.
2. **Support inventory** — option support/replacement and evidence quality.
3. **Flow and liquidity** — broad ETF lagged flow, Treasury/TGA, observed rebalance and duration context.
4. **Futures clocks** — quarterly equity/Treasury and weekly/standard VX kept separate.
5. **Next 72 hours / 14 days** — at most five highest-information official events/operations with exact ET time, status, amount fields and freshness.
6. **Why this can turn** — mechanism chain, not prediction prose.
7. **Confirm / invalidate** — at most three concise observable conditions each.
8. **Coverage** — stale, unavailable, conflicting and corrected evidence.
9. **Evidence detail** — source links, exact clocks, input digest, OI/dealer caveats and raw axes.

Required states: fresh, quiet, partial, stale, failed, recovered, cancelled, revised, conflicting, virtual/prerecorded, unknown and source-shape-changed.

Required viewports/themes/languages: 1440, 768 and 390 CSS pixels; dark/light; English/Simplified Chinese. State meaning cannot rely on color.

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
NO_REGRESS_REFUSAL
LEDGER_LANE_REFUSED
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
10. Broad-flow lag/short-history disclosure and no option-replacement-as-cash shortcut.
11. Month-end scheduled/estimated/observed separation and asset-specific duration context.
12. Quiet healthy hourly rerun produces byte-identical tracked outputs and no commit candidate.
13. Real source failure/recovery transition updates status without erasing last-good evidence.
14. Older cutoff cannot overwrite a newer current artifact.
15. Hourly append is refused; nightly ledger-only appends exactly once and reruns idempotently.
16. All new suites execute through the canonical logical job and pack runner.
17. Browser proof at all required states/viewports/themes/languages.
18. One direct machine consumer reads the exact JSON contract.
19. One prospective receipt freezes before a real eligible event/transition.
20. Static/mutation proof keeps every authority field false and kills duplicate-plane attempts.

CI green is necessary but is not product or production acceptance.

## 15. Stop condition

The W1 worker stops at one immutable Draft/HOLD-FOR-SOL implementation PR proving the complete official-source → deterministic artifact → Policy Watch → machine consumer → prospective receipt vertical.

Do not absorb:

- RIC F3 yield implementation;
- yield-cause decomposition;
- actor reaction-function forecasting;
- commodity delivery-month calendars;
- Prophet/risk/portfolio wiring;
- capital authority;
- evaluation-lab outcome computation;
- merge or deployment.

Return exact receiver, carrier receipts, pickup base/current main, head/tree/parents, changed paths, collision census, RED→GREEN evidence, selected logical CI job/executed-suite proof, hosted checks, official-source receipts, artifact digest, browser/machine proof, prospective receipt identity, authority diff and remaining gaps.