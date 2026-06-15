"""Additive A-share context blocks for the single-stock analyzer (china_lookup.html).

The China parallel of the extra panels engine/stock_fundamentals.py bakes for the US
page. Each function reads one collector's compact cache and returns {ticker: block};
a missing cache just yields {} so the page hides that panel. All DISPLAY-ONLY context —
none of these is a validated A-share selection edge (research/CHINA_HK_STOCK_SIGNALS.md):

  analyst_consensus   collectors/china_analyst        -> coverage + buy/hold/sell + fwd EPS/PE
  earnings_calendar   collectors/china_earnings       -> next / last disclosure date
  valuation_percentile collectors/china_valuation     -> P/E·P/B own-history band percentile
  margin_positioning  collectors/china_margin_detail  -> financing-balance trend + % of cap
"""
from __future__ import annotations

import json
import logging

import pandas as pd

from lib import config

log = logging.getLogger("china_extras")


def _num(v):
    try:
        if v in (None, "", "--", "—"):
            return None
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _read_payload(path) -> dict[str, dict]:
    """{ticker: parsed-payload} for the {ticker, payload(json)} cache shape. Empty on miss."""
    if not path.exists():
        return {}
    try:
        df = pd.read_parquet(path)
    except Exception as e:  # noqa: BLE001
        log.warning("china_extras: %s unreadable (%s)", path.name, e)
        return {}
    out: dict[str, dict] = {}
    for _, r in df.iterrows():
        try:
            out[str(r["ticker"])] = json.loads(r["payload"])
        except Exception:  # noqa: BLE001
            continue
    return out


# ---- analyst consensus ------------------------------------------------------
_RATINGS = [(0.40, "Buy", "买入"), (0.15, "Accumulate", "增持"),
            (-0.15, "Hold", "中性"), (-1.01, "Reduce", "减持")]


def _rating(buy: int, hold: int, sell: int) -> tuple[str, str, float] | None:
    total = buy + hold + sell
    if total <= 0:
        return None
    net = (buy - sell) / total
    for thr, en, zh in _RATINGS:
        if net >= thr:
            return en, zh, round(net, 2)
    return "Reduce", "减持", round(net, 2)


def analyst_consensus(price_by: dict[str, float] | None = None) -> dict[str, dict]:
    """Per-name sell-side picture: coverage count, buy/hold/sell mix (买入+增持 / 中性 /
    减持+卖出), a consensus rating, the current+next forward EPS, and — with the live
    price — a forward P/E. Forward P/E is the actionable cell; ratings are opinion."""
    price_by = price_by or {}
    raw = _read_payload(config.data_dir() / "china_analyst" / "forecast.parquet")
    cur_year = pd.Timestamp.now().year
    out: dict[str, dict] = {}
    for t, p in raw.items():
        buy = int(p.get("buy", 0)) + int(p.get("overweight", 0))
        hold = int(p.get("neutral", 0))
        sell = int(p.get("underweight", 0)) + int(p.get("sell", 0))
        reports = int(p.get("reports", 0))
        rat = _rating(buy, hold, sell)
        # forward EPS: first forecast year >= current year as FY1, the next as FY2
        eps = {int(y): _num(v) for y, v in (p.get("eps") or {}).items() if _num(v) is not None}
        years = sorted(y for y in eps if y >= cur_year) or sorted(eps)
        fy1 = years[0] if years else None
        fy2 = next((y for y in years if y > fy1), None) if fy1 else None
        price = _num(price_by.get(t))
        block: dict = {"reports": reports, "buy": buy, "hold": hold, "sell": sell}
        if rat:
            block.update(rating=rat[0], rating_zh=rat[1], net=rat[2])
        if fy1 and eps.get(fy1) is not None:
            block["eps_fy1"], block["fy1"] = round(eps[fy1], 2), fy1
            if price and eps[fy1] > 0:
                block["fwd_pe_fy1"] = round(price / eps[fy1], 1)
        if fy2 and eps.get(fy2) is not None:
            block["eps_fy2"], block["fy2"] = round(eps[fy2], 2), fy2
            if price and eps[fy2] > 0:
                block["fwd_pe_fy2"] = round(price / eps[fy2], 1)
        # only surface a name with at least coverage OR a forward estimate
        if reports > 0 or "eps_fy1" in block:
            out[t] = block
    return out


# ---- earnings / disclosure calendar -----------------------------------------
def earnings_calendar() -> dict[str, dict]:
    """Per-name next upcoming disclosure date (None off-season) + most recent actual
    disclosure. The page computes the days-to-disclosure countdown client-side."""
    p = config.data_dir() / "china_earnings" / "calendar.parquet"
    if not p.exists():
        return {}
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("china_extras: earnings unreadable (%s)", e)
        return {}
    out: dict[str, dict] = {}
    for _, r in df.iterrows():
        nd = r.get("next_date")
        ld = r.get("last_date")
        nd = nd if isinstance(nd, str) and nd else None
        ld = ld if isinstance(ld, str) and ld else None
        if not nd and not ld:
            continue
        out[str(r["ticker"])] = {"next_date": nd, "last_date": ld}
    return out


# ---- own-history valuation percentile ---------------------------------------
def valuation_percentile() -> dict[str, dict]:
    """Per-name current P/E·P/B·P/S and their percentile within the stock's own
    trailing-5y band (lower = cheaper vs its own history)."""
    return _read_payload(config.data_dir() / "china_valuation" / "percentiles.parquet")


# ---- per-stock margin financing positioning ---------------------------------
def margin_positioning(mktcap_by: dict[str, float] | None = None) -> dict[str, dict]:
    """Per-name financing balance (亿), its ~20-trading-day change %, and financing as a
    share of market cap (mktcap in 亿). A crowding/leverage backdrop, not a signal."""
    mktcap_by = mktcap_by or {}
    p = config.data_dir() / "china_margin_detail" / "detail.parquet"
    if not p.exists():
        return {}
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("china_extras: margin unreadable (%s)", e)
        return {}
    out: dict[str, dict] = {}
    for _, r in df.iterrows():
        fb = _num(r.get("fin_balance"))
        if fb is None:
            continue
        t = str(r["ticker"])
        prior = _num(r.get("fin_balance_prior"))
        block: dict = {"fin_balance_yi": round(fb / 1e8, 1), "date": r.get("date")}
        if prior and prior > 0:
            block["chg_pct"] = round((fb / prior - 1) * 100, 1)
        mc_yi = _num(mktcap_by.get(t))
        if mc_yi and mc_yi > 0:
            block["pct_mcap"] = round(fb / 1e8 / mc_yi * 100, 1)
        out[t] = block
    return out
