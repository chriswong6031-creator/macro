"""Per-stock fundamental panels for the single-stock analyzer (site/stock.html).

Surfaces data the dashboard ALREADY collects but never showed per name, plus a
transparent stock-archetype classifier. Inputs (all optional — a missing input
just hides its panel):

  cross-sectional factor z-scores   site/factordata/factors.json (.table)
  raw SEC EDGAR XBRL financials      data/edgar/fundamentals.parquet
  FINRA short interest               data/finra/short_interest.parquet
  SEC Form-4 insider net flow        data/sec_insider/insider.parquet (+ factors.json fallback)
  deep-set yfinance snapshot (~110)  data/stock_fundamentals/snapshots.parquet

``panels()`` returns ``{ticker: {profile, valuation, financials, factors,
positioning, analyst}}``. Each block is omitted when its inputs are absent so the
static page simply hides that panel (the `display:none` + per-key pattern). All of
it is computed at BUILD time and baked into site/stockdata/<TICKER>.json — nothing
is fetched at serve time.

This is the Phase-1 "surface what we already have" layer of
research/STOCK_FUNDAMENTALS_PLAN.md. Business descriptions, multi-year statements,
earnings, forward estimates and per-equity GEX arrive in later phases; the page
carries honest "building" / "deep-set only" stubs until then.

HONESTY: factor z-scores and valuation context are RELATIVE ranks vs the S&P 1500
cross-section, lagged to the latest FY filing — context, not a validated alpha.
"""
from __future__ import annotations

import json
import logging
import math

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# ---- archetype labels (EN, ZH) ---------------------------------------------
ARCHETYPES = {
    "quality_compounder": ("Quality compounder", "优质复利股"),
    "dividend_defensive": ("Dividend / defensive", "高股息防御"),
    "deep_value": ("Deep value", "深度价值"),
    "high_beta_momentum": ("High-beta momentum", "高贝塔动量"),
    "speculative_unprofitable": ("Speculative / unprofitable", "投机／未盈利"),
    "mixed": ("Mixed profile", "混合特征"),
}
# the six radar axes (the composite legs) in display order
RADAR_AXES = ["value", "profitability", "quality", "investment", "payout", "low_vol"]


# ---- small numeric helpers --------------------------------------------------
def _num(x) -> float | None:
    """Coerce to a finite float, else None (NaN/inf/non-numeric → None). Keeps the
    baked JSON valid — Python json.dumps would otherwise emit a bare `NaN` token
    that the client-side JSON.parse rejects."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _r(x, nd: int = 2) -> float | None:
    v = _num(x)
    return round(v, nd) if v is not None else None


def _clean(obj):
    """Recursively replace NaN/inf with None so the baked JSON parses client-side."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, (np.floating, np.integer)):
        v = float(obj)
        return v if math.isfinite(v) else None
    return obj


def _ge(z, thr: float) -> bool:
    v = _num(z)
    return v is not None and v >= thr


def _le(z, thr: float) -> bool:
    v = _num(z)
    return v is not None and v <= thr


# ---- input loaders (all graceful) ------------------------------------------
def _load_fundamentals() -> pd.DataFrame | None:
    p = config.data_dir() / "edgar" / "fundamentals.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("stock_fundamentals: edgar parquet unreadable (%s)", e)
        return None
    return df if not df.empty else None


def _load_factors() -> dict:
    """{table: {ticker: row}, labels: {...}, n: int, insider: {...}}."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    p = site / "factordata" / "factors.json"
    if not p.exists():
        return {"table": {}, "labels": {}, "n": 0, "insider": {}}
    try:
        fj = json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("stock_fundamentals: factors.json unreadable (%s)", e)
        return {"table": {}, "labels": {}, "n": 0, "insider": {}}
    table = {r["ticker"]: r for r in fj.get("table", []) if r.get("ticker")}
    return {"table": table, "labels": fj.get("factor_labels", {}),
            "n": fj.get("n", len(table)), "insider": fj.get("insider") or {}}


def _load_short() -> pd.DataFrame | None:
    p = config.data_dir() / "finra" / "short_interest.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return None
    return df if not df.empty else None


def _load_insider(facts: dict) -> dict[str, dict]:
    """ticker -> {net_usd_mn, n_buys, n_sells, quarter}. Prefer the full Form-4
    parquet; fall back to the page-level top-buyers/sellers in factors.json."""
    out: dict[str, dict] = {}
    p = config.data_dir() / "sec_insider" / "insider.parquet"
    if p.exists():
        try:
            df = pd.read_parquet(p)
            q = str(df["quarter"].iloc[0]) if "quarter" in df.columns and len(df) else None
            for t, r in df.iterrows():
                nu = _num(r.get("net_usd"))
                if nu is None:
                    continue
                out[str(t)] = {"net_usd_mn": round(nu / 1e6, 2),
                               "n_buys": int(r.get("n_buys", 0) or 0),
                               "n_sells": int(r.get("n_sells", 0) or 0), "quarter": q}
        except Exception as e:  # noqa: BLE001
            log.debug("stock_fundamentals: insider parquet unreadable (%s)", e)
    if out:
        return out
    ins = facts.get("insider") or {}
    q = ins.get("quarter")
    for side in ("top_buying", "top_selling"):
        for r in ins.get(side, []) or []:
            t = r.get("ticker")
            if t:
                out[t] = {"net_usd_mn": _num(r.get("net_usd_mn")),
                          "n_buys": r.get("buys"), "n_sells": r.get("sells"), "quarter": q}
    return out


def _load_profiles() -> dict[str, dict]:
    """ticker -> {description, sic_description, exchange, hq} from the Phase-2
    profile collector (collectors/equity_profile.py). Empty if not collected yet —
    the Profile panel then shows its "building" stub."""
    p = config.data_dir() / "profile" / "profiles.parquet"
    if not p.exists():
        return {}
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return {}
    cols = [c for c in ("description", "sic_description", "exchange", "hq") if c in df.columns]
    out: dict[str, dict] = {}
    for t, row in df.iterrows():
        out[str(t)] = {c: (row[c] if pd.notna(row[c]) else None) for c in cols}
    return out


def _load_statements() -> dict[str, list[dict]]:
    """ticker -> list of per-fiscal-year statement dicts (ascending) from the
    Phase-2 companyfacts collector (collectors/edgar_facts.py). Empty until run."""
    p = config.data_dir() / "edgar" / "statements.parquet"
    if not p.exists():
        return {}
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return {}
    if df.empty or "ticker" not in df.columns:
        return {}
    out: dict[str, list[dict]] = {}
    for t, sub in df.sort_values("fy").groupby("ticker"):
        out[str(t)] = sub.to_dict("records")
    return out


def _piotroski(rows: list[dict]) -> dict | None:
    """Piotroski F-score: count of 9 fundamental-momentum signals that pass
    (latest FY vs prior). Reports score out of however many were computable —
    sparse filers get a smaller denominator rather than a wrong absolute."""
    if len(rows) < 2:
        return None
    a, b = rows[-2], rows[-1]            # prior, latest

    def n(r, k):
        return _num(r.get(k))

    def ratio(r, num, den):
        x, y = n(r, num), n(r, den)
        return x / y if (x is not None and y not in (None, 0)) else None

    score, total = 0, 0
    tests = [
        (ratio(b, "ni", "assets"), None, "gt0"),                       # ROA > 0
        (n(b, "cfo"), None, "gt0"),                                    # CFO > 0
        (ratio(b, "ni", "assets"), ratio(a, "ni", "assets"), "gt"),   # ROA rising
        (n(b, "cfo"), n(b, "ni"), "gt"),                              # accruals: CFO > NI
        (ratio(a, "debt_lt", "assets"), ratio(b, "debt_lt", "assets"), "gt"),  # leverage falling
        (ratio(b, "cur_assets", "cur_liab"), ratio(a, "cur_assets", "cur_liab"), "gt"),  # current ratio rising
        (n(a, "shares"), n(b, "shares"), "gte"),                      # no dilution
        (ratio(b, "gross_profit", "revenue"), ratio(a, "gross_profit", "revenue"), "gt"),  # margin rising
        (ratio(b, "revenue", "assets"), ratio(a, "revenue", "assets"), "gt"),  # asset turnover rising
    ]
    for x, y, op in tests:
        if x is None or (op in ("gt", "gte") and y is None):
            continue
        total += 1
        if op == "gt0":
            score += 1 if x > 0 else 0
        elif op == "gt":
            score += 1 if x > y else 0
        elif op == "gte":
            score += 1 if x >= y * 1.01 else 0
    if total < 5:
        return None
    return {"score": score, "of": total}


def _altman(latest: dict, mktcap: float | None) -> dict | None:
    """Altman Z-score (classic, manufacturers) — distress < 1.81, grey 1.81-2.99,
    safe > 2.99. Uses market cap for X4; labelled approximate for non-manufacturers."""
    a = _num(latest.get("assets"))
    if not a or not mktcap:
        return None
    ca, cl = _num(latest.get("cur_assets")), _num(latest.get("cur_liab"))
    wc = (ca - cl) if (ca is not None and cl is not None) else None
    legs = [(1.2, wc / a if wc is not None else None),
            (1.4, _num(latest.get("retained_earnings")) and _num(latest.get("retained_earnings")) / a),
            (3.3, _num(latest.get("op_income")) and _num(latest.get("op_income")) / a),
            (0.6, mktcap / _num(latest.get("liabilities")) if _num(latest.get("liabilities")) else None),
            (1.0, _num(latest.get("revenue")) and _num(latest.get("revenue")) / a)]
    avail = [(c, x) for c, x in legs if x is not None]
    if len(avail) < 4:
        return None
    z = sum(c * x for c, x in avail)
    zone = "safe" if z > 2.99 else "grey" if z >= 1.81 else "distress"
    return {"z": round(z, 2), "zone": zone}


def _cagr(series: list) -> float | None:
    s = [x for x in series if x is not None]
    if len(series) < 2 or series[0] is None or series[-1] is None:
        return None
    if series[0] <= 0 or series[-1] <= 0:
        return None
    return round(((series[-1] / series[0]) ** (1 / (len(series) - 1)) - 1) * 100, 1)


def _multiyear(rows: list[dict], mktcap: float | None) -> dict | None:
    """Multi-year trend series + CAGRs + Piotroski/Altman from the statements rows."""
    if not rows:
        return None

    def col(k):
        return [_num(r.get(k)) for r in rows]

    rev, ni, gp = col("revenue"), col("ni"), col("gross_profit")
    cfo, capex, eps = col("cfo"), col("capex"), col("eps_diluted")

    def margin(num, den):
        return [round(n / d * 100, 1) if (n is not None and d) else None for n, d in zip(num, den)]

    fcf = [(c - x) if (c is not None and x is not None) else None for c, x in zip(cfo, capex)]
    block = {
        "years": [int(r["fy"]) for r in rows],
        "revenue": rev, "net_margin": margin(ni, rev), "gross_margin": margin(gp, rev),
        "eps": eps, "fcf": fcf, "fcf_margin": margin(fcf, rev),
        "rev_cagr": _cagr(rev), "eps_cagr": _cagr(eps),
        "piotroski": _piotroski(rows), "altman": _altman(rows[-1], mktcap),
    }
    return block


def _load_deep() -> dict[str, dict]:
    """ticker -> {metric: value} from the ~110-name yfinance snapshot (the only
    free source of forward P/E we have). Columns are '<TICKER>__<metric>'."""
    p = config.data_dir() / "stock_fundamentals" / "snapshots.parquet"
    if not p.exists():
        return {}
    try:
        sf = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return {}
    if sf.empty:
        return {}
    row = sf.iloc[-1]
    out: dict[str, dict] = {}
    for col, val in row.items():
        if "__" not in str(col):
            continue
        t, metric = str(col).split("__", 1)
        out.setdefault(t, {})[metric] = _num(val)
    return out


# ---- cross-sectional valuation context -------------------------------------
def _context_frame(fund: pd.DataFrame, table: dict) -> pd.DataFrame:
    """Per-ticker trailing multiples + within-sector cheapness percentile +
    sector medians + a universe-wide composite percentile. 'cheapness' is oriented
    so HIGHER = cheaper/better for every metric (the bar fills green to the right)."""
    rows = []
    for t, f in fund.iterrows():
        fac = table.get(t, {})
        mcap_bn = _num(fac.get("mktcap_bn"))
        mcap = mcap_bn * 1e9 if mcap_bn else None
        ni, eq, rev = _num(f.get("ni")), _num(f.get("equity")), _num(f.get("revenue"))
        cfo, div, rep = _num(f.get("cfo")), _num(f.get("dividends")), _num(f.get("repurchases"))
        rows.append({
            "ticker": t, "sector": fac.get("sector") or "—", "mktcap": mcap,
            "pe": mcap / ni if (mcap and ni and ni > 0) else np.nan,
            "pb": mcap / eq if (mcap and eq and eq > 0) else np.nan,
            "ps": mcap / rev if (mcap and rev and rev > 0) else np.nan,
            "ey": (ni / mcap * 100) if (mcap and ni is not None) else np.nan,
            "fcfy": (cfo / mcap * 100) if (mcap and cfo is not None) else np.nan,
            "shy": (((div or 0) + (rep or 0)) / mcap * 100)
                   if (mcap and (div is not None or rep is not None)) else np.nan,
            "net_margin": (ni / rev * 100) if (rev and rev > 0 and ni is not None) else np.nan,
            "composite": _num(fac.get("composite")),
        })
    M = pd.DataFrame(rows).set_index("ticker")
    if M.empty:
        return M
    # lower-is-cheaper metrics vs higher-is-cheaper (yield) metrics
    for col, lower_cheap in (("pe", True), ("pb", True), ("ps", True),
                             ("ey", False), ("fcfy", False), ("shy", False)):
        g = M.groupby("sector")[col]
        M[f"{col}_med"] = g.transform("median")
        rank = g.rank(pct=True)                       # 0..1 within sector
        M[f"{col}_cheap"] = (1.0 - rank) if lower_cheap else rank
    M["comp_pctile"] = M["composite"].rank(pct=True)  # 0..1 universe-wide
    return M


# ---- archetype classifier ---------------------------------------------------
def _archetype(fac: dict, ni: float | None, net_margin: float | None,
               nm_top_thr: float | None) -> dict | None:
    """Transparent first-match-wins cascade over the factor z-scores (the
    unprofitable veto fires FIRST so a money-loser never reads 'quality'). Returns
    {key, label, label_zh, confidence, conf_word, why, why_zh}."""
    if not fac:
        return None
    v, q, p = fac.get("value"), fac.get("quality"), fac.get("profitability")
    pay, lv, lb = fac.get("payout"), fac.get("low_vol"), fac.get("low_beta")
    nm_top = (net_margin is not None and nm_top_thr is not None and net_margin >= nm_top_thr)

    key, slack, why, why_zh = "mixed", 0.0, [], []
    if (ni is not None and ni <= 0) or (_le(p, -0.75) and _le(v, -0.5) and _le(lb, -0.5)):
        key = "speculative_unprofitable"
        if ni is not None and ni <= 0:
            why, why_zh = ["unprofitable (net loss)"], ["未盈利（净亏损）"]
            slack = 1.0
        else:
            why, why_zh = ["weak profitability & expensive & high beta"], ["盈利弱、估值高、高贝塔"]
            slack = min(abs(_num(p) + 0.75), abs(_num(v) + 0.5), abs(_num(lb) + 0.5))
    elif _le(lb, -0.6) and _le(lv, -0.4):
        key = "high_beta_momentum"
        why, why_zh = ["high beta & high volatility vs peers"], ["相对同业高贝塔、高波动"]
        slack = min(abs(_num(lb) + 0.6), abs(_num(lv) + 0.4))
    elif _ge(pay, 0.5) and _ge(lv, 0.4) and _ge(lb, 0.3):
        key = "dividend_defensive"
        why, why_zh = ["high shareholder payout, low volatility & low beta"], ["高股东回报、低波动、低贝塔"]
        slack = min(_num(pay) - 0.5, _num(lv) - 0.4, _num(lb) - 0.3)
    elif _ge(q, 0.5) and (_ge(p, 0.3) or nm_top) and not _ge(v, 0.75):
        key = "quality_compounder"
        why, why_zh = ["high quality" + (", strong margins" if nm_top else "")], \
                      ["高质量" + ("、利润率领先" if nm_top else "")]
        slack = _num(q) - 0.5
    elif _ge(v, 0.75) and not _ge(q, 0.5):
        key = "deep_value"
        why, why_zh = ["cheap on value factors, quality not high"], ["价值因子便宜，质量一般"]
        slack = _num(v) - 0.75
    else:
        key = "mixed"
        why, why_zh = ["no single factor dominates"], ["无单一因子主导"]
        slack = 0.15

    slack = _num(slack) or 0.0
    conf = max(0.0, min(1.0, slack / 0.6))
    conf_word = "high" if conf >= 0.66 else "moderate" if conf >= 0.33 else "low"
    en, zh = ARCHETYPES[key]
    return {"key": key, "label": en, "label_zh": zh,
            "confidence": round(conf, 2), "conf_word": conf_word,
            "why": "; ".join(why), "why_zh": "；".join(why_zh)}


def _mktcap_tier(mcap_bn: float | None) -> dict | None:
    if mcap_bn is None:
        return None
    if mcap_bn >= 200:
        return {"key": "mega", "label": "Mega cap", "label_zh": "超大盘"}
    if mcap_bn >= 10:
        return {"key": "large", "label": "Large cap", "label_zh": "大盘"}
    if mcap_bn >= 2:
        return {"key": "mid", "label": "Mid cap", "label_zh": "中盘"}
    return {"key": "small", "label": "Small cap", "label_zh": "小盘"}


# ---- per-ticker block builders ---------------------------------------------
def _profile(t, f, fac, M, arche, prof_row=None) -> dict:
    mcap_bn = _num(fac.get("mktcap_bn")) if fac else None
    pr = prof_row or {}
    return {
        "sector": (fac.get("sector") if fac else None) or None,
        "mktcap_bn": _r(mcap_bn, 2),
        "mktcap_tier": _mktcap_tier(mcap_bn),
        "archetype": arche,
        # identity + description from collectors/equity_profile.py (Phase 2) —
        # None until that collector has run (the panel guards for it)
        "description": pr.get("description"),
        "sic_description": pr.get("sic_description"),
        "exchange": pr.get("exchange"),
        "hq": pr.get("hq"),
    }


def _valuation(t, f, fac, M, deep) -> dict | None:
    if t not in M.index:
        return None
    m = M.loc[t]
    has_mcap = _num(m.get("mktcap")) is not None
    if not has_mcap:
        return None

    def cell(col):
        v = _num(m.get(col))
        if v is None:
            return None
        return {"v": _r(v, 2), "med": _r(m.get(f"{col}_med"), 2),
                "cheap": _r((_num(m.get(f"{col}_cheap")) or 0) * 100, 0)}

    fwd = (deep or {}).get("fwd_pe")
    return {
        "trailing_pe": cell("pe"), "price_to_book": cell("pb"),
        "price_to_sales": cell("ps"), "earnings_yield": cell("ey"),
        "fcf_proxy_yield": cell("fcfy"), "shareholder_yield": cell("shy"),
        "value_z": _r(fac.get("value"), 2) if fac else None,
        "forward_pe": _r(fwd, 1) if fwd else None,
        "forward_tier": "deep" if fwd else "lite",
    }


def _financials(t, f, deep, multiyear=None) -> dict | None:
    rev, ni, ni_p = _num(f.get("revenue")), _num(f.get("ni")), _num(f.get("ni_prior"))
    eq, cfo, gp = _num(f.get("equity")), _num(f.get("cfo")), _num(f.get("gross_profit"))
    assets, assets_p = _num(f.get("assets")), _num(f.get("assets_prior"))
    debt, sh = _num(f.get("debt_lt")), _num(f.get("shares"))
    div, rep = _num(f.get("dividends")), _num(f.get("repurchases"))
    if ni is None and rev is None and assets is None:
        return None

    def pct(a, b):
        return _r(a / b * 100, 1) if (a is not None and b not in (None, 0)) else None

    def growth(a, b):  # only meaningful when the base is positive
        return _r((a / b - 1) * 100, 1) if (a is not None and b and b > 0) else None

    avg_assets = (assets + assets_p) / 2 if (assets is not None and assets_p is not None) else None
    rev_growth_deep = (deep or {}).get("rev_growth")
    return {
        "raw": {"revenue": _num(rev), "ni": _num(ni), "gross_profit": _num(gp),
                "cfo": _num(cfo), "equity": _num(eq), "debt_lt": _num(debt),
                "assets": _num(assets), "shares": _num(sh),
                "dividends": _num(div), "repurchases": _num(rep)},
        "gross_margin": pct(gp, rev), "net_margin": pct(ni, rev),
        "fcf_margin": pct(cfo, rev),
        "ni_growth": growth(ni, ni_p),
        "rev_growth": _r(rev_growth_deep * 100, 1) if rev_growth_deep is not None else None,
        "asset_growth": growth(assets, assets_p),
        "roe": pct(ni, eq), "roa": pct(ni, assets),
        "debt_to_assets": pct(debt, assets),
        "accruals": _r((ni - cfo) / avg_assets, 3) if (ni is not None and cfo is not None and avg_assets) else None,
        # tiny 2-point sparkline series (prior, latest) — honest until companyfacts (Phase 2)
        "spark": {"ni": [_num(ni_p), _num(ni)] if (ni_p is not None and ni is not None) else None,
                  "assets": [_num(assets_p), _num(assets)] if (assets_p is not None and assets is not None) else None},
        "multiyear": multiyear,  # SEC companyfacts trends + Piotroski/Altman (Phase 2)
    }


def _factors(t, fac, facts, M) -> dict | None:
    if not fac:
        return None
    radar = [{"key": a, "z": _r(fac.get(a), 2)} for a in RADAR_AXES]
    if sum(1 for x in radar if x["z"] is not None) < 3:
        radar_ok = False
    else:
        radar_ok = True
    comp_pct = _num(M.loc[t, "comp_pctile"]) if t in M.index else None
    fund_score = round((comp_pct - 0.5) * 200) if comp_pct is not None else None
    legs = {k: _r(fac.get(k), 2) for k in
            ("value", "profitability", "quality", "investment", "payout",
             "low_vol", "low_beta", "accruals", "short_interest")}
    return {
        "radar": radar, "radar_ok": radar_ok, "legs": legs,
        "composite": _r(fac.get("composite"), 2),
        "fundamental_score": fund_score,
        "sector": fac.get("sector"),
        "n_universe": facts.get("n"),
    }


def _positioning(t, f, short, insider) -> dict | None:
    block: dict = {}
    sh = _num(f.get("shares"))
    if short is not None and t in short.index:
        sr = short.loc[t]
        ss = _num(sr.get("short_shares"))
        block["short"] = {
            "pct_float": _r(ss / sh * 100, 2) if (ss is not None and sh) else None,
            "days_to_cover": _r(sr.get("days_to_cover"), 2),
            "si_change_pct": _r(sr.get("si_change_pct"), 1),
            "settlement": str(sr.get("settlement_date")) if sr.get("settlement_date") is not None else None,
        }
    if insider:
        block["insider"] = insider
    return block or None


def _analyst(t, deep) -> dict | None:
    """Phase 1: only the deep-set yfinance snapshot carries forward P/E and a few
    market ratios. Consensus ratings & price targets are not collected yet → the
    page shows an honest 'deep-set only / not wired' stub. (Phase-2 tiered.)"""
    d = deep or {}
    fwd = d.get("fwd_pe")
    if not d:
        return {"tier": "lite", "rating": None, "target": None}
    return {
        "tier": "deep",
        "forward_pe": _r(fwd, 1) if fwd else None,
        "pe_yf": _r(d.get("pe"), 1) if d.get("pe") else None,
        "profit_margin": _r((d.get("profit_margin") or 0) * 100, 1) if d.get("profit_margin") is not None else None,
        "roe": _r((d.get("roe") or 0) * 100, 1) if d.get("roe") is not None else None,
        "div_yield": _r(d.get("div_yield"), 2) if d.get("div_yield") is not None else None,
        "rating": None, "target": None,
    }


def panels() -> dict[str, dict]:
    """{ticker: {profile, valuation, financials, factors, positioning, analyst}}
    for every name we have fundamentals on. Empty dict if the EDGAR cache is
    missing (caller logs and ships the page without fundamental panels)."""
    fund = _load_fundamentals()
    if fund is None:
        log.warning("stock_fundamentals: no edgar fundamentals — panels skipped")
        return {}
    facts = _load_factors()
    table = facts["table"]
    short = _load_short()
    insider = _load_insider(facts)
    deep = _load_deep()
    profiles = _load_profiles()
    statements = _load_statements()

    M = _context_frame(fund, table)
    nm_top_thr = _num(M["net_margin"].quantile(2 / 3)) if "net_margin" in M else None

    out: dict[str, dict] = {}
    for t, f in fund.iterrows():
        fac = table.get(t)
        ni = _num(f.get("ni"))
        net_margin = _num(M.loc[t, "net_margin"]) if t in M.index else None
        arche = _archetype(fac, ni, net_margin, nm_top_thr)
        mcap = _num(M.loc[t, "mktcap"]) if t in M.index else None
        my = _multiyear(statements.get(str(t)), mcap)
        blocks = {
            "profile": _profile(t, f, fac, M, arche, profiles.get(str(t))),
            "valuation": _valuation(t, f, fac, M, deep.get(t)),
            "financials": _financials(t, f, deep.get(t), my),
            "factors": _factors(t, fac, facts, M),
            "positioning": _positioning(t, f, short, insider.get(t)),
            "analyst": _analyst(t, deep.get(t)),
        }
        out[str(t)] = _clean({k: v for k, v in blocks.items() if v})
    log.info("stock_fundamentals: %d names with panels (factors %d, deep %d, short %s)",
             len(out), len(table), len(deep), 0 if short is None else len(short))
    return out
