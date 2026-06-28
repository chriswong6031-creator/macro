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
from engine import confluence_tiers   # owner's weighted T1->T4 cascade (TIERED_CASCADE.md)

TAKE = "take"
ANTICIPATION = "anticipation"
_BUY_TYPES = ("buy", "rebuy")

# tier sort order: take above every anticipation; within anticipation, a fired-but-pending
# buy ranks above the pre-cross early warning (it is "more formed"). 0 = best.
_TIER_ORDER = {(TAKE, None): 0, (ANTICIPATION, "pending"): 1, (ANTICIPATION, "early"): 2}
# owner's weighted cascade rank (held-out justified, TIERED_CASCADE.md): T1 master .. T4 earliest.
# pending (3D master forming) sits at 1, between the held take (T1=0) and the 2D-early tiers.
_CASCADE_RANK = {"T1": 0, "T2": 2, "T3": 3, "T4": 4}
# board ranking = convex blend of cascade tier (TIER_FRAC) + conviction percentile (1-TIER_FRAC).
# Conviction-led (<0.5) so strong EARLIER tiers surface on a take-heavy board; tier is a real
# boost (a master beats an equal-conviction earlier tier). See signal_gate.blend_sorted.
TIER_FRAC = 0.45

_VERDICT_KEYS = ("eligible", "tier", "sub", "reason", "state", "above200",
                 "weekly_bull", "early_now", "asof", "last",
                 "tier_cascade", "weight", "tier_sub", "bars_to_cross")


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
    # ---- owner's WEIGHTED tier cascade (T1 master -> T4 earliest), TIERED_CASCADE.md ----
    # Extends the take/pending/early leaf: T1 = the validated master (TAKE, or a forming
    # 'pending' master), T2/T3/T4 = the 2D-MACD-cross / 2D-projected / 2D-projected+2D-stoch
    # tiers computed close-only here. A T2/T4 name with no take/early still becomes eligible.
    take_active = (v.get("tier") == TAKE)
    casc = confluence_tiers.cascade(daily_close, take_active=take_active)
    tier_c = casc.get("tier")
    if not tier_c and v.get("sub") == "pending":
        tier_c = "T1"                         # 3D master forming counts as the T1 tier
    v["tier_cascade"] = tier_c
    v["weight"] = confluence_tiers.WEIGHTS.get(tier_c, 0.0)
    v["tier_sub"] = casc.get("sub")           # deep|shallow (display modifier; equal weight)
    v["bars_to_cross"] = casc.get("bars_to_cross")
    if tier_c and not v.get("eligible"):      # T2/T4 extend eligibility beyond take/early
        v.update(eligible=True, reason=f"tier {tier_c} (weight {v['weight']})")
    v["result"] = res
    return v


def tier_rank(v: dict | None) -> int:
    """Ascending sort rank (0 = best). Owner's cascade orders the board: held take (T1)=0,
    forming master (pending)=1, then T2=2 / T3=3 / T4=4. Non-eligible sinks to the bottom."""
    if not v or not v.get("eligible"):
        return 9
    tc = v.get("tier_cascade")
    if tc == "T1" and v.get("sub") == "pending":
        return 1                              # forming master ranks just below a held take
    if tc:
        return _CASCADE_RANK.get(tc, 8)
    return _TIER_ORDER.get((v.get("tier"), v.get("sub")), 8)


def blend_sorted(items: list, base_of, verdict_of, reverse: bool = True) -> list:
    """Order `items` by the owner's WEIGHTED cascade blend (best first by default).

    Strict tier-first buries the earlier tiers whenever confirmed masters outnumber the board
    cap (US/CN). The owner asked for a WEIGHTED blend instead: a name's board score is its
    base-score PERCENTILE within the pool, lifted by 0.5 and SCALED by the cascade weight
    (T1 1.0 .. T4 0.4) -- so masters still dominate, but a strong-conviction T2/T3 outranks a
    weak master and surfaces. Percentile-based ⇒ robust to the per-market base scale
    (US/HK composite_z, CN/CA alpha/setup). `base_of(x)`->market rank score; `verdict_of(x)`->
    the signal_gate verdict (for .weight). Ineligible / weightless names sink (score 0).
    See research/signal_engine/TIERED_CASCADE.md."""
    import bisect
    vals = sorted((base_of(x) or 0.0) for x in items)
    n = len(vals) or 1

    def _score(x):
        w = (verdict_of(x) or {}).get("weight") or 0.0
        if not w:
            return -1.0
        wn = max(0.0, min(1.0, (w - 0.4) / 0.6))                 # T1->1.0 .. T4->0.0
        pct = bisect.bisect_right(vals, base_of(x) or 0.0) / n   # conviction percentile in pool
        return TIER_FRAC * wn + (1.0 - TIER_FRAC) * pct          # convex blend (conviction-led)

    return sorted(items, key=_score, reverse=reverse)


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
