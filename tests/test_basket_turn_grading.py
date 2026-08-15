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
  (18) grade_cohorts — COLLECT_LANE gate (no writes when absent)
  (19) grade_cohorts — keep-first (already graded cohort not re-graded)
  (20) grade_cohorts — writes cohort_grades.jsonl when 21 sessions elapsed
  (21) detect_disagreement_events end-to-end against REAL committed artifacts
       (skipped cleanly when artifacts absent)
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


def _make_baskets_json(data_root: Path, themes: list[dict]) -> None:
    """Write a prod-shape site/basketdata/baskets.json under data_root.

    Mirrors the real artifact structure:
      data["theme_intel"]["themes"] → list of theme dicts with 'id' and 'reco'.
    """
    site_dir = data_root / "site" / "basketdata"
    site_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "as_of": _TODAY,
        "construction": "test",
        "history_note": "",
        "note": "",
        "categories": [],
        "story": {},
        "baskets": [],   # basket-level list (no reco here)
        "chart": {},
        "theme_intel": {
            "as_of": _TODAY,
            "themes": themes,  # reco lives here, keyed by 'id'
        },
    }
    (site_dir / "baskets.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _make_membership_json(data_root: Path, baskets: dict[str, dict]) -> None:
    """Write a prod-shape data/baskets/membership.json.

    Each basket value is a dict with 'members': [{'ticker': str, 'removed': None, ...}].
    """
    p = data_root / "baskets"
    p.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "1",
        "note": "test fixture",
        "seed_date": _TODAY,
        "curated": _TODAY,
        "baskets": baskets,
    }
    (p / "membership.json").write_text(json.dumps(payload), encoding="utf-8")


def _make_price_parquet(path: Path, start: str, n: int, daily_ret: float) -> None:
    """Write a minimal price parquet with 'close' column."""
    path.parent.mkdir(parents=True, exist_ok=True)
    idx = pd.bdate_range(start=start, periods=n)
    closes = [100.0]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1 + daily_ret))
    df = pd.DataFrame({"close": closes}, index=idx)
    df.to_parquet(path)


# ---------------------------------------------------------------------------
# Real prod-shape theme fixture (from site/basketdata/baskets.json)
# Copied from the real artifact: id, reco keys match.
# ---------------------------------------------------------------------------

_REAL_THEME_FIXTURE = {
    "id": "semicap_equipment",
    "name": "Semicap Equipment",
    "name_zh": "半导体设备",
    "category": "AI & Technology",
    "score": 55.0,
    "label": "hold",
    "label_en": "Hold",
    "label_zh": "持有",
    "reco": "hold",          # the real reco field (theme-level)
    "reco_en": "Hold",
    "reco_zh": "持有",
    "n_members": 5,
    # additional theme fields omitted — only id and reco are load-bearing
}

# Real membership fixture (from data/baskets/membership.json)
_REAL_MEMBERSHIP_FIXTURE = {
    "semicap_equipment": {
        "name": "Semicap Equipment",
        "name_zh": "半导体设备",
        "theme": "Semiconductor capital equipment",
        "category": "AI & Technology",
        "etf_proxy": "SOXX",
        "created": "2023-05-09",
        "curated": "2026-06-14",
        "omitted": [],
        "members": [
            {"ticker": "AMAT", "added": "2023-05-09", "removed": None,
             "rationale": "Applied Materials — dominant CVD/ALD/etch"},
            {"ticker": "LRCX", "added": "2023-05-09", "removed": None,
             "rationale": "Lam Research — etch/deposition"},
            {"ticker": "KLAC", "added": "2023-05-09", "removed": None,
             "rationale": "KLA — process control"},
            {"ticker": "ENTG", "added": "2023-05-09", "removed": None,
             "rationale": "Entegris — materials"},
            {"ticker": "MKSI", "added": "2023-05-09", "removed": None,
             "rationale": "MKS Instruments — power/gas delivery"},
        ],
        "weighting": "equal",
        "changelog": [],
        "parent": "Semiconductors",
        "tags": ["semicap", "equipment"],
    }
}


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
    only register the claim once.

    Uses the real qledger against root=tmp_path — the previous
    patch.dict(sys.modules) mock never took effect in a full-suite run
    (`from engine import qledger` resolves the parent-package ATTRIBUTE, not
    sys.modules), so the claim registered into the REAL data/qledger tree."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    cohorts = [{"cohort_id": _TODAY, "cohort_date": _TODAY,
                "basket_ids": ["ai_semiconductors"], "n_baskets": 1, "legs": {}}]

    # First run
    BTC.register_cohort_claims(cohorts, data_root=tmp_path, root=tmp_path)
    # Second run — cohort log should prevent re-registration
    result2 = BTC.register_cohort_claims(cohorts, data_root=tmp_path, root=tmp_path)

    assert result2 == [], "Second run should produce no new claims (keep-first)"


# ---------------------------------------------------------------------------
# (7) register_cohort_claims — new claims have status "open"
# ---------------------------------------------------------------------------

def test_register_cohort_claims_status_open(monkeypatch, tmp_path):
    """Newly registered claims should have status 'open'.

    Real qledger against root=tmp_path (see keep-first test above for why the
    sys.modules mock was dropped)."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    cohorts = [{"cohort_id": _TODAY, "cohort_date": _TODAY,
                "basket_ids": ["ai_semiconductors"], "n_baskets": 1, "legs": {}}]

    registered = BTC.register_cohort_claims(cohorts, data_root=tmp_path, root=tmp_path)

    assert len(registered) == 1
    assert registered[0]["status"] == "open"


# ---------------------------------------------------------------------------
# (8) detect_disagreement_events — fires on IGNITION + non-aligned reco
# Uses prod-shape baskets_map: {id: theme_dict} from theme_intel.themes
# ---------------------------------------------------------------------------

def test_detect_disagreement_fires_on_ignition_hold():
    """IGNITION + slow_reco='hold' → one disagreement event."""
    turn_watch_rows = [_make_ignition_row("semicap_equipment", _TODAY)]
    # Prod-shape: baskets_map keyed by id, reco at top level of theme dict
    baskets_map = {"semicap_equipment": dict(_REAL_THEME_FIXTURE)}

    events = TD.detect_disagreement_events(
        as_of=_TODAY,
        turn_watch_rows=turn_watch_rows,
        baskets_map=baskets_map,
        ship_date=_SHIP_DATE,
    )
    assert len(events) == 1
    ev = events[0]
    assert ev["basket_id"] == "semicap_equipment"
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
    theme = dict(_REAL_THEME_FIXTURE)
    theme["reco"] = "avoid"
    baskets_map = {"semicap_equipment": theme}

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
    turn_watch_rows = [_make_ignition_row("semicap_equipment", _TODAY)]
    theme = dict(_REAL_THEME_FIXTURE)
    theme["reco"] = "trim"
    baskets_map = {"semicap_equipment": theme}

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
    turn_watch_rows = [_make_ignition_row("semicap_equipment", _TODAY)]
    theme = dict(_REAL_THEME_FIXTURE)
    theme["reco"] = "enter"
    baskets_map = {"semicap_equipment": theme}

    events = TD.detect_disagreement_events(
        as_of=_TODAY,
        turn_watch_rows=turn_watch_rows,
        baskets_map=baskets_map,
        ship_date=_SHIP_DATE,
    )
    assert events == [], "IGNITION + 'enter' should not fire a disagreement"


def test_detect_disagreement_no_fire_on_accumulate():
    """IGNITION + slow_reco='accumulate' → NO disagreement event."""
    turn_watch_rows = [_make_ignition_row("semicap_equipment", _TODAY)]
    theme = dict(_REAL_THEME_FIXTURE)
    theme["reco"] = "accumulate"
    baskets_map = {"semicap_equipment": theme}

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
    turn_watch_rows = [_make_watch_row("semicap_equipment", _TODAY)]
    baskets_map = {"semicap_equipment": dict(_REAL_THEME_FIXTURE)}

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
    turn_watch_rows = [_make_ignition_row("semicap_equipment", _TODAY)]
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
    _make_turn_watch_ledger([_make_ignition_row("semicap_equipment", _TODAY)], tmp_path)

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

    _make_turn_watch_ledger([_make_ignition_row("semicap_equipment", _TODAY)], tmp_path)
    # Prod-shape baskets.json — reco in theme_intel.themes
    _make_baskets_json(tmp_path, [dict(_REAL_THEME_FIXTURE)])

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
    """Newly recorded events must have outcome_10d=None, outcome_21d=None (right-censored).

    KM convention: censored=True means event-not-yet-observed.
    """
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    _make_turn_watch_ledger([_make_ignition_row("semicap_equipment", _TODAY)], tmp_path)
    _make_baskets_json(tmp_path, [dict(_REAL_THEME_FIXTURE)])

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
    # KM: censored=True means event-not-yet-observed
    assert row["censored_10d"] is True
    assert row["censored_21d"] is True


# ---------------------------------------------------------------------------
# (15) update_outcomes — fills outcome when window elapsed + tape faded
# Uses prod-shape SPY at data/yahoo/SPY.parquet + members from membership.json
# ---------------------------------------------------------------------------

def test_update_outcomes_tape_faded(tmp_path):
    """update_outcomes fills 'tape_faded' when basket EW < SPY over the window.

    SPY is in data/yahoo/ (prod path); member prices in data/stocks/.
    Members come from membership.json (prod shape).
    """
    event_date = "2026-05-01"  # far enough in the past that 10d + 21d have elapsed
    as_of = "2026-07-09"

    # Write prod-shape membership.json with one active member
    _make_membership_json(tmp_path, {
        "semicap_equipment": {
            "name": "Semicap Equipment",
            "name_zh": "半导体设备",
            "theme": "test",
            "category": "AI & Technology",
            "etf_proxy": "SOXX",
            "created": "2023-05-09",
            "curated": "2026-06-14",
            "omitted": [],
            "members": [
                {"ticker": "AMAT", "added": "2023-05-09", "removed": None,
                 "rationale": "test member"},
            ],
            "weighting": "equal",
            "changelog": [],
            "parent": "Semiconductors",
            "tags": [],
        }
    })

    # Write stub price data: AMAT flat, SPY up
    # SPY at data/yahoo/SPY.parquet (prod path)
    _make_price_parquet(tmp_path / "yahoo" / "SPY.parquet", event_date, 30, 0.002)
    # AMAT flat in data/stocks/
    _make_price_parquet(tmp_path / "stocks" / "AMAT.parquet", event_date, 30, 0.0)

    # baskets_map is the theme-level map (reco only — members come from membership.json)
    baskets_map = {"semicap_equipment": {"id": "semicap_equipment", "reco": "hold"}}

    rows = [{
        "basket_id":    "semicap_equipment",
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
    # SPY went up, AMAT flat → basket EW < SPY → tape_faded
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


# ---------------------------------------------------------------------------
# (18) grade_cohorts — COLLECT_LANE gate (no writes when absent)
# ---------------------------------------------------------------------------

def test_grade_cohorts_gate_absent(monkeypatch, tmp_path):
    """grade_cohorts does not write when COLLECT_LANE is absent."""
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)

    cohorts = [{"cohort_id": "2026-05-01", "cohort_date": "2026-05-01",
                "basket_ids": ["semicap_equipment"], "n_baskets": 1}]
    result = BTC.grade_cohorts(cohorts, as_of=_TODAY, data_root=tmp_path)
    assert result == [], "No grades should be written when COLLECT_LANE is absent"
    grades_p = tmp_path / "basket_turn" / "cohort_grades.jsonl"
    assert not grades_p.exists()


# ---------------------------------------------------------------------------
# (19) grade_cohorts — keep-first (already graded cohort not re-graded)
# ---------------------------------------------------------------------------

def test_grade_cohorts_keep_first(monkeypatch, tmp_path):
    """A cohort already present in cohort_grades.jsonl is not re-graded."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    cohort_date = "2026-05-01"
    # Write membership and prices so the grade CAN be computed
    _make_membership_json(tmp_path, {
        "semicap_equipment": {
            "name": "test", "name_zh": "", "theme": "", "category": "",
            "etf_proxy": "", "created": cohort_date, "curated": cohort_date,
            "omitted": [], "weighting": "equal", "changelog": [], "parent": "", "tags": [],
            "members": [{"ticker": "AMAT", "added": cohort_date, "removed": None,
                         "rationale": ""}],
        }
    })
    _make_price_parquet(tmp_path / "yahoo" / "SPY.parquet", cohort_date, 30, 0.001)
    _make_price_parquet(tmp_path / "stocks" / "AMAT.parquet", cohort_date, 30, 0.002)

    cohorts = [{"cohort_id": cohort_date, "cohort_date": cohort_date,
                "basket_ids": ["semicap_equipment"], "n_baskets": 1}]

    # First run — should produce one grade
    grades1 = BTC.grade_cohorts(cohorts, as_of=_TODAY, data_root=tmp_path)
    # Second run — should produce zero (keep-first)
    grades2 = BTC.grade_cohorts(cohorts, as_of=_TODAY, data_root=tmp_path)

    assert len(grades1) == 1
    assert grades2 == [], "Second run should produce no new grades (keep-first)"

    # File should have exactly one row
    p = tmp_path / "basket_turn" / "cohort_grades.jsonl"
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# (20) grade_cohorts — writes cohort_grades.jsonl when 21 sessions elapsed
# ---------------------------------------------------------------------------

def test_grade_cohorts_writes_when_matured(monkeypatch, tmp_path):
    """grade_cohorts writes a grade row when >= 21 sessions have elapsed."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    cohort_date = "2026-05-01"
    _make_membership_json(tmp_path, {
        "semicap_equipment": {
            "name": "test", "name_zh": "", "theme": "", "category": "",
            "etf_proxy": "", "created": cohort_date, "curated": cohort_date,
            "omitted": [], "weighting": "equal", "changelog": [], "parent": "", "tags": [],
            "members": [{"ticker": "AMAT", "added": cohort_date, "removed": None,
                         "rationale": ""}],
        }
    })
    # SPY flat, AMAT up → cohort beats SPY
    _make_price_parquet(tmp_path / "yahoo" / "SPY.parquet", cohort_date, 30, 0.0)
    _make_price_parquet(tmp_path / "stocks" / "AMAT.parquet", cohort_date, 30, 0.003)

    cohorts = [{"cohort_id": cohort_date, "cohort_date": cohort_date,
                "basket_ids": ["semicap_equipment"], "n_baskets": 1}]
    grades = BTC.grade_cohorts(cohorts, as_of=_TODAY, data_root=tmp_path)

    assert len(grades) == 1
    g = grades[0]
    assert g["cohort_date"] == cohort_date
    assert g["outcome"] == "cohort_beat_spy"
    assert g["excess_vs_spy_21d"] > 0

    p = tmp_path / "basket_turn" / "cohort_grades.jsonl"
    assert p.exists()
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    assert len(rows) == 1
    assert rows[0]["cohort_date"] == cohort_date


# ---------------------------------------------------------------------------
# (21) end-to-end detect_disagreement_events against REAL committed artifacts
#      Skips cleanly when artifacts absent (e.g. in CI without repo data)
# ---------------------------------------------------------------------------

def test_detect_disagreement_end_to_end_real_artifacts():
    """Run detect_disagreement_events against the real committed artifacts.

    Loads slices of the real:
      - site/basketdata/baskets.json  (theme-level reco map)
      - data/basket_turn/ledger.jsonl (turn-watch events)
    and verifies the function runs without errors and returns a list.

    Skips cleanly if artifacts are absent.
    """
    repo_root = Path(__file__).resolve().parent.parent

    baskets_p = repo_root / "site" / "basketdata" / "baskets.json"
    ledger_p  = repo_root / "data" / "basket_turn" / "ledger.jsonl"

    if not baskets_p.exists() or not ledger_p.exists():
        pytest.skip(
            "Real committed artifacts not present — skipping end-to-end test "
            f"(missing: {'baskets.json' if not baskets_p.exists() else ''} "
            f"{'ledger.jsonl' if not ledger_p.exists() else ''}).strip()"
        )

    # Load real baskets_map (theme-level, reco from theme_intel.themes)
    raw = json.loads(baskets_p.read_text(encoding="utf-8"))
    themes = raw.get("theme_intel", {}).get("themes") or []
    baskets_map = {t["id"]: t for t in themes if t.get("id")}

    # Load real turn-watch ledger
    turn_watch_rows: list[dict] = []
    for line in ledger_p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                turn_watch_rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    # Run detect_disagreement_events for the most recent IGNITION date in ledger
    ignition_dates = sorted(set(
        r.get("date") or r.get("as_of", "")
        for r in turn_watch_rows
        if r.get("state") == "IGNITION"
    ))
    if not ignition_dates:
        pytest.skip("No IGNITION rows in committed ledger — skipping end-to-end test")

    as_of = ignition_dates[-1]
    events = TD.detect_disagreement_events(
        as_of=as_of,
        turn_watch_rows=turn_watch_rows,
        baskets_map=baskets_map,
        ship_date=BTC.SHIP_DATE,
    )

    # Verify the function returns a list (may be empty — that is valid)
    assert isinstance(events, list), "detect_disagreement_events must return a list"

    # Verify that for any fired event, slow_reco came from the real theme map
    for ev in events:
        bid = ev["basket_id"]
        expected_reco = baskets_map.get(bid, {}).get("reco")
        assert ev["slow_reco"] == expected_reco, (
            f"Event reco mismatch for {bid}: "
            f"got {ev['slow_reco']!r}, expected {expected_reco!r}"
        )
        # Real reco should NOT be an aligned state (the event should not have fired)
        assert ev["slow_reco"] not in TD.SLOW_RECO_ALIGNED, (
            f"Event fired for aligned reco {ev['slow_reco']!r} — logic bug"
        )

    # Verify semicap_equipment reco from the real artifact
    semicap_reco = baskets_map.get("semicap_equipment", {}).get("reco")
    # Print the real value for the brief's verification requirement
    print(f"\n[end-to-end] semicap_equipment real reco from committed artifact: {semicap_reco!r}")
    print(f"[end-to-end] as_of={as_of}, {len(turn_watch_rows)} ledger rows, "
          f"{len(events)} disagreement event(s)")


# ---------------------------------------------------------------------------
# (22) register_cohort_claims — claims land at <repo>/data/qledger/claims.jsonl
#      NOT at data_root/data/qledger/claims.jsonl (double-data/ bug, item 1 fix)
# ---------------------------------------------------------------------------

def test_register_cohort_claims_lands_at_repo_root(monkeypatch, tmp_path):
    """Claims must be written to <repo_root>/data/qledger/claims.jsonl.

    qledger.register_batch takes `root` as the REPO root and prepends data/
    internally (_CLAIMS_FILE = ("data", "qledger", "claims.jsonl")).

    Before the fix, register_cohort_claims passed `root=data_root`, causing
    claims to land at data_root/data/qledger/claims.jsonl (double data/).
    After the fix, root is threaded separately from data_root and passed to
    register_batch, so claims land at repo_root/data/qledger/claims.jsonl.
    """
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    # Two separate directories: repo root and data root (mimicking prod layout
    # where repo_root/data/ is the data directory, but here we keep them distinct
    # to catch the double-path bug).
    repo_root = tmp_path / "repo"
    data_root = tmp_path / "data_area"
    repo_root.mkdir()
    data_root.mkdir()

    cohorts = [{"cohort_id": _TODAY, "cohort_date": _TODAY,
                "basket_ids": ["ai_semiconductors"], "n_baskets": 1, "legs": {}}]

    # Use the REAL qledger (not mocked) so register_batch actually writes.
    import engine.qledger as q_real

    BTC.register_cohort_claims(cohorts, data_root=data_root, root=repo_root)

    canonical = repo_root / "data" / "qledger" / "claims.jsonl"
    double_data = data_root / "data" / "qledger" / "claims.jsonl"

    assert canonical.exists(), (
        f"Claims must land at <repo_root>/data/qledger/claims.jsonl but file "
        f"does not exist at {canonical}"
    )
    assert not double_data.exists(), (
        f"Claims must NOT land at data_root/data/qledger/claims.jsonl — "
        f"this indicates the double-data/ bug is still present: {double_data}"
    )


# ---------------------------------------------------------------------------
# (22) data-plane defaults — detection and maturity never key off the calendar
#      (forward-ledger audit 2026-08-05, #4568 pattern)
#
# All fixture dates below are pinned weekdays and every assertion is
# wall-clock-free: the contract is "the tape decides", so the expected values
# are store-derived constants, not today's date.
# ---------------------------------------------------------------------------

_EVENT_DATE   = "2026-07-16"   # Thursday — the turn-watch ledger's newest stamp
_EARLIER_DATE = "2026-07-15"   # Wednesday — an older stamp that must NOT win
# data/yahoo/SPY.parquet fixture: 21 business days from _EVENT_DATE
_SPY_LAST_BAR = "2026-08-13"   # Thursday — pd.bdate_range(_EVENT_DATE, 21)[-1]


def test_tape_disagreement_defaults_to_the_data_plane(monkeypatch, tmp_path):
    """as_of=None: detection keys off the ledger's MAX stamp, maturity off SPY.

    Under the pre-fix default both came from date.today(): detection looked for
    rows stamped with a calendar date the ledger may never carry (silently
    detecting nothing), and the maturity clock ran ahead of the tape.
    """
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    # Two IGNITION sessions in the ledger — only the newest is tonight's
    _make_turn_watch_ledger(
        [
            _make_ignition_row("memory_storage", _EARLIER_DATE),
            _make_ignition_row("semicap_equipment", _EVENT_DATE),
        ],
        tmp_path,
    )
    _make_baskets_json(tmp_path, [_REAL_THEME_FIXTURE])          # reco = "hold"
    _make_membership_json(tmp_path, _REAL_MEMBERSHIP_FIXTURE)
    _make_price_parquet(tmp_path / "yahoo" / "SPY.parquet", _EVENT_DATE, 21, 0.0)

    captured: dict[str, Any] = {}

    def _spy_update(rows, baskets_map, as_of, data_root=None):
        captured["as_of"] = as_of
        return [dict(r) for r in rows]

    with patch.object(TD, "update_outcomes", _spy_update):
        result = TD.nightly_run(as_of=None, data_root=tmp_path, root=tmp_path)

    assert result["ok"] is True
    assert result["n_new_events"] == 1, "only the ledger's newest session detects"

    rows = TD.load_ledger(tmp_path)
    assert len(rows) == 1
    assert rows[0]["event_date"] == _EVENT_DATE
    assert rows[0]["basket_id"] == "semicap_equipment"

    # Maturity clock = the SPY store's newest bar, not the calendar
    assert captured["as_of"] == _SPY_LAST_BAR


def test_tape_disagreement_empty_ledger_skips_detection(monkeypatch, tmp_path):
    """An empty turn-watch ledger has no session to detect for — no crash."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    _make_turn_watch_ledger([], tmp_path)
    _make_baskets_json(tmp_path, [_REAL_THEME_FIXTURE])

    result = TD.nightly_run(as_of=None, data_root=tmp_path, root=tmp_path)

    assert result["ok"] is True
    assert result["n_new_events"] == 0


# data/yahoo/SPY.parquet fixture: 22 business days from the cohort date, so
# exactly 21 sessions elapse strictly after it (the grading horizon).
_COHORT_DATE  = "2026-06-01"   # Monday
_COHORT_LAST_BAR = "2026-06-30"  # Tuesday — pd.bdate_range(_COHORT_DATE, 22)[-1]


def test_grade_cohorts_defaults_to_the_spy_tape_bound(monkeypatch, tmp_path):
    """as_of=None: the maturity clock and graded_as_of come from the SPY store.

    Under the pre-fix default graded_as_of recorded the calendar day of the run
    — a date the grader never priced anything at.
    """
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    _make_membership_json(tmp_path, {
        "semicap_equipment": {
            "name": "test", "name_zh": "", "theme": "", "category": "",
            "etf_proxy": "", "created": _COHORT_DATE, "curated": _COHORT_DATE,
            "omitted": [], "weighting": "equal", "changelog": [], "parent": "", "tags": [],
            "members": [{"ticker": "AMAT", "added": _COHORT_DATE, "removed": None,
                         "rationale": ""}],
        }
    })
    _make_price_parquet(tmp_path / "yahoo" / "SPY.parquet", _COHORT_DATE, 22, 0.0)
    _make_price_parquet(tmp_path / "stocks" / "AMAT.parquet", _COHORT_DATE, 22, 0.003)

    cohorts = [{"cohort_id": _COHORT_DATE, "cohort_date": _COHORT_DATE,
                "basket_ids": ["semicap_equipment"], "n_baskets": 1}]

    # as_of deliberately omitted — the default is what is under test
    grades = BTC.grade_cohorts(cohorts, data_root=tmp_path)

    assert len(grades) == 1
    assert grades[0]["graded_as_of"] == _COHORT_LAST_BAR
    assert grades[0]["sessions_elapsed"] == BTC.GRADE_HORIZON_SESSIONS


# ---------------------------------------------------------------------------
# (23) register_cohort_claims — the cohort claims log records the ACTUAL
#      per-claim registration outcome, never an assumed success
#
#      Defect (W3 review, PR #5679, reviewer R3): the log wrote
#      {"cohort_id": cid, "registered": True} for EVERY attempted cohort
#      without reading register_batch's per-claim status — 4 cohorts were
#      logged registered while only 2 claims reached data/qledger/claims.jsonl.
#      register_batch returns one slot per input claim in input order, and a
#      slot is either a stored row (status open / rejected) or
#      {"status": "error", ...} whose claim was never persisted at all.
# ---------------------------------------------------------------------------

def _read_cohort_log(data_root: Path) -> list[dict]:
    p = data_root / "basket_turn" / "cohort_claims_log.jsonl"
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _cohort_log_last(data_root: Path) -> dict[str, dict]:
    """cohort_id → its LAST log row (a retried cohort has more than one)."""
    return {row["cohort_id"]: row for row in _read_cohort_log(data_root)}


def _read_claims(repo_root: Path) -> list[dict]:
    p = repo_root / "data" / "qledger" / "claims.jsonl"
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _scope_key(claim: dict) -> str:
    return str((claim.get("scope") or {}).get("key") or "")


def _cohort(cid: str) -> dict:
    return {"cohort_id": cid, "cohort_date": cid,
            "basket_ids": ["ai_semiconductors"], "n_baskets": 1, "legs": {}}


def test_register_cohort_claims_partially_rejected_batch(monkeypatch, tmp_path):
    """A batch where one claim is REJECTED must log rejected, not registered.

    Only the validation verdict is steered — _prepare_claim, register_batch,
    the dedupe pass and the claims.jsonl append are all the real machinery, so
    the rejected row persists for audit exactly as it does in production.

    Under the pre-fix code all three rows read registered:true.
    """
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    repo_root = tmp_path / "repo"
    data_root = tmp_path / "data_area"
    repo_root.mkdir()
    data_root.mkdir()

    import engine.qledger as q_real

    bad = "2026-07-11"
    real_validate = q_real._validate_claim

    def _validate(claim):
        if _scope_key(claim) == bad:
            return False, "planted: schema-invalid cohort claim"
        return real_validate(claim)

    monkeypatch.setattr(q_real, "_validate_claim", _validate)

    cohorts = [_cohort("2026-07-10"), _cohort(bad), _cohort("2026-07-12")]
    results = BTC.register_cohort_claims(cohorts, data_root=data_root, root=repo_root)

    assert [r.get("status") for r in results] == ["open", "rejected", "open"], (
        "fixture did not produce a partially-rejected batch"
    )

    rows = _cohort_log_last(data_root)
    assert rows[bad].get("registered") is False, (
        "REGRESSION: a rejected claim was logged as registered — the log is "
        "asserting a registration register_batch never reported"
    )
    assert rows[bad]["outcome"] == "rejected"
    assert rows[bad].get("reason"), "a non-registered outcome must carry its reason"
    for good in ("2026-07-10", "2026-07-12"):
        assert rows[good]["outcome"] == "registered"
        assert rows[good]["registered"] is True
        assert rows[good]["claim_id"]

    # The log's registered count must equal the gradeable claims actually on disk.
    claims = _read_claims(repo_root)
    n_open = sum(1 for c in claims if c.get("status") == "open")
    n_logged = sum(1 for r in rows.values() if r["registered"])
    assert n_logged == n_open == 2, (
        f"log claims {n_logged} registrations, claims.jsonl holds {n_open} open rows"
    )

    # A rejected row IS persisted (audit), so keep-first latches it: re-running
    # must not re-attempt it (it would only dedupe against itself).
    assert BTC.register_cohort_claims(cohorts, data_root=data_root, root=repo_root) == []


def test_register_cohort_claims_failed_claim_is_never_logged_registered(monkeypatch, tmp_path):
    """A claim whose preparation RAISES persists nothing — log it as failed.

    This is the half of the defect that loses a forward bet outright: the error
    slot carries no claim_id and no row reaches claims.jsonl, yet the pre-fix
    log recorded registered:true and keep-first latched the cohort forever.
    """
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    repo_root = tmp_path / "repo"
    data_root = tmp_path / "data_area"
    repo_root.mkdir()
    data_root.mkdir()

    import engine.qledger as q_real

    doomed = "2026-07-11"
    real_prepare = q_real._prepare_claim

    def _prepare(claim):
        if _scope_key(claim) == doomed:
            raise RuntimeError("planted: claim preparation failed")
        return real_prepare(claim)

    monkeypatch.setattr(q_real, "_prepare_claim", _prepare)

    cohorts = [_cohort("2026-07-10"), _cohort(doomed), _cohort("2026-07-12")]
    results = BTC.register_cohort_claims(cohorts, data_root=data_root, root=repo_root)

    assert results[1].get("status") == "error", "fixture did not produce an error slot"

    rows = _cohort_log_last(data_root)
    assert rows[doomed].get("registered") is False, (
        "REGRESSION: a claim that never reached the store was logged as registered"
    )
    assert rows[doomed]["outcome"] == "failed"
    assert "claim_id" not in rows[doomed], "a failed claim has no claim_id to record"

    claims = _read_claims(repo_root)
    assert [_scope_key(c) for c in claims] == ["2026-07-10", "2026-07-12"]
    assert doomed not in {_scope_key(c) for c in claims}

    # keep-first must NOT latch a cohort whose claim persisted nothing: the next
    # nightly retries it, and only then does it read registered.
    monkeypatch.setattr(q_real, "_prepare_claim", real_prepare)
    retry = BTC.register_cohort_claims(cohorts, data_root=data_root, root=repo_root)
    assert [_scope_key(r) for r in retry] == [doomed], (
        "a failed cohort must stay eligible — it was silently latched instead"
    )
    assert retry[0]["status"] == "open"
    rows = _cohort_log_last(data_root)
    assert rows[doomed]["outcome"] == "registered"
    assert rows[doomed]["registered"] is True

    # ...and the retry must not duplicate the two that already landed.
    assert sum(1 for c in _read_claims(repo_root) if _scope_key(c) == "2026-07-10") == 1


def test_cohort_log_legacy_rows_still_latch(tmp_path):
    """Rows written before the outcome field existed carry no 'outcome' key and
    must keep latching keep-first exactly as they did when written."""
    log_dir = tmp_path / "basket_turn"
    log_dir.mkdir(parents=True)
    (log_dir / "cohort_claims_log.jsonl").write_text(
        json.dumps({"cohort_id": "2026-07-10", "registered": True}) + "\n"
        + json.dumps({"cohort_id": "2026-07-11", "registered": False, "outcome": "failed"}) + "\n"
        + json.dumps({"cohort_id": "2026-07-12", "registered": False, "outcome": "rejected"}) + "\n",
        encoding="utf-8",
    )

    seen = BTC._load_cohort_log(tmp_path)

    assert "2026-07-10" in seen, "legacy row (no outcome key) must latch"
    assert "2026-07-12" in seen, "a rejected row is persisted — it latches"
    assert "2026-07-11" not in seen, "a failed row persisted nothing — it must retry"
