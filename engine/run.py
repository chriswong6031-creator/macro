"""Engine entrypoint: features -> classification -> transition state ->
regime history parquet + latest-day JSON object.

The whole history is recomputed each run (vectorized, a few seconds) so the
live signal and the backtest can never drift apart.
"""
from __future__ import annotations

import json
import logging

import pandas as pd

from engine.inputs import build_features
from engine.regime import QUAD_NAMES, classify, flip_condition
from engine.sectors import pair_ratios_snapshot, preference_check, rs_table
from engine.transition import compute_flags, state_machine_detail
from lib import config, store

log = logging.getLogger(__name__)


def freshness_stamp(asof, now=None, max_age_sessions: int = 1) -> dict:
    """PIT freshness/staleness stamp for the contract (research/RISK_FLIP_2026-06-22.md).

    On 2026-06-22 the downstream bot consumed a 2026-06-18 contract through the whole
    session — Juneteenth (Fri 06-19) + the weekend meant no newer session existed, and
    the daily build only lands post-close (22:40 UTC), yet latest.json carried NO
    freshness stamp, so a 4-calendar-day-old read was treated as a live all-clear. This
    stamps asof + build wall-clock + session age so a consumer can DISCOUNT a stale
    contract. PURE (now injectable for tests). `age_sessions` is a holiday-agnostic
    weekday count — coarse, and it errs toward flagging stale. Degrade-never-raise."""
    if now is None:
        now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    asof_d, now_d = pd.Timestamp(asof).normalize(), pd.Timestamp(now).normalize()
    age_days = max(0, int((now_d - asof_d).days))
    age_sessions = (max(0, len(pd.bdate_range(asof_d, now_d)) - 1)
                    if now_d >= asof_d else 0)
    return {
        "asof": str(pd.Timestamp(asof).date()),
        "built_at": pd.Timestamp(now).isoformat(timespec="seconds") + "Z",
        "age_days": age_days,
        "age_sessions": age_sessions,
        "max_age_sessions": int(max_age_sessions),
        "stale": bool(age_sessions > int(max_age_sessions)),
        "note": ("contract asof vs build time; the daily build lands post-close "
                 "(22:40 UTC) so a consumer reading intraday should expect asof = "
                 "prior session — recompute age against built_at at read time."),
    }


def confirming_contradicting(regime: pd.DataFrame, asof: pd.Timestamp) -> tuple[list, list]:
    row = regime.loc[asof]
    confirming, contradicting = [], []
    for axis in ("growth", "inflation"):
        sign = 1 if row[f"{axis}_score"] >= 0 else -1
        for col in regime.columns:
            if not col.startswith(f"c_{axis}_"):
                continue
            v = row[col]
            if pd.isna(v) or v == 0:
                continue
            name = col.replace("c_", "", 1)
            (confirming if v * sign > 0 else contradicting).append(name)
    return confirming, contradicting


def run() -> dict:
    f = build_features()
    regime = classify(f)
    flags = compute_flags(f, regime)
    regime = regime.join(flags)
    # ratcheted + raw transition state (engine/transition.state_machine_detail):
    # transition_state stays the headline enum; _raw/_ratcheted/_dwell_remaining
    # are additive audit columns (2026-07-02 incident fix)
    regime = regime.join(state_machine_detail(flags, regime))

    hist_cols = [c for c in regime.columns if not c.startswith("c_")]
    full = regime.copy()
    store_df = regime[hist_cols]
    p = config.data_dir() / "regime"
    p.mkdir(parents=True, exist_ok=True)
    store_df.to_parquet(p / "regime_history.parquet")

    asof = regime["quad"].last_valid_index()
    row = regime.loc[asof]
    quad = row["quad"]
    label = quad
    if bool(row.get("recession", False)):
        label = f"{quad}/Recession"
    elif bool(row.get("inflation_shock", False)):
        label = f"{quad}/Inflation-shock"

    from engine.alerts import evaluate, log_and_dedup
    fired = log_and_dedup(evaluate(f), asof)

    confirming, contradicting = confirming_contradicting(full, asof)
    table = rs_table(asof)
    fc = flip_condition(f, regime, asof)
    latest = {
        # contract hygiene (research/PERCEPTION_CONTRACTS.md): versioned schema +
        # a TRUE-DATA timestamp at top level (asof = last session in the regime
        # frame, == freshness.asof; built_at lives in freshness). Additive.
        "schema_version": 1,
        "asof": str(asof.date()),
        "date": str(asof.date()),
        "quad": quad,
        "quad_name": QUAD_NAMES.get(quad, quad),
        "label": label,
        "growth_score": round(float(row["growth_score"]), 3),
        "inflation_score": round(float(row["inflation_score"]), 3),
        "growth_confidence": round(float(row["growth_confidence"]), 3),
        "inflation_confidence": round(float(row["inflation_confidence"]), 3),
        "confidence": round(float(row["regime_confidence"]), 3),
        "liquidity_overlay": row["liquidity"],
        "cycle_tag": row["cycle"],
        "transition_state": row["transition_state"],
        # ratchet audit plane (additive; incident 2026-07-02): the memoryless read,
        # whether the dwell is holding the state hotter than raw, and how many
        # clean sessions remain before the next step-down
        "transition_state_raw": row["transition_state_raw"],
        "transition_ratcheted": bool(row["transition_ratcheted"]),
        "transition_dwell_remaining": int(row["transition_dwell_remaining"]),
        "transition_flags": {c: bool(row[c]) for c in flags.columns if c != "n_flags"},
        "confirming": confirming,
        "contradicting": contradicting,
        "flip_condition": fc,
        # top-level mirror of flip_condition.margin — the single number consumers
        # damp on (was only nested; None when the axis is already mixed)
        "flip_margin": (fc or {}).get("margin"),
        "sector_rs": table.reset_index().to_dict(orient="records"),
        "preference_check": preference_check(quad, table),
        "pair_ratios": pair_ratios_snapshot(f),
        "alerts": [{"rule": a.rule, "severity": a.severity, "message": a.message,
                    "message_zh": a.message_zh}
                   for a in fired],
    }
    from engine.inputs import yahoo_closes
    from engine.playbook import build_playbook
    # Liquidity QUALITY (engine/regime.liquidity_quality; incident 2026-07-02
    # root-cause #3): classifies the bare quantity-RoC overlay into benign vs
    # stress vs hollow — RRP-buffer exhaustion, TGA/RRP-vs-WALCL composition,
    # credit/funding co-check, ffill staleness. liquidity_overlay is UNCHANGED;
    # this is the additive quality plane every consumer reads instead of
    # re-deriving. Additive, never fatal.
    try:
        lq_cfg = (config.load().get("engine", {}).get("liquidity", {}) or {})
        if lq_cfg.get("quality_enabled", True):
            from engine.regime import liquidity_quality
            latest["liquidity_quality"] = liquidity_quality(
                f, overlay=row["liquidity"], asof=asof)
        else:
            latest["liquidity_quality"] = None
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("liquidity-quality layer failed: %s", e)
        latest["liquidity_quality"] = None
    # conditions layer is computed FIRST so the exposure dial can consume the
    # recession-risk + financial-conditions edges (research/QUANT_FACTOR_EXPANSION.md).
    try:
        from engine.conditions import conditions_snapshot
        latest["conditions"] = conditions_snapshot(f)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("conditions layer failed: %s", e)
        latest["conditions"] = None
    # Business-cycle model: Conference-Board-style Leading / Coincident / Lagging tiers
    # kept SEPARATE so the lead-lag SEQUENCE is legible (where conditions.recession_risk
    # blends them). Reads the FRED/price store directly; additive, never fatal.
    # See engine/business_cycle.py + reports/business-cycle-validation.md.
    try:
        from engine.business_cycle import business_cycle_snapshot
        latest["business_cycle"] = business_cycle_snapshot()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("business-cycle layer failed: %s", e)
        latest["business_cycle"] = None
    # Base-effect forward-regime projection (the Hedgeye kernel): forward YoY paths + the
    # base-forced acceleration/deceleration sign per quarter for growth (INDPRO/PAYEMS) and
    # inflation (core CPI/PCE — the Fed's target). The forward econic 2nd-derivative the
    # market-proxy Quad lacks. DISPLAY-ONLY leaf (engine/base_effect.py): carries ZERO axis
    # weight, and each build appends to data/regime/base_effect_fwd.jsonl for later
    # forward-grading against the disclosed inversion stat (plan §A.6). See
    # research/HEDGEYE_UPGRADE_MASTER_PLAN.md.
    try:
        from engine import base_effect as _base_effect
        _bex = _base_effect.compute()
        latest["base_effect"] = _bex
        if _bex is not None:
            _bfp = p / "base_effect_fwd.jsonl"
            _today = str(asof.date())
            _last = None
            if _bfp.exists():
                _bl = _bfp.read_text().splitlines()
                if _bl:
                    try:
                        _last = json.loads(_bl[-1]).get("asof")
                    except Exception:  # noqa: BLE001
                        _last = None
            if _last != _today:  # one grading row per session, idempotent across same-day rebuilds
                with open(_bfp, "a") as _bfh:
                    _bfh.write(json.dumps(_base_effect.grading_row(_bex, _today), default=str) + "\n")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("base-effect layer failed: %s", e)
        latest["base_effect"] = None
    # Continuous regime probabilities via the informed 4-state Gaussian HMM (v1, L2): soft
    # P(Quad) + a monthly transition matrix + hazard + expected dwell, replacing the
    # |score|*agreement heuristic "confidence" with real probabilities. DISPLAY-ONLY leaf
    # (engine/regime_hmm.py): a ~1s informed fit (no EM), so it sits in the engine lane, never
    # the render (render.yml reads latest.json). The legacy raw_quad + hysteresis path in
    # engine/regime.py stays canonical; nothing here drives a weight, size, or gross dial until
    # scripts/validate_regime_fwd.py clears it. See research/HEDGEYE_UPGRADE_MASTER_PLAN.md §A.3.
    try:
        from engine.regime_hmm import fit_regime_hmm
        latest["regime_hmm"] = fit_regime_hmm(full, history_days=252)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("regime-hmm layer failed: %s", e)
        latest["regime_hmm"] = None
    # Regime One (engine/regime_one.py, masterplan W2): the canonical regime artifact
    # with an HONEST decomposition — tape (coincident market-proxy, labelled coincident)
    # vs macro (econ legs on the leak-free release frame) vs forward (causal FILTERED
    # P(Quad) + base_effect) vs fused_risk (5-state + versioned gross + inflection-aware
    # confidence). Plus FLIP ATTRIBUTION: a renormalization-driven quad flip (a dead feed
    # vanishing from the weighted sum) is VETOED and the label freezes, degraded (#3).
    # SHADOW artifact — publishes ALONGSIDE the legacy regime; ZERO behavioral change to
    # any current consumer this wave (P2-A). Additive, fail-isolated, negligible runtime.
    try:
        from engine import base_effect as _be_r1
        from engine import regime_one as _r1
        # base_effect on the leak-free path: thread as_of + vintages so CPI/PCE/PPI read
        # revised=False where vintage coverage exists (#16/#809), unlike run.py:149's call.
        _r1_bex = latest.get("base_effect")   # the revised-finals base_effect as fallback
        try:
            from collectors.fred import load_vintages as _lv
            _r1_bex = _be_r1.compute(as_of=asof, vintages=_lv())
        except Exception:  # noqa: BLE001 — fall back to the revised-finals base_effect
            _r1_bex = latest.get("base_effect")
        _r1_rel = _r1.build_release_axis_row()
        _r1_prev = None
        _r1_path = p / "regime_one.json"
        if _r1_path.exists():
            try:
                _r1_prev = json.loads(_r1_path.read_text())
            except Exception:  # noqa: BLE001
                _r1_prev = None
        _r1_out = _r1.compute(full, _r1_rel, _r1_bex, latest, prev=_r1_prev, data_dir=p)
        latest["regime_one"] = _r1_out
        with open(_r1_path, "w") as _r1fh:
            json.dump(_r1_out, _r1fh, indent=2, default=str)
        # Freshness ledger (#32): append-only compact per-component freshness alongside
        # regime history so every session is forever auditable as full-data vs degraded.
        # No retro-reconstruction (c_ columns were dropped — impossible); accrues NOW.
        _fl_path = p / "freshness_ledger.jsonl"
        _fl_today = _r1_out["asof"]
        _fl_last = None
        if _fl_path.exists():
            _fll = _fl_path.read_text().splitlines()
            if _fll:
                try:
                    _fl_last = json.loads(_fll[-1]).get("asof")
                except Exception:  # noqa: BLE001
                    _fl_last = None
        if _fl_last != _fl_today:  # one row per session, idempotent across same-day rebuilds
            with open(_fl_path, "a") as _flh:
                _flh.write(json.dumps({
                    "asof": _fl_today,
                    "quad": _r1_out["legacy_quad"],
                    "label_quad": _r1_out["label_quad"],
                    "freshness_bitmask": _r1_out["freshness_bitmask"],
                    "degraded": _r1_out["degraded"],
                }, default=str) + "\n")
        # append today's causal-HMM forward call to its grading ledger (#16 accrual)
        try:
            _r1.accrue_hmm_row(p.parent)   # p = data/regime; data_dir = data/
        except Exception:  # noqa: BLE001 — accrual is best-effort
            pass
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("regime-one layer failed: %s", e)
        latest["regime_one"] = None
    # quad_vector (engine/quad_vector.py): the published continuous-P(Quad)
    # CONTRACT — a thin reshape of regime_one's causal filtered posterior (P7:
    # the probabilities are owned by the hedgeye program; this only publishes
    # the stable consumer shape). NOT next_quad_probs — that name is taken by
    # two historical Markov objects. Additive, never fatal.
    try:
        from engine.quad_vector import build as build_quad_vector
        latest["quad_vector"] = build_quad_vector(latest, full, asof)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("quad-vector layer failed: %s", e)
        latest["quad_vector"] = None
    # Catalyst tone (LLM Tier-A): a DIGEST of the most recent public catalyst (FOMC
    # statement) as honest CONTEXT only. Default-off LEAF (engine/catalyst_tone.py);
    # None when disabled or nothing recent. NEVER enters the deterministic scoring path.
    try:
        from engine.catalyst_tone import daily_snapshot as catalyst_snapshot
        latest["catalyst_tone"] = catalyst_snapshot(asof)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("catalyst tone layer failed: %s", e)
        latest["catalyst_tone"] = None
    # Dislocation Gate-1: the Fed-put master switch that CONDITIONS the capitulation
    # gauge (buyable washout vs falling-knife). Additive risk filter; reads the
    # catalyst shock-reversibility leg when present (computed above). See
    # engine/dislocation.py + research/DISLOCATION_VALIDATION.md.
    try:
        from engine.dislocation import snapshot as dislocation_snapshot
        latest["dislocation"] = dislocation_snapshot(
            f, latest.get("conditions"), latest.get("catalyst_tone"))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("dislocation layer failed: %s", e)
        latest["dislocation"] = None
    # Cross-asset concentration: are the six markets secretly one liquidity/risk bet?
    # Additive leaf (engine/cross_asset.py) — reads the per-market price stores and
    # degrades to verdict="unknown" if too few are present.
    try:
        from engine.cross_asset import snapshot as cross_asset_snapshot
        latest["cross_asset"] = cross_asset_snapshot()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("cross-asset layer failed: %s", e)
        latest["cross_asset"] = None
    # Whole-market dealer-gamma vol regime: are dealers SHORT gamma (hedging WITH price
    # -> moves amplify, the air-pocket precondition) or LONG (pinning / vol suppressed)?
    # The SAME deriver that renders the dashboard banner (engine.market_gamma.view, used
    # by scripts/build_site.py) so the contract and the FE can NEVER drift. STEADY-STATE
    # — reports the standing regime every build, unlike the episodic gex_flip_cross alert
    # that fires only on a crossing. Additive leaf (engine/market_gamma.py): reads the
    # validated index GEX store (cboe/gex) and degrades to None if it is missing/empty.
    try:
        from engine.market_gamma import snapshot as market_gamma_snapshot
        latest["market_gamma"] = market_gamma_snapshot()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("market-gamma layer failed: %s", e)
        latest["market_gamma"] = None
    # Market-driver attribution: WHICH cross-asset force is moving the tape this
    # week (Fed repricing / real-rate / USD / credit / liquidity / China / oil /
    # AI-semis / crypto) + evidence + invalidation. Deterministic fingerprints over
    # signals already computed here — a regime READ, DISPLAY-ONLY, never scored (an
    # LLM brief only narrates it). Append-only log grades the calls later.
    try:
        from engine.market_drivers import snapshot as market_drivers_snapshot, append_log
        latest["market_drivers"] = market_drivers_snapshot()
        append_log(latest["market_drivers"])
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("market-drivers layer failed: %s", e)
        latest["market_drivers"] = None
    # Cross-asset risk budgeting (ERC/inverse-vol) + crisis stress-replay — the
    # additive "size as uncorrelated bets / cap risk" view (engine/portfolio.py).
    try:
        from engine.portfolio import snapshot as portfolio_snapshot
        latest["portfolio"] = portfolio_snapshot()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("portfolio layer failed: %s", e)
        latest["portfolio"] = None
    # Catalyst event-trigger (Stage 3b): on an ACTIVE dislocation whose FOMC digest
    # carries no usable reversibility read, digest THAT DAY's market news for a fresh
    # shock_reversible and re-attach the dislocation narrative. Gated + never fatal
    # (no-ops while dislocation isn't wired into latest on this line).
    try:
        from engine import catalyst_tone as _ct
        dis = latest.get("dislocation") or {}
        ct0 = latest.get("catalyst_tone") or {}
        if (dis.get("verdict") in ("buyable_washout", "stand_aside")
                and ct0.get("shock_reversible") not in ("reversible", "persistent")):
            ev = _ct.event_snapshot(asof, context=f"dislocation: {str(dis.get('headline', ''))[:120]}")
            if ev:
                latest["catalyst_event"] = ev
                src = ev if ev.get("shock_reversible") in ("reversible", "persistent") else ct0
                from engine.dislocation import _catalyst_narrative
                latest["dislocation"]["catalyst_narrative"] = _catalyst_narrative(dis.get("verdict"), src)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("catalyst event-trigger failed: %s", e)
    # Fed policy path (research/DATA_SIGNAL_EXPANSION_2026.md #2): the market-implied
    # rate path (ZQ/SR3 futures) vs the FOMC dot-plot + a Fed-vs-market gap read.
    # Additive DISPLAY/LLM-context leaf (engine/fed_path.py) — the path level is a
    # PRICE and repricing is reactive, so it is NEVER scored and NEVER an MRS leg.
    try:
        from engine.fed_path import snapshot as fed_path_snapshot
        latest["fed_path"] = fed_path_snapshot(f)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("fed-path layer failed: %s", e)
        latest["fed_path"] = None
    # Additive DISPLAY-only leaf (engine/fed_stance.py) — make monetary-policy STANCE an
    # explicit regime dimension (hawkish/neutral/dovish) off fed_path + catalyst_tone,
    # instead of leaving it implicit in the curve. PHASE-0 GATED: never scored, never an
    # MRS leg; nothing in axes/regime/conditions reads it. Runs after fed_path/catalyst_tone.
    try:
        from engine.fed_stance import snapshot as fed_stance_snapshot
        latest["fed_stance"] = fed_stance_snapshot(latest)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("fed-stance layer failed: %s", e)
        latest["fed_stance"] = None
    # Rate & inflation TRANSMISSION (research/RATE_INFLATION_TRANSMISSION.md): how the
    # current rate / rate-expectations / inflation (CPI, core PCE) state propagates —
    # first/second/third order — into per-asset-class headwind/tailwind, with honest
    # conditional scenarios + an inflation decomposition. DISPLAY-ONLY leaf
    # (engine/rate_inflation_transmission.py): the coefficients are the MEASURED forward
    # IC (data/transmission/calibration.json) and the scored-leg gate found NONE robust
    # enough to score — repricing is reactive. Never scored, never an MRS leg, never fatal.
    try:
        from engine.rate_inflation_transmission import snapshot as transmission_snapshot
        latest["rate_inflation_transmission"] = transmission_snapshot(f)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("rate/inflation transmission layer failed: %s", e)
        latest["rate_inflation_transmission"] = None
    # YIELD-CURVE analytics (research/YIELD_CURVE_ENGINE.md): the unified interest-rate
    # read — shape (level/slope/curvature + the Litterman-Scheinkman PCA variance), every
    # canonical slope + its momentum, the bull/bear × steepener/flattener regime with its
    # Fed-cycle phase and asset map, the recession dashboard (near-term forward spread +
    # NY-Fed probit + un-inversion + TP-adjusted), forward rates with carry/roll-down, and
    # four typed signal families (core-macro / sector / stock-factor / market-tendency).
    # DISPLAY-ONLY leaf (engine/yield_curve.py) reusing the bond-engine curve primitives;
    # the scored-leg gate found NO curve leg robust enough to score. Never fatal.
    try:
        from engine.yield_curve import snapshot as yield_curve_snapshot
        latest["yield_curve"] = yield_curve_snapshot(f)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("yield-curve layer failed: %s", e)
        latest["yield_curve"] = None
    # Turning-point fragility meta-layer (engine/turning_point.py): reads ACROSS the
    # leaves above (cross_asset / market_drivers / conditions / dislocation / fed_path)
    # and raises a DISPLAY-ONLY caution when the tape is a one-factor macro-shock
    # extreme with pinned positioning — the configuration that whipsaws. NEVER scored
    # (the layer cannot tell "forced & reversible" from "early & real"). A one-day
    # cooldown (last_active/append_log) keeps the caution from flickering.
    try:
        from engine.turning_point import (snapshot as turning_point_snapshot,
                                           append_log as turning_point_log,
                                           last_active as turning_point_prev)
        latest["turning_point"] = turning_point_snapshot(
            latest, latest.get("transition_state"), turning_point_prev(asof))
        turning_point_log(latest["turning_point"])
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("turning-point layer failed: %s", e)
        latest["turning_point"] = None
    # Thematic Foresight Desk (research/THEMATIC_FORESIGHT_DESK.md): anticipate themes at
    # the "precipice of induction" — physical-supply TIGHTNESS (T1, engine/bottleneck.py,
    # the LEADING thesis) x revision-breadth BROADENING (T4, engine/theme_revisions.py, the
    # CONFIRMATION gauge) -> a per-theme STAGE (PRECIPICE / BROADENING / RE-RATING /
    # GLUT-RISK) ranked by edge remaining. DISPLAY-ONLY leaves; entry is deferred to the
    # dislocation overlay (13D was right & ~9mo early). Each writes its own append-only
    # forward-grading ledger. Never scored, never an MRS leg, never fatal.
    try:
        from engine.theme_revisions import compute_theme_revisions
        latest["theme_revisions"] = compute_theme_revisions()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("theme-revisions layer failed: %s", e)
        latest["theme_revisions"] = None
    try:
        from engine.bottleneck import compute_bottleneck
        latest["bottleneck"] = compute_bottleneck()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("bottleneck layer failed: %s", e)
        latest["bottleneck"] = None
    # power-cluster PHYSICAL read (electricity scarcity) — the physical correlate the FRED
    # semis/metals bottleneck can't give data-center-power / grid / nuclear / solar.
    try:
        from engine.power_scarcity import compute_power_scarcity
        latest["power_scarcity"] = compute_power_scarcity()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("power-scarcity layer failed: %s", e)
        latest["power_scarcity"] = None
    try:
        from engine.demand_capex import compute_demand_capex
        latest["demand_capex"] = compute_demand_capex()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("demand-capex layer failed: %s", e)
        latest["demand_capex"] = None
    try:
        from engine.glut_watch import compute_glut_watch
        latest["glut_watch"] = compute_glut_watch(demand=latest.get("demand_capex"))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("glut-watch layer failed: %s", e)
        latest["glut_watch"] = None
    try:
        from engine.guidance_gap import compute_guidance_gap
        latest["guidance_gap"] = compute_guidance_gap()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("guidance-gap layer failed: %s", e)
        latest["guidance_gap"] = None
    try:
        from engine.altdata_confirmers import compute_altdata_confirmers
        latest["altdata_confirmers"] = compute_altdata_confirmers()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("altdata-confirmers layer failed: %s", e)
        latest["altdata_confirmers"] = None
    try:
        from engine.foresight_cascade import compute_foresight_cascade
        latest["foresight_cascade"] = compute_foresight_cascade(
            latest.get("bottleneck"), latest.get("theme_revisions"),
            latest.get("demand_capex"), latest.get("glut_watch"),
            latest.get("guidance_gap"), latest.get("altdata_confirmers"))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("foresight-cascade layer failed: %s", e)
        latest["foresight_cascade"] = None
    # Theme DISCOVERY: bottlenecks forming OUTSIDE the 18 tracked themes — a cluster of
    # un-tracked filers in one SIC industry independently reporting physical scarcity (the
    # pre-13D state). Display-only candidate generator on probation; never auto-added.
    try:
        from engine.theme_emergence import compute_theme_emergence
        latest["theme_emergence"] = compute_theme_emergence()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("theme-emergence layer failed: %s", e)
        latest["theme_emergence"] = None
    # Subsector radar: the cascade signature (text scarcity x revision breadth) over all 113
    # Finviz sub-industries — systematic coverage of the known S&P 500 at sub-industry
    # granularity, complementing the 18 curated themes + the small-cap discovery layer.
    try:
        from engine.subsector_scan import compute_subsector_scan
        latest["subsector_scan"] = compute_subsector_scan()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("subsector-scan layer failed: %s", e)
        latest["subsector_scan"] = None
    # Convergence ("neural web"): fuse the cascade + discovery + subsector radar into one
    # heating-up read — how many INDEPENDENT leading surfaces converge on a theme, weighted by
    # earliness. The single "what to investigate before the crowd" board. DISPLAY-ONLY.
    try:
        from engine.foresight_convergence import compute_convergence
        latest["foresight_convergence"] = compute_convergence(
            latest.get("foresight_cascade"), latest.get("theme_emergence"),
            latest.get("subsector_scan"), latest.get("power_scarcity"))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("convergence layer failed: %s", e)
        latest["foresight_convergence"] = None
    # LLM analyst reasoning over the convergence (graceful no-op without a credential) +
    # deterministic thesis monitor (fires THESIS-BROKEN when that convergence decays).
    try:
        from engine.foresight_analyst import compute_foresight_analyst
        latest["foresight_analyst"] = compute_foresight_analyst(
            latest.get("foresight_convergence"), latest.get("foresight_cascade"))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("foresight-analyst layer failed: %s", e)
        latest["foresight_analyst"] = None
    try:
        from engine.thesis_monitor import compute_thesis_monitor
        latest["thesis_monitor"] = compute_thesis_monitor(latest.get("foresight_convergence"))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("thesis-monitor layer failed: %s", e)
        latest["thesis_monitor"] = None
    # Cross-asset confirmation: does the leading-family complex (BONDS + FX) CONFIRM
    # or DIVERGE from the equity/macro regime computed above? Reads the two dedicated
    # dashboards' contracts (data/bonds/bond_health.json, data/forex/latest.json) — whose
    # rich signal vectors were otherwise orphaned — and compares their INDEPENDENT reads
    # (bond cycle-clock phase, credit/curve/rates-vol/sovereign bands, the dollar-smile
    # regime, EM-FX conviction) to the equity cycle/RORO/drawdown read. DISPLAY-ONLY leaf
    # (engine/cross_asset_confirm.py): never scored, never fatal. Honestly graded — most
    # legs are coincident confirmation / fragility gauges, not predictors (research/
    # CROSS_ASSET_CONFIRMATION.md). Needs `latest` (the equity regime it compares against).
    try:
        from engine.cross_asset_confirm import snapshot as confirm_snapshot
        latest["cross_asset_confirm"] = confirm_snapshot(latest)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("cross-asset-confirm layer failed: %s", e)
        latest["cross_asset_confirm"] = None
    # Macro-risk score (MRS, 0..1): one deterministic risk-OFF gauge folded from
    # the conditions/regime legs above. Derived from macro_risk_series (one coherent
    # as-of date) — NOT from the latest dict, whose legs can straddle two release
    # dates on a cadence-lag day — so the live score matches the calibrate() bands
    # by construction. Computed BEFORE the playbook so the sector heat + per-stock
    # ladder overlays can read it. Additive, never fatal. See MACRO_RISK_INTEGRATION.
    try:
        from engine.conditions import macro_risk_snapshot
        latest["macro_risk"] = macro_risk_snapshot(f, regime)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("macro-risk score failed: %s", e)
        latest["macro_risk"] = None
    # Mirror the published INDEX vol-regime snapshot into latest.json so the per-stock ladder
    # + downstream consumers read it without re-deriving it. build_vol_regime publishes
    # site/vol/regime.json (this reads the freshest available; ~1 day lag on a fresh checkout —
    # acceptable for a slow-moving, subtract-only risk caution). Additive, never fatal.
    try:
        from engine import vol_regime as _vr
        latest["vol_regime"] = _vr.published_snapshot() or None
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("vol-regime mirror failed: %s", e)
        latest["vol_regime"] = None
    # Fused equity-internal RISK STATE (engine/risk_state.py): the loud, EARLY
    # drawdown-risk gauge that leads the credit-weighted macro_risk above. Fuses the
    # orphaned detectors (complacency/hidden-fragility, breadth divergence, dealer GEX
    # posture, vol structure, HY/HYG-TLT credit, turning-point, cross-asset) into one
    # top-level state the brain can act on. Reads only the already-assembled `latest`
    # + a prior-build GEX read + HYG/TLT — runs AFTER macro_risk so it can anchor on it,
    # BEFORE the playbook so conclusions can read it. Additive, never fatal.
    try:
        from engine.risk_state import snapshot as risk_state_snapshot
        latest["risk_state"] = risk_state_snapshot(latest)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("risk-state failed: %s", e)
        latest["risk_state"] = None
    # Risk unification (P2-B', audit #4): RE-FUSE regime_one.fused_risk with the LIVE
    # risk_state (the positioning/blow-off detector) now that it exists. regime_one runs
    # BEFORE risk_state above, so its first fused_risk read is quad-prior-only; this folds
    # in the positioning leg (max-cautious) so the SHADOW fused gate + the bot prior see it.
    # SHADOW — does NOT drive the live sector-central gate (the 2026-06-23 replay did not
    # pass; scripts/ab_risk_gate.py). Re-persist regime_one.json so the artifact carries the
    # fused gate + directives. Additive, never fatal.
    try:
        if latest.get("regime_one") and latest.get("risk_state"):
            from engine import regime_one as _r1re
            latest["regime_one"] = _r1re.refuse(latest["regime_one"], latest["risk_state"])
            _r1re_path = p / "regime_one.json"
            with open(_r1re_path, "w") as _r1refh:
                json.dump(latest["regime_one"], _r1refh, indent=2, default=str)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("regime-one re-fuse failed: %s", e)
    # Risk Radar v2 (engine/risk_radar.py): the EVIDENCE-GATED, regime-typed, genuinely-leading
    # successor to risk_state — scare-typed sub-scores (credit/rates/bubble/growth + vol display-
    # only) built ONLY from signals that pass the strict day-level-lift backtest gate, loud+early,
    # with each alert carrying its measured lift/lead. Primary top-level risk read for the brain.
    # Additive, never fatal. See research/RISK_ENGINE_V2_FINDINGS.md.
    try:
        from engine.risk_radar import snapshot as risk_radar_snapshot
        latest["risk_radar"] = risk_radar_snapshot()
        # Self-auditing forward-outcome log (engine/risk_radar_audit.py): log today's read, grade
        # matured past reads vs the realized SPY path, attach the rolling realized-accuracy
        # scorecard. Feeds the Opus self-correction loop. Additive, never fatal.
        try:
            from engine import risk_radar_audit as _rra
            if latest["risk_radar"]:
                latest["risk_radar"]["forward_log"] = _rra.snapshot_and_grade(latest["risk_radar"])
        except Exception as e:  # noqa: BLE001
            log.warning("risk-radar audit failed: %s", e)
        # Recovery-channel forward-outcome log (engine/risk_radar_recovery_audit.py, W1):
        # log today's recovery + market-chip snapshot, grade matured entries vs SPY path
        # (rebound ruler, RRX-R2), attach the scorecard. Additive, never fatal.
        try:
            from engine import risk_radar_recovery as _rrr
            from engine import risk_radar_recovery_audit as _rra2
            if latest.get("risk_radar"):
                _rec = _rrr.assess(latest)
                latest["risk_radar"]["recovery_log"] = _rra2.snapshot_and_grade(
                    _rec or {}, latest["risk_radar"]
                )
        except Exception as e:  # noqa: BLE001
            log.warning("risk-radar recovery audit failed: %s", e)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("risk-radar failed: %s", e)
        latest["risk_radar"] = None
    # Ignition Radar (engine/ignition_radar.py, IGN WB): risk-ON mirror of the Risk
    # Radar — broad K-of-8 thrust confluence + narrow per-basket theme ignition.
    # DISPLAY-ONLY / NOT VALIDATED. Runs AFTER risk_radar so it can reuse the already-
    # computed catalysts payload. In-process call; writes data/ignition_radar/latest.json.
    # Additive, never fatal.
    try:
        from engine import ignition_radar as _igr
        from engine import ignition_audit as _iga
        _ig_snap = _igr.snapshot()
        latest["ignition_radar"] = _ig_snap
        # US arm forward log (engine/ignition_audit.py): log today's snapshot, grade
        # matured past reads vs SPY, attach the scorecard. Additive, never fatal.
        try:
            if _ig_snap:
                _spy_s = None
                if latest.get("risk_radar"):
                    try:
                        import pandas as _pd
                        _spy_df = store.read("yahoo", "SPY")
                        if _spy_df is not None and "close" in _spy_df.columns:
                            _spy_s = _spy_df["close"].dropna().sort_index().astype(float)
                            _spy_s.index = _pd.to_datetime(_spy_s.index)
                    except Exception:  # noqa: BLE001
                        pass
                latest["ignition_radar"]["forward_log"] = _iga.us_snapshot_and_grade(
                    _ig_snap, _spy_s
                )
        except Exception as _e:  # noqa: BLE001
            log.warning("ignition-radar audit failed: %s", _e)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("ignition-radar failed: %s", e)
        latest["ignition_radar"] = None
    # Mag-7 Regime Context Organ (engine/mag7_regime.py, M7C-R2/R3): daily regime
    # snapshot for the seven mega-cap tech names — trend_state, structure, run meter,
    # k7 breadth, member table, generals, tech_legs. DISPLAY-ONLY / NOT VALIDATED.
    # Writes data/mag7_regime/latest.json + site/stockdata/mag7_regime.json.
    # Appends ledger.jsonl (idempotent). Additive, never fatal.
    try:
        from engine import mag7_regime as _m7r
        latest["mag7_regime"] = _m7r.snapshot()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("mag7-regime failed: %s", e)
        latest["mag7_regime"] = None
    # Index Hybrid Momentum organ (engine/index_momentum.py, IHM-R1..R4): RSI-MACD
    # hybrid at 1D/2B/3B/W-FRI for 13 index carriers (US/HK/CN/INTL + MAG7 carrier).
    # Depth percentile, hist_vel3, washout_turn/trap_zone quality tags, and global-turn
    # confluence tags (us_confirm, global_washout_turn, turn_breadth). DISPLAY-ONLY /
    # NOT VALIDATED. Writes data/index_momentum/latest.json + events.parquet (idempotent).
    # Runs after ignition_radar (US lane; no new collectors required). Additive, never fatal.
    try:
        from engine import index_momentum as _ihm
        latest["index_momentum"] = _ihm.snapshot()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("index-momentum failed: %s", e)
        latest["index_momentum"] = None
    # Vol-Shock Risk Predictor (engine/vol_shock_scorecard.py): ONE forward 0-100
    # caution gauge that FUSES the fast/LEADING precursors which flash before a vol
    # shock (cross-asset concentration, dealer short-gamma, VIX term inversion,
    # compressed VRP/skew, complacent positioning, the active turning-point caution)
    # — all already computed on `latest` but never co-fused. Runs LAST so it reads
    # every leaf above (conditions / cross_asset / dislocation / turning_point /
    # macro_risk / market_gamma). DISPLAY-ONLY / validation-accruing: never scored,
    # feeds no allocation; each firing is logged + graded on forward data (the
    # outcome log can't be tuned post-hoc). Additive, never fatal.
    try:
        from engine import vol_shock_scorecard as _vss
        latest["vol_shock"] = _vss.snapshot(latest)
        _vss.append_log(latest["vol_shock"], latest)
        _vss.resolve_from_store()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("vol-shock scorecard failed: %s", e)
        latest["vol_shock"] = None
    # Froth & Fragility (engine/froth_fragility.py): the DISPLAY-ONLY macro top-risk
    # gauge that measures retail EUPHORIA (semis/AI parabolicity) AND hidden DISTRIBUTION
    # (the Stealth Distribution sub-score + leadership-distribution + A/D non-confirmation
    # + absorption) — the two halves a single VIX read cannot see. Runs LAST so it reads
    # every leaf above (conditions / cross_asset / vol_shock). Feeds NO score, NO
    # allocation, NO selection — sanctioned response is SIZING only; each firing is logged
    # + graded on forward QQQ/SMH drawdown + VIX jump. Additive, never fatal.
    try:
        from engine import froth_fragility as _ff
        latest["froth_fragility"] = _ff.snapshot(latest)
        _ff.append_log(latest["froth_fragility"], latest)
        _ff.resolve_from_store()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("froth-fragility gauge failed: %s", e)
        latest["froth_fragility"] = None
    try:
        latest["playbook"] = build_playbook(f, regime, yahoo_closes(), latest)
    except Exception as e:  # noqa: BLE001 — conclusions are additive, never fatal
        log.error("playbook failed: %s", e)
        latest["playbook"] = None
    # Freshness / staleness guard — see freshness_stamp(). Additive, never fatal.
    try:
        max_age = int((config.load().get("engine", {}).get("freshness", {}) or {})
                      .get("max_age_sessions", 1))
        latest["freshness"] = freshness_stamp(asof, max_age_sessions=max_age)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("freshness stamp failed: %s", e)
    # MTF confluence buy-filter (entry-QUALITY / RISK signal) — DISPLAY-ONLY leaf for the
    # Mastermind brain. NOT alpha; see research/signal_engine/CHARTER.md (§2, §7). Loads the
    # precomputed snapshot from scripts/build_signal_quality.py so heavy compute never slows
    # this build. The brain (engine/master_brain.py) consumes it as an entry-quality breadth
    # calibration check; validated buy-filter cut avg maxDD -23.7%->-15.5% across 110 names.
    try:
        _sq = config.data_dir() / "signal_archive" / "mtf_signals_latest.json"
        latest["mtf_signals"] = json.loads(_sq.read_text()) if _sq.exists() else None
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("mtf-signals leaf failed: %s", e)
        latest["mtf_signals"] = None
    # Regime Vector (W0.5a — Setup-Species program §3.4): thin aggregator that consumes
    # existing siblings (quad_vector, regime_one, risk_radar, vol_regime, MRS, breadth,
    # dislocation, rate_inflation_transmission) and publishes the one new categorical state
    # (rate_pressure).  Runs AFTER risk_radar (needs its rates-scare sub-score for panic
    # escalation) and BEFORE the coherence assert (whose vocabulary check now covers
    # rate_pressure tokens).  Persists daily to data/regime/regime_vector.parquet (NOT
    # regime_history.parquet — four files share that name; wrong-file appends are #1026-
    # class hazard).  Additive, never fatal.
    try:
        from engine.regime_vector import build as rv_build, persist as rv_persist
        latest["regime_vector"] = rv_build(latest)
        rv_persist(latest["regime_vector"])
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("regime-vector failed: %s", e)
        latest["regime_vector"] = None
    # Risk COHERENCE assert (P2-B', audit #4) — the "can never contradict on a stress day"
    # guarantee. Verifies (A) the three gross tables agree (single source), (B) the live
    # sector-central gate basis is still MRS (no silent flip; the 06-23 replay didn't pass),
    # and (C) no stress-day contradiction (a loud risk-off banner/fused/risk_state while the
    # live conviction gate sizes risk-on — the exact #4 hazard). Non-strict by default (logs
    # loudly); strict under COHERENCE_STRICT=1 (CI) so a real contradiction stops the build.
    try:
        from engine.regime_coherence import assert_coherence
        latest["risk_coherence"] = assert_coherence(latest, strict=None)
    except Exception as e:  # noqa: BLE001 — the assert may raise CoherenceError under strict
        if e.__class__.__name__ == "CoherenceError":
            raise
        log.error("risk coherence assert failed to run: %s", e)
        latest["risk_coherence"] = None
    with open(p / "latest.json", "w") as fh:
        json.dump(latest, fh, indent=2, default=str)
    log.info("regime %s (%s) conf=%.2f liq=%s cycle=%s transition=%s",
             label, latest["quad_name"], latest["confidence"],
             latest["liquidity_overlay"], latest["cycle_tag"], latest["transition_state"])
    return latest


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    print(json.dumps(run(), indent=2, default=str))
