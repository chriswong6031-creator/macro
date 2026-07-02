"""China Sector Cycle Intelligence — the China port of engine.sector_cycles, fused with
the evidence-gated forward layer (engine.china_sector_pathway).

Where the US page derives each GICS sector ETF's cycle from its price tape, THIS one runs
the SAME reproducible cycle kernel (engine.sector_cycles._record_core — rebased price, a
0-100 detrended-stochastic oscillator, ZigZag turns, the 5-phase wheel, a median-half-cycle
next-turn projection, RS leadership) over the authoritative domestic series:

  • SECTORS  — all 31 Shenwan (申万) L1 industry indices (data/china_sectors/<code>.parquet,
    full OHLCV, deep to 1999/2014/2021), via engine.china_sector_index.sw_close. The clean,
    survivorship-free sector tape — far deeper than the shallow on-shore sector ETFs.
  • BASKETS  — the 22 curated A-share thematic baskets (engine.baskets_china), each on its
    equal-weight member level series (the SAME series baskets_china.html charts).

Benchmark for relative strength = 000001.SS (Shanghai Composite, deep to 1999 to match the
Shenwan history), NOT the shallow CSI 300 ETF.

FORWARD HONESTY (load-bearing — research/CHINA_SECTOR_PATHWAY_PHASE0.md). Phase-0 proved NO
single China driver clears a strict FWER bar on monthly sector forward returns, and the
A-share sector trend-gate edge FAILS here. So the forward layer is deliberately layered by
how much the evidence supports it:

  1. STATE SIGNATURE (every sector/basket) — where price sits on the washout↔euphoria axis
     (own-history percentile of distance-from-200d + drawdown), the one signature Phase-0
     found stable across all four GS sectors. Descriptive, robust.
  2. CYCLE RHYTHM (every sector/basket) — the median-half-cycle next-turn projection as a
     point + IQR band. A rhythm estimate, explicitly NOT backtested — surfaced as the
     "prominent point" the user asked for, honestly bracketed.
  3. CONDITIONAL ODDS (the 4 GS-style sectors only — Banks/Consumption/Real Estate/Auto)
     — engine.china_sector_pathway's empirical Wilson-CI conditional ("when the setup looked
     like today, forward-Nm return was positive X% vs Y% base rate") + the sign-stable lead
     cluster attribution. Conditioning, not a point forecast, not alpha.

Pure-read + additive: any per-sector/basket failure is logged and skipped, never fatal.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine import china_sector_index as csi
from engine import sector_cycles as sc

log = logging.getLogger(__name__)

CN_TODAY_PAD = 0.5        # forward x-headroom (yrs) — wider than the US page so near-term
                          # projected turns are visible on the chart (the user's "prominent point").
CN_ZZ_PCT = 18.0          # fixed China sector ZigZag threshold (higher A-share vol than US's 14%);
                          # FIXED, never vol-scaled, so detected turn dates — and any narrative
                          # keys bound to them — never drift (the documented basket gotcha).

# Shenwan L1 dashboard taxonomy: code -> (en, short, zh, short_zh, group). Names are the
# canonical Shenwan L1 industry names (collectors/china_sectors.py SW_L1).
_SW: dict[str, tuple[str, str, str, str, str]] = {
    "801010": ("Agriculture",          "Agriculture",  "农林牧渔", "农业",   "Consumer"),
    "801030": ("Chemicals",            "Chemicals",    "基础化工", "化工",   "Cyclical"),
    "801040": ("Steel",                "Steel",        "钢铁",     "钢铁",   "Cyclical"),
    "801050": ("Nonferrous Metals",    "Metals",       "有色金属", "有色",   "Cyclical"),
    "801080": ("Electronics",          "Electronics",  "电子",     "电子",   "Technology"),
    "801110": ("Home Appliances",      "Appliances",   "家用电器", "家电",   "Consumer"),
    "801120": ("Food & Beverage",      "Food & Bev",   "食品饮料", "食饮",   "Consumer"),
    "801130": ("Textiles & Apparel",   "Textiles",     "纺织服饰", "纺服",   "Consumer"),
    "801140": ("Light Manufacturing",  "Light Mfg",    "轻工制造", "轻工",   "Consumer"),
    "801150": ("Pharma & Biotech",     "Pharma",       "医药生物", "医药",   "Defensive"),
    "801160": ("Utilities",            "Utilities",    "公用事业", "公用",   "Defensive"),
    "801170": ("Transportation",       "Transport",    "交通运输", "交运",   "Cyclical"),
    "801180": ("Real Estate",          "Real Estate",  "房地产",   "地产",   "Rate-sens"),
    "801200": ("Retail & Commerce",    "Retail",       "商贸零售", "零售",   "Consumer"),
    "801210": ("Consumer Services",    "Services",     "社会服务", "服务",   "Consumer"),
    "801230": ("Conglomerates",        "Conglom",      "综合",     "综合",   "Other"),
    "801710": ("Building Materials",   "Bldg Mat",     "建筑材料", "建材",   "Cyclical"),
    "801720": ("Construction",         "Construction", "建筑装饰", "建筑",   "Cyclical"),
    "801730": ("Power Equipment",      "Power Eqp",    "电力设备", "电新",   "Technology"),
    "801740": ("Defense & Military",   "Defense",      "国防军工", "军工",   "Defense"),
    "801750": ("Computers",            "Computers",    "计算机",   "计算机", "Technology"),
    "801760": ("Media",                "Media",        "传媒",     "传媒",   "Technology"),
    "801770": ("Telecoms",             "Telecoms",     "通信",     "通信",   "Technology"),
    "801780": ("Banks",                "Banks",        "银行",     "银行",   "Financials"),
    "801790": ("Non-bank Financials",  "Brokers",      "非银金融", "非银",   "Financials"),
    "801880": ("Automobiles",          "Autos",        "汽车",     "汽车",   "Cyclical"),
    "801890": ("Machinery",            "Machinery",    "机械设备", "机械",   "Cyclical"),
    "801950": ("Coal",                 "Coal",         "煤炭",     "煤炭",   "Energy"),
    "801960": ("Oil & Petrochem",      "Oil & Gas",    "石油石化", "石化",   "Energy"),
    "801970": ("Environmental",        "Environ",      "环保",     "环保",   "Other"),
    "801980": ("Beauty & Care",        "Beauty",       "美容护理", "美护",   "Consumer"),
}

_GROUP_ZH = {
    "Technology": "科技成长", "Cyclical": "周期", "Energy": "能源", "Financials": "金融",
    "Consumer": "消费", "Defensive": "防御", "Rate-sens": "利率敏感", "Defense": "国防军工",
    "Other": "综合其他",
}

# the four GS-style headline sectors carry the evidence-gated conditional forward layer.
# Shenwan code -> engine.china_sector_pathway key. Consumption maps to Food & Beverage (the
# dominant sleeve of the GS consumption composite the pathway engine actually conditions on).
_GS_BY_SW = {"801780": "banks", "801180": "real_estate", "801880": "auto", "801120": "consumption"}


def _accent(i: int, n: int) -> str:
    """Evenly-spaced, dark-bg-legible hue per series so overlaid lines stay distinct."""
    hue = round((i * 360.0 / max(n, 1) + 18) % 360)
    return f"hsl({hue} 62% 62%)"


def _signature(full: pd.Series) -> dict | None:
    """Washout(0)↔euphoria(100) state read — the Phase-0-stable signature (own-history
    percentile of distance-from-200d + drawdown-from-1y-high). Reuses the exact pathway
    engine logic so the cycles page and the sector desk can never disagree on it."""
    try:
        from engine.china_sector_pathway import _position
        sig = _position(full)
        return sig if sig and sig.get("score") is not None else None
    except Exception as e:  # noqa: BLE001
        log.debug("signature failed: %s", e)
        return None


def _pathway_block(gs_key: str) -> dict | None:
    """The evidence-gated conditional forward layer for one GS-style sector (Wilson-CI odds +
    sign-stable lead-cluster attribution + honest caveat). Display-only conditioning context."""
    try:
        from engine import china_sector_pathway as pw
        p = pw.pathway_for(gs_key)
    except Exception as e:  # noqa: BLE001
        log.warning("china_sector_cycles: pathway %s failed: %s", gs_key, e)
        return None
    if not p:
        return None
    return {
        "key": p.get("key"), "en": p.get("en"), "zh": p.get("zh"), "bbg": p.get("bbg"),
        "setup": p.get("setup"), "conditional": p.get("conditional"), "position": p.get("position"),
        "narrative_en": p.get("narrative_en"), "narrative_zh": p.get("narrative_zh"),
        "caveat_en": p.get("caveat_en"), "caveat_zh": p.get("caveat_zh"),
        "as_of": p.get("as_of"),
    }


def build_sector(code: str, meta: tuple, accent: str, bench: pd.Series | None,
                 win_start: pd.Timestamp, last_ts: pd.Timestamp) -> dict | None:
    """One Shenwan L1 index -> its full cycle record (price, oscillator, turns, phase,
    projection, RS leadership, washout↔euphoria signature, + GS conditional forward if mapped)."""
    full = csi.sw_close(code)
    if full is not None:
        full = full[full.index <= last_ts]   # PIT: never read tape past the as-of edge
    if full is None or len(full) < 300:
        log.warning("china_sector_cycles: %s too thin (%s rows) — skipped", code,
                    0 if full is None else len(full))
        return None
    core = sc._record_core(full, win_start, full.index[-1], pct=CN_ZZ_PCT)
    if core is None:
        return None
    en, short, zh, short_zh, group = meta
    rec = dict(core)
    rec.update({
        "id": code, "shenwan_code": code, "ticker": code, "kind": "sector",
        "name": en, "short": short, "name_zh": zh, "short_zh": short_zh,
        "group": group, "group_zh": _GROUP_ZH.get(group, group), "accent": accent,
    })
    sc._apply_leadership(rec, sc._basket_rs(full, bench))
    sig = _signature(full)
    if sig:
        rec["now"]["signature"] = sig
    gs = _GS_BY_SW.get(code)
    if gs:
        pb = _pathway_block(gs)
        if pb:
            rec["pathway"] = pb
    return rec


def _basket_series(bid: str, chart: dict) -> pd.Series | None:
    """Reconstruct one basket's equal-weight level series from the baskets_china chart payload
    (dates + per-basket level) — the SAME series the baskets_china page renders."""
    lvl = (chart.get("baskets") or {}).get(bid)
    dates = chart.get("dates") or []
    if not lvl or not dates or len(lvl) != len(dates):
        return None
    s = pd.Series(lvl, index=pd.to_datetime(dates), dtype="float64").dropna()
    return s if len(s) >= 300 else None


def build_basket(b: dict, chart: dict, accent: str, bench: pd.Series | None,
                 win_start: pd.Timestamp, last_ts: pd.Timestamp) -> dict | None:
    """One thematic basket -> its cycle record, off the equal-weight member level series."""
    bid = b.get("id")
    full = _basket_series(bid, chart)
    if full is not None:
        full = full[full.index <= last_ts]   # PIT: respect the as-of edge
    if full is None or len(full) < 300:
        return None
    # vol-scaled threshold, but floored at the China sector constant (18%) not the US 14% —
    # so a quiet A-share basket isn't a more sensitive turn-detector than a China sector.
    core = sc._record_core(full, win_start, full.index[-1], pct=max(CN_ZZ_PCT, sc._zz_pct_for(full)))
    if core is None:
        return None
    cat = b.get("category") or "Thematic"
    rec = dict(core)
    rec.update({
        "id": "b-" + bid, "basket_id": bid, "ticker": b.get("etf_proxy") or "", "kind": "basket",
        "name": b.get("name") or bid, "short": b.get("name") or bid,
        "name_zh": b.get("name_zh") or b.get("name") or bid,
        "short_zh": b.get("name_zh") or b.get("name") or bid,
        "group": cat, "group_zh": b.get("category_zh") or cat, "accent": accent,
        "etf_proxy": b.get("etf_proxy"), "thesis": b.get("thesis"), "thesis_zh": b.get("thesis_zh"),
        "n_members": b.get("n_members"),
    })
    sc._apply_leadership(rec, sc._basket_rs(full, bench))
    sig = _signature(full)
    if sig:
        rec["now"]["signature"] = sig
    return rec


def _rank_rs(items: list[dict]) -> None:
    ranked = sorted([s for s in items if s["now"].get("rs_63d") is not None],
                    key=lambda s: s["now"]["rs_63d"], reverse=True)
    for n, s in enumerate(ranked, 1):
        s["now"]["rs_rank"] = n


def _global_last(bench: pd.Series | None) -> pd.Timestamp:
    """The page's 'today' / right edge — the benchmark's last date (current, daily), falling
    back to the deepest Shenwan series, then the wall clock. One cheap pass, no double build."""
    if bench is not None and not bench.empty:
        return bench.index.max()
    last = None
    for code in _SW:
        s = csi.sw_close(code)
        if s is not None and not s.empty:
            last = s.index.max() if last is None else max(last, s.index.max())
    return last or pd.Timestamp.today().normalize()


def compute(asof: str | None = None) -> dict | None:
    """Top-level: build every Shenwan L1 sector + every China thematic basket cycle record,
    plus page meta. Returns None if the China sector tape can't be loaded."""
    bench = csi.benchmark_close()
    if bench is not None and asof:
        bench = bench[bench.index <= pd.Timestamp(asof)]

    last_ts = _global_last(bench)
    if asof:
        last_ts = min(last_ts, pd.Timestamp(asof))
    win_start = last_ts - pd.DateOffset(years=sc.WINDOW_YEARS)

    # ---- sectors (all 31 Shenwan L1 indices) — single build pass ----
    codes = list(_SW.keys())
    n = len(codes)
    sectors = []
    for i, code in enumerate(codes):
        try:
            rec = build_sector(code, _SW[code], _accent(i, n), bench, win_start, last_ts)
        except Exception as e:  # noqa: BLE001
            log.exception("china_sector_cycles: sector %s failed: %s", code, e)
            rec = None
        if rec:
            sectors.append(rec)
    if not sectors:
        log.warning("china_sector_cycles: no sectors built")
        return None
    _rank_rs(sectors)

    # ---- thematic baskets (off the baskets_china equal-weight member series) ----
    baskets = []
    try:
        from engine.baskets_china import compute_china_baskets
        bdata = compute_china_baskets()
    except Exception as e:  # noqa: BLE001
        log.warning("china_sector_cycles: baskets engine failed: %s", e)
        bdata = None
    if bdata and bdata.get("chart") and bdata.get("baskets"):
        chart = bdata["chart"]
        blist = bdata["baskets"]
        nb = len(blist)
        for i, b in enumerate(blist):
            try:
                rec = build_basket(b, chart, _accent(i * 3 + 1, max(nb * 3, 1)), bench, win_start, last_ts)
            except Exception as e:  # noqa: BLE001
                log.exception("china_sector_cycles: basket %s failed: %s", b.get("id"), e)
                rec = None
            if rec:
                baskets.append(rec)
        _rank_rs(baskets)
        baskets.sort(key=lambda b: (b.get("group") or "", b["name"]))

    x_lo = round(sc._yf(win_start), 3)
    x_hi = round(sc._yf(last_ts) + CN_TODAY_PAD, 3)
    x_lo_default = round(sc._yf(last_ts - pd.DateOffset(years=sc.DEFAULT_WINDOW_YEARS)), 3)
    return {
        "meta": {
            "asOf": str(last_ts.date()),
            "today": round(sc._yf(last_ts), 3),
            "xDomain": [x_lo, x_hi],
            "xDomainDefault": [x_lo_default, x_hi],
            "window_years": sc.WINDOW_YEARS,
            "default_window_years": sc.DEFAULT_WINDOW_YEARS,
            "rebaseDate": str(win_start.date()),
            "benchmark": "SHCOMP", "benchmark_zh": "上证综指",
            "region": "china",
            "forecastPoint": True,     # frontend: render the prominent projected-next-turn marker
            "experimental": True,      # frontend/template: show the EXPERIMENTAL / honest-forecast frame
            "n_sectors": len(sectors), "n_baskets": len(baskets),
        },
        "phases": sc.PHASES,
        "sectors": sectors,
        "baskets": baskets,
    }


def append_forward_log(data: dict) -> int:
    """Append today's per-series cycle SIGNAL to an append-only, point-in-time log
    (data/china_sector_cycles/forward_log.parquet), keyed by (date, id), keep-FIRST-per-date
    so a past day's stamped signal is never rewritten. A future grader joins these to realized
    forward returns to MEASURE the cycle/signature/pathway calls — the path to an earned,
    rather than asserted, forecast accuracy (nothing in the repo grades these today). Display/
    research-only; never read back into any score. Additive — failure is logged, not raised."""
    try:
        from lib import config
    except Exception:  # noqa: BLE001
        return 0
    rows = []
    asof = (data.get("meta") or {}).get("asOf")
    for rec in (data.get("sectors", []) + data.get("baskets", [])):
        nw = rec.get("now") or {}
        pr = rec.get("proj") or {}
        sig = nw.get("signature") or {}
        pw = rec.get("pathway") or {}
        cond = pw.get("conditional") or {}
        h6 = cond.get("h6") or cond.get("h3") or {}
        rows.append({
            "date": asof, "id": rec.get("id"), "kind": rec.get("kind"), "name": rec.get("name"),
            "phase": nw.get("phase"), "pos": nw.get("pos"), "osc_slope": nw.get("osc_slope"),
            "signature": sig.get("score"), "signal": nw.get("signal"),
            "above200d": nw.get("above200d"), "rs_63d": nw.get("rs_63d"), "rs_rank": nw.get("rs_rank"),
            "proj_next": pr.get("nextTurn"), "proj_central": pr.get("central"),
            "proj_lo": pr.get("low"), "proj_hi": pr.get("high"),  # cone-edge columns (N-D2-1 fix)
            "pathway_cond_rate": h6.get("cond_rate"), "pathway_base_rate": h6.get("base_rate"),
            "pathway_tercile": (pw.get("setup") or {}).get("tercile"),
        })
    if not rows or not asof:
        return 0
    try:
        new = pd.DataFrame(rows)
        p = config.data_dir() / "china_sector_cycles" / "forward_log.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            prior = pd.read_parquet(p)
            combined = pd.concat([prior, new], ignore_index=True)
            combined = combined.drop_duplicates(subset=["date", "id"], keep="first")
        else:
            combined = new
        combined.to_parquet(p, index=False)
        return len(new)
    except Exception as e:  # noqa: BLE001
        log.warning("china_sector_cycles: forward log append failed: %s", e)
        return 0
