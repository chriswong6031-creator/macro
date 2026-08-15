"""The source-local theme plane — hostile acceptance tests D–M (W3A §5, under §9).

WHAT THESE PROTECT. The local plane's failure modes are all quiet ones, and each test
below is a specific way the plane could look right and be wrong:

* **D** a member leaves ONE subtheme and stays in another — exactly one edge closes. The
  live case exists (the 2026-08-14 vintage does this 26 times); the failure is a plane
  that keys on the ticker instead of (subtheme, ticker) and closes everything.
* **E** a ratified identity break mints the epoch the break says, from the source's own
  tree, with no builder deciding anything.
* **F** the SNDK class: one name in five subthemes keeps five memberships. A plane that
  quietly picks a "primary" label loses four of them and nobody notices.
* **G/H** a local theme with NO canonical mapping survives with its memberships and the
  guard stays green. Null canonical mapping is the lawful steady state, not a defect —
  312 live CN cases and every Finviz subtheme.
* **I** an unseeded concept + a fixture that fails capability.v1 lands `semantic_only` in
  the SIDE-CAR, and no state field anywhere on the node.
* **J** a membership and a contradicting external classification COEXIST; nothing nets.
* **K** as-known-at(T) excludes what was learned at T+5. Bitemporality is only real if
  the belief filter actually removes later knowledge.
* **L** the rights gate refuses unresolved/internal families and passes display ones.
* **M** all FOUR GMI synapse entries carry six literal-false authority booleans.

Plus the amendments: capability re-derives UP when the substrate improves (the
anti-ratchet, §9.3), the materializer's second shrink wall, the adjacent-only vintage
dedupe (an A→B→A revert keeps three vintages and both intervals), and the two canonical
paths agreeing.

Fixture-only: tmp stores, tmp trees, no network, and nothing writes under ``data/``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from engine.theme_graph import (capability, identity, local_sources, materialize,
                                probation, rights, store)
from lib import config
from scripts import check_theme_graph_contracts as guard

ROOT = Path(__file__).resolve().parents[1]

SEED_ASOF = "2026-06-27"
V2_ASOF = "2026-08-14"
V3_ASOF = "2026-09-30"
BUILD_DAY = "2026-08-20"
STAMP = "2026-08-20T00:00:00Z"
XWALK_DATE = "2026-07-09"
CN_SEED = "2021-06-15"
THS_DOC_DATE = "2026-06-30"
CMAP_ASOF = "2026-06-27"

KNOWN_CODE = "900001"      # concept with a curated crosswalk row AND a seeded basket
UNSEEDED_CODE = "900002"   # concept with no basket at all


# ---------------------------------------------------------------------------
# Fixture inputs
# ---------------------------------------------------------------------------

def _write(path: Path, doc: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def _tree(subthemes: dict[str, list[str]], *, theme: str = "Artificial Intelligence",
          names: dict[str, str] | None = None) -> list[dict]:
    """The committed tree shape: [{theme, key, subsectors:[{key, name, members}]}]."""
    names = names or {}
    return [{
        "theme": theme, "key": theme,
        "subsectors": [
            {"key": key, "name": names.get(key, key.title()),
             "description": f"{key} description", "members": list(members)}
            for key, members in subthemes.items()
        ],
    }]


def _seed_doc(subthemes: dict[str, list[str]], *, asof: str = SEED_ASOF) -> dict:
    trees = _tree(subthemes)
    return {"source": "fixture://finviz", "asof": asof,
            "counts": {"themes": len(trees)}, "themes": trees}


def _history(rows: list[tuple[str, dict[str, list[str]]]]) -> str:
    return "".join(
        json.dumps({"asof": asof, "sha256": "fixture", "tree": _tree(subthemes)},
                   ensure_ascii=False) + "\n"
        for asof, subthemes in rows)


def _ths_membership() -> dict:
    return {
        "version": THS_DOC_DATE, "seed_date": CN_SEED,
        "baskets": {
            f"thsc{KNOWN_CODE}": {
                "name": "Test Concept", "name_zh": "测试概念", "created": CN_SEED,
                "etf_proxy": None, "ths_concept": "测试概念",
                "members": [
                    {"ticker": "600001.SS", "added": CN_SEED, "removed": None},
                    {"ticker": "600002.SS", "added": CN_SEED, "removed": None},
                    {"ticker": "600003.SS", "added": CN_SEED, "removed": None},
                    {"ticker": "600004.SS", "added": CN_SEED, "removed": None},
                ],
            },
        },
    }


def _crosswalk() -> dict:
    return {"version": 3, "date": XWALK_DATE, "themes": [{
        "id": "solar", "name_en": "Solar", "name_zh": "太阳能", "foresight_id": "solar",
        "basket_ids": [], "cn_basket_ids": [], "subsector_keys": [],
        "citrini_basket_ids": [], "theme_node_id": "theme:solar",
        "ths_concept_ids": [KNOWN_CODE], "note": "fixture",
    }]}


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A miniature repo: a data dir, a seed beside it, a crosswalk, an empty breaks table.

    The identity-break table is stubbed EMPTY by default so a future ratified break in the
    committed config cannot silently change what these tests assert; test E opts back into
    the real one deliberately.
    """
    root = tmp_path / "repo"
    data = root / "data"
    _write(root / local_sources.SEED_TREE_FILE, _seed_doc({"aicompute": ["AAA", "BBB"]}))
    _write(data / "baskets_china_ths" / "membership.json", _ths_membership())
    _write(data / "baskets_china_ths" / "concept_map.json",
           {"asof": CMAP_ASOF, "map": {"测试概念": KNOWN_CODE, "无篮概念": UNSEEDED_CODE}})
    xwalk = root / "theme_crosswalk.yml"
    xwalk.write_text(yaml.safe_dump(_crosswalk(), allow_unicode=True, sort_keys=False),
                     encoding="utf-8")
    monkeypatch.setattr(identity, "load_breaks", lambda *a, **k: {})
    monkeypatch.setattr(config, "data_dir", lambda: data)
    return {"root": root, "data": data, "xwalk": xwalk}


def _build(world, *, era="reconstruction", belief_time=BUILD_DAY, **kw):
    return materialize.build(era=era, belief_time=belief_time, computed_at=STAMP,
                             data_dir=world["data"], crosswalk_path=world["xwalk"], **kw)


def _set_tree(world, seed: dict[str, list[str]] | None = None,
              history: list[tuple[str, dict[str, list[str]]]] | None = None,
              *, names: dict[str, str] | None = None, asof: str = SEED_ASOF) -> None:
    if seed is not None:
        doc = _seed_doc(seed, asof=asof)
        if names:
            for sub in doc["themes"][0]["subsectors"]:
                sub["name"] = names.get(sub["key"], sub["name"])
        _write(world["root"] / local_sources.SEED_TREE_FILE, doc)
    hist = world["data"] / "themes_heatmap" / "tree_history.jsonl"
    hist.parent.mkdir(parents=True, exist_ok=True)
    hist.write_text(_history(history or []), encoding="utf-8")


def _member_edges(view, dst_prefix="ltheme:finviz:"):
    return [e for e in view.edges
            if e["type"] == "MEMBER_OF" and e["dst"].startswith(dst_prefix)]


def _price_store(world, symbols, *, sub="baskets/ohlcv") -> None:
    d = world["data"] / sub
    d.mkdir(parents=True, exist_ok=True)
    for sym in symbols:
        pd.DataFrame({"Close": [1.0, 2.0]}).to_parquet(d / f"{sym}.parquet", index=False)


# ---------------------------------------------------------------------------
# D — one membership closes, the others do not
# ---------------------------------------------------------------------------

def test_D_a_member_leaving_one_subtheme_closes_exactly_that_edge(world):
    """The live shape: 26 members left one subtheme each in the 2026-08-14 vintage while
    staying in others. A plane keyed on the ticker rather than (subtheme, ticker) would
    close every membership that name has."""
    _set_tree(world,
              {"aicompute": ["AAA", "BBB"], "aicloud": ["AAA", "CCC"]},
              [(V2_ASOF, {"aicompute": ["BBB"], "aicloud": ["AAA", "CCC"]})])
    view = _build(world)
    closed = [e for e in _member_edges(view) if e["valid_to"]]
    assert len(closed) == 1
    assert closed[0]["src"] == "co:us:AAA"
    assert closed[0]["dst"] == "ltheme:finviz:aicompute"
    assert closed[0]["valid_to"] == V2_ASOF, "closes at the first vintage seen WITHOUT it"
    assert closed[0]["valid_from"] == SEED_ASOF

    survivor = next(e for e in _member_edges(view)
                    if e["src"] == "co:us:AAA" and e["dst"] == "ltheme:finviz:aicloud")
    assert survivor["valid_to"] is None
    # The closing row cites the vintage that observed the absence — a closure dated by
    # the observation that produced it, not by an assumption.
    assert len(closed[0]["evidence_refs"]) == 2


def test_D_a_closed_membership_still_resolves_and_the_guard_stays_green(world, tmp_path):
    _set_tree(world, {"aicompute": ["AAA", "BBB"]},
              [(V2_ASOF, {"aicompute": ["BBB"]})])
    view = _build(world)
    root = _materialise(tmp_path / "store_d", view)
    breaches, _ = guard.audit(root, tmp_path / "no_breaks.yml")
    assert breaches == []
    latest = _latest_belief(root)
    assert any(_is_set(r["valid_to"]) for r in latest), "the closure must be findable"


# ---------------------------------------------------------------------------
# E — a ratified identity break, using the REAL committed rows
# ---------------------------------------------------------------------------

def test_E_a_ratified_identity_break_mints_the_epoch_it_ratified(world, monkeypatch):
    """ABX and GOLD are real ratified rows (2026-08-14, both retired Barrick symbols
    reused). The tree is a fixture; the BREAK TABLE is the committed one, because the
    point of the test is that the plane obeys ratifications it did not author."""
    monkeypatch.setattr(identity, "load_breaks",
                        lambda *a, **k: identity._load_breaks(  # noqa: SLF001
                            str(ROOT / identity.BREAKS_FILE)))
    real = identity.load_breaks()
    assert ("us", "ABX") in real and ("us", "GOLD") in real, (
        "fixture premise gone: the committed break rows are what this test rides on")

    _set_tree(world, {"goldminers": ["ABX", "GOLD", "AAA"]})
    view = _build(world)
    minted = {n["node_id"]: n for n in view.nodes if n["kind"] == "company"}
    assert "co:us:ABX#2" in minted and "co:us:GOLD#2" in minted
    assert minted["co:us:ABX#2"]["identity_epoch"] == 2
    assert "co:us:ABX" not in minted, "epoch 1 must not be minted beside its own break"
    assert minted["co:us:AAA"]["identity_epoch"] == 1
    assert {e["src"] for e in _member_edges(view)} == {
        "co:us:ABX#2", "co:us:GOLD#2", "co:us:AAA"}


def test_E_an_unratified_epoch_cannot_be_invented(world):
    """With the break table empty, the same symbols mint at epoch 1. A builder may not
    decide on its own that two listings are different companies."""
    _set_tree(world, {"goldminers": ["ABX", "GOLD"]})
    view = _build(world)
    assert {n["node_id"] for n in view.nodes
            if n["kind"] == "company" and n["market_scope"] == "us"} == {
        "co:us:ABX", "co:us:GOLD"}


# ---------------------------------------------------------------------------
# F — the SNDK class: one name, many subthemes
# ---------------------------------------------------------------------------

def test_F_a_name_in_five_subthemes_keeps_five_memberships(world):
    keys = ["aicompute", "aicloud", "aidata", "aimodels", "hardwarestorage"]
    _set_tree(world, {k: ["SNDK", "AAA"] for k in keys})
    view = _build(world)
    sndk = [e for e in _member_edges(view) if e["src"] == "co:us:SNDK"]
    assert len(sndk) == 5
    assert {e["dst"] for e in sndk} == {f"ltheme:finviz:{k}" for k in keys}
    assert all(e["valid_to"] is None for e in sndk)
    # One company node, five edges — never five variant twins.
    assert len([n for n in view.nodes if n["node_id"].startswith("co:us:SNDK")]) == 1


def test_F_a_dot_dash_variant_resolves_to_the_existing_node_not_a_twin(world):
    """The vendor writes BRK-B where the store may hold BRK.B. Two spellings of one
    listing would split its memberships in half, invisibly."""
    doc = {"version": "2026-08-01", "seed_date": "2023-05-09", "baskets": {"mega": {
        "name": "Mega", "created": "2023-05-09",
        "members": [{"ticker": "BRK.B", "added": "2023-05-09", "removed": None}]}}}
    _write(world["data"] / "baskets" / "membership.json", doc)
    _set_tree(world, {"aicompute": ["BRK-B"]})
    view = _build(world)
    companies = {n["node_id"] for n in view.nodes if n["kind"] == "company"}
    assert "co:us:BRK.B" in companies
    assert "co:us:BRK-B" not in companies, "a variant twin splits one company in two"
    assert {e["src"] for e in _member_edges(view)} == {"co:us:BRK.B"}
    assert view.local_plane["finviz"]["company_resolution"][
        "resolved_dot_dash_variant"] == 1


# ---------------------------------------------------------------------------
# G / H — null canonical mapping is the lawful steady state
# ---------------------------------------------------------------------------

def test_G_a_finviz_node_with_no_canonical_mapping_survives_guard_green(world, tmp_path):
    _set_tree(world, {"aicompute": ["AAA", "BBB"]})
    view = _build(world)
    assert not [e for e in view.edges
                if e["src"].startswith("ltheme:finviz:")], (
        "the Finviz plane mints ZERO ltheme→theme edges — that is the structural proof "
        "that no company→canonical composition path exists through it")
    assert [n for n in view.nodes if n["node_id"] == "ltheme:finviz:aicompute"]
    assert len(_member_edges(view)) == 2
    breaches, _ = guard.audit(_materialise(tmp_path / "store_g", view),
                              tmp_path / "no_breaks.yml")
    assert breaches == []


def test_H_an_unmapped_ths_concept_survives_guard_green(world, tmp_path):
    _set_tree(world, {"aicompute": ["AAA"]})
    view = _build(world)
    unmapped = f"ltheme:ths:{UNSEEDED_CODE}"
    assert [n for n in view.nodes if n["node_id"] == unmapped]
    assert not [e for e in view.edges if e["src"] == unmapped]
    breaches, _ = guard.audit(_materialise(tmp_path / "store_h", view),
                              tmp_path / "no_breaks.yml")
    assert breaches == []


# ---------------------------------------------------------------------------
# I — capability lives in the side-car, never on the node
# ---------------------------------------------------------------------------

def test_I_an_unseeded_concept_is_semantic_only_in_the_sidecar(world):
    _set_tree(world, {"aicompute": ["AAA"]})
    view = _build(world)
    unseeded = f"ltheme:ths:{UNSEEDED_CODE}"
    node = next(n for n in view.nodes if n["node_id"] == unseeded)
    assert set(node) == set(store.NODE_COLUMNS)
    assert "capability" not in node, "capability is a side-car, never a node column"
    assert node["status"] == "canonical"

    row = next(r for r in view.capability if r["node_id"] == unseeded)
    assert row["capability"] == "semantic_only"
    assert "0 live members" in row["capability_basis"]
    assert "capability.v1" in row["capability_basis"]


def test_I_four_members_with_no_price_substrate_are_semantic_only(world):
    """capability.v1 counts members that RESOLVE TO A PRICE FILE, not members. Four
    unpriced names are four names, not a measurable aggregate."""
    _set_tree(world, {"aicompute": ["AAA"]})
    view = _build(world)
    seeded = f"ltheme:ths:{KNOWN_CODE}"
    row = next(r for r in view.capability if r["node_id"] == seeded)
    assert row["capability"] == "semantic_only"
    assert "0/4" in row["capability_basis"]
    assert "basket join" in row["capability_basis"], (
        "the basis must say WHICH membership path answered — a basket join and a direct "
        "source claim are different facts")


def test_capability_re_derives_upward_when_the_substrate_improves(world):
    """The anti-ratchet (§9.3). Same graph, better price coverage, second build: the
    verdict moves UP. On a write-once node column it could never move at all."""
    _set_tree(world, {"aicompute": ["AAA", "BBB", "CCC"]})
    first = _build(world)
    node = "ltheme:finviz:aicompute"
    assert next(r for r in first.capability
                if r["node_id"] == node)["capability"] == "semantic_only"

    _price_store(world, ["AAA", "BBB", "CCC"])
    second = _build(world, belief_time="2026-08-21")
    row = next(r for r in second.capability if r["node_id"] == node)
    assert row["capability"] == "measurement_candidate"
    assert "3/3" in row["capability_basis"]
    assert "data/baskets/ohlcv/" in row["capability_basis"], "the basis names the substrate"
    # And the two derivations coexist in the side-car, newest wins in the view.
    assert not [r for r in second.capability if r["capability"] == "measurable"], (
        "measurable is W3B's verdict; W3A may not mint it by classifying")


def test_capability_needs_three_not_two(world):
    """The definitional minimum is arithmetic: two names are a pair, not a cross-section.
    A boundary test, because an off-by-one here is invisible in aggregate."""
    _set_tree(world, {"aicompute": ["AAA", "BBB", "CCC"]})
    _price_store(world, ["AAA", "BBB"])
    view = _build(world)
    row = next(r for r in view.capability if r["node_id"] == "ltheme:finviz:aicompute")
    assert row["capability"] == "semantic_only"
    assert "2/3" in row["capability_basis"]


def test_the_cn_substrate_path_is_the_one_the_beta_module_consumes(world):
    """§9.10 asked for the CN store to be VERIFIED, not assumed. engine/cn_global_beta is
    a pure compute module — it reads no store at all; its caller
    scripts/c1_cn_global_beta.py::_panel() reads the panel named here. Recorded in code so
    the next wave inherits the finding rather than re-deriving it."""
    assert capability.CN_SUBSTRATE_PANEL == "china_search/closes.parquet"
    assert "c1_cn_global_beta" in capability.CN_SUBSTRATE_OWNER
    panel = ROOT / "data" / capability.CN_SUBSTRATE_PANEL
    if not panel.exists():
        pytest.skip("CN panel not materialised in this checkout")
    import pyarrow.parquet as pq

    names = pq.ParquetFile(panel).schema.names
    assert any(str(c).endswith((".SS", ".SZ")) for c in names), (
        "the panel's columns are A-share symbols — the join key capability.v1 uses")


def test_a_cn_concept_resolves_members_through_the_panel(world):
    """CN members resolve against the wide panel's COLUMNS, not per-ticker files."""
    _set_tree(world, {"aicompute": ["AAA"]})
    panel_dir = world["data"] / "china_search"
    panel_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({sym: [1.0, 2.0] for sym in
                  ("600001.SS", "600002.SS", "600003.SS")}).to_parquet(
        panel_dir / "closes.parquet", index=False)
    view = _build(world)
    row = next(r for r in view.capability if r["node_id"] == f"ltheme:ths:{KNOWN_CODE}")
    assert row["capability"] == "measurement_candidate"
    assert "3/4" in row["capability_basis"]
    assert "china_search/closes.parquet" in row["capability_basis"]


# ---------------------------------------------------------------------------
# J — corroboration coexists, nothing nets
# ---------------------------------------------------------------------------

def test_J_a_contradicting_external_classification_coexists_and_nets_nothing(world,
                                                                            tmp_path):
    """A provider saying "not in this theme" does not delete a membership. Both rows
    survive, the edge keeps resolving, and a consumer that wants one answer has to say
    which receipt it trusts."""
    _set_tree(world, {"aicompute": ["AAA"]})
    view = _build(world)
    counter = {
        "evidence_id": "ev:externalcounter1", "kind": "external_classification",
        "published_at": "2026-08-19", "effective_at": None,
        "source_ref": "fixture://provider/classification.json",
        "licensing_internal_ok": True, "licensing_display_ok": False,
        "licensing_redistribution_ok": False, "retention": None, "computed_at": STAMP,
        "provider": "fixture_provider", "claim_type": "membership",
    }
    root = _materialise(tmp_path / "store_j", view, extra_evidence=[counter])
    breaches, _ = guard.audit(root, tmp_path / "no_breaks.yml")
    assert breaches == []

    evidence = pd.read_parquet(root / "evidence.parquet")
    assert len(evidence[evidence["kind"] == "external_classification"]) == 1
    membership = next(e for e in _member_edges(view))
    assert membership["valid_to"] is None, "a counter-claim closes nothing"
    assert "ev:externalcounter1" not in membership["evidence_refs"]

    schema = json.loads((ROOT / "contracts" / "theme_graph" /
                         "evidence.v1.schema.json").read_text(encoding="utf-8"))
    import jsonschema

    jsonschema.validate(counter, schema)


def test_W3A_mints_zero_external_classification_rows(world):
    """The class ships EMPTY: the contract exists so the first external row cannot arrive
    without one, not because anything ingested a provider this wave."""
    _set_tree(world, {"aicompute": ["AAA"]})
    view = _build(world)
    assert not [e for e in view.evidence if e["kind"] == "external_classification"]
    assert all(e["provider"] is None and e["claim_type"] is None for e in view.evidence)


# ---------------------------------------------------------------------------
# K — as-known-at(T)
# ---------------------------------------------------------------------------

def test_K_as_known_at_T_excludes_a_membership_learned_at_T_plus_5(world, tmp_path):
    """Bitemporality is only real if the belief filter removes later knowledge. The
    membership is VALID from the vintage date; it was BELIEVED five days after T, and an
    as-of-T answer must not see it."""
    _set_tree(world, {"aicompute": ["AAA"]})
    early = _build(world, belief_time="2026-08-15")
    _set_tree(world, {"aicompute": ["AAA", "LATE"]})
    late = _build(world, belief_time="2026-08-20")

    root = _materialise(tmp_path / "store_k", early)
    all_rows = pd.concat([pd.read_parquet(root / "edges.parquet"),
                          pd.DataFrame(late.edges).reindex(
                              columns=list(store.EDGE_COLUMNS))], ignore_index=True)
    all_rows.to_parquet(root / "edges.parquet", index=False)

    T = "2026-08-15"
    as_known = all_rows[all_rows["belief_time"] <= T]
    assert not (as_known["src"] == "co:us:LATE").any(), (
        "a membership learned at T+5 must be invisible to an as-known-at(T) read")
    assert (all_rows["src"] == "co:us:LATE").any(), "…and present without the filter"
    # The later row's valid_from predates T: validity and belief are different clocks,
    # which is the entire point of storing both.
    late_row = all_rows[all_rows["src"] == "co:us:LATE"].iloc[0]
    assert late_row["valid_from"] <= T < late_row["belief_time"]


# ---------------------------------------------------------------------------
# L — the rights gate
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cls", ["unresolved", "internal_only"])
def test_L_the_rights_gate_refuses_a_family_that_may_not_be_emitted(tmp_path, cls):
    reg = tmp_path / "sources.yml"
    reg.write_text(yaml.safe_dump({"version": 1, "families": {
        "vendor_x": {"rights_class": cls, "auth_class": "keyless_public"}}}),
        encoding="utf-8")
    with pytest.raises(rights.RightsRefusal, match="public emission refused"):
        rights.assert_public_emission_allowed("vendor_x", path=reg)
    assert rights.emission_allowed("vendor_x", path=reg) is False
    # …and the derived mint-time booleans say the same thing.
    assert rights.licensing_for_family("vendor_x", path=reg) == (True, False, False)


@pytest.mark.parametrize("cls,auth,expected", [
    ("derived_display_ok", "keyless_public", (True, True, False)),
    ("direct_display_ok", "house", (True, True, True)),
])
def test_L_the_rights_gate_passes_the_display_classes(tmp_path, cls, auth, expected):
    reg = tmp_path / "sources.yml"
    reg.write_text(yaml.safe_dump({"version": 1, "families": {
        "vendor_y": {"rights_class": cls, "auth_class": auth}}}), encoding="utf-8")
    rights.assert_public_emission_allowed("vendor_y", path=reg)      # must not raise
    assert rights.licensing_for_family("vendor_y", path=reg) == expected


def test_L_an_unregistered_family_fails_closed(tmp_path):
    reg = tmp_path / "sources.yml"
    reg.write_text(yaml.safe_dump({"version": 1, "families": {}}), encoding="utf-8")
    with pytest.raises(rights.RightsRefusal, match="no row in"):
        rights.rights_class("nobody_wrote_this_down", path=reg)
    with pytest.raises(rights.RightsRefusal):
        rights.assert_public_emission_allowed("nobody_wrote_this_down", path=reg)


def test_L_both_live_vendor_families_are_registered_and_refuse_today(world):
    """The live posture, read from the committed registry: both vendor families exist as
    ROWS (so nothing fails closed by accident) and both refuse emission while unresolved.
    Asserted through the gate, not against a hard-coded class, so an operator resolving a
    family updates one file and not this test."""
    for family in ("finviz_themes", "ths_concepts"):
        cls = rights.rights_class(family)
        assert cls in rights.RIGHTS_CLASSES
        assert rights.emission_allowed(family) == (cls in rights.EMISSION_OK)
    assert "mastermind_curated" in rights.known_families()


def test_L_the_guard_fails_closed_on_an_unregistered_source_family(world, tmp_path):
    _set_tree(world, {"aicompute": ["AAA"]})
    view = _build(world)
    nodes = [dict(n) for n in view.nodes]
    target = next(n for n in nodes if n["node_id"] == "ltheme:finviz:aicompute")
    meta = json.loads(target["source_meta"])
    meta["rights_family"] = "family_nobody_reviewed"
    target["source_meta"] = json.dumps(meta, ensure_ascii=False, sort_keys=True)
    root = _materialise(tmp_path / "store_l", view, nodes=nodes)
    breaches, _ = guard.audit(root, tmp_path / "no_breaks.yml")
    assert any("family_nobody_reviewed" in b and "fails CLOSED" in b for b in breaches)


def test_the_guard_refuses_a_basket_id_in_the_finviz_namespace(world, tmp_path):
    """F18 closed structurally: the suite exists for company identity only."""
    _set_tree(world, {"aicompute": ["AAA"]})
    view = _build(world)
    nodes = [dict(n) for n in view.nodes]
    nodes.append({**nodes[0], "node_id": "basket:finviz_themes:aicompute",
                  "kind": "basket", "source_meta": None})
    root = _materialise(tmp_path / "store_ns", view, nodes=nodes)
    breaches, _ = guard.audit(root, tmp_path / "no_breaks.yml")
    assert any("finviz_themes namespace" in b for b in breaches)


def test_a_mint_time_licensing_snapshot_that_disagrees_only_warns(world, tmp_path):
    """History is a record, not a mistake to be edited: an append-only row minted under
    an older rights class produces a NOTICE naming it, never a breach."""
    _set_tree(world, {"aicompute": ["AAA"]})
    view = _build(world)
    evidence = [dict(e) for e in view.evidence]
    stale = next(e for e in evidence
                 if str(e["source_ref"]).startswith("finviz_themes/"))
    stale["licensing_display_ok"] = True     # what LICENSE_VENDOR used to mint
    root = _materialise(tmp_path / "store_rights_warn", view, evidence=evidence)
    breaches, notices = guard.audit(root, tmp_path / "no_breaks.yml")
    assert breaches == []
    assert any("mint-time licensing" in n for n in notices)


# ---------------------------------------------------------------------------
# M — the synapse authority pin
# ---------------------------------------------------------------------------

def test_M_all_four_gmi_synapse_entries_carry_six_false_authority_booleans():
    reg = yaml.safe_load((ROOT / "config" / "synapse.yml").read_text(encoding="utf-8"))
    entries = ["theme-graph-nodes", "theme-graph-edges", "theme-graph-evidence",
               "theme-graph-capability"]
    for name in entries:
        art = reg["artifacts"][name]
        assert art["owner_program"] == "gmi-theme-graph"
        assert art["tier"] == "display"
        assert art["weights"] == "none"
        assert art["scored_path_surfaces"] == []
        authority = art["authority"]
        assert set(authority) == {"can_rank", "can_size", "can_gate",
                                  "can_originate_signal", "can_add_candidates",
                                  "can_escalate"}
        for key, value in authority.items():
            assert value is False, f"{name}.{key} is not literal false"


def test_M_the_capability_sidecar_is_registered_with_its_contract():
    reg = yaml.safe_load((ROOT / "config" / "synapse.yml").read_text(encoding="utf-8"))
    art = reg["artifacts"]["theme-graph-capability"]
    assert art["path"] == "data/theme_graph/capability.parquet"
    assert art["producer"] == "scripts/build_theme_graph.py"
    assert art["schema"] == "theme_graph.capability.v1"
    assert (ROOT / "contracts" / "theme_graph" / "capability.v1.schema.json").exists()


# ---------------------------------------------------------------------------
# The vintage ladder
# ---------------------------------------------------------------------------

def test_adjacent_identical_vintages_dedupe_but_a_revert_keeps_all_three(world):
    """A→B→A. Collapsing every identical vintage would erase the revert into one
    unbroken interval — precisely the history the ladder exists to keep."""
    _set_tree(world, {"aicompute": ["AAA", "BBB"]},
              [(V2_ASOF, {"aicompute": ["AAA"]}),
               (V3_ASOF, {"aicompute": ["AAA", "BBB"]})])
    view = _build(world)
    assert view.local_plane["finviz"]["vintages"] == [SEED_ASOF, V2_ASOF, V3_ASOF]

    bbb = sorted([e for e in _member_edges(view) if e["src"] == "co:us:BBB"],
                 key=lambda e: e["valid_from"])
    assert len(bbb) == 2, "closure and re-open are two intervals, not one edge edited"
    assert (bbb[0]["valid_from"], bbb[0]["valid_to"]) == (SEED_ASOF, V2_ASOF)
    assert (bbb[1]["valid_from"], bbb[1]["valid_to"]) == (V3_ASOF, None)
    assert bbb[0]["edge_id"] != bbb[1]["edge_id"]


def test_an_adjacent_identical_vintage_is_dropped(world):
    """The live case: the 2026-07-05 tape row is byte-identical to the 2026-06-27 seed,
    so the ladder holds ONE vintage and every membership opens at the seed date."""
    _set_tree(world, {"aicompute": ["AAA"]},
              [("2026-07-05", {"aicompute": ["AAA"]})])
    view = _build(world)
    plane = view.local_plane["finviz"]
    assert plane["vintages"] == [SEED_ASOF]
    assert plane["dropped_adjacent_duplicates"] == ["2026-07-05"]
    assert {e["valid_from"] for e in _member_edges(view)} == {SEED_ASOF}


def test_a_ladder_orders_by_asof_not_by_file_order(world):
    """The tape is appended to; nothing guarantees it is sorted. An out-of-order ladder
    would date every interval by whichever line happened to come first."""
    _set_tree(world, {"aicompute": ["AAA"]},
              [(V3_ASOF, {"aicompute": ["AAA", "CCC"]}),
               (V2_ASOF, {"aicompute": ["AAA", "BBB"]})])
    view = _build(world)
    assert view.local_plane["finviz"]["vintages"] == [SEED_ASOF, V2_ASOF, V3_ASOF]
    bbb = next(e for e in _member_edges(view) if e["src"] == "co:us:BBB")
    assert (bbb["valid_from"], bbb["valid_to"]) == (V2_ASOF, V3_ASOF)


def test_a_vintage_older_than_the_build_is_reconstruction_not_observation(world):
    """era says how the row was PRODUCED. A seven-week-old vintage ingested tonight is
    reconstructed history whatever mode the run is in."""
    _set_tree(world, {"aicompute": ["AAA"]})
    view = _build(world, era="observed")
    assert {e["era"] for e in _member_edges(view)} == {"reconstruction"}
    same_day = _build(world, era="observed", belief_time=SEED_ASOF)
    assert {e["era"] for e in _member_edges(same_day)} == {"observed"}


def test_the_labels_are_mint_time_snapshots(world):
    """Node rows are keep-first, so a vendor rename changes no bytes. Test C's original
    'label update only' phrasing is impossible by construction — this asserts what
    actually happens instead."""
    _set_tree(world, {"aicompute": ["AAA"]}, names={"aicompute": "Compute"})
    first = _build(world)
    node = next(n for n in first.nodes if n["node_id"] == "ltheme:finviz:aicompute")
    assert node["name_en"] == "Compute"
    assert json.loads(node["source_meta"])["source_label"] == "Compute"

    _set_tree(world, {"aicompute": ["AAA"]}, names={"aicompute": "Compute & Silicon"})
    second = _build(world)
    renamed = next(n for n in second.nodes if n["node_id"] == "ltheme:finviz:aicompute")
    assert renamed["node_id"] == node["node_id"], "the id is stable across a rename"
    assert renamed["name_en"] == "Compute & Silicon", (
        "the recomputed VIEW sees the new label; the stored ROW keeps the first one — "
        "that half is asserted in the store test below")


def test_the_store_keeps_the_first_label_not_the_rename(world, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path / "store_root")
    _set_tree(world, {"aicompute": ["AAA"]}, names={"aicompute": "Compute"})
    store.write_nodes(_build(world).nodes, lane="nightly")
    _set_tree(world, {"aicompute": ["AAA"]}, names={"aicompute": "Renamed"})
    store.write_nodes(_build(world).nodes, lane="nightly")
    rows = store.read_nodes()
    row = rows[rows["node_id"] == "ltheme:finviz:aicompute"].iloc[0]
    assert row["name_en"] == "Compute", "keep-first: the graph is a join spine, not the "\
                                        "label authority"


def test_source_meta_carries_the_parent_without_minting_a_hierarchy(world):
    _set_tree(world, {"aicompute": ["AAA"]})
    view = _build(world)
    meta = json.loads(next(n for n in view.nodes
                           if n["node_id"] == "ltheme:finviz:aicompute")["source_meta"])
    assert meta["source_family"] == "finviz_themes"
    assert meta["grain"] == "finviz_subtheme"
    assert meta["rights_family"] == "finviz_themes"
    assert meta["parent_source_label"] == "Artificial Intelligence"
    # No refresh receipt in this fixture → the layer is UNKNOWN. None, never the theme's
    # enumeration ordinal — the ordinal happened to be 0 here too, which is exactly how
    # the original wrong-value bug passed this test (diff-review F1).
    assert meta["supergroup_index"] is None
    assert meta["key_aliases"] == []
    # No node for the parent theme, and no PARENT_OF edge: hierarchy is a later wave's.
    assert not [n for n in view.nodes
                if n["node_id"] == "ltheme:finviz:Artificial Intelligence"]
    assert not [e for e in view.edges if e["type"] == "PARENT_OF"]


def test_a_zh_concept_name_never_enters_an_id(world):
    _set_tree(world, {"aicompute": ["AAA"]})
    view = _build(world)
    ths = [n for n in view.nodes if n["node_id"].startswith("ltheme:ths:")]
    assert ths
    for node in ths:
        assert identity.LOCAL_THEME_ID_RE.match(node["node_id"])
        assert node["node_id"].split(":")[2].isdigit()
        assert node["name_zh"], "the zh label rides name_zh, where it belongs"
    with pytest.raises(ValueError, match="does not match"):
        identity.local_theme_node_id("ths", "测试概念")


# ---------------------------------------------------------------------------
# The join law + the two paths agreeing
# ---------------------------------------------------------------------------

def test_the_two_canonical_paths_agree_over_the_shared_crosswalk_rows(world, tmp_path):
    _set_tree(world, {"aicompute": ["AAA"]})
    view = _build(world)
    basket = f"basket:baskets_china_ths:thsc{KNOWN_CODE}"
    concept = f"ltheme:ths:{KNOWN_CODE}"
    expresses = [e for e in view.edges if e["type"] == "EXPRESSES"]
    assert {"theme:solar"} == {e["dst"] for e in expresses
                               if e["src"] == basket and e["dst"].startswith("theme:")}
    assert {"theme:solar"} == {e["dst"] for e in expresses if e["src"] == concept}
    assert {concept} == {e["dst"] for e in expresses
                         if e["src"] == basket and e["dst"].startswith("ltheme:")}
    breaches, _ = guard.audit(_materialise(tmp_path / "store_join", view),
                              tmp_path / "no_breaks.yml")
    assert breaches == []


def test_the_guard_catches_two_paths_that_disagree(world, tmp_path):
    """The negative control: a concept resolving to a different theme than the basket
    expressing it must breach, or the agreement check proves nothing."""
    _set_tree(world, {"aicompute": ["AAA"]})
    view = _build(world)
    nodes = [dict(n) for n in view.nodes]
    nodes.append({**nodes[0], "node_id": "theme:other", "kind": "theme",
                  "market_scope": "global", "source_meta": None})
    edges = [dict(e) for e in view.edges]
    concept = f"ltheme:ths:{KNOWN_CODE}"
    rogue = next(e for e in edges
                 if e["src"] == concept and e["dst"].startswith("theme:"))
    rogue["dst"] = "theme:other"
    rogue["edge_id"] = materialize.edge_id_for("EXPRESSES", concept, "theme:other",
                                               rogue["valid_from"])
    root = _materialise(tmp_path / "store_disagree", view, nodes=nodes, edges=edges)
    breaches, _ = guard.audit(root, tmp_path / "no_breaks.yml")
    assert any("vocabulary resolution" in b for b in breaches)


def test_a_mapping_that_moved_is_not_a_disagreement_with_itself(world, tmp_path):
    """The append-only trap: a crosswalk mapping that legitimately MOVED leaves both rows
    on disk. Checked against the full history, a correct history reads as a breach — so
    the agreement check runs on the latest-belief LIVE view."""
    _set_tree(world, {"aicompute": ["AAA"]})
    view = _build(world)
    nodes = [dict(n) for n in view.nodes]
    nodes.append({**nodes[0], "node_id": "theme:old", "kind": "theme",
                  "market_scope": "global", "source_meta": None})
    concept = f"ltheme:ths:{KNOWN_CODE}"
    basket = f"basket:baskets_china_ths:thsc{KNOWN_CODE}"
    edges = [dict(e) for e in view.edges]
    superseded = []
    for src in (concept, basket):
        row = dict(next(e for e in edges
                        if e["src"] == src and e["dst"].startswith("theme:")))
        row.update({"dst": "theme:old", "belief_time": "2026-01-01",
                    "valid_to": "2026-07-09",
                    "edge_id": materialize.edge_id_for("EXPRESSES", src, "theme:old",
                                                       "2026-01-01"),
                    "valid_from": "2026-01-01"})
        superseded.append(row)
    root = _materialise(tmp_path / "store_moved", view, nodes=nodes,
                        edges=[*edges, *superseded])
    breaches, _ = guard.audit(root, tmp_path / "no_breaks.yml")
    assert breaches == [], "a closed older mapping is history, not a contradiction"


def test_the_guard_refuses_an_edge_pairing_that_is_not_in_the_table(world, tmp_path):
    """A company→theme MEMBER_OF is the derived edge W1b refused. If one ever appears,
    it appears as DATA, so the guard checks the pairing rather than trusting the writer."""
    _set_tree(world, {"aicompute": ["AAA"]})
    view = _build(world)
    edges = [dict(e) for e in view.edges]
    smuggled = dict(edges[0])
    smuggled.update({"type": "MEMBER_OF", "src": "co:us:AAA", "dst": "theme:solar",
                     "edge_id": "member_of:co:us:AAA->theme:solar@2026-06-27"})
    root = _materialise(tmp_path / "store_pairing", view, edges=[*edges, smuggled])
    breaches, _ = guard.audit(root, tmp_path / "no_breaks.yml")
    assert any("not a pairing this type may carry" in b for b in breaches)


# ---------------------------------------------------------------------------
# The materializer's second shrink wall
# ---------------------------------------------------------------------------

def test_the_second_wall_refuses_a_mass_closure_without_the_flag(world):
    """A hand-edited tree never passes through the refresh contract's interlocks, so the
    write path carries its own wall."""
    _set_tree(world, {"aicompute": ["AAA", "BBB", "CCC", "DDD"]})
    stored = pd.DataFrame(_build(world).edges).reindex(columns=list(store.EDGE_COLUMNS))

    _set_tree(world, {"aicompute": ["AAA", "BBB", "CCC", "DDD"]},
              [(V2_ASOF, {"aicompute": ["AAA"]})])
    shrunk = _build(world).edges
    refusals = materialize.source_shrink_refusals(shrunk, stored)
    assert any("finviz_themes" in r for r in refusals)
    assert any("--allow-source-shrink finviz_themes" in r for r in refusals)
    assert materialize.source_shrink_refusals(
        shrunk, stored, allow={"finviz_themes"}) == []


def test_the_second_wall_lets_ordinary_churn_through(world):
    """1 of 12 closing is 8.3% — under the 10% wall (§9.2: observed genuine churn is
    ~1.1%/7wk; the wall exists for the 11.5% distributed truncation, not for churn).
    A wall that fires on normal churn gets disabled, which is worse than not having one."""
    members = [f"M{i:02d}" for i in range(12)]
    _set_tree(world, {"aicompute": members})
    stored = pd.DataFrame(_build(world).edges).reindex(columns=list(store.EDGE_COLUMNS))
    _set_tree(world, {"aicompute": members}, [(V2_ASOF, {"aicompute": members[1:]})])
    assert materialize.source_shrink_refusals(_build(world).edges, stored) == []


def test_the_second_wall_boundary_sits_at_ten_percent(world):
    """Boundary pin for MAX_SOURCE_SHRINK=0.10 (diff-review F2): 2/20 = 10.0% passes
    (strictly-greater wall), 3/20 = 15% refuses — and the 25% constant this replaced
    would have let the canonical 11.5% truncation straight through."""
    members = [f"M{i:02d}" for i in range(20)]
    _set_tree(world, {"aicompute": members})
    stored = pd.DataFrame(_build(world).edges).reindex(columns=list(store.EDGE_COLUMNS))
    _set_tree(world, {"aicompute": members}, [(V2_ASOF, {"aicompute": members[2:]})])
    assert materialize.source_shrink_refusals(_build(world).edges, stored) == []
    _set_tree(world, {"aicompute": members}, [(V2_ASOF, {"aicompute": members[3:]})])
    refusals = materialize.source_shrink_refusals(_build(world).edges, stored)
    assert len(refusals) == 1 and "finviz_themes" in refusals[0]


def test_the_second_wall_measures_per_family(world):
    """A family that is not shrinking must not be dragged into another family's refusal —
    and a family with no stored live edges cannot 'shrink' at all."""
    _set_tree(world, {"aicompute": ["AAA", "BBB", "CCC", "DDD"]})
    view = _build(world)
    stored = pd.DataFrame(view.edges).reindex(columns=list(store.EDGE_COLUMNS))
    _set_tree(world, {"aicompute": ["AAA", "BBB", "CCC", "DDD"]},
              [(V2_ASOF, {"aicompute": ["AAA"]})])
    refusals = materialize.source_shrink_refusals(_build(world).edges, stored)
    assert len(refusals) == 1 and "finviz_themes" in refusals[0]
    assert materialize.source_shrink_refusals([], stored) == []


# ---------------------------------------------------------------------------
# The probation queue
# ---------------------------------------------------------------------------

def test_the_probation_queue_is_append_only_and_ratifies_nothing(tmp_path):
    path = tmp_path / "proposals.jsonl"
    row = probation.make_proposal(
        kind="mapping", subject={"basket": "basket:baskets:solar_us",
                                 "local_theme": "ltheme:finviz:aicompute"},
        evidence={"jaccard": 0.6}, proposed_by="overlap_stats")
    assert row["status"] == "proposed" and row["ratified_by"] is None
    added, skipped = probation.append_proposals([row], path)
    assert (added, skipped) == (1, 0)
    # Re-running a proposer re-proposes nothing: the id is a hash of the SUBJECT.
    again = probation.make_proposal(
        kind="mapping", subject={"basket": "basket:baskets:solar_us",
                                 "local_theme": "ltheme:finviz:aicompute"},
        evidence={"jaccard": 0.9}, proposed_by="overlap_stats")
    assert again["proposal_id"] == row["proposal_id"]
    assert probation.append_proposals([again], path) == (0, 1)
    assert len(probation.read_proposals(path)) == 1
    assert probation.ratified(probation.read_proposals(path)) == []


def test_a_proposal_cannot_be_born_ratified(tmp_path):
    with pytest.raises(ValueError, match="unknown proposal kind"):
        probation.make_proposal(kind="promote_now", subject={}, proposed_by="coverage_gap")
    with pytest.raises(ValueError, match="unknown proposer"):
        probation.make_proposal(kind="mapping", subject={}, proposed_by="a_hunch")
    bad = probation.make_proposal(kind="mapping", subject={"x": 1},
                                  proposed_by="overlap_stats")
    bad["status"] = "ratified"
    assert any("names its author" in e for e in probation.validate(bad))
    with pytest.raises(ValueError, match="malformed"):
        probation.append_proposals([bad], tmp_path / "p.jsonl")


# ---------------------------------------------------------------------------
# Coverage-gap + overlap diagnostics
# ---------------------------------------------------------------------------

def test_coverage_gap_case_a_fires_on_the_lithium_shape(world):
    """Three names that co-occur in the question, each covered individually, sharing no
    concept with each other. A zero-membership check sees nothing here."""
    from scripts import theme_coverage_gaps as gaps

    _set_tree(world, {"aicompute": ["AAA", "SHARED"], "aicloud": ["BBB", "SHARED2"],
                      "aidata": ["CCC", "SHARED3"]})
    view = _build(world)
    nodes = pd.DataFrame(view.nodes)
    report = gaps.analyse(["co:us:AAA", "co:us:BBB", "co:us:CCC", "co:us:NOPE"],
                          nodes, view.edges, breadth_floor=100)
    case_a = report["case_a_cooccurrence"]
    assert case_a["isolated_ids"] == ["co:us:AAA", "co:us:BBB", "co:us:CCC"]
    assert case_a["pairs_sharing_a_concept"] == []
    assert case_a["zero_membership_ids"] == []
    assert report["unresolved"] == {
        "co:us:NOPE": "no company node with this id or symbol"}

    # …and a pair that DOES share a concept is not reported as a gap.
    paired = gaps.analyse(["co:us:AAA", "co:us:SHARED"], nodes, view.edges)
    assert paired["case_a_cooccurrence"]["isolated_ids"] == []
    assert paired["case_a_cooccurrence"]["pairs_sharing_a_concept"][0]["shared"] == 1


def test_coverage_gap_case_d_prints_its_floor_and_the_distribution(world):
    from scripts import theme_coverage_gaps as gaps

    _set_tree(world, {"broad": [f"T{i}" for i in range(12)], "narrow": ["T0", "NARROW"]})
    view = _build(world)
    nodes = pd.DataFrame(view.nodes)
    report = gaps.analyse(["co:us:T1", "co:us:T0"], nodes, view.edges, breadth_floor=10)
    case_d = report["case_d_breadth"]
    assert case_d["reporting_floor_members"] == 10
    assert "not a truth claim" in case_d["floor_note"]
    assert case_d["breadth_distribution"]["max_members"] == 12
    assert case_d["broad_only_ids"] == ["co:us:T1"], (
        "T0 also sits in a narrow concept, so its coverage is not broad-only")


def test_the_overlap_proposer_prints_a_null_baseline_and_mints_no_edges(world):
    from scripts import propose_basket_ltheme_relations as overlap

    def _members(symbols):
        return [{"ticker": s, "added": "2023-05-09", "removed": None} for s in symbols]

    members = [f"M{i}" for i in range(10)]
    baskets = {"twin": {"name": "Twin", "created": "2023-05-09",
                        "members": _members(members)}}
    # Four decoy baskets, so the shuffle has a real universe to draw from. With a
    # 50-name pool a random 10-name basket overlaps the 10-name concept by ~2, which is
    # the whole point: the floor's yield under the null is what says whether 0.5 means
    # anything at this size.
    for b in range(4):
        # Symbols stay inside the company-id grammar ([A-Za-z0-9.-]): an underscore is
        # refused at mint time, which would silently empty these baskets and leave the
        # shuffle with a single basket to permute against itself.
        baskets[f"other{b}"] = {
            "name": f"Other {b}", "created": "2023-05-09",
            "members": _members([f"X{b}{i}" for i in range(10)])}
    _write(world["data"] / "baskets" / "membership.json",
           {"version": "2026-08-01", "seed_date": "2023-05-09", "baskets": baskets})
    _set_tree(world, {"mirror": members, "unrelated": [f"Z{i}" for i in range(10)]})
    view = _build(world)

    report = overlap.build_report(view.edges, suite="baskets", floor=0.5, shuffles=20,
                                  seed=7)
    assert report["edges_minted"] == 0
    pair = next(p for p in report["pairs"] if p["basket"] == "basket:baskets:twin")
    assert pair["local_theme"] == "ltheme:finviz:mirror"
    assert pair["containment_of_basket"] == 1.0 and pair["jaccard"] == 1.0
    assert not [p for p in report["pairs"] if p["basket"].endswith(("other0", "other1",
                                                                    "other2", "other3"))]

    null = report["null_baseline"]
    assert null["shuffles"] == 20 and null["seed"] == 7
    assert "degenerate" in null["what_was_shuffled"]
    assert null["mean"] < report["observed_pairs"], (
        "a null that yields as much as the real grouping would say the floor is noise")
    rows = overlap.proposals_from(report)
    assert all(r["kind"] == "mapping" and r["status"] == "proposed" for r in rows)
    assert all("null_baseline" in r["evidence"] for r in rows)


# ---------------------------------------------------------------------------
# Contract conformance of everything the plane emits
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["nodes", "edges", "evidence", "capability"])
def test_every_local_plane_row_validates_against_its_committed_contract(world, kind):
    import jsonschema

    _set_tree(world, {"aicompute": ["AAA", "BBB"]},
              [(V2_ASOF, {"aicompute": ["AAA"]})])
    view = _build(world)
    schema = json.loads((ROOT / "contracts" / "theme_graph" /
                         f"{kind}.v1.schema.json").read_text(encoding="utf-8"))
    rows = getattr(view, kind)
    assert rows, f"no {kind} emitted — a vacuous validation proves nothing"
    for row in rows:
        jsonschema.validate(row, schema)


def test_a_store_missing_the_w3a_columns_is_a_notice_not_a_breach(world, tmp_path):
    """The migration window: a store written before the additive columns existed was
    contract-valid when it was written. A guard that reds the whole fleet between a merge
    and the next nightly is a scheduled red, not a finding."""
    _set_tree(world, {"aicompute": ["AAA"]})
    view = _build(world)
    root = _materialise(tmp_path / "store_pre", view)
    for name, drop in (("nodes", ["source_meta"]), ("evidence", ["provider", "claim_type"])):
        df = pd.read_parquet(root / f"{name}.parquet").drop(columns=drop)
        df.to_parquet(root / f"{name}.parquet", index=False)
    (root / "capability.parquet").unlink()
    breaches, notices = guard.audit(root, tmp_path / "no_breaks.yml")
    assert breaches == []
    assert any("predates the W3A additive column" in n for n in notices)
    # …but a missing CORE column is still drift.
    df = pd.read_parquet(root / "edges.parquet").drop(columns=["date_provenance"])
    df.to_parquet(root / "edges.parquet", index=False)
    assert any("column set drift" in b
               for b in guard.audit(root, tmp_path / "no_breaks.yml")[0])


def test_the_guard_selftest_still_passes():
    assert guard.selftest() == 0


# ---------------------------------------------------------------------------
# Helpers that write fixture stores
# ---------------------------------------------------------------------------

def _is_set(v: object) -> bool:
    return not (v is None or (isinstance(v, float) and v != v))


def _materialise(root: Path, view, *, nodes=None, edges=None, evidence=None,
                 extra_evidence=()) -> Path:
    """Write a view to a fixture store directory. Never touches ``data/``."""
    root.mkdir(parents=True, exist_ok=True)
    (root.parent / "no_breaks.yml").write_text("breaks: []\n", encoding="utf-8")
    payload = {
        "nodes": (nodes if nodes is not None else view.nodes, store.NODE_COLUMNS),
        "edges": (edges if edges is not None else view.edges, store.EDGE_COLUMNS),
        "evidence": ([*(evidence if evidence is not None else view.evidence),
                      *extra_evidence], store.EVIDENCE_COLUMNS),
        "capability": (view.capability, store.CAPABILITY_COLUMNS),
    }
    for name, (rows, columns) in payload.items():
        pd.DataFrame(rows).reindex(columns=list(columns)).to_parquet(
            root / f"{name}.parquet", index=False)
    return root


def _latest_belief(root: Path) -> list[dict]:
    df = pd.read_parquet(root / "edges.parquet")
    ordered = df.sort_values(["edge_id", "belief_time", "computed_at"], kind="stable")
    return ordered.drop_duplicates(subset=["edge_id"], keep="last").to_dict("records")


# ---------------------------------------------------------------------------
# Supergroup layer (diff-review F1): receipts are the ONLY source; never ordinals
# ---------------------------------------------------------------------------

def _write_supergroup_receipt(world, groups: list[dict]) -> None:
    rdir = world["data"] / "themes_heatmap" / "tree_refresh_receipts"
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "20260815T000000Z.json").write_text(
        json.dumps({"promoted": True, "supergroups": groups}), encoding="utf-8")


def test_supergroup_index_comes_from_the_receipt_never_the_theme_ordinal(world):
    """Two themes in ONE group must share an index — the theme ordinal cannot fake this.

    The original defect stamped enumerate() ordinals (40 singleton groups on the real
    tree); a one-theme fixture passed because ordinal 0 == group 0. This fixture makes
    the two values diverge: theme 'Cloud' is ordinal 1 but group 0.
    """
    tree = [
        {"theme": "Artificial Intelligence", "key": "Artificial Intelligence",
         "subsectors": [{"key": "aicompute", "name": "Compute", "description": "",
                         "members": ["AAA"]}]},
        {"theme": "Cloud", "key": "Cloud",
         "subsectors": [{"key": "cloudinfra", "name": "Infra", "description": "",
                         "members": ["BBB"]}]},
        {"theme": "Metals", "key": "Metals",
         "subsectors": [{"key": "metalsgold", "name": "Gold", "description": "",
                         "members": ["CCC"]}]},
    ]
    _write(world["root"] / local_sources.SEED_TREE_FILE,
           {"asof": SEED_ASOF, "themes": tree})
    (world["data"] / "themes_heatmap" / "tree_history.jsonl").parent.mkdir(
        parents=True, exist_ok=True)
    (world["data"] / "themes_heatmap" / "tree_history.jsonl").write_text(
        "", encoding="utf-8")
    _write_supergroup_receipt(world, [
        {"group": "1", "themes": ["Artificial Intelligence", "Cloud"]},
        {"group": "2", "themes": ["Metals"]},
    ])
    view = _build(world)
    got = {}
    for n in view.nodes:
        if str(n["node_id"]).startswith("ltheme:finviz:"):
            got[n["node_id"]] = json.loads(n["source_meta"])["supergroup_index"]
    assert got["ltheme:finviz:aicompute"] == 0
    assert got["ltheme:finviz:cloudinfra"] == 0   # ordinal 1 — the group wins
    assert got["ltheme:finviz:metalsgold"] == 1   # ordinal 2 — the group wins


def test_supergroup_absent_from_receipt_is_none_not_a_guess(world):
    _set_tree(world, {"aicompute": ["AAA"]})
    _write_supergroup_receipt(world, [{"group": "1", "themes": ["Something Else"]}])
    view = _build(world)
    meta = json.loads(next(n for n in view.nodes
                           if n["node_id"] == "ltheme:finviz:aicompute")["source_meta"])
    assert meta["supergroup_index"] is None


def test_load_supergroups_handles_missing_dir_and_torn_receipt(tmp_path):
    assert local_sources.load_supergroups(tmp_path / "nope") == {}
    rdir = tmp_path / "receipts"
    rdir.mkdir()
    (rdir / "20260101T000000Z.json").write_text("{torn", encoding="utf-8")
    assert local_sources.load_supergroups(rdir) == {}
