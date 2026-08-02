"""gex_state_index — the cross-root positioning aggregate (MSC R3.2/R3.3).

Builds ``site/options_structure/gex_state/_index.json``: one compact row per root
from the per-root ``gex_state`` artifacts already in that directory. The Terminal's
screener columns and watchlist regime dot need ONE fetch across the universe;
before this file existed there was no cross-root positioning aggregate anywhere
on R2 (site/gex/index.json is site-only and speaks the board's two-state regime
vocabulary, not gex_state's six-state one).

Transport is free by construction: the file lands in the gex_state directory, so
it rides the nightly's ``git add site/`` AND the launchd R2 mirror's
``src.glob("*.json")`` (ops/launchd/run_options_matrix.sh) with zero new plumbing.

Honesty rules:
- Rows are built by GLOBBING the directory — the same set of files the mirror
  serves per-root — so the index can never disagree with what a per-root fetch
  returns. Each row carries its OWN asof date; a root that stopped building
  keeps its last state and its stale date travels with it (staleness is data,
  not something to hide by dropping the row).
- ``pin_probability`` and the trigger fields are deliberately NOT distributed:
  pin is uncalibrated (Tier C — masterplan R2.5) and the triggers are desk-only
  reads. The index carries only the glance-tier fields the consumers render.
- Malformed or ``_``-prefixed files are skipped, never fatal.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger("gex_state_index")

SCHEMA = "options_structure.gex_state_index/v1"

# Glance-tier fields copied per row (everything else stays per-root only).
_ROW_FIELDS = (
    "spot",
    "net_gex_bn",
    "gamma_regime",
    "stability_pct",
    "gamma_flip",
    "dist_to_flip_pct",
    "call_wall",
    "put_wall",
)


def build_index(gex_state_dir: Path) -> dict | None:
    """Aggregate every per-root gex_state JSON in *gex_state_dir* into one index
    dict, or None when the directory yields no usable rows (caller then leaves
    any prior _index.json untouched — a bad run must not blank the consumers)."""
    rows: dict[str, dict] = {}
    max_asof = ""
    for p in sorted(gex_state_dir.glob("*.json")):
        if p.name.startswith("_"):
            continue  # the index itself / any future underscore artifacts
        try:
            state = json.loads(p.read_text())
        except Exception:  # noqa: BLE001 — one unreadable file never kills the index
            log.warning("gex_state_index: skipping unreadable %s", p.name)
            continue
        if not isinstance(state, dict):
            continue
        root = state.get("root")
        if not isinstance(root, str) or not root:
            continue
        row: dict = {}
        for k in _ROW_FIELDS:
            v = state.get(k)
            if v is not None:
                row[k] = v
        asof = state.get("asof")
        if isinstance(asof, str) and len(asof) >= 10:
            row["asof"] = asof[:10]  # session-date resolution is all consumers need
            if asof > max_asof:
                max_asof = asof
        if not row:
            continue
        rows[root.upper()] = row
    if not rows:
        return None
    return {
        "schema": SCHEMA,
        "asof": max_asof or None,
        "n_roots": len(rows),
        "rows": rows,
    }


def write_index(gex_state_dir: Path) -> Path | None:
    """Build and write ``_index.json`` into *gex_state_dir*. Returns the path
    written, or None (no rows / directory missing) — never raises."""
    try:
        if not gex_state_dir.is_dir():
            log.warning("gex_state_index: %s missing — nothing to aggregate", gex_state_dir)
            return None
        index = build_index(gex_state_dir)
        if index is None:
            log.warning("gex_state_index: no usable rows — leaving any prior index in place")
            return None
        out = gex_state_dir / "_index.json"
        out.write_text(json.dumps(index, default=float, allow_nan=False, separators=(",", ":")))
        log.info("gex_state_index: wrote %s (%d roots, asof %s)", out, index["n_roots"], index["asof"])
        return out
    except Exception as e:  # noqa: BLE001 — additive side-effect, never fatal to the board
        log.warning("gex_state_index: failed: %s", e)
        return None
