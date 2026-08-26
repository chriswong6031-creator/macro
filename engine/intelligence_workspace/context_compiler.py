"""Deterministic W1-C visible-context compiler (`ai_context_envelope.v1`).

Frozen contract: research/DEEPVUE_W1C_CONTEXT_ENVELOPE_CONTRACT_2026-08-25.md.

This module is a PURE resolution layer sitting above the frozen W1-A read
layer and beside (never inside) W1-B's native fact planner. It:

  * parses/validates the client's optional `ai_context_client.v1` block
    (carried inside the existing `BrainChatRequest.context` dict under the
    `ai_context` key — no new transport, no new top-level request field);
  * applies the frozen precedence law
    ``explicit request > pinned context > active selection > ambient widget
    context`` to produce the canonical `ai_context_envelope.v1`;
  * derives the `ai_context_receipt.v1` SSE/response body from that envelope.

It performs NO I/O, NO identity admission, and NO owner reads. Identity
admission (symbol -> ``SEC:*``) stays exclusively W1-A's normalizer via the
existing native-facts path; this module only ever carries edge symbols.

Explicit entities are lexed via the SAME grammar W1-B already uses
(`_symbol_candidates` in ``engine/neuralweb/native_facts.py``) — this module
imports that lexer rather than forking a second grammar. Ambient/pinned/
active symbol admission reuses the exact same law as
``native_facts._context_symbol``.

The LLM never sees this module and has zero authority over precedence,
identity, facts, conflicts, or the constant ``authority`` block below.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any
import uuid

from engine.intelligence_workspace.resolver import _PRIVATE_SUBSCRIBER_TEXT
from engine.neuralweb.native_facts import _context_symbol, _symbol_candidates

ENVELOPE_SCHEMA = "ai_context_envelope.v1"
CLIENT_SCHEMA = "ai_context_client.v1"
RECEIPT_SCHEMA = "ai_context_receipt.v1"

# Frozen contract constant — a compiler constant, never a per-request knob.
CONTEXT_STALE_BUDGET_SECONDS = 900

_MAX_ORIGIN_ID_LEN = 64
_MAX_PINNED = 3
# Review repair (MAJ-1/MAJ-2): echoed strings are validated/coerced, never
# passed through raw. Ambient fields are short UI labels; entity ids in
# `unsupported` mirror the symbol length ceiling used elsewhere.
_MAX_AMBIENT_FIELD_LEN = 32
_MAX_UNSUPPORTED_ECHO_LEN = 64
_UNSUPPORTED_ECHO_PLACEHOLDER = "<invalid>"

# Privileged fields a client must never be able to set from inside ai_context;
# stripped and recorded distinctly from merely-unknown keys (contract §Client
# context block). `_server`-prefixed keys are also privileged (any of them).
_PRIVILEGED_KEYS = frozenset({
    "effective_context", "authority", "field_requests", "datapoints", "latency_lane",
})

_KNOWN_CLIENT_KEYS = frozenset({
    "schema", "origin_id", "context_revision", "captured_at", "pinned", "active", "ambient",
})

# v1 supports exactly one entity type. Anything else is `unsupported_entity_type`,
# never coerced (contract §Client context block).
_SUPPORTED_ENTITY_TYPES = frozenset({"security"})


def _is_privileged_key(key: Any) -> bool:
    return isinstance(key, str) and (key in _PRIVILEGED_KEYS or key.startswith("_server"))


def _valid_symbol(value: Any) -> str | None:
    """Reuse the exact W1-B admission law (`native_facts._context_symbol`)."""
    if not isinstance(value, str):
        return None
    return _context_symbol({"symbol": value})


def _safe_ambient_str(value: Any, *, flags: dict[str, Any]) -> str | None:
    """Coerce an echoed ambient field (timeframe/page/panel) to a short, safe
    string or ``None``. Review repair (MAJ-1): a client-supplied ambient field
    used to be echoed into the envelope RAW — an arbitrary type, an oversized
    string, or subscriber-private/path-like text (credentials, a repo path)
    would all have ridden straight into a persisted receipt. Non-conforming
    input is replaced by ``None`` and the condition is recorded once in
    ``context_flags.echo_sanitized`` (never a silent drop).
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, str):
        flags["echo_sanitized"] = True
        return None
    if len(value) > _MAX_AMBIENT_FIELD_LEN or _PRIVATE_SUBSCRIBER_TEXT.search(value):
        flags["echo_sanitized"] = True
        return None
    return value


def _safe_unsupported_echo(value: Any, *, flags: dict[str, Any]) -> str | None:
    """Coerce a value destined for `unsupported[].entity` to a short, safe
    string that is ALWAYS a string when the input existed at all (never a
    silent null the way ambient fields are — an `unsupported` row exists
    specifically to name what was rejected, so it still needs SOMETHING to
    show). Review repair (MAJ-2): a nested dict/list, a script-tag string, or a
    path-like string used to ride straight through into the envelope (and from
    there into a persisted run buffer) with no type check, length cap, or leak
    screen at all.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        flags["echo_sanitized"] = True
        return _UNSUPPORTED_ECHO_PLACEHOLDER
    text = value if isinstance(value, str) else str(value)
    if _PRIVATE_SUBSCRIBER_TEXT.search(text):
        flags["echo_sanitized"] = True
        return _UNSUPPORTED_ECHO_PLACEHOLDER
    if len(text) > _MAX_UNSUPPORTED_ECHO_LEN:
        flags["echo_sanitized"] = True
        return text[:_MAX_UNSUPPORTED_ECHO_LEN]
    return text


def _parse_rfc3339(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _validate_client_block(block: Mapping[str, Any]) -> str | None:
    """Return a malformed reason code, or ``None`` when structurally valid.

    Deliberately narrow and type/bounds-only — this is NOT identity or field
    validation, only enough shape-checking to decide whether the whole block
    can be trusted at all (contract: "never a 500, never a silent success").
    """
    schema = block.get("schema")
    if schema is not None and schema != CLIENT_SCHEMA:
        return "invalid_schema"
    origin_id = block.get("origin_id")
    if not isinstance(origin_id, str) or not origin_id or len(origin_id) > _MAX_ORIGIN_ID_LEN:
        return "invalid_origin_id"
    revision = block.get("context_revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        return "invalid_revision"
    if _parse_rfc3339(block.get("captured_at")) is None:
        return "invalid_captured_at"
    pinned = block.get("pinned", [])
    if not isinstance(pinned, list) or len(pinned) > _MAX_PINNED:
        return "invalid_pinned"
    active = block.get("active")
    if active is not None and not isinstance(active, Mapping):
        return "invalid_active"
    ambient = block.get("ambient")
    if ambient is not None and not isinstance(ambient, Mapping):
        return "invalid_ambient"
    return None


def _classify_entity(
    raw: Any, *, flags: dict[str, Any]
) -> tuple[dict[str, str] | None, dict[str, Any] | None]:
    """Validate one client entity block ({"type": ..., "id": ...}).

    Returns (entity, unsupported_row); exactly one is not None. Never raises.
    `unsupported_row.entity` is ALWAYS a sanitized echo (MAJ-1/MAJ-2) — never
    the raw client value, which could be a nested structure, an oversized
    string, or subscriber-private/path-like text.
    """
    if not isinstance(raw, Mapping):
        return None, {"entity": None, "reason": "invalid_entity_shape"}
    entity_type = raw.get("type")
    entity_id = raw.get("id")
    if entity_type not in _SUPPORTED_ENTITY_TYPES:
        return None, {
            "entity": {
                "type": _safe_unsupported_echo(entity_type, flags=flags),
                "id": _safe_unsupported_echo(entity_id, flags=flags),
            },
            "reason": "unsupported_entity_type",
        }
    symbol = _valid_symbol(entity_id)
    if symbol is None:
        return None, {
            "entity": {
                "type": "security",
                "id": _safe_unsupported_echo(entity_id, flags=flags),
            },
            "reason": "invalid_symbol",
        }
    return {"type": "security", "id": symbol}, None


def _ids(entities: Sequence[Mapping[str, str]]) -> set[str]:
    return {entity["id"] for entity in entities}


def compile_envelope(
    message: str,
    context: Mapping[str, Any] | None,
    *,
    now: datetime | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Compile the deterministic `ai_context_envelope.v1` for one request.

    Pure: given the same ``message``/``context``/``now``/``request_id`` this
    always returns the same envelope (test-proven determinism — the compiler
    holds no mutable state and performs no I/O).
    """
    now = now if now is not None else datetime.now(timezone.utc)
    request_id = request_id if request_id is not None else uuid.uuid4().hex
    context = context if isinstance(context, Mapping) else {}

    context_flags: dict[str, Any] = {
        "stale": False,
        "malformed": False,
        "malformed_reason": None,
        "ambiguous_explicit": False,
        "rejected_fields": [],
        "ignored_fields": [],
        # Review repair (MAJ-1/MAJ-2): set True whenever an echoed ambient field
        # or `unsupported[].entity` value was type/length/leak-rejected and
        # replaced (never a silent drop with no trace).
        "echo_sanitized": False,
    }

    raw_client = context.get("ai_context")
    legacy = True
    origin: dict[str, Any] = {}
    pinned_raw: list[Any] = []
    active_raw: Any = None
    ambient_raw: Mapping[str, Any] = {}

    if raw_client is not None:
        if isinstance(raw_client, Mapping):
            malformed_reason = _validate_client_block(raw_client)
        else:
            malformed_reason = "invalid_schema"
        if malformed_reason is not None:
            context_flags["malformed"] = True
            context_flags["malformed_reason"] = malformed_reason
            legacy = True
        else:
            legacy = False
            for key in raw_client:
                if key in _KNOWN_CLIENT_KEYS:
                    continue
                if _is_privileged_key(key):
                    context_flags["rejected_fields"].append(key)
                else:
                    context_flags["ignored_fields"].append(key)
            origin = {
                "origin_id": raw_client["origin_id"],
                "context_revision": int(raw_client["context_revision"]),
                "captured_at": raw_client["captured_at"],
                "legacy": False,
            }
            pinned_raw = list(raw_client.get("pinned") or [])
            active_raw = raw_client.get("active")
            ambient_raw = raw_client.get("ambient") or {}

    if legacy:
        # Legacy mapping (contract §Client context block): active <- legacy
        # context.symbol, ambient <- {page, panel}, pinned = [] — preserves
        # today's explicit-over-ambient behavior byte-for-byte in meaning.
        legacy_symbol = _context_symbol(context)
        origin = {
            "origin_id": "legacy",
            "context_revision": 0,
            "captured_at": now.isoformat().replace("+00:00", "Z"),
            "legacy": True,
        }
        pinned_raw = []
        active_raw = {"type": "security", "id": legacy_symbol} if legacy_symbol else None
        ambient_raw = {
            "symbol": None,
            "timeframe": None,
            "page": context.get("page"),
            "panel": context.get("panel"),
        }

    # --- explicit entities: the message lexer, one grammar, never forked ---
    candidate_spans, ambiguous = _symbol_candidates(str(message or ""))
    context_flags["ambiguous_explicit"] = bool(ambiguous)
    explicit_symbols = tuple(dict.fromkeys(candidate for candidate, _, _ in candidate_spans))
    explicit_entities = [{"type": "security", "id": symbol} for symbol in explicit_symbols]

    # --- validate pinned / active / ambient entities ---
    unsupported: list[dict[str, Any]] = []

    pinned_context: list[dict[str, str]] = []
    for raw_entity in pinned_raw[:_MAX_PINNED]:
        entity, bad = _classify_entity(raw_entity, flags=context_flags)
        if entity is not None:
            pinned_context.append(entity)
        elif bad is not None:
            unsupported.append({**bad, "level": "pinned"})

    active_context: list[dict[str, str]] = []
    if active_raw is not None:
        entity, bad = _classify_entity(active_raw, flags=context_flags)
        if entity is not None:
            active_context.append(entity)
        elif bad is not None:
            unsupported.append({**bad, "level": "active"})

    ambient_symbol: str | None = None
    ambient_raw_symbol = ambient_raw.get("symbol") if isinstance(ambient_raw, Mapping) else None
    if ambient_raw_symbol is not None:
        ambient_symbol = _valid_symbol(ambient_raw_symbol)
        if ambient_symbol is None:
            unsupported.append({
                "entity": {
                    "type": "security",
                    "id": _safe_unsupported_echo(ambient_raw_symbol, flags=context_flags),
                },
                "reason": "invalid_symbol",
                "level": "ambient",
            })
    ambient_entities = [{"type": "security", "id": ambient_symbol}] if ambient_symbol else []

    # --- precedence: explicit > pinned > active > ambient ---
    dropped: list[dict[str, Any]] = []
    if explicit_entities:
        effective_entities = explicit_entities
        source = "explicit"
        eff_ids = _ids(effective_entities)
        lower_ids = _ids(pinned_context) | _ids(active_context) | _ids(ambient_entities)
        reason = "explicit_entity_wins" if (lower_ids - eff_ids) else "explicit_request"
        for entity in pinned_context:
            if entity["id"] not in eff_ids:
                dropped.append({"entity": entity, "level": "pinned", "reason": "outranked_by_explicit"})
        for entity in active_context:
            if entity["id"] not in eff_ids:
                dropped.append({"entity": entity, "level": "active", "reason": "outranked_by_explicit"})
        for entity in ambient_entities:
            if entity["id"] not in eff_ids:
                dropped.append({"entity": entity, "level": "ambient", "reason": "outranked_by_explicit"})
    elif pinned_context:
        effective_entities = pinned_context
        source = "pinned"
        reason = "pinned_context"
        eff_ids = _ids(effective_entities)
        for entity in active_context:
            if entity["id"] not in eff_ids:
                dropped.append({"entity": entity, "level": "active", "reason": "outranked_by_pinned"})
        for entity in ambient_entities:
            if entity["id"] not in eff_ids:
                dropped.append({"entity": entity, "level": "ambient", "reason": "outranked_by_pinned"})
    elif active_context:
        effective_entities = active_context
        source = "active"
        reason = "active_selection"
        eff_ids = _ids(effective_entities)
        for entity in ambient_entities:
            if entity["id"] not in eff_ids:
                dropped.append({"entity": entity, "level": "ambient", "reason": "outranked_by_active"})
    elif ambient_entities:
        effective_entities = ambient_entities
        source = "ambient"
        reason = "ambient_context"
    else:
        effective_entities = []
        source = "none"
        reason = "no_context"

    # Review repair (NB-3): "explicit_over_active" used to be emitted for EVERY
    # explicit win regardless of what actually got outranked, which is
    # dishonest when nothing (or only a lower level than "active") was
    # actually dropped. `precedence` now names the highest level that
    # genuinely lost an entity in THIS compile, or "<source>_only" when
    # nothing did — frozen vocabulary is the full cross product of source and
    # outranked level (see the contract's Canonical envelope amendment).
    dropped_levels = {row["level"] for row in dropped}
    if source == "explicit":
        if "pinned" in dropped_levels:
            precedence = "explicit_over_pinned"
        elif "active" in dropped_levels:
            precedence = "explicit_over_active"
        elif "ambient" in dropped_levels:
            precedence = "explicit_over_ambient"
        else:
            precedence = "explicit_only"
    elif source == "pinned":
        if "active" in dropped_levels:
            precedence = "pinned_over_active"
        elif "ambient" in dropped_levels:
            precedence = "pinned_over_ambient"
        else:
            precedence = "pinned_only"
    elif source == "active":
        precedence = "active_over_ambient" if "ambient" in dropped_levels else "active_only"
    elif source == "ambient":
        precedence = "ambient_only"
    else:
        precedence = "none"

    captured_dt = _parse_rfc3339(origin.get("captured_at"))
    if captured_dt is not None:
        age_s = (now - captured_dt).total_seconds()
        context_flags["stale"] = age_s > CONTEXT_STALE_BUDGET_SECONDS

    envelope: dict[str, Any] = {
        "schema": ENVELOPE_SCHEMA,
        "request_id": request_id,
        "origin": origin,
        "explicit_entities": explicit_entities,
        "pinned_context": pinned_context,
        "active_selection": active_context,
        "ambient_widget_context": {
            "symbol": ambient_symbol,
            # Review repair (MAJ-1): these three ride through _safe_ambient_str —
            # type/length/leak-checked, never the client's raw value. `symbol`
            # above needs no separate pass: it is already either a validated
            # ticker (via _valid_symbol) or None.
            "timeframe": _safe_ambient_str(
                ambient_raw.get("timeframe") if isinstance(ambient_raw, Mapping) else None,
                flags=context_flags,
            ),
            "page": _safe_ambient_str(
                ambient_raw.get("page") if isinstance(ambient_raw, Mapping) else None,
                flags=context_flags,
            ),
            "panel": _safe_ambient_str(
                ambient_raw.get("panel") if isinstance(ambient_raw, Mapping) else None,
                flags=context_flags,
            ),
        },
        "effective_context": {
            "entities": effective_entities,
            "source": source,
            "reason": reason,
            "precedence": precedence,
        },
        "dropped": dropped,
        "unsupported": unsupported,
        "context_flags": context_flags,
        "field_requests": [],
        "latency_lane": "instant_fact",
        "provenance_requirement": "field_level",
        "authority": {"may_execute": False, "may_originate_signal": False},
    }
    return envelope


def compile_receipt(envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Derive the `ai_context_receipt.v1` body from a compiled envelope.

    The receipt is the envelope minus `field_requests` (which stays only in
    the native-fact receipt) — context resolution only. Additive
    `envelope_schema` echoes the envelope's own schema tag without colliding
    with the receipt's own top-level `schema`.
    """
    body = {
        key: value for key, value in envelope.items()
        if key not in ("field_requests", "schema")
    }
    return {
        "schema": RECEIPT_SCHEMA,
        "envelope_schema": envelope.get("schema", ENVELOPE_SCHEMA),
        **body,
    }


__all__ = [
    "CLIENT_SCHEMA",
    "CONTEXT_STALE_BUDGET_SECONDS",
    "ENVELOPE_SCHEMA",
    "RECEIPT_SCHEMA",
    "compile_envelope",
    "compile_receipt",
]
