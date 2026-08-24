"""Adversarial purity, parser-boundary and non-mutation properties."""
from __future__ import annotations

import ast
import copy
import json

import pytest

from lib import pr_linkage_validator as v
from tests.test_pr_linkage_validator import MANIFEST, VALID, observation


@pytest.mark.parametrize("bad", ["\ufeff" + VALID, VALID.replace("MAS28-W1", "MAS28\u200b-W1"), VALID.replace("MAS28-W1", "MAS28\x00-W1"), VALID.replace("\n", "\r\n").replace("\r\n", "\r", 1)])
def test_body_encoding_boundaries_are_typed(bad):
    with pytest.raises(v.ValidationError, match="INVALID_BODY_ENCODING"):
        v.analyze(observation(bad), MANIFEST)


def test_core_is_referentially_transparent_and_does_not_mutate_inputs():
    o = observation(VALID); m = copy.deepcopy(MANIFEST)
    before_o, before_m = v.canonical_json(o), v.canonical_json(m)
    first, second = v.analyze(o, m), v.analyze(o, m)
    assert v.canonical_json(first) == v.canonical_json(second)
    assert before_o == v.canonical_json(o) and before_m == v.canonical_json(m)


def test_pure_core_import_graph_has_no_ambient_service_or_io_capability():
    tree = ast.parse(open(v.__file__, encoding="utf-8").read())
    banned = {"socket", "requests", "urllib", "http", "time", "datetime", "random", "os", "pathlib", "subprocess", "git", "environ"}
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    names |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not (names & banned)


def test_metamorphic_json_key_order_and_crlf_are_semantically_identical():
    a = observation(VALID); b = json.loads(v.canonical_json(a)); b["pull_request"]["body"] = VALID.replace("\n", "\r\n"); b = v.finalize_receipt(b, MANIFEST)
    assert v.canonical_json(v.analyze(a, MANIFEST)["semantic"]) == v.canonical_json(v.analyze(b, MANIFEST)["semantic"])
