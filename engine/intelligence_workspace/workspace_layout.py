"""Deterministic W2-A versioned workspace layout contract (`workspace_layout.v1`).

Frozen contract: research/DEEPVUE_W2A_WORKSPACE_LAYOUT_CONTRACT_2026-08-26.md.

This module is Macro's OWNED half of the W2-A ownership split (contract §10):
the frozen vocabularies, a pure structural+cross-field validator, a reference
migration from the recognized legacy chart-layout shapes, a subscriber-safe
export projection, and a canonical digest helper. It performs NO I/O, NO
network, and holds no mutable state — every function is a pure transform of
its arguments, safe to call on hostile input without raising.

Terminal owns the TypeScript equivalents (`workspaceLayout.ts`,
`workspaceMigrate.ts`) and proves them against the SAME golden vectors this
module generates (`contracts/intelligence_workspace/fixtures/
workspace_migration/*.json`, digest-pinned in both repos — the W1-C parity
mechanism, contract §10).

This module never stores, serves, or persists a Terminal user's workspace; it
has no runtime coupling to `chart_layouts` or any HTTP route.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import re
from typing import Any

SCHEMA = "workspace_layout.v1"

# --- frozen vocabularies (contract §1-§8) -----------------------------------

WIDGET_TYPES = ("chart", "brain")
SEMANTIC_LANES = ("primary", "secondary", "rail", "dock")
ENTITY_TYPES = ("security", "industry", "theme", "portfolio", "event")
MIGRATION_SOURCES = ("legacy_v0", "chart_layout_v1", "chart_layout_v2", "none", "import")

# The complete frozen failure vocabulary (contract §8) — 16 codes, no more,
# no fewer. `validate_envelope`/`migrate_legacy` never return a code outside
# this tuple.
FAILURE_CODES = (
    "malformed_workspace", "unsupported_schema", "unsupported_floor",
    "unknown_widget_type", "invalid_widget_config", "duplicate_widget_id",
    "invalid_lane", "invalid_port", "name_conflict", "stale_revision",
    "store_unavailable", "unauthenticated", "not_found", "invalid_import",
    "oversized_workspace", "too_many_widgets",
)

# --- frozen limits (contract §3) --------------------------------------------

MAX_WIDGETS = 12
MAX_ENVELOPE_BYTES = 65536
MAX_LINK_GROUPS = 8
MAX_PORTS = 8
FLOOR_SUPPORTED = 1

# The 12 chart-config fields owned verbatim by the existing Terminal
# chart-layout contract (contract §2). Order is the frozen canonical order
# used by `envelope_digest`-adjacent tooling and the freeze doc's §1 example;
# it carries no schema meaning (the schema/dict itself is unordered).
CHART_CONFIG_FIELDS = (
    "panes", "paneTfs", "split", "activePane", "sync", "chartType",
    "inds", "indParams", "hidden", "compare", "compareCfg", "lockedVLine",
)

_TOP_LEVEL_KEYS = frozenset({
    "schema", "requires", "revision", "name", "link_groups", "widgets", "migration",
})
_WIDGET_KEYS = frozenset({
    "id", "type", "semantic_lane", "grid", "context_in", "context_out", "config",
})
_GRID_KEYS = frozenset({"x", "y", "w", "h"})
_MIGRATION_KEYS = frozenset({"source", "source_revision"})
_LINK_GROUP_KEYS = frozenset({"entity_type"})

_WIDGET_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_LINK_GROUP_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_SYMBOL_RE = re.compile(r"^[A-Z0-9._:-]{1,12}$")
_TIMEFRAME_RE = re.compile(r"^[A-Za-z0-9]{1,8}$")
_CHART_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_INDICATOR_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_PARAM_KEY_RE = re.compile(r"^[A-Za-z0-9_]{1,32}$")
# Amendment A1: 1..64 chars, no ASCII control characters (0x00-0x1f, 0x7f).
_LOCKED_VLINE_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,64}$")

# Sentinel distinguishing "field present but wrong type/shape" (never
# claimed) from a legitimately-valid `None`/`null` value (e.g. `lockedVLine`
# explicitly cleared) — a plain `None` return would be ambiguous between the
# two (contract §6 claim semantics: "ONLY claimed, correctly-typed fields").
_INVALID = object()


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_bounded_primitive(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        return len(value) <= 64
    return False


def _validate_param_block(value: Any, *, key_pattern: "re.Pattern[str]") -> Any:
    """Shared shape for `indParams`/`compareCfg`: a bounded map of
    identifier -> bounded map of param-name -> data-typed primitive. No
    executable payloads anywhere (contract §3)."""
    if not isinstance(value, dict) or len(value) > 32:
        return _INVALID
    out: dict[str, dict[str, Any]] = {}
    for key, sub in value.items():
        if not isinstance(key, str) or not key_pattern.match(key):
            return _INVALID
        if not isinstance(sub, dict) or len(sub) > 16:
            return _INVALID
        sub_out: dict[str, Any] = {}
        for sub_key, sub_val in sub.items():
            if not isinstance(sub_key, str) or not _PARAM_KEY_RE.match(sub_key):
                return _INVALID
            if not _is_bounded_primitive(sub_val):
                return _INVALID
            sub_out[sub_key] = sub_val
        out[key] = sub_out
    return out


def _v_panes(value: Any) -> Any:
    if not isinstance(value, list) or not (1 <= len(value) <= 4):
        return _INVALID
    out = []
    for item in value:
        if not isinstance(item, str) or not _SYMBOL_RE.match(item):
            return _INVALID
        out.append(item)
    return out


def _v_pane_tfs(value: Any) -> Any:
    if not isinstance(value, list) or not (1 <= len(value) <= 32):
        return _INVALID
    out = []
    for item in value:
        if not isinstance(item, str) or not _TIMEFRAME_RE.match(item):
            return _INVALID
        out.append(item)
    return out


_VALID_SPLITS = (1, 2, 4)


def _v_split(value: Any) -> Any:
    """Amendment A1 (2026-08-26): `split` is Terminal's discrete pane-split
    selector (`VALID_SPLITS = {1, 2, 4}`), never a 0-100 percentage — the
    original freeze's `0..100` bound was an authoring error that would have
    rejected every real Terminal v2 layout."""
    if not _is_int(value) or value not in _VALID_SPLITS:
        return _INVALID
    return value


def _v_active_pane(value: Any) -> Any:
    if not _is_int(value) or not (0 <= value <= 3):
        return _INVALID
    return value


def _v_sync(value: Any) -> Any:
    if not isinstance(value, bool):
        return _INVALID
    return value


def _v_chart_type(value: Any) -> Any:
    if not isinstance(value, str) or not _CHART_TYPE_RE.match(value):
        return _INVALID
    return value


def _v_inds(value: Any) -> Any:
    if not isinstance(value, list) or len(value) > 32:
        return _INVALID
    out = []
    for item in value:
        if not isinstance(item, str) or not _INDICATOR_ID_RE.match(item):
            return _INVALID
        out.append(item)
    return out


def _v_ind_params(value: Any) -> Any:
    return _validate_param_block(value, key_pattern=_INDICATOR_ID_RE)


def _v_hidden(value: Any) -> Any:
    return _v_inds(value)


def _v_compare(value: Any) -> Any:
    if not isinstance(value, list) or len(value) > 32:
        return _INVALID
    out = []
    for item in value:
        if not isinstance(item, str) or not _SYMBOL_RE.match(item):
            return _INVALID
        out.append(item)
    return out


def _v_compare_cfg(value: Any) -> Any:
    return _validate_param_block(value, key_pattern=_SYMBOL_RE)


def _v_locked_vline(value: Any) -> Any:
    """Amendment A1 (2026-08-26): `lockedVLine` is `string | null` in the
    real Terminal runtime (TerminalShell/ChartPanel own it as a string key),
    never a number — the original freeze's `number | null` bound would have
    rejected every real Terminal v2 layout that used it."""
    if value is None:
        return None
    if not isinstance(value, str):
        return _INVALID
    if not _LOCKED_VLINE_RE.match(value):
        return _INVALID
    return value


_CHART_FIELD_VALIDATORS: dict[str, Any] = {
    "panes": _v_panes,
    "paneTfs": _v_pane_tfs,
    "split": _v_split,
    "activePane": _v_active_pane,
    "sync": _v_sync,
    "chartType": _v_chart_type,
    "inds": _v_inds,
    "indParams": _v_ind_params,
    "hidden": _v_hidden,
    "compare": _v_compare,
    "compareCfg": _v_compare_cfg,
    "lockedVLine": _v_locked_vline,
}


def _error(code: str, path: str) -> dict[str, str]:
    assert code in FAILURE_CODES  # never emit a code outside the frozen vocabulary
    return {"code": code, "path": path}


def _validate_grid(value: Any) -> bool:
    if not isinstance(value, dict) or set(value.keys()) != _GRID_KEYS:
        return False
    return all(_is_int(value[key]) and 0 <= value[key] <= 64 for key in _GRID_KEYS)


def _validate_widget_config(widget_type: Any, config: Any, *, path: str) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if widget_type == "brain":
        if config != {}:
            errors.append(_error("invalid_widget_config", path))
        return errors
    if widget_type == "chart":
        if not isinstance(config, dict):
            errors.append(_error("invalid_widget_config", path))
            return errors
        for key in config:
            if key not in CHART_CONFIG_FIELDS:
                errors.append(_error("invalid_widget_config", f"{path}.{key}"))
        for field, raw in config.items():
            validator = _CHART_FIELD_VALIDATORS.get(field)
            if validator is None:
                continue  # already reported as an unknown key above
            if validator(raw) is _INVALID:
                errors.append(_error("invalid_widget_config", f"{path}.{field}"))
        return errors
    # Unknown widget type: `unknown_widget_type` is reported by the caller;
    # config shape is not independently meaningful for an unrecognized type.
    if not isinstance(config, dict):
        errors.append(_error("invalid_widget_config", path))
    return errors


def validate_envelope(obj: Any) -> dict[str, Any]:
    """Validate a `workspace_layout.v1` envelope: schema shape AND the
    cross-field laws the JSON Schema alone cannot express (contract §1-§8).

    Returns ``{"ok": bool, "errors": [{"code": ..., "path": ...}]}``. Never
    raises — every branch is a type/membership check on already-untrusted
    input, fail-closed on anything unexpected.
    """
    errors: list[dict[str, str]] = []

    if not isinstance(obj, Mapping):
        return {"ok": False, "errors": [_error("malformed_workspace", "$")]}

    for key in obj:
        if not isinstance(key, str) or key not in _TOP_LEVEL_KEYS:
            errors.append(_error("malformed_workspace", f"$.{key}"))
    for key in _TOP_LEVEL_KEYS:
        if key not in obj:
            errors.append(_error("malformed_workspace", f"$.{key}"))

    schema = obj.get("schema")
    if schema != SCHEMA:
        errors.append(_error("unsupported_schema", "$.schema"))
        # Nothing else here is safe to interpret as a workspace_layout.v1
        # object once the schema tag itself disagrees.
        return {"ok": False, "errors": errors}

    requires = obj.get("requires")
    if not isinstance(requires, Mapping) or set(requires.keys()) != {"floor"}:
        errors.append(_error("malformed_workspace", "$.requires"))
    else:
        floor = requires.get("floor")
        if not _is_int(floor) or floor < 1:
            errors.append(_error("malformed_workspace", "$.requires.floor"))
        elif floor > FLOOR_SUPPORTED:
            errors.append(_error("unsupported_floor", "$.requires.floor"))

    revision = obj.get("revision")
    if not _is_int(revision) or revision < 1:
        errors.append(_error("malformed_workspace", "$.revision"))

    name = obj.get("name")
    if name is not None:
        errors.append(_error("malformed_workspace", "$.name"))

    link_groups = obj.get("link_groups")
    declared_groups: set[str] = set()
    if not isinstance(link_groups, Mapping):
        errors.append(_error("malformed_workspace", "$.link_groups"))
    else:
        if len(link_groups) > MAX_LINK_GROUPS:
            errors.append(_error("malformed_workspace", "$.link_groups"))
        for group_name, group in link_groups.items():
            if not isinstance(group_name, str) or not _LINK_GROUP_NAME_RE.match(group_name):
                errors.append(_error("malformed_workspace", f"$.link_groups.{group_name!r}"))
                continue
            declared_groups.add(group_name)
            if not isinstance(group, Mapping) or set(group.keys()) != _LINK_GROUP_KEYS:
                errors.append(_error("malformed_workspace", f"$.link_groups.{group_name}"))
                continue
            if group.get("entity_type") not in ENTITY_TYPES:
                errors.append(_error("malformed_workspace", f"$.link_groups.{group_name}.entity_type"))

    widgets = obj.get("widgets")
    if not isinstance(widgets, list):
        errors.append(_error("malformed_workspace", "$.widgets"))
        widgets = []
    elif len(widgets) > MAX_WIDGETS:
        errors.append(_error("too_many_widgets", "$.widgets"))
    elif len(widgets) < 1:
        errors.append(_error("malformed_workspace", "$.widgets"))

    seen_ids: set[str] = set()
    for index, widget in enumerate(widgets):
        path = f"$.widgets[{index}]"
        if not isinstance(widget, Mapping):
            errors.append(_error("invalid_widget_config", path))
            continue
        for key in widget:
            if key not in _WIDGET_KEYS:
                errors.append(_error("invalid_widget_config", f"{path}.{key}"))
        for key in ("id", "type", "semantic_lane", "context_in", "context_out", "config"):
            if key not in widget:
                errors.append(_error("invalid_widget_config", f"{path}.{key}"))

        widget_id = widget.get("id")
        if not isinstance(widget_id, str) or not _WIDGET_ID_RE.match(widget_id):
            errors.append(_error("invalid_widget_config", f"{path}.id"))
        else:
            if widget_id in seen_ids:
                errors.append(_error("duplicate_widget_id", f"{path}.id"))
            seen_ids.add(widget_id)

        widget_type = widget.get("type")
        if widget_type not in WIDGET_TYPES:
            errors.append(_error("unknown_widget_type", f"{path}.type"))

        lane = widget.get("semantic_lane")
        if lane not in SEMANTIC_LANES:
            errors.append(_error("invalid_lane", f"{path}.semantic_lane"))

        if "grid" in widget and not _validate_grid(widget.get("grid")):
            errors.append(_error("invalid_widget_config", f"{path}.grid"))

        for port_key in ("context_in", "context_out"):
            ports = widget.get(port_key)
            if not isinstance(ports, list) or len(ports) > MAX_PORTS:
                errors.append(_error("invalid_widget_config", f"{path}.{port_key}"))
                continue
            for port_index, group_name in enumerate(ports):
                if not isinstance(group_name, str) or not _LINK_GROUP_NAME_RE.match(group_name):
                    errors.append(_error("invalid_port", f"{path}.{port_key}[{port_index}]"))
                elif group_name not in declared_groups:
                    errors.append(_error("invalid_port", f"{path}.{port_key}[{port_index}]"))

        if widget_type in WIDGET_TYPES:
            errors.extend(_validate_widget_config(widget_type, widget.get("config"), path=f"{path}.config"))

    migration = obj.get("migration")
    if not isinstance(migration, Mapping) or set(migration.keys()) != _MIGRATION_KEYS:
        errors.append(_error("malformed_workspace", "$.migration"))
    else:
        source = migration.get("source")
        if source not in MIGRATION_SOURCES:
            errors.append(_error("malformed_workspace", "$.migration.source"))
        source_revision = migration.get("source_revision")
        if source_revision is not None and not _is_int(source_revision):
            errors.append(_error("malformed_workspace", "$.migration.source_revision"))

    try:
        canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except (TypeError, ValueError):
        errors.append(_error("malformed_workspace", "$"))
    else:
        if len(canonical.encode("utf-8")) > MAX_ENVELOPE_BYTES:
            errors.append(_error("oversized_workspace", "$"))

    return {"ok": len(errors) == 0, "errors": errors}


def _recognize_legacy(config: Mapping[str, Any]) -> tuple[str, int | None] | None:
    """Contract §6 recognizer table, rows 0-2. Returns (source, source_revision)
    or None when the shape is not one of the recognized legacy formats."""
    has_schema_version = "schemaVersion" in config
    schema_version = config.get("schemaVersion")

    if "active" in config and not has_schema_version:
        return "legacy_v0", None
    if "panes" in config and (not has_schema_version or schema_version == 1):
        return "chart_layout_v1", 1
    if has_schema_version and schema_version == 2:
        return "chart_layout_v2", 2
    return None


def migrate_legacy(config: Any) -> dict[str, Any]:
    """Reference migration (contract §6): recognize an inbound legacy/native
    chart-layout shape and produce the canonical `workspace_layout.v1`
    envelope, or a structured failure. Never raises.

    Claim semantics: ONLY present, correctly-typed chart fields enter the
    migrated widget config; unclaimed fields are ABSENT (never null, never
    invented). `sync` defaults to `True` only when the source predates v2
    AND `panes` was claimed (verbatim contract rule) — v2 never gets an
    injected default; it owns its own `sync` value or leaves it unclaimed.
    """
    if not isinstance(config, Mapping):
        return {"ok": False, "code": "malformed_workspace"}

    if config.get("schema") == SCHEMA:
        # Row 3: already-canonical — passes through validation unchanged.
        result = validate_envelope(config)
        if result["ok"]:
            return {"ok": True, "envelope": dict(config)}
        return {"ok": False, "code": result["errors"][0]["code"]}

    recognized = _recognize_legacy(config)
    if recognized is None:
        return {"ok": False, "code": "unsupported_schema"}
    source, source_revision = recognized
    version = {"legacy_v0": 0, "chart_layout_v1": 1, "chart_layout_v2": 2}[source]

    claims: dict[str, Any] = {}
    for field in CHART_CONFIG_FIELDS:
        if field in config:
            normalized = _CHART_FIELD_VALIDATORS[field](config[field])
            if normalized is not _INVALID:
                claims[field] = normalized

    # Legacy scalar -> canonical array mappings (contract §6, v0/v1 only):
    # only applied when the canonical array field was not already directly
    # claimed above, and never for v2 (which owns `panes`/`paneTfs` natively
    # and never carried the singular `active`/`tf` legacy keys).
    if version < 2 and "panes" not in claims and isinstance(config.get("active"), str):
        normalized = _v_panes([config["active"]])
        if normalized is not _INVALID:
            claims["panes"] = normalized
    if version < 2 and "paneTfs" not in claims and isinstance(config.get("tf"), str):
        normalized = _v_pane_tfs([config["tf"]])
        if normalized is not _INVALID:
            claims["paneTfs"] = normalized

    # sync defaults true ONLY when version<2 AND panes claimed (verbatim).
    if version < 2 and "panes" in claims and "sync" not in claims:
        claims["sync"] = True

    envelope: dict[str, Any] = {
        "schema": SCHEMA,
        "requires": {"floor": FLOOR_SUPPORTED},
        "revision": 1,
        "name": None,
        "link_groups": {"primary_security": {"entity_type": "security"}},
        "widgets": [
            {
                "id": "chart-main",
                "type": "chart",
                "semantic_lane": "primary",
                "context_in": ["primary_security"],
                "context_out": ["primary_security"],
                "config": claims,
            },
        ],
        "migration": {"source": source, "source_revision": source_revision},
    }
    return {"ok": True, "envelope": envelope}


def _project_ports(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw[:MAX_PORTS]:
        if isinstance(item, str) and _LINK_GROUP_NAME_RE.match(item):
            out.append(item)
    return out


def _project_widget(widget: Any) -> dict[str, Any] | None:
    if not isinstance(widget, Mapping):
        return None
    widget_id = widget.get("id")
    if not isinstance(widget_id, str) or not _WIDGET_ID_RE.match(widget_id):
        return None
    widget_type = widget.get("type")
    if widget_type not in WIDGET_TYPES:
        return None
    lane = widget.get("semantic_lane")
    if lane not in SEMANTIC_LANES:
        return None

    config_raw = widget.get("config")
    config: dict[str, Any] = {}
    if widget_type == "chart" and isinstance(config_raw, Mapping):
        for field in CHART_CONFIG_FIELDS:
            if field in config_raw:
                normalized = _CHART_FIELD_VALIDATORS[field](config_raw[field])
                if normalized is not _INVALID:
                    config[field] = normalized

    out: dict[str, Any] = {
        "id": widget_id,
        "type": widget_type,
        "semantic_lane": lane,
        "context_in": _project_ports(widget.get("context_in")),
        "context_out": _project_ports(widget.get("context_out")),
        "config": config,
    }
    grid_raw = widget.get("grid")
    if _validate_grid(grid_raw):
        out["grid"] = {key: grid_raw[key] for key in ("x", "y", "w", "h")}
    return out


def subscriber_safe_projection(envelope: Any, row_name: Any) -> dict[str, Any]:
    """Rebuild the wire/export projection of a stored envelope with `name`
    filled from the owning row (contract §5/§11). Rebuilt entirely from
    schema-known fields — an unknown top-level, widget-level, or nested key
    injected into `envelope` cannot ride through, and no row uuid/user id/
    path is ever consulted or echoed (this function never receives them).
    """
    envelope = envelope if isinstance(envelope, Mapping) else {}

    requires_raw = envelope.get("requires")
    floor = requires_raw.get("floor") if isinstance(requires_raw, Mapping) else None
    if not _is_int(floor) or floor < 1:
        floor = FLOOR_SUPPORTED

    revision = envelope.get("revision")
    if not _is_int(revision) or revision < 1:
        revision = 1

    link_groups: dict[str, Any] = {}
    raw_groups = envelope.get("link_groups")
    if isinstance(raw_groups, Mapping):
        for group_name, group in raw_groups.items():
            if not isinstance(group_name, str) or not _LINK_GROUP_NAME_RE.match(group_name):
                continue
            if len(link_groups) >= MAX_LINK_GROUPS:
                break
            if not isinstance(group, Mapping):
                continue
            entity_type = group.get("entity_type")
            if entity_type in ENTITY_TYPES:
                link_groups[group_name] = {"entity_type": entity_type}

    widgets: list[dict[str, Any]] = []
    raw_widgets = envelope.get("widgets")
    if isinstance(raw_widgets, list):
        for widget in raw_widgets[:MAX_WIDGETS]:
            projected = _project_widget(widget)
            if projected is not None:
                widgets.append(projected)

    migration = {"source": "none", "source_revision": None}
    raw_migration = envelope.get("migration")
    if isinstance(raw_migration, Mapping):
        source = raw_migration.get("source")
        if source in MIGRATION_SOURCES:
            migration["source"] = source
        source_revision = raw_migration.get("source_revision")
        if source_revision is None or _is_int(source_revision):
            migration["source_revision"] = source_revision

    name = row_name if isinstance(row_name, str) and row_name else None

    return {
        "schema": SCHEMA,
        "requires": {"floor": floor},
        "revision": revision,
        "name": name,
        "link_groups": link_groups,
        "widgets": widgets,
        "migration": migration,
    }


def envelope_digest(envelope: Any) -> str:
    """SHA-256 over the canonical (sorted-key, compact) JSON serialization —
    the digest used to pin golden vectors and to prove Terminal's TS mirror
    byte-identical (contract §10)."""
    canonical = json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "SCHEMA",
    "WIDGET_TYPES",
    "SEMANTIC_LANES",
    "ENTITY_TYPES",
    "MIGRATION_SOURCES",
    "FAILURE_CODES",
    "MAX_WIDGETS",
    "MAX_ENVELOPE_BYTES",
    "MAX_LINK_GROUPS",
    "MAX_PORTS",
    "FLOOR_SUPPORTED",
    "CHART_CONFIG_FIELDS",
    "validate_envelope",
    "migrate_legacy",
    "subscriber_safe_projection",
    "envelope_digest",
]
