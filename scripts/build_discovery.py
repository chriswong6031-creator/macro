"""Build the cross-sector residual-alpha discovery leaderboard -> site/discovery.html.

Standalone like build_commodities.py (shares only the parquet store + theme assets).
Reads the already-computed site/factordata/alpha.json (sector-neutral residual
momentum, written by build_site.build_alpha_data — engine/residual_alpha.py) and
renders the AION-Index-style cross-sector view: a Global index (every name ranked by
the sector-neutral alpha z), a Sectors overview, and a per-GICS-sector drill with the
DUAL score (global alpha-z vs in-sector rank) plus the reversal entry overlay.

Honest framing throughout (house rule): this is a modest, regime-decayed edge —
context, not a buy list. The signal/engine/validation live in
research/RESIDUAL_ALPHA_MOMENTUM.md; this script is UI only and never recomputes it.

Usage: python -m scripts.build_discovery
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_discovery")

TOP_N = 30          # length of the global strongest / weakest lists
SECTOR_TOP = 20     # rows shown per sector drill

# reversal entry overlay tag -> (en, zh, css class). Mirrors engine.residual_alpha._entry.
ENTRY_META = {
    "extended": ("Extended", "过热", "ent-ext"),     # leader that ran hot — reversal risk
    "pullback": ("Pullback", "回调", "ent-pull"),    # leader on a dip — constructive entry
    "intact":   ("Intact", "完好", "ent-intact"),
    "laggard":  ("Laggard", "落后", "ent-lag"),
    "neutral":  ("Neutral", "中性", "ent-neutral"),
}


def _band(alpha: float | None) -> str:
    """Position band from the sector-neutral z (drives row colour)."""
    if alpha is None:
        return "mid"
    if alpha >= 1.0:
        return "strong"
    if alpha >= 0.3:
        return "leader"
    if alpha > -0.3:
        return "mid"
    if alpha > -1.0:
        return "lag"
    return "deeplag"


def _names_sectors() -> dict:
    from engine.equity_factors import _names_sectors as ns
    try:
        return ns()
    except Exception as e:  # noqa: BLE001 — degrade to ticker-only labels
        log.warning("names/sectors load failed (%s)", e)
        return {}


def _last_prices():
    """Last close per ticker for the price column (optional — guarded)."""
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


def _row(tk: str, rec: dict, ns: dict, px, attn: dict | None = None) -> dict:
    name, sector = ns.get(tk, (tk, "—"))
    a = rec.get("alpha")
    return {"ticker": tk, "name": name, "sector": sector, "alpha": a, "band": _band(a),
            "resid_ann": rec.get("resid_ann"), "total_mom": rec.get("total_mom"),
            "rev_1m": rec.get("rev_1m"), "rev_pctile": rec.get("rev_pctile"),
            "sector_rank": rec.get("sector_rank"), "sector_n": rec.get("sector_n"),
            "entry": rec.get("entry"), "price": _price(px, tk),
            "attn_z": ((attn or {}).get(tk) or {}).get("z"),   # offshore-attention caution (display-only)
            "rs": rec.get("rs"), "rs3m": rec.get("rs3m"),
            "rs6m": rec.get("rs6m"), "rs12m": rec.get("rs12m")}


def main() -> int:
    site = config.ROOT / config.load()["storage"]["site_dir"]
    ap = site / "factordata" / "alpha.json"
    if not ap.exists():
        log.error("alpha.json missing (%s) — run build_site first; skipping discovery", ap)
        return 0
    alpha = json.loads(ap.read_text())
    pt = alpha.get("per_ticker") or {}
    if not pt:
        log.error("alpha.json has no per_ticker; skipping discovery")
        return 0

    ns = _names_sectors()
    px = _last_prices()
    # offshore-attention z map (display-only over-extension caution); graceful if absent
    attn = {}
    atp = site / "factordata" / "attention.json"
    if atp.exists():
        try:
            attn = json.loads(atp.read_text()) or {}
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("attention.json unreadable (%s)", e)

    rows = [_row(tk, rec, ns, px, attn) for tk, rec in pt.items() if rec.get("alpha") is not None]
    rows.sort(key=lambda r: r["alpha"], reverse=True)
    strongest = rows[:TOP_N]
    weakest = rows[-TOP_N:][::-1]            # weakest first

    # Sectors overview — GICS sector mean alpha + share of its names in the global top quintile
    q_cut = rows[max(0, len(rows) // 5 - 1)]["alpha"] if rows else 0.0
    agg: dict[str, dict] = {}
    for r in rows:
        if r["sector"] in (None, "—"):
            continue
        a = agg.setdefault(r["sector"], {"n": 0, "sum": 0.0, "intop": 0})
        a["n"] += 1
        a["sum"] += r["alpha"]
        a["intop"] += 1 if r["alpha"] >= q_cut else 0
    sectors = sorted(
        [{"sector": s, "n": v["n"], "mean": round(v["sum"] / v["n"], 2),
          "intop": v["intop"], "pct": round(100 * v["intop"] / v["n"])}
         for s, v in agg.items()],
        key=lambda x: x["mean"], reverse=True)

    # Themes overview — curated narrow baskets ranked by mean sector-neutral alpha-z
    # + share in the universe-wide top quintile (same q_cut as Sectors). A current
    # snapshot context lens over the EXISTING alpha; baskets are NOT backtested.
    theme_cfg = config.load().get("themes", {}) or {}
    by_tk = {r["ticker"]: r for r in rows}
    themes = []
    for slug, spec in theme_cfg.items():
        mem = [by_tk[tk] for tk in spec.get("tickers", []) if tk in by_tk]
        if not mem:
            continue
        mean = sum(r["alpha"] for r in mem) / len(mem)
        intop = sum(1 for r in mem if r["alpha"] >= q_cut)
        themes.append({"slug": slug, "theme": spec.get("name", slug), "n": len(mem),
                       "mean": round(mean, 2), "intop": intop,
                       "pct": round(100 * intop / len(mem)),
                       "names": sorted(mem, key=lambda r: r["alpha"], reverse=True)})
    themes.sort(key=lambda x: x["mean"], reverse=True)

    # Sector drill — reuse alpha.json by_sector (already leaders/laggards with sector_rank);
    # enrich each row with a position band + last price.
    def _enrich(lst):
        return [dict(r, band=_band(r.get("alpha")), price=_price(px, r["ticker"]))
                for r in (lst or [])]

    by_sector = {sec: {"n": blk.get("n"),
                       "leaders": _enrich(blk.get("leaders"))[:SECTOR_TOP],
                       "laggards": _enrich(blk.get("laggards"))}
                 for sec, blk in (alpha.get("by_sector") or {}).items()}
    sector_order = [s["sector"] for s in sectors if s["sector"] in by_sector]

    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    from engine.i18n import td, tr
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    env.globals.update(td=td, tr=tr)
    html = env.get_template("discovery.html.j2").render(
        strongest=strongest, weakest=weakest, sectors=sectors, themes=themes,
        by_sector=by_sector, sector_order=sector_order, entry_meta=ENTRY_META,
        as_of=alpha.get("as_of"), windows=alpha.get("windows") or {},
        n=alpha.get("n"), built=built)
    (site / "discovery.html").write_text(html)
    log.info("wrote %s/discovery.html (%d names, %d sectors, %d KB)",
             site, alpha.get("n"), len(by_sector), len(html) // 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
