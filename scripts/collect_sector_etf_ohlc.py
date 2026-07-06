"""OTA W0.2 — One-shot OHLC collector for sector ETFs.

Spec: research/oracle_asymmetry/W0_2_SPEC.md §2.

Pulls unadjusted OHLC (auto_adjust=False) for the 11 Tier-S sector ETFs + SPY
from Yahoo Finance via yfinance, stores to data/yahoo_ohlc/{T}.parquet (worktree-local,
gitignored), and writes a committed manifest JSON with row counts, date ranges, and
pull timestamp.

Usage (one-shot research pull; run once before oracle_asymmetry_intraday.py):
    python -m scripts.collect_sector_etf_ohlc \\
        --ohlc-dir /path/to/data/yahoo_ohlc \\
        --manifest-out research/oracle_asymmetry/W0_2_ohlc_manifest.json

Prohibitions:
    - No modification of any engine/ or existing scripts/ file.
    - No writes to MAIN data dir; OHLC store lands in worktree only.
    - "validated" must not appear in any output.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("collect_ohlc")

# ---------------------------------------------------------------------------
# Universe (spec §2)
# ---------------------------------------------------------------------------
UNIVERSE = [
    "XLK", "XLV", "XLF", "XLY", "XLC", "XLI",
    "XLP", "XLE", "XLU", "XLRE", "XLB", "SPY",
]

# Columns to store (unadjusted OHLC + adj_close for cross-check reference)
STORE_COLS = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
RENAME_MAP = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adj_close",
    "Volume": "volume",
}


def _pull_ticker(
    ticker: str,
    max_retries: int = 3,
    retry_delay: float = 5.0,
) -> pd.DataFrame | None:
    """Pull max-period unadjusted OHLC for one ticker. Loud-error on failure."""
    import yfinance as yf

    for attempt in range(1, max_retries + 1):
        try:
            log.info("  Pulling %s (attempt %d/%d) ...", ticker, attempt, max_retries)
            t = yf.Ticker(ticker)
            df = t.history(period="max", auto_adjust=False, actions=False)
            if df is None or df.empty:
                log.warning("  %s: empty result on attempt %d", ticker, attempt)
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    continue
                return None
            # Keep only OHLCAV columns (yfinance v0.2+ returns multi-level sometimes)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            avail = [c for c in STORE_COLS if c in df.columns]
            if "Open" not in avail or "High" not in avail or "Low" not in avail or "Close" not in avail:
                print(
                    f"::error:: {ticker}: required OHLC columns not found; got {df.columns.tolist()}",
                    file=sys.stderr,
                )
                return None
            df = df[avail].copy()
            df.rename(columns=RENAME_MAP, inplace=True)
            # Normalize index to date-only
            df.index = pd.to_datetime(df.index).normalize()
            df.index.name = "date"
            df = df.sort_index()
            df = df.dropna(subset=["open", "high", "low", "close"])
            log.info(
                "  %s: %d rows (%s → %s)",
                ticker,
                len(df),
                str(df.index.min().date()),
                str(df.index.max().date()),
            )
            return df
        except Exception as exc:
            log.warning("  %s: attempt %d error: %s", ticker, attempt, exc)
            if attempt < max_retries:
                time.sleep(retry_delay)

    print(
        f"::error:: {ticker}: all {max_retries} pull attempts failed",
        file=sys.stderr,
    )
    return None


def pull_all(
    ohlc_dir: Path,
    *,
    pause: float = 1.0,
) -> dict[str, dict]:
    """Pull all tickers, write parquets, return manifest entries."""
    ohlc_dir.mkdir(parents=True, exist_ok=True)
    manifest_entries: dict[str, dict] = {}
    failed: list[str] = []

    for ticker in UNIVERSE:
        df = _pull_ticker(ticker)
        if df is None or df.empty:
            failed.append(ticker)
            continue
        out_path = ohlc_dir / f"{ticker}.parquet"
        df.to_parquet(out_path, engine="pyarrow", index=True)
        manifest_entries[ticker] = {
            "rows": int(len(df)),
            "date_start": str(df.index.min().date()),
            "date_end": str(df.index.max().date()),
            "columns": df.columns.tolist(),
            "path": str(out_path),
        }
        # Rate-limit friendly pause
        if pause > 0:
            time.sleep(pause)

    if failed:
        print(
            f"::error:: OHLC pull failed for tickers: {failed}",
            file=sys.stderr,
        )
        sys.exit(1)

    return manifest_entries


def write_manifest(
    manifest_entries: dict[str, dict],
    manifest_out: Path,
    ohlc_dir: Path,
) -> None:
    """Write committed manifest JSON."""
    manifest = {
        "pull_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "universe": UNIVERSE,
        "ohlc_dir": str(ohlc_dir),
        "note": (
            "Unadjusted OHLC (auto_adjust=False); dividend drag unmodeled per W0_2_SPEC §2. "
            "Store is gitignored and reproducible from this collector + manifest."
        ),
        "tickers": manifest_entries,
    }
    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    manifest_out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log.info("Manifest written: %s", manifest_out)


def sanity_print(manifest_entries: dict[str, dict]) -> None:
    """Print a compact summary table."""
    print("\n--- OHLC Pull Summary ---")
    print(f"{'Ticker':<8} {'Rows':>6}  {'Start':>12}  {'End':>12}")
    print("-" * 44)
    for ticker, info in manifest_entries.items():
        print(
            f"{ticker:<8} {info['rows']:>6}  "
            f"{info['date_start']:>12}  {info['date_end']:>12}"
        )
    print()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="OTA W0.2 — One-shot OHLC collector for sector ETFs"
    )
    parser.add_argument(
        "--ohlc-dir",
        type=Path,
        default=ROOT / "data" / "yahoo_ohlc",
        help="Output directory for parquet files (gitignored)",
    )
    parser.add_argument(
        "--manifest-out",
        type=Path,
        default=ROOT / "research" / "oracle_asymmetry" / "W0_2_ohlc_manifest.json",
        help="Path for the committed manifest JSON",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=1.0,
        help="Pause (seconds) between ticker pulls (rate-limit friendly)",
    )
    args = parser.parse_args(argv)

    ohlc_dir = args.ohlc_dir.expanduser().resolve()
    manifest_out = args.manifest_out.expanduser().resolve()

    log.info("OTA W0.2 OHLC collector — unadjusted (auto_adjust=False)")
    log.info("Tickers: %s", UNIVERSE)
    log.info("OHLC dir: %s", ohlc_dir)

    manifest_entries = pull_all(ohlc_dir, pause=args.pause)
    sanity_print(manifest_entries)
    write_manifest(manifest_entries, manifest_out, ohlc_dir)

    print(f"Done. {len(manifest_entries)}/{len(UNIVERSE)} tickers pulled successfully.")
    print(f"  OHLC store: {ohlc_dir}/")
    print(f"  Manifest:   {manifest_out}")


if __name__ == "__main__":
    main()
