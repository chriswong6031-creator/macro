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
ADDED_FAMILY_KEYS = {"registered_panel", "best"}
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
    """A synthetic instrument that prints on business days only."""
    index = pd.bdate_range(start, end)
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


def test_null_is_calibrated_on_pure_noise():
    """The whole correction rests on this: ~5% of noise panels should fire.

    A test that only proves "the implanted signal fires" would pass on a null
    that never fires at all. This is the other half, and it is what separates a
    real familywise correction from a decorative one.
    """
    fires = 0
    trials = 24
    for seed in range(trials):
        panel = _noise_panel(15, seed=1000 + seed)
        observed = season_scanner.best_window(panel.cum)
        null_max, _ = season_scanner.null_max_abs_t(panel.daily, n_resamples=250, seed=seed)
        if observed is not None and observed[2] >= np.quantile(null_max, 0.95):
            fires += 1
    rate = fires / trials
    # Nominal is 5%. The bound is deliberately loose for a 24-panel sample, but
    # it still fails a null that fires constantly (a broken statistic) or one
    # whose threshold is so high nothing can ever clear it.
    assert rate <= 0.30, f"pure-noise fire rate {rate:.0%} is far above the 5% nominal"
    assert fires <= 6


def test_exceedance_is_the_share_of_resamples_at_least_this_strong():
    null_max = np.array([1.0, 2.0, 3.0, 4.0])
    assert season_scanner.exceedance_pct(null_max, 3.0) == pytest.approx(50.0)
    assert season_scanner.exceedance_pct(null_max, 5.0) == pytest.approx(0.0)
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
        assert 0.0 < entry["p_raw"] <= 1.0
        assert 0.0 < entry["q_by"] <= 1.0
        assert entry["p_adj_maxt_family"] >= entry["p_raw"] - 1e-12, (
            "the familywise-adjusted p can never be smaller than the raw marginal p"
        )
    assert result.best is not None and result.best["clears_95"] is True


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
