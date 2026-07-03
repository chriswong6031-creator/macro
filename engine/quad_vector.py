"""quad_vector — the published continuous P(Quad) CONTRACT (latest.json top-level).

THIS MODULE COMPUTES NO PROBABILITIES. One source of truth per concept (P7):
the continuous quad posterior is owned by the hedgeye-informed program —
engine/regime_one._causal_filtered_pquad (causal forward-alpha HMM, no
lookahead), with engine/regime_hmm as the smoothed display sibling. This is a
thin publisher that reshapes their output into the stable consumer contract
the Mastermind bot (and any other machine reader) codes against, so the
producer can evolve internally without breaking consumers:

    {schema_version, asof, p{Q1..Q4}, hard_label, confidence, drivers,
     transition_momentum, degraded, degrade_reason}

Named quad_vector because next_quad_probs is TAKEN — twice — by historical
Markov objects (playbook.next_quad_probs: hard-label segment transitions;
regime_hmm.next_quad_probs: the HMM monthly transition row). Both answer
"given the label, what came next historically"; this answers "what does the
tape say the quad IS right now", a different object. Do not overload.

P2 degrade rule: a missing/stale posterior WIDENS p toward uniform and sets
degraded=true — a data outage may only lower confidence, never sharpen it
(the inverse of the missing-stockdata -> confluence=1.0 failure).

hard_label is the sticky hysteresis label and need NOT equal argmax(p); the
divergence is itself a WEAKENING tell (a contradiction plane consumers may
shrink on, never flip on).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

_QUADS = ["Q1", "Q2", "Q3", "Q4"]
# monthly_sign legs (engine/axes._component_scores) — backward-looking confirmations
# that pad the axis during fast rotations; flagged so consumers can down-weight
# them during transitions (the incident's fast/slow miss, signals.md §1 fault 2).
_SLOW_LEGS = {"payrolls_trend", "indpro_trend", "wei_trend", "gdpnow_trend",
              "sticky_cpi_direction"}
_MOM_WINDOW = 5  # sessions averaged for the d(p)/dt read


def _clean_p(raw: dict | None) -> dict | None:
    """Validate + renormalize a {Q1..Q4: float} dict; None when unusable."""
    if not isinstance(raw, dict):
        return None
    vals = {}
    for q in _QUADS:
        v = raw.get(q)
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        if not np.isfinite(v) or v < 0:
            return None
        vals[q] = v
    s = sum(vals.values())
    if s <= 0:
        return None
    return {q: v / s for q, v in vals.items()}


def _drivers(full_row: pd.Series) -> dict:
    """Signed per-leg contribution to each axis mean, from the c_ component
    scores classify() already computed: contrib_i = w_i * score_i / sum(w_avail).
    Zero-score legs are omitted (they carry no directional information)."""
    ecfg = config.load()["engine"]
    out: dict[str, list] = {}
    for axis in ("growth", "inflation"):
        comps = ecfg[f"{axis}_axis"]["components"]
        avail_w = 0.0
        raw: list[tuple[str, float, float]] = []
        for name, spec in comps.items():
            v = full_row.get(f"c_{axis}_{name}")
            if v is None or pd.isna(v):
                continue
            w = float(spec["weight"])
            avail_w += w
            raw.append((name, float(v), w))
        legs = []
        for name, v, w in raw:
            if v == 0 or avail_w == 0:
                continue
            leg = {"leg": name, "contrib": round(v * w / avail_w, 3)}
            if name in _SLOW_LEGS:
                leg["slow"] = True
            legs.append(leg)
        legs.sort(key=lambda d: -abs(d["contrib"]))
        out[axis] = legs
    return out


def _momentum(history: list | None) -> dict | None:
    """d(p)/dt: mean per-session Δp over the trailing _MOM_WINDOW sessions of the
    causal filtered history — which quad is GAINING mass (the forward tell the
    discrete transition_state cannot give)."""
    if not history or len(history) < 2:
        return None
    tail = history[-(_MOM_WINDOW + 1):]
    first, last = tail[0], tail[-1]
    n = len(tail) - 1
    try:
        rates = {q: (float(last[q]) - float(first[q])) / n for q in _QUADS}
    except (KeyError, TypeError, ValueError):
        return None
    gaining = max(rates, key=rates.get)
    losing = min(rates, key=rates.get)
    return {
        "gaining": gaining, "gaining_rate": round(rates[gaining], 4),
        "losing": losing, "losing_rate": round(rates[losing], 4),
        "window_sessions": n,
    }


def build(latest: dict, full: pd.DataFrame, asof: pd.Timestamp) -> dict:
    """Assemble the quad_vector contract from the already-computed leaves.
    Never raises past the caller's additive try/except; degrades, never fails."""
    degraded, reason = False, None
    source = None
    history = None

    r1 = (latest.get("regime_one") or {})
    pq = ((r1.get("forward") or {}).get("p_quad") or {})
    p = _clean_p(pq.get("value"))
    pq_asof = r1.get("asof")
    if p is not None:
        source = "regime_one.forward.p_quad (causal filtered HMM)"
        history = pq.get("history_filtered")
    else:
        hmm = latest.get("regime_hmm") or {}
        p = _clean_p(hmm.get("regime_probs"))
        if p is not None:
            # smoothed forward-backward == the filtered posterior AT the final
            # observation, but it is the non-causal sibling — flag honestly.
            source = "regime_hmm.regime_probs (smoothed fallback)"
            pq_asof = hmm.get("asof") or latest.get("date")
            history = hmm.get("history")
            degraded, reason = True, "causal p_quad missing; smoothed HMM fallback"
        else:
            p = {q: 0.25 for q in _QUADS}
            source = "uniform"
            pq_asof = latest.get("date")
            degraded, reason = True, "no P(Quad) producer available; p widened to uniform"

    # freshness gate: a stale posterior degrades (argmax effectively pinned to
    # last-good by construction — we publish the last-good p, flagged).
    try:
        age = int((pd.Timestamp(asof) - pd.Timestamp(pq_asof)).days)
        if age > 5:
            degraded = True
            reason = (reason + "; " if reason else "") + f"p_quad stale ({age}d old)"
    except (TypeError, ValueError):
        pass

    row = full.loc[asof] if asof in full.index else full.iloc[-1]
    agree = pd.Series([row.get("growth_agreement"), row.get("inflation_agreement")],
                      dtype=float).mean()
    max_p = max(p.values())
    confidence = None if pd.isna(agree) else round(float(max_p * agree), 3)

    hard = latest.get("quad")
    return {
        "schema_version": 1,
        "asof": str(pq_asof) if pq_asof else str(pd.Timestamp(asof).date()),
        "p": {q: round(v, 4) for q, v in p.items()},
        "source": source,
        "hard_label": hard,
        # argmax need NOT equal the sticky hysteresis label; divergence is a
        # WEAKENING tell (shrink-only consumption, never a flip trigger)
        "hard_label_agrees": bool(hard == max(p, key=p.get)),
        "confidence": confidence,  # max(p) x axis agreement, [0,1]
        "confidence_note": "max(p) * mean(growth_agreement, inflation_agreement)",
        "drivers": _drivers(row),
        "transition_momentum": _momentum(history),
        "degraded": bool(degraded),
        "degrade_reason": reason,
    }
