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


# ---------------------------------------------------------------------------
# store separation — the backfill must never touch the sealed panel
# ---------------------------------------------------------------------------

def test_backfill_targets_the_deep_store_not_the_sealed_panel():
    """engine/personality_flow_absorption (PSS-AF1, frozen) seals every row in
    panel.parquet with a row count + SHA256. Backfilling history into that file broke
    the seal even though the write was purely additive (0 rows missing, 0 modified,
    258,198 added) — the seal is tamper-evidence and cannot tell the two apart.
    History therefore lands in panel_deep.parquet and the desk unions the two.
    """
    from scripts import backfill_finra_short_volume as bf

    assert bf._panel_path().name == "panel_deep.parquet"
    assert bf._sealed_panel_path().name == "panel.parquet"
    assert bf._panel_path() != bf._sealed_panel_path()


def test_backfill_refuses_to_write_the_sealed_panel():
    """Fail-closed backstop: pointing the flush at panel.parquet must raise BEFORE the
    write, not surface as a red attestation two hours later in CI."""
    from scripts import backfill_finra_short_volume as bf

    with pytest.raises(RuntimeError, match="refusing to write panel.parquet"):
        bf._flush(bf._sealed_panel_path(), [pd.DataFrame({"date": [], "ticker": []})])


def test_desk_unions_both_stores_and_prefers_the_collector_on_overlap(tmp_path, monkeypatch):
    """The collector carries FINRA's latest restatement of a session, so on an
    overlapping (date, ticker) its row must win over the deep store's older copy."""
    import scripts.build_darkpool_desk as bdd

    d = tmp_path / "finra_short_volume"
    d.mkdir(parents=True)
    cols = ["date", "ticker", "short_vol", "short_exempt", "total_vol", "short_ratio"]
    deep = pd.DataFrame([["2023-08-01", "AAA", 1.0, 0.0, 10.0, 0.10],
                         ["2026-07-30", "AAA", 2.0, 0.0, 20.0, 0.10]], columns=cols)
    coll = pd.DataFrame([["2026-07-30", "AAA", 9.0, 0.0, 99.0, 0.09],   # restated
                         ["2026-07-31", "AAA", 3.0, 0.0, 30.0, 0.10]], columns=cols)
    deep.to_parquet(d / "panel_deep.parquet")
    coll.to_parquet(d / "panel.parquet")
    monkeypatch.setattr(bdd, "PANEL_DEEP_PATH", d / "panel_deep.parquet")
    monkeypatch.setattr(bdd, "PANEL_PATH", d / "panel.parquet")

    out = bdd._load_panel()
    assert len(out) == 3, "union should dedup the overlapping session, not double it"
    assert set(out["date"].dt.strftime("%Y-%m-%d")) == {"2023-08-01", "2026-07-30", "2026-07-31"}
    restated = out[out["date"] == pd.Timestamp("2026-07-30")].iloc[0]
    assert restated["total_vol"] == 99.0, "collector restatement must win over the deep copy"


# ---------------------------------------------------------------------------
# firm roles — retail internalisation vs institutional risk transfer
# ---------------------------------------------------------------------------

def test_firm_roles_roster_loads_and_classifies_the_major_internalisers():
    from engine.darkpool_signals import firm_role, firm_roles

    r = firm_roles()
    assert len(r["by_firm"]) > 30, "roster failed to load"
    assert firm_role("CITADEL SECURITIES LLC") == "retail_wholesaler"
    assert firm_role("VIRTU AMERICAS LLC") == "retail_wholesaler"
    assert firm_role("GOLDMAN SACHS & CO. LLC") == "institutional_desk"
    assert firm_role("MORGAN STANLEY & CO. LLC") == "institutional_desk"
    assert firm_role("DRIVEWEALTH, LLC") == "retail_broker"
    assert firm_role("citadel securities llc") == "retail_wholesaler", "match must be case-insensitive"


def test_de_minimis_and_unknown_firms_are_never_defaulted_onto_a_side():
    """FINRA's "De Minimis Firms" aggregate is ~36% of non-ATS volume and is genuinely
    unattributable. Folding it (or any unlisted firm) into either side would invent an
    attribution for a third of the tape."""
    from engine.darkpool_signals import firm_role

    assert firm_role("De Minimis Firms") is None
    assert firm_role("SOME BROKER NOBODY LISTED LLC") is None
    assert firm_role(None) is None


def test_role_mix_splits_a_names_off_exchange_volume_and_keeps_unclassified_visible():
    ats = _venue_frame([["2026-06-22", "AAA", "UBSA", "UBS ATS", 200.0, 4, 40000.0]])
    non = _venue_frame([
        ["2026-06-22", "AAA", "", "CITADEL SECURITIES LLC", 400.0, 20, 80000.0],
        ["2026-06-22", "AAA", "", "GOLDMAN SACHS & CO. LLC", 200.0, 2, 40000.0],
        ["2026-06-22", "AAA", "", "De Minimis Firms", 200.0, 5, 40000.0],
    ])
    out = venue_split(ats, non)["AAA"]
    # fractions are of TOTAL off-exchange (ATS 200 + non-ATS 800 = 1000)
    assert out["ats_frac"] == pytest.approx(0.20)
    assert out["frac_retail_wholesaler"] == pytest.approx(0.40)
    assert out["frac_institutional_desk"] == pytest.approx(0.20)
    assert out["frac_unclassified"] == pytest.approx(0.20)
    assert out["retail_frac"] == pytest.approx(0.40)
    # the four buckets plus ats_frac account for the whole tape — nothing vanishes
    total = (out["ats_frac"] + out["frac_retail_wholesaler"]
             + out["frac_retail_broker"] + out["frac_institutional_desk"]
             + out["frac_unclassified"])
    assert total == pytest.approx(1.0)


def test_role_mix_is_absent_not_zero_when_non_ats_is_missing():
    """No non-ATS week ⇒ no attribution. Zeros would read as 'no retail flow'."""
    ats = _venue_frame([["2026-06-22", "AAA", "UBSA", "UBS ATS", 200.0, 4, 40000.0]])
    out = venue_split(ats, None)["AAA"]
    assert out.get("frac_retail_wholesaler") is None
    assert out.get("frac_unclassified") is None


def test_unreadable_roster_fails_open_to_unclassified(tmp_path):
    """A missing roster must degrade to 'we cannot attribute this', never to a side."""
    from engine.darkpool_signals import firm_roles

    r = firm_roles(root=tmp_path)          # no knowledge/ dir under tmp_path
    assert r["by_firm"] == {}
    non = _venue_frame([["2026-06-22", "AAA", "", "CITADEL SECURITIES LLC", 100.0, 5, 1000.0]])
    out = venue_split(None, non, roles=r)["AAA"]
    assert out["frac_unclassified"] == pytest.approx(1.0)
    assert out["frac_retail_wholesaler"] == pytest.approx(0.0)


def test_counterparty_copy_omits_the_line_when_nothing_is_attributable():
    from engine.darkpool_context import _counterparty_character

    assert _counterparty_character({"ats_frac": 0.3}) is None
    line = _counterparty_character({
        "frac_retail_wholesaler": 0.60, "frac_institutional_desk": 0.05,
        "frac_unclassified": 0.10})
    assert "60% via retail wholesalers" in line["en"]
    assert "10% unattributed" in line["en"], "the unattributed remainder must be printed"
    # a bank-dominated name leads with the bank figure
    bank = _counterparty_character({
        "frac_retail_wholesaler": 0.10, "frac_institutional_desk": 0.40,
        "frac_unclassified": 0.05})
    assert bank["en"].startswith("40% via bank desks")


def test_desk_still_loads_when_the_deep_store_is_absent(tmp_path, monkeypatch):
    """A fresh checkout has no deep store — that is a shorter panel, not a failure."""
    import scripts.build_darkpool_desk as bdd

    d = tmp_path / "finra_short_volume"
    d.mkdir(parents=True)
    cols = ["date", "ticker", "short_vol", "short_exempt", "total_vol", "short_ratio"]
    pd.DataFrame([["2026-07-31", "AAA", 3.0, 0.0, 30.0, 0.10]],
                 columns=cols).to_parquet(d / "panel.parquet")
    monkeypatch.setattr(bdd, "PANEL_DEEP_PATH", d / "panel_deep.parquet")   # absent
    monkeypatch.setattr(bdd, "PANEL_PATH", d / "panel.parquet")

    out = bdd._load_panel()
    assert out is not None and len(out) == 1
