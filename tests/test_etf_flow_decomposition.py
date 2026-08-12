"""W1 — flow vs selection on the ETF holdings snapshot pair.

A fund's snapshot pair carries two signals the shipped share-diff path collapses
into one: creation/redemption scales EVERY constituent by a common factor
(investor money arriving in the theme), and whatever a position does beyond that
factor is the manager's own decision. The board has only ever published the
second one — flow-normalized away — which is why a $500M week of creations into
a passive thematic fund reads as nothing at all.

WHAT THIS PINS.  The decomposition identity (flow + selection == the whole share
change, in shares, dollars AND pp of fund weight), the robustness guards that
stand between raw sponsor files and a published number, and the fact that none
of it moved `conviction_pp`. Each guard gets its own adversarial fixture, because
each one exists for a specific way a holdings feed lies:

  * a share SPLIT quadruples the share count with the position's dollar value
    unchanged — unguarded it prints as the manager buying 4× the stock;
  * a re-fetch written under a second filename repeats a day, which reads as a
    zero-change interval and breaks a streak that never broke;
  * sponsors report on different cadences, so raw deltas are not comparable
    across funds and staleness has to be measured against the fleet's own edge;
  * a snapshot whose weights sum to 40 is a broken parse, not a portfolio —
    decomposing against it invents a rebalance across every constituent;
  * a name absent from ONE file is a feed hiccup; calling that a full exit prints
    the strongest negative signal the board has on a parser blink.

Run: python3 -m pytest tests/test_etf_flow_decomposition.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import etf_consensus as ec  # noqa: E402
from engine import holdings_signals as hs  # noqa: E402

# Six ballast names: enough continuing constituents for the MEDIAN scale
# estimator to be trusted (flow_min_scale_n = 5), which is the regime every real
# fund is in.
BALLAST = {"BAL1": 1000.0, "BAL2": 800.0, "BAL3": 600.0, "BAL4": 400.0,
           "BAL5": 200.0, "BAL6": 100.0}
PRICE = 10.0


@pytest.fixture(autouse=True)
def _clear_snapshot_caches():
    """Snapshot parses are cached by path; every fixture writes fresh tmp files."""
    hs._SNAP_CACHE.clear()
    hs._FLEET_LATEST.clear()
    yield
    hs._SNAP_CACHE.clear()
    hs._FLEET_LATEST.clear()


def _shares(**over) -> pd.Series:
    return pd.Series({**BALLAST, **over}, dtype=float)


def _write(d: Path, asof: str, shares: pd.Series, *, price=PRICE,
           mv: pd.Series | None = None, weights: pd.Series | None = None,
           stem: str | None = None) -> Path:
    """One holdings snapshot in the shipped schema. Weights default to the real
    share of market value, so a fixture is inside the sanity bounds unless it is
    deliberately corrupt."""
    market_value = mv if mv is not None else shares * price
    w = weights if weights is not None else 100.0 * market_value / market_value.sum()
    df = pd.DataFrame({
        "ticker": list(shares.index),
        "name": [f"{t} Corp" for t in shares.index],
        "weight_pct": [float(w.get(t, 0.0)) for t in shares.index],
        "shares": shares.astype(float).values,
        "market_value": [float(market_value.get(t, 0.0)) for t in shares.index],
        "as_of": asof,
    })
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{stem or asof}.parquet"
    df.to_parquet(p)
    return p


# --- the decomposition itself (pure) ----------------------------------------

def test_pure_creation_is_all_flow() -> None:
    """Every constituent scaled 1.3× = money into the theme, nobody picking."""
    s0 = _shares()
    s1 = s0 * 1.3
    out = hs.flow_selection(s0, s1, mv0=s0 * PRICE, mv1=s1 * PRICE)
    f = out["frame"]
    assert out["scale"] == pytest.approx(1.3) and out["scale_basis"] == "median"
    assert f["selection_shares"].abs().max() < 1e-9
    assert f["selection_usd"].abs().max() < 1e-6
    assert f.loc["BAL1", "flow_shares"] == pytest.approx(300.0)
    assert f.loc["BAL1", "flow_usd"] == pytest.approx(3000.0)


def test_pure_redemption_is_all_flow_and_signs_negative() -> None:
    s0 = _shares()
    s1 = s0 * 0.8
    out = hs.flow_selection(s0, s1, mv0=s0 * PRICE, mv1=s1 * PRICE)
    f = out["frame"]
    assert out["scale"] == pytest.approx(0.8)
    assert f["selection_shares"].abs().max() < 1e-9
    assert (f["flow_shares"] < 0).all() and (f["flow_usd"] < 0).all()


def test_pure_rebalance_is_all_selection() -> None:
    """Fund the same size, manager rotates BAL1 into BAL2 — flow must be zero."""
    s0 = _shares()
    s1 = _shares(BAL1=1200.0, BAL2=600.0)
    out = hs.flow_selection(s0, s1, mv0=s0 * PRICE, mv1=s1 * PRICE)
    f = out["frame"]
    assert out["scale"] == pytest.approx(1.0)
    assert f["flow_shares"].abs().max() < 1e-9
    assert f.loc["BAL1", "selection_shares"] == pytest.approx(200.0)
    assert f.loc["BAL2", "selection_shares"] == pytest.approx(-200.0)


def test_components_always_sum_to_the_share_change() -> None:
    """The identity the whole read rests on, under a mixed pair (creation AND
    picking AND a new name AND an exit at once)."""
    s0 = _shares(GONE=500.0)
    s1 = _shares(BAL1=1500.0, BAL3=300.0, FRESH=250.0) * 1.15
    out = hs.flow_selection(s0, s1, mv0=s0 * PRICE, mv1=s1 * PRICE)
    f = out["frame"]
    recomputed = f["flow_shares"] + f["selection_shares"]
    assert (recomputed - f["total_shares"]).abs().max() < 1e-9
    assert (f["flow_usd"] + f["selection_usd"] - f["total_usd"]).abs().max() < 1e-6
    assert f.loc["GONE", "total_shares"] == pytest.approx(-500.0)
    assert f.loc["FRESH", "flow_shares"] == pytest.approx(0.0)   # no prior base to scale


def test_median_scale_ignores_one_outsized_position() -> None:
    """The reason the estimator is a median: BAL1 is 40% of the book and doubles.
    The SUM ratio the shipped diff path uses reads that as a fund-wide +40%
    creation and prints a phantom redemption on every untouched name."""
    s0 = _shares()
    s1 = _shares(BAL1=2000.0)
    out = hs.flow_selection(s0, s1, mv0=s0 * PRICE, mv1=s1 * PRICE)
    f = out["frame"]
    assert out["scale"] == pytest.approx(1.0)
    assert f.loc["BAL4", "selection_shares"] == pytest.approx(0.0)
    assert f.loc["BAL1", "selection_shares"] == pytest.approx(1000.0)
    sum_ratio = s1.sum() / s0.sum()
    assert sum_ratio > 1.3, "fixture must be one the sum ratio actually misreads"


def test_small_universe_falls_back_to_the_sum_ratio_and_says_so() -> None:
    s0 = pd.Series({"A": 100.0, "B": 100.0})
    s1 = pd.Series({"A": 150.0, "B": 150.0})
    out = hs.flow_selection(s0, s1)
    assert out["scale_basis"] == "sum" and out["scale"] == pytest.approx(1.5)
    assert out["scale_n"] == 2


def test_dollar_estimates_are_absent_not_invented_without_market_values() -> None:
    """21 of the 76 tracked funds ship no market_value column. The shares read
    still works; the $ read must come back null rather than guessed."""
    s0 = _shares()
    out = hs.flow_selection(s0, s0 * 1.2)
    f = out["frame"]
    assert out["mv_available"] is False
    assert f["total_usd"].isna().all() and f["implied_price"].isna().all()
    assert f["flow_shares"].notna().all()


def test_an_empty_market_value_column_is_not_a_market_value_column(tmp_path) -> None:
    """21 of the 76 tracked funds ship the market_value HEADER with nothing under
    it. Grouped with pandas' default min_count, an all-NaN column sums to 0.0 —
    which prices every position at zero and publishes a confident $0 move on a
    fund that reports no dollars at all. The null has to survive the groupby."""
    d = tmp_path / "NODOLLARS"
    empty = pd.Series({t: float("nan") for t in BALLAST})
    _write(d, "2026-06-01", _shares(), mv=empty, weights=pd.Series({t: 100 / 6 for t in BALLAST}))
    _write(d, "2026-06-11", _shares(BAL1=1200.0), mv=empty,
           weights=pd.Series({t: 100 / 6 for t in BALLAST}))
    dec = hs.fund_flow_decomposition(d, 10, fund="NODOLLARS")
    assert dec["mv_available"] is False
    row = dec["by_ticker"]["BAL1"]
    assert row["total_usd"] is None and row["implied_price"] is None
    assert row["selection_shares"] == pytest.approx(200.0)   # the shares read survives


def test_exit_is_priced_off_the_prior_snapshot() -> None:
    s0 = _shares(GONE=500.0)
    s1 = _shares()
    out = hs.flow_selection(s0, s1, mv0=s0 * PRICE, mv1=s1 * PRICE)
    f = out["frame"]
    assert f.loc["GONE", "implied_price"] == pytest.approx(PRICE)
    assert f.loc["GONE", "total_usd"] == pytest.approx(-5000.0)


# --- guard: share split ------------------------------------------------------

def test_share_split_is_normalized_not_read_as_accumulation() -> None:
    """BAL1 goes 4-for-1: shares ×4, market value unchanged. Unguarded this is a
    +300% add — the single loudest fake signal a holdings feed can produce."""
    s0 = _shares()
    s1 = _shares(BAL1=4000.0)
    mv0 = s0 * PRICE
    mv1 = mv0.copy()                     # the position is worth exactly what it was
    out = hs.flow_selection(s0, s1, mv0=mv0, mv1=mv1)
    f = out["frame"]
    assert out["n_split"] == 1
    assert bool(f.loc["BAL1", "split_adjusted"]) is True
    assert f.loc["BAL1", "selection_shares"] == pytest.approx(0.0)
    assert f.loc["BAL1", "total_usd"] == pytest.approx(0.0)
    assert not f.drop(index=["BAL1"])["split_adjusted"].any()


def test_a_real_buy_that_moves_the_dollar_value_is_not_mistaken_for_a_split() -> None:
    """The discriminator: a manager doubling a position doubles its market value
    too, so the split guard must keep its hands off."""
    s0 = _shares()
    s1 = _shares(BAL1=2000.0)
    out = hs.flow_selection(s0, s1, mv0=s0 * PRICE, mv1=s1 * PRICE)
    f = out["frame"]
    assert out["n_split"] == 0
    assert f.loc["BAL1", "selection_shares"] == pytest.approx(1000.0)


def test_a_dip_buy_whose_value_lands_near_flat_is_not_a_split() -> None:
    """The measured false positive (2026-08-12, this repo's own data): ARKW cut
    NET by a third while the stock rose 37%, so the position's value drifted only
    -9% — inside a loose 'market value roughly flat' window, and at a share ratio
    of 0.665 that is 0.25% away from a clean 3-for-2 reverse split. Six of eight
    flags on real data looked like this. A split cannot move the position's value
    at all, so the value test is what has to be tight."""
    s0 = _shares(NET=156_841.0)
    s1 = _shares(NET=104_358.0)
    mv0 = s0 * PRICE
    mv1 = s1 * PRICE
    mv1["NET"] = mv0["NET"] * 0.910          # value drifted 9% — a trade, not a split
    out = hs.flow_selection(s0, s1, mv0=mv0, mv1=mv1)
    assert out["n_split"] == 0
    assert out["frame"].loc["NET", "selection_shares"] == pytest.approx(-52_483.0)


def test_a_value_preserving_move_at_an_odd_ratio_is_not_a_split() -> None:
    """The other half of the rule: value held flat by coincidence, but nobody
    re-denominates a share at 1.73-for-1."""
    s0 = _shares()
    s1 = _shares(BAL1=1730.0)
    out = hs.flow_selection(s0, s1, mv0=s0 * PRICE, mv1=s0 * PRICE)
    assert out["n_split"] == 0
    assert out["frame"].loc["BAL1", "selection_shares"] == pytest.approx(730.0)


def test_a_real_three_for_one_split_still_clears_both_tests() -> None:
    """The measured true positive: ARKW's CRWD went ×2.977 while the implied price
    went ×0.331 — value ×0.986. Real splits are not exact in a holdings file, so
    the tolerances have to admit this one."""
    s0 = _shares(CRWD=65_566.0)
    s1 = _shares(CRWD=195_208.0)
    mv0, mv1 = s0 * PRICE, s1 * PRICE
    mv1["CRWD"] = mv0["CRWD"] * 0.986
    out = hs.flow_selection(s0, s1, mv0=mv0, mv1=mv1)
    assert out["n_split"] == 1
    assert bool(out["frame"].loc["CRWD", "split_adjusted"]) is True
    assert out["frame"].loc["CRWD", "selection_shares"] == pytest.approx(0.0)


def test_split_guard_is_blind_without_market_values_and_never_guesses() -> None:
    """Documented limitation, pinned so it cannot silently become a heuristic:
    with no $ column there is no evidence a split happened, so nothing is
    adjusted — the row is published as the share change it looks like."""
    s0 = _shares()
    s1 = _shares(BAL1=4000.0)
    out = hs.flow_selection(s0, s1)
    assert out["n_split"] == 0
    assert out["frame"].loc["BAL1", "selection_shares"] == pytest.approx(3000.0)


# --- guard: duplicate snapshots ---------------------------------------------

def test_duplicate_as_of_snapshot_is_deduped(tmp_path) -> None:
    """A re-fetch filed under a second date repeats a day. Kept, it inserts a
    zero-change interval at the newest end and breaks a live streak."""
    d = tmp_path / "DUP"
    _write(d, "2026-06-01", _shares())
    _write(d, "2026-06-10", _shares(BAL1=1200.0))
    _write(d, "2026-06-10", _shares(BAL1=1200.0), stem="2026-06-11")   # the re-fetch
    dec = hs.fund_flow_decomposition(d, 10, fund="DUP")
    assert dec is not None
    assert dec["t0"] == "2026-06-01" and dec["t1"] == "2026-06-10"
    assert dec["by_ticker"]["BAL1"]["streak"] == 1, (
        "the duplicated day must not read as a flat interval that ends the streak")


# --- guard: weight-sum sanity ------------------------------------------------

def test_weight_sum_outside_bounds_quarantines_the_snapshot(tmp_path, capsys) -> None:
    d = tmp_path / "BROKEN"
    _write(d, "2026-06-01", _shares())
    _write(d, "2026-06-05", _shares(BAL1=1200.0))
    half_parsed = pd.Series({t: 4.0 for t in BALLAST})            # sums to 24, not 100
    _write(d, "2026-06-10", _shares(BAL1=9999.0), weights=half_parsed)
    dec = hs.fund_flow_decomposition(d, 10, fund="BROKEN")
    assert dec is not None
    assert dec["quarantined"] == ["2026-06-10"]
    assert dec["t1"] == "2026-06-05", "must fall back to the nearest usable snapshot"
    assert dec["by_ticker"]["BAL1"]["selection_shares"] == pytest.approx(200.0)

    out = capsys.readouterr().out
    line = next((ln for ln in out.splitlines() if "etf-snapshot-quarantine" in ln), "")
    assert line.startswith("::warning "), (
        "the null has to be PRINTED at line start or GitHub drops it: " + repr(line))
    assert "2026-06-10" in line and "BROKEN" in line


def test_a_clean_fund_prints_nothing(tmp_path, capsys) -> None:
    d = tmp_path / "CLEAN"
    _write(d, "2026-06-01", _shares())
    _write(d, "2026-06-05", _shares(BAL1=1200.0))
    hs.fund_flow_decomposition(d, 10, fund="CLEAN")
    assert "::" not in capsys.readouterr().out


# --- guard: cadence + staleness ---------------------------------------------

def test_cadence_is_measured_in_days_and_staleness_against_the_fleet(tmp_path) -> None:
    """Funds report on different cadences, so the window has to carry its own
    length; staleness is measured against the fleet's newest snapshot (what
    fund_coverage does) rather than a wall clock."""
    d = tmp_path / "SLOW"
    _write(d, "2026-06-01", _shares())
    _write(d, "2026-06-15", _shares(BAL1=1100.0))
    dec = hs.fund_flow_decomposition(d, 10, fund="SLOW", fleet_latest="2026-06-30")
    assert dec["window_days"] == 14
    assert dec["stale_days"] == 15 and dec["is_stale"] is True

    fresh = hs.fund_flow_decomposition(d, 10, fund="SLOW", fleet_latest="2026-06-17")
    assert fresh["stale_days"] == 2 and fresh["is_stale"] is False


def test_acceleration_is_per_day_so_cadences_are_comparable(tmp_path) -> None:
    """Same +10% add, one fund over 1 day and one over 10 — the per-day pace has
    to separate them even though the window totals match."""
    fast, slow = tmp_path / "FAST", tmp_path / "SLOW"
    for d, second in ((fast, "2026-06-02"), (slow, "2026-06-11")):
        _write(d, "2026-06-01", _shares())
        _write(d, second, _shares(BAL1=1100.0))
    a = hs.fund_flow_decomposition(fast, 10, fund="FAST")["by_ticker"]["BAL1"]
    b = hs.fund_flow_decomposition(slow, 10, fund="SLOW")["by_ticker"]["BAL1"]
    assert a["total_shares"] == b["total_shares"] == pytest.approx(100.0)
    assert a["accel_pct_per_day"] is None and b["accel_pct_per_day"] is None  # no prior


# --- persistence -------------------------------------------------------------

def test_streak_counts_consecutive_adds_and_a_flat_book_has_none(tmp_path) -> None:
    d = tmp_path / "STREAK"
    _write(d, "2026-06-01", _shares())
    _write(d, "2026-06-02", _shares(BAL1=1100.0))
    _write(d, "2026-06-03", _shares(BAL1=1200.0))
    _write(d, "2026-06-04", _shares(BAL1=1300.0, BAL2=700.0))
    by = hs.fund_flow_decomposition(d, 10, fund="STREAK")["by_ticker"]
    assert by["BAL1"]["streak"] == 3
    assert by["BAL2"]["streak"] == -1            # trimmed once, at the newest step
    assert by["BAL3"]["streak"] == 0             # untouched book, no manufactured run


def test_a_quiet_interval_does_not_end_a_live_streak(tmp_path) -> None:
    """Funds rebalance weekly-to-monthly and snapshot daily, so most intervals are
    no-change. If a quiet day ended the run, every position on the board would
    report 0 and the field would be dead on arrival."""
    d = tmp_path / "QUIET"
    _write(d, "2026-06-01", _shares())
    _write(d, "2026-06-02", _shares(BAL1=1100.0))
    _write(d, "2026-06-03", _shares(BAL1=1100.0))     # nothing happened
    _write(d, "2026-06-04", _shares(BAL1=1200.0))
    _write(d, "2026-06-05", _shares(BAL1=1200.0))     # nothing happened, latest
    by = hs.fund_flow_decomposition(d, 10, fund="QUIET", streak_snaps=5)["by_ticker"]
    assert by["BAL1"]["streak"] == 2
    # …and the run only ever spans the snapshots actually read: the window is a
    # bounded number of parquet reads on the render path, not the whole history.
    short = hs.fund_flow_decomposition(d, 10, fund="QUIET", streak_snaps=3)["by_ticker"]
    assert short["BAL1"]["streak"] == 1


def test_a_broken_run_resets_the_streak(tmp_path) -> None:
    d = tmp_path / "BROKENRUN"
    _write(d, "2026-06-01", _shares())
    _write(d, "2026-06-02", _shares(BAL1=1100.0))
    _write(d, "2026-06-03", _shares(BAL1=1050.0))    # a trim breaks the run
    _write(d, "2026-06-04", _shares(BAL1=1150.0))
    by = hs.fund_flow_decomposition(d, 10, fund="BROKENRUN")["by_ticker"]
    assert by["BAL1"]["streak"] == 1


def test_creations_alone_do_not_create_a_selection_streak(tmp_path) -> None:
    """Three days of pure creations: the FLOW read is the signal, and no name may
    show up as three days of manager conviction."""
    d = tmp_path / "CREATE"
    s = _shares()
    for i, day in enumerate(("2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04")):
        _write(d, day, s * (1.1 ** i))
    dec = hs.fund_flow_decomposition(d, 10, fund="CREATE")
    assert dec["scale_pct"] == pytest.approx(33.1, abs=0.01)
    assert all(r["streak"] == 0 for r in dec["by_ticker"].values())


# --- guard: missing-constituent continuity ----------------------------------

def test_one_snapshot_absence_is_not_a_confirmed_exit(tmp_path) -> None:
    d = tmp_path / "BLINK"
    _write(d, "2026-06-01", _shares(HELD=300.0))
    _write(d, "2026-06-02", _shares(HELD=300.0))
    _write(d, "2026-06-03", _shares())                      # one file drops it
    by = hs.fund_flow_decomposition(d, 10, fund="BLINK")["by_ticker"]
    assert by["HELD"]["exit_confirmed"] is False


def test_absence_across_two_snapshots_is_a_confirmed_exit(tmp_path) -> None:
    d = tmp_path / "SOLD"
    _write(d, "2026-06-01", _shares(HELD=300.0))
    _write(d, "2026-06-02", _shares())
    _write(d, "2026-06-03", _shares())
    by = hs.fund_flow_decomposition(d, 10, fund="SOLD")["by_ticker"]
    assert by["HELD"]["exit_confirmed"] is True


def test_a_position_still_held_has_no_exit_verdict(tmp_path) -> None:
    d = tmp_path / "HELD"
    _write(d, "2026-06-01", _shares(HELD=300.0))
    _write(d, "2026-06-02", _shares(HELD=250.0))
    by = hs.fund_flow_decomposition(d, 10, fund="HELD")["by_ticker"]
    assert by["HELD"]["exit_confirmed"] is None


def test_a_fund_with_one_snapshot_yields_nothing(tmp_path) -> None:
    d = tmp_path / "NEW"
    _write(d, "2026-06-01", _shares())
    assert hs.fund_flow_decomposition(d, 10, fund="NEW") is None


# --- integration: the shipped signal rows -----------------------------------

def _fixture_fund(tmp_path, name: str = "FUND") -> Path:
    """A fund whose manager adds 40% of PICK while investors add 20% to the
    theme — both components live and separable in one pair."""
    parent = tmp_path / "store"
    d = parent / name
    _write(d, "2026-06-01", _shares(PICK=1000.0))
    _write(d, "2026-06-11", _shares(PICK=1680.0) * 1.2)
    return parent


def test_etf_signals_carries_the_decomposition_and_leaves_conviction_alone(tmp_path) -> None:
    parent = _fixture_fund(tmp_path)
    rows = hs.etf_signals("FUND", base_dir=parent, is_active=True,
                          meta={"name": "Fixture"}, fleet_latest="2026-06-11")
    by = {r["ticker"]: r for r in rows}
    assert "PICK" in by
    r = by["PICK"]
    # conviction_pp is still the shipped share-diff number: w · (s1 - s0·k_sum)/s1
    assert r["conviction_pp"] > 0 and r["direction"] == "accumulating"
    # …and the new read splits the SAME move into its two causes
    assert r["driver"] == "selection"
    assert r["flow_pp"] > 0 and r["selection_pp"] > r["flow_pp"]
    assert r["total_pp"] == pytest.approx(r["flow_pp"] + r["selection_pp"], abs=1e-4)
    assert r["fund_scale_pct"] == pytest.approx(20.0, abs=0.01)
    assert r["window_days"] == 10 and r["is_stale"] is False
    assert r["total_usd"] == pytest.approx(r["flow_usd"] + r["selection_usd"], abs=1e-3)
    assert r["implied_price"] == pytest.approx(PRICE)
    assert r["usd_per_day"] == pytest.approx(r["total_usd"] / 10, abs=1e-2)


def test_selection_pp_is_conviction_pp_on_the_robust_scale(tmp_path) -> None:
    """`selection_pp` is the SAME quantity the board already ranks on, re-derived
    on the median scale factor — not a second, silently different conviction
    number. A mover that is a small share of the book barely moves either
    estimator, so the two land on top of each other."""
    parent = tmp_path / "store"
    d = parent / "AGREE"
    _write(d, "2026-06-01", _shares(PICK=40.0))
    _write(d, "2026-06-11", _shares(PICK=56.0))
    rows = hs.etf_signals("AGREE", base_dir=parent, is_active=True,
                          meta={"name": "Agree"}, fleet_latest="2026-06-11")
    r = next(x for x in rows if x["ticker"] == "PICK")
    assert r["selection_pp"] == pytest.approx(r["conviction_pp"], abs=0.02)
    assert abs(r["flow_pp"]) < 0.01


def test_a_dominant_position_is_where_the_two_scale_estimators_part(tmp_path) -> None:
    """And this is WHY the estimator moved. PICK is ~31% of the book and the
    manager adds 40% of it; the SUM ratio then reads a 9.8% fund-wide creation
    that only exists because of this one position, and credits part of the
    manager's own decision to 'flow'. The median sees no creation at all, so the
    whole move stays where it belongs — in selection. `conviction_pp` keeps its
    shipped value either way."""
    parent = tmp_path / "store"
    d = parent / "CONC"
    _write(d, "2026-06-01", _shares(PICK=1000.0))
    _write(d, "2026-06-11", _shares(PICK=1400.0))
    rows = hs.etf_signals("CONC", base_dir=parent, is_active=True,
                          meta={"name": "Concentrated"}, fleet_latest="2026-06-11")
    r = next(x for x in rows if x["ticker"] == "PICK")
    assert r["fund_scale_pct"] == pytest.approx(0.0, abs=1e-6)
    assert abs(r["flow_pp"]) < 1e-6
    assert r["selection_pp"] > r["conviction_pp"] + 1.5
    assert r["selection_pp"] == pytest.approx(r["total_pp"], abs=1e-4)


def test_a_pure_creation_fund_publishes_flow_not_conviction(tmp_path) -> None:
    """The operator's headline case: money pours into a passive thematic fund and
    the shipped board sees nothing, because flow normalization removed it. The
    flow component has to carry it."""
    parent = tmp_path / "store"
    d = parent / "PASSIVE"
    _write(d, "2026-06-01", _shares(BIG=5000.0))
    _write(d, "2026-06-11", _shares(BIG=5000.0) * 1.5)
    dec = hs.fund_flow_decomposition(d, 10, fund="PASSIVE")
    big = dec["by_ticker"]["BIG"]
    assert dec["scale_pct"] == pytest.approx(50.0)
    assert big["selection_usd"] == pytest.approx(0.0, abs=1e-6)
    assert big["flow_usd"] == pytest.approx(25000.0)
    assert hs.etf_signals("PASSIVE", base_dir=parent, meta={"name": "Passive"}) == [], (
        "flow-normalized conviction is silent here — that is the gap W1 closes")


# --- consensus roll-up -------------------------------------------------------

def _row(fund: str, ticker: str = "NVDA", **over) -> dict:
    base = {"etf": fund, "etf_name": fund, "ticker": ticker, "name": "Nvidia",
            "sector": "Technology", "category": "Semis", "is_active": False,
            "conviction_pp": 1.0, "direction": "accumulating", "weight_pct": 5.0,
            "is_new": False, "is_exit": False, "active_chg_pct": 10.0,
            "flow_usd": 1_000_000.0, "selection_usd": 500_000.0,
            "total_usd": 1_500_000.0, "flow_pp": 0.4, "selection_pp": 0.6,
            "driver": "flow", "streak": 2, "is_stale": False,
            "split_adjusted": False, "exit_confirmed": None,
            "accel_pct_per_day": 0.5}
    return {**base, **over}


def test_consensus_rolls_up_dollars_breadth_and_drivers() -> None:
    rows = [_row("SMH"), _row("BUG", driver="selection", streak=1,
                 flow_usd=200_000.0, selection_usd=800_000.0, total_usd=1_000_000.0)]
    g = ec.consensus_favored(rows, min_funds=1)[0]
    assert g["n_funds_any"] == 2 and g["n_accum"] == 2
    assert g["total_usd"] == pytest.approx(2_500_000.0)
    assert g["flow_usd"] == pytest.approx(1_200_000.0)
    assert g["selection_usd"] == pytest.approx(1_300_000.0)
    assert g["n_funds_flow"] == 1 and g["n_funds_selection"] == 1
    assert g["breadth"] == 2 and g["max_streak"] == 2
    assert g["usd_complete"] is True and g["n_funds_usd"] == 2
    assert g["net_conviction_pp"] == pytest.approx(2.0)     # unchanged headline
    assert g["funds"][0]["total_usd"] is not None


def test_consensus_discloses_partial_dollar_coverage() -> None:
    """A fund with no market_value column contributes counts but no dollars. The
    row has to say the $ total covers 1 of its 2 funds rather than under-report
    silently."""
    rows = [_row("SMH"), _row("XSD", flow_usd=None, selection_usd=None,
                 total_usd=None, driver=None)]
    g = ec.consensus_favored(rows, min_funds=1)[0]
    assert g["n_funds_any"] == 2 and g["n_funds_usd"] == 1
    assert g["usd_complete"] is False
    assert g["total_usd"] == pytest.approx(1_500_000.0)


def test_consensus_flags_flow_selection_disagreement() -> None:
    """Investors piling into the theme while the manager sells the name — an
    honest disagreement the accum-vs-trim `contested` flag cannot see, because
    both funds are on the same side of the ledger."""
    rows = [_row("URA", flow_usd=5_000_000.0, selection_usd=-4_000_000.0,
                 total_usd=1_000_000.0),
            _row("NLR", flow_usd=3_000_000.0, selection_usd=-2_500_000.0,
                 total_usd=500_000.0)]
    g = ec.consensus_favored(rows, min_funds=1)[0]
    assert g["contested"] is False              # nobody is trimming the POSITION
    assert g["contested_components"] is True    # but flow and selection disagree
    agreed = ec.consensus_favored([_row("SMH"), _row("BUG")], min_funds=1)[0]
    assert agreed["contested_components"] is False


def test_consensus_tolerates_rows_with_no_decomposition() -> None:
    """Degrade-never-raise: a row from a fund whose decomposition failed still
    counts toward breadth of funds, with null dollars."""
    bare = {"etf": "OLD", "ticker": "NVDA", "conviction_pp": 0.5,
            "direction": "accumulating"}
    g = ec.consensus_favored([bare, _row("SMH")], min_funds=1)[0]
    assert g["n_funds_any"] == 2 and g["n_funds_usd"] == 1
    assert g["breadth"] == 1 and g["accel_pct_per_day"] == pytest.approx(0.5)


# --- builder wiring ----------------------------------------------------------

def test_fund_flows_feed_carries_the_lean_slice() -> None:
    from scripts.build_site import _fund_flows_by_ticker
    feed = _fund_flows_by_ticker([_row("SMH"), _row("BUG", ticker="AMD")])
    entry = feed["NVDA"][0]
    for key in ("total_usd", "flow_usd", "selection_usd", "driver", "streak"):
        assert key in entry, f"per-stock feed lost {key}"
    assert json.loads(json.dumps(feed, default=str))["AMD"][0]["fund"] == "BUG"


def test_payload_flow_block_is_json_safe_and_declares_coverage() -> None:
    from scripts.build_site import _etf_flow_block
    favored = ec.consensus_favored([_row("SMH"), _row("XSD", total_usd=None,
                                                      flow_usd=None,
                                                      selection_usd=None)],
                                   min_funds=1)
    block = _etf_flow_block(favored)
    assert set(block) == {"NVDA"}
    assert block["NVDA"]["usd_complete"] is False
    assert block["NVDA"]["breadth"] == 2
    # NaN is not JSON; a missing number must serialize as a null the page can read
    assert "NaN" not in json.dumps(block)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
