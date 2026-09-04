from __future__ import annotations
from tests.test_pr_linkage_validator import VALID, observation, report, codes
from lib import pr_linkage_validator as validator


def test_each_header_field_mutation_is_detected():
    expected={"Workstream":"WORKSTREAM_ID_INVALID","Linear":"LINEAR_ID_INVALID","Portfolio-Mode":"PORTFOLIO_MODE_INVALID","Wave":"WAVE_INVALID","Authority":"AUTHORITY_INVALID","Completion":"COMPLETION_INVALID"}
    for field, code in expected.items():
        mutant = "bad wave" if field == "Wave" else "INVALID"
        body=VALID.replace(f"{field}: " + next(line.split(": ",1)[1] for line in VALID.splitlines() if line.startswith(field+":")), f"{field}: {mutant}")
        assert code in codes(report(body)), field


def test_rule_manifest_rows_are_closed_and_unique():
    from tests.test_pr_linkage_validator import MANIFEST
    rows=MANIFEST["rules"]
    assert len(rows)==46 and len({r["rule_id"] for r in rows})==46
    for row in rows: assert set(row)=={"rule_id","version","code","channel","severity","applicability","predicate","evidence_keys","remediation_code"}


def test_permutation_and_hash_seed_equivalence():
    a=observation(VALID); b=observation(VALID)
    b["linear"]["issues"] = list(reversed(b["linear"]["issues"]))
    assert validator.canonical_json(validator.analyze(a, __import__('json').load(open('config/pr_linkage_rules.v1.json')))) == validator.canonical_json(validator.analyze(b, __import__('json').load(open('config/pr_linkage_rules.v1.json'))))
