#!/usr/bin/env python3
"""Heal vendor-symbol leaks back onto stable universe/store keys.

The filename is retained for operator continuity, but the repository contract is
now explicit: MMC/FI remain stable membership, page and ledger keys; MRSH/FISV are
price-vendor request symbols only.  ``lib.ticker_aliases`` is the sole boundary.

This idempotent repair covers the current-state breadth/basket stores.  It never
rewrites point-in-time membership, filings, or append-only ledgers.  Cache rows are
never added or removed.  A vendor column is merged into the stable column and then
dropped; a bounded vendor pull may fill holes, but is stored under the stable key.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import config, ticker_aliases  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("heal_retired_symbol_keys")

_CACHES = {
    "_closes_cache.parquet": "Close",
    "_high_cache.parquet": "High",
    "_low_cache.parquet": "Low",
    "_volume_cache.parquet": "Volume",
}


def _download(symbols: list[str], index: pd.DatetimeIndex) -> dict[str, pd.DataFrame]:
    """Return vendor frames over the cache window; failures leave stores untouched."""
    import yfinance as yf

    span_days = int((index.max() - index.min()).days) + 10
    period = "2y" if span_days <= 720 else ("5y" if span_days <= 1800 else "max")
    try:
        raw = yf.download(symbols, period=period, auto_adjust=True,
                          progress=False, group_by="column", threads=False)
    except Exception as exc:  # noqa: BLE001
        log.warning("download failed (%s); no cache values refreshed", exc)
        return {}
    if raw is None or not len(raw):
        return {}
    level = (raw.columns.get_level_values(0)
             if isinstance(raw.columns, pd.MultiIndex) else raw.columns)
    out: dict[str, pd.DataFrame] = {}
    for field in set(_CACHES.values()):
        if field not in level:
            continue
        frame = raw[field]
        if isinstance(frame, pd.Series):
            frame = frame.to_frame(symbols[0])
        frame.index = pd.to_datetime(frame.index)
        out[field] = frame
    return out


def heal_caches(pairs: dict[str, str], check: bool) -> int:
    """Merge provider columns into stable columns and fill bounded holes."""
    directory = config.data_dir() / "breadth"
    index = None
    for filename in _CACHES:
        path = directory / filename
        if path.exists():
            index = pd.read_parquet(path).index
            break
    if index is None:
        return 0
    fetched = {} if check else _download(sorted(set(pairs.values())), index)
    changed_files = 0

    for filename, field in _CACHES.items():
        path = directory / filename
        if not path.exists():
            continue
        frame = pd.read_parquet(path)
        rows = len(frame)
        touched = False
        for stable, vendor in pairs.items():
            has_stable = stable in frame.columns
            has_vendor = vendor in frame.columns
            if check:
                if has_vendor:
                    log.error("%s: vendor key %s leaked beside stable key %s",
                              filename, vendor, stable)
                    touched = True
                continue

            if has_vendor:
                vendor_values = frame[vendor]
                frame[stable] = (frame[stable].combine_first(vendor_values)
                                 if has_stable else vendor_values)
                frame = frame.drop(columns=[vendor])
                has_stable = True
                touched = True

            vendor_frame = fetched.get(field)
            if vendor_frame is None or vendor not in vendor_frame.columns:
                continue
            active = frame.notna().sum(axis=1) >= (0.5 * max(1, frame.shape[1]))
            pulled = vendor_frame[vendor].reindex(frame.index).where(active)
            old = frame[stable] if has_stable else pd.Series(index=frame.index, dtype=float)
            new = old.combine_first(pulled)
            if int(new.notna().sum()) > int(old.notna().sum()):
                frame[stable] = new
                touched = True

        if touched:
            if check:
                changed_files += 1
                continue
            assert len(frame) == rows, f"{filename}: cache row count changed"
            frame.to_parquet(path)
            changed_files += 1
            log.info("%s: healed (%d rows, %d columns)", filename, rows, len(frame.columns))
    return changed_files


def _rekey_axis(frame: pd.DataFrame, where: str,
                pairs: dict[str, str]) -> tuple[pd.DataFrame, dict[str, str]]:
    """Return a stable-key frame, merging provider duplicates deterministically.

    A collision is the defect this healer exists to remove, not a reason to stop:
    the stable row wins (its GICS sector/name are curated), while a provider
    column fills only holes in the stable column before it is dropped.
    """
    reverse = {vendor: stable for stable, vendor in pairs.items()}
    if where == "index":
        present = {vendor: stable for vendor, stable in reverse.items()
                   if vendor in frame.index}
        out = frame.copy()
        for vendor, stable in present.items():
            if stable in out.index:
                out = out.drop(index=vendor)
            else:
                out = out.rename(index={vendor: stable})
        return out, present
    if where == "columns":
        present = {vendor: stable for vendor, stable in reverse.items()
                   if vendor in frame.columns}
        out = frame.copy()
        for vendor, stable in present.items():
            if stable in out.columns:
                out[stable] = out[stable].combine_first(out[vendor])
                out = out.drop(columns=[vendor])
            else:
                out = out.rename(columns={vendor: stable})
        return out, present
    if where not in frame.columns:
        return frame, {}
    present = {vendor: stable for vendor, stable in reverse.items()
               if (frame[where].astype(str) == vendor).any()}
    out = frame.copy()
    for vendor, stable in present.items():
        if (out[where].astype(str) == stable).any():
            out = out[out[where].astype(str) != vendor].copy()
        else:
            out.loc[out[where].astype(str) == vendor, where] = stable
    return out, present


def heal_frames(pairs: dict[str, str], check: bool) -> int:
    data = config.data_dir()
    targets = (
        (data / "breadth" / "constituents.parquet", "index"),
        (data / "breadth" / "ticker_sectors.parquet", "ticker"),
        (data / "baskets" / "extras.parquet", "columns"),
    )
    changed = 0
    for path, where in targets:
        if not path.exists():
            continue
        frame = pd.read_parquet(path)
        rows = len(frame)
        healed, hits = _rekey_axis(frame, where, pairs)
        if not hits:
            continue
        changed += 1
        if check:
            log.error("%s: vendor keys leaked into %s: %s", path.name, where, hits)
            continue
        assert len(healed) <= rows, f"{path.name}: healing added rows"
        healed.to_parquet(path)
        log.info("%s: restored stable keys %s", path.name, hits)
    return changed


def heal_membership(pairs: dict[str, str], check: bool) -> int:
    path = config.data_dir() / "baskets" / "membership.json"
    if not path.exists():
        return 0
    document = json.loads(path.read_text())
    baskets = document.get("baskets", document)
    reverse = {vendor: stable for stable, vendor in pairs.items()}
    hits: dict[str, list[str]] = {}
    for basket_id, basket in baskets.items():
        members = basket.get("members") if isinstance(basket, dict) else None
        if not isinstance(members, list):
            continue
        stable_present = {m.get("ticker") for m in members if isinstance(m, dict)}
        for member in members:
            ticker = member.get("ticker") if isinstance(member, dict) else member
            if ticker not in reverse:
                continue
            stable = reverse[ticker]
            if stable in stable_present:
                raise AssertionError(f"{basket_id}: both {stable} and {ticker} are members")
            hits.setdefault(basket_id, []).append(f"{ticker}->{stable}")
            if not check:
                if isinstance(member, dict):
                    member["ticker"] = stable
                else:
                    members[members.index(member)] = stable
    if not hits:
        return 0
    if check:
        log.error("membership.json: vendor keys leaked: %s", hits)
        return 1
    path.write_text(json.dumps(document, indent=2))
    log.info("membership.json: restored stable keys %s", hits)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if a store needs healing")
    args = parser.parse_args()
    pairs = dict(ticker_aliases.YAHOO_FETCH_ALIASES)
    changed = (heal_caches(pairs, args.check)
               + heal_frames(pairs, args.check)
               + heal_membership(pairs, args.check))
    log.info("%s: %d store(s) %s", "CHECK" if args.check else "HEAL", changed,
             "need healing" if args.check else "rewritten")
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
