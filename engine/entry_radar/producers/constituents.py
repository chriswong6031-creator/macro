"""engine/entry_radar/producers/constituents.py — index membership + the Layer-A universe.

The one producer here that emits NO nominations, on purpose.

Index membership is not a nomination — nobody *surfaced* AAPL by noticing it is
in the S&P 500.  Membership is a standing structural fact, so it enters as a
Layer-B **admission reason** (``core.index_member``) rather than as an
enlistment event.  Minting a nomination per constituent would put ~1,500 rows
into the spool every pass that carry no information beyond a list we already
have.

WHY THIS READS THE ARTIFACTS AND NOT ``build_stock_library.universe()``
------------------------------------------------------------------------
``scripts/build_stock_library.py`` is a G-8-adjacent protected consumer path;
importing it to get the universe would couple Radar's funnel to Prophet-side
scoring machinery for the sake of a name list.  So this module reads the SAME
underlying artifacts in the SAME priority order (Track C §2, verified against
``universe()`` at ``build_stock_library.py``:845):

  1. ``data/stocks/*.parquet``                    deep-history store (wins ties)
  2. ``data/breadth/constituents.parquet``        S&P 500
  3. ``data/midcap_breadth/constituents.parquet`` S&P 400
  4. ``data/smallcap_breadth/constituents.parquet`` S&P 600
  5. ``data/russell_breadth/constituents.parquet`` Russell 2000

  (``universe()``'s third leg — the yahoo store's config-listed sector/factor/FX
  tickers — is deliberately NOT replicated: those are indices, ETFs and
  currencies, i.e. exactly the wrapper population Layer A excludes.)

ARTIFACT SHAPE (verified at the write site, ``collectors/breadth.py``:503, and
the read site ``scripts/build_sp500_heatmap.py``:48): index name ``symbol``,
columns ``name`` and ``sector`` (GICS).  The midcap/smallcap adapters subclass
``BreadthAdapter`` unchanged, so all three files share the schema.  ``name`` is
the reason Layer A's wrapper classifier can work at all — without it, every
name would land ``unclassified``.

THE SELF-AUDIT IS THE POINT (Track C §2)
-----------------------------------------
``universe_sources()`` exists upstream because a group silently dropping
shrinks the universe by O(1000) — a measured real incident (2026-07-25).  So
every source here reports its own availability, an empty read is an OUTAGE
rather than an empty index, and the assembly surfaces the per-source audit on
the artifact.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from engine.entry_radar.universe import (
    UniverseSourceRead,
    read_constituents,
    read_deep_history,
)

log = logging.getLogger(__name__)

#: ``(source key, relative path, kind)`` in ``universe()``'s priority order.
DEFAULT_SOURCES: tuple[tuple[str, str, str], ...] = (
    ("deep_history", "data/stocks", "glob_parquet"),
    ("sp500", "data/breadth/constituents.parquet", "constituents"),
    ("sp400", "data/midcap_breadth/constituents.parquet", "constituents"),
    ("sp600", "data/smallcap_breadth/constituents.parquet", "constituents"),
    ("russell2000", "data/russell_breadth/constituents.parquet", "constituents"),
)

#: Which source keys are index memberships for Layer B (deep-history is not one).
MEMBERSHIP_KEYS: frozenset[str] = frozenset({"sp500", "sp400", "sp600", "russell2000"})


def read_universe_sources(root: Path, *,
                          sources: Sequence[tuple[str, str, str]] = DEFAULT_SOURCES,
                          loader: Any = None) -> list[UniverseSourceRead]:
    """Read every Layer-A source, each with its own availability verdict.

    ``loader`` is injected in tests: this worktree is sparse, ``data/`` is
    absent, and an adapter that read absence as an empty index would report a
    dead market from a checkout.
    """
    out: list[UniverseSourceRead] = []
    for key, rel, kind in sources:
        path = root / rel
        if kind == "glob_parquet":
            out.append(read_deep_history(path, key=key))
        else:
            out.append(read_constituents(path, key=key, loader=loader))
    return out


def memberships_from(sources: Sequence[UniverseSourceRead]) -> dict[str, list[str]]:
    """``index key -> [tickers]`` for the index sources that read OK.

    A source that failed is ABSENT from the mapping rather than present-and-empty
    — Layer B must be able to tell "not in the S&P 500" from "we could not read
    the S&P 500" (contract §5).
    """
    return {src.key: list(src.tickers) for src in sources
            if src.key in MEMBERSHIP_KEYS and src.status == "ok"}


def names_from(sources: Sequence[UniverseSourceRead]) -> dict[str, str]:
    """``ticker -> security name``, first source in priority order wins.

    This is the wrapper classifier's fuel: a name with no label cannot be
    classified and lands ``unclassified`` by the fail-closed rule.
    """
    out: dict[str, str] = {}
    for src in sources:
        if src.status != "ok":
            continue
        for sym, meta in (src.meta or {}).items():
            if sym in out or not isinstance(meta, Mapping):
                continue
            label = meta.get("name") or meta.get("company") or meta.get("security")
            if label:
                out[str(sym).strip().upper()] = str(label)
    return out


def sectors_from(sources: Sequence[UniverseSourceRead]) -> dict[str, str]:
    """``ticker -> GICS sector`` off the constituents files.

    Deliberately the GICS-authoritative store, not the Finviz-curated
    ``data/sp500_heatmap/industry_map.json``: two parallel sector stores exist
    and have never been cross-checked for drift (Track C §3), so Radar pins the
    one the index provider stamps.
    """
    out: dict[str, str] = {}
    for src in sources:
        if src.status != "ok":
            continue
        for sym, meta in (src.meta or {}).items():
            if sym in out or not isinstance(meta, Mapping):
                continue
            sector = meta.get("sector") or meta.get("gics_sector")
            if sector:
                out[str(sym).strip().upper()] = str(sector)
    return out
