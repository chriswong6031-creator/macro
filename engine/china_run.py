"""China engine entrypoint: features -> classification -> regime history parquet
+ latest-day JSON. Mirror of engine/run.py, leaner (no transition state machine /
alerts in v1). Recomputes the full history each run so live == backtest.
"""
from __future__ import annotations

import json
import logging

import pandas as pd

from engine.china_inputs import (build_features, pair_ratios_snapshot,
                                 preference_check, rs_table)
from engine.china_regime import classify
from lib import config

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
            (confirming if v * sign > 0 else contradicting).append(col.replace("c_", "", 1))
    return confirming, contradicting


def run() -> dict:
    f = build_features()
    regime = classify(f)

    p = config.data_dir() / "china_regime"
    p.mkdir(parents=True, exist_ok=True)
    store_df = regime[[c for c in regime.columns if not c.startswith("c_")]]
    store_df.to_parquet(p / "regime_history.parquet")

    asof = regime["quad"].last_valid_index()
    if asof is None:
        raise RuntimeError("china engine produced no classified day")
    row = regime.loc[asof]
    quad = row["quad"]
    confirming, contradicting = confirming_contradicting(regime, asof)
    table = rs_table(asof)
    latest = {
        "date": str(asof.date()),
        "quad": quad,
        "quad_name": row["quad_name"],
        "growth_score": round(float(row["growth_score"]), 3),
        "inflation_score": round(float(row["inflation_score"]), 3),
        "growth_confidence": round(float(row["growth_confidence"]), 3),
        "inflation_confidence": round(float(row["inflation_confidence"]), 3),
        "confidence": round(float(row["regime_confidence"]), 3),
        "liquidity_overlay": row["liquidity"],
        "cycle_tag": row["cycle"],
        "pending_quad": row["pending_quad"],
        "pending_days": int(row["pending_days"]) if pd.notna(row["pending_days"]) else 0,
        "confirming": confirming,
        "contradicting": contradicting,
        "sector_rs": table.reset_index().to_dict(orient="records") if not table.empty else [],
        "preference_check": preference_check(row["quad_name"], table),
        "pair_ratios": pair_ratios_snapshot(f),
    }
    # property & fiscal context (display/regime only — NOT a scored axis; A-shares
    # mean-revert). Attached so the daily brief / LLM narrator can cite the cycle.
    try:
        from engine import china_property
        latest["property"] = china_property.regime_context()
    except Exception as e:  # noqa: BLE001 — additive context, never break the engine
        log.warning("china property context failed: %s", e)
    with open(p / "latest.json", "w") as fh:
        json.dump(latest, fh, indent=2, default=str)
    log.info("china regime %s (%s) conf=%.2f liq=%s cycle=%s",
             quad, latest["quad_name"], latest["confidence"],
             latest["liquidity_overlay"], latest["cycle_tag"])
    return latest


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    print(json.dumps(run(), indent=2, default=str))
