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
# v2 taxonomy — shared constant so CN/HK/CA forks can import without duplicating.
# The original 6 buckets are preserved unchanged; 7 new buckets are appended.
ARCHETYPES = {
    # --- original 6 (factor-z driven) ---
    "quality_compounder":      ("Quality compounder",        "优质复利股"),
    "dividend_defensive":      ("Dividend / defensive",      "高股息防御"),
    "deep_value":              ("Deep value",                "深度价值"),
    "high_beta_momentum":      ("High-beta momentum",        "高贝塔动量"),
    "speculative_unprofitable": ("Speculative / unprofitable", "投机／未盈利"),
    "mixed":                   ("Mixed profile",             "混合特征"),
    # --- v2 additions ---
    "distressed":              ("Distressed",                "困境股"),
    "financial":               ("Financial",                 "金融股"),
    "rate_sensitive":          ("Rate-sensitive",            "利率敏感"),
    "commodity_sensitive":     ("Commodity-sensitive",       "大宗商品敏感"),
    "secular_growth":          ("Secular growth",            "长期成长"),
    "broken_growth":           ("Broken growth",             "成长受损"),
    "cyclical":                ("Cyclical",                  "周期股"),
}

# Shared taxonomy for CN/HK/CA forks (import this, never redefine).
ARCHETYPE_TAXONOMY = ARCHETYPES

# Deterministic first-match-wins precedence order (lower index = higher priority).
# Document: names appearing earlier in this list block later buckets for the same name.
ARCHETYPE_PRECEDENCE = [
    # 1. Hard veto — unprofitable/speculative always fires first (unchanged behavior)
    "speculative_unprofitable",
    # 2. Altman distress zone — financially impaired even if nominally profitable
    "distressed",
    # 3. Financial sector — EDGAR tags absent for banks; sector-keyed to avoid ratio noise
    "financial",
    # 4. Rate-sensitive — per-name residual rates beta; stable macro characteristic
    "rate_sensitive",
    # 5. Commodity-sensitive — oil beta; captures energy/materials via returns not SIC
    "commodity_sensitive",
    # 6. Secular growth — anchored CAGR thresholds; growth must be real and sustained
    "secular_growth",
    # 7. Broken growth — once-growth story with stalling/negative EPS
    "broken_growth",
    # 8. Cyclical — sector + earnings variability confirms the macro link
    "cyclical",
    # 9–13. Original factor-z buckets (unchanged behavior, lower priority than new v2 set)
    "high_beta_momentum",
    "dividend_defensive",
    "quality_compounder",
    "deep_value",
    "mixed",
]

# GICS sector strings that qualify for the financial archetype (sector-keyed, not ratio-keyed
# — EDGAR inventory/receivables/gross_profit tags are reliably absent for banks/insurers).
_FINANCIAL_SECTORS = frozenset({"Financials"})

# GICS sectors with structural cyclicality (confirmed by earnings variance patterns).
_CYCLICAL_SECTORS = frozenset({"Industrials", "Materials", "Consumer Discretionary", "Energy"})

# the six radar axes (the composite legs) in display order
RADAR_AXES = ["value", "profitability", "quality", "investment", "payout", "low_vol"]

# ---- v2 archetype threshold constants (anchored) ---------------------------
# Each threshold ships as a named constant with a one-line justification.
# anchored=True → absolute, stable through time; anchored=False → cross-sectional z, flagged.

# Altman distress cut: <1.81 is the published Altman (1968) distress zone boundary.  anchored=True
_ALTMAN_DISTRESS_MAX = 1.81

# Rates beta (residualized): |beta| > 0.40 flags meaningful rate sensitivity on a
# 252-day regression; the 0.40 level separates the top ~20% of TLT-beta names from
# the cross-section without being cross-sectionally defined.  anchored=True (abs level, not rank)
_RATE_BETA_THR = 0.40

# Oil beta (raw, not residualized): raw oil beta > 0.35 covers the energy / commodity
# complex; at this level a 1% oil move drives ~0.35% idiosyncratic sensitivity.  anchored=True
_OIL_BETA_THR = 0.35

# Secular growth revenue CAGR ≥ 15% p.a. over the available panel: the threshold
# sits above S&P 500 median GDP+inflation (~5%) and above the median large-cap grower,
# matching the commonly cited "secular compounder" revenue hurdle.  anchored=True
_SECULAR_REV_CAGR_THR = 15.0

# Secular growth EPS CAGR ≥ 12% p.a.: slightly lower than revenue to allow for
# investment years; still comfortably above cost-of-equity.  anchored=True
_SECULAR_EPS_CAGR_THR = 12.0

# Broken growth: revenue CAGR ≥ 10% (prior growth) but EPS CAGR ≤ 0 (margin/dilution
# destruction). The 10% revenue floor avoids labeling slow growers as "broken".  anchored=True
_BROKEN_REV_CAGR_THR = 10.0


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


def _load_short_volume() -> dict[str, dict]:
    """Per-ticker daily short-flow confirmer (keyless FINRA daily volume).
    Empty dict when the panel is absent — positioning degrades gracefully."""
    try:
        from engine import short_volume
        return short_volume.signal_map()
    except Exception:  # noqa: BLE001 — never break panels over a context chip
        return {}


def _load_analyst_revisions() -> dict[str, dict]:
    """Per-ticker analyst revision-momentum (Finnhub recommendation snapshots).
    Empty dict without a FINNHUB feed — the analyst panel degrades gracefully."""
    try:
        from engine import analyst_revisions
        return analyst_revisions.revision_map()
    except Exception:  # noqa: BLE001 — never break panels over a context chip
        return {}


def _load_betas() -> dict[str, dict]:
    """ticker -> beta row from site/factor_betas.json['betas'].
    Used by _archetype() v2 for rate_sensitive and commodity_sensitive buckets.
    Returns empty dict when the file is absent — _archetype() degrades to v1 output."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    p = site / "factor_betas.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text())
        return d.get("betas") or {}
    except Exception as e:  # noqa: BLE001
        log.debug("stock_fundamentals: factor_betas.json unreadable (%s)", e)
        return {}


def _mcap_map(facts: dict) -> dict[str, float]:
    """ticker -> market cap (USD) from the factor table's mktcap_bn, for sizing the
    insider net flow as a % of cap."""
    out: dict[str, float] = {}
    for t, r in (facts.get("table") or {}).items():
        b = _num(r.get("mktcap_bn"))
        if b and b > 0:
            out[t] = b * 1e9
    return out


def _insider_from_panel(mcap: dict[str, float], months: int, path=None) -> dict[str, dict]:
    """Per-ticker insider net flow over a trailing window of Form-4 FILINGS, with the
    DISTINCT-insider cluster count and net buying as a % of market cap — the validated
    construction (research/INSIDER_FACTOR.md). Empty if the PIT panel isn't present."""
    import os
    p = path or config.data_dir() / "sec_insider" / "insider_panel.parquet"
    if not os.path.exists(p):
        return {}
    try:
        df = pd.read_parquet(p, columns=["ticker", "filing_date", "code", "usd", "rptownercik"])
    except Exception as e:  # noqa: BLE001
        log.debug("stock_fundamentals: insider panel unreadable (%s)", e)
        return {}
    if df.empty:
        return {}
    win = df[df["filing_date"] > df["filing_date"].max() - pd.DateOffset(months=months)]
    if win.empty:
        return {}
    buys, sells = win[win["code"] == "P"], win[win["code"] == "S"]
    buy_usd, sell_usd = buys.groupby("ticker")["usd"].sum(), sells.groupby("ticker")["usd"].sum()
    buyers = buys.groupby("ticker")["rptownercik"].nunique()
    sellers = sells.groupby("ticker")["rptownercik"].nunique()
    label = f"{months}mo to {df['filing_date'].max():%Y-%m}"
    out: dict[str, dict] = {}
    for t in set(buy_usd.index) | set(sell_usd.index):
        net = float(buy_usd.get(t, 0.0)) - float(sell_usd.get(t, 0.0))
        rec = {"net_usd_mn": round(net / 1e6, 2), "cluster": True,
               "n_buyers": int(buyers.get(t, 0)), "n_sellers": int(sellers.get(t, 0)),
               "quarter": label}
        mc = mcap.get(str(t))
        if mc:
            rec["net_mcap_bps"] = round(net / mc * 1e4, 1)
        out[str(t)] = rec
    return out


def _insider_from_aggregate(mcap: dict[str, float], path=None) -> dict[str, dict]:
    """Single-quarter aggregate fallback (no panel): net flow + buy/sell TRANSACTION
    counts, size-normalised by market cap when available."""
    import os
    p = path or config.data_dir() / "sec_insider" / "insider.parquet"
    if not os.path.exists(p):
        return {}
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.debug("stock_fundamentals: insider parquet unreadable (%s)", e)
        return {}
    if df.empty or "net_usd" not in df.columns:
        return {}
    q = str(df["quarter"].iloc[0]) if "quarter" in df.columns and len(df) else None
    out: dict[str, dict] = {}
    for t, r in df.iterrows():
        nu = _num(r.get("net_usd"))
        if nu is None:
            continue
        rec = {"net_usd_mn": round(nu / 1e6, 2), "cluster": False,
               "n_buys": int(r.get("n_buys", 0) or 0),
               "n_sells": int(r.get("n_sells", 0) or 0), "quarter": q}
        mc = mcap.get(str(t))
        if mc:
            rec["net_mcap_bps"] = round(nu / mc * 1e4, 1)
        out[str(t)] = rec
    return out


def _load_insider(facts: dict) -> dict[str, dict]:
    """ticker -> insider net-flow chip. Prefers the PIT panel (trailing window,
    distinct-insider CLUSTERS, net buying as % of market cap); falls back to the
    single-quarter aggregate (size-normalised when caps are available), then to the
    page-level top-buyers/sellers in factors.json."""
    mcap = _mcap_map(facts)
    months = int(config.load()["sec_insider"].get("panel_window_months", 6))
    out = _insider_from_panel(mcap, months) or _insider_from_aggregate(mcap)
    if out:
        return out
    ins = facts.get("insider") or {}
    q = ins.get("quarter")
    for side in ("top_buying", "top_selling"):
        for r in ins.get(side, []) or []:
            t = r.get("ticker")
            if t:
                rec = {"net_usd_mn": _num(r.get("net_usd_mn")),
                       "n_buys": r.get("buys"), "n_sells": r.get("sells"), "quarter": q,
                       "cluster": bool(ins.get("cluster"))}
                if r.get("net_mcap_bps") is not None:
                    rec["net_mcap_bps"] = r.get("net_mcap_bps")
                out[t] = rec
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
    # join the cached 中文 translations of the (English-sourced) blurb, if any —
    # written by scripts/translate_profiles.py; absent ⇒ the analyzer keeps English.
    zp = config.data_dir() / "profile" / "descriptions_zh.parquet"
    if zp.exists():
        try:
            zdf = pd.read_parquet(zp)
            for t, row in zdf.iterrows():
                if str(t) in out and pd.notna(row.get("description_zh")):
                    out[str(t)]["description_zh"] = row["description_zh"]
        except Exception:  # noqa: BLE001 — translation is optional, never block panels
            pass
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
    safe > 2.99. Uses market cap for X4; labelled approximate for non-manufacturers.

    X4 (leverage) divides market cap by total liabilities. The EDGAR `Liabilities` tag is
    sparse — absent on many large filers' latest annual row — and when it is missing the leg
    used to silently drop out, summing only 4 legs and SYSTEMATICALLY understating Z (X4 is the
    term that rewards a large equity cushion vs. debt). That fabricated distress for solvent,
    liability-light names (e.g. AMZN). We now reconstruct liabilities as assets - equity (the
    `equity` tag is far more reliably populated) so the leg is not dropped. `approx=True` flags
    a score still computed WITHOUT the X4 leverage leg (liabilities un-reconstructable) — too
    incomplete for the policy layer to hard-block on."""
    a = _num(latest.get("assets"))
    if not a or not mktcap:
        return None
    ca, cl = _num(latest.get("cur_assets")), _num(latest.get("cur_liab"))
    wc = (ca - cl) if (ca is not None and cl is not None) else None
    liab = _num(latest.get("liabilities"))
    reconstructed = False
    if not liab:                                   # reconstruct: liabilities = assets - equity
        eq = _num(latest.get("equity"))
        recon = (a - eq) if eq is not None else None
        if recon is not None:
            liab, reconstructed = recon, True
    # An implausibly small total-liabilities figure (real tag OR reconstructed) makes X4 = mktcap/liab
    # explode into a false "safe" — every going concern carries meaningful liabilities. Floor it at 1%
    # of assets; below that the figure is corrupt, so drop X4 (-> approx) rather than trust it.
    if liab is not None and liab < 0.01 * a:
        liab, reconstructed = None, False
    x4 = mktcap / liab if liab else None
    if x4 is not None and x4 > 100:                # equity:liabilities > 100:1 is non-physical -> corrupt
        x4, reconstructed = None, False            # data (bad mktcap/liab); drop the leg (-> approx)
    # the four non-leverage legs — whether the name has a standalone score WITHOUT X4
    base = [(1.2, wc / a if wc is not None else None),
            (1.4, _num(latest.get("retained_earnings")) and _num(latest.get("retained_earnings")) / a),
            (3.3, _num(latest.get("op_income")) and _num(latest.get("op_income")) / a),
            (1.0, _num(latest.get("revenue")) and _num(latest.get("revenue")) / a)]
    base_avail = [(c, x) for c, x in base if x is not None]
    legs = base + [(0.6, x4)]
    avail = [(c, x) for c, x in legs if x is not None]
    if len(avail) < 4:
        return None
    z = sum(c * x for c, x in avail)
    zone = "safe" if z > 2.99 else "grey" if z >= 1.81 else "distress"
    # A reconstructed X4 (a positive leg) can only LIFT Z — it legitimately rescues a solvent name
    # from a false distress. But it must not be the SOLE reason a name ENTERS distress: if the name
    # had no standalone score without X4 (< 4 real legs) and still reads distress, that verdict rests
    # on the approximation — flag approx so the policy layer demotes it to context, never a hard veto.
    # No X4 leg at all is likewise too incomplete to hard-block on.
    approx = (x4 is None) or (reconstructed and len(base_avail) < 4 and zone == "distress")
    return {"z": round(z, 2), "zone": zone, "approx": approx}


def _leverage_ratios(rows: list[dict]) -> dict:
    """Bottom-survival-quality leverage ratios from statement rows.

    Follows the _altman()/_piotroski() pattern: takes the full list of per-fiscal-year
    statement rows (unfiltered, consistent with sibling helpers) and uses rows[-1]
    (latest filed FY), which is PIT-safe for a current-snapshot builder.
    Returns a dict with up to four keys; any ratio that cannot be computed (missing or
    zero denominator, all-None inputs) is absent from the dict (not set to 0/None) so
    the caller can detect unavailability via .get() returning None.

    None-safety law: never use `x or default` on values that can be 0 — use explicit
    `is None` checks throughout (repo footgun; 0 is a valid financial value).

    Ratios:
      interest_coverage      = op_income / interest_exp
                               None if either is None, or interest_exp <= 0.
      net_debt               = (debt_lt or 0) + (debt_cur or 0) − cash
                               None if ALL THREE inputs are None (don't fabricate zero).
      net_debt_to_op_income  = net_debt / op_income
                               None unless op_income > 0.  Labeled proxy for net_debt/EBITDA.
      net_debt_to_ebitda     = net_debt / (op_income + depreciation)
                               None unless depreciation is present AND denominator > 0.
                               Will be None for nearly everything until the drip accrues D&A.
    """
    if not rows:
        return {}
    latest = rows[-1]

    def _g(key):
        """Fetch a scalar from the latest row using explicit None check (not `or`)."""
        v = latest.get(key)
        return _num(v)

    op_income = _g("op_income")
    interest_exp = _g("interest_exp")
    debt_lt = _g("debt_lt")
    debt_cur = _g("debt_cur")
    cash = _g("cash")
    depreciation = _g("depreciation")

    out: dict = {}

    # ── interest_coverage ────────────────────────────────────────────────────
    if op_income is not None and interest_exp is not None and interest_exp > 0:
        out["interest_coverage"] = round(op_income / interest_exp, 2)

    # ── net_debt ─────────────────────────────────────────────────────────────
    # Treat individual missing debt fields as 0 only when at least one debt field
    # is present — avoids fabricating zero net_debt from fully-missing data.
    if debt_lt is None and debt_cur is None and cash is None:
        net_debt = None          # all three missing: no basis to compute
    else:
        # Use 0 for individually missing components when peer fields are present.
        debt_lt_v = debt_lt if debt_lt is not None else 0.0
        debt_cur_v = debt_cur if debt_cur is not None else 0.0
        cash_v = cash if cash is not None else 0.0
        net_debt = debt_lt_v + debt_cur_v - cash_v

    if net_debt is not None:
        out["net_debt"] = round(net_debt, 0)

    # ── net_debt_to_op_income (labeled EBITDA proxy) ─────────────────────────
    if net_debt is not None and op_income is not None and op_income > 0:
        out["net_debt_to_op_income"] = round(net_debt / op_income, 2)

    # ── net_debt_to_ebitda (true ratio; requires D&A from weekly drip) ────────
    if (
        net_debt is not None
        and op_income is not None
        and depreciation is not None
    ):
        ebitda = op_income + depreciation
        if ebitda > 0:
            out["net_debt_to_ebitda"] = round(net_debt / ebitda, 2)

    return out


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


# ---- accounting-quality read (DISPLAY-ONLY; never scored) -------------------
# Composes the cross-sectional accruals / profitability / investment / payout
# factor z-scores (all oriented HIGH = good in engine/equity_factors.py) with the
# single-period ratios and — where the companyfacts collector has run — multi-year
# trends, into one plain-language "is the accounting deteriorating?" verdict.
# CONTEXT ONLY: baked for the reader and deliberately NOT consumed by any scored
# output (eq_score / MRS / the factor ranks). It surfaces a fundamental read for a
# human to weigh; it never dampens a price/technical signal (that cross-modal
# interaction would need its own Phase-0 before it could touch scoring).
AQ_READS = {
    "earnings_quality":   ("Earnings quality",   "盈利质量"),
    "working_capital":    ("Working capital",    "营运资本"),
    "pricing_power":      ("Pricing power",      "定价能力"),
    "capital_discipline": ("Capital discipline", "资本纪律"),
    "balance_sheet":      ("Balance sheet",      "资产负债表"),
}
AQ_DEFAULTS = {
    "z_good": 0.5, "z_caution": -0.6,
    "asset_growth_aggressive_pct": 40.0,
    "margin_drop_pts": 3.0, "margin_rise_pts": 2.0,
    "accruals_trend_min": 0.03, "dilution_pct": 5.0,
    "wc_gap_pts": 25.0,
    "debt_to_assets_high_pct": 60.0,
    "piotroski_weak": 3, "min_reads": 2, "watch_cautions": 2, "warn_cautions": 3,
}
AQ_HEADLINE = {"clean": ("Clean", "稳健"), "watch": ("Watch", "关注"), "warn": ("Warning", "警示")}


def _aq_accruals_series(rows) -> list[float]:
    """(ni - cfo) / assets per fiscal year (ascending), unavailable years dropped."""
    out = []
    for r in rows or []:
        ni, cfo, a = _num(r.get("ni")), _num(r.get("cfo")), _num(r.get("assets"))
        if ni is not None and cfo is not None and a:
            out.append((ni - cfo) / a)
    return out


def _aq_wc_pair(rows, metric: str):
    """(metric_growth_pct, sales_growth_pct) over the fiscal years where BOTH the
    balance-sheet metric (inventory / receivables) and revenue are present and
    positive (>=3 points), else (None, None). Lets the chip flag inventory or
    receivables OUTGROWING sales — the Sloan working-capital accrual made concrete
    (ChatGPT's demand-slowdown / revenue-quality warnings). Needs the v2 companyfacts
    line items in statements.parquet; absent for banks and pre-seed names."""
    pts = []
    for r in rows or []:
        m, rev = _num(r.get(metric)), _num(r.get("revenue"))
        if m and m > 0 and rev and rev > 0:
            pts.append((int(r["fy"]), m, rev))
    if len(pts) < 3:
        return None, None
    pts.sort()
    return (pts[-1][1] / pts[0][1] - 1) * 100, (pts[-1][2] / pts[0][2] - 1) * 100


def _accounting_quality(fac: dict | None, fin: dict | None,
                        my: dict | None, rows: list | None, cfg: dict | None = None) -> dict | None:
    """Plain-language accounting-quality read for the single-stock page. Returns
    {verdict, reads[], ...} or None when fewer than ``min_reads`` sub-reads are
    computable (the panel then hides). Display-only — see the section header;
    nothing here feeds a scored output."""
    if fin is None and not fac:
        return None
    c = {**AQ_DEFAULTS, **(cfg or {})}
    fac, fin, my = fac or {}, fin or {}, my or {}
    raw = fin.get("raw") or {}
    reads: list[dict] = []

    def add(key, state, en, zh):
        en_lab, zh_lab = AQ_READS[key]
        reads.append({"key": key, "label": en_lab, "label_zh": zh_lab,
                      "state": state, "detail": en, "detail_zh": zh})

    # trend inputs computed once up front so they are always defined (None-safe)
    accs = _aq_accruals_series(rows)
    rising = len(accs) >= 3 and (accs[-1] - accs[0]) >= c["accruals_trend_min"] and accs[-1] > accs[0]
    falling = len(accs) >= 3 and (accs[0] - accs[-1]) >= c["accruals_trend_min"]
    alt = my.get("altman") or {}

    # 1) earnings quality — are earnings backed by cash? (accruals; Sloan)
    az = _num(fac.get("accruals"))                 # factor z: HIGH = low accruals = good
    cfo, ni = _num(raw.get("cfo")), _num(raw.get("ni"))
    if az is not None or _num(fin.get("accruals")) is not None or len(accs) >= 3:
        if rising or _le(az, c["z_caution"]):
            state = "caution"
        elif falling or (_ge(az, c["z_good"]) and (cfo is None or ni is None or cfo >= ni)):
            state = "good"
        else:
            state = "neutral"
        if rising:
            # window framing on purpose — `rising` is net-higher across the span, not
            # strictly monotonic, so we say "trending up over N years" not "rising N years"
            en = f"accruals trending up over {len(accs)} fiscal years — earnings increasingly not cash-backed"
            zh = f"应计利润在 {len(accs)} 个财年间走高——盈利的现金支撑减弱"
        elif state == "caution":
            en, zh = "accruals elevated vs peers (earnings lean on non-cash items)", "应计利润高于同业（盈利依赖非现金项目）"
        elif state == "good":
            en, zh = "earnings cash-backed", "盈利有现金支撑"
        else:
            en, zh = "accruals near the peer median", "应计利润接近同业中位"
        add("earnings_quality", state, en, zh)

    # 1b) working capital — inventory / receivables OUTGROWING sales (the Sloan
    # accrual decomposed into ChatGPT's demand-slowdown / revenue-quality warnings).
    # Only present once the v2 companyfacts line items are in statements.parquet.
    inv_g, inv_sales = _aq_wc_pair(rows, "inventory")
    recv_g, recv_sales = _aq_wc_pair(rows, "receivables")
    if inv_g is not None or recv_g is not None:
        gap = c["wc_gap_pts"]
        inv_build = inv_g is not None and (inv_g - inv_sales) >= gap
        recv_stretch = recv_g is not None and (recv_g - recv_sales) >= gap
        inv_ok = inv_g is None or (inv_g - inv_sales) <= -gap
        recv_ok = recv_g is None or (recv_g - recv_sales) <= -gap
        if inv_build or recv_stretch:
            state = "caution"
        elif inv_ok and recv_ok:
            state = "good"
        else:
            state = "neutral"
        en_parts, zh_parts = [], []
        if inv_build:
            en_parts.append(f"inventory +{round(inv_g)}% vs sales +{round(inv_sales)}%")
            zh_parts.append(f"存货 +{round(inv_g)}% 对销售 +{round(inv_sales)}%")
        if recv_stretch:
            en_parts.append(f"receivables +{round(recv_g)}% vs sales +{round(recv_sales)}%")
            zh_parts.append(f"应收 +{round(recv_g)}% 对销售 +{round(recv_sales)}%")
        if state == "caution":
            tag_en = (" — demand & revenue-quality risk" if (inv_build and recv_stretch)
                      else " — inventory building, demand risk" if inv_build
                      else " — receivables outpacing sales, revenue-quality risk")
            tag_zh = ("——需求与营收质量风险" if (inv_build and recv_stretch)
                      else "——存货积压，需求风险" if inv_build
                      else "——应收快于销售，营收质量风险")
            en, zh = "; ".join(en_parts) + tag_en, "；".join(zh_parts) + tag_zh
        elif state == "good":
            en, zh = "inventory & receivables lean vs sales", "存货与应收相对销售保持精简"
        else:
            en, zh = "working capital roughly in line with sales", "营运资本与销售大致同步"
        add("working_capital", state, en, zh)

    # 2) pricing power — gross profitability (Novy-Marx) + gross-margin trend
    pz = _num(fac.get("profitability"))            # HIGH = good
    gm = [x for x in (my.get("gross_margin") or []) if x is not None]
    gm_delta = (gm[-1] - gm[0]) if len(gm) >= 3 else None
    if pz is not None or gm_delta is not None:
        if (gm_delta is not None and gm_delta <= -c["margin_drop_pts"]) or _le(pz, c["z_caution"]):
            state = "caution"
        elif (gm_delta is not None and gm_delta >= c["margin_rise_pts"]) or _ge(pz, c["z_good"]):
            state = "good"
        else:
            state = "neutral"
        # keep the detail CONSISTENT with the dot: only show the margin trend when it
        # is what drove the state (compression for caution, expansion for good); a
        # caution from the cross-sectional profitability-z explains itself instead.
        compress = gm_delta is not None and gm_delta <= -c["margin_drop_pts"]
        expand = gm_delta is not None and gm_delta >= c["margin_rise_pts"]
        if state == "caution" and compress:
            en = f"gross margin −{abs(round(gm_delta, 1))}pts over {len(gm)} years"
            zh = f"毛利率 {len(gm)} 年下降 {abs(round(gm_delta, 1))} 个百分点"
        elif state == "caution":
            en, zh = "soft gross profitability vs peers", "毛利能力弱于同业"
        elif state == "good" and expand:
            en = f"gross margin +{round(gm_delta, 1)}pts over {len(gm)} years"
            zh = f"毛利率 {len(gm)} 年上升 {round(gm_delta, 1)} 个百分点"
        elif state == "good":
            en, zh = "strong gross profitability vs peers", "毛利能力强于同业"
        elif gm_delta is not None and abs(gm_delta) >= 0.1:
            en = f"gross margin {'+' if gm_delta >= 0 else '−'}{abs(round(gm_delta, 1))}pts over {len(gm)} years"
            zh = f"毛利率 {len(gm)} 年{'上升' if gm_delta >= 0 else '下降'} {abs(round(gm_delta, 1))} 个百分点"
        else:
            en, zh = "profitability near the peer median", "盈利能力接近同业中位"
        add("pricing_power", state, en, zh)

    # 3) capital discipline — asset growth, dilution, cash return
    iz = _num(fac.get("investment"))               # HIGH = low asset growth = good
    payz = _num(fac.get("payout"))                 # HIGH = returning cash = good
    ag = _num(fin.get("asset_growth"))             # %
    sh = [x for x in (_num(r.get("shares")) for r in (rows or [])) if x]
    dil = ((sh[-1] / sh[0] - 1.0) * 100) if len(sh) >= 3 and sh[0] else None
    if iz is not None or ag is not None or dil is not None:
        aggressive = (ag is not None and ag >= c["asset_growth_aggressive_pct"]) or _le(iz, c["z_caution"])
        diluting = dil is not None and dil >= c["dilution_pct"]
        if aggressive or diluting:
            state = "caution"
        elif _ge(iz, c["z_good"]) and (payz is None or payz >= 0):
            state = "good"
        else:
            state = "neutral"
        if diluting:
            en, zh = f"share count +{round(dil, 1)}% over {len(sh)} years (dilution)", f"股本 {len(sh)} 年增加 {round(dil, 1)}%（稀释）"
        elif aggressive and ag is not None:
            en, zh = f"assets +{round(ag, 1)}% (aggressive expansion)", f"资产 +{round(ag, 1)}%（扩张激进）"
        elif aggressive:
            en, zh = "aggressive asset growth vs peers", "资产增长快于同业"
        elif state == "good":
            en, zh = "disciplined growth, returning cash", "增长克制、回报股东"
        else:
            en, zh = "investment near the peer median", "投资力度接近同业中位"
        add("capital_discipline", state, en, zh)

    # 4) balance sheet — Altman zone (companyfacts) else a coarse leverage flag.
    # No Altman ⇒ we only ever flag caution (absolute leverage is sector-relative,
    # so we will not assert "safe" without the Altman corroboration).
    d2a = _num(fin.get("debt_to_assets"))
    if alt.get("zone") or d2a is not None:
        zone, zval = alt.get("zone"), alt.get("z")
        if zone == "distress":
            state, en, zh = "caution", f"Altman Z {zval} — distress zone", f"Altman Z {zval}——困境区"
        elif zone == "grey":
            # grey (1.81-2.99) is INDETERMINATE, not a red flag — neutral, not caution
            state, en, zh = "neutral", f"Altman Z {zval} — grey zone", f"Altman Z {zval}——灰色区"
        elif zone == "safe":
            state, en, zh = "good", f"Altman Z {zval} — safe zone", f"Altman Z {zval}——安全区"
        elif d2a is not None and d2a >= c["debt_to_assets_high_pct"]:
            state, en, zh = "caution", f"high leverage (LT debt {round(d2a)}% of assets)", f"杠杆偏高（长期债务占资产 {round(d2a)}%）"
        else:
            state, en, zh = "neutral", "leverage unremarkable", "杠杆水平一般"
        add("balance_sheet", state, en, zh)

    if len(reads) < c["min_reads"]:
        return None

    state_by = {r["key"]: r["state"] for r in reads}
    n_caution = sum(1 for r in reads if r["state"] == "caution")
    # earnings_quality (aggregate accruals) and working_capital (the inventory /
    # receivables that DRIVE those accruals) are the same phenomenon — when both fire,
    # the working-capital read is the EXPLANATION, not a second independent strike, so
    # collapse the pair to one caution. Without this, quality names with fast-growing
    # receivables (e.g. AAPL) would over-warn off what is really one accrual signal.
    if state_by.get("earnings_quality") == "caution" and state_by.get("working_capital") == "caution":
        n_caution -= 1
    severe = rising and alt.get("zone") == "distress"
    # With up to 5 RELATIVE reads, one isolated caution is the normal/modal state — so
    # clean absorbs <= 1 (the breakdown still shows the flag); watch = a couple of
    # concerns (>= watch_cautions); warn = multi-front (>= warn_cautions, accrual cluster
    # de-duped above) or `severe` = accruals deteriorating into the Altman distress zone.
    verdict = ("warn" if (n_caution >= c["warn_cautions"] or severe)
               else "watch" if n_caution >= c["watch_cautions"] else "clean")

    piotroski = my.get("piotroski")
    if verdict == "clean" and piotroski and piotroski.get("of") and piotroski["score"] <= c["piotroski_weak"]:
        verdict = "watch"   # the F-score corroborator can only DOWNGRADE a clean read

    has_trend = len(accs) >= 3 or gm_delta is not None or inv_g is not None or recv_g is not None
    en_head, zh_head = AQ_HEADLINE[verdict]
    return {
        "verdict": verdict,
        "headline": en_head, "headline_zh": zh_head,
        "n_caution": n_caution,
        "reads": reads,
        "piotroski": piotroski,
        "basis": "multi-year trend + peer ranks" if has_trend else "latest filing + peer ranks",
        "basis_zh": "多年趋势 + 同业排名" if has_trend else "最新财报 + 同业排名",
        "caveat": "Annual filings, lagged to the report date; free XBRL is sparse for some "
                  "filers. Context, not a signal — it does not change the technical call.",
        "caveat_zh": "年度财报，滞后于披露日；免费 XBRL 数据对部分公司不全。仅供参考，"
                     "并非交易信号，不改变技术面判断。",
    }


def _load_earnings() -> dict[str, dict]:
    """ticker -> earnings row (next date + surprise history) from the Phase-2
    earnings collector (collectors/equity_earnings.py). Empty until run."""
    p = config.data_dir() / "earnings" / "earnings.parquet"
    if not p.exists():
        return {}
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, dict] = {}
    for t, row in df.iterrows():
        try:
            surp = json.loads(row.get("surprises_json") or "[]")
        except Exception:  # noqa: BLE001
            surp = []
        nd = row.get("next_date")
        out[str(t)] = {
            "next_date": nd if isinstance(nd, str) and nd not in ("nan", "") else None,
            "next_time": row.get("next_time") if pd.notna(row.get("next_time")) else None,
            "eps_forecast": _num(row.get("eps_forecast")), "surprises": surp,
        }
    return out


def _earnings(row: dict | None, sue_z=None) -> dict | None:
    """Next-date + beat/miss summary for the Earnings panel, plus the SUE
    earnings-momentum z. SUE (standardized unexpected earnings — the post-
    earnings-announcement-drift effect) was the strongest factor and lone BH-FDR
    survivor on the shallow 2023-2025 window, but its cross-sectional edge COLLAPSES
    to ~0 on deep 2011-2026 history (engine/sue.py, factors.html; see
    reports/sue-deep-history-phase0.md) — kept as the earnings-quality / PEAD context
    read (a cross-sectional winsorized z vs the S&P 1500) beside the surprise history,
    not a validated standalone alpha.
    Days-to-earnings is NOT baked (it would go stale in the static JSON) — the page
    computes the countdown client-side from next_date."""
    row = row or {}
    sz = _r(sue_z, 2)
    surp = [s for s in (row.get("surprises") or []) if _num(s.get("surprise_pct")) is not None]
    if not row.get("next_date") and not surp and sz is None:
        return None
    summary = None
    if surp:                                 # Nasdaq returns most-recent first
        beats = sum(1 for s in surp if s["surprise_pct"] > 0)
        streak = 0
        for s in surp:
            if s["surprise_pct"] > 0:
                streak += 1
            else:
                break
        summary = {"beats": beats, "total": len(surp),
                   "avg_surprise": _r(sum(s["surprise_pct"] for s in surp) / len(surp), 1),
                   "streak": streak}
    tmap = {"time-pre-market": "pre-market", "time-after-hours": "after-hours"}
    return {
        "next_date": row.get("next_date"),
        "next_time": tmap.get(row.get("next_time")),
        "eps_forecast": _r(row.get("eps_forecast"), 2),
        "surprises": [{"qtr": s.get("qtr"), "eps": _r(s.get("eps"), 2),
                       "consensus": _r(s.get("consensus"), 2),
                       "surprise_pct": _r(s.get("surprise_pct"), 1)} for s in surp][:4],
        "summary": summary,
        "sue_z": sz,
    }


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
               nm_top_thr: float | None, *,
               sector: str | None = None,
               my: dict | None = None,
               betas: dict | None = None) -> dict | None:
    """Transparent first-match-wins cascade, v2.

    Original 4-argument call signature is preserved (new args are keyword-only
    with None defaults) so all existing callers compile unchanged.

    Precedence order is defined by ARCHETYPE_PRECEDENCE. The v2 new buckets
    (distressed, financial, rate_sensitive, commodity_sensitive, secular_growth,
    broken_growth, cyclical) are inserted ABOVE the original factor-z buckets
    (high_beta_momentum, dividend_defensive, quality_compounder, deep_value, mixed),
    so the original 6-bucket behavior is preserved for names where no v2 bucket
    fires.

    New inputs (all optional — degrading gracefully to v1 output when absent):
      sector  str   GICS sector string from factor table
      my      dict  _multiyear() output (rev_cagr, eps_cagr, altman sub-dict)
      betas   dict  per-ticker row from factor_betas.json['betas']

    Returns {key, label, label_zh, confidence, conf_word, why, why_zh,
             anchored, v2_inputs}.
    """
    if not fac:
        return None
    v, q, p = fac.get("value"), fac.get("quality"), fac.get("profitability")
    pay, lv, lb = fac.get("payout"), fac.get("low_vol"), fac.get("low_beta")
    nm_top = (net_margin is not None and nm_top_thr is not None and net_margin >= nm_top_thr)

    # --- v2 input extraction (graceful None when absent) ---
    altman   = (my or {}).get("altman") or {}
    rev_cagr = _num((my or {}).get("rev_cagr"))
    eps_cagr = _num((my or {}).get("eps_cagr"))
    # rates beta: residualized (orthogonal) beta from factor regression
    rates_beta = _num((betas or {}).get("rates"))
    # oil beta: raw (not residualized) beta; raw dict inside betas row
    _betas_raw = (betas or {}).get("raw") or {}
    oil_beta   = _num(_betas_raw.get("oil"))

    key, slack, why, why_zh = "mixed", 0.0, [], []

    # ── 1. speculative_unprofitable (original veto — fires first, unchanged) ──
    if (ni is not None and ni <= 0) or (_le(p, -0.75) and _le(v, -0.5) and _le(lb, -0.5)):
        key = "speculative_unprofitable"
        if ni is not None and ni <= 0:
            why, why_zh = ["unprofitable (net loss)"], ["未盈利（净亏损）"]
            slack = 1.0
        else:
            why, why_zh = ["weak profitability & expensive & high beta"], ["盈利弱、估值高、高贝塔"]
            slack = min(abs(_num(p) + 0.75), abs(_num(v) + 0.5), abs(_num(lb) + 0.5))

    # ── 2. distressed — Altman Z in distress zone (non-approx preferred) ──
    elif (altman.get("zone") == "distress" and
          not altman.get("approx", True) and
          _num(altman.get("z")) is not None and
          _num(altman.get("z")) < _ALTMAN_DISTRESS_MAX):
        key = "distressed"
        z_val = _num(altman.get("z"))
        why    = [f"Altman Z {z_val:.2f} < {_ALTMAN_DISTRESS_MAX} (distress zone)"]
        why_zh = [f"Altman Z {z_val:.2f}，处于困境区"]
        slack  = (_ALTMAN_DISTRESS_MAX - z_val) / _ALTMAN_DISTRESS_MAX   # 0→1 as Z→0

    # ── 3. financial — sector-keyed (EDGAR ratios unreliable for banks) ──
    elif sector in _FINANCIAL_SECTORS:
        key = "financial"
        why    = [f"financial sector ({sector}) — ratio-based gates unreliable"]
        why_zh = [f"金融行业（{sector}）——财务比率指标适用性受限"]
        slack  = 0.8   # sector tag is definitive when present

    # ── 4. rate_sensitive — anchored absolute residual rates beta ──
    elif rates_beta is not None and abs(rates_beta) >= _RATE_BETA_THR:
        key    = "rate_sensitive"
        dirn   = "positive" if rates_beta > 0 else "negative"
        why    = [f"residual rates beta {rates_beta:+.2f} (|β|≥{_RATE_BETA_THR}, {dirn})"]
        why_zh = [f"利率残差贝塔 {rates_beta:+.2f}（绝对值≥{_RATE_BETA_THR}，{dirn}方向）"]
        slack  = (abs(rates_beta) - _RATE_BETA_THR) / _RATE_BETA_THR

    # ── 5. commodity_sensitive — anchored absolute oil beta (raw) ──
    elif oil_beta is not None and abs(oil_beta) >= _OIL_BETA_THR:
        key    = "commodity_sensitive"
        dirn   = "positive" if oil_beta > 0 else "negative"
        why    = [f"raw oil beta {oil_beta:+.2f} (|β|≥{_OIL_BETA_THR}, {dirn})"]
        why_zh = [f"原油原始贝塔 {oil_beta:+.2f}（绝对值≥{_OIL_BETA_THR}，{dirn}方向）"]
        slack  = (abs(oil_beta) - _OIL_BETA_THR) / _OIL_BETA_THR

    # ── 6. secular_growth — anchored CAGR thresholds (never cross-sectional) ──
    elif (rev_cagr is not None and rev_cagr >= _SECULAR_REV_CAGR_THR and
          eps_cagr is not None and eps_cagr >= _SECULAR_EPS_CAGR_THR):
        key    = "secular_growth"
        why    = [f"rev CAGR {rev_cagr:.1f}%≥{_SECULAR_REV_CAGR_THR}%, "
                  f"EPS CAGR {eps_cagr:.1f}%≥{_SECULAR_EPS_CAGR_THR}%"]
        why_zh = [f"营收复合增速 {rev_cagr:.1f}%≥{_SECULAR_REV_CAGR_THR}%，"
                  f"EPS复合增速 {eps_cagr:.1f}%≥{_SECULAR_EPS_CAGR_THR}%"]
        slack  = min((rev_cagr - _SECULAR_REV_CAGR_THR) / 10.0,
                     (eps_cagr - _SECULAR_EPS_CAGR_THR) / 10.0)

    # ── 7. broken_growth — prior revenue growth, but EPS failing ──
    elif (rev_cagr is not None and rev_cagr >= _BROKEN_REV_CAGR_THR and
          eps_cagr is not None and eps_cagr <= 0.0):
        key    = "broken_growth"
        why    = [f"rev CAGR {rev_cagr:.1f}%≥{_BROKEN_REV_CAGR_THR}% "
                  f"but EPS CAGR {eps_cagr:.1f}%≤0 (margin/dilution destruction)"]
        why_zh = [f"营收复合增速 {rev_cagr:.1f}%≥{_BROKEN_REV_CAGR_THR}%，"
                  f"但EPS复合增速 {eps_cagr:.1f}%≤0（利润率/稀释问题）"]
        slack  = min((rev_cagr - _BROKEN_REV_CAGR_THR) / 10.0,
                     abs(eps_cagr) / 10.0)

    # ── 8. cyclical — sector + no strong quality/defensive overlay ──
    elif (sector in _CYCLICAL_SECTORS and
          not (_ge(pay, 0.5) and _ge(lv, 0.3)) and    # not defensive
          not _ge(q, 0.6)):                             # not quality compounder
        key    = "cyclical"
        why    = [f"cyclical sector ({sector}), no defensive/quality overlay"]
        why_zh = [f"周期性行业（{sector}），无防御/质量叠加"]
        slack  = 0.5

    # ── 9. high_beta_momentum (original — unchanged) ──
    elif _le(lb, -0.6) and _le(lv, -0.4):
        key = "high_beta_momentum"
        why, why_zh = ["high beta & high volatility vs peers"], ["相对同业高贝塔、高波动"]
        slack = min(abs(_num(lb) + 0.6), abs(_num(lv) + 0.4))

    # ── 10. dividend_defensive (original — unchanged) ──
    elif _ge(pay, 0.5) and _ge(lv, 0.4) and _ge(lb, 0.3):
        key = "dividend_defensive"
        why, why_zh = ["high shareholder payout, low volatility & low beta"], ["高股东回报、低波动、低贝塔"]
        slack = min(_num(pay) - 0.5, _num(lv) - 0.4, _num(lb) - 0.3)

    # ── 11. quality_compounder (original — unchanged) ──
    elif _ge(q, 0.5) and (_ge(p, 0.3) or nm_top) and not _ge(v, 0.75):
        key = "quality_compounder"
        why, why_zh = ["high quality" + (", strong margins" if nm_top else "")], \
                      ["高质量" + ("、利润率领先" if nm_top else "")]
        slack = _num(q) - 0.5

    # ── 12. deep_value (original — unchanged) ──
    elif _ge(v, 0.75) and not _ge(q, 0.5):
        key = "deep_value"
        why, why_zh = ["cheap on value factors, quality not high"], ["价值因子便宜，质量一般"]
        slack = _num(v) - 0.75

    # ── 13. mixed (original fallback — unchanged) ──
    else:
        key = "mixed"
        why, why_zh = ["no single factor dominates"], ["无单一因子主导"]
        slack = 0.15

    slack = _num(slack) or 0.0
    conf = max(0.0, min(1.0, slack / 0.6))
    conf_word = "high" if conf >= 0.66 else "moderate" if conf >= 0.33 else "low"
    en, zh = ARCHETYPES[key]

    # anchored flag: True when the threshold is absolute/time-stable (v2 buckets 2-8),
    # False for the factor-z driven buckets which are cross-sectionally relative.
    _ANCHORED_KEYS = frozenset({
        "distressed", "financial", "rate_sensitive", "commodity_sensitive",
        "secular_growth", "broken_growth", "cyclical",
    })
    anchored = key in _ANCHORED_KEYS

    # v2_inputs: surface which optional inputs fired (for debuggability)
    v2_inputs = {
        "sector": sector,
        "rev_cagr": rev_cagr, "eps_cagr": eps_cagr,
        "altman_z": _num(altman.get("z")), "altman_zone": altman.get("zone"),
        "rates_beta": rates_beta, "oil_beta_raw": oil_beta,
    }

    return {"key": key, "label": en, "label_zh": zh,
            "confidence": round(conf, 2), "conf_word": conf_word,
            "why": "; ".join(why), "why_zh": "；".join(why_zh),
            "anchored": anchored, "v2_inputs": v2_inputs}


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
        "description_zh": pr.get("description_zh"),  # cached 中文, if translate_profiles ran
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


def _positioning(t, f, short, insider, short_flow=None) -> dict | None:
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
    # Fresher than the bi-monthly settlement: daily off-exchange short flow.
    # A CONTEXT confirmer (trend_pp = recent vs trailing short-ratio, in pts),
    # never a scored factor — see engine/short_volume.py.
    if short_flow:
        block["short_flow"] = {
            "short_ratio_pct": _r((short_flow.get("short_ratio") or 0) * 100, 1),
            "trend_pp": _r(short_flow.get("trend_pp"), 2),
            "n_days": short_flow.get("n_days"),
            "asof": short_flow.get("asof"),
        }
    if insider:
        block["insider"] = insider
    return block or None


def _revision_block(rev: dict | None) -> dict | None:
    """Analyst revision-MOMENTUM (the change in consensus), the part that carries
    signal — the consensus level is kept only as labelled context. Phase-2 free
    read off the Finnhub recommendation snapshots (engine/analyst_revisions.py)."""
    if not rev:
        return None
    return {
        "direction": rev.get("direction"),            # upgrading / downgrading / stable
        "delta": rev.get("revision_delta"),           # net-buy change = the SIGNAL
        "consensus_pct": rev.get("consensus_pct"),    # LEVEL = context only
        "n_analysts": rev.get("n_analysts"),
        "n_periods": rev.get("n_periods"),
        "asof": rev.get("latest_period"),
    }


def _analyst(t, deep, rev=None) -> dict | None:
    """Forward P/E + market ratios from the deep yfinance snapshot, plus analyst
    revision-MOMENTUM (Phase 2). Consensus ratings & price targets remain unwired
    (Finnhub-Premium/Benzinga, out of scope), so the revision delta — the part the
    literature says actually predicts — is what we surface."""
    d = deep or {}
    fwd = d.get("fwd_pe")
    revision = _revision_block(rev)
    if not d:
        out = {"tier": "lite", "rating": None, "target": None}
        if revision:
            out["revision"] = revision
        return out
    out = {
        "tier": "deep",
        "forward_pe": _r(fwd, 1) if fwd else None,
        "pe_yf": _r(d.get("pe"), 1) if d.get("pe") else None,
        "profit_margin": _r((d.get("profit_margin") or 0) * 100, 1) if d.get("profit_margin") is not None else None,
        "roe": _r((d.get("roe") or 0) * 100, 1) if d.get("roe") is not None else None,
        "div_yield": _r(d.get("div_yield"), 2) if d.get("div_yield") is not None else None,
        "rating": None, "target": None,
    }
    if revision:
        out["revision"] = revision
    return out


# ── W2 PR-K helpers — called from panels() ───────────────────────────────────

def _compute_moat_block(
    ticker: str,
    statements_df: "pd.DataFrame | None",
    base_rates: dict,
) -> "dict | None":
    """Call compute_moat_falsifiers for one ticker; non-fatal.  Returns None when
    statements_df is absent (panel is omitted from the JSON by the ``if v`` filter)."""
    if statements_df is None or statements_df.empty:
        return None
    try:
        from engine.moat_falsifiers import compute_moat_falsifiers  # noqa: PLC0415
        result = compute_moat_falsifiers(ticker, statements_df, base_rates=base_rates)
        # Suppress missing-data results to keep JSON lean (panel hidden when absent)
        if result.get("sensor_coverage") == "missing":
            return None
        return result
    except Exception as exc:  # noqa: BLE001
        log.debug("stock_fundamentals: moat_falsifiers skipped for %s (%s)", ticker, exc)
        return None


def _compute_trap_block(
    ticker: str,
    analyst_rev: dict,
    insider: dict,
) -> "dict | None":
    """Assemble great_company_trap inputs from existing loaded structures; non-fatal.
    crowding_z is basket-level (not per-ticker in this context) — passed as None.
    Returns None when all inputs are unavailable (panel hidden from JSON)."""
    try:
        from engine.moat_falsifiers import great_company_trap  # noqa: PLC0415
        rev_row = analyst_rev.get(ticker)
        revision_dir: str | None = rev_row.get("direction") if rev_row else None
        ins_row = insider.get(ticker)
        # insider net_usd_mn is in millions; great_company_trap expects USD
        insider_net_usd: float | None = None
        if ins_row:
            mn = ins_row.get("net_usd_mn")
            if mn is not None:
                try:
                    insider_net_usd = float(mn) * 1e6
                except (TypeError, ValueError):
                    pass
        # Only emit the block when at least one input is available
        if revision_dir is None and insider_net_usd is None:
            return None
        return great_company_trap(
            crowding_z=None,
            insider_net_usd=insider_net_usd,
            revision_direction=revision_dir,
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("stock_fundamentals: great_company_trap skipped for %s (%s)", ticker, exc)
        return None


def panels() -> dict[str, dict]:
    """{ticker: {profile, valuation, financials, factors, positioning, analyst,
    thesis_clock}}
    for every name we have fundamentals on. Empty dict if the EDGAR cache is
    missing (caller logs and ships the page without fundamental panels).

    W2 PR-J: thesis_clock is a DISPLAY-ONLY Long-Hold Thesis Layer annotation.
    It carries _horizon_role="hold_thesis" and must not feed any entry-stack
    scored surface (LH-R1 firewall, G1-DEFERRED ruling 2026-07-06).
    """
    fund = _load_fundamentals()
    if fund is None:
        log.warning("stock_fundamentals: no edgar fundamentals — panels skipped")
        return {}
    facts = _load_factors()
    table = facts["table"]
    short = _load_short()
    short_flow = _load_short_volume()
    analyst_rev = _load_analyst_revisions()
    insider = _load_insider(facts)
    deep = _load_deep()
    profiles = _load_profiles()
    statements = _load_statements()
    earnings = _load_earnings()
    aq_cfg = config.load().get("accounting_quality") or {}
    betas_map = _load_betas()   # v2: per-name rates/oil betas for archetype v2

    # W2 PR-J: thesis_clock map (display-only; no entry-stack consumers)
    from engine.long_hold_clocks import thesis_clocks_from_parquet  # noqa: PLC0415
    _thesis_clocks: dict[str, dict] = {}
    try:
        _thesis_clocks = thesis_clocks_from_parquet()
    except Exception as _tc_exc:  # noqa: BLE001
        log.warning("stock_fundamentals: thesis_clocks skipped (%s)", _tc_exc)

    # W2 PR-K: moat falsifier sensors + great-company-trap overlay (display-only;
    # horizon_role=hold_thesis; MUST NOT feed entry-stack scored surfaces — LH-R1).
    from engine.moat_falsifiers import (  # noqa: PLC0415
        compute_base_rates,
        compute_moat_falsifiers,
        great_company_trap,
    )
    _statements_df: pd.DataFrame | None = None
    _moat_base_rates: dict = {}
    try:
        _sp = config.data_dir() / "edgar" / "statements.parquet"
        if _sp.exists():
            _statements_df = pd.read_parquet(_sp)
            _moat_base_rates = compute_base_rates(_statements_df)
    except Exception as _mf_exc:  # noqa: BLE001
        log.warning("stock_fundamentals: moat_falsifiers base rates skipped (%s)", _mf_exc)

    M = _context_frame(fund, table)
    nm_top_thr = _num(M["net_margin"].quantile(2 / 3)) if "net_margin" in M else None

    out: dict[str, dict] = {}
    for t, f in fund.iterrows():
        fac = table.get(t)
        ni = _num(f.get("ni"))
        net_margin = _num(M.loc[t, "net_margin"]) if t in M.index else None
        mcap = _num(M.loc[t, "mktcap"]) if t in M.index else None
        rows = statements.get(str(t))
        my = _multiyear(rows, mcap)
        # v2: pass sector, multiyear, and per-name betas into _archetype()
        arche = _archetype(
            fac, ni, net_margin, nm_top_thr,
            sector=(fac or {}).get("sector"),
            my=my,
            betas=betas_map.get(str(t)),
        )
        fin = _financials(t, f, deep.get(t), my)
        # Leverage ratios: computed from the PIT-filtered statement rows (same rows
        # already used for _multiyear).  None-safe throughout; Financial-sector names
        # and names without statements will produce an empty dict which is excluded by
        # the `if v` filter below (display-only, partial coverage expected).
        lev = _leverage_ratios(rows or [])
        blocks = {
            "profile": _profile(t, f, fac, M, arche, profiles.get(str(t))),
            "valuation": _valuation(t, f, fac, M, deep.get(t)),
            "financials": fin,
            "factors": _factors(t, fac, facts, M),
            "positioning": _positioning(t, f, short, insider.get(t), short_flow.get(str(t))),
            "analyst": _analyst(t, deep.get(t), analyst_rev.get(str(t))),
            # SUE earnings-momentum z lives in the factors table (the canonical home
            # of every factor leg, written by equity_factors just before this runs);
            # surface it on the Earnings panel since it IS an earnings read.
            "earnings": _earnings(earnings.get(str(t)), (fac or {}).get("sue")),
            # accounting-quality read — composes the accruals / profitability /
            # investment factor z's + single-period ratios + (where companyfacts has
            # run) the multi-year trend. DISPLAY-ONLY: baked for the reader, never scored.
            "accounting_quality": _accounting_quality(fac, fin, my, rows, aq_cfg),
            # bottom-survival-quality leverage ratios (display-only; partial coverage
            # until the weekly D&A drip accrues; Financial-sector names mostly absent).
            "leverage_ratios": lev if lev else None,
            # W2 PR-J — Long-Hold Thesis Layer: thesis_clock annotation.
            # Days since latest EDGAR period_end with positive fundamental delta (v1).
            # DISPLAY-ONLY; horizon_role=hold_thesis; must NOT feed entry-stack surfaces.
            "thesis_clock": _thesis_clocks.get(str(t)) or None,
            # W2 PR-K — moat falsifier sensors (DISPLAY-ONLY; horizon_role=hold_thesis).
            # Four sensors from statements.parquet: margin compression, receivables
            # stretch, inventory build, capital intensity rising.  Each sensor carries
            # a matched-control universe base rate so display layer can show context.
            # MUST NOT feed board ordering, alert triage, top-setups gates, or push floor.
            "moat_falsifiers": _compute_moat_block(
                str(t), _statements_df, _moat_base_rates,
            ),
            # W2 PR-K — great-company-trap de-escalation overlay (LH-R10).
            # Assembled ONLY from existing signals; may ONLY lower conviction context.
            "great_company_trap": _compute_trap_block(
                str(t), analyst_rev, insider,
            ),
        }
        out[str(t)] = _clean({k: v for k, v in blocks.items() if v})
    log.info("stock_fundamentals: %d names with panels (factors %d, deep %d, short %s)",
             len(out), len(table), len(deep), 0 if short is None else len(short))
    return out


# ── Historical archetype series ──────────────────────────────────────────────

def archetypes_history(out_path=None) -> pd.DataFrame:
    """Run the v2 archetype classifier over the PIT fundamentals panel
    (data/edgar/fundamentals_panel.parquet) at annual steps and persist
    the result to data/archetypes/history.parquet.

    Point-in-time (PIT) status of each input — NOT a uniform PIT guarantee:

      PIT inputs (genuinely point-in-time):
        - Altman Z ratio inputs: assets, cur_assets, cur_liab, retained_earnings,
          op_income, revenue — drawn from statements.parquet filtered to fy <= this
          row's fy, so no forward look on the balance-sheet / income numbers.
        - rev_cagr, eps_cagr — computed from statements rows with fy <= this panel fy
          (same PIT filter), so CAGR inputs are historically valid.

      CURRENT-SNAPSHOT inputs (NOT PIT — same 2026 value used for every historical row):
        - sector: from site/factordata/factors.json (single cross-sectional snapshot)
        - rates_beta: from site/factor_betas.json (single 2026 regression snapshot)
        - oil_beta_raw: from site/factor_betas.json (same 2026 snapshot)
        - factor z-scores (value, quality, profitability, …): from factors.json (2026)

    CONSEQUENCE: archetype LABELS for beta/sector-driven buckets (rate_sensitive,
    commodity_sensitive, financial, cyclical) are NON-PIT for historical rows.
    Empirical check: 0/1331 tickers vary their sector/rates_beta/oil_beta across
    years in this parquet (all snapshots are single-valued), confirming the
    non-variation is structural, not incidental.

    DISPLAY-ONLY constraint (§3.4 of the masterplan): historical archetype labels
    may seed display-only hypothesis priors. They must NEVER be used as learned
    multipliers, training labels, or species scope-gates — those uses require
    genuinely PIT inputs.

    The distressed bucket also has a silent early-year gap: Altman inputs are NaN
    for most pre-~2020 rows (EDGAR XBRL coverage is sparse before 2018-2020), so
    early-year rows are almost entirely determined by current-day inputs (sector,
    betas, factor z-scores).

    The ``basis`` column records ``annual_fy`` to make the annual step explicit.

    Inputs consumed (all optional — rows that lack them get None for those fields):
      - data/edgar/fundamentals_panel.parquet   (PIT financials — Altman inputs)
      - data/edgar/statements.parquet           (rev/EPS multi-year for CAGR — PIT-filtered)
      - site/factor_betas.json                  (rate/oil betas — CURRENT-SNAPSHOT, non-PIT)
      - site/factordata/factors.json            (sector + factor z-scores — CURRENT-SNAPSHOT, non-PIT)

    Returns the DataFrame (also written to disk).
    Lifecycle: rebuilt on demand via scripts/build_archetype_history.py; not on the
    nightly path; frozen between rebuilds.
    """
    import os

    panel_path = config.data_dir() / "edgar" / "fundamentals_panel.parquet"
    if not panel_path.exists():
        log.warning("archetypes_history: fundamentals_panel.parquet not found — skip")
        return pd.DataFrame()

    panel = pd.read_parquet(panel_path)
    if panel.empty:
        return pd.DataFrame()

    # Load side tables for v2 inputs
    stmts = _load_statements()        # ticker -> list[dict] of annual rows (ascending fy)
    betas_map = _load_betas()         # ticker -> beta row
    facts = _load_factors()
    table = facts["table"]            # ticker -> factor z-scores + sector

    # Build mktcap map from the factor table (cross-sectional, same for all years —
    # we only have one mktcap snapshot, not PIT mktcap history)
    mcap_map: dict[str, float] = {}
    for t, r in table.items():
        b = _num(r.get("mktcap_bn"))
        if b and b > 0:
            mcap_map[t] = b * 1e9

    records = []
    for _, row in panel.iterrows():
        ticker = str(row["ticker"])
        fy = int(row["fy"])
        asof = row.get("asof_date")
        period_end = row.get("period_end")

        mcap = mcap_map.get(ticker)

        # Multi-year CAGRs: use only statements rows with fy <= this panel fy (PIT-safe)
        stmt_rows = [r for r in (stmts.get(ticker) or []) if int(r.get("fy", 9999)) <= fy]
        # Altman: use the matching statements row (has cur_assets/cur_liab/retained_earnings
        # /op_income) rather than fundamentals_panel (which lacks those columns)
        stmt_latest = stmt_rows[-1] if stmt_rows else {}
        # Supplement with panel fields if statements row is incomplete
        altman_row = {
            "assets":            stmt_latest.get("assets") or row.get("assets"),
            "cur_assets":        stmt_latest.get("cur_assets"),
            "cur_liab":          stmt_latest.get("cur_liab"),
            "liabilities":       stmt_latest.get("liabilities"),
            "equity":            stmt_latest.get("equity") or row.get("equity"),
            "retained_earnings": stmt_latest.get("retained_earnings"),
            "op_income":         stmt_latest.get("op_income"),
            "revenue":           stmt_latest.get("revenue") or row.get("revenue"),
        }
        altman_result = _altman(altman_row, mcap)
        my_block = _multiyear(stmt_rows, mcap) if stmt_rows else None

        fac = table.get(ticker)
        ni = _num(row.get("ni"))

        # For net_margin we compute inline (no context_frame available here)
        rev = _num(row.get("revenue"))
        net_margin = (ni / rev * 100) if (ni is not None and rev and rev != 0) else None

        arche = _archetype(
            fac, ni, net_margin, nm_top_thr=None,   # no cross-sectional threshold
            sector=(fac or {}).get("sector"),
            my={**(my_block or {}), "altman": altman_result},
            betas=betas_map.get(ticker),
        )

        records.append({
            "ticker":     ticker,
            "fy":         fy,
            "asof_date":  asof,
            "period_end": period_end,
            "basis":      "annual_fy",
            "archetype":  arche["key"] if arche else None,
            "confidence": arche["confidence"] if arche else None,
            "anchored":   arche["anchored"] if arche else None,
            "why":        arche["why"] if arche else None,
            "sector":     (fac or {}).get("sector"),
            "rev_cagr":   (my_block or {}).get("rev_cagr"),
            "eps_cagr":   (my_block or {}).get("eps_cagr"),
            "altman_z":   (altman_result or {}).get("z"),
            "altman_zone": (altman_result or {}).get("zone"),
            "rates_beta": (betas_map.get(ticker) or {}).get("rates"),
            "oil_beta_raw": ((betas_map.get(ticker) or {}).get("raw") or {}).get("oil"),
        })

    df = pd.DataFrame(records)
    if df.empty:
        return df

    # Write to data/archetypes/history.parquet
    if out_path is None:
        out_path = config.data_dir() / "archetypes" / "history.parquet"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.to_parquet(out_path, index=False)
    log.info("archetypes_history: wrote %d rows to %s", len(df), out_path)
    return df
