"""Validated-confluence BUY GATE for the per-country Standout grids (US/CN/HK/CA/Intl).

Wraps :func:`engine.signal_quality.analyze` — the VALIDATED MACD-RSI x StochRSI confluence
buy-filter (reclaim-and-hold + bearish-div veto + 200MA bar-raiser; cut avg max drawdown
-23.7% -> -15.5% across 110 held-out US names; CHARTER.md §2/§5) — and turns its §7 marker
stream into a single grid ELIGIBILITY verdict so every country's "Standout Top Stocks" board
gates on the SAME validated signal that the chart renders.

This REPLACES the per-grid ad-hoc screens (the US standard-MACD(12,26,9)+StochRSI `cycles`
ladder; the non-US alpha-only floors) as the PRIMARY buy-entry gate. It is a DISPLAY-ONLY
entry-QUALITY / RISK gate, NOT alpha and NOT an auto-trade trigger (CHARTER §2).

Tiers (ranked; take is always above every anticipation — CHARTER §2/§7):

  TIER take          currently holding a buy-filter-ENDORSED entry: the last §7 marker is a
                     buy/rebuy with quality 'take' and no sell/cut has fired since. This is
                     the validated primary buy signal.
  TIER anticipation  imminently forming but NOT yet endorsed — surfaced as an *eligibility
                     exception*, never as a stronger buy than a take:
                       sub 'pending' = the confluence buy fired on the last 1-2 bars but its
                                       forward reclaim-and-hold confirmation isn't in yet
                                       (resolves to take/block next build; §7 'pending').
                       sub 'early'   = the validated 2D-MACD pre-cross advance-warning
                                       (early_now / m2d_s3d_early). Acting on it early is
                                       empirically WORSE entry quality (CONFLUENCE_TUNING.md
                                       §3), so it only makes a name ELIGIBLE to surface — it
                                       is never a take and never fed to conviction/auto-trade.
  not eligible       blocked buy, flat (last marker is a sell/cut), no buy signal, or
                     insufficient history (analyze() returned None -> graceful skip).

signal_quality is CLOSE-ONLY by construction (it stochs the RSI of close; it never needs
high/low), so this gate runs on every market's close-only price store and self-degrades to
"insufficient history" on thin names instead of crashing.

Anticipation-form decision: research/signal_engine/tuning_anticipation.py compared the
in-engine from-OS `early` leg (a) against a from-above-OS + 2D-cross relaxation (b) as
SURFACERS of imminent base3d buys on the 110 held-out US names. (a) dominated (b) on recall
(38.5% vs 21.9% of TAKEs), precision (32% vs 20.5%) and lead (4.6d vs 2.2d), so the gate uses
(a) = `early_now`; (b) was NOT adopted (it added mostly false alarms). See GRID_GATE.md.
"""
from __future__ import annotations

import json
from pathlib import Path

from engine.signal_quality import analyze

TAKE = "take"
ANTICIPATION = "anticipation"
_BUY_TYPES = ("buy", "rebuy")

# tier sort order: take above every anticipation; within anticipation, a fired-but-pending
# buy ranks above the pre-cross early warning (it is "more formed"). 0 = best.
_TIER_ORDER = {(TAKE, None): 0, (ANTICIPATION, "pending"): 1, (ANTICIPATION, "early"): 2}

_VERDICT_KEYS = ("eligible", "tier", "sub", "reason", "state", "above200",
                 "weekly_bull", "early_now", "asof", "last")


def verdict(result: dict | None) -> dict:
    """Map an :func:`engine.signal_quality.analyze` result (or None) to a gate verdict."""
    v = {"eligible": False, "tier": None, "sub": None, "reason": "no signal",
         "state": None, "above200": None, "weekly_bull": None, "early_now": False,
         "asof": None, "last": None}
    if not result:
        v["reason"] = "insufficient history"
        return v
    markers = result.get("markers") or []
    last = markers[-1] if markers else None
    early = bool(result.get("early_now"))
    v.update(state=result.get("state"), above200=result.get("above200"),
             weekly_bull=result.get("weekly_bull"), early_now=early,
             asof=result.get("asof"), last=last)
    if last and last.get("type") in _BUY_TYPES:
        q = last.get("quality")
        if q == "take":
            v.update(eligible=True, tier=TAKE,
                     reason=last.get("reason") or "held buy-filter confirmation")
            return v
        if q == "pending":
            v.update(eligible=True, tier=ANTICIPATION, sub="pending",
                     reason="buy fired; forward confirmation pending")
            return v
        # a blocked buy: only a live early advance-warning can still surface it
        if early:
            v.update(eligible=True, tier=ANTICIPATION, sub="early",
                     reason="early advance-warning (last buy was filtered out)")
            return v
        v.update(reason="buy blocked by filter: " + (last.get("reason") or "").strip())
        return v
    # flat: last marker is a sell/cut, or there are no markers yet
    if early:
        v.update(eligible=True, tier=ANTICIPATION, sub="early",
                 reason="early advance-warning (no open buy)")
        return v
    v.update(reason="flat: " + (last.get("type") if last else "no buy signal"))
    return v


def gate(ticker: str, daily_close) -> dict:
    """analyze() the close series, then return the verdict PLUS the raw analyze() result
    (the §7 site/signals/<T>.json payload) under "result". Never raises on thin/bad data."""
    try:
        res = analyze(ticker, daily_close)
    except Exception:
        res = None
    v = verdict(res)
    v["result"] = res
    return v


def tier_rank(v: dict | None) -> int:
    """Ascending sort rank (0 = best take). Non-eligible / missing sinks to the bottom."""
    if not v or not v.get("eligible"):
        return 9
    return _TIER_ORDER.get((v.get("tier"), v.get("sub")), 8)


def compact(v: dict | None) -> dict:
    """The display-safe verdict subset to attach to a grid card row (drops "result")."""
    if not v:
        return {"eligible": False, "tier": None, "sub": None, "reason": "no signal"}
    return {k: v.get(k) for k in _VERDICT_KEYS}


def write_signal_file(out_dir, ticker: str, result: dict | None) -> bool:
    """Write the §7 site/signals/<T>.json marker file (the chart contract). Returns True
    if written; skips None (thin history). Same shape/asof as analyze() so the chart and
    the grid gate are guaranteed consistent."""
    if not result:
        return False
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{ticker}.json").write_text(json.dumps(result, separators=(",", ":")))
    return True
