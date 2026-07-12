"""Adjustment-basis guard for windowed yfinance upserts (lib.store.basis_shifted).

yfinance re-adjusts the WHOLE series at every fetch, so a short refresh window
pulled after an ex-div/split sits on a NEW basis while the stored parquet keeps
the old one; splicing strands every pre-window row on the stale basis (measured:
data/yahoo/SPY.parquet uniformly +0.2576% off a fresh fetch on all 8,382 rows
before 2026-05-18 — exactly one dividend of drift; a missed split would be a 10x
step). Ported from the odds-store guard in scripts/build_odds.ensure_store.

Pins (network-free — the download layer is stubbed):
1. store.basis_shifted truth table: fresh name False; matching overlap False;
   sub-tol noise False; the one-dividend uniform shift True; disjoint window
   True; a split on the raw plane True.
2. collectors/yahoo.py: a shifted name's 1mo window is DISCARDED and re-pulled
   period='max' (the whole store rebases in one upsert); a clean name keeps its
   window; a failed re-pull drops the name from the run entirely (never spliced).
3. collectors/_stock_ohlc.py: the same contract for the china/hk per-stock
   stores (adjusted and raw planes share the machinery).
4. config: the yahoo block carries upsert_basis_tol, mirroring the odds block.

Run: .venv/bin/python -m pytest tests/test_upsert_basis_guard.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors import _stock_ohlc as so  # noqa: E402
from collectors import yahoo as yahoo_mod  # noqa: E402
from lib import config, store  # noqa: E402

DRIFT = 1.002576  # the measured SPY one-dividend basis factor


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    return tmp_path


def _seed(group: str, name: str, n: int = 400, cols=("close", "close_price")) -> pd.DataFrame:
    """Write a stored parquet on the OLD basis; returns the frame."""
    idx = pd.bdate_range(end="2026-06-30", periods=n)
    close = np.linspace(100.0, 150.0, n)
    df = pd.DataFrame({c: close for c in cols}, index=idx)
    df["volume"] = 1e6
    df.index.name = "Date"
    df.to_parquet(store._path(group, name))
    return df


# ---------------------------------------------------------------------------
# 1. store.basis_shifted truth table
# ---------------------------------------------------------------------------

def test_fresh_name_is_not_shifted(data_dir):
    new = pd.DataFrame({"close": [1.0, 2.0]}, index=pd.bdate_range("2026-06-01", periods=2))
    assert store.basis_shifted("yahoo", "NEWNAME", new) is False


def test_matching_overlap_is_not_shifted(data_dir):
    old = _seed("yahoo", "SPY")
    assert store.basis_shifted("yahoo", "SPY", old.tail(20).copy()) is False


def test_sub_tol_noise_is_not_shifted(data_dir):
    old = _seed("yahoo", "SPY")
    new = old.tail(20).copy()
    new["close"] *= 1.0005  # half the 1e-3 default — a late-print revision, not a re-basing
    assert store.basis_shifted("yahoo", "SPY", new) is False


def test_one_dividend_uniform_shift_flags(data_dir):
    """The SPY signature: every overlap date off by the same ~0.26% factor."""
    old = _seed("yahoo", "SPY")
    new = old.tail(20).copy()
    new["close"] /= DRIFT  # window on the fresh (post-dividend) basis
    assert store.basis_shifted("yahoo", "SPY", new) is True


def test_disjoint_window_flags(data_dir):
    """Stored series ended before the window starts: the basis is unverifiable and
    a splice would also leave a bar gap — must force a full refetch."""
    _seed("yahoo", "SPY", n=300)  # ends 2026-06-30
    new = pd.DataFrame({"close": [1.0] * 5}, index=pd.bdate_range("2026-09-01", periods=5))
    assert store.basis_shifted("yahoo", "SPY", new) is True


def test_split_is_visible_on_the_raw_plane(data_dir):
    """Raw (div-unadjusted) closes are still split-adjusted — a 10送10 re-bases them."""
    old = _seed("china_stocks_raw", "600000.SS", cols=("close",))
    new = old.tail(20).copy()
    new["close"] /= 2.0
    assert store.basis_shifted("china_stocks_raw", "600000.SS", new) is True


# ---------------------------------------------------------------------------
# 2. collectors/yahoo.py — window discarded, period='max' re-pull, drop-on-failure
# ---------------------------------------------------------------------------

def _yf_multi(frames_by_ticker: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Assemble a MultiIndex (ticker, field) frame like yf.download(group_by='ticker')."""
    parts = {}
    for t, df in frames_by_ticker.items():
        for c in df.columns:
            parts[(t, c)] = df[c]
    out = pd.DataFrame(parts)
    out.columns = pd.MultiIndex.from_tuples(out.columns)
    return out


def _yahoo_resp(stored: pd.DataFrame, tail: int | None = None, factor: float = 1.0,
                n_max: int = 420) -> pd.DataFrame:
    """A raw yfinance-shaped response (Close/Adj Close/Volume) for one ticker.
    tail=N -> the 1mo window (last N stored dates); tail=None -> a full period='max'
    history of n_max rows. factor divides the closes (fresh basis simulation)."""
    if tail is not None:
        base = stored.tail(tail)
        close = base["close"].to_numpy() / factor
        idx = base.index
    else:
        idx = pd.bdate_range(end="2026-06-30", periods=n_max)
        close = np.linspace(100.0, 150.0, n_max) / factor
    return pd.DataFrame({"Close": close, "Adj Close": close, "Volume": 1e6}, index=idx)


def _make_adapter(monkeypatch, tickers: list[str], responder, calls: list):
    a = yahoo_mod.YahooAdapter()
    monkeypatch.setattr(a, "all_tickers", lambda: list(tickers))
    monkeypatch.setattr(a, "_fill_missing_extras", lambda frames, extras: frames)

    def fake_download(batch, period):
        calls.append((period, list(batch)))
        return responder(batch, period)

    monkeypatch.setattr(a, "_download", fake_download)
    return a


def test_yahoo_shifted_name_repulls_max_and_clean_name_keeps_window(data_dir, monkeypatch):
    spy = _seed("yahoo", "SPY")
    xlk = _seed("yahoo", "XLK")
    calls: list = []

    def responder(batch, period):
        if period == "max":
            return _yf_multi({"SPY": _yahoo_resp(spy, factor=DRIFT)})
        return _yf_multi({
            "SPY": _yahoo_resp(spy, tail=20, factor=DRIFT),  # re-based window
            "XLK": _yahoo_resp(xlk, tail=20),                # clean window
        })

    a = _make_adapter(monkeypatch, ["SPY", "XLK"], responder, calls)
    frames = a.fetch(full_history=False)

    assert [c[0] for c in calls] == ["1mo", "max"]
    assert calls[1][1] == ["SPY"], "only the shifted name is re-pulled"
    assert len(frames["SPY"]) == 420, "the max re-pull replaces the 1mo window wholesale"
    assert len(frames["XLK"]) == 20, "a clean name keeps its cheap window"
    # dual-basis schema survives the re-pull path
    assert {"close", "close_price", "volume"} <= set(frames["SPY"].columns)


def test_yahoo_failed_repull_drops_the_name_instead_of_splicing(data_dir, monkeypatch):
    seeds = {t: _seed("yahoo", t) for t in ["SPY", "XLK", "HYG", "LQD"]}
    calls: list = []

    def responder(batch, period):
        if period == "max":
            raise RuntimeError("yahoo down")
        return _yf_multi({
            t: _yahoo_resp(df, tail=20, factor=DRIFT if t == "SPY" else 1.0)
            for t, df in seeds.items()
        })

    a = _make_adapter(monkeypatch, list(seeds), responder, calls)
    frames = a.fetch(full_history=False)

    assert "SPY" not in frames, "a shifted window must never reach the store"
    assert set(frames) == {"XLK", "HYG", "LQD"}


def test_yahoo_full_history_skips_the_guard(data_dir, monkeypatch):
    spy = _seed("yahoo", "SPY")
    calls: list = []
    a = _make_adapter(monkeypatch, ["SPY"], lambda batch, period:
                      _yf_multi({"SPY": _yahoo_resp(spy, factor=DRIFT)}), calls)
    frames = a.fetch(full_history=True)
    assert [c[0] for c in calls] == ["max"], "a max pull already rebases — nothing to guard"
    assert len(frames["SPY"]) == 420


# ---------------------------------------------------------------------------
# 3. collectors/_stock_ohlc.py — same contract for the china/hk stock stores
# ---------------------------------------------------------------------------

CN_CFG = {"batch_size": 50, "sleep_s": 0, "retries": 1, "backoff_base_s": 0}


def _cn_resp(stored: pd.DataFrame, tail: int | None = None, factor: float = 1.0,
             n_max: int = 420) -> pd.DataFrame:
    if tail is not None:
        base = stored.tail(tail)
        close = base["close"].to_numpy() / factor
        idx = base.index
    else:
        idx = pd.bdate_range(end="2026-06-30", periods=n_max)
        close = np.linspace(100.0, 150.0, n_max) / factor
    return pd.DataFrame({"Open": close, "Close": close, "High": close,
                         "Low": close, "Volume": 1e5}, index=idx)


def test_stock_ohlc_shifted_window_is_rebased(data_dir, monkeypatch):
    old = _seed("china_stocks", "600000.SS", cols=("close",))
    calls: list = []

    def fake_download(batch, period, cfg, auto_adjust=True):
        calls.append(period)
        return _cn_resp(old, tail=15, factor=1.1) if period == "1mo" else _cn_resp(old, factor=1.1)

    monkeypatch.setattr(so, "_download", fake_download)
    frames = so.fetch_ohlc(["600000.SS"], "china_stocks", CN_CFG, full_history=False)
    assert calls == ["1mo", "max"]
    assert len(frames["600000.SS"]) == 420


def test_stock_ohlc_clean_window_splices_as_before(data_dir, monkeypatch):
    old = _seed("china_stocks", "600000.SS", cols=("close",))
    calls: list = []

    def fake_download(batch, period, cfg, auto_adjust=True):
        calls.append(period)
        return _cn_resp(old, tail=15)

    monkeypatch.setattr(so, "_download", fake_download)
    frames = so.fetch_ohlc(["600000.SS"], "china_stocks", CN_CFG, full_history=False)
    assert calls == ["1mo"]
    assert len(frames["600000.SS"]) == 15


def test_stock_ohlc_failed_rebase_skips_the_name(data_dir, monkeypatch):
    clean = _seed("china_stocks", "000001.SZ", cols=("close",))
    drift = _seed("china_stocks", "600000.SS", cols=("close",))

    def fake_download(batch, period, cfg, auto_adjust=True):
        if period == "max":
            raise RuntimeError("yahoo down")
        return _yf_multi({
            "000001.SZ": _cn_resp(clean, tail=15),
            "600000.SS": _cn_resp(drift, tail=15, factor=1.1),
        })

    monkeypatch.setattr(so, "_download", fake_download)
    frames = so.fetch_ohlc(["000001.SZ", "600000.SS"], "china_stocks", CN_CFG,
                           full_history=False)
    assert "600000.SS" not in frames, "a shifted window must never reach the store"
    assert len(frames["000001.SZ"]) == 15


# ---------------------------------------------------------------------------
# 4. config carries the knob (mirrors the odds block)
# ---------------------------------------------------------------------------

def test_yahoo_config_carries_upsert_basis_tol():
    assert float(config.load()["yahoo"]["upsert_basis_tol"]) == pytest.approx(1e-3)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
