# Actor, Liquidity & Monthly Transition Clock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to execute this plan task by task. Use superpowers:test-driven-development for every implementation task and superpowers:verification-before-completion before every success claim.

**Goal:** Build one deterministic official-source-to-product clock that shows whether monthly market support is building, stable, pinned, expiring, replaced, overridden by a catalyst, or unknown—without creating a duplicate event/market owner or any trade authority.

**Architecture:** Normalize bounded Fed, Treasury and TreasuryDirect observations into the existing keep-FIRST evidence pattern; extend the canonical event calendar with latest valid official events and quarterly futures-roll context; compose existing OPEX/options/rebalance/TGA owners through a pure `policy_turn_clock.v1` engine; publish one machine JSON, one Policy Watch component and one immutable prospective receipt. Reuse the existing hourly White House sentinel and the canonical nightly ledger gate. Do not create another scheduler, calendar, lifecycle, options plane, TGA plane, score or recommendation path.

**Tech stack:** Python 3.12, dataclasses, `requests`, `pandas`/Parquet, XML/XSD-aware parsing, Jinja2, pytest, PyYAML, GitHub Actions and Playwright.

**Design:** `docs/superpowers/specs/2026-09-03-actor-liquidity-monthly-transition-clock-design.md`

**Canonical carrier:** Macro issue #6787, operation `policy-preturn-actor-liquidity-calendar-clock-20260903-sol-001`.

## Binding corrections from source-law self-review

These values are exact and must not be substituted:

1. Treasury buybacks are discovered from the official TreasuryDirect buyback surface:

```text
index / operation-link discovery:
https://www.treasurydirect.gov/auctions/announcements-data-results/buy-backs/

tentative schedule XML:
https://home.treasury.gov/system/files/221/Tentative-Buyback-Schedule.xml

buyback XSD:
https://www.treasurydirect.gov/xsd/buyback-schema.xsd
```

The index exposes per-operation preliminary-announcement, final-announcement and results XML links plus CSV/Excel table export. The collector must discover those current links from the official index and validate expected XML structure. It must **not** use the auction `TA_WS/securities/auctioned` endpoint as a buyback source. For XML files published after May 29, 2025, preserve `<announcementType>` (`Preliminary`, `Final`, or empty for results) and `<operationStatus>` (`Released`, `Extended`, `Cancelled`, or `Results`). Operation start/close datetimes carry the current Eastern Time UTC offset and must remain offset-aware.

2. The canonical forward-ledger gate is `engine.ledger_lane.nightly_advance_enabled()`, which reads `COLLECT_LANE=nightly` and accepts `US_LANE=nightly` only as a legacy alias. The hourly workflow must set:

```yaml
env:
  COLLECT_LANE: hourly
```

or leave both variables non-nightly. `MMX_LEDGER_LANE` is not a real gate and is forbidden in this implementation.

## Global constraints

- Re-pin protected `mastermindx-market-intelligence/Mastermind` Skillpack before pickup, START, review and release.
- Post `PICKUP_ACK` and a separate `START` only after the records architecture is merged and a fresh exact path/collision census clears.
- Do not edit:

```text
engine/yield_momentum.py
engine/rates_inflation_command.py
scripts/build_rates_command.py
.github/ci/legacy-jobs.yml
agentos/workstreams/WS-RATES-INFLATION-COMMAND.md
```

- Consume rather than duplicate `engine/event_calendar.py`, `engine/event_window.py`, `engine/opex.py`, `engine/options_surface.py`, `engine/opex_risk.py`, `engine/rebalance_calendar.py`, `engine/rebalance_pulse.py` and `engine/treasury_watch.py`.
- Calendar proximity never ranks, gates, sizes, recommends or originates a trade.
- Every action-time datetime is timezone-aware; missing, false, zero and not-applicable remain distinct.
- Official-event history is append-only/keep-FIRST; revisions and cancellations append vintages rather than overwriting evidence.
- Hourly builds never advance the prospective ledger; nightly remains its sole advancer.
- No LLM call is permitted in the W1 source, state or UI path.
- One implementation PR only. It remains Draft/HOLD-FOR-SOL through exact-head review.

## Exact implementation surface

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

### Existing source files modified

```text
engine/event_calendar.py
scripts/build_policy_watch.py
templates/policy_watch.html.j2
tests/test_policy_watch_ui.py
config/dag.yml
.github/workflows/whitehouse-sentinel.yml
.github/workflows/ci.yml
```

`tests/test_dag_conformance.py` may be modified only if the current DAG/workflow conformance owner requires an explicit expected row; declare it in the START path census before editing.

### Generated/evidence outputs

```text
data/policy_events/official_events.parquet
data/policy_events/collector_status.json
data/policy_turn_clock/forward_log.jsonl
site/policy_turn_clock.json
site/policy_watch.html
mockups/refs/policy-turn-clock/**
```

Generated files are never hand-edited.

---

## Task 0: Pickup, collision census and isolated carrier

**Files:** no source edit.

- [ ] Re-read issue #6787, architecture PR #6788, RIC F3 PR #6721, collision PR #6658, workstream-record PR #6593, current Macro main and protected Skillpack.
- [ ] Post `PICKUP_ACK` to issue #6787 with exact receiver/session, GitHub principal and `effect=NONE`.
- [ ] Create one branch/worktree from fresh `origin/main` using the operation key; record branch, worktree and common-dir.
- [ ] Compare every planned path against every open PR and active same-program branch. If any path is owned, post `BLOCKED PATH_COLLISION effect=NONE` with the exact competing carrier and stop.
- [ ] Post a separate `START` only when the records architecture is merged, current main is pinned, path census is clean, worktree is clean and the branch has no prior effect uncertainty.

Verification commands:

```bash
git fetch origin main
git rev-parse origin/main
git status --short
git worktree list --porcelain
git branch --show-current
git diff --name-only origin/main...HEAD
```

No commit is created in Task 0.

---

## Task 1: Official event, buyback and actor-presence evidence

**Files:**

```text
create collectors/policy_event_clock.py
create tests/test_policy_event_clock.py
reuse  collectors/_first_seen_store.py
```

### Public interface

```python
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from collections.abc import Mapping, Sequence
import requests

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


def actor_presence(
    records: Sequence[Mapping[str, object]], *, actor_id: str, now: datetime
) -> dict[str, object]: ...


def persist_rows(rows: Sequence[Mapping[str, object]], *, root: Path) -> int: ...


def collect(
    *, now: datetime, session: requests.Session | None = None,
    root: Path | None = None
) -> CollectionResult: ...
```

### Frozen row schema

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

Money is USD billions. An absent source amount remains null.

### TDD sequence

- [ ] Write a failing test that normalizes a Fed event with exact Eastern offset, actor role and city-level location and asserts `FACT`, `official_public` and a 64-character digest.
- [ ] Write a failing test that a timezone-naive `observed_at` raises `ValueError("datetime must be timezone-aware")`.
- [ ] Write a failing test that normalizes one buyback record with:

```python
raw = {
    "source_event_id": "buyback-2026-09-03-174000Z",
    "announcement_type": "Final",
    "operation_status": "Released",
    "operation_kind": "cash_management",
    "operation_start": "2026-09-03T13:40:00-04:00",
    "operation_end": "2026-09-03T14:00:00-04:00",
    "settlement_date": "2026-09-04",
    "announced_max_usd": "12500000000",
    "submitted_usd": "20100000000",
    "accepted_usd": "12400000000",
    "instrument_scope": "1-month to 2-year nominal coupons",
    "source_url": "https://www.treasurydirect.gov/auctions/announcements-data-results/buy-backs/",
}
```

Assert `12.5`, `20.1` and `12.4` remain three different fields.
- [ ] Write failing XML fixture tests for `Preliminary/Released`, `Final/Extended`, `Final/Cancelled` and empty-announcement-type/`Results`. Assert cancellation and extension remain separate vintages and statuses.
- [ ] Write a failing test that the collector starts from `BUYBACK_INDEX_URL`, discovers per-operation XML links and does not call any URL containing `TA_WS/securities/auctioned`.
- [ ] Write a failing test that an unexpected XML root/required-element set produces source status `failed` with `SOURCE_SHAPE_CHANGED`; zero valid rows may be healthy only when the official index and expected table/XML structure are present.
- [ ] Write failing tests that `current_records` preserves all stored vintages but projects the latest valid revision by `available_at`, then `observed_at`, then digest.
- [ ] Write failing tests that an actor location is current only inside its official event window; after the end it becomes `current_location=None`, `current_location_status="unknown"`, while `last_verified_location` remains.
- [ ] Write a failing test that two overlapping different official locations produce `current_location_status="conflicting"` and retain both candidate receipts.
- [ ] Write a failing test that a cancelled event cannot support current location.
- [ ] Write a failing test that `persist_rows` delegates to `collectors._first_seen_store.accrue_keep_first` with key `['source_key','source_event_id','source_revision']`.
- [ ] Write a failing test that a present-but-unreadable Parquet store is not overwritten.

Run RED:

```bash
python -m pytest tests/test_policy_event_clock.py -q
```

Expected before implementation: import failure or failing assertions. Record the exact failure count.

### Implementation

- [ ] Define these constants exactly:

```python
PARSER_VERSION = "policy_event_clock.v1"
FED_BOARD_CALENDAR_URL = "https://www.federalreserve.gov/newsevents/calendar.htm"
TREASURY_PRESS_URL = "https://home.treasury.gov/news/press-releases"
BUYBACK_INDEX_URL = "https://www.treasurydirect.gov/auctions/announcements-data-results/buy-backs/"
BUYBACK_SCHEDULE_XML_URL = "https://home.treasury.gov/system/files/221/Tentative-Buyback-Schedule.xml"
BUYBACK_XSD_URL = "https://www.treasurydirect.gov/xsd/buyback-schema.xsd"
EVENT_KEY = ["source_key", "source_event_id", "source_revision"]
```

- [ ] Implement `_require_aware`, canonical timestamp conversion, deterministic JSON hashing and explicit USD-to-billions conversion.
- [ ] Implement one `_finalize_row` that fills every schema field, rejects missing source identity/URL, and hashes source-semantic content before observation metadata.
- [ ] Parse Fed Board and Treasury official HTML through explicit expected containers/fields; no broad article-text heuristics.
- [ ] From `BUYBACK_INDEX_URL`, discover the current tentative schedule and per-operation preliminary/final/results XML links. Parse XML against the expected XSD shape or an explicit checked element contract. Preserve announcement type, operation status, operation and settlement clocks, maturity bucket, maximum, total offered and total accepted.
- [ ] Do not infer `submitted_usd_bn` from accepted amount or vice versa.
- [ ] Implement `current_records` and `actor_presence` with deterministic conflict handling.
- [ ] Implement `persist_rows` through the existing keep-FIRST helper and atomic status JSON writing.
- [ ] Implement per-source collection boundaries, injected `requests.Session`, connect/read timeouts, a truthful status artifact and non-destructive failure behavior.
- [ ] Add `if __name__ == "__main__": raise SystemExit(main())` so `python -m collectors.policy_event_clock` is the production entry point.

Run GREEN:

```bash
python -m pytest tests/test_policy_event_clock.py -q
python -m py_compile collectors/policy_event_clock.py
git diff --check
```

Commit:

```bash
git add collectors/policy_event_clock.py tests/test_policy_event_clock.py
git commit -m "feat(policy-clock): add official event evidence contract"
```

---

## Task 2: Quarterly futures-roll context

**Files:**

```text
create engine/futures_roll_calendar.py
create tests/test_futures_roll_calendar.py
```

### Public interface

```python
from datetime import date
from collections.abc import Mapping


def equity_roll_window(d: date) -> dict[str, object]: ...

def treasury_roll_window(d: date) -> dict[str, object]: ...

def snapshot(
    asof: date, *, live_progress: Mapping[str, object] | None = None
) -> dict[str, object]: ...
```

### TDD sequence

- [ ] Write a failing test that August 10, 2026 returns `not_applicable` for both families.
- [ ] Write a failing test that September 14, 2026 returns equity contract month `2026-09`, roll start `2026-09-14`, expiry `2026-09-18`, lead `ESU6`, next `ESZ6`, status `scheduled`, progress null.
- [ ] Write a failing test that valid same-date/same-contract next-volume and next-open-interest shares move status to `active` and preserve `progress_basis="both"`.
- [ ] Write a failing test that stale, wrong-contract or impossible progress remains `scheduled` and emits an exact gap.
- [ ] Write a failing test that December 2026 maps `ESZ6` to `ESH7`.
- [ ] Write a failing test that Treasury context uses the final ten U.S. business days before the quarterly contract month and never claims instrument-level migration without supplied progress.
- [ ] Write a failing test that all authority fields are false.

Run RED:

```bash
python -m pytest tests/test_futures_roll_calendar.py -q
```

### Implementation

- [ ] Use quarterly codes `H`, `M`, `U`, `Z` and deterministic one-digit year symbols.
- [ ] Equity expiry is the third Friday of the contract month; customary roll start is the Monday of that week, adjusted through the repository’s accepted U.S. market calendar when available. A weekday fallback must be labeled `calendar_basis="weekday_fallback"`.
- [ ] Treasury schedule context is the final ten accepted U.S. business days before the first calendar day of the quarterly contract month.
- [ ] `active` requires valid progress supplied by an existing owner. `completed` requires a supplied next-contract share of at least 0.90 after roll start or an as-of date after the declared window.
- [ ] Output `futures_roll_calendar.v1` with separate equity/Treasury blocks, source basis, gaps and false authority fields.

Run GREEN:

```bash
python -m pytest tests/test_futures_roll_calendar.py -q
python -m py_compile engine/futures_roll_calendar.py
git diff --check
```

Commit:

```bash
git add engine/futures_roll_calendar.py tests/test_futures_roll_calendar.py
git commit -m "feat(policy-clock): add quarterly futures roll context"
```

---

## Task 3: Extend the canonical event calendar

**Files:**

```text
modify engine/event_calendar.py
modify tests/test_policy_event_clock.py
run all existing tests containing us_macro_events or high_impact_strip
```

### Public interface

```python
def policy_turn_events(
    today: date | None = None,
    horizon_days: int = 14,
    *,
    official_records: Sequence[Mapping[str, object]] | None = None,
    futures_roll: Mapping[str, object] | None = None,
) -> list[dict[str, object]]: ...
```

### TDD sequence

- [ ] Write a failing test that the result contains existing NFP/OPEX rows, one official actor event and one applicable futures-roll row.
- [ ] Write a failing non-regression test that calling `policy_turn_events` does not mutate or change `us_macro_events(...)` output.
- [ ] Write a failing test that exact owner-equivalent duplicates collapse but cross-owner conflicts remain as separate rows with one stable `conflict_group`.
- [ ] Write a failing test that every row is context-only and retains source/availability clocks.
- [ ] Write a failing test that a cancelled official event remains visible and cannot be projected as upcoming-active.

Run RED:

```bash
python -m pytest tests/test_policy_event_clock.py -q
```

### Implementation

- [ ] Begin with `list(us_macro_events(...))`; do not recreate its static/release logic.
- [ ] Add latest valid official records inside the horizon.
- [ ] Add futures roll start/expiry milestones only when applicable.
- [ ] Use stable owner identities for exact dedupe and a digest for conflict groups.
- [ ] Preserve owner discrepancies instead of selecting one silently.
- [ ] Leave current `us_macro_events`, `high_impact_strip` and existing consumers behaviorally unchanged.

Run GREEN:

```bash
python -m pytest tests/test_policy_event_clock.py -q
for f in $(git grep -l "us_macro_events\|high_impact_strip" tests | sort -u); do
  python -m pytest "$f" -q || exit 1
done
git diff --check
```

Commit:

```bash
git add engine/event_calendar.py tests/test_policy_event_clock.py
git commit -m "feat(policy-clock): extend canonical event composition"
```

---

## Task 4: Pure monthly transition composer

**Files:**

```text
create engine/policy_turn_clock.py
create tests/test_policy_turn_clock.py
```

### Public interface

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

No network, file, model or ledger I/O is allowed in this module.

### Required output

```json
{
  "schema": "policy_turn_clock.v1",
  "as_of": "YYYY-MM-DD",
  "generated_at": "offset-aware timestamp",
  "evidence_cutoff": "offset-aware timestamp",
  "state": "SUPPORT_BUILDING|SUPPORT_STABLE|PINNED|SUPPORT_ROLLOFF_IMMINENT|VOLATILITY_WINDOW_OPEN|MONTH_END_REBALANCE_DOMINANT|CATALYST_DOMINANT|MIXED|UNKNOWN",
  "state_basis": [],
  "change_from_prior": {},
  "calendar": {},
  "actor_clock": {},
  "treasury_liquidity": {},
  "option_support": {},
  "futures_roll": {},
  "rebalance": {},
  "catalysts": [],
  "confirmation": [],
  "invalidation": [],
  "disagreements": [],
  "gaps": [],
  "freshness": {},
  "authority": {"can_rank": false, "can_gate": false, "can_size": false, "can_trade": false}
}
```

### TDD sequence

Create fixture helpers inside `tests/test_policy_turn_clock.py` for:

- OPEX T−1 / T+1 / outside-window states with explicit `available_at`;
- a stabilizing long-gamma/pin OPEX-risk payload with dealer-sign and vanna passports;
- a destabilizing short-gamma payload;
- comparable prior/current SPY option-surface rows with `fm_oi_frac`, `fm_gex_bn`, `bk_gex_bn`, `fw_oi_frac`, root class and availability;
- current Treasury neutral/supportive/draining/stale payloads;
- quiet and non-quiet Rebalance Pulse payloads;
- current and scheduled futures-roll payloads;
- high-impact event rows with exact timestamps.

Write and observe RED for these exact cases:

- [ ] Calendar proximity alone produces `MIXED` or `UNKNOWN`, never support direction.
- [ ] Stabilizing support near expiry plus unknown replacement produces `SUPPORT_ROLLOFF_IMMINENT`.
- [ ] Short-gamma expiration cannot produce `VOLATILITY_WINDOW_OPEN` automatically and emits the invalidation `short_gamma_expiry_can_remove_destabilizing_inventory`.
- [ ] `VOLATILITY_WINDOW_OPEN` requires prior observed stabilizing support, its rolloff and independent realized confirmation from an existing owner.
- [ ] Long-gamma plus pin proximity plus compressed-range context produces `PINNED` only when no higher-precedence catalyst/rebalance state exists.
- [ ] Comparable later option rows with rising front-month/back inventory produce replacement `building`; missing rows produce `unknown`; wrong root class produces `incomparable`.
- [ ] A high-impact event inside 24 hours plus a collision predicate produces `CATALYST_DOMINANT`.
- [ ] A valid late-month/quarter-end window plus observed non-quiet Rebalance Pulse produces `MONTH_END_REBALANCE_DOMINANT`; calendar eligibility alone remains `scheduled_unconfirmed`.
- [ ] Supportive replacement and draining Treasury liquidity produce `MIXED` with a disagreement row.
- [ ] Missing calendar plus at least two missing core mechanism families produces `UNKNOWN` and exact gaps.
- [ ] Stale Treasury data is `stale`, never neutral.
- [ ] Fixed inputs and reversed input order produce byte-equivalent semantic output.
- [ ] Authority fields remain false and top-level forbidden fields `score`, `probability`, `position_size`, `order`, `recommendation` are absent.
- [ ] Output strings do not contain `bullish`, `bearish`, `buy` or `sell` as state semantics.

Run RED:

```bash
python -m pytest tests/test_policy_turn_clock.py -q
```

### Implementation

Implement small typed private helpers:

```python
def _calendar_axis(now, events, opex, rebalance_calendar, futures_roll): ...
def _replacement_book(option_surface): ...
def _option_axis(now, opex, opex_risk, option_surface): ...
def _treasury_axis(treasury): ...
def _rebalance_axis(rebalance_calendar, rebalance_pulse): ...
def _catalyst_axis(now, events): ...
def _select_state(axes, prior_clock): ...
def _changes(prior_clock, axes, state): ...
```

The deterministic precedence is:

1. `UNKNOWN` when no valid current calendar plus at least two core mechanism families are unavailable/stale.
2. `CATALYST_DOMINANT` for a valid high-impact event inside 24 hours plus a collision/override predicate.
3. `MONTH_END_REBALANCE_DOMINANT` for a valid window plus observed non-quiet pulse.
4. `VOLATILITY_WINDOW_OPEN` only after prior stabilizing support rolls off and an independent existing owner confirms realized deterioration/expansion.
5. `SUPPORT_ROLLOFF_IMMINENT` at OPEX T−2 through T+1 when stabilizing support exists/recently existed and replacement is weak or unknown.
6. `PINNED` for valid long-gamma, pin and compressed-range context.
7. `SUPPORT_BUILDING` for replacement `building` without contradiction.
8. `SUPPORT_STABLE` for current stabilizing support without override.
9. `MIXED` otherwise.

Each chosen state lists the exact selecting predicates in `state_basis`. Use a frozen EN/ZH phrase registry for confirmation/invalidation; never use an LLM.

Run GREEN:

```bash
python -m pytest tests/test_policy_turn_clock.py -q
python -m py_compile engine/policy_turn_clock.py
! git grep -n "policy_turn_clock" -- 'engine/conditions.py' 'engine/risk_sizing.py' 'engine/prophet*' 'engine/*order*'
! git grep -nE '"(score|probability|position_size|order|recommendation)"[[:space:]]*:' engine/policy_turn_clock.py
git diff --check
```

Commit:

```bash
git add engine/policy_turn_clock.py tests/test_policy_turn_clock.py
git commit -m "feat(policy-clock): compose monthly transition state"
```

---

## Task 5: Builder, machine artifact and prospective receipt

**Files:**

```text
create scripts/build_policy_turn_clock.py
create tests/test_build_policy_turn_clock.py
reuse  engine/ledger_lane.py
```

### Public interface

```python
def gather_inputs(*, root: Path, now: datetime) -> dict[str, object]: ...
def build_payload(*, root: Path, now: datetime) -> dict[str, object]: ...
def write_payload(payload: Mapping[str, object], *, root: Path) -> Path: ...
def append_forward_receipt(payload: Mapping[str, object], *, root: Path) -> bool: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```

### TDD sequence

- [ ] Empty root writes a schema-shaped `UNKNOWN` artifact rather than disappearing.
- [ ] JSON write uses `site/policy_turn_clock.json.tmp`, flush/fsync and `os.replace`.
- [ ] A failed source keeps prior event evidence while surfacing a collector-status gap.
- [ ] One stale owner does not erase fresh independent axes.
- [ ] `gather_inputs` reads current owner artifacts only and never calls network functions.
- [ ] Comparable option rows retain root class, observation and availability clocks.
- [ ] `append_forward_receipt` returns false and creates no file when `nightly_advance_enabled()` is false.
- [ ] With the gate true, one eligible trigger appends exactly one keep-FIRST row; a rerun appends none.
- [ ] A correction appends a linked correction row and preserves `original_evidence_cutoff`.
- [ ] No backfill or wall-clock rewrite can manufacture a prospective vintage.

Run RED:

```bash
python -m pytest tests/test_build_policy_turn_clock.py -q
```

### Implementation

- [ ] `gather_inputs` reads:
  - `data/policy_events/official_events.parquet` and collector status;
  - `policy_event_clock.current_records`;
  - `event_calendar.policy_turn_events`;
  - `futures_roll_calendar.snapshot`;
  - `engine.opex.snapshot` over the existing canonical SPY close series;
  - current `opex_risk` output or its current snapshot seam;
  - latest comparable canonical option-surface rows;
  - `rebalance_calendar.tag(now.date())` plus the current rebalance-pulse artifact;
  - `treasury_watch.snapshot`.
- [ ] Every adapter returns source owner, clocks, unit and null reason; it does not substitute an alternate source.
- [ ] `build_payload` calls the pure composer and always returns a contract-shaped mapping.
- [ ] `write_payload` is deterministic for an injected clock and atomic.
- [ ] `append_forward_receipt` imports `nightly_advance_enabled` from `engine.ledger_lane` and uses it without a local shadow gate.
- [ ] Eligible triggers are: material state change, high-impact event enters 24h, OPEX T−2, post-OPEX T+1, or first observed month-/quarter-end non-quiet pulse.
- [ ] Receipt identity is `(as_of, trigger_kind, trigger_id, method_version)`; keep-FIRST.
- [ ] Add a CLI `--root` argument and `if __name__ == "__main__"` production entry.

Run GREEN:

```bash
python -m pytest tests/test_build_policy_turn_clock.py -q
python -m scripts.build_policy_turn_clock --root "$(mktemp -d)"
python -m py_compile scripts/build_policy_turn_clock.py
git diff --check
```

Commit:

```bash
git add scripts/build_policy_turn_clock.py tests/test_build_policy_turn_clock.py
git commit -m "feat(policy-clock): build artifact and prospective receipt"
```

---

## Task 6: Policy Watch decision composition

**Files:**

```text
create templates/partials/_policy_turn_clock.html.j2
modify scripts/build_policy_watch.py
modify templates/policy_watch.html.j2
modify tests/test_policy_watch_ui.py
generate site/policy_watch.html
generate mockups/refs/policy-turn-clock/**
```

### TDD sequence

- [ ] Assert `scripts/build_policy_watch.py` reads `site/policy_turn_clock.json`, passes `turn_clock=turn_clock` and never imports/calls `policy_turn_clock.compose`.
- [ ] Assert `templates/policy_watch.html.j2` includes the partial exactly once.
- [ ] Assert the partial contains stable hooks:

```text
data-ptc-state
ptc-now
ptc-support
ptc-next
ptc-confirm
ptc-invalidate
ptc-coverage
l-en
l-zh
```

- [ ] Assert fresh, partial, stale, cancelled, conflicting and unknown fixtures render visibly and preserve exact event times/amount distinctions.
- [ ] Assert labels have EN/ZH twins and raw source strings are escaped.
- [ ] Assert component text contains no buy/sell/bullish/bearish/position-size language.
- [ ] Assert state meaning is present in text and not conveyed by color alone.

Run RED:

```bash
python -m pytest tests/test_policy_watch_ui.py -q
```

### Implementation

- [ ] Defensively load `site/policy_turn_clock.json`; wrong schema becomes an explicit unavailable component, not suppression.
- [ ] Render this hierarchy:
  1. **Now** — state, what changed, one mechanism sentence.
  2. **Support inventory** — OPEX/options, futures and month-end phase.
  3. **Next 72 hours** — at most five exact official events/operations.
  4. **Confirm / invalidate** — at most three rows each.
  5. **Coverage** — stale/unavailable/conflicting source chips.
  6. **Evidence detail** — clocks, source links, announced/accepted amounts and options passports.
- [ ] Use one-column default and two-column detail at `min-width:768px`; no fixed card heights; `overflow-wrap:anywhere` for source/event strings.
- [ ] Preserve dark/light, EN/ZH, keyboard navigation and 390px layout.

Run GREEN:

```bash
python -m pytest tests/test_policy_watch_ui.py -q
python -m scripts.build_policy_turn_clock
python -m scripts.build_policy_watch
python -m scripts.check_template_site_sync
python -m scripts.check_design_system --mode enforce-added
python -m scripts.check_ui_visual_evidence
git diff --check
```

### Browser proof

Start:

```bash
python -m http.server 8765 --directory site >/tmp/policy-turn-clock-http.log 2>&1 &
echo $! >/tmp/policy-turn-clock-http.pid
```

Capture 1440, 768 and 390 viewports in dark/light and EN/ZH using Playwright. Before navigation, set:

```javascript
localStorage.setItem('theme', theme);
localStorage.setItem('lang', lang);
```

For every case assert exactly one `[data-ptc-state]` component, a non-null bounding box, no horizontal overflow and visible state text. Save full-page images under `mockups/refs/policy-turn-clock/`. Inspect every image and record repaired defects.

Stop server:

```bash
kill "$(cat /tmp/policy-turn-clock-http.pid)"
```

Commit:

```bash
git add scripts/build_policy_watch.py templates/partials/_policy_turn_clock.html.j2 templates/policy_watch.html.j2 tests/test_policy_watch_ui.py site/policy_watch.html mockups/refs/policy-turn-clock
git commit -m "feat(policy-clock): render pre-turn decision composition"
```

---

## Task 7: Existing hourly/nightly workflow, DAG and CI wiring

**Files:**

```text
modify config/dag.yml
modify .github/workflows/whitehouse-sentinel.yml
modify .github/workflows/ci.yml
conditionally modify tests/test_dag_conformance.py only if declared at START
```

### TDD sequence

- [ ] Add a failing conformance assertion that the existing White House sentinel contains these commands in order:

```text
python -m collectors.policy_event_clock
python -m scripts.build_policy_turn_clock
python -m scripts.build_policy_watch
```

- [ ] Assert the workflow retains one existing schedule block and does not create another workflow.
- [ ] Assert the clock-build step sets `COLLECT_LANE: hourly`.
- [ ] Assert the workflow and repository contain no `MMX_LEDGER_LANE` reference for this feature.
- [ ] Assert hourly commit allowlist includes official event/status and site artifacts but excludes `data/policy_turn_clock/forward_log.jsonl`.
- [ ] Assert `.github/ci/legacy-jobs.yml` is absent from the PR diff.

Run RED:

```bash
python -m pytest tests/test_dag_conformance.py -q
```

### Implementation

- [ ] Register collector → clock builder → Policy Watch consumer in `config/dag.yml` using the existing pipeline vocabulary. Mark official collection as bounded network I/O, clock composition deterministic, and forward ledger nightly-only.
- [ ] Reuse `.github/workflows/whitehouse-sentinel.yml`; add:

```yaml
- name: collect official policy event clock
  run: python -m collectors.policy_event_clock

- name: build policy turn clock
  env:
    COLLECT_LANE: hourly
  run: python -m scripts.build_policy_turn_clock

- name: rebuild policy watch
  run: python -m scripts.build_policy_watch
```

- [ ] Extend only the existing commit allowlist with:

```text
data/policy_events/official_events.parquet
data/policy_events/collector_status.json
site/policy_turn_clock.json
site/policy_watch.html
```

Do not include the forward ledger.
- [ ] Add the new tests/source paths to the nearest existing rates/policy/options CI owner in `.github/workflows/ci.yml`. Do not create a new CI authority and do not edit the colliding legacy manifest.

Run GREEN:

```bash
python -m pytest tests/test_policy_event_clock.py tests/test_futures_roll_calendar.py tests/test_policy_turn_clock.py tests/test_build_policy_turn_clock.py tests/test_policy_watch_ui.py tests/test_dag_conformance.py -q
python - <<'PY'
from pathlib import Path
import yaml
for path in (
    Path('.github/workflows/whitehouse-sentinel.yml'),
    Path('.github/workflows/ci.yml'),
    Path('config/dag.yml'),
):
    yaml.safe_load(path.read_text())
    print(f'valid {path}')
PY
! git grep -n 'MMX_LEDGER_LANE' -- collectors/policy_event_clock.py engine/policy_turn_clock.py scripts/build_policy_turn_clock.py .github/workflows/whitehouse-sentinel.yml
! git diff --name-only origin/main...HEAD | grep -Fx '.github/ci/legacy-jobs.yml'
git diff --check
```

Commit:

```bash
git add config/dag.yml .github/workflows/whitehouse-sentinel.yml .github/workflows/ci.yml
if ! git diff --quiet -- tests/test_dag_conformance.py; then git add tests/test_dag_conformance.py; fi
git commit -m "ci(policy-clock): wire existing hourly and nightly lanes"
```

---

## Task 8: Real-source, product, machine and prospective proof

**Outputs:**

```text
data/policy_events/official_events.parquet
data/policy_events/collector_status.json
data/policy_turn_clock/forward_log.jsonl when a truthful nightly trigger is eligible
site/policy_turn_clock.json
site/policy_watch.html
mockups/refs/policy-turn-clock/**
```

- [ ] Re-fetch protected procedure, current Macro main, issue #6787, architecture PR #6788, RIC F3 PR #6721, PR #6658 and PR #6593. Re-run exact planned-path collision census. Stop on collision.
- [ ] Run the real collector:

```bash
python -m collectors.policy_event_clock
python - <<'PY'
import json
from pathlib import Path
import pandas as pd
p = Path('data/policy_events/official_events.parquet')
s = Path('data/policy_events/collector_status.json')
assert p.exists() and s.exists()
rows = pd.read_parquet(p)
status = json.loads(s.read_text())
assert not rows.empty
assert status['schema'] == 'policy_event_collector_status.v1'
assert {'source_key','source_event_id','source_revision','available_at','content_sha256'}.issubset(rows.columns)
print(rows.groupby('source_key').size().to_dict())
print(json.dumps(status, indent=2, sort_keys=True))
PY
```

- [ ] Record each source’s last attempt/success, row counts, HTTP/parser status and gaps. A failed source is partial coverage, not completion.
- [ ] Build current artifacts:

```bash
python -m scripts.build_policy_turn_clock
python -m scripts.build_policy_watch
python - <<'PY'
import hashlib, json
from pathlib import Path
p = Path('site/policy_turn_clock.json')
payload = json.loads(p.read_text())
assert payload['schema'] == 'policy_turn_clock.v1'
assert payload['authority'] == {'can_rank': False, 'can_gate': False, 'can_size': False, 'can_trade': False}
print('state', payload['state'])
print('gaps', payload['gaps'])
print('sha256', hashlib.sha256(p.read_bytes()).hexdigest())
PY
```

- [ ] Prove a direct machine consumer reads the JSON rather than HTML:

```bash
python - <<'PY'
import json
from pathlib import Path
p = json.loads(Path('site/policy_turn_clock.json').read_text())
view = {
    'state': p['state'],
    'next_event': (p.get('catalysts') or [None])[0],
    'treasury': p.get('treasury_liquidity'),
    'option_support': p.get('option_support'),
    'confirm': p.get('confirmation', [])[:3],
    'invalidate': p.get('invalidation', [])[:3],
}
assert view['state']
print(json.dumps(view, indent=2, sort_keys=True))
PY
```

- [ ] Freeze a prospective receipt only when the real accepted nightly lane and a real trigger are present. Never set `COLLECT_LANE=nightly` manually to manufacture evidence. If no trigger is eligible, report `PROSPECTIVE_TRIGGER_NOT_YET_ELIGIBLE` and leave the ledger untouched.
- [ ] Verify any receipt has `trigger_kind`, `trigger_id`, `method_version`, `original_evidence_cutoff`, state, confirmation and invalidation.
- [ ] Run browser proof from Task 6 on the real artifact plus source-faithful partial/stale/cancelled/conflicting/unknown fixtures.

### Complete verification

```bash
python -m pytest tests/test_policy_event_clock.py tests/test_futures_roll_calendar.py tests/test_policy_turn_clock.py tests/test_build_policy_turn_clock.py tests/test_policy_watch_ui.py tests/test_dag_conformance.py -q
python3 scripts/agentos.py validate
python -m scripts.check_template_site_sync
python -m scripts.check_design_system --mode enforce-added
python -m scripts.check_ui_visual_evidence
python -m compileall -q collectors/policy_event_clock.py engine/futures_roll_calendar.py engine/policy_turn_clock.py scripts/build_policy_turn_clock.py
git diff --check
git status --short
```

Run the repository’s exact current semantic CI or push one immutable candidate and wait for hosted CI. Focused green is not full green.

### Required mutation kills

Temporarily create and kill these mutants one at a time; restore the clean tree after each:

1. collapse accepted amount into announced maximum;
2. keep-LAST instead of keep-FIRST;
3. leave expired actor location current;
4. accept unexpected buyback XML shape;
5. mark quarterly roll active without live progress;
6. let OPEX date alone produce rolloff/volatility state;
7. let calendar-only month-end become dominant;
8. remove dealer-sign or OI-timing passport;
9. set any authority field true;
10. permit hourly forward-ledger append;
11. suppress stale-source gaps;
12. add a buyback call to `TA_WS/securities/auctioned`.

Record the exact test that fails for each mutant.

### Return and stop

Open one Draft/HOLD-FOR-SOL implementation PR and post one same-carrier `RESULT / HOLD-FOR-SOL` on issue #6787 containing:

```text
operation key
protected procedure SHA
pickup/current-main SHA
exact head/tree
exact changed paths
collision census
PICKUP_ACK and START receipts
RED-before-GREEN evidence
focused and hosted CI
source receipts/freshness/gaps
artifact SHA-256
browser receipts
machine-consumer proof
prospective receipt or truthful not-yet-eligible state
mutation kills
known gaps and exact next bounded wave
```

Do not mark Ready, add merge-on-green, enable auto-merge, merge, deploy, start PTC-W2/PTC-W3 or change Prophet/portfolio authority. Preserve the worker continuation path until Sol issues explicit `CONTINUE` or terminal `STOP`.
