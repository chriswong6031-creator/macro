#!/usr/bin/env python3
"""Stock Identity W3A — build the localization ruler artifacts (plan Tasks 2-3).

Reads the already-committed W2 pilot expert-event/attribution store and the W1
pilot episode catalog, computes the expert-independent per-fire metrics, the
unconditional block, the outcome-independent support/coverage frame, and — once
the shipped ``ruler_spec_v1.json`` no longer carries the PR-3 pending sentinel
(Task 3C) — the two graded composites. No per-name best-expert output, no blind
arm read, no ranking anywhere.

Usage::

    python3 scripts/stock_identity_build_ruler.py --pilot --output-dir /tmp/si-w3a-ruler-smoke
    python3 scripts/stock_identity_build_ruler.py --pilot --include-nulls --output-dir /tmp/si-w3a-ruler-smoke
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from engine.stock_identity.plane import load_symbol, primary_planes  # noqa: E402
from engine.stock_identity.ruler import (  # noqa: E402
    PendingSealedCalibrationError,
    RulerSpec,
    aggregate_cell_metrics,
    build_support_coverage,
    compute_composites,
    compute_fire_metrics,
    compute_unconditional_block,
)
from engine.stock_identity.ruler_nulls import (  # noqa: E402
    equal_proximity_control,
    grain_cadence_null,
    random_fire_null,
)

DATA = REPO_ROOT / "data" / "stock_identity"
EVENTS_DIR = DATA / "expert_events"
EPISODES_PATH = DATA / "episodes" / "pilot_episode_catalog_v0.parquet"
SPEC_PATH = DATA / "ruler" / "ruler_spec_v1.json"
FINGERPRINT_PATH = DATA / "fingerprints" / "pilot_fingerprint_v0.parquet"
PARTITION_MANIFEST_PATH = DATA / "partition" / "partition_manifest_v1.json"
CALIBRATION_REPLAY_MANIFEST_PATH = DATA / "ruler" / "calibration_replay_manifest_v1.json"

#: Deterministic seeds for the two seeded nulls, recorded here and in the W3
#: registration artifact (plan Task 3 Step 4 "seeds are deterministic and
#: recorded"). Never re-drawn per invocation.
RANDOM_NULL_SEED = 20260828
GRAIN_CADENCE_NULL_SEED = 20260829
EQUAL_PROXIMITY_TOLERANCE_ATR = 0.5


def _load_pilot_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    events = pd.read_parquet(EVENTS_DIR / "pilot_events_v0.parquet")
    attribution = pd.read_parquet(EVENTS_DIR / "attribution_v0.parquet")
    episodes = pd.read_parquet(EPISODES_PATH)
    return events, attribution, episodes


def _bars_by_symbol(symbols: list[str]) -> dict[str, pd.DataFrame]:
    manifest_planes: dict[str, str] = {}
    if PARTITION_MANIFEST_PATH.exists():
        manifest = json.loads(PARTITION_MANIFEST_PATH.read_text(encoding="utf-8"))
        manifest_planes = dict(manifest.get("universe", {}).get("plane_by_symbol", {}))
    live_planes = primary_planes(REPO_ROOT)

    out: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        plane_id = manifest_planes.get(sym) or live_planes.get(sym)
        if not plane_id:
            continue
        try:
            out[sym] = load_symbol(sym, plane_id, REPO_ROOT)
        except (FileNotFoundError, ValueError):
            continue
    return out


def _feature_symbols() -> set[str]:
    if not FINGERPRINT_PATH.exists():
        return set()
    try:
        df = pd.read_parquet(FINGERPRINT_PATH, columns=["symbol"])
    except Exception:
        return set()
    return set(df["symbol"].astype(str))


def _censored_counts(episodes: pd.DataFrame) -> dict[str, int]:
    if episodes is None or episodes.empty:
        return {"n_episodes": 0, "n_censored": 0}
    return {
        "n_episodes": int(len(episodes)),
        "n_censored": int(episodes["censored"].sum()),
    }


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)


def _family_universe() -> list[str]:
    """The W2 family registry's family_key set, read from the already-committed
    calibration replay manifest (``w2_family_registry_reuse.spec_hashes_at_manifest_freeze``
    keys ARE the real family_key strings, frozen at manifest-freeze time) rather
    than re-invoking the live, heavy ``stage_registry()`` machinery here — this
    script only needs the family NAME set, not a fresh registry build (freeze
    review finding M10)."""
    if not CALIBRATION_REPLAY_MANIFEST_PATH.exists():
        return []
    manifest = json.loads(CALIBRATION_REPLAY_MANIFEST_PATH.read_text(encoding="utf-8"))
    hashes = manifest.get("w2_family_registry_reuse", {}).get("spec_hashes_at_manifest_freeze", {})
    return sorted(hashes.keys())


def build(output_dir: Path, *, include_nulls: bool) -> dict[str, Any]:
    events, attribution, episodes = _load_pilot_inputs()
    symbols = sorted(set(episodes["symbol"].astype(str)) | set(events["symbol"].astype(str)))
    bars = _bars_by_symbol(symbols)
    spec = RulerSpec.from_json(SPEC_PATH)

    fire_metrics = compute_fire_metrics(events, attribution, episodes, bars, spec)
    families = _family_universe()
    universe = [(fam, sym) for fam in families for sym in symbols] if families else None
    unconditional = compute_unconditional_block(events, attribution, episodes, universe=universe)
    support = build_support_coverage(events, attribution, episodes, bars, _feature_symbols())
    cells = aggregate_cell_metrics(fire_metrics, episodes, spec)

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_parquet(fire_metrics, output_dir / "fire_metrics_v1.parquet")
    _write_parquet(unconditional, output_dir / "unconditional_block_v1.parquet")
    _write_parquet(support, output_dir / "support_coverage_v1.parquet")
    _write_parquet(cells, output_dir / "cell_metrics_v1.parquet")

    manifest: dict[str, Any] = {
        "schema": "stock_identity.w3a_ruler_smoke.v1",
        "spec_hash": spec.spec_hash(),
        "pr3_pending": spec.pr3_pending,
        "n_symbols": len(symbols),
        "n_fire_metric_rows": int(len(fire_metrics)),
        "n_unconditional_rows": int(len(unconditional)),
        "n_support_rows": int(len(support)),
        "n_cell_rows": int(len(cells)),
        "censored_counts": _censored_counts(episodes),
        "authority": dict(spec.authority),
        "no_blind_name_table": True,
        "no_rank_or_best_output": True,
        "n_families_in_universe": len(families),
        "n_no_coverage_rows": (
            int(unconditional["no_coverage"].sum()) if "no_coverage" in unconditional.columns else 0
        ),
        # MINORS: the same provisional-basis tag the support frame's own
        # calendar_block_basis column carries, surfaced in the build summary too.
        "calendar_block_basis": "calendar_quarter_provisional",
    }

    if spec.pr3_pending:
        manifest["composites"] = "composites_pending_sealed_calibration"
    else:
        try:
            composites = compute_composites(cells, spec)
        except PendingSealedCalibrationError:
            manifest["composites"] = "composites_pending_sealed_calibration"
        else:
            _write_parquet(composites, output_dir / "composites_v1.parquet")
            manifest["composites"] = "computed"
            manifest["n_composite_rows"] = int(len(composites))
            manifest["graded_composites_present"] = [
                c for c in spec.graded_composites if c in composites.columns
            ]

    if include_nulls:
        # attribution recompute is a future wave's job; the event-sequence-level
        # null CONTROLS here (plan Task 3 Step 2) are sufficient to test
        # count/placement and cadence invariance without re-running attribution.
        random_null_events = random_fire_null(events, bars, seed=RANDOM_NULL_SEED)
        grain_null_events = grain_cadence_null(events, bars, seed=GRAIN_CADENCE_NULL_SEED)
        proximity, proximity_truncated = equal_proximity_control(fire_metrics, EQUAL_PROXIMITY_TOLERANCE_ATR)

        _write_parquet(random_null_events, output_dir / "null_random_fire_events_v1.parquet")
        _write_parquet(grain_null_events, output_dir / "null_grain_cadence_events_v1.parquet")
        _write_parquet(proximity, output_dir / "equal_proximity_control_v1.parquet")
        # parquet-side summary alongside the pairs artifact (freeze review M2/M3 —
        # any truncation must be emitted, not silently dropped; zero is expected).
        (output_dir / "equal_proximity_summary_v1.json").write_text(
            json.dumps(
                {"n_pairs": int(len(proximity)), "equal_proximity_pairs_truncated": proximity_truncated},
                indent=2, sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        manifest["nulls"] = {
            "random_fire_seed": RANDOM_NULL_SEED,
            "random_fire_rows": int(len(random_null_events)),
            "grain_cadence_seed": GRAIN_CADENCE_NULL_SEED,
            "grain_cadence_rows": int(len(grain_null_events)),
            "equal_proximity_tolerance_atr": EQUAL_PROXIMITY_TOLERANCE_ATR,
            "equal_proximity_pairs": int(len(proximity)),
            "equal_proximity_pairs_truncated": proximity_truncated,
        }

    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pilot", action="store_true", required=True,
                    help="build over the committed W2 pilot cohort (the only supported source)")
    ap.add_argument("--include-nulls", action="store_true")
    ap.add_argument("--output-dir", required=True, type=Path)
    args = ap.parse_args()

    manifest = build(args.output_dir, include_nulls=args.include_nulls)
    print(json.dumps(manifest, indent=2, sort_keys=True, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
