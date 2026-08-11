"""Truth tests for engine.top_anatomy — synthetic bars only, deterministic, fast.

The load-bearing one is `test_features_are_point_in_time`: this program uses
hindsight aggressively for LABELS (episodes, peaks, race outcomes) and must never
use it for FEATURES. Every other test pins a frozen threshold from
`research/top_anatomy/TOPA_PHASE0_PREREG.md` §4 so a silent re-pin fails here
rather than in a result.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import top_anatomy as ta
from scripts import research_top_anatomy_phase0 as rh

REPO = Path(__file__).resolve().parent.parent


# ══════════════════════════════════════════════════════════════════════════════
# builders
# ══════════════════════════════════════════════════════════════════════════════
def _cal(n: int, start: str = "2019-01-01") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


def _bars(close: np.ndarray, index: pd.DatetimeIndex, *, vol=5e6,
          with_open: bool = True) -> pd.DataFrame:
    """OHLCV around a close path: high/low a fixed 1% band, `vol` scalar or array."""
    c = pd.Series(close, index=index, dtype=float)
    v = pd.Series(vol, index=index, dtype=float) if np.isscalar(vol) \
        else pd.Series(np.asarray(vol, dtype=float), index=index)
    d = {"close": c, "high": c * 1.01, "low": c * 0.99, "volume": v}
    if with_open:
        d["open"] = c.shift(1).fillna(c.iloc[0])
    return pd.DataFrame(d)


def _ramp(n: int, *, base: float = 10.0, daily: float = 0.006, seed: int = 0,
          noise: float = 0.004) -> np.ndarray:
    """A steadily rising path — the raw material of an EXTENDED name."""
    rng = np.random.default_rng(seed)
    r = daily + rng.normal(0.0, noise, n)
    r[0] = 0.0
    return base * np.exp(np.cumsum(r))


def _maturing(n: int, *, base: float = 10.0, daily: float = 0.007, seed: int = 0,
              dip_every: int = 40) -> np.ndarray:
    """A rising path punctuated by reclaimed ~9% dips — what F5 needs to be non-null."""
    rng = np.random.default_rng(seed)
    r = daily + rng.normal(0.0, 0.005, n)
    r[0] = 0.0
    for s in range(dip_every, n - 4, dip_every):
        r[s:s + 3] = -0.032
    return base * np.exp(np.cumsum(r))


def _volumes(n: int, seed: int = 0) -> np.ndarray:
    """Share volume with real dispersion — a flat tape makes D1/D5 vacuously null."""
    rng = np.random.default_rng(seed)
    return 5e6 * np.exp(rng.normal(0.0, 0.35, n))


def _panel(paths: dict[str, np.ndarray], index: pd.DatetimeIndex, *, vol: float = 5e6):
    close = pd.DataFrame({k: pd.Series(v, index=index) for k, v in paths.items()})
    dvol = close * vol
    return close, dvol


# ══════════════════════════════════════════════════════════════════════════════
# (a) §4.1 EXT truth table — trigger, near-high, floors, history
# ══════════════════════════════════════════════════════════════════════════════
def _ext_case(*, r126: float, near_high_ratio: float, price: float, dvol: float,
              n_prior: int) -> bool:
    """One hand-built (name, day): does §4.1 call the last bar EXTENDED?"""
    n = n_prior + 1
    idx = _cal(n)
    c = np.full(n, price / near_high_ratio, dtype=float)   # the trailing-252 high level
    c[-1] = price
    if n >= 127:
        c[-127] = price / (1.0 + r126)                     # plant the exact r126
    close = pd.DataFrame({"T": pd.Series(c, index=idx)})
    dv = pd.DataFrame({"T": pd.Series(dvol, index=idx)})
    return bool(ta.extended_mask(close, dv).iloc[-1, 0])


@pytest.mark.parametrize(
    "kw,expected,why",
    [
        (dict(r126=0.60, near_high_ratio=1.00, price=50.0, dvol=5e6, n_prior=300), True,
         "clean extended day"),
        (dict(r126=0.50, near_high_ratio=1.00, price=50.0, dvol=5e6, n_prior=300), True,
         "r126 exactly at the +0.50 floor is INCLUSIVE"),
        (dict(r126=0.49, near_high_ratio=1.00, price=50.0, dvol=5e6, n_prior=300), False,
         "r126 just under the floor"),
        (dict(r126=0.60, near_high_ratio=0.90, price=50.0, dvol=5e6, n_prior=300), True,
         "exactly 0.90 x the trailing 252 high is INCLUSIVE"),
        (dict(r126=0.60, near_high_ratio=0.89, price=50.0, dvol=5e6, n_prior=300), False,
         "already broken: below 0.90 x the trailing high"),
        (dict(r126=0.60, near_high_ratio=1.00, price=2.99, dvol=5e6, n_prior=300), False,
         "under the $3 price floor"),
        (dict(r126=0.60, near_high_ratio=1.00, price=3.00, dvol=5e6, n_prior=300), True,
         "exactly $3 is INCLUSIVE"),
        (dict(r126=0.60, near_high_ratio=1.00, price=50.0, dvol=1.99e6, n_prior=300), False,
         "under the $2M median-21d dollar-volume floor"),
        (dict(r126=0.60, near_high_ratio=1.00, price=50.0, dvol=2.0e6, n_prior=300), True,
         "exactly $2M is INCLUSIVE"),
        (dict(r126=0.60, near_high_ratio=1.00, price=50.0, dvol=5e6, n_prior=259), False,
         "259 prior sessions is under the 260 history floor"),
        (dict(r126=0.60, near_high_ratio=1.00, price=50.0, dvol=5e6, n_prior=260), True,
         "260 prior sessions is INCLUSIVE"),
    ],
)
def test_extended_day_truth_table(kw, expected, why):
    assert _ext_case(**kw) is expected, why


def test_extension_variants_are_distinct_populations():
    """The two report-only sensitivity arms must actually be different masks."""
    idx = _cal(500)
    close, dvol = _panel({"T": _ramp(500, daily=0.004, seed=3)}, idx)
    primary = ta.extended_mask(close, dvol, variant="primary")
    r63 = ta.extended_mask(close, dvol, variant="r63")
    hi = close * 1.01
    lo = close * 0.99
    atrz = ta.extended_mask(close, dvol, variant="atrz", high_df=hi, low_df=lo)
    assert primary.to_numpy().sum() > 0 and r63.to_numpy().sum() > 0
    assert not primary.equals(r63)
    assert atrz.shape == primary.shape
    with pytest.raises(ValueError):
        ta.extended_mask(close, dvol, variant="nope")


# ══════════════════════════════════════════════════════════════════════════════
# (b) §4.2 episode gap merge — the 21/22 session boundary
# ══════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("gap,n_episodes", [(0, 1), (20, 1), (21, 1), (22, 2), (40, 2)])
def test_episode_gap_merge_boundary(gap, n_episodes):
    """21 intervening NON-EXT sessions merge; 22 split (prereg §4.2)."""
    idx = _cal(60)
    m = np.zeros(60, dtype=bool)
    m[5:10] = True
    second = 10 + gap
    m[second:second + 5] = True
    mask = pd.DataFrame({"T": pd.Series(m, index=idx)})
    eps = ta.extract_episodes(mask)
    assert len(eps) == n_episodes
    assert int(eps["n_ext_days"].sum()) == 10


def test_micro_episodes_are_kept_and_flagged():
    idx = _cal(40)
    m = np.zeros(40, dtype=bool)
    m[3:6] = True             # 3 EXT days -> micro
    m[30:36] = True           # 6 EXT days -> not micro
    eps = ta.extract_episodes(pd.DataFrame({"T": pd.Series(m, index=idx)}))
    assert list(eps["micro"]) == [True, False]
    assert list(eps["n_ext_days"]) == [3, 6]


def test_episode_gap_counts_sessions_not_calendar_rows():
    """A halted stretch costs SESSIONS, not rows: bars absent from the panel do not merge."""
    idx = _cal(60)
    close = pd.Series(np.nan, index=idx)
    live = list(range(0, 10)) + list(range(45, 60))     # 35 missing panel rows
    close.iloc[live] = 100.0
    m = pd.Series(False, index=idx)
    m.iloc[5:10] = True
    m.iloc[45:50] = True
    mask = pd.DataFrame({"T": m})
    cl = pd.DataFrame({"T": close})
    # measured on the segment's own bars the two runs are adjacent -> one episode
    assert len(ta.extract_episodes(mask, cl)) == 1
    # measured on panel rows they are 35 apart -> two episodes
    assert len(ta.extract_episodes(mask)) == 2


# ══════════════════════════════════════════════════════════════════════════════
# (c) §4.3 race-label truth table on hand-built paths
# ══════════════════════════════════════════════════════════════════════════════
def _race_one(path: list[float], *, horizon: int = 250, **kw) -> pd.Series:
    """Label the FIRST bar of a hand-built path as if it were the EXT day."""
    idx = _cal(len(path))
    close = pd.DataFrame({"T": pd.Series(path, index=idx, dtype=float)})
    mask = pd.DataFrame({"T": pd.Series([True] + [False] * (len(path) - 1), index=idx)})
    out = ta.race_labels(close, mask, horizon=horizon, **kw)
    assert len(out) == 1
    return out.iloc[0]


def test_race_clean_top():
    """Rise 10% (under the +15% barrier), then give back 20% from the peak."""
    r = _race_one([100.0, 105.0, 110.0, 99.0, 87.9])
    assert r["label"] == "TOPPED"
    assert r["sessions_to_resolve"] == 4          # 87.9 <= 0.80 * 110
    assert r["censor_reason"] == ""


def test_race_clean_continuation():
    r = _race_one([100.0, 104.0, 109.0, 116.0, 60.0])
    assert r["label"] == "CONTINUED"
    assert r["sessions_to_resolve"] == 3          # +15% fires before any -20%


def test_race_same_day_tie_resolves_topped():
    """A bar satisfying BOTH barriers at once resolves TOPPED — conservative, §4.3.

    The tie is forced with non-frozen barriers because the FROZEN pair cannot
    produce one (see the next test); the rule still has to be pinned, since a
    sensitivity arm could reach it.
    """
    # both barriers land on bar 1: the entry IS the running peak, so -20% from the
    # peak and the (deliberately degenerate) up barrier fire on the same bar.
    r = _race_one([100.0, 80.0], dd_frac=0.80, up_frac=0.80)
    assert r["label"] == "TOPPED"
    assert r["sessions_to_resolve"] == 1


def test_same_day_tie_is_unreachable_under_the_frozen_barriers():
    """Under −20%-from-peak vs +15%-from-entry the tie clause can never bind.

    A same-bar tie needs c_j ≥ 1.15·c_0 AND c_j ≤ 0.80·peak, so peak ≥ 1.4375·c_0 —
    but then the +15% barrier already fired at the peak bar and the race was over.
    Recorded because the prereg's tie rule reads as if it decides real events; it
    does not, and no result may be attributed to it.
    """
    rng = np.random.default_rng(17)
    for k in range(150):
        path = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.06, 60)))
        path[0] = 100.0
        r = _race_one(list(path))
        if r["label"] != "CENSORED":
            i = int(r["sessions_to_resolve"])
            peak = float(np.max(path[:i + 1]))
            tie = (path[i] <= 0.80 * peak) and (path[i] >= 1.15 * path[0])
            assert not tie, f"a frozen-parameter tie occurred on draw {k}"


def test_race_censored_at_horizon():
    path = [100.0] + [101.0] * 60
    r = _race_one(path, horizon=50)
    assert r["label"] == "CENSORED"
    assert r["censor_reason"] == "horizon"
    assert np.isnan(r["sessions_to_resolve"])


def test_race_delisting_with_terminal_collapse_is_topped():
    """A name that dies AFTER a -20% print fires TOPPED on its own bars (§4.3)."""
    r = _race_one([100.0, 112.0, 88.0])            # last bar is the delisting bar
    assert r["label"] == "TOPPED"
    assert r["censor_reason"] == ""


def test_race_delisting_flat_is_censored():
    """A name that simply stops trading, with no -20% print, is CENSORED at data end."""
    r = _race_one([100.0, 101.0, 102.0, 103.0])
    assert r["label"] == "CENSORED"
    assert r["censor_reason"] == "data_end"
    assert r["sessions_available"] == 3


def test_race_barrier_edges_are_inclusive():
    assert _race_one([100.0, 115.0])["label"] == "CONTINUED"    # exactly +15%
    assert _race_one([100.0, 110.0, 88.0])["label"] == "TOPPED"  # exactly -20% off 110


def test_race_labels_carry_display_auxiliaries():
    idx = _cal(200)
    c = _ramp(200, daily=0.003, seed=5)
    close = pd.DataFrame({"T": pd.Series(c, index=idx)})
    mask = pd.DataFrame({"T": pd.Series([False] * 10 + [True] + [False] * 189, index=idx)})
    out = ta.race_labels(close, mask)
    for col in ("fwd_ret_21", "fwd_ret_63", "fwd_ret_126", "max_dd_21", "dd_ge_10"):
        assert col in out.columns
    assert np.isfinite(out["fwd_ret_63"].iloc[0])


# ══════════════════════════════════════════════════════════════════════════════
# (d) THE PIT-LEAK GUARD — features at d may not move when the future is rewritten
# ══════════════════════════════════════════════════════════════════════════════
PIT_FEATURES = [
    "A3_r126",              # A: geometry
    "A8_trend_r2_63",       # A: rolling regression
    "B2_rsi14",             # B: recursive (Wilder) smoothing
    "C3_semivol_ratio63",   # C: masked rolling std
    "D1_dvol_z",            # D: 252-session z of a 21-session mean
    "D5_corr21_volz_absret",  # D: rolling correlation
    "E3f_rs_peak_lag",      # E: RS argmax lag (cross-sectional input)
    "E5f_rs_decel",         # E: RS slope change
    "F2_drawdown_in_episode",  # F: episode-anchored
    "F5_reclaim_speed",     # F: path-dependent scan
]


@pytest.fixture(scope="module")
def pit_world():
    """A 12-name extended world plus the frozen labels the F-family is anchored on.

    Module-scoped: the panel is expensive to build and every test that uses it only
    READS it (mutation happens on a copy), so rebuilding it per parametrization
    bought nothing but wall time.

    Episodes are LABELS and are hindsight-legal by design, so they are computed
    once from the untouched panel and held fixed; what the guard interrogates is
    whether a FEATURE VALUE at d moves when the bars after d are rewritten.
    """
    idx = _cal(700)
    paths = {f"N{i}": _maturing(700, daily=0.006 + 0.001 * (i % 3), seed=100 + i)
             for i in range(12)}
    vols = {k: _volumes(700, seed=300 + i) for i, k in enumerate(paths)}
    close = pd.DataFrame({k: pd.Series(v, index=idx) for k, v in paths.items()})
    dvol = pd.DataFrame({k: close[k] * vols[k] for k in close.columns})
    ext = ta.extended_mask(close, dvol)
    eps = ta.extract_episodes(ext, close)
    fired = ext.sum(axis=1)
    d = fired[fired >= 6].index[len(fired[fired >= 6]) // 2]     # a busy EXT session
    return close, dvol, vols, ext, eps, d


def _mutate_future(close: pd.DataFrame, d: pd.Timestamp, seed: int = 9) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    out = close.copy()
    tail = out.index > d
    out.loc[tail] = out.loc[tail].to_numpy() * rng.uniform(0.2, 4.0, out.loc[tail].shape)
    return out


@pytest.mark.parametrize("feature", PIT_FEATURES)
def test_features_are_point_in_time(feature, pit_world):
    """Rewrite EVERY bar after d — across the whole panel — and demand d is unmoved.

    This is the single most important test in the program. Labels may use the
    future; a feature that moves when the future is rewritten is a leak, and a
    leak here would manufacture a "discriminator" out of hindsight. The equal-weight
    median index is REBUILT from the mutated panel on purpose, so a cross-sectional
    leak through the RS features would fail here too.
    """
    close, _, vols, ext, eps, d = pit_world

    def compute(cl: pd.DataFrame) -> pd.DataFrame:
        bars = {c: _bars(cl[c].to_numpy(dtype=float), cl.index, vol=vols[c])
                for c in cl.columns}
        dv = pd.DataFrame({c: bars[c]["close"] * bars[c]["volume"] for c in cl.columns})
        eqw = ta.equal_weight_median_index(cl, ta.eligibility_mask(cl, dv))
        return ta.feature_library(bars, eqw, {c: [d] for c in cl.columns}, episodes=eps)

    before = compute(close)
    after = compute(_mutate_future(close, d))
    b = before.set_index("segment")[feature]
    a = after.set_index("segment")[feature]
    assert b.notna().sum() >= 6, f"{feature} is mostly null at d — the test would be vacuous"
    pd.testing.assert_series_equal(b, a, check_exact=True,
                                   obj=f"{feature} at d after the future was rewritten")


def test_extension_gate_and_eligibility_are_point_in_time(pit_world):
    """The EXT gate itself decides d from d's past only — no future bar may flip it."""
    close, dvol, vols, ext, _, d = pit_world
    mutated = _mutate_future(close, d)
    mdvol = pd.DataFrame({k: mutated[k] * vols[k] for k in mutated.columns})
    upto = close.index <= d
    assert ext.loc[upto].sum().sum() > 0
    pd.testing.assert_frame_equal(ext.loc[upto],
                                  ta.extended_mask(mutated, mdvol).loc[upto])
    pd.testing.assert_frame_equal(ta.eligibility_mask(close, dvol).loc[upto],
                                  ta.eligibility_mask(mutated, mdvol).loc[upto])


def test_pit_guard_would_catch_a_real_leak():
    """The guard is only worth something if a planted leak fails it (mutation check)."""
    idx = _cal(700)
    close, _ = _panel({"N0": _ramp(700, seed=1)}, idx)
    d = idx[500]
    leaky = close["N0"].rolling(21, center=True).mean()      # centred == peeks forward
    mutated = close.copy()
    mutated.loc[mutated.index > d] *= 3.0
    leaky_after = mutated["N0"].rolling(21, center=True).mean()
    assert not np.isclose(leaky.loc[d], leaky_after.loc[d]), \
        "a centred window must move when the future moves, or this harness proves nothing"


# ══════════════════════════════════════════════════════════════════════════════
# identity segments (reused-ticker defect, prereg ratification log 2026-08-10)
# ══════════════════════════════════════════════════════════════════════════════
def test_identity_segments_split_on_a_reused_ticker():
    """A 100-session hole is a different company; a 40-session hole is the same one."""
    cal = _cal(600)
    keep_100 = np.r_[np.arange(0, 200), np.arange(300, 600)]      # 100-session hole
    keep_40 = np.r_[np.arange(0, 200), np.arange(240, 600)]       # 40-session hole
    bars_100 = _bars(_ramp(len(keep_100), seed=2), cal[keep_100])
    bars_40 = _bars(_ramp(len(keep_40), seed=2), cal[keep_40])
    out = ta.split_identity_segments({"BBBY": bars_100, "OK": bars_40}, cal)
    assert set(out) == {"BBBY#0", "BBBY#1", "OK"}
    assert len(out["BBBY#0"]) == 200
    assert len(out["BBBY#1"]) == 300
    assert len(out["OK"]) == len(keep_40)
    assert ta.segment_ticker("BBBY#1") == "BBBY" and ta.segment_ticker("OK") == "OK"


def test_nothing_crosses_an_identity_segment_boundary():
    """The old company's bars can neither seed history nor be walked into."""
    cal = _cal(700)
    keep = np.r_[np.arange(0, 300), np.arange(400, 700)]          # 100-session hole
    old = _ramp(300, base=50.0, daily=0.008, seed=11)
    new = _ramp(300, base=4.0, daily=0.008, seed=12)
    bars = _bars(np.r_[old, new], cal[keep])
    segs = ta.split_identity_segments({"BBBY": bars}, cal)
    assert set(segs) == {"BBBY#0", "BBBY#1"}

    close = pd.DataFrame({k: v["close"] for k, v in segs.items()}).reindex(cal)
    dvol = close * 5e6

    # history floor is per SEGMENT: 300 bars can never clear 260 prior + 126 lookback
    # on the new company's early life, so no EXT day may land before bar 260 of it.
    ext = ta.extended_mask(close, dvol)
    new_dates = segs["BBBY#1"].index
    fired = ext["BBBY#1"].reindex(new_dates).to_numpy(dtype=bool)
    assert not fired[:260].any(), "the new company inherited the old one's history"

    # and a feature on the new segment cannot see the old company's price level
    f = ta.feature_library(segs, None, {"BBBY#1": [new_dates[10]]})
    assert np.isnan(f["A3_r126"].iloc[0]), "r126 reached across the identity boundary"

    # the forward race walk cannot leave a segment either
    mask = pd.DataFrame(False, index=cal, columns=close.columns)
    mask.loc[new_dates[-1], "BBBY#0"] = False
    mask.loc[segs["BBBY#0"].index[-1], "BBBY#0"] = True
    race = ta.race_labels(close, mask)
    assert race.iloc[0]["censor_reason"] == "data_end"
    assert race.iloc[0]["sessions_available"] == 0


def test_sanity_segmented_arm_breaks_only_residual_three_x_up_jumps():
    """The repair threshold is inclusive and asymmetric; a collapse is evidence."""
    idx = _cal(5)
    bars = _bars(np.array([10.0, 29.0, 87.0, 1.0, 2.99]), idx)
    assert ta.residual_up_break_positions(bars["close"]).tolist() == [2]

    gap_only = ta.split_identity_segments({"ODD": bars}, idx)
    repaired = ta.split_identity_segments(
        {"ODD": bars}, idx,
        residual_up_ratio_break=ta.RESIDUAL_UP_RATIO_BREAK,
    )
    assert set(gap_only) == {"ODD"}
    assert set(repaired) == {"ODD#0", "ODD#1"}
    assert repaired["ODD#0"].index[-1] == idx[1]
    assert repaired["ODD#1"].index[0] == idx[2]
    assert idx[3] in repaired["ODD#1"].index, "the 98.9% collapse was screened"


def test_residual_up_identity_break_resets_history_features_and_races():
    """No EXT, feature lookback, or forward race may cross the repair-arm seam."""
    idx = _cal(600)
    first = _ramp(300, base=5.0, daily=0.005, seed=41)
    second = _ramp(300, base=first[-1] * 4.0, daily=0.005, seed=42)
    bars = _bars(np.r_[first, second], idx)
    segs = ta.split_identity_segments(
        {"RSPL": bars}, idx,
        residual_up_ratio_break=ta.RESIDUAL_UP_RATIO_BREAK,
    )
    assert set(segs) == {"RSPL#0", "RSPL#1"}

    close = pd.DataFrame({k: v["close"] for k, v in segs.items()}).reindex(idx)
    ext = ta.extended_mask(close, close * 5e6)
    new_dates = segs["RSPL#1"].index
    assert not ext["RSPL#1"].reindex(new_dates).iloc[:260].any()
    f = ta.feature_library(segs, None, {"RSPL#1": [new_dates[10]]})
    assert np.isnan(f["A3_r126"].iloc[0])

    old_end = segs["RSPL#0"].index[-1]
    mask = pd.DataFrame(False, index=idx, columns=close.columns)
    mask.loc[old_end, "RSPL#0"] = True
    race = ta.race_labels(close, mask)
    assert race.iloc[0]["censor_reason"] == "data_end"
    assert race.iloc[0]["sessions_available"] == 0


def _jump_series(n: int = 700, at: int = 400, ratio: float = 25.0) -> pd.Series:
    """A calm path with ONE bar planted at `at` whose close ratio is EXACTLY `ratio`.

    The step is planted exactly (rather than by scaling the tail) so the 3.0
    inclusive/exclusive boundary can be pinned without the drift and noise of the
    surrounding path moving the observed ratio off the threshold.
    """
    v = _ramp(n, base=20.0, daily=0.0004, seed=77)
    tail = v[at:] / v[at]
    v[at:] = (v[at - 1] * ratio) * tail
    return pd.Series(v, index=_cal(n))


def _repaired_segments(bars, cal, name: str = "PAVS") -> dict:
    return ta.split_identity_segments(
        {name: bars}, cal, residual_up_ratio_break=ta.RESIDUAL_UP_RATIO_BREAK)


def test_unrepaired_reverse_split_breaks_identity():
    """A 25x single bar is a corporate action, not a move — it must split the name."""
    s = _jump_series(ratio=25.0)
    cal = s.index
    bars = _bars(s.to_numpy(), cal, vol=_volumes(len(s), seed=5))
    segs = _repaired_segments(bars, cal)
    assert set(segs) == {"PAVS#0", "PAVS#1"}
    assert len(segs["PAVS#0"]) == 400 and len(segs["PAVS#1"]) == 300
    assert segs["PAVS#1"].index[0] == cal[400], "the jump bar starts the NEW identity"


@pytest.mark.parametrize("ratio,n_segments,why", [
    (25.0, 2, "a 25x bar is an unrepaired 1:25 reverse split"),
    (3.0, 2, "exactly 3.0x is INCLUSIVE"),
    (2.99, 1, "just under the floor stays one name"),
    (2.5, 1, "a 2.5x day is a violent but real move"),
])
def test_up_jump_threshold_truth_table(ratio, n_segments, why):
    s = _jump_series(ratio=ratio)
    bars = _bars(s.to_numpy(), s.index, vol=_volumes(len(s), seed=5))
    assert len(_repaired_segments(bars, s.index)) == n_segments, why


def test_a_real_crash_day_never_breaks_identity():
    """The DOWN side is deliberately unscreened — a −70% day is the real event."""
    s = _jump_series(ratio=0.30)                 # a 70% one-day collapse
    bars = _bars(s.to_numpy(), s.index, vol=_volumes(len(s), seed=5))
    assert ta.residual_up_break_positions(s).size == 0
    assert set(_repaired_segments(bars, s.index)) == {"PAVS"}


def test_gap_and_jump_rules_compose():
    """Both triggers on one ticker yield three independent names."""
    cal = _cal(900)
    keep = np.r_[np.arange(0, 300), np.arange(500, 900)]     # 200-session hole
    v = _ramp(len(keep), base=20.0, daily=0.0004, seed=78)
    v[500:] = v[500:] * 30.0                                 # a jump inside part 2
    bars = _bars(v, cal[keep], vol=_volumes(len(keep), seed=6))
    segs = _repaired_segments(bars, cal, name="DUAL")
    assert set(segs) == {"DUAL#0", "DUAL#1", "DUAL#2"}
    assert len(segs["DUAL#0"]) == 300                        # pre-gap
    assert sum(len(b) for b in segs.values()) == len(keep)   # nothing lost


def test_jump_rule_can_be_disabled_to_reproduce_the_pre_repair_arm():
    s = _jump_series(ratio=25.0)
    bars = _bars(s.to_numpy(), s.index, vol=_volumes(len(s), seed=8))
    segs = ta.split_identity_segments({"PAVS": bars}, s.index,
                                      residual_up_ratio_break=None)
    assert set(segs) == {"PAVS"}, "the pre-repair arm must still be reproducible"


# ══════════════════════════════════════════════════════════════════════════════
# §3 RAW-LEVEL ELIGIBILITY + the full-series-vs-prefix parity HARD GATE
# ══════════════════════════════════════════════════════════════════════════════
def _split_world(n: int = 700, split_at: int = 600, ratio: float = 10.0):
    """An EXTENDED name trading just over $3 that then does a 10:1 split late on.

    Raw prints clear the $3 floor at d; the REPAIRED pre-split closes are ten times
    smaller, so an adjusted-price floor would retroactively evict every pre-split day
    the moment the split prints — the leak §3 closes. The ramp is steep enough that d
    is a genuine EXT day inside an episode, so the F-family is live rather than null.
    """
    idx = _cal(n)
    raw = pd.Series(_ramp(n, base=0.35, daily=0.006, seed=42), index=idx)
    raw.iloc[split_at:] = raw.iloc[split_at:] / ratio
    vol = pd.Series(_volumes(n, seed=43), index=idx) * 40.0
    return idx, pd.DataFrame({"close": raw, "volume": vol,
                              "high": raw * 1.01, "low": raw * 0.99,
                              "open": raw.shift(1).fillna(raw.iloc[0])})


def test_eligibility_floors_read_raw_prints_not_repaired_ones():
    """A future 10:1 split must not evict pre-split days through the price floor."""
    idx, bars = _split_world()
    rep = rh.repair_bars(bars)
    close = pd.DataFrame({"T": rep["close"]})
    dvol = pd.DataFrame({"T": rep["close"] * rep["volume"]})
    raw_c = pd.DataFrame({"T": rep["raw_close"]})
    raw_dv = pd.DataFrame({"T": rep["raw_dvol"]})
    step = pd.DataFrame({"T": rep["split_day"]})

    pre = idx[500]                                   # a pre-split day
    assert rep["raw_close"].loc[pre] >= ta.MIN_CLOSE
    assert rep["close"].loc[pre] < ta.MIN_CLOSE, "the repair must scale it under $3"

    on_raw = ta.eligibility_mask(close, dvol, raw_close_df=raw_c,
                                 raw_dollar_vol_df=raw_dv, split_day_df=step)
    on_adjusted = ta.eligibility_mask(close, dvol)    # the leaky comparison
    assert bool(on_raw.loc[pre, "T"]), "raw-level eligibility lost a pre-split day"
    assert not bool(on_adjusted.loc[pre, "T"]), \
        "the adjusted-price floor no longer evicts the day — this test is vacuous"


def test_split_factor_step_day_is_ineligible_and_the_days_before_it_survive():
    idx, bars = _split_world()
    rep = rh.repair_bars(bars)
    close = pd.DataFrame({"T": rep["close"]})
    dvol = pd.DataFrame({"T": rep["close"] * rep["volume"]})
    kw = dict(raw_close_df=pd.DataFrame({"T": rep["raw_close"]}),
              raw_dollar_vol_df=pd.DataFrame({"T": rep["raw_dvol"]}),
              split_day_df=pd.DataFrame({"T": rep["split_day"]}))
    elig = ta.eligibility_mask(close, dvol, **kw)
    steps = list(rep.index[rep["split_day"].to_numpy(dtype=bool)])
    assert steps, "the fixture must actually produce a factor step day"
    for sd in steps:
        assert not bool(elig.loc[sd, "T"]), "the split-factor step day must be ineligible"
    prior = idx[idx.get_loc(steps[0]) - 1]
    assert bool(elig.loc[prior, "T"]), \
        "the day BEFORE the split was retro-removed using future information"


def test_split_factor_carries_to_full_ohlcv_and_dollar_volume_is_invariant():
    """Factor DIVIDES open/high/low/close and MULTIPLIES volume (§3)."""
    _, bars = _split_world()
    rep = rh.repair_bars(bars)
    assert (rep["close"] <= rep["raw_close"] + 1e-12).all()
    for c in ("open", "high", "low"):
        ratio = (bars[c] / rep[c]).dropna()
        assert np.allclose(ratio, bars["close"] / rep["close"], rtol=1e-12), \
            f"{c} did not take the same factor as close"
    pd.testing.assert_series_equal(rep["close"] * rep["volume"], rep["raw_dvol"],
                                   check_names=False, rtol=1e-12)


def _parity_eqw(idx: pd.DatetimeIndex) -> pd.Series:
    """A fixed, drifting cross-section for the parity check.

    Held identical on both sides because one name's split repair cannot move a
    median-daily-return index (see `_parity_side`); drifting rather than flat so
    `rs_line = c / index` is not just a copy of the close and the E-family is
    genuinely exercised.
    """
    return pd.Series(1.0005 ** np.arange(len(idx)), index=idx)


PARITY_FAMILY_FEATURES = [
    "A6_ext_ma200_atr21",   # A — a level difference over an ATR, both factor-scaled
    "B2_rsi14",             # B — recursive smoothing of price differences
    "C1_rv21",              # C — log-return dispersion
    "D1_dvol_z",            # D — dollar-volume z (invariant only if the carry is right)
    "E5f_rs_decel",         # E — log-slope change of the RS line
    "F2_drawdown_in_episode",  # F — episode-anchored ratio
]


@pytest.mark.parametrize("feature", PARITY_FAMILY_FEATURES)
def test_full_series_vs_prefix_parity_at_every_family(feature):
    """§3 HARD GATE: a split AFTER d may not move the feature value AT d.

    Both sides run through the harness's real repair path (`repair_bars`), because a
    parity check against a re-implementation would prove nothing about the repair the
    study actually uses. The prefix stops just after d, so it cannot see the later
    split and recovers a different factor for every bar ≤ d — if any feature moves
    with that, the repair is leaking the future into a "point-in-time" value.
    """
    idx, bars = _split_world()
    d = idx[500]                                     # 100 sessions before the split
    rep = rh.prefix_parity_report(bars, d, _parity_eqw(idx)).set_index("feature")
    row = rep.loc[feature]
    assert not row["null_both"], f"{feature} is null on both sides — vacuous"
    assert row["abs_gap"] <= rh.PARITY_TOLERANCE, (
        f"{feature} moved when a FUTURE split was revealed: "
        f"full={row['full']!r} prefix={row['prefix']!r}")


def test_prefix_parity_covers_all_six_families():
    assert {f[0] for f in PARITY_FAMILY_FEATURES} == set("ABCDEF")


def test_prefix_parity_gate_fires_on_a_planted_leak():
    """The gate is only worth something if a future-reading feature fails it."""
    idx, bars = _split_world()
    d = idx[500]
    full = rh.repair_bars(bars)
    prefix = rh.repair_bars(bars.iloc[:idx.get_loc(d) + 2])
    # a "feature" that reads the repaired LEVEL rather than a ratio is exactly what
    # the split factor moves — this is the failure mode the gate exists to catch.
    assert not np.isclose(full["close"].loc[d], prefix["close"].loc[d]), \
        "the fixture no longer changes the recovered factor — the gate is untested"


# ── §6 contamination audit: the pre-repair measurement, never a spurious zero ──
def test_jump_table_names_the_fabricated_bars_and_maps_their_positions():
    idx = _cal(6)
    close = pd.DataFrame({
        "PAVS": pd.Series([2.0, 2.1, 52.5, 53.0, 54.0, 55.0], index=idx),
        "CALM": pd.Series([10.0, 10.1, 10.2, 10.3, 10.4, 10.5], index=idx),
    })
    jumps, pos_map = rh.jump_table(close)
    assert list(pos_map) == ["PAVS"] and pos_map["PAVS"].tolist() == [2]
    assert len(jumps) == 1
    row = jumps.iloc[0]
    assert row["ticker"] == "PAVS" and row["date"] == idx[2]
    assert row["ratio"] == pytest.approx(52.5 / 2.1)


def test_contamination_audit_refuses_a_sanity_segmented_cache(tmp_path):
    """A repaired panel holds zero jumps BY CONSTRUCTION — reporting that reads as
    "run-1 was clean", which is the opposite of the measurement."""
    idx = _cal(6)
    pd.DataFrame({"T": pd.Series(np.linspace(10.0, 12.0, 6), index=idx)}).to_parquet(
        tmp_path / "panel_close.parquet")
    (tmp_path / "meta.json").write_text(json.dumps(
        {"residual_up_ratio_break": ta.RESIDUAL_UP_RATIO_BREAK}))
    out = rh.run1_contamination_audit(tmp_path)
    assert out["available"] is False
    assert "sanity-segmented" in out["reason"]
    assert "n_jump_days" not in out, "a structural zero must never print as a count"


@pytest.mark.parametrize("meta", [
    {"identity_rules": {"max_gap_sessions": 60, "jump_ratio": 3.0}},
    {"repair_arm": "sanity-segmented"},
    {"n_segments": 3},                       # unstamped: caught empirically below
])
def test_contamination_audit_never_reports_a_jumpless_panel(tmp_path, meta):
    """Both repaired-stamp formats AND an unstamped repaired panel are refused."""
    idx = _cal(6)
    pd.DataFrame({"T": pd.Series(np.linspace(10.0, 12.0, 6), index=idx)}).to_parquet(
        tmp_path / "panel_close.parquet")
    (tmp_path / "meta.json").write_text(json.dumps(meta))
    out = rh.run1_contamination_audit(tmp_path)
    assert out["available"] is False and "n_jump_days" not in out


def test_preserved_contamination_carries_the_recorded_numbers_with_provenance(
        tmp_path, monkeypatch):
    src = tmp_path / "preserved.json"
    src.write_text(json.dumps({"repair_arm": {"contamination": {
        "available": True, "n_jump_days": 1264, "recomputed_this_run": True}}}))
    monkeypatch.setattr(rh, "_REPO", tmp_path)
    out = rh.preserved_contamination(src, "no pre-repair panel on disk")
    assert out["n_jump_days"] == 1264
    assert out["recomputed_this_run"] is False
    assert "preserved artifact" in out["provenance"]
    assert out["live_audit_unavailable_reason"] == "no pre-repair panel on disk"


def test_preserved_contamination_declines_an_unavailable_block(tmp_path):
    src = tmp_path / "preserved.json"
    src.write_text(json.dumps({"repair_arm": {"contamination": {"available": False}}}))
    assert rh.preserved_contamination(src) is None
    assert rh.preserved_contamination(tmp_path / "missing.json") is None


@pytest.mark.parametrize("meta,want,why", [
    ({"residual_up_ratio_break": 3.0}, 3.0, "an exact stamp match is a hit"),
    ({"residual_up_ratio_break": None}, None, "gap-only matches a gap-only stamp"),
    ({"residual_up_ratio_break": 3.0}, None, "W's rule may not serve gap-only D"),
    ({"residual_up_ratio_break": None}, 3.0, "a gap-only panel may not serve W"),
    ({"identity_rules": {"jump_ratio": 3.0}}, 3.0, "another line's stamp is unstamped"),
    ({"identity_rules": {"jump_ratio": 3.0}}, None, "same, requested gap-only"),
])
def test_panel_cache_is_reused_only_under_its_own_identity_rule(tmp_path, meta, want, why):
    """An absent or different stamp REBUILDS — never runs a track on another line's panel."""
    idx = _cal(4)
    for leg in rh._REQUIRED_PANEL_LEGS:
        pd.DataFrame({"T": pd.Series(np.linspace(10.0, 11.0, 4), index=idx)}).to_parquet(
            tmp_path / f"panel_{leg}.parquet")
    (tmp_path / "meta.json").write_text(json.dumps(meta))
    got = rh._load_cached(tmp_path, residual_up_ratio_break=want)
    hit = meta.get("residual_up_ratio_break", "absent") == want
    assert (got is not None) is hit, why


def test_todays_tape_appendix_is_uncapped():
    """G0.5 is a COVERAGE gate — run-1's defect was found by reading the whole cohort."""
    assert rh.TODAY_TAPE_CAP is None


# ══════════════════════════════════════════════════════════════════════════════
# (e) §4.5 matching bucket integrity
# ══════════════════════════════════════════════════════════════════════════════
def _matching_fixture(seed: int = 4):
    rng = np.random.default_rng(seed)
    n = 400
    dates = pd.to_datetime(rng.choice(pd.bdate_range("2022-01-03", periods=500), n))
    pool = pd.DataFrame({
        "case_id": [f"c{i}" for i in range(n)],
        "segment": [f"S{i%40}" for i in range(n)],
        "ticker": [f"S{i%40}" for i in range(n)],
        "date": dates,
        "r126": rng.uniform(0.5, 3.0, n),
        "rv63": rng.uniform(0.2, 1.5, n),
        "dvol21": rng.uniform(2e6, 5e8, n),
    })
    cases = pool.iloc[:40].copy()
    cases["case_id"] = [f"K{i}" for i in range(40)]
    return cases, pool.iloc[40:].copy()


def test_matching_never_crosses_a_bucket():
    cases, pool = _matching_fixture()
    pairs, diag = ta.matched_controls(cases, pool)
    assert not pairs.empty
    # rebuild the bucket labels the matcher used and confirm every pair agrees
    both = pd.concat([cases.assign(_arm="case"), pool.assign(_arm="control")],
                     ignore_index=True)
    both["quarter"] = pd.PeriodIndex(pd.to_datetime(both["date"]), freq="Q").astype(str)
    for col, q, out in (("r126", 5, "b_r126"), ("rv63", 3, "b_rv63"), ("dvol21", 3, "b_dvol")):
        both[out] = ta._bucket(both, col, q, out)
    lab = both.set_index(["segment", "date"])[["quarter", "b_r126", "b_rv63", "b_dvol"]]
    lab = lab[~lab.index.duplicated()]
    for _, r in pairs.iterrows():
        ctrl = lab.loc[(r["control_segment"], r["control_date"])]
        assert ctrl["quarter"] == r["quarter"]
        assert ctrl["b_r126"] == r["b_r126"]
        assert ctrl["b_rv63"] == r["b_rv63"]
        assert ctrl["b_dvol"] == r["b_dvol"]
    assert diag["n_cases"] == 40
    assert diag["n_matched"] + diag["n_dropped_no_control"] == 40


def test_matching_is_without_replacement_within_a_case_and_excludes_self():
    cases, pool = _matching_fixture(seed=8)
    pairs, _ = ta.matched_controls(cases, pool)
    for cid, g in pairs.groupby("case_id"):
        keys = list(zip(g["control_segment"], g["control_date"]))
        assert len(keys) == len(set(keys)), f"{cid} reused a control"
        assert len(keys) <= ta.MAX_CONTROLS
        assert (g["control_ticker"] != g["ticker"]).all(), f"{cid} matched its own name"


def test_matching_counts_zero_control_cases_instead_of_hiding_them():
    cases = pd.DataFrame([{
        "case_id": "K0", "segment": "A", "ticker": "A", "date": pd.Timestamp("2022-02-01"),
        "r126": 1.0, "rv63": 0.5, "dvol21": 1e7}])
    pool = pd.DataFrame([{                       # different quarter -> unmatchable
        "case_id": "c0", "segment": "B", "ticker": "B", "date": pd.Timestamp("2023-08-01"),
        "r126": 1.0, "rv63": 0.5, "dvol21": 1e7}])
    pairs, diag = ta.matched_controls(cases, pool)
    assert pairs.empty
    assert diag["n_dropped_no_control"] == 1 and diag["n_matched"] == 0


def test_matching_buckets_never_split_identical_values_by_row_order():
    """Tied gates are one economic value, not artificial arm/order quantiles."""
    f = pd.DataFrame({
        "quarter": ["2022Q1"] * 12,
        "r126": [1.0] * 12,
    })
    out = ta._bucket(f, "r126", 5, "b_r126")
    assert out.notna().all()
    assert out.nunique() == 1
    assert out.iloc[0] == 0


def _episode_delta_frame(n: int = 120, **planted) -> pd.DataFrame:
    """An episode-level Δ frame: one row per episode, keyed on its peak date."""
    peaks = pd.bdate_range("2022-01-03", periods=n, freq="7D")
    return pd.DataFrame({
        "episode_id": [f"E{i}" for i in range(n)],
        "ticker": [f"T{i%20}" for i in range(n)],
        "peak_date": peaks, "date": peaks, "n_snapshots": 3, **planted})


def test_matched_delta_stats_are_deterministic_and_fdr_corrected():
    rng = np.random.default_rng(3)
    n = 120
    d = _episode_delta_frame(
        n,
        A5_ext_ma50_atr21=rng.normal(1.5, 0.5, n),    # planted, declared direction +1
        A6_ext_ma200_atr21=rng.normal(0.0, 0.5, n))   # null
    cols = ["A5_ext_ma50_atr21", "A6_ext_ma200_atr21"]
    a = ta.matched_delta_stats(d, cols, b=200, seed=11)
    b = ta.matched_delta_stats(d, cols, b=200, seed=11)
    pd.testing.assert_frame_equal(a, b)
    row = a.set_index("feature").loc["A5_ext_ma50_atr21"]
    assert row["ci_lo"] > 0 and row["separates"] and row["grade"] == "REGISTERED"
    assert not a.set_index("feature").loc["A6_ext_ma200_atr21"]["separates"]
    assert (a["q_value"] >= a["p_value"] - 1e-12).all()
    assert (a["block_key"] == "peak_date").all(), "blocks must be episode-PEAK months"


def test_wrong_signed_move_never_separates():
    """A feature that moves the OPPOSITE way from its pre-declaration is not a survivor."""
    rng = np.random.default_rng(5)
    n = 120
    d = _episode_delta_frame(n, F1_episode_age=rng.normal(-3.0, 0.5, n))  # declared +1
    out = ta.matched_delta_stats(d, ["F1_episode_age"], b=200, seed=11)
    assert out.iloc[0]["ci_hi"] < 0
    assert not out.iloc[0]["separates"]
    assert out.iloc[0]["grade"] == ""


def test_exploratory_field_can_only_be_discovery_grade():
    """A direction-0 field may flag as a separator but can never be DETECTION (§4.5)."""
    rng = np.random.default_rng(6)
    n = 120
    d = _episode_delta_frame(n, A1_r21=rng.normal(2.0, 0.4, n))   # direction 0
    out = ta.matched_delta_stats(d, ["A1_r21"], b=200, seed=11).iloc[0]
    assert out["separates"] and out["grade"] == "EXPLORATORY-DISCOVERY"


def test_registered_separation_needs_twelve_distinct_peak_months():
    """§4.5's ≥12-peak-month floor: a strong effect inside one quarter is not enough."""
    rng = np.random.default_rng(7)
    n = 90
    d = _episode_delta_frame(n, A5_ext_ma50_atr21=rng.normal(2.0, 0.3, n))
    d["peak_date"] = pd.bdate_range("2022-01-03", periods=n, freq="D")   # ~4 months
    thin = ta.matched_delta_stats(d, ["A5_ext_ma50_atr21"], b=200, seed=11).iloc[0]
    assert thin["n_blocks"] < ta.MIN_EPISODE_MONTHS
    assert not thin["separates"], "a 4-month sample cleared the 12-peak-month floor"
    d["peak_date"] = pd.bdate_range("2022-01-03", periods=n, freq="14D")  # ~3.5 years
    wide = ta.matched_delta_stats(d, ["A5_ext_ma50_atr21"], b=200, seed=11).iloc[0]
    assert wide["n_blocks"] >= ta.MIN_EPISODE_MONTHS and wide["separates"]


# ══════════════════════════════════════════════════════════════════════════════
# §4.5 episode-first aggregation and the ≥2-finite-controls rule
# ══════════════════════════════════════════════════════════════════════════════
def _pairs_and_panel(control_values: dict[str, list[float]], case_value: float = 10.0):
    """One case with hand-picked control values, so the Δ is computable by eye."""
    day = pd.Timestamp("2022-03-01")
    rows = [{"segment": "CASE", "date": day, "A1_r21": case_value, "ticker": "CASE"}]
    pairs = []
    for i, (seg, vals) in enumerate(control_values.items()):
        rows.append({"segment": seg, "date": day, "A1_r21": vals[0], "ticker": seg})
        pairs.append({"case_id": "K0", "segment": "CASE", "ticker": "CASE", "date": day,
                      "control_segment": seg, "control_ticker": seg, "control_date": day})
    return pd.DataFrame(pairs), pd.DataFrame(rows)


def test_delta_needs_the_case_and_at_least_two_finite_controls():
    pairs, panel = _pairs_and_panel({"C1": [4.0], "C2": [6.0]})
    d = ta.matched_deltas(pairs, panel, ["A1_r21"])
    assert d.iloc[0]["A1_r21"] == pytest.approx(10.0 - 5.0)      # mean(4,6) = 5
    pairs1, panel1 = _pairs_and_panel({"C1": [4.0], "C2": [np.nan]})
    d1 = ta.matched_deltas(pairs1, panel1, ["A1_r21"])
    assert pd.isna(d1.iloc[0]["A1_r21"]), \
        "one finite control is a comparison, not a matched set — §4.5 wants >=2"


def test_episode_first_aggregation_collapses_snapshots_before_pooling():
    """Three offsets of ONE episode must count once, at their MEDIAN (§4.5)."""
    case_deltas = pd.DataFrame({
        "case_id": ["E1@21", "E1@10", "E1@5", "E2@5"],
        "ticker": ["A", "A", "A", "B"],
        "date": pd.to_datetime(["2022-01-03", "2022-01-14", "2022-01-21", "2022-05-02"]),
        "A1_r21": [1.0, 5.0, 9.0, 100.0],
    })
    cases = pd.DataFrame({
        "case_id": ["E1@21", "E1@10", "E1@5", "E2@5"],
        "episode_id": ["E1", "E1", "E1", "E2"]})
    episodes = pd.DataFrame({
        "episode_id": ["E1", "E2"],
        "peak_date": pd.to_datetime(["2022-01-28", "2022-05-09"])})
    ep = ta.episode_deltas(case_deltas, cases, episodes, ["A1_r21"])
    assert len(ep) == 2, "four snapshots must collapse to two episodes"
    e1 = ep.set_index("episode_id").loc["E1"]
    assert e1["A1_r21"] == pytest.approx(5.0)      # median(1, 5, 9)
    assert e1["n_snapshots"] == 3
    assert e1["peak_date"] == pd.Timestamp("2022-01-28"), "peak date drives the block"
    # pooling at snapshot level would have let one episode's three looks outvote the
    # other episode entirely — a different, over-weighted answer
    assert float(case_deltas["A1_r21"].median()) == pytest.approx(7.0)
    assert float(ep["A1_r21"].median()) == pytest.approx(52.5)


def test_bh_fdr_matches_the_textbook_step_up():
    q = ta.bh_fdr([0.01, 0.02, 0.03, 0.9])
    assert np.allclose(q, [0.04, 0.04, 0.04, 0.9])
    assert np.isnan(ta.bh_fdr([np.nan])[0])


# ══════════════════════════════════════════════════════════════════════════════
# (f) §2 the top ruler, on an episode whose answers are computable by eye
# ══════════════════════════════════════════════════════════════════════════════
def test_top_ruler_on_a_hand_built_episode():
    idx = _cal(11)
    # peak of 200 on bar 6; fire on bar 2 (100) and bar 5 (195)
    path = [100.0, 120.0, 100.0, 150.0, 170.0, 195.0, 200.0, 170.0, 150.0, 140.0, 130.0]
    close = pd.DataFrame({"T": pd.Series(path, index=idx)})
    episodes = pd.DataFrame([{
        "segment": "T", "ticker": "T", "episode_id": "T|ep", "start": idx[0],
        "end": idx[10], "peak_date": idx[6], "peak_close": 200.0}])
    fires = pd.DataFrame(False, index=idx, columns=["T"])
    fires.loc[idx[2], "T"] = True      # 100 -> +100.00% remaining, 4 sessions early
    fires.loc[idx[5], "T"] = True      # 195 -> +  2.56% remaining, 1 session early
    r = ta.top_ruler(fires, episodes, close, fwd_horizon=2, b=50)
    assert r["n_fires"] == 2
    # per-name median of {1.0000, 0.0256}
    assert r["median_remaining_upside"] == pytest.approx((1.0 + (200.0 / 195.0 - 1.0)) / 2,
                                                         rel=1e-9)
    # only the 195 fire is within 5% of the 200 peak -> per-name median of {0,1} = 0.5
    assert r["share_within_peak_price"] == pytest.approx(0.5)
    assert r["share_within_peak_time"] == pytest.approx(1.0)   # both within +/-10 sessions
    assert r["n_fire_episodes"] == 1 and r["n_fire_names"] == 1


def test_top_ruler_prices_a_late_warning_worse_than_an_early_one():
    idx = _cal(11)
    path = [100.0, 110.0, 130.0, 150.0, 170.0, 190.0, 200.0, 180.0, 160.0, 150.0, 140.0]
    close = pd.DataFrame({"T": pd.Series(path, index=idx)})
    episodes = pd.DataFrame([{
        "segment": "T", "ticker": "T", "episode_id": "T|ep", "start": idx[0],
        "end": idx[10], "peak_date": idx[6], "peak_close": 200.0}])
    early = pd.DataFrame(False, index=idx, columns=["T"]); early.loc[idx[1], "T"] = True
    late = pd.DataFrame(False, index=idx, columns=["T"]); late.loc[idx[5], "T"] = True
    assert (ta.top_ruler(early, episodes, close, b=0)["median_remaining_upside"]
            > ta.top_ruler(late, episodes, close, b=0)["median_remaining_upside"])


def test_top_ruler_share_is_within_name_mean_not_boolean_median():
    idx = _cal(8)
    path = [100.0, 110.0, 120.0, 150.0, 180.0, 195.0, 200.0, 190.0]
    close = pd.DataFrame({"T": pd.Series(path, index=idx)})
    episodes = pd.DataFrame([{
        "segment": "T", "ticker": "T", "episode_id": "T|ep", "start": idx[0],
        "end": idx[-1], "peak_date": idx[6], "peak_close": 200.0}])
    fires = pd.DataFrame(False, index=idx, columns=["T"])
    fires.loc[[idx[0], idx[1], idx[5]], "T"] = True
    r = ta.top_ruler(fires, episodes, close, b=0)
    assert r["share_within_peak_price"] == pytest.approx(1.0 / 3.0)


# ══════════════════════════════════════════════════════════════════════════════
# (g) §4.4 episode peak / TOPPED semantics
# ══════════════════════════════════════════════════════════════════════════════
def _episode_outcome(path: list[float], *, seal: int = 126, buffer: int = 63):
    idx = _cal(len(path))
    close = pd.DataFrame({"T": pd.Series(path, index=idx, dtype=float)})
    eps = pd.DataFrame([{
        "segment": "T", "ticker": "T", "episode_id": "T|ep",
        "start": idx[0], "end": idx[min(4, len(path) - 1)], "n_ext_days": 5,
        "span_sessions": 5, "micro": False}])
    out, dtp = ta.episode_peaks(close, eps, seal_window=seal, peak_buffer=buffer)
    return out.iloc[0], dtp


def test_episode_peak_and_topped():
    row, dtp = _episode_outcome([10, 12, 14, 16, 18, 20, 19, 17, 15.9])
    assert row["peak_close"] == 20.0
    assert row["outcome"] == "TOPPED"          # 15.9 <= 0.80 * 20
    assert not row["peak_window_censored"]
    assert list(dtp["days_to_peak"]) == [5, 4, 3, 2, 1]   # the 5 EXT days precede the peak


def test_episode_survives_without_a_twenty_percent_print():
    row, _ = _episode_outcome([10, 12, 14, 16, 18, 20, 19, 18, 17])
    assert row["outcome"] == "SURVIVED"


def test_intervening_new_high_voids_the_top():
    """§4.4's no-intervening-new-high clause: a new high resets the episode's top."""
    topped, _ = _episode_outcome([10, 12, 14, 16, 18, 20, 18, 16.0])
    assert topped["outcome"] == "TOPPED"
    # same collapse, but a new high prints FIRST -> the peak moves and there is no top
    voided, _ = _episode_outcome([10, 12, 14, 16, 18, 20, 25, 21, 20.5])
    assert voided["peak_close"] == 25.0
    assert voided["outcome"] == "SURVIVED"


def test_episode_peak_uses_the_63_session_buffer_after_the_episode():
    path = [10, 12, 14, 16, 18] + [18 + i for i in range(1, 30)]
    row, _ = _episode_outcome(path)
    assert row["peak_date"] > row["end"], "the peak may land after the last EXT day"
    assert row["peak_close"] == max(path)


def test_censored_seal_window_is_flagged_not_hidden():
    row, _ = _episode_outcome([10, 12, 14, 16, 18, 20, 19], seal=126)
    assert row["outcome"] == "SURVIVED"
    assert bool(row["peak_window_censored"])


# ══════════════════════════════════════════════════════════════════════════════
# feature-library sanity + coverage honesty
# ══════════════════════════════════════════════════════════════════════════════
def test_feature_library_emits_all_36_features_with_nulls_preserved():
    idx = _cal(700)
    close, dvol = _panel({"N0": _ramp(700, seed=21)}, idx)
    eqw = ta.equal_weight_median_index(close)
    bars_full = {"N0": _bars(close["N0"].to_numpy(dtype=float), idx)}
    bars_thin = {"N0": bars_full["N0"][["close", "high", "low"]]}   # no open, no volume
    d = idx[650]
    full = ta.feature_library(bars_full, eqw, {"N0": [d]})
    thin = ta.feature_library(bars_thin, eqw, {"N0": [d]})
    assert list(full.columns) == ["segment", "ticker", "date", *ta.FEATURES,
                                  ta.F5_UNRECLAIMED_COL]
    assert len(ta.FEATURES) == 36
    assert full[list(ta.FEATURES)].notna().sum(axis=1).iloc[0] >= 30
    for col in ("C5_gap_freq21", "D1_dvol_z", "D3_updown_dvol_ratio21", "D6_churn21"):
        assert pd.isna(thin[col].iloc[0]), f"{col} must be NULL without its input, not 0"
    assert np.isfinite(thin["A3_r126"].iloc[0])


def test_feature_directions_cover_every_feature_exactly_once():
    assert set(ta.FEATURE_DIRECTION) == set(ta.FEATURES)
    assert set(ta.FEATURE_FAMILY.values()) == set("ABCDEF")
    sizes = pd.Series(ta.FEATURE_FAMILY).value_counts().to_dict()
    assert sizes == {"A": 8, "B": 6, "C": 6, "D": 6, "E": 5, "F": 5}


def test_equal_weight_index_is_rebased_and_composition_proof():
    idx = _cal(50)
    a = np.full(50, 100.0)
    b = np.full(50, 10.0)
    b[25:] *= 1.5                       # one name steps 50% at bar 25
    close = pd.DataFrame({"A": pd.Series(a, index=idx), "B": pd.Series(b, index=idx)})
    eqw = ta.equal_weight_median_index(close)
    assert eqw.iloc[0] == pytest.approx(1.0)
    # a level jump in ONE of two names moves the median return only on that bar
    assert eqw.iloc[24] == pytest.approx(eqw.iloc[0], rel=1e-12)
    assert eqw.iloc[-1] == pytest.approx(eqw.iloc[25], rel=1e-12)


def test_relative_return_features_use_literal_cross_sectional_medians():
    idx = _cal(300)
    c = pd.Series(10.0 * np.exp(np.arange(300) * 0.004), index=idx)
    bars = {"T": _bars(c.to_numpy(), idx)}
    eqw = pd.Series(1.0, index=idx)
    cross = pd.DataFrame({"r21": 0.07, "r63": 0.19}, index=idx)
    d = idx[-1]
    f = ta.feature_library(
        bars, eqw, {"T": [d]}, cross_sectional_returns=cross)
    assert f.loc[0, "E1f_xr63"] == pytest.approx(f.loc[0, "A2_r63"] - 0.19)
    assert f.loc[0, "E2f_xr21"] == pytest.approx(f.loc[0, "A1_r21"] - 0.07)


def test_b6_streak_is_bounded_inside_the_twenty_one_session_window():
    idx = _cal(80)
    close = np.arange(10.0, 90.0)  # 79 consecutive up days
    f = ta.feature_library({"T": _bars(close, idx)}, pd.Series(1.0, index=idx),
                           {"T": [idx[-1]]})
    assert f.loc[0, "B6_max_up_streak21"] == 21


def test_cross_sectional_median_returns_are_same_day_and_eligibility_masked():
    idx = _cal(70)
    close = pd.DataFrame({
        "A": np.linspace(100, 170, 70),
        "B": np.linspace(100, 135, 70),
        "C": np.linspace(100, 107, 70),
    }, index=idx)
    eligible = pd.DataFrame(True, index=idx, columns=close.columns)
    eligible.loc[idx[-1], "C"] = False
    x = ta.cross_sectional_median_returns(close, eligible, windows=(63,))
    expected = np.median([
        close.loc[idx[-1], "A"] / close.loc[idx[-64], "A"] - 1.0,
        close.loc[idx[-1], "B"] / close.loc[idx[-64], "B"] - 1.0,
    ])
    assert x.loc[idx[-1], "r63"] == pytest.approx(expected)


# ══════════════════════════════════════════════════════════════════════════════
# import isolation — the engine module must not drag repo config into a test run
# ══════════════════════════════════════════════════════════════════════════════
def test_module_imports_without_touching_repo_config():
    """`engine.top_anatomy` is pure: no lib.config, no engine.run, no data store."""
    code = (
        "import sys; import engine.top_anatomy as t;"
        "bad=[m for m in ('lib.config','engine.run','lib') if m in sys.modules];"
        "print('LOADED:'+','.join(bad)); assert t.MIN_CLOSE==3.0"
    )
    r = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert "LOADED:\n" in r.stdout, f"engine.top_anatomy pulled in repo config: {r.stdout}"


def test_no_directional_or_exit_language_in_the_module():
    """AVOID-not-SHORT (DNR:KILL-DIRECTIONAL-SHORTING); no exit rules; no "validated".

    Disclaimers are allowed and expected ("no exit rules anywhere in this
    program") — what is banned is AFFIRMATIVE directional or exit vocabulary that
    would let a downstream surface inherit a call this program never makes.
    """
    src = (REPO / "engine" / "top_anatomy.py").read_text().lower()
    for banned in ("validated", "sell signal", "go short", "short position",
                   "stop loss", "stop-loss", "take profit", "price target"):
        assert banned not in src, f"forbidden phrase in the module: {banned!r}"
    flat = " ".join(src.split())
    assert "avoid-not-short" in flat, "the module must state its own scope fence"
    assert "zero scored authority" in flat
