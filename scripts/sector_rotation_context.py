"""Cross-sector + macro-regime ROTATION context for every sector-cycle leg.

For each leg [start, end] of each US sector ETF it measures, from real prices, the
relative-rotation and macro-regime backdrop — which sectors led/lagged, the
defensives-vs-cyclicals spread, risk-on/off (high-beta vs low-vol, VIX), the
rate/dollar/quad regime and breadth — and derives plain-English ROTATION SIGNALS
(flight-to-safety, "defensives starved" by a tech-led melt-up, rate-regime move,
strong-dollar headwind, narrow breadth, quad). This is the factual substrate the
sector-cycle narratives are written against (so a "rotation into safety" claim is
checked against whether defensives actually outperformed while VIX rose), and a
first-class artifact for the flows/rotation analysis.

Output: data/sector_cycles/leg_context.json — {sector_id: {now_ctx, legs:{date:ctx}}}.
Pure-read; uses engine.inputs.yahoo_closes() + engine.sector_cycles turning points.

Usage: python -m scripts.sector_rotation_context
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from engine import sector_cycles as sc
from engine.inputs import yahoo_closes
from lib import config

log = logging.getLogger("sector_rotation_context")

SECTORS = ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]
SNAME = {"XLB": "Materials", "XLC": "Comm", "XLE": "Energy", "XLF": "Financials", "XLI": "Industrials",
         "XLK": "Tech", "XLP": "Staples", "XLRE": "Real Estate", "XLU": "Utilities", "XLV": "Health", "XLY": "Discretionary"}
DEF = ["XLP", "XLU", "XLV"]
CYC = ["XLK", "XLY", "XLF", "XLI", "XLB", "XLE"]


def _wret(cl: pd.DataFrame, tk: str, start: str, end: str):
    if tk not in cl:
        return None
    seg = cl[tk].loc[start:end].dropna()
    if len(seg) >= 2:
        return float(seg.iloc[-1] / seg.iloc[0] - 1.0)
    a, b = cl[tk].loc[:start].dropna(), cl[tk].loc[:end].dropna()
    if a.empty or b.empty:
        return None
    return float(b.iloc[-1] / a.iloc[-1] - 1.0)


def _lvl(cl: pd.DataFrame, tk: str, when: str, side="last"):
    if tk not in cl:
        return None
    s = cl[tk].loc[:when].dropna() if side == "last" else cl[tk].loc[when:].dropna()
    return None if s.empty else float(s.iloc[-1] if side == "last" else s.iloc[0])


def _pct(x):
    return None if x is None else round(x * 100, 1)


def leg_ctx(cl: pd.DataFrame, start: str, end: str, this_tk: str) -> dict:
    secr = {t: _wret(cl, t, start, end) for t in SECTORS}
    rank = sorted([t for t in SECTORS if secr[t] is not None], key=lambda t: secr[t], reverse=True)
    this_rank = rank.index(this_tk) + 1 if this_tk in rank else None
    defv = float(np.nanmean([secr[t] for t in DEF if secr[t] is not None]))
    cycv = float(np.nanmean([secr[t] for t in CYC if secr[t] is not None]))
    spy = _wret(cl, "SPY", start, end)
    smh = _wret(cl, "SMH", start, end)
    sphb_splv = (_wret(cl, "SPHB", start, end) or 0) - (_wret(cl, "SPLV", start, end) or 0)
    iwf_iwd = (_wret(cl, "IWF", start, end) or 0) - (_wret(cl, "IWD", start, end) or 0)
    rsp_spy = (_wret(cl, "RSP", start, end) or 0) - (spy or 0)
    hyg_lqd = (_wret(cl, "HYG", start, end) or 0) - (_wret(cl, "LQD", start, end) or 0)
    tlt = _wret(cl, "TLT", start, end)
    vix0, vix1 = _lvl(cl, "^VIX", start, "first"), _lvl(cl, "^VIX", end, "last")
    dxy = _wret(cl, "DX-Y.NYB", start, end)
    oil, cu, au = _wret(cl, "CL=F", start, end), _wret(cl, "HG=F", start, end), _wret(cl, "GC=F", start, end)
    cu_au = (cu or 0) - (au or 0)

    sig: list[str] = []
    vix_up = bool(vix1 is not None and vix0 is not None and vix1 - vix0 > 2)
    vix_dn = bool(vix1 is not None and vix0 is not None and vix1 - vix0 < -2)
    risk_off = sphb_splv < -0.03 and (vix_up or (vix1 and vix1 > 22))
    risk_on = sphb_splv > 0.03 and (vix_dn or (vix1 and vix1 < 18))
    if (defv - cycv) > 0.03 and (vix_up or risk_off):
        sig.append(f"FLIGHT-TO-SAFETY: defensives led (+{_pct(defv)}% vs cyclicals {_pct(cycv)}%) with VIX {round(vix0)}->{round(vix1)} — risk-off rotation into safety, not sector strength")
    if this_tk in DEF and secr[this_tk] is not None and secr[this_tk] < cycv - 0.03 and (vix_dn or (vix1 and vix1 < 18)):
        sig.append(f"DEFENSIVES STARVED: {SNAME[this_tk]} lagged while risk-on led (SMH {_pct(smh)}%, high-beta-low-vol {_pct(sphb_splv)}, VIX {round(vix0) if vix0 else '?'}->{round(vix1) if vix1 else '?'}) — nothing wrong with the defensive, money simply rotated to tech/cyclicals")
    if smh is not None and smh > 0.15 and (vix1 and vix1 < 20) and iwf_iwd > 0.02:
        sig.append(f"TECH/SEMIS-LED RISK-ON: semis +{_pct(smh)}%, growth>value ({_pct(iwf_iwd)}), calm VIX — a melt-up that pulls flows OUT of defensives")
    if this_tk in CYC and this_rank is not None and this_rank <= 3 and risk_on:
        sig.append(f"RISK-ON LEADERSHIP: {SNAME[this_tk]} ranked #{this_rank}/11 in a risk-on tape")
    if tlt is not None and abs(tlt) > 0.06:
        d = f"yields SURGED (TLT {_pct(tlt)}%)" if tlt < 0 else f"yields FELL (TLT +{_pct(tlt)}%)"
        sig.append(f"RATE-REGIME MOVE: {d}; rate-sensitive XLU/XLRE/REITs move inversely to yields")
    if dxy is not None and abs(dxy) > 0.025:
        sig.append(f"DOLLAR {'STRONGER' if dxy > 0 else 'WEAKER'} ({_pct(dxy)}% DXY) — {'headwind' if dxy > 0 else 'tailwind'} for Materials/Energy/multinationals")
    if rsp_spy < -0.02:
        sig.append(f"NARROW BREADTH: equal-weight lagged cap-weight by {_pct(rsp_spy)}% — a mega-cap-led tape")
    elif rsp_spy > 0.02:
        sig.append(f"BROADENING: equal-weight beat cap-weight by +{_pct(rsp_spy)}% — broad participation")
    growth_up, infl_up = cycv > defv, ((oil or 0) > 0.05 or cu_au > 0.05)
    quad = ("reflation/growth-up" if growth_up and infl_up else "goldilocks/growth-up-disinflation" if growth_up
            else "stagflation-ish" if infl_up else "slowdown/deflation-scare")
    sig.append(f"QUAD read: {quad} (cyclicals {_pct(cycv)}% vs defensives {_pct(defv)}%; oil {_pct(oil)}%, copper-gold {_pct(cu_au)})")

    return {
        "this_ret": _pct(secr.get(this_tk)), "this_rank": this_rank,
        "leaders": [f"{SNAME[t]} {_pct(secr[t])}%" for t in rank[:3]],
        "laggards": [f"{SNAME[t]} {_pct(secr[t])}%" for t in rank[-3:]],
        "defensives_avg": _pct(defv), "cyclicals_avg": _pct(cycv), "spy": _pct(spy), "semis_smh": _pct(smh),
        "highbeta_minus_lowvol": _pct(sphb_splv), "growth_minus_value": _pct(iwf_iwd),
        "breadth_rsp_minus_spy": _pct(rsp_spy), "credit_hyg_minus_lqd": _pct(hyg_lqd),
        "vix": [round(vix0) if vix0 else None, round(vix1) if vix1 else None],
        "tlt_ret": _pct(tlt), "dxy_ret": _pct(dxy), "oil_ret": _pct(oil), "copper_gold": _pct(cu_au),
        "quad": quad, "signals": sig,
    }


def compute_contexts() -> dict:
    cl = yahoo_closes()
    d = sc.compute()
    if not d:
        return {}
    last = cl.index[-1]
    start6 = (last - pd.DateOffset(months=6)).strftime("%Y-%m-%d")
    out = {}
    for s in d["sectors"]:
        tk, turns = s["ticker"], s["turns"]
        legs = {}
        for i in range(len(turns) - 1):
            a, b = turns[i], turns[i + 1]
            legs[a["date"]] = {"end": b["date"], "dir": "rally" if b["k"] == "peak" else "selloff",
                               "mag_pct": b["mag_pct"], "ctx": leg_ctx(cl, a["date"], b["date"], tk)}
        out[s["id"]] = {"ticker": tk, "name": s["name"], "phase": s["now"]["phaseLabel"],
                        "pos": s["now"]["pos"], "rs_rank": s["now"].get("rs_rank"),
                        "now_ctx": leg_ctx(cl, start6, str(last.date()), tk), "legs": legs}
    return out


def main() -> int:
    out = compute_contexts()
    if not out:
        log.warning("sector_rotation_context: no data — skipped")
        return 0
    dest = config.ROOT / "data" / "sector_cycles" / "leg_context.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("wrote %s (%d sectors, %d legs)", dest, len(out), sum(len(v["legs"]) for v in out.values()))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
