"""Executable positive/control fixtures for the frozen header rule family."""
from __future__ import annotations
import pytest
from tests.test_pr_linkage_validator import VALID, report, MANIFEST

def ids(body): return {f["rule_id"] for f in report(body)["semantic"]["findings"]}

def contract(rule, body):
    finding = next(f for f in report(body)["semantic"]["findings"] if f["rule_id"] == rule)
    row = next(r for r in MANIFEST["rules"] if r["rule_id"] == rule)
    assert finding["code"] == row["code"]
    assert sorted(finding["evidence"]) == sorted(row["evidence_keys"])
    policy = MANIFEST["finding_contract"]["location_policy_by_rule"][rule]
    assert finding["location"].startswith({"DECLARATION":"DECLARATION:","SNAPSHOT":"SNAPSHOT:","BODY":"BODY:","RECEIPT":"RECEIPT:"}.get(policy["source"], "DECLARATION:"))

@pytest.mark.parametrize(("rule","body"), [
    ("R001", "Workstream: WS:AGENT-OS\nLinear: MAS-28\nPortfolio-Mode: tracked\nWave: MAS28-W1\nAuthority: implementation"),
    ("R002", VALID + "\nWorkstream: WS:AGENT-OS"),
    ("R003", "note\n" + VALID),
    ("R004", VALID.replace("MAS-28", "<MAS-###>", 1)),
    ("R005", VALID.replace("WS:AGENT-OS", "WS:bad")),
    ("R006", VALID.replace("MAS-28", "MAS-0", 1)),
    ("R007", VALID.replace("Wave: MAS28-W1", "Wave: ")),
    ("R008", VALID.replace("Wave: MAS28-W1", "Wave: bad wave")),
    ("R009", VALID.replace("tracked", "bogus")),
    ("R010", VALID.replace("tracked", "untracked_refused")),
    ("R011", VALID.replace("implementation", "bogus")),
    ("R012", VALID.replace("built-not-proven", "bogus")),
])
def test_header_rule_positive_and_canonical_control(rule, body):
    positive, control = ids(body), ids(VALID)
    assert rule in positive and rule not in control
    # Coupled policy rows (for example invalid enum plus R020) are explicitly allowed;
    # the target row must still be the only required delta for this fixture.
    assert rule in positive - control
    contract(rule, body)
