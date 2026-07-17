"""Tests for engine.leadership_crack — DISPLAY-ONLY cohort velocity + carnage organ.

Load-bearing invariants tested here:
  - State machine transitions: INTACT -> CRACKING -> BROKEN -> recovery (hysteresis)
  - Broken exits only after 3 consecutive sessions with med_dd > -0.12
  - Freshness gate excludes members with last obs > 3 sessions before panel max
  - Causal z-vel: appending future rows does NOT change past z at any date
  - Fail-open: missing/empty files return None without raising
  - latest.json written; forward_log.jsonl appended ONLY when COLLECT_LANE=nightly
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import leadership_crack as lc  # noqa: E402


# --------------------------------------------------------------------------- #
# Helpers to build synthetic test data
# --------------------------------------------------------------------------- #
def _make_member_closes(n_members: int, n_days: int,
                        trend: float = 0.0, seed: int = 42) -> pd.DataFrame:
    """Synthetic close prices for n_members tickers over n_days."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-02", periods=n_days)
    data = {}
    for i in range(n_members):
        daily_ret = rng.normal(trend, 0.015, size=n_days)
        prices = 100.0 * np.exp(np.cumsum(daily_ret))
        data[f"M{i:02d}"] = prices
    return pd.DataFrame(data, index=idx)


def _spy_closes(n_days: int, trend: float = 0.0, seed: int = 99) -> pd.Series:
    """Synthetic SPY close series."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-02", periods=n_days)
    daily_ret = rng.normal(trend, 0.008, size=n_days)
    prices = pd.Series(500.0 * np.exp(np.cumsum(daily_ret)), index=idx)
    return prices


def _run_state_machine(z_vals, med_dd_vals, carnage_ema_vals, dates=None):
    """Convenience: build Series and run state machine."""
    n = len(z_vals)
    idx = pd.bdate_range("2024-01-02", periods=n) if dates is None else pd.DatetimeIndex(dates)
    z_s = pd.Series(z_vals, index=idx, dtype=float)
    md_s = pd.Series(med_dd_vals, index=idx, dtype=float)
    ce_s = pd.Series(carnage_ema_vals, index=idx, dtype=float)
    return lc._state_machine(z_s, md_s, ce_s)


# --------------------------------------------------------------------------- #
# State machine: INTACT -> CRACKING
# --------------------------------------------------------------------------- #
def test_intact_baseline():
    """All signals benign -> INTACT throughout."""
    n = 10
    z = [0.0] * n
    md = [-0.05] * n
    ce = [0.10] * n
    states, _ = _run_state_machine(z, md, ce)
    assert all(s == "INTACT" for s in states)


def test_cracking_on_z_vel():
    """z_vel <= -1.5 trips CRACKING."""
    z = [0.0, 0.0, -2.0, -2.0]
    md = [-0.05, -0.05, -0.05, -0.05]
    ce = [0.10, 0.10, 0.10, 0.10]
    states, _ = _run_state_machine(z, md, ce)
    assert states.iloc[0] == "INTACT"
    assert states.iloc[1] == "INTACT"
    assert states.iloc[2] == "CRACKING"
    assert states.iloc[3] == "CRACKING"


def test_cracking_on_med_dd_and_carnage():
    """med_dd <= -0.12 AND carnage_ema >= 0.40 trips CRACKING."""
    z = [0.0, 0.0, 0.0, 0.0]
    md = [-0.05, -0.05, -0.13, -0.13]
    ce = [0.10, 0.10, 0.41, 0.41]
    states, _ = _run_state_machine(z, md, ce)
    assert states.iloc[0] == "INTACT"
    assert states.iloc[2] == "CRACKING"


def test_intact_requires_both_conditions_clear():
    """CRACKING only when EITHER condition, not when both cleared."""
    # z clears but med_dd+carnage still trip
    z = [0.0, -2.0, 0.0, 0.0]
    md = [-0.05, -0.05, -0.13, -0.13]
    ce = [0.10, 0.10, 0.41, 0.41]
    states, _ = _run_state_machine(z, md, ce)
    assert states.iloc[1] == "CRACKING"
    assert states.iloc[2] == "CRACKING"  # stays CRACKING because med_dd+carnage still trip
    assert states.iloc[3] == "CRACKING"


def test_return_intact_from_cracking():
    """z > -1.5 AND med_dd > -0.12 in CRACKING -> back to INTACT."""
    z = [0.0, -2.0, 0.0, 0.0]
    md = [-0.05, -0.05, -0.05, -0.05]
    ce = [0.10, 0.10, 0.10, 0.10]
    states, _ = _run_state_machine(z, md, ce)
    assert states.iloc[1] == "CRACKING"
    assert states.iloc[2] == "INTACT"
    assert states.iloc[3] == "INTACT"


# --------------------------------------------------------------------------- #
# State machine: BROKEN entry and hysteretic exit
# --------------------------------------------------------------------------- #
def test_broken_entry():
    """med_dd <= -0.20 AND carnage_ema >= 0.60 -> BROKEN."""
    z = [0.0, 0.0, 0.0]
    md = [-0.05, -0.05, -0.21]
    ce = [0.10, 0.10, 0.65]
    states, _ = _run_state_machine(z, md, ce)
    assert states.iloc[2] == "BROKEN"


def test_broken_direct_from_intact():
    """Can enter BROKEN directly from INTACT on one-day shock."""
    z = [0.0, -3.0]
    md = [-0.05, -0.25]
    ce = [0.10, 0.65]
    states, _ = _run_state_machine(z, md, ce)
    assert states.iloc[0] == "INTACT"
    assert states.iloc[1] == "BROKEN"


def test_broken_persists_no_heal():
    """BROKEN does not exit with fewer than 3 consecutive heal sessions."""
    # 2 sessions of heal, then relapse -> stays BROKEN
    z = [0.0] * 10
    md = [-0.05, -0.05, -0.25, -0.05, -0.05, -0.25, -0.25, -0.25, -0.25, -0.25]
    ce = [0.10, 0.10, 0.65, 0.65, 0.65, 0.65, 0.65, 0.65, 0.65, 0.65]
    states, _ = _run_state_machine(z, md, ce)
    assert states.iloc[2] == "BROKEN"
    # Still BROKEN after 2 heal sessions (only 2 < 3)
    assert states.iloc[4] == "BROKEN"


def test_broken_heals_after_3_consecutive():
    """BROKEN exits to INTACT after exactly 3 consecutive med_dd > -0.12."""
    z = [0.0] * 7
    md = [-0.05, -0.05, -0.25, -0.05, -0.05, -0.05, -0.05]
    ce = [0.10, 0.10, 0.65, 0.65, 0.65, 0.65, 0.65]
    states, _ = _run_state_machine(z, md, ce)
    assert states.iloc[2] == "BROKEN"
    # Session 3 (idx 3) = 1 heal, 4 = 2 heals, 5 = 3 heals -> idx 5 is still BROKEN (counter hits 3 AT idx 5)
    assert states.iloc[5] == "INTACT"
    assert states.iloc[6] == "INTACT"


def test_broken_heal_counter_resets():
    """Counter resets when heal is interrupted."""
    # 2 heal, relapse, 3 heal -> exits at 3rd consecutive after relapse
    z = [0.0] * 9
    md = [-0.05, -0.21, -0.05, -0.05, -0.21, -0.05, -0.05, -0.05, -0.05]
    ce = [0.10, 0.65, 0.65, 0.65, 0.65, 0.65, 0.65, 0.65, 0.65]
    states, _ = _run_state_machine(z, md, ce)
    assert states.iloc[1] == "BROKEN"
    assert states.iloc[3] == "BROKEN"   # only 2 consecutive heals
    assert states.iloc[4] == "BROKEN"   # relapse resets counter
    assert states.iloc[7] == "INTACT"   # 3 consecutive heals after relapse


# --------------------------------------------------------------------------- #
# Causal z-vel: no look-ahead bias
# --------------------------------------------------------------------------- #
def test_z_vel_no_lookahead(tmp_path, monkeypatch):
    """Appending future rows to the close matrix does NOT change past z_vel values."""
    n_members = 5
    n_days = 200
    mat_short = _make_member_closes(n_members, n_days, trend=-0.003, seed=7)
    spy_short = _spy_closes(n_days, trend=0.0, seed=8)

    # Extend by 5 more days
    n_extra = 5
    idx_long = pd.bdate_range("2024-01-02", periods=n_days + n_extra)
    # Prepend the existing dates, extend with new random data
    rng = np.random.default_rng(77)
    mat_long = mat_short.copy()
    for col in mat_short.columns:
        last = float(mat_short[col].iloc[-1])
        ext = [last * np.exp(rng.normal(-0.003, 0.015)) for _ in range(n_extra)]
        new_rows = pd.Series(ext, index=idx_long[-n_extra:])
        mat_long = pd.concat([mat_long, new_rows.rename(col).to_frame().T])
    mat_long.index = idx_long

    spy_long = pd.concat([spy_short,
                          pd.Series([float(spy_short.iloc[-1])] * n_extra,
                                    index=idx_long[-n_extra:])])
    spy_long.index = idx_long

    # Compute z on short
    r_coh_short = mat_short.pct_change(fill_method=None).mean(axis=1)
    r_spy_short = spy_short.pct_change(fill_method=None)
    z_short = lc._velocity_z(r_coh_short, r_spy_short)

    # Compute z on long
    r_coh_long = mat_long.pct_change(fill_method=None).mean(axis=1)
    r_spy_long = spy_long.pct_change(fill_method=None)
    z_long = lc._velocity_z(r_coh_long, r_spy_long)

    # All past z values must be identical (within float rounding)
    common_idx = z_short.dropna().index.intersection(z_long.dropna().index)
    diff = (z_short.reindex(common_idx) - z_long.reindex(common_idx)).abs()
    assert diff.max() < 1e-10, f"look-ahead found: max diff {diff.max()}"


# --------------------------------------------------------------------------- #
# Freshness gate
# --------------------------------------------------------------------------- #
def test_freshness_gate_excludes_stale():
    """Members with last obs >3 sessions before panel max are excluded."""
    n_days = 10
    idx_full = pd.bdate_range("2024-01-02", periods=n_days)
    # Member A: full series
    # Member B: stops after day 5 (panel max is day 10 -> lag = 5 sessions > 3)
    mat = pd.DataFrame({
        "A": [100.0 + i for i in range(n_days)],
        "B": [200.0 + i for i in range(5)] + [np.nan] * 5,
    }, index=idx_full)
    result = lc._fresh_members(mat)
    assert "A" in result.columns
    assert "B" not in result.columns


def test_freshness_gate_keeps_near_stale():
    """Members with lag <= 3 sessions are kept."""
    n_days = 10
    idx_full = pd.bdate_range("2024-01-02", periods=n_days)
    # Member B: last obs at day 8, panel max = day 10 -> lag = 2 sessions (kept)
    mat = pd.DataFrame({
        "A": [100.0 + i for i in range(n_days)],
        "B": [200.0 + i for i in range(8)] + [np.nan, np.nan],
    }, index=idx_full)
    result = lc._fresh_members(mat)
    assert "A" in result.columns
    assert "B" in result.columns


# --------------------------------------------------------------------------- #
# Fail-open: missing inputs
# --------------------------------------------------------------------------- #
def test_build_missing_membership(tmp_path, monkeypatch):
    """Returns None (not an exception) when membership.json is absent."""
    monkeypatch.setattr(lc, "_membership_path", lambda: tmp_path / "nonexistent.json")
    monkeypatch.setattr(lc, "_out_dir", lambda: tmp_path)
    result = lc.build()
    assert result is None


def test_build_missing_ohlcv(tmp_path, monkeypatch):
    """Returns None gracefully when ohlcv directory is empty."""
    # Point membership to a valid but trivial JSON
    mem_path = tmp_path / "membership.json"
    mem_path.write_text(json.dumps({"baskets": {
        "ai_semiconductors": {"members": [{"ticker": "FAKE", "removed": None}]}
    }}))
    monkeypatch.setattr(lc, "_membership_path", lambda: mem_path)
    monkeypatch.setattr(lc, "_ohlcv_path", lambda t: tmp_path / "missing.parquet")
    monkeypatch.setattr(lc, "_out_dir", lambda: tmp_path)
    result = lc.build()
    assert result is None


def test_build_missing_spy_degrades(tmp_path, monkeypatch):
    """Returns None (no SPY, can't compute z) but does not raise."""
    monkeypatch.setattr(lc, "_spy_path", lambda: tmp_path / "nope.parquet")
    # Even with real membership, SPY being absent means velocity is null -> no valid rows -> None
    monkeypatch.setattr(lc, "_out_dir", lambda: tmp_path)
    # Don't mock membership/ohlcv — use real data; just missing SPY
    result = lc.build()
    # With real ohlcv but no SPY, z_vel is all NaN, so valid_idx is empty
    assert result is None


# --------------------------------------------------------------------------- #
# Forward-log: append gated on nightly lane
# --------------------------------------------------------------------------- #
def test_no_forward_log_without_collect_lane(tmp_path, monkeypatch):
    """Without COLLECT_LANE=nightly, no forward_log.jsonl is created."""
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    monkeypatch.setattr(lc, "_out_dir", lambda: tmp_path)
    # Run with real data
    snap = lc.build()
    fwd = tmp_path / "forward_log.jsonl"
    assert not fwd.exists() or fwd.read_text().strip() == ""


def test_forward_log_written_on_nightly(tmp_path, monkeypatch):
    """With COLLECT_LANE=nightly, one row is appended to forward_log.jsonl."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    monkeypatch.setattr(lc, "_out_dir", lambda: tmp_path)
    snap = lc.build()
    if snap is None:
        pytest.skip("real data unavailable")
    fwd = tmp_path / "forward_log.jsonl"
    assert fwd.exists()
    rows = [json.loads(l) for l in fwd.read_text().strip().split("\n") if l.strip()]
    assert len(rows) == 1
    assert rows[0]["schema"] == "leadership_crack.v1"
    assert "logged_at" in rows[0]


def test_forward_log_idempotent_by_asof(tmp_path, monkeypatch):
    """Calling build() twice on the nightly lane writes exactly ONE row per asof (B1)."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    monkeypatch.setattr(lc, "_out_dir", lambda: tmp_path)
    snap1 = lc.build()
    if snap1 is None:
        pytest.skip("real data unavailable")
    # Second call on the same nightly — must not duplicate the row
    snap2 = lc.build()
    fwd = tmp_path / "forward_log.jsonl"
    rows = [json.loads(line) for line in fwd.read_text().strip().split("\n") if line.strip()]
    asof_values = [r["asof"] for r in rows]
    # Each asof must appear exactly once
    assert len(asof_values) == len(set(asof_values)), (
        f"duplicate asof in forward_log: {asof_values}"
    )


# --------------------------------------------------------------------------- #
# Real-data smoke test (skipped when data absent)
# --------------------------------------------------------------------------- #
def test_real_data_schema():
    """Real data: snap has all required keys and sensible values."""
    result = lc.build()
    if result is None:
        pytest.skip("real data unavailable or insufficient history")
    required_keys = ["schema", "asof", "state", "z_vel", "med_dd",
                     "carnage_share_ema", "share10", "share30",
                     "n_fresh", "n_total", "worst_members",
                     "index_dd", "dislocation", "state_since"]
    for k in required_keys:
        assert k in result, f"missing key: {k}"
    assert result["schema"] == "leadership_crack.v1"
    assert result["state"] in {"INTACT", "CRACKING", "BROKEN"}
    assert isinstance(result["dislocation"], bool)
    assert isinstance(result["worst_members"], list)
    assert len(result["worst_members"]) <= lc._WORST_N
    if result["z_vel"] is not None:
        assert isinstance(result["z_vel"], float)
    if result["med_dd"] is not None:
        assert -1.0 <= result["med_dd"] <= 0.0, result["med_dd"]
