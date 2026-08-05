"""Retired US ticker -> the symbol that currently trades. One map, site-wide.

WHY THIS EXISTS
---------------
A US listing can change its ticker without changing company, CUSIP, or listing.
When that happens this repo splits in half on its own: every collector fed by a
vendor/regulator source (SEC, FINRA, OpenFIGI, the NASDAQ symbol directory, ETF
holdings) follows the rename within days, while anything keyed off the committed
universe stays on the retired symbol. The two halves then accrue as two separate
companies, with no link between them.

Measured on Marsh McLennan (MMC -> MRSH, 2026-01-14) after ~7 months of drift:
two independent entity records in data/altdata/by_ticker.json with different
channels and scores; a live 458M ADV under one symbol and index membership under
the other in data/marketing/cashtag_tiers.json; factor betas computed over n=227
under MRSH while MMC had none; a 0/345 all-NaN price column under the key the
universe actually used; and no stock page under EITHER symbol.

This module is the missing link. It does NOT rewrite history — a 13F filed in
2024 really did say "MMC", and a forward claim registered under MMC stays under
MMC (operator ruling 2026-08-05: strand, disclose, do not re-key the append-only
ledgers). It lets a reader resolve both symbols to one company, so a
point-in-time record written under the retired symbol is still priceable and
still attributable to the live name.

SOURCE OF TRUTH
---------------
``breadth.ticker_fixups`` in config.yml, which is already exactly this mapping
(retired -> current) and is applied to the scraped constituents table. Reading it
here rather than declaring a second list is deliberate: two copies of one
vocabulary drift, and only one of them gets cured.

DIRECTION IS LOAD-BEARING. A backwards row pins the universe to a symbol that no
longer trades — which is precisely how the Marsh drift lasted 7 months, and the
Fiserv one (FI -> FISV, renamed back 2025-11-11) 9. Resolve any suspected bad
symbol against the two authoritative artifacts this repo already collects:

  * data/symbol_directory/snapshots/<date>.parquet — the NASDAQ-published listing
    file. A symbol ABSENT here is the retired one; the live one is present.
  * data/openfigi/cusip_ticker.parquet — CUSIP -> ticker. A rename keeps the CUSIP.

``scripts/check_symbol_rename_drift.py`` enforces the direction against both on
every CI run, so a backwards row now fails instead of drifting silently.
"""
from __future__ import annotations

import logging

from lib import config

log = logging.getLogger(__name__)


def rename_map() -> dict[str, str]:
    """``{retired_symbol: live_symbol}``, upper-cased and self-maps dropped.

    Empty (never raises) when config is unreadable — callers then behave exactly
    as they did before this module existed, which is the safe direction: an
    unresolvable retired symbol looks absent rather than silently borrowing some
    other company's data.
    """
    try:
        fixups = (config.load().get("breadth", {}) or {}).get("ticker_fixups") or {}
    except Exception as e:  # noqa: BLE001 — config unreadable must not break a price read
        log.warning("symbol_aliases: config unreadable (%s) — no rename map", e)
        return {}
    out: dict[str, str] = {}
    for k, v in fixups.items():
        a, b = str(k).strip().upper(), str(v).strip().upper()
        if a and b and a != b:
            out[a] = b
    return out


def resolve(ticker: str) -> str:
    """The symbol ``ticker`` currently trades under (itself when not retired).

    Single hop only. A name renamed twice (Fiserv: FISV -> FI -> FISV) is
    expressed as the one row that matters — retired FI -> live FISV — because the
    map's values are always the CURRENTLY live symbol, never an intermediate. A
    chain would mean the map itself is wrong.
    """
    t = str(ticker or "").strip().upper()
    return rename_map().get(t, t)


def retired_for(ticker: str) -> list[str]:
    """Every retired symbol that resolves to ``ticker`` (sorted; usually 0 or 1).

    Use when reading a point-in-time store to pick up rows filed under the old
    symbol — e.g. attributing a 2024 13F position to today's company.
    """
    live = str(ticker or "").strip().upper()
    return sorted(k for k, v in rename_map().items() if v == live)


def all_symbols_for(ticker: str) -> list[str]:
    """``ticker`` resolved to live, plus every retired symbol pointing at it.

    The complete key set one company's data can be filed under, live symbol
    first. Deduped and stable so it can be used to build a lookup.
    """
    live = resolve(ticker)
    return [live] + [t for t in retired_for(live) if t != live]
