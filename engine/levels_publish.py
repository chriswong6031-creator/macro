"""engine/levels_publish.py — thin publish helpers for the ``levels.v1`` plane.

Voltick Gamma-Levels program, WP-A2.5 (see
research/VOLTICK_COMPETITIVE_SWEEP_AND_BUILD_PLAN.md §5/§7). WP-A1 shipped the pure
translation engine (``engine.levels_engine.compute_levels``); this module is the thin,
still-pure seam that both the nightly options-hub builder and the standalone
``scripts/build_levels.py`` lane use to turn one ``options_hub.gex/v1`` payload into a
publishable ``levels.v1`` payload + its R2 key.

No I/O, no clock, no randomness — the actual read/write/upload lives in the callers.
Nothing here ranks, gates, or advises: levels are LOCATIONS where dealer hedging
concentrates (positioning, not prophecy), and the dealer-sign passport is inherited
verbatim from ``compute_levels`` (assumed long-call/short-put convention, never measured
inventory).
"""
from __future__ import annotations

from engine.levels_engine import compute_levels

# levels.v1 is a top-level R2 plane (sibling of options_hub/, prophet/, flowleaders/),
# read by the Terminal Levels board as f=levels:{ROOT} -> levels/{ROOT}.json.
LEVELS_PREFIX = "levels/"


def has_strikes(gex_payload: dict | None) -> bool:
    """True when the gex payload carries at least one by_strike row.

    An empty board is never published (mirror WP-GEX-SNAPSHOTS): a levels payload
    with no strikes would be all-null nodes, which is noise on the wire, not signal.
    """
    return bool(gex_payload and gex_payload.get("by_strike"))


def levels_payload_from_gex(
    gex_payload: dict | None, colorblind: bool = False
) -> dict | None:
    """Compute the ``levels.v1`` payload from one ``options_hub.gex/v1`` payload.

    Returns ``None`` when the gex payload carries no by_strike rows (do not publish an
    empty board). ``compute_levels`` stamps its own ``schema``, ``source`` lineage and
    dealer-sign passport — we do not re-derive any of it here. Spot is taken from the
    gex payload's ``spot_ref`` (the price the exposure was computed at), keeping the
    board and the exposure on the same synchronized price.
    """
    if not has_strikes(gex_payload):
        return None
    spot = gex_payload.get("spot_ref")
    return compute_levels(gex_payload, spot=spot, colorblind=colorblind)


def levels_relpath(root: str) -> str:
    """R2 key / local relpath for a root's live levels board."""
    return f"{LEVELS_PREFIX}{root}.json"
