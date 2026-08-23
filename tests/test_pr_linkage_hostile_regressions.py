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
