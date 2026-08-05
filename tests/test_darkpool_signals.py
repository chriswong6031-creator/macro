"""engine/darkpool_signals — the metric layer under the Dark Pool desk.

Each test pins a defect that was live before 2026-08-05, so a regression here fails
loudly rather than shipping a plausible-looking number.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.darkpool_signals import (
    NameMetrics,
    _pattern,
    market_gauge,
    share_break_index,
    streak_above_norm,
    trailing_z,
    unusualness,
    usable_history,
    venue_split,
)


# ---------------------------------------------------------------------------
# trailing_z — the current observation must not set its own baseline
# ---------------------------------------------------------------------------

def test_trailing_z_excludes_the_current_observation():
    """v1 z-scored today against a mean/σ that INCLUDED today, so a genuine spike
    inflated its own σ and dragged the mean toward itself.

    Pinned on the mean/σ path deliberately: that is where v1's bug lived and where
    inclusion is materially damping. Under median/MAD one extra point moves the
    centre by half a rank, so a robust-path assertion cannot see the difference —
    an earlier version of this test asserted it there and passed against a mutant
    that included the current observation.
    """
    base = [0.0, 1.0] * 40                      # mean 0.5, population σ 0.5
    z = trailing_z(base + [10.0], min_obs=40, robust=False)
    assert z == pytest.approx((10.0 - 0.5) / 0.5, rel=1e-6), \
        "baseline must be exactly the observations BEFORE the current one"

    # Same series scored with the current value folded in gives a visibly smaller z.
    folded = pd.Series(base + [10.0])
    mu, sd = folded.mean(), folded.std(ddof=0)
    assert (10.0 - mu) / sd < z * 0.7, "fixture does not separate the two definitions"


def test_trailing_z_robust_path_matches_median_mad_of_the_prior_window():
    """The default path is median/MAD; pin it analytically so the scale cannot
    silently change to mean/σ."""
    base = [0.0, 1.0] * 40                      # median 0.5, MAD 0.5
    z = trailing_z(base + [10.0], min_obs=40)
    # trailing_z rounds to 2dp, so compare at that resolution rather than rel=1e-6.
    assert z == pytest.approx((10.0 - 0.5) / (0.5 * 1.4826), abs=0.01)


def test_trailing_z_returns_none_not_zero_when_history_is_thin():
    """A null means 'not enough history to say'. Zero would read as 'perfectly normal'
    and would sort into the middle of the desk instead of being disclosed."""
    assert trailing_z([0.3] * 10, min_obs=40) is None
    assert trailing_z([], min_obs=40) is None


def test_trailing_z_returns_none_on_a_constant_series():
    """No dispersion ⇒ z is undefined. Returning 0.0 would claim normality."""
    assert trailing_z([0.25] * 300) is None


def test_trailing_z_is_robust_to_a_single_outlier_in_the_baseline():
    """Median/MAD, not mean/σ: one index-rebalance day in the baseline must not
    blow out the scale and hide every later move."""
    rng = np.random.default_rng(3)
    base = list(rng.normal(0.30, 0.01, 200))
    base[50] = 0.95                       # one absurd day inside the baseline
    z = trailing_z(base + [0.36])
    assert z is not None and z > 3, f"outlier in baseline swamped the scale (z={z})"


# ---------------------------------------------------------------------------
# streak — a flat series is not a campaign
# ---------------------------------------------------------------------------

def test_streak_is_zero_on_a_flat_series():
    """With a >= comparison every value ties its own median, so a name that did
    nothing scored a maximal streak and rode that into the ranking."""
    assert streak_above_norm([1.0] * 40) == 0


def test_streak_counts_only_the_current_run():
    assert streak_above_norm([1.0] * 30 + [2.0] * 5) == 5
    assert streak_above_norm([1.0] * 30 + [2.0] * 5 + [0.5]) == 0


# ---------------------------------------------------------------------------
# the split trap — a share-count re-basing under the denominator
# ---------------------------------------------------------------------------

def _split_series(n_pre=300, n_post=120, factor=10.0, level=0.35, seed=5):
    """Participation history for a name that did an N:1 split.

    The vendor retroactively multiplies its historical VOLUME by N while FINRA's file
    keeps the raw as-reported counts, so every pre-split day reads level ÷ N.
    """
    rng = np.random.default_rng(seed)
    pre = list(rng.normal(level / factor, level / factor * 0.06, n_pre))
    post = list(rng.normal(level, level * 0.06, n_post))
    return pd.Series(pre + post)


def test_share_break_is_detected_and_history_is_trimmed():
    s = _split_series()
    idx = share_break_index(s)
    assert idx is not None, "a 10x level break must be detected"
    kept = usable_history(s)
    assert len(kept) < len(s)
    # everything kept sits at the post-split level, not the re-based one
    assert kept.min() > 0.2, "pre-split observations survived the trim"


def test_split_history_does_not_manufacture_a_giant_z():
    """The live defect: BKNG read 1.0% participation in 2023 against 31.7% now, and
    the bimodal baseline produced z=+53.7 for a day that was BELOW its own norm."""
    s = _split_series()
    naive = trailing_z(s)
    fixed = trailing_z(usable_history(s))
    assert naive is not None and naive > 8, "fixture does not reproduce the defect"
    assert fixed is not None and abs(fixed) < 4, f"trimmed z still degenerate ({fixed})"


def test_share_break_does_not_fire_on_a_genuine_secular_trend():
    """Market-wide off-exchange participation drifted 0.318 → 0.383 over three years.
    A detector that trims on THAT would silently delete good history everywhere."""
    trend = pd.Series(np.linspace(0.318, 0.383, 755))
    assert share_break_index(trend) is None
    assert len(usable_history(trend)) == 755


def test_share_break_ignores_a_one_day_spike():
    """A single wild session is the thing we want to SCORE, not a unit change."""
    rng = np.random.default_rng(9)
    s = pd.Series(list(rng.normal(0.30, 0.02, 300)))
    s.iloc[150] = 0.95
    assert share_break_index(s) is None


# ---------------------------------------------------------------------------
# venue split — ATS vs wholesaler internalisation
# ---------------------------------------------------------------------------

def _venue_frame(rows, notional=True):
    cols = ["week_start", "ticker", "mpid", "venue_name", "shares", "trades"]
    if notional:
        cols.append("notional")
    return pd.DataFrame(rows, columns=cols)


def test_venue_split_computes_ats_fraction_and_block_sizes():
    ats = _venue_frame([
        ["2026-06-22", "AAA", "UBSA", "UBS ATS", 300.0, 6, 60000.0],
        ["2026-06-22", "AAA", "INCR", "INTELLIGENT CROSS", 100.0, 4, 20000.0],
    ])
    non = _venue_frame([
        ["2026-06-22", "AAA", "", "CITADEL SECURITIES LLC", 600.0, 30, 120000.0],
    ])
    out = venue_split(ats, non)["AAA"]
    assert out["ats_frac"] == pytest.approx(400 / 1000)
    assert out["ats_block_shares"] == pytest.approx(40.0)     # 400 shares / 10 trades
    assert out["nonats_block_shares"] == pytest.approx(20.0)  # 600 / 30
    assert out["top_ats_venue"] == "UBS ATS"
    assert out["top_nonats_firm"] == "CITADEL SECURITIES LLC"
    assert out["avg_print_price"] == pytest.approx(200000 / 1000)


def test_venue_split_keys_non_ats_on_name_because_mpid_is_empty():
    """FINRA publishes no MPID for non-ATS firms. Any `mpid.str.len() > 0` filter
    silently drops the entire wholesaler half of off-exchange volume."""
    non = _venue_frame([["2026-06-22", "BBB", "", "VIRTU AMERICAS LLC", 500.0, 10, 5000.0]])
    out = venue_split(None, non)["BBB"]
    assert out["top_nonats_firm"] == "VIRTU AMERICAS LLC"
    assert out["nonats_shares"] == 500.0
    assert out["ats_frac"] == 0.0


def test_avg_print_price_divides_only_the_legs_that_supplied_notional():
    """ATS weeks stored before 2026-08-05 carry no `notional`. Dividing a one-leg
    notional by BOTH legs' shares understated AAPL at $195.60 against a ~$285 tape."""
    ats = _venue_frame([["2026-06-22", "CCC", "UBSA", "UBS ATS", 300.0, 3]], notional=False)
    non = _venue_frame([["2026-06-22", "CCC", "", "CITADEL", 700.0, 7, 70000.0]])
    out = venue_split(ats, non)["CCC"]
    assert out["avg_print_price"] == pytest.approx(100.0)   # 70000 / 700, NOT / 1000
    assert out["avg_print_price_partial"] is True


# ---------------------------------------------------------------------------
# pattern + ranking
# ---------------------------------------------------------------------------

def test_pattern_requires_both_heavy_volume_and_a_price():
    assert _pattern(2.0, -3.0) == "heavy_into_weakness"
    assert _pattern(2.0, 3.0) == "heavy_into_strength"
    assert _pattern(2.0, 0.1) == "heavy_price_flat"
    assert _pattern(0.4, -3.0) is None      # not heavy enough
    assert _pattern(2.0, None) is None      # no price ⇒ no conjunction
    assert _pattern(None, -3.0) is None


def test_unusualness_ranks_deviation_not_the_structural_level():
    """42.7% of raw participation variance is a fixed per-name effect. A name that is
    ALWAYS dark must not outrank one that is unusually dark today."""
    always_dark = NameMetrics(ticker="A", participation=0.62, participation_z=0.1, streak=0)
    unusual_now = NameMetrics(ticker="B", participation=0.33, participation_z=2.8, streak=6)
    assert unusualness(unusual_now) > unusualness(always_dark)


def test_unusualness_sorts_unscored_names_last():
    assert unusualness(NameMetrics(ticker="N", participation=0.9, participation_z=None)) == -1.0


# ---------------------------------------------------------------------------
# market gauge
# ---------------------------------------------------------------------------

def test_market_gauge_is_dollar_weighted_not_share_weighted():
    """A $3 name and a $300 name must not count the same."""
    penny = NameMetrics(ticker="P", participation=0.80, offex_dollars=1e6)
    mega = NameMetrics(ticker="M", participation=0.30, offex_dollars=1e10)
    g = market_gauge([penny, mega])
    assert g["participation_dollar_wtd"] == pytest.approx(0.30, abs=0.01), \
        "the mega-cap's dollars must dominate the gauge"
    assert g["participation_median"] == pytest.approx(0.55)


def test_market_gauge_reports_nulls_when_inputs_are_missing():
    g = market_gauge([NameMetrics(ticker="X")])
    assert g["participation_dollar_wtd"] is None and g["n_names"] == 0
