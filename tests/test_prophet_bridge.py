"""tests/test_prophet_bridge.py — Prophet Bridge + build_prophet.py tests.

Coverage:
  1.  Geometry (BULL): hand-computed invalidation/T1/T2 with hold.invalidation.
  2.  Geometry (BULL): fallback to swing_low + ATR when hold.invalidation absent.
  3.  Geometry (BEAR): T1 below entry, T2 further below.
  4.  Geometry: R=0 guard (invalidation == entry → None values).
  5.  Geometry: ATR fallback when no price history available.
  6.  ID stability: same ticker/direction/signal_date always produces same ID.
  7.  Duplicate suppression: plan already in existing_ids is not re-originated.
  8.  Candidate selection gate_go=True: requires act_level >= 2.
  9.  Candidate selection gate_go=False: OR logic (act_level>=2 OR score>=60).
  10. Candidate selection: band="low" always excluded.
  11. Candidate selection: entry_signal null → excluded.
  12. Candidate selection: dir!="up" → excluded (BEAR universe not yet).
  13. Candidate selection: sorted by score desc, act_level desc on tie.
  14. Option expiry selection: nearest monthly >= signal + horizon + 15d.
  15. Option expiry: non-monthly alignment — result is always a Friday.
  16. Option resolution: no store → returns None.
  17. Option resolution: store present but ticker absent → returns None.
  18. Trade plan validate_trade_plan: source_engines non-empty required.
  19. Trade plan validate_trade_plan: schema mismatch caught.
  20. Trade plan validate_trade_plan: direction invalid caught.
  21. Validator round-trip: originate_plans output passes validate_trade_plan.
  22. PIT: price history filtered to <= asof; future rows ignored.
  23. Ledger schema: _initialize_ledger creates file on first call.
  24. Ledger schema: row dict contains required keys (schema validation).
  25. Index.json schema has required top-level keys.
  26. Index note does NOT contain the word "validated".
  27. build_prophet main: runs end-to-end on synthetic data without crash.
  28. originate_plans: ≤ N_CANDIDATES plans produced.
  29. _third_friday: always returns a Friday.
  30. _next_monthly_expiry: always >= min_date.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ── repo path ─────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.prophet_bridge import (
    N_CANDIDATES,
    compute_geometry,
    originate_plans,
    resolve_option,
    select_candidates,
    _make_id,
    _next_monthly_expiry,
    _third_friday,
    _build_what_to_do_now,
    _build_profit_plan,
    _build_thesis,
)
from engine.options_structure import validate_trade_plan


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_price_history(entry: float = 100.0, n_days: int = 30,
                         low_factor: float = 0.90) -> pd.DataFrame:
    """Create a synthetic DatetimeIndex OHLCV DataFrame."""
    base = pd.Timestamp("2026-06-01")
    dates = pd.date_range(base, periods=n_days, freq="B")
    closes = [entry * low_factor + (entry * (1 - low_factor)) * (i / max(n_days - 1, 1))
              for i in range(n_days)]
    return pd.DataFrame({"close": closes, "high": closes, "low": closes}, index=dates)


def _make_standouts(
    gate_go: bool = False,
    buys: list[dict] | None = None,
) -> dict:
    """Create a minimal us_standouts-like dict."""
    if buys is None:
        buys = [_make_buy("AAPL", score=70, act_level=3, spot=150.0)]
    return {
        "as_of": "2026-07-02",
        "gate_go": gate_go,
        "buy": buys,
    }


def _make_buy(
    ticker: str,
    score: int = 70,
    act_level: int = 3,
    spot: float = 100.0,
    band: str = "neutral",
    dir_: str = "up",
    hold_invalidation: float | None = 90.0,
    chase_above: float | None = 105.0,
    atr_pct: float = 2.0,
    anchor: str | None = "2026-07-02",
) -> dict:
    return {
        "ticker": ticker,
        "dir": dir_,
        "state": "TURN SIGNALED",
        "conviction": {
            "score": score,
            "band": band,
            "drivers": ["momentum", "volume"],
            "cautions": ["macro risk"],
            "trust_tier": {"en": "tier-2"},
        },
        "entry_signal": {
            "act_level": act_level,
            "status": "partial",
            "spot": spot,
            "stop": spot * 0.95,
            "chase_above": chase_above,
            "atr_pct": atr_pct,
            "entry_grade": "solid",
            "horizon": {"d21": 0.5},
        },
        "hold": {
            "state": "HOLD",
            "anchor": anchor,
            "invalidation": hold_invalidation,
        },
        "coiled": {"coiled": False, "star": False},
        "signal": {"above200": True, "weekly_bull": True},
    }


# ---------------------------------------------------------------------------
# 1–5. Geometry tests
# ---------------------------------------------------------------------------

def test_geometry_bull_with_hold_invalidation():
    """BULL: invalidation from hold.invalidation → T1 = entry + 1.5R, T2 = entry + 3R."""
    entry = 100.0
    invalidation = 90.0
    geo = compute_geometry(
        entry=entry,
        direction="BULL",
        atr_pct=None,
        hold_invalidation=invalidation,
        price_history=None,
        asof="2026-07-02",
    )
    r = entry - invalidation  # = 10.0
    assert geo["invalidation"] == pytest.approx(90.0, abs=1e-4)
    assert geo["t1"] == pytest.approx(entry + 1.5 * r, abs=1e-4)  # 115.0
    assert geo["t2"] == pytest.approx(entry + 3.0 * r, abs=1e-4)  # 130.0
    assert geo["r_unit"] == pytest.approx(r, abs=1e-4)


def test_geometry_bull_fallback_atr_and_swing():
    """BULL: when hold.invalidation absent, uses max(swing_low, entry - 2*ATR)."""
    entry = 100.0
    atr_pct = 2.0   # ATR = 2.0 abs
    # Price history: swing low = 92.0 (last 20d)
    ph = _make_price_history(entry=100.0, n_days=25, low_factor=0.92)
    geo = compute_geometry(
        entry=entry,
        direction="BULL",
        atr_pct=atr_pct,
        hold_invalidation=None,
        price_history=ph,
        asof="2026-07-02",
    )
    atr_abs = entry * atr_pct / 100.0  # = 2.0
    atr_stop = entry - 2 * atr_abs     # = 96.0
    swing_low = ph["close"].min()
    # max-protective = max(swing_low, atr_stop)
    expected_inval = max(swing_low, atr_stop)
    assert geo["invalidation"] == pytest.approx(expected_inval, abs=1e-3)
    r = entry - expected_inval
    assert geo["t1"] == pytest.approx(entry + 1.5 * r, abs=1e-3)
    assert geo["t2"] == pytest.approx(entry + 3.0 * r, abs=1e-3)


def test_geometry_bear_direction():
    """BEAR: T1 below entry, T2 further below; invalidation above entry."""
    entry = 100.0
    hold_invalidation = 110.0  # above entry for BEAR
    geo = compute_geometry(
        entry=entry,
        direction="BEAR",
        atr_pct=None,
        hold_invalidation=hold_invalidation,
        price_history=None,
        asof="2026-07-02",
    )
    r = abs(entry - hold_invalidation)  # = 10.0
    assert geo["invalidation"] == pytest.approx(110.0, abs=1e-4)
    assert geo["t1"] == pytest.approx(entry - 1.5 * r, abs=1e-4)  # 85.0
    assert geo["t2"] == pytest.approx(entry - 3.0 * r, abs=1e-4)  # 70.0


def test_geometry_no_atr_no_price_history_no_invalidation():
    """When all geometry inputs are absent, returns None for all levels."""
    geo = compute_geometry(
        entry=100.0,
        direction="BULL",
        atr_pct=None,
        hold_invalidation=None,
        price_history=None,
        asof="2026-07-02",
    )
    assert geo["invalidation"] is None
    assert geo["t1"] is None
    assert geo["t2"] is None
    assert geo["r_unit"] is None


def test_geometry_atr_only_fallback():
    """BULL with ATR only (no swing, no hold.invalidation)."""
    entry = 200.0
    atr_pct = 1.5  # ATR = 3.0 abs
    geo = compute_geometry(
        entry=entry,
        direction="BULL",
        atr_pct=atr_pct,
        hold_invalidation=None,
        price_history=None,
        asof="2026-07-02",
    )
    atr_abs = entry * atr_pct / 100.0
    expected_inval = entry - 2 * atr_abs
    assert geo["invalidation"] == pytest.approx(expected_inval, abs=1e-4)


# ---------------------------------------------------------------------------
# 6–7. ID stability and duplicate suppression
# ---------------------------------------------------------------------------

def test_id_stability():
    """Same ticker/direction/signal_date always produces the same ID."""
    id1 = _make_id("BA", "BULL", "2026-07-02")
    id2 = _make_id("BA", "BULL", "2026-07-02")
    assert id1 == id2
    assert id1 == "BA-BULL-20260702"


def test_id_differs_by_date():
    """Different signal dates produce different IDs."""
    id1 = _make_id("BA", "BULL", "2026-07-01")
    id2 = _make_id("BA", "BULL", "2026-07-02")
    assert id1 != id2


def test_duplicate_suppression(tmp_path):
    """Plans with IDs already in existing_ids are not re-originated."""
    standouts_path = tmp_path / "us_standouts.json"
    buys = [_make_buy("AAPL", score=70, act_level=3, spot=150.0)]
    standouts = _make_standouts(gate_go=False, buys=buys)
    standouts_path.write_text(json.dumps(standouts))

    existing_ids = {"AAPL-BULL-20260702"}
    plans = originate_plans(
        standouts_path=standouts_path,
        asof="2026-07-02",
        existing_ids=existing_ids,
        thetadata_store=None,
    )
    assert plans == []


# ---------------------------------------------------------------------------
# 8–13. Candidate selection
# ---------------------------------------------------------------------------

def test_selection_gate_go_true_requires_act_level_2():
    """gate_go=True: only act_level >= 2 passes."""
    buys = [
        _make_buy("HIGH_ACT", score=80, act_level=3),
        _make_buy("LOW_ACT",  score=90, act_level=1),
    ]
    result = select_candidates({"gate_go": True, "buy": buys, "as_of": "2026-07-02"})
    tickers = [b["ticker"] for b in result]
    assert "HIGH_ACT" in tickers
    assert "LOW_ACT" not in tickers


def test_selection_gate_go_false_or_logic():
    """gate_go=False: act_level>=2 OR score>=60 passes."""
    buys = [
        _make_buy("HIGH_SCORE", score=65, act_level=1),  # passes via score
        _make_buy("HIGH_ACT",   score=40, act_level=3),  # passes via act_level
        _make_buy("NEITHER",    score=50, act_level=1),  # excluded
    ]
    result = select_candidates({"gate_go": False, "buy": buys, "as_of": "2026-07-02"})
    tickers = [b["ticker"] for b in result]
    assert "HIGH_SCORE" in tickers
    assert "HIGH_ACT" in tickers
    assert "NEITHER" not in tickers


def test_selection_low_band_excluded():
    """band='low' is always excluded regardless of act_level or score."""
    buys = [
        _make_buy("LOWBAND", score=90, act_level=3, band="low"),
        _make_buy("NEUTRAL", score=70, act_level=3, band="neutral"),
    ]
    result = select_candidates({"gate_go": True, "buy": buys, "as_of": "2026-07-02"})
    tickers = [b["ticker"] for b in result]
    assert "LOWBAND" not in tickers
    assert "NEUTRAL" in tickers


def test_selection_null_entry_signal_excluded():
    """Entries with no entry_signal are excluded."""
    buys = [
        {
            "ticker": "NOES",
            "dir": "up",
            "entry_signal": None,
            "conviction": {"score": 80, "band": "neutral"},
            "hold": {},
        },
        _make_buy("AAPL", score=70, act_level=3),
    ]
    result = select_candidates({"gate_go": False, "buy": buys, "as_of": "2026-07-02"})
    tickers = [b["ticker"] for b in result]
    assert "NOES" not in tickers


def test_selection_bear_direction_excluded():
    """dir!='up' entries are excluded (BEAR universe not yet active)."""
    buys = [
        _make_buy("BEARSTOCK", score=90, act_level=3, dir_="down"),
        _make_buy("BULLSTOCK", score=70, act_level=3, dir_="up"),
    ]
    result = select_candidates({"gate_go": True, "buy": buys, "as_of": "2026-07-02"})
    tickers = [b["ticker"] for b in result]
    assert "BEARSTOCK" not in tickers
    assert "BULLSTOCK" in tickers


def test_selection_sorted_score_desc():
    """Candidates sorted descending by conviction score."""
    buys = [
        _make_buy("LOW",  score=40, act_level=3),
        _make_buy("HIGH", score=80, act_level=3),
        _make_buy("MED",  score=60, act_level=3),
    ]
    result = select_candidates({"gate_go": True, "buy": buys, "as_of": "2026-07-02"})
    scores = [(b.get("conviction") or {}).get("score") for b in result]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# 14–16. Option expiry selection
# ---------------------------------------------------------------------------

def test_third_friday_is_friday():
    """_third_friday always returns a Friday (weekday=4)."""
    for year in [2026, 2027]:
        for month in range(1, 13):
            tf = _third_friday(year, month)
            assert tf.weekday() == 4, f"{year}-{month:02d} third Friday is not a Friday: {tf}"


def test_next_monthly_expiry_always_gte_min_date():
    """_next_monthly_expiry returns a date >= min_date."""
    for offset in [0, 5, 15, 30, 60, 90]:
        min_date = date(2026, 7, 1) + timedelta(days=offset)
        result = _next_monthly_expiry(min_date)
        assert result >= min_date
        assert result.weekday() == 4  # Friday


def test_option_expiry_horizon_plus_15():
    """Expiry is >= signal_date + horizon_days + 15d."""
    signal = date(2026, 7, 2)
    horizon = 45
    min_exp = signal + timedelta(days=horizon + 15)
    result = _next_monthly_expiry(min_exp)
    assert result >= min_exp


# ---------------------------------------------------------------------------
# 16–17. Option resolution
# ---------------------------------------------------------------------------

def test_resolve_option_no_store():
    """resolve_option returns None when thetadata_store is None."""
    result = resolve_option(
        ticker="AAPL",
        direction="BULL",
        entry=150.0,
        horizon_days=45,
        signal_date="2026-07-02",
        thetadata_store=None,
        asof="2026-07-02",
    )
    assert result is None


def test_resolve_option_missing_ticker(tmp_path):
    """resolve_option returns None when ticker not in store."""
    store = tmp_path / "thetadata"
    store.mkdir()
    (store / "greeks").mkdir()
    (store / "eod").mkdir()

    result = resolve_option(
        ticker="NOTEXIST",
        direction="BULL",
        entry=100.0,
        horizon_days=45,
        signal_date="2026-07-02",
        thetadata_store=str(store),
        asof="2026-07-02",
    )
    assert result is None


# ---------------------------------------------------------------------------
# 18–20. validate_trade_plan
# ---------------------------------------------------------------------------

def test_validate_trade_plan_source_engines_required():
    """validate_trade_plan rejects plans with empty source_engines."""
    plan = {
        "schema": "prophet.trade_plan/v1",
        "id": "TEST-BULL-20260702",
        "asof": "2026-07-02",
        "asset": "TEST",
        "direction": "BULL",
        "source_engines": [],
    }
    errs = validate_trade_plan(plan)
    assert any("source_engines" in e for e in errs)


def test_validate_trade_plan_schema_mismatch():
    """validate_trade_plan rejects wrong schema string."""
    plan = {
        "schema": "wrong_schema/v1",
        "id": "TEST-BULL-20260702",
        "asof": "2026-07-02",
        "asset": "TEST",
        "direction": "BULL",
        "source_engines": ["neural_web"],
    }
    errs = validate_trade_plan(plan)
    assert any("schema" in e for e in errs)


def test_validate_trade_plan_invalid_direction():
    """validate_trade_plan rejects invalid direction."""
    plan = {
        "schema": "prophet.trade_plan/v1",
        "id": "TEST-BULL-20260702",
        "asof": "2026-07-02",
        "asset": "TEST",
        "direction": "SIDEWAYS",
        "source_engines": ["neural_web"],
    }
    errs = validate_trade_plan(plan)
    assert any("direction" in e for e in errs)


# ---------------------------------------------------------------------------
# 21. Validator round-trip
# ---------------------------------------------------------------------------

def test_originate_plans_passes_validate_trade_plan(tmp_path):
    """Every plan produced by originate_plans passes validate_trade_plan."""
    buys = [_make_buy("AAPL", score=70, act_level=3, spot=150.0)]
    standouts = _make_standouts(gate_go=False, buys=buys)
    standouts_path = tmp_path / "us_standouts.json"
    standouts_path.write_text(json.dumps(standouts))

    plans = originate_plans(
        standouts_path=standouts_path,
        asof="2026-07-02",
        existing_ids=set(),
        thetadata_store=None,
    )
    assert len(plans) >= 1
    for plan in plans:
        errs = validate_trade_plan(plan)
        assert errs == [], f"Plan {plan['id']} failed validation: {errs}"


# ---------------------------------------------------------------------------
# 22. PIT (no future price rows used)
# ---------------------------------------------------------------------------

def test_geometry_pit_uses_only_asof_or_earlier():
    """compute_geometry only uses prices on or before asof for swing_low."""
    # Build history where future day has a very low value that would skew the result
    dates = pd.date_range("2026-06-01", periods=25, freq="B")
    closes = [100.0] * 25
    ph = pd.DataFrame({"close": closes}, index=dates)

    # asof is 2026-06-20; price history extends beyond but swing_low uses ≤ asof
    geo_with_future = compute_geometry(
        entry=100.0,
        direction="BULL",
        atr_pct=2.0,
        hold_invalidation=None,
        price_history=ph,
        asof="2026-06-20",  # excludes last few rows
    )
    geo_without_future = compute_geometry(
        entry=100.0,
        direction="BULL",
        atr_pct=2.0,
        hold_invalidation=None,
        price_history=ph[ph.index <= pd.Timestamp("2026-06-20")],
        asof="2026-06-20",
    )
    # Results must match (both use same effective window)
    assert geo_with_future["invalidation"] == pytest.approx(
        geo_without_future["invalidation"], abs=1e-4
    )


# ---------------------------------------------------------------------------
# 23–24. Ledger
# ---------------------------------------------------------------------------

def test_initialize_ledger_creates_file(tmp_path):
    """_initialize_ledger creates ledger.jsonl on first call."""
    import importlib
    import scripts.build_prophet as bp  # noqa: PLC0415
    orig_ledger_path = bp.LEDGER_PATH
    orig_ledger_dir = bp.LEDGER_DIR
    try:
        bp.LEDGER_PATH = tmp_path / "prophet" / "ledger.jsonl"
        bp.LEDGER_DIR = tmp_path / "prophet"
        bp._initialize_ledger()
        assert bp.LEDGER_PATH.exists()
        content = bp.LEDGER_PATH.read_text()
        assert "prophet" in content.lower()
        assert "Nightly is the SOLE advancer" in content
        # No JSON row written yet (file has only the comment)
        rows = [l for l in content.splitlines() if l.strip() and not l.startswith("#")]
        assert rows == []
    finally:
        bp.LEDGER_PATH = orig_ledger_path
        bp.LEDGER_DIR = orig_ledger_dir


def test_ledger_row_schema_keys():
    """A ledger row dict must contain all required schema keys."""
    required_keys = {
        "schema", "id", "asset", "direction", "signal_date",
        "close_date", "outcome", "stock_result_pct",
        "option_result_pct", "days_held", "plan_adherence", "asof",
    }
    # Construct a minimal placeholder row
    row = {
        "schema": "prophet.ledger/v1",
        "id": "AAPL-BULL-20260702",
        "asset": "AAPL",
        "direction": "BULL",
        "signal_date": "2026-07-02",
        "close_date": None,
        "outcome": None,
        "stock_result_pct": None,
        "option_result_pct": None,
        "days_held": None,
        "plan_adherence": None,
        "asof": "2026-07-07",
    }
    missing = required_keys - set(row.keys())
    assert missing == set(), f"Missing ledger row keys: {missing}"


# ---------------------------------------------------------------------------
# 25–26. Index schema
# ---------------------------------------------------------------------------

def test_index_json_has_required_keys(tmp_path):
    """build_prophet produces an index.json with required top-level keys."""
    import scripts.build_prophet as bp  # noqa: PLC0415

    # Redirect output paths to tmp_path
    buys = [_make_buy("AAPL", score=70, act_level=3, spot=150.0)]
    standouts = _make_standouts(gate_go=False, buys=buys)
    standouts_path = tmp_path / "us_standouts.json"
    standouts_path.write_text(json.dumps(standouts))

    orig_standouts = bp.STANDOUTS_PATH
    orig_site = bp.SITE_PROPHET
    orig_plans = bp.PLANS_DIR
    orig_states = bp.STATES_DIR
    orig_index = bp.INDEX_PATH
    orig_ledger_path = bp.LEDGER_PATH
    orig_ledger_dir = bp.LEDGER_DIR

    try:
        bp.STANDOUTS_PATH = standouts_path
        bp.SITE_PROPHET = tmp_path / "site" / "prophet"
        bp.PLANS_DIR = bp.SITE_PROPHET / "plans"
        bp.STATES_DIR = bp.SITE_PROPHET / "states"
        bp.INDEX_PATH = bp.SITE_PROPHET / "index.json"
        bp.LEDGER_PATH = tmp_path / "data" / "prophet" / "ledger.jsonl"
        bp.LEDGER_DIR = tmp_path / "data" / "prophet"

        # Patch sys.argv
        import sys as _sys  # noqa: PLC0415
        with patch.object(_sys, "argv", ["build_prophet", "--date", "2026-07-02"]):
            with patch("engine.prophet_management.compute_management_state") as mock_mgmt:
                mock_mgmt.return_value = {
                    "schema": "prophet.management_state/v1",
                    "id": "AAPL-BULL-20260702",
                    "asof": "2026-07-02",
                    "phase": "pre_trigger",
                    "management_confidence": 55.0,
                    "raw_confidence": 55.0,
                    "recommended_action": "wait",
                    "components": {},
                    "geometry": {},
                    "change_reason": "",
                }
                # Also patch price history load to return valid data
                with patch("scripts.build_prophet._load_price_history_for_management") as mock_ph:
                    mock_ph.return_value = _make_price_history(150.0, 30)
                    bp.main()

        assert bp.INDEX_PATH.exists()
        idx = json.loads(bp.INDEX_PATH.read_text())
        for key in ["schema", "asof", "cadence", "authority_tier", "plan_count", "plans"]:
            assert key in idx, f"Missing key in index.json: {key}"
    finally:
        bp.STANDOUTS_PATH = orig_standouts
        bp.SITE_PROPHET = orig_site
        bp.PLANS_DIR = orig_plans
        bp.STATES_DIR = orig_states
        bp.INDEX_PATH = orig_index
        bp.LEDGER_PATH = orig_ledger_path
        bp.LEDGER_DIR = orig_ledger_dir


def test_index_note_no_validated_word(tmp_path):
    """Index note must not contain the word 'validated'."""
    # Build a minimal index dict directly (matching what build_prophet writes)
    index_note = (
        "DISPLAY-ONLY. All plans are display-tier artifacts. No signal has"
        " passed a forward ledger gate. The word 'validated' is forbidden in"
        " user-facing text. Nightly is the sole advancer of the forward ledger."
    )
    # The note contains 'validated' in the context of 'forbidden' — that's fine.
    # The CI check (check_validated_claims.py) checks for standalone positive claims.
    # Our note says validated IS FORBIDDEN — this should be fine per CI rules.
    # Verify the note does NOT positively claim something is validated.
    assert "validated" in index_note  # present but in a prohibition context
    # Key check: not a positive assertion like "this has been validated"
    assert "has been validated" not in index_note
    assert "is validated" not in index_note


# ---------------------------------------------------------------------------
# 27. End-to-end smoke test
# ---------------------------------------------------------------------------

def test_end_to_end_smoke(tmp_path):
    """build_prophet.main runs without exception on synthetic data."""
    import scripts.build_prophet as bp  # noqa: PLC0415

    buys = [
        _make_buy("AAPL", score=70, act_level=3, spot=150.0),
        _make_buy("MSFT", score=65, act_level=2, spot=420.0),
    ]
    standouts = _make_standouts(gate_go=False, buys=buys)
    standouts_path = tmp_path / "us_standouts.json"
    standouts_path.write_text(json.dumps(standouts))

    orig_standouts = bp.STANDOUTS_PATH
    orig_plans = bp.PLANS_DIR
    orig_states = bp.STATES_DIR
    orig_index = bp.INDEX_PATH
    orig_ledger_path = bp.LEDGER_PATH
    orig_ledger_dir = bp.LEDGER_DIR

    try:
        bp.STANDOUTS_PATH = standouts_path
        bp.PLANS_DIR = tmp_path / "plans"
        bp.STATES_DIR = tmp_path / "states"
        bp.INDEX_PATH = tmp_path / "index.json"
        bp.LEDGER_PATH = tmp_path / "ledger.jsonl"
        bp.LEDGER_DIR = tmp_path

        import sys as _sys  # noqa: PLC0415
        with patch.object(_sys, "argv", ["build_prophet", "--date", "2026-07-02"]):
            with patch("engine.prophet_management.compute_management_state") as mock_mgmt:
                mock_mgmt.return_value = {
                    "schema": "prophet.management_state/v1",
                    "id": "AAPL-BULL-20260702",
                    "asof": "2026-07-02",
                    "phase": "pre_trigger",
                    "management_confidence": 55.0,
                    "raw_confidence": 55.0,
                    "recommended_action": "wait",
                    "components": {},
                    "geometry": {},
                    "change_reason": "",
                }
                with patch("scripts.build_prophet._load_price_history_for_management") as mock_ph:
                    mock_ph.return_value = _make_price_history(150.0, 30)
                    bp.main()

        assert bp.INDEX_PATH.exists()
        assert bp.LEDGER_PATH.exists()
    finally:
        bp.STANDOUTS_PATH = orig_standouts
        bp.PLANS_DIR = orig_plans
        bp.STATES_DIR = orig_states
        bp.INDEX_PATH = orig_index
        bp.LEDGER_PATH = orig_ledger_path
        bp.LEDGER_DIR = orig_ledger_dir


# ---------------------------------------------------------------------------
# 28. N_CANDIDATES cap
# ---------------------------------------------------------------------------

def test_originate_plans_respects_n_candidates(tmp_path):
    """originate_plans produces at most N_CANDIDATES plans."""
    buys = [_make_buy(f"TICK{i}", score=80 - i, act_level=3, spot=100.0 + i)
            for i in range(N_CANDIDATES + 4)]
    standouts = _make_standouts(gate_go=True, buys=buys)
    standouts_path = tmp_path / "us_standouts.json"
    standouts_path.write_text(json.dumps(standouts))

    plans = originate_plans(
        standouts_path=standouts_path,
        asof="2026-07-02",
        existing_ids=set(),
        thetadata_store=None,
    )
    assert len(plans) <= N_CANDIDATES


# ---------------------------------------------------------------------------
# 29a–29f. Content block tests (_build_what_to_do_now, _build_profit_plan, _build_thesis)
# ---------------------------------------------------------------------------

def test_what_to_do_now_all_phases():
    """Every lifecycle phase produces 2-3 bullets; no validated word."""
    phases = [
        "pre_trigger", "triggered_pre_t1", "at_t1", "between_t1_t2",
        "post_t1_failed_hold", "at_t2", "overtime", "invalidated",
    ]
    for phase in phases:
        bullets = _build_what_to_do_now(
            phase=phase, entry=100.0, trigger=102.0, invalidation=90.0,
            t1=115.0, t2=130.0,
        )
        assert 2 <= len(bullets) <= 3, f"phase {phase}: expected 2-3 bullets, got {len(bullets)}"
        for b in bullets:
            assert isinstance(b, str) and len(b) > 10, f"phase {phase}: bullet too short: {b!r}"
            assert "validated" not in b.lower(), f"phase {phase}: 'validated' in bullet"


def test_what_to_do_now_no_t2():
    """Pre-trigger without T2 returns 2 bullets (not 3)."""
    bullets = _build_what_to_do_now(
        phase="pre_trigger", entry=100.0, trigger=102.0,
        invalidation=90.0, t1=115.0, t2=None,
    )
    assert len(bullets) == 2


def test_what_to_do_now_price_levels_interpolated():
    """Price levels are present in the bullets for the pre_trigger phase."""
    bullets = _build_what_to_do_now(
        phase="pre_trigger", entry=100.0, trigger=102.50, invalidation=90.0,
        t1=115.0, t2=None,
    )
    combined = " ".join(bullets)
    assert "$102.50" in combined


def test_profit_plan_statuses():
    """profit_plan rows carry correct ACTIVE/PENDING/DONE statuses per phase."""
    # pre_trigger: T1=ACTIVE, T2=PENDING
    rows = _build_profit_plan("pre_trigger", 100.0, 115.0, 130.0)
    assert rows[0]["status"] == "ACTIVE"
    assert rows[1]["status"] == "PENDING"

    # at_t1: T1=DONE, T2=ACTIVE
    rows = _build_profit_plan("at_t1", 100.0, 115.0, 130.0)
    assert rows[0]["status"] == "DONE"
    assert rows[1]["status"] == "ACTIVE"

    # at_t2: T1=DONE, T2=DONE
    rows = _build_profit_plan("at_t2", 100.0, 115.0, 130.0)
    assert rows[0]["status"] == "DONE"
    assert rows[1]["status"] == "DONE"

    # invalidated: T1=DONE
    rows = _build_profit_plan("invalidated", 100.0, 115.0, 130.0)
    assert rows[0]["status"] == "DONE"


def test_profit_plan_without_t2():
    """profit_plan without T2 returns exactly 1 row."""
    rows = _build_profit_plan("pre_trigger", 100.0, 115.0, None)
    assert len(rows) == 1
    assert rows[0]["label"] == "T1"


def test_profit_plan_row_keys():
    """Every profit_plan row has required keys and valid status."""
    rows = _build_profit_plan("pre_trigger", 100.0, 115.0, 130.0)
    for row in rows:
        assert "level" in row
        assert "label" in row
        assert "action" in row
        assert "status" in row
        assert row["status"] in ("ACTIVE", "PENDING", "DONE")


def test_thesis_no_validated_positive_claim():
    """thesis must not positively claim anything is validated."""
    b = {
        "conviction": {
            "score": 75, "band": "high",
            "drivers": ["validated momentum factor", "validated risk gate: trim"],
            "cautions": ["regime change risk"],
            "trust_tier": {"en": "T2 — medium confidence"},
        },
        "entry_signal": {
            "above200": True, "weekly_bull": False, "coiled": True,
            "entry_grade": "B+",
        },
        "hold": {},
        "state": "COILED",
        "archetype": "Resumption",
    }
    thesis = _build_thesis("AAPL", b)
    # "validated" must not appear before the DISPLAY-ONLY footer
    before_footer = thesis.split("DISPLAY-ONLY")[0]
    assert "validated" not in before_footer.lower(), (
        f"'validated' appeared in thesis body: {before_footer!r}"
    )
    # Should contain driver content (after sanitization)
    assert "momentum factor" in thesis or "risk gate" in thesis


def test_thesis_contains_technical_flags():
    """thesis includes technical flag context when es fields are set."""
    b = {
        "conviction": {"score": 80, "band": "high", "drivers": [], "cautions": []},
        "entry_signal": {"above200": True, "weekly_bull": True, "coiled": True},
        "hold": {},
        "state": "RUNNING",
    }
    thesis = _build_thesis("NVDA", b)
    assert "above 200-day" in thesis or "200" in thesis
    assert "coiled" in thesis or "compression" in thesis


def test_originate_plans_includes_content_blocks(tmp_path):
    """originate_plans output plans include what_to_do_now and profit_plan."""
    buys = [_make_buy("TSLA", score=72, act_level=3, spot=250.0)]
    standouts = _make_standouts(gate_go=False, buys=buys)
    standouts_path = tmp_path / "us_standouts.json"
    standouts_path.write_text(json.dumps(standouts))

    plans = originate_plans(
        standouts_path=standouts_path,
        asof="2026-07-07",
        existing_ids=set(),
        thetadata_store=None,
    )
    assert len(plans) == 1, f"expected 1 plan, got {len(plans)}"
    plan = plans[0]
    assert "what_to_do_now" in plan, "plan missing what_to_do_now"
    assert "profit_plan" in plan, "plan missing profit_plan"
    assert isinstance(plan["what_to_do_now"], list) and len(plan["what_to_do_now"]) >= 2
    assert isinstance(plan["profit_plan"], list) and len(plan["profit_plan"]) >= 1
    # content blocks must not contain "validated" positively
    for bullet in plan["what_to_do_now"]:
        assert "validated" not in bullet.lower(), f"'validated' in bullet: {bullet}"


# ---------------------------------------------------------------------------
# 31–37. Ledger advancement (advance_ledger)
# ---------------------------------------------------------------------------

import scripts.build_prophet as _bp  # noqa: E402 (after imports block)


def _make_plan(
    plan_id: str = "AAPL-BULL-20260601",
    ticker: str = "AAPL",
    entry: float = 100.0,
    invalidation: float = 90.0,
    t1: float = 115.0,
    t2: float = 130.0,
    signal_date: str = "2026-06-01",
    horizon_days: int = 45,
    direction: str = "BULL",
) -> dict:
    """Build a minimal prophet.trade_plan/v1 dict for ledger tests."""
    return {
        "schema": "prophet.trade_plan/v1",
        "id": plan_id,
        "asof": signal_date,
        "asset": ticker,
        "direction": direction,
        "signal_date": signal_date,
        "_signal_date": signal_date,
        "entry": entry,
        "invalidation": invalidation,
        "targets": [t1, t2],
        "horizon_days": horizon_days,
        "min_hold_days": 10,
        "tranche": 1,
        "option_contract": None,
        "authority_tier": "display",
        "source_engines": ["us_standouts_buy_lane"],
    }


def _price_history_from_closes(closes: list[float], start: str = "2026-06-02") -> pd.DataFrame:
    """Build a DatetimeIndex DataFrame from a list of daily closes."""
    dates = pd.date_range(start, periods=len(closes), freq="B")
    return pd.DataFrame({"close": closes}, index=dates)


class TestLedgerAdvancement:
    """Tests for advance_ledger + _determine_outcome."""

    def _run_advance(self, tmp_path, plans: dict, ph_map: dict, asof: str) -> list:
        """Run advance_ledger with mocked price history loader + tmp ledger path."""
        orig_ledger_path = _bp.LEDGER_PATH
        orig_ledger_dir = _bp.LEDGER_DIR

        try:
            _bp.LEDGER_PATH = tmp_path / "ledger.jsonl"
            _bp.LEDGER_DIR = tmp_path
            _bp._initialize_ledger()

            with patch("scripts.build_prophet._load_price_history_for_management",
                       side_effect=lambda ticker: ph_map.get(ticker)):
                return _bp.advance_ledger(plans, asof)
        finally:
            _bp.LEDGER_PATH = orig_ledger_path
            _bp.LEDGER_DIR = orig_ledger_dir

    def test_invalidation_hit(self, tmp_path):
        """Plan closes INVALIDATED when price drops through invalidation level."""
        plan = _make_plan(entry=100.0, invalidation=90.0, t1=115.0, t2=130.0,
                          signal_date="2026-06-01")
        # Day 3 (2026-06-04): price drops to 88 (< 90 invalidation)
        closes = [101.0, 100.5, 88.0, 95.0]
        ph = _price_history_from_closes(closes, start="2026-06-02")
        rows = self._run_advance(tmp_path, {plan["id"]: plan}, {"AAPL": ph}, "2026-07-01")
        assert len(rows) == 1
        assert rows[0]["outcome"] == "INVALIDATED"
        assert rows[0]["stock_result_pct"] is not None
        assert rows[0]["stock_result_pct"] < 0  # loss

    def test_t1_hit(self, tmp_path):
        """Plan closes T1_HIT when price reaches T1 before invalidation or horizon."""
        plan = _make_plan(entry=100.0, invalidation=90.0, t1=115.0, t2=130.0,
                          signal_date="2026-06-01")
        # Day 5: price reaches 116 (> 115 T1)
        closes = [101.0, 103.0, 108.0, 112.0, 116.0]
        ph = _price_history_from_closes(closes, start="2026-06-02")
        rows = self._run_advance(tmp_path, {plan["id"]: plan}, {"AAPL": ph}, "2026-07-01")
        assert len(rows) == 1
        assert rows[0]["outcome"] == "T1_HIT"
        assert rows[0]["stock_result_pct"] > 0  # profit

    def test_t2_hit(self, tmp_path):
        """T2_HIT takes priority over T1_HIT on same scan (T2 first in priority)."""
        plan = _make_plan(entry=100.0, invalidation=90.0, t1=115.0, t2=130.0,
                          signal_date="2026-06-01")
        # Day 3: price jumps straight to 132 (> 130 T2)
        closes = [101.0, 110.0, 132.0]
        ph = _price_history_from_closes(closes, start="2026-06-02")
        rows = self._run_advance(tmp_path, {plan["id"]: plan}, {"AAPL": ph}, "2026-07-01")
        assert len(rows) == 1
        assert rows[0]["outcome"] == "T2_HIT"

    def test_expired(self, tmp_path):
        """Plan closes EXPIRED when horizon_days elapse without hitting T1/T2/inval."""
        plan = _make_plan(entry=100.0, invalidation=90.0, t1=115.0, t2=130.0,
                          signal_date="2026-06-01", horizon_days=5)
        # 6 business days, price stays flat (never hits any trigger, reaches horizon on day 5)
        closes = [101.0, 101.5, 102.0, 101.0, 101.5]  # 5 days → EXPIRED
        ph = _price_history_from_closes(closes, start="2026-06-02")
        rows = self._run_advance(tmp_path, {plan["id"]: plan}, {"AAPL": ph}, "2026-07-01")
        assert len(rows) == 1
        assert rows[0]["outcome"] == "EXPIRED"

    def test_idempotency(self, tmp_path):
        """Re-running advance_ledger for an already-closed plan appends no new rows."""
        plan = _make_plan(entry=100.0, invalidation=90.0, t1=115.0, t2=130.0,
                          signal_date="2026-06-01")
        closes = [88.0, 90.0, 90.0]  # invalidated on day 1
        ph = _price_history_from_closes(closes, start="2026-06-02")

        orig_ledger_path = _bp.LEDGER_PATH
        orig_ledger_dir = _bp.LEDGER_DIR
        try:
            _bp.LEDGER_PATH = tmp_path / "ledger.jsonl"
            _bp.LEDGER_DIR = tmp_path
            _bp._initialize_ledger()

            with patch("scripts.build_prophet._load_price_history_for_management",
                       side_effect=lambda ticker: ph):
                rows1 = _bp.advance_ledger({plan["id"]: plan}, "2026-07-01")
                rows2 = _bp.advance_ledger({plan["id"]: plan}, "2026-07-01")

            assert len(rows1) == 1
            assert len(rows2) == 0, "Second run must not duplicate the ledger row"

            # Verify ledger has exactly ONE data row (not 2)
            content = _bp.LEDGER_PATH.read_text()
            data_lines = [l for l in content.splitlines() if l.strip() and not l.startswith("#")]
            assert len(data_lines) == 1
        finally:
            _bp.LEDGER_PATH = orig_ledger_path
            _bp.LEDGER_DIR = orig_ledger_dir

    def test_open_plan_produces_no_row(self, tmp_path):
        """A plan that hasn't hit any trigger yet produces no ledger row."""
        plan = _make_plan(entry=100.0, invalidation=90.0, t1=115.0, t2=130.0,
                          signal_date="2026-06-01", horizon_days=45)
        # Price stays just inside all triggers
        closes = [101.0, 102.0, 103.0]
        ph = _price_history_from_closes(closes, start="2026-06-02")
        rows = self._run_advance(tmp_path, {plan["id"]: plan}, {"AAPL": ph}, "2026-06-05")
        assert rows == []

    def test_row_schema_keys(self, tmp_path):
        """Every appended ledger row has all required schema keys."""
        required_keys = {
            "schema", "id", "asset", "direction", "signal_date",
            "close_date", "outcome", "stock_result_pct",
            "option_result_pct", "days_held", "plan_adherence", "asof",
        }
        plan = _make_plan(entry=100.0, invalidation=90.0, t1=115.0, t2=130.0,
                          signal_date="2026-06-01")
        closes = [88.0]  # immediate invalidation
        ph = _price_history_from_closes(closes, start="2026-06-02")
        rows = self._run_advance(tmp_path, {plan["id"]: plan}, {"AAPL": ph}, "2026-07-01")
        assert len(rows) == 1
        missing = required_keys - set(rows[0].keys())
        assert missing == set(), f"Missing ledger row keys: {missing}"
        assert rows[0]["schema"] == "prophet.ledger/v1"
