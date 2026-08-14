#!/usr/bin/env python3
"""Generate and verify a committed legacy-CI path-ownership index.

Scope inference walks the repository's Python/test dependency graph and is an
offline indexing operation.  A planner should not repeat it against the roughly
64k-file worktree.  This module freezes the inferred ``LegacyJob.paths`` values
behind exact source identities, then reconstructs the live manifest jobs with
those committed paths after a cheap, fail-closed verification.

The index deliberately contains no timestamp.  Identical inputs produce
identical bytes, and the canonical digest covers every semantic field except the
digest itself.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import importlib
import json
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SCHEMA = "ci.committed_scope_index.v1"
DEFAULT_MANIFEST = Path(".github/ci/legacy-jobs.yml")
SELECTOR_SOURCES = (
    Path("scripts/run_ci_pack.py"),
    Path("scripts/ci_scope_dependencies.py"),
)
SHA256_RE = re.compile(r"[0-9a-f]{64}")
MAX_INDEX_BYTES = 16 * 1024 * 1024
TOP_LEVEL_KEYS = {
    "schema",
    "manifest",
    "selector_sources",
    "job_count",
    "job_inventory",
    "jobs",
    "index_sha256",
}


class ScopeIndexError(ValueError):
    """The committed index cannot safely replace runtime scope inference."""


@dataclass(frozen=True)
class ScopeIndexVerification:
    """Verified index metadata plus manifest-backed ``LegacyJob`` replacements."""

    jobs: tuple[Any, ...]
    index_sha256: str
    manifest_sha256: str
    elapsed_seconds: float


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path, *, label: str) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise ScopeIndexError(f"cannot hash {label} {path}: {exc}") from exc
    return digest.hexdigest()


def _repo_file(repo_root: Path, path: Path | str, *, label: str) -> tuple[Path, str]:
    root = repo_root.resolve()
    candidate = Path(path)
    resolved = (
        (root / candidate).resolve()
        if not candidate.is_absolute()
        else candidate.resolve()
    )
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ScopeIndexError(
            f"{label} must be inside repository root {root}: {resolved}"
        ) from exc
    if not resolved.is_file():
        raise ScopeIndexError(f"{label} does not exist as a file: {resolved}")
    return resolved, relative.as_posix()


def _pack_module(pack_module: Any | None) -> Any:
    if pack_module is not None:
        return pack_module
    try:
        return importlib.import_module("scripts.run_ci_pack")
    except (ImportError, OSError, SyntaxError) as exc:
        raise ScopeIndexError(f"cannot import scripts.run_ci_pack: {exc}") from exc


def _selector_receipts(repo_root: Path) -> list[dict[str, str]]:
    receipts: list[dict[str, str]] = []
    for relative in SELECTOR_SOURCES:
        source, label = _repo_file(
            repo_root, relative, label=f"selector source {relative.as_posix()}"
        )
        receipts.append(
            {
                "path": label,
                "sha256": _sha256_file(source, label="selector source"),
            }
        )
    return receipts


def _validate_path(path: Any, *, job_id: str, position: int) -> str:
    label = f"job {job_id!r} path {position}"
    if not isinstance(path, str) or not path:
        raise ScopeIndexError(f"{label} must be a non-empty string")
    if path != path.strip():
        raise ScopeIndexError(f"{label} must not contain leading or trailing whitespace")
    if any(ord(char) < 32 for char in path):
        raise ScopeIndexError(f"{label} contains a control character")
    # ``run_ci_pack`` deliberately treats one trailing slash as a subtree glob.
    # Preserve that valid spelling while rejecting empty interior segments.
    path_body = path[:-1] if path.endswith("/") else path
    segments = path_body.split("/")
    if path.startswith("/") or "\\" in path or any(
        segment in {"", ".", ".."} or ".." in segment for segment in segments
    ):
        raise ScopeIndexError(
            f"{label} must be a canonical repo-relative POSIX glob without "
            "empty interior, '.', '..', or '\\' segments"
        )
    return path


def _canonical_paths(raw: Any, *, job_id: str) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise ScopeIndexError(f"job {job_id!r} paths must be a JSON array")
    paths = tuple(
        _validate_path(path, job_id=job_id, position=index)
        for index, path in enumerate(raw)
    )
    if len(paths) != len(set(paths)):
        raise ScopeIndexError(f"job {job_id!r} paths contain duplicates")
    if paths != tuple(sorted(paths)):
        raise ScopeIndexError(f"job {job_id!r} paths must be sorted canonically")
    return paths


def _normalise_generated_paths(raw: Any, *, job_id: str) -> tuple[str, ...]:
    if not isinstance(raw, (list, tuple)):
        raise ScopeIndexError(
            f"scope inference returned non-sequence paths for job {job_id!r}"
        )
    paths = tuple(
        _validate_path(path, job_id=job_id, position=index)
        for index, path in enumerate(raw)
    )
    if len(paths) != len(set(paths)):
        raise ScopeIndexError(
            f"scope inference returned duplicate paths for job {job_id!r}"
        )
    return tuple(sorted(paths))


def _require_exact_keys(value: Any, keys: set[str], *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ScopeIndexError(f"{label} must be an object")
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        details: list[str] = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unexpected " + ", ".join(extra))
        raise ScopeIndexError(f"{label} has wrong fields ({'; '.join(details)})")
    return value


def _require_sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ScopeIndexError(f"{label} must be a lowercase sha256 hex digest")
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ScopeIndexError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _read_index(path: Path) -> dict[str, Any]:
    try:
        size = path.stat().st_size
        if size > MAX_INDEX_BYTES:
            raise ScopeIndexError(
                f"scope index is {size} bytes; limit is {MAX_INDEX_BYTES}"
            )
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ScopeIndexError(f"cannot read scope index {path}: {exc}") from exc
    try:
        payload = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ScopeIndexError(f"scope index is not valid JSON: {exc}") from exc
    return _require_exact_keys(payload, TOP_LEVEL_KEYS, label="scope index")


def _write_index(path: Path, document: Mapping[str, Any]) -> None:
    rendered = json.dumps(
        document,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        try:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ScopeIndexError(f"cannot write scope index {path}: {exc}") from exc


def _job_identity(job: Any) -> tuple[str, int, int]:
    try:
        job_id = job.job_id
        ordinal = job.ordinal
        weight = job.weight
    except AttributeError as exc:
        raise ScopeIndexError(
            f"scope inference returned a non-LegacyJob value: {job!r}"
        ) from exc
    if not isinstance(job_id, str) or not job_id:
        raise ScopeIndexError("scope inference returned a job with an invalid job_id")
    if type(ordinal) is not int or ordinal < 0:
        raise ScopeIndexError(f"job {job_id!r} has invalid ordinal {ordinal!r}")
    if type(weight) is not int or weight < 1:
        raise ScopeIndexError(f"job {job_id!r} has invalid weight {weight!r}")
    return job_id, ordinal, weight


def _validate_resolved_jobs(live_jobs: Sequence[Any], resolved_jobs: Sequence[Any]) -> None:
    if len(live_jobs) != len(resolved_jobs):
        raise ScopeIndexError(
            "scope inference changed the exact job inventory "
            f"({len(live_jobs)} live, {len(resolved_jobs)} resolved)"
        )
    live_ids = [_job_identity(job) for job in live_jobs]
    resolved_ids = [_job_identity(job) for job in resolved_jobs]
    if live_ids != resolved_ids:
        raise ScopeIndexError("scope inference changed job id, ordinal, weight, or order")


def generate_scope_index(
    manifest_path: Path | str = DEFAULT_MANIFEST,
    output_path: Path | str | None = None,
    *,
    repo_root: Path | str = ROOT,
    pack_module: Any | None = None,
    infer_scopes: Callable[[Iterable[Any]], tuple[list[Any], str]] | None = None,
) -> dict[str, Any]:
    """Run expensive inference once and atomically write a deterministic index."""

    if output_path is None:
        raise ScopeIndexError("output_path is required; no production index is implicit")
    root = Path(repo_root).resolve()
    manifest, manifest_label = _repo_file(
        root, manifest_path, label="legacy manifest"
    )
    manifest_sha = _sha256_file(manifest, label="legacy manifest")
    selector_receipts = _selector_receipts(root)
    pack = _pack_module(pack_module)
    try:
        live_jobs = list(pack.load_legacy_jobs(manifest))
        resolver = infer_scopes or pack.infer_job_scopes
        resolved_jobs, _summary = resolver(live_jobs)
        resolved_jobs = list(resolved_jobs)
    except ScopeIndexError:
        raise
    except Exception as exc:
        raise ScopeIndexError(f"cannot resolve legacy job scopes: {exc}") from exc

    if manifest_sha != _sha256_file(manifest, label="legacy manifest"):
        raise ScopeIndexError("legacy manifest changed during scope index generation")
    if selector_receipts != _selector_receipts(root):
        raise ScopeIndexError("selector source changed during scope index generation")
    _validate_resolved_jobs(live_jobs, resolved_jobs)
    inventory: list[str] = []
    records: list[dict[str, Any]] = []
    for job in resolved_jobs:
        job_id, ordinal, weight = _job_identity(job)
        if job_id in inventory:
            raise ScopeIndexError(f"scope inference returned duplicate job {job_id!r}")
        try:
            raw_paths = job.paths
        except AttributeError as exc:
            raise ScopeIndexError(
                f"scope inference returned job {job_id!r} without paths"
            ) from exc
        paths = _normalise_generated_paths(raw_paths, job_id=job_id)
        inventory.append(job_id)
        records.append(
            {
                "job_id": job_id,
                "ordinal": ordinal,
                "weight": weight,
                "paths": list(paths),
            }
        )

    core: dict[str, Any] = {
        "schema": SCHEMA,
        "manifest": {
            "path": manifest_label,
            "sha256": manifest_sha,
        },
        "selector_sources": selector_receipts,
        "job_count": len(records),
        "job_inventory": inventory,
        "jobs": records,
    }
    document = dict(core)
    document["index_sha256"] = _sha256_bytes(_canonical_json_bytes(core))
    _write_index(Path(output_path).resolve(), document)
    return document


def _verify_document(
    document: dict[str, Any],
    *,
    repo_root: Path,
    manifest_path: Path | str,
    pack_module: Any | None,
) -> tuple[list[Any], str, str]:
    digest = _require_sha256(document["index_sha256"], label="index_sha256")
    core = {key: value for key, value in document.items() if key != "index_sha256"}
    computed = _sha256_bytes(_canonical_json_bytes(core))
    if not hmac.compare_digest(digest, computed):
        raise ScopeIndexError(
            f"scope index digest mismatch: recorded {digest}, computed {computed}"
        )
    if document["schema"] != SCHEMA:
        raise ScopeIndexError(
            f"unsupported scope index schema {document['schema']!r}; expected {SCHEMA!r}"
        )

    manifest_record = _require_exact_keys(
        document["manifest"], {"path", "sha256"}, label="manifest receipt"
    )
    manifest, manifest_label = _repo_file(
        repo_root, manifest_path, label="legacy manifest"
    )
    if manifest_record["path"] != manifest_label:
        raise ScopeIndexError(
            f"manifest path mismatch: index has {manifest_record['path']!r}, "
            f"loader expects {manifest_label!r}"
        )
    recorded_manifest_sha = _require_sha256(
        manifest_record["sha256"], label="manifest sha256"
    )
    live_manifest_sha = _sha256_file(manifest, label="legacy manifest")
    if not hmac.compare_digest(recorded_manifest_sha, live_manifest_sha):
        raise ScopeIndexError(
            "legacy manifest hash drift: "
            f"index has {recorded_manifest_sha}, live file has {live_manifest_sha}"
        )

    sources = document["selector_sources"]
    if not isinstance(sources, list):
        raise ScopeIndexError("selector_sources must be an array")
    expected_sources = [path.as_posix() for path in SELECTOR_SOURCES]
    if len(sources) != len(expected_sources):
        raise ScopeIndexError(
            f"selector_sources must contain exactly {len(expected_sources)} identities"
        )
    observed_sources: list[str] = []
    for index, raw in enumerate(sources):
        receipt = _require_exact_keys(
            raw, {"path", "sha256"}, label=f"selector source {index}"
        )
        path = receipt["path"]
        if not isinstance(path, str):
            raise ScopeIndexError(f"selector source {index} path must be a string")
        if path in observed_sources:
            raise ScopeIndexError(f"duplicate selector source identity {path!r}")
        observed_sources.append(path)
        if path != expected_sources[index]:
            raise ScopeIndexError(
                "selector source inventory/order mismatch: "
                f"entry {index} must be {expected_sources[index]!r}, got {path!r}"
            )
        recorded_sha = _require_sha256(
            receipt["sha256"], label=f"selector source {path!r} sha256"
        )
        source, source_label = _repo_file(
            repo_root, path, label=f"selector source {path}"
        )
        if source_label != path:
            raise ScopeIndexError(
                f"selector source path is not canonical: {path!r} != {source_label!r}"
            )
        live_sha = _sha256_file(source, label="selector source")
        if not hmac.compare_digest(recorded_sha, live_sha):
            raise ScopeIndexError(
                f"selector source hash drift for {path}: "
                f"index has {recorded_sha}, live file has {live_sha}"
            )
    job_count = document["job_count"]
    if type(job_count) is not int or job_count < 1:
        raise ScopeIndexError("job_count must be a positive integer")
    inventory = document["job_inventory"]
    if not isinstance(inventory, list) or not all(
        isinstance(job_id, str) and job_id for job_id in inventory
    ):
        raise ScopeIndexError("job_inventory must contain non-empty job-id strings")
    if len(inventory) != len(set(inventory)):
        raise ScopeIndexError("job_inventory contains duplicate job ids")
    raw_jobs = document["jobs"]
    if not isinstance(raw_jobs, list):
        raise ScopeIndexError("jobs must be an array")
    if job_count != len(inventory) or job_count != len(raw_jobs):
        raise ScopeIndexError(
            "job_count, job_inventory, and jobs length disagree: "
            f"{job_count}, {len(inventory)}, {len(raw_jobs)}"
        )

    records: list[tuple[str, int, int, tuple[str, ...]]] = []
    seen_ordinals: set[int] = set()
    for index, raw in enumerate(raw_jobs):
        record = _require_exact_keys(
            raw,
            {"job_id", "ordinal", "weight", "paths"},
            label=f"job record {index}",
        )
        job_id = record["job_id"]
        ordinal = record["ordinal"]
        weight = record["weight"]
        if not isinstance(job_id, str) or not job_id:
            raise ScopeIndexError(f"job record {index} has an invalid job_id")
        if type(ordinal) is not int or ordinal < 0:
            raise ScopeIndexError(f"job {job_id!r} has invalid ordinal {ordinal!r}")
        if ordinal in seen_ordinals:
            raise ScopeIndexError(f"duplicate job ordinal {ordinal}")
        seen_ordinals.add(ordinal)
        if type(weight) is not int or weight < 1:
            raise ScopeIndexError(f"job {job_id!r} has invalid weight {weight!r}")
        paths = _canonical_paths(record["paths"], job_id=job_id)
        records.append((job_id, ordinal, weight, paths))

    record_ids = [record[0] for record in records]
    if record_ids != inventory:
        raise ScopeIndexError(
            f"job record inventory/order mismatch: expected {inventory}, got {record_ids}"
        )

    pack = _pack_module(pack_module)
    try:
        live_jobs = list(pack.load_legacy_jobs(manifest))
    except Exception as exc:
        raise ScopeIndexError(f"cannot load bound legacy manifest: {exc}") from exc
    live_inventory = [_job_identity(job)[0] for job in live_jobs]
    if live_inventory != inventory:
        missing = sorted(set(live_inventory) - set(inventory))
        extra = sorted(set(inventory) - set(live_inventory))
        raise ScopeIndexError(
            "legacy job inventory drift"
            + (f"; missing from index: {missing}" if missing else "")
            + (f"; absent from manifest: {extra}" if extra else "")
        )

    replacements: list[Any] = []
    for live_job, record in zip(live_jobs, records, strict=True):
        job_id, ordinal, weight = _job_identity(live_job)
        recorded_id, recorded_ordinal, recorded_weight, paths = record
        if (job_id, ordinal, weight) != (
            recorded_id,
            recorded_ordinal,
            recorded_weight,
        ):
            raise ScopeIndexError(
                f"job identity drift for {job_id!r}: live "
                f"ordinal/weight=({ordinal}, {weight}), index "
                f"ordinal/weight=({recorded_ordinal}, {recorded_weight})"
            )
        replacements.append(replace(live_job, paths=paths))
    return replacements, digest, recorded_manifest_sha


def verify_scope_index(
    index_path: Path | str,
    manifest_path: Path | str = DEFAULT_MANIFEST,
    *,
    repo_root: Path | str = ROOT,
    pack_module: Any | None = None,
) -> ScopeIndexVerification:
    """Verify all identities/invariants without running scope inference."""

    started = time.perf_counter()
    root = Path(repo_root).resolve()
    document = _read_index(Path(index_path).resolve())
    jobs, digest, manifest_sha = _verify_document(
        document,
        repo_root=root,
        manifest_path=manifest_path,
        pack_module=pack_module,
    )
    return ScopeIndexVerification(
        jobs=tuple(jobs),
        index_sha256=digest,
        manifest_sha256=manifest_sha,
        elapsed_seconds=time.perf_counter() - started,
    )


def load_scope_index(
    index_path: Path | str,
    manifest_path: Path | str = DEFAULT_MANIFEST,
    *,
    repo_root: Path | str = ROOT,
    pack_module: Any | None = None,
) -> list[Any]:
    """Return manifest definitions with paths replaced from a verified index."""

    return list(
        verify_scope_index(
            index_path,
            manifest_path,
            repo_root=repo_root,
            pack_module=pack_module,
        ).jobs
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser(
        "generate", help="run offline scope inference and write the committed index"
    )
    generate.add_argument("--repo-root", type=Path, default=ROOT)
    generate.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    generate.add_argument("--output", type=Path, required=True)

    verify = subparsers.add_parser(
        "verify", help="verify identities/digest and load indexed LegacyJobs"
    )
    verify.add_argument("--repo-root", type=Path, default=ROOT)
    verify.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    verify.add_argument("--index", type=Path, required=True)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    pack_module: Any | None = None,
    infer_scopes: Callable[[Iterable[Any]], tuple[list[Any], str]] | None = None,
) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "generate":
            document = generate_scope_index(
                args.manifest,
                args.output,
                repo_root=args.repo_root,
                pack_module=pack_module,
                infer_scopes=infer_scopes,
            )
            print(
                "SCOPE_INDEX_GENERATED="
                + json.dumps(
                    {
                        "index": str(args.output),
                        "jobs": document["job_count"],
                        "index_sha256": document["index_sha256"],
                    },
                    sort_keys=True,
                )
            )
            return 0

        receipt = verify_scope_index(
            args.index,
            args.manifest,
            repo_root=args.repo_root,
            pack_module=pack_module,
        )
        print(
            "SCOPE_INDEX_VERIFIED="
            + json.dumps(
                {
                    "index": str(args.index),
                    "jobs": len(receipt.jobs),
                    "index_sha256": receipt.index_sha256,
                    "elapsed_seconds": round(receipt.elapsed_seconds, 6),
                },
                sort_keys=True,
            )
        )
        return 0
    except ScopeIndexError as exc:
        print(f"scope index {args.command} failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
