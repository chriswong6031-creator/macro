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
4. config: the yahoo block carries upsert_basis_tol, mirroring the odds block;
   the china/hk/canada/intl yahoo blocks carry it too.
5. the regional index/ETF planes (china/hk/canada/intl close+volume stores +
   the intl_etf OHLCV substrate): same discard / re-pull-max / drop-on-failure
   contract on their incremental windows.
6. collectors/sector_holdings.StockPriceAdapter (data/stocks — the US
   deep-history store; measured 2026-07-19: 30/231 names off basis, worst the
   SPGI 5.7% spin-off factor): same discard / re-pull-max / drop-on-failure
   contract, plus the shallow-stub depth heal (a throttled seed pull's ~40-row
   file has 100% volume coverage, so the volume-share check alone would call it
   healthy forever) and overwrite_overlap=True (auto_adjust=True plane).

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
from collectors import canada_prices as canada_mod  # noqa: E402
from collectors import china_prices as china_mod  # noqa: E402
from collectors import hk_prices as hk_mod  # noqa: E402
from collectors import intl_etf as etf_mod  # noqa: E402
from collectors import intl_prices as intl_mod  # noqa: E402
from collectors import sector_holdings as sh  # noqa: E402
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


def test_regional_yahoo_configs_carry_upsert_basis_tol():
    cfg = config.load()
    for region in ("china", "hk", "canada", "intl"):
        assert float(cfg[region]["yahoo"]["upsert_basis_tol"]) == pytest.approx(1e-3), region


# ---------------------------------------------------------------------------
# 5. regional index/ETF planes — same contract for the per-ticker close+volume
#    stores (china/hk/canada/intl) and the intl_etf OHLCV substrate
# ---------------------------------------------------------------------------

def _cv_resp(stored: pd.DataFrame, tail: int | None = None, factor: float = 1.0,
             n_max: int = 420) -> pd.DataFrame:
    """A close+volume yfinance-shaped response (the regional index/ETF schema)."""
    if tail is not None:
        base = stored.tail(tail)
        close = base["close"].to_numpy() / factor
        idx = base.index
    else:
        idx = pd.bdate_range(end="2026-06-30", periods=n_max)
        close = np.linspace(100.0, 150.0, n_max) / factor
    return pd.DataFrame({"Close": close, "Volume": 1e6}, index=idx)


REGIONAL = [
    pytest.param(china_mod.ChinaPriceAdapter, "china", id="china"),
    pytest.param(hk_mod.HkPriceAdapter, "hk", id="hk"),
    pytest.param(canada_mod.CanadaPriceAdapter, "canada", id="canada"),
]
NAMES = ["AAA", "BBB", "CCC", "DDD"]  # 4 names: dropping 1 stays over the 0.7 gate


@pytest.mark.parametrize("cls,group", REGIONAL)
def test_regional_shifted_name_repulls_max(data_dir, monkeypatch, cls, group):
    seeds = {t: _seed(group, t, cols=("close",)) for t in NAMES}
    calls: list = []
    a = cls()
    monkeypatch.setattr(a, "all_tickers", lambda: list(NAMES))

    def fake_download(batch, period):
        calls.append((period, list(batch)))
        if period == "max":
            return _yf_multi({"AAA": _cv_resp(seeds["AAA"], factor=DRIFT)})
        return _yf_multi({t: _cv_resp(seeds[t], tail=20,
                                      factor=DRIFT if t == "AAA" else 1.0) for t in NAMES})

    monkeypatch.setattr(a, "_download", fake_download)
    frames = a.fetch(full_history=False)
    assert [c[0] for c in calls] == ["1mo", "max"]
    assert calls[1][1] == ["AAA"], "only the shifted name is re-pulled"
    assert len(frames["AAA"]) == 420, "the max re-pull replaces the 1mo window wholesale"
    assert all(len(frames[t]) == 20 for t in NAMES[1:]), "clean names keep their windows"


@pytest.mark.parametrize("cls,group", REGIONAL)
def test_regional_failed_repull_drops_the_name(data_dir, monkeypatch, cls, group):
    seeds = {t: _seed(group, t, cols=("close",)) for t in NAMES}
    a = cls()
    monkeypatch.setattr(a, "all_tickers", lambda: list(NAMES))

    def fake_download(batch, period):
        if period == "max":
            raise RuntimeError("yahoo down")
        return _yf_multi({t: _cv_resp(seeds[t], tail=20,
                                      factor=DRIFT if t == "AAA" else 1.0) for t in NAMES})

    monkeypatch.setattr(a, "_download", fake_download)
    frames = a.fetch(full_history=False)
    assert "AAA" not in frames, "a shifted window must never reach the store"
    assert set(frames) == set(NAMES) - {"AAA"}


def test_intl_prices_shifted_name_repulls_max(data_dir, monkeypatch):
    core = ["^N225", "JPY=X", "^FTSE", "GBPUSD=X"]
    seeds = {t: _seed("intl", t, cols=("close",)) for t in core}
    calls: list = []
    a = intl_mod.IntlPriceAdapter()
    monkeypatch.setattr(a, "_ticker_sets", lambda: (list(core), []))

    def fake_download(batch, period):
        calls.append((period, list(batch)))
        if period == "max":
            return _yf_multi({"^N225": _cv_resp(seeds["^N225"], factor=DRIFT)})
        return _yf_multi({t: _cv_resp(seeds[t], tail=20,
                                      factor=DRIFT if t == "^N225" else 1.0) for t in core})

    monkeypatch.setattr(a, "_download", fake_download)
    frames = a.fetch(full_history=False)
    assert [c[0] for c in calls] == ["1mo", "max"]
    assert calls[1][1] == ["^N225"], "only the shifted name is re-pulled"
    assert len(frames["^N225"]) == 420
    assert all(len(frames[t]) == 20 for t in core[1:])


def test_intl_prices_failed_repull_drops_the_name(data_dir, monkeypatch):
    core = ["^N225", "JPY=X", "^FTSE", "GBPUSD=X"]
    seeds = {t: _seed("intl", t, cols=("close",)) for t in core}
    a = intl_mod.IntlPriceAdapter()
    monkeypatch.setattr(a, "_ticker_sets", lambda: (list(core), []))

    def fake_download(batch, period):
        if period == "max":
            return None  # intl's _download degrades to None on a dead endpoint
        return _yf_multi({t: _cv_resp(seeds[t], tail=20,
                                      factor=DRIFT if t == "^N225" else 1.0) for t in core})

    monkeypatch.setattr(a, "_download", fake_download)
    frames = a.fetch(full_history=False)
    assert "^N225" not in frames, "a shifted window must never reach the store"
    assert set(frames) == set(core) - {"^N225"}


ETF_UNIV = ["EWJ", "EWG", "EWQ", "EWU"]  # 4 tickers: dropping 1 meets the 80% gate exactly


def test_intl_etf_shifted_ticker_repulls_max(data_dir, monkeypatch):
    monkeypatch.setattr(etf_mod, "TICKERS", list(ETF_UNIV))
    seeds = {t: _seed("intl_etf", t, cols=("close",)) for t in ETF_UNIV}
    calls: list = []
    a = etf_mod.IntlEtfAdapter()

    def fake_download(batch, period):
        calls.append((period, list(batch)))
        if period == "max":
            return _yf_multi({"EWJ": _cn_resp(seeds["EWJ"], factor=DRIFT)})
        return _yf_multi({t: _cn_resp(seeds[t], tail=15,
                                      factor=DRIFT if t == "EWJ" else 1.0) for t in ETF_UNIV})

    monkeypatch.setattr(a, "_download", fake_download)
    frames = a.fetch(full_history=False)
    assert [c[0] for c in calls] == [etf_mod.INCREMENTAL_PERIOD, "max"]
    assert calls[1][1] == ["EWJ"], "only the shifted ticker is re-pulled"
    assert len(frames["EWJ"]) == 420
    assert all(len(frames[t]) == 15 for t in ETF_UNIV[1:])


def test_intl_etf_failed_repull_drops_the_ticker(data_dir, monkeypatch):
    monkeypatch.setattr(etf_mod, "TICKERS", list(ETF_UNIV))
    seeds = {t: _seed("intl_etf", t, cols=("close",)) for t in ETF_UNIV}
    a = etf_mod.IntlEtfAdapter()

    def fake_download(batch, period):
        if period == "max":
            return None  # intl_etf's _download degrades to None after retries
        return _yf_multi({t: _cn_resp(seeds[t], tail=15,
                                      factor=DRIFT if t == "EWJ" else 1.0) for t in ETF_UNIV})

    monkeypatch.setattr(a, "_download", fake_download)
    frames = a.fetch(full_history=False)
    assert "EWJ" not in frames, "a shifted window must never reach the store"
    assert set(frames) == set(ETF_UNIV) - {"EWJ"}  # 3/4 clears int(0.8*4)=3 — gate holds


# ---------------------------------------------------------------------------
# 6. collectors/sector_holdings.StockPriceAdapter — the US deep-history store
# ---------------------------------------------------------------------------

SPINOFF = 1.057  # the measured SPGI spin-off factor (action 2026-07-01)


def _stocks_resp(stored: pd.DataFrame, tail: int | None = None, factor: float = 1.0,
                 n_max: int = 420) -> pd.DataFrame:
    """A raw yfinance-shaped response (Close/High/Low/Volume) for one ticker."""
    if tail is not None:
        base = stored.tail(tail)
        close = base["close"].to_numpy() / factor
        idx = base.index
    else:
        idx = pd.bdate_range(end="2026-06-30", periods=n_max)
        close = np.linspace(100.0, 150.0, n_max) / factor
    return pd.DataFrame({"Close": close, "High": close, "Low": close,
                         "Volume": 1e6}, index=idx)


def _make_stocks_adapter(monkeypatch, tickers: list[str], responder, calls: list):
    a = sh.StockPriceAdapter()
    monkeypatch.setattr(sh, "top10_union", lambda: list(tickers))

    def fake_download(batch, period):
        calls.append((period, list(batch)))
        return responder(batch, period)

    monkeypatch.setattr(a, "_download", fake_download)
    return a


def test_stocks_shifted_name_repulls_max_and_clean_name_keeps_window(data_dir, monkeypatch):
    spgi = _seed("stocks", "SPGI", cols=("close", "high", "low"))
    aapl = _seed("stocks", "AAPL", cols=("close", "high", "low"))
    calls: list = []

    def responder(batch, period):
        if period == "max":
            return _yf_multi({"SPGI": _stocks_resp(spgi, factor=SPINOFF)})
        return _yf_multi({
            "SPGI": _stocks_resp(spgi, tail=20, factor=SPINOFF),  # re-based window
            "AAPL": _stocks_resp(aapl, tail=20),                  # clean window
        })

    a = _make_stocks_adapter(monkeypatch, ["SPGI", "AAPL"], responder, calls)
    frames = a.fetch(full_history=False)

    assert [c[0] for c in calls] == ["1mo", "max"]
    assert calls[1][1] == ["SPGI"], "only the shifted name is re-pulled"
    assert len(frames["SPGI"]) == 420, "the max re-pull replaces the 1mo window wholesale"
    assert len(frames["AAPL"]) == 20, "a clean name keeps its cheap window"
    assert {"close", "high", "low", "volume"} <= set(frames["SPGI"].columns)


def test_stocks_failed_repull_drops_the_name_instead_of_splicing(data_dir, monkeypatch):
    seeds = {t: _seed("stocks", t, cols=("close", "high", "low"))
             for t in ["SPGI", "AAPL", "MSFT", "NVDA"]}
    calls: list = []

    def responder(batch, period):
        if period == "max":
            raise RuntimeError("yahoo down")
        return _yf_multi({
            t: _stocks_resp(df, tail=20, factor=SPINOFF if t == "SPGI" else 1.0)
            for t, df in seeds.items()
        })

    a = _make_stocks_adapter(monkeypatch, list(seeds), responder, calls)
    frames = a.fetch(full_history=False)

    assert "SPGI" not in frames, "a shifted window must never reach the store"
    assert set(frames) == {"AAPL", "MSFT", "NVDA"}  # 3/4 clears the 0.7 floor


def test_stocks_shallow_stub_gets_full_backfill(data_dir, monkeypatch):
    """The CBRE/ISRG/KMI/MLM class (2026-05): a throttled seed pull left a ~42-row
    stub with 100% volume coverage, which the volume-share heal calls healthy
    forever. The depth check must route it back to period='max'."""
    stub = _seed("stocks", "ISRG", n=42, cols=("close", "high", "low"))
    calls: list = []

    def responder(batch, period):
        return _yf_multi({"ISRG": _stocks_resp(stub, n_max=420)})

    a = _make_stocks_adapter(monkeypatch, ["ISRG"], responder, calls)
    frames = a.fetch(full_history=False)

    assert [c[0] for c in calls] == ["max"], "shallow stub goes straight to full history"
    assert len(frames["ISRG"]) == 420


def test_stocks_adapter_declares_overwrite_overlap():
    """auto_adjust=True plane: the refresh window must own its span seam-free."""
    assert sh.StockPriceAdapter.overwrite_overlap is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
