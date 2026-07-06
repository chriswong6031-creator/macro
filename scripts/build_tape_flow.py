"""scripts/build_tape_flow.py — T2a signed tape-flow feature builder.

Fetches trade+NBBO for one or more (root, date) pairs from ThetaData Terminal,
aggregates into signed-flow features (engine/tape_flow.aggregate_day), and
writes per-root parquets to the tape-flow store.

## Bulk endpoint (RESOLVED live probe 2026-07-04)
trade_quote DOES accept wildcard expiration+strike when right is specified.
Two requests per root-day: right=call + right=put. Each is streamed and
aggregated on the fly; raw trade rows are DISCARDED after aggregation (T2a law).

## Coverage restriction
Bulk wildcard requires right=call|put (not right=*). Coverage is the FULL chain
for each right — all expirations, all strikes. This is not a restriction vs the
per-contract approach; it covers more contracts with fewer requests.

## Storage plane decision (math below)
Sample measurement: KRE, 2026-06-30, ~5,200 total trade+NBBO rows.
Feature row after aggregation: ~50 columns × ~8 bytes each ≈ 400 bytes per row.
Projected at 400 roots × 252 sessions/yr × 3 years ≈ 302,400 rows.
Parquet compressed: ~400 bytes/row × 0.2 compression ratio ≈ 24 MB total.
Verdict: WELL UNDER the ~30 MB git budget threshold → git storage (data/tape_flow/).

.gitignore: data/tape_flow/ is NOT excluded (small feature-only parquets, ≤30 MB).
R2 registration: NOT needed at this scale. Revisit if universe exceeds 800 names or
  history extends to 12y (would then be ~800 × 252 × 12 × 80 bytes ≈ ~193 MB — at
  that point register as R2 artifact like data/thetadata_eod/).

## Usage
  # Single date
  python -m scripts.build_tape_flow --root KRE --date 2026-06-30

  # Date range
  python -m scripts.build_tape_flow --root KRE --start 2026-01-02 --end 2026-06-30

  # Universe run (options_universe.gex_symbols() resolver)
  python -m scripts.build_tape_flow --universe --start 2026-01-02 --end 2026-06-30

  # Dry run (no writes)
  python -m scripts.build_tape_flow --root KRE --date 2026-06-30 --dry-run

## Notes
- NO daily.yml wiring in this PR (the T1 backfill owns the terminal right now).
  Historical mass-run is a follow-up ops task.
- Sequential per-root-day; one ThreadPoolExecutor request per right (2 concurrent
  per root-day) within the terminal's 8-concurrent ceiling.
- INERT on terminal unreachable (returns exit 1, writes nothing, logs one warning).
- BOTH-RIGHTS-OR-NO-ROW law (house empty-vs-failed): the collector returns None
  on FAILURE (unreachable / stream truncated) and an EMPTY DataFrame on
  SUCCESS-with-no-trades. build_one writes a day row ONLY if BOTH the call and
  put legs succeeded (neither is None). A failed leg → no row (a partial day must
  never be persisted as if complete).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator

import pandas as pd

from engine import tape_flow as tf
from lib import config

log = logging.getLogger(__name__)

# ── store path ────────────────────────────────────────────────────────────────

def _store_path(root: str) -> Path:
    """Per-root parquet path: data/tape_flow/{ROOT}.parquet"""
    return config.data_dir() / "tape_flow" / f"{root.upper()}.parquet"


# ── universe resolver ─────────────────────────────────────────────────────────

def _resolve_universe() -> list[str]:
    """options_universe.gex_symbols() + common ETF anchors, deduped."""
    from engine.options_universe import gex_symbols
    basket = gex_symbols()
    # Common ETF/index anchors always included
    anchors = ["SPY", "QQQ", "IWM", "GLD", "SLV", "TLT", "HYG", "XLF", "XLE",
               "XLU", "XLK", "XLV", "XLI", "XLB", "XLY", "XLP", "XLRE",
               "KRE", "SMH", "XBI", "ARKK"]
    seen: dict[str, None] = {}
    for t in anchors + basket:
        seen.setdefault(t.upper(), None)
    return list(seen)


# ── date helpers ──────────────────────────────────────────────────────────────

def _trading_days(start: date, end: date) -> list[date]:
    """Return Mon-Fri dates in [start, end] as a proxy for trading days.

    Accuracy: excludes weekends; does NOT filter US market holidays.
    A future enhancement can use a proper trading calendar.
    """
    out = []
    d = start
    while d <= end:
        if d.weekday() < 5:   # 0=Mon … 4=Fri
            out.append(d)
        d += timedelta(days=1)
    return out


# ── per-root-day fetch ────────────────────────────────────────────────────────

def _fetch_both_rights(root: str, trade_date: date) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """Fetch calls+puts concurrently via bulk_trade_quote (2 parallel requests).

    bulk_trade_quote uses wildcard expiration+strike, covering the full chain
    for each right in a single streamed request. Two requests per root-day.
    Within the terminal's 8-concurrent ceiling (WINDOW_WORKERS=6 leaves headroom).
    """
    from collectors import thetadata as td

    calls_df = puts_df = None
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_call = pool.submit(td.bulk_trade_quote, root, "call", trade_date, trade_date)
        fut_put  = pool.submit(td.bulk_trade_quote, root, "put",  trade_date, trade_date)
        calls_df = fut_call.result()
        puts_df  = fut_put.result()
    return calls_df, puts_df


# ── OI and greeks helpers ─────────────────────────────────────────────────────

def _load_oi_prev(root: str, trade_date: date) -> pd.DataFrame | None:
    """Load OI for t-1 (the prior business day) from the thetadata_eod store.

    OI timing law: OI published at ~06:30 ET represents EOD t-1 positions.
    For day-t, we use OI from date t-1 in the store. Missing → None.

    Uses thetadata_store.chain(date=t-1) which returns raw point-in-time OI
    for that date (NOT shifted — chain() returns raw values). The caller
    (aggregate_day) receives this as oi_prev and uses it as oi[t-1].
    """
    try:
        from engine import thetadata_store as ts
        d_prev = trade_date - timedelta(days=1)
        # Walk back up to 5 calendar days to find the prior trading day's OI
        for _ in range(5):
            chain = ts.chain(str(d_prev), root.upper())
            if not chain.empty and "open_interest" in chain.columns:
                oi_cols = [c for c in ("expiration", "strike", "right", "open_interest")
                           if c in chain.columns]
                return chain[oi_cols].dropna(subset=["open_interest"])
            d_prev -= timedelta(days=1)
        return None
    except Exception as e:  # noqa: BLE001
        log.debug("oi_prev load failed for %s %s: %s", root, trade_date, e)
        return None


def _load_greeks_chain(root: str, trade_date: date) -> pd.DataFrame | None:
    """Load EOD greeks chain for trade_date from the thetadata_eod store.

    Returns None gracefully when greeks are not yet backfilled (pre-2017 typical).
    """
    try:
        from engine import thetadata_store as ts
        chain = ts.chain(str(trade_date), root.upper())
        if chain.empty:
            return None
        return chain
    except Exception as e:  # noqa: BLE001
        log.debug("greeks chain load failed for %s %s: %s", root, trade_date, e)
        return None


# ── parquet I/O ───────────────────────────────────────────────────────────────

def _load_existing(root: str) -> pd.DataFrame:
    """Load existing per-root parquet; return empty DataFrame if not yet present."""
    path = _store_path(root)
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception as e:  # noqa: BLE001
        log.warning("tape_flow: could not read %s — starting fresh: %s", path, e)
        return pd.DataFrame()


def _write_parquet(root: str, df: pd.DataFrame, dry_run: bool = False) -> Path:
    """Write per-root parquet (atomic tmp→rename). Returns path."""
    path = _store_path(root)
    if dry_run:
        log.info("tape_flow: [DRY RUN] would write %d rows to %s", len(df), path)
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.rename(path)
    log.info("tape_flow: wrote %d rows to %s", len(df), path)
    return path


# ── core per-root-day worker ──────────────────────────────────────────────────

def build_one(root: str, trade_date: date, dry_run: bool = False) -> dict | None:
    """Fetch trade+NBBO, aggregate features, upsert to store.

    Returns the feature dict (without z-scores), or None on error.
    All raw trade rows are discarded after aggregation (T2a law).
    """
    from collectors import thetadata as td

    if not td.reachable():
        log.warning("tape_flow: terminal not reachable — skip %s %s", root, trade_date)
        return None

    t0 = time.perf_counter()

    # Fetch calls + puts (two parallel requests)
    try:
        calls_df, puts_df = _fetch_both_rights(root, trade_date)
    except Exception as e:  # noqa: BLE001
        log.warning("tape_flow: fetch failed for %s %s: %s", root, trade_date, e)
        return None

    # House empty-vs-failed law: the collector returns None on FAILURE
    # (terminal unreachable / stream truncated) and an EMPTY DataFrame on
    # SUCCESS-with-no-trades. A day row is a complete both-rights aggregate;
    # writing one when a right's fetch FAILED would persist a partial day as if
    # it were complete (the KRE 2026-06-30 puts-only bug). Require BOTH legs to
    # have succeeded (neither is None). Empty-but-successful legs are fine.
    if calls_df is None or puts_df is None:
        failed = []
        if calls_df is None:
            failed.append("call")
        if puts_df is None:
            failed.append("put")
        log.warning(
            "tape_flow: %s %s — %s leg(s) FAILED (None); refusing to write a "
            "partial day (both-rights-or-no-row law) — skip",
            root, trade_date, "+".join(failed))
        return None

    n_calls = len(calls_df)
    n_puts  = len(puts_df)
    log.info("tape_flow: %s %s — %d call rows, %d put rows (%.1fs)",
             root, trade_date, n_calls, n_puts, time.perf_counter() - t0)

    if n_calls == 0 and n_puts == 0:
        log.info("tape_flow: no trade data for %s %s (both legs empty-successful) — skip", root, trade_date)
        return None

    # Load oi[t-1] and greeks chain for this date
    oi_prev    = _load_oi_prev(root, trade_date)
    greeks_chain = _load_greeks_chain(root, trade_date)

    # Aggregate — raw rows discarded after this call returns
    feature_row = tf.aggregate_day(
        calls=calls_df,
        puts=puts_df,
        trade_date=trade_date,
        root=root,
        oi_prev=oi_prev,
        greeks_chain=greeks_chain,
    )

    # Explicitly release raw trade DataFrames now (T2a discard law)
    del calls_df, puts_df

    log.info("tape_flow: %s %s — aggregated: n_trades=%s, net_signed_premium=%s",
             root, trade_date, feature_row.get("n_trades"), feature_row.get("net_signed_premium"))

    # Upsert to store
    existing = _load_existing(root)
    updated = tf.upsert_feature_row(existing, feature_row)
    _write_parquet(root, updated, dry_run=dry_run)

    return feature_row


# ── main ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="T2a signed tape-flow feature builder (per-name daily aggregates)")
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--root", metavar="ROOT",
                     help="Single option root (e.g. KRE)")
    grp.add_argument("--universe", action="store_true",
                     help="Run all roots from options_universe resolver")

    date_grp = parser.add_mutually_exclusive_group()
    date_grp.add_argument("--date", metavar="YYYY-MM-DD",
                          help="Single trading date")
    date_grp.add_argument("--start", metavar="YYYY-MM-DD",
                          help="Start date (use with --end)")

    parser.add_argument("--end", metavar="YYYY-MM-DD",
                        help="End date (inclusive, use with --start)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Plan but do not write any parquets")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="DEBUG logging")

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Resolve roots
    if args.root:
        roots = [args.root.upper()]
    elif args.universe:
        roots = _resolve_universe()
    else:
        parser.error("Provide --root ROOT or --universe")
        return 1  # unreachable

    # Resolve dates
    if args.date:
        dates = [datetime.strptime(args.date, "%Y-%m-%d").date()]
    elif args.start:
        start = datetime.strptime(args.start, "%Y-%m-%d").date()
        end   = datetime.strptime(args.end,   "%Y-%m-%d").date() if args.end else date.today()
        dates = _trading_days(start, end)
    else:
        parser.error("Provide --date or --start [--end]")
        return 1  # unreachable

    log.info("tape_flow: %d root(s), %d date(s), dry_run=%s",
             len(roots), len(dates), args.dry_run)

    n_ok = n_skip = n_err = 0
    for root in roots:
        for trade_date in dates:
            try:
                result = build_one(root, trade_date, dry_run=args.dry_run)
                if result is None:
                    n_skip += 1
                else:
                    n_ok += 1
            except Exception as e:  # noqa: BLE001
                log.error("tape_flow: unhandled error for %s %s: %s", root, trade_date, e)
                n_err += 1

    log.info("tape_flow: done — ok=%d skip=%d err=%d", n_ok, n_skip, n_err)
    return 0 if n_err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
