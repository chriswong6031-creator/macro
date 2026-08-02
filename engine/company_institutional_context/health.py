"""Integrity checks for immutable Company Institutional Context generations."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from engine.company_intelligence.contracts import ContractError

from .contracts import bytes_sha256, canonical_json_bytes, company_filename, validate_context, validate_manifest
from .views import derive_generation_id


def _read(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def validate_generation(out_dir: Path, manifest: Mapping[str, Any] | None = None) -> dict[str, Any]:
    marker = dict(manifest) if isinstance(manifest, Mapping) else _read(out_dir / "manifest.json")
    if marker is None:
        return {"status": "empty", "warnings": ["manifest_missing"], "company_count": 0, "position_record_count": 0}
    try:
        validate_manifest(marker)
    except ContractError as exc:
        return {"status": "degraded", "warnings": [f"manifest_invalid:{exc}"], "company_count": 0, "position_record_count": 0}
    generation = out_dir / "generations" / str(marker["generation_id"])
    warnings: list[str] = []
    immutable = _read(generation / "manifest.json")
    if immutable is None:
        warnings.append("generation_manifest_missing")
    elif canonical_json_bytes(immutable) != canonical_json_bytes(marker):
        warnings.append("generation_manifest_mismatch")
    contexts: dict[str, dict[str, Any]] = {}
    records = 0
    covered = 0
    for relative, receipt in sorted(marker["files"].items()):
        path = generation / relative
        if not path.is_file() or path.stat().st_size != receipt["bytes"] or bytes_sha256(path) != receipt["sha256"]:
            warnings.append(f"file_mismatch:{relative}")
            continue
        context = _read(path)
        try:
            validate_context(context)
            if context is None or context["generation_id"] != marker["generation_id"]:
                raise ContractError("generation mismatch")
            ticker = context["company"]["ticker"]
            if relative != company_filename(ticker) or ticker in contexts:
                raise ContractError("filename ticker does not match payload company ticker")
            contexts[ticker] = context
            records += len(context["positions"])
            covered += int(context["consensus"]["current_holder_count"] > 0)
        except ContractError as exc:
            warnings.append(f"context_invalid:{relative}:{exc}")
    if len(marker["files"]) != marker["company_count"]:
        warnings.append("company_count_mismatch")
    if records != marker["position_record_count"]:
        warnings.append("position_record_count_mismatch")
    if covered != marker["covered_company_count"]:
        warnings.append("covered_company_count_mismatch")
    if not warnings:
        try:
            if derive_generation_id(contexts, marker) != marker["generation_id"]:
                warnings.append("generation_identity_mismatch")
        except (ContractError, TypeError, ValueError) as exc:
            warnings.append(f"generation_identity_invalid:{exc}")
    return {
        "status": "degraded" if warnings else marker["status"],
        "warnings": warnings or list(marker["warnings"]),
        "company_count": marker["company_count"],
        "position_record_count": marker["position_record_count"],
        "generation_id": marker["generation_id"],
    }


def build_health(out_dir: Path) -> dict[str, Any]:
    return validate_generation(out_dir)
