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

# yfinance get_info fields we keep. The second block is the Phase-1 enrichment —
# forward valuation, sell-side consensus and positioning, all already returned by the
# SAME get_info call and previously dropped (the cheapest route to US-style panels).
INFO_FIELDS = ["shortName", "longName", "longBusinessSummary", "sector", "industry",
               "trailingPE", "priceToBook", "priceToSalesTrailing12Months", "returnOnEquity",
               "profitMargins", "debtToEquity", "dividendYield", "marketCap",
               "revenueGrowth", "earningsGrowth",
               # forward valuation
               "forwardPE", "trailingPegRatio", "payoutRatio", "fiveYearAvgDividendYield",
               # analyst consensus
               "targetMeanPrice", "targetHighPrice", "targetLowPrice", "recommendationKey",
               "recommendationMean", "numberOfAnalystOpinions", "currentPrice",
               # positioning / ownership (keyless SI substitute; SEDI/IIROC not machine-readable)
               "sharesShort", "shortRatio", "shortPercentOfFloat",
               "heldPercentInsiders", "heldPercentInstitutions"]

# re-fetch a cached name when its snapshot is older than this (days) — so the new
# fields backfill onto names cached before the enrichment, a few-per-build at a time.
INFO_MAX_AGE_DAYS = 12

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
        # forward valuation (forwardPE/PEG are plain ratios; payout/5y-yield are the
        # income lens that matters most on a dividend-heavy TSX — payoutRatio is a
        # fraction -> %, fiveYearAvgDividendYield is already a percent like dividendYield)
        "forward_pe": _num(info.get("forwardPE")),
        "peg": _num(info.get("trailingPegRatio")),
        "payout": _pct(info.get("payoutRatio")),
        "five_yr_yield": round(_num(info.get("fiveYearAvgDividendYield")), 2)
                         if _num(info.get("fiveYearAvgDividendYield")) is not None else None,
    }


# recommendationKey -> (display, 中文). yfinance buckets: strong_buy/buy/hold/sell/strong_sell
_REC = {"strong_buy": ("Strong Buy", "强力买入"), "buy": ("Buy", "买入"),
        "hold": ("Hold", "持有"), "underperform": ("Underperform", "跑输"),
        "sell": ("Sell", "卖出"), "strong_sell": ("Strong Sell", "强力卖出")}


def _consensus(info: dict) -> dict | None:
    """Sell-side consensus from the same get_info call: mean/high/low price target,
    implied upside vs the current price, the rating word, and coverage breadth."""
    n = _num(info.get("numberOfAnalystOpinions"))
    tgt = _num(info.get("targetMeanPrice"))
    if not n and tgt is None:
        return None
    px = _num(info.get("currentPrice"))
    rec = str(info.get("recommendationKey") or "").lower()
    out: dict = {
        "n_analysts": int(n) if n else None,
        "target_mean": tgt, "target_high": _num(info.get("targetHighPrice")),
        "target_low": _num(info.get("targetLowPrice")),
        "rating_mean": _num(info.get("recommendationMean")),
    }
    if rec in _REC:
        out["rating"], out["rating_zh"] = _REC[rec]
    if tgt is not None and px and px > 0:
        out["upside_pct"] = round((tgt / px - 1) * 100, 1)
    return out


def _positioning(info: dict) -> dict | None:
    """Keyless positioning substitute from get_info: short interest (shares + days-to-
    cover + % float when present) and insider / institutional ownership. SEDI Form-4-style
    insider transactions and IIROC short interest are not machine-readable, so this is
    the best free read — descriptive context, not a signal."""
    ss = _num(info.get("sharesShort"))
    sr = _num(info.get("shortRatio"))
    spf = _num(info.get("shortPercentOfFloat"))
    hi = _num(info.get("heldPercentInsiders"))
    ho = _num(info.get("heldPercentInstitutions"))
    if all(x is None for x in (ss, sr, spf, hi, ho)):
        return None
    return {
        "shares_short": ss, "days_to_cover": sr,
        "short_pct_float": round(spf * 100, 2) if spf is not None else None,
        "held_insiders": round(hi * 100, 2) if hi is not None else None,
        "held_institutions": round(ho * 100, 1) if ho is not None else None,
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
    """Best-effort yfinance get_info refresh, merged into the cache. Fetches names that
    are uncached OR whose snapshot is older than INFO_MAX_AGE_DAYS (so the enrichment
    fields backfill onto pre-existing names), up to `max_new` per run. Never raises —
    returns how many names were (re)fetched."""
    import yfinance as yf

    have: dict[str, dict] = {}     # ticker -> {"info": {...}, "asof": "YYYY-MM-DD"}
    if CACHE.exists():
        try:
            df = pd.read_parquet(CACHE)
            has_asof = "asof" in df.columns
            for _, r in df.iterrows():
                asof = str(r["asof"]) if has_asof and pd.notna(r["asof"]) else ""
                have[r["ticker"]] = {"info": json.loads(r["payload"]), "asof": asof}
        except Exception as e:  # noqa: BLE001
            log.warning("canada fundamentals cache read failed: %s", e)

    fresh_cut = (pd.Timestamp.now() - pd.Timedelta(days=INFO_MAX_AGE_DAYS)).strftime("%Y-%m-%d")
    todo = [t for t in tickers if not (t in have and have[t]["asof"] >= fresh_cut)][:max_new]
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    n = 0
    for t in todo:
        try:
            info = yf.Ticker(t).get_info() or {}
            have[t] = {"info": {k: info.get(k) for k in INFO_FIELDS if info.get(k) is not None},
                       "asof": today}
            n += 1
            time.sleep(0.05)
        except Exception as e:  # noqa: BLE001 — one name down can't break the batch
            log.debug("canada fundamentals %s failed: %s", t, e)
    if n:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        rows = [{"ticker": t, "payload": json.dumps(v["info"]), "asof": v["asof"]}
                for t, v in have.items()]
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
        rec_out = {
            "description": {"summary": info.get("longBusinessSummary"),
                            "sector": info.get("sector"), "industry": info.get("industry")},
            "valuation": val,
            "archetype": arch,
            "archetype_label": ARCHETYPES.get(arch, ARCHETYPES["mixed"])[0],
            "archetype_label_zh": ARCHETYPES.get(arch, ARCHETYPES["mixed"])[1],
        }
        cons = _consensus(info)
        if cons:
            rec_out["consensus"] = cons
        pos = _positioning(info)
        if pos:
            rec_out["positioning"] = pos
        out[t] = rec_out
    return out


# ---------------------------------------------------------------- earnings (yfinance)

EARN_CACHE = config.data_dir() / "canada_earnings" / "earnings.parquet"
EARN_MAX_AGE_DAYS = 10


def _earnings_one(yf, ticker: str) -> dict | None:
    """Next scheduled earnings date + the last ~4 reported surprises for one name, via
    yfinance get_earnings_dates (the free US-parity feed for .TO). None on miss."""
    try:
        df = yf.Ticker(ticker).get_earnings_dates(limit=10)
    except Exception:  # noqa: BLE001
        return None
    if df is None or df.empty:
        return None
    today = pd.Timestamp.now().normalize()
    next_date, surprises = None, []
    for dt, row in df.sort_index().iterrows():
        d = dt.tz_localize(None) if getattr(dt, "tz", None) is not None else dt
        ds = d.strftime("%Y-%m-%d")
        rep, est, sp = _num(row.get("Reported EPS")), _num(row.get("EPS Estimate")), _num(row.get("Surprise(%)"))
        if d.normalize() > today:
            if next_date is None or ds < next_date:
                next_date = ds
        elif rep is not None:
            surprises.append({"date": ds, "eps": round(rep, 2),
                              "est": round(est, 2) if est is not None else None,
                              "surprise_pct": round(sp, 1) if sp is not None else None})
    surprises = surprises[-4:][::-1]            # most recent first, last 4
    if next_date is None and not surprises:
        return None
    return {"next_date": next_date, "surprises": surprises}


def fetch_earnings(tickers: list[str], max_new: int = 40) -> int:
    """Drip yfinance get_earnings_dates into data/canada_earnings/, capped + freshness-
    cached like fetch_info. Best-effort; returns how many names were (re)fetched."""
    import yfinance as yf

    have: dict[str, dict] = {}
    if EARN_CACHE.exists():
        try:
            df = pd.read_parquet(EARN_CACHE)
            has_asof = "asof" in df.columns
            for _, r in df.iterrows():
                asof = str(r["asof"]) if has_asof and pd.notna(r["asof"]) else ""
                have[r["ticker"]] = {"payload": r["payload"], "asof": asof}
        except Exception as e:  # noqa: BLE001
            log.warning("canada earnings cache read failed: %s", e)
    fresh_cut = (pd.Timestamp.now() - pd.Timedelta(days=EARN_MAX_AGE_DAYS)).strftime("%Y-%m-%d")
    todo = [t for t in tickers if t.endswith(".TO")
            and not (t in have and have[t]["asof"] >= fresh_cut)][:max_new]
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    n = 0
    for t in todo:
        rec = _earnings_one(yf, t)
        if rec is not None:
            have[t] = {"payload": json.dumps(rec, default=str), "asof": today}
            n += 1
        time.sleep(0.05)
    if n:
        EARN_CACHE.parent.mkdir(parents=True, exist_ok=True)
        rows = [{"ticker": t, "payload": v["payload"], "asof": v["asof"]}
                for t, v in have.items()]
        pd.DataFrame(rows).to_parquet(EARN_CACHE)
    return n


def earnings_map() -> dict[str, dict]:
    """{ticker: {next_date, surprises}} from the earnings cache. Empty if absent."""
    if not EARN_CACHE.exists():
        return {}
    try:
        df = pd.read_parquet(EARN_CACHE)
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, dict] = {}
    for _, r in df.iterrows():
        try:
            out[str(r["ticker"])] = json.loads(r["payload"])
        except Exception:  # noqa: BLE001
            continue
    return out
