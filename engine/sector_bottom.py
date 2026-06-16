"""Sector Bottom Radar — the per-sector complement to the per-stock Bottom
Confidence score (``engine.cycles.bottom_confidence``) and the index-level
buyable-washout gate (``engine.dislocation``).

WHY IT EXISTS. The Sector Heat Board's RRG stages (``engine.playbook.stage_table``:
improving / lagging / leading / weakening) are a 200-day-smoothed *rotation* lens.
They confirm a turn weeks late and — by construction — never separate a durable
sector low from a falling knife: "improving" fires identically on a real bottom and
on a bear-market bounce that rolls over. This module gives each GICS sector the SAME
validated bottoming machinery the stock library already runs per name, plus the
macro veto that the index work already validated:

  * **bottom_confidence on the sector ETF price** — the durability / drawdown-tail
    score, walk-forward calibrated MONOTONE on 69k stock evals
    (``research/BOTTOM_CONFIDENCE.md``). A sector ETF is just another price series,
    so the score applies directly; ``scripts/sector_bottom_phase0.py`` confirms the
    separation transfers to the sector level.
  * **the washout knife-risk temper** — deep-below-200-day + still-falling = knife,
    eased once price reclaims the 10-day average (``engine.cycles.washout``).
  * **the index dislocation verdict as the macro CONDITIONER** — buyable washout vs
    stand-aside / knife regime (Fed-put master switch; Phase-0 hardened,
    ``research/DISLOCATION_VALIDATION.md``). Market-wide, so it conditions every
    sector: in a put-absent regime the same washout signals kept falling in
    2000 / 2008 / 2022.
  * **a LIVE member-breadth confirmer** — share of the sector's constituents washed
    out (below their 200-day) and *turning* (reclaiming the 10-day). DISPLAYED
    context only; never folded into the score (the breadth caches are ~1y deep so
    this leg cannot be deep-backtested — it is a confirmer, not a validated leg).

HONEST CEILING (carried onto the UI). You cannot call the exact sector low. The
headline is a RISK / DURABILITY read — high = the kind of sector selloff whose low
has historically held with a shallower drawdown, *especially* once the index macro
gate reads buyable. It is NOT a return forecast and NOT an alpha signal.

ADDITIVE / LEAF. Pure functions; nothing in the scoring path imports it. Missing or
thin inputs degrade to ``None`` / empty, never raise.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.cycles import _BC_STATES, analyze, washout
from engine.technicals import rsi

# Bottoming ladder states (re-exported from the validated score's own gate) plus
# the radar verdict vocabulary.
BOTTOMING = set(_BC_STATES)

# Member-breadth thresholds (live confirmer only — see module docstring).
_OVERSOLD_RSI = 30.0
_RECLAIM_MA = 10
_BELOW_MA = 200


def _last(s: pd.Series | None) -> float | None:
    if s is None:
        return None
    s = s.dropna()
    return float(s.iloc[-1]) if len(s) else None


def sector_read(close: pd.Series, high: pd.Series | None = None,
                vix_ctx: dict | None = None) -> dict:
    """The validated per-sector core read for one sector ETF price series.

    Runs the SAME ``engine.cycles.analyze`` the stock library runs per name and
    surfaces the bottoming-relevant fields: the ladder state, the sector
    ``bottom_confidence`` (only populated in a bottoming state), the washout
    knife read, and 200-day stretch. Pure (reads nothing)."""
    c = close.dropna()
    out = {"state": None, "bottom_confidence": None, "knife": 0.0,
           "knife_level": "none", "pct_below_200d": None, "above_200d": None}
    if len(c) < 300:
        return out
    res = analyze(c, high.reindex(c.index) if high is not None else None,
                  kind="equity", vix_ctx=vix_ctx)
    lad = res.get("ladder") or {}
    cyc = res.get("cycle") or {}
    out["state"] = lad.get("state")
    out["bottom_confidence"] = lad.get("bottom_confidence")
    # carry the per-timeframe breakdown + knife caution line if the score built one
    for k in ("bc_line", "bc_line_zh", "bc_grade", "bc_grade_zh",
              "bc_weekly", "bc_monthly", "bc_knife", "bc_knife_line",
              "bc_knife_line_zh", "bc_tip", "bc_tip_zh"):
        if k in lad:
            out[k] = lad[k]
    wo = washout(c, cyc, vix_ctx)
    if wo:
        out["knife"] = wo.get("knife", 0.0)
        out["knife_level"] = wo.get("level", "none")
        out["pct_below_200d"] = wo.get("pct_below_200d")
        out["reclaim"] = wo.get("reclaim")
    sma200 = float(c.iloc[-_BELOW_MA:].mean()) if len(c) >= _BELOW_MA else None
    if sma200:
        out["above_200d"] = bool(c.iloc[-1] > sma200)
    return out


def member_breadth(members: pd.DataFrame | None) -> dict | None:
    """LIVE washout breadth for one sector from its constituents' closes (a frame
    whose columns are member tickers). Returns the share of members below their
    200-day, oversold (RSI<30), and *turning* (washed out AND reclaiming the
    10-day average — the breadth analog of the per-name reclaim that flips a knife
    to a buyable washout). DISPLAY CONTEXT ONLY — the caller attaches it to the
    card and it never enters the score. ``None`` when too few members have history."""
    if members is None or members.empty:
        return None
    below = oversold = turning = washed = n = 0
    for t in members.columns:
        s = members[t].dropna()
        if len(s) < _BELOW_MA:
            continue
        n += 1
        price = float(s.iloc[-1])
        sma200 = float(s.iloc[-_BELOW_MA:].mean())
        ma10 = float(s.iloc[-_RECLAIM_MA:].mean())
        is_below = sma200 > 0 and price < sma200
        below += int(is_below)
        r = rsi(s)
        if r is not None and len(r.dropna()):
            oversold += int(float(r.dropna().iloc[-1]) < _OVERSOLD_RSI)
        if is_below:                       # washed-out members that are turning up
            washed += 1
            turning += int(price > ma10)   # reclaiming the 10-day = the turn
    if n < 5:
        return None
    return {
        "n": n,
        "below_200d_share": round(below / n, 3),
        "oversold_share": round(oversold / n, 3),
        # of the washed-out members, how many are reclaiming the 10-day (turning)
        "turning_share": round(turning / washed, 3) if washed else 0.0,
        "washed_out_share": round(washed / n, 3),
    }


def _verdict(read: dict, put_absent: bool) -> dict:
    """Categorical radar verdict from (bottom_confidence band × knife × macro gate).
    NOT a new scored number — a label over the validated legs. EN + 中文.

    * not in a bottoming state            -> ``trend`` (defer to the heat board)
    * deep washout, still falling          -> ``falling_knife``
    * bottoming + macro put ABSENT         -> ``knife_regime`` (2000/08/22 caveat)
    * bottoming, decent bc, put present     -> ``buyable_washout``
    * bottoming, low bc                     -> ``washout_forming``
    """
    state = read.get("state")
    bc = read.get("bottom_confidence")
    knife_level = read.get("knife_level", "none")
    if state not in BOTTOMING:
        return {"verdict": "trend", "label": "Not in a washout — rotation read only.",
                "label_zh": "未处于超卖错杀——仅参考轮动。"}
    if knife_level == "high":
        return {"verdict": "falling_knife",
                "label": "Deep washout, still falling — knife risk; wait for a 10-day reclaim.",
                "label_zh": "深度超卖且仍在下跌——接飞刀风险；等待收复10日均线。"}
    if put_absent:
        return {"verdict": "knife_regime",
                "label": ("Washout, but the Fed put is ABSENT (recession or inflation-locked) — "
                          "the 2000/2008/2022 setup where the same signals kept falling. Stand aside."),
                "label_zh": ("超卖，但美联储托底缺位（衰退或通胀锁死）——即2000/2008/2022年"
                             "同类信号持续下跌的格局。观望。")}
    if bc is not None and bc >= 40:
        return {"verdict": "buyable_washout",
                "label": ("Buyable-washout setup — a durable, lower-drawdown sector low is favored "
                          "(macro put intact). Confirm into stabilization; don't anticipate."),
                "label_zh": ("可买入错杀——倾向于持久、低回撤的板块低点（宏观托底仍在）。"
                             "确认企稳后再介入，勿抢跑。")}
    return {"verdict": "washout_forming",
            "label": "Washout forming, turn not yet confirmed — durability still low; wait for the hook.",
            "label_zh": "错杀形成中，转向尚未确认——持久性仍低；等待企稳信号。"}


def radar(reads: dict[str, dict], names: dict[str, str] | None = None,
          put_absent: bool = False, macro_headline: str | None = None,
          breadth: dict[str, dict] | None = None) -> dict:
    """Assemble the per-sector reads into a Sector Bottom Radar payload.

    ``reads``   : {ticker -> :func:`sector_read` output}
    ``names``   : {ticker -> display name} (engine.playbook.SECTOR_NAMES)
    ``put_absent``  : the index dislocation macro gate (True => knife regime;
                      ``engine.dislocation`` put_state == 'put-absent').
    ``breadth`` : optional {ticker -> :func:`member_breadth`} live confirmer.

    Rows are sorted by bottom_confidence desc (washed-out sectors with the most
    durable-looking lows first), bottoming sectors ahead of trend sectors. PURE."""
    names = names or {}
    breadth = breadth or {}
    rows = []
    for t, rd in reads.items():
        v = _verdict(rd, put_absent)
        row = {"ticker": t, "name": names.get(t, t), **rd, **v}
        if t in breadth and breadth[t]:
            row["breadth"] = breadth[t]
        rows.append(row)
    # bottoming first, then by bottom_confidence desc (None last)
    rows.sort(key=lambda r: (r["verdict"] != "trend",
                             r.get("bottom_confidence") if r.get("bottom_confidence") is not None else -1.0),
              reverse=True)
    washed = [r for r in rows if r["verdict"] in ("buyable_washout", "washout_forming",
                                                  "falling_knife", "knife_regime")]
    return {
        "put_absent": bool(put_absent),
        "macro_gate": "put-absent" if put_absent else "put-present",
        "macro_headline": macro_headline,
        "n_washed_out": len(washed),
        "sectors": rows,
        "evidence": ("Per-sector reading of the validated per-stock Bottom Confidence score "
                     "(monotone on 69k evals, research/BOTTOM_CONFIDENCE.md) + the washout "
                     "knife temper, conditioned by the Phase-0-hardened index Fed-put gate "
                     "(research/DISLOCATION_VALIDATION.md). Risk/durability, not a return forecast."),
    }
