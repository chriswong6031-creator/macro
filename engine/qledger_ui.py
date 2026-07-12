"""engine/qledger_ui.py — view-model helpers for qledger state chips (D10).

Provides `chip_for_desk(desk, track_record)` which returns a chip dict that
templates render directly.  The chip is always present (never hidden) even when
`track_record.json` is absent or empty — in that case it reads UNGRADED · n=0.

Chip schema:
  {
    "state":     "UNGRADED" | "ACCRUING" | "GRADED",
    "css_class": "ql-chip-ungraded" | "ql-chip-accruing" | "ql-chip-graded-pos"
                 | "ql-chip-graded-neg",
    "label":     "UNGRADED · n=0",   # machine-derived, never hand-written
    "label_zh":  "未评级 · n=0",
    "n_dates":   0,
    "hit_rate":  None | float,        # 0..1
    "wilson_ci_low": None | float,
    "horizon_d": None | int,          # the horizon that drives this chip (smallest GRADE_HORIZONS with data)
  }

The chip picks the SMALLEST horizon that has graded data (prefer the earliest
honest signal), so alt_data or intelligence_hub pages show something as soon as
5-day grades accrue, not only when 63d completes.

`load_track_record(root)` reads site/qledger/track_record.json; never fatal —
returns {} on any failure so templates never error.

`chips_for_desks(desks, track_record)` builds a {desk: chip} mapping for a list
of desk keys, suitable for passing into the template render context.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from engine.qledger import (
    GRADE_HORIZONS,
    GRADED_MIN_DATES,
    STATE_ACCRUING,
    STATE_GRADED,
    STATE_UNGRADED,
)
from lib import config

log = logging.getLogger("qledger_ui")

_TRACK_FILE = ("site", "qledger", "track_record.json")


# --------------------------------------------------------------------------- #
# file loader (never fatal)
# --------------------------------------------------------------------------- #

def load_track_record(root: Path | str | None = None) -> dict:
    """Load site/qledger/track_record.json. Returns {} on any failure (absent
    file, parse error, IO error) so callers never need a try/except."""
    root = Path(root) if root else config.ROOT
    p = root.joinpath(*_TRACK_FILE)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.debug("qledger_ui: could not load %s: %s", p, exc)
        return {}


# --------------------------------------------------------------------------- #
# chip derivation
# --------------------------------------------------------------------------- #

# UI desk key → canonical `desk` value written by the W1 backfill adapters.
# The pages address desks by their page-local names (`alt_data`, `news`) but the
# ledger keys `by_desk` on the adapter's `desk` field (`altdata`, `china_news`).
# Without this bridge the alt_data chip would read UNGRADED forever even after
# grades land. Keys not present here pass through unchanged (radar, policy).
_DESK_ALIAS = {
    "alt_data": "altdata",
    "news": "china_news",
}


def chip_for_desk(desk: str, track_record: dict | None) -> dict:
    """Build the chip dict for ONE desk from a loaded track_record payload.

    The chip is derived entirely from the ledger; copy is never hand-written.
    When track_record is absent/empty the chip reads UNGRADED · n=0.

    The PRIMARY horizon is the smallest GRADE_HORIZONS value that has graded
    data for this desk (so grading shows up as early as the 5d clock, not 63d).

    `desk` may be a page-local UI key (e.g. `alt_data`); it is resolved to the
    canonical adapter `desk` value via `_DESK_ALIAS` before the ledger lookup.
    """
    tr = track_record or {}
    by_desk: dict = tr.get("by_desk") or {}
    ledger_key = _DESK_ALIAS.get(desk, desk)
    # Prefer the aliased key, but accept the raw key too (direct desk addressing).
    desk_stats: dict = by_desk.get(ledger_key) or by_desk.get(desk) or {}

    # Pick the smallest horizon with n_dates > 0
    best_h: int | None = None
    best_block: dict = {}
    for h in sorted(GRADE_HORIZONS):
        block = desk_stats.get(str(h)) or {}
        n_dates = block.get("n_dates") or 0
        if n_dates > 0:
            best_h = h
            best_block = block
            break

    n_dates: int = best_block.get("n_dates") or 0
    hit_rate: float | None = best_block.get("hit_rate")
    wilson: float | None = best_block.get("wilson_ci_low")
    state: str = best_block.get("state") or STATE_UNGRADED

    # Validate state vs n_dates (use derive_state as ground-truth)
    if n_dates <= 0:
        state = STATE_UNGRADED
    elif n_dates < GRADED_MIN_DATES:
        state = STATE_ACCRUING
    else:
        state = STATE_GRADED

    # CSS class:
    #   grey   → UNGRADED
    #   amber  → ACCRUING
    #   green  → GRADED, hit_rate >= 0.5 (or hit_rate is None)
    #   red    → GRADED, hit_rate < 0.5
    if state == STATE_UNGRADED:
        css = "ql-chip-ungraded"
    elif state == STATE_ACCRUING:
        css = "ql-chip-accruing"
    else:
        if hit_rate is not None and hit_rate < 0.5:
            css = "ql-chip-graded-neg"
        else:
            css = "ql-chip-graded-pos"

    # Copy strings (machine-generated, never hand-written — D10)
    label, label_zh = _chip_copy(state, n_dates, hit_rate, wilson, best_h)

    return {
        "state": state,
        "css_class": css,
        "label": label,
        "label_zh": label_zh,
        "n_dates": n_dates,
        "hit_rate": hit_rate,
        "wilson_ci_low": wilson,
        "horizon_d": best_h,
    }


def _chip_copy(state: str, n_dates: int,
               hit_rate: float | None, wilson: float | None,
               horizon_d: int | None) -> tuple[str, str]:
    """Generate (label_en, label_zh) from ledger state.  Never hand-written."""
    if state == STATE_UNGRADED:
        return (
            f"UNGRADED · n=0",
            f"未评级 · n=0",
        )
    if state == STATE_ACCRUING:
        # Plain-word glance tier: state + n_dates in plain language (DESIGN_DOCTRINE Law 2).
        # Raw stats ("ACCRUING", fractional counts) are demoted to hover/detail; the chip
        # carries the human-readable signal: "early evidence, N days of data so far".
        return (
            f"early — {n_dates}d of evidence",
            f"早期积累 — {n_dates}天数据",
        )
    # GRADED
    if hit_rate is not None:
        pct = round(hit_rate * 100)
        ci_str = ""
        if wilson is not None:
            ci_low_pct = round(wilson * 100)
            ci_str = f" [CI≥{ci_low_pct}%]"
        h_str = f"{horizon_d}d " if horizon_d else ""
        return (
            f"GRADED · {h_str}hit {pct}%{ci_str}",
            f"已评级 · {h_str}命中 {pct}%{ci_str}",
        )
    return (
        f"GRADED · n={n_dates}",
        f"已评级 · n={n_dates}",
    )


def chips_for_desks(desks: list[str],
                    track_record: dict | None) -> dict[str, dict[str, Any]]:
    """Build a {desk_key: chip} mapping for the given desk keys.  The result is
    None-safe and always includes every requested desk key."""
    return {d: chip_for_desk(d, track_record) for d in desks}
