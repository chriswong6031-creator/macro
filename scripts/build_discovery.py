"""Build the US "Top Picks" board -> site/discovery.html.

Formerly the "Alpha leaders" leaderboard (a pure residual-momentum sort, whose top was
always the most-extended hot names — the ones that already ran). This rebuilds it as a
holistic, two-axis pick board:

  * Axis 1 — CONVICTION (what to own): rank by the validated Top-Pick score
    (engine/top_picks.py) = alpha-led blend of residual momentum + a light multi-factor
    confirmation (value / quality / profitability / low-vol / insider). Beat residual
    alpha ALONE point-in-time on IC at every horizon (reports/top-picks-phase0.md).
  * Axis 2 — ENTRY (when to buy): a SEPARATE column — Buy zone (leader on a pullback) /
    Steady / Extended (just spiked → wait). Never folded into the rank (US leaders
    continue; a reversal tilt in the rank measurably hurts — the opposite of China).

Standalone like build_commodities.py. Reads the already-computed cross-sections —
site/factordata/alpha.json (sector-neutral residual momentum + entry overlay),
factors.json (smart-beta legs) and insider_signals.json (Form-4 net buy bps) — and never
recomputes a signal. Honest framing throughout: a modest, decayed, crowded edge — a
research lens with an entry read, not a buy list.

Usage: python -m scripts.build_discovery
"""
from __future__ import annotations

import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.top_picks import (ALPHA_W, ENTRY_LABELS, TILT_LEGS, TILT_W,  # noqa: E402
                              band, compute_scores, entry_meta)
from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_discovery")

TOP_N = 40          # length of the global strongest / weakest lists
SECTOR_TOP = 18     # rows shown per sector drill
BUYZONE_N = 12      # length of the "buy-zone" sweet-spot strip
BUYZONE_MIN = 0.3   # a buy-zone pick must still be a genuine top pick (top_score >= this)

# entry tag -> (en, zh, css class), for the template's echip macro
ENTRY_META = {tag: (m[0], m[1], m[2]) for tag, m in ENTRY_LABELS.items()}


def _names_sectors() -> dict:
    from engine.equity_factors import _names_sectors as ns
    try:
        return ns()
    except Exception as e:  # noqa: BLE001 — degrade to ticker-only labels
        log.warning("names/sectors load failed (%s)", e)
        return {}


def _last_prices():
    try:
        from engine.equity_factors import _closes
        c = _closes()
        return c.iloc[-1] if c is not None and not c.empty else None
    except Exception as e:  # noqa: BLE001 — price is a nicety, never fatal
        log.warning("price load failed (%s); omitting price column", e)
        return None


def _price(px, tk: str):
    if px is None or tk not in px.index:
        return None
    v = px[tk]
    return round(float(v), 2) if pd.notna(v) else None


def _load_json(site: Path, name: str) -> dict:
    p = site / "factordata" / name
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("could not read %s (%s)", name, e)
        return {}


def _clean(v):
    """JSON tolerates NaN on load but the template should not see it."""
    return None if (isinstance(v, float) and math.isnan(v)) else v


def main() -> int:
    site = config.ROOT / config.load()["storage"]["site_dir"]
    alpha = _load_json(site, "alpha.json")
    pt = alpha.get("per_ticker") or {}
    if not pt:
        log.error("alpha.json has no per_ticker — run build_site first; skipping discovery")
        return 0

    factors = _load_json(site, "factors.json")
    ftab = {r["ticker"]: r for r in (factors.get("table") or [])}
    insider = _load_json(site, "insider_signals.json")
    attn = _load_json(site, "attention.json")   # offshore-attention z (display-only caution chip)
    ns = _names_sectors()
    px = _last_prices()

    # ---- score the whole universe with the validated Top-Pick composite ---------
    inp = []
    for tk, a in pt.items():
        if a.get("alpha") is None:
            continue
        f = ftab.get(tk, {})
        ins = insider.get(tk, {})
        inp.append({"ticker": tk, "sector": ns.get(tk, (tk, "—"))[1], "alpha": a["alpha"],
                    "value": _clean(f.get("value")), "quality": _clean(f.get("quality")),
                    "profitability": _clean(f.get("profitability")),
                    "low_vol": _clean(f.get("low_vol")), "insider": _clean(ins.get("bps"))})
    scores = compute_scores(inp)
    log.info("scored %d names (alpha-led blend %.1f/%.1f)", len(scores), ALPHA_W, TILT_W)

    # ---- display rows -----------------------------------------------------------
    def _row(tk: str, a: dict) -> dict | None:
        s = scores.get(tk)
        if not s:
            return None
        name, sector = ns.get(tk, (tk, "—"))
        ins = insider.get(tk, {})
        at = attn.get(tk, {})
        en, zh, css, buyzone = entry_meta(a.get("entry"))
        return {
            "ticker": tk, "name": name, "sector": sector, "price": _price(px, tk),
            "top_score": s["top_score"], "band": band(s["top_score"]),
            "alpha": s["alpha"], "alpha_band": band(s["alpha"]),
            "conviction_z": s["conviction_z"], "n_legs": s["n_legs"], "legs": s["legs"],
            "entry": a.get("entry"), "entry_en": en, "entry_zh": zh, "entry_css": css,
            "buyzone": buyzone,
            "total_mom": a.get("total_mom"), "rev_1m": a.get("rev_1m"),
            "rev_pctile": a.get("rev_pctile"), "sector_rank": a.get("sector_rank"),
            "sector_n": a.get("sector_n"),
            "ins_buyers": ins.get("buyers") or 0, "ins_bps": _clean(ins.get("bps")),
            "attn_z": _clean(at.get("z")),   # offshore-attention z (display-only caution)
        }

    rows = [r for r in (_row(tk, a) for tk, a in pt.items()) if r is not None]
    rows.sort(key=lambda r: r["top_score"], reverse=True)
    # collapse dual-class / multi-listings to the best-ranked variant (GOOG+GOOGL → one
    # slot) BEFORE any board is sliced, so no surface spends two rows on one company.
    from engine.setups import dedupe_dual_class
    rows = dedupe_dual_class(rows)
    strongest = rows[:TOP_N]
    weakest = rows[-TOP_N:][::-1]

    # the "buy-zone" sweet spot: genuine top picks (high conviction) that are ALSO a
    # leader on a pullback — the user's "good entry into a high-alpha name".
    buyzone = [r for r in rows if r["buyzone"] and r["top_score"] >= BUYZONE_MIN][:BUYZONE_N]

    # ---- sectors overview (by mean Top-Pick conviction) + top-quintile share ------
    q_cut = rows[max(0, len(rows) // 5 - 1)]["top_score"] if rows else 0.0
    agg: dict[str, dict] = {}
    for r in rows:
        if r["sector"] in (None, "—"):
            continue
        v = agg.setdefault(r["sector"], {"n": 0, "sum": 0.0, "intop": 0})
        v["n"] += 1
        v["sum"] += r["top_score"]
        v["intop"] += 1 if r["top_score"] >= q_cut else 0
    sectors = sorted(
        [{"sector": s, "n": v["n"], "mean": round(v["sum"] / v["n"], 2),
          "intop": v["intop"], "pct": round(100 * v["intop"] / v["n"])}
         for s, v in agg.items()],
        key=lambda x: x["mean"], reverse=True)

    # ---- sector drill — leaders / laggards RE-RANKED by Top-Pick score -------------
    by_sec_rows: dict[str, list] = {}
    for r in rows:
        if r["sector"] not in (None, "—"):
            by_sec_rows.setdefault(r["sector"], []).append(r)
    by_sector = {}
    for sec, lst in by_sec_rows.items():
        lst.sort(key=lambda r: r["top_score"], reverse=True)
        by_sector[sec] = {"n": len(lst), "leaders": lst[:SECTOR_TOP],
                          "laggards": lst[-6:][::-1]}
    sector_order = [s["sector"] for s in sectors if s["sector"] in by_sector]

    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    from engine.i18n import td, tr  # noqa: F401
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    env.globals.update(td=td, tr=tr)
    html = env.get_template("discovery.html.j2").render(
        strongest=strongest, weakest=weakest, buyzone=buyzone, sectors=sectors,
        by_sector=by_sector, sector_order=sector_order, entry_meta=ENTRY_META,
        tilt_legs=list(TILT_LEGS), alpha_w=ALPHA_W, tilt_w=TILT_W,
        attn_threshold=float((config.load().get("wiki_pageviews") or {}).get("chip_threshold", 2.0)),
        as_of=alpha.get("as_of"), windows=alpha.get("windows") or {},
        n=len(rows), built=built)
    (site / "discovery.html").write_text(html)
    log.info("wrote %s/discovery.html (%d names, %d sectors, %d buy-zone, %d KB)",
             site, len(rows), len(by_sector), len(buyzone), len(html) // 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
