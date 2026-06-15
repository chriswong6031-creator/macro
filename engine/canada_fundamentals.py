"""Descriptive TSX fundamentals from yfinance `get_info` (cached).

The Canada parallel of engine/china_fundamentals.py. There is no clean keyless
multi-year statement feed for TSX names (SEC EDGAR is US-only; SEDI is not cleanly
machine-readable), so this sources the single-snapshot valuation/quality fields
yfinance exposes per ticker and caches them under data/canada_fundamentals/.
Per name it computes:

  - profile     : long business summary + sector/industry
  - valuation   : PE / PB / PS / ROE / net margin / debt / dividend yield, each vs
                  its SECTOR median
  - archetype   : a descriptive style bucket (quality compounder / dividend
                  defensive / deep value / growth / speculative …)

IMPORTANT — this is CONTEXT, NOT A SIGNAL. Value/quality are not validated
cross-sectional edges here (no Phase-0 yet), so the page surfaces this as a
fundamental backdrop to read ALONGSIDE the cycle/alpha signals, never as a buy
ranking. yfinance get_info is best-effort; a name with no info simply has no panel.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import pandas as pd

from lib import config

log = logging.getLogger("canada_fundamentals")

CACHE = config.data_dir() / "canada_fundamentals" / "fundamentals.parquet"

# yfinance get_info fields we keep (kept small + stable)
INFO_FIELDS = ["shortName", "longName", "longBusinessSummary", "sector", "industry",
               "trailingPE", "priceToBook", "priceToSalesTrailing12Months", "returnOnEquity",
               "profitMargins", "debtToEquity", "dividendYield", "marketCap",
               "revenueGrowth", "earningsGrowth"]

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


def _pct(v):
    """yfinance returns fractions for ratios (roe 0.15, dividendYield 0.04); ->%."""
    n = _num(v)
    return round(n * 100, 2) if n is not None else None


def _valuation(info: dict) -> dict:
    """PE / PB / PS / ROE / net margin / debt / dividend yield from yfinance info."""
    return {
        "pe": _num(info.get("trailingPE")),
        "pb": _num(info.get("priceToBook")),
        "ps": _num(info.get("priceToSalesTrailing12Months")),
        "roe": _pct(info.get("returnOnEquity")),
        "net_margin": _pct(info.get("profitMargins")),
        "debt_to_equity": _num(info.get("debtToEquity")),
        # yfinance returns dividendYield ALREADY as a percent (e.g. RY 2.52, ENB 4.91),
        # unlike returnOnEquity/profitMargins which are fractions — so do NOT rescale it.
        "div_yield": round(_num(info.get("dividendYield")), 2) if _num(info.get("dividendYield")) is not None else None,
        "rev_growth": _pct(info.get("revenueGrowth")),
        "market_cap": _num(info.get("marketCap")),
    }


def _archetype(val: dict) -> str:
    roe, dy = val.get("roe"), val.get("div_yield")
    nm, rev_g = val.get("net_margin"), val.get("rev_growth")
    debt = val.get("debt_to_equity")
    if nm is not None and nm < 0:
        return "speculative_unprofitable"
    if dy is not None and dy >= 3 and (rev_g is None or rev_g < 8):
        return "dividend_defensive"
    if roe is not None and roe >= 15 and (debt is None or debt < 150) \
            and (rev_g is None or rev_g >= 0):
        return "quality_compounder"
    if rev_g is not None and rev_g >= 20:
        return "growth"
    return "mixed"


# ---------------------------------------------------------------- fetch (yfinance)

def fetch_info(tickers: list[str], max_new: int = 120) -> int:
    """Best-effort yfinance get_info refresh, merged into the cache. Only up to
    `max_new` names without cached info are looked up per run (keeps CI lean).
    Never raises — returns how many names were (re)fetched."""
    import yfinance as yf

    have: dict[str, dict] = {}
    if CACHE.exists():
        try:
            df = pd.read_parquet(CACHE)
            for _, r in df.iterrows():
                have[r["ticker"]] = json.loads(r["payload"])
        except Exception as e:  # noqa: BLE001
            log.warning("canada fundamentals cache read failed: %s", e)

    todo = [t for t in tickers if t not in have][:max_new]
    n = 0
    for t in todo:
        try:
            info = yf.Ticker(t).get_info() or {}
            have[t] = {k: info.get(k) for k in INFO_FIELDS if info.get(k) is not None}
            n += 1
            time.sleep(0.05)
        except Exception as e:  # noqa: BLE001 — one name down can't break the batch
            log.debug("canada fundamentals %s failed: %s", t, e)
    if n:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        rows = [{"ticker": t, "payload": json.dumps(v)} for t, v in have.items()]
        pd.DataFrame(rows).to_parquet(CACHE)
    return n


def display_names() -> dict[str, str]:
    """{ticker: shortName/longName} from the cache, for pretty display labels.
    Empty when the cache is absent (callers fall back to the ticker)."""
    if not CACHE.exists():
        return {}
    try:
        df = pd.read_parquet(CACHE)
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, str] = {}
    for _, r in df.iterrows():
        try:
            info = json.loads(r["payload"])
        except Exception:  # noqa: BLE001
            continue
        nm = info.get("shortName") or info.get("longName")
        if nm:
            out[r["ticker"]] = str(nm)
    return out


def build_all(sector_by_ticker: dict[str, str] | None = None) -> dict[str, dict]:
    """Per-ticker fundamentals map for every cached name, each with PE/PB/ROE/yield
    vs its SECTOR median. Returns {} when the cache is absent (degrade-don't-crash)."""
    if not CACHE.exists():
        return {}
    try:
        df = pd.read_parquet(CACHE)
    except Exception as e:  # noqa: BLE001
        log.warning("canada fundamentals cache read failed: %s", e)
        return {}
    sector_by_ticker = sector_by_ticker or {}

    base: dict[str, dict] = {}
    for _, r in df.iterrows():
        try:
            info = json.loads(r["payload"])
        except Exception:  # noqa: BLE001
            continue
        base[r["ticker"]] = {"info": info, "val": _valuation(info)}

    def med(vals):
        v = sorted(x for x in vals if x is not None)
        return v[len(v) // 2] if v else None
    sec_vals: dict[str, dict[str, list]] = {}
    for t, b in base.items():
        s = sector_by_ticker.get(t) or b["info"].get("sector") or "—"
        d = sec_vals.setdefault(s, {"pe": [], "pb": [], "roe": [], "div_yield": []})
        for k in d:
            x = b["val"].get(k)
            if x is not None and (k != "pe" or x > 0):
                d[k].append(x)
    sec_med = {s: {k: med(v) for k, v in d.items()} for s, d in sec_vals.items()}

    out: dict[str, dict] = {}
    for t, b in base.items():
        info, val = b["info"], b["val"]
        s = sector_by_ticker.get(t) or info.get("sector") or "—"
        for k in ("pe", "pb", "roe", "div_yield"):
            val[f"{k}_sector_med"] = sec_med.get(s, {}).get(k)
        arch = _archetype(val)
        out[t] = {
            "description": {"summary": info.get("longBusinessSummary"),
                            "sector": info.get("sector"), "industry": info.get("industry")},
            "valuation": val,
            "archetype": arch,
            "archetype_label": ARCHETYPES.get(arch, ARCHETYPES["mixed"])[0],
            "archetype_label_zh": ARCHETYPES.get(arch, ARCHETYPES["mixed"])[1],
        }
    return out
