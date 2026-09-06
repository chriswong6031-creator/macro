"""Shared contract for ``mastermind.macro_workspace_snapshot.v1``.

Validate + canonicalize + deterministic-digest for the twelve-workspace Macro &
Monetary snapshot contract. This module is the single authority that:

* loads the committed closed schema
  (``contracts/market_os/macro_workspace_snapshot.v1.schema.json``);
* canonicalizes a snapshot deterministically;
* computes a content digest that is STABLE under wall-clock/identity/build-
  provenance churn — the digest excludes exactly the volatile generation
  fields (``generation_id``, ``built_at``, ``rendered_at``, ``content_sha256``,
  ``code_version``) so an identical owner input reproduces an identical digest
  across two builds, even when the two builds run at different commits
  (``code_version`` is re-derived from ``git rev-parse HEAD`` per invocation
  and remains published as provenance — it is simply excluded from the hash);
* seals a snapshot (``finalize``) by writing the derived ``content_sha256`` and a
  content-derived ``generation_id``;
* validates a snapshot and FAILS CLOSED on an unknown top-level key, an
  unsupported contract id/version, a schema violation, or a hash mismatch.

Pure: stdlib + ``jsonschema`` only. No owner engine import, no wall-clock read of
its own (``built_at`` is always supplied by the caller).
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker

CONTRACT_ID = "mastermind.macro_workspace_snapshot.v1"
CONTRACT_VERSION = "1.0.0"

# The fields that MUST NOT influence the content digest: a generation identity,
# the wall-clock stamps, and the build-provenance stamp (code_version, derived
# from `git rev-parse HEAD` per invocation) that all legitimately differ between
# two builds of the same owner input (adversarial review finding F2 — a build
# from a different commit but identical owner input must reproduce an
# identical digest). Everything else is content.
VOLATILE_GENERATION_FIELDS = (
    "generation_id", "built_at", "rendered_at", "content_sha256", "code_version",
)

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "contracts" / "market_os" / "macro_workspace_snapshot.v1.schema.json"

_PLACEHOLDER_DIGEST = "0" * 64


class ContractError(ValueError):
    """A snapshot violated the closed contract (schema, version, or integrity)."""


@lru_cache(maxsize=1)
def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = load_schema()
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def canonical_json(obj: Any) -> str:
    """Deterministic JSON: sorted keys, no spaces, unicode kept, no NaN/Inf."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def content_digest(snapshot: Mapping[str, Any]) -> str:
    """sha256 over canonical JSON of everything EXCEPT the volatile generation
    fields. Identical owner input -> identical digest, regardless of build time
    or a freshly minted generation id."""
    payload = copy.deepcopy(dict(snapshot))
    gen = payload.get("generation")
    if isinstance(gen, dict):
        for field in VOLATILE_GENERATION_FIELDS:
            gen[field] = None
    return sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def derive_generation_id(snapshot: Mapping[str, Any], digest: str) -> str:
    """A content-derived, deterministic generation id (never a random uuid), so
    two builds of identical owner input carry an identical id and hash."""
    ws = (snapshot.get("workspace") or {}).get("id", "unknown")
    region = (snapshot.get("region") or {}).get("code", "??")
    return f"{ws}-{region}-{digest[:16]}"


def finalize(snapshot: Mapping[str, Any]) -> dict:
    """Seal a composed snapshot: set the derived content_sha256 and a
    content-derived generation_id. Returns a new dict; input is not mutated."""
    snap = copy.deepcopy(dict(snapshot))
    if "generation" not in snap or not isinstance(snap["generation"], dict):
        raise ContractError("snapshot is missing a generation block")
    digest = content_digest(snap)
    snap["generation"]["content_sha256"] = digest
    snap["generation"]["generation_id"] = derive_generation_id(snap, digest)
    return snap


def validate(snapshot: Any, *, check_hash: bool = True) -> None:
    """Raise :class:`ContractError` unless ``snapshot`` satisfies the closed
    contract. Fails closed on: non-object, unknown/missing contract id,
    unsupported version, ANY schema violation (which includes an unknown
    top-level key, since the schema is additionalProperties:false), and — when
    ``check_hash`` — a content_sha256 that does not equal the recomputed digest."""
    if not isinstance(snapshot, Mapping):
        raise ContractError("snapshot is not a JSON object")

    sch = snapshot.get("schema")
    if not isinstance(sch, Mapping) or sch.get("contract") != CONTRACT_ID:
        raise ContractError(
            f"unknown or missing contract id: {sch.get('contract') if isinstance(sch, Mapping) else sch!r}"
        )
    if sch.get("version") != CONTRACT_VERSION:
        raise ContractError(f"unsupported schema version: {sch.get('version')!r}")

    errors = sorted(_validator().iter_errors(snapshot), key=lambda e: list(e.path))
    if errors:
        joined = "; ".join(
            f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors[:6]
        )
        raise ContractError(f"schema validation failed: {joined}")

    if check_hash:
        declared = (snapshot.get("generation") or {}).get("content_sha256")
        if declared == _PLACEHOLDER_DIGEST:
            raise ContractError("content_sha256 is still the unsealed placeholder")
        recomputed = content_digest(snapshot)
        if declared != recomputed:
            raise ContractError(
                f"content_sha256 mismatch: declared {declared} != recomputed {recomputed}"
            )


def check(snapshot: Any, *, check_hash: bool = True) -> tuple[bool, str | None]:
    """Non-raising validation for consumers: (ok, reason_when_not_ok)."""
    try:
        validate(snapshot, check_hash=check_hash)
        return True, None
    except ContractError as exc:
        return False, str(exc)
