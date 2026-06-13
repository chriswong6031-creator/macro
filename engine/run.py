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
    try:
        latest["playbook"] = build_playbook(f, regime, yahoo_closes(), latest)
    except Exception as e:  # noqa: BLE001 — conclusions are additive, never fatal
        log.error("playbook failed: %s", e)
        latest["playbook"] = None
    # complementary nowcast / conditions / risk-appetite layer (additive — never
    # alters the validated quad; see research/QUANT_FACTOR_EXPANSION.md)
    try:
        from engine.conditions import conditions_snapshot
        latest["conditions"] = conditions_snapshot(f)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("conditions layer failed: %s", e)
        latest["conditions"] = None
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
