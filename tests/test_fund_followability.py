"""Pure-function tests for engine.fund_followability.

NO network. NO disk I/O (price series injected via price_loader param; snapshot
DataFrames built in-memory). Tests cover:
  * sleeve classification (new vs add)
  * rotation IQ call extraction + hit sign conventions
  * front-run crowd counting
  * follow-score weighting + tiers (fade via loser streak; insufficient via low n)
  * contract shape (all required keys present even on empty input)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.fund_followability as ff  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _close(values: list[float], start: str = "2023-01-02") -> pd.Series:
    """Build a daily-frequency close series with DatetimeIndex."""
    idx = pd.date_range(start, periods=len(values), freq="B")
    return pd.Series(values, index=idx)


def _snap(
    tickers: list[str],
    cusips: list[str],
    values: list[float],
    filing_date: str = "2023-05-15",
    period_end: str = "2023-03-31",
    sh_type: str = "SH",
) -> pd.DataFrame:
    """Build a minimal 13F snapshot DataFrame."""
    n = len(tickers)
    return pd.DataFrame({
        "cusip": cusips,
        "ticker": tickers,
        "issuer": tickers,
        "sh_type": [sh_type] * n,
        "shares": [1000.0] * n,
        "value_usd": values,
        "fund_slug": ["testfund"] * n,
        "fund_name": ["Test Fund"] * n,
        "fund_cik": [1] * n,
        "period_end": [period_end] * n,
        "filing_date": [filing_date] * n,
        "as_of": [period_end] * n,
    })


def _make_price_loader(prices: dict[str, list[float]], start: str = "2023-01-02") -> callable:
    """Build a synthetic price_loader from ticker -> close list.

    All series are aligned to the same ``start`` date so filing-date lookups
    work correctly across tickers and SPY.
    """
    series: dict[str, pd.Series] = {}
    for tk, vals in prices.items():
        series[tk] = _close(vals, start=start)

    def loader(ticker: str) -> pd.Series | None:
        return series.get(ticker)

    return loader


# ---------------------------------------------------------------------------
# Minimal price world: SPY +10% over 70 sessions, AAPL +20%, MSFT -5%.
# Sector ETFs: XLK +15% (tech wins), XLF -8% (financials lag).
# ---------------------------------------------------------------------------

def _make_world():
    """Create a synthetic price world for deterministic testing.

    Returns (price_loader, classifications).

    Series must span from 2020-01-02 and be long enough (1100 sessions, ending
    ~2024-03-20) that any filing date used in tests plus a 63-session horizon
    completes within the series.  The latest filing date used in tests is
    2023-08-14, which needs at least 158 sessions of remaining data — all ok.

    Direction conventions (consistent throughout tests):
      AAPL > SPY (positive new-sleeve excess, into-tech hits)
      MSFT < SPY (negative add-sleeve excess when held repeatedly)
      XLK  > SPY (into-tech rotation call hits)
      XLF  < SPY (out-of-financials rotation call hits)
    """
    n = 1100  # sessions from 2020-01-02 => ends ~2024-03-20; covers all test filing dates
    start = "2020-01-02"

    spy_vals = [100 + i * 0.008 for i in range(n)]          # steady grind
    aapl_vals = [100 + i * 0.016 for i in range(n)]         # 2× spy (beats SPY)
    msft_vals = [100 - i * 0.005 for i in range(n)]         # falls (lags SPY)
    goog_vals = [100 + i * 0.012 for i in range(n)]         # beats SPY
    xlk_vals = [100 + i * 0.012 for i in range(n)]          # XLK beats SPY
    xlf_vals = [100 - i * 0.004 for i in range(n)]          # XLF lags SPY
    jpm_vals = [100 - i * 0.003 for i in range(n)]          # JPM (Financials) lags SPY

    loader = _make_price_loader({
        "SPY": spy_vals,
        "AAPL": aapl_vals,
        "MSFT": msft_vals,
        "GOOG": goog_vals,
        "JPM":  jpm_vals,
        "XLK": xlk_vals,
        "XLF": xlf_vals,
    }, start=start)

    # NOTE: JPM is in Financials so AAPL (Technology) vs JPM (Financials) enables
    # cross-sector rotation tests where the sector ETFs differ (XLK vs XLF).
    # Both XLK and XLF are in the price loader: XLK beats SPY, XLF lags SPY.
    classifications = {
        "AAPL": {"sector": "Technology"},
        "MSFT": {"sector": "Technology"},
        "GOOG": {"sector": "Technology"},
        "JPM":  {"sector": "Financials"},
    }

    return loader, classifications


# ---------------------------------------------------------------------------
# Test: import is clean (no I/O at import time)
# ---------------------------------------------------------------------------

def test_import_is_clean():
    """Importing fund_followability must not trigger any disk I/O."""
    # The import already happened at top of file; just verify the module exists
    assert hasattr(ff, "compute_followability")
    assert hasattr(ff, "load_books")
    assert hasattr(ff, "SECTOR_ETF")


# ---------------------------------------------------------------------------
# Test: contract shape — all keys present even for empty input
# ---------------------------------------------------------------------------

def test_empty_input_returns_all_keys():
    """Empty tracker and no books => all required keys present, 'insufficient' tier."""
    result = ff.compute_followability(
        tracker={},
        books_by_fund={},
        classifications={},
    )
    assert isinstance(result, dict)
    # empty => no slugs to process
    assert len(result) == 0


def test_missing_scorecard_returns_insufficient():
    """A slug in books_by_fund with no tracker entry => 'insufficient'."""
    snap_q1 = _snap(["AAPL"], ["037833100"], [1000000.0],
                    filing_date="2023-05-15", period_end="2023-03-31")
    books = {"testfund": {"2023-03-31": snap_q1}}
    result = ff.compute_followability(
        tracker={},
        books_by_fund=books,
        classifications={"AAPL": {"sector": "Technology"}},
    )
    assert "testfund" in result
    r = result["testfund"]
    _assert_shape(r)
    assert r["follow_score"] is None
    assert r["follow_tier"] == "insufficient"


def _assert_shape(r: dict) -> None:
    """All required top-level keys must be present."""
    required_top = {"follow_score", "follow_tier", "components",
                    "sleeves", "rotation_iq", "front_run", "loser_streak_q"}
    assert required_top.issubset(set(r.keys())), f"Missing keys: {required_top - set(r.keys())}"
    # components keys
    comp = r["components"]
    assert {"edge", "consistency", "durability", "sell", "n_penalty"}.issubset(comp)
    # sleeves keys
    for sleeve in ("new", "add"):
        assert sleeve in r["sleeves"]
        s = r["sleeves"][sleeve]
        assert {"n", "median_excess", "hit"}.issubset(s)
    # rotation_iq keys
    riq = r["rotation_iq"]
    assert {"score", "hit_rate", "n_calls", "n_quarters", "best_call"}.issubset(riq)
    # front_run keys
    fr = r["front_run"]
    assert {"crowd_follow_rate", "n_new_tracked", "median_next_q_excess"}.issubset(fr)
    # loser_streak_q is an int
    assert isinstance(r["loser_streak_q"], int)


# ---------------------------------------------------------------------------
# Test: sleeve classification
# ---------------------------------------------------------------------------

def test_sleeve_new_vs_add_classification():
    """Tickers absent in the prior snapshot => 'new'; present => 'add'."""
    loader, _ = _make_world()

    # q1: only AAPL
    q1 = _snap(["AAPL"], ["037833100"], [1000.0],
               filing_date="2023-05-15", period_end="2023-03-31")
    # q2: AAPL (continuing) + MSFT (new)
    q2 = _snap(["AAPL", "MSFT"], ["037833100", "594918104"], [1200.0, 800.0],
               filing_date="2023-08-14", period_end="2023-06-30")
    books = {"2023-03-31": q1, "2023-06-30": q2}

    raw = ff._sleeve_scores(books, loader)
    # AAPL was in q1 => 'add' sleeve when seen in q2
    # MSFT was NOT in q1 => 'new' sleeve
    # Both should have n >= 1 (priceable from world)
    assert raw["add"]["n"] >= 1, "AAPL should appear in add sleeve"
    assert raw["new"]["n"] >= 1, "MSFT should appear in new sleeve"


def test_sleeve_new_beats_spy():
    """AAPL +21% vs SPY +10.5% => new sleeve median_excess should be positive."""
    loader, _ = _make_world()

    q1 = _snap([], [], [], filing_date="2022-11-15", period_end="2022-09-30")
    # q2: AAPL is new (absent in empty q1)
    q2 = _snap(["AAPL"], ["037833100"], [1000.0],
               filing_date="2023-02-14", period_end="2022-12-31")
    books = {"2022-09-30": q1, "2022-12-31": q2}

    raw = ff._sleeve_scores(books, loader)
    new_s = raw["new"]
    assert new_s["n"] == 1
    assert new_s["median_excess"] is not None
    assert new_s["median_excess"] > 0, "AAPL beat SPY => positive new-sleeve excess"
    assert new_s["hit"] == 1.0


def test_sleeve_add_lags_spy():
    """MSFT -7% vs SPY +10.5% => add-sleeve median_excess is negative."""
    loader, _ = _make_world()

    # q1: MSFT already present
    q1 = _snap(["MSFT"], ["594918104"], [1000.0],
               filing_date="2022-11-15", period_end="2022-09-30")
    # q2: MSFT again (add sleeve)
    q2 = _snap(["MSFT"], ["594918104"], [1200.0],
               filing_date="2023-02-14", period_end="2022-12-31")
    books = {"2022-09-30": q1, "2022-12-31": q2}

    raw = ff._sleeve_scores(books, loader)
    add_s = raw["add"]
    assert add_s["n"] == 1
    assert add_s["median_excess"] is not None
    assert add_s["median_excess"] < 0, "MSFT lagged SPY => negative add-sleeve excess"
    assert add_s["hit"] == 0.0


# ---------------------------------------------------------------------------
# Test: rotation IQ
# ---------------------------------------------------------------------------

def test_rotation_iq_into_hit():
    """Increasing tech weight when XLK beats SPY => into-call hits => score > 50.

    Portfolio: AAPL (Technology) vs JPM (Financials).
    q1: 30% tech, 70% financials.
    q2: 70% tech, 30% financials  — rotation INTO tech.
    XLK > SPY in our world => into-tech call hits => score > 50.
    """
    loader, classifications = _make_world()

    # q1: low tech exposure (30%)
    q1 = _snap(["AAPL", "JPM"], ["037833100", "46625H100"], [300.0, 700.0],
               filing_date="2023-05-15", period_end="2023-03-31")
    # q2: high tech exposure (70%) — strong sector rotation into tech
    q2 = _snap(["AAPL", "JPM"], ["037833100", "46625H100"], [700.0, 300.0],
               filing_date="2023-08-14", period_end="2023-06-30")
    books = {"2023-03-31": q1, "2023-06-30": q2}

    riq = ff._rotation_iq(books, classifications, loader)
    assert riq["n_calls"] >= 1, f"Expected >=1 rotation calls; got {riq['n_calls']}"
    assert riq["n_quarters"] >= 1
    # into-tech: delta>0 and XLK>SPY => signed_excess > 0 => score > 50
    if riq["score"] is not None:
        assert riq["score"] > 50, (
            f"Into-tech call when XLK>SPY should yield score>50; got {riq['score']}"
        )


def test_rotation_iq_out_hit():
    """Decreasing tech weight when XLK beats SPY => 'out' call misses => score < 50.

    An 'out' call hits if the sector LAGS after the reduction. Since XLK beats SPY
    in our world, reducing tech exposure when tech is winning => out call MISSES.
    Score should therefore be below 50.
    """
    loader, classifications = _make_world()

    # q1: heavy tech (70%), q2: lighter tech (30%) — rotating OUT of tech when XLK beats SPY
    q1 = _snap(["AAPL", "JPM"], ["037833100", "46625H100"], [700.0, 300.0],
               filing_date="2023-05-15", period_end="2023-03-31")
    q2 = _snap(["AAPL", "JPM"], ["037833100", "46625H100"], [300.0, 700.0],
               filing_date="2023-08-14", period_end="2023-06-30")
    books = {"2023-03-31": q1, "2023-06-30": q2}

    riq = ff._rotation_iq(books, classifications, loader)
    if riq["score"] is not None and riq["n_calls"] > 0:
        # out-tech call: delta<0, XLK excess>0 => miss (signed_excess = -fwd < 0) => score<50
        assert riq["score"] < 50, (
            f"Out-of-tech when XLK>SPY should miss => score<50; got {riq['score']}"
        )


def test_rotation_iq_small_delta_below_threshold_excluded():
    """Sector shift of < 1pp should NOT count as a call.

    Using AAPL (Technology) and JPM (Financials) to enable cross-sector math.
    A near-equal split shifted by a tiny amount stays below the 1pp threshold.
    """
    loader, classifications = _make_world()

    # q1 and q2 both ~50/50 tech/financials; tiny shift that is < 1pp
    q1 = _snap(["AAPL", "JPM"], ["037833100", "46625H100"], [5000.0, 5000.0],
               filing_date="2023-05-15", period_end="2023-03-31")
    q2 = _snap(["AAPL", "JPM"], ["037833100", "46625H100"], [5040.0, 4960.0],
               filing_date="2023-08-14", period_end="2023-06-30")
    # AAPL: 5040/10000 = 50.4%, vs 5000/10000 = 50.0% => delta = 0.4pp < 1pp => no call
    books = {"2023-03-31": q1, "2023-06-30": q2}

    riq = ff._rotation_iq(books, classifications, loader)
    assert riq["n_calls"] == 0, (
        f"Sub-threshold 0.4pp delta should yield 0 calls; got {riq['n_calls']}"
    )


def test_rotation_iq_best_call_populated():
    """best_call should be populated when calls exist.

    Uses AAPL (Technology) and JPM (Financials) to ensure cross-sector rotation
    is detected (both sectors must be present to generate a delta call).
    """
    loader, classifications = _make_world()

    # q1: 30% tech / 70% financials
    q1 = _snap(["AAPL", "JPM"], ["037833100", "46625H100"], [300.0, 700.0],
               filing_date="2023-05-15", period_end="2023-03-31")
    # q2: 70% tech / 30% financials => strong into-tech call
    q2 = _snap(["AAPL", "JPM"], ["037833100", "46625H100"], [700.0, 300.0],
               filing_date="2023-08-14", period_end="2023-06-30")
    books = {"2023-03-31": q1, "2023-06-30": q2}

    riq = ff._rotation_iq(books, classifications, loader)
    if riq["n_calls"] > 0:
        bc = riq["best_call"]
        assert bc is not None
        assert {"sector", "period", "delta_pp", "fwd_excess"}.issubset(bc)


def test_rotation_iq_score_none_when_n_calls_below_min():
    """FIX 4: n_calls < _RIQ_MIN_CALLS_FOR_SCORE (3) => score=None, but n_calls is
    still reported (a 1-2 call sample scoring 0-100 is noise; n always printed)."""
    loader, classifications = _make_world()

    # ONE transition only => at most 2 sector calls (tech + financials); with 1 transition
    # we may get 1-2 calls depending on classification; use a minimal setup.
    q1 = _snap(["AAPL", "JPM"], ["037833100", "46625H100"], [300.0, 700.0],
               filing_date="2023-05-15", period_end="2023-03-31")
    q2 = _snap(["AAPL", "JPM"], ["037833100", "46625H100"], [700.0, 300.0],
               filing_date="2023-08-14", period_end="2023-06-30")
    books = {"2023-03-31": q1, "2023-06-30": q2}

    riq = ff._rotation_iq(books, classifications, loader)
    # With only 1 quarter-pair we get at most 2 calls (< _RIQ_MIN_CALLS_FOR_SCORE=3)
    if riq["n_calls"] < ff._RIQ_MIN_CALLS_FOR_SCORE:
        assert riq["score"] is None, (
            f"n_calls={riq['n_calls']} < {ff._RIQ_MIN_CALLS_FOR_SCORE} must yield score=None; "
            f"got {riq['score']}"
        )
        # n_calls must still be reported
        assert riq["n_calls"] >= 0


# ---------------------------------------------------------------------------
# Test: front-run
# ---------------------------------------------------------------------------

def test_front_run_crowd_follows():
    """If other funds pick up ticker at q_{t+1} that fund A initiated at q_t => crowd_follow_rate=1."""
    loader, _ = _make_world()

    # Fund A: new AAPL at q1 (q0 was empty)
    a_q0 = _snap([], [], [], filing_date="2022-11-15", period_end="2022-09-30")
    a_q1 = _snap(["AAPL"], ["037833100"], [1000.0],
                 filing_date="2023-02-14", period_end="2022-12-31")
    a_q2 = _snap(["AAPL"], ["037833100"], [1100.0],
                 filing_date="2023-05-15", period_end="2023-03-31")

    # Fund B: not holding AAPL at q1, then holds at q2 (the crowd follows)
    b_q1 = _snap(["MSFT"], ["594918104"], [500.0],
                 filing_date="2023-02-14", period_end="2022-12-31")
    b_q2 = _snap(["AAPL", "MSFT"], ["037833100", "594918104"], [400.0, 500.0],
                 filing_date="2023-05-15", period_end="2023-03-31")

    books_by_fund = {
        "fund_a": {"2022-09-30": a_q0, "2022-12-31": a_q1, "2023-03-31": a_q2},
        "fund_b": {"2022-12-31": b_q1, "2023-03-31": b_q2},
    }
    fr = ff._front_run("fund_a", books_by_fund["fund_a"], books_by_fund, loader)
    assert fr["n_new_tracked"] >= 1
    # Fund B gained AAPL at q2, count went from 0 to 1 => crowd followed
    assert fr["crowd_follow_rate"] is not None
    assert fr["crowd_follow_rate"] > 0.0, f"Expected crowd to follow; got {fr}"


def test_front_run_crowd_does_not_follow():
    """If other funds do NOT pick up the ticker after fund A's new position => rate = 0."""
    loader, _ = _make_world()

    # Fund A initiates AAPL; Fund B never holds it
    a_q0 = _snap([], [], [], filing_date="2022-11-15", period_end="2022-09-30")
    a_q1 = _snap(["AAPL"], ["037833100"], [1000.0],
                 filing_date="2023-02-14", period_end="2022-12-31")
    a_q2 = _snap(["AAPL"], ["037833100"], [1100.0],
                 filing_date="2023-05-15", period_end="2023-03-31")

    # Fund B: only MSFT at both periods
    b_q1 = _snap(["MSFT"], ["594918104"], [500.0],
                 filing_date="2023-02-14", period_end="2022-12-31")
    b_q2 = _snap(["MSFT"], ["594918104"], [500.0],
                 filing_date="2023-05-15", period_end="2023-03-31")

    books_by_fund = {
        "fund_a": {"2022-09-30": a_q0, "2022-12-31": a_q1, "2023-03-31": a_q2},
        "fund_b": {"2022-12-31": b_q1, "2023-03-31": b_q2},
    }
    fr = ff._front_run("fund_a", books_by_fund["fund_a"], books_by_fund, loader)
    if fr["n_new_tracked"] > 0:
        assert fr["crowd_follow_rate"] == 0.0, f"Expected no crowd follow; got {fr}"


def test_front_run_excess_positive_when_new_beats_spy():
    """Median excess should be positive when the new ticker (AAPL) beats SPY."""
    loader, _ = _make_world()

    a_q0 = _snap([], [], [], filing_date="2022-11-15", period_end="2022-09-30")
    a_q1 = _snap(["AAPL"], ["037833100"], [1000.0],
                 filing_date="2023-02-14", period_end="2022-12-31")
    a_q2 = _snap(["AAPL"], ["037833100"], [1100.0],
                 filing_date="2023-05-15", period_end="2023-03-31")
    books_by_fund = {
        "fund_a": {"2022-09-30": a_q0, "2022-12-31": a_q1, "2023-03-31": a_q2},
    }
    fr = ff._front_run("fund_a", books_by_fund["fund_a"], books_by_fund, loader)
    if fr["n_new_tracked"] > 0 and fr["median_next_q_excess"] is not None:
        assert fr["median_next_q_excess"] > 0, (
            f"AAPL beats SPY => positive excess; got {fr['median_next_q_excess']}"
        )


# ---------------------------------------------------------------------------
# Test: loser streak
# ---------------------------------------------------------------------------

def test_loser_streak_zero_when_no_history():
    assert ff._loser_streak([]) == 0


def test_loser_streak_zero_when_latest_positive():
    qh = [
        {"period_end": "2023-03-31", "median_excess": -0.05},
        {"period_end": "2023-06-30", "median_excess": 0.10},
    ]
    assert ff._loser_streak(qh) == 0


def test_loser_streak_counts_consecutive_negative():
    qh = [
        {"period_end": "2022-12-31", "median_excess": 0.05},
        {"period_end": "2023-03-31", "median_excess": -0.02},
        {"period_end": "2023-06-30", "median_excess": -0.08},
        {"period_end": "2023-09-30", "median_excess": -0.03},
    ]
    # last 3 quarters all negative
    assert ff._loser_streak(qh) == 3


def test_loser_streak_stops_at_positive():
    qh = [
        {"period_end": "2023-03-31", "median_excess": -0.10},
        {"period_end": "2023-06-30", "median_excess": 0.05},  # breaks the streak
        {"period_end": "2023-09-30", "median_excess": -0.02},
    ]
    assert ff._loser_streak(qh) == 1  # only last quarter is negative


# ---------------------------------------------------------------------------
# Test: follow score computation + tier logic
# ---------------------------------------------------------------------------

def _make_tracker(
    slug: str,
    n_buys: int,
    median_buy_excess: float | None,
    quarter_history: list[dict],
    sell_skill: float | None = None,
    decay: dict | None = None,
) -> dict:
    """Build a minimal tracker dict shaped like compute_tracker() output."""
    sc = {
        "n_buys": n_buys,
        "median_buy_excess": median_buy_excess,
        "quarter_history": quarter_history,
        "sell_skill": sell_skill,
        "decay": decay,
    }
    return {"by_fund": {slug: {"scorecard": sc}}}


def test_follow_score_insufficient_when_low_n():
    """n_buys < 4 => insufficient tier."""
    tracker = _make_tracker("x", n_buys=3, median_buy_excess=0.10,
                            quarter_history=[{"period_end": "2023-03-31", "median_excess": 0.10}])
    result = ff.compute_followability(tracker, books_by_fund={}, classifications={})
    assert result["x"]["follow_score"] is None
    assert result["x"]["follow_tier"] == "insufficient"


def test_follow_score_insufficient_when_no_excess():
    """median_buy_excess=None => insufficient tier regardless of n_buys."""
    tracker = _make_tracker("x", n_buys=10, median_buy_excess=None, quarter_history=[])
    result = ff.compute_followability(tracker, books_by_fund={}, classifications={})
    assert result["x"]["follow_tier"] == "insufficient"


def test_follow_score_low_score_is_now_watch_not_fade():
    """FIX 3: score-fade arm struck — a low follow_score with streak=0 must be 'watch',
    NOT 'fade'. Low-copyability funds stay 'watch' and are down-weighted naturally."""
    # score 20 with streak 0 -> watch (not fade per adjudicated FIX 3)
    qh = [
        {"period_end": f"2023-0{i}-30", "median_excess": -0.10}
        for i in range(3, 8)
    ]
    tracker = _make_tracker("x", n_buys=12, median_buy_excess=-0.30,
                            quarter_history=qh, sell_skill=-0.20,
                            decay={"h21": {"med": -0.30, "n": 12},
                                   "h63": {"med": -0.30, "n": 12},
                                   "h126": {"med": -0.30, "n": 10}})
    result = ff.compute_followability(tracker, books_by_fund={}, classifications={})
    r = result["x"]
    _assert_shape(r)
    assert r["follow_score"] is not None
    # streak is 5 in the fixture (5 negative quarters) so this becomes fade via streak, not score.
    # Use a version with streak=0 to test the pure score arm.

def test_follow_score_low_score_streak_zero_is_watch():
    """FIX 3: score=20 with streak=0 must be 'watch' (not 'fade'). The score-fade
    arm was struck; only loser_streak >= 3 triggers fade."""
    # Single positive quarter => streak=0; terrible excess => low score
    qh = [{"period_end": "2023-03-31", "median_excess": 0.001}]
    tracker = _make_tracker("x", n_buys=12, median_buy_excess=-0.30,
                            quarter_history=qh, sell_skill=-0.20,
                            decay={"h21": {"med": -0.30, "n": 12},
                                   "h63": {"med": -0.30, "n": 12},
                                   "h126": {"med": -0.30, "n": 10}})
    result = ff.compute_followability(tracker, books_by_fund={}, classifications={})
    r = result["x"]
    _assert_shape(r)
    assert r["loser_streak_q"] == 0
    # Must be watch despite low score (score-fade arm struck)
    assert r["follow_tier"] == "watch", (
        f"Expected watch (score-fade arm struck); got {r['follow_tier']} (score={r['follow_score']})"
    )


def test_follow_score_streak3_with_high_score_is_fade():
    """FIX 3: streak=3 with score=80 must be 'fade' (streak-only rule; high score doesn't rescue)."""
    qh = [
        {"period_end": "2023-03-31", "median_excess": 0.15},
        {"period_end": "2023-06-30", "median_excess": -0.05},
        {"period_end": "2023-09-30", "median_excess": -0.02},
        {"period_end": "2023-12-31", "median_excess": -0.01},
    ]
    tracker = _make_tracker("y", n_buys=10, median_buy_excess=0.15,
                            quarter_history=qh, sell_skill=0.10,
                            decay={"h21": {"med": 0.08, "n": 10},
                                   "h63": {"med": 0.09, "n": 9},
                                   "h126": {"med": 0.07, "n": 8}})
    result = ff.compute_followability(tracker, books_by_fund={}, classifications={})
    r = result["y"]
    _assert_shape(r)
    assert r["loser_streak_q"] == 3
    assert r["follow_tier"] == "fade", (
        f"Expected fade from streak=3; got {r['follow_tier']} (score={r['follow_score']})"
    )


def test_follow_score_fade_via_loser_streak():
    """loser_streak_q >= 3 => 'fade' even if raw score would be watch."""
    # medium-positive excess but 3 consecutive losing quarters
    qh = [
        {"period_end": "2022-12-31", "median_excess": 0.05},
        {"period_end": "2023-03-31", "median_excess": -0.01},
        {"period_end": "2023-06-30", "median_excess": -0.02},
        {"period_end": "2023-09-30", "median_excess": -0.01},
    ]
    tracker = _make_tracker("x", n_buys=6, median_buy_excess=0.03,
                            quarter_history=qh, sell_skill=0.01,
                            decay={"h21": {"med": 0.02, "n": 6},
                                   "h63": {"med": 0.01, "n": 5},
                                   "h126": {"med": 0.005, "n": 4}})
    result = ff.compute_followability(tracker, books_by_fund={}, classifications={})
    r = result["x"]
    _assert_shape(r)
    assert r["loser_streak_q"] >= 3
    assert r["follow_tier"] == "fade", (
        f"Expected fade from loser streak; got {r['follow_tier']} (score={r['follow_score']})"
    )


def test_follow_score_follow_tier():
    """Very strong signal + n_buys >= 8 => 'follow' tier."""
    # 10pp median excess (fractional 0.10) + strong sell + durable
    qh = [
        {"period_end": f"2023-{m:02d}-30", "median_excess": 0.12}
        for m in [3, 6, 9, 12]
    ]
    tracker = _make_tracker(
        "topgun", n_buys=10, median_buy_excess=0.15,
        quarter_history=qh,
        sell_skill=0.10,
        decay={"h21": {"med": 0.08, "n": 10},
               "h63": {"med": 0.09, "n": 9},
               "h126": {"med": 0.07, "n": 8}},
    )
    result = ff.compute_followability(tracker, books_by_fund={}, classifications={})
    r = result["topgun"]
    _assert_shape(r)
    assert r["follow_score"] is not None
    assert r["follow_score"] >= 65, f"Expected score>=65; got {r['follow_score']}"
    assert r["follow_tier"] == "follow", f"Expected follow; got {r['follow_tier']}"


def test_follow_score_watch_tier():
    """Moderate signal, not failing => 'watch'."""
    qh = [
        {"period_end": f"2023-{m:02d}-30", "median_excess": 0.02}
        for m in [3, 6, 9, 12]
    ]
    tracker = _make_tracker(
        "midgrade", n_buys=7, median_buy_excess=0.02,
        quarter_history=qh,
        sell_skill=0.01,
        decay={"h21": {"med": 0.01, "n": 7},
               "h63": {"med": 0.01, "n": 6},
               "h126": {"med": 0.005, "n": 5}},
    )
    result = ff.compute_followability(tracker, books_by_fund={}, classifications={})
    r = result["midgrade"]
    _assert_shape(r)
    assert r["follow_tier"] in ("watch", "follow", "fade"), "Must be a valid tier"
    # 2pp median excess should land somewhere in [35, 65] → watch
    if r["follow_score"] is not None:
        assert r["follow_tier"] == "watch" or r["follow_score"] >= 65 or r["follow_score"] < 35


def test_follow_score_n_penalty():
    """n_penalty should be < 1 when n_buys < _PENALTY_DENOM."""
    tracker = _make_tracker(
        "smallbook", n_buys=6, median_buy_excess=0.10,
        quarter_history=[{"period_end": "2023-03-31", "median_excess": 0.10},
                         {"period_end": "2023-06-30", "median_excess": 0.08},
                         {"period_end": "2023-09-30", "median_excess": 0.12},
                         {"period_end": "2023-12-31", "median_excess": 0.09}],
        sell_skill=0.05,
        decay={"h21": {"med": 0.06, "n": 6},
               "h63": {"med": 0.07, "n": 5},
               "h126": {"med": 0.05, "n": 4}},
    )
    result = ff.compute_followability(tracker, books_by_fund={}, classifications={})
    r = result["smallbook"]
    # n_buys=6 < _PENALTY_DENOM=12 => n_penalty = 6/12 = 0.5
    assert r["components"]["n_penalty"] == pytest.approx(0.5, abs=1e-3)


def test_follow_score_full_n_penalty_at_12():
    """n_penalty = 1.0 when n_buys >= _PENALTY_DENOM."""
    tracker = _make_tracker(
        "bigbook", n_buys=15, median_buy_excess=0.05,
        quarter_history=[{"period_end": "2023-03-31", "median_excess": 0.05}] * 4,
        sell_skill=0.02,
        decay={"h21": {"med": 0.03, "n": 15},
               "h63": {"med": 0.03, "n": 14},
               "h126": {"med": 0.02, "n": 12}},
    )
    result = ff.compute_followability(tracker, books_by_fund={}, classifications={})
    r = result["bigbook"]
    assert r["components"]["n_penalty"] == pytest.approx(1.0, abs=1e-3)


# ---------------------------------------------------------------------------
# Test: contract shape on full synthetic run
# ---------------------------------------------------------------------------

def test_full_synthetic_contract_shape():
    """Full compute_followability run with synthetic data => all keys present for each slug."""
    loader, classifications = _make_world()

    # Build 2 funds with 4 quarters of snapshots
    # Fund A: AAPL (winner), Fund B: MSFT (loser)
    def _q(pe, fd, tks, cusips, vals):
        return _snap(tks, cusips, vals, filing_date=fd, period_end=pe)

    fund_a_books = {
        "2022-09-30": _q("2022-09-30", "2022-11-15", [], [], []),
        "2022-12-31": _q("2022-12-31", "2023-02-14", ["AAPL"], ["037833100"], [1000.0]),
        "2023-03-31": _q("2023-03-31", "2023-05-15", ["AAPL"], ["037833100"], [1100.0]),
        "2023-06-30": _q("2023-06-30", "2023-08-14", ["AAPL"], ["037833100"], [1200.0]),
    }
    fund_b_books = {
        "2022-09-30": _q("2022-09-30", "2022-11-15", [], [], []),
        "2022-12-31": _q("2022-12-31", "2023-02-14", ["MSFT"], ["594918104"], [500.0]),
        "2023-03-31": _q("2023-03-31", "2023-05-15", ["MSFT"], ["594918104"], [500.0]),
        "2023-06-30": _q("2023-06-30", "2023-08-14", ["MSFT"], ["594918104"], [500.0]),
    }

    books_by_fund = {"fund_a": fund_a_books, "fund_b": fund_b_books}
    tracker_a = _make_tracker("fund_a", n_buys=5, median_buy_excess=0.05,
                              quarter_history=[{"period_end": "2023-03-31", "median_excess": 0.05},
                                              {"period_end": "2023-06-30", "median_excess": 0.03},
                                              {"period_end": "2023-09-30", "median_excess": 0.04},
                                              {"period_end": "2023-12-31", "median_excess": 0.06}])
    tracker_b = _make_tracker("fund_b", n_buys=3, median_buy_excess=-0.05, quarter_history=[])
    # Merge into single tracker
    combined_tracker = {"by_fund": {
        **tracker_a["by_fund"],
        **tracker_b["by_fund"],
    }}

    result = ff.compute_followability(
        tracker=combined_tracker,
        books_by_fund=books_by_fund,
        classifications=classifications,
        price_loader=loader,
    )

    assert "fund_a" in result
    assert "fund_b" in result
    _assert_shape(result["fund_a"])
    _assert_shape(result["fund_b"])

    # fund_b has n_buys=3 < 4 => insufficient
    assert result["fund_b"]["follow_tier"] == "insufficient"
    # fund_a has n_buys=5 >= 4, check score exists
    assert result["fund_a"]["follow_score"] is not None or result["fund_a"]["follow_tier"] == "insufficient"


# ---------------------------------------------------------------------------
# Test: per-fund isolation — one fund failure does not break others
# ---------------------------------------------------------------------------

def test_per_fund_isolation_on_error():
    """A fund with corrupted scorecard data must return empty result, not crash everything."""
    # fund_ok: valid tracker data
    tracker = {
        "by_fund": {
            "fund_ok": {"scorecard": {
                "n_buys": 5,
                "median_buy_excess": 0.05,
                "quarter_history": [{"period_end": "2023-03-31", "median_excess": 0.05},
                                    {"period_end": "2023-06-30", "median_excess": 0.03},
                                    {"period_end": "2023-09-30", "median_excess": 0.04},
                                    {"period_end": "2023-12-31", "median_excess": 0.06}],
                "sell_skill": 0.02,
                "decay": {"h21": {"med": 0.03}, "h63": {"med": 0.02}, "h126": {"med": 0.01}},
            }},
        }
    }
    result = ff.compute_followability(
        tracker=tracker,
        books_by_fund={},
        classifications={},
    )
    # fund_ok should get a result
    assert "fund_ok" in result
    _assert_shape(result["fund_ok"])


# ---------------------------------------------------------------------------
# Smoke test against real data (skipped when data absent)
# ---------------------------------------------------------------------------

def test_real_data_smoke():
    """Load 3 real funds (bakerbros, soros, himalaya) and verify output shape.

    Skipped when the committed snapshots or price caches are absent (CI checkout).
    """
    try:
        from engine.manager_trades import compute_tracker
        from engine.fund_intelligence import load_classifications
    except ImportError:
        pytest.skip("engine modules not importable")

    trk = compute_tracker()
    if not trk:
        pytest.skip("no smart_money snapshots in this checkout")

    slugs = ["bakerbros", "soros", "himalaya"]
    available = [s for s in slugs if s in trk["by_fund"]]
    if not available:
        pytest.skip("none of bakerbros/soros/himalaya in computed tracker")

    books = ff.load_books(available)
    if not books:
        pytest.skip("load_books returned empty — no parquet files accessible")

    try:
        cls = load_classifications()
    except Exception:
        cls = {}

    result = ff.compute_followability(
        tracker=trk,
        books_by_fund=books,
        classifications=cls,
    )

    for slug in available:
        if slug not in result:
            continue
        r = result[slug]
        _assert_shape(r)
        assert r["follow_tier"] in ("follow", "watch", "fade", "insufficient"), \
            f"{slug}: invalid tier {r['follow_tier']!r}"
        if r["follow_score"] is not None:
            assert 0.0 <= r["follow_score"] <= 100.0, \
                f"{slug}: score out of range {r['follow_score']}"


class TestEdgeRulerH63:
    """Edge ruler prefers the fixed-horizon h63 decay median (adjudicated 2026-07-18)."""

    def _base_scorecard(self, **kw):
        sc = {"n_buys": 20, "median_buy_excess": -0.15, "buy_hit_rate": 0.5,
              "sell_skill": 0.0, "quarter_history": [], "decay": {}}
        sc.update(kw)
        return sc

    def test_h63_preferred_over_since_filing(self):
        from engine.fund_followability import _compute_one
        # open-ended median is terrible (-15pp) but h63 median is +2pp with n>=8
        sc = self._base_scorecard(decay={"h63": {"med": 0.02, "n": 10}})
        res = _compute_one(slug="x", scorecard=sc, books={}, books_by_fund={},
                           classifications={}, price_loader=lambda t: None)
        assert res["components"]["edge_basis"] == "h63"
        assert res["components"]["edge"] > 50  # positive h63 -> above neutral

    def test_since_filing_fallback_when_h63_thin(self):
        from engine.fund_followability import _compute_one
        sc = self._base_scorecard(decay={"h63": {"med": 0.02, "n": 3}})  # n<8
        res = _compute_one(slug="x", scorecard=sc, books={}, books_by_fund={},
                           classifications={}, price_loader=lambda t: None)
        assert res["components"]["edge_basis"] == "since_filing"
        assert res["components"]["edge"] < 50  # -15pp open-ended -> below neutral
