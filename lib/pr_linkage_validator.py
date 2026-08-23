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
    if "\r" in body.replace("\r\n", "") or body.startswith("\ufeff"):
        defects.append("INVALID_BODY_ENCODING")
    body = body.replace("\r\n", "\n")
    lines = body.split("\n")
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
            if "-->" not in line[line.index("<!--") + 4:]:
                comment = True
            continue
        marker = re.match(r" {0,3}(`{3,}|~{3,})", line)
        if fence:
            if marker and marker.group(1)[0] == fence[0] and len(marker.group(1)) >= fence[1]:
                fence = None
            continue
        if marker:
            fence = (marker.group(1)[0], len(marker.group(1)))
            continue
        if line.startswith(">") or indent >= 4:
            continue
        visible.append((n, line))
    if fence or comment:
        defects.append("UNCLOSED_MARKDOWN")
    return visible, defects


def parse_header(body: str, limits: dict[str, int]) -> tuple[dict[str, str | None], dict[str, list[int]], list[tuple[str, int]], list[str], list[tuple[str, str, int]]]:
    if len(body.encode("utf-8")) > limits["body_bytes"]:
        raise ValidationError("RESOURCE_LIMIT:body_bytes")
    visible, defects = _visible_lines(body)
    if len(body.replace("\r\n", "\n").split("\n")) > limits["body_lines"]:
        raise ValidationError("RESOURCE_LIMIT:body_lines")
    for _, line in visible:
        if len(line.encode("utf-8")) > limits["line_bytes"]:
            raise ValidationError("RESOURCE_LIMIT:line_bytes")
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
    rel = re.compile(r" {0,3}(close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved|complete|completes|completed|implement|implements|implemented|ref|refs|reference|references|part of|contributes to|toward|towards|relates to|related to|skip|ignore) (MAS-[1-9][0-9]{0,8}(?:\s*,\s*MAS-[1-9][0-9]{0,8}|\s+and\s+MAS-[1-9][0-9]{0,8})*)\.?$", re.I | re.ASCII)
    for n, line in visible:
        m = rel.fullmatch(line)
        if m:
            word = m.group(1).lower()
            kind = "CLOSING" if word in {"close","closes","closed","fix","fixes","fixed","resolve","resolves","resolved","complete","completes","completed","implement","implements","implemented"} else ("SUPPRESSED" if word in {"skip","ignore"} else ("RELATION_ONLY" if word in {"relates to","related to"} else "CONTRIBUTING"))
            for issue in _issue_ids(m.group(2)):
                relationships.append((issue, kind, n))
    return values, locs, headers, defects, sorted(set(relationships))


def _rule_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["rule_id"]: r for r in manifest["rules"]}


def _location(rule: str, field: str | None = None, line: int | None = None) -> str:
    if line and field:
        return f"BODY:L{line}:{field}"
    if rule in {"R001", "R039", "R040", "R051"}:
        return "DECLARATION:BLOCK"
    snap = {"R026":"LINEAR","R027":"LINEAR","R028":"LINEAR","R033":"AGENTOS","R034":"LINEAR","R035":"LINEAR","R036":"LINEAR","R037":"CHANGED_PATHS","R038":"AGENTOS","R041":"PATH_OWNERSHIP","R042":"PATH_OWNERSHIP","R043":"CHANGED_PATHS","R044":"PATH_OWNERSHIP","R045":"PATH_OWNERSHIP","R046":"PATH_OWNERSHIP","R047":"PATH_OWNERSHIP","R053":"LINEAR","R054":"NATIVE_LINKAGE","R055":"NATIVE_LINKAGE","R056":"NATIVE_LINKAGE","R061":"AGENTOS"}
    if rule == "R060": return "RECEIPT:OBSERVATION"
    if rule == "R050": return "BRANCH"
    return "SNAPSHOT:" + snap.get(rule, "AGENTOS")


def _finding(rule_map: dict[str, dict[str, Any]], rule: str, evidence: dict[str, Any], *, field: str | None = None, line: int | None = None) -> dict[str, Any]:
    row = rule_map[rule]
    return {"code": row["code"], "rule_id": rule, "severity": row["severity"], "location": _location(rule, field, line), "evidence": {k: evidence[k] for k in sorted(evidence)}, "remediation_code": row["remediation_code"]}


def _validate_top(observation: dict[str, Any], manifest: dict[str, Any]) -> None:
    required = {"schema","ruleset_id","ruleset_digest","repository","pull_request","authoring_epoch","changed_paths","agentos","linear","path_ownership","native_linkage","receipt"}
    if not isinstance(observation, dict): raise ValidationError("TYPE_MISMATCH")
    if set(observation) != required: raise ValidationError("UNKNOWN_KEY" if set(observation)-required else "MISSING_KEY")
    if observation["schema"] != OBS_SCHEMA: raise ValidationError("TYPE_MISMATCH")
    if observation["ruleset_id"] != manifest["ruleset_id"]: raise ValidationError("UNSUPPORTED_RULESET_ID")
    if observation["ruleset_digest"] != digest(manifest): raise ValidationError("RULESET_DIGEST_MISMATCH")
    for name in ("authoring_epoch","changed_paths","agentos","linear","path_ownership","native_linkage"):
        snap = observation[name]
        if not isinstance(snap, dict) or snap.get("state") not in STATE or not isinstance(snap.get("diagnostics"), list):
            raise ValidationError("INVALID_SNAPSHOT_STATE")


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
        if len(locs[f]) > 1: add("R002", {"field":f,"locations":[f"BODY:L{x}:{f}" for x in locs[f]],"values":[text_digest(values[f] or "")]}, f)
    if defects: add("R003", {"location":"DECLARATION:BLOCK","reason":sorted(set(defects))[0]})
    normalized = dict(values)
    epoch = observation["authoring_epoch"]
    for f in ("Portfolio-Mode","Authority","Completion"):
        v = values[f]
        if v is None: continue
        if v in {"", "TBD", "TODO"} or "|" in v or (v.startswith("<") and v.endswith(">")):
            add("R004", {"field":f,"location":f"BODY:L{locs[f][0]}:{f}","value":text_digest(v)}, f); continue
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
    if ws is not None and not re.fullmatch(r"(?:NONE|WS:[A-Z0-9]+(?:-[A-Z0-9]+)*)", ws): add("R005", {"location":f"BODY:L{locs['Workstream'][0]}:Workstream","value":text_digest(ws)}, "Workstream")
    if linear is not None and not re.fullmatch(r"(?:NONE|MAS-[1-9][0-9]{0,8})", linear): add("R006", {"location":f"BODY:L{locs['Linear'][0]}:Linear","value":text_digest(linear)}, "Linear")
    if wave == "": add("R007", {"location":f"BODY:L{locs['Wave'][0]}:Wave"}, "Wave")
    elif wave is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", wave): add("R008", {"location":f"BODY:L{locs['Wave'][0]}:Wave","value":text_digest(wave)}, "Wave")
    mode, authority, completion = normalized["Portfolio-Mode"], normalized["Authority"], normalized["Completion"]
    canonical = mode in ENUMS["Portfolio-Mode"] and authority in ENUMS["Authority"] and completion in ENUMS["Completion"]
    author_state = "CANONICAL" if canonical else ("LEGACY" if any(x in ALIASES for x in values.values() if isinstance(x,str)) else ("MISSING" if missing else "INVALID"))
    classification = manifest["classification"]["mode_to_class"].get(mode, manifest["classification"]["legacy_class"] if author_state == "LEGACY" else "UNKNOWN")
    if canonical and linear == "NONE": add("R029", {"linear":"NONE","portfolio_mode":mode})
    agentos, lsnap, paths, ownership, native = (observation[x] for x in ("agentos","linear","changed_paths","path_ownership","native_linkage"))
    if mode in {"tracked","architecture_candidate","creates_workstream"} and agentos["state"] != "PRESENT": add("R033", {"snapshot_state":agentos["state"],"workstream":ws or "NONE"})
    if linear and linear != "NONE":
        if lsnap["state"] != "PRESENT": add("R035", {"linear":linear,"snapshot_state":lsnap["state"]})
        else:
            rows = [r for r in lsnap.get("issues",[]) if r.get("id") == linear]
            if not rows: add("R034", {"linear":linear})
            elif any(r.get("target_role") == "UNKNOWN" for r in rows): add("R026", {"required_targets":[linear],"target_roles":[r.get("target_role") for r in rows]})
            else:
                declared = [r for r in rows if r.get("target_role") == "DECLARED"]
                if len(declared) != 1: add("R027", {"declared":linear,"roles":sorted(r.get("target_role") for r in rows),"targets":[linear]})
                for r in rows:
                    allowed = manifest["classification"]["mode_to_issue_types"].get(mode,[]) if r.get("target_role") == "DECLARED" else manifest["classification"]["target_role_to_issue_types"].get(r.get("target_role"),[])
                    if r.get("issue_type") not in allowed: add("R028", {"issue_type":r.get("issue_type","UNKNOWN"),"portfolio_mode":mode or "UNKNOWN","target_role":r.get("target_role","UNKNOWN")})
    if canonical and tuple([mode,authority,completion]) not in {tuple(x) for x in manifest["authority_completion_allowlist"]}: add("R040", {"authority":authority,"completion":completion,"portfolio_mode":mode})
    if paths["state"] != "PRESENT": add("R043", {"snapshot_state":paths["state"]})
    if ownership["state"] != "PRESENT": add("R042", {"paths":[],"snapshot_state":ownership["state"]})
    elif canonical:
        rs = ownership.get("resolutions",[])
        unowned = [r for r in rs if r.get("resolution") == "UNOWNED"]
        excluded = [r for r in rs if r.get("resolution") == "EXACT" and authority not in r.get("allowed_authorities",[])]
        if unowned: add("R047", {"paths":[text_digest(r.get("path","")) for r in unowned],"resolutions":[canonical_digest(r) for r in unowned]})
        if excluded: add("R041", {"authority":authority,"paths":[text_digest(r.get("path","")) for r in excluded],"resolutions":[canonical_digest(r) for r in excluded]})
    if native["state"] != "PRESENT": add("R054", {"linear":linear or "NONE","snapshot_state":native["state"]})
    for sname, snap in (("AUTHORING_EPOCH",epoch),("CHANGED_PATHS",paths),("AGENTOS",agentos),("LINEAR",lsnap),("PATH_OWNERSHIP",ownership),("NATIVE_LINKAGE",native)):
        if snap["state"] == "CONTRADICTORY": add("R061", {"diagnostics":snap.get("diagnostics",[]),"snapshot":sname})
    # Visible closing claim is independently material even without an adapter native row.
    if completion in {"built-not-proven","proof-required","acceptance-required"}:
        for target, kind, line in body_relationships:
            if target == linear and kind == "CLOSING":
                findings.append(_finding(rules,"R052",{"completion":completion,"linear":linear,"relationships":[canonical_digest({"issue":target,"kind":kind})]},field="RELATIONSHIP",line=line))
    unresolved = sorted(name for name, snap in (("AUTHORING_EPOCH",epoch),("CHANGED_PATHS",paths),("AGENTOS",agentos),("LINEAR",lsnap),("PATH_OWNERSHIP",ownership),("NATIVE_LINKAGE",native)) if snap["state"] in {"PARTIAL","UNAVAILABLE","CONTRADICTORY"})
    findings.sort(key=lambda x:(SEVERITY[x["severity"]],x["code"],x["rule_id"],x["location"],canonical_json(x["evidence"])))
    # deterministic semantic de-duplication
    kept=[]; seen=set()
    for f in findings:
        k=canonical_json(f)
        if k not in seen: kept.append(f); seen.add(k)
    verdict = "REFUSE_METADATA" if any(f["severity"]=="ERROR" for f in kept) else ("PARTIAL" if any(f["severity"]=="PARTIAL" for f in kept) else ("WARN" if kept else "CONFORMANT"))
    completeness = "UNAVAILABLE" if author_state == "MISSING" else ("DEGRADED" if unresolved or any(f["severity"]=="PARTIAL" for f in kept) else "COMPLETE")
    semantic = {"ruleset_id":manifest["ruleset_id"],"ruleset_digest":digest(manifest),"enforcement":"REPORT_ONLY","declaration":{"workstream":ws,"linear":linear,"portfolio_mode":mode,"wave":wave,"authority":authority,"completion":completion,"authoring_state":author_state},"classification":classification,"verdict":verdict,"completeness":completeness,"completion_interpretation":[],"unresolved_observation_classes":unresolved,"findings":kept}
    receipt = observation["receipt"]
    return {"schema":REPORT_SCHEMA,"semantic":semantic,"semantic_hash":digest(semantic),"receipt":receipt,"human":{"summary":f"{classification}/{verdict}","remediations":sorted(set(f["remediation_code"] for f in kept))}}
