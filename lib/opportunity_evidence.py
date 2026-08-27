"""K3-E Opportunity Evidence Vector — semantic validator + deterministic composer.

This module is a VIEW/JOIN executor over the two frozen contract files:

    contracts/opportunity_evidence/vector.v1.schema.json
    contracts/opportunity_evidence/slot_registry.v1.json

It is never a store: nothing here writes to disk, opens a file for writing,
creates a directory, or persists any output. ``compose_vector`` builds a
vector purely in memory and returns it; the caller decides what (if anything)
to do with the result.

Dependency-minimal by law (see the K3-E build commission): stdlib only. No
``yaml``, ``pandas``, ``jsonschema`` or ``engine`` imports live in this
module. A hand-rolled structural checker (``_validate_node``) implements the
subset of JSON Schema draft 2020-12 the frozen wire schema actually uses
(type, const, enum, pattern, min/maxLength, min/maxItems, minimum/maximum,
required, additionalProperties, $ref/$defs, oneOf, allOf-with-if/then/else)
rather than adding a third-party dependency.

Public surface:

    load_vector_schema() / load_slot_registry()
        Repository-canonical contract loaders. No caller-supplied path
        override — callers always validate against the frozen files this
        repo ships, mirroring the K1 Evidence Foundation's no-vocabulary-
        injection law.

    validate_vector(vector) -> list[Finding]
        Structural (schema) + semantic (K3E_R0xx) validation. Fail-closed:
        unknown anything is a Finding, never a silent pass.

    compose_vector(subject, asof, slots, economic_cause_hypothesis=None, ...)
        Deterministic in-memory composition. Same input -> byte-identical
        output (content_sha256 included).
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import itertools
import json
from pathlib import Path
import re
from typing import Any, NamedTuple

# ---------------------------------------------------------------------------
# Contract locations (repo-canonical; never overridable by a caller).
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONTRACT_DIR = _REPO_ROOT / "contracts" / "opportunity_evidence"
_VECTOR_SCHEMA_PATH = _CONTRACT_DIR / "vector.v1.schema.json"
_SLOT_REGISTRY_PATH = _CONTRACT_DIR / "slot_registry.v1.json"


class OpportunityEvidenceError(Exception):
    """Raised only for programmer errors (e.g. malformed caller input to
    compose_vector). Never raised by validate_vector — that function always
    returns findings instead of raising, so a fail-closed caller can inspect
    every defect in one pass."""


@lru_cache(maxsize=1)
def load_vector_schema() -> dict:
    """Load contracts/opportunity_evidence/vector.v1.schema.json. No path
    override parameter exists on this public function by design."""

    return json.loads(_VECTOR_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_slot_registry() -> dict:
    """Load contracts/opportunity_evidence/slot_registry.v1.json. No path
    override parameter exists on this public function by design."""

    return json.loads(_SLOT_REGISTRY_PATH.read_text(encoding="utf-8"))


class Finding(NamedTuple):
    code: str
    path: str
    message: str


def _f(code: str, path: str, message: str) -> Finding:
    return Finding(code=code, path=path, message=message)


# ---------------------------------------------------------------------------
# Minimal in-module JSON-Schema structural checker (draft 2020-12 subset).
# ---------------------------------------------------------------------------

_TYPE_MAP = {"object": dict, "array": list, "string": str, "boolean": bool}


def _check_type(value: Any, type_spec: Any) -> bool:
    types = type_spec if isinstance(type_spec, list) else [type_spec]
    for t in types:
        if t == "null":
            if value is None:
                return True
        elif t == "integer":
            if isinstance(value, int) and not isinstance(value, bool):
                return True
        elif t == "number":
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return True
        elif t == "boolean":
            if isinstance(value, bool):
                return True
        else:
            py = _TYPE_MAP.get(t)
            if py is dict and isinstance(value, dict):
                return True
            if py is list and isinstance(value, list):
                return True
            if py is str and isinstance(value, str):
                return True
    return False


def _pattern_matches(pattern: str, value: str) -> bool:
    """Match a JSON-Schema `pattern` the way JSON Schema means it.

    A pattern anchored `^...$` is matched end-to-end: Python's `$` also matches
    immediately before a trailing newline, which let `"IMXI\\n"` satisfy K1's
    explicitly newline-free `^[^\\r\\n]+$` (red-team MINOR 10, 2026-08-25).
    Unanchored patterns keep `search` semantics."""

    if pattern.startswith("^") and pattern.endswith("$"):
        return re.fullmatch(pattern[1:-1], value, flags=re.DOTALL) is not None
    return re.search(pattern, value) is not None


def _resolve(schema: dict, defs: dict) -> dict:
    if isinstance(schema, dict) and "$ref" in schema:
        ref = schema["$ref"]
        prefix = "#/$defs/"
        if not ref.startswith(prefix):
            raise OpportunityEvidenceError(f"unsupported $ref shape: {ref!r}")
        return defs[ref[len(prefix):]]
    return schema


def _validate_node(instance: Any, schema: dict, defs: dict, path: str) -> list[tuple[str, str, str]]:
    schema = _resolve(schema, defs)
    errors: list[tuple[str, str, str]] = []

    if "oneOf" in schema:
        matched = 0
        for sub in schema["oneOf"]:
            if not _validate_node(instance, sub, defs, path):
                matched += 1
        if matched != 1:
            errors.append((path, f"{matched} of {len(schema['oneOf'])} oneOf branches matched", "oneOf"))
        return errors

    if "type" in schema:
        if not _check_type(instance, schema["type"]):
            errors.append((path, f"expected type {schema['type']!r}, got {type(instance).__name__}", "type"))
            return errors

    if "const" in schema:
        if instance != schema["const"]:
            errors.append((path, f"expected const {schema['const']!r}, got {instance!r}", "const"))

    if "enum" in schema:
        if instance not in schema["enum"]:
            errors.append((path, f"value {instance!r} not in enum {schema['enum']!r}", "enum"))

    if isinstance(instance, str):
        # MINOR 10 (red-team 2026-08-25): Python's `$` also matches just before a
        # trailing newline, unlike the ECMA-262 `$` JSON Schema is defined
        # against — so "IMXI\n" satisfied K1's no-newline `^[^\r\n]+$`. Anchored
        # patterns are matched end-to-end instead.
        if "pattern" in schema and _pattern_matches(schema["pattern"], instance) is False:
            errors.append((path, f"value {instance!r} does not match pattern {schema['pattern']!r}", "pattern"))
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append((path, "string shorter than minLength", "minLength"))
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append((path, "string longer than maxLength", "maxLength"))

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append((path, "value below minimum", "minimum"))
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append((path, "value above maximum", "maximum"))

    if isinstance(instance, dict):
        props = schema.get("properties", {})
        for req in schema.get("required", []):
            if req not in instance:
                errors.append((f"{path}.{req}", "missing required property", "required"))
        additional = schema.get("additionalProperties", True)
        for key, val in instance.items():
            if key in props:
                errors.extend(_validate_node(val, props[key], defs, f"{path}.{key}"))
            elif additional is False:
                errors.append((f"{path}.{key}", f"unknown property {key!r} (additionalProperties: false)", "additionalProperties"))
            elif isinstance(additional, dict):
                errors.extend(_validate_node(val, additional, defs, f"{path}.{key}"))
        if "minProperties" in schema and len(instance) < schema["minProperties"]:
            errors.append((path, "fewer than minProperties", "minProperties"))
        if "maxProperties" in schema and len(instance) > schema["maxProperties"]:
            errors.append((path, "more than maxProperties", "maxProperties"))

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append((path, "fewer than minItems", "minItems"))
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append((path, "more than maxItems", "maxItems"))
        if schema.get("uniqueItems"):
            seen: list[Any] = []
            for item in instance:
                if item in seen:
                    errors.append((path, "duplicate item violates uniqueItems", "uniqueItems"))
                    break
                seen.append(item)
        if "items" in schema:
            for i, item in enumerate(instance):
                errors.extend(_validate_node(item, schema["items"], defs, f"{path}[{i}]"))

    if "allOf" in schema:
        for sub in schema["allOf"]:
            if "if" in sub:
                matches = not _validate_node(instance, sub["if"], defs, path)
                branch = sub.get("then") if matches else sub.get("else")
                if branch is not None:
                    errors.extend(_validate_node(instance, branch, defs, path))
            else:
                errors.extend(_validate_node(instance, sub, defs, path))

    return errors


def _schema_findings(vector: dict) -> list[Finding]:
    schema = load_vector_schema()
    defs = schema.get("$defs", {})
    raw = _validate_node(vector, schema, defs, "$")
    return [Finding(f"K3E_SCHEMA_{keyword.upper()}", path, message) for path, message, keyword in raw]


# ---------------------------------------------------------------------------
# Registry-driven constants.
# ---------------------------------------------------------------------------

_DISLOC_RE = re.compile(r"^disloc\.(?P<term>[a-z0-9_]+)\.(?P<window>\d+d)$")

_AUTHORITY_ENVELOPE = {
    "can_rank": False,
    "can_gate": False,
    "can_size": False,
    "can_originate": False,
    "can_open_entry": False,
}

_SLOT_STATE_TO_LEG_STATE = {
    "observed": "observed",
    # R-7 red-team repair (2026-08-25): a leg fed by a modeled slot (e.g. GEX /
    # dealer gamma) is "modeled", never "observed" — the schema's incorporation
    # leg state enum now carries "modeled" precisely so this distinction
    # survives projection instead of being laundered into "observed".
    "modeled": "modeled",
    "missing": "missing",
    "stale": "stale",
    "rights_blocked": "rights_blocked",
    "conflicted": "conflicted",
    "unsupported": "unknown",
    "identity_unresolved": "identity_unresolved",
    "unknown": "unknown",
}

_MARKET_REFLECTION_MAP = {
    "I1_anticipation": None,
    "I2_immediate_response": "drl_resid_shock",
    "I3_estimate_revision": "estimate_revisions",
    "I4_options_repricing": "options_state",
    "I5_attention": "attention_views",
    "I6_peer_response": "theme_membership",
    "I7_persistence_rejection": None,
}

# The incorporation leg set is FIXED (order included). Both the composer and the
# validator read it, so the seven legs can never be dropped, added, reordered, or
# repeated to move a denominator.
_MARKET_REFLECTION_LEGS = tuple(_MARKET_REFLECTION_MAP)

_RESIDUAL_OWNERS = {"engine/price_pressure/", "engine/residual_alpha.py"}
_RESIDUAL_STANDALONE_CONSTRUCTS = {"drl_resid_shock"}

# Sol REQUEST_CHANGES 2026-08-25 item 3 — Entry Availability ownership. Each
# entry_availability leg is bound to the ONE registry construct whose
# `entry_role` it is lawful to read, and to that construct's required role:
#
#   entry_signal          <- entry_role "actionability"   (engine.entry_signal
#                            .assess -> prophet.board_read/v1 entry_signal.status)
#   radar_probe_coverage  <- entry_role "probe_coverage"  (Radar probe admission,
#                            explicitly a coverage state, never a trade verdict)
#
# `admission_context` (prophet_board_lane: lane / buyable / eligible) is bound
# to NO leg: board admission may never satisfy Entry Availability, and — being
# neither evidence nor an actionability read — may not be referenced from any
# projection leg at all.
_ENTRY_LEGS = (
    ("entry_signal", "prophet_entry_signal", "actionability"),
    ("radar_probe_coverage", "radar_probe_admission", "probe_coverage"),
)
_ENTRY_LEG_KEYS = tuple(leg for leg, _c, _r in _ENTRY_LEGS)
_ENTRY_ROLE_LEG_BY_ROLE = {role: leg for leg, _c, role in _ENTRY_LEGS}

_HYPOTHESIS_EVIDENCE_CLASSES = {
    "company_impairment": {
        "forensics_scalars",
        "capital_structure_supply",
        "sue_surprise",
        "eightk_recency",
        "estimate_revisions",
    },
    "positioning_unwind": {
        "short_interest",
        "options_state",
        "smart_money_13f",
        "insider_activity",
    },
}

# v1 dominant_degradation derivation order (highest severity first). R-4
# red-team repair (2026-08-25): the frozen strict order is now
# conflicted > corrected > identity_unresolved > rights_blocked > missing >
# unsupported > unknown > stale > partial_coverage > none. `unsupported` IS a
# real slot.state value and participates directly (the earlier "unreachable
# in v1" comment for `unsupported` was false and has been removed).
# `corrected` remains the sole unreachable member: no slot state or
# coverage_flag value maps to it in this v1 wire — documented, not a defect.
_DOMINANT_DEGRADATION_ORDER = [
    "conflicted",
    "identity_unresolved",
    "rights_blocked",
    "missing",
    "unsupported",
    "unknown",
    "stale",
]

# R-1 red-team repair (2026-08-25): value_or_null is now typed (scalar | flat
# one-level object of scalar leaves) by the frozen schema, closing the
# nested-payload smuggling hole. This is the SEMANTIC payload fence layered on
# top: an object-valued value_or_null may never carry a key that names or
# implies a composite/score/rank/directive, even flattened to one level and
# even though the schema itself cannot forbid a key by NAME. Frozen at build
# time; changing this set is a contract amendment, not a bug fix.
_FORBIDDEN_VALUE_PAYLOAD_KEYS = {
    "score", "scores", "scoring", "weight", "weights", "rank", "ranks", "ranking",
    "buy", "sell", "size", "sizing", "composite", "entry", "entry_open", "fused",
    "blend", "blended", "urgency", "conviction", "verdict", "potential",
}


def _is_decomp_construct(construct: str, decomp: dict) -> re.Match | None:
    m = _DISLOC_RE.match(construct)
    if not m:
        return None
    if m.group("term") not in decomp.get("terms", []):
        return None
    if m.group("window") not in decomp.get("windows", []):
        return None
    return m


def _is_residual_construct(construct: str) -> bool:
    if construct in _RESIDUAL_STANDALONE_CONSTRUCTS:
        return True
    m = _DISLOC_RE.match(construct)
    return bool(m and m.group("term") in ("ret_resid", "resid_z"))


def registry_hygiene_findings() -> list[Finding]:
    """K3E_R003(a): registry-level hygiene — no two registry constructs may
    bind the same (family_id, member) pair. Intended for TEST-level use over
    the frozen registry file, not part of per-vector validation."""

    registry = load_slot_registry()
    findings: list[Finding] = []
    seen: dict[tuple, str] = {}
    for name, row in registry.get("constructs", {}).items():
        fb = row.get("family_binding", {})
        if fb.get("kind") != "governed_family":
            continue
        key = (fb.get("family_id"), fb.get("member"))
        if key in seen:
            findings.append(_f("K3E_R003", f"constructs.{name}", f"registry double-homes {key!r} via {seen[key]!r} and {name!r}"))
        else:
            seen[key] = name
    return findings


def compute_content_sha256(vector: dict) -> str:
    payload = {k: v for k, v in vector.items() if k != "content_sha256"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Semantic rule passes.
# ---------------------------------------------------------------------------


def _recompute_denominator(slots: list[dict]) -> dict:
    d = {
        "total": len(slots),
        "included": 0,
        "excluded": 0,
        "missing": 0,
        "stale": 0,
        "rights_blocked": 0,
        "conflicted": 0,
        "unsupported": 0,
        "identity_unresolved": 0,
        "unknown": 0,
    }
    for s in slots:
        if s.get("included_in_composition"):
            d["included"] += 1
        else:
            d["excluded"] += 1
        st = s.get("state")
        if st in d:
            d[st] += 1
    return d


# Sol REQUEST_CHANGES 2026-08-25 item 2 — frozen denominator semantics for the
# two aggregate legs whose counts are not derived from slot inclusion.
#
# market_reflection: an incorporation leg is INCLUDED evidence when the market
# demonstrably reflects something on that axis — observed, modeled, or partial.
# `modeled` is the load-bearing member: modeled market-reflection evidence (e.g.
# dealer-gamma repricing) is real evidence carried under a modeled label, and
# must NOT be counted excluded merely because it is not directly observed.
# Everything else (missing / stale / rights_blocked / conflicted /
# identity_unresolved / unknown / ex_post_excluded) is excluded, still typed,
# never zero or neutral.
_MARKET_REFLECTION_INCLUDED_LEG_STATES = frozenset({"observed", "modeled", "partial"})

# failed_or_unavailable_gates: an entry is INCLUDED when the owner actually
# reached an adverse verdict on it (failed / unavailable). `not_evaluated` is
# excluded — the gate was never run, which is a coverage fact, not a verdict.
_GATE_INCLUDED_STATES = frozenset({"failed", "unavailable"})


def _recompute_market_reflection_denominator(incorporation_legs: list[dict]) -> dict:
    total = len(incorporation_legs)
    included = sum(
        1 for leg in incorporation_legs
        if (leg or {}).get("state") in _MARKET_REFLECTION_INCLUDED_LEG_STATES
    )
    return {"total": total, "included": included, "excluded": total - included}


def _recompute_gate_denominator(gates: list[dict]) -> dict:
    total = len(gates)
    included = sum(1 for g in gates if (g or {}).get("state") in _GATE_INCLUDED_STATES)
    return {"total": total, "included": included, "excluded": total - included}


def _recompute_dominant_degradation(slots: list[dict]) -> str:
    present_states = {s.get("state") for s in slots}
    partial_coverage = any((s.get("coverage_flag") or {}).get("state") == "partial" for s in slots)
    for candidate in _DOMINANT_DEGRADATION_ORDER:
        if candidate in present_states:
            return candidate
    if partial_coverage:
        return "partial_coverage"
    return "none"


def _check_constructs(slots: list[dict], registry: dict) -> list[Finding]:
    findings: list[Finding] = []
    constructs = registry.get("constructs", {})
    decomp = registry.get("decomposition_groups", {}).get("dislocation", {})
    forbidden = set(registry.get("forbidden_constructs", []))
    forbidden_prefixes = tuple(registry.get("forbidden_construct_prefixes", []))

    for slot in slots:
        construct = slot.get("construct", "")
        is_known = construct in constructs
        is_decomp = not is_known and _is_decomp_construct(construct, decomp) is not None
        is_forbidden = construct in forbidden or construct.startswith(forbidden_prefixes)

        if is_forbidden:
            findings.append(_f("K3E_R001", f"slots[{construct}]", f"forbidden construct {construct!r}"))
            findings.append(_f("K3E_R004", f"slots[{construct}]", f"forbidden construct {construct!r} is a scalar reconstruction"))
        elif not is_known and not is_decomp:
            findings.append(_f("K3E_R001", f"slots[{construct}]", f"unknown construct {construct!r}"))

        lowered = construct.lower()
        if "impair" in lowered or "net_demand" in lowered:
            findings.append(_f("K3E_R017", f"slots[{construct}]", f"construct {construct!r} claims the unowned axis (company_impairment_attribution / latent_net_demand)"))

        # R002 / R003(b) family-binding checks.
        expected = None
        if is_known:
            reg_fb = constructs[construct]["family_binding"]
            expected = (reg_fb.get("kind"), reg_fb.get("family_id"), reg_fb.get("routed_to"))
        elif is_decomp:
            grp_fb = decomp.get("family_binding", {})
            expected = (grp_fb.get("kind"), grp_fb.get("family_id"), grp_fb.get("routed_to"))

        if expected is not None:
            fb = slot.get("family_binding") or {}
            actual = (fb.get("kind"), fb.get("family_id"), fb.get("routed_to"))
            if actual != expected:
                findings.append(_f("K3E_R002", f"slots[{construct}].family_binding", f"binding {actual!r} != registry pin {expected!r}"))
                if fb.get("kind") == "governed_family" and fb.get("family_id") and fb.get("family_id") != expected[1]:
                    findings.append(_f("K3E_R003", f"slots[{construct}].family_binding", f"construct {construct!r} claims a second family {fb.get('family_id')!r}; registry homes it in {expected[1]!r}"))

        # Sol-repair BLOCKER 1 / MAJOR 7 (red-team 2026-08-25): a construct NAME
        # was the only thing separating the actionability owner from board
        # admission. `prophet_entry_signal` and `prophet_board_lane` share
        # family_binding, derivation, and clock classes, so a caller could put
        # the board's own payload AND the board's own owner_ref into a slot
        # named `prophet_entry_signal` and satisfy the Entry Availability leg —
        # defeating Sol item 3 while every check passed. Every registry-known
        # slot's owner pointer and object class must now equal its registry pin,
        # so the name can no longer be a costume.
        owner_ref = slot.get("owner_ref") or {}
        if is_known:
            reg_row = constructs[construct]
            for field in ("owner", "artifact", "reader"):
                pinned = reg_row.get(field)
                if pinned is not None and owner_ref.get(field) != pinned:
                    findings.append(_f("K3E_R008", f"slots[{construct}].owner_ref.{field}", f"{field} {owner_ref.get(field)!r} does not match the registry pin {pinned!r}: a slot may not wear another owner's construct name"))
            pinned_class = reg_row.get("object_class")
            if pinned_class is not None and slot.get("object_class") != pinned_class:
                findings.append(_f("K3E_R008", f"slots[{construct}].object_class", f"object_class {slot.get('object_class')!r} does not match the registry pin {pinned_class!r}: relabeling would move the slot past its class fences"))

        # R008 residual re-derivation.
        if construct.startswith("drl_"):
            if owner_ref.get("owner") != "engine/price_pressure/" or "price_pressure" not in (owner_ref.get("reader") or ""):
                findings.append(_f("K3E_R008", f"slots[{construct}].owner_ref", "drl_* construct must be owned by engine/price_pressure/ with a price_pressure reader"))
        if construct == "residual_alpha_momentum" and owner_ref.get("owner") != "engine/residual_alpha.py":
            findings.append(_f("K3E_R008", f"slots[{construct}].owner_ref", "residual_alpha_momentum must be owned by engine/residual_alpha.py"))
        if is_known and slot.get("derivation") != constructs[construct].get("derivation"):
            findings.append(_f("K3E_R008", f"slots[{construct}].derivation", "derivation does not match registry law"))
        decomp_match = _is_decomp_construct(construct, decomp)
        if decomp_match is not None and slot.get("state") in ("observed", "modeled") and decomp_match.group("term") in ("ret_resid", "resid_z"):
            if owner_ref.get("owner") not in _RESIDUAL_OWNERS:
                findings.append(_f("K3E_R008", f"slots[{construct}].owner_ref", "value-bearing residual decomposition slot must cite a canonical residual owner"))

        # R012 flow-nominal label.
        if is_known and constructs[construct].get("variation_required"):
            vr = slot.get("variation_receipt")
            state = slot.get("state")
            if vr is None:
                if state not in ("missing", "unknown"):
                    findings.append(_f("K3E_R012", f"slots[{construct}]", "variation-required construct with no variation_receipt must be state missing/unknown"))
            else:
                dv = vr.get("distinct_values")
                if isinstance(dv, int) and dv <= 1 and state != "stale":
                    findings.append(_f("K3E_R012", f"slots[{construct}]", "distinct_values<=1 requires state stale"))
                if state == "observed" and not (isinstance(dv, int) and dv >= 2):
                    findings.append(_f("K3E_R012", f"slots[{construct}]", "state observed requires distinct_values>=2"))

        # R-1 red-team repair (2026-08-25): R004 payload-smuggling fence over
        # value_or_null. The wire schema now types value_or_null as a scalar
        # or a flat one-level object of scalar leaves, closing nested-payload
        # smuggling; this semantic pass additionally fences forbidden KEY
        # NAMES (a schema cannot forbid by name) and enforces plain-number
        # values for value_type=number constructs (the dislocation group).
        value = slot.get("value_or_null")
        if isinstance(value, dict):
            for key in value:
                if not isinstance(key, str):
                    continue
                if key in forbidden or key.startswith(forbidden_prefixes) or key in _FORBIDDEN_VALUE_PAYLOAD_KEYS:
                    findings.append(_f("K3E_R004", f"slots[{construct}].value_or_null.{key}", f"value payload key {key!r} names/implies a forbidden composite/score/rank/directive"))

        if slot.get("state") in ("observed", "modeled"):
            value_type = None
            if is_known:
                value_type = constructs[construct].get("value_type")
            elif is_decomp:
                value_type = decomp.get("value_type")
            if value_type == "number" and not (isinstance(value, (int, float)) and not isinstance(value, bool)):
                findings.append(_f("K3E_R004", f"slots[{construct}].value_or_null", f"construct {construct!r} is value_type=number but value_or_null is {type(value).__name__}"))
    return findings


def _check_disloc_reconstruction(slots: list[dict]) -> list[Finding]:
    findings: list[Finding] = []
    by_window: dict[str, list[tuple[str, str, float]]] = {}
    for slot in slots:
        m = _DISLOC_RE.match(slot.get("construct", ""))
        if not m:
            continue
        value = slot.get("value_or_null")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        by_window.setdefault(m.group("window"), []).append((m.group("term"), slot.get("construct"), float(value)))

    for entries in by_window.values():
        for term, construct, value in entries:
            if term == "ret_raw":
                continue
            others = [v for t, c, v in entries if c != construct]
            found = False
            for r in range(2, len(others) + 1):
                for combo in itertools.combinations(others, r):
                    # R-3 red-team repair (2026-08-25): a bare absolute 1e-9
                    # tolerance is blind to a near-sum reconstruction at
                    # realistic return magnitudes (e.g. 0.08000001 vs
                    # 0.05+0.03). Tolerance is now RELATIVE to the magnitude
                    # of the value and its candidate terms, with the old
                    # absolute floor kept for near-zero values.
                    tol = max(1e-9, 1e-6 * max(abs(value), max(abs(v) for v in combo)))
                    if abs(sum(combo) - value) <= tol:
                        found = True
                        break
                if found:
                    break
            if found:
                findings.append(_f("K3E_R004", f"slots[{construct}]", "value reconstructs as a sum of two-or-more other same-window terms"))
    return findings


def _check_missing_to_neutral(vector: dict, slots: list[dict]) -> list[Finding]:
    findings: list[Finding] = []
    for slot in slots:
        construct = slot.get("construct")
        if slot.get("state") not in ("observed", "modeled") and slot.get("value_or_null") is not None:
            findings.append(_f("K3E_R005", f"slots[{construct}]", "adverse-state slot carries a non-null value_or_null"))
        missingness = slot.get("missingness") or {}
        if missingness.get("zero_substituted") is not False:
            findings.append(_f("K3E_R005", f"slots[{construct}].missingness", "zero_substituted must be false"))

    denominator = vector.get("denominator") or {}
    adverse_keys = ("missing", "stale", "rights_blocked", "conflicted", "unsupported", "identity_unresolved", "unknown")
    adverse_total = sum((denominator.get(k) or 0) for k in adverse_keys)
    if vector.get("compilation_state") == "complete" and adverse_total > 0:
        findings.append(_f("K3E_R005", "$.compilation_state", "compilation_state complete while an adverse denominator count is non-zero"))
    return findings


def _check_clocks(slots: list[dict], registry: dict) -> list[Finding]:
    findings: list[Finding] = []
    constructs = registry.get("constructs", {})
    decomp = registry.get("decomposition_groups", {}).get("dislocation", {})

    for slot in slots:
        construct = slot.get("construct", "")
        reg_row = constructs.get(construct)
        if reg_row is not None:
            asof_pin = reg_row["asof_clock"]
            known_at_pin = reg_row["known_at_clock"]
            clock_distinct = bool(reg_row.get("clock_distinct"))
        elif _is_decomp_construct(construct, decomp) is not None:
            asof_pin = {"native_field": "bar_date", "clock_class": "world_valid"}
            known_at_pin = {"native_field": "bar_date", "clock_class": "observed"}
            clock_distinct = False
        else:
            continue

        asof_clock = slot.get("asof") or {}
        known_at_clock = slot.get("known_at") or {}

        if asof_clock.get("clock_class") != asof_pin["clock_class"]:
            findings.append(_f("K3E_R006", f"slots[{construct}].asof.clock_class", "asof clock_class does not match the registry pin"))
        if asof_clock.get("state") == "known" and asof_clock.get("native_field") != asof_pin["native_field"]:
            findings.append(_f("K3E_R006", f"slots[{construct}].asof.native_field", "asof native_field does not match the registry pin"))
        if known_at_clock.get("clock_class") != known_at_pin["clock_class"]:
            findings.append(_f("K3E_R006", f"slots[{construct}].known_at.clock_class", "known_at clock_class does not match the registry pin"))
        if known_at_clock.get("state") == "known" and known_at_clock.get("native_field") != known_at_pin["native_field"]:
            findings.append(_f("K3E_R006", f"slots[{construct}].known_at.native_field", "known_at native_field does not match the registry pin"))

        if clock_distinct and asof_clock.get("state") == "known" and known_at_clock.get("state") == "known":
            if asof_clock.get("native_field") == known_at_clock.get("native_field"):
                findings.append(_f("K3E_R006", f"slots[{construct}]", "clock_distinct construct collapses asof/known_at onto one native field"))
            as_day = (asof_clock.get("value") or "")[:10]
            ka_day = (known_at_clock.get("value") or "")[:10]
            if ka_day and as_day and ka_day < as_day:
                findings.append(_f("K3E_R006", f"slots[{construct}]", "known_at precedes asof for a clock_distinct availability clock"))
    return findings


def _parse_instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _compare_known_at_to_asof(known_at_value: str | None, known_at_grain: str | None, asof_value: str | None, asof_grain: str | None) -> str:
    """R-2 red-team repair (2026-08-25): a bare [:10] truncation is blind to
    an intraday look-ahead when both clocks are datetime-grain (e.g. asof
    09:30Z vs known_at 23:59:59Z the same calendar day). Returns one of
    "after" (look-ahead — known_at strictly later), "before_or_equal"
    (lawful), or "ambiguous" (mixed grain, same calendar day — symmetric
    ambiguity, mirroring K1; must be excluded either way)."""

    if not known_at_value or not asof_value:
        return "unknown"
    if known_at_grain == "datetime" and asof_grain == "datetime":
        ka_dt = _parse_instant(known_at_value)
        as_dt = _parse_instant(asof_value)
        return "after" if ka_dt > as_dt else "before_or_equal"
    if known_at_grain == "date" and asof_grain == "date":
        return "after" if known_at_value > asof_value else "before_or_equal"
    ka_day = known_at_value[:10]
    as_day = asof_value[:10]
    if ka_day == as_day:
        return "ambiguous"
    return "after" if ka_day > as_day else "before_or_equal"


_NATIVE_IDENTITY_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$")


def _check_t0_authentication(vector: dict, registry: dict) -> list[Finding]:
    """K3E_R021 — Sol REQUEST_CHANGES 2026-08-25 item 1: authenticate the
    decision-time origin.

    A decision clock may no longer be trusted from an arbitrary caller string.
    `asof.t0_evidence_ref` is an immutable owner-backed PIT reference in K1
    reference.v1 EvidenceRef shape, and this pass checks it against the frozen
    registry `t0_sources` pins:

      * t0_mode is a member of the pin's lawful_t0_modes — the generic
        owner_pit_reference may not claim "live" at all (Sol REQUEST_CHANGES
        2026-08-26 item A), because nothing about it is checkable here
      * owner_store equals the pin for that t0_source (when the pin is not null)
      * recorded_clock.clock_class equals the pin (when not null)
      * digest_required sources carry native_digest state "known"
      * native_identity keys match the K1 propertyNames pattern (the in-module
        structural checker implements no `propertyNames`, so it is re-checked
        here rather than silently passing)
      * in t0_mode "live", the referenced object was not minted more than
        max_recording_lag_days AFTER t0 — a retrospective t0 fails closed

    Fail-closed throughout: an unknown t0_source, an unparseable clock, or a
    missing registry section is a Finding, never a silent pass."""

    findings: list[Finding] = []
    asof = vector.get("asof") or {}
    if not isinstance(asof, dict):
        return [_f("K3E_R021", "$.asof", "asof must be an object")]

    t0_source = asof.get("t0_source")
    t0_mode = asof.get("t0_mode")
    ref = asof.get("t0_evidence_ref")
    if not isinstance(ref, dict):
        return [_f("K3E_R021", "$.asof.t0_evidence_ref", "decision clock carries no owner-backed PIT reference")]

    sources = (registry.get("t0_sources") or {}).get("sources") or {}
    pin = sources.get(t0_source)
    if pin is None:
        return [_f("K3E_R021", "$.asof.t0_source", f"t0_source {t0_source!r} has no registry t0_sources pin")]

    # Sol REQUEST_CHANGES 2026-08-26 item A — assurance ceiling. t0_mode "live"
    # asserts operational point-in-time, and this contract may only let a source
    # claim it where validation can actually check the pointer (owner_store and
    # clock class pinned in the registry). owner_pit_reference pins neither: its
    # store, clock class and referenced bytes are all caller-declared, so a live
    # claim there is the caller vouching for the caller. It is an accountability
    # receipt, not a verification, and the registry restricts it to
    # "retrospective_research". Fail closed on a missing pin: an unpinned source
    # may claim only the weaker mode, never the stronger one.
    #
    # The membership test is guarded on the pin's TYPE, not just its presence.
    # `x in y` raises on a non-container and does substring matching on a bare
    # string, so a drifted registry could crash validate_vector (violating its
    # never-raises contract, red-team MAJOR 6) or silently accept "live" as a
    # substring. A malformed pin is treated exactly like a missing one.
    lawful_modes = pin.get("lawful_t0_modes")
    if not isinstance(lawful_modes, (list, tuple)):
        if lawful_modes is not None:
            findings.append(_f("K3E_R021", "$.asof.t0_source", f"registry t0_sources pin for {t0_source!r} declares a malformed lawful_t0_modes ({type(lawful_modes).__name__}); it must be a list of modes"))
        if t0_mode != "retrospective_research":
            findings.append(_f("K3E_R021", "$.asof.t0_mode", f"registry t0_sources pin for {t0_source!r} declares no usable lawful_t0_modes; only 'retrospective_research' may be claimed against a missing pin, got {t0_mode!r}"))
    elif t0_mode not in lawful_modes:
        findings.append(_f("K3E_R021", "$.asof.t0_mode", f"t0_source {t0_source!r} may not claim t0_mode {t0_mode!r}: the registry pins lawful modes {sorted(lawful_modes)!r}. A source whose owner_store and clock class this contract cannot check is an accountability receipt, not a validation-time verification, so it cannot assert operational point-in-time"))

    pinned_store = pin.get("owner_store")
    owner_store = ref.get("owner_store")
    if pinned_store is not None and owner_store != pinned_store:
        findings.append(_f("K3E_R021", "$.asof.t0_evidence_ref.owner_store", f"t0_source {t0_source!r} pins owner_store {pinned_store!r}, got {owner_store!r}"))

    digest = ref.get("native_digest") or {}
    # MINOR 11: an absent digest_required key must not silently drop the only
    # binding constraint the generic source has — default to REQUIRING it.
    if pin.get("digest_required", True) and digest.get("state") != "known":
        findings.append(_f("K3E_R021", "$.asof.t0_evidence_ref.native_digest", f"t0_source {t0_source!r} requires a known immutability digest, got state {digest.get('state')!r}"))

    identity = ref.get("native_identity")
    if not isinstance(identity, dict) or not identity:
        findings.append(_f("K3E_R021", "$.asof.t0_evidence_ref.native_identity", "native_identity must be a non-empty owner-native identity object"))
    else:
        for key in identity:
            if not _NATIVE_IDENTITY_KEY_RE.match(str(key)):
                findings.append(_f("K3E_R021", f"$.asof.t0_evidence_ref.native_identity.{key}", f"key {key!r} violates the K1 native_identity propertyNames pattern"))

    recorded = ref.get("recorded_clock") or {}
    pinned_class = pin.get("recorded_clock_class")
    if pinned_class is not None and recorded.get("clock_class") != pinned_class:
        findings.append(_f("K3E_R021", "$.asof.t0_evidence_ref.recorded_clock.clock_class", f"t0_source {t0_source!r} pins recorded clock class {pinned_class!r}, got {recorded.get('clock_class')!r}"))

    # Retrospective-t0 fence. A t0 whose own PIT object was minted well after
    # the decision date is exactly the "chose t0 after seeing what happened"
    # defect; in live mode it fails closed against the per-source lag budget.
    # retrospective_research declares the same fact visibly instead of hiding
    # it — the declaration is the disclosure, and every other check still binds.
    lag_seconds = _t0_recording_lag_seconds(recorded.get("value"), asof.get("value"))
    if t0_mode == "live":
        max_lag = pin.get("max_recording_lag_days")
        if lag_seconds is None:
            findings.append(_f("K3E_R021", "$.asof.t0_evidence_ref.recorded_clock.value", "live t0 requires a parseable recorded clock to prove it was not minted retrospectively"))
        elif max_lag is None:
            # MINOR 11: a pin that lost its budget must not silently disable the
            # anti-hindsight fence. Fail closed and name the gap.
            findings.append(_f("K3E_R021", "$.asof.t0_source", f"registry t0_sources pin for {t0_source!r} declares no max_recording_lag_days; a live t0 cannot be authenticated against a missing budget"))
        elif lag_seconds > max_lag * 86400:
            findings.append(_f("K3E_R021", "$.asof.t0_evidence_ref.recorded_clock.value", f"live t0 was recorded {lag_seconds / 86400:.3f} day(s) after t0, exceeding the {max_lag}-day budget for {t0_source!r}: declare t0_mode 'retrospective_research' instead of claiming operational PIT"))

    # MAJOR 4: the generation clock was unauthenticated, and the composer
    # defaults it to t0 — so a vector could claim it was generated BEFORE the
    # evidence it cites existed (the shipped FPI golden did exactly that).
    generated_at = vector.get("generated_at")
    gen_lag = _t0_recording_lag_seconds(generated_at, recorded.get("value"))
    if gen_lag is not None and gen_lag < 0:
        findings.append(_f("K3E_R021", "$.generated_at", f"generated_at {generated_at!r} precedes the decision-time object's recorded clock {recorded.get('value')!r}: a vector cannot be generated before the evidence it cites existed"))
    return findings


def _t0_recording_lag_seconds(recorded_value: Any, t0_value: Any) -> float | None:
    """Seconds from t0 to the moment the referenced PIT object was recorded.

    Negative when the object predates t0 (a pre-registered hypothesis — lawful,
    and the good case). None when either clock is missing or unparseable.

    Sol-repair MAJOR 5 (red-team 2026-08-25): this was day-truncated via
    ``.date()``, so an object minted 14h29m AFTER an intraday t0 measured as a
    zero-day lag and passed every budget — the same day-grain blindness the
    earlier B2 repair fixed for slot clocks but not for the decision clock. Both
    sides are now compared as instants, with a bare date read as that day's
    00:00:00Z. MAJOR 6: the value is whatever the wire carried, so non-string
    input must return None rather than raise out of ``validate_vector``, whose
    documented contract is that it never raises."""

    def _instant(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            return _parse_instant(value)
        except ValueError:
            return None

    rec, t0 = _instant(recorded_value), _instant(t0_value)
    if rec is None or t0 is None:
        return None
    if rec.tzinfo is None:
        rec = rec.replace(tzinfo=timezone.utc)
    if t0.tzinfo is None:
        t0 = t0.replace(tzinfo=timezone.utc)
    return (rec - t0).total_seconds()


def _check_lookahead(vector: dict, slots: list[dict]) -> list[Finding]:
    findings: list[Finding] = []
    asof = vector.get("asof") or {}
    asof_value = asof.get("value")
    asof_grain = asof.get("grain")

    for slot in slots:
        if not slot.get("included_in_composition"):
            continue
        construct = slot.get("construct")
        known_at = slot.get("known_at") or {}
        if known_at.get("state") != "known":
            findings.append(_f("K3E_R007", f"slots[{construct}]", "slot is included_in_composition with an unknown known_at"))
            continue
        verdict = _compare_known_at_to_asof(known_at.get("value"), known_at.get("grain"), asof_value, asof_grain)
        if verdict == "after":
            findings.append(_f("K3E_R007", f"slots[{construct}]", "included slot's known_at is after asof (look-ahead)"))
        elif verdict == "ambiguous":
            findings.append(_f("K3E_R007", f"slots[{construct}]", "date-grain vs datetime-grain same-day comparison is ambiguous and must be excluded"))

    mr = (vector.get("projection") or {}).get("market_reflection") or {}
    for leg in mr.get("incorporation_legs", []) or []:
        if leg.get("leg") == "I7_persistence_rejection" and leg.get("state") != "ex_post_excluded":
            findings.append(_f("K3E_R007", "$.projection.market_reflection.I7_persistence_rejection", "I7_persistence_rejection must always be ex_post_excluded in a t0 vector"))
    return findings


def _check_cause_hypothesis(vector: dict, slots: list[dict]) -> list[Finding]:
    findings: list[Finding] = []
    ech = vector.get("economic_cause_hypothesis")
    if not ech or ech.get("hypothesis") == "unknown":
        return findings

    by_construct = {s.get("construct"): s for s in slots}
    refs = ech.get("supporting_slot_refs") or []
    if not refs:
        findings.append(_f("K3E_R009", "$.economic_cause_hypothesis.supporting_slot_refs", "a non-unknown hypothesis requires non-empty supporting_slot_refs"))
        return findings

    unresolved = [r for r in refs if r not in by_construct]
    if unresolved:
        findings.append(_f("K3E_R009", "$.economic_cause_hypothesis.supporting_slot_refs", f"refs do not resolve to present slots: {unresolved!r}"))

    if refs and all(_is_residual_construct(r) for r in refs):
        findings.append(_f("K3E_R009", "$.economic_cause_hypothesis.supporting_slot_refs", "support set cannot consist solely of residual constructs"))

    hyp = ech.get("hypothesis")

    def _observed(names):
        return any(by_construct.get(n, {}).get("state") == "observed" for n in names)

    if hyp == "company_impairment":
        if not _observed(_HYPOTHESIS_EVIDENCE_CLASSES["company_impairment"]):
            findings.append(_f("K3E_R009", "$.economic_cause_hypothesis", "company_impairment requires an observed company-evidence slot"))
    elif hyp == "sector_or_factor_washout":
        disloc_ok = False
        for construct, slot in by_construct.items():
            m = _DISLOC_RE.match(construct)
            if m and m.group("term") in ("ret_sec", "ret_fac") and slot.get("state") == "observed":
                disloc_ok = True
                break
        if not disloc_ok or not _observed(_HYPOTHESIS_EVIDENCE_CLASSES["company_impairment"]):
            findings.append(_f("K3E_R009", "$.economic_cause_hypothesis", "sector_or_factor_washout requires an observed sector/factor decomposition slot AND observed company evidence"))
    elif hyp == "liquidity_airpocket":
        if by_construct.get("turnover_liquidity", {}).get("state") != "observed":
            findings.append(_f("K3E_R009", "$.economic_cause_hypothesis", "liquidity_airpocket requires turnover_liquidity observed"))
    elif hyp == "positioning_unwind":
        ok = any(
            by_construct.get(n, {}).get("state") == "observed" and by_construct.get(n, {}).get("included_in_composition")
            for n in _HYPOTHESIS_EVIDENCE_CLASSES["positioning_unwind"]
        )
        if not ok:
            findings.append(_f("K3E_R009", "$.economic_cause_hypothesis", "positioning_unwind requires an observed+included positioning slot"))
    return findings


def _check_identity_launder(vector: dict, slots: list[dict], registry: dict) -> list[Finding]:
    findings: list[Finding] = []
    subject = vector.get("subject") or {}
    if subject.get("identity_state") == "bridge_validated":
        return findings
    constructs = registry.get("constructs", {})
    for slot in slots:
        construct = slot.get("construct")
        reg_row = constructs.get(construct)
        if reg_row and reg_row.get("cross_owner_join"):
            if slot.get("state") != "identity_unresolved" or slot.get("included_in_composition") is not False:
                findings.append(_f("K3E_R010", f"slots[{construct}]", "cross-owner construct must be state=identity_unresolved and included_in_composition=false when subject identity is unproven"))
    return findings


# R-5(a) red-team repair (2026-08-25): entry_availability leg -> the ONE
# lawful owner-slot state each entry_availability.state value may represent.
# "read" is lawful ONLY when the referenced owner slot is itself observed; a
# missing/stale/unknown owner slot FORCES the matching leg state to equal
# that slot state — the leg may never claim more certainty than its owner
# read actually carries. Any other adverse slot.state (rights_blocked,
# conflicted, identity_unresolved, unsupported) has no matching leg-state
# word in the closed 4-value entry_availability enum, so it maps to
# "unknown" (the honest fallback, never silently upgraded to "read").
def _expected_entry_leg_state(slot: dict | None) -> str | None:
    if slot is None:
        return None
    st = slot.get("state")
    if st == "observed":
        return "read"
    if st in ("missing", "stale", "unknown"):
        return st
    return "unknown"


def _check_authority_leak(vector: dict, slots: list[dict], registry: dict) -> list[Finding]:
    findings: list[Finding] = []
    by_construct = {s.get("construct"): s for s in slots}
    constructs = registry.get("constructs", {})
    projection = vector.get("projection") or {}
    entry = projection.get("entry_availability") or {}

    for leg_key, owner_construct, required_role in _ENTRY_LEGS:
        leg = entry.get(leg_key) or {}
        leg_state = leg.get("state")
        refs = leg.get("slot_refs") or []
        if leg_state == "read":
            if not refs:
                findings.append(_f("K3E_R011", f"$.projection.entry_availability.{leg_key}", "state=read requires non-empty slot_refs"))
        # Sol item 3: a leg may reference ONLY the construct carrying its own
        # entry_role. An admission/context construct (prophet_board_lane: lane
        # / buyable / eligible) referenced here is the named ownership defect —
        # board admission can never satisfy Entry Availability — and is caught
        # in every leg state, not only "read".
        for r in refs:
            if r != owner_construct:
                ref_role = (constructs.get(r) or {}).get("entry_role")
                detail = (
                    f"ref {r!r} carries entry_role {ref_role!r} (admission/context is not an entry verdict)"
                    if ref_role else f"ref {r!r} is not {owner_construct}"
                )
                findings.append(_f("K3E_R011", f"$.projection.entry_availability.{leg_key}.slot_refs", f"{detail}; this leg may read only {owner_construct!r} (entry_role {required_role!r})"))

        # R-5(a): leg state must equal the law-derived state of the owner
        # slot it names (or of the canonical owner construct, if present in
        # the vector even without being referenced).
        owner_slot = by_construct.get(owner_construct)
        expected = _expected_entry_leg_state(owner_slot)
        if expected is not None and leg_state is not None and leg_state != expected:
            findings.append(_f("K3E_R011", f"$.projection.entry_availability.{leg_key}", f"leg state {leg_state!r} does not match owner slot {owner_construct!r} state law (expected {expected!r})"))

    # R-5(b): a gate this vector (or any composed rule) claims to have
    # computed itself is the named authority leak — failed_or_unavailable_
    # gates may only ever name a canonical OWNER gate.
    fug = projection.get("failed_or_unavailable_gates") or {}
    for gate in fug.get("gates", []) or []:
        owner = (gate.get("owner") or "")
        # MINOR 12 (red-team 2026-08-25): the fence named only two spellings, so
        # "self" / "this rule" / "internal" passed as canonical gate owners.
        normalized = owner.strip().lower()
        if ("opportunity_evidence" in normalized
                or normalized in {"computed", "self", "internal", "this rule", "this vector", "local", "n/a", "none"}):
            findings.append(_f("K3E_R011", "$.projection.failed_or_unavailable_gates.gates", f"gate owner {owner!r} names this vector/a computed rule, never a canonical owner"))

    observed = projection.get("observed") or {}
    for r in observed.get("slot_refs", []) or []:
        slot = by_construct.get(r)
        if slot and (slot.get("object_class") != "world_observation" or slot.get("state") != "observed"):
            findings.append(_f("K3E_R011", "$.projection.observed.slot_refs", f"ref {r!r} is not an observed world_observation"))

    inferred = projection.get("inferred") or {}
    for r in inferred.get("slot_refs", []) or []:
        slot = by_construct.get(r)
        if slot and slot.get("object_class") not in ("derived_view", "system_belief"):
            findings.append(_f("K3E_R011", "$.projection.inferred.slot_refs", f"ref {r!r} is not derived_view/system_belief"))

    referenced_elsewhere = set(observed.get("slot_refs", []) or []) | set(inferred.get("slot_refs", []) or [])
    mr = projection.get("market_reflection") or {}
    for leg in mr.get("incorporation_legs", []) or []:
        referenced_elsewhere |= set(leg.get("slot_refs", []) or [])

    for slot in slots:
        construct = slot.get("construct")
        reg_row = constructs.get(construct)
        if slot.get("object_class") == "instrument_state" and construct in referenced_elsewhere:
            findings.append(_f("K3E_R011", f"slots[{construct}]", "instrument_state slot referenced from observed/inferred/market_reflection (only failed_or_unavailable_gates is lawful)"))
        # R-6 red-team repair (2026-08-25), re-cut for Sol item 3: a construct
        # carrying an `entry_role` is an entry-owner read and is never vector
        # evidence — it must not enter observed/inferred/market_reflection.
        entry_role = (reg_row or {}).get("entry_role")
        # Sol-repair MAJOR 8 (red-team 2026-08-25): the fence covered only
        # observed/inferred/market_reflection, so an entry-owner read laundered
        # cleanly into `strongest_unresolved_fact` — a non-evidence leg the
        # composer already refuses to put them in. Validator and composer now
        # agree: an entry_role construct belongs to entry_availability alone.
        non_entry_refs = referenced_elsewhere | set((projection.get("strongest_unresolved_fact") or {}).get("slot_refs") or [])
        if entry_role and construct in non_entry_refs:
            findings.append(_f("K3E_R011", f"slots[{construct}]", f"entry_role {entry_role!r} construct referenced from a non-entry leg (observed/inferred/market_reflection/strongest_unresolved_fact); entry_availability is its only lawful home"))
        # Sol item 3: `admission_context` (board lane / buyable / eligible) owns
        # NO leg. It is neither evidence nor an actionability read, so it may be
        # carried as a typed context slot but never referenced from any
        # projection leg — including entry_availability, checked above.
        if entry_role and entry_role not in _ENTRY_ROLE_LEG_BY_ROLE:
            all_leg_refs = set(referenced_elsewhere)
            for leg_key in _ENTRY_LEG_KEYS:
                all_leg_refs |= set(((entry.get(leg_key) or {}).get("slot_refs") or []))
            all_leg_refs |= set((projection.get("strongest_unresolved_fact") or {}).get("slot_refs") or [])
            if construct in all_leg_refs:
                findings.append(_f("K3E_R011", f"slots[{construct}]", f"entry_role {entry_role!r} owns no projection leg: board admission is not an entry verdict and is not evidence, so it may never be referenced from any leg"))
    return findings


def _check_leg_membership(vector: dict, slots: list[dict]) -> list[Finding]:
    findings: list[Finding] = []
    known = {s.get("construct") for s in slots}
    projection = vector.get("projection") or {}

    def _refs(items, path):
        for r in items or []:
            if r not in known:
                findings.append(_f("K3E_R014", path, f"ref {r!r} does not resolve to a present slot"))

    _refs((projection.get("observed") or {}).get("slot_refs"), "$.projection.observed.slot_refs")
    _refs((projection.get("inferred") or {}).get("slot_refs"), "$.projection.inferred.slot_refs")
    for leg in (projection.get("market_reflection") or {}).get("incorporation_legs", []) or []:
        _refs(leg.get("slot_refs"), f"$.projection.market_reflection.{leg.get('leg')}.slot_refs")
    _refs((projection.get("strongest_unresolved_fact") or {}).get("slot_refs"), "$.projection.strongest_unresolved_fact.slot_refs")
    entry = projection.get("entry_availability") or {}
    for leg_key in _ENTRY_LEG_KEYS:
        _refs((entry.get(leg_key) or {}).get("slot_refs"), f"$.projection.entry_availability.{leg_key}.slot_refs")
    return findings


def _check_receipt_consistency(vector: dict, slots: list[dict]) -> list[Finding]:
    findings: list[Finding] = []
    recomputed = _recompute_denominator(slots)
    wire = vector.get("denominator") or {}
    for key, val in recomputed.items():
        if wire.get(key) != val:
            findings.append(_f("K3E_R015", f"$.denominator.{key}", f"expected {val}, got {wire.get(key)!r}"))

    dd = _recompute_dominant_degradation(slots)
    if vector.get("dominant_degradation") != dd:
        findings.append(_f("K3E_R015", "$.dominant_degradation", f"expected {dd!r}, got {vector.get('dominant_degradation')!r}"))

    by_construct = {s.get("construct"): s for s in slots}
    projection = vector.get("projection") or {}
    for leg_name in ("observed", "inferred"):
        leg = projection.get(leg_name) or {}
        refs = leg.get("slot_refs") or []
        included = sum(1 for r in refs if by_construct.get(r, {}).get("included_in_composition"))
        total = len(refs)
        expected = {"total": total, "included": included, "excluded": total - included}
        wire_denom = leg.get("denominator") or {}
        if wire_denom != expected:
            findings.append(_f("K3E_R015", f"$.projection.{leg_name}.denominator", f"expected {expected!r}, got {wire_denom!r}"))

    # R-7 red-team repair (2026-08-25): a market_reflection incorporation
    # leg's declared state must equal what its own referenced slot's state
    # law recomputes to — this is the same "wire must equal recomputed
    # truth" discipline the denominator/dominant_degradation checks above
    # already enforce, so a leg fed only by a modeled slot (e.g. GEX) can
    # never be mislabeled "observed" (documented here rather than under
    # K3E_R011 because this is a receipt-recomputation check, not a
    # cross-leg authority-boundary check).
    # Sol item 2: EVERY mandatory denominator is recomputed by public
    # validation, not merely the two slot-derived ones. market_reflection and
    # failed_or_unavailable_gates are counted from their own wire entries under
    # the frozen inclusion semantics above, so an independently tampered count
    # (inflate included, deflate excluded, silently drop a modeled leg from the
    # numerator) cannot survive validation.
    mr = projection.get("market_reflection") or {}
    mr_legs = mr.get("incorporation_legs", []) or []
    expected_mr = _recompute_market_reflection_denominator(mr_legs)
    if (mr.get("denominator") or {}) != expected_mr:
        findings.append(_f("K3E_R015", "$.projection.market_reflection.denominator", f"expected {expected_mr!r}, got {mr.get('denominator')!r}"))

    fug = projection.get("failed_or_unavailable_gates") or {}
    gate_entries = fug.get("gates", []) or []
    expected_gate = _recompute_gate_denominator(gate_entries)
    if (fug.get("denominator") or {}) != expected_gate:
        findings.append(_f("K3E_R015", "$.projection.failed_or_unavailable_gates.denominator", f"expected {expected_gate!r}, got {fug.get('denominator')!r}"))

    # Sol-repair BLOCKER 2 (red-team 2026-08-25): recomputing a denominator from
    # wire-declared leg states is worthless while the LEG SET itself is
    # attacker-controlled. Three forgeries all recomputed "consistently" before
    # this fence: dropping the adverse legs (2/7 coverage reported as 2/2 =
    # 100%), duplicating the one observed leg, and letting a ref-less leg simply
    # declare itself observed. The incorporation leg set is therefore FIXED:
    # exactly the seven I1..I7 legs, each present exactly once.
    seen_legs = [leg.get("leg") for leg in mr_legs]
    if seen_legs != list(_MARKET_REFLECTION_LEGS):
        missing = [n for n in _MARKET_REFLECTION_LEGS if n not in seen_legs]
        extra = [n for n in seen_legs if n not in _MARKET_REFLECTION_LEGS]
        dupes = sorted({n for n in seen_legs if seen_legs.count(n) > 1})
        findings.append(_f(
            "K3E_R015", "$.projection.market_reflection.incorporation_legs",
            "the seven I1..I7 incorporation legs must each appear exactly once in order "
            f"(missing={missing!r}, unexpected={extra!r}, duplicated={dupes!r}): a leg set that can "
            "shrink, grow, or repeat makes its own denominator meaningless",
        ))

    for leg in mr_legs:
        leg_name = leg.get("leg")
        if leg_name == "I7_persistence_rejection":
            continue
        refs = leg.get("slot_refs") or []
        # A leg's state is EVIDENCE-BEARING only if a present slot backs it.
        # With no resolvable ref there is nothing observed, modeled, or partial
        # to report — such a leg may only be missing/unknown, never a claim that
        # the market reflected something.
        resolved = [by_construct.get(r) for r in refs if by_construct.get(r) is not None]
        if not resolved:
            if leg.get("state") in _MARKET_REFLECTION_INCLUDED_LEG_STATES:
                findings.append(_f("K3E_R015", f"$.projection.market_reflection.{leg_name}.state", f"leg claims {leg.get('state')!r} with no resolvable backing slot (refs={refs!r}); a leg with no evidence may only be missing/unknown"))
            continue
        if len(refs) != 1:
            continue
        expected_leg_state = _SLOT_STATE_TO_LEG_STATE.get(resolved[0].get("state"), "unknown")
        if leg.get("state") != expected_leg_state:
            findings.append(_f("K3E_R015", f"$.projection.market_reflection.{leg_name}.state", f"expected {expected_leg_state!r} (from slot {refs[0]!r} state {resolved[0].get('state')!r}), got {leg.get('state')!r}"))
    return findings


def _check_content_hash(vector: dict) -> list[Finding]:
    sha = vector.get("content_sha256")
    if not isinstance(sha, str):
        return []
    recomputed = compute_content_sha256(vector)
    if recomputed != sha:
        return [_f("K3E_R020", "$.content_sha256", "content_sha256 does not match the recomputed hash of the vector")]
    return []


def validate_vector(vector: dict) -> list[Finding]:
    """Structural (JSON-Schema-subset) + semantic (K3E_R0xx) validation.
    Fail-closed: an unrecognized shape anywhere always yields a Finding
    rather than a silent pass. Always loads the two repo-canonical contract
    files; there is no caller-supplied override."""

    if not isinstance(vector, dict):
        return [_f("K3E_SCHEMA_TYPE", "$", f"vector must be an object, got {type(vector).__name__}")]

    findings: list[Finding] = list(_schema_findings(vector))

    registry = load_slot_registry()
    slots = vector.get("slots")
    if not isinstance(slots, list):
        slots = []

    findings.extend(_check_t0_authentication(vector, registry))
    findings.extend(_check_constructs(slots, registry))
    findings.extend(_check_disloc_reconstruction(slots))
    findings.extend(_check_missing_to_neutral(vector, slots))
    findings.extend(_check_clocks(slots, registry))
    findings.extend(_check_lookahead(vector, slots))
    findings.extend(_check_cause_hypothesis(vector, slots))
    findings.extend(_check_identity_launder(vector, slots, registry))
    findings.extend(_check_authority_leak(vector, slots, registry))
    findings.extend(_check_leg_membership(vector, slots))
    findings.extend(_check_receipt_consistency(vector, slots))
    findings.extend(_check_content_hash(vector))
    return findings


# ---------------------------------------------------------------------------
# Deterministic in-memory composer.
# ---------------------------------------------------------------------------


def _clock_value(raw_clock: dict | None, pin: dict) -> dict:
    raw_clock = dict(raw_clock or {})
    state = raw_clock.get("state", "known")
    grain = raw_clock.get("grain", "date")
    value = raw_clock.get("value")
    native_field = raw_clock.get("native_field", pin["native_field"])
    clock_class = raw_clock.get("clock_class", pin["clock_class"])
    if state == "unknown":
        value = None
        native_field = None
    return {"value": value, "grain": grain, "clock_class": clock_class, "native_field": native_field, "state": state}


def _derive_inclusion(state: str, asof_clock: dict, known_at_clock: dict, cross_owner_join: bool, subject: dict, missingness: dict) -> tuple[bool, str | None]:
    if cross_owner_join and subject.get("identity_state") != "bridge_validated":
        return False, "identity_unresolved"
    if state not in ("observed", "modeled"):
        reason = missingness.get("reason") or "unavailable"
        return False, reason
    if known_at_clock.get("state") == "known" and asof_clock.get("state") == "known":
        # R-2 red-team repair (2026-08-25): datetime-aware comparison — see
        # _compare_known_at_to_asof. Both "after" (strict look-ahead) and
        # "ambiguous" (mixed grain, same calendar day) are unlawful for
        # inclusion.
        verdict = _compare_known_at_to_asof(
            known_at_clock.get("value"), known_at_clock.get("grain"),
            asof_clock.get("value"), asof_clock.get("grain"),
        )
        if verdict in ("after", "ambiguous"):
            return False, "lookahead_known_at_after_asof"
    return True, None


def _compose_one_slot(raw: dict, subject: dict, constructs: dict, decomp: dict) -> dict:
    construct = raw["construct"]
    reg_row = constructs.get(construct)
    decomp_match = _is_decomp_construct(construct, decomp) if reg_row is None else None

    if reg_row is not None:
        reg_fb = reg_row["family_binding"]
        default_family_binding = {"kind": reg_fb["kind"], "family_id": reg_fb["family_id"], "routed_to": reg_fb["routed_to"]}
        default_object_class = reg_row["object_class"]
        default_derivation = reg_row["derivation"]
        asof_pin = reg_row["asof_clock"]
        known_at_pin = reg_row["known_at_clock"]
        cross_owner_join = bool(reg_row.get("cross_owner_join"))
        default_owner = {"owner": reg_row["owner"], "artifact": reg_row["artifact"], "reader": reg_row["reader"], "evidence_ref_id": None}
    elif decomp_match is not None:
        grp_fb = decomp.get("family_binding", {})
        default_family_binding = {"kind": grp_fb.get("kind"), "family_id": grp_fb.get("family_id"), "routed_to": grp_fb.get("routed_to")}
        default_object_class = decomp.get("object_class", "derived_view")
        default_derivation = "owner_read"
        asof_pin = {"native_field": "bar_date", "clock_class": "world_valid"}
        known_at_pin = {"native_field": "bar_date", "clock_class": "observed"}
        cross_owner_join = False
        default_owner = None
    else:
        default_family_binding = {"kind": "research_only", "family_id": None, "routed_to": None}
        default_object_class = "derived_view"
        default_derivation = "owner_read"
        asof_pin = {"native_field": None, "clock_class": "belief_or_build"}
        known_at_pin = {"native_field": None, "clock_class": "belief_or_build"}
        cross_owner_join = False
        default_owner = None

    family_binding = raw.get("family_binding", default_family_binding)
    object_class = raw.get("object_class", default_object_class)
    derivation = raw.get("derivation", default_derivation)

    asof_clock = _clock_value(raw.get("asof"), asof_pin)
    known_at_clock = _clock_value(raw.get("known_at"), known_at_pin)

    state = raw["state"]
    value_or_null = raw.get("value_or_null") if state in ("observed", "modeled") else None

    if state in ("observed", "modeled"):
        missingness = {"state": "present", "reason": None, "zero_substituted": False}
    else:
        reason = (raw.get("missingness") or {}).get("reason") or "unknown"
        missingness = {"state": "absent", "reason": reason, "zero_substituted": False}

    owner_ref = raw.get("owner_ref", default_owner) or {"owner": "unknown", "artifact": "unknown", "reader": "unknown", "evidence_ref_id": None}
    provenance_class = raw.get("provenance_class", "owner_artifact")
    coverage_flag = raw.get("coverage_flag") or {"state": "unknown", "note": None}
    basis = raw.get("basis")
    variation_receipt = raw.get("variation_receipt")

    included_in_composition, exclusion_reason = _derive_inclusion(
        state, asof_clock, known_at_clock, cross_owner_join, subject, missingness
    )

    return {
        "construct": construct,
        "family_binding": family_binding,
        "object_class": object_class,
        "state": state,
        "value_or_null": value_or_null,
        "asof": asof_clock,
        "known_at": known_at_clock,
        "coverage_flag": coverage_flag,
        "owner_ref": owner_ref,
        "derivation": derivation,
        "provenance_class": provenance_class,
        "missingness": missingness,
        "basis": basis,
        "variation_receipt": variation_receipt,
        "included_in_composition": included_in_composition,
        "exclusion_reason": exclusion_reason,
    }


def _leg_denominator(refs: list[str], slots_by_construct: dict) -> dict:
    total = len(refs)
    included = sum(1 for r in refs if slots_by_construct.get(r, {}).get("included_in_composition"))
    return {"total": total, "included": included, "excluded": total - included}


_ENTRY_LEG_VERDICT_CLASS = {
    "entry_signal": "owner_entry_actionability",
    "radar_probe_coverage": "probe_coverage_state_not_trade_entry",
}


def _default_entry_availability(slots_by_construct: dict) -> dict:
    # Shares _expected_entry_leg_state with the validator's R-5(a) check so
    # composition and validation can never drift apart on this law.
    #
    # Sol item 3: each leg reads ONLY its own entry_role owner. When the
    # actionability surface (prophet_entry_signal) is absent the leg composes
    # explicitly unknown — it is NEVER back-filled from board admission, which
    # owns no leg at all.
    def _leg(leg_key: str, construct_name: str) -> dict:
        slot = slots_by_construct.get(construct_name)
        expected = _expected_entry_leg_state(slot)
        verdict_class = _ENTRY_LEG_VERDICT_CLASS[leg_key]
        if expected is None:
            return {"state": "unknown", "slot_refs": [], "verdict_class": verdict_class}
        return {
            "state": expected,
            "slot_refs": [construct_name] if expected == "read" else [],
            "verdict_class": verdict_class,
        }

    return {
        "entry_signal": _leg("entry_signal", "prophet_entry_signal"),
        "radar_probe_coverage": _leg("radar_probe_coverage", "radar_probe_admission"),
        "composition_law": "owner_read_only_never_computed",
    }


def compose_vector(
    subject: dict,
    asof: dict,
    slots: list[dict],
    economic_cause_hypothesis: dict | None = None,
    *,
    permitted_consumers: list[str] | None = None,
    strongest_unresolved_fact: dict | None = None,
    next_observable: dict | None = None,
    entry_availability: dict | None = None,
    failed_or_unavailable_gates: list[dict] | None = None,
    generated_at: str | None = None,
) -> dict:
    """Deterministic, pure in-memory composition of an opportunity_evidence
    vector. Never invents, weights, nets, or drops a slot silently: slots are
    ordered canonically (registry order, then construct string), and
    inclusion/exclusion is derived by the frozen composition law
    (adverse-state, look-ahead, and unproven-identity cross-owner exclusion).
    Same input -> byte-identical output (content_sha256 included)."""

    registry = load_slot_registry()
    constructs = registry.get("constructs", {})
    decomp = registry.get("decomposition_groups", {}).get("dislocation", {})

    ordered_names = list(constructs.keys())

    def _sort_key(raw_slot: dict):
        c = raw_slot["construct"]
        if c in constructs:
            return (0, ordered_names.index(c), c)
        return (1, c)

    ordered_raw = sorted(slots, key=_sort_key)
    composed_slots = [_compose_one_slot(raw, subject, constructs, decomp) for raw in ordered_raw]
    slots_by_construct = {s["construct"]: s for s in composed_slots}

    denominator = _recompute_denominator(composed_slots)
    dominant_degradation = _recompute_dominant_degradation(composed_slots)
    adverse_total = sum(
        denominator[k] for k in ("missing", "stale", "rights_blocked", "conflicted", "unsupported", "identity_unresolved", "unknown")
    )
    compilation_state = "partial" if adverse_total > 0 else "complete"

    # R-6 red-team repair (2026-08-25), re-cut for Sol item 3: any construct
    # carrying an `entry_role` (actionability / probe_coverage /
    # admission_context) is an entry-owner read, never vector evidence, and
    # must not enter observed/inferred.
    def _is_entry_owner_read(construct: str) -> bool:
        row = constructs.get(construct)
        return bool(row and row.get("entry_role"))

    observed_refs = [
        s["construct"] for s in composed_slots
        if s["object_class"] == "world_observation" and s["state"] == "observed" and s["included_in_composition"]
        and not _is_entry_owner_read(s["construct"])
    ]
    inferred_refs = [
        s["construct"] for s in composed_slots
        if s["object_class"] in ("derived_view", "system_belief") and s["state"] in ("observed", "modeled") and s["included_in_composition"]
        and not _is_entry_owner_read(s["construct"])
    ]

    incorporation_legs = []
    for leg_name in (
        "I1_anticipation", "I2_immediate_response", "I3_estimate_revision",
        "I4_options_repricing", "I5_attention", "I6_peer_response", "I7_persistence_rejection",
    ):
        if leg_name == "I7_persistence_rejection":
            incorporation_legs.append({"leg": leg_name, "state": "ex_post_excluded", "slot_refs": []})
            continue
        mapped = _MARKET_REFLECTION_MAP.get(leg_name)
        slot = slots_by_construct.get(mapped) if mapped else None
        if slot is None:
            incorporation_legs.append({"leg": leg_name, "state": "missing", "slot_refs": []})
        else:
            incorporation_legs.append({"leg": leg_name, "state": _SLOT_STATE_TO_LEG_STATE.get(slot["state"], "unknown"), "slot_refs": [mapped]})

    # Sol item 2: composition and public validation share ONE frozen counting
    # rule, so a composed vector can never disagree with the recomputation that
    # judges it. Modeled legs count as included evidence.
    market_reflection = {
        "incorporation_legs": incorporation_legs,
        "denominator": _recompute_market_reflection_denominator(incorporation_legs),
    }

    observed_leg = {"slot_refs": observed_refs, "denominator": _leg_denominator(observed_refs, slots_by_construct)}
    inferred_leg = {
        "slot_refs": inferred_refs,
        "denominator": _leg_denominator(inferred_refs, slots_by_construct),
        "label": "owner_derived_system_belief",
    }

    if strongest_unresolved_fact is None:
        # Sol item 3: an entry-owner read is never evidence, so an absent one
        # is never "the strongest unresolved fact" about the opportunity — and
        # admission context in particular may not be referenced from any leg.
        excluded = [
            s for s in composed_slots
            if not s["included_in_composition"] and not _is_entry_owner_read(s["construct"])
        ]
        if excluded:
            first = excluded[0]
            strongest_unresolved_fact = {
                "state": "named",
                "fact": f"{first['construct']} unresolved: {first['exclusion_reason']}",
                "slot_refs": [first["construct"]],
            }
        else:
            strongest_unresolved_fact = {"state": "none_open", "fact": None, "slot_refs": []}

    if next_observable is None:
        next_observable = {"state": "none", "observable": None, "expected_clock_class": None, "expected_by": None}

    if entry_availability is None:
        entry_availability = _default_entry_availability(slots_by_construct)

    gates = list(failed_or_unavailable_gates or [])
    failed_or_unavailable_gates_leg = {
        "gates": gates,
        "denominator": _recompute_gate_denominator(gates),
    }

    projection = {
        "observed": observed_leg,
        "inferred": inferred_leg,
        "market_reflection": market_reflection,
        "strongest_unresolved_fact": strongest_unresolved_fact,
        "failed_or_unavailable_gates": failed_or_unavailable_gates_leg,
        "next_observable": next_observable,
        "entry_availability": entry_availability,
    }

    if permitted_consumers is None:
        permitted_consumers = ["research_session"]

    if generated_at is None:
        # Sol-repair MAJOR 4 (red-team 2026-08-25): defaulting purely to t0
        # backdated the generation clock behind the very object the vector
        # cites — the shipped FPI golden claimed it was generated eight days
        # before its own decision-time evidence existed. The default is now the
        # LATER of t0 and that object's recorded clock, so a composed vector is
        # never self-inconsistent (K3E_R021 enforces the same invariant on
        # anything a caller supplies). Still deterministic: both inputs are
        # caller-supplied, no wall clock is read.
        t0_stamp = f"{asof['value']}T00:00:00Z" if asof.get("grain") == "date" else asof["value"]
        recorded = ((asof.get("t0_evidence_ref") or {}).get("recorded_clock") or {}).get("value")
        rec_stamp = f"{recorded}T00:00:00Z" if isinstance(recorded, str) and len(recorded) == 10 else recorded
        candidates = [s for s in (t0_stamp, rec_stamp) if isinstance(s, str)]
        generated_at = max(candidates, key=lambda s: _parse_instant(s)) if candidates else t0_stamp

    vector = {
        "schema": "opportunity_evidence.vector.v1",
        "version": "1.0.0",
        "subject": subject,
        "asof": asof,
        "generated_at": generated_at,
        "authority": dict(_AUTHORITY_ENVELOPE),
        "display_only": True,
        "compilation_state": compilation_state,
        "slots": composed_slots,
        "projection": projection,
        "economic_cause_hypothesis": economic_cause_hypothesis,
        "denominator": denominator,
        "dominant_degradation": dominant_degradation,
        "permitted_consumers": list(permitted_consumers),
        "content_sha256": "0" * 64,
    }
    vector["content_sha256"] = compute_content_sha256(vector)
    return vector
