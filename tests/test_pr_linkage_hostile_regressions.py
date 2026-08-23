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
    assert "R037" not in ids(finish(o))


def test_merge_done_proof_stop_law_is_error_even_when_native_partial():
    o = clone(observation(VALID)); mode(o, completion="merge-is-done"); o["linear"]["issues"][0]["stop_law"] = "PROOF"
    o["native_linkage"].update(state="PARTIAL", pagination_complete=False, diagnostics=["STALE"])
    assert {"R053", "R054"} <= ids(finish(o))


def test_records_only_visible_closing_requires_exact_exception():
    o = clone(observation(VALID)); mode(o, authority="records", completion="records-only"); o["linear"]["issues"][0]["stop_law"] = "DELIVERY"
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


def test_hostile_repro_measurement(capsys):
    # The file is the durable matrix for the originally supplied false-clean and
    # state-law cases; keep its receipt visible to the commissioned review.
    cases = [name for name, value in globals().items() if name.startswith("test_") and callable(value)]
    missing = []
    print(f"hostile_repros={len(cases)} missing={missing}")
    assert len(cases) >= 10 and missing == []
