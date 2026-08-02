"""Full-tree verification for immutable earnings evidence generations."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import (
    CLAIM_GRAPH_SCHEMA,
    FACT_PACK_SCHEMA,
    TERMINAL_TRANSCRIPT_SCHEMA,
    canonical_json_bytes,
    canonical_transcript_body_bytes,
    sha256_bytes,
    validate_evidence_pair,
    validate_terminal_transcript,
    verify_fact_pack_against_transcript,
    validate_manifest,
)


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_generation(out_dir: Path, manifest: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Verify marker, immutable manifest, every file hash/byte count and schema.

    Health deliberately does not merely inspect the root marker.  A consumer
    only receives a healthy result after every marker-referenced object has
    been read and its local receipt revalidated.
    """
    root = Path(out_dir)
    issues: list[str] = []
    marker_path = root / "manifest.json"
    try:
        marker_raw = marker_path.read_bytes()
        marker = _load_json(marker_path)
    except Exception as exc:  # noqa: BLE001
        return {"status": "invalid", "warnings": [f"marker_unreadable:{type(exc).__name__}"], "generation_id": None, "event_count": 0}
    if manifest is not None and dict(manifest) != marker:
        return {"status": "invalid", "warnings": ["provided_manifest_mismatch"], "generation_id": None, "event_count": 0}
    try:
        validate_manifest(marker)
        if marker_raw != canonical_json_bytes(marker):
            raise ValueError("marker is not canonical bytes")
    except Exception as exc:  # noqa: BLE001
        return {"status": "invalid", "warnings": [f"marker_contract:{exc}"], "generation_id": None, "event_count": 0}
    assert isinstance(marker, Mapping)
    generation_id = str(marker["generation_id"])
    generation = root / "generations" / generation_id
    try:
        immutable_manifest = (generation / "manifest.json").read_bytes()
        if immutable_manifest != marker_raw:
            issues.append("immutable_manifest_marker_mismatch")
    except OSError:
        issues.append("immutable_manifest_missing")
    parsed: dict[str, object] = {}
    for relative, block in marker["files"].items():
        assert isinstance(relative, str) and isinstance(block, Mapping)
        # The manifest validator accepts only generated paths, but retain an
        # explicit filesystem guard at this boundary before opening anything.
        if relative.startswith("/") or ".." in Path(relative).parts:
            issues.append(f"unsafe_path:{relative}")
            continue
        path = generation / relative
        try:
            body = path.read_bytes()
        except OSError:
            issues.append(f"missing:{relative}")
            continue
        if len(body) != block["bytes"]:
            issues.append(f"bytes:{relative}")
        if sha256_bytes(body) != block["sha256"]:
            issues.append(f"sha256:{relative}")
        try:
            item = json.loads(body.decode("utf-8"))
            expected_bytes = canonical_transcript_body_bytes(item) if block["schema"] == TERMINAL_TRANSCRIPT_SCHEMA else canonical_json_bytes(item)
            if expected_bytes != body:
                issues.append(f"noncanonical:{relative}")
            parsed[relative] = item
        except Exception:
            issues.append(f"json:{relative}")
    for key, event in marker["events"].items():
        assert isinstance(event, Mapping)
        fact_path, graph_path, source_path = event["fact_pack"], event["claim_graph"], event["source_body"]
        fact, graph = parsed.get(fact_path), parsed.get(graph_path)
        source_body = parsed.get(source_path)
        if fact is None or graph is None or source_body is None:
            continue
        try:
            if not isinstance(fact, Mapping) or not isinstance(graph, Mapping) or not isinstance(source_body, Mapping):
                raise ValueError("artifact is not an object")
            if fact.get("schema") != FACT_PACK_SCHEMA or graph.get("schema") != CLAIM_GRAPH_SCHEMA or source_body.get("schema") != TERMINAL_TRANSCRIPT_SCHEMA:
                raise ValueError("artifact schema mismatch")
            validate_evidence_pair(fact, graph)
            validate_terminal_transcript(source_body)
            verify_fact_pack_against_transcript(fact, source_body)
            if str(fact["source"]["body_sha256"]) != event["source_sha256"]:
                raise ValueError("event source revision mismatch")
            if f"{fact['event']['ticker']}/{fact['event']['transcript_id']}" != key:
                raise ValueError("event key mismatch")
        except Exception as exc:  # noqa: BLE001
            issues.append(f"pair:{key}:{exc}")
    if issues:
        return {
            "status": "invalid",
            "warnings": sorted(issues),
            "generation_id": generation_id,
            "event_count": len(marker["events"]),
        }
    return {
        "status": str(marker["status"]),
        "warnings": list(marker["warnings"]),
        "generation_id": generation_id,
        "event_count": len(marker["events"]),
    }
