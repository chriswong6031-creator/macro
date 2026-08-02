"""Immutable local generation writer for earnings evidence artifacts."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from .contracts import (
    AUTHORITY,
    CLAIM_GRAPH_SCHEMA,
    EXECUTION_RECEIPT,
    FACT_PACK_SCHEMA,
    KNOWN_OMISSIONS,
    MANIFEST_SCHEMA,
    TERMINAL_TRANSCRIPT_SCHEMA,
    canonical_transcript_body_bytes,
    canonical_json_bytes,
    canonical_json_sha256,
    event_key,
    sha256_bytes,
    validate_evidence_pair,
    verify_fact_pack_against_transcript,
    validate_manifest,
)


@dataclass(frozen=True)
class EvidencePair:
    fact_pack: Mapping[str, Any]
    claim_graph: Mapping[str, Any]
    transcript: Mapping[str, Any]


def _prior_events(prior_manifest: object | None) -> dict[str, Mapping[str, Any]]:
    if not isinstance(prior_manifest, Mapping):
        return {}
    try:
        validate_manifest(prior_manifest)
    except Exception:  # noqa: BLE001 - a damaged local marker cannot grant lineage.
        return {}
    events = prior_manifest.get("events")
    assert isinstance(events, Mapping)
    return {
        str(key): value
        for key, value in events.items()
        if isinstance(value, Mapping)
    }


def _normalise_omissions(omissions: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for omission in omissions:
        event = str(omission.get("event_key") or "")
        reason = str(omission.get("reason") or "")
        expected = omission.get("expected_source_sha256")
        if not event or reason not in KNOWN_OMISSIONS:
            raise ValueError("invalid evidence generation omission")
        output.append({
            "event_key": event,
            "reason": reason,
            "expected_source_sha256": str(expected) if expected is not None else None,
        })
    output.sort(key=lambda item: item["event_key"])
    if len({item["event_key"] for item in output}) != len(output):
        raise ValueError("duplicate evidence generation omission")
    return output


def build_generation(
    pairs: Iterable[EvidencePair],
    *,
    prior_manifest: object | None = None,
    warnings: Iterable[str] = (),
    omissions: Iterable[Mapping[str, Any]] = (),
    coverage: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Build a content-addressed generation and its complete immutable files."""
    previous = _prior_events(prior_manifest)
    collected: dict[str, EvidencePair] = {}
    for pair in pairs:
        validate_evidence_pair(pair.fact_pack, pair.claim_graph)
        verify_fact_pack_against_transcript(pair.fact_pack, pair.transcript)
        key = event_key(pair.fact_pack["event"])
        if key in collected:
            raise ValueError(f"duplicate evidence pair: {key}")
        collected[key] = pair
    artifacts: dict[str, bytes] = {}
    events: dict[str, dict[str, Any]] = {}
    generated_at: list[str] = []
    # Root warnings describe selection/coverage only.  Per-event warnings and
    # insufficiency stay inside their own fact pack/graph, so one weak call
    # cannot suppress a verified healthy corpus.
    inherited_warnings = set(warnings)
    for key in sorted(collected):
        pair = collected[key]
        source_sha = str(pair.fact_pack["source"]["body_sha256"])
        generated_at.append(str(pair.fact_pack["source"]["index_generated_at"]))
        fact_path = f"fact_packs/{key}.json"
        graph_path = f"claim_graphs/{key}.json"
        source_path = f"source_bodies/{source_sha}.json"
        artifacts[fact_path] = canonical_json_bytes(pair.fact_pack)
        artifacts[graph_path] = canonical_json_bytes(pair.claim_graph)
        source_body = canonical_transcript_body_bytes(pair.transcript)
        existing_source = artifacts.get(source_path)
        if existing_source is not None and existing_source != source_body:
            raise ValueError(f"source body hash collision: {source_path}")
        artifacts[source_path] = source_body
        previous_event = previous.get(key)
        old_sha = str(previous_event["source_sha256"]) if previous_event is not None else None
        prior_supersedes = previous_event.get("supersedes_source_sha256") if previous_event is not None else None
        events[key] = {
            "source_sha256": source_sha,
            "supersedes_source_sha256": old_sha if old_sha and old_sha != source_sha else prior_supersedes,
            "fact_pack": fact_path,
            "claim_graph": graph_path,
            "source_body": source_path,
        }
    normalized_omissions = _normalise_omissions(omissions)
    # No current evidence is an explicit partial result, never a plausible
    # empty "ready" corpus.  The publisher will refuse partial markers.
    if not collected:
        inherited_warnings.add("no_selected_bodies")
    manifest_warnings = sorted(inherited_warnings)
    files = {
        path: {
            "sha256": sha256_bytes(body),
            "bytes": len(body),
            "schema": (
                FACT_PACK_SCHEMA if path.startswith("fact_packs/")
                else CLAIM_GRAPH_SCHEMA if path.startswith("claim_graphs/")
                else TERMINAL_TRANSCRIPT_SCHEMA
            ),
        }
        for path, body in sorted(artifacts.items())
    }
    generated = max(generated_at) if generated_at else "1970-01-01T00:00:00Z"
    dates = sorted(str(pair.fact_pack["event"]["date"]) for pair in collected.values())
    supplied_coverage = dict(coverage or {})
    expected_coverage_context = {
        "selection_policy", "cohort_limit", "historical_completeness", "index_body_count", "index_generated_at",
    }
    if supplied_coverage:
        if set(supplied_coverage) != expected_coverage_context:
            raise ValueError("coverage context fields mismatch")
    else:
        supplied_coverage = {
            "selection_policy": "explicit_input",
            "cohort_limit": max(1, len(collected)),
            "historical_completeness": False,
            "index_body_count": len(collected),
            "index_generated_at": generated,
        }
    generation_coverage = {
        **supplied_coverage,
        "event_count": len(collected),
        "oldest_call_date": dates[0] if dates else None,
        "newest_call_date": dates[-1] if dates else None,
    }
    status = "ready" if collected else "partial"
    unsigned = {
        "schema": MANIFEST_SCHEMA,
        "authority": AUTHORITY,
        "generation_id": "0" * 32,
        "generated_at": generated,
        "status": status,
        "warnings": manifest_warnings,
        "omissions": normalized_omissions,
        "coverage": generation_coverage,
        "events": events,
        "files": files,
        "execution": dict(EXECUTION_RECEIPT),
    }
    manifest = dict(unsigned)
    manifest["generation_id"] = canonical_json_sha256(unsigned)[:32]
    validate_manifest(manifest)
    return manifest, artifacts


def _read_local_marker(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read prior evidence marker: {exc}") from exc


def _atomic_bytes(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        temporary.write_bytes(body)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)


def _verify_existing_generation(target: Path, manifest: Mapping[str, Any], artifacts: Mapping[str, bytes]) -> None:
    expected = {**artifacts, "manifest.json": canonical_json_bytes(manifest)}
    for relative, body in expected.items():
        path = target / relative
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise ValueError(f"existing immutable generation is incomplete: {path}") from exc
        if existing != body:
            raise ValueError(f"immutable generation collision: {path}")


def write_generation(
    out_dir: Path,
    pairs: Iterable[EvidencePair],
    *,
    warnings: Iterable[str] = (),
    omissions: Iterable[Mapping[str, Any]] = (),
    coverage: Mapping[str, Any] | None = None,
    prior_manifest: object | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Write all immutable files before atomically advancing the local marker."""
    root = Path(out_dir)
    prior = prior_manifest if prior_manifest is not None else _read_local_marker(root / "manifest.json")
    manifest, artifacts = build_generation(pairs, prior_manifest=prior, warnings=warnings, omissions=omissions, coverage=coverage)
    generation = root / "generations" / str(manifest["generation_id"])
    if generation.exists():
        _verify_existing_generation(generation, manifest, artifacts)
    else:
        temporary = generation.with_name(f".{generation.name}.tmp.{os.getpid()}")
        temporary.mkdir(parents=True, exist_ok=False)
        try:
            for relative, body in artifacts.items():
                path = temporary / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
            (temporary / "manifest.json").write_bytes(canonical_json_bytes(manifest))
            generation.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.replace(temporary, generation)
            except FileExistsError:
                _verify_existing_generation(generation, manifest, artifacts)
        finally:
            # A failed write is intentionally not a marker promotion.  Clean
            # only the process-owned temporary files, never a prior generation.
            if temporary.exists():
                for path in sorted(temporary.rglob("*"), reverse=True):
                    if path.is_file():
                        path.unlink(missing_ok=True)
                    elif path.is_dir():
                        path.rmdir()
                temporary.rmdir()
    _atomic_bytes(root / "manifest.json", canonical_json_bytes(manifest))
    return generation, manifest
