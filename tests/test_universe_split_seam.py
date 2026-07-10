"""Split-seam repair for the search-universe closes caches (#2120 follow-up audit).

collectors/breadth.py fixed the KLAC-class seam (yfinance auto_adjust back-adjusts
only the freshly downloaded window, so a tail refresh leaves cached pre-window rows
on the pre-split price basis) for the breadth caches. The same merge pattern lives
in the search-universe collectors:

  canada/intl closes.parquet  fresh.combine_first(prev) — vulnerable everywhere
  china closes.parquet        _overwrite_overlap — seam-free INSIDE the fresh
                              window, but pre-window rows keep the old basis
  hk_search closes_deep       merged downstream by store.upsert combine_first —
                              heal must rewrite the stored file in place

All four now route through collectors.breadth.repair_seams (per-ticker full
re-pull, wholesale column replacement, never fatal). Pure-function tests: every
downloader is monkeypatched. Mirrors tests/test_breadth_split_seam.py.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.breadth import repair_seams, seam_suspects  # noqa: E402
from collectors.canada_universe import CanadaUniverseAdapter  # noqa: E402
from collectors.china_universe import ChinaUniverseAdapter, _overwrite_overlap  # noqa: E402
from collectors.hk_closes_deep import HkClosesDeepAdapter  # noqa: E402
from collectors.intl_universe import IntlUniverseAdapter  # noqa: E402

# 120 business days of history; the fresh refresh window covers the last 20
DATES = pd.bdate_range("2026-01-05", periods=120)


def _frame(cols: dict, index=None) -> pd.DataFrame:
    return pd.DataFrame(cols, index=DATES if index is None else index)


def _drifting(base: float, seed: int = 7, index=None) -> pd.Series:
    """A gently drifting price path — daily moves well inside the seam bounds."""
    idx = DATES if index is None else index
    rng = np.random.default_rng(seed)
    steps = 1 + rng.uniform(-0.02, 0.02, len(idx))
    return pd.Series(base * np.cumprod(steps), index=idx)


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


def _fake_downloader(repull: pd.DataFrame | Exception | None, calls: list):
    def download(tickers, period):
        calls.append((sorted(tickers), period))
        if isinstance(repull, Exception):
            raise repull
        assert repull is not None, "unexpected repair download"
        return repull[[t for t in sorted(tickers) if t in repull.columns]]
    return download


def _adapter(cls, repull, calls):
    # skip __init__/config.load — _merge_refreshed reads only name + _download_closes
    a = cls.__new__(cls)
    a._download_closes = _fake_downloader(repull, calls)
    return a


# --- repair_seams (the shared core) ------------------------------------------

def test_repair_seams_boundary_heal_and_span_period():
    truth, cached, fresh = _split_universe()
    calls: list = []
    merged, healed = repair_seams(fresh.combine_first(cached), fresh, cached,
                                  _fake_downloader(truth, calls))
    # one batched re-pull of exactly the seamed ticker, window derived from span
    assert calls == [(["AAA"], "1y")]
    assert healed == ["AAA"]
    pd.testing.assert_series_equal(merged["AAA"], truth["AAA"], check_names=False)
    pd.testing.assert_series_equal(merged["BBB"], truth["BBB"], check_names=False)
    r = merged / merged.shift(1)
    assert float(r.min().min()) > 0.60 and float(r.max().max()) < 1.65


def test_repair_seams_failed_repull_keeps_poison():
    truth, cached, fresh = _split_universe()
    calls: list = []
    merged, healed = repair_seams(fresh.combine_first(cached), fresh, cached,
                                  _fake_downloader(RuntimeError("yf down"), calls))
    assert calls == [(["AAA"], "1y")] and healed == []
    # the seam stays visible so the scan re-flags it next run
    assert seam_suspects(None, None, merged) == ["AAA"]
    pd.testing.assert_series_equal(merged["BBB"], truth["BBB"], check_names=False)


def test_repair_seams_real_crash_survives():
    # a genuine -62% day trips the scan; the re-pull returns the same data and
    # the "repair" must preserve the crash, not smooth it away
    crash = _drifting(100.0, 3)
    crash.iloc[40:] *= 0.38
    truth = _frame({"AAA": crash, "BBB": _drifting(50.0, 4)})
    cached, fresh = truth.iloc[:-5], truth.iloc[-20:]
    calls: list = []
    merged, healed = repair_seams(fresh.combine_first(cached), fresh, cached,
                                  _fake_downloader(truth, calls))
    assert healed == ["AAA"]
    pd.testing.assert_series_equal(merged["AAA"], truth["AAA"], check_names=False)


def test_repair_seams_clean_matrix_no_download():
    truth = _frame({"AAA": _drifting(100.0, 5), "BBB": _drifting(50.0, 6)})
    cached, fresh = truth.iloc[:-5], truth.iloc[-20:]
    calls: list = []
    merged, healed = repair_seams(fresh.combine_first(cached), fresh, cached,
                                  _fake_downloader(None, calls))
    assert calls == [] and healed == []
    pd.testing.assert_frame_equal(merged, fresh.combine_first(cached))


def test_repair_seams_scan_window_skips_deep_history():
    # a genuine crash day OLDER than the scan window (e.g. 1987/2008 in the 40y
    # hk matrix) must NOT trigger a re-pull every night — but the full-file scan
    # (scan_days=None, the one-shot healer's mode) still sees it
    idx = pd.bdate_range("2023-01-02", periods=780)          # ~3y of days
    crash = _drifting(100.0, 8, index=idx)
    crash.iloc[30:] *= 0.40                                   # deep-history -60% day
    truth = pd.DataFrame({"AAA": crash}, index=idx)
    cached, fresh = truth.iloc[:-5], truth.iloc[-20:]
    merged = fresh.combine_first(cached)
    calls: list = []
    _, healed = repair_seams(merged, fresh, cached, _fake_downloader(None, calls))
    assert calls == [] and healed == []                       # windowed scan: quiet
    calls2: list = []
    _, healed2 = repair_seams(merged, fresh, cached, _fake_downloader(truth, calls2),
                              scan_days=None)
    span_period = f"{(merged.index.max() - merged.index.min()).days // 365 + 1}y"
    assert calls2 == [(["AAA"], span_period)] and healed2 == ["AAA"]  # legacy sweep sees it


# --- canada / intl (plain combine_first refresh) ------------------------------

@pytest.mark.parametrize("cls", [CanadaUniverseAdapter, IntlUniverseAdapter])
def test_universe_merge_refreshed_heals_boundary_seam(cls):
    truth, cached, fresh = _split_universe()
    calls: list = []
    a = _adapter(cls, truth, calls)
    merged = a._merge_refreshed(fresh, cached)
    assert calls == [(["AAA"], "1y")]
    pd.testing.assert_series_equal(merged["AAA"], truth["AAA"], check_names=False)
    pd.testing.assert_series_equal(merged["BBB"], truth["BBB"], check_names=False)


@pytest.mark.parametrize("cls", [CanadaUniverseAdapter, IntlUniverseAdapter])
def test_universe_merge_refreshed_failed_repull_never_fatal(cls):
    truth, cached, fresh = _split_universe()
    calls: list = []
    a = _adapter(cls, RuntimeError("yf down"), calls)
    merged = a._merge_refreshed(fresh, cached)               # must not raise
    assert calls == [(["AAA"], "1y")]
    assert seam_suspects(None, None, merged) == ["AAA"]      # retried next run


# --- china (_overwrite_overlap leaves the PRE-window rows stale) ---------------

def test_china_pre_window_seam_healed():
    truth, cached, fresh = _split_universe()
    # _overwrite_overlap alone: fresh owns its span, but the pre-window rows stay
    # on the 10x basis — the exact residual hole this repair closes
    plain = _overwrite_overlap(fresh, cached)
    assert "AAA" in seam_suspects(fresh, cached, plain)
    calls: list = []
    a = _adapter(ChinaUniverseAdapter, truth, calls)
    merged = a._merge_refreshed(fresh, cached)
    assert calls == [(["AAA"], "1y")]
    pd.testing.assert_series_equal(merged["AAA"].dropna(), truth["AAA"].loc[
        merged["AAA"].dropna().index], check_names=False)
    r = merged.ffill() / merged.ffill().shift(1)
    assert float(r.min().min()) > 0.60 and float(r.max().max()) < 1.65


def test_china_dividend_scale_does_not_trigger():
    # dividend re-adjustment shifts the cached basis by ~1.5% — below tolerance;
    # result must be the plain _overwrite_overlap merge, no repair download
    truth = _frame({"AAA": _drifting(100.0, 5), "BBB": _drifting(50.0, 6)})
    cached = truth.iloc[:-5].copy()
    cached["AAA"] *= 1.015
    fresh = truth.iloc[-20:]
    calls: list = []
    a = _adapter(ChinaUniverseAdapter, None, calls)
    merged = a._merge_refreshed(fresh, cached)
    assert calls == []
    pd.testing.assert_frame_equal(merged, _overwrite_overlap(fresh, cached))


# --- hk closes_deep (store merged downstream — heal rewrites the file) ---------

def _hk_adapter(tmp_path, monkeypatch, repull, calls):
    from lib import config as libconfig
    monkeypatch.setattr(libconfig, "data_dir", lambda: tmp_path)
    a = HkClosesDeepAdapter.__new__(HkClosesDeepAdapter)
    a._download = _fake_downloader(repull, calls)
    return a


def test_hk_heal_rewrites_store_in_place(tmp_path, monkeypatch):
    truth, cached, fresh = _split_universe()
    store = tmp_path / "hk_search"
    store.mkdir()
    cached.to_parquet(store / "closes_deep.parquet")
    calls: list = []
    a = _hk_adapter(tmp_path, monkeypatch, truth, calls)
    a._heal_store_seams(fresh)
    assert calls == [(["AAA"], "max")]                       # deep matrix → full history
    healed = pd.read_parquet(store / "closes_deep.parquet")
    # the STORED pre-window history is on the adjusted basis before the runner's
    # combine_first merge ever sees it
    pd.testing.assert_series_equal(healed["AAA"], truth["AAA"].reindex(cached.index),
                                   check_names=False, check_freq=False)
    pd.testing.assert_series_equal(healed["BBB"], cached["BBB"],
                                   check_names=False, check_freq=False)


def test_hk_failed_repull_leaves_store_untouched(tmp_path, monkeypatch):
    _, cached, fresh = _split_universe()
    store = tmp_path / "hk_search"
    store.mkdir()
    cached.to_parquet(store / "closes_deep.parquet")
    calls: list = []
    a = _hk_adapter(tmp_path, monkeypatch, RuntimeError("yf down"), calls)
    a._heal_store_seams(fresh)                               # must not raise
    assert calls == [(["AAA"], "max")]
    kept = pd.read_parquet(store / "closes_deep.parquet")
    pd.testing.assert_frame_equal(kept, cached, check_freq=False)  # poison kept for retry


def test_hk_no_store_is_a_noop(tmp_path, monkeypatch):
    _, _, fresh = _split_universe()
    calls: list = []
    a = _hk_adapter(tmp_path, monkeypatch, None, calls)
    a._heal_store_seams(fresh)                               # no file → no scan, no raise
    assert calls == []
