"""Tests for FTR W9 grading pack.

engine/basket_turn_cohort.py + engine/tape_disagreement.py

Covers:
  (1) form_cohorts — multi-basket same-day → ONE cohort
  (2) form_cohorts — WATCH rows excluded (IGNITION-only)
  (3) form_cohorts — no backfill (pre-SHIP_DATE rows excluded)
  (4) form_cohorts — cohort_id == cohort_date (ISO string)
  (5) register_cohort_claims — COLLECT_LANE gate (no writes when gate absent)
  (6) register_cohort_claims — keep-first idempotency (re-run does not duplicate)
  (7) register_cohort_claims — new claims have status "open"
  (8) detect_disagreement_events — fires on IGNITION + non-aligned slow reco
  (9) detect_disagreement_events — does NOT fire on IGNITION + aligned reco
  (10) detect_disagreement_events — does NOT fire on WATCH state
  (11) detect_disagreement_events — fires when slow_reco is None (honest null)
  (12) tape_disagreement nightly_run — COLLECT_LANE gate (no writes when absent)
  (13) tape_disagreement nightly_run — keep-first idempotency (same event, two runs)
  (14) censoring states — outcome_10d/21d start as None (right-censored)
  (15) update_outcomes — fills outcome when window elapsed + tape faded
  (16) basket_turn_cohort nightly_run — exit-0-always (empty ledger)
  (17) tape_disagreement nightly_run — exit-0-always (empty turn-watch ledger)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.basket_turn_cohort as BTC
import engine.tape_disagreement as TD

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TODAY = "2026-07-09"
_SHIP_DATE = "2026-07-09"
_BEFORE_SHIP = "2026-07-08"  # one day before ship date


def _make_turn_watch_ledger(rows: list[dict], data_root: Path) -> Path:
    """Write a fake ledger.jsonl to data_root/basket_turn/ledger.jsonl."""
    d = data_root / "basket_turn"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "ledger.jsonl"
    with p.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return p


def _make_ignition_row(basket_id: str, date_str: str, **kwargs) -> dict:
    return {
        "basket_id": basket_id,
        "date": date_str,
        "state": "IGNITION",
        "k": 3,
        "legs": {"impulse_day": True, "rs_z": True, "breadth_surge": True,
                 "volume_confirm": False, "complex_confirm": False, "shock_relative_bid": False},
        "as_of": date_str,
        **kwargs,
    }


def _make_watch_row(basket_id: str, date_str: str) -> dict:
    return {
        "basket_id": basket_id,
        "date": date_str,
        "state": "WATCH",
        "k": 2,
        "legs": {"impulse_day": True, "rs_z": False, "breadth_surge": True,
                 "volume_confirm": False, "complex_confirm": False, "shock_relative_bid": False},
        "as_of": date_str,
    }


def _make_baskets_json(data_root: Path, baskets: list[dict]) -> None:
    """Write a fake site/basketdata/baskets.json under data_root (simulating site dir)."""
    site_dir = data_root / "site" / "basketdata"
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "baskets.json").write_text(
        json.dumps({"baskets": baskets}), encoding="utf-8"
    )


# Monkey-patch config.ROOT and config.data_dir for isolation
def _patch_config(data_root: Path):
    """Return a context that patches config so site/ resolves under data_root."""
    import lib.config as cfg
    cfg_mock = MagicMock()
    cfg_mock.ROOT = data_root
    cfg_mock.data_dir.return_value = data_root
    cfg_mock.load.return_value = {"storage": {"site_dir": "site"}}
    return cfg_mock


# ---------------------------------------------------------------------------
# (1) form_cohorts — multi-basket same-day → ONE cohort
# ---------------------------------------------------------------------------

def test_form_cohorts_multi_basket_same_day():
    """Multiple baskets reaching IGNITION on the same day → one cohort."""
    rows = [
        _make_ignition_row("ai_semiconductors", _TODAY),
        _make_ignition_row("semicap_equipment", _TODAY),
    ]
    cohorts = BTC.form_cohorts(rows, ship_date=_SHIP_DATE)
    assert len(cohorts) == 1, f"Expected 1 cohort, got {len(cohorts)}"
    c = cohorts[0]
    assert c["cohort_id"] == _TODAY
    assert set(c["basket_ids"]) == {"ai_semiconductors", "semicap_equipment"}
    assert c["n_baskets"] == 2


# ---------------------------------------------------------------------------
# (2) form_cohorts — WATCH rows excluded
# ---------------------------------------------------------------------------

def test_form_cohorts_watch_rows_excluded():
    """WATCH-state rows must NOT generate cohorts."""
    rows = [
        _make_watch_row("ai_semiconductors", _TODAY),
        _make_watch_row("semicap_equipment", _TODAY),
    ]
    cohorts = BTC.form_cohorts(rows, ship_date=_SHIP_DATE)
    assert cohorts == [], "WATCH rows should produce no cohorts"


# ---------------------------------------------------------------------------
# (3) form_cohorts — no backfill
# ---------------------------------------------------------------------------

def test_form_cohorts_no_backfill():
    """Rows before SHIP_DATE must NOT generate cohorts."""
    rows = [
        _make_ignition_row("ai_semiconductors", _BEFORE_SHIP),
    ]
    cohorts = BTC.form_cohorts(rows, ship_date=_SHIP_DATE)
    assert cohorts == [], "Pre-ship-date IGNITION rows should produce no cohorts"


# ---------------------------------------------------------------------------
# (4) form_cohorts — cohort_id == cohort_date
# ---------------------------------------------------------------------------

def test_form_cohorts_cohort_id_equals_date():
    """cohort_id must equal the ISO date string."""
    rows = [_make_ignition_row("ai_semiconductors", _TODAY)]
    cohorts = BTC.form_cohorts(rows, ship_date=_SHIP_DATE)
    assert len(cohorts) == 1
    assert cohorts[0]["cohort_id"] == _TODAY
    assert cohorts[0]["cohort_date"] == _TODAY


# ---------------------------------------------------------------------------
# (5) register_cohort_claims — COLLECT_LANE gate
# ---------------------------------------------------------------------------

def test_register_cohort_claims_gate_absent(monkeypatch, tmp_path):
    """When COLLECT_LANE is not 'nightly', no claims are registered."""
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)

    cohorts = [{"cohort_id": _TODAY, "cohort_date": _TODAY,
                "basket_ids": ["ai_semiconductors"], "n_baskets": 1, "legs": {}}]
    result = BTC.register_cohort_claims(cohorts, data_root=tmp_path)
    assert result == [], "No claims should be registered when gate is absent"


# ---------------------------------------------------------------------------
# (6) register_cohort_claims — keep-first idempotency
# ---------------------------------------------------------------------------

def test_register_cohort_claims_keep_first(monkeypatch, tmp_path):
    """Running register_cohort_claims twice for the same cohort should
    only register the claim once."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    cohorts = [{"cohort_id": _TODAY, "cohort_date": _TODAY,
                "basket_ids": ["ai_semiconductors"], "n_baskets": 1, "legs": {}}]

    mock_qledger = MagicMock()
    mock_qledger.make_claim.return_value = {"desk": "basket_turn.v1", "asof": _TODAY}
    mock_qledger.register_batch.return_value = [{"status": "open", "claim_id": "abc"}]

    with patch.dict("sys.modules", {"engine.qledger": mock_qledger}):
        # First run
        BTC.register_cohort_claims(cohorts, data_root=tmp_path)
        # Second run — cohort log should prevent re-registration
        result2 = BTC.register_cohort_claims(cohorts, data_root=tmp_path)

    assert result2 == [], "Second run should produce no new claims (keep-first)"


# ---------------------------------------------------------------------------
# (7) register_cohort_claims — new claims have status "open"
# ---------------------------------------------------------------------------

def test_register_cohort_claims_status_open(monkeypatch, tmp_path):
    """Newly registered claims should have status 'open'."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    cohorts = [{"cohort_id": _TODAY, "cohort_date": _TODAY,
                "basket_ids": ["ai_semiconductors"], "n_baskets": 1, "legs": {}}]

    mock_qledger = MagicMock()
    mock_qledger.make_claim.return_value = {"desk": "basket_turn.v1", "asof": _TODAY}
    mock_qledger.register_batch.return_value = [{"status": "open", "claim_id": "abc123"}]

    with patch.dict("sys.modules", {"engine.qledger": mock_qledger}):
        registered = BTC.register_cohort_claims(cohorts, data_root=tmp_path)

    assert len(registered) == 1
    assert registered[0]["status"] == "open"


# ---------------------------------------------------------------------------
# (8) detect_disagreement_events — fires on IGNITION + non-aligned reco
# ---------------------------------------------------------------------------

def test_detect_disagreement_fires_on_ignition_hold():
    """IGNITION + slow_reco='hold' → one disagreement event."""
    turn_watch_rows = [_make_ignition_row("ai_semiconductors", _TODAY)]
    baskets_map = {"ai_semiconductors": {"id": "ai_semiconductors", "reco": "hold"}}

    events = TD.detect_disagreement_events(
        as_of=_TODAY,
        turn_watch_rows=turn_watch_rows,
        baskets_map=baskets_map,
        ship_date=_SHIP_DATE,
    )
    assert len(events) == 1
    ev = events[0]
    assert ev["basket_id"] == "ai_semiconductors"
    assert ev["event_date"] == _TODAY
    assert ev["turn_watch_state"] == "IGNITION"
    assert ev["slow_reco"] == "hold"
    assert ev["outcome_10d"] is None   # right-censored
    assert ev["outcome_21d"] is None   # right-censored
    assert ev["censored_10d"] is True
    assert ev["censored_21d"] is True


def test_detect_disagreement_fires_on_ignition_avoid():
    """IGNITION + slow_reco='avoid' → one disagreement event."""
    turn_watch_rows = [_make_ignition_row("semicap_equipment", _TODAY)]
    baskets_map = {"semicap_equipment": {"id": "semicap_equipment", "reco": "avoid"}}

    events = TD.detect_disagreement_events(
        as_of=_TODAY,
        turn_watch_rows=turn_watch_rows,
        baskets_map=baskets_map,
        ship_date=_SHIP_DATE,
    )
    assert len(events) == 1
    assert events[0]["slow_reco"] == "avoid"


def test_detect_disagreement_fires_on_ignition_trim():
    """IGNITION + slow_reco='trim' → one disagreement event."""
    turn_watch_rows = [_make_ignition_row("biotech", _TODAY)]
    baskets_map = {"biotech": {"id": "biotech", "reco": "trim"}}

    events = TD.detect_disagreement_events(
        as_of=_TODAY,
        turn_watch_rows=turn_watch_rows,
        baskets_map=baskets_map,
        ship_date=_SHIP_DATE,
    )
    assert len(events) == 1


# ---------------------------------------------------------------------------
# (9) detect_disagreement_events — does NOT fire on IGNITION + aligned reco
# ---------------------------------------------------------------------------

def test_detect_disagreement_no_fire_on_enter():
    """IGNITION + slow_reco='enter' → NO disagreement event."""
    turn_watch_rows = [_make_ignition_row("ai_semiconductors", _TODAY)]
    baskets_map = {"ai_semiconductors": {"id": "ai_semiconductors", "reco": "enter"}}

    events = TD.detect_disagreement_events(
        as_of=_TODAY,
        turn_watch_rows=turn_watch_rows,
        baskets_map=baskets_map,
        ship_date=_SHIP_DATE,
    )
    assert events == [], "IGNITION + 'enter' should not fire a disagreement"


def test_detect_disagreement_no_fire_on_accumulate():
    """IGNITION + slow_reco='accumulate' → NO disagreement event."""
    turn_watch_rows = [_make_ignition_row("memory_storage", _TODAY)]
    baskets_map = {"memory_storage": {"id": "memory_storage", "reco": "accumulate"}}

    events = TD.detect_disagreement_events(
        as_of=_TODAY,
        turn_watch_rows=turn_watch_rows,
        baskets_map=baskets_map,
        ship_date=_SHIP_DATE,
    )
    assert events == [], "IGNITION + 'accumulate' should not fire a disagreement"


# ---------------------------------------------------------------------------
# (10) detect_disagreement_events — does NOT fire on WATCH state
# ---------------------------------------------------------------------------

def test_detect_disagreement_no_fire_on_watch():
    """WATCH state (not IGNITION) → no disagreement event, regardless of reco."""
    turn_watch_rows = [_make_watch_row("ai_semiconductors", _TODAY)]
    baskets_map = {"ai_semiconductors": {"id": "ai_semiconductors", "reco": "hold"}}

    events = TD.detect_disagreement_events(
        as_of=_TODAY,
        turn_watch_rows=turn_watch_rows,
        baskets_map=baskets_map,
        ship_date=_SHIP_DATE,
    )
    assert events == [], "WATCH state should not fire a disagreement"


# ---------------------------------------------------------------------------
# (11) detect_disagreement_events — fires when slow_reco is None
# ---------------------------------------------------------------------------

def test_detect_disagreement_fires_when_reco_none():
    """IGNITION + no slow_reco (basket not in baskets_map) → fires with reco=None."""
    turn_watch_rows = [_make_ignition_row("ai_semiconductors", _TODAY)]
    baskets_map = {}  # basket not present

    events = TD.detect_disagreement_events(
        as_of=_TODAY,
        turn_watch_rows=turn_watch_rows,
        baskets_map=baskets_map,
        ship_date=_SHIP_DATE,
    )
    assert len(events) == 1
    assert events[0]["slow_reco"] is None


# ---------------------------------------------------------------------------
# (12) tape_disagreement nightly_run — COLLECT_LANE gate
# ---------------------------------------------------------------------------

def test_tape_disagreement_gate_absent(monkeypatch, tmp_path):
    """tape_disagreement.nightly_run does not write when COLLECT_LANE absent."""
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)

    # Create a turn-watch ledger so the runner has something to process
    _make_turn_watch_ledger([_make_ignition_row("ai_semiconductors", _TODAY)], tmp_path)

    with patch("engine.tape_disagreement.config") as mock_cfg:
        mock_cfg.ROOT = tmp_path
        mock_cfg.data_dir.return_value = tmp_path
        mock_cfg.load.return_value = {"storage": {"site_dir": "site"}}

        result = TD.nightly_run(as_of=_TODAY, data_root=tmp_path, root=tmp_path)

    assert result["ok"] is True
    assert result.get("gate_skipped") is True
    assert result["n_new_events"] == 0

    # Ledger should NOT exist (no writes)
    ledger_path = tmp_path / "basket_turn" / "disagreement_ledger.jsonl"
    assert not ledger_path.exists(), "Ledger should not be written when gate is absent"


# ---------------------------------------------------------------------------
# (13) tape_disagreement nightly_run — keep-first idempotency
# ---------------------------------------------------------------------------

def test_tape_disagreement_keep_first_idempotency(monkeypatch, tmp_path):
    """Running nightly_run twice for the same event should not duplicate rows."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    _make_turn_watch_ledger([_make_ignition_row("ai_semiconductors", _TODAY)], tmp_path)
    _make_baskets_json(tmp_path, [{"id": "ai_semiconductors", "reco": "hold"}])

    with patch("engine.tape_disagreement.config") as mock_cfg:
        mock_cfg.ROOT = tmp_path
        mock_cfg.data_dir.return_value = tmp_path
        mock_cfg.load.return_value = {"storage": {"site_dir": "site"}}

        result1 = TD.nightly_run(as_of=_TODAY, data_root=tmp_path, root=tmp_path)
        result2 = TD.nightly_run(as_of=_TODAY, data_root=tmp_path, root=tmp_path)

    assert result1["n_new_events"] == 1
    assert result2["n_new_events"] == 0  # keep-first: no duplicate

    ledger_path = tmp_path / "basket_turn" / "disagreement_ledger.jsonl"
    rows = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]
    assert len(rows) == 1, f"Expected 1 row after two runs, got {len(rows)}"


# ---------------------------------------------------------------------------
# (14) censoring states — outcome_10d/21d start as None
# ---------------------------------------------------------------------------

def test_censoring_initial_state(monkeypatch, tmp_path):
    """Newly recorded events must have outcome_10d=None, outcome_21d=None (right-censored)."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    _make_turn_watch_ledger([_make_ignition_row("ai_semiconductors", _TODAY)], tmp_path)
    _make_baskets_json(tmp_path, [{"id": "ai_semiconductors", "reco": "hold"}])

    with patch("engine.tape_disagreement.config") as mock_cfg:
        mock_cfg.ROOT = tmp_path
        mock_cfg.data_dir.return_value = tmp_path
        mock_cfg.load.return_value = {"storage": {"site_dir": "site"}}

        TD.nightly_run(as_of=_TODAY, data_root=tmp_path, root=tmp_path)

    ledger_path = tmp_path / "basket_turn" / "disagreement_ledger.jsonl"
    rows = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]
    assert len(rows) == 1
    row = rows[0]
    assert row["outcome_10d"] is None, "outcome_10d should be None (right-censored at first write)"
    assert row["outcome_21d"] is None, "outcome_21d should be None (right-censored at first write)"
    assert row["censored_10d"] is True
    assert row["censored_21d"] is True


# ---------------------------------------------------------------------------
# (15) update_outcomes — fills outcome when window elapsed + tape faded
# ---------------------------------------------------------------------------

def test_update_outcomes_tape_faded(tmp_path):
    """update_outcomes fills 'tape_faded' when basket EW < SPY over the window."""
    event_date = "2026-05-01"  # far enough in the past that 10d + 21d have elapsed
    as_of = "2026-07-09"

    # Build a minimal baskets_map with one member
    baskets_map = {
        "ai_semiconductors": {
            "id": "ai_semiconductors",
            "reco": "hold",
            "members": ["NVDA"],
        }
    }

    # Write stub price data: NVDA flat, SPY up 5%
    stocks_dir = tmp_path / "stocks"
    stocks_dir.mkdir(parents=True, exist_ok=True)

    def _write_prices(ticker: str, start: str, n: int, daily_ret: float) -> None:
        idx = pd.bdate_range(start=start, periods=n)
        closes = [100.0]
        for _ in range(n - 1):
            closes.append(closes[-1] * (1 + daily_ret))
        df = pd.DataFrame({"close": closes}, index=idx)
        df.to_parquet(stocks_dir / f"{ticker}.parquet")

    _write_prices("NVDA", event_date, 30, 0.0)   # flat
    _write_prices("SPY",  event_date, 30, 0.002)  # ~0.2%/day → ~4% over 21d → tape faded

    rows = [{
        "basket_id":    "ai_semiconductors",
        "event_date":   event_date,
        "turn_watch_state": "IGNITION",
        "slow_reco":    "hold",
        "legs":         {},
        "outcome_10d":  None,
        "outcome_21d":  None,
        "censored_10d": True,
        "censored_21d": True,
    }]

    with patch("engine.tape_disagreement.config") as mock_cfg:
        mock_cfg.ROOT = tmp_path
        mock_cfg.data_dir.return_value = tmp_path

        updated = TD.update_outcomes(rows, baskets_map, as_of=as_of, data_root=tmp_path)

    assert len(updated) == 1
    row = updated[0]
    # Both windows should have elapsed (event was 2026-05-01, as_of 2026-07-09)
    assert row["censored_10d"] is False, "10d window should have elapsed"
    assert row["censored_21d"] is False, "21d window should have elapsed"
    # SPY went up, NVDA flat → basket EW < SPY → tape_faded
    assert row["outcome_10d"] == "tape_faded", f"Expected tape_faded, got {row['outcome_10d']}"
    assert row["outcome_21d"] == "tape_faded", f"Expected tape_faded, got {row['outcome_21d']}"


# ---------------------------------------------------------------------------
# (16) basket_turn_cohort nightly_run — exit-0-always (empty ledger)
# ---------------------------------------------------------------------------

def test_basket_turn_cohort_exit_0_empty_ledger(monkeypatch, tmp_path):
    """basket_turn_cohort.nightly_run must not raise when ledger is empty."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    # No ledger written — path does not exist
    result = BTC.nightly_run(data_root=tmp_path)
    assert result["ok"] is True
    assert result["n_ledger_rows"] == 0
    assert result["n_cohorts"] == 0


# ---------------------------------------------------------------------------
# (17) tape_disagreement nightly_run — exit-0-always (empty turn-watch ledger)
# ---------------------------------------------------------------------------

def test_tape_disagreement_exit_0_empty_ledger(monkeypatch, tmp_path):
    """tape_disagreement.nightly_run must not raise when turn-watch ledger is empty."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    with patch("engine.tape_disagreement.config") as mock_cfg:
        mock_cfg.ROOT = tmp_path
        mock_cfg.data_dir.return_value = tmp_path
        mock_cfg.load.return_value = {"storage": {"site_dir": "site"}}

        result = TD.nightly_run(as_of=_TODAY, data_root=tmp_path, root=tmp_path)

    assert result["ok"] is True
    assert result["n_new_events"] == 0
