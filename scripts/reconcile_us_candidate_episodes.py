"""Nightly-only reconciler for the canonical U.S. candidate-episode ledger.

The pure event contract and the source normalizers live in ``engine``.  This
module is the one persistence boundary: read-only report/replay is available in
every lane, while durable publication requires both an explicit ``--nightly``
request and the repository's canonical nightly ledger-lane gate.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Mapping, Sequence

import pyarrow as pa
import pyarrow.parquet as pq

from engine.ledger_lane import nightly_advance_enabled
from engine.us_candidate_episode import (
    DEFAULT_DEFINITION_ERA,
    EpisodeContractError,
    apply_commands,
    build_all_candidates,
    canonical_json,
    load_all_candidates,
    reconcile_observations,
    validate_events,
)
from engine.us_candidate_episode_intake import (
    IntakeBatch,
    candidate_observations,
    door_observations,
    load_identity_spine,
    radar_observations,
    turn_watch_observations,
)


RECEIPT_SCHEMA = "prophet.candidate_episode_reconcile_receipt/v1"
SUPPRESSION_SCHEMA = "prophet.candidate_episode_suppression/v1"
_PARQUET_JSON_FIELDS = frozenset({
    "intake_classes", "structural_anchor", "expert_events", "source_event_ids",
})


class ReconcileRefused(RuntimeError):
    """Raised before reads when a durable request is outside the nightly lane."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EpisodeContractError(f"{path}:{line_number} is not JSON") from exc
        if not isinstance(row, Mapping):
            raise EpisodeContractError(f"{path}:{line_number} must be a JSON object")
        rows.append(dict(row))
    return rows


def _load_existing_ledgers(episode_root: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    event_rows = [row for path in sorted((episode_root / "events").glob("*.jsonl")) for row in _jsonl(path)]
    suppression_rows = [
        row for path in sorted((episode_root / "suppressions").glob("*.jsonl")) for row in _jsonl(path)
    ]
    events = validate_events(event_rows)
    return events, _validate_suppressions(suppression_rows)


def _suppression_material(row: Mapping[str, object]) -> dict[str, object]:
    return {
        key: value for key, value in row.items()
        if key not in {"suppression_id", "recorded_at", "content_sha256"}
    }


def _suppression_address(row: Mapping[str, object]) -> str:
    return "pes:" + sha256(canonical_json(_suppression_material(row)).encode("utf-8")).hexdigest()


def _suppression_content(row: Mapping[str, object]) -> str:
    return sha256(canonical_json({key: value for key, value in row.items()
                                  if key != "content_sha256"}).encode("utf-8")).hexdigest()


def _validate_suppressions(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    seen: set[str] = set()
    result: list[dict[str, object]] = []
    for raw in rows:
        row = dict(raw)
        if row.get("schema") != SUPPRESSION_SCHEMA:
            raise EpisodeContractError("existing suppression schema is invalid")
        suppression_id = row.get("suppression_id")
        if suppression_id != _suppression_address(row):
            raise EpisodeContractError("existing suppression address is invalid")
        if row.get("content_sha256") != _suppression_content(row):
            raise EpisodeContractError("existing suppression content hash mismatch")
        if not isinstance(row.get("recorded_at"), str) or not str(row["recorded_at"]).endswith("Z"):
            raise EpisodeContractError("existing suppression recorded_at is invalid")
        assert isinstance(suppression_id, str)
        if suppression_id in seen:
            raise EpisodeContractError("duplicate suppression address")
        seen.add(suppression_id)
        result.append(row)
    return sorted(result, key=lambda row: str(row["suppression_id"]))


def _merge_suppressions(
    existing: Sequence[Mapping[str, object]], additions: Sequence[Mapping[str, object]], *, recorded_at: str,
) -> list[dict[str, object]]:
    merged = {str(row["suppression_id"]): dict(row) for row in _validate_suppressions(existing)}
    for raw in additions:
        material = _suppression_material(raw)
        if material.get("schema") != SUPPRESSION_SCHEMA:
            raise EpisodeContractError("new suppression schema is invalid")
        suppression_id = _suppression_address(material)
        if suppression_id in merged:
            continue
        row = {**material, "suppression_id": suppression_id, "recorded_at": recorded_at}
        row["content_sha256"] = _suppression_content(row)
        merged[suppression_id] = row
    return sorted(merged.values(), key=lambda row: str(row["suppression_id"]))


def _latest_turn_watch(data_root: Path) -> Path:
    paths = sorted((data_root / "us_prophet_rank" / "episode_inputs" / "turn_watch").glob("*.json"))
    return paths[-1] if paths else data_root / "us_prophet_rank" / "episode_inputs" / "turn_watch" / "missing.json"


def _load_intakes(data_root: Path, *, allow_degraded_identity: bool) -> tuple[IntakeBatch, ...]:
    try:
        spine = load_identity_spine(data_root)
    except (OSError, FileNotFoundError):
        if not allow_degraded_identity:
            raise
        return tuple(
            IntakeBatch((), (), ({"source": source, "status": "degraded",
                                  "reason": "MISSING_IDENTITY_SPINE"},))
            for source in ("turn_watch", "candidate", "doors", "entry_radar")
        )
    return (
        turn_watch_observations(_latest_turn_watch(data_root), spine),
        candidate_observations(data_root, spine),
        door_observations(data_root / "prophet_doors" / "flags.jsonl", spine),
        radar_observations(data_root / "entry_radar" / "forward.parquet", spine),
    )


def _commands(path: Path | None) -> list[dict[str, object]]:
    return [] if path is None else _jsonl(path)


def _source_hashes(repo_root: Path, correction_path: Path | None) -> dict[str, str]:
    data_root = repo_root / "data"
    paths = [
        data_root / "reference" / "vendor_aliases.parquet",
        data_root / "reference" / "security_master.parquet",
        _latest_turn_watch(data_root),
        *sorted((data_root / "us_prophet_rank" / "candidates").glob("*.parquet")),
        data_root / "prophet_doors" / "flags.jsonl",
        data_root / "entry_radar" / "forward.parquet",
    ]
    if correction_path is not None:
        paths.append(correction_path)
    result: dict[str, str] = {}
    for path in paths:
        if path.is_file():
            try:
                name = str(path.relative_to(repo_root))
            except ValueError:
                name = str(path.resolve())
            result[name] = "sha256:" + sha256(path.read_bytes()).hexdigest()
    return dict(sorted(result.items()))


def _parquet_bytes(rows: Sequence[Mapping[str, object]]) -> bytes:
    encoded = [
        {
            key: canonical_json(value) if key in _PARQUET_JSON_FIELDS else value
            for key, value in row.items()
        }
        for row in rows
    ]
    table = pa.Table.from_pylist(encoded)
    sink = pa.BufferOutputStream()
    pq.write_table(
        table,
        sink,
        compression="zstd",
        version="2.6",
        data_page_version="2.0",
        use_dictionary=False,
        write_statistics=True,
    )
    return sink.getvalue().to_pybytes()


def _decode_parquet(path: Path) -> list[dict[str, object]]:
    rows = pq.read_table(path).to_pylist()
    return [
        {
            key: json.loads(value) if key in _PARQUET_JSON_FIELDS and isinstance(value, str) else value
            for key, value in row.items()
        }
        for row in rows
    ]


def _load_and_build(
    *, repo_root: Path, recorded_at: str, correction_path: Path | None, mode: str,
) -> tuple[
    dict[str, object], dict[str, object], list[dict[str, object]], list[dict[str, object]], bytes,
]:
    data_root = repo_root / "data"
    episode_root = data_root / "us_prophet_rank" / "episodes"
    existing_events, existing_suppressions = _load_existing_ledgers(episode_root)
    batches = _load_intakes(data_root, allow_degraded_identity=mode != "nightly")
    observations = [row for batch in batches for row in batch.observations]
    intake_suppressions = [row for batch in batches for row in batch.suppressions]
    reconciled = reconcile_observations(
        existing_events,
        observations,
        recorded_at=recorded_at,
        definition_era=DEFAULT_DEFINITION_ERA,
    )
    commanded = apply_commands(
        reconciled.events,
        _commands(correction_path),
        recorded_at=recorded_at,
        definition_era=DEFAULT_DEFINITION_ERA,
    )
    run_suppressions = [*intake_suppressions, *reconciled.suppressions]
    suppressions = _merge_suppressions(existing_suppressions, run_suppressions, recorded_at=recorded_at)
    projection = build_all_candidates(commanded.events, suppression_count=len(suppressions))
    reconciled_suppression_keys = {
        (row.get("source_system"), row.get("source_schema"), row.get("source_event_id"))
        for row in reconciled.suppressions
    }
    source_counts: dict[str, dict[str, int]] = {}
    for batch in batches:
        source = next(
            (str(item["source"]) for item in batch.source_receipts if item.get("source")),
            str(batch.observations[0]["source_system"]) if batch.observations else "unknown",
        )
        reconciled_suppressed = sum(
            (
                row.get("source_system"), row.get("source_schema"), row.get("source_event_id")
            ) in reconciled_suppression_keys
            for row in batch.observations
        )
        source_input = len(batch.observations) + len(batch.suppressions)
        source_suppressed = len(batch.suppressions) + reconciled_suppressed
        source_counts[source] = {
            "input": source_input,
            "mapped": source_input - source_suppressed,
            "suppressed": source_suppressed,
        }
    input_count = sum(counts["input"] for counts in source_counts.values())
    mapped_count = sum(counts["mapped"] for counts in source_counts.values())
    suppressed_count = sum(counts["suppressed"] for counts in source_counts.values())
    if input_count != mapped_count + suppressed_count:
        raise EpisodeContractError("source accounting is not input = mapped + suppressed")
    if any(counts["input"] != counts["mapped"] + counts["suppressed"]
           for counts in source_counts.values()):
        raise EpisodeContractError("per-source accounting is not input = mapped + suppressed")
    event_count = len(commanded.events)
    ledger_hash = "sha256:" + sha256(canonical_json(tuple(commanded.events)).encode("utf-8")).hexdigest()
    projection_json = (canonical_json(projection) + "\n").encode("utf-8")
    projection_parquet = _parquet_bytes(projection["episodes"])
    receipt: dict[str, object] = {
        "schema": RECEIPT_SCHEMA,
        "mode": mode,
        "gate": {"nightly_requested": mode == "nightly", "nightly_advance_enabled": mode == "nightly"},
        "durable_write": False,
        "recorded_at": recorded_at,
        "definition_era": DEFAULT_DEFINITION_ERA,
        "source_hashes": _source_hashes(repo_root, correction_path),
        "source_counts": dict(sorted(source_counts.items())),
        "counts": {
            "input": input_count,
            "mapped": mapped_count,
            "suppressed": suppressed_count,
            "old_events": len(existing_events),
            "new_events": event_count,
            "appended_events": len(commanded.new_events) + len(reconciled.new_events),
        },
        "ledger_sha256": ledger_hash,
        "projection_hashes": {
            "all_candidates.json": "sha256:" + sha256(projection_json).hexdigest(),
            "current.parquet": "sha256:" + sha256(projection_parquet).hexdigest(),
        },
        "source_receipts": [receipt for batch in batches for receipt in batch.source_receipts],
    }
    return receipt, projection, list(commanded.events), suppressions, projection_parquet


def _event_order(row: Mapping[str, object]) -> tuple[str, str, str]:
    return str(row["known_at"]), str(row["source_system"]), str(row["source_event_id"])


def _jsonl_bytes(rows: Sequence[Mapping[str, object]]) -> bytes:
    return ("" if not rows else "\n".join(canonical_json(row) for row in rows) + "\n").encode("utf-8")


def _month(value: object, *, field: str) -> str:
    text = str(value)
    if len(text) < 7 or text[4] != "-":
        raise EpisodeContractError(f"{field} has no canonical month")
    return text[:7]


def _target_bytes(
    episode_root: Path,
    receipt: Mapping[str, object],
    projection: Mapping[str, object],
    events: Sequence[Mapping[str, object]],
    suppressions: Sequence[Mapping[str, object]],
    projection_parquet: bytes,
) -> dict[Path, bytes]:
    by_event_month: dict[str, list[Mapping[str, object]]] = {}
    for row in sorted(events, key=_event_order):
        by_event_month.setdefault(_month(row["recorded_at"], field="event.recorded_at"), []).append(row)
    by_suppression_month: dict[str, list[Mapping[str, object]]] = {}
    for row in sorted(suppressions, key=lambda value: str(value["suppression_id"])):
        by_suppression_month.setdefault(
            _month(row["recorded_at"], field="suppression.recorded_at"), []
        ).append(row)
    targets = {
        episode_root / "events" / f"{month}.jsonl": _jsonl_bytes(rows)
        for month, rows in sorted(by_event_month.items())
    }
    targets.update({
        episode_root / "suppressions" / f"{month}.jsonl": _jsonl_bytes(rows)
        for month, rows in sorted(by_suppression_month.items())
    })
    targets[episode_root / "all_candidates.json"] = (canonical_json(projection) + "\n").encode("utf-8")
    targets[episode_root / "current.parquet"] = projection_parquet
    targets[episode_root / "latest_receipt.json"] = (canonical_json(receipt) + "\n").encode("utf-8")
    return targets


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


def _fsync_tree(root: Path) -> None:
    directories = [root, *(path for path in root.rglob("*") if path.is_dir())]
    for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
        _fsync_directory(directory)


def _validate_staged(stage_new: Path, episode_root: Path, relative_targets: Sequence[Path]) -> None:
    event_rows: list[dict[str, object]] = []
    suppression_rows: list[dict[str, object]] = []
    for relative in sorted(relative_targets):
        staged = stage_new / relative
        if relative.parts[0] == "events":
            rows = _jsonl(staged)
            if staged.read_bytes() != _jsonl_bytes(rows) or rows != sorted(rows, key=_event_order):
                raise EpisodeContractError("staged event ledger is not canonical sorted JSONL")
            event_rows.extend(rows)
        elif relative.parts[0] == "suppressions":
            rows = _jsonl(staged)
            if staged.read_bytes() != _jsonl_bytes(rows):
                raise EpisodeContractError("staged suppression ledger is not canonical JSONL")
            suppression_rows.extend(rows)
    validate_events(event_rows)
    _validate_suppressions(suppression_rows)
    all_candidates = stage_new / "all_candidates.json"
    logical_json = load_all_candidates(all_candidates)
    logical_parquet = _decode_parquet(stage_new / "current.parquet")
    if canonical_json(logical_parquet) != canonical_json(logical_json):
        raise EpisodeContractError("current.parquet differs from All Candidates logical rows")
    receipt = json.loads((stage_new / "latest_receipt.json").read_text(encoding="utf-8"))
    if not isinstance(receipt, Mapping) or receipt.get("schema") != RECEIPT_SCHEMA:
        raise EpisodeContractError("staged reconcile receipt is invalid")
    expected = receipt.get("projection_hashes")
    if not isinstance(expected, Mapping):
        raise EpisodeContractError("staged reconcile receipt lacks projection hashes")
    for name in ("all_candidates.json", "current.parquet"):
        actual = "sha256:" + sha256((stage_new / name).read_bytes()).hexdigest()
        if expected.get(name) != actual:
            raise EpisodeContractError(f"staged {name} hash differs from receipt")


def _replace_file(source: Path, target: Path) -> None:
    os.replace(source, target)


def _same_receipt_inputs(old: Mapping[str, object], new: Mapping[str, object]) -> bool:
    return all(old.get(field) == new.get(field) for field in (
        "schema", "mode", "gate", "definition_era", "recorded_at", "source_hashes",
        "ledger_sha256", "projection_hashes", "source_counts", "source_receipts",
    ))


def _remove_empty_created_directories(created: Sequence[Path]) -> None:
    for directory in sorted(created, key=lambda path: len(path.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass


def _publish_transaction(
    repo_root: Path,
    receipt: dict[str, object],
    projection: Mapping[str, object],
    events: Sequence[Mapping[str, object]],
    suppressions: Sequence[Mapping[str, object]],
    projection_parquet: bytes,
) -> dict[str, object]:
    episode_root = repo_root / "data" / "us_prophet_rank" / "episodes"
    receipt = {**receipt, "durable_write": True}
    candidate_targets = _target_bytes(
        episode_root, receipt, projection, events, suppressions, projection_parquet,
    )
    previous_receipt_path = episode_root / "latest_receipt.json"
    if previous_receipt_path.is_file():
        try:
            previous_receipt = json.loads(previous_receipt_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous_receipt = None
        if isinstance(previous_receipt, Mapping) and _same_receipt_inputs(previous_receipt, receipt):
            stable_targets = _target_bytes(
                episode_root, previous_receipt, projection, events, suppressions, projection_parquet,
            )
            if all(path.is_file() and path.read_bytes() == payload
                   for path, payload in stable_targets.items()):
                return dict(previous_receipt)

    targets = candidate_targets
    changed = {path: payload for path, payload in targets.items()
               if not path.is_file() or path.read_bytes() != payload}
    if not changed:
        return receipt

    created_directories: list[Path] = []
    for directory in (repo_root / "data", repo_root / "data" / "us_prophet_rank", episode_root):
        if not directory.exists():
            directory.mkdir()
            created_directories.append(directory)
    stage = Path(tempfile.mkdtemp(prefix=".candidate-episode-stage-", dir=episode_root))
    stage_new = stage / "new"
    stage_old = stage / "old"
    relative_targets = [path.relative_to(episode_root) for path in targets]
    try:
        for target, payload in targets.items():
            relative = target.relative_to(episode_root)
            _write_fsynced(stage_new / relative, payload)
            if target in changed and target.is_file():
                _write_fsynced(stage_old / relative, target.read_bytes())
        _fsync_tree(stage)
        _validate_staged(stage_new, episode_root, relative_targets)

        created_target_directories: list[Path] = []
        for target in changed:
            missing: list[Path] = []
            cursor = target.parent
            while cursor != episode_root and not cursor.exists():
                missing.append(cursor)
                cursor = cursor.parent
            target.parent.mkdir(parents=True, exist_ok=True)
            created_target_directories.extend(missing)
        replaced: list[Path] = []
        try:
            for target in sorted(changed, key=lambda path: str(path.relative_to(episode_root))):
                _replace_file(stage_new / target.relative_to(episode_root), target)
                replaced.append(target)
                _fsync_directory(target.parent)
            _fsync_directory(episode_root)
        except BaseException:
            for target in reversed(replaced):
                relative = target.relative_to(episode_root)
                preimage = stage_old / relative
                if preimage.is_file():
                    restore = stage / "restore" / relative
                    _write_fsynced(restore, preimage.read_bytes())
                    os.replace(restore, target)
                elif target.exists():
                    target.unlink()
                _fsync_directory(target.parent)
            _remove_empty_created_directories(created_target_directories)
            raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        _remove_empty_created_directories(created_directories)
    return receipt


def reconcile(
    *,
    repo_root: Path,
    nightly: bool,
    replay: bool,
    recorded_at: str | None,
    correction_path: Path | None,
) -> dict[str, object]:
    """Reconcile registered B1 sources, publishing only in the explicit nightly lane."""
    durable = bool(nightly and not replay)
    if durable and not nightly_advance_enabled():
        raise ReconcileRefused("durable write refused: nightly_advance_enabled() is false")
    mode = "replay" if replay else "nightly" if nightly else "report"
    receipt, projection, events, suppressions, projection_parquet = _load_and_build(
        repo_root=Path(repo_root),
        recorded_at=recorded_at or _now(),
        correction_path=correction_path,
        mode=mode,
    )
    if not durable:
        return receipt
    return _publish_transaction(
        Path(repo_root), receipt, projection, events, suppressions, projection_parquet,
    )


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
    receipt = reconcile(
        repo_root=args.repo_root,
        nightly=args.nightly,
        replay=args.replay,
        recorded_at=args.recorded_at,
        correction_path=args.corrections,
    )
    print(canonical_json(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
