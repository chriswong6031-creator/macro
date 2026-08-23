"""Pure deterministic MAS-28 V1 PR-linkage observer.

This module deliberately has no filesystem, network, clock, environment or git dependency.
Adapters supply a frozen observation; the CLI is the only layer which reads/writes bytes.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

OBS_SCHEMA = "mastermind.pr_linkage_observation.v1"
REPORT_SCHEMA = "mastermind.pr_linkage_report.v1"
RULESET_ID = "mastermind.pr_linkage_rules.v1"
FROZEN_RULESET_DIGEST = "41d5634a6ca6d4bbd993e728b73d839260452b24c891e556c59da52a184a1859"
FIELDS = ("Workstream", "Linear", "Portfolio-Mode", "Wave", "Authority", "Completion")
STATE = {"PRESENT", "PARTIAL", "UNAVAILABLE", "NOT_APPLICABLE", "CONTRADICTORY"}
ALIASES_BY_FIELD = {
    "Portfolio-Mode": {"workstream_creation": "creates_workstream"},
    "Authority": {"runtime": "implementation", "production-proof": "proof"},
    "Completion": {"production-proof-required": "proof-required"},
}
ENUMS = {"Portfolio-Mode": {"tracked", "maintenance_exception", "creates_workstream", "architecture_candidate"},
         "Authority": {"implementation", "records", "research", "maintenance", "proof", "deploy", "architecture_candidate"},
         "Completion": {"merge-is-done", "built-not-proven", "proof-required", "acceptance-required", "records-only"}}
SEVERITY = {"ERROR": 0, "PARTIAL": 1, "WARNING": 2, "NOTICE": 3}
# This closed registry is intentionally explicit: implementation may never grow a hidden rule
# outside the frozen manifest.  `analyze` verifies equality before semantic reduction.
FROZEN_RULE_IDS = frozenset((
 "R001","R002","R003","R004","R005","R006","R007","R008","R009","R010","R011","R012","R020","R021","R022","R026","R027","R028","R029","R030","R031","R032","R033","R034","R035","R036","R037","R038","R039","R040","R041","R042","R043","R044","R045","R046","R047","R050","R051","R052","R053","R054","R055","R056","R060","R061"))
FROZEN_FINDINGS = {
 "R001":("HEADER_MISSING","ERROR","ADD_CANONICAL_HEADER",("missing_fields",)),"R002":("HEADER_DUPLICATE","ERROR","REMOVE_DUPLICATE_FIELD",("field","locations","values")),"R003":("HEADER_AUTHORITY_ZONE_INVALID","ERROR","REPAIR_AUTHORITY_ZONE",("location","reason")),"R004":("PLACEHOLDER_UNRESOLVED","ERROR","REPLACE_PLACEHOLDER",("field","location","value")),"R005":("WORKSTREAM_ID_INVALID","ERROR","USE_EXACT_WORKSTREAM_ID",("location","value")),"R006":("LINEAR_ID_INVALID","ERROR","USE_EXACT_LINEAR_ID",("location","value")),"R007":("WAVE_EMPTY","ERROR","SET_BOUNDED_WAVE",("location",)),"R008":("WAVE_INVALID","ERROR","SET_BOUNDED_WAVE",("location","value")),"R009":("PORTFOLIO_MODE_INVALID","ERROR","SET_CANONICAL_PORTFOLIO_MODE",("location","value")),"R010":("PORTFOLIO_MODE_RESERVED","ERROR","REMOVE_RESERVED_MODE",("location","value")),"R011":("AUTHORITY_INVALID","ERROR","SET_CANONICAL_AUTHORITY",("location","value")),"R012":("COMPLETION_INVALID","ERROR","SET_CANONICAL_COMPLETION",("location","value")),
 "R020":("AUTHORING_SCHEMA_VERSION_MISMATCH","ERROR","MIGRATE_TO_V1",("epoch","field","value")),"R021":("LEGACY_AUTHORING_ALIAS","NOTICE","MIGRATE_TO_V1",("alias","canonical","field","receipt")),"R022":("AUTHORING_CUTOVER_RELATION_UNAVAILABLE","PARTIAL","SUPPLY_CUTOVER_RECEIPT",("epoch_state","receipt_digest")),"R026":("LINEAR_TARGET_ROLE_UNAVAILABLE","PARTIAL","SUPPLY_COMPLETE_LINEAR_TARGET_ROLES",("required_targets","target_roles")),"R027":("LINEAR_TARGET_ROLE_MISMATCH","ERROR","REPAIR_LINEAR_TARGET_ROLES",("declared","roles","targets")),"R028":("LINEAR_ISSUE_TYPE_MISMATCH","ERROR","REPAIR_LINEAR_ISSUE_TYPE",("issue_type","portfolio_mode","target_role")),"R029":("LINEAR_REQUIRED_FOR_MODE","ERROR","SET_CONCRETE_LINEAR_ISSUE",("linear","portfolio_mode")),"R030":("WORKSTREAM_UNKNOWN","ERROR","USE_EXISTING_WORKSTREAM",("workstream",)),"R031":("WORKSTREAM_REQUIRED_FOR_TRACKED","ERROR","SET_TRACKED_WORKSTREAM",("portfolio_mode","workstream")),"R032":("WORKSTREAM_MUST_BE_NONE_FOR_EXCEPTION","ERROR","SET_WORKSTREAM_NONE",("portfolio_mode","workstream")),"R033":("AGENTOS_SNAPSHOT_UNAVAILABLE","PARTIAL","SUPPLY_AGENTOS_SNAPSHOT",("snapshot_state","workstream")),"R034":("LINEAR_ISSUE_UNKNOWN","ERROR","USE_EXISTING_LINEAR_ISSUE",("linear",)),"R035":("LINEAR_SNAPSHOT_UNAVAILABLE","PARTIAL","SUPPLY_LINEAR_SNAPSHOT",("linear","snapshot_state")),"R036":("LINEAR_PROJECT_WORKSTREAM_MISMATCH","ERROR","REPAIR_LINEAR_BINDING",("bound_workstream","declared_workstream","linear")),"R037":("WORKSTREAM_CREATION_NO_WORKSTREAM_RECORD","ERROR","ADD_EXACT_WORKSTREAM_RECORD",("paths","workstream")),"R038":("WORKSTREAM_CREATION_KEY_COLLISION","ERROR","CHOOSE_UNIQUE_WORKSTREAM_KEY",("collisions","workstream")),"R039":("MULTIPLE_PR_IDENTITIES","ERROR","RECONCILE_PR_IDENTITIES",("declared","targets")),"R040":("AUTHORITY_COMPLETION_MISMATCH","ERROR","USE_ALLOWED_AUTHORITY_COMPLETION",("authority","completion","portfolio_mode")),
 "R041":("AUTHORITY_PATH_MISMATCH","ERROR","RECONCILE_AUTHORITY_AND_PATHS",("authority","paths","resolutions")),"R042":("PATH_OWNERSHIP_SNAPSHOT_UNAVAILABLE","PARTIAL","SUPPLY_PATH_OWNERSHIP_SNAPSHOT",("paths","snapshot_state")),"R043":("CHANGED_PATHS_UNAVAILABLE","PARTIAL","SUPPLY_CHANGED_PATHS",("snapshot_state",)),"R044":("MAINTENANCE_EXCEPTION_UNBOUND","ERROR","BIND_MAINTENANCE_EXCEPTION",("authority","linear","paths")),"R045":("ARCHITECTURE_CANDIDATE_CLAIMS_AUTHORITY","ERROR","REMOVE_CANDIDATE_EXECUTION_AUTHORITY",("authority","paths")),"R046":("WORKSTREAM_CREATION_HIDDEN_IMPLEMENTATION","ERROR","SPLIT_WORKSTREAM_CREATION_FROM_BUILD",("path_classes","paths")),"R047":("PATH_OWNERSHIP_UNMAPPED","PARTIAL","MAP_PATH_OWNERSHIP",("paths","resolutions")),"R050":("BRANCH_LINEAR_MISMATCH","ERROR","RECONCILE_BRANCH_IDENTITY",("branch_targets","declared")),"R051":("TITLE_BODY_LINEAR_CONFLICT","ERROR","RECONCILE_TEXT_IDENTITIES",("body_targets","declared","title_targets")),"R052":("CLOSING_KEYWORD_FOR_NON_MERGE_DONE","ERROR","USE_NONCLOSING_RELATIONSHIP",("completion","linear","relationships")),"R053":("MERGE_DONE_WITH_EXPLICIT_PROOF_GATE","ERROR","SET_NONFINAL_COMPLETION",("completion","linear","stop_law")),"R054":("NATIVE_LINKAGE_SNAPSHOT_UNAVAILABLE","PARTIAL","SUPPLY_NATIVE_LINKAGE_SNAPSHOT",("linear","snapshot_state")),"R055":("NATIVE_RELATIONSHIP_AMBIGUOUS","PARTIAL","RECONCILE_NATIVE_RELATIONSHIP",("diagnostics","linear","relationships")),"R056":("PORTFOLIO_LINKAGE_COMPLETION_MISMATCH","ERROR","REPAIR_COMPLETION_RELATIONSHIP",("completion","effect","stop_law","target","target_role")),"R060":("OBSERVATION_GROUNDING_MISMATCH","ERROR","REBUILD_IMMUTABLE_OBSERVATION",("component","expected","observed")),"R061":("SNAPSHOT_CONTRADICTION","PARTIAL","RECAPTURE_CONSISTENT_SNAPSHOT",("diagnostics","snapshot")),
}


class ValidationError(ValueError):
    """Input violates the closed V1 observation contract."""


class ResourceLimitError(ValidationError):
    """A limit failure carries its measurement from the phase that observed it.

    The CLI intentionally does not reconstruct measurements from untrusted raw
    JSON after a failure: doing so can report a different quantity than the
    parser/evaluator actually bounded.
    """

    def __init__(self, key: str, limit: int, observed: int):
        self.key, self.limit, self.observed = key, limit, observed
        super().__init__(f"RESOURCE_LIMIT:{key}")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def text_digest(value: str) -> dict[str, str]:
    raw = value.encode("utf-8")
    prefix = raw[:160]
    while prefix:
        try:
            text = prefix.decode("utf-8")
            break
        except UnicodeDecodeError:
            prefix = prefix[:-1]
    else:
        text = ""
    return {"prefix": text, "sha256": hashlib.sha256(raw).hexdigest()}


def canonical_digest(value: Any) -> dict[str, str]:
    raw = canonical_json(value)
    prefix = raw[:160]
    while prefix:
        try:
            text = prefix.decode("utf-8")
            break
        except UnicodeDecodeError:
            prefix = prefix[:-1]
    else:
        text = ""
    return {"prefix": text, "sha256": hashlib.sha256(raw).hexdigest()}


def _digest_wrappers(values: Any) -> list[dict[str, str]]:
    """Deduplicate wrappers by canonical bytes, then apply the frozen digest order."""
    unique = {canonical_json(value): value for value in values}
    return sorted(unique.values(), key=lambda value:(value["sha256"].encode("ascii"), value["prefix"].encode("utf-8")))


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValidationError("DUPLICATE_OBJECT_MEMBER")
        out[key] = value
    return out


def loads_strict(raw: bytes) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("INVALID_UTF8") from exc
    try:
        return json.loads(text, object_pairs_hook=_strict_pairs)
    except ValidationError:
        raise
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValidationError("INVALID_JSON") from exc


def _issue_ids(text: str) -> list[str]:
    return sorted(set(m.group(0).upper() for m in re.finditer(r"(?<![A-Za-z0-9])MAS-[1-9][0-9]{0,8}(?![A-Za-z0-9])", text, re.ASCII | re.I)), key=_mas_key)


def _mas_key(value: str) -> tuple[int, str]:
    match = re.fullmatch(r"MAS-([1-9][0-9]{0,8})", value)
    return (int(match.group(1)), value) if match else (10**10, value)


def _repo_path(value: Any) -> bool:
    """One lexical grammar for both current and old changed-path identities."""
    return (isinstance(value, str) and bool(value) and "\x00" not in value
            and not value.startswith("/") and "\\" not in value
            and all(part not in {"", ".", ".."} for part in value.split("/")))


_RELATIONSHIP_KEYWORDS = (
    "contributes to", "references", "implements", "implemented", "completes",
    "completed", "resolves", "resolved", "relates to", "related to", "reference",
    "towards", "closes", "closed", "fixes", "fixed", "complete", "implement",
    "resolve", "part of", "toward", "refs", "close", "fix", "ref", "skip", "ignore",
)
_RELATIONSHIP_KEYWORD_RE = "|".join(re.escape(word) for word in _RELATIONSHIP_KEYWORDS)
_ISSUE_TOKEN_RE = r"MAS-[1-9][0-9]{0,8}"
# W0 permits one or more spaces after the keyword.  Target separators are much
# narrower: exactly `` and `` or a comma with at most one adjacent ASCII space.
_RELATIONSHIP_RE = re.compile(
    rf" {{0,3}}({_RELATIONSHIP_KEYWORD_RE}) +({_ISSUE_TOKEN_RE}(?:(?: ?[, ] ?| and ){_ISSUE_TOKEN_RE})*)\.?$".replace("[, ]", ","),
    re.I | re.ASCII,
)


def _relationship_kind(word: str) -> str:
    word = word.lower()
    if word in {"close", "closes", "closed", "fix", "fixes", "fixed", "resolve",
                "resolves", "resolved", "complete", "completes", "completed",
                "implement", "implements", "implemented"}:
        return "CLOSING"
    if word in {"skip", "ignore"}:
        return "SUPPRESSED"
    if word in {"relates to", "related to"}:
        return "RELATION_ONLY"
    return "CONTRIBUTING"


def _visible_lines(body: str, limits: dict[str, int]) -> tuple[list[tuple[int, str]], list[str]]:
    """Return visible lines plus deterministic parse defects, Markdown-aware enough for V1."""
    defects: list[str] = []
    forbidden = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2060-\u206f]")
    if "\r" in body.replace("\r\n", "") or body.startswith("\ufeff") or forbidden.search(body):
        raise ValidationError("INVALID_BODY_ENCODING")
    body = body.replace("\r\n", "\n")
    lines = body.split("\n")
    if len(lines) > limits["body_lines"]:
        raise ResourceLimitError("body_lines", limits["body_lines"], len(lines))
    max_line = max((len(line.encode("utf-8")) for line in lines), default=0)
    if max_line > limits["line_bytes"]:
        raise ResourceLimitError("line_bytes", limits["line_bytes"], max_line)
    visible: list[tuple[int, str]] = []
    fence: tuple[str, int] | None = None
    comment = False
    quote_pending = False
    for n, original_line in enumerate(lines, 1):
        line = original_line
        # Once a fence is open, HTML markers are ordinary inert fence content.
        if fence:
            closer = re.fullmatch(r" {0,3}([`~]{3,})[ \t]*", line)
            if closer and closer.group(1)[0] == fence[0] and len(closer.group(1)) >= fence[1]:
                fence = None
            continue

        # A comment may close mid-line.  Its visible tail is still parsed; this
        # is load-bearing for ``-->Fixes MAS-28`` and for a following fence.
        if comment:
            end = line.find("-->")
            if end < 0:
                continue
            comment = False
            quote_pending = False
            line = line[end + 3:]

        # CommonMark recognizes an opening fence before treating its info as
        # HTML.  A backtick fence's info string may not itself contain a
        # backtick; tilde-fence info has no corresponding restriction.
        opener = re.match(r" {0,3}(`{3,}|~{3,})(.*)$", line)
        if opener and (opener.group(1)[0] == "~" or "`" not in opener.group(2)):
            fence = (opener.group(1)[0], len(opener.group(1)))
            continue

        # Remove every complete comment span while preserving visible prefixes
        # and tails.  An incomplete final span retains its visible prefix and
        # marks the authority zone unclosed.
        visible_parts: list[str] = []
        remainder = line
        while "<!--" in remainder:
            start = remainder.index("<!--")
            visible_parts.append(remainder[:start])
            end = remainder.find("-->", start + 4)
            if end < 0:
                comment = True
                remainder = ""
                break
            remainder = remainder[end + 3:]
        line = "".join(visible_parts) + remainder
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        if not line:
            quote_pending = False
            continue
        if indent <= 3 and stripped.startswith(">"):
            quote_pending = True
            continue
        if quote_pending and line:
            defects.append(f"PREAMBLE@{n}:LAZY_BLOCKQUOTE_CONTINUATION")
            quote_pending = False
        if not line:
            quote_pending = False
        if indent >= 4:
            continue
        visible.append((n, line))
    if fence or comment:
        defects.append("UNCLOSED_MARKDOWN")
    return visible, defects


def parse_header(body: str, limits: dict[str, int]) -> tuple[dict[str, str | None], dict[str, list[int]], list[tuple[str, int]], list[str], list[tuple[str, str, int]]]:
    if len(body.encode("utf-8")) > limits["body_bytes"]:
        raise ResourceLimitError("body_bytes", limits["body_bytes"], len(body.encode("utf-8")))
    visible, defects = _visible_lines(body, limits)
    zone: list[tuple[int, str]] = []
    for n, line in visible:
        if re.match(r" {0,3}##(?:[ \t]|$)", line):
            break
        zone.append((n, line))
    occ: dict[str, list[tuple[int, str]]] = {f: [] for f in FIELDS}
    label_re = re.compile(r"^(Workstream|Linear|Portfolio-Mode|Wave|Authority|Completion):")
    for n, line in visible:
        match = label_re.match(line)
        if match:
            occ[match.group(1)].append((n, line))
            if len(occ[match.group(1)]) > limits["field_occurrences"]:
                raise ResourceLimitError("field_occurrences", limits["field_occurrences"], len(occ[match.group(1)]))
    headers: list[tuple[int, str, str]] = []
    for n, line in zone:
        match = re.fullmatch(r"(Workstream|Linear|Portfolio-Mode|Wave|Authority|Completion): (.*)", line)
        if match:
            headers.append((n, match.group(1), match.group(2)))
        elif line and not _RELATIONSHIP_RE.fullmatch(line):
            kind = "RELATIONSHIP" if re.match(rf" {{0,3}}(?:{_RELATIONSHIP_KEYWORD_RE})\b", line, re.I | re.ASCII) else "PREAMBLE"
            defects.append(f"{kind}@{n}:NONPERMITTED_PREAMBLE")
    block = None
    for i in range(max(0, len(headers) - 5)):
        candidate = headers[i:i + 6]
        if [f for _, f, _ in candidate] == list(FIELDS) and all(candidate[j][0] + 1 == candidate[j + 1][0] for j in range(5)):
            block = candidate
            break
    values: dict[str, str | None] = {f: None for f in FIELDS}
    locs: dict[str, list[int]] = {f: [] for f in FIELDS}
    if block:
        for n, field, val in block:
            if len(val) >= 2 and val.startswith("`") and val.endswith("`") and val.count("`") == 2:
                val = val[1:-1]
            if len(val.encode("utf-8")) > limits["value_bytes"]:
                raise ResourceLimitError("value_bytes", limits["value_bytes"], len(val.encode("utf-8")))
            values[field], locs[field] = val, [n]
    else:
        defects.append("NO_CONTIGUOUS_BLOCK")
        for n, field, val in headers:
            if values[field] is None:
                values[field], locs[field] = val, [n]
    for f, entries in occ.items():
        if len([x for x in entries if x[0] in {n for n, _, _ in headers}]) > 1:
            locs[f] = [n for n, _ in entries]
    relationships: list[tuple[str, str, int]] = []
    for n, line in visible:
        m = _RELATIONSHIP_RE.fullmatch(line)
        if m:
            kind = _relationship_kind(m.group(1))
            for issue in _issue_ids(m.group(2)):
                relationships.append((issue, kind, n))
    # Duplicates collapse by normalized relationship identity and retain the
    # earliest visible line.  Numeric MAS ordering is shared across the parser
    # and every downstream reducer (MAS-2 sorts before MAS-10).
    first: dict[tuple[str, str], int] = {}
    for issue, kind, line in relationships:
        first[(issue, kind)] = min(line, first.get((issue, kind), line))
    relationships = sorted(((issue, kind, line) for (issue, kind), line in first.items()),
                           key=lambda row: (row[2], _mas_key(row[0]), row[1]))
    if len(relationships) > limits["relationships"]:
        raise ResourceLimitError("relationships", limits["relationships"], len(relationships))
    return values, locs, headers, defects, relationships


def _rule_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out = {r["rule_id"]: r for r in manifest["rules"]}
    if set(out) != FROZEN_RULE_IDS or len(out) != 46:
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    return out


_LOCATION_RE = re.compile(
    r"(?:BODY:L[1-9][0-9]*:(?:Workstream|Linear|Portfolio-Mode|Wave|Authority|Completion|RELATIONSHIP)"
    r"|DECLARATION:(?:Workstream|Linear|Portfolio-Mode|Wave|Authority|Completion|BLOCK)"
    r"|SNAPSHOT:(?:AUTHORING_EPOCH|CHANGED_PATHS|AGENTOS|LINEAR|PATH_OWNERSHIP|NATIVE_LINKAGE)"
    r"|RECEIPT:(?:OBSERVATION|BODY|CUTOVER|RULESET|AUTHORING_EPOCH|CHANGED_PATHS|AGENTOS|LINEAR|PATH_OWNERSHIP|NATIVE_LINKAGE)"
    r"|TITLE|BRANCH|RULESET)"
)
_EVIDENCE_SCHEMA_BY_KEY = {
    "alias":"ATOM", "authority":"ATOM", "body_targets":"ATOM_LIST",
    "bound_workstream":"ATOM_OR_NULL", "branch_targets":"ATOM_LIST", "canonical":"ATOM",
    "collisions":"ATOM_LIST", "completion":"ATOM", "component":"ATOM", "declared":"ATOM",
    "declared_workstream":"ATOM_OR_NULL", "diagnostics":"ATOM_LIST", "effect":"ATOM",
    "epoch":"ATOM", "epoch_state":"ATOM", "expected":"CANONICAL_DIGEST", "field":"ATOM",
    "issue_type":"ATOM", "linear":"ATOM", "location":"LOCATION", "locations":"LOCATION_LIST",
    "missing_fields":"ATOM_LIST", "observed":"CANONICAL_DIGEST", "path_classes":"ATOM_LIST",
    "paths":"TEXT_DIGEST_LIST", "portfolio_mode":"ATOM", "reason":"ATOM",
    "receipt":"CANONICAL_DIGEST", "receipt_digest":"ATOM_OR_NULL",
    "relationships":"CANONICAL_DIGEST_LIST", "required_targets":"ATOM_LIST",
    "resolutions":"CANONICAL_DIGEST_LIST", "roles":"ATOM_LIST", "snapshot":"ATOM",
    "snapshot_state":"ATOM", "stop_law":"ATOM", "target":"ATOM", "target_role":"ATOM",
    "target_roles":"ATOM_LIST", "targets":"ATOM_LIST", "title_targets":"ATOM_LIST",
    "value":"CANONICAL_DIGEST", "values":"CANONICAL_DIGEST_LIST", "workstream":"ATOM",
}
_ONE_FINDING_RULES = {
    "R001","R003","R027","R029","R030","R031","R032","R033","R034","R035","R036",
    "R037","R038","R039","R040","R041","R042","R043","R044","R045","R046","R047",
    "R050","R051","R052","R053","R054",
}


def _atom_order(values: list[str]) -> list[str]:
    if all(re.fullmatch(r"MAS-[1-9][0-9]{0,8}", value) for value in values):
        return sorted(set(values), key=_mas_key)
    return sorted(set(values), key=lambda value:value.encode("utf-8"))


def _digest_wrapper_valid(value: Any) -> bool:
    return (isinstance(value, dict) and set(value) == {"prefix","sha256"}
            and isinstance(value["prefix"], str) and len(value["prefix"].encode("utf-8")) <= 160
            and isinstance(value["sha256"], str) and bool(re.fullmatch(r"[0-9a-f]{64}", value["sha256"])))


def _evidence_value_valid(category: str, value: Any) -> bool:
    atom = lambda item: isinstance(item, str) and bool(re.fullmatch(r"[A-Za-z0-9_.:/-]{1,160}", item))
    if category == "ATOM": return atom(value)
    if category == "ATOM_OR_NULL": return value is None or atom(value)
    if category == "LOCATION": return isinstance(value, str) and bool(_LOCATION_RE.fullmatch(value))
    if category in {"TEXT_DIGEST","CANONICAL_DIGEST"}: return _digest_wrapper_valid(value)
    if not isinstance(value, list): return False
    if category == "ATOM_LIST": return all(atom(item) for item in value) and value == _atom_order(value)
    if category == "LOCATION_LIST": return all(isinstance(item,str) and _LOCATION_RE.fullmatch(item) for item in value) and value == sorted(set(value), key=lambda item:item.encode("utf-8"))
    if category in {"TEXT_DIGEST_LIST","CANONICAL_DIGEST_LIST"}:
        return all(_digest_wrapper_valid(item) for item in value) and value == _digest_wrappers(value)
    return False


def _finding_location_valid(finding: dict[str, Any]) -> bool:
    rule, location, evidence = finding["rule_id"], finding["location"], finding["evidence"]
    if not _LOCATION_RE.fullmatch(location): return False
    if rule == "R003": return location == "DECLARATION:BLOCK" or bool(re.fullmatch(r"BODY:L[1-9][0-9]*:(?:Workstream|Linear|Portfolio-Mode|Wave|Authority|Completion|RELATIONSHIP)", location))
    if rule in {"R001","R039","R040","R051"}: return location == "DECLARATION:BLOCK"
    if rule == "R022":
        return bool(re.fullmatch(r"BODY:L[1-9][0-9]*:(?:Portfolio-Mode|Authority|Completion)", location))
    if rule in {"R002","R004","R005","R006","R007","R008","R009","R010","R011","R012","R020","R021"}:
        fixed_field = {"R005":"Workstream","R006":"Linear","R007":"Wave","R008":"Wave",
                       "R009":"Portfolio-Mode","R010":"Portfolio-Mode","R011":"Authority",
                       "R012":"Completion"}
        field = fixed_field.get(rule, evidence.get("field"))
        return field in FIELDS and bool(re.fullmatch(rf"BODY:L[1-9][0-9]*:{re.escape(field)}", location))
    if rule == "R029": return location == "DECLARATION:Linear"
    if rule in {"R030","R031","R032"}: return location == "DECLARATION:Workstream"
    if rule == "R050": return location == "BRANCH"
    if rule == "R052": return bool(re.fullmatch(r"BODY:L[1-9][0-9]*:RELATIONSHIP", location))
    if rule == "R060": return location == "RECEIPT:" + evidence.get("component", "")
    if rule == "R061": return location == "SNAPSHOT:" + evidence.get("snapshot", "")
    return location == _location(rule)


def validate_report(report: dict[str, Any]) -> None:
    """Closed report-wire validation for adapters and test fixtures."""
    required = {"schema", "semantic", "semantic_hash", "receipt", "human"}
    if not isinstance(report, dict) or set(report) != required or report.get("schema") != REPORT_SCHEMA:
        raise ValidationError("TYPE_MISMATCH")
    semantic = report["semantic"]
    semantic_keys = {"ruleset_id","ruleset_digest","enforcement","declaration","classification","verdict","completeness","completion_interpretation","unresolved_observation_classes","findings"}
    if not isinstance(semantic, dict) or set(semantic) != semantic_keys or report.get("semantic_hash") != digest(semantic):
        raise ValidationError("TYPE_MISMATCH")
    if semantic.get("ruleset_id") != RULESET_ID or semantic.get("ruleset_digest") != FROZEN_RULESET_DIGEST or semantic.get("enforcement") != "REPORT_ONLY" or semantic.get("verdict") not in {"CONFORMANT","WARN","PARTIAL","REFUSE_METADATA"} or semantic.get("classification") not in {"TRACKED","MAINTENANCE_EXCEPTION","CREATES_WORKSTREAM","ARCHITECTURE_CANDIDATE","UNCLASSIFIED_LEGACY","UNKNOWN"} or semantic.get("completeness") not in {"COMPLETE","DEGRADED","UNAVAILABLE"}:
        raise ValidationError("TYPE_MISMATCH")
    declaration = semantic.get("declaration")
    if not isinstance(declaration, dict) or set(declaration) != {"workstream","linear","portfolio_mode","wave","authority","completion","authoring_state"} or declaration.get("authoring_state") not in {"CANONICAL","LEGACY","MISSING","INVALID"} or any(v is not None and not isinstance(v, str) for k,v in declaration.items() if k != "authoring_state"):
        raise ValidationError("TYPE_MISMATCH")
    rows = semantic.get("completion_interpretation")
    if not isinstance(rows, list): raise ValidationError("TYPE_MISMATCH")
    expected_rows = sorted(rows, key=lambda r:(_mas_key(r.get("issue_id", "")),r.get("effect", ""),r.get("declared_completion") or "",r.get("stop_law") or "",r.get("consistency", "")))
    if rows != expected_rows or len({canonical_json(x) for x in rows}) != len(rows): raise ValidationError("TYPE_MISMATCH")
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"issue_id","effect","declared_completion","stop_law","consistency"} or not isinstance(row.get("issue_id"), str) or not re.fullmatch(r"MAS-[1-9][0-9]{0,8}", row["issue_id"]) or row.get("effect") not in {"COMPLETION_CAPABLE","NON_CLOSING","NONE","AMBIGUOUS","UNKNOWN"} or row.get("consistency") not in {"MATCH","MISMATCH","INDETERMINATE"} or row.get("declared_completion") is not None and (not isinstance(row["declared_completion"],str) or not row["declared_completion"] or len(row["declared_completion"].encode("utf-8")) > 80) or row.get("stop_law") not in {"MERGE","BUILT_NOT_PROVEN","PROOF","ACCEPTANCE","RECORDS_ONLY","UNKNOWN",None}:
            raise ValidationError("TYPE_MISMATCH")
    unresolved = semantic.get("unresolved_observation_classes")
    if not isinstance(unresolved, list) or unresolved != sorted(set(unresolved)) or any(x not in {"AUTHORING_EPOCH","CHANGED_PATHS","AGENTOS","LINEAR","PATH_OWNERSHIP","NATIVE_LINKAGE"} for x in unresolved):
        raise ValidationError("TYPE_MISMATCH")
    findings = semantic.get("findings")
    if not isinstance(findings, list) or len(findings) > 512: raise ValidationError("TYPE_MISMATCH")
    sort_key = lambda x:(SEVERITY.get(x.get("severity"),99),x.get("code",""),x.get("rule_id",""),x.get("location",""),canonical_json(x.get("evidence",{})))
    if findings != sorted(findings, key=sort_key) or len({canonical_json(x) for x in findings}) != len(findings): raise ValidationError("TYPE_MISMATCH")
    for finding in findings:
        if not isinstance(finding, dict) or set(finding) != {"code","rule_id","severity","location","evidence","remediation_code"} or finding["rule_id"] not in FROZEN_RULE_IDS or not isinstance(finding.get("code"), str) or not isinstance(finding.get("remediation_code"), str) or finding.get("severity") not in SEVERITY or not isinstance(finding.get("location"), str) or not isinstance(finding.get("evidence"), dict):
            raise ValidationError("TYPE_MISMATCH")
        code, severity, remediation, evidence_keys = FROZEN_FINDINGS[finding["rule_id"]]
        if (finding["code"], finding["severity"], finding["remediation_code"], tuple(sorted(finding["evidence"]))) != (code, severity, remediation, tuple(sorted(evidence_keys))) or not _finding_location_valid(finding):
            raise ValidationError("TYPE_MISMATCH")
        if any(not _evidence_value_valid(_EVIDENCE_SCHEMA_BY_KEY[key], value) for key, value in finding["evidence"].items()):
            raise ValidationError("TYPE_MISMATCH")
        if "location" in finding["evidence"] and finding["evidence"]["location"] != finding["location"]:
            raise ValidationError("TYPE_MISMATCH")
    by_rule: dict[str,list[dict[str,Any]]] = {}
    for finding in findings: by_rule.setdefault(finding["rule_id"],[]).append(finding)
    if any(len(by_rule.get(rule,[])) > 1 for rule in _ONE_FINDING_RULES): raise ValidationError("TYPE_MISMATCH")
    for rule in ("R002","R004","R005","R006","R007","R008","R009","R010","R011","R012","R020","R021","R022"):
        rows_for_rule = by_rule.get(rule,[])
        if len({row["evidence"].get("field") for row in rows_for_rule}) != len(rows_for_rule): raise ValidationError("TYPE_MISMATCH")
    for rule, key in (("R026","required_targets"),("R055","linear"),("R056","target"),("R060","component"),("R061","snapshot")):
        rows_for_rule = by_rule.get(rule,[])
        identities = [canonical_json(row["evidence"].get(key)) for row in rows_for_rule]
        if len(set(identities)) != len(identities): raise ValidationError("TYPE_MISMATCH")
    expected_verdict = ("REFUSE_METADATA" if any(row["severity"] == "ERROR" for row in findings)
                        else "PARTIAL" if any(row["severity"] == "PARTIAL" for row in findings)
                        else "WARN" if findings else "CONFORMANT")
    expected_completeness = ("UNAVAILABLE" if declaration["authoring_state"] == "MISSING"
                             else "DEGRADED" if unresolved or any(row["severity"] == "PARTIAL" for row in findings)
                             else "COMPLETE")
    class_by_mode = {"tracked":"TRACKED", "maintenance_exception":"MAINTENANCE_EXCEPTION",
                     "creates_workstream":"CREATES_WORKSTREAM", "architecture_candidate":"ARCHITECTURE_CANDIDATE"}
    expected_classification = ("UNCLASSIFIED_LEGACY" if declaration["authoring_state"] == "LEGACY"
                               else "UNKNOWN" if declaration["authoring_state"] in {"INVALID","MISSING"}
                               else class_by_mode.get(declaration["portfolio_mode"]))
    if (semantic["verdict"] != expected_verdict or semantic["completeness"] != expected_completeness
            or expected_classification is None or semantic["classification"] != expected_classification):
        raise ValidationError("TYPE_MISMATCH")
    receipt = report.get("receipt")
    receipt_keys = {"observation_schema","repository","pr_number","base_sha","head_sha","source_sha","body_sha256","observation_sha256","cutover_receipt_sha256","ruleset_digest","snapshot_digests","producer"}
    if not isinstance(receipt, dict) or set(receipt) != receipt_keys or receipt.get("observation_schema") != OBS_SCHEMA or not isinstance(receipt.get("repository"), str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",receipt["repository"]) or not _positive_int(receipt.get("pr_number")) or any(not isinstance(receipt.get(k),str) or not re.fullmatch(r"[0-9a-f]{40}",receipt[k]) for k in ("base_sha","head_sha","source_sha")) or any(not isinstance(receipt.get(k),str) or not re.fullmatch(r"[0-9a-f]{64}",receipt[k]) for k in ("body_sha256","observation_sha256")) or receipt.get("ruleset_digest") != FROZEN_RULESET_DIGEST or receipt.get("cutover_receipt_sha256") is not None and (not isinstance(receipt["cutover_receipt_sha256"],str) or not re.fullmatch(r"[0-9a-f]{64}",receipt["cutover_receipt_sha256"])) or not isinstance(receipt.get("snapshot_digests"),dict) or set(receipt["snapshot_digests"]) != {"authoring_epoch","changed_paths","agentos","linear","path_ownership","native_linkage"} or any(not isinstance(value,str) or not re.fullmatch(r"[0-9a-f]{64}",value) for value in receipt["snapshot_digests"].values()) or not isinstance(receipt.get("producer"),str) or not receipt["producer"]:
        raise ValidationError("TYPE_MISMATCH")
    human = report.get("human")
    expected_human = {"summary":f"{semantic['classification']}/{semantic['verdict']}","remediations":sorted({finding["remediation_code"] for finding in findings})}
    if not isinstance(human, dict) or human != expected_human:
        raise ValidationError("TYPE_MISMATCH")


def _location(rule: str, field: str | None = None, line: int | None = None, component: str | None = None) -> str:
    if line and field:
        return f"BODY:L{line}:{field}"
    if rule in {"R001", "R003", "R039", "R040", "R051"}:
        return "DECLARATION:BLOCK"
    declaration = {"R029": "Linear", "R030": "Workstream", "R031": "Workstream", "R032": "Workstream"}
    if rule in declaration:
        return "DECLARATION:" + declaration[rule]
    snap = {"R026":"LINEAR","R027":"LINEAR","R028":"LINEAR","R033":"AGENTOS","R034":"LINEAR","R035":"LINEAR","R036":"LINEAR","R037":"CHANGED_PATHS","R038":"AGENTOS","R041":"PATH_OWNERSHIP","R042":"PATH_OWNERSHIP","R043":"CHANGED_PATHS","R044":"PATH_OWNERSHIP","R045":"PATH_OWNERSHIP","R046":"PATH_OWNERSHIP","R047":"PATH_OWNERSHIP","R053":"LINEAR","R054":"NATIVE_LINKAGE","R055":"NATIVE_LINKAGE","R056":"NATIVE_LINKAGE"}
    if rule == "R060": return "RECEIPT:" + (component or "OBSERVATION")
    if rule == "R061": return "SNAPSHOT:" + (component or "AGENTOS")
    if rule == "R050": return "BRANCH"
    return "SNAPSHOT:" + snap.get(rule, "AGENTOS")


def _finding(rule_map: dict[str, dict[str, Any]], rule: str, evidence: dict[str, Any], *, field: str | None = None, line: int | None = None, component: str | None = None) -> dict[str, Any]:
    row = rule_map[rule]
    if set(evidence) != set(row["evidence_keys"]):
        raise ValidationError("TYPE_MISMATCH")
    return {"code": row["code"], "rule_id": rule, "severity": row["severity"], "location": _location(rule, field, line, component), "evidence": {k: evidence[k] for k in sorted(evidence)}, "remediation_code": row["remediation_code"]}


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _printable_ref(value: Any) -> bool:
    return (isinstance(value, str) and bool(value) and value.isascii() and value.isprintable()
            and not any(char.isspace() for char in value))


def _diagnostics_valid(snapshot: dict[str, Any]) -> bool:
    diagnostics = snapshot.get("diagnostics")
    if (not isinstance(diagnostics, list) or diagnostics != sorted(set(diagnostics))
            or any(not isinstance(item, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,160}", item)
                   for item in diagnostics)):
        return False
    state = snapshot.get("state")
    return ((state in {"PRESENT", "NOT_APPLICABLE"} and not diagnostics)
            or (state in {"PARTIAL", "UNAVAILABLE", "CONTRADICTORY"} and bool(diagnostics)))


def _row_order(rows: list[dict[str, Any]], key: Any, *, contradictory: bool) -> bool:
    """Require a frozen semantic-key order with a deterministic conflict tie-break."""
    order = (lambda row: (key(row), canonical_json(row))) if contradictory else key
    return rows == sorted(rows, key=order) and len({canonical_json(row) for row in rows}) == len(rows)


def _validate_top(observation: dict[str, Any], manifest: dict[str, Any]) -> None:
    required = {"schema","ruleset_id","ruleset_digest","repository","pull_request","authoring_epoch","changed_paths","agentos","linear","path_ownership","native_linkage","receipt"}
    if not isinstance(observation, dict): raise ValidationError("TYPE_MISMATCH")
    if set(observation) != required: raise ValidationError("UNKNOWN_KEY" if set(observation)-required else "MISSING_KEY")
    if observation["schema"] != OBS_SCHEMA: raise ValidationError("TYPE_MISMATCH")
    if not isinstance(manifest, dict) or manifest.get("ruleset_id") != RULESET_ID: raise ValidationError("UNSUPPORTED_RULESET_ID")
    manifest_digest = digest(manifest)
    if manifest_digest != FROZEN_RULESET_DIGEST: raise ValidationError("RULESET_DIGEST_MISMATCH")
    if observation["ruleset_id"] != manifest["ruleset_id"]: raise ValidationError("UNSUPPORTED_RULESET_ID")
    if observation["ruleset_digest"] != manifest_digest: raise ValidationError("RULESET_DIGEST_MISMATCH")
    atom_re = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    sha_re = re.compile(r"^[0-9a-f]{40}$")
    digest_re = re.compile(r"^[0-9a-f]{64}$")
    if not isinstance(observation.get("repository"), dict) or set(observation["repository"]) != {"name"} or not isinstance(observation["repository"]["name"], str) or not atom_re.fullmatch(observation["repository"]["name"]):
        raise ValidationError("TYPE_MISMATCH")
    pr = observation.get("pull_request")
    if not isinstance(pr, dict) or set(pr) != {"number","title","body","branch","base_ref","head_ref"} or not isinstance(pr.get("number"), int) or pr["number"] < 1 or not all(isinstance(pr.get(k), str) for k in ("title","body")) or not all(isinstance(pr.get(k), str) and pr[k] and pr[k].isascii() and pr[k].isprintable() and not any(c.isspace() for c in pr[k]) for k in ("branch","base_ref","head_ref")):
        raise ValidationError("TYPE_MISMATCH")
    if not isinstance(observation.get("ruleset_digest"), str) or not digest_re.fullmatch(observation["ruleset_digest"]): raise ValidationError("TYPE_MISMATCH")
    snapshot_keys = {
        "authoring_epoch": {"state","relation","default_ref","cutover_merge_sha","template_blobs","first_strict_pr_number","legacy_open_pr_numbers","receipt_ruleset_digest","cutover_receipt_sha256","diagnostics"},
        "changed_paths": {"state","paths","diagnostics"},
        "agentos": {"state","basis","workstreams","diagnostics"},
        "linear": {"state","issues","diagnostics"},
        "path_ownership": {"state","basis","resolutions","diagnostics"},
        "native_linkage": {"state","relationships","pagination_complete","diagnostics"},
    }
    for name, exact_keys in snapshot_keys.items():
        snap = observation[name]
        if (not isinstance(snap, dict) or set(snap) != exact_keys
                or snap.get("state") not in STATE or not _diagnostics_valid(snap)):
            raise ValidationError("INVALID_SNAPSHOT_STATE")
    epoch = observation["authoring_epoch"]
    epoch_keys = {"state","relation","default_ref","cutover_merge_sha","template_blobs","first_strict_pr_number","legacy_open_pr_numbers","receipt_ruleset_digest","cutover_receipt_sha256","diagnostics"}
    if set(epoch) != epoch_keys or epoch.get("state") == "NOT_APPLICABLE" or epoch.get("relation") not in {"PRE_CUTOVER","AT_OR_POST_CUTOVER","UNKNOWN"}:
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    if epoch["state"] == "PRESENT" and (epoch["relation"] == "UNKNOWN" or epoch.get("receipt_ruleset_digest") != observation["ruleset_digest"]):
        raise ValidationError("EPOCH_RECEIPT_RULESET_MISMATCH")
    if epoch["state"] == "UNAVAILABLE" and (epoch["relation"] != "UNKNOWN" or any(epoch.get(key) is not None for key in ("default_ref","cutover_merge_sha","first_strict_pr_number","receipt_ruleset_digest","cutover_receipt_sha256")) or epoch.get("template_blobs") != [] or epoch.get("legacy_open_pr_numbers") != []):
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    if epoch["state"] == "PRESENT":
        if not _printable_ref(epoch.get("default_ref")) or not isinstance(epoch.get("cutover_merge_sha"), str) or not sha_re.fullmatch(epoch["cutover_merge_sha"]) or not _positive_int(epoch.get("first_strict_pr_number")) or not isinstance(epoch.get("template_blobs"), list) or not epoch["template_blobs"] or not isinstance(epoch.get("cutover_receipt_sha256"), str) or not digest_re.fullmatch(epoch["cutover_receipt_sha256"]):
            raise ValidationError("INVALID_SNAPSHOT_STATE")
    for nullable, predicate in (("default_ref", _printable_ref), ("cutover_merge_sha", lambda x: isinstance(x, str) and bool(sha_re.fullmatch(x))), ("first_strict_pr_number", _positive_int), ("receipt_ruleset_digest", lambda x: isinstance(x, str) and bool(digest_re.fullmatch(x))), ("cutover_receipt_sha256", lambda x: isinstance(x, str) and bool(digest_re.fullmatch(x)))):
        if epoch.get(nullable) is not None and not predicate(epoch[nullable]):
            raise ValidationError("INVALID_SNAPSHOT_STATE")
    if not isinstance(epoch.get("template_blobs"), list) or not isinstance(epoch.get("legacy_open_pr_numbers"), list):
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    for blob in epoch["template_blobs"]:
        if not isinstance(blob, dict) or set(blob) != {"path","blob_sha"} or not _repo_path(blob.get("path")) or not isinstance(blob.get("blob_sha"), str) or not sha_re.fullmatch(blob["blob_sha"]):
            raise ValidationError("INVALID_SNAPSHOT_STATE")
    if epoch["template_blobs"] != sorted(epoch["template_blobs"], key=lambda row:(row["path"].encode("utf-8"),row["blob_sha"])) or len({(row["path"],row["blob_sha"]) for row in epoch["template_blobs"]}) != len(epoch["template_blobs"]):
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    if epoch["legacy_open_pr_numbers"] != sorted(set(epoch["legacy_open_pr_numbers"])) or any(not _positive_int(x) for x in epoch["legacy_open_pr_numbers"]):
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    if epoch["state"] == "PRESENT":
        if epoch["relation"] == "PRE_CUTOVER" and (pr["number"] not in epoch["legacy_open_pr_numbers"] or pr["number"] >= epoch["first_strict_pr_number"]): raise ValidationError("INVALID_SNAPSHOT_STATE")
        if epoch["relation"] == "AT_OR_POST_CUTOVER" and (pr["number"] < epoch["first_strict_pr_number"] or pr["number"] in epoch["legacy_open_pr_numbers"]): raise ValidationError("INVALID_SNAPSHOT_STATE")
        if epoch.get("cutover_receipt_sha256") != cutover_digest(observation): raise ValidationError("INVALID_SNAPSHOT_STATE")
    payloads = {"changed_paths":"paths", "agentos":"workstreams", "linear":"issues", "path_ownership":"resolutions", "native_linkage":"relationships"}
    for name, payload in payloads.items():
        snap = observation[name]
        if payload not in snap or not isinstance(snap[payload], list):
            raise ValidationError("INVALID_SNAPSHOT_STATE")
        if snap["state"] in {"UNAVAILABLE", "NOT_APPLICABLE"} and snap[payload]:
            raise ValidationError("INVALID_SNAPSHOT_STATE")
    if len(observation["changed_paths"]["paths"]) > manifest["limits"]["changed_paths"]:
        raise ResourceLimitError("changed_paths", manifest["limits"]["changed_paths"], len(observation["changed_paths"]["paths"]))
    for name, base in (("agentos", "BASE"), ("path_ownership", "BASE_POLICY")):
        if observation[name].get("basis") != base: raise ValidationError("INVALID_SNAPSHOT_STATE")
    cp = observation["changed_paths"]["paths"]
    for row in cp:
        if not isinstance(row, dict) or set(row) != {"path","change_type","old_path"} or not _repo_path(row.get("path")) or row.get("change_type") not in {"ADDED","MODIFIED","DELETED","RENAMED"} or (row["change_type"] == "RENAMED") != isinstance(row.get("old_path"), str) or (row["change_type"] == "RENAMED" and (not _repo_path(row["old_path"]) or row["old_path"] == row["path"])):
            raise ValidationError("INVALID_SNAPSHOT_STATE")
    if not _row_order(cp, lambda r:(r["path"].encode("utf-8"),r["change_type"],(r["old_path"] or "").encode("utf-8")), contradictory=observation["changed_paths"]["state"] == "CONTRADICTORY"):
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    changed_conflict = len({r["path"] for r in cp}) != len(cp) or bool({r["old_path"] for r in cp if r["old_path"]} & {r["path"] for r in cp})
    if changed_conflict and observation["changed_paths"]["state"] != "CONTRADICTORY":
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    if observation["changed_paths"]["state"] == "CONTRADICTORY" and not changed_conflict:
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    workstreams = observation["agentos"].get("workstreams", [])
    for row in workstreams:
        if not isinstance(row, dict) or set(row) != {"key","waves"} or not isinstance(row.get("key"),str) or not re.fullmatch(r"WS:[A-Z0-9]+(?:-[A-Z0-9]+)*", row["key"]) or not isinstance(row.get("waves"),list) or row["waves"] != sorted(set(row["waves"])) or any(not isinstance(x,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}",x) for x in row["waves"]):
            raise ValidationError("INVALID_SNAPSHOT_STATE")
    if not _row_order(workstreams, lambda r:r["key"], contradictory=observation["agentos"]["state"] == "CONTRADICTORY"):
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    workstream_conflict = len({row["key"] for row in workstreams}) != len(workstreams)
    if workstream_conflict and observation["agentos"]["state"] != "CONTRADICTORY":
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    if observation["agentos"]["state"] == "CONTRADICTORY" and not workstream_conflict:
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    issues = observation["linear"].get("issues", [])
    for row in issues:
        if not isinstance(row, dict) or set(row) != {"id","target_role","project_id","workstream_key","issue_type","stop_law"} or not isinstance(row.get("id"),str) or not re.fullmatch(r"MAS-[1-9][0-9]{0,8}",row["id"]) or row.get("target_role") not in {"DECLARED","SECONDARY","PARENT","PROOF_GATE","ACCEPTANCE_GATE","UNKNOWN"} or row.get("project_id") is not None and (not isinstance(row["project_id"],str) or not row["project_id"]) or row.get("workstream_key") is not None and (not isinstance(row["workstream_key"],str) or not re.fullmatch(r"WS:[A-Z0-9]+(?:-[A-Z0-9]+)*",row["workstream_key"])) or row.get("issue_type") not in {"DELIVERY","MAINTENANCE","ROOT_RECOVERY","ARCHITECTURE","PROOF_GATE","ACCEPTANCE_GATE","UNKNOWN"} or row.get("stop_law") not in {"MERGE","BUILT_NOT_PROVEN","PROOF","ACCEPTANCE","RECORDS_ONLY","UNKNOWN"}:
            raise ValidationError("INVALID_SNAPSHOT_STATE")
    if not _row_order(issues, lambda r:(_mas_key(r["id"]),r["target_role"]), contradictory=observation["linear"]["state"] == "CONTRADICTORY"):
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    linear_conflict = len({(row["id"], row["target_role"]) for row in issues}) != len(issues)
    if linear_conflict and observation["linear"]["state"] != "CONTRADICTORY":
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    if observation["linear"]["state"] == "CONTRADICTORY" and not linear_conflict:
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    resolutions = observation["path_ownership"].get("resolutions", [])
    for row in resolutions:
        if not isinstance(row,dict) or set(row) != {"path","role","resolution","owner_workstream","path_class","allowed_authorities"} or not _repo_path(row.get("path")) or row.get("role") not in {"CURRENT","OLD_RENAME_SOURCE"} or row.get("resolution") not in {"EXACT","UNOWNED","AMBIGUOUS"} or row.get("owner_workstream") is not None and (not isinstance(row["owner_workstream"],str) or row["owner_workstream"] != "NONE" and not re.fullmatch(r"WS:[A-Z0-9]+(?:-[A-Z0-9]+)*", row["owner_workstream"])) or row.get("path_class") not in {"RECORDS","RESEARCH","MAINTENANCE","IMPLEMENTATION","PROOF","DEPLOY","ARCHITECTURE","UNKNOWN"} or not isinstance(row.get("allowed_authorities"),list) or row["allowed_authorities"] != sorted(set(row["allowed_authorities"])) or any(x not in ENUMS["Authority"] for x in row["allowed_authorities"]):
            raise ValidationError("INVALID_SNAPSHOT_STATE")
        exact = row["resolution"] == "EXACT" and row["owner_workstream"] is not None and row["path_class"] != "UNKNOWN" and bool(row["allowed_authorities"])
        unowned = row["resolution"] == "UNOWNED" and row["owner_workstream"] == "NONE" and row["path_class"] == "UNKNOWN" and row["allowed_authorities"] == []
        ambiguous = row["resolution"] == "AMBIGUOUS" and row["owner_workstream"] is None and row["path_class"] == "UNKNOWN" and row["allowed_authorities"] == [] and observation["path_ownership"]["state"] in {"PARTIAL","CONTRADICTORY"}
        if not (exact or unowned or ambiguous) or (observation["path_ownership"]["state"] == "PRESENT" and row["resolution"] == "AMBIGUOUS"):
            raise ValidationError("INVALID_SNAPSHOT_STATE")
    if not _row_order(resolutions, lambda r:(r["path"].encode("utf-8"),r["role"]), contradictory=observation["path_ownership"]["state"] == "CONTRADICTORY"):
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    ownership_conflict = len({(row["path"],row["role"]) for row in resolutions}) != len(resolutions)
    if ownership_conflict and observation["path_ownership"]["state"] != "CONTRADICTORY":
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    by_identity = {(row["path"],row["role"]):row for row in resolutions}
    rename_ownership_conflict = False
    for changed in cp:
        if changed["change_type"] != "RENAMED":
            continue
        old = by_identity.get((changed["old_path"],"OLD_RENAME_SOURCE"))
        new = by_identity.get((changed["path"],"CURRENT"))
        if old and new and old["resolution"] == new["resolution"] == "EXACT" and any(old[key] != new[key] for key in ("owner_workstream","path_class","allowed_authorities")):
            rename_ownership_conflict = True
    if observation["path_ownership"]["state"] == "CONTRADICTORY" and not (ownership_conflict or rename_ownership_conflict):
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    if observation["changed_paths"]["state"] == "PRESENT" and observation["path_ownership"]["state"] == "PRESENT":
        current = {r["path"] for r in resolutions if r["role"] == "CURRENT"}
        old_sources = {r["path"] for r in resolutions if r["role"] == "OLD_RENAME_SOURCE"}
        required_current = {r["path"] for r in cp}
        required_old = {r["old_path"] for r in cp if r["change_type"] == "RENAMED"}
        if current != required_current or old_sources != required_old:
            raise ValidationError("INVALID_SNAPSHOT_STATE")
        if rename_ownership_conflict:
            raise ValidationError("INVALID_SNAPSHOT_STATE")
    native = observation["native_linkage"]
    if not isinstance(native.get("pagination_complete"), bool) or (native["state"] == "PRESENT") != native["pagination_complete"]:
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    if len(native.get("relationships", [])) > manifest["limits"]["relationships"]:
        raise ResourceLimitError("relationships", manifest["limits"]["relationships"], len(native["relationships"]))
    legal = manifest["native_reduction"]["legal_rows"]
    for row in native["relationships"]:
        if not isinstance(row, dict) or set(row) != {"issue_id","kind","source","state","completion_transition"} or not isinstance(row.get("issue_id"),str) or not re.fullmatch(r"MAS-[1-9][0-9]{0,8}",row["issue_id"]):
            raise ValidationError("INVALID_SNAPSHOT_STATE")
        state, kind, source, transition = row["state"], row["kind"], row["source"], row["completion_transition"]
        valid = False
        if state == "PRESENT" and kind == "AUTO_LINK": valid = source in {"BRANCH","TITLE"} and transition in {"ELIGIBLE","INELIGIBLE"}
        elif state == "PRESENT" and kind in {"CLOSING","CONTRIBUTING","RELATION_ONLY"}: valid = source in {"BODY","LINEAR_NATIVE","ADAPTER"} and transition == ({"CLOSING":"ELIGIBLE","CONTRIBUTING":"INELIGIBLE","RELATION_ONLY":"INELIGIBLE"}[kind])
        elif state == "SUPPRESSED": valid = kind == "SUPPRESSED" and source in {"BRANCH","TITLE"} and transition == "INELIGIBLE"
        elif state in {"AMBIGUOUS","UNAVAILABLE"}: valid = native["state"] in {"PARTIAL","CONTRADICTORY"} and kind == "UNKNOWN" and source in {"BODY","BRANCH","TITLE","LINEAR_NATIVE","ADAPTER"} and transition == "UNKNOWN"
        if not valid or (native["state"] == "PRESENT" and state not in {"PRESENT","SUPPRESSED"}):
            raise ValidationError("INVALID_SNAPSHOT_STATE")
    if not _row_order(native["relationships"], lambda r:(_mas_key(r["issue_id"]),r["source"],r["kind"],r["state"],r["completion_transition"]), contradictory=native["state"] == "CONTRADICTORY"):
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    native_keys: dict[tuple[str,str], set[str]] = {}
    transitions: dict[str, set[str]] = {}
    for row in native["relationships"]:
        native_keys.setdefault((row["issue_id"],row["source"]),set()).add(row["state"])
        if row["state"] == "PRESENT":
            transitions.setdefault(row["issue_id"],set()).add(row["completion_transition"])
    native_conflict = any("PRESENT" in states and "SUPPRESSED" in states for states in native_keys.values()) or any(len(values) > 1 for values in transitions.values())
    if native_conflict and native["state"] != "CONTRADICTORY":
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    if native["state"] == "CONTRADICTORY" and not native_conflict:
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    if native["state"] == "NOT_APPLICABLE" and re.search(r"(?m)^Portfolio-Mode: (?:tracked|`tracked`)$", pr["body"]):
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    receipt = observation.get("receipt")
    receipt_keys = {"repository","pr_number","base_sha","head_sha","source_sha","body_sha256","observation_sha256","cutover_receipt_sha256","ruleset_digest","snapshot_digests","producer"}
    if not isinstance(receipt, dict) or set(receipt) != receipt_keys:
        raise ValidationError("TYPE_MISMATCH")
    snapshot_keys = {"authoring_epoch","changed_paths","agentos","linear","path_ownership","native_linkage"}
    if receipt.get("repository") != observation["repository"]["name"] or receipt.get("pr_number") != pr["number"] or any(not isinstance(receipt.get(k), str) or not sha_re.fullmatch(receipt[k]) for k in ("base_sha","head_sha","source_sha")) or any(not isinstance(receipt.get(k), str) or not digest_re.fullmatch(receipt[k]) for k in ("body_sha256","observation_sha256","ruleset_digest")) or receipt.get("cutover_receipt_sha256") is not None and (not isinstance(receipt["cutover_receipt_sha256"],str) or not digest_re.fullmatch(receipt["cutover_receipt_sha256"])) or not isinstance(receipt.get("producer"),str) or not receipt["producer"] or not isinstance(receipt.get("snapshot_digests"),dict) or set(receipt["snapshot_digests"]) != snapshot_keys or any(not isinstance(v,str) or not digest_re.fullmatch(v) for v in receipt["snapshot_digests"].values()):
        raise ValidationError("TYPE_MISMATCH")


def cutover_digest(observation: dict[str, Any]) -> str:
    epoch = observation["authoring_epoch"]
    projection = {"repository": observation["repository"]["name"], "default_ref": epoch.get("default_ref"), "cutover_merge_sha": epoch.get("cutover_merge_sha"), "template_blobs": epoch.get("template_blobs"), "first_strict_pr_number": epoch.get("first_strict_pr_number"), "legacy_open_pr_numbers": epoch.get("legacy_open_pr_numbers"), "receipt_ruleset_digest": epoch.get("receipt_ruleset_digest")}
    return digest(projection)


def receipt_projection(observation: dict[str, Any], manifest: dict[str, Any]) -> dict[str, str | None]:
    """Return the closed, deterministic receipt values without mutating observation."""
    receiptless = json.loads(canonical_json(observation))
    receiptless["receipt"].pop("observation_sha256", None)
    epoch = observation["authoring_epoch"]
    cutover = None
    if epoch.get("cutover_receipt_sha256") is not None:
        cutover = epoch["cutover_receipt_sha256"]
    return {
        "OBSERVATION": digest(receiptless),
        "BODY": hashlib.sha256(observation["pull_request"]["body"].encode("utf-8")).hexdigest(),
        "CUTOVER": cutover,
        "RULESET": digest(manifest),
        "AUTHORING_EPOCH": digest(observation["authoring_epoch"]),
        "CHANGED_PATHS": digest(observation["changed_paths"]),
        "AGENTOS": digest(observation["agentos"]),
        "LINEAR": digest(observation["linear"]),
        "PATH_OWNERSHIP": digest(observation["path_ownership"]),
        "NATIVE_LINKAGE": digest(observation["native_linkage"]),
    }


def finalize_receipt(observation: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    """Return a receipt-grounded deep copy for fixtures/adapters; the core remains pure."""
    out = json.loads(canonical_json(observation))
    receipt = out["receipt"]
    if out["authoring_epoch"].get("state") == "PRESENT":
        out["authoring_epoch"]["cutover_receipt_sha256"] = cutover_digest(out)
    expected = receipt_projection(out, manifest)
    receipt["repository"] = out["repository"]["name"]
    receipt["pr_number"] = out["pull_request"]["number"]
    receipt["body_sha256"] = expected["BODY"]
    receipt["cutover_receipt_sha256"] = expected["CUTOVER"]
    receipt["ruleset_digest"] = expected["RULESET"]
    receipt["snapshot_digests"] = {k.lower(): expected[k] for k in ("AUTHORING_EPOCH","CHANGED_PATHS","AGENTOS","LINEAR","PATH_OWNERSHIP","NATIVE_LINKAGE")}
    # observation hash includes the complete receipt except itself; recompute once after all fields settle.
    receipt["observation_sha256"] = receipt_projection(out, manifest)["OBSERVATION"]
    return out


def analyze(observation: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    """Analyze an already-decoded frozen observation. It is referentially transparent."""
    _validate_top(observation, manifest)
    rules = _rule_map(manifest)
    values, locs, _, defects, body_relationships = parse_header(observation["pull_request"]["body"], manifest["limits"])
    findings: list[dict[str, Any]] = []
    def add(rule: str, ev: dict[str, Any], field: str | None = None):
        findings.append(_finding(rules, rule, ev, field=field, line=(locs.get(field) or [None])[0] if field else None))
    missing = sorted(f for f in FIELDS if values[f] is None)
    if missing: add("R001", {"missing_fields": missing})
    for f in FIELDS:
        if len(locs[f]) > 1:
            duplicate_values = [value for n, field, value in _ if field == f and n in locs[f]]
            findings.append(_finding(rules, "R002", {"field":f,"locations":sorted(f"BODY:L{x}:{f}" for x in locs[f]),"values":_digest_wrappers(canonical_digest(x) for x in duplicate_values)}, field=f, line=locs[f][1]))
    if defects:
        defect = sorted(set(defects))[0]
        match = re.fullmatch(r"RELATIONSHIP@([1-9][0-9]*):(.+)", defect)
        if match:
            location = f"BODY:L{match.group(1)}:RELATIONSHIP"
            findings.append(_finding(rules, "R003", {"location":location,"reason":match.group(2)}, field="RELATIONSHIP", line=int(match.group(1))))
        else:
            findings.append(_finding(rules, "R003", {"location":"DECLARATION:BLOCK","reason":defect.split(":", 1)[-1]}))
    normalized = dict(values)
    epoch = observation["authoring_epoch"]
    authorized_alias = False
    for f in FIELDS:
        v = values[f]
        if v is None: continue
        if v in {"", "TBD", "TODO"} or "|" in v or (v.startswith("<") and v.endswith(">")):
            add("R004", {"field":f,"location":f"BODY:L{locs[f][0]}:{f}","value":text_digest(v)}, f); continue
        if f not in ENUMS:
            continue
        aliases = ALIASES_BY_FIELD.get(f, {})
        if v in aliases:
            if epoch["state"] == "PRESENT" and epoch.get("relation") == "PRE_CUTOVER":
                normalized[f] = aliases[v]; authorized_alias = True; add("R021", {"alias":v,"canonical":aliases[v],"field":f,"receipt":canonical_digest(epoch)}, f)
            elif epoch["state"] == "PRESENT" and epoch.get("relation") == "AT_OR_POST_CUTOVER":
                add("R020", {"epoch":"AT_OR_POST_CUTOVER","field":f,"value":text_digest(v)}, f)
            else:
                add("R022", {"epoch_state":epoch["state"],"receipt_digest":epoch.get("cutover_receipt_sha256")}, f)
        elif v not in ENUMS[f]:
            if f == "Portfolio-Mode" and v == "untracked_refused": add("R010", {"location":f"BODY:L{locs[f][0]}:{f}","value":text_digest(v)}, f)
            add({"Portfolio-Mode":"R009","Authority":"R011","Completion":"R012"}[f], {"location":f"BODY:L{locs[f][0]}:{f}","value":text_digest(v)}, f)
            add("R020", {"epoch":epoch.get("relation","UNKNOWN"),"field":f,"value":text_digest(v)}, f)
    ws, linear, wave = values["Workstream"], values["Linear"], values["Wave"]
    linear_exact = bool(isinstance(linear, str) and re.fullmatch(r"MAS-[1-9][0-9]{0,8}", linear))
    # Placeholders are a distinct frozen rule for every scalar, including identity fields.
    for f, v in values.items():
        if v is not None and (v.startswith("<") and v.endswith(">")) and not any(x["rule_id"] == "R004" and x["location"].endswith(":" + f) for x in findings):
            add("R004", {"field":f,"location":f"BODY:L{locs[f][0]}:{f}","value":text_digest(v)}, f)
    if ws is not None and not re.fullmatch(r"(?:NONE|WS:[A-Z0-9]+(?:-[A-Z0-9]+)*)", ws): add("R005", {"location":f"BODY:L{locs['Workstream'][0]}:Workstream","value":text_digest(ws)}, "Workstream")
    if linear is not None and not re.fullmatch(r"(?:NONE|MAS-[1-9][0-9]{0,8})", linear): add("R006", {"location":f"BODY:L{locs['Linear'][0]}:Linear","value":text_digest(linear)}, "Linear")
    if wave == "": add("R007", {"location":f"BODY:L{locs['Wave'][0]}:Wave"}, "Wave")
    elif wave is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", wave): add("R008", {"location":f"BODY:L{locs['Wave'][0]}:Wave","value":text_digest(wave)}, "Wave")
    mode, authority, completion = normalized["Portfolio-Mode"], normalized["Authority"], normalized["Completion"]
    canonical = mode in ENUMS["Portfolio-Mode"] and authority in ENUMS["Authority"] and completion in ENUMS["Completion"]
    # A receipt-authorized compatibility alias is analysed through its normalized
    # value but remains visibly legacy; it can never masquerade as a V1 author.
    identity_legal = bool(ws and re.fullmatch(r"(?:NONE|WS:[A-Z0-9]+(?:-[A-Z0-9]+)*)", ws) and linear and re.fullmatch(r"(?:NONE|MAS-[1-9][0-9]{0,8})", linear) and wave and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", wave))
    author_state = "LEGACY" if authorized_alias else ("CANONICAL" if canonical and identity_legal else ("MISSING" if missing else "INVALID"))
    classification = manifest["classification"]["legacy_class"] if author_state == "LEGACY" else (manifest["classification"]["mode_to_class"].get(mode, "UNKNOWN") if author_state == "CANONICAL" else "UNKNOWN")
    if canonical and linear == "NONE": add("R029", {"linear":"NONE","portfolio_mode":mode})
    agentos, lsnap, paths, ownership, native = (observation[x] for x in ("agentos","linear","changed_paths","path_ownership","native_linkage"))
    if (mode in {"tracked","creates_workstream"} or (mode == "architecture_candidate" and ws not in {None,"NONE"})) and agentos["state"] != "PRESENT": add("R033", {"snapshot_state":agentos["state"],"workstream":ws or "NONE"})
    if mode == "tracked" and ws == "NONE": add("R031", {"portfolio_mode":mode,"workstream":ws})
    if mode == "maintenance_exception" and ws != "NONE": add("R032", {"portfolio_mode":mode,"workstream":ws or "NONE"})
    if agentos["state"] == "PRESENT" and ws and ws != "NONE" and mode in {"tracked","architecture_candidate"} and ws not in {r.get("key") for r in agentos.get("workstreams",[])}:
        add("R030", {"workstream":ws})
    branch_targets = _issue_ids(observation["pull_request"].get("branch", ""))
    title_targets = _issue_ids(observation["pull_request"].get("title", ""))
    body_targets = sorted({issue for issue, _, _ in body_relationships}, key=_mas_key)
    native_targets = sorted({r.get("issue_id") for r in native.get("relationships", []) if isinstance(r.get("issue_id"), str)}, key=_mas_key)
    target_ids = sorted(set(([linear] if linear_exact else []) + branch_targets + title_targets + body_targets + native_targets), key=_mas_key)
    roles_by_target: dict[str, list[str]] = {}
    rows_by_target: dict[str, list[dict[str, Any]]] = {}
    role_mismatch_targets: list[str] = []
    role_mismatch_roles: list[str] = []
    if linear_exact:
        if lsnap["state"] != "PRESENT":
            add("R035", {"linear":linear,"snapshot_state":lsnap["state"]})
        else:
            for target in target_ids:
                rows = [r for r in lsnap.get("issues",[]) if r.get("id") == target]
                rows_by_target[target] = rows
                roles_by_target[target] = sorted(r.get("target_role", "UNKNOWN") for r in rows)
                if target == linear and not rows:
                    add("R034", {"linear":linear})
                    continue
                if target != linear and (not rows or "UNKNOWN" in roles_by_target[target]):
                    add("R026", {"required_targets":[target],"target_roles":roles_by_target[target] or ["UNKNOWN"]})
                    continue
                if target == linear and "UNKNOWN" in roles_by_target[target]:
                    add("R026", {"required_targets":[target],"target_roles":roles_by_target[target]})
                    continue
                declared = [r for r in rows if r.get("target_role") == "DECLARED"]
                if target == linear and len(declared) != 1:
                    role_mismatch_targets.append(target); role_mismatch_roles.extend(roles_by_target[target])
                if target != linear and declared:
                    role_mismatch_targets.append(target); role_mismatch_roles.extend(roles_by_target[target])
                invalid_type_rows = []
                for r in rows:
                    allowed = manifest["classification"]["mode_to_issue_types"].get(mode,[]) if r.get("target_role") == "DECLARED" else manifest["classification"]["target_role_to_issue_types"].get(r.get("target_role"),[])
                    if r.get("issue_type") not in allowed:
                        invalid_type_rows.append(r)
                if invalid_type_rows:
                    r = sorted(invalid_type_rows, key=lambda row:(row.get("target_role","UNKNOWN"),row.get("issue_type","UNKNOWN")))[0]
                    add("R028", {"issue_type":r.get("issue_type","UNKNOWN"),"portfolio_mode":mode or "UNKNOWN","target_role":r.get("target_role","UNKNOWN")})
                if target == linear and mode in {"tracked","architecture_candidate"} and ws not in {None,"NONE"} and declared and declared[0].get("workstream_key") != ws:
                    add("R036", {"bound_workstream":declared[0].get("workstream_key"),"declared_workstream":ws,"linear":linear})
                if target == linear and mode == "creates_workstream" and declared and declared[0].get("workstream_key") not in {None, ws}:
                    add("R036", {"bound_workstream":declared[0].get("workstream_key"),"declared_workstream":ws,"linear":linear})
    if role_mismatch_targets:
        add("R027", {"declared":linear,"roles":sorted(set(role_mismatch_roles)),"targets":sorted(set(role_mismatch_targets), key=_mas_key)})
    if linear_exact:
        suppressed = {(r.get("issue_id"), r.get("source")) for r in native.get("relationships", []) if r.get("state") == "SUPPRESSED"}
        def competes(target: str, source: str) -> bool:
            return target != linear and (target, source) not in suppressed and "DECLARED" in roles_by_target.get(target, [])
        bad_branch = [x for x in branch_targets if competes(x, "BRANCH")]
        if bad_branch: add("R050", {"branch_targets":bad_branch,"declared":linear})
        competing = sorted({x for x in title_targets if competes(x, "TITLE")} | {x for x in body_targets if competes(x, "BODY")}, key=_mas_key)
        if competing: add("R051", {"body_targets":body_targets,"declared":linear,"title_targets":title_targets})
        native_competing = {r.get("issue_id") for r in native.get("relationships", []) if r.get("state") == "PRESENT" and isinstance(r.get("issue_id"), str) and competes(r["issue_id"], r.get("source", "ADAPTER"))}
        declared_targets = sorted({linear} | {x for x in branch_targets if competes(x, "BRANCH")} | {x for x in title_targets if competes(x, "TITLE")} | {x for x in body_targets if competes(x, "BODY")} | native_competing, key=_mas_key)
        if len(declared_targets) > 1: add("R039", {"declared":linear,"targets":declared_targets})
    if canonical and tuple([mode,authority,completion]) not in {tuple(x) for x in manifest["authority_completion_allowlist"]}: add("R040", {"authority":authority,"completion":completion,"portfolio_mode":mode})
    if paths["state"] != "PRESENT": add("R043", {"snapshot_state":paths["state"]})
    if ownership["state"] != "PRESENT":
        add("R042", {"paths":[],"snapshot_state":ownership["state"]})
        # Partial ownership may still contain conclusive negative evidence.  Do
        # not convert an observed UNOWNED/exact-nonmaintenance row into an
        # unknown merely because unrelated rows could not be captured.
        if canonical and mode == "maintenance_exception":
            known_bad = [r for r in ownership.get("resolutions", []) if r.get("resolution") == "UNOWNED" or (r.get("resolution") == "EXACT" and (r.get("path_class") != "MAINTENANCE" or r.get("owner_workstream") != "NONE" or "maintenance" not in r.get("allowed_authorities", [])))]
            if known_bad: add("R044", {"authority":authority,"linear":linear or "NONE","paths":_digest_wrappers(text_digest(r.get("path","")) for r in known_bad)})
    elif canonical:
        rs = ownership.get("resolutions",[])
        unowned = [r for r in rs if r.get("resolution") == "UNOWNED"]
        excluded = [r for r in rs if r.get("resolution") == "EXACT" and authority not in r.get("allowed_authorities",[])]
        if unowned: add("R047", {"paths":_digest_wrappers(text_digest(r.get("path","")) for r in unowned),"resolutions":_digest_wrappers(canonical_digest(r) for r in unowned)})
        if excluded: add("R041", {"authority":authority,"paths":_digest_wrappers(text_digest(r.get("path","")) for r in excluded),"resolutions":_digest_wrappers(canonical_digest(r) for r in excluded)})
        if mode == "maintenance_exception":
            bad = [r for r in rs if r.get("resolution") != "EXACT" or r.get("path_class") != "MAINTENANCE" or r.get("owner_workstream") != "NONE" or "maintenance" not in r.get("allowed_authorities", [])]
            if bad: add("R044", {"authority":authority,"linear":linear or "NONE","paths":_digest_wrappers(text_digest(r.get("path","")) for r in bad)})
        if mode == "architecture_candidate" and (authority in {"implementation","deploy"} or any(r.get("path_class") in {"IMPLEMENTATION","DEPLOY"} for r in rs)):
            add("R045", {"authority":authority,"paths":_digest_wrappers(text_digest(r.get("path","")) for r in rs)})
        if mode == "creates_workstream":
            impl = [r for r in rs if r.get("path_class") in {"IMPLEMENTATION","DEPLOY"}]
            if impl: add("R046", {"path_classes":sorted(set(r.get("path_class") for r in impl)),"paths":_digest_wrappers(text_digest(r.get("path","")) for r in impl)})
    if mode == "creates_workstream":
        if agentos["state"] == "PRESENT" and ws:
            collisions = sorted(r.get("key") for r in agentos.get("workstreams", []) if r.get("key", "").upper() == ws.upper())
            if collisions: add("R038", {"collisions":collisions,"workstream":ws})
        record_name = ws.replace(":", "-") if isinstance(ws, str) else ""
        if paths["state"] == "PRESENT" and ws and not any(r.get("path") == f"agentos/workstreams/{record_name}.md" and r.get("change_type") in {"ADDED","MODIFIED"} for r in paths.get("paths", [])):
            add("R037", {"paths":_digest_wrappers(text_digest(r.get("path","")) for r in paths.get("paths",[])),"workstream":ws})
    completion_rows: list[dict[str, Any]] = []
    if native["state"] in {"PARTIAL", "UNAVAILABLE"}:
        if linear_exact:
            add("R054", {"linear":linear,"snapshot_state":native["state"]})
        for target in target_ids:
            row = next((r for r in rows_by_target.get(target, []) if r.get("target_role") == "DECLARED"), None)
            completion_rows.append({"issue_id":target,"effect":"UNKNOWN","declared_completion":completion if target == linear else None,"stop_law":row.get("stop_law") if row else None,"consistency":"INDETERMINATE"})
    else:
        for target in target_ids:
            rels = [r for r in native.get("relationships", []) if r.get("issue_id") == target]
            active = [r for r in rels if r.get("state") == "PRESENT"]
            eligible = [r for r in active if r.get("completion_transition") == "ELIGIBLE"]
            ambiguous = native["state"] == "CONTRADICTORY" or len({r.get("completion_transition") for r in active}) > 1
            effect = "AMBIGUOUS" if ambiguous else ("COMPLETION_CAPABLE" if eligible else ("NON_CLOSING" if active else "NONE"))
            role = next((r.get("target_role") for r in rows_by_target.get(target, []) if r.get("target_role") != "UNKNOWN"), "UNKNOWN")
            declared_row = next((r for r in rows_by_target.get(target, []) if r.get("target_role") == "DECLARED"), None)
            stop_law = declared_row.get("stop_law") if declared_row else None
            declared_completion = completion if target == linear else None
            records_exception = target == linear and completion == "records-only" and stop_law == "RECORDS_ONLY" and ownership["state"] == "PRESENT" and bool(ownership.get("resolutions")) and all(r.get("resolution") == "EXACT" and r.get("path_class") == "RECORDS" and r.get("owner_workstream") in {"NONE", None} and "records" in r.get("allowed_authorities", []) for r in ownership.get("resolutions", []))
            mismatch = (target == linear and completion == "merge-is-done" and effect != "COMPLETION_CAPABLE") or (effect == "COMPLETION_CAPABLE" and ((target != linear) or (completion in {"built-not-proven","proof-required","acceptance-required"}) or (completion == "records-only" and not records_exception)))
            consistency = "INDETERMINATE" if ambiguous or native["state"] != "PRESENT" else ("MISMATCH" if mismatch else "MATCH")
            completion_rows.append({"issue_id":target,"effect":effect,"declared_completion":declared_completion,"stop_law":stop_law,"consistency":consistency})
            if ambiguous:
                add("R055", {"diagnostics":native.get("diagnostics", []),"linear":target,"relationships":_digest_wrappers(canonical_digest(r) for r in rels)})
            if mismatch:
                add("R056", {"completion":completion,"effect":effect,"stop_law":stop_law or "UNKNOWN","target":target,"target_role":role})
            if target == linear and completion == "merge-is-done" and stop_law in {"PROOF","ACCEPTANCE"}:
                add("R053", {"completion":completion,"linear":linear,"stop_law":stop_law})
    for sname, snap in (("AUTHORING_EPOCH",epoch),("CHANGED_PATHS",paths),("AGENTOS",agentos),("LINEAR",lsnap),("PATH_OWNERSHIP",ownership),("NATIVE_LINKAGE",native)):
        if snap["state"] == "CONTRADICTORY": findings.append(_finding(rules, "R061", {"diagnostics":snap.get("diagnostics",[]),"snapshot":sname}, component=sname))
    # Grounding mismatches are semantic (valid observation, refused metadata), not an exit-2 route.
    receipt = observation["receipt"]
    ground = receipt_projection(observation, manifest)
    observed_ground = {
        "OBSERVATION": receipt.get("observation_sha256"), "BODY": receipt.get("body_sha256"),
        "CUTOVER": receipt.get("cutover_receipt_sha256"), "RULESET": receipt.get("ruleset_digest"),
        "AUTHORING_EPOCH": receipt.get("snapshot_digests", {}).get("authoring_epoch"),
        "CHANGED_PATHS": receipt.get("snapshot_digests", {}).get("changed_paths"),
        "AGENTOS": receipt.get("snapshot_digests", {}).get("agentos"),
        "LINEAR": receipt.get("snapshot_digests", {}).get("linear"),
        "PATH_OWNERSHIP": receipt.get("snapshot_digests", {}).get("path_ownership"),
        "NATIVE_LINKAGE": receipt.get("snapshot_digests", {}).get("native_linkage"),
    }
    for component, expected in ground.items():
        observed = observed_ground[component]
        if observed != expected:
            findings.append(_finding(rules,"R060",{"component":component,"expected":canonical_digest(expected),"observed":canonical_digest(observed)}, component=component))
    # Visible closing claim is independently material even without an adapter native row.
    if completion in {"built-not-proven","proof-required","acceptance-required","records-only"}:
        closing = []
        for target, kind, line in body_relationships:
            declared_row = next((r for r in rows_by_target.get(target, []) if r.get("target_role") == "DECLARED"), None)
            records_ok = completion == "records-only" and declared_row and declared_row.get("stop_law") == "RECORDS_ONLY" and ownership["state"] == "PRESENT" and bool(ownership.get("resolutions")) and all(r.get("resolution") == "EXACT" and r.get("path_class") == "RECORDS" and r.get("owner_workstream") in {"NONE", None} and "records" in r.get("allowed_authorities", []) for r in ownership.get("resolutions", []))
            if target == linear and kind == "CLOSING" and not records_ok:
                closing.append((line, canonical_digest({"issue":target,"kind":kind})))
        if closing:
            closing.sort(key=lambda x:(x[0], canonical_json(x[1])))
            relationship_evidence = _digest_wrappers(x[1] for x in closing)
            findings.append(_finding(rules,"R052",{"completion":completion,"linear":linear,"relationships":relationship_evidence},field="RELATIONSHIP",line=closing[0][0]))
    if linear_exact and lsnap["state"] == "PRESENT":
        declared_rows = [r for r in rows_by_target.get(linear, []) if r.get("target_role") == "DECLARED"]
        if completion == "merge-is-done" and declared_rows and declared_rows[0].get("stop_law") in {"PROOF","ACCEPTANCE"}:
            if not any(f.get("rule_id") == "R053" for f in findings):
                add("R053", {"completion":completion,"linear":linear,"stop_law":declared_rows[0]["stop_law"]})
    if linear_exact and not completion_rows:
        declared_rows = [r for r in lsnap.get("issues", []) if r.get("id") == linear and r.get("target_role") == "DECLARED"] if lsnap["state"] == "PRESENT" else []
        completion_rows.append({"issue_id":linear,"effect":"UNKNOWN","declared_completion":completion,"stop_law":declared_rows[0].get("stop_law") if declared_rows else None,"consistency":"INDETERMINATE"})
    unresolved = sorted(name for name, snap in (("AUTHORING_EPOCH",epoch),("CHANGED_PATHS",paths),("AGENTOS",agentos),("LINEAR",lsnap),("PATH_OWNERSHIP",ownership),("NATIVE_LINKAGE",native)) if snap["state"] in {"PARTIAL","UNAVAILABLE","CONTRADICTORY"})
    findings.sort(key=lambda x:(SEVERITY[x["severity"]],x["code"],x["rule_id"],x["location"],canonical_json(x["evidence"])))
    # deterministic semantic de-duplication
    kept=[]; seen=set()
    for f in findings:
        k=canonical_json(f)
        if k not in seen:
            kept.append(f); seen.add(k)
            if len(kept) > manifest["limits"]["findings"]:
                raise ResourceLimitError("findings", manifest["limits"]["findings"], len(kept))
    verdict = "REFUSE_METADATA" if any(f["severity"]=="ERROR" for f in kept) else ("PARTIAL" if any(f["severity"]=="PARTIAL" for f in kept) else ("WARN" if kept else "CONFORMANT"))
    completeness = "UNAVAILABLE" if author_state == "MISSING" else ("DEGRADED" if unresolved or any(f["severity"]=="PARTIAL" for f in kept) else "COMPLETE")
    completion_rows.sort(key=lambda r:(_mas_key(r["issue_id"]),r["effect"],r["declared_completion"] or "",r["stop_law"] or "",r["consistency"]))
    semantic = {"ruleset_id":manifest["ruleset_id"],"ruleset_digest":digest(manifest),"enforcement":"REPORT_ONLY","declaration":{"workstream":ws,"linear":linear,"portfolio_mode":mode,"wave":wave,"authority":authority,"completion":completion,"authoring_state":author_state},"classification":classification,"verdict":verdict,"completeness":completeness,"completion_interpretation":completion_rows,"unresolved_observation_classes":unresolved,"findings":kept}
    receipt = observation["receipt"]
    # A supplied receipt mismatch remains in R060's observed evidence.  The
    # emitted report receipt is the core's revalidated grounding projection,
    # so it never repeats a digest it has just proven false.
    report_receipt = json.loads(canonical_json(receipt))
    report_receipt["observation_schema"] = OBS_SCHEMA
    report_receipt["observation_sha256"] = ground["OBSERVATION"]
    report_receipt["body_sha256"] = ground["BODY"]
    report_receipt["cutover_receipt_sha256"] = ground["CUTOVER"]
    report_receipt["ruleset_digest"] = ground["RULESET"]
    report_receipt["snapshot_digests"] = {
        key.lower(): ground[key]
        for key in ("AUTHORING_EPOCH","CHANGED_PATHS","AGENTOS","LINEAR","PATH_OWNERSHIP","NATIVE_LINKAGE")
    }
    report = {"schema":REPORT_SCHEMA,"semantic":semantic,"semantic_hash":digest(semantic),"receipt":report_receipt,"human":{"summary":f"{classification}/{verdict}","remediations":sorted(set(f["remediation_code"] for f in kept))}}
    validate_report(report)
    return report
