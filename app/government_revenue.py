"""Read-only API for the Government Revenue vertical intelligence workbench.

The service never recalculates procurement metrics at request time.  It serves
the compact, deterministic artifact produced by
``scripts.build_government_revenue`` and fails closed when that artifact is
missing or malformed.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException, Query

from engine.government_revenue.budget_program import (
    BUDGET_PROGRAM_GRAPH_CONTRACT,
    is_valid_budget_program_graph,
)
from engine.government_revenue.candidates import (
    CONTRACT as CANDIDATE_CONTRACT,
)
from engine.government_revenue.candidates import (
    HISTORICAL_SUPPRESSION_CONFIG_PATH,
    HISTORICAL_SUPPRESSION_SCHEMA_PATH,
    ISSUANCE_CORRECTION_APPLICATION_CONTRACT,
    ISSUANCE_CORRECTION_CONFIG_PATH,
    ISSUANCE_CORRECTION_SCHEMA_PATH,
    build_candidate_observations,
    candidate_latest_semantic_sha256,
    candidate_queue_content_id,
    is_valid_candidate_payload,
    is_valid_candidate_queue,
    validate_candidate_reviewed_history_binding,
)
from engine.government_revenue.candidates import (
    QUEUE_CONTRACT as CANDIDATE_QUEUE_CONTRACT,
)
from engine.government_revenue.dossiers import (
    DOSSIER_CONTRACT,
    dossier_content_id,
    is_valid_dossier_payload,
)
from engine.government_revenue.entity_resolution import load_recipient_entity_graph
from engine.government_revenue.idv_bridge import (
    award_bridge_view,
    build_idv_bridge_payload,
    unavailable_award_bridge_view,
)
from engine.government_revenue.idv_dossiers import (
    IDV_DOSSIER_CONTRACT,
    idv_dossier_content_id,
    is_valid_idv_dossier_payload,
)
from engine.government_revenue.subaward_dossiers import (
    SUBAWARD_DOSSIER_CONTRACT,
    is_valid_subaward_dossier_payload,
    subaward_dossier_content_id,
)
from engine.government_revenue.workspace import is_valid_procurement_workspace

router = APIRouter()

_REPO = Path(os.environ.get("MACRO_REPO", "/opt/macro"))
_PATHS = (
    _REPO / "data" / "government_revenue" / "latest.json",
    _REPO / "site" / "government-revenue-data" / "latest.json",
)
_DOSSIER_PATHS = (
    _REPO / "data" / "government_revenue" / "dossiers.json",
    _REPO / "site" / "government-revenue-data" / "dossiers.json",
)
_SUBAWARD_DOSSIER_PATHS = (
    _REPO / "data" / "government_revenue" / "subaward_dossiers.json",
    _REPO / "site" / "government-revenue-data" / "subaward-dossiers.json",
)
_BUDGET_PROGRAM_PATHS = (
    _REPO / "data" / "government_revenue" / "budget_program_graph.json",
    _REPO / "site" / "government-revenue-data" / "budget-program.json",
)
_IDV_DOSSIER_PATHS = (
    _REPO / "data" / "government_revenue" / "idv_dossiers.json",
    _REPO / "site" / "government-revenue-data" / "idv-dossiers.json",
)
_CANDIDATE_QUEUE_PATHS = (
    _REPO / "data" / "government_revenue" / "candidate_queue.json",
    _REPO / "site" / "government-revenue-data" / "candidates.json",
)
_CANDIDATE_LEDGER_PATH = _REPO / "data" / "government_revenue" / "candidate_ledger.jsonl"
_CANDIDATE_STATE_PATH = _REPO / "data" / "government_revenue" / "candidate_projection_state.json"
_CANDIDATE_STATUS_PATH = _REPO / "data" / "government_revenue" / "candidate_projection_status.json"
_CANDIDATE_REPO_ROOT = _REPO
_CANDIDATE_SUPPRESSION_MANIFEST_PATH = _REPO / HISTORICAL_SUPPRESSION_CONFIG_PATH
_CANDIDATE_SUPPRESSION_SCHEMA_PATH = _REPO / HISTORICAL_SUPPRESSION_SCHEMA_PATH
_CANDIDATE_SUPPRESSION_REQUIRED = True
_CANDIDATE_CORRECTION_MANIFEST_PATH = _REPO / ISSUANCE_CORRECTION_CONFIG_PATH
_CANDIDATE_CORRECTION_SCHEMA_PATH = _REPO / ISSUANCE_CORRECTION_SCHEMA_PATH
_CANDIDATE_CORRECTION_REQUIRED = True
_CANDIDATE_SOURCE_PATHS = (
    _REPO / "data" / "government_revenue" / "latest.json",
    _REPO / "data" / "government_revenue" / "workspace.json",
    _REPO / "data" / "government_revenue" / "recipient_entity_graph.json",
)
_TICKER = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")
_NOTICE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_AWARD_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:|+-]{0,599}$")
_SUBAWARD_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:|+-]{0,599}$")
_BUDGET_LINE_KEY = re.compile(r"^dod:[a-z0-9:_-]{8,600}$")
_BUDGET_PROGRAM_KEY = re.compile(r"^dod-program:[a-z0-9:_-]{8,600}$")
_CANDIDATE_ID = re.compile(r"^grc1-[a-f0-9]{24}$")
_LOCK = threading.RLock()
_CACHE: dict = {"path": None, "mtime_ns": None, "payload": None}
_DOSSIER_CACHE: dict = {"state": None, "payload": None}
_SUBAWARD_DOSSIER_CACHE: dict = {"state": None, "payload": None}
_BUDGET_PROGRAM_CACHE: dict = {"state": None, "payload": None}
_IDV_DOSSIER_CACHE: dict = {"state": None, "payload": None}
_IDV_BRIDGE_CACHE: dict = {"state": None, "payload": None}
_CANDIDATE_CACHE: dict = {"state": None, "payload": None}
_DOD_BUDGET_SOURCE_HOSTS = {"comptroller.defense.gov", "comptroller.war.gov"}
_SENSITIVE_KEY = re.compile(
    r"(?:^private|api[_-]?key|authorization|(?:^|_)(?:secret|token|password|credential)s?(?:$|_)|"
    r"raw_(?:body|payload|receipt|request|response)|(?:request|response)_headers)",
    re.IGNORECASE,
)
_SENSITIVE_QUERY_KEY = re.compile(
    r"(?:api[_-]?key|authorization|secret|token|password|credential)", re.IGNORECASE
)
_SENSITIVE_INLINE_VALUE = re.compile(
    r"(?i)\b(api[_-]?key|authorization|secret|token|password|credential)\s*[:=]\s*[^\s,;&]+"
)
_DOSSIER_SOURCE_HOSTS = {"api.usaspending.gov", "usaspending.gov", "www.usaspending.gov"}


def _public_url(value: object) -> str | None:
    try:
        parsed = urlsplit(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        return None
    query = urlencode([
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not _SENSITIVE_QUERY_KEY.search(key)
    ])
    host = parsed.hostname.lower()
    try:
        port = parsed.port
    except ValueError:
        return None
    if port:
        host = f"{host}:{port}"
    return urlunsplit(("https", host, parsed.path, query, parsed.fragment))


def _scrub_public(value: object) -> object:
    """Recursively remove collector-private keys and credential-shaped URL params."""
    if isinstance(value, dict):
        return {
            str(key): _scrub_public(item)
            for key, item in value.items()
            # A ``source_coverage.authorization`` rail is public semantic
            # metadata (status + reason), not an HTTP Authorization header.
            # Preserve only that exact bounded object; all header/token-shaped
            # authorization keys remain redacted by the general rule.
            if (
                not _SENSITIVE_KEY.search(str(key))
                or (
                    str(key) == "authorization"
                    and isinstance(item, dict)
                    and set(item).issubset({"status", "reason"})
                    and isinstance(item.get("status"), str)
                    and isinstance(item.get("reason"), str)
                )
            )
        }
    if isinstance(value, (list, tuple)):
        return [_scrub_public(item) for item in value]
    if isinstance(value, str) and value.lower().startswith(("http://", "https://")):
        return _public_url(value)
    if isinstance(value, str):
        return _SENSITIVE_INLINE_VALUE.sub(r"\1=[redacted]", value)
    return value


def _artifact_path() -> Path | None:
    return next((path for path in _PATHS if path.exists()), None)


def _dossier_source_url(value: object) -> str | None:
    """The dossier rail admits only scrubbed official USAspending HTTPS URLs."""
    safe = _public_url(value)
    if safe is None:
        return None
    try:
        host = urlsplit(safe).hostname
    except ValueError:
        return None
    return safe if host and host.lower() in _DOSSIER_SOURCE_HOSTS else None


def _dod_budget_source_url(value: object) -> str | None:
    """Expose only stable, credential-free official Comptroller document URLs."""
    safe = _public_url(value)
    if safe is None:
        return None
    try:
        parsed = urlsplit(safe)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.hostname.lower() not in _DOD_BUDGET_SOURCE_HOSTS
        or parsed.username
        or parsed.password
        or port not in {None, 443}
        or parsed.query
        or parsed.fragment
    ):
        return None
    return safe


def _load_dossiers() -> dict:
    """Load one byte-identical, schema-validated dossier generation or fail closed.

    Both canonical and site twins are required.  Serving one after a partial
    publication could silently detach a cursor's content identity from the
    static artifact, so a transient mismatch is intentionally a 503 rather
    than a stale best-effort response.
    """
    canonical, site = _DOSSIER_PATHS
    try:
        canonical_state = canonical.stat()
        site_state = site.stat()
    except OSError as exc:
        raise HTTPException(status_code=503, detail="government revenue dossier artifact unavailable") from exc
    state = (
        canonical_state.st_mtime_ns,
        canonical_state.st_size,
        site_state.st_mtime_ns,
        site_state.st_size,
    )
    with _LOCK:
        if _DOSSIER_CACHE["payload"] is not None and _DOSSIER_CACHE["state"] == state:
            return _DOSSIER_CACHE["payload"]
        try:
            canonical_bytes = canonical.read_bytes()
            site_bytes = site.read_bytes()
            payload = json.loads(canonical_bytes)
        except (OSError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=503, detail="government revenue dossier artifact unreadable") from exc
        if canonical_bytes != site_bytes:
            raise HTTPException(status_code=503, detail="government revenue dossier artifact twin mismatch")
        if (
            not isinstance(payload, dict)
            or payload.get("contract") != DOSSIER_CONTRACT
            or not is_valid_dossier_payload(payload)
            or dossier_content_id(payload) != payload.get("content_id")
        ):
            raise HTTPException(status_code=503, detail="government revenue dossier artifact schema mismatch")
        _DOSSIER_CACHE.update(state=state, payload=payload)
        return payload


def _prime_award_key_by_generated_id(payload: dict) -> dict[str, str]:
    """Build the exact, source-native parent bridge from the prime dossier."""
    mapping: dict[str, str] = {}
    for row in payload.get("awards") or []:
        if not isinstance(row, dict):
            raise HTTPException(status_code=503, detail="government revenue dossier schema mismatch")
        award_key = row.get("award_key")
        identity = row.get("identity")
        generated_award_id = (
            identity.get("generated_award_id") if isinstance(identity, dict) else None
        )
        if generated_award_id is None:
            continue
        if not isinstance(generated_award_id, str) or not generated_award_id or not isinstance(award_key, str) or not award_key:
            raise HTTPException(status_code=503, detail="government revenue dossier parent bridge invalid")
        previous = mapping.get(generated_award_id)
        if previous is not None and previous != award_key:
            raise HTTPException(status_code=503, detail="government revenue dossier parent bridge ambiguous")
        mapping[generated_award_id] = award_key
    return mapping


def _subaward_parent_binding(row: dict) -> tuple[str, str] | None:
    """Read only the strict parent pair emitted by the build-time rail."""
    award_key = row.get("parent_award_key")
    identity = row.get("identity")
    generated_award_id = (
        identity.get("parent_generated_award_id")
        if isinstance(identity, dict)
        else None
    )
    if not isinstance(award_key, str) or not award_key:
        return None
    if not isinstance(generated_award_id, str) or not generated_award_id:
        return None
    return award_key, generated_award_id


def _validate_subaward_parent_bindings(payload: dict, prime_payload: dict) -> None:
    """Fail closed unless every subaward cites exactly one prime dossier row."""
    prime_by_generated = _prime_award_key_by_generated_id(prime_payload)
    envelopes: dict[str, str] = {}
    for envelope in payload.get("primes") or []:
        if not isinstance(envelope, dict):
            raise HTTPException(status_code=503, detail="government revenue subaward dossier schema mismatch")
        generated_award_id = envelope.get("parent_generated_award_id")
        award_key = envelope.get("award_key")
        if not isinstance(generated_award_id, str) or not generated_award_id or not isinstance(award_key, str) or not award_key:
            raise HTTPException(status_code=503, detail="government revenue subaward parent binding invalid")
        if generated_award_id in envelopes:
            raise HTTPException(status_code=503, detail="government revenue subaward parent binding ambiguous")
        if prime_by_generated.get(generated_award_id) != award_key:
            raise HTTPException(status_code=503, detail="government revenue subaward parent binding unresolved")
        envelopes[generated_award_id] = award_key
    if envelopes != prime_by_generated:
        raise HTTPException(status_code=503, detail="government revenue subaward parent coverage mismatch")
    for row in payload.get("subawards") or []:
        if not isinstance(row, dict):
            raise HTTPException(status_code=503, detail="government revenue subaward dossier schema mismatch")
        binding = _subaward_parent_binding(row)
        if binding is None:
            raise HTTPException(status_code=503, detail="government revenue subaward parent binding invalid")
        award_key, generated_award_id = binding
        if prime_by_generated.get(generated_award_id) != award_key:
            raise HTTPException(status_code=503, detail="government revenue subaward parent binding unresolved")


def _load_subaward_dossiers() -> dict:
    """Load one exact, precomputed subaward generation or fail closed.

    This cache is deliberately independent from the prime dossier cache.  The
    subaward artifact has its own content identity and twin boundary, but is
    admitted only when every stored parent pair matches the current prime
    dossier's exact generated-award-ID bridge.
    """
    canonical, site = _SUBAWARD_DOSSIER_PATHS
    # Read the prime dossier before deciding a subaward cache hit: a subaward
    # payload that survived while its prime parent generation changed is not a
    # valid bound rail.
    prime_payload = _load_dossiers()
    try:
        canonical_state = canonical.stat()
        site_state = site.stat()
    except OSError as exc:
        raise HTTPException(status_code=503, detail="government revenue subaward dossier artifact unavailable") from exc
    state = (
        canonical_state.st_mtime_ns,
        canonical_state.st_size,
        site_state.st_mtime_ns,
        site_state.st_size,
        prime_payload.get("content_id"),
    )
    with _LOCK:
        if (
            _SUBAWARD_DOSSIER_CACHE["payload"] is not None
            and _SUBAWARD_DOSSIER_CACHE["state"] == state
        ):
            return _SUBAWARD_DOSSIER_CACHE["payload"]
        try:
            canonical_bytes = canonical.read_bytes()
            site_bytes = site.read_bytes()
            payload = json.loads(canonical_bytes)
        except (OSError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=503, detail="government revenue subaward dossier artifact unreadable") from exc
        if canonical_bytes != site_bytes:
            raise HTTPException(status_code=503, detail="government revenue subaward dossier artifact twin mismatch")
        if (
            not isinstance(payload, dict)
            or payload.get("contract") != SUBAWARD_DOSSIER_CONTRACT
            or not is_valid_subaward_dossier_payload(payload)
            or subaward_dossier_content_id(payload) != payload.get("content_id")
        ):
            raise HTTPException(status_code=503, detail="government revenue subaward dossier artifact schema mismatch")
        _validate_subaward_parent_bindings(payload, prime_payload)
        _SUBAWARD_DOSSIER_CACHE.update(state=state, payload=payload)
        return payload


def _validate_budget_program_award_bindings(payload: dict, prime_payload: dict) -> None:
    """Keep reviewed documentary award links exact and non-attributional."""
    exact_award_keys = set(_prime_award_key_by_generated_id(prime_payload).values())
    for edge in payload.get("edges") or []:
        if not isinstance(edge, dict):
            raise HTTPException(status_code=503, detail="government revenue budget/program graph schema mismatch")
        if edge.get("to_type") == "award" and edge.get("to_id") not in exact_award_keys:
            raise HTTPException(status_code=503, detail="government revenue budget/program graph award binding unresolved")


def _load_budget_program_graph() -> dict:
    """Load one exact, precomputed DoD request-evidence graph or fail closed.

    This route family never reads PDFs, recomputes budget values, or creates a
    company/issuer conclusion.  An absent graph is an explicit unavailable
    optional rail; a one-sided/stale static twin is a 503.
    """
    prime_payload = _load_dossiers()
    canonical, site = _BUDGET_PROGRAM_PATHS
    try:
        canonical_state = canonical.stat()
        site_state = site.stat()
    except OSError as exc:
        raise HTTPException(status_code=503, detail="government revenue DoD budget/program graph unavailable") from exc
    state = (
        canonical_state.st_mtime_ns,
        canonical_state.st_size,
        site_state.st_mtime_ns,
        site_state.st_size,
        prime_payload.get("content_id"),
    )
    with _LOCK:
        if _BUDGET_PROGRAM_CACHE["payload"] is not None and _BUDGET_PROGRAM_CACHE["state"] == state:
            return _BUDGET_PROGRAM_CACHE["payload"]
        try:
            canonical_bytes = canonical.read_bytes()
            site_bytes = site.read_bytes()
            payload = json.loads(canonical_bytes)
        except (OSError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=503, detail="government revenue DoD budget/program graph unreadable") from exc
        if canonical_bytes != site_bytes:
            raise HTTPException(status_code=503, detail="government revenue DoD budget/program graph twin mismatch")
        if (
            not isinstance(payload, dict)
            or payload.get("contract") != BUDGET_PROGRAM_GRAPH_CONTRACT
            or not is_valid_budget_program_graph(payload)
        ):
            raise HTTPException(status_code=503, detail="government revenue DoD budget/program graph schema mismatch")
        _validate_budget_program_award_bindings(payload, prime_payload)
        _BUDGET_PROGRAM_CACHE.update(state=state, payload=payload)
        return payload


def _validate_idv_dossier_bindings(payload: dict, prime_payload: dict) -> None:
    """Require the stored child bridge to match this exact prime generation."""
    prime_by_generated = _prime_award_key_by_generated_id(prime_payload)
    for parent in payload.get("idvs") or []:
        if (
            not isinstance(parent, dict)
            or not str(parent.get("idv_generated_award_id") or "").startswith("CONT_IDV_")
            or "award_key" in parent
            or "parent_award_key" in parent
        ):
            raise HTTPException(status_code=503, detail="government revenue IDV parent binding invalid")
    for relationship in payload.get("relationships") or []:
        identity = relationship.get("identity") if isinstance(relationship, dict) else None
        if not isinstance(identity, dict):
            raise HTTPException(status_code=503, detail="government revenue IDV relationship identity invalid")
        parent = identity.get("idv_generated_award_id")
        child = identity.get("child_generated_award_id")
        if (
            not isinstance(parent, str)
            or not parent.startswith("CONT_IDV_")
            or not isinstance(child, str)
            or not child.startswith("CONT_AWD_")
        ):
            raise HTTPException(status_code=503, detail="government revenue IDV relationship identity invalid")
        if relationship.get("child_award_key") != prime_by_generated.get(child):
            raise HTTPException(status_code=503, detail="government revenue IDV child bridge unresolved")
        if "parent_award_key" in relationship:
            raise HTTPException(status_code=503, detail="government revenue IDV parent bridge invalid")


def _load_idv_dossiers() -> dict:
    """Load one independent source-native IDV generation or fail closed."""
    prime_payload = _load_dossiers()
    canonical, site = _IDV_DOSSIER_PATHS
    try:
        canonical_state = canonical.stat()
        site_state = site.stat()
    except OSError as exc:
        raise HTTPException(status_code=503, detail="government revenue IDV dossier unavailable") from exc
    state = (
        canonical_state.st_mtime_ns,
        canonical_state.st_size,
        site_state.st_mtime_ns,
        site_state.st_size,
        prime_payload.get("content_id"),
    )
    with _LOCK:
        if _IDV_DOSSIER_CACHE["payload"] is not None and _IDV_DOSSIER_CACHE["state"] == state:
            return _IDV_DOSSIER_CACHE["payload"]
        try:
            canonical_bytes = canonical.read_bytes()
            site_bytes = site.read_bytes()
            payload = json.loads(canonical_bytes)
        except (OSError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=503, detail="government revenue IDV dossier unreadable") from exc
        if canonical_bytes != site_bytes:
            raise HTTPException(status_code=503, detail="government revenue IDV dossier twin mismatch")
        if (
            not isinstance(payload, dict)
            or payload.get("contract") != IDV_DOSSIER_CONTRACT
            or not is_valid_idv_dossier_payload(payload)
            or idv_dossier_content_id(payload) != payload.get("content_id")
        ):
            raise HTTPException(status_code=503, detail="government revenue IDV dossier schema mismatch")
        _validate_idv_dossier_bindings(payload, prime_payload)
        _IDV_DOSSIER_CACHE.update(state=state, payload=payload)
        return payload


def _award_idv_bridge(prime_payload: dict, idv_payload: dict, award_key: str) -> dict:
    """Project one award's exact IDV bridge from two already-validated rails.

    The bridge is a deterministic display-tier join over content-addressed
    bytes, so it is cached on the joint identity of its two inputs rather than
    stored as a separate artifact.  This is an optional context rail on top of
    the receipt-bound relationship route: a projection that cannot be built
    returns an explicit unavailable state so the proven relationships keep
    serving, and so a reader never mistakes "not checked" for "no link".
    """
    state = (prime_payload.get("content_id"), idv_payload.get("content_id"))
    with _LOCK:
        payload = _IDV_BRIDGE_CACHE["payload"] if _IDV_BRIDGE_CACHE["state"] == state else None
        if payload is None:
            try:
                payload = build_idv_bridge_payload(
                    idv_payload=idv_payload,
                    prime_payload=prime_payload,
                    as_of=prime_payload.get("as_of"),
                )
            except (ValueError, TypeError, KeyError):
                return unavailable_award_bridge_view(
                    award_key,
                    "The exact vehicle bridge could not be projected from this generation, so no link was "
                    "checked. That is not an observation that no link exists.",
                )
            _IDV_BRIDGE_CACHE.update(state=state, payload=payload)
        return award_bridge_view(payload, award_key)


def _candidate_authority_is_display_only(value: object) -> bool:
    return value == {
        "tier": "display",
        "context_only": True,
        "can_rank": False,
        "can_size": False,
        "can_gate": False,
        "can_originate_signal": False,
        "can_add_candidates": False,
        "can_escalate": False,
    }


def _candidate_projection_state(
    paths: tuple[Path, ...],
    *,
    content_sha_paths: frozenset[Path] = frozenset(),
) -> tuple:
    state: list[tuple[str, int, int, str | None]] = []
    for path in paths:
        try:
            before = path.stat()
            if path in content_sha_paths:
                raw = path.read_bytes()
                after = path.stat()
            else:
                raw = None
                after = before
        except OSError as exc:
            raise HTTPException(
                status_code=503,
                detail="government revenue candidate projection unavailable",
            ) from exc
        if (
            before.st_mtime_ns != after.st_mtime_ns
            or before.st_size != after.st_size
            or (raw is not None and len(raw) != after.st_size)
        ):
            raise HTTPException(
                status_code=503,
                detail="government revenue candidate projection changed while loading",
            )
        state.append(
            (
                str(path),
                after.st_mtime_ns,
                after.st_size,
                hashlib.sha256(raw).hexdigest() if raw is not None else None,
            )
        )
    return tuple(state)


def _candidate_review_config_paths() -> tuple[Path, ...]:
    """Bind both reviewed manifests and schemas into every relevant cache key."""
    paths: list[Path] = []
    for required, manifest, schema in (
        (
            _CANDIDATE_SUPPRESSION_REQUIRED,
            _CANDIDATE_SUPPRESSION_MANIFEST_PATH,
            _CANDIDATE_SUPPRESSION_SCHEMA_PATH,
        ),
        (
            _CANDIDATE_CORRECTION_REQUIRED,
            _CANDIDATE_CORRECTION_MANIFEST_PATH,
            _CANDIDATE_CORRECTION_SCHEMA_PATH,
        ),
    ):
        # Optional historical test roots may predate these rails.  Once either
        # half appears, bind both halves and fail closed on an incomplete pair.
        if required or manifest.exists() or schema.exists():
            paths.extend((manifest, schema))
    return tuple(paths)


def _candidate_projection_json(path: Path, *, label: str) -> tuple[bytes, dict]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"government revenue candidate {label} unreadable",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=503,
            detail=f"government revenue candidate {label} malformed",
        )
    return raw, payload


def _candidate_ledger_rows(raw: bytes) -> list[dict]:
    if not raw:
        return []
    if raw and not raw.endswith(b"\n"):
        raise HTTPException(
            status_code=503,
            detail="government revenue candidate ledger is not append-safe",
        )
    if b"\r" in raw:
        raise HTTPException(
            status_code=503,
            detail="government revenue candidate ledger is not canonical",
        )
    lines = raw[:-1].split(b"\n")
    if not lines or any(not line for line in lines):
        raise HTTPException(
            status_code=503,
            detail="government revenue candidate ledger is not canonical",
        )
    rows: list[dict] = []
    observation_ids: set[str] = set()
    observation_keys: set[tuple] = set()
    for line in lines:
        try:
            row = json.loads(line.decode("utf-8"))
            canonical = json.dumps(
                row,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (UnicodeDecodeError, ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=503,
                detail="government revenue candidate ledger unreadable",
            ) from exc
        if (
            not isinstance(row, dict)
            or row.get("contract") != CANDIDATE_CONTRACT
            or not is_valid_candidate_payload(row)
        ):
            raise HTTPException(
                status_code=503,
                detail="government revenue candidate ledger schema mismatch",
            )
        if line != canonical:
            raise HTTPException(
                status_code=503,
                detail="government revenue candidate ledger is not canonical",
            )
        observation_id = row.get("observation_id")
        if observation_id in observation_ids:
            raise HTTPException(
                status_code=503,
                detail="government revenue candidate ledger contains duplicate observations",
            )
        observation_ids.add(observation_id)
        # One row per hypothesis per moment it was knowable.  `observation_id`
        # additionally folds in the reviewed-graph digest, so it moves on every
        # curation edit; this pair is what the writer treats as already recorded.
        observation_key = (row.get("candidate_id"), row.get("known_at"))
        if observation_key in observation_keys:
            raise HTTPException(
                status_code=503,
                detail="government revenue candidate ledger contains duplicate observations",
            )
        observation_keys.add(observation_key)
        rows.append(row)
    return rows


def _load_candidate_projection() -> dict:
    """Load one fully bound queue/ledger generation or fail closed.

    A legitimate zero-candidate projection is a normal success.  Missing twins,
    mixed publication generations, ledger mutation, or a trusted content-ID
    mismatch is unavailable rather than an invented empty result.
    """
    canonical, public = _CANDIDATE_QUEUE_PATHS
    review_config_paths = _candidate_review_config_paths()
    paths = (
        canonical,
        public,
        _CANDIDATE_LEDGER_PATH,
        _CANDIDATE_STATE_PATH,
        _CANDIDATE_STATUS_PATH,
        *_CANDIDATE_SOURCE_PATHS,
        *review_config_paths,
    )
    state_key = _candidate_projection_state(
        paths,
        content_sha_paths=frozenset(review_config_paths),
    )
    with _LOCK:
        if _CANDIDATE_CACHE["payload"] is not None and _CANDIDATE_CACHE["state"] == state_key:
            return _CANDIDATE_CACHE["payload"]

        canonical_raw, queue = _candidate_projection_json(canonical, label="queue")
        public_raw, _public_queue = _candidate_projection_json(public, label="public twin")
        state_raw, projection_state = _candidate_projection_json(
            _CANDIDATE_STATE_PATH,
            label="projection state",
        )
        _status_raw, projection_status = _candidate_projection_json(
            _CANDIDATE_STATUS_PATH,
            label="projection status",
        )
        _latest_raw, latest = _candidate_projection_json(
            _CANDIDATE_SOURCE_PATHS[0],
            label="source latest",
        )
        _workspace_raw, workspace = _candidate_projection_json(
            _CANDIDATE_SOURCE_PATHS[1],
            label="source workspace",
        )
        _graph_raw, recipient_graph = _candidate_projection_json(
            _CANDIDATE_SOURCE_PATHS[2],
            label="recipient graph",
        )
        try:
            ledger_raw = _CANDIDATE_LEDGER_PATH.read_bytes()
        except OSError as exc:
            raise HTTPException(
                status_code=503,
                detail="government revenue candidate ledger unavailable",
            ) from exc

        if canonical_raw != public_raw:
            raise HTTPException(
                status_code=503,
                detail="government revenue candidate queue twin mismatch",
            )
        if (
            queue.get("contract") != CANDIDATE_QUEUE_CONTRACT
            or not is_valid_candidate_queue(queue)
            or candidate_queue_content_id(queue) != queue.get("content_id")
        ):
            raise HTTPException(
                status_code=503,
                detail="government revenue candidate queue schema mismatch",
            )

        rows = _candidate_ledger_rows(ledger_raw)
        ledger_sha256 = hashlib.sha256(ledger_raw).hexdigest()
        ledger_binding = projection_state.get("ledger")
        if (
            projection_state.get("contract") != "government_revenue.candidate_projection_state.v1"
            or projection_state.get("schema_version") != "1.0.0"
            or not isinstance(ledger_binding, dict)
            or ledger_binding.get("sha256") != ledger_sha256
            or ledger_binding.get("byte_count") != len(ledger_raw)
            or ledger_binding.get("line_count") != len(rows)
            or not isinstance(ledger_binding.get("prior_line_count"), int)
            or isinstance(ledger_binding.get("prior_line_count"), bool)
            or not 0 <= ledger_binding["prior_line_count"] <= len(rows)
            or projection_state.get("queue_content_id") != queue.get("content_id")
        ):
            raise HTTPException(
                status_code=503,
                detail="government revenue candidate projection state mismatch",
            )
        if (
            projection_status.get("contract") != "government_revenue.candidate_projection_status.v1"
            or projection_status.get("schema_version") != "1.0.0"
            or projection_status.get("status") != "ok"
            or projection_status.get("queue_content_id") != queue.get("content_id")
            or projection_status.get("ledger_sha256") != ledger_sha256
            or projection_status.get("ledger_byte_count") != len(ledger_raw)
            or projection_status.get("ledger_line_count") != len(rows)
            or projection_status.get("candidate_count") != len(queue.get("candidates") or [])
            or projection_status.get("mapping_backlog_count") != len(queue.get("mapping_backlog") or [])
            or projection_status.get("latest_sha256") != projection_state.get("latest_sha256")
            or not _candidate_authority_is_display_only(projection_status.get("authority"))
        ):
            raise HTTPException(
                status_code=503,
                detail="government revenue candidate projection status mismatch",
            )
        for clock in ("as_of", "known_at", "generated_at"):
            if (
                projection_state.get(clock) != queue.get(clock)
                or projection_status.get(clock) != queue.get(clock)
            ):
                raise HTTPException(
                    status_code=503,
                    detail="government revenue candidate projection clock mismatch",
                )

        embedded_workspace = latest.get("procurement_workspace")
        workspace_semantic = {
            key: value for key, value in workspace.items() if key != "generated_at"
        }
        workspace_sha256 = hashlib.sha256(
            json.dumps(
                workspace_semantic,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        latest_sha256 = candidate_latest_semantic_sha256(latest)
        loaded_graph = load_recipient_entity_graph(
            recipient_graph,
            as_of=queue.get("as_of"),
        )
        if (
            not isinstance(embedded_workspace, dict)
            or json.dumps(embedded_workspace, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            != json.dumps(workspace, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            or projection_state.get("workspace_bundle_id") != workspace.get("bundle_id")
            or projection_status.get("workspace_bundle_id") != workspace.get("bundle_id")
            or projection_state.get("workspace_sha256") != workspace_sha256
            or projection_state.get("latest_sha256") != latest_sha256
            or loaded_graph.get("status") != "ready"
            or projection_state.get("recipient_graph_id") != loaded_graph.get("graph_id")
            or projection_status.get("recipient_graph_id") != loaded_graph.get("graph_id")
            or projection_state.get("recipient_graph_digest") != loaded_graph.get("graph_digest")
            or projection_status.get("recipient_graph_digest") != loaded_graph.get("graph_digest")
        ):
            raise HTTPException(
                status_code=503,
                detail="government revenue candidate source generation mismatch",
            )
        try:
            current_observations = build_candidate_observations(
                latest,
                recipient_graph,
                generated_at=queue.get("generated_at"),
            )
            if not isinstance(current_observations, list):
                raise ValueError("candidate source observations are invalid")
            reviewed_history_binding = validate_candidate_reviewed_history_binding(
                queue,
                projection_state,
                root=_CANDIDATE_REPO_ROOT,
                allow_exact_legacy_predecessor=True,
                allow_exact_incident_predecessor=False,
                current_observations=current_observations,
                issued_observations=rows,
                require_manifest=(
                    _CANDIDATE_SUPPRESSION_REQUIRED
                    or _CANDIDATE_CORRECTION_REQUIRED
                ),
                queue_raw_sha256=hashlib.sha256(canonical_raw).hexdigest(),
                projection_state_raw_sha256=hashlib.sha256(state_raw).hexdigest(),
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=503,
                detail="government revenue candidate reviewed-history binding mismatch",
            ) from exc

        # The ledger is keyed on graph-independent observation identity.  A
        # reviewed-graph edit mints a new `observation_id` for a candidate that is
        # already recorded, so keying the served rows on it would unbind the whole
        # queue after any curation increment.  Rows the last generation did not
        # append keep the graph generation they were recorded under; everything
        # newer is bound to today's.
        ledger_observations = {
            (row.get("candidate_id"), row.get("known_at")): row for row in rows
        }
        issued_earlier = {
            row.get("observation_id")
            for row in rows[: ledger_binding["prior_line_count"]]
        }
        projected = list(queue.get("candidates") or []) + list(queue.get("recently_matured") or [])
        required_source_content_ids = {
            f"latest-sha256:{latest_sha256}",
            f"graph-sha256:{loaded_graph.get('graph_digest')}",
            workspace.get("bundle_id"),
        }
        if any(
            (row.get("candidate_id"), row.get("known_at")) not in ledger_observations
            or json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            != json.dumps(
                ledger_observations[(row.get("candidate_id"), row.get("known_at"))],
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            or not isinstance(row.get("issuer_resolution_ref"), dict)
            or f"graph-sha256:{row['issuer_resolution_ref'].get('graph_digest')}"
            not in (row.get("artifact_content_ids") or [])
            or (
                row.get("observation_id") not in issued_earlier
                and (
                    row["issuer_resolution_ref"].get("graph_id") != loaded_graph.get("graph_id")
                    or row["issuer_resolution_ref"].get("graph_digest") != loaded_graph.get("graph_digest")
                )
            )
            for row in projected
        ):
            raise HTTPException(
                status_code=503,
                detail="government revenue candidate queue is not ledger bound",
            )
        if (
            not isinstance(queue.get("source_content_ids"), list)
            or not required_source_content_ids.issubset(set(queue["source_content_ids"]))
            or any(
                not isinstance(row, dict)
                or f"latest-sha256:{latest_sha256}" not in (row.get("source_artifact_content_ids") or [])
                or f"graph-sha256:{loaded_graph.get('graph_digest')}" not in (row.get("source_artifact_content_ids") or [])
                for row in queue.get("mapping_backlog") or []
            )
        ):
            raise HTTPException(
                status_code=503,
                detail="government revenue candidate queue source binding mismatch",
            )
        counts = queue.get("counts") if isinstance(queue.get("counts"), dict) else {}
        if (
            counts.get("total") != len(queue.get("candidates") or [])
            or counts.get("exact_linked") != len(queue.get("candidates") or [])
            or counts.get("mapping_needed") != len(queue.get("mapping_backlog") or [])
        ):
            raise HTTPException(
                status_code=503,
                detail="government revenue candidate queue count mismatch",
            )

        loaded = {
            "queue": queue,
            "ledger": rows,
            "projection_state": projection_state,
            "projection_status": projection_status,
            "reviewed_history_binding": reviewed_history_binding,
        }
        _CANDIDATE_CACHE.update(state=state_key, payload=loaded)
        return loaded


def _load() -> dict:
    path = _artifact_path()
    if path is None:
        raise HTTPException(status_code=503, detail="government revenue artifact unavailable")
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError as exc:
        raise HTTPException(status_code=503, detail="government revenue artifact unavailable") from exc
    with _LOCK:
        if (
            _CACHE["payload"] is not None
            and _CACHE["path"] == str(path)
            and _CACHE["mtime_ns"] == mtime_ns
        ):
            return _CACHE["payload"]
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=503, detail="government revenue artifact unreadable") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != "company_government_revenue.v1":
            raise HTTPException(status_code=503, detail="government revenue artifact schema mismatch")
        workspace = payload.get("procurement_workspace")
        if (
            isinstance(workspace, dict)
            and workspace.get("schema_version") == "government_procurement_workspace.v2"
            and not is_valid_procurement_workspace(workspace)
        ):
            raise HTTPException(
                status_code=503,
                detail="government procurement workspace contract mismatch",
            )
        _CACHE.update(path=str(path), mtime_ns=mtime_ns, payload=payload)
        return payload


def _public_company(row: dict) -> dict:
    """Return the already-public compact row; never expose collector receipts."""
    allowed = {
        "ticker", "name", "entity_match", "metrics", "monthly_obligations",
        "recompete_candidates", "catalyst_facts", "confidence", "provenance",
        "awards", "recent_actions", "tags", "authority", "opportunity_candidates",
    }
    return _scrub_public({key: row[key] for key in allowed if key in row})


def _opportunity_intelligence(payload: dict) -> dict:
    value = payload.get("opportunity_intelligence")
    return value if isinstance(value, dict) else {}


def _procurement_workspace(payload: dict) -> dict:
    value = payload.get("procurement_workspace")
    if not isinstance(value, dict) or value.get("schema_version") not in {
        "government_procurement_workspace.v1",
        "government_procurement_workspace.v2",
    }:
        raise HTTPException(status_code=503, detail="government procurement workspace unavailable")
    return value


def _public_workspace_event(row: dict) -> dict:
    allowed = {
        "contract", "event_id", "record_id", "version", "kind", "state",
        "title_original", "title_zh", "translation_status", "agency", "change",
        "opportunity", "recompete", "award_change", "dates", "amounts", "primary_date_id",
        "primary_amount_id", "listed_company_impacts", "primary_ticker",
        "display_priority", "evidence", "authority",
    }
    return _scrub_public({key: row[key] for key in allowed if key in row})


def _workspace_cursor_version(workspace: dict) -> str:
    return "v2" if workspace.get("schema_version") == "government_procurement_workspace.v2" else "v1"


def _encode_cursor(offset: int, *, version: str = "v1") -> str:
    if version not in {"v1", "v2"}:
        raise ValueError("unsupported cursor version")
    return base64.urlsafe_b64encode(f"{version}:{offset}".encode("ascii")).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None, *, expected_version: str = "v1") -> int:
    if not cursor:
        return 0
    if len(cursor) > 32 or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor):
        raise HTTPException(status_code=400, detail="invalid cursor")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii")
        version, offset = raw.split(":", 1)
        value = int(offset)
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    if version != expected_version or value < 0 or value > 10_000:
        raise HTTPException(status_code=400, detail="invalid cursor")
    return value


def _public_opportunity(row: dict) -> dict:
    """Expose normalized official evidence and bounded derived context only."""
    allowed = {
        "contract", "notice_id", "solicitation_number", "revision_id", "title",
        "description", "notice_type", "base_type", "status", "agency", "office",
        "organization_code", "naics_code", "psc_code", "set_aside", "posted_at",
        "response_deadline", "archive_date", "place_of_performance", "resource_links",
        "known_at", "effective_at", "source_url", "tags", "documents",
        "days_to_response", "defense_relevant", "company_candidates", "authority",
        "current_state", "observation_horizon_at", "observation_age_minutes",
        "observation_basis", "current_state_reason",
    }
    return _scrub_public({key: row[key] for key in allowed if key in row})


def _public_opportunity_event(row: dict) -> dict:
    allowed = {
        "contract", "event_id", "event_type", "version", "notice_id", "revision_id",
        "title", "known_at", "effective_at", "first_seen_at", "changed_fields",
        "changed_values", "source_refs", "evidence_class", "confidence_state", "authority",
    }
    event = {key: row[key] for key in allowed if key in row}
    snapshot = row.get("record_snapshot")
    if isinstance(snapshot, dict):
        event["record_snapshot"] = _public_opportunity(snapshot)
    return _scrub_public(event)


def _validated_ticker(value: str | None) -> str | None:
    if value is None:
        return None
    ticker = value.strip().upper()
    if not _TICKER.fullmatch(ticker):
        raise HTTPException(status_code=400, detail="invalid ticker")
    return ticker


def _validated_award_key(value: str) -> str:
    if not _AWARD_KEY.fullmatch(value):
        raise HTTPException(status_code=400, detail="invalid award key")
    return value


def _validated_subaward_key(value: str) -> str:
    if not _SUBAWARD_KEY.fullmatch(value):
        raise HTTPException(status_code=400, detail="invalid subaward key")
    return value


def _validated_budget_line_key(value: str) -> str:
    if not _BUDGET_LINE_KEY.fullmatch(value):
        raise HTTPException(status_code=400, detail="invalid budget line key")
    return value


def _validated_budget_program_key(value: str) -> str:
    if not _BUDGET_PROGRAM_KEY.fullmatch(value):
        raise HTTPException(status_code=400, detail="invalid budget program key")
    return value


def _validated_action_date(value: str | None, *, label: str) -> str | None:
    if value is None:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise HTTPException(status_code=400, detail=f"invalid {label}")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid {label}") from exc
    return value


def _dossier_cursor_binding(scope: dict) -> str:
    """Bind opaque cursors to the exact artifact, route, and stored-field filters."""
    raw = json.dumps(scope, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _encode_dossier_cursor(offset: int, *, content_id: str, binding: str) -> str:
    if offset < 0 or offset > 50_000:
        raise ValueError("invalid dossier cursor offset")
    raw = f"d1:{content_id}:{binding}:{offset}"
    return base64.urlsafe_b64encode(raw.encode("ascii")).decode("ascii").rstrip("=")


def _decode_dossier_cursor(cursor: str | None, *, content_id: str, binding: str) -> int:
    if not cursor:
        return 0
    if len(cursor) > 180 or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor):
        raise HTTPException(status_code=400, detail="invalid dossier cursor")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii")
        version, cursor_content, cursor_binding, offset = raw.split(":", 3)
        value = int(offset)
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="invalid dossier cursor") from exc
    if (
        version != "d1"
        or cursor_content != content_id
        or cursor_binding != binding
        or value < 0
        or value > 50_000
    ):
        raise HTTPException(status_code=400, detail="invalid dossier cursor")
    return value


def _encode_subaward_cursor(offset: int, *, content_id: str, binding: str) -> str:
    """Emit an opaque cursor bound to one immutable subaward generation."""
    if offset < 0 or offset > 50_000:
        raise ValueError("invalid subaward cursor offset")
    raw = f"sd1:{content_id}:{binding}:{offset}"
    return base64.urlsafe_b64encode(raw.encode("ascii")).decode("ascii").rstrip("=")


def _decode_subaward_cursor(
    cursor: str | None,
    *,
    content_id: str,
    binding: str,
) -> int:
    if not cursor:
        return 0
    if len(cursor) > 200 or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor):
        raise HTTPException(status_code=400, detail="invalid subaward cursor")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii")
        version, cursor_content, cursor_binding, offset = raw.split(":", 3)
        value = int(offset)
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="invalid subaward cursor") from exc
    if (
        version != "sd1"
        or cursor_content != content_id
        or cursor_binding != binding
        or value < 0
        or value > 50_000
    ):
        raise HTTPException(status_code=400, detail="invalid subaward cursor")
    return value


def _validated_candidate_id(value: str) -> str:
    if not _CANDIDATE_ID.fullmatch(value):
        raise HTTPException(status_code=400, detail="invalid candidate id")
    return value


def _encode_candidate_cursor(offset: int, *, content_id: str, binding: str) -> str:
    if offset < 0 or offset > 50_000:
        raise ValueError("invalid candidate cursor offset")
    raw = f"cq1:{content_id}:{binding}:{offset}"
    return base64.urlsafe_b64encode(raw.encode("ascii")).decode("ascii").rstrip("=")


def _decode_candidate_cursor(
    cursor: str | None,
    *,
    content_id: str,
    binding: str,
) -> int:
    if not cursor:
        return 0
    if len(cursor) > 200 or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor):
        raise HTTPException(status_code=400, detail="invalid candidate cursor")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii")
        version, cursor_content, cursor_binding, offset = raw.split(":", 3)
        value = int(offset)
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="invalid candidate cursor") from exc
    if (
        version != "cq1"
        or cursor_content != content_id
        or cursor_binding != binding
        or value < 0
        or value > 50_000
    ):
        raise HTTPException(status_code=400, detail="invalid candidate cursor")
    return value


def _public_candidate(row: dict) -> dict:
    """Expose the complete bounded research record plus plain UI summaries."""
    public = _scrub_public(row)
    if not isinstance(public, dict):
        raise HTTPException(status_code=503, detail="government revenue candidate malformed")
    mechanism = row.get("mechanism") if isinstance(row.get("mechanism"), dict) else {}
    public["observed_change"] = _scrub_public(mechanism.get("observed_change"))
    return public


def _candidate_correction_receipt(queue: dict) -> dict | None:
    coverage = queue.get("coverage")
    receipt = (
        coverage.get("historical_candidate_issuance_correction")
        if isinstance(coverage, dict)
        else None
    )
    if (
        not isinstance(receipt, dict)
        or receipt.get("contract") != ISSUANCE_CORRECTION_APPLICATION_CONTRACT
        or not isinstance(receipt.get("entries"), list)
    ):
        return None
    return receipt


def _candidate_correction_entry(queue: dict, row: dict) -> dict | None:
    """Match one corrected observation, never a whole candidate identity."""
    receipt = _candidate_correction_receipt(queue)
    if receipt is None:
        return None
    candidate_id = row.get("candidate_id")
    observation_id = row.get("observation_id")
    matches = [
        entry
        for entry in receipt["entries"]
        if isinstance(entry, dict)
        and entry.get("candidate_id") == candidate_id
        and entry.get("observation_id") == observation_id
    ]
    return matches[0] if len(matches) == 1 else None


def _candidate_correction_ref(queue: dict, entry: dict) -> dict:
    receipt = _candidate_correction_receipt(queue) or {}
    activation = receipt.get("activation")
    return {
        "contract": receipt.get("contract"),
        "manifest_sha256": receipt.get("manifest_sha256"),
        "incident_id": receipt.get("incident_id"),
        "activation_id": (
            activation.get("activation_id") if isinstance(activation, dict) else None
        ),
        "candidate_id": entry.get("candidate_id"),
        "observation_id": entry.get("observation_id"),
    }


def _public_candidate_history_row(queue: dict, row: dict) -> dict:
    public = _public_candidate(row)
    correction = _candidate_correction_entry(queue, row)
    if correction is not None:
        public["publication_state"] = "quarantined_historical_issuance"
        public["correction_ref"] = _candidate_correction_ref(queue, correction)
    return public


def _candidate_envelope(
    queue: dict,
    *,
    items: list[dict],
    total: int,
    next_cursor: str | None,
) -> dict:
    return _scrub_public({
        "contract": queue.get("contract"),
        "schema_version": queue.get("schema_version"),
        "content_id": queue.get("content_id"),
        "as_of": queue.get("as_of"),
        "known_at": queue.get("known_at"),
        "generated_at": queue.get("generated_at"),
        "total": total,
        "items": items,
        "next_cursor": next_cursor,
        "mapping_backlog_total": len(queue.get("mapping_backlog") or []),
        "counts": queue.get("counts"),
        "coverage": queue.get("coverage"),
        "freshness": queue.get("freshness"),
        "display_sort": queue.get("display_sort"),
        "authority": queue.get("authority"),
        "limitations": queue.get("limitations"),
    })


def _candidate_rows_for_queue(queue: dict) -> list[dict]:
    rows = [
        row
        for row in queue.get("candidates") or []
        if isinstance(row, dict) and _candidate_correction_entry(queue, row) is None
    ]
    rows.sort(key=lambda row: str(row.get("candidate_id") or ""))
    rows.sort(key=lambda row: str(row.get("known_at") or ""), reverse=True)
    return rows


def _dossier_company_map(payload: dict) -> dict[str, dict]:
    return {
        row["ticker"]: row
        for row in payload.get("companies") or []
        if isinstance(row, dict) and isinstance(row.get("ticker"), str)
    }


def _dossier_award_map(payload: dict) -> dict[str, dict]:
    return {
        row["award_key"]: row
        for row in payload.get("awards") or []
        if isinstance(row, dict) and isinstance(row.get("award_key"), str)
    }


def _dossier_action_map(payload: dict) -> dict[str, dict]:
    return {
        row["action_key"]: row
        for row in payload.get("actions") or []
        if isinstance(row, dict) and isinstance(row.get("action_key"), str)
    }


def _public_dossier_company(row: dict) -> dict:
    allowed = {
        "ticker", "name", "collection_scope", "award_count", "action_count", "known_at",
    }
    return _scrub_public({key: row[key] for key in allowed if key in row})


def _public_dossier_award(row: dict) -> dict:
    """Strict projection: only schema-listed public fields, never raw receipts."""
    allowed = {
        "award_key", "identity", "record_origin", "collection_scope_tickers", "recipient",
        "description", "agency", "classifications", "dates", "values", "provenance", "action_count",
    }
    out = {key: row[key] for key in allowed if key in row}
    source = row.get("source")
    if isinstance(source, dict):
        out["source"] = {
            "publisher": "USAspending.gov",
            "award_search_url": _dossier_source_url(source.get("award_search_url")),
            "award_detail_url": _dossier_source_url(source.get("award_detail_url")),
            "award_page_url": _dossier_source_url(source.get("award_page_url")),
            "action_history_url": _dossier_source_url(source.get("action_history_url")),
        }
    return _scrub_public(out)


def _public_dossier_action(row: dict) -> dict:
    allowed = {
        "action_key", "action_id", "award_key", "modification_number", "action_type",
        "action_type_description", "description", "action_date", "effective_at", "known_at",
        "first_seen_at", "obligation",
    }
    out = {key: row[key] for key in allowed if key in row}
    source = row.get("source")
    if isinstance(source, dict):
        out["source"] = {
            "publisher": "USAspending.gov",
            "transaction_url": _dossier_source_url(source.get("transaction_url")),
            "award_page_url": _dossier_source_url(source.get("award_page_url")),
            "native_action_id": bool(source.get("native_action_id") is True),
        }
    return _scrub_public(out)


def _subaward_map(payload: dict) -> dict[str, dict]:
    return {
        row["subaward_key"]: row
        for row in payload.get("subawards") or []
        if isinstance(row, dict) and isinstance(row.get("subaward_key"), str)
    }


def _subaward_parent_coverage(payload: dict, award_key: str) -> dict:
    matches = [
        row
        for row in payload.get("primes") or []
        if isinstance(row, dict) and row.get("award_key") == award_key
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("coverage"), dict):
        raise HTTPException(
            status_code=503,
            detail="government revenue subaward parent coverage unavailable",
        )
    return matches[0]["coverage"]


def _public_subaward(row: dict) -> dict:
    """Expose only stored public subaward evidence, never source receipts."""
    allowed = {
        "subaward_key", "parent_award_key", "identity", "subawardee_name",
        "subaward_type", "description", "description_truncated", "dates",
        "reported_amount", "source", "provenance",
    }
    out = {key: row[key] for key in allowed if key in row}
    source = row.get("source")
    if isinstance(source, dict):
        out["source"] = {
            "publisher": "USAspending.gov",
            "subaward_url": _dossier_source_url(source.get("subaward_url")),
            "parent_award_url": _dossier_source_url(source.get("parent_award_url")),
        }
    return _scrub_public(out)


def _public_budget_graph_envelope(payload: dict) -> dict:
    """Expose stored DoD request evidence without a funding or issuer claim."""
    documents = []
    for raw in payload.get("documents") or []:
        if not isinstance(raw, dict):
            continue
        document = {
            key: raw[key]
            for key in (
                "receipt_id", "fiscal_year", "exhibit", "content_sha256", "page_count",
                "page_text_sha256s", "extraction_semantic_sha256", "extractor_version",
                "parser_version", "observed_at",
            )
            if key in raw
        }
        document["source_url"] = _dod_budget_source_url(raw.get("source_url"))
        documents.append(document)
    return _scrub_public({
        "contract": payload.get("contract"),
        "schema_version": payload.get("schema_version"),
        "content_id": payload.get("content_id"),
        "as_of": payload.get("as_of"),
        "known_at": payload.get("known_at"),
        "authority": payload.get("authority"),
        "source_coverage": payload.get("source_coverage"),
        "documents": documents,
        "limitations": payload.get("limitations"),
    })


def _public_budget_line(row: dict) -> dict:
    """Return a retained source line exactly as precomputed by the graph rail."""
    allowed = {
        "contract", "line_key", "line_family_key", "fiscal_year", "document_stage",
        "exhibit", "component", "appropriation", "appropriation_code",
        "budget_activity", "native_identifier", "program_name", "amounts", "quantities",
        "source", "provenance", "line_state_sha256", "effective_at", "known_at",
        "first_seen_at",
    }
    out = {key: row[key] for key in allowed if key in row}
    source = row.get("source")
    if isinstance(source, dict):
        out["source"] = {
            "publisher": "Office of the Under Secretary of Defense (Comptroller)",
            "source_url": _dod_budget_source_url(source.get("source_url")),
            "document_sha256": source.get("document_sha256"),
            "receipt_id": source.get("receipt_id"),
        }
    return _scrub_public(out)


def _public_budget_program(row: dict) -> dict:
    allowed = {"program_key", "kind", "native_identifier", "name", "line_keys"}
    return _scrub_public({key: row[key] for key in allowed if key in row})


def _public_budget_edge(row: dict) -> dict:
    allowed = {
        "contract", "edge_id", "from_type", "from_id", "to_type", "to_id",
        "edge_type", "review_state", "economic_weight", "effective_at", "known_at",
        "evidence",
    }
    return _scrub_public({key: row[key] for key in allowed if key in row})


def _public_idv_relationship(row: dict) -> dict:
    """Expose an official relationship observation, never an issuer assertion."""
    allowed = {
        "relationship_key", "child_award_key", "identity", "recipient_name", "agency",
        "dates", "amounts", "source", "provenance",
    }
    out = {key: row[key] for key in allowed if key in row}
    source = row.get("source")
    if isinstance(source, dict):
        out["source"] = {
            "publisher": "USAspending.gov",
            "activity_url": _dossier_source_url(source.get("activity_url")),
        }
    return _scrub_public(out)


def _dossier_envelope(payload: dict, *, results: list[dict], next_cursor: str | None, total: int) -> dict:
    return _scrub_public({
        "schema_version": payload.get("schema_version"),
        "content_id": payload.get("content_id"),
        "as_of": payload.get("as_of"),
        "known_at": payload.get("known_at"),
        "source_coverage": payload.get("source_coverage"),
        "freshness": payload.get("freshness"),
        "results": results,
        "next_cursor": next_cursor,
        "total": total,
    })


def _subaward_dossier_envelope(
    payload: dict,
    *,
    results: list[dict],
    next_cursor: str | None,
    total: int,
    parent_coverage: dict,
) -> dict:
    """Return a precomputed-only subaward page with explicit coverage state."""
    return _scrub_public({
        "schema_version": payload.get("schema_version"),
        "content_id": payload.get("content_id"),
        "as_of": payload.get("as_of"),
        "known_at": payload.get("known_at"),
        "authority": payload.get("authority"),
        "source_coverage": payload.get("source_coverage"),
        "freshness": payload.get("freshness"),
        "parent_coverage": parent_coverage,
        "limitations": payload.get("limitations"),
        "results": results,
        "next_cursor": next_cursor,
        "total": total,
    })


def _official_award_text(row: dict) -> str:
    """The query corpus intentionally excludes discovery tickers and company names."""
    identity = row.get("identity") if isinstance(row.get("identity"), dict) else {}
    recipient = row.get("recipient") if isinstance(row.get("recipient"), dict) else {}
    agency = row.get("agency") if isinstance(row.get("agency"), dict) else {}
    classifications = row.get("classifications") if isinstance(row.get("classifications"), dict) else {}
    return " ".join(str(value or "") for value in (
        identity.get("generated_award_id"), identity.get("piid"), recipient.get("name"),
        row.get("description"), agency.get("awarding"), agency.get("awarding_subagency"),
        agency.get("funding"), agency.get("funding_subagency"), classifications.get("award_type"),
        classifications.get("naics"), classifications.get("psc"), classifications.get("program"),
    )).casefold()


def _official_action_text(row: dict) -> str:
    return " ".join(str(value or "") for value in (
        row.get("action_id"), row.get("modification_number"), row.get("action_type"),
        row.get("action_type_description"), row.get("description"),
    )).casefold()


@router.get("/api/government-revenue/latest")
def latest(limit: int = Query(default=100, ge=1, le=250)) -> dict:
    payload = _load()
    opportunity = _opportunity_intelligence(payload)
    workspace = payload.get("procurement_workspace") or {}
    top_level = {
        key: payload.get(key)
        for key in (
            "schema_version", "workbench", "as_of", "known_at", "generated_at",
            "source", "authority", "freshness", "coverage", "market",
        )
        if key in payload
    }
    return _scrub_public(top_level | {
        "companies": [_public_company(row) for row in (payload.get("companies") or [])[:limit]],
        "opportunity_intelligence": {
            key: opportunity.get(key)
            for key in (
                "schema_version", "record_contract", "event_contract", "as_of",
                "known_at", "authority", "freshness", "coverage", "market", "provenance",
            )
            if key in opportunity
        },
        "procurement_workspace": {
            key: workspace.get(key)
            for key in (
                "schema_version", "event_contract", "as_of", "known_at", "authority",
                "freshness", "coverage", "facets", "total", "display_sort", "limitations",
            )
            if key in workspace
        },
    })


@router.get("/api/government-revenue/candidates")
def candidates(
    ticker: str | None = Query(default=None),
    family: str | None = Query(
        default=None,
        pattern=r"^(award_obligation_change|award_ceiling_change|option_exercise|new_award)$",
    ),
    state: str | None = Query(
        default=None,
        pattern=r"^(detected|awaiting_crosscheck|active|matured|superseded|withdrawn|blocked)$",
    ),
    direction: str | None = Query(
        default=None,
        pattern=r"^(possible_positive|possible_negative|mixed|unknown)$",
    ),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=100),
) -> dict:
    """Page exact, receipt-bound research candidates in evidence-recency order."""
    ticker = _validated_ticker(ticker)
    projection = _load_candidate_projection()
    queue = projection["queue"]
    rows = [
        row
        for row in _candidate_rows_for_queue(queue)
        if (ticker is None or row.get("ticker") == ticker)
        and (family is None or row.get("candidate_family") == family)
        and (state is None or row.get("candidate_state") == state)
        and (direction is None or row.get("transmission_direction") == direction)
    ]
    binding = _dossier_cursor_binding({
        "route": "candidates",
        "ticker": ticker,
        "family": family,
        "state": state,
        "direction": direction,
    })
    offset = _decode_candidate_cursor(
        cursor,
        content_id=queue["content_id"],
        binding=binding,
    )
    page = rows[offset:offset + limit]
    next_offset = offset + len(page)
    return _candidate_envelope(
        queue,
        items=[_public_candidate(row) for row in page],
        total=len(rows),
        next_cursor=(
            _encode_candidate_cursor(
                next_offset,
                content_id=queue["content_id"],
                binding=binding,
            )
            if next_offset < len(rows)
            else None
        ),
    )


@router.get("/api/government-revenue/candidate/{candidate_id}/history")
def candidate_history(
    candidate_id: str,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=100),
) -> dict:
    """Return immutable observations for one research hypothesis."""
    candidate_id = _validated_candidate_id(candidate_id)
    projection = _load_candidate_projection()
    queue = projection["queue"]
    rows = [
        row
        for row in projection["ledger"]
        if row.get("candidate_id") == candidate_id
    ]
    if not rows:
        raise HTTPException(status_code=404, detail="candidate not covered")
    rows.sort(key=lambda row: str(row.get("observation_id") or ""))
    rows.sort(key=lambda row: str(row.get("known_at") or ""), reverse=True)
    binding = _dossier_cursor_binding({
        "route": "candidate_history",
        "candidate_id": candidate_id,
    })
    offset = _decode_candidate_cursor(
        cursor,
        content_id=queue["content_id"],
        binding=binding,
    )
    page = rows[offset:offset + limit]
    next_offset = offset + len(page)
    return _candidate_envelope(
        queue,
        items=[_public_candidate_history_row(queue, row) for row in page],
        total=len(rows),
        next_cursor=(
            _encode_candidate_cursor(
                next_offset,
                content_id=queue["content_id"],
                binding=binding,
            )
            if next_offset < len(rows)
            else None
        ),
    )


@router.get("/api/government-revenue/candidate/{candidate_id}")
def candidate(candidate_id: str) -> dict:
    """Return the latest exact observation for one candidate identity."""
    candidate_id = _validated_candidate_id(candidate_id)
    projection = _load_candidate_projection()
    queue = projection["queue"]
    rows = [
        row
        for row in projection["ledger"]
        if row.get("candidate_id") == candidate_id
    ]
    if not rows:
        raise HTTPException(status_code=404, detail="candidate not covered")
    active_rows = [
        row
        for row in list(queue.get("candidates") or [])
        + list(queue.get("recently_matured") or [])
        if isinstance(row, dict)
        and row.get("candidate_id") == candidate_id
        and _candidate_correction_entry(queue, row) is None
    ]
    corrected_rows = [
        row for row in rows if _candidate_correction_entry(queue, row) is not None
    ]
    if corrected_rows and not active_rows:
        corrected_rows.sort(
            key=lambda row: (
                str(row.get("known_at") or ""),
                str(row.get("observation_id") or ""),
            ),
            reverse=True,
        )
        correction_entry = _candidate_correction_entry(queue, corrected_rows[0])
        if correction_entry is None:  # pragma: no cover - guarded by corrected_rows
            raise HTTPException(
                status_code=503,
                detail="government revenue candidate correction binding is invalid",
            )
        raise HTTPException(
            status_code=410,
            detail={
                "code": "candidate_historical_issuance_quarantined",
                "candidate_id": candidate_id,
                "history_url": (
                    f"/api/government-revenue/candidate/{candidate_id}/history"
                ),
                "correction_ref": _candidate_correction_ref(
                    queue, correction_entry
                ),
            },
        )
    selected_rows = active_rows or rows
    selected_rows.sort(
        key=lambda row: (str(row.get("known_at") or ""), str(row.get("observation_id") or "")),
        reverse=True,
    )
    return _scrub_public({
        "contract": queue.get("contract"),
        "schema_version": queue.get("schema_version"),
        "content_id": queue.get("content_id"),
        "as_of": queue.get("as_of"),
        "known_at": queue.get("known_at"),
        "generated_at": queue.get("generated_at"),
        "candidate": _public_candidate(selected_rows[0]),
        "history_count": len(rows),
        "freshness": queue.get("freshness"),
        "authority": queue.get("authority"),
        "limitations": queue.get("limitations"),
    })


@router.get("/api/government-revenue/company/{ticker}/candidates")
def company_candidates(
    ticker: str,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=100),
) -> dict:
    """Page exact candidates for a covered ticker without discovery fallback."""
    ticker = _validated_ticker(ticker)
    projection = _load_candidate_projection()
    queue = projection["queue"]
    active_rows = _candidate_rows_for_queue(queue)
    covered_tickers = {
        row.get("ticker")
        for row in active_rows + list(queue.get("mapping_backlog") or [])
        if isinstance(row, dict)
    }
    if ticker not in covered_tickers:
        raise HTTPException(status_code=404, detail="company not covered")
    rows = [row for row in active_rows if row.get("ticker") == ticker]
    binding = _dossier_cursor_binding({
        "route": "company_candidates",
        "ticker": ticker,
    })
    offset = _decode_candidate_cursor(
        cursor,
        content_id=queue["content_id"],
        binding=binding,
    )
    page = rows[offset:offset + limit]
    next_offset = offset + len(page)
    return _candidate_envelope(
        queue,
        items=[_public_candidate(row) for row in page],
        total=len(rows),
        next_cursor=(
            _encode_candidate_cursor(
                next_offset,
                content_id=queue["content_id"],
                binding=binding,
            )
            if next_offset < len(rows)
            else None
        ),
    )


@router.get("/api/government-revenue/mapping-backlog")
def mapping_backlog(
    ticker: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=100),
) -> dict:
    """Page discovery-scope companies still requiring exact issuer proof."""
    ticker = _validated_ticker(ticker)
    projection = _load_candidate_projection()
    queue = projection["queue"]
    rows = [
        row
        for row in queue.get("mapping_backlog") or []
        if isinstance(row, dict) and (ticker is None or row.get("ticker") == ticker)
    ]
    rows.sort(key=lambda row: (str(row.get("ticker") or ""), str(row.get("backlog_id") or "")))
    binding = _dossier_cursor_binding({
        "route": "mapping_backlog",
        "ticker": ticker,
    })
    offset = _decode_candidate_cursor(
        cursor,
        content_id=queue["content_id"],
        binding=binding,
    )
    page = rows[offset:offset + limit]
    next_offset = offset + len(page)
    return _scrub_public({
        "contract": queue.get("contract"),
        "schema_version": queue.get("schema_version"),
        "content_id": queue.get("content_id"),
        "as_of": queue.get("as_of"),
        "known_at": queue.get("known_at"),
        "generated_at": queue.get("generated_at"),
        "total": len(rows),
        "items": page,
        "next_cursor": (
            _encode_candidate_cursor(
                next_offset,
                content_id=queue["content_id"],
                binding=binding,
            )
            if next_offset < len(rows)
            else None
        ),
        "freshness": queue.get("freshness"),
        "coverage": queue.get("coverage"),
        "authority": queue.get("authority"),
        "limitations": queue.get("limitations"),
    })


@router.get("/api/government-revenue/company/{ticker}")
def company(ticker: str) -> dict:
    ticker = _validated_ticker(ticker)
    payload = _load()
    row = next((item for item in payload.get("companies") or [] if item.get("ticker") == ticker), None)
    if row is None:
        raise HTTPException(status_code=404, detail="company not covered")
    return {
        "schema_version": payload["schema_version"],
        "as_of": payload.get("as_of"),
        "known_at": payload.get("known_at"),
        "authority": payload.get("authority"),
        "company": _public_company(row),
    }


@router.get("/api/government-revenue/budget-programs")
def budget_programs() -> dict:
    """List precomputed DoD request-evidence program nodes.

    P-1/R-1 evidence is kept separate from authorization, enacted
    appropriation, execution, award value, and issuer conclusions; the stored
    source-coverage rails make that boundary explicit in every response.
    """
    payload = _load_budget_program_graph()
    return _public_budget_graph_envelope(payload) | {
        "programs": [_public_budget_program(row) for row in payload.get("programs") or []],
        "total": len(payload.get("programs") or []),
    }


@router.get("/api/government-revenue/budget-line/{line_key}")
def budget_line(line_key: str) -> dict:
    """Return one receipt-bound budget line and its source-native program edge."""
    line_key = _validated_budget_line_key(line_key)
    payload = _load_budget_program_graph()
    line = next(
        (row for row in payload.get("lines") or [] if isinstance(row, dict) and row.get("line_key") == line_key),
        None,
    )
    if line is None:
        raise HTTPException(status_code=404, detail="budget line not covered")
    edges = [
        _public_budget_edge(row)
        for row in payload.get("edges") or []
        if isinstance(row, dict) and row.get("from_type") == "budget_line" and row.get("from_id") == line_key
    ]
    return _public_budget_graph_envelope(payload) | {
        "line": _public_budget_line(line),
        "source_native_edges": edges,
    }


@router.get("/api/government-revenue/program/{program_key}")
def budget_program(program_key: str) -> dict:
    """Return one program node with exact stored lines and documentary edges."""
    program_key = _validated_budget_program_key(program_key)
    payload = _load_budget_program_graph()
    program = next(
        (row for row in payload.get("programs") or [] if isinstance(row, dict) and row.get("program_key") == program_key),
        None,
    )
    if program is None:
        raise HTTPException(status_code=404, detail="budget program not covered")
    line_keys = set(program.get("line_keys") or [])
    lines = [
        _public_budget_line(row)
        for row in payload.get("lines") or []
        if isinstance(row, dict) and row.get("line_key") in line_keys
    ]
    edges = [
        _public_budget_edge(row)
        for row in payload.get("edges") or []
        if isinstance(row, dict) and (
            (row.get("from_type") == "program" and row.get("from_id") == program_key)
            or (row.get("to_type") == "program" and row.get("to_id") == program_key)
        )
    ]
    return _public_budget_graph_envelope(payload) | {
        "program": _public_budget_program(program),
        "lines": lines,
        "documentary_edges": edges,
    }


@router.get("/api/government-revenue/dossier/company/{ticker}")
def dossier_company(ticker: str) -> dict:
    """Return precomputed collection-scope metadata, not issuer attribution."""
    ticker = _validated_ticker(ticker)
    payload = _load_dossiers()
    row = _dossier_company_map(payload).get(ticker)
    if row is None:
        raise HTTPException(status_code=404, detail="company collection scope not covered")
    return _scrub_public({
        "schema_version": payload.get("schema_version"),
        "content_id": payload.get("content_id"),
        "as_of": payload.get("as_of"),
        "known_at": payload.get("known_at"),
        "source_coverage": payload.get("source_coverage"),
        "freshness": payload.get("freshness"),
        "company": _public_dossier_company(row),
    })


def _award_sort_key(row: dict, sort: str) -> tuple:
    values = row.get("values") if isinstance(row.get("values"), dict) else {}
    dates = row.get("dates") if isinstance(row.get("dates"), dict) else {}
    if sort == "obligation_desc":
        return (float(values.get("obligated") or float("-inf")), str(row.get("award_key") or ""))
    if sort == "current_value_desc":
        return (float(values.get("current_award_value") or float("-inf")), str(row.get("award_key") or ""))
    if sort == "ceiling_desc":
        return (float(values.get("ceiling") or float("-inf")), str(row.get("award_key") or ""))
    return (str(dates.get("effective_at") or ""), str(dates.get("known_at") or ""), str(row.get("award_key") or ""))


@router.get("/api/government-revenue/company/{ticker}/awards")
def company_awards(
    ticker: str,
    q: str | None = Query(default=None, min_length=1, max_length=160),
    agency: str | None = Query(default=None, min_length=1, max_length=200),
    naics: str | None = Query(default=None, min_length=1, max_length=32),
    psc: str | None = Query(default=None, min_length=1, max_length=32),
    award_type: str | None = Query(default=None, min_length=1, max_length=160),
    sort: str = Query(default="effective_desc", pattern=r"^(effective_desc|obligation_desc|current_value_desc|ceiling_desc)$"),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    """Cursor through precomputed award history using official stored fields only."""
    ticker = _validated_ticker(ticker)
    payload = _load_dossiers()
    company_row = _dossier_company_map(payload).get(ticker)
    if company_row is None:
        raise HTTPException(status_code=404, detail="company collection scope not covered")
    normalized = {
        "q": q.casefold().strip() if q else None,
        "agency": agency.casefold().strip() if agency else None,
        "naics": naics.casefold().strip() if naics else None,
        "psc": psc.casefold().strip() if psc else None,
        "award_type": award_type.casefold().strip() if award_type else None,
        "sort": sort,
    }
    if any(value == "" for value in normalized.values() if isinstance(value, str)):
        raise HTTPException(status_code=400, detail="invalid award filter")
    awards = _dossier_award_map(payload)
    rows = [awards[key] for key in company_row.get("award_keys", []) if key in awards]
    filtered: list[dict] = []
    for row in rows:
        agency_data = row.get("agency") if isinstance(row.get("agency"), dict) else {}
        classes = row.get("classifications") if isinstance(row.get("classifications"), dict) else {}
        if normalized["q"] and normalized["q"] not in _official_award_text(row):
            continue
        if normalized["agency"] and normalized["agency"] not in " ".join(
            str(agency_data.get(key) or "") for key in ("awarding", "awarding_subagency", "funding", "funding_subagency")
        ).casefold():
            continue
        if normalized["naics"] and normalized["naics"] != str(classes.get("naics") or "").casefold():
            continue
        if normalized["psc"] and normalized["psc"] != str(classes.get("psc") or "").casefold():
            continue
        if normalized["award_type"] and normalized["award_type"] != str(classes.get("award_type") or "").casefold():
            continue
        filtered.append(row)
    filtered.sort(key=lambda row: _award_sort_key(row, sort), reverse=True)
    binding = _dossier_cursor_binding({"route": "company_awards", "ticker": ticker, **normalized})
    offset = _decode_dossier_cursor(
        cursor, content_id=payload["content_id"], binding=binding,
    )
    page = filtered[offset:offset + limit]
    next_offset = offset + len(page)
    return _dossier_envelope(
        payload,
        results=[_public_dossier_award(row) for row in page],
        next_cursor=(
            _encode_dossier_cursor(next_offset, content_id=payload["content_id"], binding=binding)
            if next_offset < len(filtered) else None
        ),
        total=len(filtered),
    )


@router.get("/api/government-revenue/award/{award_key}/actions")
def award_actions(
    award_key: str,
    q: str | None = Query(default=None, min_length=1, max_length=160),
    action_type: str | None = Query(default=None, min_length=1, max_length=160),
    sort: str = Query(default="effective_desc", pattern=r"^(effective_desc|obligation_desc)$"),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    """Cursor through precomputed native-ID transaction observations for an award."""
    award_key = _validated_award_key(award_key)
    payload = _load_dossiers()
    award_row = _dossier_award_map(payload).get(award_key)
    if award_row is None:
        raise HTTPException(status_code=404, detail="award not covered")
    normalized_q = q.casefold().strip() if q else None
    normalized_type = action_type.casefold().strip() if action_type else None
    if normalized_q == "" or normalized_type == "":
        raise HTTPException(status_code=400, detail="invalid action filter")
    actions = _dossier_action_map(payload)
    rows = [actions[key] for key in award_row.get("action_keys", []) if key in actions]
    filtered = [
        row for row in rows
        if (not normalized_q or normalized_q in _official_action_text(row))
        and (not normalized_type or normalized_type == str(row.get("action_type") or "").casefold())
    ]
    if sort == "obligation_desc":
        filtered.sort(
            key=lambda row: (float(row.get("obligation") or float("-inf")), str(row.get("action_key") or "")),
            reverse=True,
        )
    else:
        filtered.sort(
            key=lambda row: (str(row.get("effective_at") or ""), str(row.get("known_at") or ""), str(row.get("action_key") or "")),
            reverse=True,
        )
    binding = _dossier_cursor_binding({
        "route": "award_actions", "award_key": award_key, "q": normalized_q,
        "action_type": normalized_type, "sort": sort,
    })
    offset = _decode_dossier_cursor(
        cursor, content_id=payload["content_id"], binding=binding,
    )
    page = filtered[offset:offset + limit]
    next_offset = offset + len(page)
    return _dossier_envelope(
        payload,
        results=[_public_dossier_action(row) for row in page],
        next_cursor=(
            _encode_dossier_cursor(next_offset, content_id=payload["content_id"], binding=binding)
            if next_offset < len(filtered) else None
        ),
        total=len(filtered),
    )


@router.get("/api/government-revenue/award/{award_key}/idv-relationships")
def award_idv_relationships(award_key: str) -> dict:
    """Return exact source-native IDV parents bridged to one definitive award.

    This is a relationship lookup, not vehicle participation, seat, utilization,
    award-value, or issuer-attribution analysis.  Direct and grandchild depth
    remain explicitly stored on every returned observation.
    """
    award_key = _validated_award_key(award_key)
    prime_payload = _load_dossiers()
    if award_key not in _dossier_award_map(prime_payload):
        raise HTTPException(status_code=404, detail="award not covered")
    payload = _load_idv_dossiers()
    bridge = _award_idv_bridge(prime_payload, payload, award_key)
    relationships = [
        _public_idv_relationship(row)
        for row in payload.get("relationships") or []
        if isinstance(row, dict) and row.get("child_award_key") == award_key
    ]
    relationships.sort(key=lambda row: str(row.get("relationship_key") or ""))
    selection = payload.get("selection_provenance")
    source_coverage = payload.get("source_coverage")
    selection = selection if isinstance(selection, dict) else {}
    source_coverage = source_coverage if isinstance(source_coverage, dict) else {}
    if source_coverage.get("status") != "ok" or selection.get("status") != "verified":
        award_coverage = {
            "status": "unavailable",
            "exhaustive": False,
            "exact_relationship_count": 0,
            "selected_parent_count": 0,
            "selection_manifest_id": None,
            "reason": "No publication-eligible bounded IDV selection is active; no relationship conclusion was inferred.",
        }
    else:
        observed = bool(relationships)
        selected_count = selection.get("selected_parent_count")
        award_coverage = {
            "status": "observed" if observed else "not_observed",
            "exhaustive": False,
            "exact_relationship_count": len(relationships),
            "selected_parent_count": selected_count,
            "selection_manifest_id": selection.get("selection_manifest_id"),
            "reason": (
                "Published exact generated-ID relationship observations for this award in the bounded active IDV cut."
                if observed
                else f"No exact generated-ID bridge was observed for this award in the bounded {selected_count}-parent IDV cut; absence is not evidence that no IDV relationship exists."
            ),
        }
    return _scrub_public({
        "schema_version": payload.get("schema_version"),
        "content_id": payload.get("content_id"),
        "as_of": payload.get("as_of"),
        "known_at": payload.get("known_at"),
        "authority": payload.get("authority"),
        "source_coverage": payload.get("source_coverage"),
        "freshness": payload.get("freshness"),
        "selection_provenance": payload.get("selection_provenance"),
        "award_coverage": award_coverage,
        "bridge": bridge,
        "limitations": payload.get("limitations"),
        "award_key": award_key,
        "relationships": relationships,
        "total": len(relationships),
    })


def _subaward_action_date(row: dict) -> str | None:
    dates = row.get("dates")
    value = dates.get("action_date") if isinstance(dates, dict) else None
    return value if isinstance(value, str) else None


def _subaward_subrecipient_text(row: dict) -> str:
    return str(row.get("subawardee_name") or "").casefold()


@router.get("/api/government-revenue/award/{award_key}/subawards")
def award_subawards(
    award_key: str,
    subrecipient: str | None = Query(default=None, min_length=1, max_length=200),
    action_date_from: str | None = Query(default=None),
    action_date_to: str | None = Query(default=None),
    sort: str = Query(default="action_date_desc", pattern=r"^action_date_desc$"),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    """Page only precomputed, exact-parent subaward observations.

    An empty valid rail returns a normal zero-result envelope for a covered
    prime award.  That expresses an uninitialized or unavailable source
    honestly without inventing a subaward relationship; a malformed or
    partial artifact is rejected by the loader before it reaches this route.
    """
    award_key = _validated_award_key(award_key)
    date_from = _validated_action_date(action_date_from, label="action_date_from")
    date_to = _validated_action_date(action_date_to, label="action_date_to")
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(status_code=400, detail="invalid action date range")
    normalized_subrecipient = subrecipient.casefold().strip() if subrecipient else None
    if normalized_subrecipient == "":
        raise HTTPException(status_code=400, detail="invalid subrecipient")

    prime_payload = _load_dossiers()
    if award_key not in set(_prime_award_key_by_generated_id(prime_payload).values()):
        raise HTTPException(status_code=404, detail="award not covered")
    payload = _load_subaward_dossiers()
    parent_coverage = _subaward_parent_coverage(payload, award_key)
    rows = [
        row
        for row in payload.get("subawards") or []
        if isinstance(row, dict)
        and (binding := _subaward_parent_binding(row)) is not None
        and binding[0] == award_key
    ]
    filtered = [
        row for row in rows
        if (not normalized_subrecipient or normalized_subrecipient in _subaward_subrecipient_text(row))
        and (
            (date_from is None and date_to is None)
            or (
                (row_date := _subaward_action_date(row)) is not None
                and (date_from is None or row_date >= date_from)
                and (date_to is None or row_date <= date_to)
            )
        )
    ]
    filtered.sort(
        key=lambda row: (_subaward_action_date(row) or "", str(row.get("subaward_key") or "")),
        reverse=True,
    )
    binding = _dossier_cursor_binding({
        "route": "award_subawards",
        "award_key": award_key,
        "subrecipient": normalized_subrecipient,
        "action_date_from": date_from,
        "action_date_to": date_to,
        "sort": sort,
    })
    offset = _decode_subaward_cursor(
        cursor, content_id=payload["content_id"], binding=binding,
    )
    page = filtered[offset:offset + limit]
    next_offset = offset + len(page)
    return _subaward_dossier_envelope(
        payload,
        results=[_public_subaward(row) for row in page],
        next_cursor=(
            _encode_subaward_cursor(
                next_offset, content_id=payload["content_id"], binding=binding,
            )
            if next_offset < len(filtered)
            else None
        ),
        total=len(filtered),
        parent_coverage=parent_coverage,
    )


@router.get("/api/government-revenue/subaward/{subaward_key}")
def subaward(subaward_key: str) -> dict:
    """Return one exact precomputed subaward observation, never live lookup."""
    subaward_key = _validated_subaward_key(subaward_key)
    payload = _load_subaward_dossiers()
    row = _subaward_map(payload).get(subaward_key)
    if row is None:
        raise HTTPException(status_code=404, detail="subaward not covered")
    binding = _subaward_parent_binding(row)
    if binding is None:
        raise HTTPException(status_code=503, detail="government revenue subaward parent binding invalid")
    return _scrub_public({
        "schema_version": payload.get("schema_version"),
        "content_id": payload.get("content_id"),
        "as_of": payload.get("as_of"),
        "known_at": payload.get("known_at"),
        "authority": payload.get("authority"),
        "source_coverage": payload.get("source_coverage"),
        "freshness": payload.get("freshness"),
        "parent_coverage": _subaward_parent_coverage(payload, binding[0]),
        "limitations": payload.get("limitations"),
        "subaward": _public_subaward(row),
    })


@router.get("/api/government-revenue/award/{award_key}")
def award(award_key: str) -> dict:
    """Return one precomputed award dossier; no request-time enrichment occurs."""
    award_key = _validated_award_key(award_key)
    payload = _load_dossiers()
    row = _dossier_award_map(payload).get(award_key)
    if row is None:
        raise HTTPException(status_code=404, detail="award not covered")
    return _scrub_public({
        "schema_version": payload.get("schema_version"),
        "content_id": payload.get("content_id"),
        "as_of": payload.get("as_of"),
        "known_at": payload.get("known_at"),
        "source_coverage": payload.get("source_coverage"),
        "freshness": payload.get("freshness"),
        "award": _public_dossier_award(row),
    })


@router.get("/api/government-revenue/search")
def search(q: str = Query(min_length=1, max_length=80), limit: int = Query(default=20, ge=1, le=50)) -> dict:
    needle = q.casefold().strip()
    payload = _load()
    matches = []
    for row in payload.get("companies") or []:
        haystack = f"{row.get('ticker', '')} {row.get('name', '')}".casefold()
        if needle in haystack:
            matches.append({
                "ticker": row.get("ticker"),
                "name": row.get("name"),
                "metrics": row.get("metrics") or {},
                "confidence": row.get("confidence"),
            })
        if len(matches) >= limit:
            break
    return {"as_of": payload.get("as_of"), "query": q, "results": matches}


@router.get("/api/government-revenue/opportunities")
def opportunities(
    q: str | None = Query(default=None, min_length=1, max_length=120),
    ticker: str | None = Query(default=None),
    agency: str | None = Query(default=None, min_length=1, max_length=100),
    status: str | None = Query(default=None, min_length=1, max_length=40),
    defense_only: bool = Query(default=False),
    deadline_within_days: int | None = Query(default=None, ge=0, le=730),
    offset: int = Query(default=0, ge=0, le=10_000),
    limit: int = Query(default=50, ge=1, le=250),
) -> dict:
    """Search the prebuilt, point-in-time opportunity projection."""
    payload = _load()
    intelligence = _opportunity_intelligence(payload)
    ticker = _validated_ticker(ticker)
    needle = q.casefold().strip() if q else None
    agency_needle = agency.casefold().strip() if agency else None
    status_needle = status.casefold().strip() if status else None
    rows: list[dict] = []
    for raw in intelligence.get("opportunities") or []:
        if not isinstance(raw, dict):
            continue
        candidates = raw.get("company_candidates") or []
        if ticker and not any(item.get("ticker") == ticker for item in candidates if isinstance(item, dict)):
            continue
        if agency_needle and agency_needle not in str(raw.get("agency") or "").casefold():
            continue
        if status_needle and status_needle != str(raw.get("status") or "").casefold():
            continue
        if defense_only and not raw.get("defense_relevant"):
            continue
        days = raw.get("days_to_response")
        if deadline_within_days is not None and (
            not isinstance(days, int) or days < 0 or days > deadline_within_days
        ):
            continue
        if needle:
            haystack = " ".join(
                str(raw.get(key) or "")
                for key in (
                    "notice_id", "solicitation_number", "title", "description",
                    "agency", "office", "naics_code", "psc_code",
                )
            ).casefold()
            candidate_text = " ".join(
                f"{item.get('ticker', '')} {item.get('name', '')}"
                for item in candidates if isinstance(item, dict)
            ).casefold()
            if needle not in haystack and needle not in candidate_text:
                continue
        rows.append(_public_opportunity(raw))
    total = len(rows)
    page = rows[offset:offset + limit]
    return {
        "schema_version": intelligence.get("schema_version"),
        "as_of": intelligence.get("as_of") or payload.get("as_of"),
        "known_at": intelligence.get("known_at"),
        "authority": intelligence.get("authority") or payload.get("authority"),
        "freshness": intelligence.get("freshness") or {},
        "query": {
            "q": q, "ticker": ticker, "agency": agency, "status": status,
            "defense_only": defense_only, "deadline_within_days": deadline_within_days,
        },
        "pagination": {
            "offset": offset,
            "limit": limit,
            "total": total,
            "has_more": offset + len(page) < total,
        },
        "results": page,
    }


@router.get("/api/government-revenue/opportunity/{notice_id}")
def opportunity(notice_id: str) -> dict:
    if not _NOTICE_ID.fullmatch(notice_id):
        raise HTTPException(status_code=400, detail="invalid notice id")
    payload = _load()
    intelligence = _opportunity_intelligence(payload)
    row = next(
        (
            item for item in intelligence.get("opportunities") or []
            if isinstance(item, dict) and item.get("notice_id") == notice_id
        ),
        None,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="opportunity not covered")
    events = [
        event for event in intelligence.get("events") or []
        if isinstance(event, dict) and event.get("notice_id") == notice_id
    ]
    return {
        "schema_version": intelligence.get("schema_version"),
        "as_of": intelligence.get("as_of") or payload.get("as_of"),
        "known_at": intelligence.get("known_at"),
        "authority": intelligence.get("authority") or payload.get("authority"),
        "opportunity": _public_opportunity(row),
        "events": [_public_opportunity_event(event) for event in events],
    }


@router.get("/api/government-revenue/recompetes")
def recompetes(
    ticker: str | None = Query(default=None),
    within_days: int = Query(default=540, ge=30, le=1095),
    offset: int = Query(default=0, ge=0, le=10_000),
    limit: int = Query(default=50, ge=1, le=250),
) -> dict:
    """Return deterministic POP-end watches, never implied solicitation forecasts."""
    payload = _load()
    ticker = _validated_ticker(ticker)
    rows: list[dict] = []
    for company_row in payload.get("companies") or []:
        if not isinstance(company_row, dict):
            continue
        if ticker and company_row.get("ticker") != ticker:
            continue
        for watch in company_row.get("recompete_candidates") or []:
            if not isinstance(watch, dict) or int(watch.get("days_to_end") or 10**9) > within_days:
                continue
            rows.append({
                "ticker": company_row.get("ticker"),
                "name": company_row.get("name"),
                "classification": "derived_deterministic",
                "label_limit": "period-of-performance expiry watch; not an official recompete date or solicitation forecast",
                "authority": payload.get("authority"),
                **watch,
            })
    rows.sort(key=lambda row: (int(row.get("days_to_end") or 10**9), str(row.get("ticker") or "")))
    total = len(rows)
    page = rows[offset:offset + limit]
    return {
        "schema_version": payload.get("schema_version"),
        "as_of": payload.get("as_of"),
        "known_at": payload.get("known_at"),
        "authority": payload.get("authority"),
        "pagination": {
            "offset": offset, "limit": limit, "total": total,
            "has_more": offset + len(page) < total,
        },
        "results": page,
    }


@router.get("/api/government-revenue/workspace")
def workspace(
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    """Return a stable cursor page in the backend-prioritized workspace order."""
    source = _procurement_workspace(_load())
    cursor_version = _workspace_cursor_version(source)
    offset = _decode_cursor(cursor, expected_version=cursor_version)
    events = [
        _public_workspace_event(row)
        for row in (source.get("events") or [])[offset:offset + limit]
        if isinstance(row, dict)
    ]
    total = int(source.get("total") or len(source.get("events") or []))
    next_offset = offset + len(events)
    metadata = {
        key: source.get(key)
        for key in (
            "schema_version", "event_contract", "as_of", "known_at", "generated_at",
            "authority", "freshness", "coverage", "facets", "total", "display_sort",
            "federation_contract", "limitations",
        )
        if key in source
    }
    return _scrub_public(metadata | {
        "events": events,
        "next_cursor": _encode_cursor(next_offset, version=cursor_version) if next_offset < total else None,
    })


def _event_critical_date(row: dict) -> str:
    primary = row.get("primary_date_id")
    dates = row.get("dates") or []
    value = next(
        (item.get("value") for item in dates if isinstance(item, dict) and item.get("id") == primary),
        None,
    )
    return str(value or "9999-12-31")


def _event_primary_amount(row: dict) -> float:
    primary = row.get("primary_amount_id")
    amounts = row.get("amounts") or []
    value = next(
        (item.get("value") for item in amounts if isinstance(item, dict) and item.get("id") == primary),
        None,
    )
    return float(value) if isinstance(value, (int, float)) else float("-inf")


@router.get("/api/government-revenue/events")
def events(
    mode: str = Query(default="changes", pattern=r"^(changes|awards|opportunities|recompetes)$"),
    q: str | None = Query(default=None, min_length=1, max_length=120),
    ticker: str | None = Query(default=None),
    agency_id: str | None = Query(default=None, min_length=1, max_length=120),
    notice_type: str | None = Query(default=None, min_length=1, max_length=80),
    evidence_class: str | None = Query(default=None, min_length=1, max_length=60),
    impact: str | None = Query(default=None, pattern=r"^(high|medium|low|unknown)$"),
    deadline: str = Query(default="all", pattern=r"^(7d|30d|90d|540d|all)$"),
    scope: str | None = Query(default=None, pattern=r"^(mapped|all)$"),
    sort: str = Query(default="priority", pattern=r"^(priority|newest|critical_date|largest_official_amount)$"),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    """Filter the prebuilt event ledger without recalculating intelligence."""
    source = _procurement_workspace(_load())
    cursor_version = _workspace_cursor_version(source)
    effective_scope = scope or ("all" if mode == "awards" else "mapped")
    ticker = _validated_ticker(ticker)
    needle = q.casefold().strip() if q else None
    agency_needle = agency_id.casefold().strip() if agency_id else None
    notice_needle = notice_type.casefold().strip() if notice_type else None
    evidence_needle = evidence_class.casefold().strip() if evidence_class else None
    deadline_days = None if deadline == "all" else int(deadline[:-1])
    source_rows = [row for row in source.get("events") or [] if isinstance(row, dict)]
    if mode == "opportunities":
        latest_by_record: dict[str, dict] = {}
        for row in source_rows:
            if row.get("kind") != "opportunity":
                continue
            record_id = str(row.get("record_id") or "")
            prior = latest_by_record.get(record_id)
            row_clock = str((row.get("change") or {}).get("known_at") or "")
            prior_clock = str((prior.get("change") or {}).get("known_at") or "") if prior else ""
            if prior is None or (row_clock, int(row.get("version") or 0)) > (
                prior_clock,
                int(prior.get("version") or 0),
            ):
                latest_by_record[record_id] = row
        source_rows = list(latest_by_record.values())

    rows: list[dict] = []
    for raw in source_rows:
        if not isinstance(raw, dict):
            continue
        if mode == "opportunities" and raw.get("kind") != "opportunity":
            continue
        if mode == "awards" and raw.get("kind") != "award_change":
            continue
        if mode == "recompetes" and raw.get("kind") != "recompete":
            continue
        impacts = raw.get("listed_company_impacts") or []
        if effective_scope == "mapped" and not impacts:
            continue
        if ticker and raw.get("primary_ticker") != ticker and not any(
            item.get("ticker") == ticker for item in impacts if isinstance(item, dict)
        ):
            continue
        agency = raw.get("agency") or {}
        agency_name = str(agency.get("department_name") or agency.get("name") or "")
        if agency_needle and agency_needle not in agency_name.casefold():
            continue
        raw_notice_type = str((raw.get("opportunity") or {}).get("notice_type") or "")
        if notice_needle and notice_needle != raw_notice_type.casefold():
            continue
        mapping_class = str((raw.get("evidence") or {}).get("mapping_class") or "unmapped")
        if evidence_needle and evidence_needle != mapping_class.casefold():
            continue
        materiality = str(
            (((impacts or [{}])[0].get("materiality") or {}).get("band") or "unknown")
        )
        if impact and impact != materiality:
            continue
        if deadline_days is not None:
            days = (raw.get("recompete") or {}).get("days_to_current_end")
            if days is None:
                due = next(
                    (
                        item.get("value") for item in raw.get("dates") or []
                        if isinstance(item, dict) and item.get("id") == "response_deadline"
                    ),
                    None,
                )
                try:
                    due_day = datetime.fromisoformat(str(due).replace("Z", "+00:00")).date()
                    as_of_day = datetime.fromisoformat(str(source.get("as_of"))).date()
                    days = (due_day - as_of_day).days
                except (TypeError, ValueError):
                    days = None
            if not isinstance(days, int) or days < 0 or days > deadline_days:
                continue
        if needle:
            award_change = raw.get("award_change") or {}
            haystack = " ".join([
                str(raw.get("event_id") or ""),
                str(raw.get("record_id") or ""),
                str(raw.get("title_original") or ""),
                agency_name,
                str(raw.get("primary_ticker") or ""),
                str((raw.get("change") or {}).get("what_changed_en") or ""),
                str(award_change.get("award_key") or ""),
                str(award_change.get("generated_award_id") or ""),
                str(award_change.get("piid") or ""),
                str(award_change.get("action_id") or ""),
                str(award_change.get("recipient_name") or ""),
                str(award_change.get("event_type") or ""),
                str(award_change.get("source_rail") or ""),
            ]).casefold()
            if needle not in haystack:
                continue
        rows.append(raw)

    if sort == "newest":
        rows.sort(key=lambda row: str((row.get("change") or {}).get("known_at") or ""), reverse=True)
    elif sort == "critical_date":
        rows.sort(key=_event_critical_date)
    elif sort == "largest_official_amount":
        rows.sort(key=_event_primary_amount, reverse=True)
    # priority retains the audited order already serialized by the engine.

    offset = _decode_cursor(cursor, expected_version=cursor_version)
    total = len(rows)
    page = rows[offset:offset + limit]
    next_offset = offset + len(page)
    return {
        "schema_version": source.get("schema_version"),
        "event_contract": source.get("event_contract"),
        "as_of": source.get("as_of"),
        "known_at": source.get("known_at"),
        "authority": source.get("authority"),
        "freshness": source.get("freshness"),
        "query": {
            "mode": mode, "q": q, "ticker": ticker, "agency_id": agency_id,
            "notice_type": notice_type, "evidence_class": evidence_class,
            "impact": impact, "deadline": deadline, "scope": effective_scope, "sort": sort,
        },
        "events": [_public_workspace_event(row) for row in page],
        "next_cursor": _encode_cursor(next_offset, version=cursor_version) if next_offset < total else None,
        "total": total,
    }


@router.get("/api/government-revenue/event/{event_id}")
def event(event_id: str) -> dict:
    if not _NOTICE_ID.fullmatch(event_id):
        raise HTTPException(status_code=400, detail="invalid event id")
    source = _procurement_workspace(_load())
    row = next(
        (
            item for item in source.get("events") or []
            if isinstance(item, dict) and item.get("event_id") == event_id
        ),
        None,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="procurement event not covered")
    return {
        "schema_version": source.get("schema_version"),
        "as_of": source.get("as_of"),
        "known_at": source.get("known_at"),
        "authority": source.get("authority"),
        "event": _public_workspace_event(row),
    }
