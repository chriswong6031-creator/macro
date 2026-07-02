"""scripts/sample_qledger_placebo.py — Daily placebo tape sampler (W1/B3, D3).

Spec excerpt (D3):
  "Daily, sample K random LOW-importance events and grade them through the
   identical pipeline. High-importance items must beat the placebo tape, not
   zero. Sample from the full accrual, not the displayed feed. Deterministic
   sampling seeded by date (no Date.now in configs) so reruns are idempotent."

W1 debt note (fixed here):
  The original sampler drew from all LOW-importance events without requiring a
  resolvable ticker, so 18/20 sampled placebos landed on the no-ticker path
  → scope_key == bench → excess ≡ 0. The counterfactual was measuring "zero"
  rather than a real entity-magnitude null distribution.

Fix (W1 placebo-strength, D3 bias correction):
  Sample preferentially from LOW-importance events that carry ≥1 ticker with
  local price coverage (data/china_stocks/<T>.parquet for CN; data/yahoo/<T>
  or the S&P-1500 breadth-cache / engine.ai_desk._close_series for US).  Fall
  back to no-ticker / uncovered events only when the day has fewer than K
  covered candidates; the fallback count is recorded in n_fallback so callers
  can audit the rate.

Design:
  - Samples K=10 events per run, split across BOTH corpora:
      * data/china_news_vector/events.parquet  (CN)
      * data/news_vector/events.parquet        (US)
    If a corpus has fewer than K events, all qualifying events are used.
  - "LOW-importance" = score < median of the FULL corpus (not just displayed
    feed).  US events.parquet has no `score` column; we treat all US events as
    low-importance (no importance filter).
  - Covered-ticker preference: within each corpus, the candidate pool is
    partitioned into covered (≥1 ticker with local price data) and uncovered
    (no tickers or all tickers missing price files).  We sample from covered
    first; once the covered pool is exhausted we draw from uncovered and
    increment n_fallback.
  - Ticker assignment for placebo: if the event carries covered tickers, we
    register ONE claim per covered ticker. If the event has no covered tickers
    (fallback path), we register a BASKET claim against the bench (the
    "diffuse event" path from D4 — the null-outcome is explicitly recorded
    rather than silently skipped).
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


def _has_price_cn(ticker: str, root: Path) -> bool:
    """True when the CN price layer covers this ticker."""
    return (root / "data" / "china_stocks" / f"{ticker}.parquet").exists()


def _has_price_us(ticker: str, root: Path) -> bool:
    """True when the US price layer covers this ticker.

    Reuses the same fallback chain as backfill_qledger_us._ticker_priceable
    (engine.ai_desk._close_series): yahoo → breadth cache.  We use a direct
    file check for yahoo (fast) and fall back to the close-series call only
    when the yahoo file is absent (avoids loading the breadth cache for names
    that are in yahoo).
    """
    if (root / "data" / "yahoo" / f"{ticker}.parquet").exists():
        return True
    # Breadth-cache fallback: reuse engine.ai_desk._close_series which already
    # has the memoized breadth frame.
    try:
        from engine.ai_desk import _close_series  # noqa: PLC0415 (deferred import)
        s = _close_series(ticker, root)
        return s is not None and not s.empty
    except Exception:  # noqa: BLE001
        return False


def _covered_tickers(tickers_raw: str, corpus: str, root: Path) -> list[str]:
    """Return the subset of tickers that have local price coverage."""
    tickers = [t.strip() for t in tickers_raw.split(",") if t.strip()]
    if corpus == "cn":
        return [t for t in tickers if _has_price_cn(t, root)]
    return [t for t in tickers if _has_price_us(t, root)]


def _has_any_covered(row: "pd.Series", corpus: str, root: Path) -> bool:  # noqa: F821
    """True when the event row has at least one ticker with local price coverage."""
    raw = str(row.get("tickers", "") or "").strip()
    if not raw:
        return False
    return bool(_covered_tickers(raw, corpus, root))


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
    """Compatibility shim — dispatches to the corpus-specific check."""
    if corpus == "cn":
        return _has_price_cn(ticker, root)
    return _has_price_us(ticker, root)


def _biased_sample(
    df: pd.DataFrame, n: int, rng: random.Random, corpus: str, root: Path
) -> tuple[pd.DataFrame, int]:
    """Sample n rows from df, preferring rows with covered tickers.

    Returns (sampled_df, n_fallback) where n_fallback is the number of sampled
    rows that landed on the no-covered-ticker fallback pool.
    """
    if df.empty or n <= 0:
        return df.iloc[:0], 0

    # Partition into covered (≥1 ticker with local price) and uncovered
    covered_mask = df.apply(lambda row: _has_any_covered(row, corpus, root), axis=1)
    covered = df[covered_mask]
    uncovered = df[~covered_mask]

    n_from_covered = min(n, len(covered))
    n_from_uncovered = n - n_from_covered

    chosen_idx: list = []
    n_fallback = 0

    if n_from_covered > 0:
        chosen_idx.extend(rng.sample(list(covered.index), n_from_covered))

    if n_from_uncovered > 0 and not uncovered.empty:
        n_draw = min(n_from_uncovered, len(uncovered))
        chosen_idx.extend(rng.sample(list(uncovered.index), n_draw))
        n_fallback = n_draw

    return df.loc[chosen_idx], n_fallback


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

    # Only register claims for tickers that have local price coverage; fall back
    # to the bench-basket path only when no covered ticker exists.
    covered = _covered_tickers(tickers_raw, corpus, root) if tickers_raw else []

    counts = {"n_registered": 0, "n_blocked": 0, "n_rejected": 0}

    if covered:
        # Entity-level placebo: one claim per covered ticker (mirrors real backfill)
        for ticker in covered:
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
                        "placebo_path": "covered_ticker",
                    },
                )
                claim["salt"] = f"placebo:{event_id}:{ticker}:{horizon_d}:{asof_run}"
                if dry_run:
                    counts["n_registered"] += 1
                    continue
                stored = register(claim, root=root)
                if stored.get("status") == "rejected":
                    counts["n_rejected"] += 1
                    log.warning("Placebo rejected: %s — %s", ticker,
                                stored.get("reject_reason"))
                else:
                    counts["n_registered"] += 1
    else:
        # No covered tickers — register a basket/macro-proxy claim on the bench
        # (records that this low-importance diffuse event produced no move).
        # Use scope_type="basket", scope_key=bench so the grader prices the bench
        # vs itself (excess == 0, which IS the null outcome we want to record).
        # This is the fallback path; n_fallback in the outer summary tracks it.
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
                    "placebo_path": "fallback_no_ticker",
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

    # Count uncovered tickers from the raw list (had tickers but none covered)
    if tickers_raw and not covered:
        all_tickers = [t.strip() for t in tickers_raw.split(",") if t.strip()]
        counts["n_blocked"] += len(all_tickers)
    elif tickers_raw:
        all_tickers = [t.strip() for t in tickers_raw.split(",") if t.strip()]
        uncovered_cnt = len(all_tickers) - len(covered)
        if uncovered_cnt > 0:
            counts["n_blocked"] += uncovered_cnt

    return counts


def run(root: Path, asof: str, k: int = _K_DEFAULT, dry_run: bool = False) -> dict:
    """Sample K low-importance events (ticker-bearing preferred) and register
    placebo claims.

    Returns a summary dict with n_sampled / n_registered / n_blocked /
    n_rejected / n_fallback (events that landed on the no-covered-ticker path).
    """
    rng = random.Random(_asof_seed(asof))
    log.info("Placebo sampler: asof=%s seed=%d k=%d dry_run=%s",
             asof, _asof_seed(asof), k, dry_run)

    cn_low = _load_cn_low_importance(root)
    us_all = _load_us_events(root)

    # Sample evenly from each corpus (floor(k/2) each, remainder to CN)
    k_us = k // 2
    k_cn = k - k_us

    cn_sample, cn_fallback = _biased_sample(cn_low, k_cn, rng, "cn", root)
    us_sample, us_fallback = _biased_sample(us_all, k_us, rng, "us", root)

    total_sampled = len(cn_sample) + len(us_sample)
    total_fallback = cn_fallback + us_fallback
    log.info(
        "Sampled %d CN (fallback=%d) + %d US (fallback=%d) = %d events",
        len(cn_sample), cn_fallback,
        len(us_sample), us_fallback,
        total_sampled,
    )

    totals: dict = {
        "n_sampled": total_sampled,
        "n_registered": 0,
        "n_blocked": 0,
        "n_rejected": 0,
        "n_fallback": total_fallback,  # events where no covered ticker was found
    }
    for df_slice in (cn_sample, us_sample):
        for _, row in df_slice.iterrows():
            c = _register_one_event(row, asof_run=asof, root=root, dry_run=dry_run)
            totals["n_registered"] += c["n_registered"]
            totals["n_blocked"] += c["n_blocked"]
            totals["n_rejected"] += c["n_rejected"]

    log.info(
        "Placebo done — sampled=%d registered=%d blocked=%d rejected=%d fallback=%d",
        totals["n_sampled"], totals["n_registered"],
        totals["n_blocked"], totals["n_rejected"],
        totals["n_fallback"],
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
