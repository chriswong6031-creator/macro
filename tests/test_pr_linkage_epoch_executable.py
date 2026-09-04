"""Executable compatibility-epoch fixtures for R020--R022."""
from __future__ import annotations
import pytest
from tests.test_pr_linkage_validator import VALID, MANIFEST, observation
from lib import pr_linkage_validator as validator

ALIAS_BODY = VALID.replace("Authority: implementation", "Authority: runtime")

def findings(body, epoch):
    return validator.analyze(observation(body, epoch=epoch), MANIFEST)["semantic"]["findings"]

def check(rule, body, epoch, expected_added):
    positive = findings(body, epoch)
    row = next(x for x in MANIFEST["rules"] if x["rule_id"] == rule)
    target = next(x for x in positive if x["rule_id"] == rule)
    assert (target["rule_id"], target["code"], sorted(target["evidence"])) == (rule, row["code"], sorted(row["evidence_keys"]))
    assert target["location"] == "BODY:L5:Authority"
    control = findings(VALID, "AT_OR_POST_CUTOVER")
    assert {x["rule_id"] for x in positive} - {x["rule_id"] for x in control} == expected_added

def test_r020_post_cutover_alias_is_invalid():
    check("R020", ALIAS_BODY, "AT_OR_POST_CUTOVER", {"R020"})

def test_r021_pre_cutover_alias_is_legacy_notice():
    check("R021", ALIAS_BODY, "PRE_CUTOVER", {"R021"})

def test_r022_unavailable_epoch_refuses_alias_normalization():
    o = observation(ALIAS_BODY)
    o["authoring_epoch"] = {"state":"UNAVAILABLE","relation":"UNKNOWN","default_ref":None,"cutover_merge_sha":None,"template_blobs":[],"first_strict_pr_number":None,"legacy_open_pr_numbers":[],"receipt_ruleset_digest":None,"cutover_receipt_sha256":None,"diagnostics":["NO_RECEIPT"]}
    positive = validator.analyze(o, MANIFEST)["semantic"]["findings"]
    target = next(x for x in positive if x["rule_id"] == "R022")
    row = next(x for x in MANIFEST["rules"] if x["rule_id"] == "R022")
    assert target["code"] == row["code"] and sorted(target["evidence"]) == sorted(row["evidence_keys"])
    assert target["location"] == "BODY:L5:Authority"
