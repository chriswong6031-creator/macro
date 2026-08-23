"""Closed-wire schema and receipt matrix for MAS-28 V1."""
from __future__ import annotations

import json
import itertools
from pathlib import Path

import jsonschema
import pytest

from lib import pr_linkage_validator as validator
from tests.test_pr_linkage_validator import MANIFEST, VALID, observation, report

ROOT = Path(__file__).parents[1]
SCHEMAS = {
    "observation": ROOT / "contracts/pr_linkage/pr_linkage_observation.v1.schema.json",
    "report": ROOT / "contracts/pr_linkage/pr_linkage_report.v1.schema.json",
    "manifest": ROOT / "contracts/pr_linkage/pr_linkage_rule_manifest.v1.schema.json",
    "execution_error": ROOT / "contracts/pr_linkage/pr_linkage_execution_error.v1.schema.json",
}


def load(name):
    return json.loads(SCHEMAS[name].read_text())


def envelope(route):
    measured = route["reason_code"] == "RESOURCE_LIMIT"
    error = {"code": route["error_code"], "component": route["component"], "reason_code": route["reason_code"], "limit": 512 if measured else None, "observed": 513 if measured else None}
    return {"schema": "mastermind.pr_linkage_execution_error.v1", "enforcement": "REPORT_ONLY", "error": error, "execution_error_hash": validator.digest(error), "receipt": {"input_sha256": None, "source_sha": None, "producer": "scripts/pr_linkage_validator.py"}}


@pytest.mark.parametrize("name,value", [
    ("manifest", MANIFEST),
    ("observation", observation(VALID)),
    ("report", report()),
    ("execution_error", envelope(MANIFEST["execution_error"]["routes"][0])),
])
def test_all_four_v1_schemas_accept_canonical_examples(name, value):
    jsonschema.Draft202012Validator(load(name)).validate(value)


@pytest.mark.parametrize("route", MANIFEST["execution_error"]["routes"], ids=lambda r: r["reason_code"])
def test_all_twenty_execution_routes_have_closed_schema_envelopes(route):
    result = envelope(route)
    jsonschema.Draft202012Validator(load("execution_error")).validate(result)
    assert result["execution_error_hash"] == validator.digest(result["error"])


def test_schema_nested_boundary_mutations_are_closed():
    observation_value = observation(VALID)
    observation_value["native_linkage"]["relationships"].append({"issue_id":"MAS-29","kind":"CLOSING","source":"BODY","state":"PRESENT","completion_transition":"ELIGIBLE","extra":True})
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(load("observation")).validate(observation_value)
    error = envelope(MANIFEST["execution_error"]["routes"][0]); error["error"]["extra"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(load("execution_error")).validate(error)
    report_value = report(); report_value["semantic"]["declaration"]["extra"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(load("report")).validate(report_value)


def dict_paths(value, prefix=()):
    if isinstance(value, dict):
        yield prefix
        for key, child in value.items():
            yield from dict_paths(child, prefix + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from dict_paths(child, prefix + (index,))


def locate(value, path):
    for part in path:
        value = value[part]
    return value


@pytest.mark.parametrize("name,value,total", [
    ("observation", observation(VALID), 14),
    ("report", report("note\n" + VALID), 9),
    ("manifest", MANIFEST, 155),
    ("execution_error", envelope(MANIFEST["execution_error"]["routes"][0]), 3),
])
def test_recursive_unknown_key_walk_rejects_every_dictionary_node(name, value, total, capsys):
    validator_ = jsonschema.Draft202012Validator(load(name))
    paths = list(dict_paths(value))
    accepted = []
    for index, path in enumerate(paths):
        mutant = json.loads(validator.canonical_json(value))
        locate(mutant, path)[f"unknown_{index}"] = True
        if validator_.is_valid(mutant):
            accepted.append(path)
    print(f"RECURSIVE {name} accepted={len(accepted)}/{len(paths)}")
    assert len(paths) == total
    assert accepted == []


def test_manifest_exact_leaf_vocabulary_and_order_are_frozen():
    schema = jsonschema.Draft202012Validator(load("manifest"))
    mutations = [
        lambda m: m["parser_contract"].__setitem__("extra", 1),
        lambda m: m["classification"].__setitem__("extra", 1),
        lambda m: m["classification"]["mode_to_class"].__setitem__("tracked", "FORGED"),
        lambda m: m["rules"][0].__setitem__("severity", "NOTICE"),
        lambda m: m["execution_error"]["routes"][0].__setitem__("component", "OUTPUT"),
        lambda m: m["authority_completion_allowlist"][0].__setitem__(1, "deploy"),
    ]
    for mutate in mutations:
        mutant = json.loads(validator.canonical_json(MANIFEST))
        mutate(mutant)
        assert not schema.is_valid(mutant)


def test_schema_state_execution_and_report_cross_bindings_reject_direct_probes():
    observation_schema = jsonschema.Draft202012Validator(load("observation"))
    probes = []
    value = observation(VALID); value["linear"]["diagnostics"] = ["RESIDUE"]; probes.append(value)
    value = observation(VALID); value["native_linkage"]["pagination_complete"] = False; probes.append(value)
    value = observation(VALID); value["linear"].update(state="PARTIAL", diagnostics=[]); probes.append(value)
    value = observation(VALID); value["native_linkage"].update(state="NOT_APPLICABLE", pagination_complete=False, relationships=[], diagnostics=[]); probes.append(value)
    value = observation(VALID); value["linear"]["issues"][0]["issue_type"] = "BOGUS"; probes.append(value)
    assert all(not observation_schema.is_valid(value) for value in probes)

    execution_schema = jsonschema.Draft202012Validator(load("execution_error"))
    route = MANIFEST["execution_error"]["routes"][0]
    for mutate in (
        lambda e: e["error"].__setitem__("component", "OUTPUT"),
        lambda e: e["error"].__setitem__("code", "OUTPUT_WRITE_ERROR"),
        lambda e: e["error"].update(limit=1, observed=2),
    ):
        value = envelope(route); mutate(value)
        assert not execution_schema.is_valid(value)

    report_schema = jsonschema.Draft202012Validator(load("report"))
    base = report("note\n" + VALID)
    mutants = []
    value = json.loads(validator.canonical_json(base)); value["semantic"]["findings"][0]["location"] = "SNAPSHOT:AGENTOS"; mutants.append(value)
    value = json.loads(validator.canonical_json(base)); value["semantic"]["findings"][0]["evidence"]["reason"] = "bad atom with spaces"; mutants.append(value)
    value = json.loads(validator.canonical_json(base)); value["semantic"]["ruleset_digest"] = "0" * 64; mutants.append(value)
    value = json.loads(validator.canonical_json(base)); value["receipt"]["ruleset_digest"] = "0" * 64; mutants.append(value)
    value = json.loads(validator.canonical_json(base)); value["semantic"]["verdict"] = "CONFORMANT"; mutants.append(value)
    value = json.loads(validator.canonical_json(base)); value["semantic"]["classification"] = "UNKNOWN"; mutants.append(value)
    value = json.loads(validator.canonical_json(base)); value["semantic"]["completeness"] = "DEGRADED"; mutants.append(value)
    value = json.loads(validator.canonical_json(base)); value["semantic"]["declaration"]["portfolio_mode"] = "forged"; mutants.append(value)
    value = json.loads(validator.canonical_json(base)); value["human"]["summary"] = "UNKNOWN/REFUSE_METADATA"; mutants.append(value)
    value = json.loads(validator.canonical_json(base)); value["human"]["remediations"] = ["FORGED"]; mutants.append(value)
    value = json.loads(validator.canonical_json(base)); value["semantic"]["findings"].append(json.loads(validator.canonical_json(value["semantic"]["findings"][0]))); value["semantic"]["findings"][1]["evidence"]["reason"] = "OTHER"; mutants.append(value)
    for value in mutants:
        value["semantic"]["findings"].sort(key=lambda finding:(validator.SEVERITY[finding["severity"]], finding["code"], finding["rule_id"], finding["location"], validator.canonical_json(finding["evidence"])))
        value["semantic_hash"] = validator.digest(value["semantic"])
        assert not report_schema.is_valid(value)


def test_ownership_resolution_full_cross_product_matches_runtime_and_schema(capsys):
    schema = jsonschema.Draft202012Validator(load("observation"))
    total = legal_count = 0
    for state, resolution, owner, path_class, authorities in itertools.product(
        ("PRESENT", "PARTIAL"), ("EXACT", "UNOWNED", "AMBIGUOUS"),
        (None, "NONE", "WS:AGENT-OS"), ("UNKNOWN", "IMPLEMENTATION"),
        ([], ["implementation"]),
    ):
        value = observation(VALID)
        value["changed_paths"]["paths"] = [{"path":"x","change_type":"ADDED","old_path":None}]
        value["path_ownership"].update(
            state=state, diagnostics=[] if state == "PRESENT" else ["PARTIAL_OWNER"],
            resolutions=[{"path":"x","role":"CURRENT","resolution":resolution,
                          "owner_workstream":owner,"path_class":path_class,
                          "allowed_authorities":authorities}],
        )
        expected = (
            resolution == "EXACT" and owner is not None and path_class == "IMPLEMENTATION" and authorities == ["implementation"]
            or resolution == "UNOWNED" and owner == "NONE" and path_class == "UNKNOWN" and authorities == []
            or resolution == "AMBIGUOUS" and state == "PARTIAL" and owner is None and path_class == "UNKNOWN" and authorities == []
        )
        try:
            validator._validate_top(value, MANIFEST)
            runtime_valid = True
        except validator.ValidationError:
            runtime_valid = False
        schema_valid = schema.is_valid(value)
        assert runtime_valid == schema_valid == expected, (state, resolution, owner, path_class, authorities)
        total += 1; legal_count += int(expected)
    print(f"ownership_cross_product={total} legal={legal_count}")
    assert total == 72


def test_native_row_full_cross_product_matches_runtime_and_schema(capsys):
    schema = jsonschema.Draft202012Validator(load("observation"))
    total = legal_count = 0
    for outer, row_state, kind, source, transition in itertools.product(
        ("PRESENT", "PARTIAL"), ("PRESENT", "SUPPRESSED", "AMBIGUOUS", "UNAVAILABLE"),
        ("CLOSING", "CONTRIBUTING", "RELATION_ONLY", "AUTO_LINK", "SUPPRESSED", "UNKNOWN"),
        ("BODY", "BRANCH", "TITLE", "LINEAR_NATIVE", "ADAPTER"),
        ("ELIGIBLE", "INELIGIBLE", "UNKNOWN"),
    ):
        value = observation(VALID)
        value["native_linkage"].update(
            state=outer, pagination_complete=outer == "PRESENT",
            diagnostics=[] if outer == "PRESENT" else ["PARTIAL_NATIVE"],
            relationships=[{"issue_id":"MAS-28","kind":kind,"source":source,
                            "state":row_state,"completion_transition":transition}],
        )
        conclusive = (
            row_state == "PRESENT" and kind == "AUTO_LINK" and source in {"BRANCH","TITLE"} and transition in {"ELIGIBLE","INELIGIBLE"}
            or row_state == "PRESENT" and kind in {"CLOSING","CONTRIBUTING","RELATION_ONLY"}
               and source in {"BODY","LINEAR_NATIVE","ADAPTER"}
               and transition == {"CLOSING":"ELIGIBLE","CONTRIBUTING":"INELIGIBLE","RELATION_ONLY":"INELIGIBLE"}[kind]
            or row_state == "SUPPRESSED" and kind == "SUPPRESSED" and source in {"BRANCH","TITLE"} and transition == "INELIGIBLE"
        )
        diagnostic = (outer == "PARTIAL" and row_state in {"AMBIGUOUS","UNAVAILABLE"}
                      and kind == "UNKNOWN" and transition == "UNKNOWN")
        expected = conclusive or diagnostic
        try:
            validator._validate_top(value, MANIFEST)
            runtime_valid = True
        except validator.ValidationError:
            runtime_valid = False
        schema_valid = schema.is_valid(value)
        assert runtime_valid == schema_valid == expected, (outer, row_state, kind, source, transition)
        total += 1; legal_count += int(expected)
    print(f"native_cross_product={total} legal={legal_count}")
    assert (total, legal_count) == (720, 40)


def test_snapshot_state_payload_diagnostic_full_matrix_matches_runtime_and_schema(capsys):
    schema = jsonschema.Draft202012Validator(load("observation"))
    snapshots = ("authoring_epoch", "changed_paths", "agentos", "linear", "path_ownership", "native_linkage")
    states = ("PRESENT", "PARTIAL", "UNAVAILABLE", "NOT_APPLICABLE", "CONTRADICTORY")
    checked = valid_count = 0
    for name, state in itertools.product(snapshots, states):
        value = observation(VALID)
        snap = value[name]
        if name == "authoring_epoch":
            if state == "UNAVAILABLE":
                value[name] = {"state":"UNAVAILABLE","relation":"UNKNOWN","default_ref":None,
                    "cutover_merge_sha":None,"template_blobs":[],"first_strict_pr_number":None,
                    "legacy_open_pr_numbers":[],"receipt_ruleset_digest":None,
                    "cutover_receipt_sha256":None,"diagnostics":["NO_EPOCH"]}
            else:
                snap.update(state=state, relation="UNKNOWN" if state == "CONTRADICTORY" else snap["relation"],
                            diagnostics=[] if state in {"PRESENT","NOT_APPLICABLE"} else ["EPOCH_STATE"])
                if state == "CONTRADICTORY": snap["receipt_ruleset_digest"] = "0" * 64
        else:
            payload = {"changed_paths":"paths", "agentos":"workstreams", "linear":"issues",
                       "path_ownership":"resolutions", "native_linkage":"relationships"}[name]
            snap.update(state=state, diagnostics=[] if state in {"PRESENT","NOT_APPLICABLE"} else ["SNAPSHOT_STATE"])
            if name == "native_linkage": snap["pagination_complete"] = state == "PRESENT"
            if state in {"UNAVAILABLE", "NOT_APPLICABLE"}: snap[payload] = []
            if state == "CONTRADICTORY":
                if name == "changed_paths": snap[payload] = [
                    {"path":"x","change_type":"ADDED","old_path":None},
                    {"path":"x","change_type":"MODIFIED","old_path":None},]
                elif name == "agentos": snap[payload] = [
                    {"key":"WS:AGENT-OS","waves":["A"]}, {"key":"WS:AGENT-OS","waves":["B"]}]
                elif name == "linear": snap[payload] = [
                    {"id":"MAS-28","target_role":"DECLARED","project_id":None,"workstream_key":"WS:AGENT-OS","issue_type":"ARCHITECTURE","stop_law":"BUILT_NOT_PROVEN"},
                    {"id":"MAS-28","target_role":"DECLARED","project_id":None,"workstream_key":"WS:AGENT-OS","issue_type":"DELIVERY","stop_law":"BUILT_NOT_PROVEN"},]
                elif name == "path_ownership": snap[payload] = [
                    {"path":"x","role":"CURRENT","resolution":"EXACT","owner_workstream":"NONE","path_class":"IMPLEMENTATION","allowed_authorities":["implementation"]},
                    {"path":"x","role":"CURRENT","resolution":"EXACT","owner_workstream":"NONE","path_class":"RECORDS","allowed_authorities":["records"]},]
                else: snap[payload] = [
                    {"issue_id":"MAS-28","kind":"AUTO_LINK","source":"TITLE","state":"PRESENT","completion_transition":"ELIGIBLE"},
                    {"issue_id":"MAS-28","kind":"SUPPRESSED","source":"TITLE","state":"SUPPRESSED","completion_transition":"INELIGIBLE"},]
            if name == "native_linkage" and state == "NOT_APPLICABLE":
                value["pull_request"]["body"] = VALID.replace("Portfolio-Mode: tracked", "Portfolio-Mode: architecture_candidate")
        expected = not (name == "authoring_epoch" and state == "NOT_APPLICABLE")
        try:
            validator._validate_top(value, MANIFEST); runtime_valid = True
        except validator.ValidationError:
            runtime_valid = False
        schema_valid = schema.is_valid(value)
        assert runtime_valid == schema_valid == expected, (name, state)
        checked += 1; valid_count += int(expected)
        if expected:
            mutant = json.loads(validator.canonical_json(value))
            mutant[name]["diagnostics"] = ["RESIDUE"] if state in {"PRESENT","NOT_APPLICABLE"} else []
            with pytest.raises(validator.ValidationError): validator._validate_top(mutant, MANIFEST)
            assert not schema.is_valid(mutant), (name, state, "diagnostics")
    print(f"snapshot_state_matrix={checked} valid={valid_count}")
    assert (checked, valid_count) == (30, 29)


def test_receipt_projection_covers_all_ten_frozen_components():
    o = observation(VALID)
    projection = validator.receipt_projection(o, MANIFEST)
    assert list(projection) == ["OBSERVATION", "BODY", "CUTOVER", "RULESET", "AUTHORING_EPOCH", "CHANGED_PATHS", "AGENTOS", "LINEAR", "PATH_OWNERSHIP", "NATIVE_LINKAGE"]
    for component in projection:
        mutant = json.loads(validator.canonical_json(o))
        key = {"OBSERVATION": "observation_sha256", "BODY": "body_sha256", "CUTOVER": "cutover_receipt_sha256", "RULESET": "ruleset_digest"}.get(component)
        if key:
            mutant["receipt"][key] = "0" * 64 if component != "CUTOVER" else "0" * 64
        else:
            mutant["receipt"]["snapshot_digests"][component.lower()] = "0" * 64
        matches = [f for f in validator.analyze(mutant, MANIFEST)["semantic"]["findings"] if f["rule_id"] == "R060" and f["evidence"]["component"] == component]
        assert len(matches) == 1
        assert matches[0]["location"] == "RECEIPT:" + component


def test_observation_schema_retains_known_installed_receipt_digest_mismatch_for_r060():
    value = observation(VALID); value["receipt"]["ruleset_digest"] = "0" * 64
    jsonschema.Draft202012Validator(load("observation")).validate(value)
    report_value = validator.analyze(value, MANIFEST)
    assert any(f["rule_id"] == "R060" and f["evidence"]["component"] == "RULESET"
               for f in report_value["semantic"]["findings"])
    assert report_value["receipt"]["ruleset_digest"] == validator.FROZEN_RULESET_DIGEST


def test_schema_measurement(capsys):
    print(f"schemas={len(SCHEMAS)} rules={len(MANIFEST['rules'])}")
    assert len(SCHEMAS) == 4 and len(MANIFEST["rules"]) == 46
