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

import pandas as pd

from engine.signal_quality import analyze
from engine import confluence_tiers   # owner's weighted T1->T4 cascade (TIERED_CASCADE.md)

TAKE = "take"
ANTICIPATION = "anticipation"
_BUY_TYPES = ("buy", "rebuy")

# tier sort order: take above every anticipation; within anticipation, a fired-but-pending
# buy ranks above the pre-cross early warning (it is "more formed"). 0 = best.
_TIER_ORDER = {(TAKE, None): 0, (ANTICIPATION, "pending"): 1, (ANTICIPATION, "early"): 2}
# operator-ratified 2026-07-06: T2 now scores above T1 for entry quality (fills closer to
# trough, confirmed-bar with low repaint). T2=0 (best), T1-held=1, T1-pending=2, T3=3, T4=4.
# pending (3D master forming) sits at 2, just below the held T1 and the T2 cross.
_CASCADE_RANK = {"T1": 1, "T2": 0, "T3": 3, "T4": 4}
# board ranking = convex blend of cascade tier (TIER_FRAC) + conviction percentile (1-TIER_FRAC).
# Conviction-led (<0.5) so strong EARLIER tiers surface on a take-heavy board; tier is a real
# boost (a master beats an equal-conviction earlier tier). See signal_gate.blend_sorted.
TIER_FRAC = 0.45

# The tiers that constitute a FRESH, ACTIONABLE confluence BUY for the "what to buy now"
# boards (the Top-setups strip on us_stocks.html + the discovery "Buy-zone" picks). This is
# the owner's explicit spec — a name is only a recommendation if EITHER:
#   * it has triggered the MACD-2D x StochRSI-3D confluence — the 2D RSI-MACD has JUST crossed
#     (its arrow is <= FRESH_TICKS 2D-ticks old, the "just-crossed" trigger) while the 3D
#     StochRSI has crossed RECENTLY (within the confluence window CONF_W) and is still
#     constructive / not-topped (T2); or the validated 3D master take is itself just-crossed
#     and not-topped (T1, the stronger superset). NOTE the asymmetry is intentional and matches
#     the validated engine (confluence_tiers TIERED_CASCADE.md): the StochRSI sets up the zone
#     (it need not be same-bar), the 2D MACD cross is the freshness-gated trigger; the
#     not-topped veto kills a stale/overbought setup regardless of when the StochRSI crossed; OR
#   * the 3D StochRSI has ALREADY crossed and the 2D RSI-MACD is about to cross in the next
#     1-2 ticks (T3, the anticipation tier).
# T4 is DELIBERATELY EXCLUDED: it fires off the *2D* StochRSI (not the 3D), so it does not meet
# the "StochRSI 3D crossover" requirement and is the earliest / weakest anti-falling-knife tier.
BUYABLE_TIERS = ("T1", "T2", "T3")


def is_buyable(v: dict | None) -> bool:
    """True iff a gate verdict (full or :func:`compact`) is a fresh, actionable confluence buy
    per BUYABLE_TIERS — a just-crossed confirmed cross (T1/T2) or the StochRSI-3D-crossed /
    MACD-2D-about-to-cross anticipation (T3). The topped / stale / early-only paths in
    :func:`gate` clear ``tier_cascade`` to None, so a HOLD or a downtrend never reads buyable."""
    if not v or not v.get("eligible"):
        return False
    return v.get("tier_cascade") in BUYABLE_TIERS


_VERDICT_KEYS = ("eligible", "tier", "sub", "reason", "state", "above200",
                 "weekly_bull", "early_now", "asof", "last",
                 "tier_cascade", "weight", "tier_sub", "bars_to_cross", "fresh_bars", "ticks",
                 "provisional", "htf_s1", "htf_s2")


def _bars_since(daily_close, marker) -> int | None:
    """Trading bars between a §7 buy marker's date and the latest close bar (None if unknown).
    Used to age a held 'take': a buy that fired weeks ago is no longer a FRESH entry."""
    if not marker or not marker.get("date"):
        return None
    try:
        idx = pd.to_datetime(pd.Index(getattr(daily_close, "index", [])))
        if len(idx) == 0:
            return None
        return int((idx > pd.Timestamp(marker["date"])).sum())
    except Exception:
        return None


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
    last_m = v.get("last")
    is_buy = bool(last_m and last_m.get("type") in _BUY_TYPES)   # take OR forming 'pending'
    take_date = last_m.get("date") if is_buy else None           # age the arrow by its OWN date
    v["fresh_bars"] = _bars_since(daily_close, last_m) if is_buy else None
    casc = confluence_tiers.cascade(daily_close, take_active=take_active,
                                    take_date=take_date)
    topped = not casc.get("not_topped", True)
    tier_c = casc.get("tier")
    ticks = casc.get("ticks")
    v["ticks"] = ticks                                   # native-TF ticks since the cross/arrow
    fresh = (ticks is None) or (ticks <= confluence_tiers.FRESH_TICKS)   # just-crossed window
    # FRESHNESS + NOT-TOPPED gate (the AMAT / HON-after-10-days fix). A held 'take' makes the
    # name eligible in verdict() the whole time it is long (until a sell fires) -- but for a BUY
    # board that surfaces names that crossed several ticks ago and have been rising. cascade()
    # blesses the take as T1 ONLY while its arrow is JUST-crossed (<= FRESH_TICKS ticks old on the
    # 3D grid; 1 tick = 3 days, so 2 ticks ~= 6 days) AND momentum is still constructive. Otherwise
    # the name drops: it is a HOLD, not one of the "about to cross" / "just crossed" board buys.
    if take_active and tier_c != "T1":
        why = "topped/rolled-over" if topped else "risen for many days (cross 2+ ticks ago)"
        v.update(eligible=False, tier=None, reason=f"held but {why} — no longer a fresh entry")
        # W0.2 Stage C near-miss annotation (Appendix A): stamped ONLY when the name
        # failed EXACTLY ONE condition — topped AND stale together is two failures,
        # which is a plain rejection, not a near-miss.
        if topped and not fresh:
            pass
        elif topped:
            v["near_miss_reason"] = "not_topped_veto"
        else:
            v["near_miss_reason"] = "freshness_expired"
    # A forming 'pending' master counts as T1, but only while it is JUST-fired (<= FRESH_TICKS)
    # and not already topping -- otherwise it too is stale and drops off the board.
    if tier_c is None and v.get("sub") == "pending":
        if not topped and fresh:
            tier_c = "T1"
        else:
            why = "already topping" if topped else "risen for many days"
            v.update(eligible=False, tier=None, reason=f"forming master {why} — not a fresh entry")
            # W0.2 Stage C: same exactly-one near-miss rule as the held-take branch.
            if topped and not fresh:
                pass
            elif topped:
                v["near_miss_reason"] = "not_topped_veto"
            else:
                v["near_miss_reason"] = "freshness_expired"
    v["tier_cascade"] = tier_c
    v["weight"] = confluence_tiers.WEIGHTS.get(tier_c, 0.0)
    v["tier_sub"] = casc.get("sub")           # deep|shallow (display modifier; equal weight)
    v["bars_to_cross"] = casc.get("bars_to_cross")
    # PROVISIONAL-basis flag (W6 #22): a T3 grade is projected off the incomplete 2D resample
    # tail and repaints at a measured 23.8% US / 15.1% CN of fresh fires — above the ~15% flip
    # criterion (T1/T2 measured 5.3%/8.8%, fine). Boards badge it so the trader knows the tier
    # may vanish when the bucket completes (calibration/provisional_replay.json).
    v["provisional"] = bool(casc.get("provisional")) and tier_c == "T3"
    # HTF super-tier (S1/S2): display-only, rank-neutral, 2026-07-06.
    # Sourced from cascade() htf dict; defaults to False when absent (thin history / exception).
    _htf = casc.get("htf") or {}
    v["htf_s1"] = bool(_htf.get("s1", False))
    v["htf_s2"] = bool(_htf.get("s2", False))
    if tier_c and not v.get("eligible"):      # T2/T4 (or a fresh re-trigger) extend eligibility
        v.update(eligible=True, reason=f"tier {tier_c} (weight {v['weight']})")
    v["result"] = res
    return v


def tier_rank(v: dict | None) -> int:
    """Ascending sort rank (0 = best). Operator-ratified 2026-07-06 order: T2 confirmed
    cross=0, T1 held take=1, T1 forming master (pending)=2, T3=3, T4=4. Non-eligible sinks."""
    if not v or not v.get("eligible"):
        return 9
    tc = v.get("tier_cascade")
    if tc == "T1" and v.get("sub") == "pending":
        return 2                              # forming master ranks just below T1 held and T2
    if tc:
        return _CASCADE_RANK.get(tc, 8)
    return _TIER_ORDER.get((v.get("tier"), v.get("sub")), 8)


def blend_sorted(items: list, base_of, verdict_of, reverse: bool = True, bonus_of=None,
                 *, tier_frac: float | None = None, wn_floor: float = 0.0) -> list:
    """Order `items` by the owner's WEIGHTED cascade blend (best first by default).

    Strict tier-first buries the earlier tiers whenever confirmed masters outnumber the board
    cap (US/CN). The owner asked for a WEIGHTED blend instead: a name's board score is its
    base-score PERCENTILE within the pool, lifted by 0.5 and SCALED by the cascade weight
    (T1 1.0 .. T4 0.4) -- so masters still dominate, but a strong-conviction T2/T3 outranks a
    weak master and surfaces. Percentile-based ⇒ robust to the per-market base scale
    (US/HK composite_z, CN/CA alpha/setup). `base_of(x)`->market rank score; `verdict_of(x)`->
    the signal_gate verdict (for .weight). Ineligible / weightless names sink (score 0).

    `bonus_of(x)` (optional) -> an ADDITIVE per-row lift on the 0..1 blend scale (e.g. the China
    2W-StochRSI washout-reclaim bonus, or a NEGATIVE anti-chase extension penalty). It is added on
    top of the tier×conviction blend, so a bonus of ~one TIER_FRAC lifts a row by roughly a full
    tier WHILE the cascade tier still orders rows that share the same bonus. Default None = no lift.

    `tier_frac` overrides the module TIER_FRAC (how much the tier vs conviction drives the blend);
    `wn_floor` COMPRESSES the tier weight toward parity — the normalised tier weight wn (T1→1 ..
    T4→0) is remapped to [wn_floor, 1], so wn_floor=0.6 means T4 still gets 60% of T1's tier credit.
    Both default to the US behaviour (unchanged callers). CHINA passes a lower tier_frac + a wn_floor
    so a FRESH T2/T3 competes with a fresh — but often already-extended — T1 (medium-term A-share
    momentum is dead; a confirmed breakout is frequently already run). Anti-chase is handled
    ORTHOGONALLY by the extension penalty in bonus_of, NOT by inverting the tier.
    See research/signal_engine/TIERED_CASCADE.md."""
    import bisect
    tf = TIER_FRAC if tier_frac is None else tier_frac
    wf = max(0.0, min(1.0, wn_floor))
    vals = sorted((base_of(x) or 0.0) for x in items)
    n = len(vals) or 1

    def _score(x):
        b = (bonus_of(x) if bonus_of else 0.0) or 0.0           # optional additive lift/penalty
        w = (verdict_of(x) or {}).get("weight") or 0.0
        if not w:
            return -1.0 + b
        wn = max(0.0, min(1.0, (w - 0.4) / 0.6))                 # T1->1.0 .. T4->0.0
        wn = wf + (1.0 - wf) * wn                                # compress toward parity (CN flatten)
        pct = bisect.bisect_right(vals, base_of(x) or 0.0) / n   # conviction percentile in pool
        return tf * wn + (1.0 - tf) * pct + b                    # convex blend + optional lift

    return sorted(items, key=_score, reverse=reverse)


def compact(v: dict | None) -> dict:
    """The display-safe verdict subset to attach to a grid card row (drops "result")."""
    if not v:
        return {"eligible": False, "tier": None, "sub": None, "reason": "no signal"}
    return {k: v.get(k) for k in _VERDICT_KEYS}


# the SLIM, fully JSON-safe verdict for the "what to buy" boards (Top-setups strip on
# us_stocks.html + the discovery Buy-zone picks). Unlike compact() it drops the §7 marker
# payload ("last"/"state"/...) — those can carry NaN, and the boards only need the tier +
# freshness — so it is safe to persist with allow_nan=False. is_buyable() reads from this.
_BUY_KEYS = ("eligible", "tier_cascade", "tier_sub", "ticks", "bars_to_cross", "provisional",
             "htf_s1", "htf_s2")


def buy_signal(v: dict | None) -> dict:
    """Slim, JSON-safe buy verdict: confluence tier + freshness + HTF badges, no markers."""
    if not v:
        return {"eligible": False, "tier_cascade": None, "htf_s1": False, "htf_s2": False}
    return {k: v.get(k) for k in _BUY_KEYS}


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
