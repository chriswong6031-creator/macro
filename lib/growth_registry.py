"""lib/growth_registry.py — the growth-event registry as COLLECTOR AUTHORITY (W2-1).

`config/growth_events.yml` began life declarative: `app/main.py::_MM_EVENT_TYPES` was a
hardcoded closed set, and `tests/test_growth_events_registry.py` could only assert the
weaker direction (every accepted wire appears in the registry marked live). This module
flips the arrow — the beacon's accepted set is DERIVED from the registry, so an event
cannot ship "accepted but undeclared" or "declared live but dropped". That closes the
silent-drop failure the registry header names: unknown types are dropped silently,
which is how an instrumentation program ships dead.

Deliberately import-light: yaml + stdlib only. app/main.py imports this at startup, and
the registry tests import it directly — pulling FastAPI into a config test (or a second
hand-typed whitelist into a test helper) is exactly the drift this file removes.

Envelope v1 (DEC:ANALYTICS-EID-USES-EXISTING-EVENT-PRIMARY-KEY): events whose registry
entry carries `envelope: v1` are the newly implemented commercial wires. For those and
only those, acceptance additionally requires:
  * `eid`    — a valid UUID string; it becomes the analytics_events.id primary key, so
               an exact replay of the same event is ONE row (conflict-safe insert).
  * `schema` — the literal registry schema version ("growth_events.v1").
  * `meta`   — a dict whose keys are exactly a subset of the declared properties, every
               DECLARED property present, values matching the declared scalar/enum type.
Legacy wires (no `envelope` key) keep their existing acceptance unchanged — their rows
continue to receive server-generated UUIDs and their `meta` stays a bounded passthrough.

Validation here REJECTS rather than coerces (null contract: "invalid new events are
dropped/rejected with a bounded diagnostic, never coerced"). The one enum worth naming:
`insider` is not in the tier enum, so a raw legacy tier value is rejected by the same
rule that rejects any out-of-enum value — normalization to `essential` is the EMITTER's
job (lib/tiers.py), never telemetry's.
"""
from __future__ import annotations

import re
import uuid as _uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = _ROOT / "config" / "growth_events.yml"

SCHEMA_VERSION = "growth_events.v1"

#: Property string values are display-safe identifiers/counts, never prose. A cap this
#: small also makes the "oversized string" rejection testable without a second budget.
_MAX_PROP_STRING = 200

_WIRE_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")


@lru_cache(maxsize=4)
def _load(path_str: str) -> dict[str, Any]:
    return yaml.safe_load(Path(path_str).read_text(encoding="utf-8"))


def registry(path: Path | None = None) -> dict[str, Any]:
    """The parsed registry document (cached per path)."""
    return _load(str(path or REGISTRY_PATH))


def accepted_wires(path: Path | None = None) -> frozenset[str]:
    """Every wire the beacon accepts: exactly the `status: live` wires. THE whitelist."""
    reg = registry(path)
    return frozenset(
        e["wire"] for e in reg.get("events", ())
        if e.get("status") == "live" and isinstance(e.get("wire"), str)
    )


def envelope_v1_wires(path: Path | None = None) -> frozenset[str]:
    """Live wires that require the v1 envelope (eid + schema + closed typed meta)."""
    reg = registry(path)
    return frozenset(
        e["wire"] for e in reg.get("events", ())
        if e.get("status") == "live" and e.get("envelope") == "v1"
        and isinstance(e.get("wire"), str)
    )


def _spec_by_wire(path: Path | None = None) -> dict[str, dict[str, Any]]:
    reg = registry(path)
    return {e["wire"]: e for e in reg.get("events", ()) if isinstance(e.get("wire"), str)}


def _check_value(decl: str, value: Any, enums: dict[str, list]) -> str | None:
    """None when `value` satisfies `decl`; otherwise a short reason token."""
    decl = str(decl)
    if decl.startswith("enum:"):
        key = decl.split(":", 1)[1]
        nullable = key.endswith("|null")
        if nullable:
            key = key[: -len("|null")]
        if value is None:
            return None if nullable else "null_required_property"
        if not isinstance(value, str) or value not in enums.get(key, ()):
            return "enum_mismatch"
        return None
    if value is None:
        return "null_required_property"
    if decl == "string":
        if not isinstance(value, str):
            return "type_mismatch"
        if len(value) > _MAX_PROP_STRING:
            return "string_too_long"
        return None
    if decl == "int":
        # bool is an int subclass; a True smuggled into a count is a type error here.
        if isinstance(value, bool) or not isinstance(value, int):
            return "type_mismatch"
        return None
    if decl == "bool":
        return None if isinstance(value, bool) else "type_mismatch"
    if decl == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return "type_mismatch"
        return None
    return "unknown_declared_type"


def validate_v1_event(
    wire: str,
    eid: Any,
    schema: Any,
    meta: Any,
    path: Path | None = None,
) -> tuple[str | None, str | None]:
    """Validate one envelope-v1 event. Returns (canonical_eid, None) on acceptance or
    (None, reason) on rejection. Reasons are closed tokens (see the CA1A handoff §13):
    event_id_invalid, schema_invalid, meta_missing, undeclared_property,
    null_required_property, enum_mismatch, type_mismatch, string_too_long.
    """
    try:
        canonical = str(_uuid.UUID(str(eid)))
    except (ValueError, AttributeError, TypeError):
        return None, "event_id_invalid"
    if schema != SCHEMA_VERSION:
        return None, "schema_invalid"
    if not isinstance(meta, dict):
        return None, "meta_missing"
    spec = _spec_by_wire(path).get(wire)
    if spec is None:  # caller guarantees membership; belt-and-braces
        return None, "schema_invalid"
    props: dict[str, Any] = spec.get("properties") or {}
    enums: dict[str, list] = registry(path).get("enums") or {}
    undeclared = set(meta) - set(props)
    if undeclared:
        return None, "undeclared_property"
    for prop, decl in props.items():
        if prop not in meta:
            return None, "null_required_property"
        reason = _check_value(str(decl), meta[prop], enums)
        if reason:
            return None, reason
    return canonical, None
