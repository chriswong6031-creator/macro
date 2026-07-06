"""Tests for prediction-market flow analytics (engine/pm_flow.py) and
collector schema evolution (collectors/prediction_markets.py).

Coverage:
  T1 — schema evolution: old parquet (7-col) loads and new nullable columns are NaN
  T2 — extract_outcomes returns mkt_volume24hr field (new collector field)
  T3 — compute_flow_z: min-history gate (< 20 → NaN z)
  T4 — compute_flow_z: z-score correctness on a controlled series
  T5 — compute_flow_z: missing volume24hr column raises ValueError
  T6 — collector graceful-degrade: _safe_float handles None/str/bad input
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ── helpers ──────────────────────────────────────────────────────────────────


def _make_old_snapshots(n: int = 5) -> pd.DataFrame:
    """Simulate a legacy parquet that pre-dates the flow columns."""
    rows = []
    for i in range(n):
        rows.append({
            "snapshot_date": f"2026-06-{14 + i:02d}",
            "source": "polymarket",
            "event_key": "fed_next",
            "event_title": "Fed Decision in July?",
            "end_date": "2026-07-30",
            "outcome": "25 bps decrease",
            "prob": 0.42 + i * 0.01,
        })
    return pd.DataFrame(rows)


def _make_new_snapshots(n: int = 25, base_vol: float = 1_000_000.0) -> pd.DataFrame:
    """Snapshots that include the new flow columns."""
    rows = []
    for i in range(n):
        rows.append({
            "snapshot_date": f"2026-06-{1 + i:02d}",
            "source": "polymarket",
            "event_key": "fed_next",
            "event_title": "Fed Decision in July?",
            "end_date": "2026-07-30",
            "outcome": "25 bps decrease",
            "prob": 0.42,
            "volume24hr": base_vol + i * 50_000,
            "volume_total": 10_000_000.0 + i * 200_000,
            "liquidity": 2_000_000.0,
            "open_interest": 500_000.0,
            "mkt_volume24hr": base_vol * 0.3 + i * 15_000,
        })
    return pd.DataFrame(rows)


# ── T1: schema evolution ──────────────────────────────────────────────────────


def test_old_parquet_loads_with_new_cols_null(tmp_path: Path) -> None:
    """Old 7-column parquet loads; new flow columns are NaN for legacy rows."""
    old = _make_old_snapshots(3)
    old_path = tmp_path / "snapshots.parquet"
    old.to_parquet(old_path, index=False)

    loaded = pd.read_parquet(old_path)
    # Original columns present and intact
    assert set(["snapshot_date", "source", "event_key", "prob"]) <= set(loaded.columns)
    # New flow columns are ABSENT from old parquet (not NaN — just not there yet)
    for col in ("volume24hr", "volume_total", "liquidity", "open_interest", "mkt_volume24hr"):
        assert col not in loaded.columns, f"expected {col} absent in legacy parquet"

    # Simulate append: concat old with new-format rows → new cols NaN for old rows
    new = _make_new_snapshots(2)
    merged = pd.concat([loaded, new], ignore_index=True)
    old_mask = merged["snapshot_date"].isin(old["snapshot_date"])
    assert merged.loc[old_mask, "volume24hr"].isna().all(), \
        "legacy rows should have NaN volume24hr after concat"
    assert not merged.loc[~old_mask, "volume24hr"].isna().any(), \
        "new rows should have non-null volume24hr"


# ── T2: extract_outcomes returns mkt_volume24hr ───────────────────────────────


def test_extract_outcomes_includes_mkt_volume24hr() -> None:
    from collectors.prediction_markets import extract_outcomes

    event = {
        "markets": [
            {
                "groupItemTitle": "Cut 25bps",
                "outcomePrices": '["0.72", "0.28"]',
                "volume24hr": 123456.78,
            },
            {
                "groupItemTitle": "Hold",
                "outcomePrices": '["0.25", "0.75"]',
                "volume24hr": None,  # missing — should become None
            },
        ]
    }
    outcomes = extract_outcomes(event)
    assert len(outcomes) == 2
    assert outcomes[0]["outcome"] == "Cut 25bps"
    assert abs(outcomes[0]["prob"] - 0.72) < 1e-6
    assert outcomes[0]["mkt_volume24hr"] == pytest.approx(123456.78)
    assert outcomes[1]["mkt_volume24hr"] is None


def test_extract_outcomes_missing_volume24hr_field() -> None:
    """Older-format market dicts without volume24hr key → mkt_volume24hr is None."""
    from collectors.prediction_markets import extract_outcomes

    event = {
        "markets": [
            {"groupItemTitle": "Yes", "outcomePrices": '["0.5", "0.5"]'}
            # no volume24hr key
        ]
    }
    outcomes = extract_outcomes(event)
    assert outcomes[0]["mkt_volume24hr"] is None


# ── T3: z-score min-history gate ─────────────────────────────────────────────


def test_flow_z_below_min_history_gate() -> None:
    """Events with < MIN_HISTORY snapshots emit NaN for vol24_z."""
    from engine.pm_flow import MIN_HISTORY, compute_flow_z

    n = MIN_HISTORY - 1  # one below threshold
    snaps = _make_new_snapshots(n)
    result = compute_flow_z(snaps, min_history=MIN_HISTORY)
    assert not result.empty
    # All z-scores must be NaN (not enough history)
    assert result["vol24_z"].isna().all(), \
        f"expected all NaN z-scores for {n} snapshots (gate = {MIN_HISTORY})"


def test_flow_z_at_min_history_emits_z() -> None:
    """Events with MIN_HISTORY snapshots of varying volume emit a numeric z-score."""
    from engine.pm_flow import MIN_HISTORY, compute_flow_z

    # Varying volume24hr so the delta series has non-zero std → z is emitted.
    rows = []
    np.random.seed(42)
    vol = 1_000_000.0
    for i in range(MIN_HISTORY + 5):
        vol += float(np.random.uniform(10_000, 100_000))  # random increments
        rows.append({
            "snapshot_date": f"2026-06-{1 + i:02d}",
            "event_key": "var_event",
            "volume24hr": vol,
            "source": "polymarket", "event_title": "T", "end_date": "2026-12-01",
            "outcome": "Yes", "prob": 0.5,
        })
    snaps = pd.DataFrame(rows)
    result = compute_flow_z(snaps, min_history=MIN_HISTORY)
    valid = result.dropna(subset=["vol24_z"])
    assert not valid.empty, "expected at least one non-NaN z-score with varying volume"


# ── T4: z-score correctness ───────────────────────────────────────────────────


def test_flow_z_correctness_constant_delta() -> None:
    """Constant volume increment → delta series is constant → z-score = 0."""
    from engine.pm_flow import MIN_HISTORY, compute_flow_z

    n = MIN_HISTORY + 10
    # volume24hr increases by exactly 50_000 each snapshot → constant delta
    rows = []
    for i in range(n):
        rows.append({
            "snapshot_date": f"2026-0{1 + i // 28:01d}-{1 + (i % 28):02d}",
            "event_key": "test_event",
            "volume24hr": float(i * 50_000),
            "source": "polymarket", "event_title": "T", "end_date": "2026-12-01",
            "outcome": "Yes", "prob": 0.5,
        })
    snaps = pd.DataFrame(rows)
    result = compute_flow_z(snaps, min_history=MIN_HISTORY)
    valid = result.dropna(subset=["vol24_z"])
    # With constant delta, std → 0 (or near-0 from float arithmetic);
    # z should be 0 or NaN (std == 0 guard). Either is acceptable.
    for _, row in valid.iterrows():
        z = row["vol24_z"]
        assert z == pytest.approx(0.0, abs=1e-6) or math.isnan(z), \
            f"constant delta should yield z≈0, got {z}"


def test_flow_z_spike_yields_positive_z() -> None:
    """A large positive delta spike on the last snapshot yields a high z-score."""
    from engine.pm_flow import MIN_HISTORY, compute_flow_z

    n = MIN_HISTORY + 5
    rows = []
    for i in range(n - 1):
        rows.append({
            "snapshot_date": f"2026-06-{i + 1:02d}",
            "event_key": "spike_event",
            "volume24hr": float(i * 10_000),
            "source": "polymarket", "event_title": "T", "end_date": "2026-12-01",
            "outcome": "Yes", "prob": 0.5,
        })
    # Spike: 100x normal increment
    rows.append({
        "snapshot_date": f"2026-07-01",
        "event_key": "spike_event",
        "volume24hr": rows[-1]["volume24hr"] + 1_000_000,  # huge spike
        "source": "polymarket", "event_title": "T", "end_date": "2026-12-01",
        "outcome": "Yes", "prob": 0.5,
    })
    snaps = pd.DataFrame(rows)
    result = compute_flow_z(snaps, min_history=MIN_HISTORY)
    last = result[result["snapshot_date"] == "2026-07-01"]
    assert not last.empty
    z = last.iloc[0]["vol24_z"]
    assert not math.isnan(z), "spike row should have a numeric z"
    assert z > 2.0, f"spike should produce z > 2, got {z:.2f}"


# ── T5: missing column raises ────────────────────────────────────────────────


def test_flow_z_raises_on_missing_volume24hr_col() -> None:
    from engine.pm_flow import compute_flow_z

    bad = pd.DataFrame({"snapshot_date": ["2026-06-01"], "event_key": ["x"]})
    with pytest.raises(ValueError, match="missing columns"):
        compute_flow_z(bad)


# ── T6: _safe_float graceful degrade ─────────────────────────────────────────


def test_safe_float_handles_various_inputs() -> None:
    from collectors.prediction_markets import _safe_float

    assert _safe_float(None) is None
    assert _safe_float("") is None
    assert _safe_float("abc") is None
    assert _safe_float("1234.5") == pytest.approx(1234.5)
    assert _safe_float(9999) == pytest.approx(9999.0)
    assert _safe_float(0.0) == pytest.approx(0.0)
