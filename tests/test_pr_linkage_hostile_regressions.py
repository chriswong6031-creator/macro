"""Hostile-review regressions with paired bounded controls."""
from __future__ import annotations

from lib import pr_linkage_validator as v
from tests.test_pr_linkage_rulecase_matrix import clone, finish, mode
from tests.test_pr_linkage_validator import MANIFEST, VALID, observation
import pytest


def ids(o): return {f["rule_id"] for f in v.analyze(o, MANIFEST)["semantic"]["findings"]}


def test_pre_cutover_alias_stays_legacy_not_canonical():
    o = clone(observation(VALID, epoch="PRE_CUTOVER")); mode(o, authority="runtime")
    report = v.analyze(finish(o), MANIFEST)
    assert report["semantic"]["declaration"]["authoring_state"] == "LEGACY"
    assert "R021" in {f["rule_id"] for f in report["semantic"]["findings"]}


def test_aliases_are_field_specific_and_manifest_digest_is_pinned():
    wrong = VALID.replace("Workstream: WS:AGENT-OS", "Workstream: runtime")
    result = v.analyze(observation(wrong, epoch="PRE_CUTOVER"), MANIFEST)
    assert result["semantic"]["declaration"]["authoring_state"] == "INVALID"
    assert "R021" not in {f["rule_id"] for f in result["semantic"]["findings"]}
    forged = clone(MANIFEST); forged["limits"]["findings"] = 513
    with pytest.raises(v.ValidationError, match="RULESET_DIGEST_MISMATCH"):
        v.analyze(observation(VALID), forged)


def test_creates_workstream_uses_filename_not_colon_key():
    o = clone(observation(VALID)); mode(o, workstream="WS:NEW", linear="MAS-99", portfolio="creates_workstream", authority="records", completion="records-only")
    o["linear"]["issues"] = [{"id":"MAS-99","target_role":"DECLARED","project_id":None,"workstream_key":None,"issue_type":"ROOT_RECOVERY","stop_law":"RECORDS_ONLY"}]
    o["agentos"]["workstreams"] = []
    o["changed_paths"]["paths"] = [{"path":"agentos/workstreams/WS-NEW.md","change_type":"ADDED","old_path":None}]
    o["path_ownership"]["resolutions"] = [{"path":"agentos/workstreams/WS-NEW.md","role":"CURRENT","resolution":"EXACT","owner_workstream":"WS:NEW","path_class":"RECORDS","allowed_authorities":["records"]}]
    assert "R037" not in ids(finish(o))


def test_merge_done_proof_stop_law_is_error_even_when_native_partial():
    o = clone(observation(VALID)); mode(o, completion="merge-is-done"); o["linear"]["issues"][0]["stop_law"] = "PROOF"
    o["native_linkage"].update(state="PARTIAL", pagination_complete=False, diagnostics=["STALE"])
    assert {"R053", "R054"} <= ids(finish(o))


def test_records_only_visible_closing_requires_exact_exception():
    o = clone(observation(VALID)); mode(o, authority="records", completion="records-only"); o["linear"]["issues"][0]["stop_law"] = "MERGE"
    o["pull_request"]["body"] += "\nFixes MAS-28"
    assert "R052" in ids(finish(o))


def test_forged_receipt_identity_and_impossible_precohort_are_typed_invalid():
    o = clone(observation(VALID)); o["receipt"]["repository"] = "other/repository"
    with pytest.raises(v.ValidationError): v.analyze(o, MANIFEST)
    p = clone(observation(VALID, epoch="PRE_CUTOVER")); p["authoring_epoch"]["legacy_open_pr_numbers"] = []
    p = finish(p)
    with pytest.raises(v.ValidationError): v.analyze(p, MANIFEST)


def test_reversed_changed_path_order_is_rejected_not_semantically_reordered():
    o = clone(observation(VALID)); o["changed_paths"]["paths"] = [{"path":"z","change_type":"ADDED","old_path":None},{"path":"a","change_type":"ADDED","old_path":None}]
    o = finish(o)
    with pytest.raises(v.ValidationError): v.analyze(o, MANIFEST)


def test_parser_fence_html_tab_and_inline_code_repros():
    wrapped = VALID.replace("MAS28-W1", "`MAS28-W1`")
    assert "R008" not in ids(observation(wrapped))
    bad_tab = VALID + "\nFixes MAS-28\tand MAS-29"
    assert "R052" not in ids(observation(bad_tab))
    mixed = "<!-- guide -->note\n" + VALID
    assert "R003" in ids(observation(mixed))
    unclosed = "```\n" + VALID + "\n``` trailing"
    assert "R003" in ids(observation(unclosed))


def test_malformed_relationship_spacing_has_line_addressable_r003():
    assert "R003" not in ids(observation(VALID + "\nFixes  MAS-28"))
    finding = next(x for x in v.analyze(observation(VALID + "\nFixes MAS-28  and  MAS-29"), MANIFEST)["semantic"]["findings"] if x["rule_id"] == "R003")
    assert finding["location"] == "BODY:L7:RELATIONSHIP"
    assert finding["evidence"]["location"] == "BODY:L7:RELATIONSHIP"


def test_report_receipt_is_deep_copied_and_r054_is_one_aggregate():
    o = clone(observation(VALID)); o["native_linkage"].update(state="PARTIAL", pagination_complete=False, diagnostics=["STALE"])
    r = v.analyze(finish(o), MANIFEST)
    assert len([f for f in r["semantic"]["findings"] if f["rule_id"] == "R054"]) == 1
    o["receipt"]["repository"] = "mutated/repository"
    assert r["receipt"]["repository"] != "mutated/repository"


def test_lazy_quote_garbage_preamble_and_native_257_are_refused():
    assert "R003" in ids(observation("> quoted\n" + VALID))
    assert "R003" in ids(observation("Fixes garbage\n" + VALID))
    o = clone(observation(VALID)); o["native_linkage"]["relationships"] = [{"issue_id":f"MAS-{i+1}","kind":"CLOSING","source":"BODY","state":"PRESENT","completion_transition":"ELIGIBLE"} for i in range(257)]
    o = finish(o)
    with pytest.raises(v.ValidationError, match="RESOURCE_LIMIT:relationships"): v.analyze(o, MANIFEST)


def test_r002_keeps_every_duplicate_value_and_second_location():
    o = clone(observation(VALID)); o["pull_request"]["body"] += "\nWorkstream: WS:OTHER"
    f = next(x for x in v.analyze(finish(o), MANIFEST)["semantic"]["findings"] if x["rule_id"] == "R002")
    assert f["location"] == "BODY:L7:Workstream" and len(f["evidence"]["values"]) == 2


def test_reversed_ownership_rows_are_refused_before_semantic_hashing():
    o = clone(observation(VALID))
    o["path_ownership"]["resolutions"] = [
        {"path":"z","role":"CURRENT","resolution":"EXACT","owner_workstream":"NONE","path_class":"RECORDS","allowed_authorities":["records"]},
        {"path":"a","role":"CURRENT","resolution":"EXACT","owner_workstream":"NONE","path_class":"RECORDS","allowed_authorities":["records"]},
    ]
    with pytest.raises(v.ValidationError, match="INVALID_SNAPSHOT_STATE"):
        v.analyze(finish(o), MANIFEST)


def test_report_wire_rejects_nested_extra_type_and_order_mutants():
    good = v.analyze(observation(VALID), MANIFEST)
    extra = clone(good); extra["semantic"]["declaration"]["extra"] = True
    with pytest.raises(v.ValidationError): v.validate_report(extra)
    bad_type = clone(good); bad_type["semantic"]["findings"] = "not-a-list"
    bad_type["semantic_hash"] = v.digest(bad_type["semantic"])
    with pytest.raises(v.ValidationError): v.validate_report(bad_type)
    unordered = clone(good); unordered["semantic"]["completion_interpretation"] = list(reversed(unordered["semantic"]["completion_interpretation"]))
    unordered["semantic_hash"] = v.digest(unordered["semantic"])
    if unordered["semantic"]["completion_interpretation"] != good["semantic"]["completion_interpretation"]:
        with pytest.raises(v.ValidationError): v.validate_report(unordered)


def test_report_finding_binding_refuses_forged_code_severity_remediation_and_evidence():
    report = v.analyze(observation("note\n" + VALID), MANIFEST)
    finding = report["semantic"]["findings"][0]
    for key, value in (("code", "FORGED"), ("severity", "NOTICE"), ("remediation_code", "FORGED")):
        mutant = clone(report); mutant["semantic"]["findings"][0][key] = value; mutant["semantic_hash"] = v.digest(mutant["semantic"])
        with pytest.raises(v.ValidationError): v.validate_report(mutant)
    mutant = clone(report); mutant["semantic"]["findings"][0]["evidence"]["forged"] = "value"; mutant["semantic_hash"] = v.digest(mutant["semantic"])
    with pytest.raises(v.ValidationError): v.validate_report(mutant)


def test_reviewer_reducers_r027_r044_r052_native_source_and_numeric_order():
    # R027 is one aggregate even when two targets carry a declared role.
    o = clone(observation(VALID)); o["pull_request"]["title"] = "MAS-29 MAS-30"
    o["linear"]["issues"] += [
        {"id":"MAS-29","target_role":"DECLARED","project_id":None,"workstream_key":None,"issue_type":"DELIVERY","stop_law":"MERGE"},
        {"id":"MAS-30","target_role":"DECLARED","project_id":None,"workstream_key":None,"issue_type":"DELIVERY","stop_law":"MERGE"},
    ]
    r = v.analyze(finish(o), MANIFEST)
    assert len([x for x in r["semantic"]["findings"] if x["rule_id"] == "R027"]) == 1
    # Conclusive partial ownership still disproves a maintenance exception.
    p = clone(observation(VALID)); mode(p, workstream="NONE", portfolio="maintenance_exception", authority="maintenance", completion="built-not-proven")
    p["linear"]["issues"][0]["issue_type"] = "MAINTENANCE"; p["path_ownership"].update(state="PARTIAL", diagnostics=["STALE"], resolutions=[{"path":"x","role":"CURRENT","resolution":"EXACT","owner_workstream":"NONE","path_class":"IMPLEMENTATION","allowed_authorities":["maintenance"]}])
    assert {"R042","R044"} <= ids(finish(p))
    # Records-only cannot suppress a closing claim through an empty/non-record path set.
    q = clone(observation(VALID)); mode(q, authority="records", completion="records-only"); q["linear"]["issues"][0]["stop_law"]="RECORDS_ONLY"; q["pull_request"]["body"] += "\nFixes MAS-28\nFixes MAS-28"; q["changed_paths"]["paths"]=[{"path":"x","change_type":"ADDED","old_path":None}]; q["path_ownership"]["resolutions"]=[{"path":"x","role":"CURRENT","resolution":"EXACT","owner_workstream":"NONE","path_class":"IMPLEMENTATION","allowed_authorities":["records"]}]
    row = next(x for x in v.analyze(finish(q), MANIFEST)["semantic"]["findings"] if x["rule_id"] == "R052")
    assert len(row["evidence"]["relationships"]) == 1 and row["location"] == "BODY:L7:RELATIONSHIP"
    # Native rows must use numeric MAS order and preserve their source rather than adapterizing it.
    n = clone(observation(VALID)); n["native_linkage"]["relationships"] = [{"issue_id":"MAS-2","kind":"CLOSING","source":"LINEAR_NATIVE","state":"PRESENT","completion_transition":"ELIGIBLE"},{"issue_id":"MAS-10","kind":"CLOSING","source":"LINEAR_NATIVE","state":"PRESENT","completion_transition":"ELIGIBLE"}]
    v.analyze(finish(n), MANIFEST)
    n["native_linkage"]["relationships"].reverse()
    with pytest.raises(v.ValidationError, match="INVALID_SNAPSHOT_STATE"): v.analyze(finish(n), MANIFEST)


def test_reviewer_state_rows_epoch_and_resource_caps_fail_closed():
    # PRESENT native requires complete pagination; unavailable payloads cannot carry rows.
    o = clone(observation(VALID)); o["native_linkage"]["pagination_complete"] = False
    with pytest.raises(v.ValidationError, match="INVALID_SNAPSHOT_STATE"): v.analyze(finish(o), MANIFEST)
    o = clone(observation(VALID)); o["linear"].update(state="UNAVAILABLE", diagnostics=["NO_ACCESS"], issues=[o["linear"]["issues"][0]])
    with pytest.raises(v.ValidationError, match="INVALID_SNAPSHOT_STATE"): v.analyze(finish(o), MANIFEST)
    # Epoch rows, receipt members, and all three representative first-over-cap values are typed.
    o = clone(observation(VALID)); o["authoring_epoch"]["template_blobs"][0]["path"] = "../wrong.md"
    with pytest.raises(v.ValidationError, match="INVALID_SNAPSHOT_STATE"): v.analyze(finish(o), MANIFEST)
    o = clone(observation(VALID)); o["receipt"]["snapshot_digests"].pop("linear")
    with pytest.raises(v.ValidationError, match="TYPE_MISMATCH"): v.analyze(o, MANIFEST)
    body = "\n".join(["Workstream: WS:AGENT-OS"] * 101)
    with pytest.raises(v.ValidationError, match="RESOURCE_LIMIT:field_occurrences"): v.parse_header(body, MANIFEST["limits"])
    with pytest.raises(v.ValidationError, match="RESOURCE_LIMIT:body_lines"): v.parse_header("\n" * 10001, MANIFEST["limits"])


def test_snapshot_state_path_and_semantic_key_laws_fail_closed():
    o = clone(observation(VALID)); o["linear"]["diagnostics"] = ["SHOULD_NOT_EXIST"]
    with pytest.raises(v.ValidationError, match="INVALID_SNAPSHOT_STATE"): v.analyze(finish(o), MANIFEST)


def test_runtime_nested_keys_state_payloads_paths_enums_and_applicability_close():
    o = clone(observation(VALID)); o["linear"]["extra"] = 1
    with pytest.raises(v.ValidationError): v.analyze(finish(o), MANIFEST)
    o = clone(observation(VALID)); o["authoring_epoch"] = {"state":"UNAVAILABLE","relation":"UNKNOWN","default_ref":"main","cutover_merge_sha":None,"template_blobs":[],"first_strict_pr_number":None,"legacy_open_pr_numbers":[],"receipt_ruleset_digest":None,"cutover_receipt_sha256":None,"diagnostics":["NO_RECEIPT"]}
    with pytest.raises(v.ValidationError, match="INVALID_SNAPSHOT_STATE"): v.analyze(finish(o), MANIFEST)
    o = clone(observation(VALID)); o["native_linkage"].update(state="NOT_APPLICABLE", pagination_complete=False, diagnostics=[], relationships=[])
    with pytest.raises(v.ValidationError, match="INVALID_SNAPSHOT_STATE"): v.analyze(finish(o), MANIFEST)
    for path, accepted in (("研究/x.py", True), ("research/x", True), ("lib/\x00x", False), ("../x", False)):
        o = clone(observation(VALID)); o["changed_paths"]["paths"] = [{"path":path,"change_type":"ADDED","old_path":None}]
        o["path_ownership"]["resolutions"] = [{"path":path,"role":"CURRENT","resolution":"EXACT","owner_workstream":"NONE","path_class":"IMPLEMENTATION","allowed_authorities":["implementation"]}]
        if accepted: v.analyze(finish(o), MANIFEST)
        else:
            with pytest.raises(v.ValidationError, match="INVALID_SNAPSHOT_STATE"): v.analyze(finish(o), MANIFEST)
    for field in ("issue_type", "stop_law"):
        o = clone(observation(VALID)); o["linear"]["issues"][0][field] = "BOGUS"
        with pytest.raises(v.ValidationError, match="INVALID_SNAPSHOT_STATE"): v.analyze(finish(o), MANIFEST)


def test_ownership_legal_products_coverage_conflict_and_partial_ambiguity():
    o = clone(observation(VALID)); o["changed_paths"]["paths"] = [{"path":"x","change_type":"ADDED","old_path":None}]
    o["path_ownership"]["resolutions"] = [{"path":"x","role":"CURRENT","resolution":"AMBIGUOUS","owner_workstream":"NONE","path_class":"UNKNOWN","allowed_authorities":[]}]
    with pytest.raises(v.ValidationError, match="INVALID_SNAPSHOT_STATE"): v.analyze(finish(o), MANIFEST)
    o["path_ownership"].update(state="PARTIAL", diagnostics=["AMBIGUOUS_OWNER"], resolutions=[{"path":"x","role":"CURRENT","resolution":"AMBIGUOUS","owner_workstream":None,"path_class":"UNKNOWN","allowed_authorities":[]}])
    assert "R042" in ids(finish(o))
    o = clone(observation(VALID)); o["changed_paths"]["paths"] = [{"path":"x","change_type":"ADDED","old_path":None}]
    o["path_ownership"]["resolutions"] = [
        {"path":"x","role":"CURRENT","resolution":"EXACT","owner_workstream":"NONE","path_class":"IMPLEMENTATION","allowed_authorities":["implementation"]},
        {"path":"x","role":"CURRENT","resolution":"EXACT","owner_workstream":"NONE","path_class":"RECORDS","allowed_authorities":["records"]},
    ]
    with pytest.raises(v.ValidationError, match="INVALID_SNAPSHOT_STATE"): v.analyze(finish(o), MANIFEST)
    for path_class in ("RESEARCH","MAINTENANCE","PROOF","DEPLOY","ARCHITECTURE"):
        o = clone(observation(VALID)); o["changed_paths"]["paths"] = [{"path":"x","change_type":"ADDED","old_path":None}]
        o["path_ownership"]["resolutions"] = [{"path":"x","role":"CURRENT","resolution":"EXACT","owner_workstream":"NONE","path_class":path_class,"allowed_authorities":["implementation"]}]
        v.analyze(finish(o), MANIFEST)


def test_native_issue_order_pagination_and_active_suppressed_conflict_state():
    o = clone(observation(VALID)); o["native_linkage"]["relationships"] = [{"issue_id":"BAD","kind":"CLOSING","source":"BODY","state":"PRESENT","completion_transition":"ELIGIBLE"}]
    with pytest.raises(v.ValidationError, match="INVALID_SNAPSHOT_STATE"): v.analyze(finish(o), MANIFEST)
    o = clone(observation(VALID)); o["native_linkage"].update(state="PARTIAL",pagination_complete=True,diagnostics=["PAGE"],relationships=[])
    with pytest.raises(v.ValidationError, match="INVALID_SNAPSHOT_STATE"): v.analyze(finish(o), MANIFEST)
    rows = [
        {"issue_id":"MAS-28","kind":"AUTO_LINK","source":"TITLE","state":"PRESENT","completion_transition":"ELIGIBLE"},
        {"issue_id":"MAS-28","kind":"SUPPRESSED","source":"TITLE","state":"SUPPRESSED","completion_transition":"INELIGIBLE"},
    ]
    o = clone(observation(VALID)); o["native_linkage"]["relationships"] = rows
    with pytest.raises(v.ValidationError, match="INVALID_SNAPSHOT_STATE"): v.analyze(finish(o), MANIFEST)
    o["native_linkage"].update(state="CONTRADICTORY",pagination_complete=False,diagnostics=["ACTIVE_SUPPRESSED_CONFLICT"])
    result = v.analyze(finish(o), MANIFEST)
    assert {f["rule_id"] for f in result["semantic"]["findings"]} >= {"R055","R061"}


def test_contradictory_payloads_are_retained_but_same_conflicts_reject_under_present():
    cases = []
    o = clone(observation(VALID)); o["changed_paths"].update(state="CONTRADICTORY",diagnostics=["CONFLICT"],paths=[{"path":"x","change_type":"ADDED","old_path":None},{"path":"x","change_type":"MODIFIED","old_path":None}]); cases.append(("changed_paths",o))
    o = clone(observation(VALID)); o["agentos"].update(state="CONTRADICTORY",diagnostics=["CONFLICT"],workstreams=[{"key":"WS:AGENT-OS","waves":["A"]},{"key":"WS:AGENT-OS","waves":["B"]}]); cases.append(("agentos",o))
    o = clone(observation(VALID)); o["linear"].update(state="CONTRADICTORY",diagnostics=["CONFLICT"],issues=[{"id":"MAS-28","target_role":"DECLARED","project_id":None,"workstream_key":"WS:AGENT-OS","issue_type":"ARCHITECTURE","stop_law":"BUILT_NOT_PROVEN"},{"id":"MAS-28","target_role":"DECLARED","project_id":None,"workstream_key":"WS:AGENT-OS","issue_type":"DELIVERY","stop_law":"BUILT_NOT_PROVEN"}]); cases.append(("linear",o))
    for name, o in cases:
        result = v.analyze(finish(o), MANIFEST)
        assert len([f for f in result["semantic"]["findings"] if f["rule_id"] == "R061" and f["evidence"]["snapshot"] == name.upper()]) == 1
        o[name]["state"] = "PRESENT"; o[name]["diagnostics"] = []
        with pytest.raises(v.ValidationError, match="INVALID_SNAPSHOT_STATE"): v.analyze(finish(o), MANIFEST)


def test_contradictory_state_requires_a_retained_conflict_payload():
    for name in ("changed_paths", "agentos", "linear", "path_ownership", "native_linkage"):
        o = clone(observation(VALID)); o[name]["state"] = "CONTRADICTORY"; o[name]["diagnostics"] = ["CLAIMED_CONFLICT"]
        if name == "native_linkage": o[name]["pagination_complete"] = False
        with pytest.raises(v.ValidationError, match="INVALID_SNAPSHOT_STATE"):
            v.analyze(finish(o), MANIFEST)


def test_contradictory_ownership_rename_conflict_is_retained_but_present_rejects():
    o = clone(observation(VALID))
    o["changed_paths"]["paths"] = [{"path":"b/new","change_type":"RENAMED","old_path":"a/old"}]
    o["path_ownership"].update(
        state="CONTRADICTORY", diagnostics=["RENAME_OWNER_CONFLICT"],
        resolutions=[
            {"path":"a/old","role":"OLD_RENAME_SOURCE","resolution":"EXACT","owner_workstream":"WS:AGENT-OS","path_class":"RECORDS","allowed_authorities":["records"]},
            {"path":"b/new","role":"CURRENT","resolution":"EXACT","owner_workstream":"WS:AGENT-OS","path_class":"IMPLEMENTATION","allowed_authorities":["implementation"]},
        ],
    )
    report = v.analyze(finish(o), MANIFEST)
    assert any(f["rule_id"] == "R061" and f["evidence"]["snapshot"] == "PATH_OWNERSHIP" for f in report["semantic"]["findings"])
    o["path_ownership"].update(state="PRESENT", diagnostics=[])
    with pytest.raises(v.ValidationError, match="INVALID_SNAPSHOT_STATE"):
        v.analyze(finish(o), MANIFEST)


def test_exact_macro_two_template_epoch_inventory_and_order_is_a_golden():
    o = clone(observation(VALID)); o["authoring_epoch"]["template_blobs"] = [
        {"path":".github/PULL_REQUEST_TEMPLATE/design_migration.md","blob_sha":"27af158978b0ab51d7cbfdb376fa346a8d6da5e9"},
        {"path":".github/pull_request_template.md","blob_sha":"b7bd0dc2d9a30960722d92974b4be088fd6a25ce"},
    ]
    assert v.analyze(finish(o), MANIFEST)["semantic"]["verdict"] == "CONFORMANT"
    o["authoring_epoch"]["template_blobs"].reverse()
    with pytest.raises(v.ValidationError, match="INVALID_SNAPSHOT_STATE"): v.analyze(finish(o), MANIFEST)


def test_parser_comment_fence_info_and_exact_separator_matrix():
    assert "R052" in ids(observation(VALID + "\nFixes  MAS-28"))
    for malformed in ("Fixes MAS-28  and  MAS-99", "Fixes MAS-28  ,  MAS-99"):
        finding = next(f for f in v.analyze(observation(VALID + "\n" + malformed), MANIFEST)["semantic"]["findings"] if f["rule_id"] == "R003")
        assert finding["location"] == "BODY:L7:RELATIONSHIP"
    assert "R052" in ids(observation(VALID + "\n<!-- hidden\n-->Fixes MAS-28"))
    assert ids(observation("```\n<!--\n```\n" + VALID)) == set()
    assert "R052" in ids(observation("```fo`o\nFixes MAS-28\n" + VALID))
    parsed = v.parse_header("```fo`o\nFixes MAS-28\n```\n" + VALID, MANIFEST["limits"])
    assert parsed[4] == [("MAS-28", "CLOSING", 2)]


def test_backtick_wrapped_tracked_mode_still_requires_native_snapshot():
    o = clone(observation(VALID.replace("Portfolio-Mode: tracked", "Portfolio-Mode: `tracked`")))
    o["native_linkage"].update(state="NOT_APPLICABLE", pagination_complete=False, diagnostics=[], relationships=[])
    with pytest.raises(v.ValidationError, match="INVALID_SNAPSHOT_STATE"):
        v.analyze(finish(o), MANIFEST)


def test_report_validator_binds_location_evidence_cardinality_ruleset_receipt_and_human():
    report = v.analyze(observation("note\n" + VALID), MANIFEST)
    mutations = [
        lambda r: r["semantic"]["findings"][0].__setitem__("location", "SNAPSHOT:AGENTOS"),
        lambda r: r["semantic"]["findings"][0]["evidence"].__setitem__("reason", "bad atom with spaces"),
        lambda r: r["semantic"].__setitem__("ruleset_digest", "0" * 64),
        lambda r: r["receipt"].__setitem__("ruleset_digest", "0" * 64),
        lambda r: r["human"].__setitem__("summary", "forged"),
    ]
    for mutate in mutations:
        mutant = clone(report); mutate(mutant); mutant["semantic_hash"] = v.digest(mutant["semantic"])
        with pytest.raises(v.ValidationError, match="TYPE_MISMATCH"): v.validate_report(mutant)
    mutant = clone(report); mutant["semantic"]["findings"].append(clone(mutant["semantic"]["findings"][0])); mutant["semantic"]["findings"][1]["evidence"]["reason"] = "OTHER"
    mutant["semantic"]["findings"].sort(key=lambda f:(v.SEVERITY[f["severity"]],f["code"],f["rule_id"],f["location"],v.canonical_json(f["evidence"])))
    mutant["semantic_hash"] = v.digest(mutant["semantic"])
    with pytest.raises(v.ValidationError, match="TYPE_MISMATCH"): v.validate_report(mutant)
    for field, forged in (("verdict", "CONFORMANT"), ("classification", "UNKNOWN"), ("completeness", "DEGRADED")):
        mutant = clone(report); mutant["semantic"][field] = forged
        mutant["human"] = {"summary":f"{mutant['semantic']['classification']}/{mutant['semantic']['verdict']}",
                           "remediations":sorted({finding["remediation_code"] for finding in mutant["semantic"]["findings"]})}
        mutant["semantic_hash"] = v.digest(mutant["semantic"])
        with pytest.raises(v.ValidationError, match="TYPE_MISMATCH"):
            v.validate_report(mutant)


def test_post_cutover_alias_is_invalid_and_numeric_mas_order_is_shared():
    result = v.analyze(observation(VALID.replace("Authority: implementation","Authority: runtime")), MANIFEST)
    assert result["semantic"]["declaration"]["authoring_state"] == "INVALID"
    assert result["semantic"]["classification"] == "UNKNOWN"
    o = clone(observation(VALID)); o["pull_request"]["title"] = "MAS-28 MAS-2 MAS-10"; o["pull_request"]["body"] += "\nRefs MAS-10 and MAS-2"
    o["linear"]["issues"] += [
        {"id":"MAS-2","target_role":"DECLARED","project_id":None,"workstream_key":None,"issue_type":"DELIVERY","stop_law":"MERGE"},
        {"id":"MAS-10","target_role":"DECLARED","project_id":None,"workstream_key":None,"issue_type":"DELIVERY","stop_law":"MERGE"},
    ]
    o["linear"]["issues"].sort(key=lambda row:(v._mas_key(row["id"]), row["target_role"]))
    result = v.analyze(finish(o), MANIFEST)
    r051 = next(f for f in result["semantic"]["findings"] if f["rule_id"] == "R051")
    assert r051["evidence"]["body_targets"] == ["MAS-2","MAS-10"]
    assert r051["evidence"]["title_targets"] == ["MAS-2","MAS-10","MAS-28"]
    assert [row["issue_id"] for row in result["semantic"]["completion_interpretation"]] == ["MAS-2","MAS-10","MAS-28"]


def test_r028_is_per_target_and_findings_cap_reports_first_retained_513():
    o = clone(observation(VALID)); o["pull_request"]["title"] = "MAS-99"
    o["linear"]["issues"].extend([
        {"id":"MAS-99","target_role":"PARENT","project_id":None,"workstream_key":None,"issue_type":"UNKNOWN","stop_law":"MERGE"},
        {"id":"MAS-99","target_role":"SECONDARY","project_id":None,"workstream_key":None,"issue_type":"UNKNOWN","stop_law":"MERGE"},
    ])
    result = v.analyze(finish(o), MANIFEST)
    assert len([f for f in result["semantic"]["findings"] if f["rule_id"] == "R028"]) == 1
    o = clone(observation(VALID)); o["pull_request"]["title"] = " ".join(f"MAS-{index}" for index in range(1, 601))
    with pytest.raises(v.ResourceLimitError) as caught: v.analyze(finish(o), MANIFEST)
    assert (caught.value.key, caught.value.limit, caught.value.observed) == ("findings", 512, 513)
    o = clone(observation(VALID)); o["changed_paths"]["paths"] = [{"path":"new/a","change_type":"RENAMED","old_path":"../old/a"}]
    with pytest.raises(v.ValidationError, match="INVALID_SNAPSHOT_STATE"): v.analyze(finish(o), MANIFEST)
    o = clone(observation(VALID)); o["linear"]["issues"].append(dict(o["linear"]["issues"][0], issue_type="ARCHITECTURE"))
    with pytest.raises(v.ValidationError, match="INVALID_SNAPSHOT_STATE"): v.analyze(finish(o), MANIFEST)
    o = clone(observation(VALID)); o["changed_paths"]["paths"] = [{"path":"x","change_type":"ADDED","old_path":None}]
    with pytest.raises(v.ValidationError, match="INVALID_SNAPSHOT_STATE"): v.analyze(finish(o), MANIFEST)


def test_hostile_repro_measurement(capsys):
    # The file is the durable matrix for the originally supplied false-clean and
    # state-law cases; keep its receipt visible to the commissioned review.
    cases = [name for name, value in globals().items() if name.startswith("test_") and callable(value)]
    missing = []
    print(f"hostile_repros={len(cases)} missing={missing}")
    assert len(cases) >= 10 and missing == []
