# Actor, Liquidity & Monthly Transition Clock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one deterministic official-source-to-product clock that shows whether monthly market support is building, stable, pinned, expiring, overridden by a catalyst, or unknown—without creating duplicate source owners or any trade authority.

**Architecture:** Normalize bounded Fed/Treasury/TreasuryDirect observations into the existing keep-FIRST evidence pattern; extend the canonical event calendar with current official events and quarterly futures-roll context; compose existing OPEX/options/rebalance/TGA owners through a pure `policy_turn_clock.v1` engine; publish one machine JSON, one Policy Watch component and one immutable prospective receipt. Reuse the existing hourly White House sentinel and nightly ledger lane; do not create another scheduler or semantic store.

**Tech Stack:** Python 3.12, dataclasses, `requests`, `pandas`/Parquet, Jinja2, pytest, PyYAML, GitHub Actions, Playwright for browser proof.

**Spec:** `docs/superpowers/specs/2026-09-03-actor-liquidity-monthly-transition-clock-design.md`

## Global Constraints

- Re-pin current protected `mastermindx-market-intelligence/Mastermind` Skillpack before pickup, START, review and release.
- Canonical implementation carrier is Macro issue #6787 and operation `policy-preturn-actor-liquidity-calendar-clock-20260903-sol-001`.
- Post `PICKUP_ACK` and a separate `START` only after fresh path/collision census clears every planned source path.
- Do not edit `engine/yield_momentum.py`, `engine/rates_inflation_command.py`, `scripts/build_rates_command.py`, `.github/ci/legacy-jobs.yml` or `agentos/workstreams/WS-RATES-INFLATION-COMMAND.md`.
- Consume rather than duplicate `engine/event_calendar.py`, `engine/event_window.py`, `engine/opex.py`, `engine/options_surface.py`, `engine/opex_risk.py`, `engine/rebalance_calendar.py`, `engine/rebalance_pulse.py` and `engine/treasury_watch.py`.
- Calendar proximity never ranks, gates, sizes, recommends or originates a trade.
- Every action-time datetime is timezone-aware; missing, false, zero and not-applicable remain distinct.
- Official-event history is append-only/keep-FIRST; corrections and cancellations append vintages rather than overwriting evidence.
- The hourly lane never advances the prospective ledger; nightly remains its sole advancer.
- No LLM call is permitted in the first-wave state path.
- One implementation PR only; remain Draft/HOLD-FOR-SOL until exact-head Sol acceptance.

---

## File Structure

### New source files

- `collectors/policy_event_clock.py` — pure official-source normalizers, current-revision projection, actor-presence logic, bounded HTTP collection and keep-FIRST persistence.
- `engine/futures_roll_calendar.py` — pure quarterly equity-index and Treasury-futures roll schedule/progress context.
- `engine/policy_turn_clock.py` — pure independent-axis construction, state precedence, bilingual confirmation/invalidation phrases and contract validation.
- `scripts/build_policy_turn_clock.py` — read canonical artifacts, build/write machine JSON and append a nightly-only keep-FIRST prospective receipt.
- `templates/partials/_policy_turn_clock.html.j2` — one product component; no independent semantics.
- `tests/test_policy_event_clock.py` — parser, revision, storage, location and failure tests.
- `tests/test_futures_roll_calendar.py` — quarter/month, contract and live-progress tests.
- `tests/test_policy_turn_clock.py` — state, authority, null, ordering and contradiction tests.
- `tests/test_build_policy_turn_clock.py` — I/O, stale/partial/unknown and receipt tests.

### Existing files modified

- `engine/event_calendar.py` — additive `policy_turn_events(...)` canonical composition.
- `scripts/build_policy_watch.py` — load/pass the clock artifact only.
- `templates/policy_watch.html.j2` — include the new partial near the glance tier.
- `tests/test_policy_watch_ui.py` — structural/bilingual/failure-state UI guards.
- `config/dag.yml` — declare collector/builder/consumer in the existing pipeline.
- `.github/workflows/whitehouse-sentinel.yml` — reuse the existing hourly schedule and commit lane.
- `.github/workflows/ci.yml` — register focused tests/path ownership without touching `.github/ci/legacy-jobs.yml`.

### Generated/evidence outputs

- `data/policy_events/official_events.parquet`
- `data/policy_events/collector_status.json`
- `data/policy_turn_clock/forward_log.jsonl`
- `site/policy_turn_clock.json`
- `site/policy_watch.html`
- `mockups/refs/policy-turn-clock/`

---

### Task 1: Official policy-event evidence and actor-presence contract

**Files:**
- Create: `collectors/policy_event_clock.py`
- Create: `tests/test_policy_event_clock.py`
- Read/Reuse: `collectors/_first_seen_store.py`

**Interfaces:**
- Consumes: source-faithful Fed Board, Treasury and TreasuryDirect record dictionaries plus timezone-aware `datetime`.
- Produces:
  - `CollectionResult(rows_seen: int, rows_added: int, status: dict[str, object], gaps: tuple[str, ...])`
  - `normalize_fed_board_event(raw, *, observed_at) -> dict[str, object] | None`
  - `normalize_treasury_event(raw, *, observed_at) -> dict[str, object] | None`
  - `normalize_buyback_record(raw, *, observed_at) -> dict[str, object] | None`
  - `current_records(rows, *, now) -> list[dict[str, object]]`
  - `actor_presence(records, *, actor_id, now) -> dict[str, object]`
  - `collect(*, now, session=None, root=None) -> CollectionResult`

- [ ] **Step 1: Write the failing normalization and amount-separation tests**

Add exact source-faithful dictionaries and assertions:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from collectors import policy_event_clock as pec

ET = ZoneInfo("America/New_York")


def test_fed_event_preserves_exact_clocks_and_location_precision():
    raw = {
        "source_event_id": "fed-2026-09-03-waller",
        "actor_id": "fed:christopher-waller",
        "actor_name": "Christopher J. Waller",
        "actor_role": "Member, Board of Governors",
        "headline": "Economic Outlook",
        "scheduled_start": "2026-09-03T08:30:00-04:00",
        "scheduled_end": "2026-09-03T09:30:00-04:00",
        "location_label": "New York, NY",
        "location_precision": "city",
        "source_url": "https://www.federalreserve.gov/newsevents/calendar.htm",
        "source_published_at": "2026-08-31T12:00:00-04:00",
        "status": "scheduled",
    }
    row = pec.normalize_fed_board_event(
        raw, observed_at=datetime(2026, 9, 3, 7, 0, tzinfo=ET)
    )
    assert row is not None
    assert row["scheduled_start"] == "2026-09-03T08:30:00-04:00"
    assert row["scheduled_end"] == "2026-09-03T09:30:00-04:00"
    assert row["location_precision"] == "city"
    assert row["evidence_class"] == "FACT"
    assert row["rights_class"] == "official_public"
    assert len(row["content_sha256"]) == 64


def test_buyback_never_collapses_max_submitted_and_accepted_amounts():
    raw = {
        "operation_id": "2026-09-03-cash-management",
        "operation_kind": "cash_management",
        "operation_start": "2026-09-03T13:40:00-04:00",
        "operation_end": "2026-09-03T14:00:00-04:00",
        "settlement_date": "2026-09-04",
        "announced_max_usd": "12500000000",
        "submitted_usd": "20100000000",
        "accepted_usd": "12400000000",
        "instrument_scope": "1-month to 2-year nominal coupons",
        "source_url": "https://treasurydirect.gov/TA_WS/securities/auctioned",
    }
    row = pec.normalize_buyback_record(
        raw, observed_at=datetime(2026, 9, 3, 14, 5, tzinfo=ET)
    )
    assert row is not None
    assert row["announced_max_usd_bn"] == 12.5
    assert row["submitted_usd_bn"] == 20.1
    assert row["accepted_usd_bn"] == 12.4
    assert row["settlement_date"] == "2026-09-04"
```

- [ ] **Step 2: Write the failing revision, cancellation and current-location tests**

```python

def _event_revision(revision: str, status: str, available_at: str) -> dict[str, object]:
    return {
        "source_key": "fed_board",
        "source_event_id": "fed-2026-09-03-waller",
        "source_revision": revision,
        "record_kind": "actor_event",
        "actor_id": "fed:christopher-waller",
        "actor_name": "Christopher J. Waller",
        "actor_role": "Member, Board of Governors",
        "organization": "Federal Reserve Board",
        "operation_kind": "speech",
        "headline": "Economic Outlook",
        "scheduled_start": "2026-09-03T08:30:00-04:00",
        "scheduled_end": "2026-09-03T09:30:00-04:00",
        "status": status,
        "location_label": "New York, NY",
        "location_precision": "city",
        "source_url": "https://www.federalreserve.gov/newsevents/calendar.htm",
        "source_published_at": "2026-08-31T12:00:00-04:00",
        "observed_at": available_at,
        "available_at": available_at,
        "first_seen": available_at,
        "content_sha256": revision.rjust(64, "0"),
        "evidence_class": "FACT",
        "rights_class": "official_public",
        "parser_version": "policy_event_clock.v1",
    }


def test_current_records_projects_cancellation_without_deleting_prior_vintage():
    rows = [
        _event_revision("1", "scheduled", "2026-09-03T06:00:00-04:00"),
        _event_revision("2", "cancelled", "2026-09-03T07:30:00-04:00"),
    ]
    current = pec.current_records(
        rows, now=datetime(2026, 9, 3, 8, 0, tzinfo=ET)
    )
    assert len(rows) == 2
    assert len(current) == 1
    assert current[0]["source_revision"] == "2"
    assert current[0]["status"] == "cancelled"


def test_actor_presence_expires_current_location_at_event_end():
    record = _event_revision("1", "scheduled", "2026-09-03T06:00:00-04:00")
    during = pec.actor_presence(
        [record],
        actor_id="fed:christopher-waller",
        now=datetime(2026, 9, 3, 9, 0, tzinfo=ET),
    )
    after = pec.actor_presence(
        [record],
        actor_id="fed:christopher-waller",
        now=datetime(2026, 9, 3, 10, 0, tzinfo=ET),
    )
    assert during["current_location"] == "New York, NY"
    assert during["current_location_status"] == "verified_event_window"
    assert after["current_location"] is None
    assert after["current_location_status"] == "unknown"
    assert after["last_verified_location"] == "New York, NY"


def test_conflicting_overlapping_locations_never_choose_one():
    a = _event_revision("1", "scheduled", "2026-09-03T06:00:00-04:00")
    b = {**a, "source_event_id": "fed-2026-09-03-waller-2", "location_label": "Washington, DC"}
    result = pec.actor_presence(
        [a, b],
        actor_id="fed:christopher-waller",
        now=datetime(2026, 9, 3, 9, 0, tzinfo=ET),
    )
    assert result["current_location"] is None
    assert result["current_location_status"] == "conflicting"
    assert sorted(result["candidate_locations"]) == ["New York, NY", "Washington, DC"]
```

- [ ] **Step 3: Write the failing keep-FIRST and unreadable-store tests**

Use `monkeypatch` so the test proves this collector delegates to the existing house helper rather than implementing a second persistence dialect:

```python
from pathlib import Path


def test_persist_rows_uses_existing_keep_first_contract(monkeypatch, tmp_path: Path):
    calls: list[dict[str, object]] = []

    def fake_accrue(path, rows, *, columns, key, sort_by):
        calls.append({"path": path, "rows": rows, "columns": columns, "key": key, "sort_by": sort_by})
        return 1

    monkeypatch.setattr(pec, "accrue_keep_first", fake_accrue)
    added = pec.persist_rows([_event_revision("1", "scheduled", "2026-09-03T06:00:00-04:00")], root=tmp_path)
    assert added == 1
    assert calls[0]["key"] == ["source_key", "source_event_id", "source_revision"]
    assert calls[0]["path"] == tmp_path / "data/policy_events/official_events.parquet"


def test_naive_observation_time_is_rejected():
    raw = {
        "source_event_id": "fed-naive",
        "headline": "Speech",
        "source_url": "https://www.federalreserve.gov/newsevents/calendar.htm",
    }
    with pytest.raises(ValueError, match="timezone-aware"):
        pec.normalize_fed_board_event(raw, observed_at=datetime(2026, 9, 3, 7, 0))
```

- [ ] **Step 4: Run the focused tests and record RED**

Run:

```bash
python -m pytest tests/test_policy_event_clock.py -q
```

Expected: collection fails because `collectors.policy_event_clock` does not exist. Save the exact command and failure count in the PR evidence.

- [ ] **Step 5: Implement the pure contract and storage delegation**

Implement:

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from collectors._first_seen_store import accrue_keep_first

PARSER_VERSION = "policy_event_clock.v1"
EVENT_KEY = ["source_key", "source_event_id", "source_revision"]

@dataclass(frozen=True)
class CollectionResult:
    rows_seen: int
    rows_added: int
    status: dict[str, object]
    gaps: tuple[str, ...]


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")


def _digest(payload: Mapping[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(raw.encode("utf-8")).hexdigest()
```

Normalize all rows through one private `_finalize_row(...)` that fills explicit nulls, rejects missing source identity/URL, canonicalizes timestamps and hashes the source-semantic payload before adding observation fields. Amount conversion accepts only an explicit USD amount and divides by `1_000_000_000`.

`current_records` groups by `(source_key, source_event_id)`, chooses the latest valid revision by parsed `available_at`, then `observed_at`, then `content_sha256`, and returns stable sorted output. It does not drop cancelled records; cancellation is a current state.

`persist_rows` calls `accrue_keep_first` with the exact key and full frozen columns. Do not add a custom Parquet writer.

- [ ] **Step 6: Implement bounded HTTP collection and typed status**

Use injected `requests.Session` and explicit timeouts. Each source has its own function and error boundary. A source parser may return zero valid records with `status="healthy"` only when the HTTP response and document structure are valid; missing expected container/columns is `status="failed"`, `error_code="SOURCE_SHAPE_CHANGED"`.

The CLI boundary catches per-source errors, persists successful-source rows, writes `data/policy_events/collector_status.json` atomically, and returns exit 0 when at least one configured source remains healthy or partial. It returns nonzero when all sources fail, while preserving prior evidence.

- [ ] **Step 7: Run tests and quality checks**

Run:

```bash
python -m pytest tests/test_policy_event_clock.py -q
python -m py_compile collectors/policy_event_clock.py
git diff --check
```

Expected: all tests pass; compile and diff checks exit 0.

- [ ] **Step 8: Commit Task 1**

```bash
git add collectors/policy_event_clock.py tests/test_policy_event_clock.py
git commit -m "feat(policy-clock): add official event evidence contract"
```

---

### Task 2: Quarterly futures-roll context

**Files:**
- Create: `engine/futures_roll_calendar.py`
- Create: `tests/test_futures_roll_calendar.py`

**Interfaces:**
- Consumes: `date` and optional source-owned `live_progress` mapping.
- Produces:
  - `equity_roll_window(d: date) -> dict[str, object]`
  - `treasury_roll_window(d: date) -> dict[str, object]`
  - `snapshot(asof: date, *, live_progress=None) -> dict[str, object]`

- [ ] **Step 1: Write the failing month/quarter and progress tests**

```python
from datetime import date

from engine import futures_roll_calendar as frc


def test_non_quarterly_month_is_not_applicable_not_unknown():
    snap = frc.snapshot(date(2026, 8, 10))
    assert snap["equity_index"]["status"] == "not_applicable"
    assert snap["treasury"]["status"] == "not_applicable"


def test_september_equity_roll_is_scheduled_without_live_progress():
    snap = frc.snapshot(date(2026, 9, 14))
    eq = snap["equity_index"]
    assert eq["contract_month"] == "2026-09"
    assert eq["roll_start"] == "2026-09-14"
    assert eq["expiry"] == "2026-09-18"
    assert eq["status"] == "scheduled"
    assert eq["progress"] is None
    assert eq["progress_basis"] == "not_provided"


def test_live_progress_is_required_for_active_state():
    snap = frc.snapshot(
        date(2026, 9, 15),
        live_progress={
            "equity_index": {
                "as_of": "2026-09-15",
                "lead_contract": "ESU6",
                "next_contract": "ESZ6",
                "next_volume_share": 0.64,
                "next_open_interest_share": 0.55,
            }
        },
    )
    eq = snap["equity_index"]
    assert eq["status"] == "active"
    assert eq["progress"] == {"next_volume_share": 0.64, "next_open_interest_share": 0.55}
    assert eq["progress_basis"] == "both"


def test_stale_or_wrong_contract_progress_does_not_activate_roll():
    snap = frc.snapshot(
        date(2026, 9, 15),
        live_progress={
            "equity_index": {
                "as_of": "2026-09-10",
                "lead_contract": "ESM6",
                "next_contract": "ESU6",
                "next_volume_share": 0.8,
            }
        },
    )
    assert snap["equity_index"]["status"] == "scheduled"
    assert "progress_contract_mismatch" in snap["equity_index"]["gaps"]
```

- [ ] **Step 2: Write the year-boundary and authority tests**

```python

def test_december_roll_maps_to_next_calendar_year_contract():
    snap = frc.snapshot(date(2026, 12, 14))
    eq = snap["equity_index"]
    assert eq["lead_contract"] == "ESZ6"
    assert eq["next_contract"] == "ESH7"


def test_roll_contract_has_no_trade_authority():
    snap = frc.snapshot(date(2026, 9, 14))
    assert snap["authority"] == {
        "can_rank": False,
        "can_gate": False,
        "can_size": False,
        "can_trade": False,
    }
```

- [ ] **Step 3: Run the focused tests and record RED**

```bash
python -m pytest tests/test_futures_roll_calendar.py -q
```

Expected: import failure because `engine.futures_roll_calendar` does not exist.

- [ ] **Step 4: Implement deterministic schedules**

Implement contract-month helpers for `H`, `M`, `U`, `Z`. Equity-index expiry is the third Friday of the contract month; customary roll start is the Monday of that week, adjusted through the repository’s accepted U.S. business-calendar helper when available and otherwise labeled `calendar_basis="weekday_fallback"`.

Treasury roll context uses the final ten U.S. business days before the first calendar day of the quarterly contract month. It is schedule context only; it does not assert when a particular instrument’s open interest migrated.

Only same-window, same-contract, same-date live progress can move status from `scheduled` to `active`. `completed` requires supplied next-contract share at or above 0.90 after roll start or an as-of date after the declared roll window. Preserve the raw progress basis and gaps.

- [ ] **Step 5: Run tests and compile**

```bash
python -m pytest tests/test_futures_roll_calendar.py -q
python -m py_compile engine/futures_roll_calendar.py
git diff --check
```

Expected: all pass.

- [ ] **Step 6: Commit Task 2**

```bash
git add engine/futures_roll_calendar.py tests/test_futures_roll_calendar.py
git commit -m "feat(policy-clock): add quarterly futures roll context"
```

---

### Task 3: Extend the canonical event calendar

**Files:**
- Modify: `engine/event_calendar.py`
- Modify: `tests/test_policy_event_clock.py`
- Test: existing event-calendar tests discovered by `git grep -l "us_macro_events\|high_impact_strip" tests`

**Interfaces:**
- Consumes: `us_macro_events(...)`, current official event records and `futures_roll_calendar.v1` snapshot.
- Produces: `policy_turn_events(today=None, horizon_days=14, *, official_records=None, futures_roll=None) -> list[dict[str, object]]`.

- [ ] **Step 1: Add failing composition and non-regression tests**

```python
from datetime import date
from engine import event_calendar


def test_policy_turn_events_composes_existing_owner_official_and_roll_rows():
    official = [_event_revision("1", "scheduled", "2026-09-03T06:00:00-04:00")]
    roll = {
        "schema": "futures_roll_calendar.v1",
        "as_of": "2026-09-14",
        "equity_index": {
            "status": "scheduled",
            "roll_start": "2026-09-14",
            "expiry": "2026-09-18",
            "lead_contract": "ESU6",
            "next_contract": "ESZ6",
        },
        "treasury": {"status": "not_applicable"},
    }
    rows = event_calendar.policy_turn_events(
        date(2026, 9, 1), 20, official_records=official, futures_roll=roll
    )
    types = [row["type"] for row in rows]
    assert "NFP" in types
    assert "OPEX" in types
    assert "ACTOR_EVENT" in types
    assert "FUTURES_ROLL" in types
    assert all(row["is_context_only"] is True for row in rows)


def test_policy_turn_events_does_not_change_existing_macro_event_output():
    before = event_calendar.us_macro_events(date(2026, 9, 1), 20, use_fred=False)
    event_calendar.policy_turn_events(date(2026, 9, 1), 20, official_records=[], futures_roll=None)
    after = event_calendar.us_macro_events(date(2026, 9, 1), 20, use_fred=False)
    assert after == before


def test_conflicting_official_records_are_preserved_not_silently_deduped():
    a = _event_revision("1", "scheduled", "2026-09-03T06:00:00-04:00")
    b = {**a, "source_key": "treasury", "source_event_id": "different-owner", "headline": "Conflicting official event"}
    rows = event_calendar.policy_turn_events(
        date(2026, 9, 1), 5, official_records=[a, b], futures_roll=None
    )
    actor_rows = [row for row in rows if row["type"] == "ACTOR_EVENT"]
    assert len(actor_rows) == 2
    assert actor_rows[0]["conflict_group"] == actor_rows[1]["conflict_group"]
```

- [ ] **Step 2: Run the focused test and record RED**

```bash
python -m pytest tests/test_policy_event_clock.py::test_policy_turn_events_composes_existing_owner_official_and_roll_rows -q
```

Expected: `AttributeError` for missing `policy_turn_events`.

- [ ] **Step 3: Implement additive canonical composition**

Add `policy_turn_events` after `us_macro_events`. Begin with `list(us_macro_events(...))`. Normalize official records into the existing event shape without discarding source clocks. Add one roll-start row and one expiry row only for applicable roll families. Use stable identity:

```text
existing event: (type, date, time_et, label, source)
official event: (source_key, source_event_id, source_revision)
roll event: (family, contract_month, milestone)
```

Only exact owner-equivalent duplicates collapse. Cross-owner disagreements remain separate and receive one deterministic `conflict_group` digest.

- [ ] **Step 4: Run all affected calendar tests**

```bash
python -m pytest tests/test_policy_event_clock.py -q
for f in $(git grep -l "us_macro_events\|high_impact_strip" tests | sort -u); do python -m pytest "$f" -q || exit 1; done
git diff --check
```

Expected: all pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add engine/event_calendar.py tests/test_policy_event_clock.py
git commit -m "feat(policy-clock): extend canonical event composition"
```

---

### Task 4: Pure monthly transition composer

**Files:**
- Create: `engine/policy_turn_clock.py`
- Create: `tests/test_policy_turn_clock.py`

**Interfaces:**
- Consumes: current canonical owner snapshots via the exact keyword-only `compose(...)` signature frozen in the design.
- Produces: deterministic `policy_turn_clock.v1` mapping.

- [ ] **Step 1: Create reusable source-faithful fixtures**

In `tests/test_policy_turn_clock.py`, define builders that include exact owner passports:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from engine import policy_turn_clock as ptc

ET = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 17, 12, 0, tzinfo=ET)


def opex_phase(*, td_to: int | None, td_since: int | None, in_week: bool) -> dict[str, object]:
    return {
        "asof": "2026-09-17",
        "td_to_opex": td_to,
        "td_since_opex": td_since,
        "in_opex_week": in_week,
        "is_quad_cycle": True,
        "available_at": "2026-09-17T06:40:00-04:00",
    }


def stabilizing_opex_risk() -> dict[str, object]:
    return {
        "schema": "opex_risk.v1",
        "asof": "2026-09-17",
        "states": {
            "concentration_hot": True,
            "dealer_load_extreme": True,
            "pin_proximity": True,
            "vanna_relief_active": True,
            "vanna_drag": False,
        },
        "gamma_regime": {"regime": "long", "net_gex_bn": 8.2},
        "dealer_sign_passport": "long_call_short_put_unobservable_assumption",
        "vanna_symmetry_caveat": "drag side less documented",
        "available_at": "2026-09-17T06:40:00-04:00",
    }


def surface_rows(*, fm_oi_prior: float, fm_oi_now: float) -> list[dict[str, object]]:
    return [
        {
            "root": "SPY", "root_class": "index_etf", "date": "2026-09-16",
            "fm_oi_frac": fm_oi_prior, "fm_gex_bn": 1.0, "bk_gex_bn": 2.0,
            "fw_oi_frac": 0.58, "dealer_sign_assumption": "long_call_short_put",
            "available_at": "2026-09-17T06:30:00-04:00",
        },
        {
            "root": "SPY", "root_class": "index_etf", "date": "2026-09-17",
            "fm_oi_frac": fm_oi_now, "fm_gex_bn": 1.6, "bk_gex_bn": 2.1,
            "fw_oi_frac": 0.41, "dealer_sign_assumption": "long_call_short_put",
            "available_at": "2026-09-18T06:30:00-04:00",
        },
    ]


def compose_base(**overrides):
    args = {
        "now": NOW,
        "events": [],
        "opex": opex_phase(td_to=1, td_since=None, in_week=True),
        "opex_risk": stabilizing_opex_risk(),
        "option_surface": surface_rows(fm_oi_prior=0.21, fm_oi_now=0.22),
        "rebalance_calendar": {"in_qtr_end_window": False, "available_at": "2026-09-17T00:00:00-04:00"},
        "rebalance_pulse": {"class": "quiet", "date": "2026-09-17", "available_at": "2026-09-17T17:00:00-04:00"},
        "treasury": {"state": "neutral", "asof": "2026-09-17", "available_at": "2026-09-17T16:30:00-04:00"},
        "futures_roll": {"schema": "futures_roll_calendar.v1", "as_of": "2026-09-17", "equity_index": {"status": "scheduled"}, "treasury": {"status": "not_applicable"}},
        "prior_clock": None,
    }
    args.update(overrides)
    return ptc.compose(**args)
```

- [ ] **Step 2: Write failing authority, calendar-only and rolloff tests**

```python

def test_calendar_proximity_alone_cannot_create_support_or_direction():
    result = compose_base(opex_risk=None, option_surface=None, treasury=None)
    assert result["state"] == "MIXED"
    assert "bullish" not in str(result).lower()
    assert "bearish" not in str(result).lower()


def test_positive_support_near_expiry_with_unknown_replacement_is_rolloff_imminent():
    result = compose_base(option_surface=None)
    assert result["state"] == "SUPPORT_ROLLOFF_IMMINENT"
    assert result["option_support"]["replacement_book"]["status"] == "unknown"
    assert any(row["predicate"] == "stabilizing_support_near_expiry" for row in result["state_basis"])


def test_short_gamma_expiration_does_not_assume_volatility_rises():
    risk = stabilizing_opex_risk()
    risk["gamma_regime"] = {"regime": "short", "net_gex_bn": -6.0}
    risk["states"]["pin_proximity"] = False
    result = compose_base(opex_risk=risk, option_surface=None)
    assert result["state"] != "VOLATILITY_WINDOW_OPEN"
    assert "short_gamma_expiry_can_remove_destabilizing_inventory" in result["invalidation"]


def test_authority_is_always_false_and_forbidden_fields_are_absent():
    result = compose_base()
    assert result["authority"] == {
        "can_rank": False,
        "can_gate": False,
        "can_size": False,
        "can_trade": False,
    }
    forbidden = {"score", "probability", "position_size", "order", "recommendation"}
    assert forbidden.isdisjoint(result)
```

- [ ] **Step 3: Write failing precedence and evidence-minimum tests**

```python

def test_high_impact_collision_precedes_opex_state():
    event = {
        "type": "CPI",
        "date": "2026-09-18",
        "time_et": "08:30",
        "scheduled_at": "2026-09-18T08:30:00-04:00",
        "impact": "high",
        "is_context_only": True,
        "collision": "cpi_in_opex_week",
    }
    result = compose_base(events=[event])
    assert result["state"] == "CATALYST_DOMINANT"


def test_observed_nonquiet_month_end_pulse_precedes_support_state():
    result = compose_base(
        now=datetime(2026, 9, 30, 16, 5, tzinfo=ET),
        opex=opex_phase(td_to=None, td_since=8, in_week=False),
        rebalance_calendar={"in_qtr_end_window": True, "available_at": "2026-09-30T00:00:00-04:00"},
        rebalance_pulse={"class": "mechanical_spike_distributed", "date": "2026-09-30", "available_at": "2026-09-30T16:01:00-04:00"},
    )
    assert result["state"] == "MONTH_END_REBALANCE_DOMINANT"


def test_calendar_window_without_observed_pulse_is_not_dominant():
    result = compose_base(
        now=datetime(2026, 9, 30, 12, 0, tzinfo=ET),
        rebalance_calendar={"in_qtr_end_window": True, "available_at": "2026-09-30T00:00:00-04:00"},
        rebalance_pulse=None,
    )
    assert result["state"] != "MONTH_END_REBALANCE_DOMINANT"
    assert result["rebalance"]["status"] == "scheduled_unconfirmed"


def test_volatility_window_requires_independent_realized_confirmation():
    prior = compose_base(option_surface=None)
    result = compose_base(
        now=datetime(2026, 9, 21, 11, 0, tzinfo=ET),
        opex=opex_phase(td_to=None, td_since=1, in_week=False),
        opex_risk={**stabilizing_opex_risk(), "realized_confirmation": {"volatility_expanding": True, "source": "existing_market_owner"}},
        prior_clock=prior,
    )
    assert result["state"] == "VOLATILITY_WINDOW_OPEN"
```

- [ ] **Step 4: Write failing null, contradiction and determinism tests**

```python

def test_missing_core_families_returns_unknown_with_exact_gaps():
    result = ptc.compose(
        now=NOW, events=[], opex=None, opex_risk=None, option_surface=None,
        rebalance_calendar=None, rebalance_pulse=None, treasury=None,
        futures_roll=None, prior_clock=None,
    )
    assert result["state"] == "UNKNOWN"
    assert set(result["gaps"]) >= {"calendar_unavailable", "option_support_unavailable", "treasury_liquidity_unavailable"}


def test_contradictory_support_and_drain_is_mixed():
    result = compose_base(
        option_surface=surface_rows(fm_oi_prior=0.20, fm_oi_now=0.36),
        treasury={"state": "draining", "asof": "2026-09-17", "available_at": "2026-09-17T16:30:00-04:00"},
        opex=opex_phase(td_to=5, td_since=None, in_week=False),
    )
    assert result["state"] == "MIXED"
    assert result["disagreements"]


def test_input_order_does_not_change_semantic_payload():
    rows = surface_rows(fm_oi_prior=0.20, fm_oi_now=0.36)
    a = compose_base(option_surface=rows)
    b = compose_base(option_surface=list(reversed(rows)))
    assert a == b
```

- [ ] **Step 5: Run focused tests and record RED**

```bash
python -m pytest tests/test_policy_turn_clock.py -q
```

Expected: import failure for missing engine.

- [ ] **Step 6: Implement pure axes and state selection**

Use small private functions with explicit return mappings:

```python
def _calendar_axis(now, events, opex, rebalance_calendar, futures_roll): ...
def _replacement_book(option_surface): ...
def _option_axis(now, opex, opex_risk, option_surface): ...
def _treasury_axis(treasury): ...
def _rebalance_axis(rebalance_calendar, rebalance_pulse): ...
def _catalyst_axis(now, events): ...
def _select_state(axes, prior_clock): ...
def _changes(prior_clock, current_axes, state): ...
```

Each helper validates owner passports and freshness before interpretation. Comparison of option rows requires same root and root class, strictly ordered observation dates, explicit availability, and the dealer-sign assumption. Missing or incomparable observations return typed statuses.

Implement the design’s exact state precedence without weights. `state_basis` is constructed from the predicates that actually selected the state. Bilingual phrases come from constant dictionaries keyed by predicate; input prose never becomes unescaped product copy.

- [ ] **Step 7: Run tests, compile and authority scan**

```bash
python -m pytest tests/test_policy_turn_clock.py -q
python -m py_compile engine/policy_turn_clock.py
! git grep -n "policy_turn_clock" -- 'engine/conditions.py' 'engine/risk_sizing.py' 'engine/prophet*' 'engine/*order*'
! git grep -nE '"(score|position_size|order|recommendation)"[[:space:]]*:' engine/policy_turn_clock.py
git diff --check
```

Expected: tests/compile pass and both negated scans exit 0.

- [ ] **Step 8: Commit Task 4**

```bash
git add engine/policy_turn_clock.py tests/test_policy_turn_clock.py
git commit -m "feat(policy-clock): compose monthly transition state"
```

---

### Task 5: Builder, machine artifact and prospective receipt

**Files:**
- Create: `scripts/build_policy_turn_clock.py`
- Create: `tests/test_build_policy_turn_clock.py`
- Read/Reuse: `engine/ledger_lane.py`

**Interfaces:**
- Consumes: official-event evidence/status, canonical owner artifacts and injected clock/root.
- Produces:
  - `gather_inputs(*, root: Path, now: datetime) -> dict[str, object]`
  - `build_payload(*, root: Path, now: datetime) -> dict[str, object]`
  - `write_payload(payload, *, root: Path) -> Path`
  - `append_forward_receipt(payload, *, root: Path) -> bool`
  - CLI `main(argv=None) -> int`

- [ ] **Step 1: Write failing complete/unknown and atomic-write tests**

```python
import json
from pathlib import Path

from scripts import build_policy_turn_clock as builder


def test_builder_always_writes_schema_shaped_unknown_artifact(tmp_path: Path):
    payload = builder.build_payload(root=tmp_path, now=NOW)
    assert payload["schema"] == "policy_turn_clock.v1"
    assert payload["state"] == "UNKNOWN"
    out = builder.write_payload(payload, root=tmp_path)
    assert out == tmp_path / "site/policy_turn_clock.json"
    saved = json.loads(out.read_text())
    assert saved == payload


def test_write_payload_uses_atomic_sibling_replace(monkeypatch, tmp_path: Path):
    replaced: list[tuple[Path, Path]] = []
    monkeypatch.setattr(builder.os, "replace", lambda src, dst: replaced.append((Path(src), Path(dst))))
    builder.write_payload({"schema": "policy_turn_clock.v1", "state": "UNKNOWN"}, root=tmp_path)
    assert replaced[0][0].name == "policy_turn_clock.json.tmp"
    assert replaced[0][1].name == "policy_turn_clock.json"
```

- [ ] **Step 2: Write failing stale-input and last-good-evidence tests**

```python

def test_failed_collector_preserves_events_but_marks_source_gap(tmp_path: Path):
    data = tmp_path / "data/policy_events"
    data.mkdir(parents=True)
    pd.DataFrame([_event_revision("1", "scheduled", "2026-09-03T06:00:00-04:00")]).to_parquet(data / "official_events.parquet", index=False)
    (data / "collector_status.json").write_text(json.dumps({
        "schema": "policy_event_collector_status.v1",
        "generated_at": "2026-09-03T11:00:00-04:00",
        "sources": {"fed_board": {"status": "failed", "last_success_at": "2026-09-03T06:00:00-04:00", "error_code": "SOURCE_UNAVAILABLE"}},
    }))
    payload = builder.build_payload(root=tmp_path, now=datetime(2026, 9, 3, 12, 0, tzinfo=ET))
    assert "fed_board_failed" in payload["gaps"]
    assert payload["actor_clock"]["events"]
```

- [ ] **Step 3: Write failing keep-FIRST prospective receipt tests**

```python

def test_forward_receipt_is_nightly_only_and_keep_first(monkeypatch, tmp_path: Path):
    payload = {
        "schema": "policy_turn_clock.v1",
        "as_of": "2026-09-17",
        "generated_at": "2026-09-17T12:00:00-04:00",
        "evidence_cutoff": "2026-09-17T12:00:00-04:00",
        "state": "SUPPORT_ROLLOFF_IMMINENT",
        "state_basis": [], "confirmation": [], "invalidation": [], "gaps": [],
        "authority": {"can_rank": False, "can_gate": False, "can_size": False, "can_trade": False},
    }
    monkeypatch.setattr(builder, "nightly_advance_enabled", lambda: False)
    assert builder.append_forward_receipt(payload, root=tmp_path) is False
    assert not (tmp_path / "data/policy_turn_clock/forward_log.jsonl").exists()

    monkeypatch.setattr(builder, "nightly_advance_enabled", lambda: True)
    assert builder.append_forward_receipt(payload, root=tmp_path) is True
    assert builder.append_forward_receipt(payload, root=tmp_path) is False
    rows = [json.loads(line) for line in (tmp_path / "data/policy_turn_clock/forward_log.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["trigger_kind"] == "opex_t_minus_2_or_rolloff"
    assert rows[0]["original_evidence_cutoff"] == "2026-09-17T12:00:00-04:00"
```

- [ ] **Step 4: Run tests and record RED**

```bash
python -m pytest tests/test_build_policy_turn_clock.py -q
```

Expected: import failure for the missing builder.

- [ ] **Step 5: Implement bounded I/O and owner adapters**

`gather_inputs` reads only known paths and uses small adapters that preserve raw owner payloads plus explicit `available_at`/`null_reason`. It calls:

- `policy_event_clock.current_records` over the Parquet rows;
- `event_calendar.policy_turn_events`;
- `futures_roll_calendar.snapshot`;
- `engine.opex.snapshot` when a canonical SPY close series is available;
- `engine.opex_risk.snapshot` or its existing generated payload;
- latest comparable option-surface rows;
- `rebalance_calendar.tag(now.date())` and current rebalance-pulse artifact;
- `treasury_watch.snapshot`.

One missing owner must not erase other axes. No adapter substitutes an alternate data source.

`write_payload` serializes with sorted keys/UTF-8 through `site/policy_turn_clock.json.tmp`, flushes, then `os.replace`.

`append_forward_receipt` checks `nightly_advance_enabled()`, determines a frozen trigger identity, scans existing JSONL identities, appends one newline-delimited row and fsyncs. It never mutates a prior row.

- [ ] **Step 6: Run builder tests and a local empty-root smoke test**

```bash
python -m pytest tests/test_build_policy_turn_clock.py -q
python -m scripts.build_policy_turn_clock --root "$(mktemp -d)"
python -m py_compile scripts/build_policy_turn_clock.py
git diff --check
```

Expected: tests pass; CLI writes an `UNKNOWN` artifact and exits 0.

- [ ] **Step 7: Commit Task 5**

```bash
git add scripts/build_policy_turn_clock.py tests/test_build_policy_turn_clock.py
git commit -m "feat(policy-clock): build artifact and prospective receipt"
```

---

### Task 6: Policy Watch decision composition

**Files:**
- Create: `templates/partials/_policy_turn_clock.html.j2`
- Modify: `scripts/build_policy_watch.py`
- Modify: `templates/policy_watch.html.j2`
- Modify: `tests/test_policy_watch_ui.py`
- Generated: `site/policy_watch.html`
- Evidence: `mockups/refs/policy-turn-clock/**`

**Interfaces:**
- Consumes: `site/policy_turn_clock.json` as `turn_clock`.
- Produces: one accessible bilingual glance/detail component; no independent semantic calculation.

- [ ] **Step 1: Write failing builder and template-structure tests**

```python

def test_policy_watch_builder_reads_turn_clock_without_recomputing():
    source = (ROOT / "scripts/build_policy_watch.py").read_text()
    assert 'site / "policy_turn_clock.json"' in source
    assert "turn_clock=turn_clock" in source
    assert "policy_turn_clock.compose" not in source


def test_policy_watch_includes_one_policy_turn_clock_partial():
    template = (ROOT / "templates/policy_watch.html.j2").read_text()
    assert template.count('include "partials/_policy_turn_clock.html.j2"') == 1


def test_turn_clock_partial_has_now_next_confirm_invalidate_and_coverage_layers():
    partial = (ROOT / "templates/partials/_policy_turn_clock.html.j2").read_text()
    for token in (
        "ptc-now", "ptc-next", "ptc-confirm", "ptc-invalidate", "ptc-coverage",
        "l-en", "l-zh", "data-ptc-state",
    ):
        assert token in partial
    for forbidden in ("buy", "sell", "position size", "bullish", "bearish"):
        assert forbidden not in partial.lower()
```

- [ ] **Step 2: Add a source-faithful UI fixture and rendered-state tests**

Create the fixture inside the test file and render through the existing Jinja environment. Assert:

```python

def test_turn_clock_partial_renders_unknown_and_cancelled_events_honestly():
    html = render_turn_clock({
        "schema": "policy_turn_clock.v1",
        "state": "UNKNOWN",
        "state_basis": [],
        "change_from_prior": {"changed": False, "prior_state": None, "changed_axes": []},
        "calendar": {},
        "actor_clock": {"events": [{"headline": "Economic Outlook", "status": "cancelled", "scheduled_start": "2026-09-03T08:30:00-04:00"}]},
        "treasury_liquidity": {"status": "stale"},
        "option_support": {"status": "unavailable"},
        "futures_roll": {"equity_index": {"status": "not_applicable"}},
        "rebalance": {"status": "scheduled_unconfirmed"},
        "catalysts": [],
        "confirmation": [],
        "invalidation": [],
        "gaps": ["fed_board_failed", "option_support_unavailable"],
        "freshness": {},
        "authority": {"can_rank": False, "can_gate": False, "can_size": False, "can_trade": False},
    })
    assert "UNKNOWN" in html
    assert "cancelled" in html
    assert "fed_board_failed" in html
    assert "option_support_unavailable" in html
```

- [ ] **Step 3: Run UI tests and record RED**

```bash
python -m pytest tests/test_policy_watch_ui.py -q
```

Expected: new assertions fail because the partial/integration does not exist.

- [ ] **Step 4: Implement defensive builder loading**

In `scripts/build_policy_watch.py`, load `site/policy_turn_clock.json` into `turn_clock`. Reject non-dict/wrong-schema payloads into an explicit schema-shaped unavailable view; do not suppress the component. Pass it to Jinja. Do not import the composer.

- [ ] **Step 5: Implement the partial and include it once**

Use the existing `t(...)`/language conventions. Render:

- current state and change chip;
- support inventory and monthly phase;
- at most five next-72-hour records sorted by scheduled timestamp;
- up to three confirm and three invalidate rows;
- gaps/freshness chips;
- expandable evidence with clocks, source links, announced/accepted amount distinctions and dealer passports.

Use semantic text plus icons, not color alone. Treat raw source strings as escaped data. All labels have EN/ZH twins.

- [ ] **Step 6: Add responsive component CSS in the owning template block**

Use a single-column layout by default, two-column detail at `min-width: 768px`, and no fixed card heights. Preserve 390px readability and `overflow-wrap:anywhere` for source/event text. Do not create a second full-width hero that displaces the current policy thesis.

- [ ] **Step 7: Run UI/template guards and build the page**

```bash
python -m pytest tests/test_policy_watch_ui.py -q
python -m scripts.build_policy_turn_clock
python -m scripts.build_policy_watch
python -m scripts.check_template_site_sync
python -m scripts.check_design_system --mode enforce-added
python -m scripts.check_ui_visual_evidence
git diff --check
```

Expected: tests and guards pass; both site artifacts are generated.

- [ ] **Step 8: Capture browser evidence with exact theme/language state**

Start the local server:

```bash
python -m http.server 8765 --directory site > /tmp/policy-turn-clock-http.log 2>&1 &
echo $! > /tmp/policy-turn-clock-http.pid
```

Run this Playwright script from the repository root:

```bash
node <<'NODE'
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const browser = await chromium.launch({headless: true});
  const cases = [
    {w:1440,h:1200,theme:'dark',lang:'en'},
    {w:1440,h:1200,theme:'light',lang:'zh'},
    {w:768,h:1024,theme:'dark',lang:'en'},
    {w:768,h:1024,theme:'light',lang:'zh'},
    {w:390,h:844,theme:'dark',lang:'en'},
    {w:390,h:844,theme:'light',lang:'zh'},
  ];
  fs.mkdirSync('mockups/refs/policy-turn-clock', {recursive:true});
  for (const c of cases) {
    const context = await browser.newContext({viewport:{width:c.w,height:c.h}});
    await context.addInitScript(({theme,lang}) => {
      localStorage.setItem('theme', theme);
      localStorage.setItem('lang', lang);
    }, {theme:c.theme,lang:c.lang});
    const page = await context.newPage();
    await page.goto('http://127.0.0.1:8765/policy_watch.html', {waitUntil:'networkidle'});
    const card = page.locator('[data-ptc-state]');
    if (await card.count() !== 1) throw new Error('expected exactly one policy-turn-clock component');
    const box = await card.boundingBox();
    if (!box || box.width > c.w || box.x < 0) throw new Error(`overflow at ${c.w}/${c.theme}/${c.lang}`);
    await page.screenshot({path:`mockups/refs/policy-turn-clock/${c.w}-${c.theme}-${c.lang}.png`, fullPage:true});
    await context.close();
  }
  await browser.close();
})();
NODE
kill "$(cat /tmp/policy-turn-clock-http.pid)"
```

Inspect every image. Record exact defects fixed and final dimensions in the PR body.

- [ ] **Step 9: Commit Task 6**

```bash
git add scripts/build_policy_watch.py templates/partials/_policy_turn_clock.html.j2 templates/policy_watch.html.j2 tests/test_policy_watch_ui.py site/policy_watch.html mockups/refs/policy-turn-clock
git commit -m "feat(policy-clock): render pre-turn decision composition"
```

---

### Task 7: Existing hourly/nightly workflow, DAG and CI wiring

**Files:**
- Modify: `config/dag.yml`
- Modify: `.github/workflows/whitehouse-sentinel.yml`
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/test_dag_conformance.py` only if the existing conformance test needs an explicit expected row and the change remains within current owner semantics.

**Interfaces:**
- Consumes: existing hourly White House sentinel and nightly pipeline conventions.
- Produces: official-event poll → clock build → Policy Watch rebuild on the existing scheduler; nightly-only forward receipt; focused CI coverage.

- [ ] **Step 1: Write/extend failing workflow conformance assertions**

Add exact checks to the existing DAG/workflow test location:

```python

def test_policy_turn_clock_reuses_whitehouse_hourly_scheduler():
    workflow = (ROOT / ".github/workflows/whitehouse-sentinel.yml").read_text()
    assert "python -m collectors.policy_event_clock" in workflow
    assert "python -m scripts.build_policy_turn_clock" in workflow
    assert "python -m scripts.build_policy_watch" in workflow
    assert workflow.count("schedule:") == 1
    assert "data/policy_events/official_events.parquet" in workflow
    assert "site/policy_turn_clock.json" in workflow


def test_policy_turn_clock_never_touches_legacy_ci_manifest():
    changed = set(subprocess.check_output(["git", "diff", "--name-only", "origin/main...HEAD"], text=True).splitlines())
    assert ".github/ci/legacy-jobs.yml" not in changed
```

- [ ] **Step 2: Run conformance tests and record RED**

```bash
python -m pytest tests/test_dag_conformance.py -q
```

Expected: new workflow assertions fail before wiring.

- [ ] **Step 3: Register the existing pipeline sequence in `config/dag.yml`**

Declare the collector before the clock builder and the builder before Policy Watch. Mark:

- official event collector as hourly/bounded network I/O;
- clock builder as deterministic artifact composition;
- Policy Watch as consumer;
- forward ledger as nightly-only;
- all failures non-fatal to unrelated product builds but visible through collector status and artifact gaps.

Do not create a second pipeline lane or authority.

- [ ] **Step 4: Extend the existing hourly workflow**

Add three steps to `.github/workflows/whitehouse-sentinel.yml` after checkout/dependencies and before the existing commit step:

```yaml
- name: collect official policy event clock
  run: python -m collectors.policy_event_clock

- name: build policy turn clock
  env:
    MMX_LEDGER_LANE: hourly
  run: python -m scripts.build_policy_turn_clock

- name: rebuild policy watch
  run: python -m scripts.build_policy_watch
```

Expand only the existing commit allowlist to include:

```text
data/policy_events/official_events.parquet
data/policy_events/collector_status.json
site/policy_turn_clock.json
site/policy_watch.html
```

Do not include `data/policy_turn_clock/forward_log.jsonl` in the hourly commit path.

- [ ] **Step 5: Add focused CI paths/tests without editing the colliding manifest**

Register the four new test files and changed source paths in `.github/workflows/ci.yml` using the nearest existing rates/policy/options test job. Do not create another CI job if an existing one can own the files. Explicitly include `tests/test_policy_watch_ui.py` in the same visual/template gate already responsible for Policy Watch.

- [ ] **Step 6: Run workflow, DAG and full focused suite**

```bash
python -m pytest tests/test_policy_event_clock.py tests/test_futures_roll_calendar.py tests/test_policy_turn_clock.py tests/test_build_policy_turn_clock.py tests/test_policy_watch_ui.py tests/test_dag_conformance.py -q
python - <<'PY'
from pathlib import Path
import yaml
for path in (Path('.github/workflows/whitehouse-sentinel.yml'), Path('.github/workflows/ci.yml'), Path('config/dag.yml')):
    yaml.safe_load(path.read_text())
    print(f"valid {path}")
PY
! git diff --name-only origin/main...HEAD | grep -Fx '.github/ci/legacy-jobs.yml'
git diff --check
```

Expected: tests pass; YAML parses; the protected colliding path is absent.

- [ ] **Step 7: Commit Task 7**

```bash
git add config/dag.yml .github/workflows/whitehouse-sentinel.yml .github/workflows/ci.yml tests/test_dag_conformance.py
git commit -m "ci(policy-clock): wire existing hourly and nightly lanes"
```

If `tests/test_dag_conformance.py` was not changed, omit it from `git add`.

---

### Task 8: Real-source proof, prospective receipt and immutable return

**Files:**
- Generate/update: `data/policy_events/official_events.parquet`
- Generate/update: `data/policy_events/collector_status.json`
- Generate/update: `data/policy_turn_clock/forward_log.jsonl` only from a truthful nightly-lane proof
- Generate/update: `site/policy_turn_clock.json`
- Generate/update: `site/policy_watch.html`
- Generate: `mockups/refs/policy-turn-clock/**`
- PR evidence only: source receipts, commands, digests, browser and machine-consumer proof.

**Interfaces:**
- Consumes: real official sources and current repository artifacts.
- Produces: one immutable implementation head and a complete return packet for independent review/Sol acceptance.

- [ ] **Step 1: Re-pin procedure, current main and path ownership before real effects**

Record exact outputs:

```bash
git fetch origin main
git rev-parse origin/main
git rev-parse HEAD
git status --short
git diff --name-only "$(git merge-base origin/main HEAD)"...HEAD
```

Fresh-read issue #6787, PR #6721, PR #6658, PR #6593 and current protected Skillpack. If any planned path is newly owned by another active carrier, post `BLOCKED PATH_COLLISION` on #6787 and stop without widening.

- [ ] **Step 2: Run the real official-source collector**

```bash
python -m collectors.policy_event_clock
python - <<'PY'
import json
from pathlib import Path
import pandas as pd
p = Path('data/policy_events/official_events.parquet')
s = Path('data/policy_events/collector_status.json')
assert p.exists(), p
assert s.exists(), s
rows = pd.read_parquet(p)
status = json.loads(s.read_text())
assert not rows.empty
assert status['schema'] == 'policy_event_collector_status.v1'
assert {'source_key','source_event_id','source_revision','available_at','content_sha256'}.issubset(rows.columns)
print(rows.groupby('source_key').size().to_dict())
print(json.dumps(status, indent=2, sort_keys=True))
PY
```

Record per-source last-success times, row counts, and any gaps. Do not describe a failed source as complete coverage.

- [ ] **Step 3: Build and validate current machine artifact**

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

- [ ] **Step 4: Prove a real machine consumer uses JSON, not HTML**

Run:

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

This is the minimum machine-contract proof. A stronger existing Terminal consumer may replace it only if it reads the same contract directly and is evidenced.

- [ ] **Step 5: Freeze one prospective receipt before a real event/window**

Use the existing nightly-lane environment only when the execution is truthfully running in the accepted nightly context. Never set the gate variable merely to manufacture a receipt. Inspect the resulting row:

```bash
python - <<'PY'
import json
from pathlib import Path
p = Path('data/policy_turn_clock/forward_log.jsonl')
assert p.exists()
rows = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
assert rows
last = rows[-1]
for key in ('trigger_kind','trigger_id','method_version','original_evidence_cutoff','state','confirmation','invalidation'):
    assert key in last, key
print(json.dumps(last, indent=2, sort_keys=True))
PY
```

If no trigger is currently eligible, report `PROSPECTIVE_TRIGGER_NOT_YET_ELIGIBLE` and leave the file untouched; do not backdate or lower the gate.

- [ ] **Step 6: Run complete local verification**

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

Then run the repository’s exact current full semantic CI command or push the immutable candidate and wait for hosted CI. Do not claim full green from the focused suite.

- [ ] **Step 7: Adversarial mutation pass**

Temporarily create and kill at least these mutants without committing them:

1. collapse `accepted_usd_bn` into announced maximum;
2. keep-LAST instead of keep-FIRST;
3. allow expired event location to remain current;
4. mark quarterly roll active without progress;
5. let OPEX date alone produce rolloff/volatility state;
6. let calendar-only month-end become dominant;
7. remove dealer-sign passport;
8. permit `can_trade=True`;
9. let hourly lane append the forward ledger;
10. delete stale-source gap propagation.

For each mutant, record the exact test that fails. Restore the clean candidate after every mutation and verify `git diff --check`.

- [ ] **Step 8: Push one immutable implementation candidate and open Draft/HOLD-FOR-SOL PR**

The PR body must include:

```text
operation key
protected procedure SHA
pickup/current-main SHA
exact head and tree
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
capability = BUILT_NOT_PROVEN until real production acceptance
```

Do not mark Ready, add merge-on-green, enable auto-merge, merge or deploy.

- [ ] **Step 9: Return and stop**

Post one same-carrier `RESULT / HOLD-FOR-SOL` on issue #6787 with exact head/tree, evidence and unresolved gaps. Preserve the worker continuation path until Sol issues explicit `CONTINUE` or terminal `STOP`. Do not start PTC-W2 or PTC-W3.
