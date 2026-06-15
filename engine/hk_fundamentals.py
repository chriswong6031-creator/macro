"""Derive descriptive HK fundamentals from the akshare cache.

The HK parallel of engine/china_fundamentals.py. Reads collectors/hk_fundamentals.py
records and computes, per name:

  - profile      : industry, employees, founding date, domicile
  - financials   : multi-year trend (revenue, margins, EPS) + CAGRs
  - quality      : ROE / ROA / margins / leverage / current ratio (currency-neutral)
  - piotroski    : fundamental-health F-score from the precomputed ratios
  - valuation    : PE / PB when financials are HKD-reported (else omitted — many HK
                   names report in CNY, so a CNY EPS over an HKD price is wrong)
  - consensus    : the HK-UNIQUE analyst read — median target (vs price), upside %,
                   buy/hold/sell mix, coverage count
  - archetype    : a descriptive style bucket

CONTEXT, NOT A SIGNAL. HK has no validated idiosyncratic stock-selection edge
(residual momentum is dead on a 40y panel; research/CHINA_HK_STOCK_SIGNALS.md), so
fundamentals are a health/quality backdrop to read alongside the validated global-
risk-beta read — never a buy ranking. Analyst targets are sell-side opinion, shown
as coverage context, not an endorsement.
"""
from __future__ import annotations

import json
import logging

import pandas as pd

from lib import config

log = logging.getLogger("hk_fundamentals")

CACHE = config.data_dir() / "hk_fundamentals" / "fundamentals.parquet"

ARCHETYPES = {
    "quality_compounder": ("Quality compounder", "优质复利股"),
    "dividend_defensive": ("Dividend / defensive", "高股息防御"),
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


def _shares(row: dict):
    ni, eps = _num(row.get("ni")), _num(row.get("eps"))
    return ni / eps if (ni is not None and eps not in (None, 0)) else None


def _piotroski(rows: list[dict]) -> dict | None:
    """F-score from the precomputed HK ratios (asset-turnover signal unavailable)."""
    if len(rows) < 2:
        return None
    a, b = rows[-2], rows[-1]
    sa, sb = _shares(a), _shares(b)
    # accruals proxy: operating-cash-flow / sales vs net margin (CFO 'quality')
    tests = [
        (_num(b.get("roa")), None, "gt0"),
        (_num(b.get("cfo_ps")), None, "gt0"),
        (_num(b.get("roa")), _num(a.get("roa")), "gt"),
        (_num(b.get("ocf_sales")), _num(b.get("net_margin")), "gt"),       # CFO > earnings (accruals)
        (_num(a.get("debt_ratio")), _num(b.get("debt_ratio")), "gt"),      # leverage falling
        (_num(b.get("current_ratio")), _num(a.get("current_ratio")), "gt"),
        (sa, sb, "gte"),
        (_num(b.get("gross_margin")), _num(a.get("gross_margin")), "gt"),
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
            score += 1 if x >= y * 0.99 else 0
    return {"score": score, "of": total} if total >= 4 else None


def _financials(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    rev = [_num(r.get("revenue")) for r in rows]
    return {
        "years": [r["fy"] for r in rows],
        "revenue": rev,
        "net_margin": [_num(r.get("net_margin")) for r in rows],
        "gross_margin": [_num(r.get("gross_margin")) for r in rows],
        "eps": [_num(r.get("eps")) for r in rows],
        "rev_cagr": _cagr(rev), "eps_cagr": _cagr([_num(r.get("eps")) for r in rows]),
        "currency": rows[-1].get("currency"),
    }


def _consensus(fc: dict, price: float | None) -> dict | None:
    if not fc or not fc.get("n_analysts"):
        return None
    out = dict(fc)
    tm = fc.get("target_med")
    if tm and price:
        out["upside_pct"] = round((tm / price - 1) * 100, 1)
    return out


def _archetype(q: dict, fin: dict | None) -> str:
    roe, ni = q.get("roe"), q.get("ni")
    debt = q.get("debt_ratio")
    rev_cagr = (fin or {}).get("rev_cagr")
    if ni is not None and ni < 0:
        return "speculative_unprofitable"
    if roe is not None and roe >= 15 and (debt is None or debt < 60) \
            and (rev_cagr is None or rev_cagr >= 0):
        return "quality_compounder"
    if rev_cagr is not None and rev_cagr >= 20:
        return "growth"
    return "mixed"


def build_all(price_by_ticker: dict[str, float]) -> dict[str, dict]:
    if not CACHE.exists():
        return {}
    try:
        df = pd.read_parquet(CACHE)
    except Exception as e:  # noqa: BLE001
        log.warning("hk fundamentals cache read failed: %s", e)
        return {}

    out: dict[str, dict] = {}
    for _, r in df.iterrows():
        try:
            rec = json.loads(r["payload"])
        except Exception:  # noqa: BLE001
            continue
        t = rec.get("ticker")
        rows = rec.get("financials") or []
        latest = rows[-1] if rows else {}
        price = price_by_ticker.get(t)
        cur = latest.get("currency")
        q = {k: _num(latest.get(k)) for k in
             ("roe", "roa", "gross_margin", "net_margin", "debt_ratio", "current_ratio")}
        q["ni"] = _num(latest.get("ni"))
        val: dict = {}
        # PE/PB only when the statements are HKD (same unit as price)
        if cur == "HKD" and price is not None:
            eps, bvps = _num(latest.get("eps")), _num(latest.get("bvps"))
            if eps not in (None, 0):
                val["pe"] = round(price / eps, 1)
            if bvps not in (None, 0):
                val["pb"] = round(price / bvps, 2)
        fin = _financials(rows)
        arch = _archetype(q, fin)
        if not (rows or rec.get("forecast") or rec.get("profile")):
            continue
        out[t] = {
            "profile": rec.get("profile") or {},
            "quality": q,
            "valuation": val,
            "financials": fin,
            "piotroski": _piotroski(rows),
            "consensus": _consensus(rec.get("forecast") or {}, price),
            "archetype": arch,
            "archetype_label": ARCHETYPES.get(arch, ARCHETYPES["mixed"])[0],
            "archetype_label_zh": ARCHETYPES.get(arch, ARCHETYPES["mixed"])[1],
            "fy": latest.get("fy"), "currency": cur,
        }
    return out
