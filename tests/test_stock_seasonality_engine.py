"""Tests for the stock-seasonality calendar clock (Lane 1 + Lane 2 + selection).

These pin the things that would ship silently broken: a leap-day return quietly
dropped, an incomplete year counted as evidence, a window that wraps December
into January, a null that shifts every year together (which would leave a real
seasonal effect intact and make the correction decorative), and an artifact whose
key set has drifted from the contract the page is built against.

The single most valuable test here is
``test_null_is_calibrated_on_pure_noise``: it proves the familywise correction
fires at roughly its nominal rate on data with no seasonality at all. A
correction that never fires is not conservative, it is broken, and one that fires
constantly is decoration.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from engine.seasonality import calendar as season_calendar
from engine.seasonality import panel as season_panel
from engine.seasonality import scanner as season_scanner
from engine.seasonality.foundation import build_methodology_manifest
from engine.seasonality.multiplicity import max_t_adjusted_p_values
from scripts.build_stock_seasonality import (
    CUM_SCALE,
    ENTITY_SCHEMA,
    INDEX_SCHEMA,
    SELECTION_FORMAT,
    build,
    quantize,
)

# --- the contract, spelled out so drift in EITHER direction fails --------------
#
# design-spec §9 is the binding shape. The additions are deliberate and each one
# is justified in the PR body; listing them here means an UNDOCUMENTED addition
# reds this test just as loudly as a missing contract key.

SPEC_ENTITY_KEYS = {
    "schema", "symbol", "name", "asof", "generated_at", "price_source", "coverage",
    "calendar", "years", "current_year", "aggregate", "views", "family",
    "default_window", "neutral",
}
SPEC_COVERAGE_KEYS = {
    "n_years_complete", "first_year", "last_complete_year", "n_years_available",
    "years_capped_at", "complete_year_rule", "missing_session_policy", "leap_policy",
}
SPEC_CALENDAR_KEYS = {"basis", "n_slots", "labels"}
ADDED_CALENDAR_KEYS = {"cum_encoding", "cum_scale", "window_convention"}
SPEC_FAMILY_KEYS = {"n_candidates", "start_days", "horizons_days", "statistic", "null"}
ADDED_FAMILY_KEYS = {"registered_panel", "best", "registered_panel_pricing", "null_by_lookback"}
SPEC_NULL_KEYS = {"method", "B", "max_abs_t_quantiles"}
ADDED_NULL_KEYS = {"seed", "n_years", "max_abs_t_quantile_ladder"}
SPEC_DEFAULT_WINDOW_KEYS = {
    "start_doy", "end_doy", "source", "abs_t", "null_max_exceedance_pct", "state",
    "raw_clears", "neutral_clears", "stability",
}
SPEC_STABILITY_KEYS = {"shifts_days", "abs_t", "sign_stable", "survives"}
ADDED_DEFAULT_WINDOW_KEYS = {"null_max_exceedance_raw_pct", "neutral_basis"}
SPEC_VIEW_KEYS = {"k", "mean", "median", "up_share", "n"}
SPEC_INDEX_KEYS = {"schema", "as_of", "default_symbol", "n_entities", "entities"}
ADDED_INDEX_KEYS = {"program_rates", "disclosures"}
SPEC_INDEX_ENTITY_KEYS = {"symbol", "name", "group", "sector", "n_years", "first_year"}
ADDED_INDEX_ENTITY_KEYS = {"n_years_panel"}


# --- fixtures ---------------------------------------------------------------


def _calendar_series(start: str, end: str, *, seed: int = 0, drift: float = 0.0) -> pd.Series:
    """A synthetic instrument that prints EVERY calendar day (leap days included)."""
    index = pd.date_range(start, end, freq="D")
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, 0.01, size=len(index))
    return pd.Series(100.0 * np.exp(np.cumsum(returns)), index=index, name="close")


def _session_series(start: str, end: str, *, seed: int = 0) -> pd.Series:
    """A synthetic instrument on a realistic US equity calendar.

    Business days MINUS the fixed-date market holidays, which matters more than it
    looks: ``bdate_range`` happily trades on Jan 1 whenever it falls on a weekday,
    and no US equity ever does. Slot 0 is the cumulative path's rebase anchor, so a
    fixture that trades on Jan 1 is testing a shape the production universe cannot
    have — and it hid a real guard until the builder started refusing it.
    """
    index = pd.bdate_range(start, end)
    holidays = {(1, 1), (7, 4), (12, 25)}
    index = index[[(ts.month, ts.day) not in holidays for ts in index]]
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0, 0.01, size=len(index))
    return pd.Series(100.0 * np.exp(np.cumsum(returns)), index=index, name="close")


def _noise_panel(n_years: int, seed: int) -> season_panel.YearPanel:
    rng = np.random.default_rng(seed)
    daily = rng.normal(0.0, 0.01, size=(n_years, season_panel.N_SLOTS))
    cumulative = np.cumsum(daily, axis=1)
    return season_panel.YearPanel(
        symbol=f"NOISE{seed}",
        years=tuple(range(2000, 2000 + n_years)),
        daily=daily,
        cum=cumulative - cumulative[:, :1],
        n_years_available=n_years,
        first_available_year=2000,
        last_available_year=2000 + n_years - 1,
        current_year=None,
        current_cum=None,
        current_last_index=None,
        last_session=date(2000 + n_years - 1, 12, 31),
    )


def _implanted_panel(n_years: int, seed: int, *, lo: int = 200, hi: int = 230) -> season_panel.YearPanel:
    """Pure noise plus a genuinely repeating window, present in EVERY year."""
    base = _noise_panel(n_years, seed)
    daily = base.daily.copy()
    daily[:, lo:hi] += 0.004
    cumulative = np.cumsum(daily, axis=1)
    return season_panel.YearPanel(
        symbol=f"IMPLANT{seed}",
        years=base.years,
        daily=daily,
        cum=cumulative - cumulative[:, :1],
        n_years_available=n_years,
        first_available_year=base.first_available_year,
        last_available_year=base.last_available_year,
        current_year=None,
        current_cum=None,
        current_last_index=None,
        last_session=base.last_session,
    )


def _write_store(root, series_by_symbol: dict[str, pd.Series], *, min_years: int = 15) -> None:
    """Materialise a fake data/yahoo store plus the universe policy."""
    store = root / "data" / "yahoo"
    store.mkdir(parents=True, exist_ok=True)
    for symbol, closes in series_by_symbol.items():
        frame = pd.DataFrame({"close_price": closes.to_numpy(), "close": closes.to_numpy()})
        frame.index = pd.DatetimeIndex(closes.index, name="Date")
        frame.to_parquet(store / f"{symbol}.parquet")
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "seasonality_universe.yml").write_text(
        yaml.safe_dump(
            {
                "selection": {
                    "min_complete_years": min_years,
                    "years_cap": season_panel.YEARS_CAP,
                    "exclude_prefixes": ["_"],
                    "exclude_suffixes": ["_X", "_F"],
                    "exclude": [],
                },
                "benchmark": "SPY",
                "default_symbol": "SPY",
                "labels": {"SPY": {"name": "Benchmark", "group": "index", "sector": "Index"}},
            }
        ),
        encoding="utf-8",
    )


# --- Lane 1: the year panel -------------------------------------------------


def test_leap_day_folds_into_feb_28_and_preserves_the_year_total():
    closes = _calendar_series("2019-12-31", "2021-01-05", seed=3)
    returns = season_panel.daily_log_returns(closes)
    panel = season_panel.build_year_panel(returns, symbol="LEAP")
    assert 2020 in panel.years

    row = panel.daily[panel.years.index(2020)]
    feb_28_slot = season_panel.slots_for(pd.DatetimeIndex(["2020-02-28"]))[0]
    assert season_panel.slots_for(pd.DatetimeIndex(["2020-02-29"]))[0] == feb_28_slot

    year_returns = returns[pd.DatetimeIndex(returns.index).year == 2020]
    assert row.sum() == pytest.approx(float(year_returns.sum()), abs=1e-12)

    both_days = float(
        year_returns[pd.DatetimeIndex(year_returns.index).isin(pd.to_datetime(["2020-02-28", "2020-02-29"]))].sum()
    )
    assert row[feb_28_slot] == pytest.approx(both_days, abs=1e-12)
    assert len(row) == 365


def test_incomplete_years_are_excluded_and_the_partial_year_is_carried_separately():
    closes = _session_series("2015-06-15", "2020-07-31", seed=11)  # mid-year "IPO"
    returns = season_panel.daily_log_returns(closes)
    panel = season_panel.build_year_panel(returns, symbol="IPO")

    assert 2015 not in panel.years, "an instrument that started in June has no complete 2015"
    assert panel.years == (2016, 2017, 2018, 2019)
    assert panel.current_year == 2020
    assert panel.current_last_index is not None
    assert panel.current_cum is not None
    assert len(panel.current_cum) == panel.current_last_index + 1
    assert panel.current_last_index == season_panel.slots_for(pd.DatetimeIndex(["2020-07-31"]))[0]


def test_non_trading_days_carry_zero_and_the_path_is_flat_across_a_weekend():
    closes = _session_series("2015-12-01", "2019-12-31", seed=5)
    returns = season_panel.daily_log_returns(closes)
    panel = season_panel.build_year_panel(returns, symbol="WEEKEND")
    row_index = panel.years.index(2017)

    friday, saturday, sunday, monday = season_panel.slots_for(
        pd.DatetimeIndex(["2017-07-07", "2017-07-08", "2017-07-09", "2017-07-10"])
    )
    assert panel.daily[row_index, saturday] == 0.0
    assert panel.daily[row_index, sunday] == 0.0
    assert panel.cum[row_index, friday] == panel.cum[row_index, saturday] == panel.cum[row_index, sunday]
    assert panel.cum[row_index, monday] != panel.cum[row_index, sunday]
    assert panel.cum[row_index, 0] == 0.0


def test_year_cap_keeps_the_most_recent_years_and_reports_what_was_dropped():
    closes = _session_series("1989-12-01", "2025-12-31", seed=7)
    returns = season_panel.daily_log_returns(closes)
    panel = season_panel.build_year_panel(returns, symbol="DEEP", cap=25)
    assert panel.n_years == 25
    assert panel.years[-1] == 2025
    assert panel.n_years_available > 25
    assert panel.first_available_year is not None and panel.first_available_year < panel.years[0]


def test_market_neutral_beta_never_sees_its_own_session():
    """The `.shift(1)` is load-bearing: without it day t's residual uses day t's beta."""
    market = season_panel.daily_log_returns(_session_series("2010-01-01", "2016-12-31", seed=1))
    symbol = season_panel.daily_log_returns(_session_series("2010-01-01", "2016-12-31", seed=2))
    beta = season_panel.pit_trailing_beta(symbol, market, window=252)

    joined = pd.DataFrame({"s": symbol, "m": market}).dropna()
    probe = beta.index[100]
    position = joined.index.get_loc(probe)
    trailing = joined.iloc[position - 252 : position]
    expected = trailing["s"].cov(trailing["m"]) / trailing["m"].var()
    assert beta.loc[probe] == pytest.approx(float(expected), rel=1e-9)

    # A window that INCLUDED the session would be a different number; prove it.
    inclusive = joined.iloc[position - 251 : position + 1]
    assert beta.loc[probe] != pytest.approx(
        float(inclusive["s"].cov(inclusive["m"]) / inclusive["m"].var()), rel=1e-6
    )


# --- Lane 2: curve + views --------------------------------------------------


def test_canonical_paths_aggregate_in_log_space_not_price_space():
    panel = _noise_panel(12, seed=21)
    paths = season_calendar.canonical_paths(panel)
    assert set(paths) == {"median", "p20", "p80", "mean_log"}
    for values in paths.values():
        assert values.shape == (season_panel.N_SLOTS,)
    assert np.all(paths["p20"] <= paths["median"] + 1e-12)
    assert np.all(paths["median"] <= paths["p80"] + 1e-12)
    assert paths["mean_log"] == pytest.approx(panel.cum.mean(axis=0))
    # The display rebase is the ONLY place a level appears, and it exponentiates
    # an already-aggregated log path rather than averaging prices.
    assert season_calendar.rebase_to_100(paths["median"])[0] == pytest.approx(100.0)


def test_views_count_years_not_days():
    closes = _session_series("2004-12-01", "2024-12-31", seed=13)
    returns = season_panel.daily_log_returns(closes)
    panel = season_panel.build_year_panel(returns, symbol="VIEWS")
    views = season_calendar.build_views(panel, returns)

    assert [entry["k"] for entry in views["month"]] == list(range(1, 13))
    assert [entry["k"] for entry in views["weekday"]] == [0, 1, 2, 3, 4]
    assert all(entry["k"] <= season_calendar.MAX_TRADING_DAY_OF_MONTH for entry in views["trading_day_of_month"])
    for name, entries in views.items():
        for entry in entries:
            assert set(entry) == SPEC_VIEW_KEYS, name
            assert entry["n"] <= panel.n_years, (
                f"{name} bucket k={entry['k']} reports n={entry['n']} with only "
                f"{panel.n_years} complete years — the unit of evidence has slipped to days"
            )
            assert 0.0 <= entry["up_share"] <= 1.0

    month_january = views["month"][0]
    first, last = season_panel.month_slot_bounds(1)
    assert month_january["mean"] == pytest.approx(
        float(panel.daily[:, first : last + 1].sum(axis=1).mean()), abs=1e-6
    )


# --- window family ----------------------------------------------------------


def test_family_is_exactly_2645_windows_and_never_wraps_the_year():
    family = season_scanner.window_family()
    assert len(family) == 2645 == season_scanner.family_size() == season_scanner.N_CANDIDATES
    assert len(set(family)) == len(family)
    for start_doy, horizon in family:
        assert horizon in season_scanner.HORIZONS_DAYS
        assert start_doy >= 1
        assert start_doy + horizon <= season_panel.N_SLOTS, "a window wrapped December into January"
    for horizon in season_scanner.HORIZONS_DAYS:
        starts = [start for start, h in family if h == horizon]
        assert starts == list(range(1, season_panel.N_SLOTS - horizon + 1))


def test_grid_matches_the_declared_family_and_guards_degenerate_windows():
    panel = _noise_panel(10, seed=31)
    grid = season_scanner.grid_abs_t(panel.cum)
    assert sum(values.size for values in grid.values()) == season_scanner.N_CANDIDATES

    flat = np.zeros((6, season_panel.N_SLOTS))
    stats = season_scanner.window_statistics(flat, 10, 40)
    assert stats["sd"] == 0.0
    assert stats["abs_t"] is None, "a zero-variance window must be None, never inf"

    single = np.zeros((1, season_panel.N_SLOTS))
    assert season_scanner.window_statistics(single, 10, 40)["abs_t"] is None


# --- the null ---------------------------------------------------------------


def test_year_offsets_are_drawn_per_year_not_shared():
    offsets = season_scanner.draw_year_offsets(np.random.default_rng(7), 25, 6)
    assert offsets.shape == (25, 6)
    distinct_per_row = [len(set(row.tolist())) for row in offsets]
    assert max(distinct_per_row) > 1, "every year got the same shift — this is the synchronized null"
    assert sum(1 for count in distinct_per_row if count > 1) >= 24


def test_independent_shift_destroys_a_seasonal_effect_that_a_synchronized_shift_would_keep():
    """The reason the synchronized null is not implemented, made measurable."""
    panel = _implanted_panel(18, seed=41)
    independent, _ = season_scanner.null_max_abs_t(panel.daily, n_resamples=200, seed=5)

    # A synchronized shift: ONE offset shared by every year, so the implanted
    # window merely moves to a new date and the effect survives intact.
    rng = np.random.default_rng(5)
    shared = np.repeat(rng.integers(0, season_panel.N_SLOTS, size=(200, 1)), panel.n_years, axis=1)
    rolled = season_scanner.circular_year_shift(panel.daily, shared)
    cumulative = np.cumsum(rolled, axis=-1)
    synchronized = season_scanner._grid_max_abs_t(cumulative - cumulative[..., :1])

    assert np.quantile(independent, 0.95) < np.quantile(synchronized, 0.95), (
        "the independent null must price away the implanted effect that a "
        "synchronized shift only relocates"
    )


def test_real_seasonal_window_clears_the_null_and_noise_does_not():
    implanted = _implanted_panel(18, seed=51)
    observed = season_scanner.best_window(implanted.cum)
    null_max, _ = season_scanner.null_max_abs_t(implanted.daily, n_resamples=300, seed=11)
    assert observed is not None
    assert observed[2] > np.quantile(null_max, 0.95)

    noise = _noise_panel(18, seed=51)
    noise_observed = season_scanner.best_window(noise.cum)
    noise_null, _ = season_scanner.null_max_abs_t(noise.daily, n_resamples=300, seed=11)
    assert noise_observed is not None
    assert noise_observed[2] < np.quantile(noise_null, 0.95)


def _fire_rate(panel_factory, *, trials: int, n_resamples: int) -> int:
    fires = 0
    for seed in range(trials):
        panel = panel_factory(seed)
        observed = season_scanner.best_window(panel.cum)
        null_max, _ = season_scanner.null_max_abs_t(panel.daily, n_resamples=n_resamples, seed=seed)
        if observed is not None and observed[2] >= np.quantile(null_max, 0.95):
            fires += 1
    return fires


def test_null_is_calibrated_on_pure_noise():
    """The whole correction rests on this: ~5% of noise panels should fire.

    Both bounds are load-bearing and the LOWER one is the easy thing to forget.
    A test that only caps the rate passes on a null inflated 60% — verified: with
    the family maximum scaled by 1.2, 1.4 or 1.6 this fires 0/24 while every other
    test in this file stays green. A correction that can never fire is not
    conservative, it is broken, and it would read on the page as "nothing in this
    market has ever had a season".
    """
    trials = 24
    fires = _fire_rate(lambda s: _noise_panel(15, seed=1000 + s), trials=trials, n_resamples=250)
    rate = fires / trials
    assert rate <= 0.30, f"pure-noise fire rate {rate:.0%} is far above the 5% nominal"
    assert fires >= 1, (
        "nothing fired in 24 pure-noise panels — at a 5% nominal rate that is the "
        "signature of an inflated null threshold, not of a clean sample"
    )


def test_null_is_calibrated_on_a_PRODUCTION_SHAPED_panel():
    """Calibration on iid Gaussian says nothing about the data this actually sees.

    A real panel has ~115 zero slots per year (weekends and holidays), fat tails,
    and volatility clustering. `_noise_panel` has none of those. This repeats the
    calibration on a panel carrying the real calendar's zero structure and a
    heavy-tailed innovation, so the suite's evidence is about the input shape the
    builder is given.
    """

    def shaped(seed: int) -> season_panel.YearPanel:
        rng = np.random.default_rng(4000 + seed)
        base = _noise_panel(15, seed=4000 + seed)
        daily = rng.standard_t(3.0, size=base.daily.shape) * 0.006  # fat tails
        trading = np.ones(season_panel.N_SLOTS, dtype=bool)
        closed = rng.choice(season_panel.N_SLOTS, size=115, replace=False)
        trading[closed] = False
        daily[:, ~trading] = 0.0  # weekends + holidays carry zero, as in production
        cumulative = np.cumsum(daily, axis=1)
        return season_panel.YearPanel(
            symbol=f"SHAPED{seed}",
            years=base.years,
            daily=daily,
            cum=cumulative - cumulative[:, :1],
            n_years_available=15,
            first_available_year=base.first_available_year,
            last_available_year=base.last_available_year,
            current_year=None,
            current_cum=None,
            current_last_index=None,
            last_session=base.last_session,
        )

    trials = 20
    fires = _fire_rate(shaped, trials=trials, n_resamples=250)
    assert fires / trials <= 0.35, (
        f"{fires}/{trials} production-shaped noise panels fired — the null does not "
        "survive the zero slots and fat tails of a real trading calendar"
    )


def test_exceedance_carries_the_monte_carlo_floor_and_never_reads_zero():
    null_max = np.array([1.0, 2.0, 3.0, 4.0])
    # (1 + #{>= observed}) / (B + 1), the same floor as every other p here.
    assert season_scanner.exceedance_pct(null_max, 3.0) == pytest.approx(60.0)
    assert season_scanner.exceedance_pct(null_max, 5.0) == pytest.approx(20.0)
    assert season_scanner.exceedance_pct(null_max, 5.0) > 0.0, (
        "a window that beat every draw must not publish 0% — the resolution floor is 1/(B+1)"
    )
    ladder = season_scanner.quantile_ladder(null_max)
    assert len(ladder) == season_scanner.LADDER_STEPS
    assert ladder[0] == pytest.approx(1.0) and ladder[-1] == pytest.approx(4.0)
    assert ladder == sorted(ladder)


# --- selection correction ---------------------------------------------------


def test_max_t_primitive_and_the_null_max_derivation_agree():
    """The scanner collapses each null row to its maximum; prove that is lossless."""
    rng = np.random.default_rng(99)
    n_resamples, n_hypotheses = 40, 6
    full = rng.normal(0.0, 1.0, size=(n_resamples, n_hypotheses))
    observed = [2.4, 0.3, 1.1, 3.9, 0.05, 1.7]

    from_full_matrix = max_t_adjusted_p_values(observed, full.tolist())
    null_max = np.abs(full).max(axis=1)
    from_collapsed = max_t_adjusted_p_values(
        observed, [[value] * n_hypotheses for value in null_max.tolist()]
    )
    by_hand = [
        (1 + int((null_max >= abs(statistic)).sum())) / (n_resamples + 1) for statistic in observed
    ]
    assert from_full_matrix == pytest.approx(from_collapsed)
    assert from_full_matrix == pytest.approx(by_hand)


def test_month_windows_return_exactly_the_month_the_views_report():
    """The off-by-one that would silently forfeit the 1st of every month.

    ``month_view`` sums a month's slots directly; the registered panel derives the
    same month through the window convention. If the two disagree, the artifact
    reports one number for February in ``views`` and a different one in
    ``family.registered_panel``, and both look plausible.
    """
    panel = _noise_panel(14, seed=95)
    views = season_calendar.month_view(panel)
    for month in range(2, 13):  # January's day 0 IS the rebase anchor — see month_window
        start_doy, end_doy = season_scanner.month_window(month)
        first, last = season_panel.month_slot_bounds(month)
        assert start_doy == first and end_doy == last + 1
        per_year = season_scanner.window_returns(panel.cum, start_doy, end_doy)
        assert per_year == pytest.approx(panel.daily[:, first : last + 1].sum(axis=1))
        assert float(per_year.mean()) == pytest.approx(views[month - 1]["mean"], abs=1e-6)

    january = season_scanner.month_window(1)
    assert january == (1, 31)
    assert season_scanner.month_window(12) == (334, 365)
    for month in range(1, 13):
        start_doy, end_doy = season_scanner.month_window(month)
        assert start_doy >= 1 and end_doy <= season_panel.N_SLOTS


def test_null_maximum_equals_the_row_max_of_the_real_family_matrix():
    """What the Westfall-Young collapse actually depends on, pinned.

    `test_max_t_primitive_and_the_null_max_derivation_agree` proves collapse-to-max
    is lossless for the PRIMITIVE — true by construction. The claim that matters is
    that the scanner's `null_max` really is the row maximum of the [B][2645] matrix
    it never materialises. Dropping a horizon from `_grid_max_abs_t` alone leaves
    every other test in this file green; this one goes red.
    """
    panel = _noise_panel(12, seed=131)
    offsets = season_scanner.draw_year_offsets(np.random.default_rng(3), 6, panel.n_years)
    rolled = season_scanner.circular_year_shift(panel.daily, offsets)
    cum = np.cumsum(rolled, axis=-1)
    cum = cum - cum[..., :1]

    collapsed = season_scanner._grid_max_abs_t(cum)
    columns = [values for values in season_scanner.grid_abs_t(cum).values()]
    full = np.concatenate(columns, axis=-1)
    assert full.shape[-1] == season_scanner.N_CANDIDATES
    assert collapsed == pytest.approx(np.nanmax(full, axis=-1))


def test_window_statistics_uses_the_sample_standard_deviation():
    """The second, independent copy of the t formula — `ddof` pinned numerically.

    `window_statistics` is what prices every registered-panel row, every stability
    shift, and `neutral_clears`. Switching it to `ddof=0` moves all of those and
    leaves `best.abs_t` (computed by `_abs_t`) untouched, so the client-formula
    test still passes.
    """
    panel = _noise_panel(9, seed=133)
    stats = season_scanner.window_statistics(panel.cum, 40, 70)
    values = panel.cum[:, 69] - panel.cum[:, 39]
    assert stats["n_years"] == 9
    assert stats["mean"] == pytest.approx(float(values.mean()))
    assert stats["sd"] == pytest.approx(float(values.std(ddof=1)))
    assert stats["sd"] != pytest.approx(float(values.std(ddof=0)))
    assert stats["abs_t"] == pytest.approx(
        abs(float(values.mean())) / (float(values.std(ddof=1)) / np.sqrt(9))
    )


def test_stability_median_floor_decides_when_the_sign_is_stable():
    """`STABILITY_MEDIAN_FLOOR` tested in BOTH directions.

    The spike fixture is rejected by `sign_stable`, so it never exercises the
    magnitude branch — the constant the whole rule rests on was free at any value
    from 0.0 to 0.99. This panel keeps the sign at every shift and only collapses
    in magnitude, which is the case the floor exists to judge.
    """
    base = _noise_panel(20, seed=137)
    daily = base.daily.copy()
    daily[:, 150:170] += 0.0035  # the window itself: strong and one-signed
    daily[:, 145:150] += 0.0004  # shoulders: same sign, far weaker
    daily[:, 170:176] += 0.0004
    cumulative = np.cumsum(daily, axis=1)
    cum = cumulative - cumulative[:, :1]

    result = season_scanner.window_stability(cum, 151, 170)
    assert result["sign_stable"] is True, "fixture must exercise the MAGNITUDE branch"
    base_t = season_scanner.window_statistics(cum, 151, 170)["abs_t"]
    ratio = float(np.median([v for v in result["abs_t"] if v is not None])) / base_t
    assert result["survives"] is (ratio >= season_scanner.STABILITY_MEDIAN_FLOOR)
    assert 0.0 < ratio < 1.0, "a fixture whose shifts do not degrade cannot test the floor"


def test_overlap_share_counts_the_days_a_window_actually_covers():
    """A window `(s, e)` covers `e - s` days, not `e - s + 1`.

    Treating the endpoints as an inclusive day range made two windows that share
    nothing but a boundary — which belongs to neither one's return — report 17%
    overlap.
    """
    assert season_scanner._overlap_share((100, 105), (105, 110)) == 0.0
    assert season_scanner._overlap_share((1, 31), (31, 59)) == 0.0
    assert season_scanner._overlap_share((100, 110), (100, 110)) == 1.0
    assert season_scanner._overlap_share((100, 110), (105, 115)) == pytest.approx(0.5)
    assert season_scanner._overlap_share((100, 110), (106, 116)) < 0.5


def test_registered_panel_is_twelve_months_plus_non_overlapping_discoveries():
    panel = _implanted_panel(16, seed=61)
    windows = season_scanner.registered_panel_windows(panel.cum, k=season_scanner.TOP_K_DISCOVERED)
    months = [entry for entry in windows if entry["kind"] == "calendar_month"]
    discovered = [entry for entry in windows if entry["kind"] == "discovered"]
    assert [entry["month"] for entry in months] == list(range(1, 13))
    assert 0 < len(discovered) <= season_scanner.TOP_K_DISCOVERED

    for index, first in enumerate(discovered):
        for second in discovered[index + 1 :]:
            share = season_scanner._overlap_share(
                (first["start_doy"], first["end_doy"]), (second["start_doy"], second["end_doy"])
            )
            assert share < season_scanner.MAX_OVERLAP_SHARE, (
                "two discovered windows restate each other; the panel would look like "
                "independent findings it is not"
            )


def test_a_smeared_season_survives_a_nudge_and_a_one_week_spike_does_not():
    """The neighbouring-window check, which is what separates a season from a date.

    A five-day window pinned to a recurring corporate event collapses the moment
    it stops covering that date; a real season degrades gently.
    """
    season = _implanted_panel(18, seed=91, lo=200, hi=230)
    smeared = season_scanner.window_stability(season.cum, 205, 225)
    assert set(smeared) == SPEC_STABILITY_KEYS
    assert smeared["shifts_days"] == [-5, -2, 2, 5]
    assert smeared["sign_stable"] is True
    assert smeared["survives"] is True

    spike = _noise_panel(18, seed=91)
    daily = spike.daily.copy()
    daily[:, 150:153] += 0.02  # the same three calendar days every single year
    cumulative = np.cumsum(daily, axis=1)
    spike_cum = cumulative - cumulative[:, :1]
    pinned = season_scanner.window_stability(spike_cum, 151, 153)
    assert pinned["survives"] is False, "a 3-day date artefact must not read as a season"


def test_stability_at_the_year_edge_is_null_and_cannot_survive():
    panel = _noise_panel(12, seed=93)
    december = season_scanner.window_stability(panel.cum, 335, 365)
    assert december["abs_t"][2] is None and december["abs_t"][3] is None, (
        "a shift past day 365 would wrap the year; it must be published as null"
    )
    assert december["survives"] is False
    assert december["sign_stable"] is False

    january = season_scanner.window_stability(panel.cum, 2, 32)
    assert january["abs_t"][0] is None
    assert january["survives"] is False


def test_scan_publishes_the_correction_and_its_sensitivity():
    panel = _implanted_panel(16, seed=71)
    result = season_scanner.scan(panel, n_resamples=200)
    assert result is not None
    assert result.n_candidates == 2645
    assert set(result.max_abs_t_quantiles) == {"0.90", "0.95", "0.99"}
    assert result.max_abs_t_quantiles["0.90"] <= result.max_abs_t_quantiles["0.95"]
    assert result.max_abs_t_quantiles["0.95"] <= result.max_abs_t_quantiles["0.99"]
    assert result.seed == season_scanner.seed_for_symbol(panel.symbol)
    for entry in result.registered_panel:
        assert set(entry["stability"]) == SPEC_STABILITY_KEYS
        assert 0.0 < entry["p_adj_maxt_family"] <= 1.0
        if entry["kind"] == "calendar_month":
            assert 0.0 < entry["p_raw"] <= 1.0
            assert 0.0 < entry["q_by"] <= 1.0
            assert entry["p_adj_maxt_family"] >= entry["p_raw"] - 1e-12, (
                "the familywise-adjusted p can never be smaller than the raw marginal p"
            )
        else:
            assert entry["p_raw"] is None and entry["q_by"] is None
    assert result.best is not None and result.best["clears_95"] is True


def test_discovered_rows_publish_no_marginal_p_or_q():
    """A window chosen for being the largest cannot then be tested as if it were not.

    On a pure-noise panel the top-k discovered rows have marginal p below 0.05
    essentially always — they were selected for exactly that. Publishing one, or
    letting it into a BY panel, would hand every symbol on earth a "discovery".
    Only `p_adj_maxt_family`, which prices the search that found them, is valid.
    """
    result = season_scanner.scan(_noise_panel(18, seed=97), n_resamples=200)
    assert result is not None
    months = [e for e in result.registered_panel if e["kind"] == "calendar_month"]
    discovered = [e for e in result.registered_panel if e["kind"] == "discovered"]
    assert len(months) == 12 and discovered

    assert all(e["p_raw"] is None and e["q_by"] is None for e in discovered)
    assert all(e["p_raw"] is not None and e["q_by"] is not None for e in months)
    # BY is a step-up over the 12 PRE-REGISTERED rows only.
    from engine.seasonality.multiplicity import benjamini_yekutieli

    assert [e["q_by"] for e in months] == pytest.approx(
        [round(v, 6) for v in benjamini_yekutieli([e["p_raw"] for e in months])]
    )
    # And the discovered rows still carry the correction that IS theirs.
    assert all(0.0 < e["p_adj_maxt_family"] <= 1.0 for e in discovered)


def test_panel_hash_changes_when_the_vendor_re_adjusts_old_prices():
    panel = _noise_panel(12, seed=81)
    before = season_scanner.panel_fingerprint(panel)
    touched = panel.daily.copy()
    touched[0, 100] += 1e-4  # a re-adjustment of ONE old session
    moved = season_panel.YearPanel(
        symbol=panel.symbol,
        years=panel.years,
        daily=touched,
        cum=panel.cum,
        n_years_available=panel.n_years_available,
        first_available_year=panel.first_available_year,
        last_available_year=panel.last_available_year,
        current_year=None,
        current_cum=None,
        current_last_index=None,
        last_session=panel.last_session,
    )
    assert season_scanner.panel_fingerprint(moved) != before


# --- the artifact -----------------------------------------------------------


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> tuple:
    root = tmp_path_factory.mktemp("seasonality-root")
    _write_store(
        root,
        {
            "SPY": _session_series("1999-12-01", "2026-07-08", seed=101),
            "AAA": _session_series("1999-12-01", "2026-07-08", seed=102),
            "SHORT": _session_series("2020-01-01", "2026-07-08", seed=103),
        },
    )
    summary = build(
        root=root,
        as_of=date(2026, 7, 8),
        generated_at="2026-07-09T04:00:00Z",
        resamples=120,
    )
    index_payload = json.loads((root / "site" / "seasonalitydata" / "index.json").read_text())
    entity = json.loads((root / "site" / "seasonalitydata" / "entities" / "AAA.json").read_text())
    return root, summary, index_payload, entity


def test_artifact_matches_the_design_spec_key_set(built):
    _root, _summary, index_payload, entity = built

    assert set(entity) == SPEC_ENTITY_KEYS
    assert entity["schema"] == ENTITY_SCHEMA
    assert set(entity["coverage"]) == SPEC_COVERAGE_KEYS
    assert set(entity["calendar"]) == SPEC_CALENDAR_KEYS | ADDED_CALENDAR_KEYS
    assert set(entity["price_source"]) == {"vendor", "adjustment", "is_pit_adjustment", "field"}
    assert entity["price_source"]["is_pit_adjustment"] is False
    assert set(entity["family"]) == SPEC_FAMILY_KEYS | ADDED_FAMILY_KEYS
    assert set(entity["family"]["null"]) == SPEC_NULL_KEYS | ADDED_NULL_KEYS
    assert set(entity["default_window"]) == SPEC_DEFAULT_WINDOW_KEYS | ADDED_DEFAULT_WINDOW_KEYS
    assert entity["default_window"]["source"] == "symbol_best"
    assert entity["default_window"]["state"] in {"own", "market", "fails", "thin"}
    assert set(entity["default_window"]["stability"]) == SPEC_STABILITY_KEYS
    assert entity["default_window"]["stability"]["shifts_days"] == [-5, -2, 2, 5]
    for entry in entity["family"]["registered_panel"]:
        assert set(entry["stability"]) == SPEC_STABILITY_KEYS
    assert set(entity["aggregate"]) == {"median", "p20", "p80", "mean_log"}
    assert set(entity["views"]) == {"month", "weekday", "trading_day_of_month"}
    assert set(entity["neutral"]) == {"market"}
    assert set(entity["neutral"]["market"]) == {"benchmark", "beta_source", "years", "family"}
    assert entity["neutral"]["market"]["benchmark"] == "SPY"

    for year_row in entity["years"]:
        assert set(year_row) == {"year", "cum"}
        assert len(year_row["cum"]) == season_panel.N_SLOTS
        assert year_row["cum"][0] == 0
        assert all(isinstance(value, int) for value in year_row["cum"])
    assert len(entity["calendar"]["labels"]) == season_panel.N_SLOTS
    assert entity["calendar"]["labels"][0] == "01-01"
    assert entity["calendar"]["labels"][-1] == "12-31"
    assert set(entity["current_year"]) == {"year", "last_index", "cum"}

    assert set(index_payload) == SPEC_INDEX_KEYS | ADDED_INDEX_KEYS
    assert index_payload["schema"] == INDEX_SCHEMA
    assert index_payload["n_entities"] == len(index_payload["entities"])
    for row in index_payload["entities"]:
        assert set(row) == SPEC_INDEX_ENTITY_KEYS | ADDED_INDEX_ENTITY_KEYS


def test_universe_is_measured_so_a_short_history_is_not_covered(built):
    _root, summary, index_payload, _entity = built
    covered = {row["symbol"] for row in index_payload["entities"]}
    assert covered == {"SPY", "AAA"}
    assert "SHORT" not in covered, "a symbol below the complete-year floor must not be covered"
    assert summary["n_entities"] == 2
    assert index_payload["default_symbol"] == "SPY"


def test_asof_is_the_last_observed_session_not_the_wall_clock(tmp_path):
    """`asof` is rendered as "Through Jul 31". A stale store must SAY it is stale."""
    root = tmp_path / "freshness"
    _write_store(
        root,
        {
            "SPY": _session_series("1999-12-01", "2026-03-13", seed=601),
            "AAA": _session_series("1999-12-01", "2026-03-13", seed=602),
        },
    )
    build(root=root, generated_at="2099-01-01T00:00:00Z", resamples=40)  # no --as-of override
    entity = json.loads((root / "site" / "seasonalitydata" / "entities" / "AAA.json").read_text())
    index_payload = json.loads((root / "site" / "seasonalitydata" / "index.json").read_text())
    assert entity["asof"] == "2026-03-13"
    assert index_payload["as_of"] == "2026-03-13"
    assert entity["asof"] != date.today().isoformat()


def test_benchmark_ships_without_a_market_neutral_panel(built):
    root, _summary, _index_payload, _entity = built
    benchmark = json.loads((root / "site" / "seasonalitydata" / "entities" / "SPY.json").read_text())
    assert benchmark["neutral"] == {}
    assert benchmark["default_window"]["neutral_basis"] == "self_benchmark"
    assert benchmark["default_window"]["state"] in {"market", "fails", "thin"}
    assert benchmark["default_window"]["state"] != "own", (
        "the benchmark cannot have a pattern of its own AFTER removing the market"
    )


def test_program_rates_are_disclosure_and_carry_the_chance_expectation(built):
    _root, _summary, index_payload, _entity = built
    rates = index_payload["program_rates"]
    assert rates["chance_expectation_share"] == 0.05
    assert rates["raw"]["n_symbols"] == index_payload["n_entities"]
    assert 0 <= rates["raw"]["n_clearing"] <= rates["raw"]["n_symbols"]
    assert index_payload["disclosures"]["survivorship"]
    assert index_payload["disclosures"]["price_adjustment"]
    assert "no score, rank" in index_payload["disclosures"]["no_ranking"]


def test_quantised_round_trip_reproduces_window_returns(built):
    root, _summary, _index_payload, entity = built
    closes = season_panel.load_adjusted_closes(root, "AAA")
    panel = season_panel.build_year_panel(season_panel.daily_log_returns(closes), symbol="AAA")

    worst = 0.0
    for row_index, year_row in enumerate(entity["years"]):
        assert year_row["year"] == panel.years[row_index]
        for start_doy, horizon in ((3, 5), (60, 30), (200, 90), (275, 90)):
            end_doy = start_doy + horizon
            exact = float(panel.cum[row_index, end_doy - 1] - panel.cum[row_index, start_doy - 1])
            recovered = (year_row["cum"][end_doy - 1] - year_row["cum"][start_doy - 1]) * CUM_SCALE
            worst = max(worst, abs(exact - recovered))
    assert worst < 1e-4, f"quantised window return drifted by {worst}"
    assert entity["calendar"]["cum_scale"] == CUM_SCALE
    assert quantize(np.array([0.0, 0.30125])) == [0, 30125]


def test_client_formula_reproduces_the_shipped_default_window(built):
    """§9's client contract: everything on the page must be derivable from years[].cum."""
    _root, _summary, _index_payload, entity = built
    window = entity["default_window"]
    values = np.array(
        [
            (row["cum"][window["end_doy"] - 1] - row["cum"][window["start_doy"] - 1]) * CUM_SCALE
            for row in entity["years"]
        ]
    )
    statistic = abs(values.mean()) / (values.std(ddof=1) / np.sqrt(values.size))
    assert statistic == pytest.approx(window["abs_t"], rel=2e-3)
    clears = statistic >= entity["family"]["null"]["max_abs_t_quantiles"]["0.95"]
    assert clears == window["raw_clears"]


def test_build_is_deterministic(tmp_path):
    payloads = []
    for name in ("run-a", "run-b"):
        root = tmp_path / name
        _write_store(
            root,
            {
                "SPY": _session_series("1999-12-01", "2026-07-08", seed=201),
                "AAA": _session_series("1999-12-01", "2026-07-08", seed=202),
            },
        )
        build(root=root, as_of=date(2026, 7, 8), generated_at="2026-07-09T04:00:00Z", resamples=80)
        payloads.append(
            (root / "site" / "seasonalitydata" / "entities" / "AAA.json").read_bytes()
            + (root / "site" / "seasonalitydata" / "index.json").read_bytes()
        )
    assert payloads[0] == payloads[1]


def test_selection_cache_is_reused_when_the_panel_has_not_moved(tmp_path):
    root = tmp_path / "cached"
    _write_store(
        root,
        {
            "SPY": _session_series("1999-12-01", "2026-07-08", seed=301),
            "AAA": _session_series("1999-12-01", "2026-07-08", seed=302),
        },
    )
    first = build(root=root, as_of=date(2026, 7, 8), generated_at="2026-07-09T04:00:00Z", resamples=80)
    assert first["null_recomputed"] == 2

    second = build(root=root, as_of=date(2026, 7, 9), generated_at="2026-07-10T04:00:00Z", resamples=80)
    assert second["null_recomputed"] == 0, "an unchanged complete-year panel must reuse its null"

    cache = json.loads((root / "data" / "seasonality" / "selection" / "AAA.json").read_text())
    assert cache["schema"] == "biopharma_seasonality.selection_cache.v1"
    assert cache["raw"]["panel_hash"].startswith("sha256:")
    assert cache["neutral"] is not None

    # A vendor re-adjustment of the complete-year panel must bust it.
    cache_path = root / "data" / "seasonality" / "selection" / "AAA.json"
    cache["raw"]["panel_hash"] = "sha256:" + "0" * 64
    cache_path.write_text(json.dumps(cache), encoding="utf-8")
    third = build(root=root, as_of=date(2026, 7, 10), generated_at="2026-07-11T04:00:00Z", resamples=80)
    assert third["null_recomputed"] == 1


def test_cache_is_busted_by_a_shape_change_not_only_by_the_panel(tmp_path):
    """A code change to the cached block is invisible to the panel hash.

    Without a format/shape check the cache would serve blocks built by the
    PREVIOUS version of the scanner forever — the panel did not move, so nothing
    would ever ask for them again.
    """
    root = tmp_path / "shape"
    _write_store(
        root,
        {
            "SPY": _session_series("1999-12-01", "2026-07-08", seed=501),
            "AAA": _session_series("1999-12-01", "2026-07-08", seed=502),
        },
    )
    build(root=root, as_of=date(2026, 7, 8), generated_at="2026-07-09T04:00:00Z", resamples=60)
    cache_path = root / "data" / "seasonality" / "selection" / "AAA.json"
    cache = json.loads(cache_path.read_text())

    stale_format = json.loads(json.dumps(cache))
    stale_format["raw"]["format"] = SELECTION_FORMAT - 1
    cache_path.write_text(json.dumps(stale_format), encoding="utf-8")
    assert (
        build(root=root, as_of=date(2026, 7, 9), generated_at="2026-07-10T04:00:00Z", resamples=60)[
            "null_recomputed"
        ]
        == 1
    )

    missing_key = json.loads(json.dumps(cache))
    missing_key["raw"].pop("max_abs_t_ladder")
    cache_path.write_text(json.dumps(missing_key), encoding="utf-8")
    assert (
        build(root=root, as_of=date(2026, 7, 10), generated_at="2026-07-11T04:00:00Z", resamples=60)[
            "null_recomputed"
        ]
        == 1
    )


def test_build_never_raises_on_a_bad_symbol(tmp_path):
    root = tmp_path / "faulty"
    _write_store(root, {"SPY": _session_series("1999-12-01", "2026-07-08", seed=401)})
    (root / "data" / "yahoo" / "BROKEN.parquet").write_bytes(b"not a parquet file")
    summary = build(root=root, as_of=date(2026, 7, 8), generated_at="2026-07-09T04:00:00Z", resamples=40)
    assert summary["n_entities"] == 1


def test_methodology_manifest_still_admits_no_forecast_screener_or_event_graph():
    manifest = build_methodology_manifest(date(2026, 8, 1))
    availability = manifest["availability"]
    assert availability["live_forecasts"] is False
    assert availability["live_screener"] is False
    assert availability["live_event_graph"] is False
    assert availability["live_calendar_clock"] is True
    assert availability["live_selection_correction"] is True
    assert manifest["calendar_clock"]["window_family"]["n_candidates"] == 2645
    assert manifest["calendar_clock"]["window_family"]["wraps_year"] is False
    assert manifest["calendar_clock"]["unit_of_evidence"] == "one_complete_year"
    assert manifest["calendar_clock"]["disclosed_limits"]["price_adjustment_is_point_in_time"] is False
    assert manifest["calendar_clock"]["disclosed_limits"]["universe_is_survivorship_biased"] is True
    for key in (
        "may_rank",
        "may_gate",
        "may_size",
        "may_originate",
        "may_rewrite_geometry",
        "may_boost_confidence",
        "may_deescalate",
    ):
        assert manifest["authority"][key] is False


def test_artifact_carries_no_score_rank_or_ordering(built):
    """No ranking anywhere: this tranche is an explorer, not a screener."""
    _root, _summary, index_payload, entity = built
    banned = {"rank", "score", "ranking", "percentile_rank", "grade", "conviction"}
    for blob in (entity, index_payload):
        text = json.dumps(blob)
        for word in banned:
            assert f'"{word}"' not in text, f"{word} appeared as a key in a display-tier artifact"
    symbols = [row["symbol"] for row in index_payload["entities"]]
    assert symbols == sorted(symbols), "the index is sorted by ticker, never by any statistic"


def test_a_lookback_gets_its_own_null_never_the_full_panel_s():
    """The `10y | 15y | 25y | Max` pills each change the panel, so each needs its own null.

    Judging a 10-year window against a 25-year null compares it to a threshold
    built from a different sample size and a different autocorrelation structure,
    and it errs in the flattering direction for short lookbacks.
    """
    panel = _noise_panel(25, seed=141)
    nulls = season_scanner.lookback_nulls(panel, n_resamples=150, seed=7)
    assert set(nulls) == {"10", "15"}, "a lookback >= the panel IS the panel — omit it"
    for key, block in nulls.items():
        assert block["n_years"] == int(key)
        assert set(block) == {
            "method", "B", "seed", "n_years", "max_abs_t_quantiles", "max_abs_t_quantile_ladder",
        }
        assert block["method"] == season_scanner.NULL_METHOD
        q = block["max_abs_t_quantiles"]
        assert q["0.90"] <= q["0.95"] <= q["0.99"]

    full = season_scanner.null_summary(panel.daily, n_resamples=150, seed=7)
    assert nulls["10"]["max_abs_t_quantiles"]["0.95"] != full["max_abs_t_quantiles"]["0.95"], (
        "a 10-year null identical to the 25-year null means the sub-panel never took effect"
    )

    short = _noise_panel(12, seed=141)
    assert set(season_scanner.lookback_nulls(short, n_resamples=80, seed=7)) == {"10"}


def test_lookback_null_uses_the_most_recent_years():
    panel = _noise_panel(25, seed=143)
    direct = season_scanner.null_summary(panel.daily[-10:], n_resamples=120, seed=(7 + 10) % (2**32))
    via = season_scanner.lookback_nulls(panel, n_resamples=120, seed=7)["10"]
    assert via == direct


def test_partial_run_never_prunes_or_republishes_the_index(tmp_path):
    """`--symbols AAPL` must not delete the other ~219 entity files.

    The failure mode is total and silent: `covered` came from the FILTERED run, so
    prune removed everything else and `index.json` was rewritten to a single row.
    """
    root = tmp_path / "partial"
    _write_store(
        root,
        {
            "SPY": _session_series("1999-12-01", "2026-07-08", seed=701),
            "AAA": _session_series("1999-12-01", "2026-07-08", seed=702),
            "BBB": _session_series("1999-12-01", "2026-07-08", seed=703),
        },
    )
    build(root=root, as_of=date(2026, 7, 8), generated_at="2026-07-09T04:00:00Z", resamples=40)
    entities = root / "site" / "seasonalitydata" / "entities"
    index_path = root / "site" / "seasonalitydata" / "index.json"
    assert sorted(p.stem for p in entities.glob("*.json")) == ["AAA", "BBB", "SPY"]
    before = index_path.read_bytes()

    summary = build(
        root=root,
        as_of=date(2026, 7, 8),
        generated_at="2026-07-09T05:00:00Z",
        resamples=40,
        symbols=["AAA"],
    )
    assert summary["partial"] is True
    assert sorted(p.stem for p in entities.glob("*.json")) == ["AAA", "BBB", "SPY"]
    assert index_path.read_bytes() == before, "a partial run must not speak for the universe"


def test_cache_is_busted_when_the_window_family_changes(tmp_path, monkeypatch):
    """Same data is not the same question.

    The panel hash cannot see a change to the SEARCH. Widen the horizons without
    this and every symbol keeps its stored null, so the artifact publishes a
    3075-window search priced by a 2645-window null — with no visible symptom.
    """
    root = tmp_path / "family"
    _write_store(
        root,
        {
            "SPY": _session_series("1999-12-01", "2026-07-08", seed=801),
            "AAA": _session_series("1999-12-01", "2026-07-08", seed=802),
        },
    )
    build(root=root, as_of=date(2026, 7, 8), generated_at="2026-07-09T04:00:00Z", resamples=40)
    assert build(root=root, as_of=date(2026, 7, 9), generated_at="2026-07-10T04:00:00Z", resamples=40)[
        "null_recomputed"
    ] == 0

    monkeypatch.setattr(season_scanner, "TOP_K_DISCOVERED", 4)
    assert season_scanner.family_fingerprint() != json.loads(
        (root / "data" / "seasonality" / "selection" / "AAA.json").read_text()
    )["raw"]["family_hash"]
    assert build(root=root, as_of=date(2026, 7, 10), generated_at="2026-07-11T04:00:00Z", resamples=40)[
        "null_recomputed"
    ] == 2


def test_a_year_still_in_progress_is_not_evidence(tmp_path):
    """From Dec 20 the completeness rule would admit the year you are standing in.

    The rule was written for vendor coverage of years that are OVER. Applied to the
    live year it does two bad things at once for the last ~10 sessions of every
    December: a truncated year joins the historical evidence base with its
    remaining slots reading as flat zero returns, AND the "you are here" overlay
    disappears because the year is no longer partial.
    """
    closes = _session_series("2004-12-01", "2026-12-22", seed=901)
    panel = season_panel.build_year_panel(season_panel.daily_log_returns(closes), symbol="DEC")
    assert 2026 not in panel.years, "a year that has not finished is not a complete year"
    assert panel.years[-1] == 2025
    assert panel.current_year == 2026, "and it must still be carried as the partial year"
    assert panel.current_last_index is not None

    finished = _session_series("2004-12-01", "2026-12-31", seed=901)
    done = season_panel.build_year_panel(season_panel.daily_log_returns(finished), symbol="DEC")
    assert done.years[-1] == 2026 and done.current_year is None


def test_benchmark_regressed_on_itself_yields_no_neutral_panel(tmp_path):
    """Residual dust is not a market-neutral panel.

    pandas computes rolling cov and rolling var down separate code paths, so beta
    against oneself is 1 +/- 1e-16 rather than exactly 1. Scanned, that dust
    produces a confident "surviving" 20-day season fitted entirely to rounding
    error. Only the builder's symbol check stood between that and the artifact.
    """
    market = season_panel.daily_log_returns(_session_series("2000-01-01", "2026-07-08", seed=911))
    assert season_panel.build_neutral_panel(
        market, market, symbol="SPY", keep_years=tuple(range(2001, 2026))
    ) is None

    other = season_panel.daily_log_returns(_session_series("2000-01-01", "2026-07-08", seed=912))
    real = season_panel.build_neutral_panel(
        other, market, symbol="AAA", keep_years=tuple(range(2001, 2026))
    )
    assert real is not None and real.n_years > 0


def test_an_unreadable_benchmark_does_not_destroy_cached_neutral_blocks(tmp_path):
    """One bad night must not cost every symbol a full resample the night after."""
    root = tmp_path / "outage"
    _write_store(
        root,
        {
            "SPY": _session_series("1999-12-01", "2026-07-08", seed=921),
            "AAA": _session_series("1999-12-01", "2026-07-08", seed=922),
        },
    )
    build(root=root, as_of=date(2026, 7, 8), generated_at="2026-07-09T04:00:00Z", resamples=40)
    cache_path = root / "data" / "seasonality" / "selection" / "AAA.json"
    good = json.loads(cache_path.read_text())
    assert good["neutral"] is not None

    (root / "data" / "yahoo" / "SPY.parquet").write_bytes(b"corrupt")
    build(root=root, as_of=date(2026, 7, 9), generated_at="2026-07-10T04:00:00Z", resamples=40)
    after = json.loads(cache_path.read_text())
    assert after["neutral"] == good["neutral"], (
        "a stale-but-good neutral block was overwritten with null on a benchmark outage"
    )


def test_program_rates_count_only_symbols_whose_null_was_computed(tmp_path):
    """The denominator the honesty strip compares against 5% must be symbols TESTED."""
    root = tmp_path / "budget"
    _write_store(
        root,
        {
            "SPY": _session_series("1999-12-01", "2026-07-08", seed=931),
            "AAA": _session_series("1999-12-01", "2026-07-08", seed=932),
            "BBB": _session_series("1999-12-01", "2026-07-08", seed=933),
        },
    )
    build(
        root=root,
        as_of=date(2026, 7, 8),
        generated_at="2026-07-09T04:00:00Z",
        resamples=40,
        null_budget=1,
    )
    index_payload = json.loads((root / "site" / "seasonalitydata" / "index.json").read_text())
    untested = [e["symbol"] for e in index_payload["entities"]]
    entities = {
        s: json.loads((root / "site" / "seasonalitydata" / "entities" / f"{s}.json").read_text())
        for s in untested
    }
    with_family = sum(1 for e in entities.values() if e["family"] is not None)
    assert with_family < len(entities), "fixture must actually exhaust the budget"
    assert index_payload["program_rates"]["raw"]["n_symbols"] == with_family


def test_display_labels_resolve_for_the_covered_set(tmp_path):
    """68% of symbols shipped as `AMGN AMGN` with no sector, and nothing said so.

    The §6 picker renders `TICKER · Name · N years`, so an unresolved symbol shows
    its ticker twice. The old chain relied on a SEC file that does not exist in
    this repo and degraded silently to the ticker.
    """
    root = tmp_path / "labels"
    _write_store(
        root,
        {
            "SPY": _session_series("1999-12-01", "2026-07-08", seed=941),
            "ABT": _session_series("1999-12-01", "2026-07-08", seed=942),
            "MMM": _session_series("1999-12-01", "2026-07-08", seed=943),
            "ZZZZ": _session_series("1999-12-01", "2026-07-08", seed=944),
        },
    )
    membership = root / "data" / "universe" / "membership.parquet"
    membership.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "ticker": ["ABT", "MMM"],
            "name": ["Abbott Laboratories", "3M"],
            "sector": ["Health Care", "Industrials"],
        }
    ).to_parquet(membership)

    build(root=root, as_of=date(2026, 7, 8), generated_at="2026-07-09T04:00:00Z", resamples=40)
    rows = {
        e["symbol"]: e
        for e in json.loads((root / "site" / "seasonalitydata" / "index.json").read_text())["entities"]
    }
    assert rows["ABT"]["name"] == "Abbott Laboratories" and rows["ABT"]["sector"] == "Health Care"
    assert rows["MMM"]["name"] == "3M" and rows["MMM"]["sector"] == "Industrials"
    assert rows["SPY"]["name"] == "Benchmark", "config labels must outrank the registry"
    assert rows["ZZZZ"]["name"] == "ZZZZ", "an unknown ticker still degrades — legibly"

    resolved = sum(1 for e in rows.values() if e["name"] != e["symbol"])
    assert resolved / len(rows) >= 0.75


def test_the_real_universe_resolves_most_of_its_display_names():
    """A floor on the SHIPPED artifact, so the silent degrade cannot come back."""
    root = Path(__file__).resolve().parents[1]
    index_path = root / "site" / "seasonalitydata" / "index.json"
    if not index_path.exists():  # pragma: no cover — artifact-less checkout
        pytest.skip("seasonality index not built in this checkout")
    rows = json.loads(index_path.read_text())["entities"]
    assert rows
    resolved = [e for e in rows if e["name"] != e["symbol"]]
    share = len(resolved) / len(rows)
    assert share >= 0.80, (
        f"only {len(resolved)}/{len(rows)} ({share:.0%}) covered symbols have a display "
        "name — the picker would render the ticker twice for the rest"
    )
    sectored = [e for e in rows if e["sector"]]
    assert len(sectored) / len(rows) >= 0.60
