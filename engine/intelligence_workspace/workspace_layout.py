"""Deterministic W2-A versioned workspace layout contract (`workspace_layout.v1`).

Frozen contract: research/DEEPVUE_W2A_WORKSPACE_LAYOUT_CONTRACT_2026-08-26.md
(as amended by Amendment A1 — `lockedVLine`/`split` real-runtime types —
Amendment A2 — Phase 6 adversarial review rulings: real-runtime grammar,
lossless-or-refuse migration, canonicalization, wire mode, fail-closed
projection, key deny-list, optional `requires`, honest provenance — and
Amendment A3 — direction-scoped lossless law (`migrate_legacy(..., strict=)`),
IEEE-754-safe number bounds, and error precedence (schema-literal, then
`requires.floor`, only then the general sweep). Amendment A3 rulings 4/5
(follow-up-read-by-id, conversion-path ABA fence) are Terminal/Postgres-side
law only — no Python artifact here carries them).

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
import copy
import hashlib
import json
import math
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
# Amendment A2 ruling 1: bounded map nesting — 64 keys per level, depth <=3
# below the per-indicator/per-symbol object inside indParams/compareCfg.
MAX_PARAM_KEYS_PER_LEVEL = 64
MAX_PARAM_NEST_DEPTH = 3
# Amendment A3 ruling 2 (number law, completes A2 ruling 4): integers bounded
# to the IEEE-754 safe range everywhere numbers occur (params, revision,
# source_revision, grid); a non-integral float is valid only within
# 1e-4 <= |x| < 1e12 — both languages' shortest-repr is exponent-free and
# digit-identical in that window, which is exactly why it was chosen.
MAX_SAFE_INT = 9007199254740991  # 2**53 - 1
MIN_NONZERO_FLOAT_MAGNITUDE = 1e-4
MAX_FLOAT_MAGNITUDE = 1e12  # exclusive upper bound

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
# Amendment A2 ruling 11: `requires` is optional (absent -> floor 1).
_REQUIRED_TOP_LEVEL_KEYS = frozenset(_TOP_LEVEL_KEYS - {"requires"})
_WIDGET_KEYS = frozenset({
    "id", "type", "semantic_lane", "grid", "context_in", "context_out", "config",
})
_GRID_KEYS = frozenset({"x", "y", "w", "h"})
_MIGRATION_KEYS = frozenset({"source", "source_revision"})
_LINK_GROUP_KEYS = frozenset({"entity_type"})

# Amendment A2 ruling 10: prototype-pollution-shaped keys are never valid
# identifiers anywhere a key/id is accepted (widget ids, link-group names,
# indParams/compareCfg identifiers and nested param keys).
_DENIED_KEYS = frozenset({"__proto__", "constructor", "prototype"})

_WIDGET_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_LINK_GROUP_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_TIMEFRAME_RE = re.compile(r"^[A-Za-z0-9]{1,8}$")
# Amendment A2 ruling 1 (real-runtime grammar, Phase 6 review):
#   symbol       — covers composite panes ("NVDA+AMD"), caret index panes
#                  ("^NDX"), and colon venue-qualified tickers ("BINANCE:BTCUSDT").
#   chart_type   — covers hyphenated chart types ("line-markers").
#   indicator_id — covers underscore-prefixed ids ("_lab").
#   param_key    — covers dotted premium-suite keys ("ob.showLast").
_SYMBOL_RE = re.compile(r"^[\^A-Z0-9.+:_-]{1,24}$")
_CHART_TYPE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_INDICATOR_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,31}$")
_PARAM_KEY_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.]{0,63}$")
# Amendment A1: 1..64 chars, no ASCII control characters (0x00-0x1f, 0x7f).
_LOCKED_VLINE_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,64}$")

# Sentinel distinguishing "field present but wrong type/shape" (never
# claimed) from a legitimately-valid `None`/`null` value (e.g. `lockedVLine`
# explicitly cleared) — a plain `None` return would be ambiguous between the
# two (contract §6 claim semantics: "ONLY claimed, correctly-typed fields").
_INVALID = object()


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_safe_int(value: Any) -> bool:
    """Amendment A3 ruling 2: an integer within the IEEE-754 safe range
    (|n| <= 2**53 - 1) — the bound applied everywhere a plain integer is
    accepted (params, revision, source_revision, grid)."""
    return _is_int(value) and abs(value) <= MAX_SAFE_INT


def _is_denied_key(key: Any) -> bool:
    return key in _DENIED_KEYS


def _is_bounded_primitive(value: Any) -> bool:
    """A data-typed leaf value: bool/safe-int/bounded-float/None, or a
    string <=64 chars. NaN/Infinity are never valid (Amendment A2 ruling 4).
    Amendment A3 ruling 2: a plain integer must be IEEE-754-safe
    (|n| <= 2**53 - 1); an integral-valued float normalizes to that same
    integer bound; a non-integral float is valid only within
    1e-4 <= |x| < 1e12 (both languages' shortest-repr is exponent-free and
    digit-identical there). No executable payloads, no non-finite or
    unbounded numerics, anywhere (contract §3)."""
    if value is None or isinstance(value, bool):
        return True
    if isinstance(value, int):
        return abs(value) <= MAX_SAFE_INT
    if isinstance(value, float):
        if not math.isfinite(value):
            return False
        if value == int(value):
            return abs(int(value)) <= MAX_SAFE_INT
        magnitude = abs(value)
        return MIN_NONZERO_FLOAT_MAGNITUDE <= magnitude < MAX_FLOAT_MAGNITUDE
    if isinstance(value, str):
        return len(value) <= 64
    return False


def _validate_param_leaf_or_nested(value: Any, remaining_depth: int) -> Any:
    """A value inside a per-indicator/per-symbol params object: either a
    bounded primitive leaf, or — while `remaining_depth` budget remains — a
    further bounded nested object whose own keys/values recurse the same
    rule (Amendment A2 ruling 1: nesting depth <=3 below the per-indicator
    object, e.g. the real `_vis` visibility-range shape)."""
    if isinstance(value, dict):
        if remaining_depth <= 0:
            return _INVALID
        if len(value) > MAX_PARAM_KEYS_PER_LEVEL:
            return _INVALID
        out: dict[str, Any] = {}
        for key, sub in value.items():
            if not isinstance(key, str) or not _PARAM_KEY_RE.match(key) or _is_denied_key(key):
                return _INVALID
            normalized = _validate_param_leaf_or_nested(sub, remaining_depth - 1)
            if normalized is _INVALID:
                return _INVALID
            out[key] = normalized
        return out
    if not _is_bounded_primitive(value):
        return _INVALID
    return value


def _validate_param_block(value: Any, *, key_pattern: "re.Pattern[str]") -> Any:
    """Shared shape for `indParams`/`compareCfg`: a bounded map of
    identifier -> bounded map of param-name -> (bounded primitive | nested
    object up to depth 3, Amendment A2 ruling 1). No executable payloads
    anywhere (contract §3); prototype-pollution-shaped keys denied at every
    level (Amendment A2 ruling 10)."""
    if not isinstance(value, dict) or len(value) > MAX_PARAM_KEYS_PER_LEVEL:
        return _INVALID
    out: dict[str, dict[str, Any]] = {}
    for key, sub in value.items():
        if not isinstance(key, str) or not key_pattern.match(key) or _is_denied_key(key):
            return _INVALID
        if not isinstance(sub, dict) or len(sub) > MAX_PARAM_KEYS_PER_LEVEL:
            return _INVALID
        sub_out: dict[str, Any] = {}
        for sub_key, sub_val in sub.items():
            if not isinstance(sub_key, str) or not _PARAM_KEY_RE.match(sub_key) or _is_denied_key(sub_key):
                return _INVALID
            normalized = _validate_param_leaf_or_nested(sub_val, MAX_PARAM_NEST_DEPTH)
            if normalized is _INVALID:
                return _INVALID
            sub_out[sub_key] = normalized
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
    """Amendment A1: `split` is Terminal's discrete pane-split selector
    (`VALID_SPLITS = {1, 2, 4}`), never a 0-100 percentage — the original
    freeze's `0..100` bound was an authoring error that would have rejected
    every real Terminal v2 layout."""
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
        if not isinstance(item, str) or not _INDICATOR_ID_RE.match(item) or _is_denied_key(item):
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
    """Amendment A1: `lockedVLine` is `string | null` in the real Terminal
    runtime (TerminalShell/ChartPanel own it as a string key), never a
    number — the original freeze's `number | null` bound would have
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
    return all(_is_safe_int(value[key]) and 0 <= value[key] <= 64 for key in _GRID_KEYS)


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


def _normalize_numeric(value: Any) -> Any:
    """Amendment A2 ruling 4 + Amendment A3 ruling 2: integral-valued floats
    normalize to `int` before canonical serialization (closes the Python
    `20.0` vs JS `20` digest split — JS has no separate float type, so this
    asymmetry is purely a Python artifact). Non-integral floats are left
    as-is (Python's shortest-round-trip `repr`, used by `json.dumps`,
    already matches JS's own shortest-repr algorithm for the general case).
    This is also the canonicalization-time BACKSTOP for the number law
    (field-level checks are the first line): raises `ValueError` on a
    non-finite float, an integer/integral-float outside the IEEE-754 safe
    range, or a non-integral float outside `1e-4 <= |x| < 1e12` — the
    caller is expected to treat any of these as `malformed_workspace`,
    never to let one escape as an uncaught crash."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INT:
            raise ValueError("integer exceeds the IEEE-754 safe range")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite float is not a valid canonical value")
        if value == int(value):
            as_int = int(value)
            if abs(as_int) > MAX_SAFE_INT:
                raise ValueError("integral float exceeds the IEEE-754 safe range")
            return as_int
        magnitude = abs(value)
        if not (MIN_NONZERO_FLOAT_MAGNITUDE <= magnitude < MAX_FLOAT_MAGNITUDE):
            raise ValueError("non-integral float outside the canonical magnitude window")
        return value
    if isinstance(value, dict):
        return {key: _normalize_numeric(sub) for key, sub in value.items()}
    if isinstance(value, list):
        return [_normalize_numeric(item) for item in value]
    return value


def _canonical_dumps(obj: Any) -> str:
    """Amendment A2 ruling 4: canonical JSON is `ensure_ascii=False,
    allow_nan=False, sort_keys=True, separators=(",", ":")`, over the
    numeric-normalized structure. Raises `ValueError`/`TypeError` on
    non-finite floats or otherwise non-serializable content — callers
    convert that into `malformed_workspace` rather than letting it escape.
    """
    normalized = _normalize_numeric(obj)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _is_normalized_name(value: Any) -> bool:
    """Wire-mode name law (Amendment A2 ruling 5/14): already trimmed, no
    internal whitespace runs collapsed away, 1..60 chars."""
    if not isinstance(value, str):
        return False
    if not (1 <= len(value) <= 60):
        return False
    if value != value.strip():
        return False
    if re.search(r"\s{2,}", value):
        return False
    return True


def _normalize_name(value: Any) -> str | None:
    """Trim + collapse internal whitespace runs + bound to 1..60 chars.
    Returns `None` when the input is not a usable name at all (not a
    string, or empty/oversized after normalization) — the caller refuses
    rather than store/echo an unusable name (Amendment A2 ruling 14)."""
    if not isinstance(value, str):
        return None
    collapsed = re.sub(r"\s+", " ", value.strip())
    if not (1 <= len(collapsed) <= 60):
        return None
    return collapsed


def validate_envelope(obj: Any, wire: bool = False) -> dict[str, Any]:
    """Validate a `workspace_layout.v1` envelope: schema shape AND the
    cross-field laws the JSON Schema alone cannot express (contract §1-§8,
    amended by A1/A2/A3).

    ``wire=False`` (default) is the STORED-row law: `name` must be `null`.
    ``wire=True`` (Amendment A2 ruling 5) is the wire/export law: `name` may
    additionally be a normalized non-null string (trim/collapse/1..60,
    ruling 14) — used to validate the read/export projection and import
    payloads, never the stored row itself.

    Amendment A3 ruling 3 (error precedence): the `schema` literal is
    checked FIRST — a mismatch returns `unsupported_schema` ALONE, before
    any other issue in the object is even inspected. `requires.floor` is
    checked SECOND — a well-formed but unsupported floor returns
    `unsupported_floor` ALONE. Only once both gates pass does the general
    structural sweep run. A future/incompatible payload therefore always
    reports a single clean signal, never a stew mixed with unrelated
    unknown-key noise.

    Returns ``{"ok": bool, "errors": [{"code": ..., "path": ...}]}``. Never
    raises — every branch is a type/membership check on already-untrusted
    input, fail-closed on anything unexpected.
    """
    if not isinstance(obj, Mapping):
        return {"ok": False, "errors": [_error("malformed_workspace", "$")]}

    # --- Ruling 3, gate 1: schema literal, alone. ---------------------------
    schema = obj.get("schema")
    if schema != SCHEMA:
        return {"ok": False, "errors": [_error("unsupported_schema", "$.schema")]}

    # --- Ruling 3, gate 2: requires.floor, alone (Amendment A2 ruling 11:
    # `requires`/`requires.floor` are optional — absent defaults to floor 1).
    # A STRUCTURALLY malformed `requires` is not "unsupported", so it is
    # remembered here and folded into the general sweep below instead of
    # short-circuiting — only a well-formed-but-too-high floor gets the
    # alone-and-immediate treatment.
    requires = obj.get("requires", {})
    requires_error: dict[str, str] | None = None
    if not isinstance(requires, Mapping) or (set(requires.keys()) - {"floor"}):
        requires_error = _error("malformed_workspace", "$.requires")
    else:
        floor = requires.get("floor", FLOOR_SUPPORTED)
        if not _is_safe_int(floor) or floor < 1:
            requires_error = _error("malformed_workspace", "$.requires.floor")
        elif floor > FLOOR_SUPPORTED:
            return {"ok": False, "errors": [_error("unsupported_floor", "$.requires.floor")]}

    # --- Gate passed: the general structural sweep. -------------------------
    errors: list[dict[str, str]] = []
    if requires_error is not None:
        errors.append(requires_error)

    for key in obj:
        if not isinstance(key, str) or key not in _TOP_LEVEL_KEYS:
            errors.append(_error("malformed_workspace", f"$.{key}"))
    for key in _REQUIRED_TOP_LEVEL_KEYS:
        if key not in obj:
            errors.append(_error("malformed_workspace", f"$.{key}"))

    revision = obj.get("revision")
    if not _is_safe_int(revision) or revision < 1:
        errors.append(_error("malformed_workspace", "$.revision"))

    name = obj.get("name")
    if wire:
        if name is not None and not _is_normalized_name(name):
            errors.append(_error("malformed_workspace", "$.name"))
    else:
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
            if (
                not isinstance(group_name, str)
                or not _LINK_GROUP_NAME_RE.match(group_name)
                or _is_denied_key(group_name)
            ):
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
        if (
            not isinstance(widget_id, str)
            or not _WIDGET_ID_RE.match(widget_id)
            or _is_denied_key(widget_id)
        ):
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
        # Amendment A2 ruling 12 + A3 ruling 2: 1 <= source_revision <= safe int.
        if source_revision is not None and (not _is_safe_int(source_revision) or source_revision < 1):
            errors.append(_error("malformed_workspace", "$.migration.source_revision"))

    try:
        canonical = _canonical_dumps(obj)
        encoded = canonical.encode("utf-8")
    except (TypeError, ValueError):
        # Amendment A2 ruling 4: NaN/Infinity anywhere in the structure, or a
        # lone UTF-16 surrogate in any string (UnicodeEncodeError is a
        # ValueError subclass), both land here as malformed, never a crash.
        errors.append(_error("malformed_workspace", "$"))
    else:
        if len(encoded) > MAX_ENVELOPE_BYTES:
            errors.append(_error("oversized_workspace", "$"))

    return {"ok": len(errors) == 0, "errors": errors}


def _recognize_legacy(config: Mapping[str, Any]) -> tuple[str, int | None] | None:
    """Contract §6 recognizer table, rows 0-2 (Amendment A2 ruling 13: honest
    provenance — `source_revision` is null unless the payload actually
    carried a valid integer `schemaVersion`; a boolean is never treated as a
    version number). Returns (source, source_revision), or None when the
    shape is not one of the recognized legacy formats."""
    has_schema_version = "schemaVersion" in config
    schema_version = config.get("schemaVersion")
    version_is_int = _is_int(schema_version)

    if "active" in config and not has_schema_version:
        return "legacy_v0", None
    if "panes" in config and (not has_schema_version or (version_is_int and schema_version == 1)):
        source_revision = 1 if (has_schema_version and version_is_int and schema_version == 1) else None
        return "chart_layout_v1", source_revision
    if has_schema_version and version_is_int and schema_version == 2:
        return "chart_layout_v2", 2
    return None


def migrate_legacy(config: Any, strict: bool = True) -> dict[str, Any]:
    """Reference migration (contract §6): recognize an inbound legacy/native
    chart-layout shape and produce the canonical `workspace_layout.v1`
    envelope, or a structured failure. Never raises.

    Claim semantics: ONLY present, correctly-typed chart fields enter the
    migrated widget config; unclaimed (ABSENT) fields are never invented.
    `sync` defaults to `True` only when the source predates v2 AND `panes`
    was claimed (verbatim contract rule) — v2 never gets an injected
    default; it owns its own `sync` value or leaves it unclaimed.

    Direction-scoped lossless law (Amendment A3 ruling 1, supersedes the
    "no third state" sentence of A2 ruling 2):

    - ``strict=True`` (the default — WRITE/IMPORT direction): lossless-or-
      refuse, exactly as A2 froze it. A field the source format OWNS but
      that fails its validator is never silently dropped — migration
      refuses outright with ``{"ok": False, "code": "invalid_widget_config"}``.
    - ``strict=False`` (READ/RENDER direction): per-field TOLERANT, mirroring
      the shipped read boundary's own documented fallbacks. A present-but-
      invalid owned field becomes no-claim (ABSENT, exactly as if it had
      never been present) instead of refusing the whole migration, and its
      canonical field name is appended to a returned ``unclaimed`` list —
      ``{"ok": True, "envelope": ..., "unclaimed": [...]}`` (empty when
      nothing was dropped). A bad field never makes a row unopenable in
      this direction; the caller MUST surface a non-empty `unclaimed` to
      the user in plain words before any subsequent save (a save is the
      WRITE direction and reverts to `strict=True`).

    The already-canonical passthrough (row 3 of the recognizer table) is
    unaffected by `strict` — an already-`workspace_layout.v1` payload either
    validates whole or refuses; there is no per-field claim concept for an
    object already in the target shape.
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
    unclaimed: list[str] = []
    for field in CHART_CONFIG_FIELDS:
        if field in config:
            normalized = _CHART_FIELD_VALIDATORS[field](config[field])
            if normalized is _INVALID:
                if strict:
                    # Lossless-or-refuse: an owned field is PRESENT but
                    # invalid — refuse loudly rather than silently omit it.
                    return {"ok": False, "code": "invalid_widget_config"}
                # Tolerant read: no-claim (absent) + named, never dropped
                # silently.
                unclaimed.append(field)
                continue
            claims[field] = normalized

    # Legacy scalar -> canonical array mappings (contract §6, v0/v1 only):
    # only applied when the canonical array field was not already directly
    # claimed above, and never for v2 (which owns `panes`/`paneTfs` natively
    # and never carried the singular `active`/`tf` legacy keys). Same
    # direction-scoped lossless law applies to these legacy-named owned
    # fields.
    if version < 2 and "panes" not in claims and "active" in config:
        raw_active = config["active"]
        normalized = _v_panes([raw_active]) if isinstance(raw_active, str) else _INVALID
        if normalized is _INVALID:
            if strict:
                return {"ok": False, "code": "invalid_widget_config"}
            if "panes" not in unclaimed:
                unclaimed.append("panes")
        else:
            claims["panes"] = normalized
    if version < 2 and "paneTfs" not in claims and "tf" in config:
        raw_tf = config["tf"]
        normalized = _v_pane_tfs([raw_tf]) if isinstance(raw_tf, str) else _INVALID
        if normalized is _INVALID:
            if strict:
                return {"ok": False, "code": "invalid_widget_config"}
            if "paneTfs" not in unclaimed:
                unclaimed.append("paneTfs")
        else:
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
    if strict:
        return {"ok": True, "envelope": envelope}
    return {"ok": True, "envelope": envelope, "unclaimed": unclaimed}


def subscriber_safe_projection(envelope: Any, row_name: Any) -> dict[str, Any]:
    """Read/export projection of a stored envelope with `name` filled from
    the owning row (contract §5/§11, amended by A2 rulings 6/14).

    FAIL-CLOSED (ruling 6): the input is first validated in STORED mode
    (`wire=False` — the stored row's own `name` must be `null`). ANY
    failure returns ``{"ok": False, "code": ...}`` — the payload is never
    rewritten, downgraded, or partially projected; a blocked row's export
    is the caller's problem to solve some other way (Terminal exports the
    raw stored bytes instead), never this function's job to paper over.

    On success the output is the input 1:1 plus a NORMALIZED `name`
    (trim/collapse whitespace, 1..60 chars, ruling 14) — an unnormalizable
    `row_name` (not a string, or empty/oversized after normalization) is
    itself a refusal (`malformed_workspace`), never a silent blank/garbled
    echo. Because the input already passed strict stored-mode validation,
    the output is wire-valid (`validate_envelope(..., wire=True)`) by
    construction — no unknown key can have been present to smuggle through.
    """
    stored = validate_envelope(envelope, wire=False)
    if not stored["ok"]:
        return {"ok": False, "code": stored["errors"][0]["code"]}

    normalized_name = _normalize_name(row_name)
    if normalized_name is None:
        return {"ok": False, "code": "malformed_workspace"}

    projected = copy.deepcopy(dict(envelope))
    projected["name"] = normalized_name
    return {"ok": True, "envelope": projected}


def envelope_digest(envelope: Any) -> str:
    """SHA-256 over the canonical (sorted-key, compact, numeric-normalized)
    JSON serialization — the digest used to pin golden vectors and to prove
    Terminal's TS mirror byte-identical (contract §10). Never raises: an
    undigestable structure (non-finite float, lone surrogate) still returns
    a stable 64-char hex string rather than crashing — callers are expected
    to validate with `validate_envelope` first."""
    try:
        canonical = _canonical_dumps(envelope)
        encoded = canonical.encode("utf-8")
    except (TypeError, ValueError):
        encoded = b"\x00invalid-envelope"
    return hashlib.sha256(encoded).hexdigest()


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
    "MAX_PARAM_KEYS_PER_LEVEL",
    "MAX_PARAM_NEST_DEPTH",
    "CHART_CONFIG_FIELDS",
    "validate_envelope",
    "migrate_legacy",
    "subscriber_safe_projection",
    "envelope_digest",
]
