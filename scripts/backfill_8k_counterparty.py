#!/usr/bin/env python3
"""GR3b — one-off, resumable backfill of 8-K counterparty / contract-amount extraction.

OFF THE RENDER PATH.  This is a manual catch-up run, not a nightly step: the nightly
lane (scripts/build_theme_addons.py -> enrich_contract_amounts(incremental=True)) keeps
reading only newly-filed 1.01/2.03 reports and is unaffected by anything here.

Why a backfill at all: every committed revision of material_8k_events.parquet carries a
null counterparty, because (a) the primary-document selector read the EDGAR submission
HEADER page instead of the 8-K body, (b) the fetched HTML was never stripped to prose, so
the amount and name regexes could not match across tag boundaries, and (c) the name leg
was gated behind the amount leg, so a filing with no parseable $ could never yield a name
even when one was there.  The 207 rows already marked extraction_ok=False were read under
those rules and must be RE-ATTEMPTED, which a plain `extraction_ok.isna()` mask can never
do -- hence the `enrich_rev` stamp that drives the backfill target set.

Resume story: interrupt at any point and re-run the same command.  Rows already stamped
with the current `_ENRICH_REV` drop out of the target set, and every document fetched so
far is served from data/edgar/_8k_doc_cache/, so a resumed run re-issues no request for
anything it has already seen.  The parquet is written after every chunk, so at most one
chunk of parse work is lost to an interrupt.

Usage:
    python3 scripts/backfill_8k_counterparty.py --months 24
    python3 scripts/backfill_8k_counterparty.py --months 24 --limit 200   # bounded probe
    python3 scripts/backfill_8k_counterparty.py --dry-run                 # count only
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.edgar_8k import (  # noqa: E402
    _ENRICH_REV,
    _EXHIBIT_CAP,
    _EXHIBIT_MAX_BYTES,
    PACE_S,
    enrich_contract_amounts,
)
from lib import config  # noqa: E402

log = logging.getLogger("backfill_8k_counterparty")

_ITEM_RE = r"1\.01|2\.03"


def _events_path() -> Path:
    return config.data_dir() / "edgar" / "material_8k_events.parquet"


def _scope(df: pd.DataFrame, window_days: int | None) -> pd.Series:
    """Rows the backfill considers in scope (1.01/2.03 inside the horizon)."""
    mask = df["items"].str.contains(_ITEM_RE, na=False)
    if window_days is not None:
        dates = pd.to_datetime(df["filing_date"], errors="coerce", utc=True)
        mask &= dates >= (pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=window_days))
    return mask


def _counts(df: pd.DataFrame, scope: pd.Series) -> dict[str, int]:
    """Yield counters for the in-scope slice, tolerating columns that do not exist yet."""
    sub = df[scope]

    def _nn(col: str) -> int:
        return int(sub[col].notna().sum()) if col in sub.columns else 0

    def _true(col: str) -> int:
        return int((sub[col] == True).sum()) if col in sub.columns else 0  # noqa: E712

    return {
        "rows": int(len(sub)),
        "counterparty_non_null": _nn("counterparty"),
        "amount_non_null": _nn("amount_usd"),
        "extraction_ok_true": _true("extraction_ok"),
        "extraction_ok_false": int((sub["extraction_ok"] == False).sum())  # noqa: E712
        if "extraction_ok" in sub.columns else 0,
        "stamped": int(pd.to_numeric(sub["enrich_rev"], errors="coerce").notna().sum())
        if "enrich_rev" in sub.columns else 0,
    }


def _render_table(before: dict, after: dict, stats: dict, window_days: int | None) -> str:
    """Markdown yield table for the PR body."""
    rows = [
        ("in-scope rows (1.01/2.03, trailing window)", before["rows"], after["rows"]),
        ("rows examined this run", "-", stats.get("targeted", 0)),
        ("filings read (doc fetched + parsed)", "-", stats.get("read", 0)),
        ("filings unreadable (retry-eligible)", "-", stats.get("unread", 0)),
        ("primary-only name hits", "-", stats.get("name_primary", 0)),
        ("exhibit-added name hits", "-", stats.get("name_exhibit", 0)),
        ("non-null counterparty (total)", before["counterparty_non_null"], after["counterparty_non_null"]),
        ("dollar-amount hits (amount_usd non-null)", before["amount_non_null"], after["amount_non_null"]),
        ("  of which from primary doc", "-", stats.get("amount_primary", 0)),
        ("  of which from an exhibit", "-", stats.get("amount_exhibit", 0)),
        ("extraction_ok True", before["extraction_ok_true"], after["extraction_ok_true"]),
        ("extraction_ok False", before["extraction_ok_false"], after["extraction_ok_false"]),
        ("rows stamped enrich_rev", before["stamped"], after["stamped"]),
    ]
    out = [
        f"| metric | before | after |",
        f"| --- | ---: | ---: |",
    ]
    out += [f"| {label} | {b} | {a} |" for label, b, a in rows]
    out += [
        "",
        f"Window: trailing {window_days} days. Exhibit policy: <= {_EXHIBIT_CAP} per filing, "
        f"<= {_EXHIBIT_MAX_BYTES} bytes each, consulted only when the primary doc leaves a leg unfilled.",
        f"Filings that consulted exhibits: {stats.get('filings_consulting_exhibits', 0)} · "
        f"exhibits read: {stats.get('exhibits_read', 0)} · "
        f"exhibit cap bound on: {stats.get('exhibit_cap_binds', 0)} filings "
        f"({stats.get('exhibits_skipped', 0)} exhibits unread) · "
        f"exhibits truncated at the byte cap: {stats.get('exhibit_truncated', 0)}",
        f"Fetches: {stats.get('fetch_ok', 0)} network · {stats.get('cache_hits', 0)} cache hits · "
        f"{stats.get('fetch_http_err', 0)} non-200 · {stats.get('fetch_exc', 0)} transport errors",
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--months", type=int, default=24, help="trailing horizon in months (default 24)")
    ap.add_argument("--all-history", action="store_true", help="ignore --months and process all rows")
    ap.add_argument("--limit", type=int, default=None, help="stop after this many rows total")
    ap.add_argument("--chunk", type=int, default=50, help="rows per parquet checkpoint (default 50)")
    ap.add_argument("--pace", type=float, default=PACE_S, help=f"min seconds between EDGAR requests (default {PACE_S})")
    ap.add_argument("--sample", type=int, default=20, help="random sample rows to print for review (default 20)")
    ap.add_argument("--seed", type=int, default=7, help="sample seed (default 7)")
    ap.add_argument("--dry-run", action="store_true", help="report the target count and exit")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    window_days = None if args.all_history else int(round(args.months * 365.25 / 12))

    path = _events_path()
    if not path.exists():
        log.error("no events parquet at %s", path)
        return 1
    df = pd.read_parquet(path)
    scope = _scope(df, window_days)
    before = _counts(df, scope)
    log.info("scope: %d rows in trailing %s days (%d already stamped at rev>=%d)",
             before["rows"], window_days, before["stamped"], _ENRICH_REV)

    if args.dry_run:
        print(_render_table(before, before, {}, window_days))
        return 0

    stats: dict = {}
    attempted: set[str] = set()
    processed = 0
    try:
        while True:
            remaining = args.limit - processed if args.limit is not None else None
            if remaining is not None and remaining <= 0:
                log.info("--limit %d reached", args.limit)
                break
            chunk = args.chunk if remaining is None else min(args.chunk, remaining)

            before_stats_targeted = stats.get("targeted", 0)
            df = enrich_contract_amounts(
                df, incremental=False, pace_s=args.pace,
                window_days=window_days, limit=chunk,
                skip_accessions=attempted, stats=stats,
            )
            n_this = stats.get("targeted", 0) - before_stats_targeted
            if n_this == 0:
                log.info("no targets left — backfill complete")
                break

            # Every row the chunk touched is off the table for this process, read or not:
            # an unreadable filing stays deliberately unstamped so a LATER run retries it,
            # and without this the same failures would re-fill the head of every chunk.
            attempted = set(stats.get("attempted_accessions", []))
            processed += n_this
            df.to_parquet(path)
            log.info("checkpoint: %d rows processed this run (%d read, %d unread)",
                     processed, stats.get("read", 0), stats.get("unread", 0))
    except KeyboardInterrupt:
        log.warning("interrupted — writing checkpoint; re-run the same command to resume")
        df.to_parquet(path)

    df.to_parquet(path)
    after = _counts(df, _scope(df, window_days))
    print()
    print(_render_table(before, after, stats, window_days))

    if args.sample and "counterparty" in df.columns:
        hits = df[_scope(df, window_days) & df["counterparty"].notna()]
        if not hits.empty:
            samp = hits.sample(n=min(args.sample, len(hits)), random_state=args.seed)
            print()
            print("| ticker | filed_at | counterparty | source |")
            print("| --- | --- | --- | --- |")
            for _, r in samp.iterrows():
                print(f"| {r['ticker']} | {r['filing_date']} | {r['counterparty']} | {r.get('counterparty_src')} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
