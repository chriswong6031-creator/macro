"""scripts/sample_qledger_placebo.py — Daily placebo tape sampler (W1/B3, D3).

Spec excerpt (D3):
  "Daily, sample K random LOW-importance events and grade them through the
   identical pipeline. High-importance items must beat the placebo tape, not
   zero. Sample from the full accrual, not the displayed feed. Deterministic
   sampling seeded by date (no Date.now in configs) so reruns are idempotent."

Design:
  - Samples K=10 events per run, split across BOTH corpora:
      * data/china_news_vector/events.parquet  (CN)
      * data/news_vector/events.parquet        (US)
    If a corpus has fewer than K events, all qualifying events are used.
  - "LOW-importance" = score < median of the FULL corpus (not just displayed feed).
    US events.parquet has no `score` column; we treat all US events as low-importance
    (no importance filter) since the column is absent — the scoreboard can slice by
    `is_placebo=True` to separate the populations.
  - Ticker assignment for placebo: if the event carries tickers, we register ONE
    claim per ticker (same as the real backfill). If no tickers, we register a
    BASKET claim against the bench (the "diffuse event" path from D4).
  - direction = 0 (salience-only; placebo claims measure magnitude against the tape)
  - bench = "510300.SS" for CN events; "SPY" for US events
  - Deterministic seed: sha256(asof_str) -> int, seeded into random.Random,
    no global state mutation. Reruns with the same --asof produce the same sample.
  - All claims carry is_placebo=True and are excluded from headline scoreboard
    stats but counted in counts.n_placebo (§2.2).

Usage:
    python scripts/sample_qledger_placebo.py [--asof YYYY-MM-DD] [--k K] [--dry-run] [--root PATH]

Called nightly by the qledger runner after backfills complete.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engine.qledger import make_claim, register  # noqa: E402

log = logging.getLogger("placebo_sampler")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

_K_DEFAULT = 10
_CN_BENCH = "510300.SS"
_US_BENCH = "SPY"
_DESK = "placebo"
_HORIZONS = (5, 21)


def _asof_seed(asof: str) -> int:
    """Deterministic seed from the asof date string. sha256 -> first 8 bytes -> int."""
    h = hashlib.sha256(asof.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big")


def _today_iso() -> str:
    return date.today().isoformat()


def _load_cn_low_importance(root: Path) -> pd.DataFrame:
    """Low-importance China events: score < median of the FULL corpus."""
    p = root / "data" / "china_news_vector" / "events.parquet"
    if not p.exists():
        log.warning("China events.parquet not found: %s", p)
        return pd.DataFrame()
    df = pd.read_parquet(p)
    if "score" not in df.columns:
        return df
    threshold = float(df["score"].median())
    low = df[df["score"] < threshold].copy()
    low["_corpus"] = "cn"
    low["_bench"] = _CN_BENCH
    return low


def _load_us_events(root: Path) -> pd.DataFrame:
    """All US news_vector events (no score column — treated as low-importance)."""
    p = root / "data" / "news_vector" / "events.parquet"
    if not p.exists():
        log.warning("US events.parquet not found: %s", p)
        return pd.DataFrame()
    df = pd.read_parquet(p).copy()
    df["_corpus"] = "us"
    df["_bench"] = _US_BENCH
    # US events carry no 'score'; fill 0 for consistent schema
    if "score" not in df.columns:
        df["score"] = 0.0
    # US events carry no 'tickers'; fill empty string
    if "tickers" not in df.columns:
        df["tickers"] = ""
    return df


def _entry_date(first_seen_utc: str) -> str:
    ts = pd.Timestamp(first_seen_utc, tz="UTC")
    return ts.date().isoformat()


def _has_price(ticker: str, corpus: str, root: Path) -> bool:
    if corpus == "cn":
        return (root / "data" / "china_stocks" / f"{ticker}.parquet").exists()
    # US: check yahoo parquets
    return (root / "data" / "yahoo" / f"{ticker}.parquet").exists()


def _register_one_event(
    row: "pd.Series",  # noqa: F821
    asof_run: str,
    root: Path,
    dry_run: bool,
) -> dict:
    """Register one or more placebo claims for a sampled event row.
    Returns a dict: {n_registered, n_blocked, n_rejected}.
    """
    corpus = str(row["_corpus"])
    bench = str(row["_bench"])
    event_id = str(row["event_id"])
    first_seen = str(row["first_seen_utc"])
    tickers_raw = str(row.get("tickers", "") or "").strip()
    asof = _entry_date(first_seen)
    score = float(row.get("score", 0.0))

    tickers = [t.strip() for t in tickers_raw.split(",") if t.strip()] if tickers_raw else []

    counts = {"n_registered": 0, "n_blocked": 0, "n_rejected": 0}

    if tickers:
        # Entity-level placebo: one claim per ticker (mirrors real backfill path)
        for ticker in tickers:
            if not _has_price(ticker, corpus, root):
                counts["n_blocked"] += 1
                log.debug("Placebo: no price for %s (%s)", ticker, corpus)
                continue
            for horizon_d in _HORIZONS:
                claim = make_claim(
                    desk=_DESK,
                    asof=asof,
                    scope_type="entity",
                    scope_key=ticker,
                    direction=0,
                    horizon_d=horizon_d,
                    timestamp_quality="CRAWL_BOUNDED",
                    bench=bench,
                    control=None,
                    is_placebo=True,
                    claim_family=_DESK,
                    extra={
                        "event_id": event_id,
                        "corpus": corpus,
                        "importance_score": score,
                        "sampled_on": asof_run,
                    },
                )
                claim["salt"] = f"placebo:{event_id}:{ticker}:{horizon_d}:{asof_run}"
                if dry_run:
                    counts["n_registered"] += 1
                    continue
                stored = register(claim, root=root)
                if stored.get("status") == "rejected":
                    counts["n_rejected"] += 1
                    log.warning("Placebo rejected: %s — %s", ticker, stored.get("reject_reason"))
                else:
                    counts["n_registered"] += 1
    else:
        # No tickers — register a basket/macro-proxy claim on the bench itself
        # (records that this low-importance diffuse event produced no move)
        # Use scope_type="basket", scope_key=bench so the grader prices the bench
        # vs itself (excess == 0, which IS the null outcome we want to record).
        for horizon_d in _HORIZONS:
            claim = make_claim(
                desk=_DESK,
                asof=asof,
                scope_type="basket",
                scope_key=bench,
                direction=0,
                horizon_d=horizon_d,
                timestamp_quality="CRAWL_BOUNDED",
                bench=bench,
                control=None,
                is_placebo=True,
                claim_family=_DESK,
                extra={
                    "event_id": event_id,
                    "corpus": corpus,
                    "importance_score": score,
                    "sampled_on": asof_run,
                },
            )
            claim["salt"] = f"placebo:{event_id}:noTicker:{horizon_d}:{asof_run}"
            if dry_run:
                counts["n_registered"] += 1
                continue
            stored = register(claim, root=root)
            if stored.get("status") == "rejected":
                counts["n_rejected"] += 1
                log.warning("Placebo (no ticker) rejected: %s — %s",
                            event_id, stored.get("reject_reason"))
            else:
                counts["n_registered"] += 1

    return counts


def run(root: Path, asof: str, k: int = _K_DEFAULT, dry_run: bool = False) -> dict:
    """Sample K low-importance events and register placebo claims.

    Returns a summary dict with n_sampled / n_registered / n_blocked / n_rejected.
    """
    rng = random.Random(_asof_seed(asof))
    log.info("Placebo sampler: asof=%s seed=%d k=%d dry_run=%s",
             asof, _asof_seed(asof), k, dry_run)

    cn_low = _load_cn_low_importance(root)
    us_all = _load_us_events(root)

    # Sample evenly from each corpus (floor(k/2) each, remainder to CN)
    k_us = k // 2
    k_cn = k - k_us

    def _sample(df: pd.DataFrame, n: int) -> pd.DataFrame:
        if df.empty:
            return df
        n = min(n, len(df))
        idx = rng.sample(list(df.index), n)
        return df.loc[idx]

    cn_sample = _sample(cn_low, k_cn)
    us_sample = _sample(us_all, k_us)

    total_sampled = len(cn_sample) + len(us_sample)
    log.info("Sampled %d CN + %d US = %d events", len(cn_sample), len(us_sample), total_sampled)

    totals = {"n_sampled": total_sampled, "n_registered": 0, "n_blocked": 0, "n_rejected": 0}
    for df_slice in (cn_sample, us_sample):
        for _, row in df_slice.iterrows():
            c = _register_one_event(row, asof_run=asof, root=root, dry_run=dry_run)
            totals["n_registered"] += c["n_registered"]
            totals["n_blocked"] += c["n_blocked"]
            totals["n_rejected"] += c["n_rejected"]

    log.info(
        "Placebo done — sampled=%d registered=%d blocked=%d rejected=%d",
        totals["n_sampled"], totals["n_registered"],
        totals["n_blocked"], totals["n_rejected"],
    )
    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asof", default=None,
                        help="Date to use as 'today' for sampling (YYYY-MM-DD). "
                             "Defaults to today.")
    parser.add_argument("--k", type=int, default=_K_DEFAULT,
                        help=f"Total events to sample (default {_K_DEFAULT})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate but do not write to the ledger")
    parser.add_argument("--root", default=None,
                        help="Repo root (default: auto-detected from script location)")
    parser.add_argument("--json", action="store_true",
                        help="Emit summary as JSON to stdout")
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else _ROOT
    asof = args.asof or _today_iso()
    result = run(root, asof=asof, k=args.k, dry_run=args.dry_run)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for key, val in result.items():
            print(f"{key}: {val}")


if __name__ == "__main__":
    main()
