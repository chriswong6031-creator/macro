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
from engine.baskets import _membership
from engine.equity_factors import _closes, _names_sectors
from engine.momentum_king import build_board
from engine.residual_alpha import compute_residual_alpha
from engine.subsector_scan import _industry_map
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

# ── Sub-industry / theme group thresholds (T2) — frozen alongside the sector seeds
_THEME_MIN_MEMBERS = 5     # curated baskets are small & concentrated (Mag7 = 7)
_SUB_MIN_MEMBERS = 6       # sub-industry peer sets — matches residual_alpha min_sector
_GROUP_MIN_ROWS = 147      # default form(252)/skip(21) need ≥147 non-NaN residual rows
_MAX_GROUPS = 60           # render-budget cap per family (one residual pass each)


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


def _remap_names(blk: dict, ns_real: dict) -> None:
    """A custom tkr_sector makes residual_alpha set each leader's `name` = its ticker.
    Restore the real company name (leave `sector` as the group label — the state
    machine is label-agnostic). Load-bearing: without this every theme/sub leader
    would display its ticker as its name."""
    for lst in ("leaders", "laggards"):
        for rec in blk.get(lst, []):
            nm = ns_real.get(rec.get("ticker"))
            if nm:
                rec["name"] = nm[0]


def _group_residual(group_closes, label: str, min_members: int) -> dict | None:
    """One within-group residual pass. market=None → residual_alpha loads SPY as the
    MARKET leg; the group's own equal-weight peer is the SECTOR leg (within-group
    neutralization — 'who leads THIS group'). NEVER pass the peer basket as market,
    that would double-neutralize. Returns the by_sector block for `label`, or None.

    Window: group passes use a 126-day (~6-month) beta+formation window, NOT the
    252-day sector-spine window. A small group has far fewer full-history members
    than the 1500-name universe, and the default 252-day residual needs ~252 rows of
    per-name history to survive — which silently starved group coverage (a 252-window
    run yielded 0 sub-industries). 126 aligns with the ≥147-row _GROUP_MIN_ROWS floor,
    keeps the boards populated, and gives a more responsive current-leader read; the
    slightly less-stable betas are acceptable for a display-tier group signal. The
    252-day sector spine (the main residual pass) is unchanged."""
    res = compute_residual_alpha(
        closes=group_closes, market=None,
        tkr_sector={t: label for t in group_closes.columns},
        win=126, form=126, skip=21,
        min_names=min_members, min_sector=min_members)
    if not res or label not in res.get("by_sector", {}):
        return None
    return res["by_sector"][label]


def _build_theme_groups(closes, ns_real, *, min_members=_THEME_MIN_MEMBERS,
                        max_groups=_MAX_GROUPS, min_rows=_GROUP_MIN_ROWS):
    """{basket_id -> by_sector-shaped block}, {basket_id -> meta}. Overlap by design →
    one residual pass per basket. Absent-safe (empty on missing membership.json)."""
    try:
        mem = _membership()
        if not mem or not isinstance(mem.get("baskets"), dict):
            return {}, {}
        cands = []
        for bid, b in mem["baskets"].items():
            present = [t for t in (m["ticker"] for m in b.get("members", []) if not m.get("removed"))
                       if t in closes.columns and t not in _ETF_SET]
            if len(present) >= min_members:
                cands.append((bid, b, present))
        cands.sort(key=lambda x: -len(x[2]))          # biggest baskets first (bound cost)
        by_theme, meta, skipped = {}, {}, 0
        for bid, b, present in cands[:max_groups]:
            gc = closes[present]
            if gc.shape[0] < min_rows:
                skipped += 1
                continue
            blk = _group_residual(gc, bid, min_members)
            if blk is None:
                skipped += 1
                continue
            _remap_names(blk, ns_real)
            by_theme[bid] = blk
            # NB: 'theme_desc', not 'theme' — the row's label_key is already 'theme'
            # (= basket id), so a meta 'theme' key would be dropped by setdefault.
            meta[bid] = {"name": b.get("name", bid), "name_zh": b.get("name_zh", b.get("name", bid)),
                         "category": b.get("category", "Other"), "theme_desc": b.get("theme", "")}
        if skipped:
            log.info("build_momentum_king: %d themes skipped (short history / thin)", skipped)
        return by_theme, meta
    except Exception as e:  # noqa: BLE001 — display-tier, never break the nightly
        log.warning("build_momentum_king: theme groups failed: %s", e)
        return {}, {}


def _build_subindustry_groups(closes, ns_real, *, min_members=_SUB_MIN_MEMBERS,
                              max_groups=_MAX_GROUPS, min_rows=_GROUP_MIN_ROWS):
    """{sub_industry -> by_sector-shaped block}, {sub_industry -> meta}. Absent-safe."""
    try:
        imap = _industry_map()
        if not imap:
            return {}, {}
        cands = []
        for (sector, sub), tickers in imap.items():
            if not sub or sub == "—":
                continue
            present = [t for t in tickers if t in closes.columns and t not in _ETF_SET]
            if len(present) >= min_members:
                cands.append((sub, sector, present))
        cands.sort(key=lambda x: -len(x[2]))
        by_sub, meta, skipped = {}, {}, 0
        for sub, sector, present in cands[:max_groups]:
            gc = closes[present]
            if gc.shape[0] < min_rows:
                skipped += 1
                continue
            blk = _group_residual(gc, sub, min_members)
            if blk is None:
                skipped += 1
                continue
            _remap_names(blk, ns_real)
            by_sub[sub] = blk
            meta[sub] = {"sub_industry": sub, "sector": sector}
        if skipped:
            log.info("build_momentum_king: %d sub-industries skipped (short history / thin)", skipped)
        return by_sub, meta
    except Exception as e:  # noqa: BLE001
        log.warning("build_momentum_king: sub-industry groups failed: %s", e)
        return {}, {}


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

    # Sub-industry + theme granularities (T2) — each an independent per-group
    # residual pass (themes overlap, so one pass per basket). Both absent-safe
    # (empty on missing data) and purely additive to the sector spine.
    ns_real = _names_sectors("broad")
    by_theme, theme_meta = _build_theme_groups(closes, ns_real)
    by_sub, sub_meta = _build_subindustry_groups(closes, ns_real)

    board = build_board(
        residual, closes,
        as_of=residual.get("as_of"),
        stale=_is_stale(closes),
        by_sub_industry=by_sub, sub_meta=sub_meta,
        by_theme=by_theme, theme_meta=theme_meta,
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
        "build_momentum_king: wrote %s (%d sectors, %d sub-industries, %d themes, "
        "%d leader-candidates, %d bytes, stale=%s)",
        out_path, cov.get("n_sectors", 0), cov.get("n_sub_industries", 0),
        cov.get("n_themes", 0), cov.get("n_leader_candidates", 0),
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
