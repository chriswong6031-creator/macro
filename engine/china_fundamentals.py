"""Derive descriptive A-share fundamentals from the akshare cache.

The China parallel of engine/stock_fundamentals.py. Reads the compact records
written by collectors/china_fundamentals.py and computes, per name:

  - profile      : company / main-business description
  - financials   : multi-year trend (revenue, margins, EPS, FCF) + CAGRs
  - piotroski    : 9-signal fundamental-health F-score (from the abstract ratios)
  - altman       : distress Z-score (4 abstract-derivable legs + WC when present)
  - valuation    : PE / PB / PS / ROE / dividend yield, each vs its sector median
  - shareholders : the A-share retail-concentration tell (holder count + trend)
  - archetype    : a descriptive style bucket (quality compounder / dividend
                   defensive / deep value / speculative …)

IMPORTANT — this is CONTEXT, NOT A SIGNAL. Phase-0 work (reports/china-value-
phase0.md, china-quality results) showed value and quality are NOT validated
cross-sectional edges on A-shares — cheap names are value traps, junk beats
quality. So the page surfaces this as a fundamental-health backdrop to read
ALONGSIDE the validated reversal / low-vol signals, never as a buy ranking.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from lib import config

log = logging.getLogger("china_fundamentals")

CACHE = config.data_dir() / "china_fundamentals" / "fundamentals.parquet"

ARCHETYPES = {
    "quality_compounder": ("Quality compounder", "优质复利股"),
    "dividend_defensive": ("Dividend / defensive", "高股息防御"),
    "deep_value": ("Deep value", "深度价值"),
    "growth": ("Growth", "成长股"),
    "speculative_unprofitable": ("Speculative / unprofitable", "投机／未盈利"),
    "mixed": ("Mixed profile", "混合特征"),
}


def _num(v):
    try:
        if v in (None, "", "--", "—"):
            return None
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _cagr(series: list) -> float | None:
    s = [x for x in series if x is not None]
    if len(s) < 2 or s[0] is None or s[-1] is None or s[0] <= 0 or s[-1] <= 0:
        return None
    return round(((s[-1] / s[0]) ** (1 / (len(s) - 1)) - 1) * 100, 1)


def _shares(row: dict) -> float | None:
    """Shares outstanding ≈ equity / book-value-per-share (both in the abstract)."""
    eq, bvps = _num(row.get("equity")), _num(row.get("bvps"))
    return eq / bvps if (eq is not None and bvps not in (None, 0)) else None


def _piotroski(rows: list[dict]) -> dict | None:
    """Piotroski F-score from the ready abstract ratios (latest FY vs prior).
    Scored out of however many of the 9 were computable."""
    if len(rows) < 2:
        return None
    a, b = rows[-2], rows[-1]
    sa, sb = _shares(a), _shares(b)
    tests = [
        (_num(b.get("roa")), None, "gt0"),                                   # ROA > 0
        (_num(b.get("cfo")), None, "gt0"),                                   # CFO > 0
        (_num(b.get("roa")), _num(a.get("roa")), "gt"),                      # ROA rising
        (_num(b.get("cfo")), _num(b.get("ni")), "gt"),                       # accruals: CFO > NI
        (_num(a.get("debt_ratio")), _num(b.get("debt_ratio")), "gt"),        # leverage falling
        (_num(b.get("current_ratio")), _num(a.get("current_ratio")), "gt"),  # current ratio rising
        (sa, sb, "gte"),                                                      # no dilution
        (_num(b.get("gross_margin")), _num(a.get("gross_margin")), "gt"),    # margin rising
        (_num(b.get("asset_turnover")), _num(a.get("asset_turnover")), "gt"),  # turnover rising
    ]
    score, total = 0, 0
    for x, y, op in tests:
        if x is None or (op in ("gt", "gte") and y is None):
            continue
        total += 1
        if op == "gt0":
            score += 1 if x > 0 else 0
        elif op == "gt":
            score += 1 if x > y else 0
        elif op == "gte":
            score += 1 if x >= y * 0.99 else 0   # ≥ prior (allow tiny buyback noise)
    return {"score": score, "of": total} if total >= 5 else None


def _altman(row: dict, mktcap: float | None) -> dict | None:
    """Altman Z (classic legs derivable from the abstract: RE/TA, EBIT/TA,
    mktcap/TL, sales/TA). Labelled approximate — A-share accounting differs and
    it is shown as distress CONTEXT, not a validated signal."""
    eq, mult = _num(row.get("equity")), _num(row.get("equity_multiplier"))
    ta = eq * mult if (eq is not None and mult not in (None, 0)) else None
    if not ta or not mktcap:
        return None
    tl = ta - eq if eq is not None else None
    sh = _shares(row)
    re = (_num(row.get("retained_earnings_ps")) * sh
          if (_num(row.get("retained_earnings_ps")) is not None and sh is not None) else None)
    rev = _num(row.get("revenue"))
    ebit = (rev * _num(row.get("ebit_margin")) / 100
            if (rev is not None and _num(row.get("ebit_margin")) is not None) else None)
    legs = [(1.4, re / ta if re is not None else None),
            (3.3, ebit / ta if ebit is not None else None),
            (0.6, mktcap / tl if tl not in (None, 0) else None),
            (1.0, rev / ta if rev is not None else None)]
    avail = [(c, x) for c, x in legs if x is not None]
    if len(avail) < 4:
        return None
    z = round(sum(c * x for c, x in avail), 2)
    zone = "safe" if z > 2.99 else "grey" if z >= 1.81 else "distress"
    return {"z": z, "zone": zone, "approx": True}


def _financials(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    rev = [_num(r.get("revenue")) for r in rows]
    ni = [_num(r.get("ni")) for r in rows]
    eps = [_num(r.get("eps")) for r in rows]
    nm = [_num(r.get("net_margin")) for r in rows]
    gm = [_num(r.get("gross_margin")) for r in rows]
    # FCF/share is in the abstract; scale to a yuan figure with shares
    fcf = []
    for r in rows:
        fps, sh = _num(r.get("fcf_ps")), _shares(r)
        fcf.append(fps * sh if (fps is not None and sh is not None) else None)
    return {
        "years": [r["fy"] for r in rows],
        "revenue": rev, "net_margin": nm, "gross_margin": gm, "eps": eps, "fcf": fcf,
        "rev_cagr": _cagr(rev), "eps_cagr": _cagr(eps), "ni_cagr": _cagr(ni),
    }


def _archetype(val: dict, fin: dict | None, latest: dict) -> str:
    roe = _num(latest.get("roe"))
    debt = _num(latest.get("debt_ratio"))
    ni = _num(latest.get("ni"))
    dy = val.get("div_yield")
    rev_cagr = (fin or {}).get("rev_cagr")
    if ni is not None and ni < 0:
        return "speculative_unprofitable"
    if dy is not None and dy >= 3 and (rev_cagr is None or rev_cagr < 8):
        return "dividend_defensive"
    if roe is not None and roe >= 15 and (debt is None or debt < 55) \
            and (rev_cagr is None or rev_cagr >= 0):
        return "quality_compounder"
    if rev_cagr is not None and rev_cagr >= 20:
        return "growth"
    pe, pe_med = val.get("pe"), val.get("pe_sector_med")
    if pe is not None and pe > 0 and pe_med and pe < pe_med * 0.7:
        return "deep_value"
    return "mixed"


def _valuation(latest: dict, price: float | None, mktcap_yi: float | None) -> dict:
    """PE / PB / PS / ROE / dividend yield from the latest FY + current price."""
    eps, bvps = _num(latest.get("eps")), _num(latest.get("bvps"))
    rev = _num(latest.get("revenue"))
    out: dict = {"roe": _num(latest.get("roe")), "net_margin": _num(latest.get("net_margin")),
                 "debt_ratio": _num(latest.get("debt_ratio")),
                 "rev_growth": _num(latest.get("rev_growth")),
                 "ni_growth": _num(latest.get("ni_growth"))}
    if price is not None and eps not in (None, 0):
        out["pe"] = round(price / eps, 1)
    if price is not None and bvps not in (None, 0):
        out["pb"] = round(price / bvps, 2)
    # market cap (亿) / revenue (亿) — revenue is in yuan, mktcap_yi in 亿
    if mktcap_yi and rev:
        out["ps"] = round(mktcap_yi / (rev / 1e8), 2)
    return out


def build_all(price_by_ticker: dict[str, float],
              sector_by_ticker: dict[str, str],
              mktcap_by_ticker: dict[str, float]) -> dict[str, dict]:
    """Compute the per-ticker fundamentals map for every cached name, including
    each name's PE/PB/ROE/yield vs its SECTOR median. Returns {ticker: {...}}."""
    if not CACHE.exists():
        return {}
    try:
        df = pd.read_parquet(CACHE)
    except Exception as e:  # noqa: BLE001
        log.warning("china fundamentals cache read failed: %s", e)
        return {}

    raw: dict[str, dict] = {}
    for _, r in df.iterrows():
        try:
            raw[r["ticker"]] = json.loads(r["payload"])
        except Exception:  # noqa: BLE001
            continue

    # pass 1: base valuation per name (needs price + mktcap)
    base: dict[str, dict] = {}
    for t, rec in raw.items():
        rows = rec.get("financials") or []
        if not rows:
            continue
        latest = rows[-1]
        val = _valuation(latest, price_by_ticker.get(t), mktcap_by_ticker.get(t))
        # dividend yield: latest cash payout (per 10 shares) / price
        dv = rec.get("dividends") or {}
        payout10, px = _num(dv.get("latest_payout_per10")), price_by_ticker.get(t)
        if payout10 and px:
            val["div_yield"] = round((payout10 / 10) / px * 100, 2)
        base[t] = {"latest": latest, "rows": rows, "val": val, "rec": rec}

    # pass 2: sector medians of pe / pb / roe / div_yield
    def med(vals):
        v = sorted(x for x in vals if x is not None)
        return v[len(v) // 2] if v else None
    sec_vals: dict[str, dict[str, list]] = {}
    for t, b in base.items():
        s = sector_by_ticker.get(t) or "—"
        d = sec_vals.setdefault(s, {"pe": [], "pb": [], "roe": [], "div_yield": []})
        for k in d:
            x = b["val"].get(k)
            if x is not None and (k != "pe" or x > 0):
                d[k].append(x)
    sec_med = {s: {k: med(v) for k, v in d.items()} for s, d in sec_vals.items()}

    # pass 3: assemble
    out: dict[str, dict] = {}
    for t, b in base.items():
        val, latest, rows, rec = b["val"], b["latest"], b["rows"], b["rec"]
        s = sector_by_ticker.get(t) or "—"
        for k in ("pe", "pb", "roe", "div_yield"):
            val[f"{k}_sector_med"] = sec_med.get(s, {}).get(k)
        fin = _financials(rows)
        arch = _archetype(val, fin, latest)
        out[t] = {
            "description": rec.get("description") or {},
            "valuation": val,
            "financials": fin,
            "piotroski": _piotroski(rows),
            "altman": _altman(latest, (mktcap_by_ticker.get(t) or 0) * 1e8 or None),
            "shareholders": rec.get("shareholders") or {},
            "archetype": arch,
            "archetype_label": ARCHETYPES.get(arch, ARCHETYPES["mixed"])[0],
            "archetype_label_zh": ARCHETYPES.get(arch, ARCHETYPES["mixed"])[1],
            "fy": latest.get("fy"),
        }
    return out
