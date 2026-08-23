#!/usr/bin/env python3
"""Run the frozen Dislocation P0-S1F exact-70 source selection.

The runner is intentionally source-blind: it reads only the frozen candidate
metadata and the A1R/freeze/policy metadata that binds the selection.  It does
not resolve a filing, materialize an SEC document, or accept a semantic, market,
price, outcome, model, or audit input.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.research.dislocation_p0_a1_lib import canonical_cik, canonical_json
from scripts.research.dislocation_p0_s1f_selection import (
    AUTHORITY,
    STRATA,
    SelectionBlocked,
    exact70_manifest,
    manifest_bytes,
    selection_margins_ok,
)


REQUIRED_UNIVERSE_SHA256 = "aca01d616b859a9e59381748b86cd65405eb3bf54b57a10b1d7faef32b51a733"
REQUIRED_UNIVERSE_ROWS = 277_549
REQUIRED_COMPLETE_CELLS = 146
REQUIRED_DESIGN_MANIFEST_SHA256 = "740454d9d229b28e71fe35c4eb599cb0d1912227c4c44448214e5159a3d13085"


class RunnerBlocked(RuntimeError):
    """The prospective source-selection boundary could not be verified."""


def _canonical_digest(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise RunnerBlocked(f"S1F_JSON_UNREADABLE:{path}:{exc}") from exc


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RunnerBlocked(code)


def _design_ciks(design_manifest: Mapping[str, Any]) -> list[str]:
    candidates = design_manifest.get("candidates")
    _require(isinstance(candidates, list) and len(candidates) == 20, "S1F_A1R_DESIGN_MANIFEST_INVALID")
    ciks = {canonical_cik(candidate.get("cik")) for candidate in candidates if isinstance(candidate, Mapping)}
    ciks.discard(None)
    _require(len(ciks) == 20, "S1F_A1R_DESIGN_CIKS_INVALID")
    return sorted(ciks)


def _validate_frozen_bindings(
    *,
    freeze: Mapping[str, Any],
    completion: Mapping[str, Any],
    design_manifest: Mapping[str, Any],
    universe_path: Path,
    design_manifest_path: Path,
    expected_universe_sha256: str,
    expected_universe_rows: int,
    expected_complete_cells: int,
    expected_design_manifest_sha256: str,
) -> list[str]:
    """Verify the prospective freeze/A1R facts before candidate JSON is loaded."""
    frozen_universe = freeze.get("frozen_candidate_universe")
    immutable_design = freeze.get("a1r_immutable_design_evidence")
    query_ledger = completion.get("query_ledger")
    completion_universe = completion.get("candidate_universe")
    completed_cache = completion.get("completed_cache")
    if not all(isinstance(value, Mapping) for value in (frozen_universe, immutable_design, query_ledger, completion_universe, completed_cache)):
        raise RunnerBlocked("S1F_FROZEN_BINDING_SHAPE_INVALID")
    _require(freeze.get("status") == "FROZEN_PROSPECTIVE", "S1F_NOT_PROSPECTIVELY_FROZEN")
    _require(frozen_universe.get("candidate_universe_file_sha256") == expected_universe_sha256, "S1F_UNIVERSE_SHA_NOT_FROZEN")
    _require(frozen_universe.get("candidate_count") == expected_universe_rows, "S1F_UNIVERSE_COUNT_NOT_FROZEN")
    _require(frozen_universe.get("complete_cells") == expected_complete_cells, "S1F_COMPLETE_CELLS_NOT_FROZEN")
    _require(completion.get("status") == "COMPLETE", "S1F_A1R_COMPLETION_NOT_COMPLETE")
    _require(query_ledger.get("logical_cells") == expected_complete_cells, "S1F_A1R_LOGICAL_CELLS_INVALID")
    _require(query_ledger.get("complete_cells") == expected_complete_cells, "S1F_A1R_COMPLETION_146_OF_146_REQUIRED")
    _require(query_ledger.get("complete_cell_sha256") == frozen_universe.get("complete_cell_sha256"), "S1F_A1R_COMPLETE_CELL_HASH_MISMATCH")
    _require(completed_cache.get("incomplete_records") == 0, "S1F_A1R_COMPLETED_CACHE_INCOMPLETE")
    _require(completion_universe.get("count") == expected_universe_rows, "S1F_A1R_UNIVERSE_COUNT_INVALID")
    _require(completion_universe.get("raw_sha256") == expected_universe_sha256, "S1F_A1R_UNIVERSE_SHA_INVALID")
    _require(_file_sha256(universe_path) == expected_universe_sha256, "S1F_UNIVERSE_SHA_MISMATCH")
    _require(_file_sha256(design_manifest_path) == expected_design_manifest_sha256, "S1F_A1R_DESIGN_MANIFEST_SHA_MISMATCH")
    _require(immutable_design.get("exact20_selection_file_sha256") == expected_design_manifest_sha256, "S1F_A1R_DESIGN_NOT_BOUND_BY_FREEZE")
    _require(design_manifest.get("manifest_sha256") == "e436c6e87870468d0df0449c86cc9b69a9d23aa1396885fffdfcbfcf6398852e", "S1F_A1R_DESIGN_LOGICAL_HASH_MISMATCH")
    design_ciks = _design_ciks(design_manifest)
    _require(design_ciks == list(immutable_design.get("design_ciks", ())), "S1F_A1R_DESIGN_CIK_SET_MISMATCH")
    return design_ciks


def _packet_id(candidate: Mapping[str, Any]) -> str:
    return f"s1f_packet_{candidate['selection_key']}"


def _selection_logical_hash(candidates: Sequence[Mapping[str, Any]]) -> str:
    return _canonical_digest({
        "selection_identity": ["cik", "accession"],
        "packets": [
            {
                "packet_id": _packet_id(candidate),
                "stratum": candidate["stratum"],
                "era": candidate["era"],
                "form": candidate["form"],
                "cik": candidate["cik"],
                "accession": candidate["accession"],
                "selection_key": candidate["selection_key"],
            }
            for candidate in candidates
        ],
    })


def _batch_plan(
    *, policy: Mapping[str, Any], policy_sha256: str, candidates: Sequence[Mapping[str, Any]],
    selection_logical_sha256: str, universe_sha256: str,
) -> dict[str, Any]:
    batches = policy.get("batches")
    _require(isinstance(batches, list) and len(batches) == len(STRATA), "S1F_BATCH_POLICY_INVALID")
    planned_batches: list[dict[str, Any]] = []
    seen_packet_ids: set[str] = set()
    for expected_stratum, definition in zip(STRATA, batches, strict=True):
        _require(isinstance(definition, Mapping), "S1F_BATCH_POLICY_INVALID")
        _require(definition.get("retrieval_stratum") == expected_stratum, "S1F_BATCH_POLICY_ORDER_MISMATCH")
        selected = sorted(
            (candidate for candidate in candidates if candidate["stratum"] == expected_stratum),
            key=lambda candidate: str(candidate["selection_key"]),
        )
        _require(len(selected) == 10 and definition.get("packet_count") == 10, "S1F_BATCH_PACKET_MARGIN_BREACH")
        packets = [
            {
                "packet_id": _packet_id(candidate),
                "cik": candidate["cik"],
                "accession": candidate["accession"],
                "selection_key": candidate["selection_key"],
            }
            for candidate in selected
        ]
        _require(not (seen_packet_ids & {packet["packet_id"] for packet in packets}), "S1F_BATCH_DUPLICATE_PACKET")
        seen_packet_ids.update(packet["packet_id"] for packet in packets)
        planned_batches.append({
            "batch_id": definition.get("batch_id"),
            "retrieval_stratum": expected_stratum,
            "packet_count": 10,
            "packets": packets,
        })
    _require(len(seen_packet_ids) == 70, "S1F_BATCH_PLAN_NOT_EXACT70")
    plan = {
        "schema": "mastermind.dislocation_p0.s1f_exact70_audit_batch_plan.v1",
        "frozen_candidate_universe_sha256": universe_sha256,
        "selection_logical_sha256": selection_logical_sha256,
        "audit_batch_policy_file_sha256": policy_sha256,
        "batch_order": [batch["batch_id"] for batch in planned_batches],
        "batches": planned_batches,
        "authority": dict(AUTHORITY),
    }
    plan["batch_plan_sha256"] = _canonical_digest(plan)
    return plan


def run(
    *, universe_path: Path, freeze_path: Path, completion_path: Path, design_manifest_path: Path,
    policy_path: Path, output_dir: Path, expected_universe_sha256: str = REQUIRED_UNIVERSE_SHA256,
    expected_universe_rows: int = REQUIRED_UNIVERSE_ROWS, expected_complete_cells: int = REQUIRED_COMPLETE_CELLS,
    expected_design_manifest_sha256: str = REQUIRED_DESIGN_MANIFEST_SHA256,
) -> dict[str, Any]:
    """Validate frozen metadata, select exact-70, and write canonical artifacts."""
    freeze = _read_json(freeze_path)
    completion = _read_json(completion_path)
    design_manifest = _read_json(design_manifest_path)
    policy = _read_json(policy_path)
    _require(all(isinstance(value, Mapping) for value in (freeze, completion, design_manifest, policy)), "S1F_METADATA_SHAPE_INVALID")
    design_ciks = _validate_frozen_bindings(
        freeze=freeze, completion=completion, design_manifest=design_manifest,
        universe_path=universe_path, design_manifest_path=design_manifest_path,
        expected_universe_sha256=expected_universe_sha256, expected_universe_rows=expected_universe_rows,
        expected_complete_cells=expected_complete_cells, expected_design_manifest_sha256=expected_design_manifest_sha256,
    )
    rows = _read_json(universe_path)
    _require(isinstance(rows, list) and len(rows) == expected_universe_rows, "S1F_UNIVERSE_ROW_COUNT_MISMATCH")
    manifest = exact70_manifest(rows, design_ciks=design_ciks, frozen_universe_sha256=expected_universe_sha256)
    candidates = manifest["candidates"]
    _require(selection_margins_ok(candidates), "S1F_EXACT70_MARGIN_BREACH")
    selected_ciks = {candidate["cik"] for candidate in candidates}
    _require(not (selected_ciks & set(design_ciks)), "S1F_DESIGN_CIK_EXCLUSION_BREACH")
    selection_logical_sha256 = _selection_logical_hash(candidates)
    policy_sha256 = _file_sha256(policy_path)
    batch_plan = _batch_plan(
        policy=policy, policy_sha256=policy_sha256, candidates=candidates,
        selection_logical_sha256=selection_logical_sha256, universe_sha256=expected_universe_sha256,
    )
    receipt = {
        "schema": "mastermind.dislocation_p0.s1f_exact70_selection_receipt.v1",
        "status": "COMPLETE",
        "frozen_candidate_universe_sha256": expected_universe_sha256,
        "candidate_count": expected_universe_rows,
        "a1r_candidate_universe": {
            "count": completion["candidate_universe"]["count"],
            "raw_sha256": completion["candidate_universe"]["raw_sha256"],
            "count_by_family": completion["candidate_universe"].get("count_by_family"),
            "pool_sha256_by_family": completion["candidate_universe"].get("pool_sha256_by_family"),
        },
        "a1r_completion": {
            "status": completion["status"],
            "logical_cells": completion["query_ledger"]["logical_cells"],
            "complete_cells": completion["query_ledger"]["complete_cells"],
            "complete_cell_sha256": completion["query_ledger"].get("complete_cell_sha256"),
        },
        "a1r_completed_cache": {
            "record_count": completion["completed_cache"]["record_count"],
            "incomplete_records": completion["completed_cache"]["incomplete_records"],
            "raw_sha256": completion["completed_cache"]["raw_sha256"],
        },
        "a1r_design_manifest_file_sha256": expected_design_manifest_sha256,
        "design_ciks_excluded": design_ciks,
        "design_cik_count": len(design_ciks),
        "selection_packet_manifest": "S1F_EXACT70_SOURCE_MANIFEST.json",
        "batch_plan": "S1F_EXACT70_AUDIT_BATCH_PLAN.json",
        "selection_count": len(candidates),
        "selection_identity_count": len({(candidate["cik"], candidate["accession"]) for candidate in candidates}),
        "selection_logical_sha256": selection_logical_sha256,
        "selection_manifest_sha256": manifest["manifest_sha256"],
        "batch_plan_sha256": batch_plan["batch_plan_sha256"],
        "authority": dict(AUTHORITY),
    }
    receipt["receipt_sha256"] = _canonical_digest(receipt)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "manifest": output_dir / "S1F_EXACT70_SOURCE_MANIFEST.json",
        "receipt": output_dir / "S1F_EXACT70_SELECTION_RECEIPT.json",
        "batch_plan": output_dir / "S1F_EXACT70_AUDIT_BATCH_PLAN.json",
    }
    outputs["manifest"].write_bytes(manifest_bytes(manifest))
    outputs["receipt"].write_bytes((canonical_json(receipt) + "\n").encode("utf-8"))
    outputs["batch_plan"].write_bytes((canonical_json(batch_plan) + "\n").encode("utf-8"))
    return {"manifest": manifest, "receipt": receipt, "batch_plan": batch_plan, "outputs": outputs}


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, default=root / "research/dislocation_intelligence/p0_s1f/S1F_PROSPECTIVE_FREEZE_RECEIPT.json")
    parser.add_argument("--completion", type=Path, required=True)
    parser.add_argument("--design-manifest", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=root / "research/dislocation_intelligence/p0_s1f/S1F_AUDIT_BATCH_POLICY.json")
    parser.add_argument("--output-dir", type=Path, default=root / "research/dislocation_intelligence/p0_s1f")
    args = parser.parse_args()
    try:
        result = run(
            universe_path=args.universe, freeze_path=args.freeze, completion_path=args.completion,
            design_manifest_path=args.design_manifest, policy_path=args.policy, output_dir=args.output_dir,
        )
    except (RunnerBlocked, SelectionBlocked) as exc:
        print(f"S1F_SELECTION_BLOCKED:{exc}")
        return 2
    print(canonical_json({
        "status": result["receipt"]["status"],
        "selection_logical_sha256": result["receipt"]["selection_logical_sha256"],
        "selection_manifest_sha256": result["receipt"]["selection_manifest_sha256"],
        "batch_plan_sha256": result["receipt"]["batch_plan_sha256"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
