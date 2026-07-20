"""Tests for the Prophet × Stage-Analysis fusion harness (engine.prophet_stage_fusion).

Coverage (>= 8, per the task contract):
  1. PIT-safety — stage_at_entry uses ONLY pre-entry data (look-ahead guard: a future
     price spike after the entry must not change the stage read at entry).
  2. PIT-safety (EC) — ec_sent_at_entry is strictly call_date < entry_date.
  3. Arm-filter correctness — A/B/B-fresh/C membership rules.
  4. Wilson-CI math — against a known reference value.
  5. Wilson-diff CI — sign + monotonicity sanity.
  6. n_dates independence — same-day fires across names count as ONE date.
  7. win = CLEAN_LIFTOFF — only CLEAN_LIFTOFF fires count as wins; STOPPED as stopped.
  8. Fail-open on absent EC parquet — arm C degrades to n=0, no crash.
  9. Regime bucketing — dates land in the right regime; out-of-range → None.
 10. Small synthetic end-to-end — assemble_results over hand-built fires.
 11. Fresh-fire = transition INTO T1/T2 (not a sustained-tier day).
 12. Late-IPO exclusion counted — a too-young name is flagged excluded, its fires drop
     from stageable arms but stay in A.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import grading, prophet_stage_fusion as psf


# --------------------------------------------------------------------------- #
# Synthetic price builders                                                     #
# --------------------------------------------------------------------------- #
def _bdays(start: str, n: int) -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=n)


def _stage2_series(n: int = 500, start: str = "2020-01-01") -> pd.Series:
    """A clean rising series that classifies Stage-2 late (close > rising 30w SMA)."""
    idx = _bdays(start, n)
    # steady uptrend with mild noise → Stage 2 advancing
    base = np.linspace(100, 300, n)
    noise = np.sin(np.arange(n) / 9.0) * 2.0
    return pd.Series(base + noise, index=idx)


def _bench_series(n: int = 600, start: str = "2019-06-01") -> pd.Series:
    idx = _bdays(start, n)
    return pd.Series(np.linspace(100, 130, n), index=idx)


# --------------------------------------------------------------------------- #
# 1. PIT-safety — the look-ahead guard on stage_at_entry                        #
# --------------------------------------------------------------------------- #
def test_pit_stage_at_entry_ignores_future():
    close = _stage2_series(500)
    bench = _bench_series(700)
    entry = close.index[400]

    st, wis, nwk = psf.stage_at_entry(close, None, bench, entry)

    # Now DETONATE the future: crash everything AFTER the entry to -90%.
    future = close.copy()
    future.loc[future.index > entry] = future.loc[future.index > entry] * 0.1
    st2, wis2, nwk2 = psf.stage_at_entry(future, None, bench, entry)

    # The stage read AT the entry must be identical — the guard truncates to <= entry.
    assert (st, wis, nwk) == (st2, wis2, nwk2), "future data leaked into the entry-date stage read"


def test_pit_stage_series_lookup_matches_truncated_classify():
    """The efficient per-fire lookup equals the audited truncating classify at the entry."""
    close = _stage2_series(500)
    bench = _bench_series(700)
    stage_ser = psf.weinstein_stage.stage_series(close, None, bench)
    entry = close.index[420]
    st_fast, wis_fast = psf._stage_lookup_from_series(stage_ser, entry)
    st_pit, wis_pit, _ = psf.stage_at_entry(close, None, bench, entry)
    assert st_fast == st_pit
    # weeks_in_stage from the two paths agree (both count the trailing run of the stage).
    assert wis_fast == wis_pit


# --------------------------------------------------------------------------- #
# 2. PIT-safety — EC join is strictly BEFORE the entry                          #
# --------------------------------------------------------------------------- #
def test_ec_strictly_before_entry():
    ec_df = pd.DataFrame({
        "ticker": ["XYZ", "XYZ", "XYZ"],
        "call_date": pd.to_datetime(["2022-01-10", "2022-04-10", "2022-07-10"]),
        "earnings_call_sent": [10.0, 26.0, 28.0],
    })
    idx = psf.ec_index(ec_df)
    # entry exactly ON the 2022-04-10 call: that call is NOT usable (strictly-before).
    v = psf.ec_sent_at_entry(idx, "XYZ", pd.Timestamp("2022-04-10"))
    assert v == 10.0, "a call printed on the entry day leaked (must be strictly before)"
    # entry one day later: the 04-10 call is now usable.
    v2 = psf.ec_sent_at_entry(idx, "XYZ", pd.Timestamp("2022-04-11"))
    assert v2 == 26.0
    # no prior call → None.
    assert psf.ec_sent_at_entry(idx, "XYZ", pd.Timestamp("2022-01-05")) is None
    # unknown ticker → None.
    assert psf.ec_sent_at_entry(idx, "NOPE", pd.Timestamp("2022-05-01")) is None


# --------------------------------------------------------------------------- #
# 3. Arm-filter correctness                                                     #
# --------------------------------------------------------------------------- #
def test_arm_filter_membership():
    d = pd.Timestamp("2023-01-05")
    # A always in; B needs stage==2; B_fresh needs stage2 ∧ weeks<=10; C needs stage2 ∧ ec>=24.
    f_s2_fresh_ec = psf.Fire("T", d, "T1/T2", stage=2, weeks_in_stage=5, ec_sent=25.0)
    f_s2_aged_ec = psf.Fire("T", d, "T1/T2", stage=2, weeks_in_stage=20, ec_sent=25.0)
    f_s2_fresh_lowec = psf.Fire("T", d, "T1/T2", stage=2, weeks_in_stage=3, ec_sent=10.0)
    f_s2_no_ec = psf.Fire("T", d, "T1/T2", stage=2, weeks_in_stage=3, ec_sent=None)
    f_s4 = psf.Fire("T", d, "T1/T2", stage=4, weeks_in_stage=3, ec_sent=28.0)

    for f in (f_s2_fresh_ec, f_s2_aged_ec, f_s2_fresh_lowec, f_s2_no_ec, f_s4):
        assert f.in_arm("A")  # arm A takes everything

    assert f_s2_fresh_ec.in_arm("B") and f_s2_fresh_ec.in_arm("B_fresh") and f_s2_fresh_ec.in_arm("C")
    assert f_s2_aged_ec.in_arm("B") and not f_s2_aged_ec.in_arm("B_fresh") and f_s2_aged_ec.in_arm("C")
    assert f_s2_fresh_lowec.in_arm("B") and f_s2_fresh_lowec.in_arm("B_fresh") and not f_s2_fresh_lowec.in_arm("C")
    assert f_s2_no_ec.in_arm("B") and not f_s2_no_ec.in_arm("C")
    assert not f_s4.in_arm("B") and not f_s4.in_arm("B_fresh") and not f_s4.in_arm("C")

    with pytest.raises(ValueError):
        f_s4.in_arm("Z")


# --------------------------------------------------------------------------- #
# 4 + 5. Wilson-CI math                                                         #
# --------------------------------------------------------------------------- #
def test_wilson_ci_reference():
    # Known reference: 5 successes of 10 → point 0.5, Wilson 95% CI ≈ [0.2366, 0.7634].
    p, lo, hi = psf.wilson_ci(5, 10)
    assert p == pytest.approx(0.5, abs=1e-9)
    assert lo == pytest.approx(0.2366, abs=1e-3)
    assert hi == pytest.approx(0.7634, abs=1e-3)
    # 0 of 0 → all None (no crash).
    assert psf.wilson_ci(0, 0) == (None, None, None)
    # 0 of 20 → lo pinned at 0, hi > 0.
    p0, lo0, hi0 = psf.wilson_ci(0, 20)
    assert p0 == 0.0 and lo0 == 0.0 and hi0 > 0.0
    # all successes → hi pinned at 1.
    p1, lo1, hi1 = psf.wilson_ci(20, 20)
    assert p1 == 1.0 and hi1 == 1.0 and lo1 < 1.0


def test_wilson_diff_ci_sign():
    # B clearly beats A (large, separated) → diff positive, lower bound > 0.
    diff, lo, hi = psf.wilson_diff_ci(succ_a=10, n_a=100, succ_b=60, n_b=100)
    assert diff == pytest.approx(0.5, abs=1e-9)
    assert lo > 0.0
    # No difference → diff 0, CI straddles 0 (lower bound <= 0).
    diff2, lo2, hi2 = psf.wilson_diff_ci(30, 100, 30, 100)
    assert diff2 == pytest.approx(0.0, abs=1e-9)
    assert lo2 <= 0.0 <= hi2
    # n==0 guard.
    assert psf.wilson_diff_ci(0, 0, 5, 10) == (None, None, None)


# --------------------------------------------------------------------------- #
# 6. n_dates independence — same-day fires across names = ONE date              #
# --------------------------------------------------------------------------- #
def _lifted(ticker, date):
    f = psf.Fire(ticker, pd.Timestamp(date), "T1/T2", stage=2, weeks_in_stage=3, ec_sent=25.0)
    f.state_15_126 = grading.TerminalState.CLEAN_LIFTOFF
    f.matured_15_126 = True
    f._liftoff_bar_clean15_126 = 30
    f.fwd = {"fwd_ret_63": 0.2, "fwd_ret_126": 0.3, "fwd_mdd_126": -0.02}
    return f


def test_n_dates_independence():
    # 4 fires but only 2 distinct calendar dates.
    fires = [
        _lifted("AAA", "2023-03-01"),
        _lifted("BBB", "2023-03-01"),   # same date as AAA
        _lifted("CCC", "2023-03-02"),
        _lifted("DDD", "2023-03-02"),   # same date as CCC
    ]
    agg = psf.aggregate_arm(fires, "A", "clean15_126")
    assert agg["n_entries"] == 4
    assert agg["n_dates"] == 2, "same-day fires across names must collapse to one independent date"


# --------------------------------------------------------------------------- #
# 7. win = CLEAN_LIFTOFF (and STOPPED counted separately)                        #
# --------------------------------------------------------------------------- #
def test_win_is_clean_liftoff_only():
    fires = []
    for i in range(3):
        f = psf.Fire(f"W{i}", pd.Timestamp(f"2023-04-0{i+1}"), "T1/T2", 2, 3, 25.0)
        f.state_15_126 = grading.TerminalState.CLEAN_LIFTOFF
        f.matured_15_126 = True
        f._liftoff_bar_clean15_126 = 40
        f.fwd = {"fwd_ret_63": 0.2, "fwd_ret_126": 0.3, "fwd_mdd_126": -0.01}
        fires.append(f)
    for i in range(2):
        f = psf.Fire(f"S{i}", pd.Timestamp(f"2023-05-0{i+1}"), "T1/T2", 2, 3, 25.0)
        f.state_15_126 = grading.TerminalState.STOPPED
        f.matured_15_126 = True
        f.fwd = {"fwd_ret_63": -0.1, "fwd_ret_126": -0.2, "fwd_mdd_126": -0.15}
        fires.append(f)
    # a CUSHIONED fire is neither a win nor a stop.
    fc = psf.Fire("CU", pd.Timestamp("2023-06-01"), "T1/T2", 2, 3, 25.0)
    fc.state_15_126 = grading.TerminalState.CUSHIONED
    fc.matured_15_126 = True
    fc.fwd = {"fwd_ret_63": 0.03, "fwd_ret_126": 0.04, "fwd_mdd_126": -0.03}
    fires.append(fc)

    agg = psf.aggregate_arm(fires, "A", "clean15_126")
    assert agg["n_entries"] == 6
    assert agg["wins"] == 3
    assert agg["win_rate"] == pytest.approx(3 / 6)
    assert agg["stopped"] == 2
    assert agg["stopped_rate"] == pytest.approx(2 / 6)
    # bars-to-liftoff median over the 3 winners (all 40).
    assert agg["median_bars_to_liftoff"] == pytest.approx(40.0)


# --------------------------------------------------------------------------- #
# 8. Fail-open on absent EC parquet                                             #
# --------------------------------------------------------------------------- #
def test_ec_absent_fail_open(tmp_path):
    missing = tmp_path / "does_not_exist.parquet"
    ec_df = psf.load_ec_table(missing)
    assert ec_df.empty
    idx = psf.ec_index(ec_df)
    assert idx == {}
    # arm C over a fire with no EC → excluded, not crashed.
    f = psf.Fire("T", pd.Timestamp("2023-01-01"), "T1/T2", stage=2, weeks_in_stage=3,
                 ec_sent=None)
    assert not f.in_arm("C")
    agg = psf.aggregate_arm([f], "C", "clean15_126")
    assert agg["n_entries"] == 0


# --------------------------------------------------------------------------- #
# 9. Regime bucketing                                                           #
# --------------------------------------------------------------------------- #
def test_regime_bucketing():
    assert psf._regime_of(pd.Timestamp("2022-06-15")) == "2022_bear"
    assert psf._regime_of(pd.Timestamp("2023-01-01")) == "2023_24_bull"
    assert psf._regime_of(pd.Timestamp("2024-12-31")) == "2023_24_bull"
    assert psf._regime_of(pd.Timestamp("2025-06-01")) == "2025_26"
    # out of range (before/after the union window) → None.
    assert psf._regime_of(pd.Timestamp("2019-01-01")) is None
    assert psf._regime_of(pd.Timestamp("2027-01-01")) is None


# --------------------------------------------------------------------------- #
# 10. Small synthetic end-to-end (assemble_results + falsifiers)                #
# --------------------------------------------------------------------------- #
def test_assemble_results_end_to_end():
    fires = []
    # Arm B beats A: stage-2 fires all win, non-stage fires mostly stop.
    for i in range(40):
        d = pd.Timestamp("2023-01-01") + pd.Timedelta(days=i * 5)
        f = psf.Fire(f"WIN{i}", d, "T1/T2", stage=2, weeks_in_stage=4, ec_sent=26.0)
        f.state_15_126 = grading.TerminalState.CLEAN_LIFTOFF if i % 3 else grading.TerminalState.STOPPED
        f.matured_15_126 = True
        f.state_8_21 = f.state_15_126
        f.matured_8_21 = True
        f._liftoff_bar_clean15_126 = 30 if i % 3 else None
        f.fwd = {"fwd_ret_63": 0.1, "fwd_ret_126": 0.2, "fwd_mdd_126": -0.03}
        fires.append(f)
    for i in range(40):
        d = pd.Timestamp("2023-02-01") + pd.Timedelta(days=i * 5)
        f = psf.Fire(f"LOSE{i}", d, "T1/T2", stage=4, weeks_in_stage=6, ec_sent=None)
        f.state_15_126 = grading.TerminalState.STOPPED
        f.matured_15_126 = True
        f.state_8_21 = f.state_15_126
        f.matured_8_21 = True
        f.fwd = {"fwd_ret_63": -0.1, "fwd_ret_126": -0.2, "fwd_mdd_126": -0.2}
        fires.append(f)

    res = psf.assemble_results(fires, n_universe=100, n_with_prices=80, n_late_ipo=3)
    assert res["proxy_disclosure"] == psf.PROXY_DISCLOSURE
    assert res["universe"]["n_late_ipo_excluded_counted"] == 3
    assert res["n_fires_total"] == 80
    p15 = res["params"]["clean15_126"]["arms"]
    # Arm A pools everyone; Arm B is only the stage-2 winners subset.
    assert p15["A"]["overall"]["n_entries"] == 80
    assert p15["B"]["overall"]["n_entries"] == 40
    # B win-rate should exceed A win-rate here by construction.
    assert p15["B"]["overall"]["win_rate"] > p15["A"]["overall"]["win_rate"]
    # falsifiers present with the expected keys.
    fals = res["params"]["clean15_126"]["falsifiers"]
    assert set(fals) >= {"PSF_H1", "PSF_H2", "PSF_H3", "KILL"}
    assert fals["PSF_H1"]["verdict"] in ("pass", "fail")


# --------------------------------------------------------------------------- #
# 11. Fresh-fire = transition INTO T1/T2                                         #
# --------------------------------------------------------------------------- #
def test_fresh_fire_is_transition(monkeypatch):
    # Build a fake tier_stream: None, None, T1, T1, None, T2, T2 → fires on the 1st T1 and 1st T2.
    idx = _bdays("2023-01-02", 7)
    fake = pd.DataFrame({"tier": [None, None, "T1", "T1", None, "T2", "T2"]}, index=idx)
    monkeypatch.setattr(psf.confluence_tiers, "tier_stream", lambda c: fake)
    fires = psf.fresh_fire_dates(pd.Series(range(7), index=idx))
    assert list(fires) == [idx[2], idx[5]], "fresh fire must be the transition INTO T1/T2, not sustained days"


def test_fresh_fire_empty_on_no_stream(monkeypatch):
    monkeypatch.setattr(psf.confluence_tiers, "tier_stream", lambda c: pd.DataFrame())
    fires = psf.fresh_fire_dates(pd.Series([1, 2, 3], index=_bdays("2023-01-02", 3)))
    assert len(fires) == 0


# --------------------------------------------------------------------------- #
# 12. Late-IPO exclusion is COUNTED                                             #
# --------------------------------------------------------------------------- #
def test_late_ipo_excluded_counted(monkeypatch):
    # A name with < 45 completed weeks: its fires get stage=0 → drop from B/C, stay in A,
    # and the name is flagged late_ipo_excluded.
    idx = _bdays("2022-01-03", 300)  # ~14 months → ~60 weeks, but we mock the stage series short
    close = pd.Series(np.linspace(100, 150, 300), index=idx)

    fire_date = idx[100]
    monkeypatch.setattr(psf, "fresh_fire_dates", lambda c: pd.DatetimeIndex([fire_date]))
    # stage series with only 10 completed weeks before the fire → too-young at the fire.
    short_weeks = pd.Series([2] * 10, index=pd.bdate_range("2022-01-07", periods=10, freq="W-FRI"))
    monkeypatch.setattr(psf.weinstein_stage, "stage_series", lambda c, v, b: short_weeks)
    # neutralize grading so we isolate the exclusion logic.
    monkeypatch.setattr(psf, "grade_fire", lambda gc, f: f)

    fires, late = psf.fires_for_ticker("YOUNG", close, None, close, {})
    assert late is True, "a name too young at all in-window fires must be flagged excluded"
    assert len(fires) == 1
    assert fires[0].stage == 0  # not stageable → drops from B/B-fresh/C
    assert fires[0].in_arm("A")  # but still counted in A
    assert not fires[0].in_arm("B")


# --------------------------------------------------------------------------- #
# 13. FIX-1 — block-bootstrap DIFFERENCE CI is the primary falsifier statistic  #
# --------------------------------------------------------------------------- #
def _fire_at(ticker, date, win, stage=2, ec=26.0):
    f = psf.Fire(ticker, pd.Timestamp(date), "T1/T2", stage=stage, weeks_in_stage=4, ec_sent=ec)
    st = grading.TerminalState.CLEAN_LIFTOFF if win else grading.TerminalState.STOPPED
    f.state_15_126 = st
    f.matured_15_126 = True
    f.state_8_21 = st
    f.matured_8_21 = True
    f._liftoff_bar_clean15_126 = 30 if win else None
    f.bars_to_mfe_peak_126 = 40 if win else 10
    f.fwd = {"fwd_ret_63": 0.2 if win else -0.1, "fwd_ret_126": 0.3 if win else -0.2,
             "fwd_mdd_126": -0.02 if win else -0.2, "fwd_mfe_126": 0.4 if win else 0.05}
    return f


def test_block_bootstrap_diff_ci_shape_and_null():
    # Build B (stage2) and A-only (stage4) fires spread across many months, IDENTICAL win-rate
    # → the difference CI must straddle 0 (a true null).
    fires = []
    for m in range(1, 13):
        for d in range(1, 6):
            date = f"2023-{m:02d}-{d:02d}"
            # every stage-2 fire and matched stage-4 fire win 50% (i even) — no arm edge
            fires.append(_fire_at(f"S2_{m}_{d}", date, win=(d % 2 == 0), stage=2))
            fires.append(_fire_at(f"S4_{m}_{d}", date, win=(d % 2 == 0), stage=4))
    bd = psf.block_bootstrap_diff_ci(fires, "B", "A", "clean15_126")
    assert bd["n_months"] == 12
    assert bd["ci95"][0] is not None and bd["ci95"][1] is not None
    # a true null → lower bound <= 0 <= upper bound (straddles 0).
    assert bd["straddles_0"] is True
    assert bd["lower_gt_0"] is False


def test_block_bootstrap_diff_ci_detects_clean_edge():
    # B(stage2) wins ALL, the stage-4 fires win NONE. Arm A pools EVERYONE (both), so A wins
    # 50%; arm B wins 100% → diff = +0.5, spread over 6 months, lower bound clearly > 0.
    fires = []
    for m in range(1, 7):
        for d in range(1, 8):
            date = f"2023-{m:02d}-{d:02d}"
            fires.append(_fire_at(f"B_{m}_{d}", date, win=True, stage=2))
            fires.append(_fire_at(f"A_{m}_{d}", date, win=False, stage=4))
    bd = psf.block_bootstrap_diff_ci(fires, "B", "A", "clean15_126")
    assert bd["diff_point"] == pytest.approx(0.5, abs=1e-9)  # B=100% - A(pooled)=50%
    assert bd["lower_gt_0"] is True


def test_falsifier_uses_bootstrap_diff_as_primary():
    # Verdict must flip to FAIL when the bootstrap-diff CI straddles 0 EVEN IF the (anti-
    # conservative) Wilson diff would clear — the primary statistic governs.
    fires = []
    for m in range(1, 13):
        for d in range(1, 6):
            date = f"2023-{m:02d}-{d:02d}"
            fires.append(_fire_at(f"S2_{m}_{d}", date, win=(d % 2 == 0), stage=2))
            fires.append(_fire_at(f"S4_{m}_{d}", date, win=(d % 2 == 0), stage=4))
    fals = psf.falsifier_verdicts(fires, "clean15_126")
    assert fals["PSF_H1"]["primary_stat"] == "block_bootstrap_diff_ci (B−A)"
    assert "bootstrap_diff" in fals["PSF_H1"]
    # true null → FAIL on the primary bootstrap-diff lower bound.
    assert fals["PSF_H1"]["verdict"] == "fail"
    # the anti-conservative Wilson diff is still reported under its labelled key.
    assert "wilson_diff_ci95_ANTICONSERVATIVE" in fals["PSF_H1"]


# --------------------------------------------------------------------------- #
# 14. FIX-3 — H3 uses UNCONDITIONAL bars-to-MFE-peak over ALL matured fires      #
# --------------------------------------------------------------------------- #
def test_h3_unconditional_hold_metric():
    # 3 winners (mfe-peak bar 40) + 3 losers (mfe-peak bar 10) → unconditional median = 25,
    # NOT the conditional-on-winning 40. aggregate_arm must expose the unconditional metric.
    fires = [_fire_at(f"W{i}", f"2023-01-0{i+1}", win=True) for i in range(3)]
    fires += [_fire_at(f"L{i}", f"2023-02-0{i+1}", win=False) for i in range(3)]
    agg = psf.aggregate_arm(fires, "A", "clean15_126")
    assert agg["median_bars_to_mfe_peak_126"] == pytest.approx(25.0)   # (40,40,40,10,10,10)
    assert agg["median_bars_to_liftoff"] == pytest.approx(30.0)         # conditional (winners only; _liftoff_bar=30)
    # median MFE magnitude over ALL matured fires (unconditional).
    assert agg["median_fwd_mfe_126"] == pytest.approx(0.225)            # median(0.4,0.4,0.4,0.05,0.05,0.05)


# --------------------------------------------------------------------------- #
# 15. FIX-4 — de-overlap keeps one fire per name per non-overlapping window      #
# --------------------------------------------------------------------------- #
def test_de_overlap_one_fire_per_window():
    # Name AAA fires 3x within 30 days (all inside one 126-bar window) + once 200 days later.
    fires = [
        _fire_at("AAA", "2023-01-02", win=True),
        _fire_at("AAA", "2023-01-15", win=True),   # < 126 days from first → dropped
        _fire_at("AAA", "2023-02-01", win=True),   # < 126 days from first → dropped
        _fire_at("AAA", "2023-08-01", win=True),   # > 126 days → kept
        _fire_at("BBB", "2023-01-02", win=True),   # different name → kept
    ]
    deov = psf.de_overlap_fires(fires, window_bars=126)
    # AAA keeps 2 (first + the 200-day-later one), BBB keeps 1 → 3 total.
    kept_dates = sorted((f.ticker, str(f.date.date())) for f in deov)
    assert kept_dates == [("AAA", "2023-01-02"), ("AAA", "2023-08-01"), ("BBB", "2023-01-02")]


def test_fire_multiplicity_disclosure():
    fires = [_fire_at("AAA", f"2023-01-0{i+1}", win=True) for i in range(4)]
    fires += [_fire_at("BBB", "2023-01-01", win=True)]
    fm = psf.fire_multiplicity(fires)
    assert fm["n_names"] == 2
    assert fm["n_fires"] == 5
    assert fm["max_fires_per_name"] == 4
    assert fm["mean_fires_per_name"] == pytest.approx(2.5)


# ===========================================================================  #
# PSQ tests (Prophet × Stage QUALITY re-grade, PSQ prereg §4-§5)               #
# ===========================================================================  #

def _psq_fire(ticker, date, ret126, mfe126, mdd126, stage=2, weeks=5, ec=26.0,
              win=True, stopped=False):
    """Build a synthetic matured_15_126 Fire with explicit forward metrics for PSQ tests."""
    f = psf.Fire(ticker, pd.Timestamp(date), "T1/T2", stage=stage,
                 weeks_in_stage=weeks, ec_sent=ec)
    if win:
        f.state_15_126 = grading.TerminalState.CLEAN_LIFTOFF
    elif stopped:
        f.state_15_126 = grading.TerminalState.STOPPED
    else:
        f.state_15_126 = grading.TerminalState.CUSHIONED
    f.matured_15_126 = True
    f.state_8_21 = f.state_15_126
    f.matured_8_21 = True
    f._liftoff_bar_clean15_126 = 30 if win else None
    f.bars_to_mfe_peak_126 = 60 if win else 20
    f.fwd = {
        "fwd_ret_126": float(ret126),
        "fwd_mfe_126": float(mfe126),
        "fwd_mdd_126": float(mdd126),
        "fwd_ret_63": float(ret126) / 2,
    }
    return f


# --------------------------------------------------------------------------- #
# PSQ-T1: synthetic fires with known median shift — CI excludes zero           #
# --------------------------------------------------------------------------- #
def _month_date(m: int) -> str:
    """Return a date string for sequential month index m (1-based, up to 60)."""
    year = 2022 + (m - 1) // 12
    mon = ((m - 1) % 12) + 1
    return f"{year}-{mon:02d}-15"


def test_block_bootstrap_stat_diff_ci_known_shift():
    """C has a consistently higher fwd_ret_126 than A. With 24+ months and a clear shift,
    the CI lower bound must be > 0 (CI excludes zero).

    Uses 30 months × 5 fires per arm.  A fires: ret=0.01 (1%), C fires: ret=0.06 (6%).
    True diff = +0.05 (5pp).  Bootstrap CI must exclude 0.
    """
    fires = []
    for m in range(1, 31):          # 30 months → > 24 month gate
        date = _month_date(m)
        for k in range(5):
            # Arm A only (stage != 2, so not in C).
            fires.append(_psq_fire(f"A_{m}_{k}", date, ret126=0.01, mfe126=0.08, mdd126=-0.03,
                                   stage=4, ec=None, win=True))
            # Arm C (stage==2, ec>=24).
            fires.append(_psq_fire(f"C_{m}_{k}", date, ret126=0.06, mfe126=0.12, mdd126=-0.01,
                                   stage=2, ec=26.0, win=True))

    bd = psf.block_bootstrap_stat_diff_ci(
        fires, "C", "A", psf._stat_fwd_ret_126, "test_median_ret",
        n_boot=2000, seed=42
    )
    assert bd["no_verdict"] is False
    assert bd["n_months"] >= 24
    # Arm A pools all fires (stage-2 and stage-4) → median per month = median(0.01, 0.06) = 0.035.
    # Arm C is stage-2 only → median per month = 0.06.  diff_point ~ 0.06 - 0.035 = 0.025.
    assert bd["diff_point"] == pytest.approx(0.025, abs=0.005)
    # CI must exclude zero (lower > 0): the shift is consistent across ALL months.
    assert bd["lower_gt_0"] is True, f"Expected CI lower > 0, got ci95={bd['ci95']}"
    assert bd["ci95"][0] > 0.0


# --------------------------------------------------------------------------- #
# PSQ-T2: paired-months property — identical arms → diff CI centered on 0      #
# --------------------------------------------------------------------------- #
def test_block_bootstrap_stat_diff_ci_identical_arms():
    """When arm_hi and arm_lo are the same fires (C = A, no Stage-2 filter applied to A),
    the difference must be zero and the CI must contain zero.

    We pass the same fire set for both arms by using a stat_fn that ignores arm membership
    and directly compare C−A where ALL fires are in both arms.
    """
    fires = []
    for m in range(1, 30):
        date = _month_date(m)
        for k in range(5):
            # All fires are Stage-2 with EC, so arm_C == arm_A for any stat over Stage-2.
            fires.append(_psq_fire(f"X_{m}_{k}", date, ret126=0.04, mfe126=0.10, mdd126=-0.02,
                                   stage=2, ec=26.0, win=True))

    # C and A are the same fires (all are stage-2∩EC, so arm A and arm C have the same pool).
    # However arm A (all fires) = arm C here because all fires are in C.
    # The diff must be 0 and CI must contain 0.
    bd = psf.block_bootstrap_stat_diff_ci(
        fires, "C", "A", psf._stat_fwd_ret_126, "identical_arms_test",
        n_boot=2000, seed=99
    )
    assert bd["no_verdict"] is False
    # diff_point must be 0 (same pool).
    assert bd["diff_point"] == pytest.approx(0.0, abs=1e-9)
    # CI must contain 0.
    lo, hi = bd["ci95"]
    assert lo <= 0.0 <= hi, f"CI must straddle 0 for identical arms, got [{lo}, {hi}]"


# --------------------------------------------------------------------------- #
# PSQ-T3: degenerate-month guard (< 24 months → no_verdict)                   #
# --------------------------------------------------------------------------- #
def test_block_bootstrap_stat_diff_ci_degenerate_month_guard():
    """With fewer than PSQ_MIN_MONTHS (24) distinct months, must return no_verdict=True."""
    fires = []
    for m in range(1, 20):    # only 19 months — below the 24-month gate
        date = _month_date(m)
        fires.append(_psq_fire(f"G_{m}", date, ret126=0.05, mfe126=0.10, mdd126=-0.02,
                               stage=2, ec=26.0, win=True))
        fires.append(_psq_fire(f"H_{m}", date, ret126=0.02, mfe126=0.06, mdd126=-0.04,
                               stage=4, ec=None, win=True))

    bd = psf.block_bootstrap_stat_diff_ci(
        fires, "C", "A", psf._stat_fwd_ret_126, "degenerate_test",
        n_boot=500, seed=7
    )
    assert bd["no_verdict"] is True, (
        f"Expected no_verdict=True with {bd['n_months']} months, got no_verdict={bd['no_verdict']}"
    )
    assert bd["ci95"] == [None, None]


# --------------------------------------------------------------------------- #
# PSQ-T3b: aggregator=np.mean gives correct stopped FRACTION (not median)      #
# --------------------------------------------------------------------------- #
def test_block_bootstrap_stat_diff_ci_aggregator_mean():
    """H3 uses aggregator=np.mean so stopped_fraction = mean(0/1 flags), not median.

    With 65% of fires stopped (majority → median=1.0, but mean=0.65):
    C arm: 30% stopped. A arm: 65% stopped. Diff = -0.35 (C better).
    The CI with aggregator=np.mean should have a negative upper bound (PASS for H3).
    """
    fires = []
    for m in range(1, 30):   # 29 months → above 24-month gate
        date = _month_date(m)
        # Arm A (stage 4): 65% stopped → 13 stopped, 7 wins per month.
        for k in range(7):
            fires.append(_psq_fire(f"AW_{m}_{k}", date, ret126=0.1, mfe126=0.2, mdd126=-0.03,
                                   stage=4, ec=None, win=True, stopped=False))
        for k in range(13):
            fires.append(_psq_fire(f"AS_{m}_{k}", date, ret126=-0.1, mfe126=0.04, mdd126=-0.18,
                                   stage=4, ec=None, win=False, stopped=True))
        # Arm C (stage 2, EC): 30% stopped → 7 wins, 3 stopped per month.
        for k in range(7):
            fires.append(_psq_fire(f"CW_{m}_{k}", date, ret126=0.12, mfe126=0.22, mdd126=-0.02,
                                   stage=2, ec=26.0, win=True, stopped=False))
        for k in range(3):
            fires.append(_psq_fire(f"CS_{m}_{k}", date, ret126=-0.08, mfe126=0.05, mdd126=-0.12,
                                   stage=2, ec=26.0, win=False, stopped=True))

    bd = psf.block_bootstrap_stat_diff_ci(
        fires, "C", "A", psf._stat_stopped_flag, "stopped_fraction_test",
        n_boot=500, seed=42, aggregator=np.mean
    )
    assert bd["no_verdict"] is False
    # Arm A pools ALL T1/T2 fires (stage-4 + stage-2+EC combined):
    #   per month: 7 AW + 13 AS + 7 CW + 3 CS = 30 fires; stopped = 13+3 = 16 → 53.3%.
    # Arm C: 7 CW + 3 CS = 10 fires; stopped = 3 → 30%.
    # Diff = 0.30 - 0.533 ≈ -0.233 (C lower stopped rate = better).
    assert bd["diff_point"] == pytest.approx(-7 / 30, abs=0.02)
    # CI upper bound must be < 0 (C better across all months consistently).
    assert bd["upper_lt_0"] is True, f"Expected CI upper < 0, got ci95={bd['ci95']}"


# --------------------------------------------------------------------------- #
# PSQ-T4: EA arithmetic correctness (_stat_ea_126)                             #
# --------------------------------------------------------------------------- #
def test_psq_ea_arithmetic():
    """EA = fwd_mfe_126 + fwd_mdd_126.  Verify the stat callable returns the correct sum."""
    f = _psq_fire("EA_TEST", "2023-03-01", ret126=0.03, mfe126=0.15, mdd126=-0.08,
                  stage=2, ec=26.0, win=True)
    ea = psf._stat_ea_126(f)
    assert ea == pytest.approx(0.15 + (-0.08), abs=1e-9)

    # None mfe → None.
    f2 = _psq_fire("EA_NONE", "2023-03-02", ret126=0.01, mfe126=0.10, mdd126=-0.05,
                   stage=2, ec=26.0, win=True)
    f2.fwd = {"fwd_ret_126": 0.01, "fwd_mdd_126": -0.05}  # mfe missing
    assert psf._stat_ea_126(f2) is None

    # Both zero → 0.0.
    f3 = _psq_fire("EA_ZERO", "2023-03-03", ret126=0.0, mfe126=0.0, mdd126=0.0,
                   stage=2, ec=26.0, win=True)
    assert psf._stat_ea_126(f3) == pytest.approx(0.0, abs=1e-9)


# --------------------------------------------------------------------------- #
# PSQ-T5: psq_falsifier_verdicts wiring (full dict keys)                       #
# --------------------------------------------------------------------------- #
def test_psq_falsifier_verdicts_keys():
    """psq_falsifier_verdicts must return the expected top-level keys."""
    # Minimal fire set to exercise all code paths without triggering degenerate guards.
    fires = []
    for m in range(1, 26):    # 25 months (above the 24-month gate)
        date = _month_date(m)
        fires.append(_psq_fire(f"C_{m}", date, ret126=0.05, mfe126=0.10, mdd126=-0.02,
                               stage=2, ec=26.0, win=True))
        fires.append(_psq_fire(f"A_{m}", date, ret126=0.02, mfe126=0.06, mdd126=-0.04,
                               stage=4, ec=None, win=True))

    result = psf.psq_falsifier_verdicts(fires)
    assert "PSQ_H1" in result
    assert "PSQ_H1_decompositions" in result
    assert "PSQ_H1_deoverlapped" in result
    assert "PSQ_H2" in result
    assert "PSQ_H3" in result
    assert "KILL_PSQ" in result
    assert "regime_leg" in result
    # Each hypothesis must have a verdict key.
    for key in ("PSQ_H1", "PSQ_H2", "PSQ_H3"):
        assert result[key]["verdict"] in ("PASS", "FAIL", "NO-VERDICT"), (
            f"{key} verdict={result[key]['verdict']!r} not in {{PASS, FAIL, NO-VERDICT}}"
        )
    # KILL must be a bool.
    assert isinstance(result["KILL_PSQ"]["triggered"], bool)


# --------------------------------------------------------------------------- #
# PSQ-T6: stopped_flag stat — 1 for STOPPED, 0 for others                     #
# --------------------------------------------------------------------------- #
def test_psq_stopped_flag_stat():
    """_stat_stopped_flag returns 1.0 for STOPPED, 0.0 for CLEAN_LIFTOFF, None if not matured."""
    f_stop = _psq_fire("S1", "2023-01-10", ret126=-0.15, mfe126=0.02, mdd126=-0.18,
                        stage=2, ec=26.0, win=False, stopped=True)
    assert psf._stat_stopped_flag(f_stop) == pytest.approx(1.0)

    f_win = _psq_fire("W1", "2023-01-11", ret126=0.10, mfe126=0.18, mdd126=-0.03,
                       stage=2, ec=26.0, win=True)
    assert psf._stat_stopped_flag(f_win) == pytest.approx(0.0)

    f_unmat = psf.Fire("U1", pd.Timestamp("2023-01-12"), "T1/T2", 2, 4, 26.0)
    # matured_15_126 not set (defaults False).
    assert psf._stat_stopped_flag(f_unmat) is None


# --------------------------------------------------------------------------- #
# PSQ-T7: build_psq_fires_table columns and row counts                          #
# --------------------------------------------------------------------------- #
def test_build_psq_fires_table(tmp_path):
    """build_psq_fires_table must include only matured fires and have the right columns."""
    fires = []
    # 5 matured (arm C: stage2+ec), 3 matured (arm A only: stage4), 2 unmatured.
    for i in range(5):
        fires.append(_psq_fire(f"C{i}", f"2023-0{i+1}-10", ret126=0.05, mfe126=0.10, mdd126=-0.02,
                               stage=2, ec=26.0, win=True))
    for i in range(3):
        f = _psq_fire(f"A{i}", f"2023-0{i+1}-15", ret126=0.01, mfe126=0.04, mdd126=-0.05,
                      stage=4, ec=None, win=True)
        fires.append(f)
    for i in range(2):
        f = psf.Fire(f"U{i}", pd.Timestamp(f"2023-0{i+1}-20"), "T1/T2", 2, 5, 26.0)
        # matured_15_126 = False → excluded.
        fires.append(f)

    tbl = psf.build_psq_fires_table(fires)
    # Only 8 matured.
    assert len(tbl) == 8
    required_cols = {"ticker", "entry_date", "arm_A", "arm_B", "arm_B_fresh", "arm_C",
                     "fwd_ret_126", "fwd_mfe_126", "fwd_mdd_126", "ea_126",
                     "terminal_state_15_126", "stopped_flag", "entry_month", "regime"}
    assert required_cols.issubset(set(tbl.columns))
    # All arm_A must be True.
    assert tbl["arm_A"].all()
    # Stage-2+ec fires have arm_C=True.
    c_rows = tbl[tbl["ticker"].str.startswith("C")]
    assert c_rows["arm_C"].all()
    # Stage-4 fires have arm_C=False.
    a_rows = tbl[tbl["ticker"].str.startswith("A")]
    assert (~a_rows["arm_C"]).all()
    # EA arithmetic check.
    assert (tbl["ea_126"] == tbl["fwd_mfe_126"] + tbl["fwd_mdd_126"]).all()
