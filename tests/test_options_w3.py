"""Volland parity W3 — delta-space exposure and the cross-root screener.

Run: .venv/bin/python -m pytest tests/test_options_w3.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.options_hub import _DELTA_BUCKET, compute_gex  # noqa: E402
from engine.quad_screener import (  # noqa: E402
    MIN_HISTORY_DAYS,
    PCTILE_WINDOW_DAYS,
    SCHEMA,
    build_quad,
    quadrant,
)

ASOF = "2026-07-31"
EXP = "2026-09-18"


def _chain(spot=100.0, strikes=(90.0, 95.0, 100.0, 105.0, 110.0)):
    """A chain whose per-contract deltas span the full 0..1 call-equivalent range."""
    rows = []
    for k in strikes:
        # Crude but monotone: deep ITM calls near 1, deep OTM near 0.
        call_delta = max(0.02, min(0.98, 0.5 + (spot - k) / (0.4 * spot)))
        for right in ("C", "P"):
            rows.append({
                "expiration": EXP, "strike": float(k), "right": right, "date": ASOF,
                "underlying_price": spot, "implied_vol": 0.20,
                "delta": call_delta if right == "C" else call_delta - 1.0,
                "gamma": 0.01, "vanna": 0.5, "charm": -0.3, "vega": 90.0,
            })
    return pd.DataFrame(rows)


def _oi(strikes=(90.0, 95.0, 100.0, 105.0, 110.0), n=500.0):
    return pd.DataFrame([
        {"expiration": EXP, "strike": float(k), "right": r, "open_interest": n}
        for k in strikes for r in ("C", "P")
    ])


# ── Floating Strike (by_delta) ────────────────────────────────────────────────

def test_by_delta_buckets_are_published_and_ordered():
    out = compute_gex(_chain(), _oi(), ASOF, "TEST")
    rows = out["by_delta"]
    assert rows, "by_delta must be published when the chain carries delta"
    assert all(r["hi"] - r["lo"] == pytest.approx(_DELTA_BUCKET) for r in rows)
    assert [r["lo"] for r in rows] == sorted(r["lo"] for r in rows)
    assert all(0.0 <= r["lo"] < r["hi"] <= 1.0 for r in rows)


def test_by_delta_conserves_the_whole_book_within_the_window():
    """Re-indexing must not create or destroy exposure — only move where it is filed.

    Valid ONLY while every strike sits inside by_strike's ±20% window, which is true of
    this fixture (90-110 against spot 100). See the test below for what happens when it
    is not — that case is why this one is not the whole story.
    """
    out = compute_gex(_chain(), _oi(), ASOF, "TEST")
    for col in ("gamma_net", "delta_net", "vanna_net", "charm_net"):
        by_delta = sum(r[col] for r in out["by_delta"])
        by_strike = sum(r[col] for r in out["by_strike"])
        assert by_delta == pytest.approx(by_strike, abs=len(out["by_strike"]) * 5e-5), col


def test_by_delta_covers_the_full_book_while_by_strike_is_windowed():
    """The two views are NOT the same population, and the payload must say so.

    ⚠️ This test exists because the conservation test above gave false confidence: its
    fixture happens to fit inside by_strike's ±20% window, so the two totals agreed and
    the difference was invisible. On any real index root they do not agree — by_strike
    is windowed to ±20% of spot and capped at 160 rows, while by_delta is the FULL book,
    deliberately: the 0-5 and 95-100 delta bands are far OTM/ITM by definition and live
    outside that window, and they are exactly what a delta view exists to show.

    Windowing delta space by STRIKE would gut it. Disclosing the difference is the fix.
    """
    wide = [50.0, 90.0, 95.0, 100.0, 105.0, 110.0, 160.0]   # 50 and 160 are outside ±20%
    # Call-heavy, so calls and puts do NOT cancel and the wings carry real net exposure.
    # A symmetric book sums to zero on both views and would hide the very difference
    # this test exists to demonstrate.
    oi = pd.DataFrame([
        {"expiration": EXP, "strike": float(k), "right": r,
         "open_interest": 900.0 if r == "C" else 100.0}
        for k in wide for r in ("C", "P")
    ])
    out = compute_gex(_chain(strikes=wide), oi, ASOF, "TEST")

    strikes_in_ladder = {r["strike"] for r in out["by_strike"]}
    assert 50.0 not in strikes_in_ladder and 160.0 not in strikes_in_ladder

    by_delta = sum(r["gamma_net"] for r in out["by_delta"])
    by_strike = sum(r["gamma_net"] for r in out["by_strike"])
    assert by_delta != pytest.approx(by_strike), (
        "the wings are missing from by_strike, so the totals cannot agree"
    )

    # The payload discloses the full-book count so a consumer can state the difference
    # rather than imply the views are one book re-indexed.
    assert out["by_delta_full_n"] == len(wide) * 2
    assert out["by_strike_full_n"] == len(wide)


def test_a_put_lands_in_its_call_equivalent_bucket():
    """A -0.30 put describes the same region as a +0.70 call and belongs beside it.

    Filing puts by |delta| instead would put the wings on the wrong side of the axis —
    invisible in the totals and completely wrong as a picture.
    """
    g = pd.DataFrame([{
        "expiration": EXP, "strike": 100.0, "right": "P", "date": ASOF,
        "underlying_price": 100.0, "implied_vol": 0.2,
        "delta": -0.30, "gamma": 0.01, "vanna": 0.5, "charm": -0.3,
    }])
    oi = pd.DataFrame([{"expiration": EXP, "strike": 100.0, "right": "P", "open_interest": 100.0}])
    rows = compute_gex(g, oi, ASOF, "TEST")["by_delta"]
    assert len(rows) == 1
    assert rows[0]["lo"] == pytest.approx(0.70)
    # dealer short puts -> negative gamma contribution survives the fold
    assert rows[0]["gamma_net"] < 0


def test_delta_of_exactly_one_joins_the_top_bucket():
    """Not a 21st bucket of its own — the classic off-by-one on a floor()ed axis."""
    g = pd.DataFrame([{
        "expiration": EXP, "strike": 1.0, "right": "C", "date": ASOF,
        "underlying_price": 100.0, "implied_vol": 0.2,
        "delta": 1.0, "gamma": 0.0001, "vanna": 0.0, "charm": 0.0,
    }])
    oi = pd.DataFrame([{"expiration": EXP, "strike": 1.0, "right": "C", "open_interest": 10.0}])
    rows = compute_gex(g, oi, ASOF, "TEST")["by_delta"]
    assert len(rows) == 1
    assert rows[0]["hi"] == pytest.approx(1.0)
    assert rows[0]["lo"] == pytest.approx(1.0 - _DELTA_BUCKET)


@pytest.mark.parametrize("put_delta,expect_lo", [
    (-0.30, 0.70), (-0.25, 0.75), (-0.50, 0.50), (-0.05, 0.95), (-0.70, 0.30),
])
def test_round_deltas_land_on_the_right_side_of_a_bucket_edge(put_delta, expect_lo):
    """Bucket edges are exactly where binary fractions bite.

    1.0 - 0.3 divided by 0.05 is 13.999999999999998, so a naive floor() files a -0.30
    put in 0.65-0.70. Round-numbered deltas are what a chain is FULL of, so the whole
    picture would sit one bucket low while looking perfectly reasonable.
    """
    g = pd.DataFrame([{
        "expiration": EXP, "strike": 100.0, "right": "P", "date": ASOF,
        "underlying_price": 100.0, "implied_vol": 0.2,
        "delta": put_delta, "gamma": 0.01, "vanna": 0.5, "charm": -0.3,
    }])
    oi = pd.DataFrame([{"expiration": EXP, "strike": 100.0, "right": "P", "open_interest": 100.0}])
    rows = compute_gex(g, oi, ASOF, "TEST")["by_delta"]
    assert rows[0]["lo"] == pytest.approx(expect_lo)


def test_by_delta_is_absent_not_invented_when_delta_is():
    g = _chain().drop(columns=["delta"])
    assert compute_gex(g, _oi(), ASOF, "TEST")["by_delta"] == []
    assert "by_delta" in compute_gex(pd.DataFrame(), _oi(), ASOF, "TEST")


# ── Quad screener ─────────────────────────────────────────────────────────────

def _frame(n: int, gamma_end: float, vanna_end: float) -> pd.DataFrame:
    """n sessions ramping to a chosen final reading, so the percentile is predictable."""
    dates = pd.bdate_range("2020-01-01", periods=n).strftime("%Y-%m-%d")
    return pd.DataFrame({
        "date": dates,
        "spot": np.linspace(100.0, 200.0, n),
        "atm_iv": np.linspace(0.15, 0.20, n),
        "gamma": np.concatenate([np.linspace(-5e9, 5e9, n - 1), [gamma_end]]),
        "vanna": np.concatenate([np.linspace(-1e9, 1e9, n - 1), [vanna_end]]),
    })


def test_each_root_is_ranked_against_its_own_history():
    """The point of the design: no cross-sectional normalisation anywhere.

    A big book at its own median must NOT outrank a small book at its own extreme —
    which is exactly what normalising across the screen would do.
    """
    board = build_quad(
        {
            "BIG": _frame(400, 0.0, 0.0),        # huge exposures, sitting mid-range
            "SMALL": _frame(400, -9e9, -9e9),    # tiny book, at its own floor
        },
        ASOF,
    )
    by = {r["root"]: r for r in board["rows"]}
    assert by["SMALL"]["gamma_pctile"] < by["BIG"]["gamma_pctile"]
    assert by["SMALL"]["extreme"] is True
    assert by["BIG"]["extreme"] is False


def test_thin_history_is_skipped_not_published_with_a_weak_percentile():
    board = build_quad({"THIN": _frame(MIN_HISTORY_DAYS - 1, 1e9, 1e9)}, ASOF)
    assert board["rows"] == []
    assert board["skipped"] == ["THIN"]
    assert board["n_skipped"] == 1


def test_rows_carry_the_size_behind_the_rank():
    board = build_quad({"SPY": _frame(400, -8.1e9, 6.2e9)}, ASOF)
    row = board["rows"][0]
    assert row["gamma_bn"] == pytest.approx(-8.1)
    assert row["vanna_bn"] == pytest.approx(6.2)
    assert row["n_days"] == 400
    assert row["since"]


def test_quadrants_name_the_four_hedging_regimes():
    assert quadrant(10, 10) == "amplify_stable"
    assert quadrant(10, 90) == "amplify_volsens"
    assert quadrant(90, 10) == "dampen_stable"
    assert quadrant(90, 90) == "dampen_volsens"
    # boundary belongs to the upper half on both axes
    assert quadrant(50, 50) == "dampen_volsens"


def test_board_is_honest_when_nothing_qualifies():
    board = build_quad({}, ASOF)
    assert board["schema"] == SCHEMA
    assert board["rows"] == []
    assert board["n_roots"] == 0
    board2 = build_quad({"EMPTY": pd.DataFrame(), "NONE": None}, ASOF)
    assert board2["n_skipped"] == 2


def test_a_root_missing_a_greek_column_is_skipped_rather_than_half_plotted():
    """Both axes are required — a row with one coordinate cannot be placed."""
    f = _frame(400, 1e9, 1e9).drop(columns=["vanna"])
    assert build_quad({"HALF": f}, ASOF)["rows"] == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_percentile_uses_a_trailing_window_not_the_whole_series():
    """A rank against nine years of a TRENDING series measures growth, not extremity.

    Measured on the real store: dealer exposure scales with the underlying (gamma with
    S-squared, vanna and charm with S), SPY went 225 -> 741 between 2017 and 2026, and its
    yearly median vanna climbed 3.54bn -> 5.07bn with 2024/2025/2026 the three highest
    years on record. The first build of this board put 20 of 23 roots above the 85th
    vanna percentile -- not a finding, a trend.

    Constructed so the right answer is unambiguous: today's reading is set to exactly the
    MEDIAN of the trailing year, so a correct windowed percentile is ~50. Against the full
    drifting series the identical reading sits near the top purely because the market grew.
    """
    n = 1500
    drift = np.linspace(1e9, 5e9, n)                # pure growth, no positioning story
    wobble = np.sin(np.arange(n) / 9.0) * 4e8       # within-year positioning swing
    series = drift + wobble
    # Today = the median of its own trailing year, by construction.
    series[-1] = float(np.median(series[-PCTILE_WINDOW_DAYS:-1]))

    dates = pd.bdate_range("2019-01-01", periods=n).strftime("%Y-%m-%d")
    f = pd.DataFrame({
        "date": dates, "spot": np.linspace(100, 400, n), "atm_iv": np.full(n, 0.18),
        "gamma": series, "vanna": series,
    })

    row = build_quad({"DRIFT": f}, ASOF)["rows"][0]
    assert 35 <= row["gamma_pctile"] <= 65, (
        f"a reading at its own one-year median read as the {row['gamma_pctile']}th "
        "percentile — the window is not being applied"
    )
    # The same reading against the WHOLE series reads as a near-record, purely drift.
    full = float((series[:-1] < series[-1]).mean() * 100)
    assert full > 85
    assert full - row["gamma_pctile"] > 25


def test_the_window_is_disclosed_in_the_payload():
    """A percentile without its reference window is not interpretable."""
    board = build_quad({"SPY": _frame(400, 1e9, 1e9)}, ASOF)
    assert board["pctile_window_days"] == PCTILE_WINDOW_DAYS
    assert board["rows"][0]["pctile_n"] == min(400, PCTILE_WINDOW_DAYS)
    # n_days still reports the FULL history, which is what the thin-history gate uses.
    assert board["rows"][0]["n_days"] == 400


# ── Audit regression: quad rows must carry their OWN session ───────────────────

def test_each_quad_row_carries_its_own_last_session():
    """A stale cache must not render as today's positioning.

    The board is rebuilt from EVERY cached root, not just the ones this run refreshed,
    so a root whose build failed (or which simply was not in --roots) contributes
    coordinates — and a `spot` — from an old session. Without a per-row date the reader
    sees month-old positioning under a current-dated header.
    """
    fresh = _frame(400, -8.1e9, 6.2e9)
    stale = _frame(400, 1e9, 1e9)
    stale["date"] = pd.bdate_range("2019-01-01", periods=400).strftime("%Y-%m-%d")

    board = build_quad({"FRESH": fresh, "STALE": stale}, ASOF)
    by = {r["root"]: r for r in board["rows"]}
    assert by["FRESH"]["asof"] == str(fresh["date"].iloc[-1])
    assert by["STALE"]["asof"] == str(stale["date"].iloc[-1])
    assert by["STALE"]["asof"] < by["FRESH"]["asof"]


def test_the_board_counts_how_many_rows_trail_it():
    """Named, not merely derivable — a consumer that forgets to compare would show
    stale rows as current."""
    fresh = _frame(400, 1e9, 1e9)
    stale = _frame(400, 1e9, 1e9)
    stale["date"] = pd.bdate_range("2019-01-01", periods=400).strftime("%Y-%m-%d")
    board = build_quad({"FRESH": fresh, "STALE": stale}, str(fresh["date"].iloc[-1]))
    assert board["n_stale"] == 1

    clean = build_quad({"A": fresh}, str(fresh["date"].iloc[-1]))
    assert clean["n_stale"] == 0
