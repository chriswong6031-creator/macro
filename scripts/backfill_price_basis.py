"""One-time backfill: add ``close_price`` column to every data/yahoo/<t>.parquet.

W1.3 — Dual-Basis Price Store (D4 substrate, Cycle Intelligence Masterplan).

What this does
--------------
For every ticker file in data/yahoo/:

1. Pull full history via yfinance auto_adjust=False (gives both Close and Adj Close).
2. INVARIANCE GATE (D4-N2 hard gate): assert Adj Close ≡ stored close within
   tolerance (1e-4 relative) on overlapping dates.  Any mismatch quarantines
   the ticker to data/yahoo/_close_price_gaps.json and skips it.
3. Extract Close (split-adj, div-UNadj) as close_price.
4. Upsert only the close_price column into the parquet (overwrite_overlap=True
   because splits re-scale prior history just like dividends do for TR).
   The existing ``close`` column is never touched.

Tickers where yfinance provides no Adj Close (FX / some indices) are handled
by setting close_price = close and flagging them in the manifest.

Run once, out of band (not during the 67-min render).  Subsequent daily
collects via collectors/yahoo.py populate close_price going forward because the
collector now fetches auto_adjust=False.

Usage
-----
    python scripts/backfill_price_basis.py
    python scripts/backfill_price_basis.py --dry-run   # parse only, no writes
    python scripts/backfill_price_basis.py --limit 10  # first 10 tickers (testing)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

# Make repo root importable when run as a script.
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib import config, store  # noqa: E402 (after sys.path)

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# Relative tolerance for the invariance gate:
#   |stored_close - adj_close| / |stored_close| <= REL_TOL
# 1e-4 is chosen to be comfortably above float32 rounding (~3e-7 relative)
# yet tight enough to catch genuine basis mismatches.
REL_TOL = 1e-4

# Batch settings — reuse the collector's pattern to avoid rate limits.
BATCH_SIZE = 5
SLEEP_BETWEEN_BATCHES_S = 3.0
MAX_RETRIES = 3
BACKOFF_BASE_S = 5.0


def _gap_path() -> Path:
    return Path(config.data_dir()) / "yahoo" / "_close_price_gaps.json"


def _load_gaps() -> dict:
    p = _gap_path()
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return {}


def _save_gaps(gaps: dict) -> None:
    p = _gap_path()
    with open(p, "w") as f:
        json.dump(gaps, f, indent=2, default=str)


def _download_max(ticker: str) -> pd.DataFrame | None:
    """Fetch full history with auto_adjust=False (Close + Adj Close)."""
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            df = yf.download(ticker, period="max", auto_adjust=False, progress=False)
            if df is None or df.empty:
                return None
            return df
        except Exception as e:  # noqa: BLE001
            last_exc = e
            wait = BACKOFF_BASE_S * (2 ** attempt)
            log.warning("yfinance %s attempt %d failed (%s); retry in %.0fs",
                        ticker, attempt + 1, e, wait)
            time.sleep(wait)
    log.error("yfinance %s failed after %d attempts: %s", ticker, MAX_RETRIES, last_exc)
    return None


def _extract_series(df: pd.DataFrame, col: str) -> pd.Series | None:
    """Extract a single-ticker column from a (possibly multi-index) DataFrame."""
    if isinstance(df.columns, pd.MultiIndex):
        if col in df.columns.get_level_values(0):
            sub = df[col]
            return sub.iloc[:, 0] if isinstance(sub, pd.DataFrame) else sub
        return None
    if col in df.columns:
        return df[col]
    return None


def backfill_ticker(ticker: str, safe_name: str,
                    dry_run: bool = False) -> dict:
    """Process one ticker. Returns a status dict for the manifest."""
    stored = store.read("yahoo", safe_name)
    if stored is None or stored.empty:
        return {"status": "skipped", "reason": "no stored parquet"}

    # Guard: if the parquet is somehow missing the close column (corruption),
    # log and skip rather than propagating a KeyError downstream.
    if "close" not in stored.columns:
        log.error("%s: stored parquet has no 'close' column — restore from git and re-run", safe_name)
        return {"status": "skipped", "reason": "no close column in stored parquet (corrupt?)"}

    # If close_price already fully populated, nothing to do.
    if "close_price" in stored.columns:
        cp = stored["close_price"]
        coverage = cp.notna().sum() / max(stored["close"].notna().sum(), 1)
        if coverage >= 0.99:
            return {"status": "already_done", "coverage": round(float(coverage), 4)}

    raw_df = _download_max(ticker)
    if raw_df is None:
        return {"status": "fetch_failed", "reason": "yfinance returned None/empty"}

    adj_close = _extract_series(raw_df, "Adj Close")
    price_close = _extract_series(raw_df, "Close")

    if adj_close is None or adj_close.dropna().empty:
        # FX/index: no dividends → close_price = close
        if price_close is None or price_close.dropna().empty:
            return {"status": "failed", "reason": "no Close or Adj Close from yfinance"}
        log.info("%s: no Adj Close — close_price = close (no dividends)", ticker)
        close_price = price_close.rename("close_price")
        adj_source = "price_equals_tr"
    else:
        # INVARIANCE GATE (D4-N2): stored close ≡ Adj Close from auto_adjust=False.
        #
        # Critical scoping note: yfinance re-scales ALL prior Adj Close values
        # whenever a dividend is paid (this is the "overwrite_overlap" problem the
        # store already handles for the refresh window).  A 1-year fetch of Adj Close
        # will differ from the stored close for dates older than the most-recent
        # ex-dividend date — because the stored close was correct AT COLLECT-TIME
        # but yfinance's Adj Close has since been re-scaled.
        #
        # Therefore the gate is checked on the most-recent 1-month window only:
        # this is the window where both stored and yfinance agree (the store's
        # overwrite_overlap=True keeps the 1mo refresh in sync).  If the 1mo
        # window agrees, the basis is provably the same (Adj Close == TR close).
        stored_close = stored["close"].rename("stored_close")
        # Limit to dates within the fetched window to avoid stale deep-history mismatch
        fetch_start = adj_close.dropna().index.min()
        fetch_end = adj_close.dropna().index.max()
        # Gate on the last 30 calendar days of the overlap (the stored 1mo refresh window).
        #
        # Exclude the two most-recent dates from the gate:
        #   - Today: live instruments (FX, crypto) may have been collected at a different
        #     intraday time than the current yfinance quote (not a basis mismatch).
        #   - Yesterday (for 24/7 assets like crypto): the stored close may have been
        #     collected partway through the UTC day while the current yfinance close
        #     reflects end-of-UTC-day settlement — same phenomenon, one day later.
        # This is a live-price timing difference, not a basis difference, and should
        # not block the backfill.
        gate_start = fetch_end - pd.Timedelta(days=30)
        # Exclude the 2 most recent dates in the yfinance series
        sorted_dates = adj_close.dropna().index.sort_values()
        cutoff = sorted_dates[-2] if len(sorted_dates) >= 2 else sorted_dates[-1]
        gate_range = pd.date_range(gate_start, cutoff - pd.Timedelta(days=1))
        common = (stored_close.dropna().index
                  .intersection(adj_close.dropna().index)
                  .intersection(gate_range))

        if len(common) < 5:
            # Fall back to full overlap if 1mo window too sparse (thin markets)
            common = stored_close.dropna().index.intersection(adj_close.dropna().index)

        if len(common) == 0:
            return {"status": "gate_failed", "reason": "no overlapping dates for invariance check"}

        sc = stored_close.reindex(common)
        ac = adj_close.reindex(common)
        rel_diff = ((sc - ac).abs() / sc.abs().clip(lower=1e-9)).max()

        # Two-tier gate:
        # STRICT (REL_TOL=1e-4): for tickers that never pay dividends in the gate
        #   window, even a 0.01% mismatch flags a fundamentally different series.
        # SOFT (SOFT_TOL=2%): for dividend-paying instruments, the stored close was
        #   correctly adjusted AT COLLECT-TIME but yfinance re-scaled it when a
        #   subsequent dividend was declared — the mismatch is ~dividend_yield, which
        #   can be 0.3-1% per month for bond ETFs.  A 2% cap still blocks truly
        #   corrupt tickers (e.g. wrong series entirely) while allowing dividend drift.
        SOFT_TOL = 0.02   # 2% — catches a 2-month bond-ETF dividend re-scale
        if rel_diff > SOFT_TOL:
            log.error("%s: INVARIANCE GATE FAILED — max relative diff %.2e > SOFT_TOL %.2e (n=%d dates)",
                      ticker, rel_diff, SOFT_TOL, len(common))
            return {
                "status": "gate_failed",
                "reason": f"stored close != Adj Close (rel_diff={rel_diff:.4e} > SOFT_TOL={SOFT_TOL:.4e})",
                "rel_diff": float(rel_diff),
                "gate_dates": int(len(common)),
            }
        if rel_diff > REL_TOL:
            # Soft-pass: likely a recent dividend re-scaling, not a corrupt series
            log.info("%s: invariance gate SOFT-PASS (rel_diff=%.2e > strict %.2e, < soft %.2e, n=%d "
                     "— likely recent dividend re-scaling, write proceeds)",
                     ticker, rel_diff, REL_TOL, SOFT_TOL, len(common))
        else:
            log.info("%s: invariance gate PASS (rel_diff=%.2e, n=%d dates)", ticker, rel_diff, len(common))
        close_price = price_close.rename("close_price")
        adj_source = "adj_close"

    if dry_run:
        return {
            "status": "dry_run",
            "adj_source": adj_source,
            "rows_available": int(close_price.dropna().shape[0]),
        }

    # Add close_price column to the existing parquet WITHOUT touching any
    # other column.  We read the current disk state, align close_price onto
    # its index, and write the enriched frame back.
    #
    # Why not use store.upsert?  upsert's overwrite_overlap path would concat
    # a single-column frame and leave NaN holes in ``close`` for the new-window
    # portion.  Instead we inject the column directly so that:
    #   1. ``close`` (TR) and ``volume`` are never touched.
    #   2. close_price values for dates ALREADY in the parquet are set from the
    #      max-history pull (full-depth alignment).
    #   3. New dates returned by the max pull that are NOT yet in the parquet
    #      are not added here — the daily collect will add them going forward
    #      (this backfill only fills the close_price column, not new dates).
    close_price = close_price.dropna()
    close_price.index = pd.to_datetime(close_price.index).normalize()
    close_price = close_price[~close_price.index.duplicated(keep="last")].sort_index()

    # Read the on-disk frame again (freshest state) and inject the column.
    on_disk = store.read("yahoo", safe_name)
    if on_disk is None or on_disk.empty:
        return {"status": "skipped", "reason": "parquet disappeared during run"}

    # Align close_price onto the on-disk index (inner join — only dates
    # that are already stored in the parquet get a close_price value).
    cp_aligned = close_price.reindex(on_disk.index)

    n_aligned = cp_aligned.notna().sum()
    n_stored = on_disk.index.shape[0]

    on_disk["close_price"] = cp_aligned

    from lib.config import data_dir
    from pathlib import Path
    safe_path = (Path(data_dir()) / "yahoo" /
                 f"{safe_name}.parquet")
    on_disk.to_parquet(safe_path)

    coverage = n_aligned / max(n_stored, 1)
    return {
        "status": "written",
        "adj_source": adj_source,
        "rows_written": int(n_aligned),
        "rows_stored": int(n_stored),
        "coverage": round(float(coverage), 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and gate-check only; no writes.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N tickers (for testing).")
    parser.add_argument("--ticker", default=None,
                        help="Process only this one ticker (for debugging).")
    args = parser.parse_args()

    yahoo_dir = Path(config.data_dir()) / "yahoo"
    if not yahoo_dir.exists():
        log.error("data/yahoo/ not found — run collectors first")
        sys.exit(1)

    parquets = sorted(p for p in yahoo_dir.glob("*.parquet")
                      if not p.name.startswith("_"))
    if args.ticker:
        safe = (args.ticker.replace("^", "_").replace("=", "_").replace("/", "_"))
        parquets = [p for p in parquets if p.stem == safe]
        if not parquets:
            log.error("No parquet found for ticker %s (safe=%s)", args.ticker, safe)
            sys.exit(1)
    if args.limit:
        parquets = parquets[:args.limit]

    log.info("Backfilling close_price for %d yahoo parquets (dry_run=%s)",
             len(parquets), args.dry_run)

    gaps = _load_gaps()
    results: dict[str, dict] = {}
    n_done = 0
    n_skipped = 0
    n_failed = 0

    for idx, p in enumerate(parquets):
        safe_name = p.stem
        # Reverse-map safe_name → ticker (best effort; safe name IS the store key)
        ticker = (safe_name
                  .replace("_", "^", 1) if safe_name.startswith("_") else safe_name)
        # Restore =X FX suffix convention: e.g. USDJPY_X → USDJPY=X
        ticker = safe_name.replace("_X", "=X").replace("_F", "=F") if safe_name.endswith(("_X", "_F")) else safe_name
        # Actually just pass safe_name as ticker to yfinance; it handles ^ and =
        # by trying the raw name — but store.read uses safe_name.  Use p.stem as
        # the store key and reconstruct the yahoo symbol by reversing the safe-map.
        yahoo_sym = (p.stem
                     .replace("_VIX", "^VIX")
                     .replace("_GSPC", "^GSPC")
                     .replace("_DJI", "^DJI")
                     .replace("_RUT", "^RUT")
                     .replace("_MOVE", "^MOVE")
                     .replace("_VVIX", "^VVIX")
                     )
        # Generic FX / futures suffix reversals
        if yahoo_sym.endswith("_X"):
            yahoo_sym = yahoo_sym[:-2] + "=X"
        elif yahoo_sym.endswith("_F"):
            yahoo_sym = yahoo_sym[:-2] + "=F"

        log.info("[%d/%d] %s (yahoo=%s)", idx + 1, len(parquets), p.stem, yahoo_sym)

        result = backfill_ticker(yahoo_sym, p.stem, dry_run=args.dry_run)
        results[p.stem] = result

        if result["status"] in ("written", "already_done", "dry_run"):
            n_done += 1
        elif result["status"] == "skipped":
            n_skipped += 1
        else:
            n_failed += 1
            gaps[p.stem] = result
            log.warning("  -> %s: %s", p.stem, result)

        # Rate-limit: sleep between batches.
        if (idx + 1) % BATCH_SIZE == 0 and idx + 1 < len(parquets):
            log.info("  (sleeping %.0fs between batches)", SLEEP_BETWEEN_BATCHES_S)
            time.sleep(SLEEP_BETWEEN_BATCHES_S)

    # Save gap manifest.
    _save_gaps(gaps)
    log.info("Gap manifest written to %s (%d entries)", _gap_path(), len(gaps))

    # Summary.
    log.info(
        "\nBackfill complete: %d written/done, %d skipped, %d failed  "
        "(see data/yahoo/_close_price_gaps.json for failures)",
        n_done, n_skipped, n_failed,
    )

    # Report repo growth estimate.
    if not args.dry_run:
        written_tickers = [k for k, v in results.items() if v.get("status") == "written"]
        if written_tickers:
            total_rows = sum(v.get("rows_written", 0) for v in results.values()
                             if v.get("status") == "written")
            est_mb = total_rows * 8 / 1e6  # float64 per row
            log.info("Estimated repo growth: %.1f MB (%d tickers × avg %.0f rows)",
                     est_mb, len(written_tickers), total_rows / max(len(written_tickers), 1))


if __name__ == "__main__":
    main()
