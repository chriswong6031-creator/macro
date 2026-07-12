"""scripts/backfill_options_flow.py — historical backfill of data/options_flow/summary_<KEY>.parquet.

Iterates day-files in the local raw-store (data/massive_options_day/ or
RAW_STORE_DIR env override), re-uses engine/options_flow.build_flow() EXACTLY
(import, not reimplementation — byte-identical rows for the same input), and
upserts the per-ticker summary parquets idempotently (dates already present in
the store are skipped per ticker).

Memory: streams ONE day-file at a time; no multi-GB load.

Schema variants handled:
  • 2026+: underlying column is present (already OCC-parsed).
  • Older: underlying column absent — OCC symbol parsed on the fly.

Usage:
    python -m scripts.backfill_options_flow [--since 2026-01-02] [--until 2026-07-01]

Env:
    RAW_STORE_DIR   override the raw-parquet root (default: <repo>/data/massive_options_day)

Ends with lib.procutil.hard_exit(0) to bypass the pyarrow exit-deadlock.
"""
from __future__ import annotations

import argparse
import glob
import logging
import os
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from engine import options_flow as of
from engine.options_universe import gex_symbols
from lib import config, procutil, store

log = logging.getLogger(__name__)

SUMMARY_KEYS = (
    "spot", "volume", "premium_mn", "net_premium_mn", "pc_ratio", "signed_pc",
    "zerodte_share", "gamma_flow_bn", "delta_flow_mn", "assumed_gex_bn",
    "fresh_contracts", "net_doi", "doi_pc",
)

# OCC regex for fallback parsing when `underlying` column is absent
_OCC_RE = re.compile(r"^O:([A-Z]+)\d{6}[CP]\d{8}$")


def _raw_store_root() -> Path:
    """Root of the local cached-flatfile store (env-overridable)."""
    env = os.environ.get("RAW_STORE_DIR")
    if env:
        return Path(env)
    return config.ROOT / "data" / "massive_options_day"


def _discover_dates(root: Path, since: date, until: date) -> list[tuple[date, Path]]:
    """Return sorted (session_date, parquet_path) pairs within [since, until].

    Selection rule when multiple files share a date:
      _all   > _u392_   > any other tag
    (broader universe preferred; _all is the full-market file built after merge).
    """
    pattern = str(root / "*" / "*" / "*.parquet")
    date_files: dict[date, list[tuple[int, Path]]] = defaultdict(list)

    for f in glob.glob(pattern):
        base = Path(f).name
        m = re.match(r"(\d{4}-\d{2}-\d{2})_(.*?)\.parquet$", base)
        if not m:
            continue
        try:
            d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            continue
        if d < since or d > until:
            continue
        tag = m.group(2)
        # Priority: _all = 2, u392 prefix = 1, other = 0
        if tag == "all":
            pri = 2
        elif tag.startswith("u392"):
            pri = 1
        else:
            pri = 0
        date_files[d].append((pri, Path(f)))

    result: list[tuple[date, Path]] = []
    for d, choices in sorted(date_files.items()):
        # pick the highest priority; if tied, largest file (more data)
        choices_sorted = sorted(choices, key=lambda t: (t[0], os.path.getsize(t[1])),
                                reverse=True)
        result.append((d, choices_sorted[0][1]))
    return result


def _ensure_underlying(df: pd.DataFrame) -> pd.DataFrame:
    """Add/reconstruct `underlying` from OCC ticker when the column is absent
    (2024–early-2025 schema variant). No-op if already present."""
    if "underlying" in df.columns:
        return df
    # vectorised extract of the root symbol from O:<SYM>YYMMDD[CP]XXXXXXXXX
    ex = df["ticker"].str.extract(_OCC_RE)
    df = df.copy()
    df["underlying"] = ex[0]
    return df


def _load_day(path: Path, syms: set[str]) -> pd.DataFrame:
    """Load one day-file, ensure OCC cols present, filter to our universe."""
    try:
        df = pd.read_parquet(path)
    except Exception as e:  # noqa: BLE001 — corrupt file → skip
        log.warning("backfill: could not read %s: %s", path, e)
        return pd.DataFrame()

    df = _ensure_underlying(df)

    # Filter to our universe
    df = df[df["underlying"].isin(syms)]
    if df.empty:
        return df

    # Ensure OCC-derived columns exist (expiry, is_call, strike) — they should
    # be present in all cached files, but guard just in case.
    missing_occ = {"expiry", "is_call", "strike"} - set(df.columns)
    if missing_occ:
        log.warning("backfill: %s missing OCC cols %s — skipping", path.name, missing_occ)
        return pd.DataFrame()

    # Ensure expiry is datetime (some older files store it differently)
    if not pd.api.types.is_datetime64_any_dtype(df["expiry"]):
        df = df.copy()
        df["expiry"] = pd.to_datetime(df["expiry"], errors="coerce")

    return df.reset_index(drop=True)


def _already_present(sym: str, d: date) -> bool:
    """Return True if this date is already in the stored summary for sym."""
    existing = store.read("options_flow", f"summary_{sym}")
    if existing is None or existing.empty:
        return False
    ts = pd.Timestamp(d)
    return ts in existing.index


def _extract_summary_row(sym: str, d: date, minute_df: pd.DataFrame) -> pd.DataFrame | None:
    """Build_flow → extract SUMMARY_KEYS → return 1-row DataFrame. None if not available."""
    try:
        payload = of.build_flow(sym, minute_df, None, None, d)
    except Exception as e:  # noqa: BLE001
        log.warning("backfill: build_flow %s %s failed: %s", sym, d, e)
        return None

    if not payload.get("available"):
        return None

    dealer = payload.get("dealer") or {}
    newpos = payload.get("new_positions") or {}
    pos = payload.get("positioning") or {}
    srow = {}
    for k in SUMMARY_KEYS:
        if k in payload:
            srow[k] = payload[k]
        elif k in dealer:
            srow[k] = dealer[k]
        elif k in newpos:
            srow[k] = newpos[k]
        elif k in pos:
            srow[k] = pos[k]
        else:
            srow[k] = None

    sdf = pd.DataFrame({k: [srow[k]] for k in SUMMARY_KEYS},
                       index=[pd.Timestamp(d)])
    return sdf


def backfill(since: date, until: date, syms: set[str]) -> dict[str, int]:
    """Run the backfill. Returns {sym: n_new_rows_written}."""
    root = _raw_store_root()
    log.info("backfill: raw store = %s", root)
    day_files = _discover_dates(root, since, until)
    log.info("backfill: found %d day-files in [%s .. %s]", len(day_files), since, until)

    counts: dict[str, int] = {s: 0 for s in syms}
    skipped = 0

    for d, path in day_files:
        log.info("backfill: processing %s  (%s)", d, path.name)
        day_df = _load_day(path, syms)
        if day_df.empty:
            log.info("backfill:   no data after filter — skipping %s", d)
            continue

        covered = set(day_df["underlying"].dropna().unique()) & syms

        for sym in sorted(covered):
            if _already_present(sym, d):
                skipped += 1
                continue
            msub = day_df[day_df["underlying"] == sym]
            sdf = _extract_summary_row(sym, d, msub)
            if sdf is None:
                continue
            try:
                store.upsert("options_flow", f"summary_{sym}", sdf, outlier_col=None)
                counts[sym] += 1
            except Exception as e:  # noqa: BLE001
                log.warning("backfill: upsert %s %s failed: %s", sym, d, e)

        log.info("backfill:   %s — %d names written, %d already-present skips (cumulative)",
                 d, sum(1 for s in covered if counts.get(s, 0) > 0), skipped)

    total = sum(counts.values())
    log.info("backfill: DONE — %d new rows across %d tickers (%d existing skipped)",
             total, len([s for s, c in counts.items() if c > 0]), skipped)
    return counts


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-01-02",
                    help="Start date inclusive (YYYY-MM-DD)")
    ap.add_argument("--until", default="2026-07-01",
                    help="End date inclusive (YYYY-MM-DD)")
    args = ap.parse_args()

    since = datetime.strptime(args.since, "%Y-%m-%d").date()
    until = datetime.strptime(args.until, "%Y-%m-%d").date()

    cfg = config.load()
    gex_cfg = (cfg.get("polygon", {}) or {}).get("gex")
    syms = set(gex_symbols(gex_cfg))
    if not syms:
        log.warning("backfill: no universe configured — exiting")
        return 1

    log.info("backfill: universe = %d underlyings, range %s .. %s", len(syms), since, until)
    backfill(since, until, syms)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
