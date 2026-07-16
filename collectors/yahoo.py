"""Yahoo Finance collector via yfinance — unofficial API, replaceable by design.

Stores EOD adjusted close (+ volume) per ticker under data/yahoo/. Daily runs
fetch a short overlap window and upsert; backfill fetches max history.

Dual-basis store (W1.3):
- ``close``       — total-return (split+dividend adjusted) = Adj Close from yfinance
                    auto_adjust=False.  Byte-identical to the old auto_adjust=True Close.
- ``close_price`` — split-adjusted, dividend-UNadjusted = Close from yfinance
                    auto_adjust=False.  The correct basis for all structure math
                    (ZigZag, detrended osc, DCL/failed-cycle, drawdown-from-ATH).
For tickers where yfinance supplies no Adj Close (certain FX/index symbols), close_price
is set equal to close (no dividends → no basis difference) and the fact is logged.

Adjustment-basis guard: both stored bases are re-adjusted by Yahoo at every fetch,
so a 1mo window pulled after an ex-div/split disagrees with stored history on every
overlap date. ``store.basis_shifted`` detects that and the name is re-pulled
period='max' instead of spliced (see ``_rebase_shifted``).
"""
from __future__ import annotations

import logging
import time

import pandas as pd
import yfinance as yf

from collectors.base import Adapter
from lib import config, store

log = logging.getLogger(__name__)


class YahooAdapter(Adapter):
    name = "yahoo"
    group = "yahoo"

    def __init__(self) -> None:
        self.cfg = config.load()["yahoo"]

    def all_tickers(self) -> list[str]:
        out: list[str] = []
        for grp in self.cfg["tickers"].values():
            out.extend(grp)
        # stock_search.extra_tickers must be collected here or they can never be
        # searched (build_stock_library reads data/yahoo/<t>.parquet for them).
        # Skip ^-prefixed index symbols — they belong in the tickers groups.
        extra = config.load().get("stock_search", {}).get("extra_tickers", []) or []
        out.extend(t for t in extra if not str(t).startswith("^"))
        # W3 — Foresight Desk theme members: derive from config.themes at collect
        # time so future theme-member changes flow automatically (self-maintaining;
        # no separate list to keep in sync). foresight_grader._closes + the tape-
        # extension leg in foresight_score both require data/yahoo/<ticker>.parquet
        # for every theme member — without this, _theme_excess returns None and the
        # grading ledger stays pending forever.
        for theme in (config.load().get("themes") or {}).values():
            # (theme or {}): a bare `some_theme:` YAML key yields None — never crash collect
            for t in ((theme or {}).get("tickers") or []):
                if t and not str(t).startswith("^"):
                    out.append(t)
        return list(dict.fromkeys(out))

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        tickers = self.all_tickers()
        period = "max" if full_history else "1mo"
        # Keep intraday High/Low for the volatility group (^VIX etc.) — the daily
        # VIX wick (intraday high vs close) is a washout / thin-quote tell that
        # engine/dislocation.py reads. Everything else stays close+volume to avoid
        # churning ~1500 parquets.
        ohlc = set(self.cfg["tickers"].get("vol", []))
        frames: dict[str, pd.DataFrame] = {}
        no_adj_close: list[str] = []
        bs = self.cfg["batch_size"]
        for i in range(0, len(tickers), bs):
            batch = tickers[i:i + bs]
            df = self._download(batch, period)
            for t in batch:
                sub_out = self._extract(df, t, ohlc, no_adj_close)
                if sub_out is not None:
                    frames[t] = sub_out
        if no_adj_close:
            log.info("yahoo: %d tickers had no Adj Close (close_price=close, no dividends): %s",
                     len(no_adj_close), no_adj_close)
        deferred: list[str] = []
        if not full_history:
            deferred = self._rebase_shifted(frames, ohlc)
        # Stooq fallback for searchable single stocks Yahoo refused this run.
        # Basis-deferred names are NOT refilled: Stooq is a different source/basis,
        # so a refill would splice exactly what the guard just refused.
        extras = config.load().get("stock_search", {}).get("extra_tickers", []) or []
        self._fill_missing_extras(frames, [t for t in extras if t not in deferred])
        if len(frames) < len(tickers) * 0.7:
            raise RuntimeError(f"yahoo returned only {len(frames)}/{len(tickers)} tickers")
        return frames

    def _extract(self, df: pd.DataFrame, t: str, ohlc: set[str],
                 no_adj_close: list[str]) -> pd.DataFrame | None:
        """Slice one ticker out of a (possibly MultiIndex) yf.download response and
        rename to the store schema; None when yfinance returned nothing for it."""
        try:
            sub = df[t] if isinstance(df.columns, pd.MultiIndex) else df
            # W1.3 dual-basis rename:
            #   Adj Close -> close     (TR, byte-identical to old auto_adjust=True Close)
            #   Close     -> close_price (split-adj, div-UNadj — structure-math basis)
            # Vol/OHLC group also gets High/Low.
            if t in ohlc:
                want = ["High", "Low", "Close", "Adj Close", "Volume"]
            else:
                want = ["Close", "Adj Close", "Volume"]
            available = sub[[c for c in want if c in sub.columns]]
            if "Adj Close" in available.columns:
                renamed = available.rename(columns={
                    "Adj Close": "close",
                    "Close":     "close_price",
                    "Volume":    "volume",
                    "High":      "high",
                    "Low":       "low",
                })
            else:
                # FX / indices that yfinance provides no Adj Close for:
                # Close ≡ Adj Close (no dividends) → set close_price = close.
                no_adj_close.append(t)
                renamed = available.rename(columns={
                    "Close":  "close",
                    "Volume": "volume",
                    "High":   "high",
                    "Low":    "low",
                })
                if "close" in renamed.columns:
                    renamed["close_price"] = renamed["close"]
            sub_out = renamed.dropna(subset=["close"])
            return sub_out if not sub_out.empty else None
        except KeyError:
            log.warning("yahoo: no data for %s", t)
            return None

    def _rebase_shifted(self, frames: dict[str, pd.DataFrame],
                        ohlc: set[str]) -> list[str]:
        """Adjustment-basis guard (the odds-store pattern from scripts/build_odds).

        A name whose 1mo window disagrees with stored closes on the overlap dates
        was re-adjusted by Yahoo (ex-div/split) since the last pull; splicing the
        window would strand every pre-window row on the stale basis (measured on
        SPY: +0.2576% on all rows before 2026-05-18 — one dividend of drift; a
        missed split would be a 10x step). Flagged names are re-pulled
        period='max' so the whole store rebases in one shot. A name whose re-pull
        fails is DROPPED from this run — never spliced — leaving the store
        untouched so the guard re-flags it the next night. Returns the tickers
        dropped without a heal (the caller keeps them away from the Stooq refill)."""
        tol = float(self.cfg.get("upsert_basis_tol", 1e-3))
        shifted = [t for t, f in frames.items()
                   if store.basis_shifted(self.group, t, f, tol=tol)]
        if not shifted:
            return []
        log.info("yahoo: %d name(s) on a re-adjusted basis — refetching period='max': %s",
                 len(shifted), shifted[:12])
        for t in shifted:
            frames.pop(t, None)
        healed: list[str] = []
        scrap: list[str] = []  # no-Adj-Close names were already logged on the window pass
        bs = self.cfg["batch_size"]
        for i in range(0, len(shifted), bs):
            batch = shifted[i:i + bs]
            try:
                df = self._download(batch, "max")
            except Exception as e:  # noqa: BLE001 — degrade: skip tonight, re-flag next run
                log.warning("yahoo: basis refetch failed for %d name(s) (%s) — kept out "
                            "of this run; the guard retries next night", len(batch), e)
                continue
            for t in batch:
                sub_out = self._extract(df, t, ohlc, scrap)
                if sub_out is not None:
                    frames[t] = sub_out
                    healed.append(t)
        return [t for t in shifted if t not in healed]

    def _fill_missing_extras(self, frames: dict[str, pd.DataFrame],
                             extras: list[str]) -> dict[str, pd.DataFrame]:
        """Best-effort Stooq backfill for extra_tickers Yahoo returned no data for.

        Yahoo intermittently 404s live large-caps (e.g. Marsh MMC, Fiserv FI —
        served only under stale symbols); without a fallback they never reach the
        store and drop out of the library. Bounded to the extra_tickers set (plain
        US symbols Stooq's ``.us`` feed understands, not crypto/futures/indices)
        and never fatal — Stooq is IP-gated, so a block just leaves the name
        missing, no worse than before."""
        missing = [t for t in extras if not str(t).startswith("^") and t not in frames]
        if not missing:
            return frames
        from lib import stooq
        recovered = []
        for t in missing:
            s = stooq.stooq_daily(t)
            if s is not None and not s.empty:
                frames[t] = s
                recovered.append(t)
        if recovered:
            log.info("yahoo: Stooq fallback recovered %d name(s): %s", len(recovered), recovered)
        still = [t for t in missing if t not in frames]
        if still:
            log.warning("yahoo: no data from Yahoo or Stooq for %s", still)
        return frames

    def _download(self, batch: list[str], period: str) -> pd.DataFrame:
        last_exc: Exception | None = None
        for attempt in range(self.cfg["retries"]):
            try:
                # W1.3: auto_adjust=False returns BOTH Close (split-adj, div-UNadj)
                # AND Adj Close (split+div adjusted = TR).  The old auto_adjust=True
                # returned only an adjusted Close.  Switching to False + renaming
                # Adj Close→close keeps the stored ``close`` values byte-identical to
                # what was stored before this change (the invariance gate verified this
                # for SPY, EWJ, ^GSPC, and a FX pair with relative error < 1e-6).
                df = yf.download(batch, period=period, auto_adjust=False,
                                 progress=False, group_by="ticker", threads=True)
                if df is None or df.empty:
                    raise RuntimeError("empty yfinance response")
                return df
            except Exception as e:  # noqa: BLE001
                last_exc = e
                wait = self.cfg["backoff_base_s"] * (2 ** attempt)
                log.warning("yfinance batch failed (%s); retry in %.0fs", e, wait)
                time.sleep(wait)
        raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Store-level freshness tripwire (the check_cor_vol_freshness idiom from
# collectors/cboe_indices, VSB W1a). detect_stale_series (collectors/base) only
# inspects frames a fetch RETURNED, so a series NO adapter fetches is invisible
# to it. That is exactly how data/yahoo/_GSPC.parquet froze silently for a month
# (last obs 2026-06-12): ^GSPC was seeded once by a one-shot backtest script
# (scripts/spvector_baseline.py) and never entered any config["yahoo"]["tickers"]
# group, while eight engines kept reading it via store.read("yahoo", "^GSPC").
# The pinned list below is deliberately IN CODE, not derived from the config
# ticker groups — a config-derived expectation goes blind the moment a name
# falls out of the list, which is the failure class this tripwire guards.
# ---------------------------------------------------------------------------
ENGINE_CRITICAL_SERIES: tuple[str, ...] = (
    "^GSPC",   # US price-index benchmark: intl_performance RRG, cycle_proxies,
               # equity_alloc, financial_news, intl_claims, lab, live_overlay, signal_lab
    "SPY",     # master US total-return benchmark — engine.inputs features + many more
    "^VIX",    # vol-regime / dislocation OHLC substrate
)


def check_yahoo_freshness(max_lag_sessions: int = 3, min_rows: int = 1000) -> list[dict]:
    """NYSE-calendar freshness + row-floor check on the engine-critical yahoo names.

    Reads the STORE (not the fetch result) against the exchange calendar, so it
    fires no matter WHY a series stopped accruing: never in the ticker config
    (the ^GSPC failure), dropped from a group, breaker wedged, or upstream
    serving a frozen tail with 200-OK. Warn/alert only — it writes named
    run_status["stale_series"] entries and logs; it NEVER fails the lane."""
    from datetime import timedelta

    from collectors.base import _write_stale_series
    from lib import nyse_calendar

    expected = nyse_calendar.expected_last_session()
    problems: list[dict] = []
    for series in ENGINE_CRITICAL_SERIES:
        df = store.read("yahoo", series)
        rows = 0 if df is None else len(df)
        last = None if (df is None or df.empty) else pd.Timestamp(df.index.max()).date()
        lag = 0
        if last is not None:
            # sessions missing from the store: NYSE sessions in (last, expected]
            d = last + timedelta(days=1)
            while d <= expected and lag <= max_lag_sessions + 1:
                if nyse_calendar.is_session(d):
                    lag += 1
                d += timedelta(days=1)
        reason = None
        if df is None:
            reason = "missing from store"
        elif rows < min_rows:
            reason = f"row floor: {rows} < {min_rows} (stub re-seed)"
        elif lag > max_lag_sessions:
            reason = f"stale: last obs {last} is >{max_lag_sessions} sessions behind {expected}"
        if reason:
            entry = {"group": "yahoo", "series": series, "rows": rows,
                     "last_obs": str(last) if last else None,
                     "cadence_days": 1,
                     "age_days": (expected - last).days if last else None,
                     "reason": reason}
            problems.append(entry)
            log.warning("yahoo freshness: %s — %s", series, reason)
    if problems:
        _write_stale_series(problems)
    else:
        log.info("yahoo freshness: all %d engine-critical series fresh "
                 "(last expected session %s)", len(ENGINE_CRITICAL_SERIES), expected)
    return problems
