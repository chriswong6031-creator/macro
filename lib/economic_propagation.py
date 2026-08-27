"""K3-D Economic Propagation — hypothesis-record validator + deterministic composer.

This module is a pure in-memory VIEW/JOIN executor over the two frozen
contract files:

    contracts/economic_propagation/propagation_hypothesis.v1.schema.json
    contracts/economic_propagation/generator_registry.v1.json

It is never a store: nothing here writes to disk, creates a directory, or
persists any output. ``compose_hypothesis`` builds a record purely in memory
and returns it; the caller decides what (if anything) to do with the result.
It is never a graph: it reads owner evidence references and composes ONE
governed hypothesis/abstention record; it originates no edge, no score, no
rank, no grade, and no authority.

Three-graph law (D0, binding): Graph 1 = economic relationship (why transfer
could occur), Graph 2 = fundamental/narrative similarity (what is comparable),
Graph 3 = residual market (how the market treats the names now). Graph 2/3
evidence can NEVER launder a missing Graph-1 relationship, and a correct typed
abstention is a successful product behavior — this module must refuse where a
naive system would overclaim causality.

Binding kills, carried const in every record (``binding_kills``):
DNR:KILL-PSS-SR2-PEER-DIFFUSION, DNR:KILL-PSS-SR3-PARTICIPATION (the
participation target-generator construction is KILLED — any future peer-state
species needs an ORTHOGONAL source; peer participation/breadth alone never
admits a target here), DNR:KILL-CN-SUPPLY-ABSORPTION, DNR:KILL-CAUSAL-DAG-ALPHA.

Public surface:

    load_hypothesis_schema() / load_generator_registry()
        Repository-canonical contract loaders. No caller-supplied path
        override — callers always validate against the frozen files this
        repo ships (K1 no-vocabulary-injection law).

    validate_hypothesis(record) -> list[Finding]
        Structural (jsonschema draft 2020-12) + semantic (K3D_R0xx)
        validation. Fail-closed: unknown anything is a Finding, never a
        silent pass. Never raises on record defects.

    compose_hypothesis(...) -> dict
        Deterministic in-memory composition. Same input -> byte-identical
        output (record_id + content_sha256 included). Derives graph states,
        hypothesis state, mechanism gating and typed abstention from the
        legs; caller-authored summary/confidence/score of any kind is
        refused with EconomicPropagationError.
"""

from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from typing import Any, NamedTuple

from jsonschema import Draft202012Validator

# ---------------------------------------------------------------------------
# Contract locations (repo-canonical; never overridable by a caller).
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONTRACT_DIR = _REPO_ROOT / "contracts" / "economic_propagation"
_SCHEMA_PATH = _CONTRACT_DIR / "propagation_hypothesis.v1.schema.json"
_REGISTRY_PATH = _CONTRACT_DIR / "generator_registry.v1.json"

SCHEMA_ID = "economic_propagation.propagation_hypothesis/v1"

BINDING_KILLS = (
    "DNR:KILL-PSS-SR2-PEER-DIFFUSION",
    "DNR:KILL-PSS-SR3-PARTICIPATION",
    "DNR:KILL-CN-SUPPLY-ABSORPTION",
    "DNR:KILL-CAUSAL-DAG-ALPHA",
)

_AUTHORITY_CONST = {
    "trading": False,
    "ranking": False,
    "gating": False,
    "sizing": False,
    "entry": False,
    "originates_signals": False,
    "display_only": True,
    "permitted_consumers": ["research", "display"],
}

# Roles that assert a specific economic relationship. Claiming one requires
# role-specific owner evidence (K3D_R031) — a generic agreement or a
# financing-agent counterparty proves only that two names signed something.
_ROLE_SPECIFIC = frozenset(
    {
        "customer",
        "supplier",
        "partner",
        "competitor",
        "distributor",
        "licensor",
        "licensee",
        "common_customer",
        "common_supplier",
        "product_exposure",
        "end_market_exposure",
        "geography_exposure",
        "regulation_exposure",
        "program_participant",
        "facility_dependency",
        "bottleneck_dependency",
        "ownership_cashflow",
    }
)

_ROLE_EVIDENCE_SUFFICIENT = frozenset({"disclosed_role_specific", "strongly_evidenced_role"})

# Scalar-authority vocabulary that must not appear as a key anywhere in a
# record or in composer input. Defense in depth on top of
# additionalProperties:false — a caller smuggling a score through any object
# is refused by name, not by accident.
_FORBIDDEN_KEY_TOKENS = (
    "score",
    "confidence",
    "grade",
    "rank",
    "weight",
    "conviction",
    "probability",
    "alpha",
    "strength",
)

# Trade/price vocabulary forbidden in record prose: the predicted direction
# is an OPERATING direction, never a price forecast or trade instruction.
_TRADE_LANGUAGE = re.compile(
    r"\b(buy|buying|sell|selling|long|short|shorting|overweight|underweight"
    r"|outperform|underperform"
    r"|price\s+target|target\s+price|share\s+price|stock\s+price|upside|downside"
    r"|rally|returns?|alpha|entry|exit)\b",
    re.IGNORECASE,
)

# Scalar-authority vocabulary forbidden in ANY record prose (review MAJOR-2,
# 2026-08-27): a confidence/score/rank smuggled as a sentence is still a
# scalar authority claim. Flat word ban — reword the prose instead.
_AUTHORITY_LANGUAGE = re.compile(
    r"\b(confidence|conviction|probabilit(?:y|ies)|score[sd]?|scoring"
    r"|grade[sd]?|grading|rank(?:s|ed|ing)?)\b",
    re.IGNORECASE,
)

_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


class EconomicPropagationError(Exception):
    """Raised only for programmer errors in compose_hypothesis (malformed or
    unlawful caller input). validate_hypothesis never raises on record
    defects — it returns findings so a fail-closed caller sees every defect
    in one pass."""


class Finding(NamedTuple):
    code: str
    path: str
    message: str


def _f(code: str, path: str, message: str) -> Finding:
    return Finding(code=code, path=path, message=message)


@lru_cache(maxsize=1)
def load_hypothesis_schema() -> dict:
    """Load the frozen record schema. No path override exists by design."""

    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_generator_registry() -> dict:
    """Load the frozen generator registry. No path override exists by design."""

    return json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    schema = load_hypothesis_schema()
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


# ---------------------------------------------------------------------------
# Canonical serialization / deterministic identity.
# ---------------------------------------------------------------------------


def canonical_bytes(record: dict) -> bytes:
    """Canonical serialization used for content_sha256: sorted keys, no
    whitespace, UTF-8, with content_sha256 blanked."""

    shadow = dict(record)
    shadow["content_sha256"] = ""
    return json.dumps(shadow, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def content_sha256(record: dict) -> str:
    return hashlib.sha256(canonical_bytes(record)).hexdigest()


def derive_record_id(event_id: str, requested_key: str, asof: str) -> str:
    digest = hashlib.sha256(f"{event_id}\n{requested_key}\n{asof}".encode("utf-8")).hexdigest()
    return f"eph1:{digest[:16]}"


def _date_key(value: Any) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    m = _DATE_RE.match(value)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


# Exact keys the token scan must not flag: the contract's own vocabulary that
# happens to contain a forbidden substring. 'ranking' is the const-FALSE
# authority axis; 'claim_strength' is a closed enum, not a scalar.
_FORBIDDEN_KEY_ALLOWLIST = frozenset({"claim_strength", "ranking"})


def _scan_forbidden_keys(node: Any, path: str, out: list[Finding], code: str) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if str(key) in _FORBIDDEN_KEY_ALLOWLIST:
                # Allowlisted KEY only — the subtree underneath is still scanned.
                _scan_forbidden_keys(value, f"{path}.{key}", out, code)
                continue
            lowered = str(key).lower()
            for token in _FORBIDDEN_KEY_TOKENS:
                if token in lowered:
                    out.append(
                        _f(
                            code,
                            f"{path}.{key}",
                            f"forbidden scalar-authority key '{key}' (token '{token}'): no score, "
                            "confidence, grade, rank, weight or probability may exist anywhere in a "
                            "K3-D record",
                        )
                    )
            _scan_forbidden_keys(value, f"{path}.{key}", out, code)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _scan_forbidden_keys(item, f"{path}[{i}]", out, code)


# ---------------------------------------------------------------------------
# Derivations (single source of truth for composer AND validator).
# ---------------------------------------------------------------------------


def _usable(leg: dict) -> bool:
    return leg.get("usability_state") == "usable"


def derive_graph_states(
    relationship_paths: list[dict],
    similarity_evidence: list[dict],
    market_evidence: list[dict],
) -> dict:
    """Derive the three graph summary states from the legs. Only usable legs
    count. Graph-1 absence is unknown_unavailable — never a false
    relationship, never zero."""

    g1_legs = list(relationship_paths)
    usable_g1 = [leg for leg in g1_legs if _usable(leg)]
    role_specific = [
        leg
        for leg in usable_g1
        if leg.get("role") in _ROLE_SPECIFIC
        and leg.get("role_evidence_class") in _ROLE_EVIDENCE_SUFFICIENT
        and leg.get("claim_strength") in ("disclosed", "strongly_evidenced")
    ]
    if role_specific:
        graph_1 = "supported"
    elif usable_g1:
        graph_1 = "insufficient_role"
    elif g1_legs:
        if any(leg.get("usability_state") == "rights_blocked" for leg in g1_legs):
            graph_1 = "rights_blocked_only"
        else:
            graph_1 = "unknown_unavailable"
    else:
        graph_1 = "unknown_unavailable"

    graph_2 = "present" if any(_usable(leg) for leg in similarity_evidence) else "absent"
    graph_3 = "present" if any(_usable(leg) for leg in market_evidence) else "absent"
    return {"graph_1": graph_1, "graph_2": graph_2, "graph_3": graph_3}


def _effective_admissions(admissions: list[dict], registry: dict) -> list[dict]:
    rows = {row.get("generator_id"): row for row in registry.get("generators", [])}
    out = []
    for admission in admissions:
        row = rows.get(admission.get("generator_id"))
        if row is None or not row.get("admits_target", False):
            continue
        if admission.get("coverage_state") in ("covered", "partial"):
            out.append(admission)
    return out


def derive_abstention_reasons(
    resolution_state: str,
    graph_states: dict,
    admissions: list[dict],
    registry: dict,
    mechanism_hypothesized: bool,
    relationship_paths: list[dict] | tuple = (),
) -> list[str]:
    """Typed abstention reasons in a fixed, closed order.

    Truthfulness law (review MAJOR-4, 2026-08-27): no_graph1_evidence means
    ZERO Graph-1 legs exist. Evidence that exists but is unusable at the
    cutoff derives its own typed reason (rights_blocked, stale_owner_object,
    correction_not_yet_knowable, coverage_insufficient) — an abstention must
    never misreport "unusable now" as "does not exist"."""

    reasons: list[str] = []
    if resolution_state in ("CONFLICTING", "ENTITY_TYPE_CONFLICT"):
        return ["conflicting_identity"]
    if resolution_state in ("NOT_IN_MASTER", "UNRESOLVED", "UNSUPPORTED_MARKET", "DEFERRED_IDENTITY_EXCEPTION"):
        return ["unresolved_identity"]

    graph_1 = graph_states["graph_1"]
    g1_legs = [leg for leg in relationship_paths if isinstance(leg, dict)]
    if graph_1 == "insufficient_role":
        reasons.append("insufficient_role_evidence")
    elif graph_1 in ("unknown_unavailable", "rights_blocked_only") and g1_legs:
        states = {leg.get("usability_state") for leg in g1_legs}
        if "rights_blocked" in states:
            reasons.append("rights_blocked")
        if states & {"stale", "superseded"}:
            reasons.append("stale_owner_object")
        if "not_yet_knowable" in states:
            reasons.append("correction_not_yet_knowable")
        if "coverage_insufficient" in states:
            reasons.append("coverage_insufficient")
        if not reasons:
            reasons.append("no_graph1_evidence")
    elif graph_1 == "unknown_unavailable":
        reasons.append("no_graph1_evidence")

    if admissions and not _effective_admissions(admissions, registry) and "coverage_insufficient" not in reasons:
        reasons.append("coverage_insufficient")

    if graph_1 == "supported" and not mechanism_hypothesized:
        reasons.append("no_mechanism_hypothesized")
    return reasons


# ---------------------------------------------------------------------------
# Validator.
# ---------------------------------------------------------------------------


def validate_hypothesis(record: Any) -> list[Finding]:
    """Structural + semantic validation. Returns every finding; empty list
    means the record is contract-lawful."""

    findings: list[Finding] = []
    if not isinstance(record, dict):
        return [_f("K3D_R000", "$", "record must be a JSON object")]

    for error in sorted(_schema_validator().iter_errors(record), key=lambda e: str(e.json_path)):
        findings.append(_f("K3D_R001", error.json_path, error.message[:400]))

    version = record.get("version")
    if not (isinstance(version, int) and not isinstance(version, bool) and version == 1):
        findings.append(
            _f(
                "K3D_R002",
                "$.version",
                f"version must be the INTEGER 1 (got {version!r}): a float 1.0 satisfies numeric "
                "equality but changes the canonical bytes across producers",
            )
        )

    registry = load_generator_registry()
    vocabulary = registry.get("construct_vocabulary", {})
    generator_rows = {row.get("generator_id"): row for row in registry.get("generators", [])}

    target = record.get("target") if isinstance(record.get("target"), dict) else {}
    resolution = target.get("resolution") if isinstance(target.get("resolution"), dict) else {}
    resolution_state = resolution.get("resolution_state")

    admissions = record.get("generator_admissions") if isinstance(record.get("generator_admissions"), list) else []
    g1_legs = record.get("relationship_paths") if isinstance(record.get("relationship_paths"), list) else []
    g2_legs = record.get("similarity_evidence") if isinstance(record.get("similarity_evidence"), list) else []
    g3_legs = record.get("market_evidence") if isinstance(record.get("market_evidence"), list) else []
    mechanism = record.get("mechanism") if isinstance(record.get("mechanism"), dict) else {}
    abstention = record.get("abstention") if isinstance(record.get("abstention"), dict) else {}

    # --- K3D_R010: exact-identity gate precedes every semantic inference.
    if resolution_state != "RESOLVED":
        if abstention.get("abstained") is not True:
            findings.append(
                _f(
                    "K3D_R010",
                    "$.abstention.abstained",
                    f"target resolution_state={resolution_state!r}: the record MUST be a typed "
                    "abstention — a convenient ticker/theme/member string is not permission to "
                    "guess the target entity",
                )
            )
        for name, legs in (
            ("generator_admissions", admissions),
            ("relationship_paths", g1_legs),
            ("similarity_evidence", g2_legs),
            ("market_evidence", g3_legs),
        ):
            if legs:
                findings.append(
                    _f(
                        "K3D_R011",
                        f"$.{name}",
                        f"target resolution_state={resolution_state!r}: abstention precedes semantic "
                        f"inference, so {name} must be empty",
                    )
                )
        if mechanism.get("state") == "hypothesized":
            findings.append(
                _f("K3D_R012", "$.mechanism.state", "unresolved/conflicting identity cannot carry a hypothesized mechanism")
            )
    else:
        if resolution.get("issuer_id") in (None, ""):
            findings.append(
                _f("K3D_R013", "$.target.resolution.issuer_id", "RESOLVED requires a non-null Data OS/Stock Identity issuer_id")
            )
        if not admissions and (abstention.get("abstained") is not True or g1_legs or g2_legs or g3_legs):
            findings.append(
                _f(
                    "K3D_R023",
                    "$.generator_admissions",
                    "a resolved record carrying evidence (or claiming support) needs at least one "
                    "admitting generator (journey step 6) — evidence with no admitting generator is "
                    "an unexplained target",
                )
            )

    # --- K3D_R02x: generator admissions against the frozen registry.
    for i, admission in enumerate(admissions):
        if not isinstance(admission, dict):
            continue
        path = f"$.generator_admissions[{i}]"
        gen_id = admission.get("generator_id")
        row = generator_rows.get(gen_id)
        if row is None:
            findings.append(_f("K3D_R020", f"{path}.generator_id", f"unknown generator_id {gen_id!r}: not in generator_registry.v1"))
        else:
            if not row.get("admits_target", False):
                findings.append(
                    _f(
                        "K3D_R021",
                        f"{path}.generator_id",
                        f"generator {gen_id!r} is a REFUSAL row: peer participation/breadth alone can "
                        "never admit a target as economic propagation "
                        "(DNR:KILL-PSS-SR2-PEER-DIFFUSION, DNR:KILL-PSS-SR3-PARTICIPATION)",
                    )
                )
            if admission.get("graph") != row.get("graph"):
                findings.append(
                    _f(
                        "K3D_R022",
                        f"{path}.graph",
                        f"admission graph {admission.get('graph')!r} does not match registry graph "
                        f"{row.get('graph')!r} for generator {gen_id!r}",
                    )
                )
            if admission.get("construct") != row.get("construct"):
                findings.append(
                    _f(
                        "K3D_R022",
                        f"{path}.construct",
                        f"admission construct {admission.get('construct')!r} does not match registry "
                        f"construct {row.get('construct')!r} for generator {gen_id!r}",
                    )
                )

    # --- K3D_R03x: construct->graph vocabulary + owner/grammar/role bindings.
    construct_owners = registry.get("construct_owners", {})
    owner_grammars = registry.get("owner_evidence_grammars", {})
    role_constructs = registry.get("graph1_role_constructs", {})
    g2_basis_constructs = registry.get("graph2_basis_constructs", {})
    g3_basis_constructs = registry.get("graph3_basis_constructs", {})

    def _check_owner_binding(path: str, construct: Any, owner_ref: Any) -> None:
        allowed = construct_owners.get(construct)
        owner = owner_ref.get("owner_program") if isinstance(owner_ref, dict) else None
        if allowed is not None and owner is not None and owner not in allowed:
            findings.append(
                _f(
                    "K3D_R034",
                    f"{path}.owner_ref.owner_program",
                    f"owner {owner!r} is not a lawful owner of construct {construct!r} "
                    f"(lawful: {allowed!r}) — a construct claim is only as good as the owner "
                    "surface that can actually carry it",
                )
            )

    def _check_evidence_grammar(path: str, construct: Any, owner_ref: Any, evidence_refs: Any, expected_graph: str) -> None:
        owner = owner_ref.get("owner_program") if isinstance(owner_ref, dict) else None
        grammar = owner_grammars.get(owner)
        if not grammar or not isinstance(evidence_refs, list):
            return
        prefix = grammar.get(f"{expected_graph}_edge_prefix")
        if not prefix:
            return
        pattern = re.compile(prefix)
        for j, ref in enumerate(evidence_refs):
            if isinstance(ref, str) and re.match(r"^[a-z_]+:", ref) and not pattern.match(ref):
                findings.append(
                    _f(
                        "K3D_R035",
                        f"{path}.evidence_refs[{j}]",
                        f"LAUNDERING: evidence ref {ref[:80]!r} is not a {expected_graph}-type object "
                        f"of owner {owner!r} (required prefix {prefix!r}) — re-labeling a "
                        "membership/expression edge as an economic relationship is refused by the "
                        "owner's own id grammar",
                    )
                )

    for name, legs, expected_graph in (
        ("relationship_paths", g1_legs, "graph_1"),
        ("similarity_evidence", g2_legs, "graph_2"),
        ("market_evidence", g3_legs, "graph_3"),
    ):
        for i, leg in enumerate(legs):
            if not isinstance(leg, dict):
                continue
            path = f"$.{name}[{i}]"
            construct = leg.get("construct")
            vocab_graph = vocabulary.get(construct)
            if vocab_graph is None:
                findings.append(_f("K3D_R030", f"{path}.construct", f"unknown construct {construct!r}"))
            elif vocab_graph != expected_graph:
                findings.append(
                    _f(
                        "K3D_R032",
                        f"{path}.construct",
                        f"LAUNDERING: construct {construct!r} belongs to {vocab_graph}, but this leg "
                        f"claims {expected_graph} — Graph 2/3 evidence can never fill a Graph-1 role "
                        "and no opaque RELATED flattening exists in this contract",
                    )
                )
            _check_owner_binding(path, construct, leg.get("owner_ref"))
            _check_evidence_grammar(path, construct, leg.get("owner_ref"), leg.get("evidence_refs"), expected_graph)

    for i, admission in enumerate(admissions):
        if isinstance(admission, dict):
            path = f"$.generator_admissions[{i}]"
            _check_owner_binding(path, admission.get("construct"), admission.get("owner_ref"))
            vocab_graph = vocabulary.get(admission.get("construct"))
            if vocab_graph in ("graph_1", "graph_2", "graph_3"):
                _check_evidence_grammar(path, admission.get("construct"), admission.get("owner_ref"), admission.get("evidence_refs"), vocab_graph)

    for i, leg in enumerate(g2_legs):
        if isinstance(leg, dict):
            basis = leg.get("comparability_basis")
            allowed_constructs = g2_basis_constructs.get(basis)
            if allowed_constructs is not None and leg.get("construct") not in allowed_constructs:
                findings.append(
                    _f(
                        "K3D_R036",
                        f"$.similarity_evidence[{i}].comparability_basis",
                        f"basis {basis!r} does not cohere with construct {leg.get('construct')!r} "
                        f"(lawful constructs: {allowed_constructs!r})",
                    )
                )
    for i, leg in enumerate(g3_legs):
        if isinstance(leg, dict):
            basis = leg.get("market_state_basis")
            allowed_constructs = g3_basis_constructs.get(basis)
            if allowed_constructs is not None and leg.get("construct") not in allowed_constructs:
                findings.append(
                    _f(
                        "K3D_R036",
                        f"$.market_evidence[{i}].market_state_basis",
                        f"basis {basis!r} does not cohere with construct {leg.get('construct')!r} "
                        f"(lawful constructs: {allowed_constructs!r}) — participation/breadth "
                        "evidence cannot travel under a residual/sympathy label",
                    )
                )

    for i, leg in enumerate(g1_legs):
        if not isinstance(leg, dict):
            continue
        path = f"$.relationship_paths[{i}]"
        role = leg.get("role")
        role_class = leg.get("role_evidence_class")
        construct = leg.get("construct")
        if role in _ROLE_SPECIFIC and role_class not in _ROLE_EVIDENCE_SUFFICIENT:
            findings.append(
                _f(
                    "K3D_R031",
                    f"{path}.role",
                    f"role {role!r} claimed on role_evidence_class {role_class!r}: a generic "
                    "agreement, financing-agent counterparty, ownership-without-cash-flow-rights or "
                    "absent source can only carry role_unknown",
                )
            )
        if construct == "disclosed_agreement_role_unknown" and role != "role_unknown":
            findings.append(
                _f(
                    "K3D_R031",
                    f"{path}.role",
                    "construct disclosed_agreement_role_unknown can only carry role=role_unknown "
                    "(who-supplies-whom is not disclosed)",
                )
            )
        if role == "ownership_cashflow" and construct != "ownership_cashflow_change":
            findings.append(
                _f(
                    "K3D_R031",
                    f"{path}.role",
                    "ownership_cashflow requires construct ownership_cashflow_change (ownership counts "
                    "only when it changes cash-flow rights)",
                )
            )
        if leg.get("claim_strength") == "disclosed" and role_class != "disclosed_role_specific":
            findings.append(
                _f(
                    "K3D_R033",
                    f"{path}.claim_strength",
                    "claim_strength=disclosed requires role_evidence_class=disclosed_role_specific",
                )
            )
        allowed_role_constructs = role_constructs.get(role)
        if allowed_role_constructs is not None and construct not in allowed_role_constructs:
            findings.append(
                _f(
                    "K3D_R037",
                    f"{path}.role",
                    f"role {role!r} does not cohere with construct {construct!r} "
                    f"(lawful constructs: {allowed_role_constructs!r})",
                )
            )

    # --- K3D_R04x: mechanism gating + operating-direction-only law.
    graph_states_claimed = record.get("graph_states") if isinstance(record.get("graph_states"), dict) else {}
    if mechanism.get("state") == "hypothesized":
        for field in ("mechanism_class", "hypothesis_text", "predicted_operating_direction", "operating_metric_class"):
            if mechanism.get(field) is None:
                findings.append(_f("K3D_R040", f"$.mechanism.{field}", "hypothesized mechanism requires a non-null value here"))
    elif mechanism.get("state") == "abstained":
        for field in ("mechanism_class", "hypothesis_text", "predicted_operating_direction", "operating_metric_class"):
            if mechanism.get(field) is not None:
                findings.append(
                    _f(
                        "K3D_R040",
                        f"$.mechanism.{field}",
                        "abstained mechanism must carry null here — a partial object must not read "
                        "as confirmed transfer",
                    )
                )
    text = mechanism.get("hypothesis_text")
    if isinstance(text, str):
        match = _TRADE_LANGUAGE.search(text)
        if match:
            findings.append(
                _f(
                    "K3D_R041",
                    "$.mechanism.hypothesis_text",
                    f"trade/price vocabulary {match.group(0)!r} in mechanism prose: the prediction is an "
                    "operating direction, never a price return or trade direction",
                )
            )

    # --- K3D_R043: authority/trade language in ANY free-prose field (review
    # MAJOR-2): a confidence/score/rank/trade instruction smuggled as a
    # sentence is still an authority claim. Flat word ban; reword the prose.
    prose_fields: list[tuple[str, Any]] = [("$.mechanism.hypothesis_text", text)]
    alternatives = record.get("alternatives") if isinstance(record.get("alternatives"), list) else []
    falsifiers = record.get("falsifiers") if isinstance(record.get("falsifiers"), list) else []
    expiry = record.get("expiry") if isinstance(record.get("expiry"), dict) else {}
    for i, alt in enumerate(alternatives):
        if isinstance(alt, dict):
            prose_fields.append((f"$.alternatives[{i}].text", alt.get("text")))
    for i, fz in enumerate(falsifiers):
        if isinstance(fz, dict):
            prose_fields.append((f"$.falsifiers[{i}].condition", fz.get("condition")))
            prose_fields.append((f"$.falsifiers[{i}].observable", fz.get("observable")))
    prose_fields.append(("$.expiry.note", expiry.get("note")))
    for prose_path, prose in prose_fields:
        if not isinstance(prose, str):
            continue
        hit = _AUTHORITY_LANGUAGE.search(prose)
        if hit:
            findings.append(
                _f(
                    "K3D_R043",
                    prose_path,
                    f"scalar-authority vocabulary {hit.group(0)!r} in record prose: no confidence, "
                    "score, grade, rank or probability may be asserted anywhere in a K3-D record",
                )
            )
        if prose_path != "$.mechanism.hypothesis_text":
            hit2 = _TRADE_LANGUAGE.search(prose)
            if hit2:
                findings.append(
                    _f(
                        "K3D_R043",
                        prose_path,
                        f"trade/price vocabulary {hit2.group(0)!r} in record prose: a hypothesis "
                        "record carries no trade instruction in any field",
                    )
                )

    # --- K3D_R05x: derived fields must equal the derivation (no caller-authored summaries).
    derived_states = derive_graph_states(
        [leg for leg in g1_legs if isinstance(leg, dict)],
        [leg for leg in g2_legs if isinstance(leg, dict)],
        [leg for leg in g3_legs if isinstance(leg, dict)],
    )
    if graph_states_claimed != derived_states:
        findings.append(
            _f(
                "K3D_R051",
                "$.graph_states",
                f"caller-authored graph_states {graph_states_claimed!r} != derived {derived_states!r}: "
                "summary availability/state is compiler-derived from the legs, never authored",
            )
        )
        if (
            graph_states_claimed.get("graph_1") == "supported"
            and derived_states["graph_1"] != "supported"
            and any(isinstance(leg, dict) and not _usable(leg) for leg in g1_legs)
        ):
            findings.append(
                _f(
                    "K3D_R063",
                    "$.relationship_paths",
                    "non-usable (rights_blocked/stale/not_yet_knowable/superseded) evidence was "
                    "counted toward a supported Graph-1 state",
                )
            )

    mechanism_hypothesized = mechanism.get("state") == "hypothesized"
    expected_reasons: list[str] | None = None
    if isinstance(resolution_state, str):
        expected_reasons = derive_abstention_reasons(
            resolution_state,
            derived_states,
            [a for a in admissions if isinstance(a, dict)],
            registry,
            mechanism_hypothesized,
            [leg for leg in g1_legs if isinstance(leg, dict)],
        )
        claimed_reasons = abstention.get("reasons") if isinstance(abstention.get("reasons"), list) else []
        expected_abstained = bool(expected_reasons)
        if bool(abstention.get("abstained")) != expected_abstained or claimed_reasons != expected_reasons:
            findings.append(
                _f(
                    "K3D_R053",
                    "$.abstention",
                    f"abstention {{abstained: {abstention.get('abstained')!r}, reasons: {claimed_reasons!r}}} "
                    f"!= derived {{abstained: {expected_abstained!r}, reasons: {expected_reasons!r}}}",
                )
            )

    # Unified headline (review MAJOR-5): supported_hypothesis IFF the derived
    # abstention is empty — a record can never be supported AND abstained.
    if expected_reasons is not None:
        expected_hypothesis_state = "supported_hypothesis" if not expected_reasons else "abstained"
    else:
        expected_hypothesis_state = "abstained"
    if record.get("hypothesis_state") != expected_hypothesis_state:
        findings.append(
            _f(
                "K3D_R052",
                "$.hypothesis_state",
                f"hypothesis_state {record.get('hypothesis_state')!r} != derived {expected_hypothesis_state!r}",
            )
        )
    if mechanism_hypothesized and (derived_states["graph_1"] != "supported" or (expected_reasons or [])):
        findings.append(
            _f(
                "K3D_R042",
                "$.mechanism.state",
                f"mechanism hypothesized while the derived record abstains "
                f"(graph_1={derived_states['graph_1']!r}, reasons={expected_reasons!r}): "
                "an abstaining record cannot carry a confident mechanism",
            )
        )

    # --- K3D_R06x: clocks. Evidence known after the cutoff cannot participate.
    asof_key = _date_key(record.get("asof"))
    if asof_key is not None:
        for name, rows in (
            ("generator_admissions", admissions),
            ("relationship_paths", g1_legs),
            ("similarity_evidence", g2_legs),
            ("market_evidence", g3_legs),
        ):
            for i, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                for clock in ("asof", "known_at"):
                    key = _date_key(row.get(clock))
                    if key is None:
                        findings.append(
                            _f("K3D_R060", f"$.{name}[{i}].{clock}", "evidence clock missing or unparseable")
                        )
                    elif key > asof_key:
                        findings.append(
                            _f(
                                "K3D_R061",
                                f"$.{name}[{i}].{clock}",
                                f"LOOKAHEAD: {clock}={row.get(clock)!r} is after the record cutoff "
                                f"asof={record.get('asof')!r} — later filings/edges/corrections cannot "
                                "rewrite a prior as-of hypothesis",
                            )
                        )
        source_event_obj = record.get("source_event") if isinstance(record.get("source_event"), dict) else {}
        for clock in ("event_time", "known_at"):
            key = _date_key(source_event_obj.get(clock))
            if key is not None and key > asof_key:
                findings.append(
                    _f(
                        "K3D_R061",
                        f"$.source_event.{clock}",
                        f"LOOKAHEAD: source event {clock}={source_event_obj.get(clock)!r} is after the "
                        f"record cutoff asof={record.get('asof')!r}",
                    )
                )
        source_identity = source_event_obj.get("source_identity") if isinstance(source_event_obj.get("source_identity"), dict) else {}
        for res_path, res_obj in (
            ("$.target.resolution.resolution_asof", resolution),
            ("$.source_event.source_identity.resolution_asof", source_identity),
        ):
            key = _date_key(res_obj.get("resolution_asof"))
            if key is not None and key > asof_key:
                findings.append(
                    _f(
                        "K3D_R061",
                        res_path,
                        f"LOOKAHEAD: identity resolution_asof={res_obj.get('resolution_asof')!r} is after "
                        f"the record cutoff asof={record.get('asof')!r} — a future identity verdict is "
                        "not lawful evidence",
                    )
                )
        expiry_obj = record.get("expiry") if isinstance(record.get("expiry"), dict) else {}
        review_key = _date_key(expiry_obj.get("review_by"))
        if review_key is not None and review_key <= asof_key:
            findings.append(
                _f(
                    "K3D_R064",
                    "$.expiry.review_by",
                    f"review_by={expiry_obj.get('review_by')!r} is not after asof={record.get('asof')!r}: "
                    "a record expired at composition is not a live hypothesis",
                )
            )
        compiled_key = _date_key(record.get("compiled_at"))
        if compiled_key is not None and compiled_key < asof_key:
            findings.append(
                _f("K3D_R062", "$.compiled_at", "compiled_at earlier than asof cutoff: a record cannot be compiled before its own cutoff")
            )

    # --- K3D_R07x: zero authority, forbidden scalars, reserved axes.
    if record.get("authority") != _AUTHORITY_CONST:
        findings.append(_f("K3D_R070", "$.authority", "authority must be the const all-false object"))
    _scan_forbidden_keys(record, "$", findings, "K3D_R071")
    if record.get("economic_share") is not None:
        findings.append(
            _f(
                "K3D_R072",
                "$.economic_share",
                "economic_share is formula-unowned and reserved: it stays null until its canonical "
                "owner mints a formula; K3-D may not invent one",
            )
        )

    # --- K3D_R08x: deterministic identity.
    source_event = record.get("source_event") if isinstance(record.get("source_event"), dict) else {}
    event_id = source_event.get("event_id")
    requested_key = target.get("requested_key")
    asof = record.get("asof")
    if isinstance(event_id, str) and isinstance(requested_key, str) and isinstance(asof, str):
        expected_id = derive_record_id(event_id, requested_key, asof)
        if record.get("record_id") != expected_id:
            findings.append(
                _f("K3D_R082", "$.record_id", f"record_id {record.get('record_id')!r} != derived {expected_id!r}")
            )
    claimed_sha = record.get("content_sha256")
    if isinstance(claimed_sha, str) and re.fullmatch(r"[0-9a-f]{64}", claimed_sha):
        expected_sha = content_sha256(record)
        if claimed_sha != expected_sha:
            findings.append(
                _f("K3D_R081", "$.content_sha256", "content_sha256 does not match the canonical serialization")
            )

    return findings


# ---------------------------------------------------------------------------
# Composer.
# ---------------------------------------------------------------------------

_DERIVED_FIELDS = frozenset(
    {
        "graph_states",
        "hypothesis_state",
        "abstention",
        "authority",
        "binding_kills",
        "economic_share",
        "record_id",
        "content_sha256",
        "schema",
        "version",
    }
)


def _refuse_derived_or_scored(part: Any, label: str) -> None:
    if isinstance(part, dict):
        for key in part:
            if key in _DERIVED_FIELDS:
                raise EconomicPropagationError(
                    f"{label} carries derived/authority field {key!r}: summary state, authority and "
                    "identity are compiler-derived, never caller-authored"
                )
    findings: list[Finding] = []
    _scan_forbidden_keys(part, label, findings, "K3D_R071")
    if findings:
        raise EconomicPropagationError(findings[0].message)


def compose_hypothesis(
    *,
    source_event: dict,
    target: dict,
    asof: str,
    compiled_at: str,
    generator_admissions: list[dict] | tuple = (),
    relationship_paths: list[dict] | tuple = (),
    similarity_evidence: list[dict] | tuple = (),
    market_evidence: list[dict] | tuple = (),
    mechanism_proposal: dict | None = None,
    alternatives: list[dict],
    falsifiers: list[dict],
    expiry: dict,
) -> dict:
    """Compose one propagation_hypothesis/v1 record deterministically.

    The composer derives graph states, hypothesis state, mechanism gating and
    typed abstention. It never reads a wall clock, never touches disk beyond
    the frozen contract files, and returns a record that passes
    validate_hypothesis with zero findings — or raises EconomicPropagationError
    on unlawful caller input."""

    for label, part in (
        ("source_event", source_event),
        ("target", target),
        ("mechanism_proposal", mechanism_proposal),
        ("expiry", expiry),
    ):
        _refuse_derived_or_scored(part, label)
    for label, rows in (
        ("generator_admissions", generator_admissions),
        ("relationship_paths", relationship_paths),
        ("similarity_evidence", similarity_evidence),
        ("market_evidence", market_evidence),
        ("alternatives", alternatives),
        ("falsifiers", falsifiers),
    ):
        for i, row in enumerate(rows):
            _refuse_derived_or_scored(row, f"{label}[{i}]")

    resolution = target.get("resolution") if isinstance(target.get("resolution"), dict) else {}
    resolution_state = resolution.get("resolution_state")
    if resolution_state not in (
        "RESOLVED",
        "NOT_IN_MASTER",
        "UNRESOLVED",
        "CONFLICTING",
        "UNSUPPORTED_MARKET",
        "DEFERRED_IDENTITY_EXCEPTION",
        "ENTITY_TYPE_CONFLICT",
    ):
        raise EconomicPropagationError(f"target.resolution.resolution_state {resolution_state!r} is not a lawful state")

    admissions = [dict(a) for a in generator_admissions]
    g1_legs = [dict(leg) for leg in relationship_paths]
    g2_legs = [dict(leg) for leg in similarity_evidence]
    g3_legs = [dict(leg) for leg in market_evidence]

    if resolution_state != "RESOLVED":
        if admissions or g1_legs or g2_legs or g3_legs:
            raise EconomicPropagationError(
                f"target is {resolution_state}: typed abstention precedes semantic inference — "
                "evidence legs and generator admissions are unlawful on an unresolved identity"
            )
        if mechanism_proposal is not None:
            raise EconomicPropagationError(f"target is {resolution_state}: a mechanism cannot be hypothesized")
    else:
        if not admissions:
            raise EconomicPropagationError("a resolved target requires at least one generator admission")

    registry = load_generator_registry()
    generator_rows = {row.get("generator_id"): row for row in registry.get("generators", [])}
    for admission in admissions:
        row = generator_rows.get(admission.get("generator_id"))
        if row is None:
            raise EconomicPropagationError(f"unknown generator_id {admission.get('generator_id')!r}")
        if not row.get("admits_target", False):
            raise EconomicPropagationError(
                f"generator {admission.get('generator_id')!r} is a refusal row: participation/breadth "
                "alone can never admit a target as economic propagation"
            )

    graph_states = derive_graph_states(g1_legs, g2_legs, g3_legs)
    base_reasons = derive_abstention_reasons(
        resolution_state, graph_states, admissions, registry, True, g1_legs
    )

    if mechanism_proposal is not None:
        if graph_states["graph_1"] != "supported" or base_reasons:
            raise EconomicPropagationError(
                f"mechanism proposed while the record abstains "
                f"(graph_1={graph_states['graph_1']!r}, reasons={base_reasons!r}): "
                "an abstaining record cannot carry a confident mechanism — "
                "compose the abstention instead"
            )
        for field in ("mechanism_class", "hypothesis_text", "predicted_operating_direction", "operating_metric_class"):
            if mechanism_proposal.get(field) in (None, ""):
                raise EconomicPropagationError(f"mechanism_proposal.{field} is required")
        match = _TRADE_LANGUAGE.search(str(mechanism_proposal.get("hypothesis_text")))
        if match:
            raise EconomicPropagationError(
                f"mechanism prose contains trade/price vocabulary {match.group(0)!r}: predicted "
                "direction is an operating direction only"
            )
        mechanism = {
            "state": "hypothesized",
            "mechanism_class": mechanism_proposal["mechanism_class"],
            "hypothesis_text": mechanism_proposal["hypothesis_text"],
            "predicted_operating_direction": mechanism_proposal["predicted_operating_direction"],
            "operating_metric_class": mechanism_proposal["operating_metric_class"],
        }
    else:
        mechanism = {
            "state": "abstained",
            "mechanism_class": None,
            "hypothesis_text": None,
            "predicted_operating_direction": None,
            "operating_metric_class": None,
        }

    mechanism_hypothesized = mechanism["state"] == "hypothesized"
    reasons = derive_abstention_reasons(
        resolution_state, graph_states, admissions, registry, mechanism_hypothesized, g1_legs
    )
    hypothesis_state = "supported_hypothesis" if not reasons else "abstained"

    record = {
        "schema": SCHEMA_ID,
        "version": 1,
        "record_id": derive_record_id(str(source_event.get("event_id")), str(target.get("requested_key")), asof),
        "binding_kills": list(BINDING_KILLS),
        "asof": asof,
        "compiled_at": compiled_at,
        "source_event": dict(source_event),
        "target": {"requested_key": target.get("requested_key"), "resolution": dict(resolution)},
        "generator_admissions": admissions,
        "relationship_paths": g1_legs,
        "similarity_evidence": g2_legs,
        "market_evidence": g3_legs,
        "graph_states": graph_states,
        "mechanism": mechanism,
        "hypothesis_state": hypothesis_state,
        "abstention": {"abstained": bool(reasons), "reasons": reasons},
        "alternatives": [dict(a) for a in alternatives],
        "falsifiers": [dict(fz) for fz in falsifiers],
        "expiry": dict(expiry),
        "authority": json.loads(json.dumps(_AUTHORITY_CONST)),
        "economic_share": None,
        "content_sha256": "",
    }
    record["content_sha256"] = content_sha256(record)

    findings = validate_hypothesis(record)
    if findings:
        raise EconomicPropagationError(
            "composed record failed its own contract (first finding: "
            f"{findings[0].code} {findings[0].path} {findings[0].message})"
        )
    return record
