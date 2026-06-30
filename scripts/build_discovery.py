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

from engine import confluence_tiers, signal_gate  # noqa: E402 — MACD-2D x StochRSI-3D buy gate
from engine.extension import (GRADES, VAL_LABELS, cohort_stretch,  # noqa: E402
                              extension_signals, valuation_vs_history)
from engine.top_picks import (ALPHA_W, TILT_LEGS, TILT_W,  # noqa: E402
                              band, compute_scores, entry_meta)
from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_discovery")

TOP_N = 40          # length of the global strongest / weakest lists
SECTOR_TOP = 18     # rows shown per sector drill
BUYZONE_N = 12      # length of the "buy-zone" sweet-spot strip
BUYZONE_MIN = 0.3   # a buy-zone pick must still be a genuine top pick (top_score >= this)

# confluence-tier -> (en, zh, css) for the actionable BUY signal chip. T1/T2 are a CONFIRMED,
# just-crossed buy; T3 is the "about to cross" anticipation. Keyed by the cascade tier.
SIGNAL_LABELS = {
    "T1": ("Buy zone", "买入区", "sg-confirmed"),     # validated 3D master take, just-crossed
    "T2": ("Buy zone", "买入区", "sg-confirmed"),     # 2D MACD x 3D StochRSI just crossed
    "T3": ("About to cross", "即将交叉", "sg-imminent"),  # 3D StochRSI crossed, 2D MACD imminent
}


def _signal_verdicts(site: Path, closes) -> dict:
    """ticker -> the compact MACD-2D x StochRSI-3D confluence verdict that gates the Top-setups
    strip on us_stocks.html. PRIMARY source: site/factordata/signal_gate.json, written by
    build_stock_library in the SAME daily run (so the discovery board and the Top-setups strip
    agree exactly, and T1 — the validated §7 master take — is included). FALLBACK (standalone /
    first run): recompute the close-only cascade here (T2/T3/T4 only; T1 needs the §7 analysis),
    so the gate still applies. Never fatal: returns {} and the page degrades to no buy-zone."""
    p = site / "factordata" / "signal_gate.json"
    if p.exists():
        try:
            data = json.loads(p.read_text())
            v = data.get("verdicts") if isinstance(data, dict) else None
            if v:
                log.info("loaded signal_gate.json (%d verdicts)", len(v))
                return v
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("signal_gate.json unreadable (%s); recomputing cascade", e)
    if closes is None:
        return {}
    log.info("signal_gate.json absent — recomputing close-only cascade (no T1)")
    out: dict[str, dict] = {}
    for tk in closes.columns:
        try:
            s = closes[tk].dropna()
            if s.empty:
                continue
            casc = confluence_tiers.cascade(s, take_active=False)
            out[tk] = {"eligible": bool(casc.get("eligible")),
                       "tier_cascade": casc.get("tier"), "tier_sub": casc.get("sub"),
                       "ticks": casc.get("ticks"), "bars_to_cross": casc.get("bars_to_cross")}
        except Exception:  # noqa: BLE001 — one bad series must not 404 the page
            continue
    return out


def _names_sectors() -> dict:
    from engine.equity_factors import _names_sectors as ns
    try:
        return ns()
    except Exception as e:  # noqa: BLE001 — degrade to ticker-only labels
        log.warning("names/sectors load failed (%s)", e)
        return {}


def _closes_full():
    """Full daily close matrix (shallow ~3y cache) — feeds the extension + valuation reads.
    Never fatal: returns None and the chips degrade off."""
    try:
        from engine.equity_factors import _closes
        c = _closes()
        return c if c is not None and not c.empty else None
    except Exception as e:  # noqa: BLE001
        log.warning("closes load failed (%s); omitting extension/valuation chips", e)
        return None


def _fund_panel():
    try:
        return pd.read_parquet(config.data_dir() / "edgar" / "fundamentals_panel.parquet")
    except Exception as e:  # noqa: BLE001 — valuation chip is a nicety
        log.warning("fundamentals panel load failed (%s); omitting valuation chip", e)
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

    # extension / exhaustion + valuation-vs-own-history (display-only; validated downside read
    # in reports/top-picks-freshness-phase0.md — NEVER folded into the rank).
    closes = _closes_full()
    px = closes.iloc[-1] if closes is not None else None
    ext = extension_signals(closes) if closes is not None else {}
    val = valuation_vs_history(closes, _fund_panel()) if closes is not None else {}
    log.info("extension read on %d names (%d parabolic), valuation on %d",
             len(ext), sum(1 for v in ext.values() if v.get("parabolic")), len(val))

    # the MACD-2D x StochRSI-3D confluence verdict per name — the HARD gate on what is allowed
    # to read "Buy zone" (engine/signal_gate). Same source the Top-setups strip on us_stocks.html
    # gates on, so the two surfaces never disagree.
    verdicts = _signal_verdicts(site, closes)

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
        ex = ext.get(tk, {})
        vl = val.get(tk, {})
        en, zh, css = entry_meta(a.get("entry"))   # trend-position CONTEXT (not a buy call)
        g = ex.get("grade", "na")
        g_en, g_zh, g_css, g_caution = GRADES.get(g, GRADES["na"])
        vlab = vl.get("val_label")
        v_en, v_zh, v_css = VAL_LABELS.get(vlab, (None, None, None))
        # the actionable BUY signal: only a fresh MACD-2D x StochRSI-3D confluence (T1/T2/T3)
        # counts — a "Pullback" trend read is NOT a buy on its own.
        cv = verdicts.get(tk) or {}
        tier = cv.get("tier_cascade")
        buyable = signal_gate.is_buyable(cv)
        sg_en, sg_zh, sg_css = SIGNAL_LABELS.get(tier, (None, None, None))
        return {
            "ticker": tk, "name": name, "sector": sector, "price": _price(px, tk),
            "top_score": s["top_score"], "band": band(s["top_score"]),
            "alpha": s["alpha"], "alpha_band": band(s["alpha"]),
            "conviction_z": s["conviction_z"], "n_legs": s["n_legs"], "legs": s["legs"],
            "entry": a.get("entry"), "entry_en": en, "entry_zh": zh, "entry_css": css,
            # confluence BUY signal (the hard gate) — display fields for the template chip
            "buyable": buyable, "sig_tier": tier, "sig_ticks": cv.get("ticks"),
            "sig_btc": cv.get("bars_to_cross"),
            "sig_en": sg_en, "sig_zh": sg_zh, "sig_css": sg_css,
            "total_mom": a.get("total_mom"), "rev_1m": a.get("rev_1m"),
            "rev_pctile": a.get("rev_pctile"), "sector_rank": a.get("sector_rank"),
            "sector_n": a.get("sector_n"),
            "ins_buyers": ins.get("buyers") or 0, "ins_bps": _clean(ins.get("bps")),
            "attn_z": _clean(at.get("z")),   # offshore-attention z (display-only caution)
            # extension / exhaustion axis (display-only; never in the score)
            "grade": g, "grade_en": g_en, "grade_zh": g_zh, "grade_css": g_css,
            "grade_caution": g_caution, "ext_z": ex.get("ext_z"), "ext": ex.get("ext"),
            "near_52wh": ex.get("near_52wh"), "id_score": ex.get("id_score"),
            "parabolic": ex.get("parabolic", False),
            # valuation vs own ~3y history (display-only tail flag)
            "ey_pctile": vl.get("ey_pctile"), "val_label": vlab,
            "val_en": v_en, "val_zh": v_zh, "val_css": v_css,
        }

    rows = [r for r in (_row(tk, a) for tk, a in pt.items()) if r is not None]
    rows.sort(key=lambda r: r["top_score"], reverse=True)
    # collapse dual-class / multi-listings to the best-ranked variant (GOOG+GOOGL → one
    # slot) BEFORE any board is sliced, so no surface spends two rows on one company.
    from engine.setups import dedupe_dual_class
    rows = dedupe_dual_class(rows)
    strongest = rows[:TOP_N]
    weakest = rows[-TOP_N:][::-1]

    # cohort-stretch banner: how stretched is the LEADERSHIP cohort vs its own norms?
    # Display-only fragility/size-down context (crowding raises crash *probability*, it
    # does not time) — computed off the top-conviction quintile by Top-Pick score.
    cohort_n = max(8, len(rows) // 5)
    banner = cohort_stretch(rows[:cohort_n])

    # the "buy-zone" sweet spot: genuine top picks (conviction >= BUYZONE_MIN) that have ALSO
    # triggered the MACD-2D x StochRSI-3D confluence buy (T1/T2 just-crossed, or T3 about-to-
    # cross). HARD-gated — a high-conviction name that is downtrending on the 3D MACD/StochRSI
    # no longer reads "Buy zone" (the bug this fixes). Confirmed crosses (T1/T2) rank above the
    # T3 anticipation, then by conviction.
    _tier_rank = {"T1": 0, "T2": 0, "T3": 1}
    buyzone = sorted(
        [r for r in rows if r["buyable"] and r["top_score"] >= BUYZONE_MIN],
        key=lambda r: (_tier_rank.get(r["sig_tier"], 9), -r["top_score"]))[:BUYZONE_N]
    n_buyable = sum(1 for r in rows if r["buyable"])
    log.info("buy-zone: %d confluence-buyable names (%d in strip ≥%.1f conviction)",
             n_buyable, len(buyzone), BUYZONE_MIN)

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
        by_sector=by_sector, sector_order=sector_order,
        tilt_legs=list(TILT_LEGS), alpha_w=ALPHA_W, tilt_w=TILT_W, banner=banner,
        attn_threshold=float((config.load().get("wiki_pageviews") or {}).get("chip_threshold", 2.0)),
        as_of=alpha.get("as_of"), windows=alpha.get("windows") or {},
        n=len(rows), n_buyable=n_buyable, built=built)
    (site / "discovery.html").write_text(html)
    log.info("wrote %s/discovery.html (%d names, %d sectors, %d buy-zone, %d KB)",
             site, len(rows), len(by_sector), len(buyzone), len(html) // 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
