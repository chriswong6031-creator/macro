"""Project the verified earnings-evidence root into immutable story packets.

This worker is deliberately a transport/compiler bridge, not an author.  It
hydrates one exact ``earnings_evidence`` root from R2, reuses unchanged packet
objects from the last ``earnings_story_packets`` root, compiles only new or
corrected evidence revisions, validates the complete local projection, and
then advances the packet root with compare-and-swap.

No CLI option can choose a tier or supply prose.  Promotion is replayed from
the repository policy and exact evidence receipts, with zero model calls and
zero tokens.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.earnings_narrative.contracts import (
    TERMINAL_TRANSCRIPT_SCHEMA,
    ContractError,
    canonical_json_bytes,
    canonical_json_sha256,
    canonical_transcript_body_bytes,
    sha256_bytes,
    validate_manifest,
)
from engine.earnings_narrative.promotion import (
    load_promotion_policy,
    promotion_policy_sha256,
)
from engine.earnings_narrative.story_packets import validate_story_packet_manifest
from engine.earnings_narrative.story_store import (
    verify_story_packet_store,
    write_story_packet_generation,
)
from scripts.publish_earnings_evidence_graph_r2 import PREFIX as EVIDENCE_PREFIX
from scripts.publish_earnings_story_packets_r2 import (
    PREFIX as STORY_PREFIX,
    PUBLISH_CONFLICT,
    publish as publish_story_packets,
)


DOWNLOAD_WORKERS = 12


class RefreshError(RuntimeError):
    """A prerequisite cannot be proven; retain the last-good packet root."""


def _client() -> Any | None:
    endpoint = os.environ.get("R2_ENDPOINT")
    access_key = os.environ.get("R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (endpoint and access_key and secret_key):
        return None
    try:
        import boto3  # noqa: PLC0415
        from botocore.config import Config  # noqa: PLC0415
    except ImportError:
        return None
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(
            region_name="auto",
            signature_version="s3v4",
            max_pool_connections=DOWNLOAD_WORKERS,
            retries={"max_attempts": 4, "mode": "standard"},
        ),
    )


def _is_not_found(exc: Exception) -> bool:
    response = getattr(exc, "response", {})
    error = response.get("Error", {}) if isinstance(response, Mapping) else {}
    metadata = response.get("ResponseMetadata", {}) if isinstance(response, Mapping) else {}
    return (
        str(error.get("Code") or "").lower() in {"404", "nosuchkey", "notfound", "no_such_key"}
        or int(metadata.get("HTTPStatusCode") or 0) == 404
        or (type(exc) is RuntimeError and str(exc).strip().lower() in {"missing", "not found"})
    )


def _read_object(s3: Any, bucket: str, key: str, *, allow_missing: bool = False) -> bytes | None:
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        stream = response["Body"]
        body = stream.read()
        close = getattr(stream, "close", None)
        if callable(close):
            close()
    except Exception as exc:  # noqa: BLE001
        if allow_missing and _is_not_found(exc):
            return None
        raise RefreshError(f"cannot read R2 object {key}: {exc}") from exc
    if not isinstance(body, bytes):
        raise RefreshError(f"R2 object did not return bytes: {key}")
    return body


def _canonical_object(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RefreshError(f"{label} is not UTF-8 JSON") from exc
    if not isinstance(payload, dict) or raw != canonical_json_bytes(payload):
        raise RefreshError(f"{label} is not canonical JSON")
    return payload


def _atomic_bytes(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        temporary.write_bytes(body)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _root_snapshot(
    s3: Any,
    bucket: str,
    *,
    prefix: str,
    validator: Callable[[object], None],
    required: bool,
) -> tuple[dict[str, Any] | None, bytes | None, str | None]:
    """Read a root and prove its immutable generation is byte-identical."""
    raw = _read_object(s3, bucket, f"{prefix}/manifest.json", allow_missing=not required)
    if raw is None:
        return None, None, None
    marker = _canonical_object(raw, label=f"{prefix} root marker")
    try:
        validator(marker)
    except Exception as exc:  # noqa: BLE001
        raise RefreshError(f"{prefix} root marker fails its contract: {exc}") from exc
    generation_id = str(marker.get("generation_id") or "")
    immutable = _read_object(s3, bucket, f"{prefix}/generations/{generation_id}/manifest.json")
    if immutable != raw:
        raise RefreshError(f"{prefix} immutable generation differs from its root marker")
    return marker, raw, sha256_bytes(raw)


def _write_verified_object(path: Path, body: bytes, receipt: Mapping[str, Any], *, label: str) -> None:
    expected_sha = receipt.get("sha256")
    expected_bytes = receipt.get("bytes")
    if (
        not isinstance(expected_sha, str)
        or len(expected_sha) != 64
        or isinstance(expected_bytes, bool)
        or not isinstance(expected_bytes, int)
        or expected_bytes <= 0
        or len(body) != expected_bytes
        or sha256_bytes(body) != expected_sha
    ):
        raise RefreshError(f"{label} receipt mismatch")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RefreshError(f"{label} is not UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise RefreshError(f"{label} must contain a JSON object")
    expected = (
        canonical_transcript_body_bytes(payload)
        if receipt.get("schema") == TERMINAL_TRANSCRIPT_SCHEMA
        else canonical_json_bytes(payload)
    )
    if body != expected:
        raise RefreshError(f"{label} canonical replay mismatch")
    _atomic_bytes(path, body)


def _download_receipts(
    s3: Any,
    bucket: str,
    *,
    prefix: str,
    root: Path,
    receipts: Mapping[str, Mapping[str, Any]],
) -> None:
    """Hydrate a deduplicated receipt set and reject every absent/tampered body."""
    unique: dict[str, Mapping[str, Any]] = {}
    for receipt in receipts.values():
        object_key = receipt.get("object_key")
        if (
            not isinstance(object_key, str)
            or not object_key
            or object_key.startswith("/")
            or ".." in Path(object_key).parts
        ):
            raise RefreshError(f"{prefix} manifest contains an unsafe object key")
        prior = unique.get(object_key)
        if prior is not None and dict(prior) != dict(receipt):
            raise RefreshError(f"{prefix} object key has conflicting receipts: {object_key}")
        unique[object_key] = receipt

    def fetch(item: tuple[str, Mapping[str, Any]]) -> None:
        object_key, receipt = item
        body = _read_object(s3, bucket, f"{prefix}/{object_key}")
        assert body is not None
        _write_verified_object(root / object_key, body, receipt, label=f"{prefix}/{object_key}")

    errors: list[Exception] = []
    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS, thread_name_prefix=f"{prefix}-hydrate") as pool:
        futures = [pool.submit(fetch, item) for item in sorted(unique.items())]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
    if errors:
        raise RefreshError(str(errors[0])) from errors[0]


def _hydrate_story_lineage(
    s3: Any,
    bucket: str,
    *,
    root: Path,
    marker: Mapping[str, Any],
    marker_raw: bytes,
) -> None:
    """Hydrate the current packet catalog, plus every immutable parent marker."""
    _atomic_bytes(root / "manifest.json", marker_raw)
    generation_id = str(marker["generation_id"])
    _atomic_bytes(root / "generations" / generation_id / "manifest.json", marker_raw)
    current: Mapping[str, Any] = marker
    seen = {generation_id}
    lineage_files: dict[str, Mapping[str, Any]] = {
        str(value["object_key"]): value for value in marker["files"].values()
    }
    while current.get("parent_generation_id") is not None:
        parent_id = str(current["parent_generation_id"])
        if parent_id in seen:
            raise RefreshError("earnings story packet parent chain has a cycle")
        seen.add(parent_id)
        parent_raw = _read_object(s3, bucket, f"{STORY_PREFIX}/generations/{parent_id}/manifest.json")
        assert parent_raw is not None
        parent = _canonical_object(parent_raw, label=f"story packet parent {parent_id}")
        try:
            validate_story_packet_manifest(parent)
        except Exception as exc:  # noqa: BLE001
            raise RefreshError(f"story packet parent {parent_id} fails its contract: {exc}") from exc
        if parent.get("generation_id") != parent_id:
            raise RefreshError("earnings story packet parent generation id mismatch")
        _atomic_bytes(root / "generations" / parent_id / "manifest.json", parent_raw)
        for receipt in parent["files"].values():
            object_key = str(receipt["object_key"])
            prior = lineage_files.get(object_key)
            if prior is not None and dict(prior) != dict(receipt):
                raise RefreshError(f"story packet lineage receipt collision: {object_key}")
            lineage_files[object_key] = receipt
        current = parent
    _download_receipts(s3, bucket, prefix=STORY_PREFIX, root=root, receipts=lineage_files)


def _evidence_receipts_needed(
    evidence: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
    *,
    policy_sha256: str,
) -> dict[str, Mapping[str, Any]]:
    prior_packets = prior.get("packets") if isinstance(prior, Mapping) else None
    prior_policy = prior.get("policy") if isinstance(prior, Mapping) else None
    same_policy = isinstance(prior_policy, Mapping) and prior_policy.get("sha256") == policy_sha256
    needed: dict[str, Mapping[str, Any]] = {}
    for key, event in evidence["events"].items():
        prior_index = prior_packets.get(key) if isinstance(prior_packets, Mapping) else None
        if (
            same_policy
            and isinstance(prior_index, Mapping)
            and prior_index.get("source_sha256") == event.get("source_sha256")
        ):
            continue
        for logical in (event["fact_pack"], event["claim_graph"], event["source_body"]):
            receipt = evidence["files"].get(logical)
            if not isinstance(receipt, Mapping):
                raise RefreshError(f"earnings evidence receipt missing: {logical}")
            needed[str(logical)] = receipt
    return needed


def refresh(
    work_dir: str | Path,
    *,
    out_dir: str | Path | None = None,
    promote: bool = False,
    s3: Any | None = None,
    bucket: str | None = None,
) -> int:
    """Hydrate, deterministically compile, verify, and optionally CAS-publish."""
    client = s3 if s3 is not None else _client()
    if client is None:
        print("earnings story packets: no R2 credentials; deterministic projection skipped")
        return 0
    target_bucket = bucket or os.environ.get("R2_BUCKET", "")
    if not target_bucket:
        raise RefreshError("R2_BUCKET not set for earnings story packet projection")
    scratch = Path(work_dir)
    scratch.mkdir(parents=True, exist_ok=True)
    evidence_dir = scratch / "evidence"
    output = Path(out_dir) if out_dir is not None else scratch / "output"
    evidence, evidence_raw, _evidence_digest = _root_snapshot(
        client,
        target_bucket,
        prefix=EVIDENCE_PREFIX,
        validator=validate_manifest,
        required=True,
    )
    assert evidence is not None and evidence_raw is not None
    if evidence.get("status") != "ready" or not evidence.get("events"):
        raise RefreshError("earnings evidence root is not a non-empty ready catalog")
    prior, prior_raw, prior_digest = _root_snapshot(
        client,
        target_bucket,
        prefix=STORY_PREFIX,
        validator=validate_story_packet_manifest,
        required=False,
    )
    policy = load_promotion_policy()
    policy_sha = promotion_policy_sha256(policy)
    evidence_receipt = {
        "schema": evidence["schema"],
        "generation_id": evidence["generation_id"],
        "manifest_sha256": canonical_json_sha256(evidence),
    }
    if (
        prior is not None
        and prior.get("evidence_root") == evidence_receipt
        and isinstance(prior.get("policy"), Mapping)
        and prior["policy"].get("sha256") == policy_sha
    ):
        print(
            "earnings story packets: evidence root and policy unchanged; "
            f"generation={prior['generation_id']} is a true no-op"
        )
        return 0

    if prior is None and (output / "manifest.json").exists():
        raise RefreshError("local story marker exists while the authoritative R2 root is absent")
    if prior is not None:
        assert prior_raw is not None
        _hydrate_story_lineage(client, target_bucket, root=output, marker=prior, marker_raw=prior_raw)

    _atomic_bytes(evidence_dir / "manifest.json", evidence_raw)
    _atomic_bytes(
        evidence_dir / "generations" / str(evidence["generation_id"]) / "manifest.json",
        evidence_raw,
    )
    needed = _evidence_receipts_needed(evidence, prior, policy_sha256=policy_sha)
    _download_receipts(client, target_bucket, prefix=EVIDENCE_PREFIX, root=evidence_dir, receipts=needed)
    try:
        _generation, manifest = write_story_packet_generation(
            output,
            evidence_dir,
            policy=policy,
            prior_manifest=prior,
        )
    except (ContractError, OSError, ValueError) as exc:
        raise RefreshError(f"story packet compilation refused: {exc}") from exc
    health = verify_story_packet_store(output, manifest=manifest)
    if health.get("status") != "ready":
        raise RefreshError("story packet store verification failed: " + ", ".join(health.get("warnings") or []))
    tier_counts = {"B": 0, "C": 0}
    for index in manifest["packets"].values():
        receipt = manifest["files"][index["object_key"]]
        packet = json.loads((output / receipt["object_key"]).read_text(encoding="utf-8"))
        tier = str(packet["promotion"]["tier"])
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
    print(
        "earnings story packets: verified deterministic projection "
        f"generation={manifest['generation_id']} packets={health['packet_count']} "
        f"tier_b={tier_counts.get('B', 0)} tier_c={tier_counts.get('C', 0)} "
        f"evidence_objects_fetched={len(needed)}"
    )
    if not promote:
        print("earnings story packets: public root not promoted")
        return 0
    result = publish_story_packets(
        output,
        expected_base_marker_sha256=prior_digest,
        require_absent_root=prior is None,
        s3=client,
        bucket=target_bucket,
    )
    if result == PUBLISH_CONFLICT:
        print("earnings story packets: root promotion lost a safe compare-and-swap race")
        return result
    if result != 0:
        raise RefreshError(f"story packet R2 publication failed with exit code {result}")
    print("earnings story packets: immutable generation published and root marker promoted")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True, help="Disposable hydration scratch parent")
    parser.add_argument("--out-dir", type=Path, default=None, help="Optional verified generation handoff directory")
    parser.add_argument("--promote", action="store_true", help="CAS-promote the verified packet root")
    args = parser.parse_args(argv)
    try:
        return refresh(args.work_dir, out_dir=args.out_dir, promote=args.promote)
    except RefreshError as exc:
        print(f"earnings story packets: refresh refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
