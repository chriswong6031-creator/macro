"""Pure-function tests for the 13F smart-money TRADE TRACKER (engine.manager_trades).

No network. The price-dependent math is exercised against a tiny in-memory close
panel (a fake breadth frame + a fake SPY series), so excess-return, direction-aware
quality, the per-fund scorecard, and the leaderboard z-grade are all asserted without
disk. A final smoke test runs compute_tracker against the committed snapshots if they
are present, else skips.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import manager_trades as mt  # noqa: E402


def _panel():
    """A ClosePanel over a fake breadth frame: WIN doubles, LAG halves, SPY +10% —
    over the same window. yahoo is absent (data dir untouched), so .get falls through
    to the injected breadth frame."""
    idx = pd.date_range("2025-01-01", periods=70, freq="B")
    win = pd.Series([100.0 + i for i in range(70)], index=idx)        # +69% over the window
    lag = pd.Series([100.0 - 0.5 * i for i in range(70)], index=idx)  # falls steadily
    spy = pd.Series([100.0 + 0.2 * i for i in range(70)], index=idx)  # mild grind up
    breadth = pd.concat({"WIN": win, "LAG": lag, "SPY": spy}, axis=1)
    p = mt.ClosePanel(breadth=breadth)
    # the fake panel has no yahoo SPY; force the benchmark from the breadth frame
    p.spy = breadth["SPY"]
    p.thru = str(breadth.index[-1].date())
    return p, idx


def test_excess_since_is_benchmark_relative():
    p, idx = _panel()
    r = p.excess("WIN", str(idx[0].date()))            # since-to-latest
    assert r is not None
    assert r["abs"] > 0 and r["excess"] > 0            # WIN beat SPY
    assert r["excess"] == round(r["abs"] - r["spy"], 4)
    assert r["hold_days"] > 0


def test_excess_horizon_not_elapsed_is_none():
    p, idx = _panel()
    # entry near the end leaves < HORIZON sessions → fixed-window not scorable
    late = str(idx[-3].date())
    assert p.excess("WIN", late, horizon=63) is None
    # but the live since-read is still available
    assert p.excess("WIN", late) is not None


def test_excess_unpriced_ticker_is_none():
    p, idx = _panel()
    assert p.excess("NOPE", str(idx[0].date())) is None


def test_excess_snap_forward_flags_and_drops_skill_leg():
    p, idx = _panel()
    # an entry well before the series start snaps forward to the first session:
    early = "2024-10-01"                              # ~3 months before idx[0]
    since = p.excess("WIN", early)                    # realised read kept, flagged
    assert since is not None and since["entry_lag_days"] > mt.SNAP_MAX_DAYS
    # but the filing-anchored fixed-horizon skill leg is dropped (mis-anchored window)
    assert p.excess("WIN", early, horizon=10) is None


def test_trade_quality_direction_aware():
    # a BUY is skillful when the name then beat SPY (+excess)
    assert mt._trade_quality("add", 0.20) == 0.20
    assert mt._trade_quality("new", -0.10) == -0.10
    # a SELL is skillful when the name then LAGGED (−excess) → flips sign
    assert mt._trade_quality("trim", -0.15) == 0.15
    assert mt._trade_quality("exit", 0.05) == -0.05
    assert mt._trade_quality("hold", 0.5) is None
    assert mt._trade_quality("add", None) is None


def _trade(action, ticker, since, conv=5.0, period="2025-06-30"):
    return {"slug": "x", "fund": "X", "name": "X", "ticker": ticker, "issuer": ticker,
            "action": action, "period_end": period, "filing_date": "2025-08-14",
            "pct_portfolio": conv, "shares_change_pct": 10.0,
            "since_excess": since, "since_abs": since, "spy_since": 0.0,
            "hold_days": 100, "fwd_excess": since, "fwd_abs": since,
            "quality": mt._trade_quality(action, since)}


def test_fund_scorecard_aggregates():
    trades = [_trade("new", "A", 0.40), _trade("add", "B", -0.10),
              _trade("trim", "C", -0.30)]            # good sell (then lagged)
    sc = mt.fund_scorecard(trades)
    assert sc["n_buys"] == 2 and sc["n_sells"] == 1
    assert sc["avg_buy_excess"] == pytest.approx((0.40 - 0.10) / 2, abs=1e-6)
    assert sc["median_buy_excess"] == pytest.approx(0.15, abs=1e-6)   # median([0.40,-0.10])
    assert sc["buy_hit_rate"] == pytest.approx(0.5, abs=1e-6)
    assert sc["sell_skill"] == pytest.approx(0.30, abs=1e-6)   # −(−0.30)
    assert sc["best_trade"]["ticker"] == "A"
    assert sc["worst_trade"]["ticker"] == "B"


def test_fund_scorecard_tolerates_none_since_excess():
    """A buy with an unpriced since_excess must NOT crash best/worst ranking (the PURE
    invariant the live pipeline guarantees but the harness can violate)."""
    trades = [_trade("add", "A", 0.20), _trade("new", "B", None)]
    sc = mt.fund_scorecard(trades)                    # would TypeError without the guard
    assert sc["n_buys"] == 1                          # only the priced buy counts
    assert sc["best_trade"]["ticker"] == "A"
    assert sc["worst_trade"]["ticker"] == "A"


def test_score_fund_trades_counters_track_coverage():
    """The optional counters out-dict accumulates attempted vs priced moves so the
    caller can expose a per-fund coverage fraction (smoke — exercises the live path)."""
    cov = {}
    trk = mt.compute_tracker()
    if not trk:
        pytest.skip("no snapshots in this checkout")
    # every ranked fund exposes a coverage fraction in [0, 100]
    for r in trk["leaderboard"]:
        c = r.get("coverage_pct")
        assert c is None or (0.0 <= c <= 100.0)


def test_leaderboard_grades_and_orders():
    cards = {
        "good":  {**mt.fund_scorecard([_trade("add", f"G{i}", 0.30) for i in range(6)]), "name": "Good"},
        "mid":   {**mt.fund_scorecard([_trade("add", f"M{i}", 0.00) for i in range(6)]), "name": "Mid"},
        "bad":   {**mt.fund_scorecard([_trade("add", f"B{i}", -0.30) for i in range(6)]), "name": "Bad"},
        "thin":  {**mt.fund_scorecard([_trade("add", "T", 0.90)]), "name": "Thin"},   # below gate
    }
    board = mt.rank_leaderboard(cards, min_buys=5)
    by = {r["slug"]: r for r in board}
    # eligible funds ranked best→worst; the thin fund is unranked and sorted last
    assert by["good"]["rank"] == 1 and by["good"]["grade"] == "A"
    assert by["bad"]["grade"] == "D"
    assert by["thin"]["rank"] is None and by["thin"]["grade"] == "n/a"
    ranks = [r["slug"] for r in board if r["ranked"]]
    assert ranks == ["good", "mid", "bad"]


def test_compute_tracker_smoke():
    """If the committed snapshots + price caches exist, the full payload is well-formed
    and Tepper's marquee names actually scored (the ADR-coverage upgrade). Skips when
    the data isn't present (e.g. a thin CI checkout)."""
    trk = mt.compute_tracker()
    if not trk:
        pytest.skip("no smart_money snapshots / price caches in this checkout")
    for k in ("leaderboard", "best_trades", "worst_trades", "by_fund", "coverage"):
        assert k in trk
    assert trk["coverage"]["trades_scored"] > 0
    # leaderboard ranks are contiguous over the eligible set
    ranked = [r["rank"] for r in trk["leaderboard"] if r["ranked"]]
    assert ranked == list(range(1, len(ranked) + 1))
    # the leaderboard order honors the robust ranking key (median, then hit-rate)
    elig = [r for r in trk["leaderboard"] if r["ranked"]]
    meds = [r["median_buy_excess"] for r in elig]
    assert meds == sorted(meds, reverse=True)
    # the bilingual note survives as an {en, zh} pair
    assert set(trk["note"]) == {"en", "zh"} and trk["note"]["zh"]
