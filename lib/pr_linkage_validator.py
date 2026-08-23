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
FIELDS = ("Workstream", "Linear", "Portfolio-Mode", "Wave", "Authority", "Completion")
STATE = {"PRESENT", "PARTIAL", "UNAVAILABLE", "NOT_APPLICABLE", "CONTRADICTORY"}
ALIASES = {"workstream_creation": "creates_workstream", "runtime": "implementation",
           "production-proof": "proof", "production-proof-required": "proof-required"}
ENUMS = {"Portfolio-Mode": {"tracked", "maintenance_exception", "creates_workstream", "architecture_candidate"},
         "Authority": {"implementation", "records", "research", "maintenance", "proof", "deploy", "architecture_candidate"},
         "Completion": {"merge-is-done", "built-not-proven", "proof-required", "acceptance-required", "records-only"}}
SEVERITY = {"ERROR": 0, "PARTIAL": 1, "WARNING": 2, "NOTICE": 3}
# This closed registry is intentionally explicit: implementation may never grow a hidden rule
# outside the frozen manifest.  `analyze` verifies equality before semantic reduction.
FROZEN_RULE_IDS = frozenset((
 "R001","R002","R003","R004","R005","R006","R007","R008","R009","R010","R011","R012","R020","R021","R022","R026","R027","R028","R029","R030","R031","R032","R033","R034","R035","R036","R037","R038","R039","R040","R041","R042","R043","R044","R045","R046","R047","R050","R051","R052","R053","R054","R055","R056","R060","R061"))


class ValidationError(ValueError):
    """Input violates the closed V1 observation contract."""


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
    return sorted(set(m.group(0).upper() for m in re.finditer(r"(?<![A-Za-z0-9])MAS-[1-9][0-9]{0,8}(?![A-Za-z0-9])", text, re.ASCII | re.I)))


def _visible_lines(body: str) -> tuple[list[tuple[int, str]], list[str]]:
    """Return visible lines plus deterministic parse defects, Markdown-aware enough for V1."""
    defects: list[str] = []
    forbidden = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2060-\u206f]")
    if "\r" in body.replace("\r\n", "") or body.startswith("\ufeff") or forbidden.search(body):
        raise ValidationError("INVALID_BODY_ENCODING")
    body = body.replace("\r\n", "\n")
    lines = body.split("\n")
    if len(lines) > 10000:
        raise ValidationError("RESOURCE_LIMIT:body_lines")
    if any(len(line.encode("utf-8")) > 16384 for line in lines):
        raise ValidationError("RESOURCE_LIMIT:line_bytes")
    visible: list[tuple[int, str]] = []
    fence: tuple[str, int] | None = None
    comment = False
    for n, line in enumerate(lines, 1):
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        if comment:
            if "-->" in line:
                comment = False
            continue
        if "<!--" in line:
            start, end = line.index("<!--"), line.find("-->", line.index("<!--") + 4)
            if end < 0:
                comment = True
                continue
            line = line[:start] + line[end + 3:]
            stripped = line.lstrip(" "); indent = len(line) - len(stripped)
            if not line:
                continue
        marker = re.match(r" {0,3}(`{3,}|~{3,})(?:[^`~].*)?$", line)
        if fence:
            closer = re.fullmatch(r" {0,3}([`~]{3,})[ \t]*", line)
            if closer and closer.group(1)[0] == fence[0] and len(closer.group(1)) >= fence[1]:
                fence = None
            continue
        if marker:
            fence = (marker.group(1)[0], len(marker.group(1)))
            continue
        if (indent <= 3 and stripped.startswith(">")) or indent >= 4:
            continue
        visible.append((n, line))
    if fence or comment:
        defects.append("UNCLOSED_MARKDOWN")
    return visible, defects


def parse_header(body: str, limits: dict[str, int]) -> tuple[dict[str, str | None], dict[str, list[int]], list[tuple[str, int]], list[str], list[tuple[str, str, int]]]:
    if len(body.encode("utf-8")) > limits["body_bytes"]:
        raise ValidationError("RESOURCE_LIMIT:body_bytes")
    visible, defects = _visible_lines(body)
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
                raise ValidationError("RESOURCE_LIMIT:field_occurrences")
    headers: list[tuple[int, str, str]] = []
    for n, line in zone:
        match = re.fullmatch(r"(Workstream|Linear|Portfolio-Mode|Wave|Authority|Completion): (.*)", line)
        if match:
            headers.append((n, match.group(1), match.group(2)))
        elif line and not re.fullmatch(r"(?:close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved|complete|completes|completed|implement|implements|implemented|ref|refs|reference|references|part of|contributes to|toward|towards|relates to|related to|skip|ignore) .+", line, re.I):
            defects.append("NONPERMITTED_PREAMBLE")
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
                raise ValidationError("RESOURCE_LIMIT:value_bytes")
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
    rel = re.compile(r" {0,3}(close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved|complete|completes|completed|implement|implements|implemented|ref|refs|reference|references|part of|contributes to|toward|towards|relates to|related to|skip|ignore) (MAS-[1-9][0-9]{0,8}(?: *, *MAS-[1-9][0-9]{0,8}| +and +MAS-[1-9][0-9]{0,8})*)\.?$", re.I | re.ASCII)
    for n, line in visible:
        m = rel.fullmatch(line)
        if m:
            word = m.group(1).lower()
            kind = "CLOSING" if word in {"close","closes","closed","fix","fixes","fixed","resolve","resolves","resolved","complete","completes","completed","implement","implements","implemented"} else ("SUPPRESSED" if word in {"skip","ignore"} else ("RELATION_ONLY" if word in {"relates to","related to"} else "CONTRIBUTING"))
            for issue in _issue_ids(m.group(2)):
                relationships.append((issue, kind, n))
    relationships = sorted(set(relationships))
    if len(relationships) > limits["relationships"]:
        raise ValidationError("RESOURCE_LIMIT:relationships")
    return values, locs, headers, defects, relationships


def _rule_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out = {r["rule_id"]: r for r in manifest["rules"]}
    if set(out) != FROZEN_RULE_IDS or len(out) != 46:
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    return out


def validate_report(report: dict[str, Any]) -> None:
    """Closed report-wire validation for adapters and test fixtures."""
    required = {"schema", "semantic", "semantic_hash", "receipt", "human"}
    if not isinstance(report, dict) or set(report) != required or report.get("schema") != REPORT_SCHEMA:
        raise ValidationError("TYPE_MISMATCH")
    semantic = report["semantic"]
    if not isinstance(semantic, dict) or report.get("semantic_hash") != digest(semantic):
        raise ValidationError("TYPE_MISMATCH")
    if semantic.get("enforcement") != "REPORT_ONLY" or semantic.get("verdict") not in {"CONFORMANT","WARN","PARTIAL","REFUSE_METADATA"}:
        raise ValidationError("TYPE_MISMATCH")
    for finding in semantic.get("findings", []):
        if set(finding) != {"code","rule_id","severity","location","evidence","remediation_code"} or finding["rule_id"] not in FROZEN_RULE_IDS:
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


def _validate_top(observation: dict[str, Any], manifest: dict[str, Any]) -> None:
    required = {"schema","ruleset_id","ruleset_digest","repository","pull_request","authoring_epoch","changed_paths","agentos","linear","path_ownership","native_linkage","receipt"}
    if not isinstance(observation, dict): raise ValidationError("TYPE_MISMATCH")
    if set(observation) != required: raise ValidationError("UNKNOWN_KEY" if set(observation)-required else "MISSING_KEY")
    if observation["schema"] != OBS_SCHEMA: raise ValidationError("TYPE_MISMATCH")
    if observation["ruleset_id"] != manifest["ruleset_id"]: raise ValidationError("UNSUPPORTED_RULESET_ID")
    if observation["ruleset_digest"] != digest(manifest): raise ValidationError("RULESET_DIGEST_MISMATCH")
    atom_re = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    sha_re = re.compile(r"^[0-9a-f]{40}$")
    digest_re = re.compile(r"^[0-9a-f]{64}$")
    if not isinstance(observation.get("repository"), dict) or set(observation["repository"]) != {"name"} or not isinstance(observation["repository"]["name"], str) or not atom_re.fullmatch(observation["repository"]["name"]):
        raise ValidationError("TYPE_MISMATCH")
    pr = observation.get("pull_request")
    if not isinstance(pr, dict) or set(pr) != {"number","title","body","branch","base_ref","head_ref"} or not isinstance(pr.get("number"), int) or pr["number"] < 1 or not all(isinstance(pr.get(k), str) for k in ("title","body")) or not all(isinstance(pr.get(k), str) and pr[k] and pr[k].isascii() for k in ("branch","base_ref","head_ref")):
        raise ValidationError("TYPE_MISMATCH")
    if not isinstance(observation.get("ruleset_digest"), str) or not digest_re.fullmatch(observation["ruleset_digest"]): raise ValidationError("TYPE_MISMATCH")
    for name in ("authoring_epoch","changed_paths","agentos","linear","path_ownership","native_linkage"):
        snap = observation[name]
        if not isinstance(snap, dict) or snap.get("state") not in STATE or not isinstance(snap.get("diagnostics"), list) or any(not isinstance(x, str) for x in snap.get("diagnostics", [])) or snap["diagnostics"] != sorted(set(snap["diagnostics"])):
            raise ValidationError("INVALID_SNAPSHOT_STATE")
    epoch = observation["authoring_epoch"]
    epoch_keys = {"state","relation","default_ref","cutover_merge_sha","template_blobs","first_strict_pr_number","legacy_open_pr_numbers","receipt_ruleset_digest","cutover_receipt_sha256","diagnostics"}
    if set(epoch) != epoch_keys or epoch.get("relation") not in {"PRE_CUTOVER","AT_OR_POST_CUTOVER","UNKNOWN"}:
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    if epoch["state"] == "PRESENT" and (epoch["relation"] == "UNKNOWN" or epoch.get("receipt_ruleset_digest") != observation["ruleset_digest"]):
        raise ValidationError("EPOCH_RECEIPT_RULESET_MISMATCH")
    if epoch["state"] == "PRESENT":
        if not isinstance(epoch.get("default_ref"), str) or not isinstance(epoch.get("cutover_merge_sha"), str) or not sha_re.fullmatch(epoch["cutover_merge_sha"]) or not isinstance(epoch.get("first_strict_pr_number"), int) or not epoch.get("template_blobs"):
            raise ValidationError("INVALID_SNAPSHOT_STATE")
        if epoch["legacy_open_pr_numbers"] != sorted(set(epoch["legacy_open_pr_numbers"])) or any(not isinstance(x, int) or x < 1 for x in epoch["legacy_open_pr_numbers"]): raise ValidationError("INVALID_SNAPSHOT_STATE")
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
        raise ValidationError("RESOURCE_LIMIT:changed_paths")
    for name, base in (("agentos", "BASE"), ("path_ownership", "BASE_POLICY")):
        if observation[name].get("basis") != base: raise ValidationError("INVALID_SNAPSHOT_STATE")
    cp = observation["changed_paths"]["paths"]
    if cp != sorted(cp, key=lambda r:(r.get("path", ""), r.get("change_type", ""), r.get("old_path") or "")) or len({(r.get("path"),r.get("change_type"),r.get("old_path")) for r in cp}) != len(cp): raise ValidationError("INVALID_SNAPSHOT_STATE")
    native = observation["native_linkage"]
    if not isinstance(native.get("pagination_complete"), bool):
        raise ValidationError("INVALID_SNAPSHOT_STATE")
    legal = manifest["native_reduction"]["legal_rows"]
    for row in native["relationships"]:
        if not isinstance(row, dict) or set(row) != {"issue_id","kind","source","state","completion_transition"}:
            raise ValidationError("INVALID_SNAPSHOT_STATE")
        state, kind, source, transition = row["state"], row["kind"], row["source"], row["completion_transition"]
        valid = False
        if state == "PRESENT" and kind == "AUTO_LINK": valid = source in {"BRANCH","TITLE"} and transition in {"ELIGIBLE","INELIGIBLE"}
        elif state == "PRESENT" and kind in {"CLOSING","CONTRIBUTING","RELATION_ONLY"}: valid = source in {"BODY","LINEAR_NATIVE","ADAPTER"} and transition == ({"CLOSING":"ELIGIBLE","CONTRIBUTING":"INELIGIBLE","RELATION_ONLY":"INELIGIBLE"}[kind])
        elif state == "SUPPRESSED": valid = kind == "SUPPRESSED" and source in {"BRANCH","TITLE"} and transition == "INELIGIBLE"
        elif state in {"AMBIGUOUS","UNAVAILABLE"}: valid = native["state"] in {"PARTIAL","CONTRADICTORY"} and kind == "UNKNOWN" and source in {"BODY","BRANCH","TITLE","LINEAR_NATIVE","ADAPTER"} and transition == "UNKNOWN"
        if not valid or (native["state"] == "PRESENT" and state not in {"PRESENT","SUPPRESSED"}):
            raise ValidationError("INVALID_SNAPSHOT_STATE")
    receipt = observation.get("receipt")
    receipt_keys = {"repository","pr_number","base_sha","head_sha","source_sha","body_sha256","observation_sha256","cutover_receipt_sha256","ruleset_digest","snapshot_digests","producer"}
    if not isinstance(receipt, dict) or set(receipt) != receipt_keys:
        raise ValidationError("TYPE_MISMATCH")
    if receipt.get("repository") != observation["repository"]["name"] or receipt.get("pr_number") != pr["number"] or any(not isinstance(receipt.get(k), str) or not sha_re.fullmatch(receipt[k]) for k in ("base_sha","head_sha","source_sha")) or any(not isinstance(receipt.get(k), str) or not digest_re.fullmatch(receipt[k]) for k in ("body_sha256","observation_sha256","ruleset_digest")):
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
    missing = [f for f in FIELDS if values[f] is None]
    if missing: add("R001", {"missing_fields": missing})
    for f in FIELDS:
        if len(locs[f]) > 1:
            findings.append(_finding(rules, "R002", {"field":f,"locations":[f"BODY:L{x}:{f}" for x in locs[f]],"values":[canonical_digest(values[f] or "")]}, field=f, line=locs[f][1]))
    if defects: add("R003", {"location":"DECLARATION:BLOCK","reason":sorted(set(defects))[0]})
    normalized = dict(values)
    epoch = observation["authoring_epoch"]
    for f in FIELDS:
        v = values[f]
        if v is None: continue
        if v in {"", "TBD", "TODO"} or "|" in v or (v.startswith("<") and v.endswith(">")):
            add("R004", {"field":f,"location":f"BODY:L{locs[f][0]}:{f}","value":text_digest(v)}, f); continue
        if f not in ENUMS:
            continue
        if v in ALIASES:
            if epoch["state"] == "PRESENT" and epoch.get("relation") == "PRE_CUTOVER":
                normalized[f] = ALIASES[v]; add("R021", {"alias":v,"canonical":ALIASES[v],"field":f,"receipt":canonical_digest(epoch)}, f)
            elif epoch["state"] == "PRESENT" and epoch.get("relation") == "AT_OR_POST_CUTOVER":
                add("R020", {"epoch":"AT_OR_POST_CUTOVER","field":f,"value":text_digest(v)}, f)
            else:
                add("R022", {"epoch_state":epoch["state"],"receipt_digest":epoch.get("cutover_receipt_sha256")}, f)
        elif v not in ENUMS[f]:
            if f == "Portfolio-Mode" and v == "untracked_refused": add("R010", {"location":f"BODY:L{locs[f][0]}:{f}","value":text_digest(v)}, f)
            add({"Portfolio-Mode":"R009","Authority":"R011","Completion":"R012"}[f], {"location":f"BODY:L{locs[f][0]}:{f}","value":text_digest(v)}, f)
            add("R020", {"epoch":epoch.get("relation","UNKNOWN"),"field":f,"value":text_digest(v)}, f)
    ws, linear, wave = values["Workstream"], values["Linear"], values["Wave"]
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
    author_state = "LEGACY" if any(x in ALIASES for x in values.values() if isinstance(x,str)) else ("CANONICAL" if canonical else ("MISSING" if missing else "INVALID"))
    classification = manifest["classification"]["mode_to_class"].get(mode, manifest["classification"]["legacy_class"] if author_state == "LEGACY" else "UNKNOWN")
    if canonical and linear == "NONE": add("R029", {"linear":"NONE","portfolio_mode":mode})
    agentos, lsnap, paths, ownership, native = (observation[x] for x in ("agentos","linear","changed_paths","path_ownership","native_linkage"))
    if (mode in {"tracked","creates_workstream"} or (mode == "architecture_candidate" and ws not in {None,"NONE"})) and agentos["state"] != "PRESENT": add("R033", {"snapshot_state":agentos["state"],"workstream":ws or "NONE"})
    if mode == "tracked" and ws == "NONE": add("R031", {"portfolio_mode":mode,"workstream":ws})
    if mode == "maintenance_exception" and ws != "NONE": add("R032", {"portfolio_mode":mode,"workstream":ws or "NONE"})
    if agentos["state"] == "PRESENT" and ws and ws != "NONE" and mode in {"tracked","architecture_candidate"} and ws not in {r.get("key") for r in agentos.get("workstreams",[])}:
        add("R030", {"workstream":ws})
    branch_targets = _issue_ids(observation["pull_request"].get("branch", ""))
    title_targets = _issue_ids(observation["pull_request"].get("title", ""))
    body_targets = sorted({issue for issue, _, _ in body_relationships})
    native_targets = sorted({r.get("issue_id") for r in native.get("relationships", []) if isinstance(r.get("issue_id"), str)})
    target_ids = sorted(set(([linear] if linear and linear != "NONE" else []) + branch_targets + title_targets + body_targets + native_targets))
    roles_by_target: dict[str, list[str]] = {}
    rows_by_target: dict[str, list[dict[str, Any]]] = {}
    if linear and linear != "NONE":
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
                    add("R027", {"declared":linear,"roles":roles_by_target[target],"targets":[target]})
                if target != linear and declared:
                    add("R027", {"declared":linear,"roles":roles_by_target[target],"targets":[target]})
                for r in rows:
                    allowed = manifest["classification"]["mode_to_issue_types"].get(mode,[]) if r.get("target_role") == "DECLARED" else manifest["classification"]["target_role_to_issue_types"].get(r.get("target_role"),[])
                    if r.get("issue_type") not in allowed:
                        add("R028", {"issue_type":r.get("issue_type","UNKNOWN"),"portfolio_mode":mode or "UNKNOWN","target_role":r.get("target_role","UNKNOWN")})
                if target == linear and mode in {"tracked","architecture_candidate"} and ws not in {None,"NONE"} and declared and declared[0].get("workstream_key") != ws:
                    add("R036", {"bound_workstream":declared[0].get("workstream_key"),"declared_workstream":ws,"linear":linear})
                if target == linear and mode == "creates_workstream" and declared and declared[0].get("workstream_key") not in {None, ws}:
                    add("R036", {"bound_workstream":declared[0].get("workstream_key"),"declared_workstream":ws,"linear":linear})
    if linear and linear != "NONE":
        suppressed = {(r.get("issue_id"), r.get("source")) for r in native.get("relationships", []) if r.get("state") == "SUPPRESSED"}
        def competes(target: str, source: str) -> bool:
            return target != linear and (target, source) not in suppressed and "DECLARED" in roles_by_target.get(target, [])
        bad_branch = [x for x in branch_targets if competes(x, "BRANCH")]
        if bad_branch: add("R050", {"branch_targets":bad_branch,"declared":linear})
        competing = sorted({x for x in title_targets if competes(x, "TITLE")} | {x for x in body_targets if competes(x, "BODY")})
        if competing: add("R051", {"body_targets":body_targets,"declared":linear,"title_targets":title_targets})
        declared_targets = sorted({linear} | {x for x in branch_targets if competes(x, "BRANCH")} | {x for x in title_targets if competes(x, "TITLE")} | {x for x in body_targets if competes(x, "BODY")} | {x for x in native_targets if competes(x, "ADAPTER")})
        if len(declared_targets) > 1: add("R039", {"declared":linear,"targets":declared_targets})
    if canonical and tuple([mode,authority,completion]) not in {tuple(x) for x in manifest["authority_completion_allowlist"]}: add("R040", {"authority":authority,"completion":completion,"portfolio_mode":mode})
    if paths["state"] != "PRESENT": add("R043", {"snapshot_state":paths["state"]})
    if ownership["state"] != "PRESENT": add("R042", {"paths":[],"snapshot_state":ownership["state"]})
    elif canonical:
        rs = ownership.get("resolutions",[])
        unowned = [r for r in rs if r.get("resolution") == "UNOWNED"]
        excluded = [r for r in rs if r.get("resolution") == "EXACT" and authority not in r.get("allowed_authorities",[])]
        if unowned: add("R047", {"paths":[text_digest(r.get("path","")) for r in unowned],"resolutions":[canonical_digest(r) for r in unowned]})
        if excluded: add("R041", {"authority":authority,"paths":[text_digest(r.get("path","")) for r in excluded],"resolutions":[canonical_digest(r) for r in excluded]})
        if mode == "maintenance_exception":
            bad = [r for r in rs if r.get("resolution") != "EXACT" or r.get("path_class") != "MAINTENANCE" or r.get("owner_workstream") != "NONE" or "maintenance" not in r.get("allowed_authorities", [])]
            if bad: add("R044", {"authority":authority,"linear":linear or "NONE","paths":[text_digest(r.get("path","")) for r in bad]})
        if mode == "architecture_candidate" and (authority in {"implementation","deploy"} or any(r.get("path_class") in {"IMPLEMENTATION","DEPLOY"} for r in rs)):
            add("R045", {"authority":authority,"paths":[text_digest(r.get("path","")) for r in rs]})
        if mode == "creates_workstream":
            impl = [r for r in rs if r.get("path_class") in {"IMPLEMENTATION","DEPLOY"}]
            if impl: add("R046", {"path_classes":sorted(set(r.get("path_class") for r in impl)),"paths":[text_digest(r.get("path","")) for r in impl]})
    if mode == "creates_workstream":
        if agentos["state"] == "PRESENT" and ws:
            collisions = sorted(r.get("key") for r in agentos.get("workstreams", []) if r.get("key", "").upper() == ws.upper())
            if collisions: add("R038", {"collisions":collisions,"workstream":ws})
        record_name = ws.replace(":", "-") if isinstance(ws, str) else ""
        if paths["state"] == "PRESENT" and ws and not any(r.get("path") == f"agentos/workstreams/{record_name}.md" and r.get("change_type") in {"ADDED","MODIFIED"} for r in paths.get("paths", [])):
            add("R037", {"paths":[text_digest(r.get("path","")) for r in paths.get("paths",[])],"workstream":ws})
    completion_rows: list[dict[str, Any]] = []
    if native["state"] in {"PARTIAL", "UNAVAILABLE"}:
        if linear and linear != "NONE":
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
            records_exception = target == linear and completion == "records-only" and stop_law == "RECORDS_ONLY" and ownership["state"] == "PRESENT" and all(r.get("resolution") == "EXACT" for r in ownership.get("resolutions", []))
            mismatch = (target == linear and completion == "merge-is-done" and effect != "COMPLETION_CAPABLE") or (effect == "COMPLETION_CAPABLE" and ((target != linear) or (completion in {"built-not-proven","proof-required","acceptance-required"}) or (completion == "records-only" and not records_exception)))
            consistency = "INDETERMINATE" if ambiguous or native["state"] != "PRESENT" else ("MISMATCH" if mismatch else "MATCH")
            completion_rows.append({"issue_id":target,"effect":effect,"declared_completion":declared_completion,"stop_law":stop_law,"consistency":consistency})
            if ambiguous:
                add("R055", {"diagnostics":native.get("diagnostics", []),"linear":target,"relationships":[canonical_digest(r) for r in rels]})
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
            records_ok = completion == "records-only" and declared_row and declared_row.get("stop_law") == "RECORDS_ONLY" and ownership["state"] == "PRESENT" and all(r.get("resolution") == "EXACT" for r in ownership.get("resolutions", []))
            if target == linear and kind == "CLOSING" and not records_ok:
                closing.append((line, canonical_digest({"issue":target,"kind":kind})))
        if closing:
            closing.sort(key=lambda x:(x[0], canonical_json(x[1])))
            findings.append(_finding(rules,"R052",{"completion":completion,"linear":linear,"relationships":[x[1] for x in closing]},field="RELATIONSHIP",line=closing[0][0]))
    if linear and linear != "NONE" and lsnap["state"] == "PRESENT":
        declared_rows = [r for r in rows_by_target.get(linear, []) if r.get("target_role") == "DECLARED"]
        if completion == "merge-is-done" and declared_rows and declared_rows[0].get("stop_law") in {"PROOF","ACCEPTANCE"}:
            if not any(f.get("rule_id") == "R053" for f in findings):
                add("R053", {"completion":completion,"linear":linear,"stop_law":declared_rows[0]["stop_law"]})
    if linear and linear != "NONE" and not completion_rows:
        declared_rows = [r for r in lsnap.get("issues", []) if r.get("id") == linear and r.get("target_role") == "DECLARED"] if lsnap["state"] == "PRESENT" else []
        completion_rows.append({"issue_id":linear,"effect":"UNKNOWN","declared_completion":completion,"stop_law":declared_rows[0].get("stop_law") if declared_rows else None,"consistency":"INDETERMINATE"})
    unresolved = sorted(name for name, snap in (("AUTHORING_EPOCH",epoch),("CHANGED_PATHS",paths),("AGENTOS",agentos),("LINEAR",lsnap),("PATH_OWNERSHIP",ownership),("NATIVE_LINKAGE",native)) if snap["state"] in {"PARTIAL","UNAVAILABLE","CONTRADICTORY"})
    findings.sort(key=lambda x:(SEVERITY[x["severity"]],x["code"],x["rule_id"],x["location"],canonical_json(x["evidence"])))
    # deterministic semantic de-duplication
    kept=[]; seen=set()
    for f in findings:
        k=canonical_json(f)
        if k not in seen: kept.append(f); seen.add(k)
    if len(kept) > manifest["limits"]["findings"]:
        raise ValidationError("RESOURCE_LIMIT:findings")
    verdict = "REFUSE_METADATA" if any(f["severity"]=="ERROR" for f in kept) else ("PARTIAL" if any(f["severity"]=="PARTIAL" for f in kept) else ("WARN" if kept else "CONFORMANT"))
    completeness = "UNAVAILABLE" if author_state == "MISSING" else ("DEGRADED" if unresolved or any(f["severity"]=="PARTIAL" for f in kept) else "COMPLETE")
    completion_rows.sort(key=lambda r:(r["issue_id"],r["effect"],r["declared_completion"] or "",r["stop_law"] or "",r["consistency"]))
    semantic = {"ruleset_id":manifest["ruleset_id"],"ruleset_digest":digest(manifest),"enforcement":"REPORT_ONLY","declaration":{"workstream":ws,"linear":linear,"portfolio_mode":mode,"wave":wave,"authority":authority,"completion":completion,"authoring_state":author_state},"classification":classification,"verdict":verdict,"completeness":completeness,"completion_interpretation":completion_rows,"unresolved_observation_classes":unresolved,"findings":kept}
    receipt = observation["receipt"]
    report = {"schema":REPORT_SCHEMA,"semantic":semantic,"semantic_hash":digest(semantic),"receipt":json.loads(canonical_json(receipt)),"human":{"summary":f"{classification}/{verdict}","remediations":sorted(set(f["remediation_code"] for f in kept))}}
    validate_report(report)
    return report
