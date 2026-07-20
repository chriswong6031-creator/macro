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
