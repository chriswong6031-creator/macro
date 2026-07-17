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
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# ── spine truncation / staleness guard constants (sector-central-china-6) ───
# If the cycle spine comes back from a truncated akshare scrape, we get silently
# corrupted RS/signature data.  Guard thresholds are additive — degraded state
# is flagged in the returned meta, never fatal.
_SPINE_MIN_SECTORS = 4    # Shenwan L1 has ~10+ sectors; <4 = definitely truncated
_SPINE_STALE_DAYS  = 3    # calendar days before flagging the spine asOf as stale

# ── regime-leg staleness guard (W0.4) ────────────────────────────────────────
# Maximum acceptable age (calendar days) for each de-risk leg's input data,
# judged from the DATA's own newest content date (availability_date / date
# index), never file mtime — mtime lies on CI checkouts (#2690 class), which
# made this watchdog blind to exactly the frozen-upstream case it exists for.
# Thresholds reflect the natural release cadence of each series:
#   credit: monthly TSF is released ~day 16 of the following month (up to 47d gap
#           is normal).  Flag at 60d — almost 2 calendar months without an update
#           would indicate a stale collector rather than a normal release lag.
#   vol:    CSI 300 daily close — content lags T+1 plus weekends; a CN Golden
#           Week closure (≈8 calendar days) plus T+1 and an adjacent weekend
#           can reach ~11d while perfectly healthy. Flag at 12d.
#   margin: daily margin balance, published T+1 — same holiday allowance, 12d.
# A stale leg silently pins the gate at an extreme. The staleness check surfaces
# this so an operator can diagnose a frozen upstream collector.
_LEG_STALE_DAYS: dict[str, int] = {"credit": 60, "vol": 12, "margin": 12}

# ── tier-cap threshold (W0.4) ────────────────────────────────────────────────
# When gate_factor < this value the top conviction tier (Accumulate, score ≥ 72)
# becomes structurally unreachable.  Derivation: max achievable score at gate g is
# round((g + 0.15 + 1.0) / 2.0 * 100) ≈ 58 + 50g with best-case lead=1 + mom=0.3.
# Solving 58 + 50g ≥ 72 → g ≥ 0.28.  We use 0.29 (with a small float margin).
_GATE_ACCUMULATE_FLOOR = 0.29

# conviction tiers (score 0–100, after gate + context)
TIERS = [
    (72, "Accumulate",   "积极配置", "up"),
    (58, "Constructive", "建设性",   "up"),
    (43, "Neutral",      "中性",     "flat"),
    (30, "Cautious",     "谨慎",     "down"),
    (0,  "Reduce",       "减配",     "down"),
]

# zh for the reasoning-BODY tokens. The en bodies are composed in English from
# upstream regime/quad/phase/momentum reads, so the zh trace would otherwise leak
# raw English words (Stagflation, Trough, lagging, …). Canonical zh mirrors the
# cycle page (site/cycle_app.js phase wheel) and the signal stacks (quad names).
_PHASE_ZH = {"Trough": "筑底", "Recovery": "复苏", "Expansion": "扩张",
             "Peak": "见顶", "Downturn": "回落"}
_QUAD_ZH = {"Goldilocks": "理想增长", "Reflation": "再通胀", "Stagflation": "滞胀",
            "Growth-scare": "增长恐慌", "Growth scare": "增长恐慌",
            "Growth Scare": "增长恐慌", "Deflation": "通缩"}
_LEAD_ZH = {"leading": "领先", "lagging": "落后", "mid-pack": "中游"}


# =========================================================================== #
# market context — the validated regime GATE + display flow/froth context
# =========================================================================== #
def _newest_content_date(path: Path, column: str | None) -> date | None:
    """Newest data date inside the parquet — `column` if given, else the index.
    Returns None when the file/stamp is unreadable (logged; caller keeps None
    = unknown, matching the missing-file semantics)."""
    try:
        df = pd.read_parquet(path, columns=[column] if column else [])
        vals = df[column] if column else pd.Series(df.index)
        ts = pd.to_datetime(vals, errors="coerce").dropna()
        if ts.empty:
            return None
        return ts.max().date()
    except Exception as e:  # noqa: BLE001
        log.warning("central: cannot read content date from %s (%s)", path, e)
        return None


def _regime_leg_staleness(legs: list[dict] | None) -> dict[str, int | None]:
    """Return the calendar-day age of each de-risk leg's input data, keyed by leg name.

    The age is the distance from today to the DATA's own newest content date
    (tsf availability_date / margin & close date index) — NEVER file mtime.
    On CI runners a checkout rewrites files with mtime = checkout time, so a
    frozen upstream always looked freshly written and this watchdog was blind
    to exactly the silent-freeze case it exists for (#2690 class). None means
    the file could not be found or its stamp was unreadable (collector never
    ran or schema changed).  Used by _regime_anchor() to populate leg_stale
    and any_stale in the returned market context, so the template can surface
    a warning banner when a frozen upstream silently pins the gate. (W0.4)
    """
    data_dir = config.data_dir()
    # Source files for each leg — matches china_strategies._margin_derisk / _credit_derisk /
    # _vol_derisk.  Vol reads CSI-300 close from data/china/510300.SS.parquet (via the shared
    # china store, NOT the yahoo store — china_masterminds._cnclose uses store.read("china", ...)).
    # Stamp column: tsf carries an explicit PIT availability_date; margin/vol are
    # date-indexed (DIM_DATE / Date).
    _leg_sources: dict[str, tuple[Path, str | None]] = {
        "credit": (data_dir / "china_credit" / "tsf.parquet", "availability_date"),
        "margin": (data_dir / "china_margin" / "balance.parquet", None),
        "vol": (data_dir / "china" / "510300.SS.parquet", None),
    }
    ages: dict[str, int | None] = {}
    today = date.today()
    for key, (path, column) in _leg_sources.items():
        try:
            if path.exists():
                newest = _newest_content_date(path, column)
                ages[key] = (today - newest).days if newest is not None else None
            else:
                ages[key] = None
        except Exception:  # noqa: BLE001
            ages[key] = None
    return ages


def _regime_anchor() -> dict:
    """The validated risk posture (china_masterminds.regime_state: credit/vol/margin blend) +
    the quad / liquidity context (data/china_regime/latest.json). Returns a normalized market
    read with a risk-on scalar in [-1,+1] and a [0,1] gate factor for bullish convictions.

    W0.4 additions:
    - leg_stale: {credit/vol/margin → age_days|None} so the template can warn when a
      collector has stopped updating and is silently pinning a leg at an extreme.
    - any_stale: True when any leg's input is older than its threshold (see _LEG_STALE_DAYS).
    - gate_caps_tier: the name of the top conviction tier that becomes structurally
      unreachable at the current gate (e.g. "Accumulate"), or None when all tiers are
      reachable.  Displayed as a regime banner on the page so the user knows that calls
      above this tier cannot appear regardless of individual sector setup.
    """
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

    # W0.4: staleness check — detect a frozen upstream that silently pins the gate.
    leg_stale: dict[str, int | None] = {}
    any_stale = False
    try:
        leg_stale = _regime_leg_staleness((rs or {}).get("legs"))
        any_stale = any(
            age is not None and age > _LEG_STALE_DAYS.get(k, 999)
            for k, age in leg_stale.items()
        )
        if any_stale:
            stale_names = [k for k, age in leg_stale.items()
                           if age is not None and age > _LEG_STALE_DAYS.get(k, 999)]
            log.warning(
                "central: regime leg(s) stale: %s — gate may be frozen at %.2f",
                stale_names, gate,
            )
    except Exception as e:  # noqa: BLE001
        log.debug("central: leg staleness check failed: %s", e)

    # W0.4: gate_caps_tier — surface which top tier is structurally blocked at this gate.
    # At gate < _GATE_ACCUMULATE_FLOOR the Accumulate tier (score ≥ 72) is unreachable
    # even with a perfect cycle state + validated pathway + maximum momentum confirmer.
    gate_caps_tier: str | None = None
    if gate < _GATE_ACCUMULATE_FLOOR:
        gate_caps_tier = "Accumulate"

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
        # W0.4 honesty fields
        "leg_stale": leg_stale,
        "any_stale": any_stale,
        "gate_caps_tier": gate_caps_tier,
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
def _rolling_over(now: dict) -> bool:
    """Fast-rollover detector (parity with engine.sector_central._rolling_over). The slow 5-phase
    label lags a sharp multi-week rollover, so a name down hard off a recent high can still read
    'Trending'. Keys only off fields the cycle record already carries (osc_slope / pos / pos_v2 /
    timing_state / signal / divergence) — no new data.

    Two arms (2026-07 rollover-lag audit, ported from the US detector — the original single
    arm never fired post-roll):
      • decline arm: oscillator falling + stretched + daily ladder still IN decline.
      • post-roll arm: oscillator in COLLAPSE (≤ −10) off an elevated position with a SELL
        turn signal / divergence / decline ladder. The original arm demanded pos ≥ 68 AND a
        DECLINE-family ladder — but a name that already fell has pos < 68 and its ladder has
        moved on to bottom-hunting (TURN SIGNALED), so the override never fired on a real
        rollover. No whipsaw on wiggles: every arm still needs a clearly falling oscillator
        plus stretch plus a confirming fast signal."""
    slope = now.get("osc_slope") or 0.0
    pv2 = now.get("pos_v2")
    pos_eff = pv2 if pv2 is not None else (now.get("pos") or 0)
    timing = (now.get("timing_state") or "").upper()
    hard_dn = timing in ("DECLINE", "ROLLING OVER")
    if slope < -3.0 and pos_eff >= 68.0 and hard_dn:
        return True
    confirm = bool(now.get("signal") == "SELL" or now.get("divergence") or hard_dn)
    return bool(slope <= -10.0 and pos_eff >= 50.0 and confirm)


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
    # fast-rollover override: don't let a lagging 'Trending' phase read a rolling-over name UP
    # (de-rate to cautious, never a lift). See _rolling_over.
    rolling = _rolling_over(now)
    if rolling:
        score = float(np.clip(min(score, -0.25), -1, 1))
    sig_d = now.get("signature") or {}
    return score, {"signature": sig, "phase": phase,
                   "label": sig_d.get("label"), "label_zh": sig_d.get("label_zh"),
                   "rolling": rolling}


def _forward_tilt(rec: dict) -> tuple[float | None, dict | None]:
    """The honest forward tilt. PRIMARY: china_sector_pathway conditional (4 GS sectors) — a
    display-only, evidence-gated conditioning input (NOT alpha, NOT a forecast). Returns a tilt
    in [-1,+1] scaled by sample confidence, or None where no pathway exists (then the cycle
    projection is rhythm-only).

    W2.6: the pathway's conditional now reports n_months + a DATE-BLOCKED bootstrap CI on the
    (cond − base) LIFT (era-stabilized composite). The old level-CI-straddles-base test is
    equivalent to lift-CI-straddles-0; effective independent sample (n_eff) is used for the
    confidence shrink because the overlapping monthly windows make raw n_months over-count.
    """
    pw = rec.get("pathway")
    if not pw:
        return None, None
    cond = pw.get("conditional") or {}
    h = cond.get("h6") or cond.get("h3")
    if not h:
        return None, {"has_pathway": True}
    lift = float(h.get("lift") or 0.0)               # cond_rate − base_rate
    n = int(h.get("n_months") or 0)
    n_eff = float(h.get("n_eff") or 0.0)
    lift_lo, lift_hi = h.get("lift_ci_lo"), h.get("lift_ci_hi")
    base = float(h.get("base_rate") or 0.5)
    # confidence: shrink the tilt when the LIFT CI straddles zero (no separation from base) or
    # the EFFECTIVE sample is small. With ~6-month overlap n_eff ≪ n_months, so confidence stays
    # honestly low even when raw n_months looks comfortable — the point of the W2.6 CI fix.
    straddles = (lift_lo is not None and lift_hi is not None and lift_lo <= 0.0 <= lift_hi)
    conf = float(np.clip((n_eff if n_eff > 0 else n) / 30.0, 0.2, 1.0)) * (0.5 if straddles else 1.0)
    tilt = float(np.clip(lift * 6.0, -1, 1)) * conf   # lift ~±0.17 → ~±1 before conf
    return tilt, {"cond_rate": h.get("cond_rate"), "base_rate": h.get("base_rate"),
                  "lift_ci_lo": lift_lo, "lift_ci_hi": lift_hi, "n_months": n, "n_eff": n_eff,
                  "h": h.get("h"), "tercile": (pw.get("setup") or {}).get("tercile"),
                  "composition_version": h.get("composition_version"),
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
        if state_d.get("rolling"):
            # the slow phase label lags; the fast signals say it has rolled over → surface that
            # instead of the stale 'Trending' read.
            t.append({"layer": "Cycle state", "tier": "validated", "stance": "bearish",
                      "en": f"Rolling over (signature {sig:.0f}/100) — oscillator falling, "
                            "daily ladder in decline (slow phase label lags)",
                      "zh": f"回落中（特征 {sig:.0f}/100）— 振荡指标下行、日线阶梯走弱（慢速阶段标签滞后）"})
        else:
            stance = "bullish" if sig <= 35 else "bearish" if sig >= 65 else "neutral"
            ph = state_d.get("phase")
            t.append({"layer": "Cycle state", "tier": "validated", "stance": stance,
                      "en": f"{state_d.get('label') or '—'} (signature {sig:.0f}/100), phase {ph}",
                      "zh": f"{state_d.get('label_zh') or state_d.get('label') or '—'}"
                            f"（特征 {sig:.0f}/100），阶段 {_PHASE_ZH.get(ph, ph or '—')}"})
    if fwd_d and fwd_d.get("cond_rate") is not None:
        cr, br = round(fwd_d["cond_rate"] * 100), round(fwd_d["base_rate"] * 100)
        stance = "bullish" if fwd_d.get("lift", 0) > 0.03 else "bearish" if fwd_d.get("lift", 0) < -0.03 else "neutral"
        # W2.6: report the block-bootstrap LIFT band (pp) + n_months/n_eff, never a raw
        # overlapping-window count as if independent; tier is "display" not "validated" (the
        # pathway is display-only conditioning — doctrine, not alpha; matches the caveat).
        lift_lo, lift_hi = fwd_d.get("lift_ci_lo"), fwd_d.get("lift_ci_hi")
        band = (f", lift {round((lift_lo)*100)}–{round((lift_hi)*100)}pp"
                if (lift_lo is not None and lift_hi is not None) else "")
        neff = fwd_d.get("n_eff")
        nstr = f"n={fwd_d.get('n_months')}mo" + (f", n_eff≈{neff}" if neff else "")
        t.append({"layer": "Forward odds", "tier": "display", "stance": stance,
                  "en": f"{cr}% forward-{fwd_d.get('h')}m positive vs {br}% base ({nstr}{band})",
                  "zh": f"未来{fwd_d.get('h')}个月上涨概率 {cr}%（基准 {br}%，月度样本 {fwd_d.get('n_months')}）"})
    rstance = "bullish" if (mkt.get("risk_on") or 0) > 0.1 else "bearish" if (mkt.get("risk_on") or 0) < -0.1 else "neutral"
    quad_name = mkt.get("quad_name")
    quad_zh = _QUAD_ZH.get(quad_name, quad_name) if quad_name else (mkt.get("quad") or "—")
    t.append({"layer": "Regime gate", "tier": "validated", "stance": rstance,
              "en": f"{mkt.get('state_en')} (de-risk {mkt.get('derisk_blended')}, {quad_name or mkt.get('quad') or '—'}, "
                    f"liquidity {mkt.get('liquidity') or '—'}) → gate ×{mkt.get('gate_factor')}",
              "zh": f"{mkt.get('state_zh') or mkt.get('state_en')}（降险 {mkt.get('derisk_blended')}，{quad_zh}）→ 门控 ×{mkt.get('gate_factor')}"})
    lead = mom_d.get("lead")
    t.append({"layer": "Momentum", "tier": "confirmer", "stance": lead,
              "en": f"RS #{mom_d.get('rs_rank') or '—'} — {lead}"
                    + (" (early — not yet confirmed by trend)" if early else ""),
              "zh": f"相对强度 #{mom_d.get('rs_rank') or '—'} — {_LEAD_ZH.get(lead, lead)}"
                    + ("（偏早 — 趋势尚未确认）" if early else "")})
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

    # --- truncation / staleness guard (sector-central-china-6) ---
    spine_degraded = False
    spine_degraded_reason = None
    n_spine_sectors = len(cyc.get("sectors", []))
    if n_spine_sectors < _SPINE_MIN_SECTORS:
        spine_degraded = True
        spine_degraded_reason = (
            f"spine has only {n_spine_sectors} sectors (< {_SPINE_MIN_SECTORS} min)"
            " — possible truncated akshare scrape"
        )
        log.warning("central: %s — convictions will be degraded", spine_degraded_reason)
    # check staleness
    spine_as_of_str = cyc.get("meta", {}).get("asOf")
    if spine_as_of_str:
        try:
            spine_as_of = pd.Timestamp(spine_as_of_str)
            today = pd.Timestamp.today().normalize()
            lag = (today - spine_as_of).days
            if lag > _SPINE_STALE_DAYS:
                stale_reason = (
                    f"spine asOf={spine_as_of_str} is {lag} days stale"
                    f" (>{_SPINE_STALE_DAYS})"
                )
                spine_degraded = True
                spine_degraded_reason = stale_reason
                log.warning("central: %s — convictions may reflect stale spine", stale_reason)
        except Exception:  # noqa: BLE001
            pass

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
                 "spine_degraded": spine_degraded,
                 "spine_degraded_reason": spine_degraded_reason,
                 "method": "gated-confluence (research/ALLOCATION_CHINA_AUDIT.md)"},
        "market": mkt,
        "sectors": sectors,
        "baskets": baskets,
    }


def _carry(rec: dict) -> dict:
    """Carry the identity + a compact cycle snapshot from the cycle record onto the central row."""
    now = rec.get("now") or {}
    # override the (lagging) slow label when the fast signals show a rollover, so the card chip
    # matches the de-rated conviction instead of reading 'Trending'.
    phase_label = "Rolling over" if _rolling_over(now) else now.get("phaseLabel")
    return {
        "id": rec.get("id"), "ticker": rec.get("ticker"), "kind": rec.get("kind"),
        "basket_id": rec.get("basket_id"), "shenwan_code": rec.get("shenwan_code"),
        "name": rec.get("name"), "name_zh": rec.get("name_zh"),
        "group": rec.get("group"), "group_zh": rec.get("group_zh"), "accent": rec.get("accent"),
        "etf_proxy": rec.get("etf_proxy"),
        "cycle": {"phase": now.get("phase"), "phaseLabel": phase_label,
                  "pos": now.get("pos"), "proj": rec.get("proj"),
                  "rs_rank": now.get("rs_rank"), "above200d": now.get("above200d")},
    }
