"""Executable one-mutant/one-control matrix for all frozen MAS-28 rule IDs."""
from __future__ import annotations

import json

import pytest

from lib import pr_linkage_validator as v
from tests.test_pr_linkage_validator import MANIFEST, VALID, observation


def clone(o):
    return json.loads(v.canonical_json(o))


def body(o, **replacements):
    lines = o["pull_request"]["body"].splitlines()
    o["pull_request"]["body"] = "\n".join(replacements.get(line.split(":", 1)[0], line) for line in lines)


def finish(o):
    return v.finalize_receipt(o, MANIFEST)


def mode(o, *, workstream="WS:AGENT-OS", linear="MAS-28", portfolio="tracked", authority="implementation", completion="built-not-proven"):
    body(o, Workstream=f"Workstream: {workstream}", Linear=f"Linear: {linear}", **{"Portfolio-Mode":f"Portfolio-Mode: {portfolio}", "Authority":f"Authority: {authority}", "Completion":f"Completion: {completion}"})


def case(rule):
    o = clone(observation(VALID))
    if rule == "R001": o["pull_request"]["body"] = "\n".join(VALID.splitlines()[:-1])
    elif rule == "R002": o["pull_request"]["body"] += "\nWorkstream: WS:AGENT-OS"
    elif rule == "R003": o["pull_request"]["body"] = "note\n" + VALID
    elif rule == "R004": body(o, Wave="Wave: <WAVE>")
    elif rule == "R005": body(o, Workstream="Workstream: WS:bad")
    elif rule == "R006": body(o, Linear="Linear: MAS-0")
    elif rule == "R007": body(o, Wave="Wave: ")
    elif rule == "R008": body(o, Wave="Wave: invalid wave")
    elif rule == "R009": body(o, **{"Portfolio-Mode":"Portfolio-Mode: invalid"})
    elif rule == "R010": body(o, **{"Portfolio-Mode":"Portfolio-Mode: untracked_refused"})
    elif rule == "R011": body(o, Authority="Authority: invalid")
    elif rule == "R012": body(o, Completion="Completion: invalid")
    elif rule == "R020": body(o, Authority="Authority: runtime")
    elif rule == "R021":
        body(o, Authority="Authority: runtime"); o["authoring_epoch"].update(relation="PRE_CUTOVER", first_strict_pr_number=124, legacy_open_pr_numbers=[123])
    elif rule == "R022": body(o, Authority="Authority: runtime"); o["authoring_epoch"]["state"] = "UNAVAILABLE"; o["authoring_epoch"]["relation"] = "UNKNOWN"; o["authoring_epoch"]["diagnostics"] = ["NO_RECEIPT"]
    elif rule == "R026": o["pull_request"]["title"] = "MAS-99"; o["linear"]["issues"].append({"id":"MAS-99","target_role":"UNKNOWN","project_id":None,"workstream_key":None,"issue_type":"UNKNOWN","stop_law":"UNKNOWN"})
    elif rule == "R027": o["linear"]["issues"][0]["target_role"] = "SECONDARY"
    elif rule == "R028": o["linear"]["issues"][0]["issue_type"] = "UNKNOWN"
    elif rule == "R029": body(o, Linear="Linear: NONE")
    elif rule == "R030": o["agentos"]["workstreams"] = []
    elif rule == "R031": body(o, Workstream="Workstream: NONE")
    elif rule == "R032": mode(o, portfolio="maintenance_exception", authority="maintenance"); o["linear"]["issues"][0]["issue_type"] = "MAINTENANCE"
    elif rule == "R033": o["agentos"]["state"] = "PARTIAL"; o["agentos"]["diagnostics"] = ["STALE"]
    elif rule == "R034": o["linear"]["issues"] = []
    elif rule == "R035": o["linear"]["state"] = "PARTIAL"; o["linear"]["diagnostics"] = ["STALE"]
    elif rule == "R036": o["linear"]["issues"][0]["workstream_key"] = "WS:OTHER"
    elif rule in {"R037","R038","R046"}:
        mode(o, workstream="WS:NEW", linear="MAS-99", portfolio="creates_workstream", authority="records", completion="records-only"); o["linear"]["issues"] = [{"id":"MAS-99","target_role":"DECLARED","project_id":None,"workstream_key":None,"issue_type":"ROOT_RECOVERY","stop_law":"RECORDS_ONLY"}]; o["agentos"]["workstreams"] = ([{"key":"WS:NEW","waves":[]}] if rule == "R038" else [])
        if rule == "R046": o["path_ownership"]["resolutions"] = [{"path":"app/x.py","role":"CURRENT","resolution":"EXACT","owner_workstream":"NONE","path_class":"IMPLEMENTATION","allowed_authorities":["records"]}]
    elif rule == "R039": o["pull_request"]["title"] = "MAS-99"; o["linear"]["issues"].append({"id":"MAS-99","target_role":"DECLARED","project_id":None,"workstream_key":None,"issue_type":"DELIVERY","stop_law":"MERGE"})
    elif rule == "R040": mode(o, authority="records")
    elif rule == "R041": o["path_ownership"]["resolutions"] = [{"path":"x","role":"CURRENT","resolution":"EXACT","owner_workstream":"NONE","path_class":"RECORDS","allowed_authorities":["records"]}]
    elif rule == "R042": o["path_ownership"]["state"] = "PARTIAL"; o["path_ownership"]["diagnostics"] = ["STALE"]
    elif rule == "R043": o["changed_paths"]["state"] = "PARTIAL"; o["changed_paths"]["diagnostics"] = ["STALE"]
    elif rule == "R044": mode(o, workstream="NONE", portfolio="maintenance_exception", authority="maintenance"); o["linear"]["issues"][0]["issue_type"] = "MAINTENANCE"; o["path_ownership"]["resolutions"] = [{"path":"x","role":"CURRENT","resolution":"EXACT","owner_workstream":"NONE","path_class":"IMPLEMENTATION","allowed_authorities":["maintenance"]}]
    elif rule == "R045": mode(o, portfolio="architecture_candidate", authority="records", completion="records-only"); o["linear"]["issues"][0]["issue_type"] = "ARCHITECTURE"; o["path_ownership"]["resolutions"] = [{"path":"x","role":"CURRENT","resolution":"EXACT","owner_workstream":"NONE","path_class":"IMPLEMENTATION","allowed_authorities":["records"]}]
    elif rule == "R047": o["path_ownership"]["resolutions"] = [{"path":"x","role":"CURRENT","resolution":"UNOWNED","owner_workstream":"NONE","path_class":"UNKNOWN","allowed_authorities":[]}]
    elif rule == "R050": o["pull_request"]["branch"] = "mas-99"; o["linear"]["issues"].append({"id":"MAS-99","target_role":"DECLARED","project_id":None,"workstream_key":None,"issue_type":"DELIVERY","stop_law":"MERGE"})
    elif rule == "R051": o["pull_request"]["title"] = "MAS-99"; o["linear"]["issues"].append({"id":"MAS-99","target_role":"DECLARED","project_id":None,"workstream_key":None,"issue_type":"DELIVERY","stop_law":"MERGE"})
    elif rule == "R052": o["pull_request"]["body"] += "\nFixes MAS-28"
    elif rule == "R053": mode(o, completion="merge-is-done"); o["linear"]["issues"][0]["stop_law"] = "PROOF"; o["native_linkage"]["relationships"] = [{"issue_id":"MAS-28","kind":"CLOSING","source":"BODY","state":"PRESENT","completion_transition":"ELIGIBLE"}]
    elif rule == "R054": o["native_linkage"]["state"] = "PARTIAL"; o["native_linkage"]["pagination_complete"] = False; o["native_linkage"]["diagnostics"] = ["STALE"]
    elif rule == "R055": o["native_linkage"]["relationships"] = [{"issue_id":"MAS-28","kind":"CLOSING","source":"BODY","state":"PRESENT","completion_transition":"ELIGIBLE"},{"issue_id":"MAS-28","kind":"CONTRIBUTING","source":"ADAPTER","state":"PRESENT","completion_transition":"INELIGIBLE"}]
    elif rule == "R056": o["native_linkage"]["relationships"] = [{"issue_id":"MAS-28","kind":"CLOSING","source":"BODY","state":"PRESENT","completion_transition":"ELIGIBLE"}]
    elif rule == "R060": o["receipt"]["body_sha256"] = "0" * 64; return o
    elif rule == "R061": o["agentos"]["state"] = "CONTRADICTORY"; o["agentos"]["diagnostics"] = ["CONFLICT"]
    return finish(o)


RULE_IDS = [row["rule_id"] for row in MANIFEST["rules"]]


@pytest.mark.parametrize("rule", RULE_IDS)
def test_every_frozen_rule_has_emitted_mutant_and_paired_clean_control(rule):
    positive = v.analyze(case(rule), MANIFEST)
    target = next(f for f in positive["semantic"]["findings"] if f["rule_id"] == rule)
    row = next(r for r in MANIFEST["rules"] if r["rule_id"] == rule)
    assert (target["rule_id"], target["code"], sorted(target["evidence"])) == (rule, row["code"], sorted(row["evidence_keys"]))
    assert rule not in {f["rule_id"] for f in v.analyze(observation(VALID), MANIFEST)["semantic"]["findings"]}


def test_actual_rulecase_measurement_is_complete(capsys):
    emitted = {f["rule_id"] for rule in RULE_IDS for f in v.analyze(case(rule), MANIFEST)["semantic"]["findings"]}
    missing = sorted(set(RULE_IDS) - emitted)
    print(f"emitted={len(emitted)} missing={missing} paired-control total={len(RULE_IDS)}")
    assert len(emitted) == 46 and missing == []


def test_secondary_and_suppressed_autolinks_are_not_competing_identities():
    o = clone(observation(VALID))
    o["pull_request"]["branch"] = "mas-99"
    o["pull_request"]["title"] = "MAS-99"
    o["linear"]["issues"].append({"id":"MAS-99","target_role":"SECONDARY","project_id":None,"workstream_key":None,"issue_type":"DELIVERY","stop_law":"MERGE"})
    o["native_linkage"]["relationships"] = [{"issue_id":"MAS-99","kind":"SUPPRESSED","source":"BRANCH","state":"SUPPRESSED","completion_transition":"INELIGIBLE"}]
    ids = {f["rule_id"] for f in v.analyze(finish(o), MANIFEST)["semantic"]["findings"]}
    assert not ({"R039", "R050", "R051"} & ids)


def test_secondary_completion_capability_is_reported_and_refused():
    o = clone(observation(VALID))
    o["pull_request"]["title"] = "MAS-99"
    o["linear"]["issues"].append({"id":"MAS-99","target_role":"SECONDARY","project_id":None,"workstream_key":None,"issue_type":"DELIVERY","stop_law":"MERGE"})
    o["native_linkage"]["relationships"] = [{"issue_id":"MAS-99","kind":"CLOSING","source":"ADAPTER","state":"PRESENT","completion_transition":"ELIGIBLE"}]
    r = v.analyze(finish(o), MANIFEST)
    assert any(x["issue_id"] == "MAS-99" and x["effect"] == "COMPLETION_CAPABLE" for x in r["semantic"]["completion_interpretation"])
    assert any(f["rule_id"] == "R056" and f["evidence"]["target"] == "MAS-99" for f in r["semantic"]["findings"])
