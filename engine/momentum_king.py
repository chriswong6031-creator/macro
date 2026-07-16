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
        cs_active = bool(last.get("CS", False))
        # K-of-N multi-timeframe trend legs (persistent states, not point events)
        legs = int(sum(bool(last.get(c, False))
                       for c in ("w2_bull", "w_bull", "mo_bull", "above200")))

        # Ignition freshness is derived from the SAME canonical confluence-buy (CB)
        # grid as the trend legs — NOT from postcross — so ticks_since_cross can never
        # disagree with cb_recent. (postcross rides a different RSI warm-up than
        # canon; see the MK hardening note. That is a separate, shared-module issue.)
        # ticks = number of 3D buckets since the last CB.
        cb = conf["CB"].astype(bool).to_numpy()
        cb_hits = np.flatnonzero(cb)
        ticks = int(len(cb) - 1 - cb_hits[-1]) if cb_hits.size else None
        cb_recent = ticks is not None and ticks <= int(fresh_within)

        # postcross supplies the auxiliary extension / structure reads only.
        pc = postcross(close, atr_series)
        ext_atr = pc.get("ext_atr")
        extended = None if ext_atr is None else (float(ext_atr) > float(extended_atr))

        # FRESH_INITIATION: a confluence buy printed within `fresh_within` buckets
        # AND the move is confirmed not-yet-stretched past the entry screen.
        fresh = bool(cb_recent and extended is False)
        species = ("FRESH_INITIATION" if fresh
                   else "ESTABLISHED_CONTINUATION" if legs >= MIN_TREND_LEGS
                   else None)

        out.update({"fresh_cross": fresh, "trend_legs": legs,
                    "ticks_since_cross": ticks,
                    "species": species, "extended": extended,
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

    a_ok = alpha is not None and np.isfinite(float(alpha))
    legs_ok = legs is not None and int(legs) >= int(min_legs)
    g1 = a_ok and float(alpha) >= float(alpha_min)
    g2 = legs_ok and not bool(onset.get("cs_active"))
    # G3 is FAIL-CLOSED: an UNKNOWN extension (None — short history / no postcross)
    # blocks eligibility rather than passing silently. Only a confirmed not-extended
    # (extended is False) and a residual overlay that isn't "extended" clears it.
    g3 = (onset.get("extended") is False) and entry != "extended"

    reasons = []
    if not g1:
        reasons.append("alpha_below_leader")
    if not legs_ok:
        reasons.append("weak_confluence")
    if bool(onset.get("cs_active")):
        reasons.append("active_sell")
    if onset.get("extended") is None:
        reasons.append("not_enough_history")
    elif not g3:
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
        try:
            v = float(v)
        except (TypeError, ValueError):
            return float("-inf")
        return v if np.isfinite(v) else float("-inf")

    ranked = sorted(members, key=_a, reverse=True)
    eligibles = [m for m in ranked if m.get("eligible")]

    if not eligibles or not np.isfinite(_a(eligibles[0])):
        return {"state": "NO_CLEAR_LEADER", "leader": None,
                "dominance_margin": None, "ranked": ranked}

    top = eligibles[0]
    # Margin over the strongest FINITE-alpha competitor in the whole field (any name,
    # not just eligible ones — the leader must separate from the full pack). A null /
    # -inf alpha member is skipped, never treated as a real competitor (BUG-2). A lone
    # member with no comparable competitor cannot demonstrate dominance → abstain (BUG-4).
    second = next((m for m in ranked if m is not top and np.isfinite(_a(m))), None)
    if second is None:
        return {"state": "NO_CLEAR_LEADER", "leader": None,
                "dominance_margin": None, "ranked": ranked}

    margin = round(float(_a(top) - _a(second)), 3)
    if margin >= float(dominance_tau):
        return {"state": "LEADER_CANDIDATE", "leader": top.get("ticker"),
                "dominance_margin": margin, "ranked": ranked}
    return {"state": "CONTESTED", "leader": None,
            "dominance_margin": margin, "ranked": ranked}


# ──────────────────────────────────────────────────────────────────────────────
# 4. Board assembly — the per-group state machine, reused across granularities
# ──────────────────────────────────────────────────────────────────────────────

_STATE_ORDER = {"LEADER_CANDIDATE": 0, "CONTESTED": 1, "NO_CLEAR_LEADER": 2}


def _assemble_groups(by_group: dict, closes: pd.DataFrame, *, label_key: str,
                     flow_witness: dict, options_ctx: dict,
                     alpha_min: float, min_legs: int, dominance_tau: float,
                     fresh_within: int = FRESH_WITHIN, extended_atr: float = EXTENDED_ATR,
                     meta: dict | None = None,
                     onset_cache: dict | None = None) -> list[dict]:
    """Run the per-group state machine over ANY grouping (sector / sub-industry /
    theme). For each group: confluence_onset → classify_name per leader, then
    sector_state over the classified members, emitting one row per group. The
    machinery is identical regardless of granularity — only the emitted label field
    name and an optional meta merge differ. `onset_cache` memoizes confluence_onset
    by ticker so a name that appears in several families (its sector + a sub-industry
    + a theme) is computed once and reads identically everywhere.
    """
    out = []
    have = set(closes.columns) if closes is not None else set()
    meta = meta or {}
    for gid, blk in by_group.items():
        classified = []
        for rec in blk.get("leaders", []):
            t = rec.get("ticker")
            if onset_cache is not None and t in onset_cache:
                onset = onset_cache[t]
            elif t in have:
                onset = confluence_onset(closes[t].dropna(),
                                         fresh_within=fresh_within, extended_atr=extended_atr)
                if onset_cache is not None:
                    onset_cache[t] = onset
            else:
                onset = {"trend_legs": None}
            m = classify_name(rec, onset, alpha_min=alpha_min, min_legs=min_legs)
            if t in flow_witness:
                m["net_inflow_witness"] = {**flow_witness[t], "authority_tier": "display"}
            if t in options_ctx:
                m["options_context"] = {**options_ctx[t], "authority_tier": "display"}
            classified.append(m)

        st = sector_state(classified, dominance_tau=dominance_tau)
        # Cohort breadth (display-only witness): of this group's shown leaders, how many
        # are in a multi-TF confluence uptrend? Distinguishes a lone-spike leader (narrow)
        # from a broadly-participating cohort (broad). Derived from the already-classified
        # members AFTER the state machine — it never feeds sector_state, so it annotates
        # the group but can never change its state (same subordinate-witness discipline).
        n_shown = len(classified)
        n_bull = sum(1 for m in classified if (m.get("gates") or {}).get("confluence_bull"))
        row = {label_key: gid, "state": st["state"], "leader": st["leader"],
               "dominance_margin": st["dominance_margin"],
               "n": int(blk.get("n", len(classified))), "members": st["ranked"],
               "breadth": {"n_shown": n_shown, "n_confluence_bull": n_bull,
                           "bull_frac": (round(n_bull / n_shown, 3) if n_shown else None),
                           "authority_tier": "display"}}
        if gid in meta:
            for k, v in meta[gid].items():
                row.setdefault(k, v)   # merge display meta; never clobber state fields
        out.append(row)
    return out


def _rank_groups(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Sort group rows (LEADER_CANDIDATE first, then leader alpha desc) and return
    (sorted_rows, top_candidates) — the cross-group strip of only the crowned leaders."""
    def _lead(s):
        return next((m for m in s.get("members", []) if m.get("ticker") == s.get("leader")), None)

    def _key(s):
        lead = _lead(s)
        a = lead.get("alpha") if lead else None
        return (_STATE_ORDER.get(s["state"], 3), -(float(a) if a is not None else -1e9))

    rows = sorted(rows, key=_key)
    top = []
    for s in rows:
        if s["state"] == "LEADER_CANDIDATE":
            lead = _lead(s)
            if lead:
                top.append({k: lead.get(k) for k in
                            ("ticker", "name", "sector", "alpha", "species",
                             "trend_legs", "fresh_cross", "ticks_since_cross")})
    top.sort(key=lambda r: -(float(r["alpha"]) if r.get("alpha") is not None else -1e9))
    return rows, top


def compute_persistence(history: list, current: dict) -> dict:
    """Leadership persistence from a prior-session ledger. Pure + display-only.

    history : prior session rows oldest→newest, each {'as_of': str, 'entries': {gid: leader}}.
    current : {gid: leader} for THIS session's LEADER_CANDIDATE groups (gid = 'family:group').
    Returns {gid: {tenure, first_seen, handoff, authority_tier}} where tenure = consecutive
    sessions (incl. now) the SAME leader has held the group; handoff = the immediately-prior
    session had a different non-null leader; first_seen = as_of of the earliest consecutive
    session. Cold-start (no matching history) → tenure 1, first_seen None, handoff False.
    Distinguishes a durable, established run from a one-session blip — a display witness only.
    """
    out = {}
    hist = list(history or [])
    for gid, leader in (current or {}).items():
        if not leader:
            continue
        tenure = 1
        first_seen = None
        for row in reversed(hist):
            if ((row.get("entries") or {}).get(gid)) == leader:
                tenure += 1
                first_seen = row.get("as_of")
            else:
                break
        prev = (hist[-1].get("entries") or {}).get(gid) if hist else None
        out[gid] = {"tenure": tenure, "first_seen": first_seen,
                    "handoff": bool(prev and prev != leader), "authority_tier": "display"}
    return out


def build_board(residual: dict, closes: pd.DataFrame, *,
                flow_witness: dict | None = None,
                options_ctx: dict | None = None,
                by_sub_industry: dict | None = None, sub_meta: dict | None = None,
                by_theme: dict | None = None, theme_meta: dict | None = None,
                alpha_min: float = ALPHA_LEADER_MIN,
                min_legs: int = MIN_TREND_LEGS,
                dominance_tau: float = DOMINANCE_TAU,
                fresh_within: int = FRESH_WITHIN,
                extended_atr: float = EXTENDED_ATR,
                as_of: str | None = None, stale: bool = False) -> dict | None:
    """Assemble momentum_king.v1 from a residual_alpha result + a close panel.

    `residual` : compute_residual_alpha() output — must carry `by_sector` (the spine).
    `closes`   : date-indexed close matrix (columns = tickers) for the onset overlay.
    `by_sub_industry` / `by_theme` : OPTIONAL group dicts shaped exactly like
                 `by_sector` ({group -> {'n','leaders':[...]}}), produced by the build
                 script per sub-industry / per curated theme. Each runs the IDENTICAL
                 state machine. Absent → that section is omitted (never a false empty).
    `sub_meta` / `theme_meta` : {group -> {display fields}} merged onto each group row.
    `flow_witness` / `options_ctx` : optional {ticker: {...}} display annotations.

    Onset/confluence is computed only for each group's residual leaders and memoized
    by ticker across families — cheap and internally consistent.
    """
    if not residual or not isinstance(residual.get("by_sector"), dict):
        log.warning("momentum_king.build_board: no residual by_sector")
        return None

    onset_cache: dict = {}
    common = dict(flow_witness=flow_witness or {}, options_ctx=options_ctx or {},
                  alpha_min=alpha_min, min_legs=min_legs, dominance_tau=dominance_tau,
                  fresh_within=fresh_within, extended_atr=extended_atr,
                  onset_cache=onset_cache)

    sectors_out = _assemble_groups(residual["by_sector"], closes, label_key="sector", **common)
    sectors_out, top_candidates = _rank_groups(sectors_out)

    coverage = {
        "n_sectors": len(sectors_out),
        "n_leader_candidates": sum(1 for s in sectors_out if s["state"] == "LEADER_CANDIDATE"),
        "n_contested": sum(1 for s in sectors_out if s["state"] == "CONTESTED"),
        "n_no_clear_leader": sum(1 for s in sectors_out if s["state"] == "NO_CLEAR_LEADER"),
    }

    out = {
        "schema": SCHEMA,
        "as_of": as_of or residual.get("as_of"),
        "stale": bool(stale),
        "note": NOTE,
        "params": {"alpha_leader_min": alpha_min, "min_trend_legs": min_legs,
                   "dominance_tau": dominance_tau, "fresh_within": fresh_within,
                   "extended_atr": extended_atr},
        "coverage": coverage,
        "top_candidates": top_candidates,
        "sectors": sectors_out,
    }

    # ── Additive granularities — each independently absent-safe (omitted when the
    #    loader returned nothing, never emitted as a false-empty section) ─────────
    if by_sub_industry:
        subs_out = _assemble_groups(by_sub_industry, closes, label_key="sub_industry",
                                    meta=sub_meta or {}, **common)
        subs_out, sub_top = _rank_groups(subs_out)
        out["sub_industries"] = subs_out
        out["sub_industry_top"] = sub_top
        coverage["n_sub_industries"] = len(subs_out)
        coverage["n_sub_leader_candidates"] = sum(1 for s in subs_out if s["state"] == "LEADER_CANDIDATE")

    if by_theme:
        themes_out = _assemble_groups(by_theme, closes, label_key="theme",
                                      meta=theme_meta or {}, **common)
        themes_out, theme_top = _rank_groups(themes_out)
        out["themes"] = themes_out
        out["theme_top"] = theme_top
        coverage["n_themes"] = len(themes_out)
        coverage["n_theme_leader_candidates"] = sum(1 for s in themes_out if s["state"] == "LEADER_CANDIDATE")

    return out
