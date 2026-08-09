#!/usr/bin/env python3
"""Fail when a stable universe key lacks a valid price-vendor boundary alias.

Universe, page and ledger keys are intentionally stable across ticker changes.  A
vendor can nevertheless move the underlying history to a different symbol.  The
only supported seam is ``lib.ticker_aliases``: fetch under the vendor symbol and
store under the stable membership key.  This guard proves that every unlisted
universe key resolves to a currently listed vendor symbol and that the vendor key
has not also leaked into the universe as a duplicate company.

This is deliberately not a company-identity mapper.  Historical filings and
point-in-time membership keep the symbols they actually carried.
"""
from __future__ import annotations

import glob
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import config, ticker_aliases  # noqa: E402

_UNIVERSES = (
    ("sp500", "breadth"),
    ("sp400", "midcap_breadth"),
    ("sp600", "smallcap_breadth"),
)


def _latest_directory() -> tuple[set[str], str] | tuple[None, None]:
    files = sorted(glob.glob(str(
        config.data_dir() / "symbol_directory" / "snapshots" / "*.parquet"
    )))
    if not files:
        return None, None
    frame = pd.read_parquet(files[-1])
    return set(frame["symbol"].astype(str).str.upper()), Path(files[-1]).name


def is_listed(ticker: str, listed: set[str]) -> bool:
    """Directory membership with the repo's class-share spellings tolerated."""
    value = str(ticker).strip().upper()
    if value in listed or value.replace("-", ".") in listed:
        return True
    base = re.sub(r"[.-][A-Z]$", "", value)
    return base != value and base in listed


def _members() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for name, subdir in _UNIVERSES:
        path = config.data_dir() / subdir / "constituents.parquet"
        if path.exists():
            out[name] = {str(value).strip().upper()
                         for value in pd.read_parquet(path).index}
    return out


def check_alias_contract(listed: set[str], snapshot: str,
                         universes: dict[str, set[str]]) -> int:
    """Alias values are listed vendor symbols and never second universe keys."""
    bad = 0
    all_members = set().union(*universes.values()) if universes else set()
    aliases = ticker_aliases.YAHOO_FETCH_ALIASES
    vendor_values = list(aliases.values())
    if len(vendor_values) != len(set(vendor_values)):
        print("::error title=duplicate ticker alias target::"
              "two stable membership keys resolve to one vendor symbol", flush=True)
        bad += 1
    for stable, vendor in aliases.items():
        if stable == vendor:
            print(f"::error title=identity ticker alias::{stable} maps to itself", flush=True)
            bad += 1
        if not is_listed(vendor, listed):
            print(f"::error title=vendor alias is not listed::{stable} -> {vendor}, but "
                  f"{vendor} is absent from {snapshot}", flush=True)
            bad += 1
        if vendor in all_members:
            print(f"::error title=vendor symbol leaked into universe::{vendor} is the "
                  f"fetch alias for stable key {stable}, but both are universe members; "
                  "that mints two stores for one company", flush=True)
            bad += 1
    return bad


def check_universe_coverage(listed: set[str], snapshot: str,
                            universes: dict[str, set[str]]) -> int:
    """Every stable key is listed itself or resolves to a listed vendor symbol."""
    bad = 0
    for name, members in universes.items():
        missing: list[str] = []
        for stable in sorted(members):
            if is_listed(stable, listed):
                continue
            vendor = ticker_aliases.fetch_symbol(stable)
            if vendor == stable or not is_listed(vendor, listed):
                missing.append(stable)
        if missing:
            print(f"::error title=unresolved universe ticker::{name}: {len(missing)} "
                  f"stable key(s) are absent from {snapshot} and have no listed "
                  f"lib.ticker_aliases boundary: {', '.join(missing[:10])}", flush=True)
            bad += len(missing)
    return bad


def report_stale_pit_intervals(listed: set[str]) -> None:
    """Advisory only: PIT hygiene is historical evidence, not this live-key gate."""
    path = config.data_dir() / "breadth" / "sp1500_pit_membership.parquet"
    if not path.exists():
        return
    frame = pd.read_parquet(path)
    open_symbols = sorted({str(t) for t in frame[frame["end_date"].isna()]["ticker"]})
    stale = [ticker for ticker in open_symbols if not is_listed(ticker, listed)]
    if stale:
        print(f"::warning title=stale open PIT intervals::{len(stale)} open interval(s) "
              f"name an unlisted historical symbol: {', '.join(stale[:15])}", flush=True)


def main() -> int:
    listed, snapshot = _latest_directory()
    if not listed:
        print("::error title=symbol directory missing::no tracked listing snapshot", flush=True)
        return 1
    universes = _members()
    report_stale_pit_intervals(listed)
    bad = (check_alias_contract(listed, snapshot, universes)
           + check_universe_coverage(listed, snapshot, universes))
    if bad:
        print(f"ticker alias boundary: {bad} problem(s) against {snapshot}", flush=True)
        return 1
    print(f"ticker alias boundary: clean against {snapshot} "
          f"({len(listed)} listed symbols, "
          f"{len(ticker_aliases.YAHOO_FETCH_ALIASES)} alias row(s))", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
