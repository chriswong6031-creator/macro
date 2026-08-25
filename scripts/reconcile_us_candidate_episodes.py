"""Nightly-only immutable-generation writer for U.S. candidate episodes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Mapping, Sequence

import pyarrow as pa
import pyarrow.parquet as pq

from engine.ledger_lane import nightly_advance_enabled
from engine.us_candidate_episode import (
    DEFAULT_DEFINITION_ERA,
    GENERATION_MANIFEST_SCHEMA,
    HEAD_SCHEMA,
    PARQUET_JSON_FIELDS,
    RECONCILE_RECEIPT_SCHEMA,
    SUPPRESSION_REASONS,
    SUPPRESSION_SCHEMA,
    EpisodeContractError,
    _load_partitioned_events as _core_load_event_partitions,
    _load_partitioned_suppressions as _core_load_suppression_partitions,
    apply_commands,
    build_all_candidates,
    canonical_json,
    load_candidate_episode_store_snapshot,
    reconcile_observations,
    validate_candidate_episode_generation,
    validate_candidate_episode_generation_payload,
    validate_events,
    validate_suppressions,
)
from engine.us_candidate_episode_intake import (
    IntakeBatch,
    candidate_observations,
    door_observations,
    load_identity_spine,
    radar_observations,
    turn_watch_observations,
)


RECEIPT_SCHEMA = RECONCILE_RECEIPT_SCHEMA
_PARQUET_JSON_FIELDS = PARQUET_JSON_FIELDS
_SUPPRESSION_REASON_MAP = {
    "MISSING_TRIGGER": "NO_EVALUATED_TRIGGER",
    "UNEVALUATED_TRIGGER": "NO_EVALUATED_TRIGGER",
    "MISSING_RESET_LOW": "INVALID_STRUCTURAL_ANCHOR",
    "MALFORMED_RECEIPT": "SOURCE_RECEIPT_INVALID",
    "MISSING_EXPERT_EVENT_ID": "SOURCE_SCHEMA_UNSUPPORTED",
}


class ReconcileRefused(RuntimeError):
    """Raised before reads when a durable request is outside the nightly lane."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical_recorded_at(value: object) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise EpisodeContractError("recorded_at must be canonical RFC3339 UTC ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise EpisodeContractError("recorded_at must be canonical RFC3339 UTC") from exc
    if parsed.tzinfo is None:
        raise EpisodeContractError("recorded_at must be timezone-aware")
    canonical = parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    canonical = canonical.replace(".000000Z", "Z")
    if canonical != value:
        raise EpisodeContractError("recorded_at must use canonical RFC3339 UTC Z text")
    return canonical


def _sha_receipt(payload: bytes) -> str:
    return "sha256:" + sha256(payload).hexdigest()


def _jsonl_from_bytes(payload: bytes, *, source: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(payload.splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EpisodeContractError(f"{source}:{line_number} is not JSON") from exc
        if not isinstance(value, Mapping):
            raise EpisodeContractError(f"{source}:{line_number} must be a JSON object")
        rows.append(dict(value))
    return rows


def _load_commands_snapshot(path: Path | None) -> tuple[list[dict[str, object]], dict[str, object] | None]:
    if path is None:
        return [], None
    payload = Path(path).read_bytes()
    rows = _jsonl_from_bytes(payload, source=Path(path))
    canonical = b"" if not rows else ("\n".join(canonical_json(row) for row in rows) + "\n").encode("utf-8")
    if payload != canonical:
        raise EpisodeContractError("correction commands must be canonical JSONL")
    return rows, {"path": str(Path(path).resolve()), "sha256": _sha_receipt(payload)}


def _latest_turn_watch(data_root: Path) -> Path:
    paths = sorted((data_root / "us_prophet_rank" / "episode_inputs" / "turn_watch").glob("*.json"))
    return paths[-1] if paths else data_root / "us_prophet_rank" / "episode_inputs" / "turn_watch" / "missing.json"


def _load_intakes(data_root: Path, *, allow_degraded_identity: bool):
    try:
        spine = load_identity_spine(data_root)
    except OSError:
        if not allow_degraded_identity:
            raise
        spine = None
        batches = tuple(
            IntakeBatch((), (), ({"source": source, "status": "degraded",
                                  "reason": "MISSING_IDENTITY_SPINE"},))
            for source in ("turn_watch", "candidate", "doors", "entry_radar")
        )
        return (), batches
    batches = (
        turn_watch_observations(_latest_turn_watch(data_root), spine),
        candidate_observations(data_root, spine),
        door_observations(data_root / "prophet_doors" / "flags.jsonl", spine),
        radar_observations(data_root / "entry_radar" / "forward.parquet", spine),
    )
    return spine.source_receipts, batches


def _source_hashes(
    repo_root: Path,
    identity_receipts: Sequence[Mapping[str, object]],
    batches: Sequence[IntakeBatch],
    correction_receipt: Mapping[str, object] | None,
) -> dict[str, str]:
    file_receipts: list[Mapping[str, object]] = list(identity_receipts)
    for batch in batches:
        for receipt in batch.source_receipts:
            files = receipt.get("files", [])
            if isinstance(files, list):
                file_receipts.extend(item for item in files if isinstance(item, Mapping))
    if correction_receipt is not None:
        file_receipts.append(correction_receipt)
    result: dict[str, str] = {}
    for receipt in file_receipts:
        normalized = _canonical_source_file_receipt(repo_root, receipt)
        name, digest = normalized["path"], normalized["sha256"]
        prior = result.get(name)
        if prior is not None and prior != digest:
            raise EpisodeContractError("one source path produced conflicting once-read hashes")
        result[name] = digest
    return dict(sorted(result.items()))


def _canonical_source_file_receipt(
    repo_root: Path, receipt: Mapping[str, object],
) -> dict[str, str]:
    path, digest = receipt.get("path"), receipt.get("sha256")
    if not isinstance(path, str) or not isinstance(digest, str):
        raise EpisodeContractError("once-read source receipt is incomplete")
    source_path = Path(path).resolve()
    try:
        name = source_path.relative_to(Path(repo_root).resolve()).as_posix()
    except ValueError:
        name = source_path.as_posix()
    return {"path": name, "sha256": digest}


def _canonical_source_status_receipts(
    repo_root: Path, batches: Sequence[IntakeBatch],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for batch in batches:
        for receipt in batch.source_receipts:
            row = dict(receipt)
            files = row.get("files")
            if isinstance(files, list):
                normalized_files: list[dict[str, str]] = []
                for file_receipt in files:
                    if not isinstance(file_receipt, Mapping):
                        raise EpisodeContractError("once-read source receipt is incomplete")
                    normalized_files.append(
                        _canonical_source_file_receipt(repo_root, file_receipt)
                    )
                row["files"] = normalized_files
            rows.append(row)
    return rows


def _load_event_partitions(directory: Path) -> list[dict[str, object]]:
    return _core_load_event_partitions(directory)


def _load_suppression_partitions(directory: Path) -> list[dict[str, object]]:
    return _core_load_suppression_partitions(directory)


def _resolve_current_generation(episode_root: Path):
    head_path = episode_root / "HEAD.json"
    if not head_path.exists():
        return None
    return load_candidate_episode_store_snapshot(episode_root)


def _load_existing_ledgers(episode_root: Path):
    snapshot = _resolve_current_generation(episode_root)
    if snapshot is None:
        return [], [], None, None
    generation = snapshot.generation
    return (
        list(generation.events),
        list(generation.suppressions),
        generation.path,
        dict(generation.receipt),
    )


def _command_semantic(command: Mapping[str, object]) -> dict[str, object]:
    required = {
        "event_type", "episode_id", "source_system", "source_schema", "source_event_id",
        "occurred_at", "known_at", "source_receipt", "payload",
    }
    missing = required - set(command)
    if missing:
        raise EpisodeContractError(f"command is missing {sorted(missing)[0]}")
    return {
        "event_type": command["event_type"],
        "episode_id": command["episode_id"],
        "source_system": command["source_system"],
        "source_schema": command["source_schema"],
        "source_event_id": command["source_event_id"],
        "occurred_at": command["occurred_at"],
        "known_at": command["known_at"],
        "source_receipt": command["source_receipt"],
        "definition_era": DEFAULT_DEFINITION_ERA,
        "correction_of": command.get("correction_of"),
        "payload": command["payload"],
    }


def _event_command_semantic(event: Mapping[str, object]) -> dict[str, object]:
    return {key: event[key] for key in (
        "event_type", "episode_id", "source_system", "source_schema", "source_event_id",
        "occurred_at", "known_at", "source_receipt", "definition_era", "correction_of", "payload",
    )}


def _dedupe_commands(events: Sequence[Mapping[str, object]], commands: Sequence[Mapping[str, object]]):
    existing = {
        (str(event["source_system"]), str(event["source_schema"]), str(event["source_event_id"])): event
        for event in events
    }
    accepted: list[dict[str, object]] = []
    seen_input: dict[tuple[str, str, str], str] = {}
    for raw in commands:
        command = dict(raw)
        semantic = _command_semantic(command)
        key = (
            str(semantic["source_system"]), str(semantic["source_schema"]),
            str(semantic["source_event_id"]),
        )
        encoded = canonical_json(semantic)
        prior_input = seen_input.get(key)
        if prior_input is not None:
            if prior_input != encoded:
                raise EpisodeContractError("correction source identity carries changed semantic payload")
            continue
        seen_input[key] = encoded
        prior = existing.get(key)
        if prior is not None:
            if canonical_json(_event_command_semantic(prior)) != encoded:
                raise EpisodeContractError("correction source identity carries changed semantic payload")
            continue
        accepted.append(command)
    return accepted


def _normalize_suppression(raw: Mapping[str, object], *, recorded_at: str) -> dict[str, object]:
    reason = _SUPPRESSION_REASON_MAP.get(str(raw.get("reason")), str(raw.get("reason")))
    if reason not in SUPPRESSION_REASONS:
        reason = "SOURCE_SCHEMA_UNSUPPORTED"
    source_receipt = raw.get("source_receipt")
    if reason == "SOURCE_RECEIPT_INVALID":
        source_receipt = None
    session = raw.get("observation_session")
    if not isinstance(session, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", session):
        session = recorded_at[:10]
    material: dict[str, object] = {
        "schema": SUPPRESSION_SCHEMA,
        "recorded_at": recorded_at,
        "source_system": raw.get("source_system"),
        "source_schema": raw.get("source_schema"),
        "source_event_id": raw.get("source_event_id"),
        "source_receipt": source_receipt,
        "observation_session": session,
        "ticker_at_observation": raw.get("ticker_at_observation"),
        "security_id": raw.get("security_id"),
        "reason": reason,
    }
    address = {key: value for key, value in material.items() if key != "recorded_at"}
    suppression_id = "pes:" + sha256(canonical_json(address).encode("utf-8")).hexdigest()
    row = {**material, "suppression_id": suppression_id}
    row["content_sha256"] = sha256(canonical_json(row).encode("utf-8")).hexdigest()
    return validate_suppressions([row])[0]


def _merge_suppressions(existing, additions, *, recorded_at: str):
    merged = {str(row["suppression_id"]): dict(row) for row in validate_suppressions(existing)}
    for raw in additions:
        candidate = _normalize_suppression(raw, recorded_at=recorded_at)
        key = str(candidate["suppression_id"])
        if key not in merged:
            merged[key] = candidate
    return sorted(merged.values(), key=lambda row: str(row["suppression_id"]))


def _parquet_bytes(rows: Sequence[Mapping[str, object]]) -> bytes:
    encoded = [{key: canonical_json(value) if key in _PARQUET_JSON_FIELDS else value
                for key, value in row.items()} for row in rows]
    table = pa.Table.from_pylist(encoded)
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink, compression="zstd", version="2.6", data_page_version="2.0",
                   use_dictionary=False, write_statistics=True)
    return sink.getvalue().to_pybytes()


def _source_accounting(batches: Sequence[IntakeBatch], reconciled_suppressions):
    suppression_keys = {(row.get("source_system"), row.get("source_schema"), row.get("source_event_id"))
                        for row in reconciled_suppressions}
    result: dict[str, dict[str, int]] = {}
    for batch in batches:
        source = next((str(item["source"]) for item in batch.source_receipts if item.get("source")), "unknown")
        core_suppressed = sum((row.get("source_system"), row.get("source_schema"),
                               row.get("source_event_id")) in suppression_keys
                              for row in batch.observations)
        input_count = len(batch.observations) + len(batch.suppressions)
        suppressed = len(batch.suppressions) + core_suppressed
        result[source] = {"input": input_count, "mapped": input_count - suppressed,
                          "suppressed": suppressed}
    return dict(sorted(result.items()))


def _stable_receipt(old: Mapping[str, object], new: Mapping[str, object]) -> bool:
    return all(old.get(field) == new.get(field) for field in (
        "schema", "mode", "gate", "definition_era", "source_hashes", "source_counts",
        "ledger_sha256", "projection_hashes", "source_receipts",
    ))


def _load_and_build(*, repo_root: Path, recorded_at: str, correction_path: Path | None, mode: str):
    data_root = repo_root / "data"
    episode_root = data_root / "us_prophet_rank" / "episodes"
    (existing_events, existing_suppressions, current_generation,
     previous_receipt) = _load_existing_ledgers(episode_root)
    identity_receipts, batches = _load_intakes(data_root, allow_degraded_identity=mode != "nightly")
    observations = [row for batch in batches for row in batch.observations]
    intake_suppressions = [row for batch in batches for row in batch.suppressions]
    reconciled = reconcile_observations(existing_events, observations, recorded_at=recorded_at,
                                        definition_era=DEFAULT_DEFINITION_ERA)
    commands, correction_receipt = _load_commands_snapshot(correction_path)
    commands = _dedupe_commands(reconciled.events, commands)
    commanded = apply_commands(reconciled.events, commands, recorded_at=recorded_at,
                               definition_era=DEFAULT_DEFINITION_ERA)
    run_suppressions = [*intake_suppressions, *reconciled.suppressions]
    suppressions = _merge_suppressions(existing_suppressions, run_suppressions,
                                       recorded_at=recorded_at)
    projection = build_all_candidates(commanded.events, suppression_count=len(suppressions))
    projection_json = (canonical_json(projection) + "\n").encode("utf-8")
    projection_parquet = _parquet_bytes(projection["episodes"])
    source_counts = _source_accounting(batches, reconciled.suppressions)
    input_count = sum(row["input"] for row in source_counts.values())
    mapped_count = sum(row["mapped"] for row in source_counts.values())
    suppressed_count = sum(row["suppressed"] for row in source_counts.values())
    if input_count != mapped_count + suppressed_count:
        raise EpisodeContractError("aggregate source accounting is unbalanced")
    ledger_hash = _sha_receipt(canonical_json(tuple(commanded.events)).encode("utf-8"))
    receipt: dict[str, object] = {
        "schema": RECEIPT_SCHEMA,
        "mode": mode,
        "gate": {"nightly_requested": mode == "nightly", "nightly_advance_enabled": mode == "nightly"},
        "durable_write": False,
        "recorded_at": recorded_at,
        "definition_era": DEFAULT_DEFINITION_ERA,
        "source_hashes": _source_hashes(repo_root, identity_receipts, batches, correction_receipt),
        "source_counts": source_counts,
        "counts": {
            "input": input_count, "mapped": mapped_count, "suppressed": suppressed_count,
            "ledger_suppressions": len(suppressions),
            "old_events": len(existing_events), "new_events": len(commanded.events),
            "appended_events": len(commanded.events) - len(existing_events),
        },
        "ledger_sha256": ledger_hash,
        "projection_hashes": {
            "all_candidates.json": _sha_receipt(projection_json),
            "current.parquet": _sha_receipt(projection_parquet),
        },
        "source_receipts": _canonical_source_status_receipts(repo_root, batches),
    }
    return (receipt, projection, list(commanded.events), suppressions, projection_parquet,
            current_generation, previous_receipt)


def _event_order(row: Mapping[str, object]):
    return str(row["known_at"]), str(row["source_system"]), str(row["source_event_id"])


def _jsonl_bytes(rows: Sequence[Mapping[str, object]]) -> bytes:
    return ("" if not rows else "\n".join(canonical_json(row) for row in rows) + "\n").encode()


def _generation_payloads(receipt, projection, events, suppressions, projection_parquet):
    by_event_month: dict[str, list[Mapping[str, object]]] = {}
    for row in sorted(events, key=_event_order):
        by_event_month.setdefault(str(row["recorded_at"])[:7], []).append(row)
    by_suppression_month: dict[str, list[Mapping[str, object]]] = {}
    for row in sorted(suppressions, key=lambda value: str(value["suppression_id"])):
        by_suppression_month.setdefault(str(row["recorded_at"])[:7], []).append(row)
    payloads = {f"events/{month}.jsonl": _jsonl_bytes(rows)
                for month, rows in sorted(by_event_month.items())}
    payloads.update({f"suppressions/{month}.jsonl": _jsonl_bytes(rows)
                     for month, rows in sorted(by_suppression_month.items())})
    payloads.update({
        "all_candidates.json": (canonical_json(projection) + "\n").encode(),
        "current.parquet": projection_parquet,
        "latest_receipt.json": (canonical_json(receipt) + "\n").encode(),
    })
    return payloads


def _write_fsynced(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _mkdirs_fsynced(path: Path) -> None:
    """Create each missing directory and durably persist its parent entry before continuing."""
    target = Path(path)
    missing: list[Path] = []
    cursor = target
    while not cursor.exists():
        missing.append(cursor)
        if cursor == cursor.parent:
            raise EpisodeContractError("cannot find an existing parent for durable directory creation")
        cursor = cursor.parent
    if not cursor.is_dir():
        raise EpisodeContractError("durable directory parent is not a directory")
    for directory in reversed(missing):
        directory.mkdir()
        _fsync_directory(directory.parent)
    if not target.is_dir():
        raise EpisodeContractError("durable directory target is not a directory")


def _fsync_tree(root: Path) -> None:
    directories = [root, *(path for path in root.rglob("*") if path.is_dir())]
    for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        _fsync_directory(directory)


def _validate_generation_payload(directory: Path) -> None:
    validate_candidate_episode_generation_payload(directory)


def _manifest_for(directory: Path):
    files: dict[str, dict[str, object]] = {}
    for path in sorted(directory.rglob("*")):
        relative = str(path.relative_to(directory))
        if not path.is_file() or relative == "manifest.json":
            continue
        payload = path.read_bytes()
        files[relative] = {
            "sha256": _sha_receipt(payload), "bytes": len(payload),
        }
    material = {"schema": GENERATION_MANIFEST_SCHEMA, "files": files}
    generation_id = "peg:" + sha256(canonical_json(material).encode()).hexdigest()
    manifest = {**material, "generation_id": generation_id}
    manifest["content_sha256"] = sha256(canonical_json(manifest).encode()).hexdigest()
    return generation_id, manifest


def _validate_generation_directory(directory: Path, expected_generation_id: str) -> None:
    validate_candidate_episode_generation(directory, expected_generation_id=expected_generation_id)


def _install_generation(stage: Path, destination: Path) -> None:
    if destination.exists():
        _validate_generation_directory(destination, destination.name)
        shutil.rmtree(stage)
        return
    os.rename(stage, destination)
    _fsync_directory(destination.parent)


def _replace_head(source: Path, target: Path) -> None:
    os.replace(source, target)


def _head_bytes(generation_id: str, manifest_bytes: bytes) -> bytes:
    head = {"schema": HEAD_SCHEMA, "generation_id": generation_id,
            "manifest_sha256": _sha_receipt(manifest_bytes)}
    head["content_sha256"] = sha256(canonical_json(head).encode()).hexdigest()
    return (canonical_json(head) + "\n").encode()


def _publish_head(episode_root: Path, payload: bytes) -> None:
    target = episode_root / "HEAD.json"
    if target.is_file() and target.read_bytes() == payload:
        return
    descriptor, temporary_name = tempfile.mkstemp(prefix=".HEAD.", suffix=".json", dir=episode_root)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_head(temporary, target)
        _fsync_directory(episode_root)
    finally:
        if temporary.exists():
            temporary.unlink()


def _publish_transaction(repo_root: Path, receipt, projection, events, suppressions,
                         projection_parquet):
    episode_root = repo_root / "data" / "us_prophet_rank" / "episodes"
    generations = episode_root / "generations"
    _mkdirs_fsynced(generations)
    _fsync_directory(episode_root.parent)
    durable_receipt = {**receipt, "durable_write": True}
    payloads = _generation_payloads(durable_receipt, projection, events, suppressions,
                                    projection_parquet)
    stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=generations))
    installed = False
    try:
        (stage / "events").mkdir()
        (stage / "suppressions").mkdir()
        for relative, payload in payloads.items():
            _write_fsynced(stage / relative, payload)
        generation_id, manifest = _manifest_for(stage)
        _write_fsynced(stage / "manifest.json", (canonical_json(manifest) + "\n").encode())
        _fsync_tree(stage)
        _validate_generation_directory(stage, generation_id)
        destination = generations / generation_id
        _install_generation(stage, destination)
        installed = True
        manifest_bytes = (destination / "manifest.json").read_bytes()
        _publish_head(episode_root, _head_bytes(generation_id, manifest_bytes))
        return durable_receipt
    finally:
        if not installed and stage.exists():
            shutil.rmtree(stage)


def reconcile(*, repo_root: Path, nightly: bool, replay: bool, recorded_at: str | None,
              correction_path: Path | None) -> dict[str, object]:
    durable = bool(nightly and not replay)
    if durable and not nightly_advance_enabled():
        raise ReconcileRefused("durable write refused: nightly_advance_enabled() is false")
    run_clock = _canonical_recorded_at(recorded_at if recorded_at is not None else _now())
    mode = "replay" if replay else "nightly" if nightly else "report"
    (receipt, projection, events, suppressions, projection_parquet,
     current_generation, previous_receipt) = _load_and_build(
        repo_root=Path(repo_root), recorded_at=run_clock, correction_path=correction_path, mode=mode,
    )
    if not durable:
        return receipt
    durable_candidate = {**receipt, "durable_write": True}
    if current_generation is not None and isinstance(previous_receipt, Mapping) and _stable_receipt(
        previous_receipt, durable_candidate
    ):
        return dict(previous_receipt)
    return _publish_transaction(Path(repo_root), receipt, projection, events, suppressions,
                                projection_parquet)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nightly", action="store_true")
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--recorded-at")
    parser.add_argument("--corrections", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    receipt = reconcile(repo_root=args.repo_root, nightly=args.nightly, replay=args.replay,
                        recorded_at=args.recorded_at, correction_path=args.corrections)
    print(canonical_json(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
