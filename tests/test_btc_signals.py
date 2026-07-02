"""Bitcoin Vector signal-engine tests on synthetic price paths — no network.

Run: .venv/bin/python -m tests.test_btc_signals
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import btc_overrides as OV  # noqa: E402
from engine import btc_signals as S  # noqa: E402
from lib import config  # noqa: E402


def _synthetic(n=600, trend=0.002, vol=0.02, seed=1) -> dict:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    rets = rng.normal(trend, vol, n)
    close = pd.Series(100 * np.exp(np.cumsum(rets)), index=idx)
    px = pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                       "close": close, "volume": rng.uniform(1, 2, n)}, index=idx)
    return {"price": px, "hourly": None, "intraday_vol": None}


def test_momentum_bounds_and_direction() -> None:
    cfg = config.load()["vector"]["momentum"]
    up = S.momentum(_synthetic(trend=0.004, seed=2), cfg)
    dn = S.momentum(_synthetic(trend=-0.004, seed=3), cfg)
    assert up["momentum"].between(-1, 1).all()
    assert up["momentum"].tail(60).mean() > 0.3   # sustained uptrend -> bullish
    assert dn["momentum"].tail(60).mean() < -0.3  # sustained downtrend -> bearish


def test_risk_index_range_and_regime() -> None:
    inp = _synthetic(trend=-0.006, seed=4)
    mom = S.momentum(inp, config.load()["vector"]["momentum"])["momentum"]
    rk = S.risk(inp, mom, config.load()["vector"]["risk"])
    assert rk["risk_index"].dropna().between(0, 100).all()
    assert rk["risk_oscillator"].dropna().between(0, 1).all()
    assert set(rk["risk_regime"].unique()) <= {"high_risk", "low_risk"}


def test_hysteresis_reduces_flips() -> None:
    # a score that dithers right around the trigger should NOT flip every bar
    idx = pd.date_range("2021-01-01", periods=200, freq="D")
    rng = np.random.default_rng(5)
    score = pd.Series(0.5 + rng.normal(0, 0.05, 200), index=idx)  # hovering at +0.5
    naive = pd.Series(np.where(score > 0.5, "bull", "neutral"), index=idx)
    hyst = S._hysteresis_tri(score, 0.5, 0.25)
    naive_flips = (naive != naive.shift()).sum()
    hyst_flips = (hyst != hyst.shift()).sum()
    assert hyst_flips < naive_flips


def test_allocation_base_grid_preserved() -> None:
    # with Point-4 sizing OFF the base grid is exactly the legacy {0, 0.5, 1.0} steps —
    # conviction/brake are layered ON TOP of this, never replacing it.
    cfg = {**config.load()["vector"]["allocation"],
           "conviction_sizing": False, "drawdown_brake": False}
    n = 400
    mom = pd.Series(np.linspace(-1, 1, n), index=pd.date_range("2021-01-01", periods=n))
    risk = pd.Series(np.linspace(80, 0, n), index=mom.index)
    al = S.allocation(mom, risk, cfg)
    for c in al.columns:
        assert set(al[c].dropna().unique()) <= {0.0, 0.5, 1.0}


def test_conviction_multiplier_monotone_in_tier() -> None:
    # the size multiplier must be MONOTONE in conviction: EDGE >= LEAN >= TOSS-UP,
    # and continuous (non-decreasing) in the underlying directional-confidence score.
    cfg = config.load()["vector"]["allocation"]
    floor = float(cfg.get("conviction_floor", 0.5))
    scores = np.linspace(0.5, 1.0, 200)
    mult = S.conviction_multiplier(scores, cfg)
    assert np.all((mult >= floor - 1e-9) & (mult <= 1.0 + 1e-9))   # bounded [floor, 1]
    assert np.all(np.diff(mult) >= -1e-12)                          # monotone non-decreasing
    # one representative score per tier -> strictly ordered multipliers
    toss = 0.5 + cfg.get("conviction_toss", 0.05) / 2              # inside TOSS-UP band
    lean = 0.5 + (cfg.get("conviction_toss", 0.05) + cfg.get("conviction_edge", 0.30)) / 2
    edge = 0.5 + cfg.get("conviction_edge", 0.30) + 0.05          # past EDGE band
    assert S.conviction_tier(toss, cfg) == "TOSS-UP"
    assert S.conviction_tier(lean, cfg) == "LEAN"
    assert S.conviction_tier(edge, cfg) == "EDGE"
    m_toss = S.conviction_multiplier(toss, cfg)
    m_lean = S.conviction_multiplier(lean, cfg)
    m_edge = S.conviction_multiplier(edge, cfg)
    assert m_toss < m_lean < m_edge
    assert abs(m_toss - floor) < 1e-9 and abs(m_edge - 1.0) < 1e-9  # TOSS-UP=floor, EDGE=full


def test_drawdown_brake_reduces_exposure_when_underwater() -> None:
    # a flat-1.0 allocation through a rising-then-crashing path: the brake leaves
    # exposure untouched while at a high-water mark, then tightens once underwater.
    cfg = config.load()["vector"]["allocation"]
    floor = float(cfg.get("dd_floor", 0.30))
    n = 120
    idx = pd.date_range("2021-01-01", periods=n)
    alloc = pd.Series(1.0, index=idx)
    rets = np.concatenate([np.full(50, 0.01), np.full(n - 50, -0.03)])  # rally, then bleed
    ret = pd.Series(rets, index=idx)
    braked = S.drawdown_brake(alloc, ret, cfg)
    assert braked.between(0.0, 1.0).all()
    assert (braked <= alloc + 1e-12).all()                # never adds exposure
    assert np.allclose(braked.iloc[:50].values, 1.0)      # no brake at the high-water mark
    assert braked.iloc[-1] < 1.0                          # tightened while deep underwater
    assert braked.min() >= floor - 1e-9                   # never below the configured floor
    assert braked.iloc[-1] <= braked.iloc[60]             # tightens as drawdown deepens


def test_allocation_conviction_and_brake_unit_range() -> None:
    # the full path (grid -> conviction -> brake) stays in [0,1] AND actually produces
    # CONTINUOUS sizes (a thin setup no longer sizes the same as a strong one).
    cfg = config.load()["vector"]["allocation"]
    inp = _synthetic(n=500, trend=0.003, seed=11)
    close = inp["price"]["close"]
    mom = S.momentum(inp, config.load()["vector"]["momentum"])["momentum"]
    risk = S.risk(inp, mom, config.load()["vector"]["risk"])["risk_index"]
    al = S.allocation(mom, risk, cfg, close=close)
    for c in al.columns:
        col = al[c].dropna()
        assert col.between(0.0, 1.0).all()
        # sizing is no longer pinned to the three legacy steps
        assert not set(col.round(6).unique()) <= {0.0, 0.5, 1.0}


def _flat_inputs(start, end, price=100.0):
    idx = pd.date_range(start, end, freq="D")
    close = pd.Series(float(price), index=idx)
    return {"price": pd.DataFrame({"close": close}, index=idx)}


def test_cycle_phase_clock_phase_and_projection() -> None:
    cfg = {"bottoms": ["2019-06-01", "2023-06-01"], "tops": ["2021-06-01"],
           "up_days": 730, "down_days": 365, "overdue_pct": 1.10}
    out = S.cycle_phase_clock(_flat_inputs("2019-01-01", "2024-01-01"), cfg)
    up = out.loc["2020-06-01"]
    assert up["cphase_phase"] == "markup" and up["cphase_next_kind"] == "top"
    # next pivot == anchor + leg length (deterministic projection)
    assert up["cphase_next_pivot"] == (pd.Timestamp("2019-06-01")
                                       + pd.Timedelta(days=730)).strftime("%Y-%m-%d")
    dn = out.loc["2022-01-01"]
    assert dn["cphase_phase"] == "markdown" and dn["cphase_next_kind"] == "bottom"
    # before the first anchor -> no phase (PIT: nothing has happened yet)
    assert pd.isna(out.loc["2019-03-01"]["cphase_phase"])
    # pct & days_left are internally consistent
    assert abs(up["cphase_days_in"] + up["cphase_days_left"] - up["cphase_len"]) < 1e-6


def test_cycle_phase_clock_status_invalidation_and_overdue() -> None:
    # markdown that prints a NEW HIGH above the anchor top -> invalidated
    inv = _flat_inputs("2021-01-01", "2022-12-31")
    inv["price"].loc["2022-01-01":, "close"] = 150.0     # > the 100 "top" price
    cfg = {"bottoms": ["2020-01-01"], "tops": ["2021-06-01"],
           "up_days": 500, "down_days": 365, "overdue_pct": 1.10}
    out = S.cycle_phase_clock(inv, cfg)
    assert out.loc["2022-06-01"]["cphase_status"] == "invalidated"
    assert out.loc["2021-09-01"]["cphase_status"] == "on_track"
    # a markup that runs far past its window with no new pivot -> overdue
    ov = _flat_inputs("2021-01-01", "2023-12-31")
    cfg2 = {"bottoms": ["2021-02-01"], "tops": [], "up_days": 300, "down_days": 364,
            "overdue_pct": 1.10}
    out2 = S.cycle_phase_clock(ov, cfg2)
    assert out2.loc["2023-06-01"]["cphase_status"] == "overdue"
    assert out2.loc["2021-06-01"]["cphase_status"] == "on_track"


def test_cycle_phase_clock_config_locks_1064_364() -> None:
    # regression lock on the accuracy claim: the shipped anchors must reproduce the
    # measured 1064/364 fit (up within 15d, down within 20d — the weaker leg).
    cfg = config.load()["vector"]["cycle_phase_clock"]
    bots = [pd.Timestamp(d) for d in cfg["bottoms"]]
    tops = [pd.Timestamp(d) for d in cfg["tops"]]
    for b, t in zip(bots, tops):
        assert abs((t - b).days - cfg["up_days"]) <= 15
    for t, b in zip(tops, bots[1:]):
        assert abs((b - t).days - cfg["down_days"]) <= 20


def test_cycle_phase_clock_no_lookahead() -> None:
    inp = _flat_inputs("2019-01-01", "2024-01-01")
    inp["price"]["close"] = np.linspace(100, 200, len(inp["price"]))
    cfg = {"bottoms": ["2019-06-01", "2023-06-01"], "tops": ["2021-06-01"],
           "up_days": 730, "down_days": 365, "overdue_pct": 1.10}
    full = S.cycle_phase_clock(inp, cfg)
    trunc = S.cycle_phase_clock({"price": inp["price"].loc[:"2022-01-01"]}, cfg)
    overlap = trunc.index
    assert (full.loc[overlap, "cphase_phase"].fillna("X")
            == trunc["cphase_phase"].fillna("X")).all()


def test_no_lookahead_smoke() -> None:
    # truncating the series must not change earlier signal values
    inp = _synthetic(n=500, seed=6)
    cfg = config.load()["vector"]["momentum"]
    full = S.momentum(inp, cfg)["momentum"]
    trunc_inp = {"price": inp["price"].iloc[:400], "hourly": None, "intraday_vol": None}
    trunc = S.momentum(trunc_inp, cfg)["momentum"]
    # EMA is causal -> overlapping region should match closely
    overlap = full.iloc[100:390]
    assert np.allclose(overlap.values, trunc.reindex(overlap.index).values, atol=1e-6)


def test_us_election_date() -> None:
    # first Tuesday AFTER the first Monday of November
    assert S._us_election_date(2014) == pd.Timestamp("2014-11-04")
    assert S._us_election_date(2018) == pd.Timestamp("2018-11-06")
    assert S._us_election_date(2022) == pd.Timestamp("2022-11-08")
    assert S._us_election_date(2026) == pd.Timestamp("2026-11-03")
    assert S._us_election_date(2030) == pd.Timestamp("2030-11-05")


def test_midterm_blackout_windows() -> None:
    idx = pd.date_range("2021-01-01", "2027-12-31", freq="D")
    g = S.midterm_blackout(idx, {"enabled": True})
    # 2022 midterm year: blackout from Jan 1 until the Nov 8 vote, then clear
    assert g.loc["2022-01-01"] and g.loc["2022-06-30"] and g.loc["2022-11-07"]
    assert not g.loc["2022-11-08"] and not g.loc["2022-12-31"]
    # 2026 midterm year: blackout until the Nov 3 vote
    assert g.loc["2026-01-01"] and g.loc["2026-10-31"]
    assert not g.loc["2026-11-03"] and not g.loc["2026-11-04"]
    # non-midterm years are never gated (2021 odd, 2024 presidential, 2023/2025/2027)
    for y in ("2021", "2023", "2024", "2025", "2027"):
        assert not g.loc[y].any()
    # disabled / missing config -> never gated
    assert not S.midterm_blackout(idx, {"enabled": False}).any()
    assert not S.midterm_blackout(idx, None).any()
    # buy_lead_days releases the gate earlier
    g14 = S.midterm_blackout(idx, {"enabled": True, "buy_lead_days": 14})
    assert not g14.loc["2022-10-26"] and g.loc["2022-10-26"]


def test_allocation_midterm_gate_forces_flat() -> None:
    # W0 REWRITE: allocation() is now PURE ENGINE — it no longer applies the gate.
    # This test now exercises btc_overrides.apply(), which is where the gate lives.
    # Verifies: final alloc_* forced 0.0 in the blackout window, *_raw columns are
    # NOT zeroed, and override_active / override_id are correct.
    idx = pd.date_range("2022-01-01", "2023-06-30", freq="D")
    mom = pd.Series(1.0, index=idx)
    risk = pd.Series(0.0, index=idx)
    base = {**config.load()["vector"]["allocation"],
            "conviction_sizing": False, "drawdown_brake": False, "bottom_overlay": False,
            "midterm_gate": {"enabled": False}}   # allocation() sees no gate
    pure = S.allocation(mom, risk, base)

    # pure engine output must be fully invested the whole window (strong mom, zero risk)
    assert (pure["alloc_optimal"] > 0).all(), "pure allocation should be > 0 everywhere"

    # apply the override via btc_overrides.apply
    acfg = {**base, "midterm_gate": {"enabled": True}}
    result = OV.apply(pure, acfg)

    # final (gated): flat through the blackout, invested again after the Nov 8 2022 vote
    assert result["alloc_optimal"].loc["2022-01-01":"2022-11-07"].eq(0.0).all(), \
        "final alloc_optimal must be 0 during the 2022 blackout"
    assert (result["alloc_optimal"].loc["2022-11-08":] > 0).all(), \
        "final alloc_optimal must be > 0 after the 2022 vote"

    # _raw columns must NOT be zeroed — they carry the pure engine output
    assert (result["alloc_optimal_raw"] > 0).all(), \
        "alloc_optimal_raw must remain > 0 (pure engine, not suppressed)"

    # override_active must be True in the window, False after
    assert result["override_active"].loc["2022-01-01":"2022-11-07"].all(), \
        "override_active must be True inside the 2022 blackout"
    assert not result["override_active"].loc["2022-11-08":].any(), \
        "override_active must be False after the 2022 vote"

    # override_id must name 'midterm_blackout' inside the window
    assert (result["override_id"].loc["2022-01-01":"2022-11-07"] == "midterm_blackout").all()
    assert (result["override_id"].loc["2022-11-08":] == "").all()

    # the gate applies to every variant, not just optimal
    alloc_cols = [c for c in result.columns if c.startswith("alloc_") and not c.endswith("_raw")]
    for c in alloc_cols:
        assert result[c].loc["2022-06-01":"2022-10-31"].eq(0.0).all(), \
            f"{c} must be 0 in mid-blackout window"


if __name__ == "__main__":
    for fn in [test_momentum_bounds_and_direction, test_risk_index_range_and_regime,
               test_hysteresis_reduces_flips, test_allocation_base_grid_preserved,
               test_conviction_multiplier_monotone_in_tier,
               test_drawdown_brake_reduces_exposure_when_underwater,
               test_allocation_conviction_and_brake_unit_range,
               test_cycle_phase_clock_phase_and_projection,
               test_cycle_phase_clock_status_invalidation_and_overdue,
               test_cycle_phase_clock_config_locks_1064_364,
               test_cycle_phase_clock_no_lookahead,
               test_us_election_date,
               test_midterm_blackout_windows,
               test_allocation_midterm_gate_forces_flat,
               test_no_lookahead_smoke]:
        fn()
        print(f"PASS {fn.__name__}")
    print("all btc signal tests passed")
