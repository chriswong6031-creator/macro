"""Commodity Index + Breadth Engine tests — deterministic, no network.

Run: python -m pytest tests/test_commodity_index.py -q
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.commodity_index import build_index, price_shock  # noqa: E402
from lib import config  # noqa: E402

CFG = config.load()["commodities"]


@pytest.fixture(autouse=True)
def _isolate_signals_store(tmp_path, monkeypatch):
    """build_index persists signals_index.parquet via config.data_dir() on every
    call — unredirected it REWRITES (truncates) the real
    data/commodity/signals_index.parquet with the synthetic fixture frame."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path / "data")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _make_close(n: int = 800, trend: float = 0.0002, vol: float = 0.012,
                seed: int = 1, start: str = "2015-01-01") -> pd.Series:
    """Synthetic daily close series on a business-day DatetimeIndex."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n, freq="B")
    close = pd.Series(
        100 * np.exp(np.cumsum(rng.normal(trend, vol, n))),
        index=idx,
        name="close",
    )
    return close


def _make_member_frame(
    n: int = 800,
    trend: float = 0.0002,
    vol: float = 0.012,
    seed: int = 1,
    ts_trend_val: str = "up",
    momentum_state_val: str = "bull",
    risk_regime_val: str = "low_risk",
    start: str = "2015-01-01",
) -> pd.DataFrame:
    """Synthetic member DataFrame with all columns needed by build_index breadth logic."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n, freq="B")
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(trend, vol, n))), index=idx)
    ts_mom = np.tanh(close.pct_change(252) / 0.3).clip(-1, 1)
    return pd.DataFrame({
        "close": close,
        "ts_trend": ts_trend_val,
        "ts_momentum": ts_mom,
        "momentum_state": momentum_state_val,
        "risk_regime": risk_regime_val,
        "risk_index": rng.uniform(10, 40, n),
        "cycle_position": rng.uniform(0.3, 0.7, n),
    }, index=idx)


def _make_member_results(
    n_members: int = 8,
    n: int = 800,
    ts_trend_val: str = "up",
    momentum_state_val: str = "bull",
    risk_regime_val: str = "low_risk",
) -> dict[str, pd.DataFrame]:
    """Create n_members synthetic member frames with the same start date."""
    out = {}
    for i in range(n_members):
        out[f"member_{i}"] = _make_member_frame(
            n=n, seed=i + 10,
            ts_trend_val=ts_trend_val,
            momentum_state_val=momentum_state_val,
            risk_regime_val=risk_regime_val,
        )
    return out


# --------------------------------------------------------------------------- #
# price_shock tests
# --------------------------------------------------------------------------- #
def test_price_shock_columns() -> None:
    close = _make_close(n=500)
    out = price_shock(close, CFG["index"]["price_shock"])
    assert "shock_z_price" in out.columns
    assert "shock_state_price" in out.columns


def test_price_shock_washout() -> None:
    """A large negative return must be flagged as 'washout'."""
    close = _make_close(n=500, vol=0.005, trend=0.0)
    # inject a large drop at the end
    close_crash = close.copy()
    close_crash.iloc[-1] = close_crash.iloc[-22] * 0.75  # -25% 21d return
    cfg_ps = {"return_window_d": 21, "z_lookback_d": 252, "shock_z": 1.0}
    out = price_shock(close_crash, cfg_ps)
    tail = out["shock_state_price"].dropna().tail(5)
    assert (tail == "washout").any(), f"Expected washout, got: {tail.tolist()}"


def test_price_shock_blowoff() -> None:
    """A large positive return must be flagged as 'blowoff'."""
    close = _make_close(n=500, vol=0.005, trend=0.0)
    close_surge = close.copy()
    close_surge.iloc[-1] = close_surge.iloc[-22] * 1.35  # +35% 21d return
    cfg_ps = {"return_window_d": 21, "z_lookback_d": 252, "shock_z": 1.0}
    out = price_shock(close_surge, cfg_ps)
    tail = out["shock_state_price"].dropna().tail(5)
    assert (tail == "blowoff").any(), f"Expected blowoff, got: {tail.tolist()}"


def test_price_shock_normal_states() -> None:
    """Middle-of-the-road returns must produce 'normal' states."""
    close = _make_close(n=600, vol=0.005, trend=0.0)
    out = price_shock(close, CFG["index"]["price_shock"])
    states = set(out["shock_state_price"].dropna().unique())
    assert states <= {"washout", "blowoff", "normal"}
    # most should be normal for a low-vol series
    normal_frac = (out["shock_state_price"] == "normal").sum() / out["shock_state_price"].notna().sum()
    assert normal_frac > 0.5


def test_price_shock_no_lookahead() -> None:
    """Truncating the series must not change earlier shock_z values."""
    close = _make_close(n=600)
    cfg_ps = {"return_window_d": 21, "z_lookback_d": 252, "shock_z": 1.75}
    full = price_shock(close, cfg_ps)
    trunc = price_shock(close.iloc[:500], cfg_ps)
    overlap = full["shock_z_price"].iloc[50:490].dropna()
    trunc_vals = trunc["shock_z_price"].reindex(overlap.index)
    np.testing.assert_allclose(overlap.values, trunc_vals.values, rtol=1e-9)


# --------------------------------------------------------------------------- #
# build_index: composite arithmetic tests
# --------------------------------------------------------------------------- #
def test_composite_nan_before_min_members() -> None:
    """idx_ew must be NaN on dates where fewer than rebase_min_members members have data."""
    min_m = CFG["index"]["rebase_min_members"]
    # create members that START on different dates: first min_m-1 members start
    # 200 days LATER than the others — so in the first ~200 bars only a few are present
    early_start = "2015-01-01"
    late_start = "2015-10-01"  # ~190 business days later

    member_results = {}
    # 3 members with early start
    for i in range(3):
        member_results[f"early_{i}"] = _make_member_frame(n=800, seed=i, start=early_start)

    # enough late members to push total above min_m after late_start
    for i in range(min_m):
        member_results[f"late_{i}"] = _make_member_frame(n=600, seed=i + 20, start=late_start)

    snap = build_index(member_results, {}, CFG)
    assert snap != {}, "build_index returned empty unexpectedly"

    # Reload the persisted parquet to check idx_ew NaN structure
    parquet_path = config.data_dir() / "commodity" / "signals_index.parquet"
    assert parquet_path.exists(), "build_index should persist signals_index.parquet"
    df = pd.read_parquet(parquet_path)
    early_rows = df.loc[df.index < pd.Timestamp(late_start), "idx_ew"]
    # Only 3 early members present before late_start (< rebase_min_members) -> the
    # composite is not yet published, so idx_ew must be entirely NaN there.
    assert early_rows.isna().all(), \
        f"idx_ew must be NaN before roster maturity; got {int(early_rows.notna().sum())} non-NaN"


def test_composite_numeric_when_enough_members() -> None:
    """idx_ew must be a finite number when >= rebase_min_members are present."""
    member_results = _make_member_results(n_members=10, n=800)
    snap = build_index(member_results, {}, CFG)
    assert snap != {}
    ew = snap["index"]["ew"]
    assert ew is not None and math.isfinite(ew), f"idx_ew={ew} is not finite"


# --------------------------------------------------------------------------- #
# build_index: breadth counts
# --------------------------------------------------------------------------- #
def test_breadth_counts_match_inputs() -> None:
    """6-of-10 members with ts_trend='up' -> n_up_trend=6, pct_up_trend=0.6.

    We use 10 members (>= rebase_min_members=6) to ensure the composite is not
    masked as NaN.  6 are 'up'/'bull'/'low_risk', 4 are 'down'/'bear'/'high_risk'.
    """
    member_results: dict[str, pd.DataFrame] = {}
    n_up = 6
    n_dn = 4
    for i in range(n_up):
        member_results[f"up_{i}"] = _make_member_frame(
            n=800, seed=i, ts_trend_val="up", momentum_state_val="bull", risk_regime_val="low_risk"
        )
    for i in range(n_dn):
        member_results[f"dn_{i}"] = _make_member_frame(
            n=800, seed=i + 50, ts_trend_val="down", momentum_state_val="bear", risk_regime_val="high_risk"
        )

    snap = build_index(member_results, {}, CFG)
    assert snap != {}
    b = snap["breadth"]
    assert b["n_up_trend"] == n_up, f"n_up_trend={b['n_up_trend']}"
    assert b["n_members"] == n_up + n_dn, f"n_members={b['n_members']}"
    assert abs(b["pct_up_trend"] - n_up / (n_up + n_dn)) < 0.01, f"pct_up_trend={b['pct_up_trend']}"
    assert b["n_bull_momentum"] == n_up, f"n_bull_momentum={b['n_bull_momentum']}"
    assert b["n_low_risk"] == n_up, f"n_low_risk={b['n_low_risk']}"


def test_breadth_all_bull() -> None:
    """All members up -> pct_up_trend == 1.0."""
    member_results = _make_member_results(n_members=8, ts_trend_val="up", momentum_state_val="bull")
    snap = build_index(member_results, {}, CFG)
    b = snap["breadth"]
    assert b["n_up_trend"] == b["n_members"]
    assert abs(b["pct_up_trend"] - 1.0) < 0.01


def test_breadth_all_bear() -> None:
    """All members down -> n_up_trend == 0."""
    member_results = _make_member_results(n_members=8, ts_trend_val="down", momentum_state_val="bear",
                                          risk_regime_val="high_risk")
    snap = build_index(member_results, {}, CFG)
    b = snap["breadth"]
    assert b["n_up_trend"] == 0
    assert b["n_bull_momentum"] == 0
    assert b["n_low_risk"] == 0


# --------------------------------------------------------------------------- #
# build_index: robustness / never-raises
# --------------------------------------------------------------------------- #
def test_build_index_empty_returns_empty() -> None:
    """Empty member_results must return {} without raising."""
    result = build_index({}, {}, CFG)
    assert result == {}


def test_build_index_below_min_members_returns_empty() -> None:
    """Fewer than rebase_min_members members with close data -> empty {}."""
    min_m = CFG["index"]["rebase_min_members"]
    member_results = _make_member_results(n_members=max(1, min_m - 1))
    result = build_index(member_results, {}, CFG)
    assert result == {}


def test_build_index_degenerate_constant_close() -> None:
    """Constant close (zero vol) must not raise."""
    frames = {}
    idx = pd.date_range("2015-01-01", periods=600, freq="B")
    for i in range(8):
        frames[f"flat_{i}"] = pd.DataFrame({
            "close": pd.Series(100.0, index=idx),
            "ts_trend": "flat",
            "ts_momentum": 0.0,
            "momentum_state": "neutral",
            "risk_regime": "low_risk",
            "risk_index": 20.0,
            "cycle_position": 0.5,
        })
    result = build_index(frames, {}, CFG)
    # may return {} or a partial snapshot — must not raise
    assert isinstance(result, dict)


def test_build_index_single_date_member() -> None:
    """Member with only 1 data point must not raise."""
    member_results = _make_member_results(n_members=8, n=800)
    # add a degenerate 1-row member
    idx1 = pd.DatetimeIndex(["2022-01-03"])
    member_results["tiny"] = pd.DataFrame({
        "close": [100.0],
        "ts_trend": ["up"],
        "ts_momentum": [0.5],
        "momentum_state": ["bull"],
        "risk_regime": ["low_risk"],
        "risk_index": [25.0],
        "cycle_position": [0.5],
    }, index=idx1)
    result = build_index(member_results, {}, CFG)
    assert isinstance(result, dict)


# --------------------------------------------------------------------------- #
# build_index: JSON serialisability
# --------------------------------------------------------------------------- #
def test_snapshot_json_serializable() -> None:
    """json.dumps(snapshot) must succeed — no numpy scalars, no NaN."""
    member_results = _make_member_results(n_members=10, n=800)
    snap = build_index(member_results, {}, CFG)
    assert snap != {}
    # Must not raise
    encoded = json.dumps(snap)
    assert len(encoded) > 10


def test_snapshot_members_sorted_by_class_then_name() -> None:
    """Members are ordered by class (precious<industrial<energy<grain<soft<
    livestock) then name. Uses REAL complex_members names so each carries its
    config class (synthetic member_N names all map to class '' and can't test order)."""
    complex_m = config.load()["commodities"].get("complex_members", {})
    if len(complex_m) < 6:
        pytest.skip("complex_members config not available")
    # a scattered subset spanning several classes, deliberately name-unsorted
    picks = [n for n in ("cotton", "gold", "natgas", "corn", "copper", "sugar", "silver")
             if n in complex_m]
    member_results = {n: _make_member_frame(n=800, seed=i) for i, n in enumerate(picks)}
    snap = build_index(member_results, {}, CFG)
    assert snap != {}
    class_order = {"precious": 0, "industrial": 1, "energy": 2, "grain": 3, "soft": 4, "livestock": 5}
    seq = [(class_order.get(m["class"], 99), m["name"]) for m in snap["members"]]
    assert seq == sorted(seq), f"members not sorted by (class, name): {seq}"


def test_snapshot_no_nan_in_json() -> None:
    """No NaN or infinity in the JSON output (JSON spec forbids them)."""
    member_results = _make_member_results(n_members=10, n=800)
    snap = build_index(member_results, {}, CFG)
    if not snap:
        return
    encoded = json.dumps(snap)
    assert "NaN" not in encoded
    assert "Infinity" not in encoded
    assert "-Infinity" not in encoded


# --------------------------------------------------------------------------- #
# build_index: velocity
# --------------------------------------------------------------------------- #
def test_snapshot_velocity_keys() -> None:
    """Velocity sub-dict must have r5, r20, r60, r252, accel, impulse."""
    member_results = _make_member_results(n_members=10, n=800)
    snap = build_index(member_results, {}, CFG)
    assert snap != {}
    vel = snap["index"]["velocity"]
    for key in ("r5", "r20", "r60", "r252", "accel", "impulse"):
        assert key in vel, f"Missing velocity key: {key}"


def test_member_velocity_keys() -> None:
    """Each member in snapshot must have a velocity sub-dict with the same keys."""
    member_results = _make_member_results(n_members=10, n=800)
    snap = build_index(member_results, {}, CFG)
    assert snap != {}
    for m in snap["members"]:
        vel = m.get("velocity", {})
        for key in ("r5", "r20", "r60", "r252", "accel", "impulse"):
            assert key in vel, f"Member {m['name']} missing velocity.{key}"


# --------------------------------------------------------------------------- #
# build_index: benchmark handling
# --------------------------------------------------------------------------- #
def test_benchmarks_in_snapshot() -> None:
    """When benchmarks are provided, they appear in snapshot.index.benchmarks."""
    member_results = _make_member_results(n_members=10, n=800)
    dbc = _make_close(n=800, seed=99)
    gsg = _make_close(n=800, seed=100)
    snap = build_index(member_results, {"DBC": dbc, "GSG": gsg}, CFG)
    assert snap != {}
    bench = snap["index"]["benchmarks"]
    assert "DBC" in bench and "GSG" in bench
    assert bench["DBC"]["last"] is not None
    assert bench["GSG"]["last"] is not None


def test_empty_benchmarks_ok() -> None:
    """Empty benchmarks dict must not cause a failure."""
    member_results = _make_member_results(n_members=10, n=800)
    snap = build_index(member_results, {}, CFG)
    assert snap != {}
    assert snap["index"]["benchmarks"] == {}


# --------------------------------------------------------------------------- #
# commodity_inputs.load_members contract
# --------------------------------------------------------------------------- #
def test_load_members_returns_dict() -> None:
    """load_members must return a dict (possibly empty if no price stores present)."""
    from engine import commodity_inputs
    result = commodity_inputs.load_members()
    assert isinstance(result, dict)
    # all returned entries must have the required ai keys
    for name, ai in result.items():
        for key in ("asset", "class", "ticker", "price", "cot_net_pct_oi", "drivers"):
            assert key in ai, f"load_members[{name}] missing key '{key}'"
        assert ai["asset"] == name


if __name__ == "__main__":
    fns = [
        test_price_shock_columns,
        test_price_shock_washout,
        test_price_shock_blowoff,
        test_price_shock_normal_states,
        test_price_shock_no_lookahead,
        test_composite_nan_before_min_members,
        test_composite_numeric_when_enough_members,
        test_breadth_counts_match_inputs,
        test_breadth_all_bull,
        test_breadth_all_bear,
        test_build_index_empty_returns_empty,
        test_build_index_below_min_members_returns_empty,
        test_build_index_degenerate_constant_close,
        test_build_index_single_date_member,
        test_snapshot_json_serializable,
        test_snapshot_members_sorted_by_class_then_name,
        test_snapshot_no_nan_in_json,
        test_snapshot_velocity_keys,
        test_member_velocity_keys,
        test_benchmarks_in_snapshot,
        test_empty_benchmarks_ok,
        test_load_members_returns_dict,
    ]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print("all commodity index tests passed")
