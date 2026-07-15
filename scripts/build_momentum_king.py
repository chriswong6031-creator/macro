"""scripts/build_momentum_king.py — Momentum King board nightly builder (MK-1).

Reuses the shipped, validated engines and adds only the confirmation state
machine on top (see engine/momentum_king.py):
  * engine/residual_alpha.compute_residual_alpha()  → sector-neutral alpha king
  * engine/canon + engine/postcross                 → onset / fresh-cross gate

Inputs (all absent-safe — honest nulls on miss):
  data/*/constituents.parquet + breadth close caches   via engine.equity_factors._closes
  data/yahoo/SPY.parquet                               market series (loaded inside residual_alpha)
Output:
  site/momentumking/board.json                         schema momentum_king.v1

Kill-switch: config momentum_king.enabled: false → skip (no write).
Display-tier: zero data/ writes; fail-soft; always exits 0.
Subordinate witnesses (net-inflow, options) are MK-P2 — the hooks exist here but
are left unpopulated in MK-P1 so the board never carries a false witness zero.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.equity_factors import _closes
from engine.momentum_king import build_board
from engine.residual_alpha import compute_residual_alpha
from lib import config

log = logging.getLogger(__name__)

_STALE_MAX_LAG_DAYS = 4   # calendar days from last close before the board is stale


def _json_default(obj: Any) -> Any:
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return None if not np.isfinite(float(obj)) else float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()
    if obj is pd.NA or obj is pd.NaT:
        return None
    try:
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _enabled() -> bool:
    try:
        return bool(config.load().get("momentum_king", {}).get("enabled", True))
    except Exception:  # noqa: BLE001
        return True


def _is_stale(closes: pd.DataFrame) -> bool:
    try:
        last = pd.Timestamp(closes.index.max()).normalize()
        now = pd.Timestamp(datetime.now(timezone.utc).date())
        return (now - last).days > _STALE_MAX_LAG_DAYS
    except Exception:  # noqa: BLE001
        return False


def build() -> dict | None:
    if not _enabled():
        log.info("build_momentum_king: kill-switch active — skipping")
        return None

    closes = _closes("broad")
    if closes is None or closes.empty:
        log.warning("build_momentum_king: no close panel — nothing to build")
        return None

    # residual_alpha loads its own SPY market + GICS sectors/names internally;
    # passing the SAME `closes` keeps the alpha rank and the onset overlay on one
    # PIT-aligned panel.
    residual = compute_residual_alpha(closes=closes)
    if not residual:
        log.warning("build_momentum_king: residual_alpha returned no result")
        return None

    board = build_board(
        residual, closes,
        as_of=residual.get("as_of"),
        stale=_is_stale(closes),
    )
    if not board:
        log.warning("build_momentum_king: empty board")
        return None

    board["built_utc"] = datetime.now(timezone.utc).isoformat()

    out_dir = ROOT / "site" / "momentumking"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "board.json"
    out_path.write_text(json.dumps(board, separators=(",", ":"), default=_json_default))
    cov = board.get("coverage", {})
    log.info(
        "build_momentum_king: wrote %s (%d sectors, %d leader-candidates, %d bytes, stale=%s)",
        out_path, cov.get("n_sectors", 0), cov.get("n_leader_candidates", 0),
        out_path.stat().st_size, board.get("stale"),
    )
    return board


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    try:
        build()
    except Exception as e:  # noqa: BLE001 — display-tier, never break the nightly
        log.error("build_momentum_king: unexpected error: %s", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
