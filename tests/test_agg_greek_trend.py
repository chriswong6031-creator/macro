"""Aggregate greek trend + the shared exposure formula.

Two things are pinned here.

1. **The formulas themselves**, against arithmetic written out longhand in the
   test. If someone "simplifies" ``dealer_exposures``, these fail.

2. **That ``compute_gex`` and ``agg_trend`` agree.** This is the important one.
   The 2026-08-01 gamma-flip defect existed because two code paths computed the
   same quantity differently and each looked plausible alone. The aggregate trend
   is a nine-year series whose last point IS today's headline — if they can drift,
   the chart silently lies about where today sits in its own history.

Run: .venv/bin/python -m pytest tests/test_agg_greek_trend.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.agg_trend import (  # noqa: E402
    GREEKS,
    SCHEMA,
    build_trend_payload,
    daily_aggregates,
    merge_history,
)
from engine.exposure_math import (  # noqa: E402
    DAYS_PER_YEAR,
    MULT,
    PCT_MOVE,
    VOL_POINT,
    dealer_exposures,
    usable_quote,
)
from engine.options_hub import compute_gex  # noqa: E402


# ── fixtures ──────────────────────────────────────────────────────────────────

def _chain(date: str, spot: float, strikes, *, oi: float = 500.0) -> pd.DataFrame:
    """A small two-sided chain with plausible per-share greeks."""
    rows = []
    for k in strikes:
        for right in ("C", "P"):
            moneyness = k / spot
            rows.append({
                "root": "TEST",
                "expiration": "2026-09-18",
                "strike": float(k),
                "right": right,
                "date": date,
                "underlying_price": spot,
                "implied_vol": 0.20 + 0.05 * abs(moneyness - 1.0),
                "delta": (0.5 if right == "C" else -0.5) * moneyness,
                "gamma": 0.01 * moneyness,
                "vanna": 0.8 * moneyness,
                "charm": -0.4 * moneyness,
                "vega": 100.0 * moneyness,
            })
    return pd.DataFrame(rows)


def _oi(date: str, strikes, *, call_oi: float = 500.0, put_oi: float = 700.0) -> pd.DataFrame:
    rows = []
    for k in strikes:
        for right, n in (("C", call_oi), ("P", put_oi)):
            rows.append({
                "root": "TEST",
                "expiration": "2026-09-18",
                "strike": float(k),
                "right": right,
                "date": date,
                "open_interest": float(n),
            })
    return pd.DataFrame(rows)


STRIKES = [90.0, 95.0, 100.0, 105.0, 110.0]


# ── the formulas ──────────────────────────────────────────────────────────────

def test_gamma_exposure_is_dollars_per_one_percent():
    x = dealer_exposures(is_call=[True], oi=[10.0], spot=100.0, gamma=[0.05])
    assert x["gamma"] == pytest.approx(1.0 * 0.05 * 10.0 * MULT * 100.0**2 * PCT_MOVE)
    # Longhand: 10 contracts x 100 shares = 1,000 shares of underlying; gamma .05
    # means delta moves .05 per $1, and 1% of a $100 spot is $1 -> 50 shares of
    # delta -> $5,000 of stock the dealer must transact per +1% move.
    assert x["gamma"] == pytest.approx(5_000.0)


def test_puts_carry_the_opposite_dealer_sign():
    call = dealer_exposures(is_call=[True], oi=[1.0], spot=50.0, gamma=[0.02])["gamma"]
    put = dealer_exposures(is_call=[False], oi=[1.0], spot=50.0, gamma=[0.02])["gamma"]
    assert call == -put != 0.0


def test_vega_is_price_space_and_takes_no_spot_factor():
    """The single easiest unit bug in the file: vega must NOT be scaled by spot.

    ThetaData vega is already the option's dollar move per 1.00 of vol, so an extra
    spot factor would inflate SPY vega exposure ~700x — large enough to dominate
    every aggregate it appears in, and plausible enough to survive a glance.
    """
    x = dealer_exposures(is_call=[True], oi=[1.0], spot=700.0, vega=[1.0])
    assert x["vega"] == pytest.approx(MULT * VOL_POINT)
    assert x["vega"] == pytest.approx(1.0)  # NOT 700


def test_charm_is_per_day_not_per_year():
    x = dealer_exposures(is_call=[True], oi=[1.0], spot=100.0, charm=[365.0])
    assert x["charm"] == pytest.approx(1.0 * (365.0 / DAYS_PER_YEAR) * MULT * 100.0)


def test_only_supplied_greeks_come_back():
    x = dealer_exposures(is_call=[True], oi=[1.0], spot=1.0, gamma=[1.0])
    assert set(x) == {"gamma"}


def test_spot_may_vary_per_row():
    """A multi-session frame must price each row at ITS session's spot."""
    x = dealer_exposures(
        is_call=[True, True], oi=[1.0, 1.0], spot=[100.0, 200.0], gamma=[0.01, 0.01],
    )
    assert x["gamma"][1] == pytest.approx(4.0 * x["gamma"][0])


# ── the agreement that matters ────────────────────────────────────────────────

def test_trend_last_point_equals_the_hub_headline():
    """A one-session aggregate must reproduce compute_gex's net_gex_bn exactly.

    The trend chart's right-hand end is today. If it disagrees with the number the
    Exposure desk prints for the same session, the whole "where does today sit in
    its own history" reading is void.
    """
    date, spot = "2026-07-31", 100.0
    g, o = _chain(date, spot, STRIKES), _oi(date, STRIKES)

    hub = compute_gex(g, o, date, "TEST")
    agg = daily_aggregates(g, o)

    assert len(agg) == 1
    assert agg["gamma"].iloc[0] / 1e9 == pytest.approx(hub["net_gex_bn"], rel=1e-9)


def test_trend_matches_the_hub_on_every_greek_it_publishes():
    """Not just gamma — delta/vanna/charm must agree with the hub's by_strike sums."""
    date, spot = "2026-07-31", 100.0
    g, o = _chain(date, spot, STRIKES), _oi(date, STRIKES)

    hub = compute_gex(g, o, date, "TEST")
    agg = daily_aggregates(g, o).iloc[0]

    # by_strike rows are rounded to 4dp of $mn, so the tolerance is the worst-case
    # accumulated rounding across the ladder — not a fudge factor for a real gap.
    tol = len(hub["by_strike"]) * 5e-5
    for greek in ("gamma", "delta", "vanna", "charm"):
        hub_total = sum(r[f"{greek}_net"] for r in hub["by_strike"])  # $mn
        assert agg[greek] / 1e6 == pytest.approx(hub_total, abs=tol), greek


# ── the degenerate-quote gate (live defect, 2026-08-01) ───────────────────────
#
# Measured: SPY published net gamma −$1,129bn on 2026-06-26, every dollar of it
# the 729 put expiring that session — spot 728.99, T→0, feed iv 0.0001, feed
# gamma 198.17. BS gamma diverges as sigma*sqrt(T) -> 0, so the number was
# arithmetically right and financially absurd. 21 of 2,407 SPY sessions were
# contaminated; on 2024-03-13 the artifact inverted the published SIGN.


def _with_degenerate_row(date: str, spot: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A normal chain plus one expiring at-the-money quote with a collapsed iv."""
    g, o = _chain(date, spot, STRIKES), _oi(date, STRIKES)
    bad_g = pd.DataFrame([{
        "root": "TEST", "expiration": date, "strike": spot, "right": "P",
        "date": date, "underlying_price": spot,
        "implied_vol": 0.0001, "delta": -0.5, "gamma": 198.1665,
        "vanna": 0.0, "charm": 0.0, "vega": 0.0,
    }])
    bad_o = pd.DataFrame([{
        "root": "TEST", "expiration": date, "strike": spot, "right": "P",
        "date": date, "open_interest": 10640.0,
    }])
    return pd.concat([g, bad_g], ignore_index=True), pd.concat([o, bad_o], ignore_index=True)


def test_a_collapsed_iv_quote_cannot_dominate_the_aggregate():
    date, spot = "2026-06-26", 728.99
    clean = daily_aggregates(_chain(date, spot, STRIKES), _oi(date, STRIKES))
    g, o = _with_degenerate_row(date, spot)
    guarded = daily_aggregates(g, o)
    assert guarded["gamma"].iloc[0] == pytest.approx(clean["gamma"].iloc[0])


def test_the_hub_headline_is_guarded_too():
    """Both consumers gate identically — this is the number the desk renders."""
    date, spot = "2026-06-26", 728.99
    clean = compute_gex(_chain(date, spot, STRIKES), _oi(date, STRIKES), date, "TEST")
    g, o = _with_degenerate_row(date, spot)
    guarded = compute_gex(g, o, date, "TEST")
    assert guarded["net_gex_bn"] == pytest.approx(clean["net_gex_bn"])


def test_ordinary_quotes_are_untouched_by_the_gate():
    """The gate must repair only the sessions that were already wrong.

    Measured on live SPY: 2026-07-30 reads −8.102bn with and without it. A filter
    that moved ordinary sessions would be a silent redefinition of the metric.
    """
    date = "2026-07-31"
    g, o = _chain(date, 100.0, STRIKES), _oi(date, STRIKES)
    assert daily_aggregates(g, o)["gamma"].iloc[0] == pytest.approx(
        daily_aggregates(g, o)["gamma"].iloc[0]
    )
    ivs = np.asarray([0.20, 0.005, 0.0049, np.nan, -1.0])
    assert list(usable_quote(ivs)) == [True, True, False, False, False]


def test_a_missing_iv_is_kept_for_the_black_scholes_fallback():
    """No quote at all is a different case from a degenerate quote.

    compute_gex substitutes a Black-Scholes gamma when the feed value is absent;
    dropping those rows would discard real positioning rather than an artifact.
    """
    assert list(usable_quote([np.nan], [1.0])) == [False]  # agg_trend: no iv -> no row
    date = "2026-07-31"
    g = _chain(date, 100.0, STRIKES)
    g["implied_vol"] = np.nan
    hub = compute_gex(g, _oi(date, STRIKES), date, "TEST")
    assert hub["by_strike"], "rows with no quoted iv must survive into by_strike"


def test_usable_quote_also_drops_contracts_nobody_holds():
    assert list(usable_quote([0.2, 0.2], [100.0, 0.0])) == [True, False]


# ── daily aggregation ─────────────────────────────────────────────────────────

def test_one_row_per_session_in_date_order():
    frames_g, frames_o = [], []
    for i, d in enumerate(["2026-07-29", "2026-07-30", "2026-07-31"]):
        frames_g.append(_chain(d, 100.0 + i, STRIKES))
        frames_o.append(_oi(d, STRIKES))
    agg = daily_aggregates(pd.concat(frames_g), pd.concat(frames_o))
    assert list(agg["date"]) == ["2026-07-29", "2026-07-30", "2026-07-31"]
    assert list(agg["spot"]) == [100.0, 101.0, 102.0]


def test_each_session_is_priced_at_its_own_spot():
    """The failure mode this guards: a series computed at today's spot tracks the
    index level rather than the positioning, and looks entirely reasonable."""
    # Strikes scale with spot so the per-share greeks are identical in both
    # sessions — the ONLY difference between them is the spot each is priced at.
    doubled = [k * 2 for k in STRIKES]
    g = pd.concat([_chain("2026-01-02", 100.0, STRIKES), _chain("2026-07-31", 200.0, doubled)])
    o = pd.concat([_oi("2026-01-02", STRIKES), _oi("2026-07-31", doubled)])
    agg = daily_aggregates(g, o)
    # gamma exposure scales with spot^2, so a 2x spot with identical greeks/OI
    # must give a 4x reading — not 1x (every row fixed at the earliest spot).
    assert agg["gamma"].iloc[1] / agg["gamma"].iloc[0] == pytest.approx(4.0)


def test_zero_open_interest_contracts_are_dropped():
    date = "2026-07-31"
    o = _oi(date, STRIKES)
    o.loc[o["right"] == "P", "open_interest"] = 0.0
    agg = daily_aggregates(_chain(date, 100.0, STRIKES), o)
    assert agg["n_contracts"].iloc[0] == len(STRIKES)  # calls only
    assert agg["gamma"].iloc[0] > 0  # dealer long calls -> positive gamma


def test_a_session_missing_from_either_store_is_absent_not_wrong():
    """An inner join is deliberate: greeks with no OI would read as zero exposure,
    which is a real number and therefore worse than a gap."""
    g = pd.concat([_chain("2026-07-30", 100.0, STRIKES), _chain("2026-07-31", 101.0, STRIKES)])
    o = _oi("2026-07-30", STRIKES)
    agg = daily_aggregates(g, o)
    assert list(agg["date"]) == ["2026-07-30"]


def test_atm_iv_is_the_near_the_money_median():
    date = "2026-07-31"
    agg = daily_aggregates(_chain(date, 100.0, STRIKES), _oi(date, STRIKES))
    iv = agg["atm_iv"].iloc[0]
    assert 0.19 < iv < 0.23


def test_empty_and_degenerate_inputs_give_an_empty_frame():
    empty = pd.DataFrame()
    for g, o in ((empty, empty), (_chain("2026-07-31", 100.0, STRIKES), empty)):
        out = daily_aggregates(g, o)
        assert out.empty
        assert "gamma" in out.columns


def test_a_missing_greek_column_does_not_sink_the_session():
    """Pre-2024 store years can lack vanna. The row must still publish gamma."""
    date = "2026-07-31"
    g = _chain(date, 100.0, STRIKES).drop(columns=["vanna"])
    agg = daily_aggregates(g, _oi(date, STRIKES))
    assert np.isfinite(agg["gamma"].iloc[0])
    assert np.isnan(agg["vanna"].iloc[0])


# ── incremental merge ─────────────────────────────────────────────────────────

def test_merge_prefers_the_freshly_computed_row():
    """Recent open interest can be revised upstream, so the new frame wins."""
    old = pd.DataFrame({"date": ["2026-07-30", "2026-07-31"], "gamma": [1.0, 2.0]})
    new = pd.DataFrame({"date": ["2026-07-31"], "gamma": [9.0]})
    out = merge_history(old, new)
    assert list(out["date"]) == ["2026-07-30", "2026-07-31"]
    assert list(out["gamma"]) == [1.0, 9.0]


def test_merge_handles_either_side_empty():
    df = pd.DataFrame({"date": ["2026-07-31"], "gamma": [1.0]})
    assert len(merge_history(None, df)) == 1
    assert len(merge_history(df, pd.DataFrame())) == 1


# ── payload ───────────────────────────────────────────────────────────────────

def _series_frame(n: int = 60) -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-02", periods=n).strftime("%Y-%m-%d")
    ramp = np.linspace(-5e9, 5e9, n)
    return pd.DataFrame({
        "date": dates,
        "spot": np.linspace(100.0, 120.0, n),
        "n_contracts": np.full(n, 100),
        "oi_total": np.full(n, 1e5),
        "atm_iv": np.linspace(0.15, 0.25, n),
        **{g: ramp for g in GREEKS},
    })


def test_payload_is_bn_and_carries_its_units():
    p = build_trend_payload(_series_frame(), "SPY", "2026-03-26")
    assert p["schema"] == SCHEMA
    assert p["root"] == "SPY"
    assert p["n_days"] == 60
    assert p["units"]["gamma"] == "per +1% spot"
    assert p["units"]["charm"] == "per +1 day"
    assert p["series"][-1]["g"] == pytest.approx(5.0)  # $5bn, not 5e9


def test_stats_place_today_in_its_own_distribution():
    p = build_trend_payload(_series_frame(), "SPY", "2026-03-26")
    s = p["stats"]["gamma"]
    assert s["min"] == pytest.approx(-5.0)
    assert s["max"] == pytest.approx(5.0)
    assert s["last"] == pytest.approx(5.0)
    # a monotone ramp ending at the max sits at the top of its own history
    assert s["pctile"] > 98.0
    assert s["p05"] < s["p50"] < s["p95"]


def test_empty_payload_is_honest_rather_than_absent():
    p = build_trend_payload(pd.DataFrame(), "ZZZZ", "2026-07-31")
    assert p["schema"] == SCHEMA
    assert p["n_days"] == 0
    assert p["series"] == []
    assert p["stats"] == {}
    assert p["since"] is None


def test_a_non_finite_value_is_omitted_not_zeroed():
    df = _series_frame(10)
    df.loc[3, "gamma"] = np.nan
    p = build_trend_payload(df, "SPY", "2026-01-15")
    assert "g" not in p["series"][3]
    assert "g" in p["series"][4]


def test_stats_pctile_uses_midrank_on_ties():
    """Strict-less rank read a value tying the minimum as '0th percentile' — an
    extreme-low claim about an unexceptional value. Midrank: flat series ≈ 50th,
    max of five = 90th, min of five = 10th. One definition with the Terminal's
    lib/aggTrend.windowStats."""
    from engine.agg_trend import _stats

    flat = _stats(np.array([5.0, 5.0, 5.0, 5.0]))
    assert flat["pctile"] == pytest.approx(50.0)
    hi = _stats(np.array([1.0, 2.0, 3.0, 4.0, 10.0]))
    assert hi["pctile"] == pytest.approx(90.0)
    lo = _stats(np.array([10.0, 4.0, 3.0, 2.0, 1.0]))
    assert lo["pctile"] == pytest.approx(10.0)
