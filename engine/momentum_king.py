"""engine/momentum_king.py — Momentum King board (MK-1, display-tier).

Synthesis orchestrator over SHIPPED, validated engines. It adds NOTHING to the
alpha math — it LAYERS the Phase-0-prescribed confirmation state machine on top
of the sector-neutral residual-momentum ranking that already ships:

    residual_alpha.compute_residual_alpha()   ← the alpha king: each name's return
        with BOTH its market AND its sector beta stripped (= excess vs sector AND
        index), ranked WITHIN sector, plus an extended/pullback/intact overlay.
    + canon.confluence_signals()               ← the onset gate: MACD/StochRSI 2-D
        confluence buy (CB) on the 3D grid + the multi-timeframe trend legs.
    + postcross()                              ← ignition freshness: ticks_since_cross.
    → per-sector unique-dominance STATE MACHINE with an honest abstain
      (LEADER_CANDIDATE / CONTESTED / NO_CLEAR_LEADER).
    → subordinate DISPLAY witnesses (net-inflow, options) that ANNOTATE only.

Doctrine (research/INTRADAY_LARGE_CAP_TECH_LEADER_PHASE0_RESULTS.md):
  * You cannot predict the single future winner — emit a STATE, not a pick.
  * Three labels stay separate. This module emits ONLY the current-leader
    classification; the remaining-session / tradeable labels live in the
    prospective shadow ledger (MK P3), never here.
  * Options + net-inflow are SUBORDINATE witnesses — they annotate / de-escalate;
    they never create or kill a candidate.
  * postcross ARMED has NO ranking power (W8-A-OOS failed) — never gate on it.
  * Short-term residual momentum is REVERSAL (residual_alpha docstring): "onset"
    = a FRESH confluence cross on a NOT-yet-extended leader, NOT the biggest
    recent move. Extended leaders are shown but are NOT candidates.
  * K-of-N boolean gating only — never a weighted composite.

Pure functions, zero I/O: the whole board is unit-testable from synthetic frames.
scripts/build_momentum_king.py wires the live loaders. This is CONTEXT, not sizing.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.canon import confluence_signals
from engine.postcross import postcross

log = logging.getLogger(__name__)

SCHEMA = "momentum_king.v1"

NOTE = (
    "Momentum King: sector-neutral residual-momentum LEADERS (alpha vs market AND "
    "sector) that are also at a FRESH multi-timeframe confluence cross and not yet "
    "extended — the onset of a leadership run, not its exhaustion. A confirmation "
    "state machine with an honest abstain; display context, never a sizing input."
)

# ── Prospective-preregistration SEEDS (frozen before the MK-P3 shadow ledger;
#    revised only by a written amendment, never fit to the sample) ─────────────
ALPHA_LEADER_MIN = 0.5      # sector-neutral residual-IR z to count as a leader
                            #   (matches residual_alpha._entry's own leader cut)
MIN_TREND_LEGS = 2          # K-of-N: multi-TF trend legs up (of w2/w/mo/above200)
FRESH_WITHIN = 3            # CB within this many 3D buckets → FRESH_INITIATION
EXTENDED_ATR = 2.0          # ext_atr beyond the pre-registered [-6,+2] entry screen
DOMINANCE_TAU = 0.5         # alpha-z margin of #1 over #2 to declare a unique leader


# ──────────────────────────────────────────────────────────────────────────────
# 1. Onset overlay — the fresh-cross / ignition read for one name
# ──────────────────────────────────────────────────────────────────────────────

def confluence_onset(close: pd.Series, *, fresh_within: int = FRESH_WITHIN,
                     extended_atr: float = EXTENDED_ATR,
                     atr_series: pd.Series | None = None) -> dict:
    """Read the MACD/StochRSI 2-D confluence + post-cross state for one name.

    Returns a JSON-able dict; every field is None when the series is too short
    (confluence_signals needs ~90 3D bars ≈ 270 daily bars). Never raises.
    """
    out = {"fresh_cross": None, "trend_legs": None, "ticks_since_cross": None,
           "species": None, "extended": None, "cb_recent": None,
           "cs_active": None, "based": None, "shaken": None, "ext_atr": None}
    try:
        conf = confluence_signals(close)
        if conf is None or conf.empty:
            return out
        last = conf.iloc[-1]
        tail = conf.tail(int(max(1, fresh_within)))
        cb_recent = bool(tail["CB"].any())
        cs_active = bool(last.get("CS", False))
        # K-of-N multi-timeframe trend legs (persistent states, not point events)
        legs = int(sum(bool(last.get(c, False))
                       for c in ("w2_bull", "w_bull", "mo_bull", "above200")))

        pc = postcross(close, atr_series)
        ticks = pc.get("ticks_since_cross")
        ext_atr = pc.get("ext_atr")
        extended = ext_atr is not None and float(ext_atr) > float(extended_atr)

        # FRESH_INITIATION: a confluence buy printed within `fresh_within` buckets
        # and the move is not already stretched past the entry screen.
        fresh = bool(cb_recent and not extended)
        species = ("FRESH_INITIATION" if fresh
                   else "ESTABLISHED_CONTINUATION" if legs >= MIN_TREND_LEGS
                   else None)

        out.update({"fresh_cross": fresh, "trend_legs": legs,
                    "ticks_since_cross": (int(ticks) if ticks is not None else None),
                    "species": species, "extended": bool(extended),
                    "cb_recent": cb_recent, "cs_active": cs_active,
                    "based": bool(pc.get("based")), "shaken": bool(pc.get("shaken")),
                    "ext_atr": (round(float(ext_atr), 3) if ext_atr is not None else None)})
    except Exception as e:  # noqa: BLE001 — fail-soft, display-tier
        log.warning("momentum_king.confluence_onset: %s", e)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# 2. Per-name classification — combine the alpha rank with the onset read
# ──────────────────────────────────────────────────────────────────────────────

def classify_name(res_rec: dict, onset: dict, *,
                  alpha_min: float = ALPHA_LEADER_MIN,
                  min_legs: int = MIN_TREND_LEGS) -> dict:
    """Fuse a residual_alpha per-name record with its onset read into a
    candidate verdict. K-of-N boolean gates — no weighted score.

    Eligibility (a LEADER-CANDIDATE-eligible name must pass ALL three):
      G1 alpha_leader  : sector-neutral residual-IR z ≥ alpha_min
      G2 confluence_bull: ≥ min_legs multi-TF trend legs up AND no active CS sell
      G3 not_extended  : not stretched past the entry screen and residual_alpha's
                         own entry overlay is not "extended"  (early ignition, not
                         the end of a run)
    """
    alpha = res_rec.get("alpha")
    entry = res_rec.get("entry")
    legs = onset.get("trend_legs")

    g1 = alpha is not None and float(alpha) >= float(alpha_min)
    g2 = (legs is not None and int(legs) >= int(min_legs)
          and not bool(onset.get("cs_active")))
    g3 = (not bool(onset.get("extended"))) and entry != "extended"

    reasons = []
    if not g1:
        reasons.append("alpha_below_leader")
    if not g2:
        reasons.append("weak_confluence" if not (legs and legs >= min_legs) else "active_sell")
    if not g3:
        reasons.append("extended")

    return {
        "ticker": res_rec.get("ticker"),
        "name": res_rec.get("name"),
        "sector": res_rec.get("sector"),
        "alpha": alpha,
        "sector_rank": res_rec.get("sector_rank"),
        "sector_n": res_rec.get("sector_n"),
        "residual_entry": entry,          # residual_alpha overlay (extended/pullback/intact)
        "rev_pctile": res_rec.get("rev_pctile"),
        "species": onset.get("species"),
        "trend_legs": legs,
        "fresh_cross": onset.get("fresh_cross"),
        "ticks_since_cross": onset.get("ticks_since_cross"),
        "extended": onset.get("extended"),
        "based": onset.get("based"),
        "eligible": bool(g1 and g2 and g3),
        "gates": {"alpha_leader": g1, "confluence_bull": g2, "not_extended": g3},
        "reasons": reasons,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 3. Per-sector state machine — the honest abstain
# ──────────────────────────────────────────────────────────────────────────────

def sector_state(members: list[dict], *, dominance_tau: float = DOMINANCE_TAU) -> dict:
    """Collapse a sector's classified members into one state.

      0 eligible                              → NO_CLEAR_LEADER
      1+ eligible AND #1 clears #2 by ≥ tau   → LEADER_CANDIDATE(#1)
      else (tie / no separation)              → CONTESTED
    Margin is measured over the #2 name by alpha in the whole sector (the field),
    so a lone eligible name still has to separate from the pack.
    """
    def _a(m):
        v = m.get("alpha")
        return float(v) if v is not None else float("-inf")

    ranked = sorted(members, key=_a, reverse=True)
    eligibles = [m for m in ranked if m.get("eligible")]

    if not eligibles:
        return {"state": "NO_CLEAR_LEADER", "leader": None,
                "dominance_margin": None, "ranked": ranked}

    top = eligibles[0]
    second_alpha = _a(ranked[1]) if len(ranked) >= 2 else None
    margin = (_a(top) - second_alpha) if second_alpha is not None else _a(top)
    margin = None if not np.isfinite(margin) else round(float(margin), 3)

    if margin is not None and margin >= float(dominance_tau):
        state, leader = "LEADER_CANDIDATE", top.get("ticker")
    else:
        state, leader = "CONTESTED", None
    return {"state": state, "leader": leader,
            "dominance_margin": margin, "ranked": ranked}


# ──────────────────────────────────────────────────────────────────────────────
# 4. Board assembly
# ──────────────────────────────────────────────────────────────────────────────

def build_board(residual: dict, closes: pd.DataFrame, *,
                flow_witness: dict | None = None,
                options_ctx: dict | None = None,
                alpha_min: float = ALPHA_LEADER_MIN,
                min_legs: int = MIN_TREND_LEGS,
                dominance_tau: float = DOMINANCE_TAU,
                as_of: str | None = None, stale: bool = False) -> dict | None:
    """Assemble momentum_king.v1 from a residual_alpha result + a close panel.

    `residual` : the dict from residual_alpha.compute_residual_alpha() — must carry
                 `by_sector` (per-sector leaders) with per-name alpha/entry/etc.
    `closes`   : date-indexed close matrix (columns = tickers) for the onset overlay.
    `flow_witness` / `options_ctx` : optional {ticker: {...}} display annotations
                 (MK-P2). Absent → the field is simply omitted (never a false zero).

    Onset/confluence is computed ONLY for each sector's residual leaders, not the
    whole universe — cheap and sufficient (leadership lives at the top of the rank).
    """
    if not residual or not isinstance(residual.get("by_sector"), dict):
        log.warning("momentum_king.build_board: no residual by_sector")
        return None

    flow_witness = flow_witness or {}
    options_ctx = options_ctx or {}
    have = set(closes.columns) if closes is not None else set()

    sectors_out = []
    for sec, blk in residual["by_sector"].items():
        classified = []
        for rec in blk.get("leaders", []):
            t = rec.get("ticker")
            onset = (confluence_onset(closes[t].dropna())
                     if t in have else {"trend_legs": None})
            m = classify_name(rec, onset, alpha_min=alpha_min, min_legs=min_legs)
            if t in flow_witness:
                m["net_inflow_witness"] = {**flow_witness[t], "authority_tier": "display"}
            if t in options_ctx:
                m["options_context"] = {**options_ctx[t], "authority_tier": "display"}
            classified.append(m)

        st = sector_state(classified, dominance_tau=dominance_tau)
        sectors_out.append({
            "sector": sec,
            "state": st["state"],
            "leader": st["leader"],
            "dominance_margin": st["dominance_margin"],
            "n": int(blk.get("n", len(classified))),
            "members": st["ranked"],
        })

    # sort sectors: LEADER_CANDIDATE first, then by leader alpha
    _order = {"LEADER_CANDIDATE": 0, "CONTESTED": 1, "NO_CLEAR_LEADER": 2}

    def _sec_key(s):
        lead = next((m for m in s["members"] if m.get("ticker") == s.get("leader")), None)
        a = lead.get("alpha") if lead else None
        return (_order.get(s["state"], 3), -(float(a) if a is not None else -1e9))

    sectors_out.sort(key=_sec_key)

    # cross-sector top candidates (LEADER_CANDIDATE leaders only, by alpha)
    top_candidates = []
    for s in sectors_out:
        if s["state"] == "LEADER_CANDIDATE":
            lead = next((m for m in s["members"] if m.get("ticker") == s["leader"]), None)
            if lead:
                top_candidates.append({k: lead.get(k) for k in
                                       ("ticker", "name", "sector", "alpha", "species",
                                        "trend_legs", "fresh_cross", "ticks_since_cross")})
    top_candidates.sort(key=lambda r: -(float(r["alpha"]) if r.get("alpha") is not None else -1e9))

    n_cand = sum(1 for s in sectors_out if s["state"] == "LEADER_CANDIDATE")
    return {
        "schema": SCHEMA,
        "as_of": as_of or residual.get("as_of"),
        "stale": bool(stale),
        "note": NOTE,
        "params": {"alpha_leader_min": alpha_min, "min_trend_legs": min_legs,
                   "dominance_tau": dominance_tau, "fresh_within": FRESH_WITHIN,
                   "extended_atr": EXTENDED_ATR},
        "coverage": {"n_sectors": len(sectors_out),
                     "n_leader_candidates": n_cand,
                     "n_contested": sum(1 for s in sectors_out if s["state"] == "CONTESTED"),
                     "n_no_clear_leader": sum(1 for s in sectors_out if s["state"] == "NO_CLEAR_LEADER")},
        "top_candidates": top_candidates,
        "sectors": sectors_out,
    }
