"""scripts/backfill_qledger_cn.py — China event-move claim backfill (W1/B3).

Registers one qledger claim per (event, ticker) pair from the China news-vector
events.parquet, using the spec's D3/D5 design:
  - desk      = "china_news"
  - scope     = entity / per ticker
  - direction = 0  (salience-only — contrarian sign frozen until CCTV backfill
                    lands in W4 and earns its way through the promotion gate, D5)
  - horizon_d = 5 then 21 (two separate claims — both horizons registered per pair)
  - bench     = "510300.SS" (CSI300 ETF; the parquet at data/china/510300.SS.parquet)
  - importance_band = "HIGH" / "LOW" recorded in extra{} so the scoreboard can
                      answer "does the High band move more than Low?" per-slice
  - timestamp_quality = CRAWL_BOUNDED (first_seen_utc is the crawl timestamp)

Claims are registered idempotently (register() deduplication), so this script can
be re-run nightly without duplicating the ledger.

Usage:
    python scripts/backfill_qledger_cn.py [--dry-run] [--root PATH]

Output to stdout:
    n_events       total events in source
    n_tagged       events with non-empty tickers field
    n_pairs        (event, ticker) pairs attempted
    n_registered   claims written (per horizon_d, so 2× pairs)
    n_blocked      pairs skipped due to missing price data
    n_rejected     claims qledger rejected
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import pandas as pd

# Ensure project root is on sys.path when run directly.
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engine.qledger import make_claim, register  # noqa: E402

log = logging.getLogger("backfill_cn")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

_BENCH = "510300.SS"
_DESK = "china_news"
_HORIZONS = (5, 21)

# Importance threshold: score >= median is "HIGH", below is "LOW".
# The median across the full accrual (all events, not just tagged) keeps the
# cutpoint stable across re-runs and consistent with the placebo sampler.
_IMPORTANCE_THRESHOLD: float | None = None  # resolved lazily from the data


def _score_threshold(df: pd.DataFrame) -> float:
    return float(df["score"].median())


def _importance_band(score: float, threshold: float) -> str:
    return "HIGH" if score >= threshold else "LOW"


def _has_price(ticker: str, root: Path) -> bool:
    """Quick existence check for data/china_stocks/<ticker>.parquet."""
    p = root / "data" / "china_stocks" / f"{ticker}.parquet"
    return p.exists()


def _bench_exists(root: Path) -> bool:
    return (root / "data" / "china" / f"{_BENCH}.parquet").exists()


def _entry_date_for(first_seen_utc: str) -> str:
    """Convert first_seen_utc (ISO string, UTC) to a local date string (YYYY-MM-DD).
    timestamp_quality = CRAWL_BOUNDED so no embargo shift; we use the date of
    the crawl event as the asof anchor."""
    ts = pd.Timestamp(first_seen_utc, tz="UTC")
    return ts.date().isoformat()


def run(root: Path, dry_run: bool = False) -> dict:
    cn_events_path = root / "data" / "china_news_vector" / "events.parquet"
    if not cn_events_path.exists():
        log.error("events.parquet not found: %s", cn_events_path)
        sys.exit(1)

    if not _bench_exists(root):
        log.error("Bench %s not found in data/china/", _BENCH)
        sys.exit(1)

    df = pd.read_parquet(cn_events_path)
    n_events = len(df)
    threshold = _score_threshold(df)
    log.info("Loaded %d events; importance threshold (median score) = %.4f", n_events, threshold)

    # Select events with at least one ticker
    tagged = df[df["tickers"].str.strip() != ""].copy()
    n_tagged = len(tagged)
    log.info("Events with tickers: %d", n_tagged)

    counters = {
        "n_events": n_events,
        "n_tagged": n_tagged,
        "n_pairs": 0,
        "n_registered": 0,
        "n_blocked": 0,
        "n_rejected": 0,
    }

    for _, row in tagged.iterrows():
        raw_tickers = [t.strip() for t in str(row["tickers"]).split(",") if t.strip()]
        asof = _entry_date_for(str(row["first_seen_utc"]))
        band = _importance_band(float(row["score"]), threshold)
        event_id = str(row["event_id"])
        score = float(row["score"])

        for ticker in raw_tickers:
            counters["n_pairs"] += 1

            if not _has_price(ticker, root):
                counters["n_blocked"] += 1
                log.debug("No price data for ticker %s (event %s) — blocked", ticker, event_id)
                continue

            for horizon_d in _HORIZONS:
                claim = make_claim(
                    desk=_DESK,
                    asof=asof,
                    scope_type="entity",
                    scope_key=ticker,
                    direction=0,  # salience-only (D5 — contrarian sign deferred)
                    horizon_d=horizon_d,
                    timestamp_quality="CRAWL_BOUNDED",
                    bench=_BENCH,
                    # control: None — CSI300 sector breakdown not available; the
                    # bench IS the sector-equivalent for A/H names (D4 entity exempt)
                    control=None,
                    claim_family=_DESK,
                    extra={
                        "importance_band": band,
                        "importance_score": score,
                        "event_id": event_id,
                        "source_tier": int(row.get("source_tier", 2)),
                    },
                )
                # Use event_id+ticker+horizon as salt for distinct claim per pair
                claim["salt"] = f"{event_id}:{ticker}:{horizon_d}"

                if dry_run:
                    counters["n_registered"] += 1
                    log.debug("DRY-RUN claim: %s %s h=%d band=%s", ticker, asof, horizon_d, band)
                    continue

                stored = register(claim, root=root)
                if stored.get("status") == "rejected":
                    counters["n_rejected"] += 1
                    log.warning(
                        "Claim rejected: %s %s h=%d — %s",
                        ticker, asof, horizon_d, stored.get("reject_reason"),
                    )
                else:
                    counters["n_registered"] += 1

    log.info(
        "Done — events=%d tagged=%d pairs=%d registered=%d blocked=%d rejected=%d",
        counters["n_events"], counters["n_tagged"], counters["n_pairs"],
        counters["n_registered"], counters["n_blocked"], counters["n_rejected"],
    )
    return counters


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate but do not write to the ledger")
    parser.add_argument("--root", default=None,
                        help="Repo root (default: auto-detected from script location)")
    parser.add_argument("--json", action="store_true",
                        help="Emit summary as JSON to stdout")
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else _ROOT
    result = run(root, dry_run=args.dry_run)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for k, v in result.items():
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()
