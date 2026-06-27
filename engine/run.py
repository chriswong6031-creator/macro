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
from engine.transition import compute_flags, state_machine
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
    regime["transition_state"] = state_machine(flags, regime)

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
    latest = {
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
        "transition_flags": {c: bool(row[c]) for c in flags.columns if c != "n_flags"},
        "confirming": confirming,
        "contradicting": contradicting,
        "flip_condition": flip_condition(f, regime, asof),
        "sector_rs": table.reset_index().to_dict(orient="records"),
        "preference_check": preference_check(quad, table),
        "pair_ratios": pair_ratios_snapshot(f),
        "alerts": [{"rule": a.rule, "severity": a.severity, "message": a.message,
                    "message_zh": a.message_zh}
                   for a in fired],
    }
    from engine.inputs import yahoo_closes
    from engine.playbook import build_playbook
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
    try:
        from engine.foresight_cascade import compute_foresight_cascade
        latest["foresight_cascade"] = compute_foresight_cascade(
            latest.get("bottleneck"), latest.get("theme_revisions"))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("foresight-cascade layer failed: %s", e)
        latest["foresight_cascade"] = None
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
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("risk-radar failed: %s", e)
        latest["risk_radar"] = None
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
