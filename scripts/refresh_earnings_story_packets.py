"""Project the verified earnings-evidence root into immutable story packets.

This worker is deliberately a transport/compiler bridge, not an author.  It
hydrates one exact ``earnings_evidence`` root from R2, reuses unchanged packet
objects from the last ``earnings_story_packets`` root, compiles only new or
corrected evidence revisions, validates the bounded transition, and then
advances the packet root with compare-and-swap.

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
import time
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
    verify_story_packet_delta_store,
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
DEFAULT_MAX_NEW_EVENTS = 500
DEFAULT_VERIFY_LINEAGE_DEPTH = 1


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


def _stage_current_story_root(
    s3: Any,
    bucket: str,
    *,
    root: Path,
    marker: Mapping[str, Any],
    marker_raw: bytes,
    prior_body_keys: set[str],
) -> int:
    """Stage the verified parent marker and only correction bodies that need it.

    The old hourly path downloaded every packet object in the lifetime catalog
    before adding at most 500 new calls.  At 6,000 packets that already consumed
    ~18 minutes; corpus growth therefore recreated the timeout after the first
    recovery.  Unchanged content-addressed packet bodies need no replay here:
    their exact index rows + receipts are inherited from the immutable parent.
    The daily remote audit still performs the complete object/evidence replay.
    """
    _atomic_bytes(root / "manifest.json", marker_raw)
    generation_id = str(marker["generation_id"])
    _atomic_bytes(root / "generations" / generation_id / "manifest.json", marker_raw)
    receipts: dict[str, Mapping[str, Any]] = {}
    for key in sorted(prior_body_keys):
        index = marker["packets"].get(key)
        if not isinstance(index, Mapping):
            raise RefreshError(f"prior story packet index missing for correction: {key}")
        receipt = marker["files"].get(index.get("object_key"))
        if not isinstance(receipt, Mapping):
            raise RefreshError(f"prior story packet receipt missing for correction: {key}")
        receipts[str(receipt["object_key"])] = receipt
    if receipts:
        _download_receipts(s3, bucket, prefix=STORY_PREFIX, root=root, receipts=receipts)
    return len(receipts)


def _catalog_is_complete(
    evidence: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
    *,
    policy_sha256: str,
) -> bool:
    """True when the prior packet catalog already covers this evidence root."""
    if prior is None:
        return False
    prior_policy = prior.get("policy")
    if not (isinstance(prior_policy, Mapping) and prior_policy.get("sha256") == policy_sha256):
        return False
    prior_packets = prior.get("packets")
    if not isinstance(prior_packets, Mapping):
        return False
    if set(prior_packets) != set(evidence["events"]):
        return False
    for key, event in evidence["events"].items():
        index = prior_packets.get(key)
        if not isinstance(index, Mapping) or index.get("source_sha256") != event.get("source_sha256"):
            return False
    return True


def _correction_keys(
    evidence: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
) -> set[str]:
    """Existing packet keys whose verified transcript revision changed."""
    if not isinstance(prior, Mapping):
        return set()
    prior_packets = prior.get("packets")
    if not isinstance(prior_packets, Mapping):
        return set()
    out: set[str] = set()
    for key, event in evidence["events"].items():
        old = prior_packets.get(key)
        if (
            isinstance(old, Mapping)
            and str(old.get("source_sha256") or "") != str(event.get("source_sha256") or "")
        ):
            out.add(str(key))
    return out


def _phase(name: str) -> Callable[[str], None]:
    started = time.monotonic()

    def done(detail: str = "") -> None:
        extra = f" {detail}" if detail else ""
        print(
            f"earnings story packets: phase {name} {time.monotonic() - started:.1f}s{extra}",
            flush=True,
        )

    return done


def _evidence_receipts_needed(
    evidence: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
    *,
    policy_sha256: str,
    only_keys: set[str] | None = None,
) -> dict[str, Mapping[str, Any]]:
    prior_packets = prior.get("packets") if isinstance(prior, Mapping) else None
    prior_policy = prior.get("policy") if isinstance(prior, Mapping) else None
    same_policy = isinstance(prior_policy, Mapping) and prior_policy.get("sha256") == policy_sha256
    needed: dict[str, Mapping[str, Any]] = {}
    for key, event in evidence["events"].items():
        if only_keys is not None and key not in only_keys:
            continue
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
    max_new_events: int | None = DEFAULT_MAX_NEW_EVENTS,
    verify_lineage_depth: int | None = DEFAULT_VERIFY_LINEAGE_DEPTH,
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
    root_done = _phase("root_manifest")
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
    root_done(
        f"evidence_events={len(evidence['events'])} "
        f"prior_packets={0 if prior is None else len(prior.get('packets') or {})}"
    )
    if _catalog_is_complete(evidence, prior, policy_sha256=policy_sha):
        assert prior is not None
        print(
            "earnings story packets: evidence catalog already fully projected; "
            f"generation={prior['generation_id']} is a true no-op"
        )
        return 0

    if prior is not None:
        prior_policy = prior.get("policy")
        if not isinstance(prior_policy, Mapping) or prior_policy.get("sha256") != policy_sha:
            raise RefreshError(
                "promotion policy changed while a story root exists; bounded hourly projection "
                "cannot mix policy generations — run a separately reviewed policy migration"
            )
    corrections = _correction_keys(evidence, prior)
    if prior is None and (output / "manifest.json").exists():
        raise RefreshError("local story marker exists while the authoritative R2 root is absent")
    if prior is not None:
        assert prior_raw is not None
        hydrate_done = _phase("prior_root_hydration")
        hydrated_prior_objects = _stage_current_story_root(
            client,
            target_bucket,
            root=output,
            marker=prior,
            marker_raw=prior_raw,
            prior_body_keys=corrections,
        )
        hydrate_done(
            f"catalog_receipts_reused={len(prior['files']) - hydrated_prior_objects} "
            f"correction_objects={hydrated_prior_objects}"
        )

    _atomic_bytes(evidence_dir / "manifest.json", evidence_raw)
    _atomic_bytes(
        evidence_dir / "generations" / str(evidence["generation_id"]) / "manifest.json",
        evidence_raw,
    )
    from engine.earnings_narrative.story_store import _pending_new_event_keys

    prior_packets = prior.get("packets") if isinstance(prior, Mapping) else {}
    if not isinstance(prior_packets, Mapping):
        prior_packets = {}
    policy_ref = (
        dict(prior["policy"])
        if prior is not None and isinstance(prior.get("policy"), Mapping)
        else {"schema": "", "sha256": policy_sha, "snapshot": policy}
    )
    pending = _pending_new_event_keys(
        evidence, prior_packets, policy_ref=policy_ref, prior=prior,
    )
    if max_new_events is not None and pending:
        rank_done = _phase("rank_new_event_dates")
        rank_receipts: dict[str, Mapping[str, Any]] = {}
        for key in pending:
            logical = evidence["events"][key]["fact_pack"]
            receipt = evidence["files"].get(logical)
            if not isinstance(receipt, Mapping):
                raise RefreshError(f"earnings evidence receipt missing: {logical}")
            rank_receipts[str(logical)] = receipt
        _download_receipts(
            client, target_bucket, prefix=EVIDENCE_PREFIX, root=evidence_dir, receipts=rank_receipts,
        )
        pending = _pending_new_event_keys(
            evidence,
            prior_packets,
            policy_ref=policy_ref,
            prior=prior,
            evidence_root=evidence_dir,
        )[:max_new_events]
        rank_done(f"selected={len(pending)}")
    changed_keys = corrections | set(pending)
    fetch_keys = changed_keys if max_new_events is not None else None
    needed = _evidence_receipts_needed(
        evidence, prior, policy_sha256=policy_sha, only_keys=fetch_keys,
    )
    fetch_done = _phase("new_evidence_downloads")
    _download_receipts(client, target_bucket, prefix=EVIDENCE_PREFIX, root=evidence_dir, receipts=needed)
    fetch_done(f"objects={len(needed)}")
    compile_done = _phase("story_compilation")
    try:
        _generation, manifest = write_story_packet_generation(
            output,
            evidence_dir,
            policy=policy,
            prior_manifest=prior,
            max_new_events=max_new_events,
            prior_body_keys=corrections if prior is not None else None,
        )
    except (ContractError, OSError, ValueError) as exc:
        raise RefreshError(f"story packet compilation refused: {exc}") from exc
    compile_done(f"packets={len(manifest['packets'])} delta={len(changed_keys)}")
    verify_done = _phase("verification")
    if prior is None:
        health = verify_story_packet_store(
            output, manifest=manifest, lineage_depth=verify_lineage_depth,
        )
    else:
        health = verify_story_packet_delta_store(
            output,
            manifest,
            prior_manifest=prior,
        )
    if health.get("status") != "ready":
        raise RefreshError("story packet store verification failed: " + ", ".join(health.get("warnings") or []))
    verify_done(f"delta_packets={health.get('verified_delta_packet_count', len(manifest['packets']))}")
    tier_counts = {"B": 0, "C": 0}
    for key in sorted(changed_keys):
        index = manifest["packets"].get(key)
        if not isinstance(index, Mapping):
            continue
        receipt = manifest["files"][index["object_key"]]
        path = output / receipt["object_key"]
        if not path.exists():
            continue
        packet = json.loads(path.read_text(encoding="utf-8"))
        tier = str(packet["promotion"]["tier"])
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
    remaining = len(evidence["events"]) - len(manifest["packets"])
    from engine.earnings_narrative.story_store import _event_call_date

    newest_packet = max(
        (
            _event_call_date(evidence_dir, evidence["events"][key], evidence["files"])
            for key in changed_keys
            if key in evidence["events"]
        ),
        default="",
    )
    evidence_newest = str((evidence.get("coverage") or {}).get("newest_call_date") or "")
    print(
        "earnings story packets: verified deterministic projection "
        f"generation={manifest['generation_id']} packets={health['packet_count']} "
        f"delta_tier_b={tier_counts.get('B', 0)} delta_tier_c={tier_counts.get('C', 0)} "
        f"prior_story_objects_fetched={len(corrections)} "
        f"evidence_objects_fetched={len(needed)} remaining={remaining} "
        f"complete={remaining == 0} newest_delta_packet={newest_packet} "
        f"newest_evidence={evidence_newest}"
    )
    if remaining:
        print(
            f"::warning title=earnings-story-packets-catchup::earnings story packets: "
            f"projected {health['packet_count']} of {len(evidence['events'])} evidence "
            f"events; {remaining} remain for later bounded runs",
            flush=True,
        )
    if not promote:
        print("earnings story packets: public root not promoted")
        return 0
    publish_done = _phase("r2_promotion")
    result = publish_story_packets(
        output,
        expected_base_marker_sha256=prior_digest,
        require_absent_root=prior is None,
        s3=client,
        bucket=target_bucket,
        verify_lineage_depth=verify_lineage_depth,
    )
    if result == PUBLISH_CONFLICT:
        print("earnings story packets: root promotion lost a safe compare-and-swap race")
        return result
    if result != 0:
        raise RefreshError(f"story packet R2 publication failed with exit code {result}")
    publish_done()
    print("earnings story packets: immutable generation published and root marker promoted")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True, help="Disposable hydration scratch parent")
    parser.add_argument("--out-dir", type=Path, default=None, help="Optional verified generation handoff directory")
    parser.add_argument("--promote", action="store_true", help="CAS-promote the verified packet root")
    parser.add_argument(
        "--max-new-events",
        type=int,
        default=DEFAULT_MAX_NEW_EVENTS,
        help="Newest-first new-event cap per run (0 disables the cap)",
    )
    parser.add_argument(
        "--verify-lineage-depth",
        type=int,
        default=DEFAULT_VERIFY_LINEAGE_DEPTH,
        help="Parent hops to replay (0 = current generation only, negative = full chain)",
    )
    args = parser.parse_args(argv)
    max_new = None if args.max_new_events <= 0 else args.max_new_events
    lineage_depth = None if args.verify_lineage_depth < 0 else args.verify_lineage_depth
    try:
        return refresh(
            args.work_dir,
            out_dir=args.out_dir,
            promote=args.promote,
            max_new_events=max_new,
            verify_lineage_depth=lineage_depth,
        )
    except RefreshError as exc:
        print(f"earnings story packets: refresh refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
