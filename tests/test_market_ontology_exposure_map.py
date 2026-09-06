"""RED-first tests for engine.market_ontology.exposure_map (A-F04-W2-1).

All fixtures are in-memory (list[dict]) — no test reads or writes data/, and no test
requires a materialized theme graph store. A fake StoreView is the whole harness.
"""
from __future__ import annotations

import ast
import datetime
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from engine.market_ontology.exposure_map import ShockSpec, compose_exposure_map, to_json

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "contracts" / "market_ontology" / "exposure_map.v1.schema.json"
MODULE_PATH = REPO_ROOT / "engine" / "market_ontology" / "exposure_map.py"


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def edge(edge_id, type_, src, dst, *, valid_from="2026-01-01", valid_to=None,
         belief_time="2026-01-01", computed_at="2026-01-01T00:00:00Z",
         evidence_time="2026-01-01", era="observed", source_class="curated",
         date_provenance="curated_changelog", evidence_refs=None,
         confidence_basis="membership_doc.v1", engine_version="theme_graph.v1"):
    return {
        "edge_id": edge_id, "type": type_, "src": src, "dst": dst,
        "valid_from": valid_from, "valid_to": valid_to, "evidence_time": evidence_time,
        "belief_time": belief_time, "era": era, "source_class": source_class,
        "date_provenance": date_provenance, "evidence_refs": evidence_refs or [],
        "confidence_basis": confidence_basis, "computed_at": computed_at,
        "engine_version": engine_version,
    }


def identity_row(node_id, *, resolution_state="RESOLVED", security_id=None,
                  listing_key=None, issuer_id=None, resolution_asof="2026-01-01",
                  refusal_reason=None):
    return {
        "node_id": node_id, "resolution_state": resolution_state,
        "security_id": security_id, "listing_key": listing_key,
        "issuer_id": issuer_id, "resolution_asof": resolution_asof,
        "refusal_reason": refusal_reason,
    }


class FakeStore:
    def __init__(self, edges, identity=None, meta=None, raise_on_read=False):
        self._edges = edges
        self._identity = identity or []
        self._meta = meta if meta is not None else {"ok": True}
        self._raise = raise_on_read

    def read_edges(self):
        if self._raise:
            raise RuntimeError("store unavailable")
        return self._edges

    def read_identity_resolution(self):
        return self._identity

    def read_meta(self):
        return self._meta

    def read_nodes(self):
        return []


CHAINS = {
    "credit_spreads_refinancing": {
        "chain": "credit_spreads_refinancing",
        "title": {"en": "Credit spreads widen -> refinancing-dependent cohort de-rate",
                   "zh": "信用利差走阔 -> 依赖再融资的板块下修"},
        "tier": "hypothesis",
    }
}


def _chain_loader():
    return CHAINS


def _allow_all(_family):
    return None


def _refuse(family_to_refuse):
    def _assert(family):
        if family == family_to_refuse:
            raise RuntimeError("refused")
    return _assert


def _spec(theme_ids, shock_id="credit_spreads_refinancing"):
    return ShockSpec(shock_id=shock_id, theme_node_ids=tuple(theme_ids), declared_by="test")


def _compose(store, spec, asof="2026-06-01", **kw):
    kw.setdefault("chain_loader", _chain_loader)
    kw.setdefault("assert_allowed", _allow_all)
    return compose_exposure_map(store, spec, asof=asof, **kw)


def test_direct_membership_projection():
    edges = [
        edge("e1", "MEMBER_OF", "co:us:AAA", "ltheme:finviz:x"),
        edge("e2", "MEMBER_OF", "co:us:BBB", "ltheme:finviz:x"),
    ]
    m = _compose(FakeStore(edges), _spec(["ltheme:finviz:x"]))
    theme = m.themes[0]
    assert theme.state == "OK"
    assert [c["company_node_id"] for c in theme.companies] == ["co:us:AAA", "co:us:BBB"]
    for c in theme.companies:
        p = c["paths"][0]
        assert p["path_kind"] == "direct_membership" and p["hops"] == 1
        assert p["edges"][0]["edge_id"] in ("e1", "e2")


def test_basket_bridge_projection():
    edges = [
        edge("e1", "MEMBER_OF", "co:cn:X", "basket:baskets_china_ths:B"),
        edge("e2", "EXPRESSES", "basket:baskets_china_ths:B", "ltheme:ths:C"),
    ]
    m = _compose(FakeStore(edges), _spec(["ltheme:ths:C"]))
    theme = m.themes[0]
    assert theme.state == "OK"
    path = theme.companies[0]["paths"][0]
    assert path["path_kind"] == "basket_bridge"
    assert path["hops"] == 2
    assert path["via_node_id"] == "basket:baskets_china_ths:B"


def test_local_theme_bridge_for_canonical_theme():
    edges = [
        edge("e1", "EXPRESSES", "ltheme:finviz:L", "theme:t1"),
        edge("e2", "MEMBER_OF", "co:us:Z", "ltheme:finviz:L"),
    ]
    m = _compose(FakeStore(edges), _spec(["theme:t1"]))
    theme = m.themes[0]
    assert theme.state == "OK"
    path = theme.companies[0]["paths"][0]
    assert path["path_kind"] == "local_theme_bridge"
    assert path["via_node_id"] == "ltheme:finviz:L"
    # Path C never chains into Path B: no basket_bridge should appear here.
    assert all(p["path_kind"] != "basket_bridge" for c in theme.companies for p in c["paths"])


def test_rights_suppression_emits_typed_null_and_leaks_nothing():
    edges = [edge("e1", "MEMBER_OF", "co:us:SECRET", "ltheme:ths:C")]
    m = _compose(FakeStore(edges), _spec(["ltheme:ths:C"]),
                 assert_allowed=_refuse("ths_concepts"))
    theme = m.themes[0]
    assert theme.state == "RIGHTS_SUPPRESSED"
    assert theme.companies is None
    dumped = json.dumps(to_json(m))
    assert "co:us:SECRET" not in dumped


def test_rights_suppressed_basket_bridge_blocks_its_members():
    edges = [
        edge("e1", "MEMBER_OF", "co:cn:X", "basket:baskets_china_ths:B"),
        edge("e2", "EXPRESSES", "basket:baskets_china_ths:B", "ltheme:ths:C"),
    ]
    m = _compose(FakeStore(edges), _spec(["ltheme:ths:C"]),
                 assert_allowed=_refuse("ths_concepts"))
    theme = m.themes[0]
    # theme's own family (ths_concepts) is also refused here since ltheme:ths: is
    # the same family — so this exercises the theme-level suppression path too.
    assert theme.state == "RIGHTS_SUPPRESSED"
    assert theme.companies is None


def test_asof_belief_filtering():
    edges = [
        edge("e1", "MEMBER_OF", "co:us:A", "ltheme:finviz:x", valid_from="2026-05-01"),
        edge("e2", "MEMBER_OF", "co:us:B", "ltheme:finviz:x", valid_to="2026-01-01"),
        edge("e3", "MEMBER_OF", "co:us:C", "ltheme:finviz:x", valid_to="2026-12-01"),
        edge("e4", "MEMBER_OF", "co:us:D", "ltheme:finviz:x", valid_from="2026-07-01"),
    ]
    m = _compose(FakeStore(edges), _spec(["ltheme:finviz:x"]), asof="2026-06-01")
    companies = {c["company_node_id"] for c in m.themes[0].companies}
    assert companies == {"co:us:A", "co:us:C"}


def test_clock_mismatch_abstention():
    edges = [edge("e1", "MEMBER_OF", "co:us:A", "ltheme:finviz:x", belief_time="2026-09-01")]
    m = _compose(FakeStore(edges), _spec(["ltheme:finviz:x"]), asof="2026-06-01")
    theme = m.themes[0]
    codes = {a["code"] for a in theme.abstentions}
    assert "BELIEF_AFTER_ASOF" in codes
    assert theme.companies is None


def test_historical_belief_recollapse():
    edges = [
        edge("e1", "MEMBER_OF", "co:us:A", "ltheme:finviz:x",
             belief_time="2026-01-01", computed_at="2026-01-01T00:00:00Z", valid_to=None),
        edge("e1", "MEMBER_OF", "co:us:A", "ltheme:finviz:x",
             belief_time="2026-08-01", computed_at="2026-08-01T00:00:00Z", valid_to="2026-07-01"),
    ]
    m_early = _compose(FakeStore(edges), _spec(["ltheme:finviz:x"]), asof="2026-03-01")
    assert m_early.themes[0].state == "OK"
    assert m_early.themes[0].companies[0]["company_node_id"] == "co:us:A"

    m_late = _compose(FakeStore(edges), _spec(["ltheme:finviz:x"]), asof="2026-09-01")
    # The later belief closed the interval (valid_to=2026-07-01), so by 2026-09-01
    # there is truly no edge in view for this theme at all.
    assert m_late.themes[0].state == "NO_THEME_EDGES"


def test_no_membership_yet_null_pre_6809():
    edges = [edge("e1", "EXPRESSES", "ltheme:ths:C", "theme:t1")]
    m = _compose(FakeStore(edges), _spec(["ltheme:ths:C"]))
    theme = m.themes[0]
    assert theme.state == "NO_MEMBERSHIP_YET"
    assert theme.companies is None
    assert theme.unavailable["reason"]["en"] and theme.unavailable["reason"]["zh"]


def test_no_theme_edges_null():
    m = _compose(FakeStore([]), _spec(["ltheme:finviz:nothing"]))
    assert m.themes[0].state == "NO_THEME_EDGES"


def test_identity_unresolved_null():
    m = _compose(FakeStore([]), _spec(["garbage:1"]))
    theme = m.themes[0]
    assert theme.state == "IDENTITY_UNRESOLVED"
    assert theme.theme_node_id == "garbage:1"


def test_shock_unknown_null():
    m = _compose(FakeStore([]), _spec(["ltheme:finviz:x"], shock_id="not_a_real_chain"))
    assert m.unavailable["code"] == "SHOCK_UNKNOWN"
    assert m.themes == ()


def test_store_unavailable_null():
    m = _compose(FakeStore([], raise_on_read=True), _spec(["ltheme:finviz:x"]))
    assert m.unavailable["code"] == "STORE_UNAVAILABLE"
    assert m.themes == ()


def test_identity_collision_abstention():
    edges = [
        edge("e1", "MEMBER_OF", "co:us:A", "ltheme:finviz:x"),
        edge("e2", "MEMBER_OF", "co:us:B", "ltheme:finviz:x"),
    ]
    identity = [
        identity_row("co:us:A", security_id="SEC:1"),
        identity_row("co:us:B", security_id="SEC:1"),
    ]
    m = _compose(FakeStore(edges, identity), _spec(["ltheme:finviz:x"]))
    theme = m.themes[0]
    assert theme.company_count == 2
    assert theme.distinct_security_count == 1
    assert any(a["code"] == "IDENTITY_COLLISION" for a in theme.abstentions)
    for c in theme.companies:
        assert c["identity"]["collision_group"] == "SEC:1"


def test_double_count_abstention():
    edges = [
        edge("e1", "MEMBER_OF", "co:cn:X", "ltheme:ths:C"),
        edge("e2", "MEMBER_OF", "co:cn:X", "basket:baskets_china_ths:B"),
        edge("e3", "EXPRESSES", "basket:baskets_china_ths:B", "ltheme:ths:C"),
    ]
    m = _compose(FakeStore(edges), _spec(["ltheme:ths:C"]))
    theme = m.themes[0]
    assert theme.company_count == 1
    assert len(theme.companies) == 1
    assert len(theme.companies[0]["paths"]) == 2
    kinds = {p["path_kind"] for p in theme.companies[0]["paths"]}
    assert kinds == {"direct_membership", "basket_bridge"}


def test_identity_never_joined_on_symbol():
    edges = [edge("e1", "MEMBER_OF", "co:us:A", "ltheme:finviz:x")]
    identity = [{"node_id": "co:us:OTHER", "resolution_state": "RESOLVED",
                 "security_id": "SEC:9", "listing_key": None, "issuer_id": None,
                 "resolution_asof": "2026-01-01", "refusal_reason": None,
                 "source_native_symbol": "A"}]
    m = _compose(FakeStore(edges, identity), _spec(["ltheme:finviz:x"]))
    company = m.themes[0].companies[0]
    assert company["identity"]["state"] == "NO_RESOLUTION_ROW"
    assert company["identity"]["security_id"] is None


@pytest.mark.parametrize("case", [
    "direct", "basket_bridge", "rights_suppressed", "no_membership", "no_theme_edges",
    "identity_unresolved", "shock_unknown", "store_unavailable", "collision",
])
def test_schema_validation_every_case(case):
    schema = _schema()
    assert schema["$id"] == "https://mastermind-x.com/contracts/market_ontology/exposure_map.v1.schema.json"

    if case == "direct":
        edges = [edge("e1", "MEMBER_OF", "co:us:A", "ltheme:finviz:x")]
        m = _compose(FakeStore(edges), _spec(["ltheme:finviz:x"]))
    elif case == "basket_bridge":
        edges = [
            edge("e1", "MEMBER_OF", "co:cn:X", "basket:baskets_china_ths:B"),
            edge("e2", "EXPRESSES", "basket:baskets_china_ths:B", "ltheme:ths:C"),
            edge("e3", "TRACKS", "etf:KWEB", "basket:baskets_china_ths:B"),
        ]
        m = _compose(FakeStore(edges), _spec(["ltheme:ths:C"]))
    elif case == "rights_suppressed":
        edges = [edge("e1", "MEMBER_OF", "co:us:A", "ltheme:ths:C")]
        m = _compose(FakeStore(edges), _spec(["ltheme:ths:C"]), assert_allowed=_refuse("ths_concepts"))
    elif case == "no_membership":
        edges = [edge("e1", "EXPRESSES", "ltheme:ths:C", "theme:t1")]
        m = _compose(FakeStore(edges), _spec(["ltheme:ths:C"]))
    elif case == "no_theme_edges":
        m = _compose(FakeStore([]), _spec(["ltheme:finviz:nothing"]))
    elif case == "identity_unresolved":
        m = _compose(FakeStore([]), _spec(["garbage:1"]))
    elif case == "shock_unknown":
        m = _compose(FakeStore([]), _spec(["ltheme:finviz:x"], shock_id="nope"))
    elif case == "store_unavailable":
        m = _compose(FakeStore([], raise_on_read=True), _spec(["ltheme:finviz:x"]))
    else:  # collision
        edges = [
            edge("e1", "MEMBER_OF", "co:us:A", "ltheme:finviz:x"),
            edge("e2", "MEMBER_OF", "co:us:B", "ltheme:finviz:x"),
        ]
        identity = [identity_row("co:us:A", security_id="SEC:1"),
                    identity_row("co:us:B", security_id="SEC:1")]
        m = _compose(FakeStore(edges, identity), _spec(["ltheme:finviz:x"]))

    jsonschema.validate(to_json(m), schema)


def test_deterministic_ordering():
    edges = [
        edge("e3", "MEMBER_OF", "co:us:CCC", "ltheme:finviz:x"),
        edge("e1", "MEMBER_OF", "co:us:AAA", "ltheme:finviz:x"),
        edge("e2", "MEMBER_OF", "co:us:BBB", "ltheme:finviz:x"),
    ]
    m1 = _compose(FakeStore(list(edges)), _spec(["ltheme:finviz:x"]))
    m2 = _compose(FakeStore(list(reversed(edges))), _spec(["ltheme:finviz:x"]))
    assert json.dumps(to_json(m1), sort_keys=False) == json.dumps(to_json(m2), sort_keys=False)


_FORBIDDEN_IMPORTS = (
    "engine.prophet", "engine.regime", "engine.axes", "engine.conditions",
    "engine.alerts", "engine.run", "lib.store", "requests", "urllib", "httpx",
    "openai", "anthropic",
)


def test_module_is_a_pure_leaf():
    tree = ast.parse(MODULE_PATH.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(alias.name.startswith(f) for f in _FORBIDDEN_IMPORTS), alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(f) for f in _FORBIDDEN_IMPORTS), node.module
        elif isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            assert name not in ("now", "today"), "no clock call allowed"
            if isinstance(fn, ast.Name) and fn.id == "open":
                pytest.fail("no filesystem write allowed")

    out = subprocess.run(
        ["grep", "-rl", "engine.market_ontology", "engine/prophet", "engine/regime",
         "engine/axes", "engine/conditions", "engine/alerts", "engine/run.py"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert out.stdout.strip() == ""


_FORBIDDEN_KEY_RE = __import__("re").compile(
    r"(score|rank|weight|alpha|signal|conviction|size|target|priced|probability|confidence_pct)",
    __import__("re").IGNORECASE,
)


def _walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_keys(item)


def test_authority_ceiling_keys():
    edges = [
        edge("e1", "MEMBER_OF", "co:us:A", "ltheme:finviz:x"),
        edge("e2", "MEMBER_OF", "co:cn:X", "basket:baskets_china_ths:B"),
        edge("e3", "EXPRESSES", "basket:baskets_china_ths:B", "ltheme:ths:C"),
    ]
    m = _compose(FakeStore(edges), _spec(["ltheme:finviz:x", "ltheme:ths:C"]))
    payload = to_json(m)
    for key in _walk_keys(payload):
        if key == "confidence_basis":
            continue
        assert not _FORBIDDEN_KEY_RE.search(key), key
    assert payload["authority_ceiling"] == "research_display_only"
    assert payload["display_only"] is True


def test_post_6809_fixture_needs_no_code_change():
    # Simulates the state AFTER #6809 lands: a direct co:*->ltheme:ths:* MEMBER_OF
    # edge exists (today only Finviz has this; THS gets it via #6809). No code
    # change to this module should be required for this to work.
    edges = [edge("e1", "MEMBER_OF", "co:cn:300123", "ltheme:ths:C")]
    m = _compose(FakeStore(edges), _spec(["ltheme:ths:C"]))
    theme = m.themes[0]
    assert theme.state == "OK"
    assert theme.companies[0]["paths"][0]["path_kind"] == "direct_membership"
