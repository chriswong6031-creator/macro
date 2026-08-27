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
        sub = _drop_non_trading_placeholders(sub)
        sub = _drop_invalid_ohlc(sub)
        return sub.astype("float64") if not sub.empty else None
    except KeyError:
        log.warning("stock_ohlc[%s]: no data for %s", group, t)
        return None


def _drop_non_trading_placeholders(df: pd.DataFrame) -> pd.DataFrame:
    """Remove Yahoo's zero-volume flat rows without guessing from missing data.

    Suspended China/Hong Kong names can receive a synthetic daily row whose OHLC all
    repeat the prior close and whose volume is exactly zero. That row is not a market
    session. Require close/high/low plus an explicit non-positive volume before
    excluding it; a missing volume or a positive-volume flat session remains honest.
    """
    required = {"close", "high", "low", "volume"}
    if not required.issubset(df.columns):
        return df
    price_cols = [c for c in ("open", "close", "high", "low") if c in df.columns]
    prices = df[price_cols]
    finite_prices = prices.notna().all(axis=1)
    close = df["close"]
    tolerance = close.abs() * 1e-10 + 1e-8
    flat = prices.sub(close, axis=0).abs().le(tolerance, axis=0).all(axis=1)
    explicit_zero_volume = df["volume"].notna() & df["volume"].le(0)
    return df.loc[~(finite_prices & flat & explicit_zero_volume)]


def _drop_invalid_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """Remove bars whose CLOSE sits outside the session's own ``[low, high]`` range.

    A close outside the day's range is arithmetically impossible, so the bar is not a
    session — it is stitched. Yahoo emits one for an A-share RESUMING from suspension:
    open/high/low stay frozen on the last traded session while close jumps to the
    resumption print. Measured on 002155.SZ (Hunan Gold) 2026-08-27, the session it
    reopened after a five-day halt: ``o/h/l = 24.48/25.39/24.20`` carried over from
    2026-08-14/08-19 against ``close = 27.02``, the +10% limit — a close 6.4% ABOVE the
    bar's own high. ``_drop_non_trading_placeholders`` cannot see it (volume is real and
    the prices are not flat), so without this the resumption bar lands in the store and
    every range-derived reader — limit-up/gap detection above all — reads a nonsense day.

    Guarded on CLOSE, plus an inverted ``high < low``. ``open`` is deliberately NOT
    checked: Yahoo serves a provisional open intraday that settles after the close, so an
    open briefly outside the band is a timing artifact rather than corruption — 574 of
    1,861 CN names carried one for 2026-08-26 and every sampled name self-corrected on a
    later pull, so dropping those bars would discard real sessions for a third of the
    universe. Sizing on the committed stores: the close rule excludes 673/6,832,040 CN
    rows (0.0099%, over half of them one bad Yahoo day, 2024-03-29) and 0 of the
    2,279,395 US ``data/stocks`` rows — the invariant already holds wherever the feed is
    clean. A dropped date is left ABSENT rather than repaired; ``upsert`` is incremental,
    so a later corrected pull fills it in (``overwrite_overlap`` owns its whole span).

    Fail-open on missing data, matching the placeholder guard: a NaN in close/high/low
    is not evidence of corruption and leaves the row alone.
    """
    required = {"close", "high", "low"}
    if not required.issubset(df.columns):
        return df
    close, high, low = df["close"], df["high"], df["low"]
    known = close.notna() & high.notna() & low.notna()
    tolerance = close.abs() * 1e-9 + 1e-8
    outside_band = (close > high + tolerance) | (close < low - tolerance)
    inverted_range = high < low - tolerance
    return df.loc[~(known & (outside_band | inverted_range))]
