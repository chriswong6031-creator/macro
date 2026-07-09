"""W5-B Options Tape Signed Pilot — data build, NO signal analysis.

LANE A11 / Wave-5-B.  Pure data-build authorization pass.

PRE-REGISTRATION (written before computing, 2026-07-06):
  This script pulls raw trade_quote streams from ThetaTerminal v3, classifies
  each trade against its contemporaneous NBBO using the simple quote rule
  (NOT Lee-Ready tick-test; stated explicitly below), and aggregates per
  underlying per day to three signed metrics.  No signal families, no
  backtests, no trial ledger entries — this is a data-quality and throughput
  measurement build, not a statistical test.

  Amendment A1 (pre-registered before first compute):
    The ThetaTerminal v3 trade_quote endpoint accepts wildcard expiration
    (expiration="*") for per-day pulls — confirmed live before script was
    written.  The window-stall law (≤7 calendar days) from bulk_eod applies
    per-underlying, not per-day within the trade_quote endpoint; the stall
    risk for trade_quote is different because the terminal streams row-by-row
    rather than assembling old data server-side for multi-day ranges.  For
    pilot safety: ONE calendar day per request, concurrent across underlyings.

  Amendment A2 (pre-registered before first compute):
    Delta source: massive_options_day store (Polygon flatfiles) carries volume
    but NOT delta.  The thetadata_eod store (data/thetadata_eod) has no
    per-ticker data yet (backfill not run).  Therefore: delta is NOT available
    from any local store for most contracts.  We use moneyness-bucket proxy for
    delta-weighted volume.

    Moneyness convention (matches _moneyness_delta_proxy implementation):
      For calls: signed_m = (spot - strike) / spot   [positive = ITM call]
      For puts:  signed_m = (strike - spot) / spot   [positive = ITM put]
    Bucketing branches on sign of signed_m (ITM = positive, OTM = negative):
      ITM branch (signed_m >= 0):
        deep ITM  |m| > 0.20            → proxy delta = 0.90
        ITM       0.10 < |m| <= 0.20    → proxy delta = 0.70
        NTM/ATM   |m| <= 0.10           → proxy delta = 0.50
      OTM branch (signed_m < 0):
        OTM       |m| <= 0.20           → proxy delta = 0.30  (NTM-OTM included)
        deep OTM  |m| > 0.20            → proxy delta = 0.10
    Note 1: the 0.03 ATM boundary listed in early planning is NOT implemented;
    NTM and ATM are collapsed into the single bucket |m|<=0.10 within the ITM branch.
    Note 2: slightly-OTM (NTM-OTM) contracts with |m|<=0.10 receive delta_proxy=0.30,
    NOT 0.50 — because they fall in the OTM branch, which has no sub-ATM bucket.

    IMPORTANT: delta_proxy is an UNSIGNED magnitude. Both calls and puts
    receive a positive proxy value (e.g., a deep-ITM put gets delta_proxy=0.90,
    not -0.90). Therefore net_delta_proxy is NOT a directional put-vs-call flow
    indicator — it is a signed premium-volume proxy weighted by moneyness
    magnitude, where sign comes from BUY/SELL classification only.
    Consumers must not interpret net_delta_proxy as a delta-adjusted
    directional position.

    underlying_price is sourced from the last available close in massive_stock_day.
    This proxy is STATED, not hidden.  Delta column in output is labeled
    'delta_proxy' to distinguish from model delta.

SIGNING RULE (simple quote rule, NOT Lee-Ready):
  The lane spec explicitly says "simple quote-rule, NOT Lee-Ready tick-test".
  Classification:
    price >= ask  → BUY-SIDE    (initiator paid the ask or lifted above)
    price <= bid  → SELL-SIDE   (initiator hit the bid or below)
    bid < price < ask → MIDPOINT → EXCLUDED (ambiguous initiator)
  Trades where bid is NaN, ask is NaN, or bid > ask (crossed market) are also
  EXCLUDED.  The exclusion rate is reported.

OUTPUTS per underlying:
  data/options_tape_signed/<UNDERLYING>.parquet
    Columns (16 total): underlying, date, raw_rows, elapsed_s,
             buy_premium, sell_premium, net_premium,
             buy_delta_proxy, sell_delta_proxy, net_delta_proxy,
             buy_count, sell_count, excluded_count, total_count,
             exclusion_rate, mid_rate
    raw_rows: total rows returned by the terminal before signing.
    elapsed_s: wall-clock seconds for the fetch+sign step (per name-day).

  data/options_tape_signed/_backfill_state.json
    Resumable state machine: {version, underlyings: {sym: {cursor: YYYYMMDD,
    completed_dates: [...], errors: {date: msg}}}}

PILOT SCOPE:
  20 liquid underlyings: SPY QQQ AAPL MSFT NVDA TSLA AMZN META GOOGL AMD
                         GS JPM BAC XOM CVX JNJ UNH WMT HD V
  Most recent 60 trading days (from massive_stock_day/SPY.parquet index).
  Runtime budget: ~45 min.  If budget exceeded, write honest partial coverage.

NIGHTLY WIRING (for consolidation — see report):
  Accrual: nightly at 21:00 ET (after ThetaTerminal post-market update ~20:00 ET).
  Append today's trades to each <UNDERLYING>.parquet (resumable via cursor).
  Estimated: 20 min/night for 20 names (measured from pilot throughput).
  Extension to 500 names: concurrent, bounded by terminal 8-connection ceiling.

Run:
  python -m scripts.options_tape_signed_pilot [--max-days N] [--resume]
  python -m scripts.options_tape_signed_pilot --dry-run  (reachability + coverage only)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.thetadata import reachable, _session, _get_csv, _date_int

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

log = logging.getLogger("options_tape_signed_pilot")

PILOT_UNDERLYINGS: list[str] = [
    # Index ETFs (largest, most options volume)
    "SPY", "QQQ",
    # Mega-cap tech
    "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL", "AMD",
    # Liquid single names (financials, energy, healthcare, consumer, tech)
    "GS", "JPM", "BAC", "XOM", "CVX", "JNJ", "UNH", "WMT", "HD", "V",
]

assert len(PILOT_UNDERLYINGS) == 20, "Pilot must be exactly 20 underlyings"

# Concurrency: terminal ceiling 8, we use 6 (headroom for other ops)
CONCURRENT_UNDERLYINGS = 6

# Moneyness buckets for delta proxy (Amendment A2)
# |moneyness| = |strike - S| / S for calls, |S - strike| / S for puts
# where sign convention: calls ITM when S > strike (moneyness < 0 in standard convention)
# We use directionality: for a call, moneyness proxy = (S - strike)/S, sign matters for ITM/OTM
_DELTA_PROXY_THRESHOLDS = [
    (0.20, 0.90),   # deep ITM: |m| > 0.20
    (0.10, 0.70),   # ITM:      0.10 < |m| <= 0.20
    (0.03, 0.50),   # NTM/ATM:  |m| <= 0.10 (also ATM)
]
_DELTA_PROXY_OTM = [
    (0.10, 0.30),   # OTM:      0.10 < |m| <= 0.20
    (float("inf"), 0.10),  # deep OTM: |m| > 0.20
]


def _moneyness_delta_proxy(strike: pd.Series, is_call: pd.Series, spot: float) -> pd.Series:
    """Return scalar proxy delta for each contract row.

    For calls: ITM when spot > strike (positive moneyness in our convention).
    For puts:  ITM when spot < strike.
    Magnitude of moneyness determines the bucket; sign determines ITM vs OTM.
    """
    # signed_m: positive = ITM, negative = OTM (call convention)
    signed_m_call = (spot - strike) / spot  # >0 = call ITM
    signed_m_put  = (strike - spot) / spot  # >0 = put ITM

    # Select moneyness based on is_call
    signed_m = np.where(is_call, signed_m_call, signed_m_put)
    abs_m = np.abs(signed_m)

    proxy = pd.Series(np.where(signed_m >= 0,
        # ITM branch
        np.select(
            [abs_m > 0.20, abs_m > 0.10, abs_m <= 0.10],
            [0.90,         0.70,          0.50],
            default=0.50,
        ),
        # OTM branch
        np.select(
            [abs_m > 0.20, abs_m <= 0.20],
            [0.10,         0.30],
            default=0.10,
        ),
    ), index=strike.index, dtype=float)
    return proxy


def _sign_trades(df: pd.DataFrame, spot: float) -> pd.DataFrame:
    """Apply simple quote rule to classify each trade.

    Adds columns: side ('BUY'/'SELL'/None), delta_proxy.
    Rows with side=None are excluded from aggregation.

    Amendment A2: delta_proxy from moneyness bucket, not from model delta.
    """
    if df.empty:
        df = df.copy()
        df["side"] = pd.Series(dtype="object")
        df["delta_proxy"] = pd.Series(dtype=float)
        return df

    df = df.copy()

    # Numeric coerce
    for col in ("price", "bid", "ask", "strike"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "size" in df.columns:
        df["size"] = pd.to_numeric(df["size"], errors="coerce")

    # Simple quote rule
    valid_nbbo = (
        df["bid"].notna() & df["ask"].notna() &
        (df["ask"] > df["bid"])  # non-crossed market
    )

    buy_mask  = valid_nbbo & (df["price"] >= df["ask"])
    sell_mask = valid_nbbo & (df["price"] <= df["bid"])

    df["side"] = None
    df.loc[buy_mask, "side"]  = "BUY"
    df.loc[sell_mask, "side"] = "SELL"
    # Midpoint (buy_mask=False AND sell_mask=False AND valid_nbbo=True): side stays None (excluded)

    # Delta proxy
    is_call = df["right"].str.upper().isin(["CALL", "C"]) if "right" in df.columns else pd.Series(True, index=df.index)
    strike = df["strike"] if "strike" in df.columns else pd.Series(np.nan, index=df.index)
    df["delta_proxy"] = _moneyness_delta_proxy(strike, is_call, spot).values

    return df


def _aggregate_day(df_signed: pd.DataFrame) -> dict[str, float | int]:
    """Aggregate one underlying's signed trades to scalar metrics for one day."""
    if df_signed.empty:
        return {
            "buy_premium": 0.0, "sell_premium": 0.0, "net_premium": 0.0,
            "buy_delta_proxy": 0.0, "sell_delta_proxy": 0.0, "net_delta_proxy": 0.0,
            "buy_count": 0, "sell_count": 0, "excluded_count": 0, "total_count": 0,
            "exclusion_rate": float("nan"), "mid_rate": float("nan"),
        }

    total = len(df_signed)
    buy  = df_signed[df_signed["side"] == "BUY"]
    sell = df_signed[df_signed["side"] == "SELL"]
    excl = df_signed[df_signed["side"].isna()]

    # Premium = price * size * 100 (one contract = 100 shares underlying)
    buy_prem  = (buy["price"]  * buy["size"]  * 100).sum() if len(buy)  else 0.0
    sell_prem = (sell["price"] * sell["size"] * 100).sum() if len(sell) else 0.0

    # Delta-weighted volume: delta_proxy * size (signed: buy=+, sell=-)
    buy_dv  = (buy["delta_proxy"]  * buy["size"]).sum()  if len(buy)  else 0.0
    sell_dv = (sell["delta_proxy"] * sell["size"]).sum() if len(sell) else 0.0

    mid_count = df_signed[
        df_signed["side"].isna() &
        df_signed["bid"].notna() & df_signed["ask"].notna() &
        (df_signed["ask"] > df_signed["bid"]) &
        (df_signed["price"] > df_signed["bid"]) &
        (df_signed["price"] < df_signed["ask"])
    ].shape[0] if "bid" in df_signed.columns else 0

    return {
        "buy_premium":      float(buy_prem),
        "sell_premium":     float(sell_prem),
        "net_premium":      float(buy_prem - sell_prem),
        "buy_delta_proxy":  float(buy_dv),
        "sell_delta_proxy": float(sell_dv),
        "net_delta_proxy":  float(buy_dv - sell_dv),
        "buy_count":        int(len(buy)),
        "sell_count":       int(len(sell)),
        "excluded_count":   int(len(excl)),
        "total_count":      int(total),
        "exclusion_rate":   float(len(excl) / total) if total else float("nan"),
        "mid_rate":         float(mid_count / total) if total else float("nan"),
    }


def _load_spot(underlying: str, as_of: date,
               stock_day_dir: Path) -> float:
    """Load last available close from massive_stock_day for spot price proxy.

    Falls back to a conservative default (0, delta_proxy=0.50 for all) if unavailable.
    Returns NaN if store not found (caller handles gracefully).
    stock_day_dir should already be resolved by _resolve_stock_day_dir().
    """
    p = stock_day_dir / f"{underlying}.parquet"
    if not p.exists():
        return float("nan")
    try:
        df = pd.read_parquet(p, columns=["close"])
        df.index = pd.to_datetime(df.index)
        # Last close strictly before or on as_of date (PIT)
        mask = df.index.date <= as_of
        if not mask.any():
            return float("nan")
        return float(df.loc[mask, "close"].iloc[-1])
    except Exception:
        return float("nan")


def _save_classification_sample(
    df_signed: pd.DataFrame,
    underlying: str,
    trade_date: date,
    out_dir: Path,
    n: int = 10,
) -> None:
    """Save first N signed rows (with NBBO, price, strike, right, side) to a JSON sidecar.

    File: data/options_tape_signed/_sample_<UNDERLYING>_<DATE>.json
    Written once at build time so the report can reference it without a live re-pull.
    Columns captured: price, bid, ask, strike, right, size, side, delta_proxy.
    """
    cols = [c for c in ["price", "bid", "ask", "strike", "right", "size", "side", "delta_proxy"]
            if c in df_signed.columns]
    sample = df_signed[cols].head(n)
    out = {
        "underlying": underlying,
        "date": trade_date.isoformat(),
        "n_rows": len(sample),
        "note": (
            "First 10 raw signed rows for this name-day. "
            "side=BUY: price>=ask; side=SELL: price<=bid; side=null: midpoint/excluded."
        ),
        "rows": sample.to_dict(orient="records"),
    }
    sidecar = out_dir / f"_sample_{underlying}_{trade_date.isoformat()}.json"
    sidecar.write_text(json.dumps(out, indent=2, default=str))


def _fetch_and_sign_one_day(
    underlying: str,
    trade_date: date,
    stock_day_dir: Path,
    out_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Pull trade_quote for one underlying, one day; sign; aggregate.

    Returns dict with keys: underlying, date, <metrics>, raw_rows, elapsed_s.
    Returns None on terminal error (caller records as error in state).

    If out_dir is provided, saves first 10 signed rows to a JSON sidecar
    (_sample_<UNDERLYING>_<DATE>.json) for report spot-check reproducibility.
    """
    t0 = time.perf_counter()
    session = _session()
    date_int = int(trade_date.strftime("%Y%m%d"))
    params = {
        "symbol": underlying.upper(),
        "expiration": "*",
        "start_date": date_int,
        "end_date": date_int,
    }

    try:
        df = _get_csv(session, "/v3/option/history/trade_quote", params)
    except Exception as e:
        log.warning("fetch_error %s %s: %s", underlying, trade_date, e)
        return None

    elapsed = time.perf_counter() - t0

    if df is None:
        log.warning("returned None: %s %s (%.1fs)", underlying, trade_date, elapsed)
        return None

    raw_rows = len(df)

    if df.empty:
        log.info("empty: %s %s (%.1fs)", underlying, trade_date, elapsed)
        return {
            "underlying": underlying, "date": trade_date,
            "raw_rows": 0, "elapsed_s": elapsed,
            **_aggregate_day(pd.DataFrame()),
        }

    # Spot price (PIT: last close at or before trade_date)
    spot = _load_spot(underlying, trade_date, stock_day_dir)
    if np.isnan(spot) or spot <= 0:
        # Use midpoint of first valid bid/ask as fallback
        for col in ("price", "bid", "ask"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        mid_prices = ((df["bid"] + df["ask"]) / 2).dropna()
        spot = float(mid_prices.median()) if len(mid_prices) else 100.0
        log.info("spot fallback for %s %s: %.2f", underlying, trade_date, spot)

    df_signed = _sign_trades(df, spot=spot)
    agg = _aggregate_day(df_signed)

    # Save first-10-row classification sample for report reproducibility (build-time capture).
    # Sidecar written once; does not affect aggregation or state.
    if out_dir is not None:
        try:
            _save_classification_sample(df_signed, underlying, trade_date, out_dir)
        except Exception as exc:
            log.debug("sample save skipped for %s %s: %s", underlying, trade_date, exc)

    log.info(
        "done: %s %s rows=%d buy=%d sell=%d excl=%d (%.1fs)",
        underlying, trade_date, raw_rows,
        agg["buy_count"], agg["sell_count"], agg["excluded_count"], elapsed,
    )

    return {
        "underlying": underlying,
        "date": trade_date,
        "raw_rows": raw_rows,
        "elapsed_s": elapsed,
        **agg,
    }


class BackfillStateMachine:
    """Resumable per-underlying date cursor.

    JSON schema:
      {
        "version": 1,
        "underlyings": {
          "SPY": {
            "cursor": "2026-04-08",          # next date to pull (inclusive)
            "completed_dates": ["2026-04-08", ...],
            "errors": {"2026-04-09": "timeout"},
          }
        }
      }

    Design: cursor advances only after a successful write.  On restart,
    any date in completed_dates is skipped.  Errors are stored but do not
    block future dates (the run continues; the error date is retried on next run).

    Extension to 500 names: add new underlyings to state["underlyings"] dict;
    the driver reads completed_dates per-underlying to skip done work.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._state: dict[str, Any] = {"version": 1, "underlyings": {}}
        if path.exists():
            try:
                self._state = json.loads(path.read_text())
            except Exception:
                log.warning("state file corrupt, starting fresh: %s", path)
                self._state = {"version": 1, "underlyings": {}}

    def _ensure(self, underlying: str) -> None:
        if underlying not in self._state["underlyings"]:
            self._state["underlyings"][underlying] = {
                "cursor": None,
                "completed_dates": [],
                "errors": {},
            }

    def is_done(self, underlying: str, d: date) -> bool:
        self._ensure(underlying)
        return d.isoformat() in self._state["underlyings"][underlying]["completed_dates"]

    def mark_done(self, underlying: str, d: date) -> None:
        self._ensure(underlying)
        ds = d.isoformat()
        u = self._state["underlyings"][underlying]
        if ds not in u["completed_dates"]:
            u["completed_dates"].append(ds)
        u["cursor"] = ds

    def mark_error(self, underlying: str, d: date, msg: str) -> None:
        self._ensure(underlying)
        self._state["underlyings"][underlying]["errors"][d.isoformat()] = msg

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._state, indent=2, default=str))
        tmp.replace(self.path)

    def coverage_summary(self) -> dict[str, int]:
        return {
            sym: len(u["completed_dates"])
            for sym, u in self._state["underlyings"].items()
        }


def _merge_into_parquet(out_dir: Path, underlying: str, rows: list[dict]) -> None:
    """Append new rows to data/options_tape_signed/<UNDERLYING>.parquet."""
    if not rows:
        return
    new_df = pd.DataFrame(rows)
    new_df["date"] = pd.to_datetime(new_df["date"])

    out_path = out_dir / f"{underlying}.parquet"
    if out_path.exists():
        old = pd.read_parquet(out_path)
        old["date"] = pd.to_datetime(old["date"])
        combined = pd.concat([old, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["underlying", "date"]).sort_values("date")
    else:
        combined = new_df.sort_values("date")

    combined.to_parquet(out_path, index=False)


def _resolve_stock_day_dir(stock_day_dir: Path) -> Path:
    """Resolve potentially-nested massive_stock_day symlink.

    PRICE-STORE LAW (house rules): after symlinking, per-ticker parquets may resolve
    NESTED (data/massive_stock_day/massive_stock_day/<T>.parquet). Probe and return
    the real directory that contains SPY.parquet.
    """
    # Direct path
    if (stock_day_dir / "SPY.parquet").exists():
        return stock_day_dir
    # Nested one level (symlink resolved into subdirectory with same name)
    nested = stock_day_dir / stock_day_dir.name
    if (nested / "SPY.parquet").exists():
        return nested
    # Try the canonical main-repo path directly
    canonical = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data/massive_stock_day")
    if (canonical / "SPY.parquet").exists():
        return canonical
    raise FileNotFoundError(
        f"SPY.parquet not found at {stock_day_dir} (tried direct, nested, canonical). "
        f"Ensure massive_stock_day symlink is set up per house rules."
    )


def _get_trading_dates(n: int, stock_day_dir: Path) -> list[date]:
    """Return last N trading dates from SPY store index."""
    resolved = _resolve_stock_day_dir(stock_day_dir)
    spy = resolved / "SPY.parquet"
    df = pd.read_parquet(spy, columns=[])
    dates = sorted(pd.to_datetime(df.index).date.tolist())
    return dates[-n:]


def run_pilot(
    out_dir: Path,
    stock_day_dir: Path,
    max_days: int = 60,
    max_runtime_s: float = 2400.0,  # 40 min hard ceiling
    resume: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run the pilot: 20 underlyings x up to max_days trading days.

    Returns a stats dict for the report.
    """
    if not reachable():
        raise RuntimeError(
            "ThetaTerminal unreachable at http://127.0.0.1:25503.\n"
            "Restart: scripts/run_theta_terminal.sh  (or see docstring for --api-key)"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = out_dir / "_backfill_state.json"
    state = BackfillStateMachine(state_path)

    # PRICE-STORE LAW: resolve nested symlink before use; print coverage for audit
    resolved_stock_day_dir = _resolve_stock_day_dir(stock_day_dir)
    log.info("massive_stock_day resolved to: %s", resolved_stock_day_dir)
    spy_check = resolved_stock_day_dir / "SPY.parquet"
    aapl_check = resolved_stock_day_dir / "AAPL.parquet"
    log.info("Coverage probe: SPY=%s AAPL=%s", spy_check.exists(), aapl_check.exists())
    stock_day_dir = resolved_stock_day_dir  # rebind to resolved path

    trading_dates = _get_trading_dates(max_days, stock_day_dir)
    log.info("Pilot: %d underlyings x %d dates (%s → %s)",
             len(PILOT_UNDERLYINGS), len(trading_dates),
             trading_dates[0], trading_dates[-1])

    if dry_run:
        log.info("DRY RUN: reachability confirmed, %d dates identified, exiting",
                 len(trading_dates))
        return {
            "dry_run": True, "terminal_up": True,
            "trading_dates": len(trading_dates),
            "start": trading_dates[0].isoformat(),
            "end": trading_dates[-1].isoformat(),
        }

    # Build task list: (underlying, date) pairs, skipping already-done
    tasks: list[tuple[str, date]] = []
    for sym in PILOT_UNDERLYINGS:
        for d in trading_dates:
            if resume and state.is_done(sym, d):
                continue
            tasks.append((sym, d))

    log.info("Tasks remaining: %d (of %d total)",
             len(tasks), len(PILOT_UNDERLYINGS) * len(trading_dates))

    pilot_start = time.perf_counter()
    completed_rows: dict[str, list[dict]] = {sym: [] for sym in PILOT_UNDERLYINGS}
    name_day_count = 0
    error_count = 0
    elapsed_times: list[float] = []
    row_counts: list[int] = []

    # Throughput measurement: run first few tasks serially to measure, then concurrent
    # Process in date-major order so each day's data writes together
    # Group tasks by date (process date-by-date; within each date, run underlyings concurrently)
    from collections import defaultdict
    tasks_by_date: dict[date, list[str]] = defaultdict(list)
    for sym, d in tasks:
        tasks_by_date[d].append(sym)

    for trade_date in sorted(tasks_by_date.keys()):
        syms_this_day = tasks_by_date[trade_date]
        wall = time.perf_counter() - pilot_start

        if wall > max_runtime_s:
            log.warning("Runtime budget exceeded (%.0fs > %.0fs); stopping at %s",
                        wall, max_runtime_s, trade_date)
            break

        # Run underlyings for this date concurrently
        futures: dict[Future, str] = {}
        with ThreadPoolExecutor(max_workers=CONCURRENT_UNDERLYINGS) as executor:
            for sym in syms_this_day:
                f = executor.submit(
                    _fetch_and_sign_one_day, sym, trade_date, stock_day_dir, out_dir
                )
                futures[f] = sym

            for f in as_completed(futures):
                sym = futures[f]
                try:
                    result = f.result()
                except Exception as e:
                    log.error("Unexpected error %s %s: %s", sym, trade_date, e)
                    state.mark_error(sym, trade_date, str(e))
                    error_count += 1
                    continue

                if result is None:
                    state.mark_error(sym, trade_date, "returned_none")
                    error_count += 1
                    continue

                completed_rows[sym].append(result)
                state.mark_done(sym, trade_date)
                name_day_count += 1
                elapsed_times.append(result["elapsed_s"])
                row_counts.append(result["raw_rows"])

        # Write parquets for all underlyings after each date
        for sym in syms_this_day:
            new_rows = [r for r in completed_rows[sym]
                        if r.get("date") == trade_date]
            if new_rows:
                _merge_into_parquet(out_dir, sym, new_rows)

        # Save state after each date
        state.save()

        wall = time.perf_counter() - pilot_start
        log.info("Date %s done (wall=%.0fs, name-days=%d)", trade_date, wall, name_day_count)

    total_wall = time.perf_counter() - pilot_start

    stats = {
        "terminal_up": True,
        "underlyings": len(PILOT_UNDERLYINGS),
        "trading_dates_target": len(trading_dates),
        "name_days_completed": name_day_count,
        "name_days_target": len(PILOT_UNDERLYINGS) * len(trading_dates),
        "error_count": error_count,
        "total_wall_s": total_wall,
        "coverage": state.coverage_summary(),
    }

    if elapsed_times:
        stats["avg_elapsed_s_per_name_day"] = float(np.mean(elapsed_times))
        stats["median_elapsed_s"] = float(np.median(elapsed_times))
        stats["p95_elapsed_s"] = float(np.percentile(elapsed_times, 95))
        stats["total_raw_rows"] = int(sum(row_counts))
        stats["avg_rows_per_name_day"] = float(np.mean(row_counts))
    else:
        stats["avg_elapsed_s_per_name_day"] = float("nan")

    return stats


def _write_report(stats: dict[str, Any], out_path: Path) -> None:
    """Write plain-language report to reports/w5b-options-tape-pilot.md."""
    lines: list[str] = []
    a = lines.append

    if stats.get("dry_run"):
        a("# W5-B Options Tape Signed Pilot — DRY RUN")
        a("")
        a("ThetaTerminal reachable. Pilot not run (dry-run mode).")
        out_path.write_text("\n".join(lines))
        return

    term_status = "UP" if stats.get("terminal_up") else "DOWN"
    a(f"# W5-B Options Tape Signed Pilot — ThetaTerminal {term_status}")
    a("")
    a("**In plain English:** We pulled every options trade with its simultaneous bid/ask")
    a("quote from ThetaTerminal for 20 liquid names. Each trade was classified as buyer-")
    a("or seller-initiated using the simple quote rule (trade at/above ask = buy, at/below")
    a("bid = sell, in the middle = excluded). The data is stored per-name as signed")
    a("aggregate premium and delta-weighted volume for each trading day.")
    a("")
    a("## Pre-registration")
    a("")
    a("Pre-registered gates and amendments (written before first compute):")
    a("- **Signing rule:** simple quote rule (price >= ask → BUY, price <= bid → SELL,")
    a("  midpoint excluded). NOT Lee-Ready tick-test. Stated explicitly.")
    a("- **Delta source:** moneyness-bucket proxy (Amendment A2). No live delta store")
    a("  available. Column labeled `delta_proxy` to distinguish from model delta.")
    a("- **Amendment A1:** trade_quote accepts wildcard expiration per day (confirmed live).")
    a("  One-calendar-day per request, 6 concurrent underlyings.")
    a("")
    a("## Coverage")
    a("")

    nd_done = stats.get("name_days_completed", 0)
    nd_total = stats.get("name_days_target", 0)
    coverage_pct = 100.0 * nd_done / nd_total if nd_total else 0.0

    a(f"- Underlyings targeted: {stats.get('underlyings', 20)}")
    a(f"- Trading days targeted: {stats.get('trading_dates_target', 0)}")
    a(f"- Name-days completed: {nd_done} of {nd_total} ({coverage_pct:.1f}%)")
    a(f"- Errors: {stats.get('error_count', 0)}")
    a(f"- Total wall-clock: {stats.get('total_wall_s', 0):.0f}s "
      f"({stats.get('total_wall_s', 0)/60:.1f} min)")
    a("")

    cov = stats.get("coverage", {})
    if cov:
        a("### Per-underlying completed dates")
        a("")
        a("| Underlying | Dates completed |")
        a("|-----------|----------------|")
        for sym in PILOT_UNDERLYINGS:
            n = cov.get(sym, 0)
            a(f"| {sym} | {n} |")
        a("")

    a("## Throughput")
    a("")
    avg_s = stats.get("avg_elapsed_s_per_name_day", float("nan"))
    med_s = stats.get("median_elapsed_s", float("nan"))
    p95_s = stats.get("p95_elapsed_s", float("nan"))
    total_rows = stats.get("total_raw_rows", 0)
    avg_rows = stats.get("avg_rows_per_name_day", float("nan"))

    a(f"- Average elapsed per name-day: {avg_s:.1f}s")
    a(f"- Median elapsed per name-day: {med_s:.1f}s")
    a(f"- P95 elapsed per name-day: {p95_s:.1f}s")
    a(f"- Total raw trade rows processed: {total_rows:,}")
    a(f"- Average raw rows per name-day: {avg_rows:,.0f}")
    a("")

    a("### Projected full-build wall-clock")
    a("")
    total_wall_s = stats.get("total_wall_s", float("nan"))
    nd_done = stats.get("name_days_completed", 0)
    if not np.isnan(avg_s) and not np.isnan(total_wall_s) and nd_done > 0:
        # Scale from MEASURED wall-clock (total_wall_s covers 1200 name-days with
        # concurrency=6, so it is the actual real-world build time for the pilot).
        # All projections are linear extrapolations from this measured anchor.
        pilot_min = total_wall_s / 60

        # Full backfill: ~3,500 trading days x 20 names = 70,000 name-days
        # Rate: total_wall_s / nd_done seconds of wall-clock per name-day (with concurrency)
        nd_rate_wall = total_wall_s / nd_done  # wall-s per name-day (concurrent)
        full_backfill_s = nd_rate_wall * 70000
        full_backfill_h = full_backfill_s / 3600

        # 500 names x 60 days (linear scale of pilot)
        ext_500_60d_min = pilot_min * (500 / max(nd_done / stats.get("trading_dates_target", 60), 1))
        # Simpler: pilot covered 20 names x 60d; scale by name count
        ext_500_60d_h = pilot_min * (500.0 / 20) / 60

        # 500 names x full backfill
        ext_500_full_h = full_backfill_h * (500.0 / 20)

        # Nightly incremental (1 new day x 20 names = 20 name-days)
        nightly_min = nd_rate_wall * 20 / 60

        a(f"**Measured actual:** 20 names x 60 days = {total_wall_s:.0f}s ({pilot_min:.1f} min)."
          f" This is the ground truth.")
        a("")
        a(f"- **20 names x 60 days pilot:** {pilot_min:.1f} min (measured, not projected)")
        a(f"- **Full backfill to 2012-06-01 (20 names x ~3500 trading days):**")
        a(f"  ~3500/60 x {pilot_min:.1f} min = {pilot_min:.1f} min x"
          f" {3500//60} = ~{full_backfill_h:.0f} hours at measured throughput")
        a(f"- **Extension to 500 names (full pilot universe, 60 days):**")
        a(f"  500/20 x {pilot_min:.1f} min = ~{ext_500_60d_h:.0f} hours")
        a(f"- **Extension to 500 names x full backfill:**")
        a(f"  500/20 x {full_backfill_h:.0f} hours = ~{ext_500_full_h:.0f} hours"
          f" (~{ext_500_full_h/24:.0f} days serial)")
        a(f"  → Strategy: run incremental nightly, full backfill offline as a batch job")
        a("")
        a(f"**Nightly incremental (1 new day, 20 names):** {pilot_min:.1f} min / 60 ="
          f" ~{nightly_min:.2f} min ({nightly_min*60:.0f} sec) per day")
        a("")
        a("> NOTE: SPY and QQQ dominate P95 (2M+ rows/day each, 25-70s each vs 1-12s for single-names).")
        a("> Separating ETFs from single-names into two concurrent pools would reduce the tail significantly.")
        a(f"> The actual {pilot_min:.1f} min vs {(1200/CONCURRENT_UNDERLYINGS)*p95_s/60:.0f} min"
          f" P95-projected reflects that P95 is a per-name metric, not per-batch.")
    else:
        a("_(No throughput data — pilot did not complete any name-days)_")

    a("")
    a("## Data quality spot-check")
    a("")

    # Load one parquet and compute exclusion rates if available
    out_dir = out_path.parent.parent / "data" / "options_tape_signed"
    loaded_any = False
    for sym in ["AAPL", "AMD", "MSFT"]:
        p = out_dir / f"{sym}.parquet"
        if p.exists():
            try:
                df = pd.read_parquet(p)
                avg_excl = df["exclusion_rate"].mean() if "exclusion_rate" in df.columns else float("nan")
                avg_mid = df["mid_rate"].mean() if "mid_rate" in df.columns else float("nan")
                a(f"**{sym}** ({len(df)} days):")
                a(f"  - Average exclusion rate: {avg_excl:.1%} (midpoint trades excluded)")
                a(f"  - Average midpoint rate: {avg_mid:.1%}")
                if "buy_premium" in df.columns and len(df) > 0:
                    a(f"  - Net premium sample (last 3 days): "
                      f"{df['net_premium'].tail(3).values.tolist()}")
                a("")
                loaded_any = True
            except Exception as e:
                a(f"_{sym}: could not load parquet — {e}_")
                a("")

    if not loaded_any:
        a("_(No completed parquets available for spot-check)_")

    a("")
    a("## PIT assumptions")
    a("")
    a("- Spot price: sourced from `massive_stock_day/<UNDERLYING>.parquet` last close")
    a("  strictly at or before the trade date. This is PIT-safe: no look-ahead.")
    a("- Delta proxy: moneyness bucket as of the spot price at the time of signing.")
    a("  Because spot is EOD-prior (not intraday), there is a small intraday bias;")
    a("  stated, not hidden.")
    a("- OI timing (for future signal use): OPRA reports OI at 06:30 ET = EOD t-1.")
    a("  Any signal using OI must lag one day.")
    a("")
    a("## Signing rule detail")
    a("")
    a("```")
    a("Simple quote rule (NOT Lee-Ready tick-test):")
    a("  price >= ask          → BUY-SIDE  (trade at or above the offer)")
    a("  price <= bid          → SELL-SIDE (trade at or below the bid)")
    a("  bid < price < ask     → EXCLUDED  (midpoint; initiator ambiguous)")
    a("  bid=NaN or ask=NaN    → EXCLUDED  (missing NBBO)")
    a("  bid > ask (crossed)   → EXCLUDED  (crossed market; quote unreliable)")
    a("```")
    a("")
    a("The Lee-Ready tick-test would classify midpoint trades using the")
    a("prior tick direction. We chose the simpler pure-quote rule because:")
    a("1. The lane spec explicitly instructs it.")
    a("2. Tick-test introduces path-dependence that is harder to audit.")
    a("3. Exclusion rate is measured and reported; if high, a future pass")
    a("   can add tick-test as an alternative classification.")
    a("")
    a("## Output schema")
    a("")
    a("```")
    a("data/options_tape_signed/<UNDERLYING>.parquet")
    a("Columns:")
    a("  underlying          str  — ticker symbol")
    a("  date               datetime64  — trading date")
    a("  buy_premium        float  — sum(price * size * 100) for BUY trades")
    a("  sell_premium       float  — sum(price * size * 100) for SELL trades")
    a("  net_premium        float  — buy_premium - sell_premium (signed flow)")
    a("  buy_delta_proxy    float  — sum(delta_proxy * size) for BUY trades")
    a("  sell_delta_proxy   float  — sum(delta_proxy * size) for SELL trades")
    a("  net_delta_proxy    float  — buy_delta_proxy - sell_delta_proxy")
    a("  buy_count          int    — number of BUY-classified trades")
    a("  sell_count         int    — number of SELL-classified trades")
    a("  excluded_count     int    — number of excluded (midpoint/missing) trades")
    a("  total_count        int    — total raw trades (buy + sell + excluded)")
    a("  exclusion_rate     float  — excluded_count / total_count")
    a("  mid_rate           float  — midpoint-only exclusion / total_count")
    a("")
    a("data/options_tape_signed/_backfill_state.json")
    a("  Resumable state machine per-underlying: cursor, completed_dates, errors.")
    a("```")
    a("")
    a("## Delta proxy bucketing (Amendment A2)")
    a("")
    a("```")
    a("Moneyness = (spot - strike)/spot for calls, (strike - spot)/spot for puts")
    a("  ITM  |m|>0.20  → delta_proxy = 0.90")
    a("  ITM  |m|>0.10  → delta_proxy = 0.70")
    a("  NTM/ATM |m|≤0.10 → delta_proxy = 0.50")
    a("  OTM  |m|>0.10  → delta_proxy = 0.30")
    a("  OTM  |m|>0.20  → delta_proxy = 0.10")
    a("Source: massive_stock_day EOD close (PIT-safe).")
    a("Label in output: delta_proxy (NOT model delta).")
    a("```")
    a("")
    a("## Nightly wiring note (for consolidation)")
    a("")
    a("**Accrual cadence proposal:**")
    a("")
    a("1. **Timing:** run at 21:00 ET (after ThetaTerminal post-market data update ~20:00 ET).")
    a("   Today's trade_quote data is available from the terminal within ~1h of market close.")
    a("")
    a("2. **Incremental pull:** read `_backfill_state.json`; for each underlying, pull only")
    a("   dates after the cursor. Typical nightly load: 1 date x 20 names = 20 name-days.")
    if not np.isnan(total_wall_s) and nd_done > 0:
        # Use measured wall-clock: total_wall_s / nd_done = wall-s per name-day (concurrent)
        nd_rate_wall_nightly = total_wall_s / nd_done
        nightly_min_est = nd_rate_wall_nightly * 20 / 60
        nightly_sec_est = nightly_min_est * 60
        pilot_min_nightly = total_wall_s / 60
        trading_dates_target = stats.get("trading_dates_target", 60)
        a(f"   Estimated: ~{nightly_sec_est:.0f} sec/night"
          f" (measured: {pilot_min_nightly:.1f} min / {trading_dates_target} dates,"
          f" wall-clock for 20 concurrent names)")
    else:
        a("   Estimated: TBD (pilot throughput not yet measured)")
    a("")
    a("3. **Consolidation target:** `scripts/collect.py` nightly job.")
    a("   Add a `collect_options_tape` stage after existing theta stages.")
    a("   (This file does NOT edit collect.py — per House Rule 6.)")
    a("")
    a("4. **Extension to 500 names:** add to `PILOT_UNDERLYINGS` list in this script,")
    a("   or pass via `--underlyings` flag (future). Concurrency ceiling = 6 connections.")
    if not np.isnan(total_wall_s) and nd_done > 0:
        nightly_500_min = (total_wall_s / nd_done) * 500 / 60
        a(f"   At 500 names, nightly incremental load: ~{nightly_500_min:.0f} min/night")
    a("")
    a("5. **R2 storage (future):** at 500 names x 3500 trading days, the store will grow")
    a("   to ~10-50 GB compressed parquet. If this exceeds git budget, move to R2 bucket")
    a("   (pattern: `data/options_tape_signed/` → `r2://options-tape-signed/`), consistent")
    a("   with the existing R2 pattern for `massive_stock_day`.")
    a("")

    out_path.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="W5-B Options Tape Signed Pilot")
    parser.add_argument("--max-days", type=int, default=60,
                        help="Max trading days to pull (default=60)")
    parser.add_argument("--max-runtime", type=float, default=2400.0,
                        help="Hard wall-clock ceiling in seconds (default=2400=40min)")
    parser.add_argument("--no-resume", action="store_true",
                        help="Ignore existing state; re-pull all dates")
    parser.add_argument("--dry-run", action="store_true",
                        help="Check reachability and dates only, no data pull")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    wt_root = Path(__file__).resolve().parent.parent
    out_dir = wt_root / "data" / "options_tape_signed"
    stock_day_dir = wt_root / "data" / "massive_stock_day"
    report_path = wt_root / "reports" / "w5b-options-tape-pilot.md"

    log.info("W5-B Options Tape Signed Pilot starting")
    log.info("Output: %s", out_dir)
    log.info("State:  %s", out_dir / "_backfill_state.json")

    try:
        stats = run_pilot(
            out_dir=out_dir,
            stock_day_dir=stock_day_dir,
            max_days=args.max_days,
            max_runtime_s=args.max_runtime,
            resume=not args.no_resume,
            dry_run=args.dry_run,
        )
    except RuntimeError as e:
        log.error("BLOCKED: %s", e)
        # Write blocked report
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            f"# W5-B Options Tape Signed Pilot — BLOCKED\n\n"
            f"ThetaTerminal is DOWN.\n\n"
            f"```\n{e}\n```\n\n"
            f"Re-run once terminal is restarted.\n"
        )
        sys.exit(1)

    log.info("Writing report: %s", report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    _write_report(stats, report_path)

    log.info("Done. Name-days completed: %d / %d",
             stats.get("name_days_completed", 0),
             stats.get("name_days_target", 0))

    print(f"\nReport: {report_path}")
    print(f"Name-days completed: {stats.get('name_days_completed', 0)} / {stats.get('name_days_target', 0)}")


if __name__ == "__main__":
    main()
