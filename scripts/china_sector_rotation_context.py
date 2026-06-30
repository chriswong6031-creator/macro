"""Cross-Shenwan + macro ROTATION context for every China sector-cycle leg.

The China sibling of scripts/sector_rotation_context.py. For each leg [start, end] of each
Shenwan L1 sector (and each A-share thematic basket) it measures, from the real domestic
tape, the relative-rotation backdrop — which Shenwan industries led/lagged, the
defensives-vs-cyclicals spread, the growth(电子/计算机/电新/军工)-vs-value(银行/能源/周期)
tilt, the Shanghai Composite return, and a plain-English risk-on/off + flight-to-safety read.

This is the factual substrate the China sector-cycle narratives are written and CHECKED
against (so a "rotation into policy beneficiaries" claim is verified against whether those
Shenwan groups actually led while the index behaved as stated). Pure-read.

Output: data/china_sector_cycles/leg_context.json — {series_id: {now_ctx, legs:{date:ctx}}},
series_id = Shenwan code (801080…) for sectors, "b-"+basket-id for baskets — matching the
engine.china_sector_cycles record ids.

Usage: python -m scripts.china_sector_rotation_context
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from engine import china_sector_cycles as ccc
from engine import china_sector_index as csi
from engine import sector_cycles as sc
from lib import config

log = logging.getLogger("china_sector_rotation_context")

# Shenwan-group rotation buckets (from ccc._SW group field). Defensives = the classic
# A-share safe-haven sleeves; Cyclicals = the beta sleeves; Growth/Value for the style tilt.
_GRP = {code: meta[4] for code, meta in ccc._SW.items()}
DEF = [c for c, g in _GRP.items() if g in ("Defensive",)] + ["801780", "801120"]   # +banks, food&bev (A-share havens)
CYC = [c for c, g in _GRP.items() if g in ("Cyclical", "Energy", "Rate-sens")]
GROWTH = [c for c, g in _GRP.items() if g in ("Technology", "Defense")]
VALUE = [c for c, g in _GRP.items() if g in ("Financials", "Energy", "Cyclical")]
SNAME = {code: meta[1] for code, meta in ccc._SW.items()}    # short EN name


def _pct(x):
    return None if x is None else round(float(x) * 100, 1)


def _seg_ret(s: pd.Series, start: str, end: str):
    if s is None or s.empty:
        return None
    seg = s.loc[start:end].dropna()
    if len(seg) >= 2:
        return float(seg.iloc[-1] / seg.iloc[0] - 1.0)
    a, b = s.loc[:start].dropna(), s.loc[:end].dropna()
    if a.empty or b.empty:
        return None
    return float(b.iloc[-1] / a.iloc[-1] - 1.0)


def _grp_avg(rets: dict, codes) -> float | None:
    vals = [rets[c] for c in codes if rets.get(c) is not None]
    return float(np.nanmean(vals)) if vals else None


def leg_ctx(sw: dict, bench: pd.Series, start: str, end: str,
            this_code: str | None, this_series: pd.Series | None = None) -> dict:
    """Cross-Shenwan + macro backdrop for one leg [start, end]. this_code = the Shenwan code
    being narrated (None for a basket); this_series = the basket's own level series."""
    rets = {c: _seg_ret(s, start, end) for c, s in sw.items()}
    rank = sorted([c for c in rets if rets[c] is not None], key=lambda c: rets[c], reverse=True)
    this_rank = rank.index(this_code) + 1 if this_code in rank else None
    if this_code is not None:
        this_ret = rets.get(this_code)
    else:
        this_ret = _seg_ret(this_series, start, end)

    defv, cycv = _grp_avg(rets, DEF), _grp_avg(rets, CYC)
    grv, vav = _grp_avg(rets, GROWTH), _grp_avg(rets, VALUE)
    bret = _seg_ret(bench, start, end)
    gv = (grv - vav) if (grv is not None and vav is not None) else None

    sig: list[str] = []
    if defv is not None and cycv is not None:
        if (defv - cycv) > 0.04 and (bret is not None and bret < 0):
            sig.append(f"FLIGHT-TO-SAFETY: defensives led ({_pct(defv)}% vs cyclicals {_pct(cycv)}%) "
                       f"while SHCOMP fell {_pct(bret)}% — risk-off rotation, not sector strength")
        elif (cycv - defv) > 0.04 and (bret is not None and bret > 0):
            sig.append(f"RISK-ON BETA: cyclicals led ({_pct(cycv)}% vs defensives {_pct(defv)}%) "
                       f"with SHCOMP +{_pct(bret)}% — broad beta rally")
    if gv is not None and abs(gv) > 0.05:
        side = "GROWTH (电子/计算机/电新/军工)" if gv > 0 else "VALUE (银行/能源/周期)"
        sig.append(f"STYLE TILT: {side} led by {_pct(abs(gv))}pp — "
                   f"{'liquidity/theme-driven tape' if gv > 0 else 'policy/cyclical-value tape'}")
    if this_rank is not None and this_rank <= 3 and this_ret is not None:
        sig.append(f"LEADERSHIP: {SNAME.get(this_code, this_code)} ranked #{this_rank}/{len(rank)} "
                   f"({_pct(this_ret)}%) — among the strongest Shenwan industries this leg")
    elif this_rank is not None and this_rank >= len(rank) - 2 and this_ret is not None:
        sig.append(f"LAGGARD: {SNAME.get(this_code, this_code)} ranked #{this_rank}/{len(rank)} "
                   f"({_pct(this_ret)}%) — among the weakest this leg")
    if bret is not None and abs(bret) > 0.12:
        sig.append(f"INDEX {'SURGE' if bret > 0 else 'DRAWDOWN'}: SHCOMP {_pct(bret)}% — a broad "
                   f"market {'up' if bret > 0 else 'down'}-leg, sector move is partly beta")

    return {
        "this_ret": _pct(this_ret), "this_rank": this_rank, "n_universe": len(rank),
        "leaders": [f"{SNAME.get(c, c)} {_pct(rets[c])}%" for c in rank[:3]],
        "laggards": [f"{SNAME.get(c, c)} {_pct(rets[c])}%" for c in rank[-3:]],
        "defensives_avg": _pct(defv), "cyclicals_avg": _pct(cycv),
        "growth_minus_value": _pct(gv), "shcomp_ret": _pct(bret),
        "signals": sig,
    }


def compute_contexts() -> dict:
    bench = csi.benchmark_close()
    d = ccc.compute()
    if not d:
        return {}
    sw = {c: csi.sw_close(c) for c in ccc._SW}
    last = pd.Timestamp(d["meta"]["asOf"])
    start6 = (last - pd.DateOffset(months=6)).strftime("%Y-%m-%d")
    out = {}

    # sectors — rank within the 31 Shenwan industries
    for s in d["sectors"]:
        code, turns = s["id"], s["turns"]
        legs = {}
        for i in range(len(turns) - 1):
            a, b = turns[i], turns[i + 1]
            legs[a["date"]] = {"end": b["date"], "dir": "rally" if b["k"] == "peak" else "selloff",
                               "mag_pct": b["mag_pct"], "ctx": leg_ctx(sw, bench, a["date"], b["date"], code)}
        out[code] = {"shenwan_code": code, "name": s["name"], "phase": s["now"]["phaseLabel"],
                     "pos": s["now"]["pos"], "rs_rank": s["now"].get("rs_rank"),
                     "now_ctx": leg_ctx(sw, bench, start6, str(last.date()), code), "legs": legs}

    # baskets — macro/rotation backdrop (no Shenwan rank); this_ret from the basket's own tape
    try:
        from engine.baskets_china import compute_china_baskets
        bdata = compute_china_baskets()
        chart = (bdata or {}).get("chart") or {}
    except Exception as e:  # noqa: BLE001
        log.warning("china basket series unavailable: %s", e)
        chart = {}
    for b in d.get("baskets", []):
        bid = b.get("basket_id") or b["id"].replace("b-", "", 1)
        series = ccc._basket_series(bid, chart) if chart else None
        turns = b["turns"]
        legs = {}
        for i in range(len(turns) - 1):
            a, c = turns[i], turns[i + 1]
            legs[a["date"]] = {"end": c["date"], "dir": "rally" if c["k"] == "peak" else "selloff",
                               "mag_pct": c["mag_pct"],
                               "ctx": leg_ctx(sw, bench, a["date"], c["date"], None, series)}
        out[b["id"]] = {"basket_id": bid, "name": b["name"], "phase": b["now"]["phaseLabel"],
                        "pos": b["now"]["pos"], "rs_rank": b["now"].get("rs_rank"),
                        "now_ctx": leg_ctx(sw, bench, start6, str(last.date()), None, series), "legs": legs}
    return out


def main() -> int:
    out = compute_contexts()
    if not out:
        log.warning("china_sector_rotation_context: no data — skipped")
        return 0
    dest = Path(config.ROOT) / "data" / "china_sector_cycles" / "leg_context.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("wrote %s (%d series, %d legs)", dest, len(out), sum(len(v["legs"]) for v in out.values()))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
