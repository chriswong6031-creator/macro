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
    try:
        latest["playbook"] = build_playbook(f, regime, yahoo_closes(), latest)
    except Exception as e:  # noqa: BLE001 — conclusions are additive, never fatal
        log.error("playbook failed: %s", e)
        latest["playbook"] = None
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
