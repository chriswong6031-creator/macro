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
    df = _read_table("china_margin_detail", "detail")     # latest-session slice of the PIT history
    if df is None or df.empty:
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


# ===========================================================================
# US-parity alt-data parsers (Stage 2) — one function per new collector cache.
# All DISPLAY/CONTEXT-ONLY; each returns {ticker: block} and degrades to {} on a
# missing/broken cache. Score fields are bounded reads, never a scored allocation.
# ===========================================================================
def _clip(x, lo=-1.0, hi=1.0):
    try:
        return max(lo, min(hi, float(x)))
    except (TypeError, ValueError):
        return 0.0


def _clip01(x):
    return _clip(x, 0.0, 1.0)


# append-only drip caches now hold a PIT HISTORY (multiple dates). Every legacy consumer here
# expects a single-day per-ticker snapshot, so slice to the newest date on read. Map group→date col.
_DRIP_DATE_COL = {"china_zt_pool": "date", "china_margin_detail": "date", "china_lhb": "asof"}


def _read_table(group: str, name: str) -> "pd.DataFrame | None":
    p = config.data_dir() / group / f"{name}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("china_extras: %s/%s unreadable (%s)", group, name, e)
        return None
    dc = _DRIP_DATE_COL.get(group)
    if dc and dc in (df.columns if df is not None else []):
        from collectors._drip import latest_snapshot
        return latest_snapshot(df, dc)                     # single-day snapshot from PIT history
    return df


def comment() -> dict[str, dict]:
    """千股千评 (collectors/china_comment): per-name retail attention, institutional
    participation, main-force cost gap, composite score + rank momentum."""
    df = _read_table("china_comment", "detail")
    if df is None or df.empty:
        return {}
    out: dict[str, dict] = {}
    for r in df.itertuples():
        t = str(getattr(r, "ticker", "") or "")
        if not t:
            continue
        attn = _num(getattr(r, "attention", None))
        instp = _num(getattr(r, "inst_participation", None))
        mcost = _num(getattr(r, "main_cost", None))
        price = _num(getattr(r, "price", None))
        score = _num(getattr(r, "score", None))
        rdelta = _num(getattr(r, "rank_delta", None)) or 0.0
        inst_vs_retail = _clip((instp - 50.0) / 50.0) if instp is not None else None
        mcg = ((price / mcost - 1.0) * 100.0) if (price and mcost and mcost > 0) else None
        cscore = 0.0
        if score is not None:
            cscore += 0.4 * _clip((score - 50.0) / 30.0)
        if inst_vs_retail is not None:
            cscore += 0.4 * inst_vs_retail
        cscore += 0.2 * (1 if rdelta > 0 else (-1 if rdelta < 0 else 0)) * _clip01(abs(rdelta) / 200.0)
        out[t] = {"attention": attn, "inst_participation": instp, "main_cost": mcost,
                  "price": price, "score": score, "rank_delta": rdelta,
                  "inst_vs_retail": None if inst_vs_retail is None else round(inst_vs_retail, 3),
                  "main_force_cost_gap": None if mcg is None else round(mcg, 1),
                  "comment_score": round(cscore, 3),
                  "main_force_below": bool(mcg is not None and mcg < 0)}
    return out


def comment_velocity() -> dict[str, float]:
    """Attention momentum from data/china_comment/attention_hist.parquet:
    (latest − trailing-avg)/trailing-avg per ticker. {} if no history."""
    df = _read_table("china_comment", "attention_hist")
    if df is None or df.empty or "ticker" not in df.columns:
        return {}
    out: dict[str, float] = {}
    try:
        for t, g in df.groupby("ticker"):
            g = g.sort_values("date")
            vals = pd.to_numeric(g["attention"], errors="coerce").dropna()
            if len(vals) < 3:
                continue
            latest = float(vals.iloc[-1])
            prior = float(vals.iloc[:-1].tail(10).mean())
            if prior and prior > 0:
                out[str(t)] = round((latest - prior) / prior, 3)
    except Exception as e:  # noqa: BLE001
        log.debug("comment_velocity failed (%s)", e)
    return out


def lhb() -> dict[str, dict]:
    """龙虎榜 (collectors/china_lhb): hot-money net buy + institutional-seat accumulation."""
    df = _read_table("china_lhb", "detail")
    if df is None or df.empty:
        return {}
    nb = pd.to_numeric(df.get("net_buy_yi"), errors="coerce").abs()
    p90 = float(nb.quantile(0.90)) if not nb.dropna().empty else 1.0
    p90 = p90 if p90 > 0 else 1.0
    import math
    out: dict[str, dict] = {}
    for r in df.itertuples():
        t = str(getattr(r, "ticker", "") or "")
        if not t:
            continue
        net = _num(getattr(r, "net_buy_yi", None)) or 0.0
        inb = _num(getattr(r, "inst_net_buy_yi", None)) or 0.0
        nbuy = int(_num(getattr(r, "n_inst_buy", None)) or 0)
        nsell = int(_num(getattr(r, "n_inst_sell", None)) or 0)
        hot = _clip(net / p90)
        inst_accum = _clip01(0.5 * _clip01((nbuy - nsell) / 4.0)
                             + 0.5 * _clip01(math.log1p(max(inb * 1e8, 0)) / math.log1p(3e8)))
        leading = bool(inb > 0 and nbuy >= 2)
        out[t] = {"net_buy_yi": round(net, 2), "inst_net_buy_yi": round(inb, 2),
                  "n_inst_buy": nbuy, "n_inst_sell": nsell,
                  "hotmoney_score": round(hot, 3), "inst_accum_score": round(inst_accum, 3),
                  "leading": leading, "tag": "机构吸筹" if leading else "游资"}
    return out


def block_trades() -> dict[str, dict]:
    """大宗交易 (collectors/china_block_trades): block premium(+)/discount(−) signed score."""
    df = _read_table("china_block_trades", "detail")
    if df is None or df.empty:
        return {}
    amt = pd.to_numeric(df.get("block_amt_yi"), errors="coerce")
    t66 = float(amt.quantile(0.66)) if not amt.dropna().empty else 0.0
    out: dict[str, dict] = {}
    for r in df.itertuples():
        t = str(getattr(r, "ticker", "") or "")
        if not t:
            continue
        prem = _num(getattr(r, "avg_premium_pct", None)) or 0.0
        a = _num(getattr(r, "block_amt_yi", None)) or 0.0
        score = _clip(prem / 8.0) if a >= t66 else 0.0
        out[t] = {"avg_premium_pct": round(prem, 2), "block_amt_yi": round(a, 2),
                  "block_score": round(score, 3),
                  "block_discount_unload": bool(prem < -5 and a >= t66)}
    return out


def fundflow() -> dict[str, dict]:
    """主力资金流向 (collectors/tushare_moneyflow, GATED): per-name main-force (超大单+大单) net
    inflow as a signed accumulate(+)/distribute(−) read. {} when the Tushare token is absent
    (the free push2 feed is unreachable from a non-CN IP, so there is no fallback — the leg is
    simply omitted, never read as 0). main_net / net_amount are 万元; flow_score is bounded [-1,1]
    on the net rate (the convergence re-ranks it cross-sectionally anyway)."""
    df = _read_table("tushare", "moneyflow")
    if df is None or df.empty:
        return {}
    out: dict[str, dict] = {}
    for r in df.itertuples():
        t = str(getattr(r, "ticker", "") or "")
        if not t:
            continue
        rate = _num(getattr(r, "main_net_rate", None))
        net = _num(getattr(r, "main_net", None))
        namt = _num(getattr(r, "net_amount", None))
        if rate is None and net is None:
            continue
        out[t] = {"main_net": None if net is None else round(net, 1),
                  "net_amount": None if namt is None else round(namt, 1),
                  "main_net_rate": None if rate is None else round(rate, 2),
                  "name": str(getattr(r, "name", "") or "") or t,
                  "flow_score": round(_clip((rate if rate is not None else 0.0) / 20.0), 3)}
    return out


def broker_gold(top_n: int = 24) -> list[dict]:
    """券商每月金股 (collectors/tushare_broker, GATED): the names most picked by sell-side desks
    this month, as a pick-count CONVICTION TALLY. [] when the Tushare token is absent. DISPLAY-ONLY
    — a discrete monthly pick list, not the ~97%-buy ratings; never scored into the convergence."""
    df = _read_table("tushare", "broker")
    if df is None or df.empty:
        return []
    out: list[dict] = []
    for r in df.itertuples():
        t = str(getattr(r, "ticker", "") or "")
        if not t:
            continue
        try:
            brokers = json.loads(getattr(r, "brokers", "[]") or "[]")
        except Exception:  # noqa: BLE001
            brokers = []
        out.append({"ticker": t, "name": str(getattr(r, "name", "") or "") or t,
                    "n_brokers": int(_num(getattr(r, "n_brokers", None)) or len(brokers)),
                    "brokers": brokers, "month": str(getattr(r, "month", "") or "")})
    out.sort(key=lambda x: x["n_brokers"], reverse=True)
    return out[:top_n]


def chips() -> dict[str, dict]:
    """筹码胜率 (collectors/tushare_chips, GATED): per-name holder cost-basis + win-rate. {} when the
    Tushare token is absent. DISPLAY-ONLY positioning context (registered pending in china_signal_lab)."""
    df = _read_table("tushare", "chips")
    if df is None or df.empty:
        return {}
    out: dict[str, dict] = {}
    for r in df.itertuples():
        t = str(getattr(r, "ticker", "") or "")
        if not t:
            continue
        wr = _num(getattr(r, "winner_rate", None))
        out[t] = {"winner_rate": None if wr is None else round(wr, 1),
                  "weight_avg": _num(getattr(r, "weight_avg", None)),
                  "cost_50pct": _num(getattr(r, "cost_50pct", None))}
    return out


# 业绩预告 type → bilingual label (for the display panel; never put these in a title= attr)
GUIDANCE_LABELS: dict[str, tuple[str, str]] = {
    "预增": ("Sharp rise", "预增"), "略增": ("Slight rise", "略增"),
    "扭亏": ("Turn to profit", "扭亏"), "续盈": ("Stays profitable", "续盈"),
    "预盈": ("Expected profit", "预盈"), "减亏": ("Loss narrowing", "减亏"),
    "预减": ("Sharp fall", "预减"), "略减": ("Slight fall", "略减"),
    "首亏": ("First loss", "首亏"), "续亏": ("Stays in loss", "续亏"),
    "预亏": ("Expected loss", "预亏"), "增亏": ("Loss widening", "增亏"),
}


def forecast_guidance(top_n: int = 16) -> dict:
    """业绩预告 (collectors/tushare_forecast, GATED): the strongest positive + negative earnings-guidance
    surprises (type direction × guided net-profit %-change). {} when the Tushare token is absent.
    DISPLAY-ONLY — validated as the `guidance` family in china_validation, never scored here."""
    df = _read_table("tushare", "forecast")
    if df is None or df.empty or "guidance_score" not in df.columns:
        return {}
    rows: list[dict] = []
    for r in df.itertuples():
        t = str(getattr(r, "ticker", "") or "")
        gs = _num(getattr(r, "guidance_score", None))
        if not t or gs is None:
            continue
        rows.append({"ticker": t, "type": str(getattr(r, "type", "") or ""),
                     "p_change_min": _num(getattr(r, "p_change_min", None)),
                     "p_change_max": _num(getattr(r, "p_change_max", None)),
                     "guidance_score": round(gs, 3), "ann_date": str(getattr(r, "ann_date", "") or "")})
    if not rows:
        return {}
    rows.sort(key=lambda x: x["guidance_score"], reverse=True)
    # sign-FILTER (not rank-slice) so the ▲Positive / ▼Negative columns can never cross-contaminate
    # when the scored universe is small (< 2·top_n); guidance_score is strictly signed (None for neutral).
    up = [r for r in rows if r["guidance_score"] > 0][:top_n]
    down = [r for r in rows if r["guidance_score"] < 0][-top_n:][::-1]
    return {"up": up, "down": down}


def zt_pool() -> dict[str, dict]:
    """涨停板 (collectors/china_zt_pool): limit-up momentum tier + seal quality + froth."""
    df = _read_table("china_zt_pool", "pool")
    if df is None or df.empty:
        return {}
    seal = pd.to_numeric(df.get("seal_fund_yi"), errors="coerce")
    p75 = float(seal.quantile(0.75)) if not seal.dropna().empty else 1.0
    p75 = p75 if p75 > 0 else 1.0
    out: dict[str, dict] = {}
    for r in df.itertuples():
        t = str(getattr(r, "ticker", "") or "")
        if not t:
            continue
        consec = int(_num(getattr(r, "consec_boards", None)) or 0)
        sf = _num(getattr(r, "seal_fund_yi", None)) or 0.0
        fails = int(_num(getattr(r, "failed_seals", None)) or 0)
        turn = _num(getattr(r, "turnover_pct", None)) or 0.0
        tier = "龙头" if consec >= 4 else ("连板" if consec >= 2 else "首板")
        out[t] = {"consec_boards": consec, "seal_fund_yi": round(sf, 2),
                  "failed_seals": fails, "turnover_pct": round(turn, 1),
                  "sector": str(getattr(r, "sector", "") or ""), "momentum_tier": tier,
                  "limitup_froth": bool(consec >= 2 or turn > 25),
                  "seal_quality": round(_clip01(sf / p75 - fails * 0.3), 3)}
    return out


def zt_sector_breadth() -> dict[str, dict]:
    """{sector: {n_zt, consec_max}} — limit-up breadth by sector (rotation thermometer)."""
    df = _read_table("china_zt_pool", "pool")
    if df is None or df.empty or "sector" not in df.columns:
        return {}
    out: dict[str, dict] = {}
    try:
        for sec, g in df.groupby("sector"):
            if not str(sec):
                continue
            out[str(sec)] = {"n_zt": int(len(g)),
                             "consec_max": int(pd.to_numeric(g["consec_boards"], errors="coerce").max())}
    except Exception as e:  # noqa: BLE001
        log.debug("zt_sector_breadth failed (%s)", e)
    return out


def buyback() -> dict[str, dict]:
    """回购 (collectors/china_buyback): corporate buyback conviction (in-progress, capped 0.40)."""
    df = _read_table("china_buyback", "buyback")
    if df is None or df.empty:
        return {}
    import math
    out: dict[str, dict] = {}
    for r in df.itertuples():
        t = str(getattr(r, "ticker", "") or "")
        if not t:
            continue
        pct = _num(getattr(r, "pct_shares", None)) or 0.0
        done = _num(getattr(r, "done_amt_yi", None)) or 0.0
        prog = str(getattr(r, "progress", "") or "")
        in_prog = ("实施" in prog) or ("完成" in prog)
        score = 0.0
        if in_prog:
            score = min(0.40, 0.6 * _clip01(pct / 3.0)
                        + 0.4 * _clip01(math.log1p(max(done * 1e8, 0)) / math.log1p(1e9)))
        out[t] = {"pct_shares": round(pct, 2), "done_amt_yi": round(done, 2),
                  "progress": prog, "in_progress": in_prog, "buyback_score": round(score, 3)}
    return out


def pledge() -> dict[str, dict]:
    """股权质押 (collectors/china_pledge): forced-liquidation tail risk (RISK leg only)."""
    df = _read_table("china_pledge", "pledge")
    if df is None or df.empty:
        return {}
    out: dict[str, dict] = {}
    for r in df.itertuples():
        t = str(getattr(r, "ticker", "") or "")
        if not t:
            continue
        ratio = _num(getattr(r, "pledge_ratio", None))
        if ratio is None:
            continue
        out[t] = {"pledge_ratio": round(ratio, 1), "sector": str(getattr(r, "sector", "") or ""),
                  "pledge_risk": round(_clip01((ratio - 30.0) / 40.0), 3),
                  "pledge_overhang": bool(ratio >= 50)}
    return out
