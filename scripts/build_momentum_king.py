"""scripts/build_momentum_king.py — Momentum King board nightly builder (MK-1).

Reuses the shipped, validated engines and adds only the confirmation state
machine on top (see engine/momentum_king.py):
  * engine/residual_alpha.compute_residual_alpha()  → sector-neutral alpha king
  * engine/canon + engine/postcross                 → onset / fresh-cross gate

Inputs (all absent-safe — honest nulls on miss):
  data/*/constituents.parquet + breadth close caches   via engine.equity_factors._closes
  data/yahoo/SPY.parquet                               market series (loaded inside residual_alpha)
Outputs:
  site/momentumking/board.json                         schema momentum_king.v1
  site/momentum_king.html                              rendered from templates/momentum_king.html.j2

Kill-switch: config momentum_king.enabled: false → noindex stub at site/momentum_king.html, skip JSON.
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

from jinja2 import Environment, FileSystemLoader
from engine.equity_factors import _closes
from engine.momentum_king import build_board
from engine.residual_alpha import compute_residual_alpha
from lib import config

log = logging.getLogger(__name__)

_STALE_MAX_LAG_DAYS = 4   # calendar days from last close before the board is stale
_TPL_ROOT = ROOT / "templates"
_SITE_HTML = ROOT / "site" / "momentum_king.html"

# ETF hygiene — a sector/index ETF must never rank as a single-NAME leader.
# Mirrors scripts/build_flow_leaders._ETF_SET (kept in sync manually to avoid a
# cross-script import side-effect at nightly time).
_ETF_SET = frozenset({
    "SPY", "QQQ", "IWM", "DIA",
    "XLK", "XLF", "XLE", "XLI", "XLU", "XLV", "XLY", "XLP", "XLB", "XLC", "XLRE",
    "SMH", "SOXX", "KRE", "XBI", "ARKK",
})


# ── Kill-switch stub ──────────────────────────────────────────────────────────

def _write_noindex_stub() -> None:
    stub = (
        '<!DOCTYPE html><html lang="en"><head>'
        '<meta charset="utf-8"><meta name="robots" content="noindex">'
        '<title>Momentum King (disabled)</title></head>'
        '<body><p>Momentum King is currently disabled.</p></body></html>'
    )
    _SITE_HTML.parent.mkdir(parents=True, exist_ok=True)
    _SITE_HTML.write_text(stub)
    log.info("build_momentum_king: kill-switch active — wrote noindex stub")


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


def _render_html(board: dict) -> None:
    """Render momentum_king.html from the board dict.  Never raises — log + continue on failure."""
    tpl_path = _TPL_ROOT / "momentum_king.html.j2"
    if not tpl_path.exists():
        log.info("build_momentum_king: template %s absent — skipping HTML render", tpl_path)
        return
    try:
        env = Environment(loader=FileSystemLoader(str(_TPL_ROOT)), autoescape=False)
        tpl = env.get_template("momentum_king.html.j2")
        rendered = tpl.render(mk=board)
        _SITE_HTML.parent.mkdir(parents=True, exist_ok=True)
        _SITE_HTML.write_text(rendered)
        log.info("build_momentum_king: rendered %s", _SITE_HTML)
    except Exception as e:  # noqa: BLE001
        log.warning("build_momentum_king: HTML render failed: %s", e)


def _is_stale(closes: pd.DataFrame) -> bool:
    try:
        last = pd.Timestamp(closes.index.max()).normalize()
        now = pd.Timestamp(datetime.now(timezone.utc).date())
        return (now - last).days > _STALE_MAX_LAG_DAYS
    except Exception:  # noqa: BLE001
        return False


def build() -> dict | None:
    if not _enabled():
        _write_noindex_stub()
        return None

    closes = _closes("broad")
    if closes is None or closes.empty:
        log.warning("build_momentum_king: no close panel — nothing to build")
        return None

    # ETF hygiene: drop sector/index ETFs so a fund can never be crowned a
    # single-name leader (they carry a GICS label and would otherwise rank).
    etfs = [c for c in closes.columns if c in _ETF_SET]
    if etfs:
        closes = closes.drop(columns=etfs)
        log.info("build_momentum_king: excluded %d ETFs from the leader universe", len(etfs))

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

    # ── Render HTML ───────────────────────────────────────────────────────────
    _render_html(board)

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
