"""Mechanical immutability coverage for every frozen MAS-28 manifest surface."""
import pytest
from tests.test_pr_linkage_validator import MANIFEST
from lib import pr_linkage_validator as validator

RULES = MANIFEST["rules"]

@pytest.mark.parametrize("row", RULES, ids=lambda r: r["rule_id"])
def test_closed_rule_row(row):
    assert set(row) == {"rule_id","version","code","channel","severity","applicability","predicate","evidence_keys","remediation_code"}
    assert row["version"] == 1 and row["channel"] == "SEMANTIC"
    assert sum(x["rule_id"] == row["rule_id"] for x in RULES) == 1

@pytest.mark.parametrize("key,encoding", sorted(MANIFEST["finding_contract"]["evidence_schema_by_key"].items()))
def test_closed_evidence_encoding(key, encoding):
    assert encoding in {"ATOM","ATOM_OR_NULL","ATOM_LIST","LOCATION","LOCATION_LIST","TEXT_DIGEST","TEXT_DIGEST_LIST","CANONICAL_DIGEST","CANONICAL_DIGEST_LIST"}
    assert any(key in row["evidence_keys"] for row in RULES)

@pytest.mark.parametrize("route", MANIFEST["execution_error"]["routes"], ids=lambda r:r["reason_code"])
def test_closed_execution_route(route):
    assert route["exit"] in {2,3}
    assert route["reason_code"] in MANIFEST["execution_error"]["reason_codes"]

def test_evaluator_rule_registry_exactly_matches_manifest():
    """The executable evaluator may not invent or silently drop a frozen rule ID."""
    assert validator.FROZEN_RULE_IDS == {row["rule_id"] for row in RULES}

def test_pure_module_has_no_network_clock_random_or_environment_imports():
    import ast, pathlib
    tree = ast.parse(pathlib.Path(validator.__file__).read_text())
    banned = {"socket", "requests", "urllib", "http", "time", "random", "os", "subprocess"}
    imports = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in (n.names if isinstance(n, ast.Import) else [ast.alias(n.module or "")])}
    assert not (imports & banned)
