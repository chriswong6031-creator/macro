"""tests/test_cohort_flow_chips.py — FL-D FC-R5 cohort flow chips.

Tests:
  (a) fail-open: absent data/options_flow/cohorts.parquet → flow block None,
      panel identical to no-flow baseline, basket_turn_watch row unchanged
  (b) tilt words at P/C boundaries (0.75 / 1.25 exact)
  (c) cohort_flow.v1 forward ledger idempotence (same date → single row)
  (d) forbidden field names not in basket_turn_watch output (direction, score)
  (e) missing flow absent when basket is not a cohort
  (f) mag7_regime snapshot includes flow block when cohorts.parquet present
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MAG7 = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]


def _bdays(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range(end=str(date.today()), periods=n)


def _price_series(n: int = 300, slope: float = 0.001) -> pd.Series:
    idx = _bdays(n)
    prices = 100.0 * (1 + slope) ** np.arange(n)
    return pd.Series(prices, index=idx, name="close")


def _write_ohlcv(tmp: Path, sym: str, series: pd.Series) -> None:
    out = tmp / "data" / "baskets" / "ohlcv" / f"{sym}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"close": series}).to_parquet(out)


def _write_spy(tmp: Path, series: pd.Series) -> None:
    out = tmp / "data" / "yahoo" / "SPY.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"close": series}).to_parquet(out)


def _write_cohorts(
    data_root: Path,
    rows: list[dict],
) -> None:
    """Write cohorts.parquet under data_root/options_flow/cohorts.parquet.

    ``data_root`` is the engine data root (e.g. tmp_path / "data"), matching
    the ``root`` argument of ``_compute_flow_block``.  The helper does NOT
    add another "data/" prefix so callers can pass the data root directly.
    """
    p = data_root / "options_flow" / "cohorts.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(p)


def _minimal_mag7_fixture(tmp: Path) -> None:
    """Write minimal price data so mag7_regime.snapshot() doesn't crash."""
    for sym in MAG7:
        _write_ohlcv(tmp, sym, _price_series())
    _write_spy(tmp, _price_series(slope=0.0005))


def _cohort_row(
    cohort_id: str,
    pc_ratio: float,
    n_sessions: int = 1,
    asof_offset_days: int = 0,
) -> list[dict]:
    """Build a list of cohort rows for testing."""
    rows = []
    for i in range(n_sessions):
        d = date.today() - timedelta(days=asof_offset_days + (n_sessions - 1 - i))
        rows.append({
            "date": pd.Timestamp(d),
            "cohort_id": cohort_id,
            "gross_premium_mn": 100.0 + i * 10,
            "net_premium_mn": 50.0 + i * 5,
            "pc_ratio": pc_ratio,
            "zerodte_share": 0.15,
            "n_members_covered": 7,
            "n_members": 7,
        })
    return rows


# ---------------------------------------------------------------------------
# (a) fail-open: absent cohorts.parquet → flow block is None
# ---------------------------------------------------------------------------


def test_flow_block_absent_when_no_cohorts_file(tmp_path):
    """_compute_flow_block returns None when cohorts.parquet is missing."""
    from engine.mag7_regime import _compute_flow_block
    result = _compute_flow_block(root=tmp_path / "data")
    assert result is None, "Expected None when cohorts.parquet absent"


def test_mag7_snapshot_flow_none_when_no_cohorts(tmp_path):
    """mag7_regime.snapshot() flow field is None when cohorts.parquet absent."""
    _minimal_mag7_fixture(tmp_path)
    from engine import mag7_regime
    payload = mag7_regime.snapshot(root=tmp_path)
    # flow key should exist but be None (fail-open)
    assert "flow" in payload, "payload must have 'flow' key"
    assert payload["flow"] is None, "flow must be None when cohorts.parquet absent"


def test_basket_turn_row_no_cohort_flow_when_no_file(tmp_path):
    """basket_turn_watch rows must not have cohort_flow when cohorts.parquet absent."""
    # Build minimal baskets metadata with mag7 basket
    bdata = tmp_path / "data"
    bdata.mkdir(parents=True, exist_ok=True)
    membership = {
        "mag7": {
            "members": [{"ticker": t, "removed": None} for t in MAG7]
        }
    }
    mp = bdata / "baskets" / "membership.json"
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps({"baskets": membership}))

    from engine import basket_turn_watch
    result = basket_turn_watch.compute(data_root=bdata)
    basket_rows = result.get("baskets", [])
    for row in basket_rows:
        if row.get("basket_id") == "mag7":
            assert "cohort_flow" not in row, (
                "cohort_flow must be absent on row when cohorts.parquet missing"
            )


# ---------------------------------------------------------------------------
# (b) tilt words at P/C boundaries
# ---------------------------------------------------------------------------


def test_pc_word_call_tilted(tmp_path):
    """pc_ratio = 0.75 → call_tilted (boundary: <= 0.75)."""
    from engine.mag7_regime import _compute_flow_block
    _write_cohorts(tmp_path / "data", _cohort_row("mag7", 0.75))
    result = _compute_flow_block(root=tmp_path / "data")
    assert result is not None
    assert result["pc_word"] == "call_tilted", f"Expected call_tilted, got {result['pc_word']}"


def test_pc_word_balanced_just_above_call(tmp_path):
    """pc_ratio = 0.76 → balanced (just above call_tilted threshold)."""
    from engine.mag7_regime import _compute_flow_block
    _write_cohorts(tmp_path / "data", _cohort_row("mag7", 0.76))
    result = _compute_flow_block(root=tmp_path / "data")
    assert result is not None
    assert result["pc_word"] == "balanced", f"Expected balanced, got {result['pc_word']}"


def test_pc_word_put_tilted(tmp_path):
    """pc_ratio = 1.25 → put_tilted (boundary: >= 1.25)."""
    from engine.mag7_regime import _compute_flow_block
    _write_cohorts(tmp_path / "data", _cohort_row("mag7", 1.25))
    result = _compute_flow_block(root=tmp_path / "data")
    assert result is not None
    assert result["pc_word"] == "put_tilted", f"Expected put_tilted, got {result['pc_word']}"


def test_pc_word_balanced_just_below_put(tmp_path):
    """pc_ratio = 1.24 → balanced (just below put_tilted threshold)."""
    from engine.mag7_regime import _compute_flow_block
    _write_cohorts(tmp_path / "data", _cohort_row("mag7", 1.24))
    result = _compute_flow_block(root=tmp_path / "data")
    assert result is not None
    assert result["pc_word"] == "balanced", f"Expected balanced, got {result['pc_word']}"


def test_pc_word_well_below_call(tmp_path):
    """pc_ratio = 0.50 → call_tilted."""
    from engine.mag7_regime import _compute_flow_block
    _write_cohorts(tmp_path / "data", _cohort_row("mag7", 0.50))
    result = _compute_flow_block(root=tmp_path / "data")
    assert result is not None
    assert result["pc_word"] == "call_tilted"


def test_pc_word_well_above_put(tmp_path):
    """pc_ratio = 2.0 → put_tilted."""
    from engine.mag7_regime import _compute_flow_block
    _write_cohorts(tmp_path / "data", _cohort_row("mag7", 2.0))
    result = _compute_flow_block(root=tmp_path / "data")
    assert result is not None
    assert result["pc_word"] == "put_tilted"


# ---------------------------------------------------------------------------
# (c) tilt_sessions count
# ---------------------------------------------------------------------------


def test_tilt_sessions_counts_call_tilted(tmp_path):
    """tilt_sessions = count of call_tilted in last 5 sessions."""
    from engine.mag7_regime import _compute_flow_block

    # Build 5 sessions: 3 call_tilted (0.60) and 2 put_tilted (1.40)
    rows = []
    pcs = [0.60, 0.60, 1.40, 0.60, 1.40]  # 3 call_tilted
    today = date.today()
    for i, pc in enumerate(pcs):
        rows.append({
            "date": pd.Timestamp(today - timedelta(days=4 - i)),
            "cohort_id": "mag7",
            "gross_premium_mn": 100.0,
            "net_premium_mn": 50.0,
            "pc_ratio": pc,
            "zerodte_share": 0.15,
            "n_members_covered": 7,
            "n_members": 7,
        })
    _write_cohorts(tmp_path / "data", rows)
    result = _compute_flow_block(root=tmp_path / "data")
    assert result is not None
    # last row has pc=1.40 → put_tilted
    assert result["pc_word"] == "put_tilted"
    assert result["tilt_sessions"] == 3, (
        f"Expected 3 call_tilted sessions, got {result['tilt_sessions']}"
    )


# ---------------------------------------------------------------------------
# (d) ledger idempotence
# ---------------------------------------------------------------------------


def test_cohort_flow_ledger_idempotent(tmp_path, monkeypatch):
    """Appending the same date+cohort twice → only one row in ledger."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    from engine.mag7_regime import _append_cohort_flow_ledger

    rows = [{"date": "2026-07-11", "cohort": "mag7", "tilt": "call_tilted",
             "pc_ratio": 0.70, "gross_mn": 120.0}]
    _append_cohort_flow_ledger("2026-07-11", rows, root=tmp_path / "data")
    _append_cohort_flow_ledger("2026-07-11", rows, root=tmp_path / "data")

    ledger_path = tmp_path / "data" / "cohort_flow_ledger" / "ledger.jsonl"
    assert ledger_path.exists()
    lines = [l for l in ledger_path.read_text().splitlines() if l.strip()]
    assert len(lines) == 1, f"Expected 1 row after 2 identical appends, got {len(lines)}"
    obj = json.loads(lines[0])
    assert obj["date"] == "2026-07-11"
    assert obj["cohort"] == "mag7"
    assert obj["tilt"] == "call_tilted"


def test_cohort_flow_ledger_lane_gate(tmp_path, monkeypatch):
    """Ledger does not write when COLLECT_LANE != nightly."""
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)

    from engine.mag7_regime import _append_cohort_flow_ledger

    rows = [{"date": "2026-07-11", "cohort": "mag7", "tilt": "balanced",
             "pc_ratio": 1.0, "gross_mn": 80.0}]
    _append_cohort_flow_ledger("2026-07-11", rows, root=tmp_path / "data")

    ledger_path = tmp_path / "data" / "cohort_flow_ledger" / "ledger.jsonl"
    assert not ledger_path.exists(), "Ledger must not be written outside nightly lane"


def test_cohort_flow_ledger_multi_date(tmp_path, monkeypatch):
    """Different dates → multiple rows in ledger."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    from engine.mag7_regime import _append_cohort_flow_ledger

    for d_str in ["2026-07-10", "2026-07-11"]:
        rows = [{"date": d_str, "cohort": "mag7", "tilt": "balanced",
                 "pc_ratio": 0.90, "gross_mn": 100.0}]
        _append_cohort_flow_ledger(d_str, rows, root=tmp_path / "data")

    ledger_path = tmp_path / "data" / "cohort_flow_ledger" / "ledger.jsonl"
    lines = [l for l in ledger_path.read_text().splitlines() if l.strip()]
    assert len(lines) == 2, f"Expected 2 rows for 2 dates, got {len(lines)}"


# ---------------------------------------------------------------------------
# (e) basket not in cohort set → no cohort_flow field
# ---------------------------------------------------------------------------


def test_non_cohort_basket_no_flow_field(tmp_path):
    """Baskets not in _COHORT_BASKET_IDS must not receive cohort_flow field."""
    from engine import basket_turn_watch

    # Write a cohorts file so enrichment would run if it had a cohort id
    _write_cohorts(tmp_path / "data", _cohort_row("mag7", 0.70))

    # Build a non-cohort basket (e.g. 'energy_oil')
    membership = {
        "energy_oil": {
            "members": [{"ticker": "XOM", "removed": None}, {"ticker": "CVX", "removed": None}]
        }
    }
    mp = tmp_path / "data" / "baskets" / "membership.json"
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps({"baskets": membership}))

    result = basket_turn_watch.compute(data_root=tmp_path / "data")
    for row in result.get("baskets", []):
        if row.get("basket_id") == "energy_oil":
            assert "cohort_flow" not in row, (
                "Non-cohort basket must not have cohort_flow field"
            )


# ---------------------------------------------------------------------------
# (f) mag7_regime snapshot with flow present
# ---------------------------------------------------------------------------


def test_mag7_snapshot_has_flow_block_when_cohorts_present(tmp_path):
    """mag7_regime.snapshot() payload.flow is populated when cohorts.parquet exists."""
    _minimal_mag7_fixture(tmp_path)
    _write_cohorts(
        tmp_path / "data",
        _cohort_row("mag7", 0.70, n_sessions=5),
    )
    from engine import mag7_regime
    payload = mag7_regime.snapshot(root=tmp_path)
    assert "flow" in payload
    flow = payload["flow"]
    assert flow is not None, "flow must not be None when cohorts.parquet present"
    assert "pc_word" in flow
    assert flow["pc_word"] == "call_tilted"
    assert "tilt_sessions" in flow
    assert "coverage" in flow


# ---------------------------------------------------------------------------
# (g) forbidden fields — no direction/score language in basket_turn_watch output
# ---------------------------------------------------------------------------


def test_no_direction_score_fields_in_flow_context(tmp_path):
    """cohort_flow dict must not contain direction, score, or composite fields."""
    from engine.mag7_regime import _compute_flow_block
    _write_cohorts(tmp_path / "data", _cohort_row("mag7", 0.70))
    result = _compute_flow_block(root=tmp_path / "data")
    assert result is not None
    forbidden = {"direction", "score", "composite", "signal", "rank"}
    actual_keys = set(result.keys())
    overlap = forbidden & actual_keys
    assert not overlap, f"Flow block contains forbidden keys: {overlap}"
