"""Split-seam repair guard for the breadth close caches (BreadthAdapter._merge_refreshed).

yfinance auto_adjust back-adjusts only the freshly downloaded window, so the
tail refresh (fresh 1mo combine_first cached) leaves cached pre-window rows on
the pre-split basis after a stock split. Observed 2026-07-10 in the live S&P
500 cache: KLAC $1,842.80 -> $180.90 across 2026-05-11/12 (fake -90.2% day from
the 10:1 split of 2026-06-12; the seam sits where the 1mo window stopped
rewriting), plus CRWD 4:1 and a DD re-basing. Poisons pct_above_50/200, 252d
NH/NL, adv/dec and the OHLCV extras caches until the lookback rolls past.

Pure-function tests (no network): the yfinance downloader is monkeypatched.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.breadth import BreadthAdapter, seam_suspects  # noqa: E402

# 120 business days of history; the fresh refresh window covers the last 20
DATES = pd.bdate_range("2026-01-05", periods=120)
FRESH_START = 100


def _frame(cols: dict) -> pd.DataFrame:
    return pd.DataFrame(cols, index=DATES)


def _drifting(base: float, seed: int = 7) -> pd.Series:
    """A gently drifting price path — daily moves well inside the seam bounds."""
    rng = np.random.default_rng(seed)
    steps = 1 + rng.uniform(-0.02, 0.02, len(DATES))
    return pd.Series(base * np.cumprod(steps), index=DATES)


def _adapter(repull: pd.DataFrame | Exception | None, calls: list) -> BreadthAdapter:
    # skip __init__/config.load — _merge_refreshed reads cfg/name + _download_closes
    a = BreadthAdapter.__new__(BreadthAdapter)
    a.cfg = {"lookback_days_live": 1100}
    a._last_extras = {}

    def fake_download(tickers, period):
        calls.append((sorted(tickers), period))
        if isinstance(repull, Exception):
            raise repull
        assert repull is not None, "unexpected repair download"
        a._last_extras = getattr(a, "_repull_extras", {})
        return repull[[t for t in sorted(tickers) if t in repull.columns]]

    a._download_closes = fake_download
    return a


def _split_universe():
    """AAA has a 10:1 split during the fresh window; BBB is a clean control.

    truth = the coherent back-adjusted history a full re-pull returns.
    cached = truth on the PRE-split basis (10x) — what the cache held before.
    fresh  = last 20 days of truth — the auto-adjusted refresh window.
    """
    truth = _frame({"AAA": _drifting(100.0, 1), "BBB": _drifting(50.0, 2)})
    cached = truth.iloc[:-5].copy()
    cached["AAA"] *= 10
    fresh = truth.iloc[-20:]
    return truth, cached, fresh


def test_boundary_seam_detected_and_repaired():
    truth, cached, fresh = _split_universe()
    calls: list = []
    a = _adapter(truth, calls)
    merged = a._merge_refreshed(fresh, cached)
    # the repair re-pulled exactly the seamed ticker, at the full live window
    assert calls == [(["AAA"], "4y")]
    # pre-window history is now on the adjusted basis — no fake -90% day left
    pd.testing.assert_series_equal(merged["AAA"], truth["AAA"], check_names=False)
    r = merged / merged.shift(1)
    assert float(r.min().min()) > 0.60 and float(r.max().max()) < 1.65
    # the clean ticker is untouched
    pd.testing.assert_series_equal(merged["BBB"], truth["BBB"], check_names=False)


def test_legacy_mid_history_seam_repaired():
    # cache already part-healed by later refreshes (the live KLAC shape): the
    # seam sits mid-history, so cached and fresh AGREE on the overlap and only
    # the residual-jump scan can see it
    truth, _, fresh = _split_universe()
    cached = truth.iloc[:-5].copy()
    cached.loc[: DATES[60], "AAA"] *= 10
    calls: list = []
    a = _adapter(truth, calls)
    merged = a._merge_refreshed(fresh, cached)
    assert calls == [(["AAA"], "4y")]
    pd.testing.assert_series_equal(merged["AAA"], truth["AAA"], check_names=False)


def test_real_crash_survives_repair():
    # a genuine -62% day trips the scan; the re-pull returns the same data and
    # the "repair" must preserve the crash, not smooth it away
    crash = _drifting(100.0, 3)
    crash.iloc[40:] *= 0.38
    truth = _frame({"AAA": crash, "BBB": _drifting(50.0, 4)})
    cached, fresh = truth.iloc[:-5], truth.iloc[-20:]
    calls: list = []
    a = _adapter(truth, calls)
    merged = a._merge_refreshed(fresh, cached)
    assert calls == [(["AAA"], "4y")]
    pd.testing.assert_series_equal(merged["AAA"], truth["AAA"], check_names=False)


def test_dividend_scale_basis_does_not_trigger():
    # dividend re-adjustment shifts the cached basis by ~1.5% — below tolerance
    truth = _frame({"AAA": _drifting(100.0, 5), "BBB": _drifting(50.0, 6)})
    cached = truth.iloc[:-5].copy()
    cached["AAA"] *= 1.015
    fresh = truth.iloc[-20:]
    calls: list = []
    a = _adapter(None, calls)
    merged = a._merge_refreshed(fresh, cached)
    assert calls == []  # no repair download
    # plain combine_first result
    pd.testing.assert_frame_equal(merged, fresh.combine_first(cached))


def test_failed_repull_keeps_poisoned_column_for_retry():
    # repair download dies -> the seam must stay visible (NOT truncated), so
    # the scan re-flags it next run instead of silently orphaning the ticker
    truth, cached, fresh = _split_universe()
    calls: list = []
    a = _adapter(RuntimeError("yf down"), calls)
    merged = a._merge_refreshed(fresh, cached)
    assert calls == [(["AAA"], "4y")]
    assert seam_suspects(None, None, merged) == ["AAA"]
    pd.testing.assert_series_equal(merged["BBB"], truth["BBB"], check_names=False)


def test_extras_grafted_over_fresh_window():
    # the repaired ticker's OHLCV extras must span the full re-pulled window so
    # the later combine_first against the extras cache overrides poisoned rows
    truth, cached, fresh = _split_universe()
    calls: list = []
    a = _adapter(truth, calls)
    a._last_extras = {"high": fresh * 1.01, "volume": fresh * 0 + 1000}
    a._repull_extras = {"high": truth * 1.01, "volume": truth * 0 + 1000}
    merged = a._merge_refreshed(fresh, cached)
    assert calls == [(["AAA"], "4y")]
    high = a._last_extras["high"]
    # AAA's extras now reach back over the whole cached window on the new basis
    assert high["AAA"].first_valid_index() == DATES[0]
    assert float(high["AAA"].iloc[0]) == pytest.approx(float(truth["AAA"].iloc[0]) * 1.01)
    # BBB's extras still only cover the fresh window (cache fills the rest)
    assert high["BBB"].first_valid_index() == fresh.index[0]
    pd.testing.assert_series_equal(merged["AAA"], truth["AAA"], check_names=False)


def test_seam_scan_sees_across_nan_gaps():
    # a suspension gap ending exactly at the seam: without ffill the 1-day
    # ratio at the basis break is NaN/NaN and the seam is invisible
    truth, cached, fresh = _split_universe()
    cached.loc[DATES[95]:DATES[99], "AAA"] = np.nan
    merged = fresh.combine_first(cached)
    assert "AAA" in seam_suspects(None, None, merged)
