"""scripts/backfill_options_flow.py — historical backfill of data/options_flow/summary_<KEY>.parquet.

Iterates day-files in the local raw-store (data/massive_options_day/ or
RAW_STORE_DIR env override), computes MAGNITUDE-ONLY columns from the daily
per-contract aggregate feedstock, and upserts idempotently.

WHY MAGNITUDE-ONLY
==================
The raw store (data/massive_options_day/*.parquet) contains ONE row per
option contract per session — a DAILY aggregate, not intraday minute data.
engine/options_flow.sign_volume() derives net signed direction from the
MINUTE-OVER-MINUTE close tick (shift within a ticker). With one row per
contract, shift() always returns NaN, so the tick collapses to 0 and
net_premium_mn would be stored as literal 0.0 — not NaN — which poisons
every trailing-window baseline that reads it (flare_persistence T2 witness,
build_flow_leaders net_premium_mn inflection history).

VALID (computable from daily aggregates):
  volume, premium_mn, pc_ratio, zerodte_share

INVALID (always collapse to 0 or meaningless without minute ticks / greeks):
  net_premium_mn, signed_pc, gamma_flow_bn, delta_flow_mn,
  assumed_gex_bn, fresh_contracts, net_doi, doi_pc

All INVALID columns are stored as NaN (explicit honest absence). Consumers
that dropna() will skip them cleanly. 0.0 is banned as a sentinel value
for "not computable".

OVERWRITE SEMANTICS
===================
Uses store.upsert(overwrite_overlap=True) so that a re-run with the corrected
NaN values REPLACES any prior run that may have stored 0.0 (the backfill now
forces the corrected value into the date-range it owns).

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

import numpy as np
import pandas as pd

from engine.options_flow import sign_volume
from engine.options_universe import gex_symbols
from lib import config, procutil, store

log = logging.getLogger(__name__)

# Columns we CAN compute honestly from daily per-contract aggregates
MAGNITUDE_KEYS = ("volume", "premium_mn", "pc_ratio", "zerodte_share")

# Columns that REQUIRE minute-tick signing or per-contract greeks + OI snapshots.
# These are stored as NaN (explicit honest absence) for the backfill path.
# DO NOT store 0.0 — that value poisons trailing-window baselines.
SIGNED_KEYS = (
    "net_premium_mn", "signed_pc", "gamma_flow_bn", "delta_flow_mn",
    "assumed_gex_bn", "fresh_contracts", "net_doi", "doi_pc",
)

# spot is also NaN — not available from the raw flatfile store
SUMMARY_KEYS = ("spot",) + MAGNITUDE_KEYS + SIGNED_KEYS

_CONTRACT_MULT = 100.0

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
    """Return True if a VALID backfill row exists for this date.

    Returns False (forcing an overwrite) if:
    - The date is not in the index at all.
    - The row has net_premium_mn == 0.0 (sign-collapse sentinel from a prior
      buggy run; must be replaced with NaN via overwrite_overlap=True).
    """
    existing = store.read("options_flow", f"summary_{sym}")
    if existing is None or existing.empty:
        return False
    ts = pd.Timestamp(d)
    if ts not in existing.index:
        return False
    # Detect the buggy 0.0 sentinel: a prior run stored sign-collapsed zeros.
    # overwrite_overlap=True in backfill() will fix them when we return False here.
    row = existing.loc[[ts]]
    if "net_premium_mn" in row.columns:
        v = row["net_premium_mn"].iloc[0]
        if v == 0.0 and not pd.isna(v):
            log.debug("backfill: %s %s has 0.0 net_premium_mn — will overwrite", sym, d)
            return False
    return True


def _compute_magnitude_row(sym: str, d: date, day_df: pd.DataFrame) -> pd.DataFrame | None:
    """Compute MAGNITUDE-ONLY summary columns from daily per-contract data.

    Uses sign_volume() for per-contract aggregation (the vol/premium/expiry
    values it produces are correct even from daily data; only signed_vol
    collapses to 0, which we do NOT store).

    Returns a 1-row DataFrame indexed by d, with:
      - MAGNITUDE_KEYS filled with real values
      - SIGNED_KEYS stored as NaN (honest absence, not 0.0)
      - spot stored as NaN (not available from the flatfile store)

    Returns None if aggregation yields no data.
    """
    # sign_volume aggregates per-contract; vol/premium/expiry/is_call/strike
    # are valid sums/firsts. signed_vol is 0 for daily data — we discard it.
    agg = sign_volume(day_df)
    if agg is None or agg.empty:
        return None

    asof_ts = pd.Timestamp(d)
    tot_vol = float(agg["vol"].sum())
    if tot_vol == 0:
        return None

    # --- MAGNITUDE (valid from daily aggregates) ---
    prem = float(agg["premium"].sum())
    premium_mn = round(prem / 1e6, 2)

    calls = agg[agg["is_call"]]
    puts = agg[~agg["is_call"]]
    cv = float(calls["vol"].sum())
    pv = float(puts["vol"].sum())
    pc_ratio = round(pv / cv, 2) if cv > 0 else None

    zerodte_vol = float(
        agg.loc[agg["expiry"].dt.normalize() == asof_ts.normalize(), "vol"].sum()
    )
    zerodte_share = round(zerodte_vol / tot_vol, 3)

    # --- BUILD THE ROW ---
    # Signed / greeks / OI columns are EXPLICITLY NaN (not 0.0)
    row: dict[str, object] = {
        "spot": None,
        "volume": int(tot_vol),
        "premium_mn": premium_mn,
        "net_premium_mn": None,    # requires minute tick-rule signing → NaN
        "pc_ratio": pc_ratio,
        "signed_pc": None,         # requires minute tick-rule signing → NaN
        "zerodte_share": zerodte_share,
        "gamma_flow_bn": None,     # requires greeks OI snapshot → NaN
        "delta_flow_mn": None,     # requires greeks OI snapshot → NaN
        "assumed_gex_bn": None,    # requires greeks OI snapshot → NaN
        "fresh_contracts": None,   # requires OI snapshot → NaN
        "net_doi": None,           # requires OI day-over-day snapshot → NaN
        "doi_pc": None,            # requires OI day-over-day snapshot → NaN
    }

    sdf = pd.DataFrame({k: [row[k]] for k in SUMMARY_KEYS}, index=[asof_ts])
    return sdf


def backfill(since: date, until: date, syms: set[str]) -> dict[str, int]:
    """Run the backfill. Returns {sym: n_new_rows_written}.

    Uses overwrite_overlap=True so that a corrected re-run (e.g., fixing a prior
    run that stored 0.0 net_premium_mn) forces the new NaN values to win over
    the previously stored 0.0 values.
    """
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
            sdf = _compute_magnitude_row(sym, d, msub)
            if sdf is None:
                continue
            try:
                # overwrite_overlap=True: the corrected NaN values overwrite any
                # prior 0.0 values that may have been stored by an earlier run.
                store.upsert("options_flow", f"summary_{sym}", sdf,
                             outlier_col=None, overwrite_overlap=True)
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
