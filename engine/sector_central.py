"""US Sector Central Intelligence — the fuser that amalgamates the cycle map, the validated
absolute-trend drawdown gate, the macro regime posture, and the (audited) momentum / heat /
crowding CONTEXT into ONE per-sector intelligence record, with a transparent reasoning trace.

This is the US sister of engine.china_sector_central. It ports the gated-confluence skeleton
but rewires every leg to US-validated inputs — and the load-bearing difference is real:

  • In CHINA the absolute-trend gate FAILED Phase-0 (not a drawdown gate); momentum had no alpha.
  • In the US the absolute-trend gate is VALIDATED as a drawdown lever
    (data/strategies/thematic_rotation_phase0.json: region=us, gate_helps=true,
    verdict.absolute_trend_gate="validated_risk_control" — no mean-return edge, but materially
    lower vol & shallower drawdown: ew_buyhold sectors max_dd −0.49 vs gated top4_mom12_dual −0.24).

So the honest US confluence hierarchy is:

    where-are-we (cycle state)                                  →  LEAD  (rhythm, not a forecast)
    is the macro regime permissive? is it above its own trend?  →  GATE  (the validated levers)
    is it confirmed by momentum? heat? any crowding fragility?  →  CONFIRM / SIZE (capped context)
  → a conviction tier + a 0–100 confluence score + a human-readable reasoning trace.

HONESTY DISCIPLINE (the repo registry): US relative momentum rank-IC≈0 — a *focus lens*, not
alpha; the only statistically validated FORWARD signal is the trend gate's drawdown/staying-power
control, NOT a directional odds forecast (there is no US sector-pathway engine — we do not
fabricate one). The basket cycle math uses current-membership tape (survivorship-NOT-clean) →
baskets are CONTEXT, never a backtest claim. Every dated call is logged & graded
(engine.sector_central_grader). Intervals, not forecasts.

Pure-read + additive: any failure on a layer degrades gracefully; the cycle spine is the only
hard requirement.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# conviction tiers (score 0–100, after gate + context) — EN-first, zh kept for the bilingual UI
TIERS = [
    (72, "Accumulate",   "积极配置", "up"),
    (58, "Constructive", "建设性",   "up"),
    (43, "Neutral",      "中性",     "flat"),
    (30, "Cautious",     "谨慎",     "down"),
    (0,  "Reduce",       "减配",     "down"),
]

# zh for the reasoning-BODY tokens (this hub is EN-first, but the bilingual UI still
# renders the zh body — keep it from leaking raw English). Canonical zh mirrors the US
# sector-cycles page (templates/sector_cycles.js phase shorts) + the signal stacks (quads).
_PHASELABEL_ZH = {"Bottoming": "筑底", "Prime entry": "入场良机", "Trending": "上行",
                  "Topping": "见顶", "Rolling over": "回落"}
_PHASE_ZH = {"Trough": "筑底", "Recovery": "复苏", "Expansion": "扩张",
             "Peak": "见顶", "Downturn": "回落"}
_QUAD_ZH = {"Goldilocks": "理想增长", "Reflation": "再通胀", "Stagflation": "滞胀",
            "Growth-scare": "增长恐慌", "Growth scare": "增长恐慌",
            "Growth Scare": "增长恐慌", "Deflation": "通缩"}
_LEAD_ZH = {"leading": "领先", "lagging": "落后", "mid-pack": "中游"}
_SIGNAL_ZH = {"BUY": "买入", "SELL": "卖出"}

# SPDR sector ETF → Finviz heatmap sector vocabulary (the heatmap uses Finviz names, which
# differ from GICS — map before joining heat to a sector row). 11 clean entries.
SPDR_TO_FINVIZ = {
    "XLK": "Technology", "XLC": "Communication Services", "XLY": "Consumer Cyclical",
    "XLF": "Financial", "XLI": "Industrials", "XLB": "Basic Materials", "XLE": "Energy",
    "XLV": "Healthcare", "XLP": "Consumer Defensive", "XLU": "Utilities", "XLRE": "Real Estate",
}


# =========================================================================== #
# market context — the validated regime GATE + heatmap/flow display context
# =========================================================================== #
def _regime_anchor(latest: dict | None = None) -> dict:
    """The validated US risk posture. There is NO engine.masterminds.regime_state() to call;
    the US analogue is data/regime/latest.json + engine.conditions.macro_risk_score (the
    validated risk-OFF scalar). Returns a normalized market read with a risk-on scalar in
    [-1,+1] and a [0,1] gate factor for bullish convictions.

    `latest`: an already-assembled latest.json dict (the coherence assert passes the IN-MEMORY
    latest for THIS run — before it is written to disk — so the gate is validated against the
    same-run risk read, not the previous run's persisted file). Default None → read from disk."""
    d = latest if isinstance(latest, dict) and latest else {}
    if not d:
        try:
            p = config.data_dir() / "regime" / "latest.json"
            if p.exists():
                d = json.loads(p.read_text()) or {}
        except Exception as e:  # noqa: BLE001
            log.warning("central: regime latest.json unreadable: %s", e)

    quad, quad_name = d.get("quad"), d.get("quad_name")
    liquidity = d.get("liquidity_overlay") or d.get("liquidity")
    g_score, i_score = d.get("growth_score"), d.get("inflation_score")
    rstate = d.get("risk_state") or {}

    # validated risk-OFF scalar: macro_risk_score MRS in [0,1], higher = more risk-OFF.
    mrs = None
    try:
        from engine.conditions import macro_risk_score
        mrs = macro_risk_score(d)
    except Exception as e:  # noqa: BLE001
        log.warning("central: macro_risk_score failed: %s", e)
    mrs = mrs or (d.get("macro_risk") if isinstance(d.get("macro_risk"), dict) else None) or {}
    derisk = mrs.get("score")                       # 0..1, higher = more risk-off
    # flip to a risk-on scalar in [-1,+1] (+1 risk-on … −1 risk-off)
    risk_on = round(-(2.0 * float(derisk) - 1.0), 2) if derisk is not None else None

    quad_lean = {"Q1": 1, "Q2": 1, "Q3": -1, "Q4": -1}.get(quad)
    liq_lean = {"expanding": 1, "contracting": -1, "neutral": 0, "unknown": None}.get(liquidity)

    # gate factor for BULLISH convictions in [0,1]: risk-off shrinks long tilts (gating, not a
    # switch). Driven by the validated MRS; quad/liquidity nudge — identical arithmetic to China.
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
    # the validated LEADING risk-off tell (breadth divergence) one-way caps the gate
    caution = (((d.get("conditions") or {}).get("complacency") or {}).get("caution"))
    if caution:
        gate = min(gate, 0.85)
    gate = round(float(np.clip(gate, 0.2, 1.0)), 2)

    # the GATE posture (what actually drives the gate) is the validated MRS scalar — kept verbatim
    # as gate_state_* and surfaced as the banner sub-line. The gating arithmetic above is unchanged.
    r = risk_on or 0
    gate_state_en = "Risk-on" if r > 0.2 else "Risk-off" if r < -0.2 else "Neutral"
    gate_state_zh = "偏多" if r > 0.2 else "偏空" if r < -0.2 else "中性"

    # HEADLINE = the SAME radar-aware Market State verdict the macro page shows, so the two pages
    # can never disagree. The macro_risk leg above IGNORES the Risk Radar (that is exactly why this
    # page used to read "Risk-on" while macro.html read "Risk-off"); the Market State verdict does
    # not. Prefer the persisted nightly snapshot (byte-identical to macro.html); else recompute from
    # the same latest.json (radar-aware, sans the trend leg); else fall back to the gate label.
    state_en, state_zh = gate_state_en, gate_state_zh
    ms_verdict = ms_score = ms_color = radar_state = None
    try:
        from engine import market_state as _ms
        snap = _ms.load_persisted() or _ms.market_state_snapshot(d)
        if snap:
            state_en = snap.get("label_en") or state_en
            state_zh = snap.get("label_zh") or state_zh
            ms_verdict, ms_score, ms_color = snap.get("verdict"), snap.get("score"), snap.get("color")
            radar_state = (snap.get("radar") or {}).get("state")
    except Exception as e:  # noqa: BLE001
        log.warning("central: market_state unify failed: %s", e)

    return {
        "risk_on": risk_on, "gate_factor": gate,
        "state_en": state_en, "state_zh": state_zh,
        "gate_state_en": gate_state_en, "gate_state_zh": gate_state_zh,
        "ms_verdict": ms_verdict, "ms_score": ms_score, "ms_color": ms_color,
        "radar_state": radar_state,
        "tactical_label": rstate.get("label_en"), "tactical_label_zh": rstate.get("label_zh"),
        "risk_state_score": rstate.get("score"), "risk_state_state": rstate.get("state"),
        "headline_en": rstate.get("headline_en"), "headline_zh": rstate.get("headline_zh"),
        "derisk_blended": (round(float(derisk), 2) if derisk is not None else None),
        "mrs_label": mrs.get("label"), "mrs_components": mrs.get("components"),
        "quad": quad, "quad_name": quad_name, "liquidity": liquidity,
        "growth_score": g_score, "inflation_score": i_score,
        "caution": bool(caution),
        "validated": True,
    }


def _heat_table() -> dict:
    """Per-(Finviz)-sector cap-weighted heat + breadth from the Sector Heatmap feed
    (site/marketdata/sp500_heatmap.json). Display CONTEXT only — coincident color, never a lead.
    Python port of heatmap.js weightedPc/breadth (size_basis=='marketcap' → cap-weighted)."""
    out = {}
    try:
        site = config.ROOT / config.load()["storage"]["site_dir"]
        p = site / "marketdata" / "sp500_heatmap.json"
        if not p.exists():
            return {}
        hm = json.loads(p.read_text())
        cap_weighted = (hm.get("size_basis") != "weight_proxy")
        agg = {}
        for tile in hm.get("tiles", []):
            sec = tile.get("sector")
            if not sec:
                continue
            a = agg.setdefault(sec, {"w": 0.0, "ws": {}, "vals": {}, "adv": {}, "dec": {}})
            sz = float(tile.get("size") or 0.0)
            perf = tile.get("perf") or {}
            for tf, v in perf.items():
                if v is None:
                    continue
                v = float(v)
                a["ws"].setdefault(tf, 0.0)
                a["vals"].setdefault(tf, 0.0)
                a["adv"].setdefault(tf, 0)
                a["dec"].setdefault(tf, 0)
                if cap_weighted:
                    a["ws"][tf] += sz
                    a["vals"][tf] += sz * v
                else:
                    a["ws"][tf] += 1.0
                    a["vals"][tf] += v
                if v > 0:
                    a["adv"][tf] += 1
                elif v < 0:
                    a["dec"][tf] += 1
        for sec, a in agg.items():
            row = {}
            for tf in ("1D", "1M", "YTD"):
                w = a["ws"].get(tf, 0.0)
                row["heat_" + tf] = round(a["vals"][tf] / w, 2) if w else None
            adv, dec = a["adv"].get("1M", 0), a["dec"].get("1M", 0)
            row["adv"], row["dec"] = adv, dec
            row["breadth_pct"] = round(100.0 * adv / max(adv + dec, 1), 0)
            out[sec] = row
    except Exception as e:  # noqa: BLE001
        log.debug("central: heatmap aggregate failed: %s", e)
    return out


def market_context() -> dict:
    anc = _regime_anchor()
    # crowding fragility map (per-ticker; display/size context only) — degrades to {}
    crowd = {}
    try:
        from engine.crowding import compute_fragility
        crowd = compute_fragility() or {}
    except Exception as e:  # noqa: BLE001
        log.debug("central: compute_fragility failed: %s", e)
    return {**anc, "heat": _heat_table(), "_crowd_by_ticker": crowd}


# =========================================================================== #
# per-sector / per-basket confluence
# =========================================================================== #
def _rolling_over(now: dict) -> bool:
    """Fast-rollover detector. The slow 5-phase label (`phase`) is weekly-MACD-led, so a name
    that has dropped hard off a recent high can still read 'Trending/Expansion' for weeks after
    it rolled — the label LAGS the move. Keys only off signals the cycle record already carries
    (osc_slope / pos / pos_v2 / timing_state / signal / divergence) — no new data.

    Two arms (2026-07 audit — the original single arm never fired on the June rollover):
      • decline arm: oscillator falling + stretched + daily ladder still IN decline.
      • post-roll arm: oscillator in COLLAPSE (≤ −10) off an elevated position with a SELL
        turn signal / divergence / decline ladder. The original arm demanded pos ≥ 68 AND a
        DECLINE-family ladder — but a name that already fell has pos < 68 and its ladder has
        moved on to bottom-hunting (TURN SIGNALED), so XLK/AI-infra rolled −20/−30 osc points
        with the chip stuck on the slow label. No whipsaw on wiggles: every arm still needs a
        clearly falling oscillator plus stretch plus a confirming fast signal."""
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
    """Where-are-we, from the cycle-position oscillator + phase direction. The US cycle record
    has NO `signature` field (unlike China) — key off `pos` (0–100 oscillator: low = washed-out =
    bullish setup, high = stretched), its slope, the 5-phase wheel, and the BUY/SELL turn signal.
    Returns a setup score in [-1,+1] (washed-out + turning up = +1) + a descriptor."""
    pos = now.get("pos")
    # pos 0=washout(bullish setup) … 100=stretched(bearish). Map to [-1,+1] like China's signature.
    setup = (50.0 - float(pos)) / 50.0 if pos is not None else 0.0
    phase = now.get("phase")
    phase_dir = {"Trough": 0.5, "Recovery": 0.6, "Expansion": 0.25,
                 "Peak": -0.4, "Downturn": -0.55}.get(phase, 0.0)
    score = float(np.clip(0.6 * setup + 0.4 * phase_dir, -1, 1))
    sig = now.get("signal")
    if sig == "BUY":
        score = float(np.clip(score + 0.12, -1, 1))
    elif sig == "SELL":
        score = float(np.clip(score - 0.12, -1, 1))
    # fast-rollover override: the slow phase label lags a sharp multi-week rollover, so don't let a
    # stale 'Trending' read a rolling-over name UP. De-rate to cautious (never a lift). See
    # _rolling_over: needs oscillator falling + stretched (detrended) + daily ladder in decline.
    rolling = _rolling_over(now)
    if rolling:
        score = float(np.clip(min(score, -0.25), -1, 1))
    return score, {"pos": pos, "phase": phase, "phaseLabel": now.get("phaseLabel"),
                   "signal": sig, "osc_slope": now.get("osc_slope"), "rolling": rolling}


def _momentum_confirm(now: dict, n_peers: int) -> tuple[float, dict]:
    """CONFIRMER (capped ±0.3, never alpha): RS leadership rank + trend direction. A leading,
    above-trend sector CONFIRMS a constructive call; a lagging one flags it as 'early'. US
    relative momentum has rank-IC≈0 — a focus lens, not a forecast (hence the hard cap)."""
    rank = now.get("rs_rank")
    above = now.get("above200d")
    rs63 = now.get("rs_63d")
    rs21 = now.get("rs_21d")
    rank21 = now.get("rs_21d_rank")
    pct = (1.0 - (rank - 1) / max(n_peers - 1, 1)) if rank else 0.5   # 1=leader
    c = (pct - 0.5) * 0.6                                              # ±0.3
    if above is False:
        c -= 0.1
    c = float(np.clip(c, -0.3, 0.3))
    # the TAG reads the fast (21d) rank when stamped — the 63d rank kept XLK "leading"
    # three weeks after its top (2026-07 audit); the capped score nudge above stays on
    # the legacy 63d rank so graded conviction semantics don't shift mid-ledger.
    rank_now = rank21 if rank21 is not None else rank
    lead = ("leading" if (rank_now or 99) <= max(3, n_peers // 4) else
            "lagging" if (rank_now or 0) >= n_peers - max(3, n_peers // 4) else "mid-pack")
    fading = bool(rank and rank21 and rank <= max(3, n_peers // 4) and rank21 > n_peers // 2)
    return c, {"rs_rank": rank, "rs_63d": rs63, "rs_21d": rs21, "rs_21d_rank": rank21,
               "above_200d": above, "lead": lead, "fading": fading}


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


def _fuse(rec: dict, mkt: dict, n_peers: int, trend: dict | None = None,
          heat: dict | None = None, members: list | None = None) -> dict:
    """The gated-confluence conviction for one sector/basket + the reasoning trace."""
    now = rec.get("now") or {}
    state, state_d = _state_score(now)
    mom, mom_d = _momentum_confirm(now, n_peers)
    crowd = _crowd_for_members(members or [], mkt.get("_crowd_by_ticker", {}))

    # LEAD: cycle state only. There is NO US sector-pathway engine — we do NOT fabricate a
    # directional odds forecast. The validated FORWARD axis is the trend gate (applied below),
    # surfaced as a GATE, not a probability tilt.
    lead = state

    # GATE 1 — macro regime, differentiated PER SECTOR by macro beta (the US-only lever):
    # in risk-off, cyclicals (high beta) are gated harder than defensives (negative beta).
    gate = mkt.get("gate_factor", 0.7)
    beta = 0.0
    try:
        from engine.conditions import sector_macro_beta
        beta = sector_macro_beta(_as_str(rec.get("ticker")) or rec.get("name"))
    except Exception:  # noqa: BLE001
        beta = 0.0
    risk_on = mkt.get("risk_on") or 0.0
    gate_eff = float(np.clip(gate * (1.0 + 0.25 * beta * risk_on), 0.2, 1.0))
    if lead > 0:
        gated = lead * gate_eff
    else:
        gated = lead * (2.0 - gate_eff)          # risk-off amplifies a bearish read
    gated = float(np.clip(gated, -1, 1))

    # GATE 2 — the VALIDATED absolute-trend drawdown gate (US gate_helps=true). Below own 200dma
    # or negative 12m = drawdown/staying-power risk → de-rate a bullish conviction (the validated
    # risk-control action). Above trend = permissive. This is the genuine US forward lever.
    trend_pass = (trend or {}).get("pass")
    if trend_pass is False and gated > 0:
        gated *= 0.5
    gated = float(np.clip(gated, -1, 1))

    # CONFIRM: capped momentum nudge
    raw = float(np.clip(gated + 0.5 * mom, -1, 1))
    score = round((raw + 1.0) / 2.0 * 100)

    # CONFLUENCE: how many of the validated layers (state / trend-gate / regime) agree with dir
    dir_sign = 1 if raw > 0.05 else -1 if raw < -0.05 else 0
    tg_sign = 1 if trend_pass is True else -1 if trend_pass is False else 0
    layers_sign = [np.sign(state), tg_sign,
                   (1 if risk_on > 0.1 else -1 if risk_on < -0.1 else 0)]
    agree = sum(1 for s in layers_sign if dir_sign != 0 and s == dir_sign)
    confluence = {"agree": int(agree), "of": 3,
                  "label": ("high" if agree >= 3 else "moderate" if agree == 2 else "low/mixed")}

    en, zh, _dir = _tier_for(score)
    # caps: a below-trend name can't be top-tier (validated drawdown control); a stretched or
    # crowded name can't be top-tier (fragility — down-size, never fade the leader).
    stretched = (state_d.get("pos") or 0) >= 80
    if trend_pass is False and score >= 58:
        score = min(score, 57); en, zh, _dir = _tier_for(score)
    if (stretched or (crowd and crowd["frac"] >= 0.34)) and score >= 58:
        score = min(score, 57); en, zh, _dir = _tier_for(score)

    # W4.6 — fitted RISK-channel SIZE cap (additive, capped, traced). The ladder state's
    # vol-residualized forward-drawdown multiplier (data/regime/ladder_risk_calibration.json)
    # is a SIZE lever ONLY: a value < 1.0 shaves a bullish conviction toward neutral (deeper
    # tail → size down); it NEVER lifts a score and never touches direction. Per the W4.6
    # verdict every cell currently ships 1.0 (no risk-sizing signal survived FDR), so this is
    # presently a no-op — but it is wired so a future price-basis re-fit binds automatically.
    fam = rec.get("family") or ("us_sector" if rec.get("kind") == "sector" else None)
    size_mult = 1.0
    try:
        from engine.cycles import risk_size_mult as _rsm
        size_mult = float(_rsm(now.get("timing_state") or "", fam))
    except Exception:  # noqa: BLE001
        size_mult = 1.0
    if size_mult < 1.0 and score > 50:
        # shave the ABOVE-neutral portion of the score by the size multiplier (never below 50,
        # never a lift). This is the size cap; direction (the sign around 50) is untouched.
        score = int(round(50 + (score - 50) * size_mult))
        en, zh, _dir = _tier_for(score)
    # bullish lead but lagging momentum → mark "early" (don't over-promise on a focus-lens leg)
    early = raw > 0 and mom_d.get("lead") == "lagging"

    forward = _forward_view(trend, rec.get("cycle", {}).get("proj") or rec.get("proj"))
    trace = _trace(state_d, forward, mkt, mom_d, crowd, early, stretched, beta, heat)
    return {
        "conviction": {"score": int(score), "label_en": en, "label_zh": zh,
                       "dir": _dir, "early": bool(early), "confluence": confluence},
        "forward": forward, "state": state_d, "momentum": mom_d, "crowding": crowd,
        "heat": heat,
        "components": {"state": round(state, 2), "forward": None,
                       "lead": round(lead, 2), "gate_factor": gate, "gate_eff": round(gate_eff, 2),
                       "macro_beta": round(float(beta), 2), "trend_pass": trend_pass,
                       "gated": round(gated, 2), "momentum": round(mom, 2),
                       "raw": round(raw, 2), "risk_size_mult": round(size_mult, 3),
                       "weighting": "state→gate(regime×β + trend)→confirm→risk-size-cap"},
        "reasoning": trace,
    }


def _forward_view(trend: dict | None, proj: dict | None) -> dict:
    """The honest forward panel: the validated trend-gate state + the cycle-rhythm projection.
    NOT a directional odds forecast — intervals & staying-power, not a probability."""
    t = trend or {}
    out = {"trend_pass": t.get("pass"), "above_200dma": t.get("above_200dma"),
           "ret_12m": t.get("ret_12m"), "pos_12m": t.get("pos_12m"), "source": t.get("source")}
    if proj:
        out["proj_tilt"] = proj.get("tilt")
        out["next_turn"] = proj.get("nextTurn") or proj.get("central")
        out["window"] = ([proj.get("low"), proj.get("high")]
                         if proj.get("low") and proj.get("high") else None)
    return out


def _trace(state_d, fwd, mkt, mom_d, crowd, early, stretched, beta, heat) -> list[dict]:
    """Human-readable, tier-tagged reasoning trace (the 'deep reasoning' surface)."""
    t = []
    pos = state_d.get("pos")
    if pos is not None:
        if state_d.get("rolling"):
            # the slow phase label lags; the fast signals say it has rolled over → surface that
            # instead of the stale 'Trending' read (keeps the board honest vs. a −20% pullback).
            t.append({"layer": "Cycle state", "tier": "validated", "stance": "bearish",
                      "en": f"Rolling over — position {pos:.0f}/100 · oscillator falling "
                            "hard off a stretched read (slow phase label lags)",
                      "zh": f"回落中 — 位置 {pos:.0f}/100 · 振荡指标自高位急跌（慢速阶段标签滞后）"})
        else:
            stance = "bullish" if pos <= 40 else "bearish" if pos >= 65 else "neutral"
            sig = state_d.get("signal")
            sigtxt = f" · turn signal {sig}" if sig else ""
            sigtxt_zh = f" · 转向信号 {_SIGNAL_ZH.get(sig, sig)}" if sig else ""
            plab = state_d.get("phaseLabel")
            ph = state_d.get("phase")
            plab_zh = (_PHASELABEL_ZH.get(plab) if plab else None) or _PHASE_ZH.get(ph, plab or ph or "—")
            t.append({"layer": "Cycle state", "tier": "validated", "stance": stance,
                      "en": f"{plab or ph or '—'} — position {pos:.0f}/100{sigtxt}",
                      "zh": f"{plab_zh} — 位置 {pos:.0f}/100{sigtxt_zh}"})
    # the validated trend gate (forward axis)
    tp = (fwd or {}).get("trend_pass")
    if tp is not None:
        r12 = (fwd or {}).get("ret_12m")
        r12txt = (f"{r12 * 100:+.0f}% 12m" if r12 is not None else "12m —")
        r12txt_zh = (f"12个月{r12 * 100:+.0f}%" if r12 is not None else "12个月 —")
        stance = "bullish" if tp else "bearish"
        en = ("above its own 200-day trend & " + r12txt + " — drawdown gate OPEN") if tp else \
             ("below its own 200-day trend / " + r12txt + " — drawdown gate SHUT (longs de-rated)")
        zh = ("位于自身200日趋势之上且" + r12txt_zh + " — 回撤门控开启") if tp else \
             ("跌破自身200日趋势/" + r12txt_zh + " — 回撤门控关闭（多头降级）")
        t.append({"layer": "Trend gate", "tier": "validated", "stance": stance, "en": en, "zh": zh})
    # regime gate
    rstance = "bullish" if (mkt.get("risk_on") or 0) > 0.1 else "bearish" if (mkt.get("risk_on") or 0) < -0.1 else "neutral"
    betatxt = (" · cyclical (β+)" if beta > 0.3 else " · defensive (β−)" if beta < -0.3 else "")
    betatxt_zh = (" · 周期性（β+）" if beta > 0.3 else " · 防御性（β−）" if beta < -0.3 else "")
    quad_name = mkt.get("quad_name")
    quad_zh = _QUAD_ZH.get(quad_name, quad_name) if quad_name else (mkt.get("quad") or "—")
    t.append({"layer": "Regime gate", "tier": "validated", "stance": rstance,
              "en": f"{mkt.get('gate_state_en') or mkt.get('state_en')} (MRS {mkt.get('derisk_blended')}, {quad_name or mkt.get('quad') or '—'}, "
                    f"liquidity {mkt.get('liquidity') or '—'}) → gate ×{mkt.get('gate_factor')}{betatxt}",
              "zh": f"{mkt.get('gate_state_zh') or mkt.get('state_zh') or mkt.get('gate_state_en') or mkt.get('state_en')}（宏观风险 {mkt.get('derisk_blended')}，{quad_zh}）→ 门控 ×{mkt.get('gate_factor')}{betatxt_zh}"})
    lead = mom_d.get("lead")
    rk21, rk63 = mom_d.get("rs_21d_rank"), mom_d.get("rs_rank")
    rk_en = (f"RS 21d #{rk21} · 63d #{rk63 or '—'}" if rk21 is not None
             else f"RS #{rk63 or '—'}")
    rk_zh = (f"相对强度 21日 #{rk21} · 63日 #{rk63 or '—'}" if rk21 is not None
             else f"相对强度 #{rk63 or '—'}")
    fading = mom_d.get("fading")
    t.append({"layer": "Momentum", "tier": "confirmer",
              "stance": ("caution" if fading else lead),
              "en": f"{rk_en} — {lead} (focus lens, not alpha)"
                    + (" · 63d leader fading on 21d" if fading else "")
                    + (" · early — not yet trend-confirmed" if early else ""),
              "zh": f"{rk_zh} — {_LEAD_ZH.get(lead, lead)}（聚焦视角，非超额）"
                    + (" · 63日领先、21日转弱" if fading else "")
                    + (" · 偏早 — 趋势尚未确认" if early else "")})
    if heat and heat.get("heat_1M") is not None:
        hstance = "bullish" if (heat.get("heat_1M") or 0) > 0 else "bearish"
        t.append({"layer": "Heat", "tier": "display", "stance": hstance,
                  "en": f"breadth {heat.get('breadth_pct')}% adv · {heat.get('heat_1M'):+.1f}% 1M (cap-wt)",
                  "zh": f"宽度 {heat.get('breadth_pct')}% 上涨 · 近月 {heat.get('heat_1M'):+.1f}%（市值加权）"})
    if crowd:
        t.append({"layer": "Crowding", "tier": "display", "stance": "caution",
                  "en": f"{crowd['n_crowded']}/{crowd['n_members']} members crowded-fragile → size down",
                  "zh": f"{crowd['n_crowded']}/{crowd['n_members']} 只成分拥挤脆弱 → 降低仓位"})
    if stretched:
        t.append({"layer": "Fragility", "tier": "display", "stance": "caution",
                  "en": "stretched/extended — conviction capped", "zh": "拉伸/过热 — 信念封顶"})
    return t


# =========================================================================== #
# trend gates (the validated drawdown lever) — per row
# =========================================================================== #
def _trend_gates(closes, rotation) -> dict:
    """id → {pass, above_200dma, ret_12m, pos_12m, source}. SECTORS use the validated SPDR
    universe (engine.narrative_rotation._abs_gate on the ETF's own close); BASKETS reuse the
    narrative-rotation per-theme gate (context — the basket universe is survivorship-NOT-clean)."""
    gates = {}
    try:
        from engine.narrative_rotation import _abs_gate
    except Exception as e:  # noqa: BLE001
        log.warning("central: cannot import _abs_gate: %s", e)
        return gates
    # sectors: validated SPDR universe, keyed by id = ticker.lower()
    if closes is not None and not closes.empty:
        for tk in SPDR_TO_FINVIZ:
            if tk in closes.columns:
                try:
                    ok, g = _abs_gate(closes[tk].dropna())
                    gates[tk.lower()] = {**g, "pass": bool(ok), "source": "spdr"}
                except Exception:  # noqa: BLE001
                    pass
    # baskets: per-theme gate from narrative rotation, keyed by id = "b-"+theme_id
    for r in (rotation or {}).get("ranks", []) or []:
        bid = r.get("id")
        if bid is None:
            continue
        gates["b-" + str(bid)] = {**(r.get("gate") or {}), "pass": r.get("eligible"),
                                  "source": "basket-ctx"}
    return gates


# ---------------------------------------------------------------------------
# XSR-R2 / XSR-R9 helpers — fast-rotation attach, board sort, split view
# ---------------------------------------------------------------------------

# Conviction label → tier integer (highest = most bullish)
_CONVICTION_TIER: dict[str, int] = {
    "Accumulate":   5,
    "Constructive": 4,
    "Neutral":      3,
    "Cautious":     2,
    "Reduce":       1,
}

# Plain-word copy for split_view (XSR-R9).  Banned vocab: governor, OB, MACD,
# mom20, state names.  "fast tape" = the fast rotation lens; "slow clock" = the
# gated-confluence conviction.
_SPLIT_COPY_EN = {
    "faster":  "Slow clock: {conv}. Fast tape: money rotating in — split view.",
    "slower":  "Slow clock: {conv}. Fast tape: rotating out — split view.",
}
_SPLIT_COPY_ZH = {
    "faster":  "慢时钟：{conv}。快线：资金流入中 — 分歧视角。",
    "slower":  "慢时钟：{conv}。快线：资金流出 — 分歧视角。",
}

# Plain-word equivalents for the conviction labels in split copy
_CONV_PLAIN_EN: dict[str, str] = {
    "Accumulate":   "looking extended after the run",
    "Constructive": "constructive on the trend",
    "Neutral":      "neutral, no strong lean",
    "Cautious":     "cautious",
    "Reduce":       "risk looks elevated",
}
_CONV_PLAIN_ZH: dict[str, str] = {
    "Accumulate":   "强势延伸后偏高位",
    "Constructive": "趋势建设性",
    "Neutral":      "中性，无明显倾向",
    "Cautious":     "偏谨慎",
    "Reduce":       "风险较高",
}

# XSR-W1b: plain-word translations for rotation state_used enum.
# Tier 1 (glance) must never expose internal enum names (banned vocab).
# EN and ZH phrases kept short: fits in a chip label (≤4 words guideline).
# These are display-only labels; the full state name is retained in hover/receipt.
_STATE_PLAIN_EN: dict[str, str] = {
    "FRESH BUY":           "money moving in",
    "TURN SIGNALED":       "watching for entry",
    "CONFIRMING TURN":     "turn in progress",
    "RALLY ON":            "trend running",
    "TOP WATCH":           "extended — watch",
    "ROLLING OVER":        "rolling over",
    "BOTTOM WATCH":        "washed out — watch",
    "COUNTERTREND BOUNCE": "bounce, not a turn",
    "DECLINE":             "declining",
}
_STATE_PLAIN_ZH: dict[str, str] = {
    "FRESH BUY":           "资金流入",
    "TURN SIGNALED":       "关注入场",
    "CONFIRMING TURN":     "拐点进行中",
    "RALLY ON":            "趋势延伸",
    "TOP WATCH":           "偏高位 — 观察",
    "ROLLING OVER":        "趋势转弱",
    "BOTTOM WATCH":        "超跌 — 观察",
    "COUNTERTREND BOUNCE": "反弹非拐点",
    "DECLINE":             "下行中",
}


def _rotation_rank_bucket(rank: int, n_total: int) -> int:
    """Map rotation_rank to a tier int 1–5 (5 = best) within its universe.

    Per-kind: top ~18% → 5, then roughly quintile-ish buckets.
    Documented thresholds (11 sectors example):
        rank 1-2  → 5  (top 18%)
        rank 3-4  → 4
        rank 5-7  → 3
        rank 8-9  → 2
        rank 10-11 → 1
    Generalised to any N with ceiling-division.
    """
    if rank is None or n_total is None or n_total < 1:
        return 0  # unmatched / unknown
    top18 = max(1, round(n_total * 0.18))
    if rank <= top18:
        return 5
    # remaining N-top18 split into 4 roughly equal buckets
    rem = n_total - top18
    bucket_size = max(1, rem / 4.0)
    pos_in_rem = rank - top18  # 1-indexed
    if pos_in_rem <= bucket_size:
        return 4
    if pos_in_rem <= 2 * bucket_size:
        return 3
    if pos_in_rem <= 3 * bucket_size:
        return 2
    return 1


def _load_rotation_artifact() -> dict:
    """Load data/us_sector_rotation/latest.json.

    Returns an empty dict on any error (fail-open: callers degrade gracefully).
    """
    import datetime as _dt
    try:
        p = config.data_dir() / "us_sector_rotation" / "latest.json"
        if not p.exists():
            log.debug("sector_central: rotation artifact absent — conviction sort retained")
            return {}
        raw = json.loads(p.read_text(encoding="utf-8"))
        # Freshness guard: if artifact is >48h old, skip re-ordering
        ts_str = raw.get("ts") or raw.get("asof")
        if ts_str:
            try:
                from datetime import timezone as _tz
                ts_dt = _dt.datetime.fromisoformat(str(ts_str))
                # Treat naive datetimes as UTC
                if ts_dt.tzinfo is None:
                    ts_dt = ts_dt.replace(tzinfo=_tz.utc)
                age_h = (_dt.datetime.now(_tz.utc) - ts_dt).total_seconds() / 3600
                if age_h > 48:
                    log.warning("sector_central: rotation artifact stale (%.1fh) — conviction sort retained", age_h)
                    return {}
            except Exception:
                pass  # unparseable ts — accept the artifact anyway
        return raw
    except Exception as e:  # noqa: BLE001
        log.warning("sector_central: rotation artifact load failed (%s) — conviction sort retained", e)
        return {}


def _attach_rotation(records: list[dict], rotation_raw: dict, kind: str) -> list[dict]:
    """Attach rotation block to each record and re-sort by rotation_rank ascending.

    If rotation_raw is empty or parsing fails, returns records in conviction order
    (unchanged).  Unmatched records sort last (by conviction score descending as
    tiebreaker among themselves).

    Matching is kind-aware: a record with kind=='sector' may only match a rotation
    instrument that also has kind=='sector'; a record with kind=='basket' may only
    match a rotation instrument with kind=='basket'.  This prevents the 11
    b-us_sector_* proxy-basket records from borrowing a sector's rank via ticker
    match — those proxies now receive rotation=None and sort among unmatched by
    conviction score.

    Also sets split_view / split_copy_en / split_copy_zh (XSR-R9) when the
    conviction tier and rotation tier diverge by ≥ 2.  Split-view tier math for
    baskets is computed only over genuinely-matched basket records.
    """
    instruments_raw = rotation_raw.get("instruments") if rotation_raw else None
    if not rotation_raw or not instruments_raw or not isinstance(instruments_raw, list):
        # fail-open: no rotation data (or malformed) → conviction sort already applied
        for rec in records:
            rec["rotation"] = None
        return records

    # Build lookup: (kind, key) → rotation instrument record.
    # Separate tables keyed by (kind, id), (kind, ticker), (kind, basket_id) so
    # a sector record can never match a basket instrument and vice versa.
    rot_by_id: dict[tuple[str, str], dict] = {}
    rot_by_ticker: dict[tuple[str, str], dict] = {}
    rot_by_basket: dict[tuple[str, str], dict] = {}
    for inst in instruments_raw:
        inst_kind = inst.get("kind") or ""
        iid = inst.get("id") or inst.get("key") or ""
        tk = (inst.get("ticker") or "").upper()
        bid = inst.get("basket_id") or ""
        if iid:
            rot_by_id[(inst_kind, iid)] = inst
        if tk:
            rot_by_ticker[(inst_kind, tk)] = inst
        if bid:
            rot_by_basket[(inst_kind, bid)] = inst

    # First pass: match records to rotation instruments (kind-aware)
    matched_pairs: list[tuple[dict, dict]] = []  # (rec, inst)
    unmatched: list[dict] = []

    for rec in records:
        rec_kind = rec.get("kind") or ""
        rid = rec.get("id") or ""
        ticker = (rec.get("ticker") or "").upper()
        basket_id = rec.get("id") or ""  # sector_central uses id as basket_id

        inst = (
            rot_by_id.get((rec_kind, rid))
            or rot_by_id.get((rec_kind, rid.lstrip("b-")))
            or rot_by_ticker.get((rec_kind, ticker))
            or rot_by_basket.get((rec_kind, basket_id))
            or rot_by_basket.get((rec_kind, "b-" + basket_id))
        )

        if inst is None:
            rec["rotation"] = None
            unmatched.append(rec)
        else:
            matched_pairs.append((rec, inst))

    # Sort matched pairs by global rotation_rank (score tiebreak) — determines
    # per-kind display order and the per-kind ordinal rank for split-tier math.
    matched_pairs.sort(key=lambda t: (t[1].get("rotation_rank") or 9999,
                                      -(t[1].get("rotation_score") or 0.0)))

    # Per-kind ordinal rank: position in the sorted matched list (1-indexed).
    # This is semantically correct for _rotation_rank_bucket — the bucket function
    # measures where this instrument sits among its own kind (sectors or baskets),
    # not in the global mixed-kind ranking.
    n_total = len(matched_pairs) if matched_pairs else 1

    matched: list[dict] = []
    for per_kind_ordinal, (rec, inst) in enumerate(matched_pairs, 1):
        rrank = inst.get("rotation_rank")   # global rank (stored; for display/hover)
        rscore = inst.get("rotation_score")
        state = inst.get("state_used")
        components = inst.get("components") or {}
        stale = bool(inst.get("stale_flags"))

        rec["rotation"] = {
            "rank":        rrank,            # global rank (1-indexed across all kinds; hover receipt)
            "ordinal":     per_kind_ordinal, # per-kind display rank (e.g. #2 of 11 sectors)
            "n_matched":   n_total,          # total matched in this kind universe (11 for sectors)
            "score":       rscore,
            "state":       state,            # internal enum — hover/receipt only, never tier-1
            "state_plain_en": _STATE_PLAIN_EN.get((state or "").upper(), ""),
            "state_plain_zh": _STATE_PLAIN_ZH.get((state or "").upper(), ""),
            "components":  components,
            "stale":       stale,
        }

        # XSR-R9: split view.  Use per-kind ordinal position for bucket math so
        # the tier comparison is within-universe (11 sectors vs 11 sectors, not
        # sector #7 of 46 instruments).
        conv_label = (rec.get("conviction") or {}).get("label_en", "")
        conv_tier = _CONVICTION_TIER.get(conv_label, 0)
        rot_tier = _rotation_rank_bucket(per_kind_ordinal, n_total)

        diff = rot_tier - conv_tier  # positive = faster than conviction
        if abs(diff) >= 2 and conv_tier > 0 and rot_tier > 0:
            direction = "faster" if diff > 0 else "slower"
            plain_en = _CONV_PLAIN_EN.get(conv_label, conv_label.lower())
            plain_zh = _CONV_PLAIN_ZH.get(conv_label, conv_label)
            rec["split_view"] = True
            rec["split_copy_en"] = _SPLIT_COPY_EN[direction].format(conv=plain_en)
            rec["split_copy_zh"] = _SPLIT_COPY_ZH[direction].format(conv=plain_zh)
        else:
            rec["split_view"] = False
            rec["split_copy_en"] = None
            rec["split_copy_zh"] = None

        matched.append(rec)

    # Unmatched sort by conviction score descending (preserve their relative order)
    unmatched.sort(key=lambda x: -(x.get("conviction") or {}).get("score", 0))

    return matched + unmatched


def compute() -> dict | None:
    """Top-level: fuse the cycle spine + market regime + trend gates + heat/crowding into
    per-sector and per-basket central intelligence records, ranked by conviction."""
    try:
        from engine import sector_cycles as sc
        cyc = sc.compute()
    except Exception as e:  # noqa: BLE001
        log.error("central: cycle spine failed: %s", e)
        return None
    if not cyc or not cyc.get("sectors"):
        return None
    mkt = market_context()
    heat = mkt.get("heat", {})

    # the validated trend gates need the close panel (sectors) + the rotation gate (baskets)
    closes = None
    try:
        from engine.inputs import yahoo_closes
        closes = yahoo_closes()
    except Exception as e:  # noqa: BLE001
        log.warning("central: yahoo_closes failed: %s", e)
    rotation = None
    try:
        from engine.narrative_rotation import compute_narrative_rotation
        rotation = compute_narrative_rotation(region="us")
    except Exception as e:  # noqa: BLE001
        log.debug("central: narrative rotation unavailable: %s", e)
    trend = _trend_gates(closes, rotation)

    # basket membership (for crowding aggregation) — data/baskets/membership.json, members[].symbol
    memb = {}
    try:
        f = config.data_dir() / "baskets" / "membership.json"
        if f.exists():
            mm = (json.loads(f.read_text(encoding="utf-8")) or {}).get("baskets", {}) or {}
            for bid, b in mm.items():
                memb[bid] = [m.get("symbol") for m in (b.get("members") or []) if m.get("symbol")]
    except Exception:  # noqa: BLE001
        memb = {}

    n_sec = len(cyc["sectors"])
    sectors = []
    for rec in cyc["sectors"]:
        carried = _carry(rec)
        finviz = SPDR_TO_FINVIZ.get(rec.get("ticker"))
        h = heat.get(finviz) if finviz else None
        fused = _fuse(rec, mkt, n_sec, trend=trend.get(rec.get("id")), heat=h)
        sectors.append({**carried, **fused})
    n_bsk = max(len(cyc.get("baskets", [])), 1)
    baskets = []
    for rec in cyc.get("baskets", []):
        carried = _carry(rec)
        bid = (rec.get("id") or "")[2:] if (rec.get("id") or "").startswith("b-") else rec.get("id")
        fused = _fuse(rec, mkt, n_bsk, trend=trend.get(rec.get("id")),
                      members=memb.get(bid, []))
        baskets.append({**carried, **fused})

    # XSR-R2: primary sort is conviction score (will be replaced by rotation rank below).
    # This establishes the fallback order used when rotation artifact is absent.
    sectors.sort(key=lambda x: -x["conviction"]["score"])
    baskets.sort(key=lambda x: -x["conviction"]["score"])

    # XSR-R2/R9: load rotation artifact and re-sort by fast-rotation rank.
    # Fail-open: if artifact missing/stale/unparseable, conviction sort is kept and
    # rotation fields are null on all records.
    rotation_raw = _load_rotation_artifact()
    sectors = _attach_rotation(sectors, rotation_raw, kind="sector")
    baskets = _attach_rotation(baskets, rotation_raw, kind="basket")

    n_above = sum(1 for s in sectors if (s.get("forward") or {}).get("trend_pass") is True)
    mkt.pop("_crowd_by_ticker", None)
    mkt["n_above_trend"] = n_above
    mkt["n_sectors"] = len(sectors)
    rotation_armed = bool(rotation_raw and rotation_raw.get("instruments"))
    mkt["rotation_board_order"] = "fast-lens" if rotation_armed else "conviction"

    return {
        "as_of": cyc["meta"]["asOf"],
        "meta": {"n_sectors": len(sectors), "n_baskets": len(baskets),
                 "region": "us", "experimental": True,
                 "method": "gated-confluence (trend gate validated_risk_control, "
                           "data/strategies/thematic_rotation_phase0.json)",
                 "board_order": "fast-lens (XSR-R2)" if rotation_armed else "conviction"},
        "market": mkt,
        "sectors": sectors,
        "baskets": baskets,
    }


def _as_str(v) -> str | None:
    """Some baskets carry a LIST etf_proxy (e.g. defensives → ['XLP','XLU']). Flatten to a
    string so the value is parquet-safe and hashable (sector_macro_beta lookups, JSON display)."""
    if isinstance(v, (list, tuple)):
        return "/".join(str(x) for x in v) or None
    return v


def _carry(rec: dict) -> dict:
    """Carry the identity + a compact cycle snapshot from the cycle record onto the central row."""
    now = rec.get("now") or {}
    # the displayed phase-label chip: override the (lagging) slow label when the fast signals show
    # a rollover, so the card chip matches the de-rated conviction instead of reading 'Trending'.
    phase_label = "Rolling over" if _rolling_over(now) else now.get("phaseLabel")
    return {
        "id": rec.get("id"), "ticker": _as_str(rec.get("ticker")), "kind": rec.get("kind"),
        "etf_proxy": _as_str(rec.get("etf_proxy")),
        "name": rec.get("name"), "name_zh": rec.get("name_zh"),
        "group": rec.get("group"), "group_zh": rec.get("group_zh"), "accent": rec.get("accent"),
        "cycle": {"phase": now.get("phase"), "phaseLabel": phase_label,
                  "pos": now.get("pos"), "proj": rec.get("proj"),
                  "rs_rank": now.get("rs_rank"), "rs_21d_rank": now.get("rs_21d_rank"),
                  "above200d": now.get("above200d")},
    }
