#!/usr/bin/env python3
"""Execute the bounded P0-A1R FTS repair and exact-twenty source freeze.

The command has one network capability: it injects the canonical #6117 SEC FTS
enumerator into the retry-only A1R kernel.  The kernel can request only the five
named failed leaves.  Everything after those leaf responses is offline,
deterministic, and source-only.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research.dislocation_p0_a1_lib import (  # noqa: E402
    ALLOWED_HOSTS,
    AccessLog,
    assert_blind_workspace,
    authority_flags,
    build_query_ledger,
    canonical_json,
    forbidden_market_fields,
    sha256_text,
    split_date_range,
)
from scripts.research.dislocation_p0_a1_harvest import (  # noqa: E402
    enumerate_leaf,
    session,
)
from scripts.research.dislocation_p0_a1r import (  # noqa: E402
    DERIVED_AGGREGATES,
    FAILED_LEAVES,
    FAMILIES,
    cache_key,
    compile_annual_source_plane,
    complete_pool_hashes,
    eligible_candidates,
    exact20_manifest,
    logical_cell_census,
    manifest_bytes,
    recompute_derived_aggregates,
    retry_only_completion,
    write_retry_version,
)


PUBLIC_COMPLETION_NAME = "A1R_QUERY_COMPLETION_AND_POOL_RECEIPT.json"
PUBLIC_SELECTION_NAME = "A1R_EXACT20_SOURCE_SELECTION.json"


class SourceRunBlocked(RuntimeError):
    """The bounded source repair could not produce a lawful exact-twenty set."""


def file_sha256(path: Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_canonical_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
    temporary.replace(path)


def _checkpoint_path(workspace: Path, leaf: Mapping[str, str]) -> Path:
    digest = sha256_text(cache_key(leaf))
    return workspace / "source_completion" / "leaf_checkpoints" / f"{digest}.json"


def _read_leaf_checkpoint(
    workspace: Path, leaf: Mapping[str, str]
) -> tuple[Mapping[str, Any], list[dict[str, Any]]] | None:
    path = _checkpoint_path(workspace, leaf)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SourceRunBlocked(f"leaf checkpoint is not an object: {path.name}")
    claimed = payload.pop("checkpoint_sha256", None)
    if claimed != sha256_text(canonical_json(payload)):
        raise SourceRunBlocked(f"leaf checkpoint hash mismatch: {path.name}")
    if payload.get("leaf") != dict(leaf):
        raise SourceRunBlocked(f"leaf checkpoint identity mismatch: {path.name}")
    result = payload.get("result")
    events = payload.get("access_events")
    if (
        not isinstance(result, Mapping)
        or result.get("complete") is not True
        or not isinstance(events, list)
        or not all(isinstance(event, dict) for event in events)
    ):
        raise SourceRunBlocked(f"leaf checkpoint is incomplete: {path.name}")
    return result, events


def _write_leaf_checkpoint(
    workspace: Path,
    leaf: Mapping[str, str],
    result: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
) -> None:
    payload = {
        "schema": "mastermind.dislocation_p0.a1r_leaf_checkpoint.v1",
        "leaf": dict(leaf),
        "result": dict(result),
        "access_events": [dict(event) for event in events],
    }
    payload["checkpoint_sha256"] = sha256_text(canonical_json(payload))
    write_canonical_json(_checkpoint_path(workspace, leaf), payload)


def derived_child_keys() -> dict[str, tuple[str, str]]:
    mapping: dict[str, tuple[str, str]] = {}
    for parent in DERIVED_AGGREGATES:
        split = split_date_range(parent["start"], parent["end"])
        if split is None:
            raise SourceRunBlocked(f"derived aggregate cannot split: {parent}")
        (left_start, left_end), (right_start, right_end) = split
        left = dict(parent) | {"start": left_start, "end": left_end}
        right = dict(parent) | {"start": right_start, "end": right_end}
        mapping[cache_key(parent)] = (cache_key(left), cache_key(right))
    return mapping


def initial_defect_keys(cache: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    expected = {cache_key(spec) for spec in FAILED_LEAVES}
    expected.update(cache_key(spec) for spec in DERIVED_AGGREGATES)
    actual = {
        key for key, record in cache.items()
        if isinstance(record, Mapping) and record.get("complete") is False
    }
    return expected, actual


def _official_hosts(access: AccessLog) -> list[str]:
    hosts: set[str] = set()
    for event in access.events:
        if event.get("kind") != "url":
            continue
        host = (urlparse(str(event.get("target") or "")).hostname or "").lower()
        if host:
            hosts.add(host)
    if not hosts or not hosts.issubset(ALLOWED_HOSTS):
        raise SourceRunBlocked(f"access receipt contains a non-SEC host: {sorted(hosts)}")
    return sorted(hosts)


def execute_source_run(
    *,
    historical_cache_path: Path,
    workspace: Path,
    public_out: Path,
) -> dict[str, Any]:
    workspace = Path(workspace)
    public_out = Path(public_out)
    historical_cache_path = Path(historical_cache_path)
    forbidden_dirs = assert_blind_workspace(workspace)
    historical_sha = file_sha256(historical_cache_path)
    with historical_cache_path.open("r", encoding="utf-8") as handle:
        cache = json.load(handle)
    if not isinstance(cache, dict):
        raise SourceRunBlocked("historical FTS cache must be an object")

    expected_defects, actual_defects = initial_defect_keys(cache)
    if actual_defects != expected_defects:
        raise SourceRunBlocked(canonical_json({
            "code": "UNEXPECTED_FTS_DEFECT_SET",
            "expected": sorted(expected_defects),
            "actual": sorted(actual_defects),
        }))

    access = AccessLog()
    sec_session = session()
    retry_nested_cache: dict[str, Any] = {}

    def fetch_leaf(leaf: Mapping[str, str]) -> Mapping[str, Any]:
        checkpoint = _read_leaf_checkpoint(workspace, leaf)
        if checkpoint is not None:
            result, checkpoint_events = checkpoint
            access.events.extend(checkpoint_events)
            print(
                f"retry-checkpoint {cache_key(leaf)} "
                f"rows={len(result.get('rows') or [])}",
                flush=True,
            )
            return result
        print(f"retry-start {cache_key(leaf)}", flush=True)
        event_start = len(access.events)
        result = enumerate_leaf(
            sec_session,
            access,
            phrase=leaf["phrase"],
            form=leaf["form"],
            start=leaf["start"],
            end=leaf["end"],
            cache=retry_nested_cache,
        )
        if result.get("complete") is True:
            _write_leaf_checkpoint(
                workspace, leaf, result, access.events[event_start:]
            )
        print(
            f"retry-done {cache_key(leaf)} complete={result.get('complete')} "
            f"rows={len(result.get('rows') or [])}",
            flush=True,
        )
        return result

    try:
        completed, retry_receipt = retry_only_completion(
            cache, fetch_leaf, historical_cache_sha256=historical_sha
        )
    finally:
        sec_session.close()
    completed, aggregate_receipt = recompute_derived_aggregates(
        completed, derived_child_keys()
    )
    remaining = {
        key for key, record in completed.items()
        if isinstance(record, Mapping) and record.get("complete") is False
    }
    if remaining:
        raise SourceRunBlocked(f"incomplete FTS records remain: {sorted(remaining)}")

    ledger = build_query_ledger()
    ledger_sha = sha256_text(canonical_json(ledger))
    cell_receipts, candidates = compile_annual_source_plane(ledger, completed)
    census = logical_cell_census(ledger, cell_receipts)
    eligible = eligible_candidates(candidates, set(census["cell_ids"]))
    manifest_one = exact20_manifest(eligible, census)
    manifest_two = exact20_manifest(eligible, census)
    first_bytes, second_bytes = manifest_bytes(manifest_one), manifest_bytes(manifest_two)
    if first_bytes != second_bytes:
        raise SourceRunBlocked("exact-twenty manifest changed on identical-input rerun")

    work_output = workspace / "source_completion"
    cache_path, retry_path = write_retry_version(work_output, completed, retry_receipt)
    completed_cache_sha = file_sha256(cache_path)
    if file_sha256(historical_cache_path) != historical_sha:
        raise SourceRunBlocked("historical #6117 cache changed during retry")

    candidate_path = work_output / "complete_candidate_universe.json"
    write_canonical_json(candidate_path, eligible)
    candidate_sha = file_sha256(candidate_path)
    family_counts = Counter(str(row["family"]) for row in eligible)
    if set(family_counts) != set(FAMILIES):
        raise SourceRunBlocked(
            f"complete candidate universe lacks an eligible family: {dict(family_counts)}"
        )

    access_hosts = _official_hosts(access)
    completion = {
        "schema": "mastermind.dislocation_p0.a1r_source_completion_receipt.v1",
        "status": "COMPLETE",
        "historical_cache": {
            "raw_sha256": historical_sha,
            "preserved_unchanged": True,
            "record_count": len(cache),
            "initial_incomplete_records": len(actual_defects),
        },
        "retry": retry_receipt,
        "derived_aggregate_repair": aggregate_receipt,
        "completed_cache": {
            "raw_sha256": completed_cache_sha,
            "record_count": len(completed),
            "incomplete_records": 0,
        },
        "query_ledger": {
            "canonical_json_sha256": ledger_sha,
            "declared_04d_status": "HISTORICAL_NONAUTHORITY_SUPERSEDED",
            "logical_cells": len(cell_receipts),
            "complete_cells": census["complete"],
            "complete_cell_sha256": census["complete_sha256"],
            "cell_receipts": cell_receipts,
        },
        "candidate_universe": {
            "raw_sha256": candidate_sha,
            "count": len(eligible),
            "count_by_family": dict(sorted(family_counts.items())),
            "pool_sha256_by_family": complete_pool_hashes(eligible),
        },
        "exact_twenty": {
            "manifest_sha256": manifest_one["manifest_sha256"],
            "file_sha256": sha256(first_bytes).hexdigest(),
            "byte_identical_rerun": True,
        },
        "firewall": {
            "forbidden_dirs_present": forbidden_dirs,
            "official_sec_hosts": access_hosts,
            "access_events": access.events,
            "access_log_sha256": access.digest(),
            "banned_reads": access.banned_reads(),
        },
        "authority": {
            "can_rank": False,
            "can_gate": False,
            "can_size": False,
            "can_originate_signal": False,
            "can_escalate": False,
        },
    }
    if authority_flags(completion) != completion["authority"]:
        raise SourceRunBlocked("authority flags changed")
    forbidden = forbidden_market_fields(completion)
    if forbidden:
        raise SourceRunBlocked(f"forbidden source-only fields: {forbidden}")

    completion_path = public_out / PUBLIC_COMPLETION_NAME
    selection_path = public_out / PUBLIC_SELECTION_NAME
    write_canonical_json(completion_path, completion)
    selection_path.parent.mkdir(parents=True, exist_ok=True)
    selection_path.write_bytes(first_bytes)
    if selection_path.read_bytes() != second_bytes:
        raise SourceRunBlocked("written manifest does not reproduce the second run")

    return {
        "historical_cache_sha256": historical_sha,
        "completed_cache_sha256": completed_cache_sha,
        "candidate_universe_sha256": candidate_sha,
        "candidate_count": len(eligible),
        "query_cells_complete": census["complete"],
        "manifest_sha256": manifest_one["manifest_sha256"],
        "manifest_file_sha256": file_sha256(selection_path),
        "retry_receipt_path": str(retry_path),
        "public_completion_path": str(completion_path),
        "public_selection_path": str(selection_path),
        "official_sec_hosts": access_hosts,
    }


def execute_selection_rerun(
    *,
    completed_universe_path: Path,
    completion_receipt_path: Path,
    selection_path: Path,
) -> dict[str, Any]:
    """Rerun only the deterministic exact-20 step over the frozen complete pool.

    The 146-cell source plane is already complete and immutable.  A selection-law
    repair must not re-fetch SEC or rewrite the multi-gigabyte cache; it verifies
    the committed complete-universe and cell receipts, then mints a new selection
    and completion-receipt version while retaining the superseded hashes.
    """
    completed_universe_path = Path(completed_universe_path)
    completion_receipt_path = Path(completion_receipt_path)
    selection_path = Path(selection_path)
    prior_completion_file_sha256 = file_sha256(completion_receipt_path)
    prior_selection_file_sha256 = file_sha256(selection_path)
    completion = json.loads(completion_receipt_path.read_text(encoding="utf-8"))
    universe = json.loads(completed_universe_path.read_text(encoding="utf-8"))
    if not isinstance(completion, dict) or completion.get("status") != "COMPLETE":
        raise SourceRunBlocked("selection-only rerun requires a complete source receipt")
    if not isinstance(universe, list):
        raise SourceRunBlocked("complete candidate universe must be an array")
    universe_receipt = completion.get("candidate_universe")
    if not isinstance(universe_receipt, Mapping) or (
        universe_receipt.get("raw_sha256") != file_sha256(completed_universe_path)
        or universe_receipt.get("count") != len(universe)
    ):
        raise SourceRunBlocked("complete candidate universe does not bind its receipt")
    query_receipt = completion.get("query_ledger")
    cell_receipts = (
        query_receipt.get("cell_receipts")
        if isinstance(query_receipt, Mapping)
        else None
    )
    if not isinstance(cell_receipts, list):
        raise SourceRunBlocked("complete source receipt lacks logical-cell receipts")
    census = logical_cell_census(build_query_ledger(), cell_receipts)
    if (
        query_receipt.get("complete_cells") != 146
        or query_receipt.get("complete_cell_sha256") != census["complete_sha256"]
    ):
        raise SourceRunBlocked("logical-cell completion receipt does not replay")

    manifest_one = exact20_manifest(universe, census)
    manifest_two = exact20_manifest(universe, census)
    first_bytes, second_bytes = manifest_bytes(manifest_one), manifest_bytes(manifest_two)
    if first_bytes != second_bytes:
        raise SourceRunBlocked("exact-twenty manifest changed on identical-input rerun")
    prior_exact = completion.get("exact_twenty")
    if not isinstance(prior_exact, Mapping):
        raise SourceRunBlocked("prior exact-twenty receipt is absent")
    completion["schema"] = "mastermind.dislocation_p0.a1r_source_completion_receipt.v2"
    completion["selection_law_repair"] = {
        "uniqueness": ["cik", "accession"],
        "reason": "GLOBAL_CIK_UNIQUENESS_WAS_STRICTER_THAN_FROZEN_SOURCE_LAW",
        "superseded_completion_file_sha256": prior_completion_file_sha256,
        "superseded_selection_manifest_sha256": prior_exact.get("manifest_sha256"),
        "superseded_selection_file_sha256": prior_selection_file_sha256,
        "source_cache_rewritten": False,
        "network_accessed": False,
    }
    completion["exact_twenty"] = {
        "manifest_sha256": manifest_one["manifest_sha256"],
        "file_sha256": sha256(first_bytes).hexdigest(),
        "byte_identical_rerun": True,
    }
    if forbidden_market_fields(completion):
        raise SourceRunBlocked("selection-only receipt contains forbidden fields")
    write_canonical_json(completion_receipt_path, completion)
    selection_path.write_bytes(first_bytes)
    if selection_path.read_bytes() != second_bytes:
        raise SourceRunBlocked("written manifest does not reproduce the second run")
    return {
        "status": "COMPLETE",
        "mode": "SELECTION_ONLY",
        "candidate_universe_sha256": universe_receipt["raw_sha256"],
        "candidate_count": len(universe),
        "query_cells_complete": census["complete"],
        "manifest_sha256": manifest_one["manifest_sha256"],
        "manifest_file_sha256": file_sha256(selection_path),
        "selection_changed": prior_exact.get("manifest_sha256")
        != manifest_one["manifest_sha256"],
        "source_cache_rewritten": False,
        "network_accessed": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--historical-cache", type=Path)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--public-out", type=Path)
    parser.add_argument("--selection-only", action="store_true")
    parser.add_argument("--completed-universe", type=Path)
    parser.add_argument("--completion-receipt", type=Path)
    parser.add_argument("--selection-output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.selection_only:
            if not all(
                (args.completed_universe, args.completion_receipt, args.selection_output)
            ):
                raise SourceRunBlocked(
                    "--selection-only requires --completed-universe, "
                    "--completion-receipt, and --selection-output"
                )
            result = execute_selection_rerun(
                completed_universe_path=args.completed_universe,
                completion_receipt_path=args.completion_receipt,
                selection_path=args.selection_output,
            )
        else:
            if not all((args.historical_cache, args.workspace, args.public_out)):
                raise SourceRunBlocked(
                    "source completion requires --historical-cache, --workspace, "
                    "and --public-out"
                )
            result = execute_source_run(
                historical_cache_path=args.historical_cache,
                workspace=args.workspace,
                public_out=args.public_out,
            )
    except Exception as exc:  # noqa: BLE001 - CLI emits one named blocker.
        print(canonical_json({"status": "BLOCKED", "blocker": type(exc).__name__, "detail": str(exc)}))
        return 1
    print(canonical_json({"status": "COMPLETE", **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
