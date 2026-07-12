"""Shared per-name daily-OHLC pull for the China + HK signal stores
(group = ``china_stocks`` / ``hk_stocks``).

Mirrors ``collectors/china_prices.py``'s yfinance pull but keeps the **full OHLC**
(close/high/low/volume) that the MACD-RSI x StochRSI confluence + buy-filter need —
versus the close+volume the index/ETF stores (``data/china`` / ``data/hk``) keep.
Store layout matches ``data/stocks/*.parquet`` (the US deep-history store): one
parquet per ticker, ``DatetimeIndex`` named ``Date``, columns ``[open, close, high,
low, volume]`` float64. yfinance ``.SS``/``.SZ``/``.HK`` suffixes already match the
existing namespaces, so there is no remap. See
``research/signal_engine/MULTICOUNTRY_DATA.md`` for the source decision.

``open`` was added (CN-1 masterplan §W6-CN) so the china_standout_track ledger can
grade a TRUE T+1-open fill instead of the (H+L)/2 proxy — the dominant fill-realism
uncertainty (+4.41% vs +2.13% at 21d). Legacy history has no Open until
``scripts/backfill_stock_open.py`` re-pulls it; ``store.upsert`` merges the column
in additively and every downstream reader treats it as optional, so the schema
change is backward-compatible.
"""
from __future__ import annotations

import logging
import time

import pandas as pd
import yfinance as yf

from lib import config, store

log = logging.getLogger(__name__)

_OHLC = ["Open", "Close", "High", "Low", "Volume"]
_REN = {"Open": "open", "Close": "close", "High": "high", "Low": "low", "Volume": "volume"}
_DEEP_MIN_ROWS = 250  # already-deep names take the cheap 1mo window


def universe_columns(relpath: str, seed: list[str] | None = None) -> list[str]:
    """Ticker universe = the column names of a committed wide-closes cache
    (e.g. ``china_search/closes.parquet``), unioned with the config ``seed``.
    Defensive: a missing cache (e.g. a fresh CI checkout) degrades to the seed
    alone rather than raising — the runner just collects fewer names that night."""
    out: list[str] = list(seed or [])
    p = config.data_dir() / relpath
    if p.exists():
        try:
            out += [str(c) for c in pd.read_parquet(p).columns]
        except Exception as e:  # noqa: BLE001 — universe is best-effort context, never fatal
            log.warning("stock_ohlc: could not read universe %s: %s", relpath, e)
    return list(dict.fromkeys(out))


def _download(batch: list[str], period: str, cfg: dict, auto_adjust: bool = True) -> pd.DataFrame:
    last_exc: Exception | None = None
    for attempt in range(cfg["retries"]):
        try:
            df = yf.download(batch, period=period, auto_adjust=auto_adjust,
                             progress=False, group_by="ticker", threads=True)
            if df is None or df.empty:
                raise RuntimeError("empty yfinance response")
            return df
        except Exception as e:  # noqa: BLE001
            last_exc = e
            wait = cfg["backoff_base_s"] * (2 ** attempt)
            log.warning("stock_ohlc batch failed (%s); retry in %.0fs", e, wait)
            time.sleep(wait)
    raise last_exc  # type: ignore[misc]


def _fetch_plan(tickers: list[str], group: str, full_history: bool) -> dict[str, list[str]]:
    """Newly-added / shallow names pull ``period='max'`` (backfill from inception);
    names already deep on disk take the cheap ``'1mo'`` window. ``store.upsert``
    dedups by date, so re-pulling 'max' over a shallow series just completes it."""
    if full_history:
        return {"max": list(tickers)}
    deep, shallow = [], []
    for t in tickers:
        df = store.read(group, t)
        (deep if (df is not None and len(df) >= _DEEP_MIN_ROWS) else shallow).append(t)
    return {"1mo": deep, "max": shallow}


def fetch_ohlc(tickers: list[str], group: str, cfg: dict,
               full_history: bool, auto_adjust: bool = True) -> dict[str, pd.DataFrame]:
    """Pull OHLC for ``tickers`` into ``{ticker: frame[close,high,low,volume]}``.

    Chunked (``batch_size``) with an inter-chunk ``sleep_s`` to stay under Yahoo's
    429 throttle on the ~1.5k-name first backfill. A chunk that fails permanently is
    SKIPPED (logged), not fatal — ``store.upsert`` is incremental so the next nightly
    run refills the gap. Raises only when *nothing* came back (so the circuit breaker
    can act on a truly dead endpoint).

    ``auto_adjust`` — True (default) is the dividend/split-ADJUSTED total-return plane
    the confluence/reversal signals use. False is the RAW/nominal price plane needed for
    level, limit-up/gap and honest A/H-premium logic (there is no raw A-share close
    anywhere else in the repo — masterplan §W6-CN fix 3). The raw plane stores to a
    SEPARATE group so the two planes never mix.

    Adjustment-basis guard (``store.basis_shifted``, the odds-store pattern): a deep
    name whose 1mo window disagrees with its stored closes on the overlap dates was
    re-adjusted by Yahoo (ex-div/split) since the last pull — splicing would strand
    every pre-window row on the stale basis. The window is discarded and the name
    re-pulled period='max'; a failed re-pull just skips the name tonight (store
    untouched, re-flagged next run). Applies to the raw plane too: raw closes are
    still split-adjusted, so a split re-bases them the same way."""
    frames: dict[str, pd.DataFrame] = {}
    rebase: list[str] = []
    bs = int(cfg.get("batch_size", 50))
    sleep_s = float(cfg.get("sleep_s", 2.0))
    tol = float(cfg.get("upsert_basis_tol", 1e-3))
    for period, tks in _fetch_plan(tickers, group, full_history).items():
        for i in range(0, len(tks), bs):
            batch = tks[i:i + bs]
            if not batch:
                continue
            try:
                df = _download(batch, period, cfg, auto_adjust=auto_adjust)
            except Exception as e:  # noqa: BLE001 — one dead chunk must not kill the rest
                log.warning("stock_ohlc[%s]: chunk of %d failed permanently (%s); skipping",
                            group, len(batch), e)
                continue
            for t in batch:
                sub = _extract(df, t, group)
                if sub is None:
                    continue
                if period == "1mo" and store.basis_shifted(group, t, sub, tol=tol):
                    rebase.append(t)  # discard the window; re-pull full history below
                    continue
                frames[t] = sub
            if i + bs < len(tks):
                time.sleep(sleep_s)
    if rebase:
        log.info("stock_ohlc[%s]: %d name(s) on a re-adjusted basis — refetching "
                 "period='max': %s", group, len(rebase), rebase[:12])
        for i in range(0, len(rebase), bs):
            batch = rebase[i:i + bs]
            try:
                df = _download(batch, "max", cfg, auto_adjust=auto_adjust)
            except Exception as e:  # noqa: BLE001 — skip tonight; the guard re-flags next run
                log.warning("stock_ohlc[%s]: basis refetch failed for %d name(s) (%s) — "
                            "kept out of this run", group, len(batch), e)
                continue
            for t in batch:
                sub = _extract(df, t, group)
                if sub is not None:
                    frames[t] = sub
            if i + bs < len(rebase):
                time.sleep(sleep_s)
    if not frames:
        raise RuntimeError(f"stock_ohlc[{group}]: 0/{len(tickers)} tickers returned data")
    return frames


def _extract(df: pd.DataFrame, t: str, group: str) -> pd.DataFrame | None:
    """Slice one ticker out of a (possibly MultiIndex) yf.download response into the
    store schema. Open is preferred but optional: a yfinance response missing it (rare)
    must not drop the whole name — keep every requested column present, require Close."""
    try:
        sub = df[t] if isinstance(df.columns, pd.MultiIndex) else df
        cols = [c for c in _OHLC if c in sub.columns]
        if "Close" not in cols:
            raise KeyError("Close")
        sub = sub[cols].rename(columns=_REN).dropna(subset=["close"])
        return sub.astype("float64") if not sub.empty else None
    except KeyError:
        log.warning("stock_ohlc[%s]: no data for %s", group, t)
        return None
