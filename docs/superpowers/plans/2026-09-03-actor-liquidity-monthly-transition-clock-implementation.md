# Actor, Liquidity & Monthly Transition Clock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` or `superpowers:executing-plans` task by task. Use `superpowers:test-driven-development` for every source change and `superpowers:verification-before-completion` before every success claim.

**Goal:** Build one correction-safe official-source-to-product clock that explains whether monthly market support is building, stable, pinned, rolling off, replaced, contradicted or overridden—without creating a duplicate market owner or any capital authority.

**Architecture:** An hourly single-writer lane normalizes official Fed/Treasury evidence and publishes one current `policy_turn_clock.v1` JSON. A pure composer receives explicit canonical option, Treasury/TGA, broad-flow, rebalance, futures, duration and market-confirmation inputs. The existing nightly regional-desk lane invokes the same builder in ledger-only mode to freeze prospective receipts without republishing current state. Policy Watch loads the same-origin JSON; the canonical CI manifest executes every new suite.

**Tech stack:** Python 3.12, dataclasses, `zoneinfo`, `requests`, `pandas`/Parquet, XML/XSD-aware parsing, Jinja2, vanilla browser JavaScript, pytest, PyYAML, GitHub Actions and Playwright.

**Spec:** `docs/superpowers/specs/2026-09-03-actor-liquidity-monthly-transition-clock-design.md`

**Canonical carrier:** Macro issue #6787, operation `policy-preturn-actor-liquidity-calendar-clock-20260903-sol-001`.

## Global constraints

- Re-pin current protected `mastermindx-market-intelligence/Mastermind` Skillpack before pickup, START, review and release.
- Architecture PR #6788 must be accepted and merged before W1 START.
- Fresh-census every planned path against all open PRs, active branches/worktrees and started operations.
- `.github/ci/legacy-jobs.yml` must be collision-free before START; current historical owner lists are not sufficient.
- Do not edit:

```text
engine/yield_momentum.py
engine/rates_inflation_command.py
scripts/build_rates_command.py
agentos/workstreams/WS-RATES-INFLATION-COMMAND.md
collectors/cboe_vix_futures.py
```

- Consume canonical event, OPEX, options, rebalance, broad-flow, Treasury/TGA, VX, market-state, volatility and ledger owners.
- No network or filesystem I/O inside `engine/policy_turn_clock.py` or `engine/futures_roll_calendar.py`.
- All action-time datetimes are offset-aware. U.S. decision/session semantics normalize to `America/New_York`.
- Missing, false, zero, quiet, stale, conflicting and not-applicable remain distinct.
- Official evidence is append-only/keep-FIRST and correction-safe.
- Hourly is the sole official-event/current-artifact writer. Nightly is ledger-only.
- No model call is permitted in source normalization, composition, publication or UI interpretation.
- All `can_rank`, `can_gate`, `can_size`, and `can_trade` values remain false.
- One implementation PR only. It remains Draft/HOLD-FOR-SOL through exact-head review.

## File structure

### Create

```text
collectors/policy_event_clock.py       official evidence normalization/persistence only
engine/futures_roll_calendar.py        pure quarterly-roll and VX-settlement context
engine/policy_turn_clock.py            pure deterministic transition composition
scripts/build_policy_turn_clock.py     bounded I/O, modes, no-regress, prospective receipt
templates/partials/_policy_turn_clock.html.j2
                                      static shell/fallback for dynamic component
tests/test_policy_event_clock.py
tests/test_futures_roll_calendar.py
tests/test_policy_turn_clock.py
tests/test_build_policy_turn_clock.py
```

### Modify

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

`tests/test_dag_conformance.py` may be modified only after declaring the exact current expectation that requires it.

---

## Task 0: Pickup, path census and isolated carrier

**Files:** no source edit.

**Produces:** one clean worktree/branch, exact collision census, Pickup ACK, watcher receipt and separate START only when all gates are open.

- [ ] **Step 1: Fresh-read governing state**

Read current protected Skillpack, issue #6787, merged architecture, current Macro main, PR #6721, all open PRs touching planned paths, current worktrees and branch refs.

- [ ] **Step 2: Post Pickup ACK**

```text
PICKUP_ACK policy-preturn-actor-liquidity-calendar-clock-20260903-sol-001 receiver=<actual task/session> github=<actual principal> effect=NONE
```

- [ ] **Step 3: Arm or reuse one exact-carrier continuation source**

Post `WATCH_ARMED` or a truthful `WATCH_UNAVAILABLE`; do not create a second watcher for the same side/operation/carrier/purpose.

- [ ] **Step 4: Create the isolated worktree**

```bash
git fetch origin main
git worktree add ../policy-turn-clock-w1 -b codex/policy-turn-clock-w1-20260903 origin/main
cd ../policy-turn-clock-w1
git branch --show-current
git status --short
git rev-parse HEAD
git rev-parse --git-common-dir
```

Expected: correct branch, clean status, HEAD equal to the fresh `origin/main` pickup SHA.

- [ ] **Step 5: Run the complete collision census**

Check every path in the file structure above against all open PR file lists, active worktrees and local/remote branches. Explicitly census `.github/ci/legacy-jobs.yml`; do not assume release because one historical owner changed.

- [ ] **Step 6: Stop on collision or post START**

Collision response:

```text
BLOCKED PATH_COLLISION operation=policy-preturn-actor-liquidity-calendar-clock-20260903-sol-001 owner=<carrier> path=<path> effect=NONE
```

Clean response:

```text
START policy-preturn-actor-liquidity-calendar-clock-20260903-sol-001 base=<sha> branch=<branch> worktree=<path> effect=ISOLATED_SOURCE_AUTHORIZED
```

No commit is created in Task 0.

---

## Task 1: Official event, Treasury operation and actor-presence evidence

**Files:**

```text
Create: collectors/policy_event_clock.py
Create: tests/test_policy_event_clock.py
Reuse:  collectors/_first_seen_store.py
```

**Consumes:** official-public Fed/Treasury/TreasuryDirect responses, injected aware `now`, existing keep-FIRST helper.

**Produces:** normalized rows, current projection, actor-presence projection, atomic store/status writes and a source collection result.

### Interfaces

```python
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import requests

@dataclass(frozen=True)
class CollectionResult:
    rows_seen: int
    rows_added: int
    semantic_changes: int
    status_changed: bool
    status: dict[str, object]
    gaps: tuple[str, ...]


def normalize_fed_event(
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
    rows: Sequence[Mapping[str, object]], *, actor_id: str, now: datetime
) -> dict[str, object]: ...


def persist_rows(rows: Sequence[Mapping[str, object]], *, root: Path) -> int: ...


def write_status_if_changed(
    status: Mapping[str, object], *, root: Path
) -> bool: ...


def collect(
    *, now: datetime, session: requests.Session | None = None,
    root: Path | None = None
) -> CollectionResult: ...
```

### Frozen enums and fields

```python
PARSER_VERSION = "policy_event_clock.v1"
EVENT_KEY = [
    "source_key", "source_event_id", "source_revision",
    "canonical_semantic_sha256",
]

RECORD_KINDS = {"actor_event", "treasury_operation"}
EVENT_KINDS = {"speech", "interview", "meeting", "testimony", "release", "other"}
OPERATION_KINDS = {
    "auction", "buyback", "cash_management_operation", "settlement",
    "tga_release", "tga_build", "other",
}
OPERATION_PURPOSES = {
    "cash_management", "liquidity_support", "funding", "market_function",
    "debt_management", "other",
}
ATTENDANCE_MODES = {"in_person", "virtual", "hybrid", "prerecorded", "unknown"}
```

### RED tests

- [ ] **Step 1: Write timezone and semantic-identity tests**

```python
def test_observed_at_must_be_aware():
    with pytest.raises(ValueError, match="datetime must be timezone-aware"):
        normalize_fed_event({"id": "x"}, observed_at=datetime(2026, 9, 3, 9, 0))


def test_formatting_only_change_keeps_semantic_digest():
    a = normalize_fed_event(FED_EVENT_HTML_A, observed_at=ET_NOW)
    b = normalize_fed_event(FED_EVENT_HTML_FORMATTING_ONLY, observed_at=ET_LATER)
    assert a["canonical_semantic_sha256"] == b["canonical_semantic_sha256"]
```

- [ ] **Step 2: Write buyback taxonomy/amount tests**

```python
def test_buyback_keeps_mechanism_purpose_and_amounts_separate():
    row = normalize_buyback_record({
        "source_event_id": "bb-2026-09-03",
        "announcement_type": "Final",
        "operation_status": "Released",
        "operation_type": "Cash Management",
        "operation_start": "2026-09-03T13:40:00-04:00",
        "operation_end": "2026-09-03T14:00:00-04:00",
        "settlement_date": "2026-09-04",
        "max_par_usd": "12500000000",
        "offered_par_usd": "20100000000",
        "accepted_par_usd": "12400000000",
        "source_url": BUYBACK_INDEX_URL,
    }, observed_at=ET_NOW)
    assert row["operation_kind"] == "buyback"
    assert row["operation_purpose"] == "cash_management"
    assert row["announced_max_usd_bn"] == 12.5
    assert row["offered_usd_bn"] == 20.1
    assert row["submitted_usd_bn"] is None
    assert row["accepted_usd_bn"] == 12.4
```

- [ ] **Step 3: Write actor-presence tests**

```python
def test_virtual_event_never_proves_physical_location():
    row = normalize_fed_event(VIRTUAL_EVENT, observed_at=ET_NOW)
    result = actor_presence([row], actor_id="powell", now=EVENT_MIDPOINT)
    assert result["current_physical_location"] is None
    assert result["attendance_mode"] == "virtual"
    assert result["current_location_status"] == "unknown"


def test_explicit_in_person_active_event_can_confirm_location():
    row = normalize_fed_event(IN_PERSON_EXPLICIT, observed_at=ET_NOW)
    result = actor_presence([row], actor_id="powell", now=EVENT_MIDPOINT)
    assert result["current_physical_location"] == "New York, NY"
    assert result["current_location_status"] == "publicly_confirmed"


def test_ended_event_expires_current_location_but_keeps_last_verified():
    row = normalize_fed_event(IN_PERSON_EXPLICIT, observed_at=ET_NOW)
    result = actor_presence([row], actor_id="powell", now=EVENT_END + timedelta(seconds=1))
    assert result["current_physical_location"] is None
    assert result["last_verified_location"] == "New York, NY"
```

- [ ] **Step 4: Write revision-collision tests**

```python
def test_same_explicit_revision_changed_semantics_is_collision():
    rows = [NORMALIZED_V1, NORMALIZED_SAME_REVISION_CHANGED]
    current = current_records(rows, now=ET_NOW)
    assert current[0]["projection_status"] == "revision_id_collision"
    assert len(current[0]["candidate_receipts"]) == 2
```

- [ ] **Step 5: Write persistence/no-op tests**

```python
def test_quiet_success_status_is_byte_stable(tmp_path):
    assert write_status_if_changed(SEMANTIC_STATUS, root=tmp_path) is True
    before = (tmp_path / "data/policy_events/collector_status.json").read_bytes()
    later = {**SEMANTIC_STATUS, "ephemeral_last_attempt_at": "2026-09-03T11:00:00-04:00"}
    assert write_status_if_changed(later, root=tmp_path) is False
    assert (tmp_path / "data/policy_events/collector_status.json").read_bytes() == before


def test_present_but_unreadable_store_is_not_replaced(tmp_path):
    p = tmp_path / "data/policy_events/official_events.parquet"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"not parquet")
    assert persist_rows([NORMALIZED_V1], root=tmp_path) == 0
    assert p.read_bytes() == b"not parquet"
```

Run RED:

```bash
python -m pytest tests/test_policy_event_clock.py -q
```

Expected: import failure or failing assertions. Record exact failures.

### Implementation

- [ ] **Step 6: Implement aware-time and canonical semantic hashing**

Canonicalize timestamps to ISO strings with offsets. Hash normalized semantic fields only; exclude `observed_at`, `first_seen`, ephemeral attempts and raw page chrome.

- [ ] **Step 7: Implement explicit source parsers**

Define exact constants:

```python
FED_BOARD_CALENDAR_URL = "https://www.federalreserve.gov/newsevents/calendar.htm"
TREASURY_PRESS_URL = "https://home.treasury.gov/news/press-releases"
BUYBACK_INDEX_URL = "https://www.treasurydirect.gov/auctions/announcements-data-results/buy-backs/"
BUYBACK_SCHEDULE_XML_URL = "https://home.treasury.gov/system/files/221/Tentative-Buyback-Schedule.xml"
BUYBACK_XSD_URL = "https://www.treasurydirect.gov/xsd/buyback-schema.xsd"
```

Discover current buyback preliminary/final/results XML links from the official index. Validate expected roots/elements. Never call a URL containing `TA_WS/securities/auctioned` for buybacks.

- [ ] **Step 8: Implement identity, current projection and actor presence**

Keep source status immutable, derive phase separately, preserve collisions, and require explicit live physical-presence evidence.

- [ ] **Step 9: Implement keep-FIRST persistence and semantic status writes**

Use `collectors._first_seen_store.accrue_keep_first` with `EVENT_KEY`. Write status atomically only when semantic status changes. Log attempts ephemerally.

- [ ] **Step 10: Verify GREEN**

```bash
python -m pytest tests/test_policy_event_clock.py -q
python -m py_compile collectors/policy_event_clock.py
git diff --check
```

- [ ] **Step 11: Commit**

```bash
git add collectors/policy_event_clock.py tests/test_policy_event_clock.py
git commit -m "feat(policy-clock): add correction-safe official evidence"
```

---

## Task 2: Quarterly futures and monthly VX settlement context

**Files:**

```text
Create: engine/futures_roll_calendar.py
Create: tests/test_futures_roll_calendar.py
```

**Produces:** pure `futures_roll_calendar.v1` with `equity_index`, `treasury`, and `volatility` families.

### Interfaces

```python
def equity_roll_window(d: date) -> dict[str, object]: ...
def treasury_roll_window(d: date) -> dict[str, object]: ...
def vix_settlement_window(
    d: date, *, front: Mapping[str, object] | None = None,
    curve: Mapping[str, object] | None = None,
    source_asof: date | None = None,
) -> dict[str, object]: ...
def snapshot(
    asof: date, *, live_progress: Mapping[str, object] | None = None,
    vix_front: Mapping[str, object] | None = None,
    vix_curve: Mapping[str, object] | None = None,
    vix_source_asof: date | None = None,
) -> dict[str, object]: ...
```

### RED tests

- [ ] **Step 1: Write quarterly-family tests**

```python
def test_august_equity_and_treasury_are_not_applicable():
    out = snapshot(date(2026, 8, 10))
    assert out["equity_index"]["status"] == "not_applicable"
    assert out["treasury"]["status"] == "not_applicable"


def test_september_equity_roll_is_scheduled_without_progress():
    out = snapshot(date(2026, 9, 14))
    assert out["equity_index"]["roll_start"] == "2026-09-14"
    assert out["equity_index"]["expiry"] == "2026-09-18"
    assert out["equity_index"]["status"] == "scheduled"
```

- [ ] **Step 2: Write VX calendar and weekly-front tests**

```python
def test_september_standard_vx_expiry_is_2026_09_16():
    out = vix_settlement_window(date(2026, 9, 1))
    assert out["standard_expiry"] == "2026-09-16"


def test_weekly_front_does_not_replace_standard_monthly():
    out = vix_settlement_window(
        date(2026, 9, 1),
        front={"front_settle": 18.0, "days_to_expiry": 1},
        curve={"m1_settle": 19.0, "m1_dte": 15, "m2_settle": 20.0, "m2_dte": 43},
        source_asof=date(2026, 9, 1),
    )
    assert out["front_is_weekly"] is True
    assert out["standard_expiry"] == "2026-09-16"
```

- [ ] **Step 3: Write curve and rank-roll tests**

```python
@pytest.mark.parametrize((m1, m2, expected), [
    (20.0, 20.3, "contango"),
    (20.0, 20.05, "flat"),
    (20.0, 19.6, "backwardation"),
])
def test_curve_state(m1, m2, expected):
    out = vix_settlement_window(
        date(2026, 9, 10),
        curve={"m1_settle": m1, "m1_dte": 6, "m2_settle": m2, "m2_dte": 34},
        source_asof=date(2026, 9, 10),
    )
    assert out["curve_state"] == expected


def test_rank_roll_never_claims_same_contract_change():
    out = vix_settlement_window(
        date(2026, 9, 17),
        curve={"m1_settle": 20.0, "m1_dte": 27, "m2_settle": 21.0, "m2_dte": 55,
               "prior_m1_dte": 0},
        source_asof=date(2026, 9, 17),
    )
    assert out["rank_roll_boundary"] is True
    assert out["same_contract_change_available"] is False
```

Run RED:

```bash
python -m pytest tests/test_futures_roll_calendar.py -q
```

### Implementation and verification

- [ ] **Step 4: Implement NYSE/Cboe-aware date helpers and quarterly codes**

Use existing calendar helpers where available. Do not use generic weekday arithmetic when exchange holidays control.

- [ ] **Step 5: Implement progress validation and VX source reconciliation**

Wrong contract/date, stale observation, impossible shares or computed/source expiry disagreement emit typed gaps and never produce `active`/current-looking state.

- [ ] **Step 6: Verify GREEN and commit**

```bash
python -m pytest tests/test_futures_roll_calendar.py -q
python -m py_compile engine/futures_roll_calendar.py
git diff --check
git add engine/futures_roll_calendar.py tests/test_futures_roll_calendar.py
git commit -m "feat(policy-clock): add futures transition context"
```

---

## Task 3: Extend the canonical event calendar

**Files:**

```text
Modify: engine/event_calendar.py
Test:   tests/test_policy_event_clock.py
Test:   tests/test_futures_roll_calendar.py
```

**Consumes:** `current_records(...)` and `futures_roll_calendar.snapshot(...)` outputs.

**Produces:** additive official-event and futures-context entries without a second calendar.

### Interfaces

```python
def merge_official_events(
    base_events: Sequence[Mapping[str, object]],
    official_events: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]: ...


def transition_context(
    *, asof: date, official_events: Sequence[Mapping[str, object]],
    futures: Mapping[str, object] | None,
) -> dict[str, object]: ...
```

- [ ] **Step 1: Write failing dedupe/correction tests**

Assert stable identity, latest-valid projection, cancellation retention, no duplicate event, and unchanged `is_context_only=True`/authority false.

- [ ] **Step 2: Write failing futures-context tests**

Assert weekly VX, standard VX and quarterly rolls remain separate; no event row contains direction, score or size.

- [ ] **Step 3: Run RED**

```bash
python -m pytest tests/test_policy_event_clock.py tests/test_futures_roll_calendar.py -q
```

- [ ] **Step 4: Implement minimal additive helpers**

Do not change existing release/OPEX behavior. No network calls enter `event_calendar.py` beyond its existing accepted boundaries.

- [ ] **Step 5: Verify and commit**

```bash
python -m pytest tests/test_policy_event_clock.py tests/test_futures_roll_calendar.py -q
python -m py_compile engine/event_calendar.py
git diff --check
git add engine/event_calendar.py tests/test_policy_event_clock.py tests/test_futures_roll_calendar.py
git commit -m "feat(policy-clock): compose official events into canonical calendar"
```

---

## Task 4: Pure `policy_turn_clock.v1` composer

**Files:**

```text
Create: engine/policy_turn_clock.py
Create: tests/test_policy_turn_clock.py
```

**Consumes:** all explicit inputs in the design interface.

**Produces:** deterministic, order-invariant, authority-false `policy_turn_clock.v1`.

### Interface

Use exactly the full `compose(...)` signature in the design, including `official_treasury_operations`, `broad_market_flow`, `duration_extension_context`, `market_confirmation` and `prior_clock`.

### RED tests

- [ ] **Step 1: Write output/authority and input-order tests**

```python
def test_payload_has_method_and_semantic_identity():
    out = compose(**BASE_INPUTS)
    assert out["schema"] == "policy_turn_clock.v1"
    assert out["method_version"] == "policy_turn_clock.v1.0.0"
    assert len(out["input_digest"]) == 64
    assert out["authority"] == {
        "can_rank": False, "can_gate": False,
        "can_size": False, "can_trade": False,
    }


def test_input_order_does_not_change_digest():
    a = compose(**BASE_INPUTS)
    b = compose(**{**BASE_INPUTS, "events": list(reversed(BASE_INPUTS["events"]))})
    assert a["input_digest"] == b["input_digest"]
```

- [ ] **Step 2: Write same-instant/timezone and method tests**

```python
def test_same_instant_has_same_us_decision_date_and_state():
    et = datetime(2026, 9, 3, 21, 30, tzinfo=ZoneInfo("America/New_York"))
    utc = et.astimezone(timezone.utc)
    a = compose(**{**BASE_INPUTS, "now": et})
    b = compose(**{**BASE_INPUTS, "now": utc})
    assert (a["as_of"], a["state"], a["input_digest"]) == (
        b["as_of"], b["state"], b["input_digest"]
    )


def test_cross_method_prior_is_not_compared():
    out = compose(**{**BASE_INPUTS, "prior_clock": {"method_version": "old.v1"}})
    assert out["change_from_prior"]["comparable"] is False
    assert "METHOD_VERSION_MISMATCH" in out["gaps"]
```

- [ ] **Step 3: Write OPEX/gamma/replacement tests**

```python
def test_post_opex_calendar_alone_is_not_bearish_or_open_vol():
    out = compose(**POST_OPEX_NO_CONFIRMATION)
    assert out["state"] in {"SUPPORT_ROLLOFF_IMMINENT", "MIXED", "UNKNOWN"}
    assert out["state"] != "VOLATILITY_WINDOW_OPEN"


def test_short_gamma_expiry_does_not_inherit_long_gamma_rolloff():
    out = compose(**SHORT_GAMMA_EXPIRY)
    assert "stabilizing_support_rolled_off" not in {
        row["predicate"] for row in out["state_basis"]
    }


def test_missing_replacement_is_unknown():
    out = compose(**NO_REPLACEMENT_DATA)
    assert out["option_support"]["replacement"] == "unknown"
```

- [ ] **Step 4: Write support-building and month-end tests**

```python
def test_replacement_alone_is_not_broad_support_building():
    out = compose(**REPLACEMENT_ONLY)
    assert out["state"] != "SUPPORT_BUILDING"


def test_two_independent_support_mechanisms_can_build_support():
    out = compose(**REPLACEMENT_AND_SUPPORTIVE_FLOW)
    assert out["state"] == "SUPPORT_BUILDING"
    assert out["option_support"]["applicable_support_count"] >= 2


def test_calendar_only_month_end_is_scheduled_unconfirmed():
    out = compose(**MONTH_END_NO_PULSE)
    assert out["rebalance"]["status"] == "scheduled_unconfirmed"
    assert out["state"] != "MONTH_END_REBALANCE_DOMINANT"
```

- [ ] **Step 5: Write Treasury/market-confirmation/VX tests**

```python
def test_official_buyback_enters_treasury_axis():
    out = compose(**WITH_BUYBACK)
    assert out["treasury_liquidity"]["operations"][0]["operation_kind"] == "buyback"
    assert out["treasury_liquidity"]["operations"][0]["offered_usd_bn"] == 20.1


def test_volatility_window_requires_independent_fresh_confirmation():
    out = compose(**ROLLOFF_WITH_STALE_CONFIRMATION)
    assert out["state"] != "VOLATILITY_WINDOW_OPEN"
    assert "MARKET_CONFIRMATION_UNAVAILABLE" in out["gaps"]


def test_vx_settlement_alone_has_no_state_authority():
    out = compose(**VX_SETTLEMENT_ONLY)
    assert out["state"] != "VOLATILITY_WINDOW_OPEN"
```

Run RED:

```bash
python -m pytest tests/test_policy_turn_clock.py -q
```

### Implementation

- [ ] **Step 6: Implement normalization and semantic digest**

Exclude `generated_at`; include method version, source versions/watermarks, canonical inputs and decision-date identity.

- [ ] **Step 7: Implement independent axes**

Use literal predicates and applicable counts. Do not add a score. Preserve stale/unavailable/conflicting evidence.

- [ ] **Step 8: Implement exact state precedence and bilingual phrase keys**

Phrase keys are deterministic; rendered strings live in one frozen registry. The composer emits keys and plain data, not model text.

- [ ] **Step 9: Implement prior comparison**

Only compare equal methods. Identical input digest is unchanged despite later `generated_at`.

- [ ] **Step 10: Verify and commit**

```bash
python -m pytest tests/test_policy_turn_clock.py -q
python -m py_compile engine/policy_turn_clock.py
git diff --check
git add engine/policy_turn_clock.py tests/test_policy_turn_clock.py
git commit -m "feat(policy-clock): compose monthly transition state"
```

---

## Task 5: Builder modes, no-regress publication and prospective ledger

**Files:**

```text
Create: scripts/build_policy_turn_clock.py
Create: tests/test_build_policy_turn_clock.py
```

**Consumes:** official store/status and current canonical owner artifacts.

**Produces:** current JSON in publish mode; keep-FIRST receipt in nightly ledger-only mode.

### Interfaces

```python
def gather_inputs(*, root: Path, now: datetime) -> dict[str, object]: ...
def build_payload(*, root: Path, now: datetime) -> dict[str, object]: ...
def write_payload_if_newer(
    payload: Mapping[str, object], *, root: Path
) -> tuple[Path, bool, str]: ...
def append_forward_receipt(
    payload: Mapping[str, object], *, root: Path
) -> int: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```

CLI:

```text
--mode publish-current
--mode ledger-only
--mode verify
```

### RED tests

- [ ] **Step 1: Write canonical-input and stale/null tests**

Use temp fixtures for official events, options surface, broad flows, Rebalance Pulse, TGA, VX, market structure and regime. Assert every owner watermark is exposed and stale input is unavailable rather than neutral.

- [ ] **Step 2: Write semantic no-op/no-regress tests**

```python
def test_later_generated_at_same_inputs_is_noop(tmp_path):
    first = build_payload(root=seed_all(tmp_path), now=ET_0900)
    _, wrote, _ = write_payload_if_newer(first, root=tmp_path)
    assert wrote is True
    second = build_payload(root=tmp_path, now=ET_1000)
    _, wrote, reason = write_payload_if_newer(second, root=tmp_path)
    assert wrote is False
    assert reason == "semantic_noop"


def test_older_evidence_cutoff_cannot_overwrite_newer(tmp_path):
    write_payload_if_newer(NEWER_PAYLOAD, root=tmp_path)
    _, wrote, reason = write_payload_if_newer(OLDER_PAYLOAD, root=tmp_path)
    assert wrote is False
    assert reason == "no_regress_refusal"
```

- [ ] **Step 3: Write lane tests**

```python
def test_hourly_publish_never_appends(monkeypatch, tmp_path):
    monkeypatch.setenv("COLLECT_LANE", "hourly")
    assert main(["--root", str(seed_all(tmp_path)), "--mode", "publish-current"]) == 0
    assert not (tmp_path / "data/policy_turn_clock/forward_log.jsonl").exists()


def test_nightly_ledger_only_appends_once_and_does_not_publish(monkeypatch, tmp_path):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    root = seed_all(tmp_path)
    assert main(["--root", str(root), "--mode", "ledger-only"]) == 0
    first = (root / "data/policy_turn_clock/forward_log.jsonl").read_text().splitlines()
    assert len(first) == 1
    assert not (root / "site/policy_turn_clock.json").exists()
    assert main(["--root", str(root), "--mode", "ledger-only"]) == 0
    assert (root / "data/policy_turn_clock/forward_log.jsonl").read_text().splitlines() == first
```

- [ ] **Step 4: Write failure/recovery tests**

A source failure publishes degraded current status while preserving last-good evidence. Recovery advances semantic status. One malformed source does not erase healthy axes.

Run RED:

```bash
python -m pytest tests/test_build_policy_turn_clock.py -q
```

### Implementation

- [ ] **Step 5: Implement bounded artifact readers and owner watermarks**

Read exact canonical paths and preserve each owner’s as-of/freshness/caveat. No network calls.

- [ ] **Step 6: Implement publish-current and no-regress**

Atomically write only when semantic identity or a meaningful status/freshness transition changes. Preserve byte stability for quiet reruns.

- [ ] **Step 7: Implement ledger-only through `engine.ledger_lane.nightly_advance_enabled()`**

Identity includes `as_of`, trigger kind/id, method version and input digest. Off-lane append returns zero.

- [ ] **Step 8: Verify and commit**

```bash
python -m pytest tests/test_build_policy_turn_clock.py -q
python -m py_compile scripts/build_policy_turn_clock.py
git diff --check
git add scripts/build_policy_turn_clock.py tests/test_build_policy_turn_clock.py
git commit -m "feat(policy-clock): publish current state and nightly receipts"
```

---

## Task 6: Policy Watch dynamic component and bilingual states

**Files:**

```text
Create: templates/partials/_policy_turn_clock.html.j2
Modify: scripts/build_policy_watch.py
Modify: templates/policy_watch.html.j2
Modify: tests/test_policy_watch_ui.py
```

**Produces:** static shell/fallback and same-origin dynamic JSON consumer.

### RED tests

- [ ] **Step 1: Write structural and accessibility tests**

Assert one component root, JSON URL, noscript/unavailable state, keyboard-accessible evidence details, bilingual labels and no recommendation vocabulary.

- [ ] **Step 2: Write state-fixture tests**

Fixtures: fresh support-building, rolloff imminent, catalyst dominant, stale, source failed, cancelled, conflicting location, virtual/prerecorded, unknown and rank-roll boundary.

- [ ] **Step 3: Write same-artifact/no-stale-embed test**

Assert the template does not embed a full stale clock payload and runtime code reads `policy_turn_clock.json` from same origin. The static fallback cannot claim current state.

Run RED:

```bash
python -m pytest tests/test_policy_watch_ui.py -q
```

### Implementation

- [ ] **Step 4: Implement static shell and deterministic browser renderer**

Render Now, Support Inventory, Flow/Liquidity, Futures Clocks, Next 72h/14d, Why This Can Turn, Confirm, Invalidate, Coverage and Evidence. No model call.

- [ ] **Step 5: Preserve theme/language and failure layouts**

State meaning is textual, not color-only. EN/ZH parity is complete.

- [ ] **Step 6: Verify and commit**

```bash
python -m pytest tests/test_policy_watch_ui.py -q
python -m scripts.build_policy_watch
git diff --check
git add templates/partials/_policy_turn_clock.html.j2 scripts/build_policy_watch.py \
  templates/policy_watch.html.j2 tests/test_policy_watch_ui.py
git commit -m "feat(policy-clock): add Policy Watch transition workflow"
```

---

## Task 7: Real hourly/nightly wiring and executable CI ownership

**Files:**

```text
Modify: .github/workflows/whitehouse-sentinel.yml
Modify: scripts/ci/daily_engine_regional_desk_builders.sh
Modify: config/dag.yml
Modify: .github/workflows/ci.yml
Modify: .github/ci/legacy-jobs.yml
Possibly modify: tests/test_dag_conformance.py
```

### RED/validation requirements

- [ ] **Step 1: Write/extend conformance tests before workflow edits**

Tests assert:

- hourly sequence is collector → publish-current → focused validation;
- hourly `COLLECT_LANE` is non-nightly;
- nightly regional builder invokes `--mode ledger-only` immediately before Policy Watch;
- no nightly official-event collector or current-artifact publisher exists;
- DAG mirrors both real calls;
- every new suite has exactly one executable logical owner;
- exact source subjects are in owner paths and PR triggers;
- no new logical job/workflow/runner/planner/permission/trusted-executor/concurrency/merge control exists;
- current-main unrelated manifest markers remain.

- [ ] **Step 2: Run RED/validate-only**

```bash
python -m pytest tests/test_dag_conformance.py tests/test_build_policy_turn_clock.py -q
python -m scripts.run_ci_pack --validate-only
python -m scripts.audit_unrun_tests
```

Expected before wiring: missing invocation/ownership failures.

### Implementation

- [ ] **Step 3: Wire hourly single writer**

In the existing sentinel, run:

```bash
python -m collectors.policy_event_clock
COLLECT_LANE=hourly python -m scripts.build_policy_turn_clock --mode publish-current
python -m pytest tests/test_policy_event_clock.py tests/test_futures_roll_calendar.py \
  tests/test_policy_turn_clock.py tests/test_build_policy_turn_clock.py \
  tests/test_policy_watch_ui.py -q
```

Stage only owned event/status/current JSON and existing sentinel-owned outputs. A quiet semantic no-op yields no commit.

- [ ] **Step 4: Wire nightly ledger-only**

In `scripts/ci/daily_engine_regional_desk_builders.sh`, immediately before the existing Policy Watch command, add a distinct buffered `brun` call for:

```text
scripts.build_policy_turn_clock --mode ledger-only
```

Do not run the collector or publish-current mode nightly.

- [ ] **Step 5: Update DAG mirror**

Declare both actual calls and modes in existing vocabulary. Do not treat DAG as execution.

- [ ] **Step 6: Compose canonical CI ownership**

Only after a fresh path census is clean, extend one existing policy/front-facing logical job in `.github/ci/legacy-jobs.yml`. Name every new suite. Add exact source/test/workflow/DAG path closure and matching `.github/workflows/ci.yml` triggers. Preserve all unrelated current-main lines.

- [ ] **Step 7: Run GREEN and mutation checks**

```bash
python -m pytest tests/test_policy_event_clock.py \
  tests/test_futures_roll_calendar.py \
  tests/test_policy_turn_clock.py \
  tests/test_build_policy_turn_clock.py \
  tests/test_policy_watch_ui.py \
  tests/test_dag_conformance.py -q
python -m scripts.run_ci_pack --validate-only
python -m scripts.audit_unrun_tests
git diff --check
```

Temporarily remove one new suite from the manifest and verify the unrun/contract guard fails; restore. Temporarily remove one source subject from the owner path closure and verify failure; restore. Temporarily set hourly `COLLECT_LANE=nightly` and verify lane test failure; restore.

- [ ] **Step 8: Commit**

```bash
git add .github/workflows/whitehouse-sentinel.yml \
  scripts/ci/daily_engine_regional_desk_builders.sh \
  config/dag.yml .github/workflows/ci.yml .github/ci/legacy-jobs.yml
[ -n "$(git status --short tests/test_dag_conformance.py)" ] && git add tests/test_dag_conformance.py || true
git commit -m "ci(policy-clock): wire hourly publisher and nightly evidence owner"
```

---

## Task 8: End-to-end real proof and immutable return

**Files:** implementation and evidence outputs only; no scope widening.

- [ ] **Step 1: Re-pin and re-census before proof**

Fresh-read protected procedure, current main, all planned paths and current PR collisions. Reconcile main history-preservingly without force or dropped commits.

- [ ] **Step 2: Run real official sources**

Run the collector against current Fed/Treasury/TreasuryDirect sources. Record source URLs, response/status shape, observed/available clocks, semantic rows, additions, failures and collector-status digest. Do not expose secrets.

- [ ] **Step 3: Run real current artifact build**

Use current canonical OPEX/options/TGA/rebalance/broad-flow/VX/market-state inputs and `COLLECT_LANE=hourly`. Produce `site/policy_turn_clock.json`, record input digest/source watermarks/evidence cutoff, and rerun to prove semantic no-op.

- [ ] **Step 4: Prove no-regress**

Attempt to publish a fixture with an older cutoff and verify refusal. Prove a real source-failure status transition can publish while last-good evidence remains.

- [ ] **Step 5: Prove nightly ledger-only**

Under `COLLECT_LANE=nightly`, freeze one eligible prospective receipt. Rerun and prove no duplicate. Prove current JSON/UI are not written by ledger-only mode.

- [ ] **Step 6: Prove machine consumer**

Use a direct JSON reader—not HTML scraping—to parse schema, method version, input digest, state, axes, gaps and authority.

- [ ] **Step 7: Browser proof**

Capture 1440, 768 and 390 CSS-pixel evidence in dark/light and EN/ZH for fresh, partial, stale, cancelled, conflicting, virtual/prerecorded and unknown states. Verify no clipped times/amounts and keyboard accessibility.

- [ ] **Step 8: Run full verification**

```bash
python -m pytest tests/test_policy_event_clock.py \
  tests/test_futures_roll_calendar.py \
  tests/test_policy_turn_clock.py \
  tests/test_build_policy_turn_clock.py \
  tests/test_policy_watch_ui.py \
  tests/test_dag_conformance.py -q
python -m scripts.run_ci_pack --validate-only
python -m scripts.audit_unrun_tests
python -m compileall collectors/policy_event_clock.py engine/futures_roll_calendar.py \
  engine/policy_turn_clock.py scripts/build_policy_turn_clock.py
git diff --check
git status --short
```

Push one branch and open one Draft/HOLD-FOR-SOL implementation PR. Run hosted exact-head fences and semantic CI. Do not mark Ready or merge.

- [ ] **Step 9: Return**

Return on issue #6787 and the exact communication carrier:

```text
operation key
receiver/session and GitHub identity
PICKUP_ACK / WATCH / START receipts
pickup base / current main
exact head / tree / parents
exact changed paths
collision census
RED→GREEN evidence
selected logical CI job and executed-suite proof
hosted checks
real official-source/freshness receipts
artifact digest/method/input identity
browser receipts
machine-consumer receipt
prospective receipt ID
no-regress and quiet-no-op proof
authority diff
known gaps/corrections
effect=APPLIED_REMOTE_SOURCE / MERGE_NONE / DEPLOY_NONE / PRODUCTION_NONE
```

Re-arm the exact-carrier continuation source and wait for Sol’s explicit review edge.

## Self-review checklist

- Every source, state, time, null, correction, writer, CI and authority requirement maps to a task above.
- No `TBD`, `TODO`, “implement later,” generic error-handling instruction or undefined neighboring interface remains.
- `operation_kind`, `operation_purpose`, amount fields, presence fields, composer arguments, builder modes, method identity and artifact fields are consistent across tasks.
- Hourly owns official/current publication; nightly owns prospective append only.
- Calendar, options, futures, Treasury, broad flows, rebalance, duration and market confirmation remain independent axes.
- No calendar state receives direction or capital authority.
- Stop condition is one immutable Draft/HOLD-FOR-SOL W1 implementation PR.