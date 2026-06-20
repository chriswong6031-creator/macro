"""Real-activity VALIDATION overlay for the narrative-rotation book (display + tie-break).

The deep-integration seam: it reads the Divergence Radar (site/basketdata/radar.json) and
annotates each ranked theme with whether independent REAL ACTIVITY (federal contracts +
Quiver gov-contracts/congress/lobbying/patents + news velocity) is running AHEAD of price.

THE ASYMMETRY INVARIANT (the spine of the whole design):
  * crowding / extension can only ever DOWN-SIZE a theme;
  * this validation overlay can only ever UPGRADE a theme ONE slot earlier — and ONLY a
    theme that ALREADY passes the absolute-trend gate (eligible). It NEVER relaxes
    eligibility, NEVER touches the price-scored `score`/`rank`, and NEVER lifts a risk clamp.

So the price-scored core stays BYTE-IDENTICAL: `apply_validation` only writes NEW keys
(val_z / val_state / val_upgrade) onto each ranks[bid]; `allocate()` uses val_upgrade as a
bounded one-slot tie-break among already-eligible themes. With no radar (or no theme
diverging) the overlay is a pure no-op and the book is unchanged.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from lib import config

log = logging.getLogger(__name__)

VAL_UP_THRESH = 0.75   # radar divergence (activity z − price z) above this earns a one-slot upgrade

_STATE_TO_VAL = {
    "POSITIVE_DIVERGENCE": "diverging",   # activity ahead of price — the upgrade case
    "CONFIRMED_UP": "confirming",
    "NEGATIVE_DIVERGENCE": "fading",
    "CONFIRMED_DOWN": "fading",
    "QUIET": "quiet",
}


def _read_radar(root=None) -> dict | None:
    base = Path(root) if root is not None else config.ROOT
    p = base / "site" / "basketdata" / "radar.json"
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def apply_validation(ranks: dict, region: str = "us", root=None, radar: dict | None = None) -> None:
    """Annotate ranks[bid] in place with val_z / val_state / val_upgrade. The radar is US-only
    for now → a no-op for other regions. NEVER touches score / rank / eligible. Never raises."""
    if region != "us":
        return
    if radar is None:
        radar = _read_radar(root)
    if not radar or not radar.get("flags"):
        return
    flags = {f.get("basket"): f for f in radar["flags"]}
    for bid, rk in ranks.items():
        f = flags.get(bid)
        if not f:
            rk["val_state"] = "no_data"
            continue
        div = f.get("divergence")
        rk["val_z"] = div
        rk["val_state"] = _STATE_TO_VAL.get(f.get("state"), "quiet")
        rk["val_upgrade"] = bool(
            f.get("state") == "POSITIVE_DIVERGENCE"
            and rk.get("eligible")
            and div is not None
            and div >= VAL_UP_THRESH
        )
