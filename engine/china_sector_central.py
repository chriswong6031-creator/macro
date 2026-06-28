"""China Sector Central Intelligence — the fuser that amalgamates the cycle map, the
evidence-gated pathway forward layer, and the (audited) momentum / flow / crowding CONTEXT
into ONE per-sector intelligence record, under a validated regime GATE, with a transparent
reasoning trace.

DISCIPLINE (research/ALLOCATION_CHINA_AUDIT.md + the house registry). The audit proved the
narrative-rotation momentum score is a CONFIRMER with no tradeable forward alpha in China, and
that the absolute-trend gate is NOT a China drawdown gate. The only validated inputs are:
  • the REGIME de-risk anchor (credit_impulse 0.45 / vol_regime 0.35 / margin_euphoria 0.20,
    via engine.china_masterminds.regime_state) — the scored gate;
  • engine.china_sector_pathway's Wilson-CI conditional odds (the 4 GS sectors) — the only
    honest forward tilt;
  • the washout↔euphoria state signature (Phase-0 stable).
Everything else — momentum/RS, southbound/margin flow, turnover, crowding, narrative rotation —
is CONFIRMER / CONTEXT: it confirms and sizes, capped so it can never masquerade as alpha.

So this is NOT an equal-weight blend. It is a GATED CONFLUENCE hierarchy that mimics layered
reasoning:
    where-are-we (cycle state) + what's-next (pathway, where validated)  →  LEAD
    is the regime permissive?                                            →  GATE
    is it confirmed by momentum / flow? any fragility?                   →  CONFIRM / SIZE
  → a conviction tier + a 0–100 confluence score + a human-readable reasoning trace, plus the
    honest forward odds. Every dated call is logged so the engine is GRADED, not asserted
    (engine.china_sector_central_grader / append_central_log).

Pure-read + additive: any failure on a layer degrades gracefully; the market gate and the
cycle spine are the only hard requirements.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# conviction tiers (score 0–100, after gate + context)
TIERS = [
    (72, "Accumulate",   "积极配置", "up"),
    (58, "Constructive", "建设性",   "up"),
    (43, "Neutral",      "中性",     "flat"),
    (30, "Cautious",     "谨慎",     "down"),
    (0,  "Reduce",       "减配",     "down"),
]


# =========================================================================== #
# market context — the validated regime GATE + display flow/froth context
# =========================================================================== #
def _regime_anchor() -> dict:
    """The validated risk posture (china_masterminds.regime_state: credit/vol/margin blend) +
    the quad / liquidity context (data/china_regime/latest.json). Returns a normalized market
    read with a risk-on scalar in [-1,+1] and a [0,1] gate factor for bullish convictions."""
    rs = None
    try:
        from engine.china_masterminds import regime_state
        rs = regime_state()
    except Exception as e:  # noqa: BLE001
        log.warning("central: regime_state failed: %s", e)

    quad = quad_name = liquidity = None
    g_score = i_score = None
    try:
        p = config.data_dir() / "china_regime" / "latest.json"
        if p.exists():
            d = json.loads(p.read_text())
            quad, quad_name = d.get("quad"), d.get("quad_name")
            liquidity = d.get("liquidity_overlay") or d.get("liquidity")
            g_score, i_score = d.get("growth_score"), d.get("inflation_score")
    except Exception as e:  # noqa: BLE001
        log.debug("central: regime latest.json unreadable: %s", e)

    # validated risk-on scalar: regime_state.tilt is +1=de-risk(risk-OFF) → flip sign.
    risk_on = None
    if rs and rs.get("tilt") is not None:
        risk_on = round(-float(rs["tilt"]), 2)            # +1 risk-on … −1 risk-off
    # quad confirmation (context): Q1/Q2 risk-on, Q3/Q4 risk-off
    quad_lean = {"Q1": 1, "Q2": 1, "Q3": -1, "Q4": -1}.get(quad)
    liq_lean = {"expanding": 1, "contracting": -1, "neutral": 0, "unknown": None}.get(liquidity)

    # gate factor for BULLISH convictions in [0,1]: risk-off shrinks long tilts (it does NOT
    # forbid them — gating, not a switch). Driven by the validated regime; quad/liquidity nudge.
    if risk_on is None:
        gate = 0.7
    else:
        gate = float(np.clip(0.5 + 0.5 * risk_on, 0.2, 1.0))
    if quad_lean == -1:
        gate *= 0.85
    if liq_lean == -1:
        gate *= 0.8
    elif liq_lean == 1:
        gate = min(1.0, gate * 1.1)
    gate = round(float(np.clip(gate, 0.2, 1.0)), 2)

    tone = (rs or {}).get("tone")
    state_en = (rs or {}).get("state_en") or ("risk-off" if (risk_on or 0) < -0.2 else
                                              "risk-on" if (risk_on or 0) > 0.2 else "neutral")
    return {
        "risk_on": risk_on, "gate_factor": gate, "tone": tone, "state_en": state_en,
        "state_zh": (rs or {}).get("state_zh"),
        "derisk_blended": (rs or {}).get("blended"), "regime_legs": (rs or {}).get("legs"),
        "quad": quad, "quad_name": quad_name, "liquidity": liquidity,
        "growth_score": g_score, "inflation_score": i_score,
        "validated": True,
    }


def _flow_froth() -> dict:
    """Display-only market flow + froth context (china_internals + china_crowding). NEVER a
    scored leg — southbound DIVERGENCE is powered-negative, northbound net is dead."""
    out = {"validated": False}
    try:
        from engine import china_internals as ci
        out["turnover"] = ci.market_turnover()
        out["southbound"] = ci.southbound_flow()
        out["margin"] = ci.margin_meter()
    except Exception as e:  # noqa: BLE001
        log.debug("central: china_internals failed: %s", e)
    try:
        from engine import china_crowding
        cb = china_crowding.build()
        out["froth_anchor"] = cb.get("market_anchor")        # whole-A valuation froth pctile
        out["crowd_by_ticker"] = cb.get("by_ticker") or {}
    except Exception as e:  # noqa: BLE001
        log.debug("central: china_crowding failed: %s", e)
        out["crowd_by_ticker"] = {}
    return out


def market_context() -> dict:
    anc = _regime_anchor()
    flow = _flow_froth()
    return {**anc, "flow": {k: v for k, v in flow.items() if k != "crowd_by_ticker"},
            "_crowd_by_ticker": flow.get("crowd_by_ticker", {})}


# =========================================================================== #
# per-sector / per-basket confluence
# =========================================================================== #
def _state_score(now: dict) -> tuple[float, dict]:
    """Where-are-we, from the validated washout↔euphoria signature + the cycle phase direction.
    Returns a setup score in [-1,+1] (washed-out + turning up = +1) + a descriptor."""
    sig = (now.get("signature") or {}).get("score")
    # signature 0=washout(bullish setup) … 100=euphoric(bearish). Map to [-1,+1].
    setup = (50.0 - sig) / 50.0 if sig is not None else 0.0
    phase = now.get("phase")
    phase_dir = {"Trough": 0.5, "Recovery": 0.6, "Expansion": 0.25,
                 "Peak": -0.4, "Downturn": -0.55}.get(phase, 0.0)
    score = float(np.clip(0.6 * setup + 0.4 * phase_dir, -1, 1))
    return score, {"signature": sig, "phase": phase,
                   "label": (now.get("signature") or {}).get("label")}


def _forward_tilt(rec: dict) -> tuple[float | None, dict | None]:
    """The honest forward tilt. PRIMARY: china_sector_pathway Wilson-CI conditional (4 GS
    sectors) — the only validated forward input. Returns a tilt in [-1,+1] scaled by sample
    confidence, or None where no pathway exists (then the cycle projection is rhythm-only)."""
    pw = rec.get("pathway")
    if not pw:
        return None, None
    cond = pw.get("conditional") or {}
    h = cond.get("h6") or cond.get("h3")
    if not h:
        return None, {"has_pathway": True}
    lift = float(h.get("lift") or 0.0)               # cond_rate − base_rate
    n = int(h.get("n") or 0)
    ci_lo, ci_hi = h.get("ci_lo"), h.get("ci_hi")
    base = float(h.get("base_rate") or 0.5)
    # confidence: shrink the tilt when the CI straddles the base rate or n is small
    straddles = (ci_lo is not None and ci_hi is not None and ci_lo <= base <= ci_hi)
    conf = float(np.clip(n / 60.0, 0.3, 1.0)) * (0.5 if straddles else 1.0)
    tilt = float(np.clip(lift * 6.0, -1, 1)) * conf   # lift ~±0.17 → ~±1 before conf
    return tilt, {"cond_rate": h.get("cond_rate"), "base_rate": h.get("base_rate"),
                  "ci_lo": ci_lo, "ci_hi": ci_hi, "n": n, "h": h.get("h"),
                  "tercile": (pw.get("setup") or {}).get("tercile"),
                  "lift": round(lift, 3), "confidence": round(conf, 2),
                  "narrative_en": pw.get("narrative_en"), "narrative_zh": pw.get("narrative_zh")}


def _momentum_confirm(now: dict, n_peers: int) -> tuple[float, dict]:
    """CONFIRMER (capped ±0.3, never alpha): RS leadership rank + trend direction. A leading,
    above-trend sector CONFIRMS a constructive call; a lagging one flags it as 'early'."""
    rank = now.get("rs_rank")
    above = now.get("above200d")
    rs63 = now.get("rs_63d")
    pct = (1.0 - (rank - 1) / max(n_peers - 1, 1)) if rank else 0.5   # 1=leader
    c = (pct - 0.5) * 0.6                                              # ±0.3
    if above is False:
        c -= 0.1
    c = float(np.clip(c, -0.3, 0.3))
    lead = ("leading" if (rank or 99) <= max(3, n_peers // 4) else
            "lagging" if (rank or 0) >= n_peers - max(3, n_peers // 4) else "mid-pack")
    return c, {"rs_rank": rank, "rs_63d": rs63, "above_200d": above, "lead": lead}


def _crowd_for_members(members: list, crowd_by_ticker: dict) -> dict | None:
    if not members or not crowd_by_ticker:
        return None
    hits = [t for t in members if t in crowd_by_ticker]
    if not hits:
        return None
    return {"n_crowded": len(hits), "n_members": len(members),
            "frac": round(len(hits) / max(len(members), 1), 2),
            "names": hits[:6]}


def _tier_for(score: float) -> tuple[str, str, str]:
    for thr, en, zh, dir_ in TIERS:
        if score >= thr:
            return en, zh, dir_
    return TIERS[-1][1], TIERS[-1][2], TIERS[-1][3]


def _fuse(rec: dict, mkt: dict, n_peers: int, members: list | None = None) -> dict:
    """The gated-confluence conviction for one sector/basket + the reasoning trace."""
    now = rec.get("now") or {}
    state, state_d = _state_score(now)
    fwd, fwd_d = _forward_tilt(rec)
    mom, mom_d = _momentum_confirm(now, n_peers)
    crowd = _crowd_for_members(members or [], mkt.get("_crowd_by_ticker", {}))

    # LEAD: state + forward (forward weighted higher where a validated pathway exists)
    if fwd is not None:
        lead = 0.45 * state + 0.55 * fwd
        w_note = "state+pathway"
    else:
        lead = state
        w_note = "state-only (no validated pathway)"

    # GATE: risk-off shrinks bullish tilts (gating, not a switch); risk-off deepens caution
    gate = mkt.get("gate_factor", 0.7)
    if lead > 0:
        gated = lead * gate
    else:
        gated = lead * (2.0 - gate)          # risk-off (gate<1) amplifies a bearish read
    gated = float(np.clip(gated, -1, 1))

    # CONFIRM: capped momentum nudge
    raw = float(np.clip(gated + 0.5 * mom, -1, 1))
    score = round((raw + 1.0) / 2.0 * 100)

    # CONFLUENCE: how many validated/state layers agree in the conviction's direction
    dir_sign = 1 if raw > 0.05 else -1 if raw < -0.05 else 0
    layers_sign = [np.sign(state), (np.sign(fwd) if fwd is not None else 0),
                   (1 if (mkt.get("risk_on") or 0) > 0.1 else -1 if (mkt.get("risk_on") or 0) < -0.1 else 0)]
    agree = sum(1 for s in layers_sign if dir_sign != 0 and s == dir_sign)
    confluence = {"agree": int(agree), "of": 3,
                  "label": ("high" if agree >= 3 else "moderate" if agree == 2 else "low/mixed")}

    en, zh, _dir = _tier_for(score)
    # fragility / euphoria cap: a euphoric or crowded name can't be top-tier
    euphoric = (state_d.get("signature") or 0) >= 80
    if (euphoric or (crowd and crowd["frac"] >= 0.34)) and score >= 58:
        score = min(score, 57); en, zh, _dir = _tier_for(score)
    # if the lead is bullish but momentum lagging, mark "early" (don't upgrade past constructive)
    early = raw > 0 and mom_d.get("lead") == "lagging"

    trace = _trace(state_d, fwd_d, mkt, mom_d, crowd, early, euphoric)
    return {
        "conviction": {"score": int(score), "label_en": en, "label_zh": zh,
                       "dir": _dir, "early": bool(early), "confluence": confluence},
        "forward": fwd_d, "state": state_d,
        "momentum": mom_d, "crowding": crowd,
        "components": {"state": round(state, 2), "forward": (round(fwd, 2) if fwd is not None else None),
                       "lead": round(lead, 2), "gate_factor": gate, "gated": round(gated, 2),
                       "momentum": round(mom, 2), "raw": round(raw, 2), "weighting": w_note},
        "reasoning": trace,
    }


def _trace(state_d, fwd_d, mkt, mom_d, crowd, early, euphoric) -> list[dict]:
    """Human-readable, tier-tagged reasoning trace (the 'deep reasoning' surface)."""
    t = []
    sig = state_d.get("signature")
    if sig is not None:
        stance = "bullish" if sig <= 35 else "bearish" if sig >= 65 else "neutral"
        t.append({"layer": "Cycle state", "tier": "validated", "stance": stance,
                  "en": f"{state_d.get('label') or '—'} (signature {sig:.0f}/100), phase {state_d.get('phase')}",
                  "zh": f"{state_d.get('label') or '—'}（特征 {sig:.0f}/100），阶段 {state_d.get('phase')}"})
    if fwd_d and fwd_d.get("cond_rate") is not None:
        cr, br = round(fwd_d["cond_rate"] * 100), round(fwd_d["base_rate"] * 100)
        stance = "bullish" if fwd_d.get("lift", 0) > 0.03 else "bearish" if fwd_d.get("lift", 0) < -0.03 else "neutral"
        t.append({"layer": "Forward odds", "tier": "validated", "stance": stance,
                  "en": f"{cr}% forward-{fwd_d.get('h')}m positive vs {br}% base "
                        f"(CI {round((fwd_d.get('ci_lo') or 0)*100)}–{round((fwd_d.get('ci_hi') or 0)*100)}%, n={fwd_d.get('n')})",
                  "zh": f"未来{fwd_d.get('h')}个月上涨概率 {cr}%（基准 {br}%，样本 {fwd_d.get('n')}）"})
    rstance = "bullish" if (mkt.get("risk_on") or 0) > 0.1 else "bearish" if (mkt.get("risk_on") or 0) < -0.1 else "neutral"
    t.append({"layer": "Regime gate", "tier": "validated", "stance": rstance,
              "en": f"{mkt.get('state_en')} (de-risk {mkt.get('derisk_blended')}, {mkt.get('quad_name') or mkt.get('quad') or '—'}, "
                    f"liquidity {mkt.get('liquidity') or '—'}) → gate ×{mkt.get('gate_factor')}",
              "zh": f"{mkt.get('state_zh') or mkt.get('state_en')}（降险 {mkt.get('derisk_blended')}，{mkt.get('quad_name') or '—'}）→ 门控 ×{mkt.get('gate_factor')}"})
    t.append({"layer": "Momentum", "tier": "confirmer", "stance": mom_d.get("lead"),
              "en": f"RS #{mom_d.get('rs_rank') or '—'} — {mom_d.get('lead')}"
                    + (" (early — not yet confirmed by trend)" if early else ""),
              "zh": f"相对强度 #{mom_d.get('rs_rank') or '—'} — {mom_d.get('lead')}"})
    if crowd:
        t.append({"layer": "Crowding", "tier": "display", "stance": "caution",
                  "en": f"{crowd['n_crowded']}/{crowd['n_members']} members crowded-fragile → size down",
                  "zh": f"{crowd['n_crowded']}/{crowd['n_members']} 只成分拥挤脆弱 → 降低仓位"})
    if euphoric:
        t.append({"layer": "Fragility", "tier": "display", "stance": "caution",
                  "en": "euphoric/extended — conviction capped", "zh": "过热/拉伸 — 信念封顶"})
    return t


def compute() -> dict | None:
    """Top-level: fuse the cycle spine + market regime + flow/froth into per-sector and
    per-basket central intelligence records, ranked by conviction."""
    try:
        from engine import china_sector_cycles as ccc
        cyc = ccc.compute()
    except Exception as e:  # noqa: BLE001
        log.error("central: cycle spine failed: %s", e)
        return None
    if not cyc or not cyc.get("sectors"):
        return None
    mkt = market_context()

    # basket membership (for crowding aggregation)
    memb = {}
    try:
        from engine.baskets_china import _membership
        mm = _membership() or {}
        for bid, b in (mm.get("baskets") or {}).items():
            memb[bid] = [m["ticker"] for m in b.get("members", [])]
    except Exception:  # noqa: BLE001
        memb = {}

    n_sec = len(cyc["sectors"])
    sectors = []
    for rec in cyc["sectors"]:
        fused = _fuse(rec, mkt, n_sec)
        sectors.append({**_carry(rec), **fused})
    n_bsk = max(len(cyc.get("baskets", [])), 1)
    baskets = []
    for rec in cyc.get("baskets", []):
        fused = _fuse(rec, mkt, n_bsk, members=memb.get(rec.get("basket_id"), []))
        baskets.append({**_carry(rec), **fused})

    sectors.sort(key=lambda x: -x["conviction"]["score"])
    baskets.sort(key=lambda x: -x["conviction"]["score"])
    mkt.pop("_crowd_by_ticker", None)

    return {
        "as_of": cyc["meta"]["asOf"],
        "meta": {"n_sectors": len(sectors), "n_baskets": len(baskets),
                 "region": "china", "experimental": True,
                 "method": "gated-confluence (research/ALLOCATION_CHINA_AUDIT.md)"},
        "market": mkt,
        "sectors": sectors,
        "baskets": baskets,
    }


def _carry(rec: dict) -> dict:
    """Carry the identity + a compact cycle snapshot from the cycle record onto the central row."""
    now = rec.get("now") or {}
    return {
        "id": rec.get("id"), "ticker": rec.get("ticker"), "kind": rec.get("kind"),
        "basket_id": rec.get("basket_id"), "shenwan_code": rec.get("shenwan_code"),
        "name": rec.get("name"), "name_zh": rec.get("name_zh"),
        "group": rec.get("group"), "group_zh": rec.get("group_zh"), "accent": rec.get("accent"),
        "etf_proxy": rec.get("etf_proxy"),
        "cycle": {"phase": now.get("phase"), "phaseLabel": now.get("phaseLabel"),
                  "pos": now.get("pos"), "proj": rec.get("proj"),
                  "rs_rank": now.get("rs_rank"), "above200d": now.get("above200d")},
    }
