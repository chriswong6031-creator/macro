"""Hong Kong market valuation — the currency-neutral PE/PB read hk_fundamentals
deliberately skipped.

collectors/hk_fundamentals.py refuses to compute PE/PB because many HK names report
financials in CNY while the price/target are in HKD (a CNY EPS over an HKD price is a
broken ratio). This collector sidesteps that entirely: it pulls Baidu's pre-computed,
single-currency valuation time series per name, so there is no cross-currency mixing.

SOURCE (keyless, via akshare 1.18.x):
  ak.stock_hk_valuation_baidu(symbol=<5-digit zero-padded HK code, e.g. "00700">,
                              indicator=<"市盈率(TTM)"|"市净率"|"股息率"|"总市值">,
                              period="近一年"|"全部")
    -> a two-column daily frame (date, value) per name+indicator, ~1y by default,
       deep history (2004->) when period="全部".

We aggregate a CURATED set of the largest HSI constituents (config hk.valuation.names,
falling back to a built-in big-cap default; symbols sourced from config hk.names keys)
into a daily MARKET-MEDIAN valuation series — robust to the inevitable per-name gaps.

GOTCHAS (live-verified 2026-06-17):
  - SYMBOL FORMAT: Baidu wants the 5-digit zero-padded bare code ("00700"), not the
    "0700.HK" form config uses. Same normaliser as hk_fundamentals.ak_symbol.
  - akshare raises ConnectionError / RemoteDisconnected (not HTTP codes), so every
    akshare call is wrapped in an explicit retry loop with exponential backoff.
  - 股息率 (dividend yield) is NOT one of akshare's documented indicators for this
    endpoint and currently returns no chart for the names probed -> the wrapper raises
    a TypeError ("'NoneType' object is not subscriptable"). We still request it (so it
    flows through if Baidu ever serves it) but treat its absence as normal: the median
    frame simply omits div_yield when nothing resolves. PE/PB are the load-bearing legs.
  - per-NAME and per-INDICATOR isolation: one broken name/indicator logs a warning and
    the rest proceed. We only raise (so the breaker can act) when NOTHING resolves.

Display-only / regime-context: degrades to absent, never feeds a scored leg.

Stored under group `hk_valuation`:
  median   daily market-median across the curated cohort
           columns: pe, pb[, div_yield], n_pe, n_pb (cohort coverage counts)
  by_name  one appended row per run = latest per-name snapshot
           columns: <code>_pe, <code>_pb[, <code>_dy] (e.g. 00700_pe)
"""
from __future__ import annotations

import logging
import time
from datetime import date

import akshare as ak
import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

# stored metric -> Baidu indicator label
_INDICATORS = {
    "pe": "市盈率(TTM)",
    "pb": "市净率",
    "div_yield": "股息率",   # often unavailable from this endpoint; per-series isolated
}

# default curated cohort: the largest / most-liquid HSI constituents (all present in
# config hk.names as of 2026-06). Overridable via config hk.valuation.names.
_DEFAULT_NAMES = [
    "0700.HK", "9988.HK", "3690.HK", "9618.HK", "1810.HK", "9888.HK", "9999.HK",
    "0981.HK", "1398.HK", "0939.HK", "3988.HK", "0005.HK", "2318.HK", "1299.HK",
    "2628.HK", "0883.HK", "0857.HK", "1088.HK", "0016.HK", "1109.HK", "1211.HK",
    "0941.HK", "0388.HK", "0001.HK", "0002.HK", "0003.HK", "0011.HK", "0066.HK",
    "2020.HK", "0027.HK",
]


def _ak_symbol(ticker: str) -> str:
    """0700.HK -> 00700 (Baidu / akshare 5-digit zero-padded HK code)."""
    return ticker.split(".")[0].zfill(5)


class HkValuationAdapter(Adapter):
    name = "hk_valuation"
    group = "hk_valuation"
    stale_after_days = 8   # daily Baidu series; tolerate HK holidays + Baidu hiccups

    def __init__(self) -> None:
        cfg = config.load().get("hk", {}).get("valuation", {}) or {}
        names = config.load().get("hk", {}).get("names", {}) or {}
        want = cfg.get("names") or _DEFAULT_NAMES
        # keep only tickers config actually knows about (defensive); preserve order
        self.tickers = [t for t in want if t in names] or list(want)
        self.retries = int(cfg.get("retries", 3))
        self.backoff_base = float(cfg.get("backoff_base_s", 3.0))

    # -- one akshare call, wrapped in the retry loop --------------------------
    def _series(self, sym: str, indicator: str, period: str) -> pd.Series | None:
        """Return a date-indexed numeric Series for one name+indicator, or None.

        akshare raises ConnectionError/RemoteDisconnected (not HTTP codes); retry with
        backoff. A TypeError/KeyError means Baidu served no chart for this query
        (e.g. 股息率) — that is a data-level miss, not a transport fault: return None
        rather than burning the whole retry budget on it."""
        for attempt in range(self.retries):
            try:
                raw = ak.stock_hk_valuation_baidu(symbol=sym, indicator=indicator,
                                                  period=period)
                if raw is None or raw.empty or "value" not in raw.columns:
                    return None
                s = pd.Series(
                    pd.to_numeric(raw["value"], errors="coerce").to_numpy(),
                    index=pd.to_datetime(raw["date"]),
                )
                s = s[s > 0].dropna().sort_index()   # PE/PB/yield are strictly positive
                return s if not s.empty else None
            except (TypeError, KeyError, IndexError):
                # Baidu returned no usable chart for this name/indicator -> miss, no retry
                return None
            except Exception as e:  # noqa: BLE001 — transport flake: retry then surface
                if attempt == self.retries - 1:
                    raise
                time.sleep(self.backoff_base * (2 ** attempt))
        return None

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        period = "全部" if full_history else "近一年"
        # metric -> DataFrame(date x ticker) of per-name series
        wide: dict[str, pd.DataFrame] = {m: pd.DataFrame() for m in _INDICATORS}
        latest: dict[str, dict] = {}   # ticker -> {pe, pb, dy}
        errors: list[str] = []
        ok_names = 0

        for ticker in self.tickers:
            sym = _ak_symbol(ticker)
            got_any = False
            for metric, indicator in _INDICATORS.items():
                try:
                    s = self._series(sym, indicator, period)
                except Exception as e:  # noqa: BLE001 — per-name/indicator isolation
                    errors.append(f"{ticker}/{metric}: {e}")
                    log.warning("hk_valuation %s %s failed: %s", ticker, metric, e)
                    continue
                if s is None:
                    continue
                wide[metric][sym] = s
                got_any = True
                # latest snapshot value for the by_name frame
                key = {"pe": "pe", "pb": "pb", "div_yield": "dy"}[metric]
                latest.setdefault(sym, {})[key] = round(float(s.iloc[-1]), 4)
            if got_any:
                ok_names += 1

        # -- median frame: collapse each metric's wide frame to its daily median ----
        med = pd.DataFrame()
        for metric, df in wide.items():
            if df.empty:
                continue
            med[metric] = df.median(axis=1, skipna=True)
            if metric in ("pe", "pb"):
                med[f"n_{metric}"] = df.notna().sum(axis=1).astype(float)
        if not med.empty:
            med = med.dropna(how="all").sort_index()

        frames: dict[str, pd.DataFrame] = {}
        if not med.empty:
            frames["median"] = med

        # -- by_name frame: one appended row (today) of the latest per-name snapshot -
        if latest:
            # tz-NAIVE to match the median frame + validate()/upsert() normalize
            # convention (run_adapter compares max-dates across frames); matches the
            # sibling accrue-forward idiom (china_flows / hk_ah_official) — no deprecated utcnow
            asof = pd.Timestamp(date.today())
            row: dict[str, float] = {}
            for sym, vals in latest.items():
                for k, v in vals.items():
                    row[f"{sym}_{k}"] = v
            if row:
                frames["by_name"] = pd.DataFrame([row], index=[asof])

        if not frames:
            raise RuntimeError(
                "hk_valuation: no series resolved for any name — "
                + (" | ".join(errors[:6]) if errors else "all empty"))
        log.info("hk_valuation: %d/%d names ok, median rows=%d, by_name cols=%d",
                 ok_names, len(self.tickers),
                 len(frames.get("median", [])),
                 frames.get("by_name", pd.DataFrame()).shape[1])
        return frames
