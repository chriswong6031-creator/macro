"""engine.neuralweb.envelope — Provenance-stamp helper for the Neural Web bus.

PURPOSE
-------
Every registered artifact that flows on the signal bus must carry five sibling
keys — the "envelope" — so consumers can verify provenance, detect staleness,
and skip unchanged work without re-fetching bytes.

THE WRAPPER PROHIBITION (2026-07-02 semis incident)
---------------------------------------------------
The five keys MUST be added as siblings on the artifact's top-level dict,
never as a nested wrapper object.  The incident: scripts/build_feeds.py
extracts the risk_radar sub-object with::

    rr = latest.get("risk_radar")
    _write_json(out, "risk_radar.json", rr)

It writes whatever `rr` IS — not a wrapper around it.  If the producer had
wrapped it as ``{"envelope": {...}, "data": rr}``, then ``rr`` would be that
wrapper and ``site/feeds/risk_radar.json`` would expose ``rr.get("state") ->
None``, re-darkening the feed exactly as the incident did.  Sibling keys on
`rr` are preserved verbatim; `rr.get("state")`` still returns the value.

ENVELOPE KEYS
-------------
``schema_version``  int   — schema generation; bump on breaking field changes.
``produced_by``     str   — module path of the producer (e.g. "engine/run.py").
``produced_at``     str   — ISO-8601 UTC build timestamp (NOT the data as_of).
``inputs_hash``     str   — "sha256:" + hex of the payload MINUS the envelope
                            keys, serialised with sort_keys=True.  Unchanged
                            data yields the same hash across builds.
``tier``            str   — qual_ladder tier ("display"|"shadow"|"confirmer"|
                            "scored"|"infrastructure").

ADOPTION RECIPE (two-line change per producer)
----------------------------------------------
::

    from engine.neuralweb.envelope import stamp
    payload = stamp(payload, artifact_id="regime-latest")

That's it. The registry supplies defaults for schema_version / produced_by /
tier.  produced_at is set to the current UTC time; inputs_hash is computed
over the payload-minus-envelope so re-stamping unchanged data gives the same
hash.

To avoid produced_at churn when data has not changed, use stamp_if_changed::

    payload = stamp_if_changed(payload, prev_payload, artifact_id="regime-latest")

When the payload is unchanged (same inputs_hash), the previous envelope is
preserved verbatim — the artifact stays BYTE-IDENTICAL on disk, and
publish_r2's content-hash skip fires.

SCHEMA_VERSION COLLISION GUARD
-------------------------------
``data/regime/latest.json`` already carries a ``schema_version`` int (its own
schema generation counter, not the envelope's).  stamp() detects this and
takes ``max(existing, registry_default)`` rather than clobbering.  The other
four envelope keys are always clobbered (they are ours to own).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.neuralweb.synapse import load_registry

# ─────────────────────────────────────────────────────────────────────────────
# Public constants
# ─────────────────────────────────────────────────────────────────────────────

ENVELOPE_KEYS: tuple[str, ...] = (
    "schema_version",
    "produced_by",
    "produced_at",
    "inputs_hash",
    "tier",
)

# Default schema_version when the registry entry does not specify one.
_DEFAULT_SCHEMA_VERSION = 1


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _compute_inputs_hash(payload_ex_envelope: dict) -> str:
    """sha256 of the canonical JSON of *payload_ex_envelope*.

    sort_keys=True + separators=(",",":") + ensure_ascii=False gives a
    byte-stable serialisation that is independent of insertion order.
    produced_at is excluded so re-stamping unchanged data yields the SAME hash.
    """
    text = json.dumps(
        payload_ex_envelope,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _registry_defaults(artifact_id: str, registry: dict) -> dict:
    """Extract envelope defaults from the registry entry for *artifact_id*.

    Raises
    ------
    KeyError
        When *artifact_id* is not present in the registry's ``artifacts``
        section.  Failing loudly here prevents silent propagation of empty
        ``produced_by`` / ``tier`` values into published artifacts — a class
        of mistake that would only surface at downstream consumers.

        The error message lists up to five known ids so callers can spot typos
        immediately without opening synapse.yml.
    """
    artifacts = registry.get("artifacts", {})
    if artifact_id not in artifacts:
        known = sorted(artifacts.keys())
        sample = known[:5]
        rest = len(known) - len(sample)
        sample_str = ", ".join(repr(k) for k in sample)
        if rest:
            sample_str += f" … (+{rest} more)"
        raise KeyError(
            f"artifact_id {artifact_id!r} not in config/synapse.yml — "
            f"register it first; known ids: {sample_str}"
        )
    entry = artifacts[artifact_id]
    return {
        "schema_version": _DEFAULT_SCHEMA_VERSION,
        "produced_by": entry.get("producer", ""),
        "tier": entry.get("tier", ""),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def strip_envelope(obj: dict) -> dict:
    """Return a shallow copy of *obj* with all ENVELOPE_KEYS removed.

    Used internally before hashing, and available to producers that need to
    compare payloads without the envelope obscuring the diff.
    """
    return {k: v for k, v in obj.items() if k not in ENVELOPE_KEYS}


def stamp(
    payload: dict,
    *,
    artifact_id: str,
    registry: dict | None = None,
    now: datetime | None = None,
) -> dict:
    """Stamp *payload* with the five envelope keys and return a shallow copy.

    The original dict is never mutated.  The returned dict has:
    - All original keys preserved at the top level (sibling, never wrapper).
    - The five envelope keys added / updated.

    Parameters
    ----------
    payload:
        The artifact dict to stamp.  Must be a dict (not a list or scalar).
    artifact_id:
        The registry key (e.g. ``"regime-latest"``).  Used to look up
        defaults for produced_by, tier, and schema_version.
    registry:
        Parsed synapse.yml dict.  If None, load_registry() is called.
    now:
        UTC datetime for produced_at.  Injectable so tests are deterministic.
        Defaults to ``datetime.now(timezone.utc)``.

    COLLISION GUARD — schema_version
    ---------------------------------
    If the payload already carries ``schema_version`` as its own field (e.g.
    ``data/regime/latest.json`` has ``"schema_version": 1`` as part of its
    own schema), we take ``max(existing, registry_default)`` rather than
    clobbering.  The other four keys (produced_by, produced_at, inputs_hash,
    tier) are always written by the envelope — they are ours to own.
    """
    if not isinstance(payload, dict):
        raise TypeError(f"stamp() requires a dict, got {type(payload).__name__}")

    if registry is None:
        registry = load_registry()

    now = now or datetime.now(timezone.utc)
    defaults = _registry_defaults(artifact_id, registry)

    # Strip pre-existing envelope keys before hashing so re-stamping gives the
    # same inputs_hash on unchanged data.
    payload_ex = strip_envelope(payload)
    h = _compute_inputs_hash(payload_ex)

    # Collision guard: if the payload already owns schema_version, respect it.
    existing_sv = payload.get("schema_version")
    registry_sv = defaults["schema_version"]
    if isinstance(existing_sv, int):
        # Take the max — the payload's own schema may have advanced beyond our default.
        resolved_sv = max(existing_sv, registry_sv)
    else:
        resolved_sv = registry_sv

    stamped = dict(payload_ex)  # shallow copy without old envelope keys
    stamped["schema_version"] = resolved_sv
    stamped["produced_by"] = defaults["produced_by"]
    stamped["produced_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    stamped["inputs_hash"] = h
    stamped["tier"] = defaults["tier"]
    return stamped


def stamp_if_changed(
    payload: dict,
    prev_payload: dict | None,
    *,
    artifact_id: str,
    registry: dict | None = None,
    now: datetime | None = None,
) -> dict:
    """Stamp *payload* only when the data content has changed vs *prev_payload*.

    When the computed inputs_hash of *payload* matches the inputs_hash already
    present in *prev_payload*, ``prev_payload`` is returned **verbatim** — the
    exact same Python object, unchanged.  Returning the previous object rather
    than rebuilding it guarantees byte-for-bit identity when the result is
    later serialised with ``json.dumps(sort_keys=False)``, which is the path
    that publish_r2.py (line 196) uses for its md5-based content-hash skip.
    Any dict rebuild — even one that copies all keys faithfully — risks
    reordering Python dict insertion order and producing different JSON bytes.

    Consequence: even if the caller passes a key-reordered payload whose
    content is identical to ``prev_payload``, ``stamp_if_changed`` returns
    ``prev_payload`` verbatim (the hash matches because
    ``_compute_inputs_hash`` uses ``sort_keys=True``).  The returned bytes are
    the *previous* serialisation, not the caller's ordering.  Callers that
    need the new key order must use ``stamp()`` directly.

    When data has changed (or prev_payload is None / has no inputs_hash), a
    fresh stamp is applied via stamp().

    Parameters
    ----------
    payload:
        Current artifact dict (without envelope, or with stale envelope).
    prev_payload:
        The artifact as it was on the previous run (e.g. read from disk).
        May be None if no previous version exists.
    artifact_id, registry, now:
        Forwarded to stamp().
    """
    payload_ex = strip_envelope(payload)
    new_hash = _compute_inputs_hash(payload_ex)

    if prev_payload is not None:
        prev_hash = prev_payload.get("inputs_hash", "")
        if prev_hash == new_hash:
            # Data unchanged — return prev_payload VERBATIM so the serialised
            # bytes are bit-for-bit identical to the previous on-disk artifact.
            # This is what lets publish_r2.py's md5-based content-hash skip fire
            # (publish_r2.py:196).  Any dict-rebuild here — even one that copies
            # the same keys — can reorder Python dict insertion order and produce
            # different JSON bytes under json.dumps(sort_keys=False).
            return prev_payload

    # Data changed or no previous version — apply a fresh stamp.
    return stamp(payload, artifact_id=artifact_id, registry=registry, now=now)


def verify(obj: dict, *, registry: dict | None = None) -> list[str]:
    """Return a list of problems with *obj*'s envelope.

    An empty list means the envelope is present and internally consistent.
    Problems include: missing keys, hash mismatch, unknown tier.
    """
    if registry is None:
        try:
            registry = load_registry()
        except Exception:  # noqa: BLE001
            registry = {}

    problems: list[str] = []

    # 1. Required keys present?
    for k in ENVELOPE_KEYS:
        if k not in obj:
            problems.append(f"missing envelope key: {k!r}")

    # 2. inputs_hash internally consistent?
    if "inputs_hash" in obj:
        payload_ex = strip_envelope(obj)
        expected = _compute_inputs_hash(payload_ex)
        if obj["inputs_hash"] != expected:
            problems.append(
                f"inputs_hash mismatch: stored={obj['inputs_hash']!r} "
                f"computed={expected!r}"
            )

    # 3. tier is from the known vocabulary?
    tier_vocab = set(registry.get("meta", {}).get("tier_vocabulary", []))
    if tier_vocab and "tier" in obj:
        t = obj["tier"]
        if t not in tier_vocab:
            problems.append(
                f"unknown tier {t!r}; valid: {sorted(tier_vocab)}"
            )

    return problems


# ─────────────────────────────────────────────────────────────────────────────
# Sidecar for non-JSON formats (parquet, JSONL)
# ─────────────────────────────────────────────────────────────────────────────

def write_sidecar(
    artifact_path: Path,
    *,
    artifact_id: str,
    registry: dict | None = None,
    now: datetime | None = None,
    payload_bytes: bytes | None = None,
) -> Path:
    """Write a ``<artifact_path>.envelope.json`` sidecar for a binary artifact.

    For formats (parquet, JSONL) that cannot carry inline metadata without
    schema changes, the sidecar holds the five envelope fields plus:
    - ``artifact_path``: path relative to the repo root (or absolute if
      relative cannot be determined).
    - ``byte_sha256``: sha256 of the artifact's raw bytes (file content hash,
      distinct from inputs_hash which covers the parsed payload).

    Parameters
    ----------
    artifact_path:
        Path to the artifact file.
    payload_bytes:
        If provided, used as the artifact bytes for byte_sha256 instead of
        reading the file.  Useful when the file is written in the same build
        step and may not yet be flushed.
    """
    if registry is None:
        registry = load_registry()
    now = now or datetime.now(timezone.utc)
    defaults = _registry_defaults(artifact_id, registry)

    # Read the artifact file for the byte hash.
    raw: bytes
    if payload_bytes is not None:
        raw = payload_bytes
    elif artifact_path.exists():
        raw = artifact_path.read_bytes()
    else:
        raw = b""

    byte_sha = "sha256:" + hashlib.sha256(raw).hexdigest()

    # Attempt a repo-relative path.
    try:
        rel = artifact_path.resolve().relative_to(
            Path(__file__).resolve().parent.parent.parent
        )
        rel_str = str(rel)
    except ValueError:
        rel_str = str(artifact_path)

    sidecar: dict[str, Any] = {
        "schema_version": defaults["schema_version"],
        "produced_by": defaults["produced_by"],
        "produced_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inputs_hash": byte_sha,   # for binary artifacts, the hash IS the byte hash
        "tier": defaults["tier"],
        "artifact_path": rel_str,
        "byte_sha256": byte_sha,
    }

    sidecar_path = Path(str(artifact_path) + ".envelope.json")
    sidecar_path.write_text(
        json.dumps(sidecar, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return sidecar_path


def read_sidecar(artifact_path: Path) -> dict | None:
    """Read the sidecar for *artifact_path*, or None if absent / unreadable."""
    sidecar_path = Path(str(artifact_path) + ".envelope.json")
    if not sidecar_path.exists():
        return None
    try:
        return json.loads(sidecar_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
