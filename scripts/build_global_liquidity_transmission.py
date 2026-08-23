#!/usr/bin/env python3
"""Build the W-LIQ.1 state-only contract, history, and frozen comparison receipt."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
ROOT = _ROOT

from engine.global_liquidity_transmission import (  # noqa: E402
    build_contract,
    load_producer_config,
    walk_forward_factor_comparison,
)
from lib import store  # noqa: E402


CONTRACT_PATH = ROOT / "site/liquiditydata/global_liquidity_transmission.json"
HISTORY_PATH = ROOT / "data/global_liquidity_transmission/state_history.parquet"
HISTORY_META_PATH = ROOT / "data/global_liquidity_transmission/state_history_meta.json"
COMPARISON_PATH = ROOT / "data/global_liquidity_transmission/factor_comparison_btc_4w.json"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")


def preserve_first_known(payload: dict, previous: dict | None) -> dict:
    """Keep the earliest first-known clock for an exact immutable source retry."""
    if not previous:
        return payload
    if previous.get("meta", {}).get("source_snapshot_hash") != payload["meta"]["source_snapshot_hash"]:
        return payload
    old_clock = (
        previous.get("state", {})
        .get("event_reference", {})
        .get("clocks", {})
        .get("first_known_at")
    )
    if not old_clock:
        return payload
    payload["state"]["event_reference"]["clocks"]["first_known_at"] = old_clock
    payload["freshness"]["clocks"]["first_known_at"] = old_clock
    return payload


def build(asof: str | None = None) -> dict:
    producer_cfg = load_producer_config()
    generated_at = datetime.now(timezone.utc)
    payload, history = build_contract(
        producer_cfg=producer_cfg,
        root=ROOT,
        asof=asof,
        generated_at=generated_at,
    )
    previous = None
    if CONTRACT_PATH.exists():
        try:
            previous = json.loads(CONTRACT_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            previous = None
    payload = preserve_first_known(payload, previous)

    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    history.to_parquet(HISTORY_PATH)
    _write_json(CONTRACT_PATH, payload)

    btc = store.read("yahoo", "BTC-USD")
    if btc is None or "close" not in btc:
        comparison = {
            "schema": "global_liquidity_transmission.factor_comparison.v1",
            "authority": "research_only_no_promotion",
            "status": "unavailable",
            "reason": "canonical yahoo/BTC-USD:close store missing",
        }
    else:
        comparison = walk_forward_factor_comparison(history, btc["close"])
        comparison["generated_at"] = generated_at.isoformat()
        comparison["history_cutoff"] = payload["state"]["asof"]
        comparison["source_snapshot_hash"] = payload["meta"]["source_snapshot_hash"]
        comparison["model_version"] = payload["meta"]["model_version"]
        comparison["data_version"] = payload["meta"]["data_version"]
    _write_json(COMPARISON_PATH, comparison)

    metadata = {
        "schema": "global_liquidity_transmission.history_meta.v1",
        "contract_schema": payload["meta"]["schema"],
        "producer_version": payload["meta"]["producer_version"],
        "model_version": payload["meta"]["model_version"],
        "data_version": payload["meta"]["data_version"],
        "source_snapshot_hash": payload["meta"]["source_snapshot_hash"],
        "config_hash": payload["meta"]["config_hash"],
        "generated_at": generated_at.isoformat(),
        "artifact": str(HISTORY_PATH.relative_to(ROOT)),
        "rows": len(history),
        "first_asof": str(history.index.min().date()),
        "last_asof": str(history.index.max().date()),
        "first_complete_state": (
            str(history.dropna(subset=["monetary_stance"]).index.min().date())
            if history["monetary_stance"].notna().any()
            else None
        ),
        "columns": list(history.columns),
        "pit_policy": payload["meta"]["pit_policy"],
        "historical_clock_law": {
            "observation_and_release": "reconstructed conservatively from economic reference dates and configured date-only lags",
            "first_known": "not reconstructable before the W-LIQ.1 producer existed; historical rows are not episode timestamps",
            "2023_2026_exact_episode_chronology": [],
            "chronology_status": "unavailable_do_not_infer_from_backfill",
        },
        "revision_law": payload["meta"]["revision_law"],
        "current_first_known_at": payload["state"]["event_reference"]["clocks"]["first_known_at"],
        "comparison_receipt": str(COMPARISON_PATH.relative_to(ROOT)),
    }
    _write_json(HISTORY_META_PATH, metadata)
    return {
        "contract": str(CONTRACT_PATH.relative_to(ROOT)),
        "history": str(HISTORY_PATH.relative_to(ROOT)),
        "history_meta": str(HISTORY_META_PATH.relative_to(ROOT)),
        "comparison": str(COMPARISON_PATH.relative_to(ROOT)),
        "asof": payload["state"]["asof"],
        "quality_status": payload["quality"]["status"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asof", help="Optional YYYY-MM-DD causal cutoff")
    args = parser.parse_args()
    print(json.dumps(build(args.asof), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
