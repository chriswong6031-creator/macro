"""Bitemporal materialization of the theme graph (masterplan §4.1, directive §2C).

WHAT THESE PROTECT — the honesty invariants, which are all invisible at runtime:

* A backfill is RECONSTRUCTION. Every row says so, and its belief_time is the run's own
  date, so the graph never claims to have known a membership when it took effect.
* ``date_provenance`` separates a real dated changelog entry from the seed CONSTANT a
  membership document uses for its first-run members. That constant is where a series
  begins, not when a company joined a theme, and stamping it ``curated_changelog`` would
  be exactly the "make present knowledge look historically known" failure G0.2 forbids.
* Corroborating evidence is ADDED, never merged: a member the raw vendor dump also shows
  gets a second receipt beside the membership document's, and nothing nets.
* The store is append-only. A removal appends a NEW row carrying valid_to; the row that
  opened the interval survives, and the closed edge keeps resolving.
* A THS concept code the vendor has since renamed is reported, not fatal.

Fixture-only: every input is built under tmp_path, the identity-break table is stubbed
empty, and nothing here reads live ``data/`` or pins a live count.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from engine.theme_graph import identity, local_sources, materialize, store
from lib import config

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts" / "theme_graph"

US_SEED = "2023-05-09"
CN_SEED = "2021-06-15"
SNAP_DATE = "2026-06-30"
XWALK_DATE = "2026-07-09"
CMAP_ASOF = "2026-06-27"
US_DOC_DATE = "2026-08-07"
CN_DOC_DATE = "2026-06-20"
THS_DOC_DATE = "2026-06-30"

KNOWN_CODE = "900001"
DRIFTED_CODE = "999999"   # in the crosswalk, gone from the vendor's concept map


# ---------------------------------------------------------------------------
# Fixture tree
# ---------------------------------------------------------------------------

def _write(path: Path, doc: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def _us_doc(*, removed: str | None = None) -> dict:
    """US family — deliberately keyed by ``symbol``, not ``ticker``.

    Every live family uses ``ticker`` today; the materializer DETECTS the key rather
    than assuming it, and this fixture is what keeps that detection honest.
    """
    return {
        "version": US_DOC_DATE, "seed_date": US_SEED,
        "baskets": {
            "solar_us": {
                "name": "Solar", "created": US_SEED, "etf_proxy": "TAN",
                "members": [
                    {"symbol": "AAA", "added": US_SEED, "removed": None, "name": "Alpha"},
                    {"symbol": "BBB", "added": "2024-02-02", "removed": removed,
                     "name": "Beta"},
                ],
            },
            "multi_us": {
                "name": "Multi", "created": "2024-01-01",
                # A LIST proxy: the shape `defensives` actually ships.
                "etf_proxy": ["XLP", "XLU"],
                "members": [{"symbol": "CCC", "added": "2024-01-01", "removed": None,
                             "name": "Gamma"}],
            },
        },
    }


def _cn_doc() -> dict:
    return {
        "version": CN_DOC_DATE, "seed_date": CN_SEED,
        "baskets": {
            "cn_solar": {
                "name": "CN Solar", "name_zh": "光伏", "created": CN_SEED,
                "etf_proxy": None,
                "members": [{"ticker": "600001.SS", "added": CN_SEED, "removed": None,
                             "name_zh": "甲公司"}],
            },
        },
    }


def _ths_doc() -> dict:
    return {
        "version": THS_DOC_DATE, "seed_date": CN_SEED,
        "baskets": {
            f"thsc{KNOWN_CODE}": {
                "name": "Test Concept", "name_zh": "测试概念", "created": CN_SEED,
                "etf_proxy": None, "ths_concept": "测试概念",
                "members": [
                    {"ticker": "600001.SS", "added": CN_SEED, "removed": None,
                     "name_zh": "甲公司"},
                    {"ticker": "600002.SS", "added": CN_SEED, "removed": None,
                     "name_zh": "乙公司"},
                ],
            },
        },
    }


def _crosswalk() -> dict:
    return {
        "version": 3, "date": XWALK_DATE,
        "themes": [{
            "id": "solar", "name_en": "Solar", "name_zh": "太阳能",
            "foresight_id": "solar", "primary_basket_id": "solar_us",
            "basket_ids": ["solar_us", "not_a_basket"],
            "subsector_keys": [], "citrini_basket_ids": [],
            "theme_node_id": "theme:solar",
            "ths_concept_ids": [KNOWN_CODE, DRIFTED_CODE],
            "cn_basket_ids": ["cn_solar"],
            "note": "fixture",
        }],
    }


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A miniature of the live layout: three suites, a concept map, a raw side-car."""
    root = tmp_path / "data"
    _write(root / "baskets" / "membership.json", _us_doc())
    _write(root / "baskets_china" / "membership.json", _cn_doc())
    _write(root / "baskets_china_ths" / "membership.json", _ths_doc())
    pd.DataFrame([
        {"snapshot_date": THS_DOC_DATE, "suite": "baskets_china_ths",
         "basket_id": f"thsc{KNOWN_CODE}", "ticker": "600001.SS",
         "source_shape": "membership"},
        {"snapshot_date": THS_DOC_DATE, "suite": "baskets_china_ths",
         "basket_id": f"thsc{KNOWN_CODE}", "ticker": "600002.SS",
         "source_shape": "membership"},
    ]).to_parquet(root / "baskets_china_ths" / "membership_history.parquet", index=False)
    _write(root / "baskets_china_ths" / "concept_map.json", {
        "asof": CMAP_ASOF,
        "map": {"测试概念": KNOWN_CODE, "另一概念": "900002", "第三概念": "900003"},
    })
    xwalk = tmp_path / "theme_crosswalk.yml"
    xwalk.write_text(yaml.safe_dump(_crosswalk(), allow_unicode=True, sort_keys=False),
                     encoding="utf-8")
    # The identity-break table is stubbed empty so a future ratified break in the
    # committed config cannot silently change what these tests assert.
    monkeypatch.setattr(identity, "load_breaks", lambda *a, **k: {})
    monkeypatch.setattr(config, "data_dir", lambda: root)
    return root, xwalk


RAW_SNAPSHOT = (SNAP_DATE, {"测试概念": [{"ticker": "600001.SS", "name": "甲公司"}]})


def _build(tree, *, era="reconstruction", belief_time="2026-08-11",
           raw_snapshot=RAW_SNAPSHOT, **kw):
    root, xwalk = tree
    ths_history = kw.pop("ths_history", None)
    if ths_history is None:
        ths_history = pd.read_parquet(root / "baskets_china_ths" / "membership_history.parquet")
    return materialize.build(era=era, belief_time=belief_time,
                             computed_at="2026-08-11T00:00:00Z",
                             data_dir=root, crosswalk_path=xwalk,
                             raw_snapshot=raw_snapshot, ths_history=ths_history, **kw)


def _by_type(view, edge_type):
    return [e for e in view.edges if e["type"] == edge_type]


def _edge(view, edge_type, src, dst):
    hits = [e for e in _by_type(view, edge_type) if e["src"] == src and e["dst"] == dst]
    assert len(hits) == 1, f"expected exactly one {edge_type} {src}->{dst}, got {hits}"
    return hits[0]


def test_ths_owner_history_keeps_first_observed_boundary_and_reappearance():
    """D2C: owner snapshots, never today's membership, define THS PIT intervals.

    Dump-shaped rows are REFUSED by default — their concept→basket resolution used
    the current map, so admitting them would backdate a mapping we do not historically
    possess. The filter lives inside ``ths_membership_intervals`` so every caller
    inherits it.
    """
    history = pd.DataFrame([
        {"snapshot_date": "2026-06-30", "basket_id": "thsc900001",
         "ticker": "600001.SS", "source_shape": "ths_concept_dump"},
        {"snapshot_date": "2026-07-08", "basket_id": "thsc900001",
         "ticker": "600002.SS", "source_shape": "membership"},
        {"snapshot_date": "2026-07-15", "basket_id": "thsc900001",
         "ticker": "600001.SS", "source_shape": "membership"},
        {"snapshot_date": "2026-07-15", "basket_id": "thsc900001",
         "ticker": "600002.SS", "source_shape": "membership"},
    ])

    intervals = local_sources.ths_membership_intervals(history)

    assert [(iv.basket_id, iv.ticker, iv.valid_from, iv.valid_to,
             iv.source_shape) for iv in intervals] == [
        ("thsc900001", "600002.SS", "2026-07-08", None, "membership"),
        ("thsc900001", "600001.SS", "2026-07-15", None, "membership"),
    ], "ths_concept_dump rows must be refused by the default shape filter"

    # Explicit opt-in still admits dump rows for intentional exercises.
    with_dumps = local_sources.ths_membership_intervals(
        history, shapes=frozenset({"membership", "ths_concept_dump"}))
    assert any(iv.source_shape == "ths_concept_dump" for iv in with_dumps)


def test_ths_owner_history_staggered_multi_basket_collection_never_fabricates_exits():
    """A date collected for basket A but not basket B must be a GAP for B, never
    an absence that closes/reopens B's interval (the presence axis is PER-BASKET,
    not the global set of snapshot dates)."""
    history = pd.DataFrame([
        {"snapshot_date": "2026-06-30", "basket_id": "B",
         "ticker": "X", "source_shape": "membership"},
        {"snapshot_date": "2026-07-01", "basket_id": "A",
         "ticker": "Y", "source_shape": "membership"},
        {"snapshot_date": "2026-07-08", "basket_id": "B",
         "ticker": "X", "source_shape": "membership"},
    ])

    intervals = local_sources.ths_membership_intervals(history)

    assert [(iv.basket_id, iv.ticker, iv.valid_from, iv.valid_to)
            for iv in intervals] == [
        ("B", "X", "2026-06-30", None),
        ("A", "Y", "2026-07-01", None),
    ], ("neither basket was ever observed absent — a staggered collection date "
        "for the OTHER basket must never fabricate an exit")


def test_ths_graph_never_leaks_a_later_member_back_into_an_earlier_snapshot(tree):
    """D2C mutation guard: current membership must not fill an older PIT vintage."""
    root, _xwalk = tree
    history = pd.DataFrame([
        {"snapshot_date": "2026-06-30", "basket_id": f"thsc{KNOWN_CODE}",
         "ticker": "600001.SS", "source_shape": "membership"},
        {"snapshot_date": "2026-07-08", "basket_id": f"thsc{KNOWN_CODE}",
         "ticker": "600001.SS", "source_shape": "membership"},
        {"snapshot_date": "2026-07-08", "basket_id": f"thsc{KNOWN_CODE}",
         "ticker": "600002.SS", "source_shape": "membership"},
        {"snapshot_date": "2026-07-15", "basket_id": f"thsc{KNOWN_CODE}",
         "ticker": "600003.SS", "source_shape": "ths_concept_dump"},
    ])
    history.to_parquet(root / "baskets_china_ths" / "membership_history.parquet", index=False)

    view = _build(tree)
    basket = f"basket:baskets_china_ths:thsc{KNOWN_CODE}"
    early = _edge(view, "MEMBER_OF", "co:cn:600001.SS", basket)
    later = _edge(view, "MEMBER_OF", "co:cn:600002.SS", basket)
    assert early["valid_from"] == "2026-06-30"
    assert later["valid_from"] == "2026-07-08"
    assert later["valid_from"] > early["valid_from"]
    assert not [edge for edge in view.edges if edge["src"] == "co:cn:600003.SS"], (
        "a raw concept dump has a current-basis concept-to-basket mapping and cannot "
        "become a historical graph membership")
    assert view.per_suite["baskets_china_ths"]["excluded_source_shapes"] == [
        "ths_concept_dump"]


def test_ths_graph_declines_current_membership_when_owner_history_is_absent(tree):
    view = _build(tree, ths_history=pd.DataFrame())
    assert not [edge for edge in _by_type(view, "MEMBER_OF")
                if edge["dst"].startswith("basket:baskets_china_ths:")]
    report = view.per_suite["baskets_china_ths"]
    assert report["member_edges"] == 0
    # m1: degraded path still emits the full key set consumers inspect.
    for key in ("closed_member_edges", "skipped_unidentifiable", "tracks_edges",
                "membership_published_at", "seed_constant", "unlabelled_nodes", "note"):
        assert key in report
    assert report["closed_member_edges"] == 0
    assert report["tracks_edges"] == 0
    assert report["membership_published_at"] == THS_DOC_DATE
    assert report["seed_constant"] == CN_SEED
    assert report["note"]


def test_ths_per_suite_keeps_coverage_disclosure_fields(tree):
    """M1: membership_published_at / seed_constant / tracks_edges stay cited."""
    view = _build(tree)
    report = view.per_suite["baskets_china_ths"]
    assert report["membership_published_at"] == THS_DOC_DATE
    assert report["seed_constant"] == CN_SEED
    assert report["tracks_edges"] == 0
    assert "closed_member_edges" in report
    assert "skipped_unidentifiable" in report
    assert "unlabelled_nodes" in report
    assert report["note"] is None
    ths_member = _edge(view, "MEMBER_OF", "co:cn:600001.SS",
                       f"basket:baskets_china_ths:thsc{KNOWN_CODE}")
    assert ths_member["date_provenance"] == "membership_pit"


def test_ths_canonical_join_declines_a_mapping_receipted_after_the_crosswalk(tree):
    root, _xwalk = tree
    doc = _ths_doc()
    doc["version"] = "2026-07-10"  # after the crosswalk's 2026-07-09 receipt
    _write(root / "baskets_china_ths" / "membership.json", doc)
    view = _build(tree)
    assert not [edge for edge in _by_type(view, "EXPRESSES")
                if edge["src"] == f"basket:baskets_china_ths:thsc{KNOWN_CODE}"
                and edge["dst"] == "theme:solar"]


# ---------------------------------------------------------------------------
# 1. The rows satisfy their committed contracts
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["nodes", "edges", "evidence"])
def test_every_emitted_row_validates_against_its_committed_contract(tree, kind):
    """Producer-emitted rows against the SCHEMA, not against a hand-copied field list —
    a test asserting its own idea of the shape goes green while the schema and the
    writer drift apart."""
    import jsonschema

    view = _build(tree)
    schema = json.loads((CONTRACTS / f"{kind}.v1.schema.json").read_text(encoding="utf-8"))
    rows = getattr(view, kind)
    assert rows, f"no {kind} emitted — a vacuous validation proves nothing"
    for row in rows:
        jsonschema.validate(row, schema)


def test_the_emitted_columns_are_exactly_the_stores(tree):
    view = _build(tree)
    assert set(view.nodes[0]) == set(store.NODE_COLUMNS)
    assert set(view.edges[0]) == set(store.EDGE_COLUMNS)
    assert set(view.evidence[0]) == set(store.EVIDENCE_COLUMNS)


# ---------------------------------------------------------------------------
# 2. Honesty: era, belief_time, date_provenance
# ---------------------------------------------------------------------------

def test_a_backfill_is_labelled_reconstruction_and_believed_today(tree):
    view = _build(tree, belief_time="2026-08-11")
    assert {e["era"] for e in view.edges} == {"reconstruction"}
    assert {e["belief_time"] for e in view.edges} == {"2026-08-11"}
    # ...and the evidence it cites is dated when the SOURCE was published, not today.
    assert {e["evidence_time"] for e in _by_type(view, "MEMBER_OF")} == \
        {US_DOC_DATE, CN_DOC_DATE, THS_DOC_DATE}


def test_the_seed_constant_is_flagged_and_a_real_date_is_not(tree):
    """The distinction the whole store turns on. Both members below sit in the same
    basket; one carries the document's seed constant and one a real curated date."""
    view = _build(tree)
    seeded = _edge(view, "MEMBER_OF", "co:us:AAA", "basket:baskets:solar_us")
    curated = _edge(view, "MEMBER_OF", "co:us:BBB", "basket:baskets:solar_us")
    assert seeded["valid_from"] == US_SEED
    assert seeded["date_provenance"] == "seed_constant"
    assert curated["valid_from"] == "2024-02-02"
    assert curated["date_provenance"] == "curated_changelog"


def test_the_seed_constant_rule_is_per_document_not_per_market(tree):
    """The US suite seeds at its OWN constant (2023-05-09), the CN suites at theirs
    (2021-06-15). A CN-only rule would stamp the US convention dates as observations."""
    view = _build(tree)
    cn = _edge(view, "MEMBER_OF", "co:cn:600001.SS", "basket:baskets_china:cn_solar")
    assert cn["valid_from"] == CN_SEED and cn["date_provenance"] == "seed_constant"
    us = _edge(view, "MEMBER_OF", "co:us:AAA", "basket:baskets:solar_us")
    assert us["valid_from"] == US_SEED and us["date_provenance"] == "seed_constant"
    assert us["valid_from"] != cn["valid_from"], "the two constants must not be conflated"


def test_crosswalk_derived_edges_declare_their_own_provenance(tree):
    """Scoped to the edges the CROSSWALK derives — the ones whose destination is
    canonical vocabulary. W3A added source-local EXPRESSES edges (basket→ltheme) that
    come from a vendor snapshot instead, and they carry that provenance honestly."""
    view = _build(tree)
    canonical = [e for e in _by_type(view, "EXPRESSES") if e["dst"].startswith("theme:")]
    assert canonical, "no crosswalk-derived edges — a vacuous check proves nothing"
    for e in canonical:
        assert e["date_provenance"] == "crosswalk"
        assert e["valid_from"] == XWALK_DATE


# ---------------------------------------------------------------------------
# 3. Evidence: corroboration adds, never replaces
# ---------------------------------------------------------------------------

def test_a_raw_ths_concept_dump_never_backdates_a_basket_membership(tree):
    view = _build(tree)
    ths_basket = f"basket:baskets_china_ths:thsc{KNOWN_CODE}"
    covered = _edge(view, "MEMBER_OF", "co:cn:600001.SS", ths_basket)
    uncovered = _edge(view, "MEMBER_OF", "co:cn:600002.SS", ths_basket)
    assert len(covered["evidence_refs"]) == len(uncovered["evidence_refs"]) == 1
    assert covered["confidence_basis"] == "membership_pit.ths.v1"
    refs = {e["evidence_id"]: e for e in view.evidence}
    assert all(refs[eid]["source_ref"].endswith(f"@{THS_DOC_DATE}")
               for eid in covered["evidence_refs"])


def test_without_a_raw_snapshot_the_membership_receipt_stands_alone(tree):
    view = _build(tree, raw_snapshot=None)
    ths_basket = f"basket:baskets_china_ths:thsc{KNOWN_CODE}"
    assert len(_edge(view, "MEMBER_OF", "co:cn:600001.SS", ths_basket)["evidence_refs"]) == 1


def test_receipt_licensing_is_derived_from_the_rights_registry(tree):
    """W3A §9.4: the REGISTRY is the single rights authority and a new receipt's booleans
    are derived from it, never from a constant in the builder. The expected values are
    read from the registry FILE here — parsed independently, not through rights.py — so
    this pins the derivation without pinning today's classes, and it keeps holding on the
    day the operator resolves a vendor family."""
    registry = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "config" / "theme_sources.yml")
        .read_text(encoding="utf-8"))["families"]
    display_ok = {"derived_display_ok", "direct_display_ok"}

    view = _build(tree)
    ev = {e["source_ref"]: e for e in view.evidence}
    for source_ref, family in (("data/baskets_china_ths/membership.json", "ths_concepts"),
                               ("data/baskets/membership.json", "mastermind_curated")):
        row = ev[source_ref]
        cls = registry[family]["rights_class"]
        assert row["licensing_internal_ok"] is True
        assert row["licensing_display_ok"] is (cls in display_ok), family
        # Only house-authored content may be republished, whatever the display class.
        assert row["licensing_redistribution_ok"] is (
            cls in display_ok and registry[family]["auth_class"] == "house"), family


def test_every_edge_cites_at_least_one_dated_receipt(tree):
    view = _build(tree)
    dated = {e["evidence_id"] for e in view.evidence if e["published_at"]}
    for e in view.edges:
        assert e["evidence_refs"], e["edge_id"]
        assert set(e["evidence_refs"]) <= dated


# ---------------------------------------------------------------------------
# 4. The three edge types
# ---------------------------------------------------------------------------

def test_expresses_comes_from_all_three_crosswalk_paths(tree):
    view = _build(tree)
    canonical = [e for e in _by_type(view, "EXPRESSES") if e["dst"].startswith("theme:")]
    assert {e["src"] for e in canonical} == {
        "basket:baskets:solar_us",                          # basket_ids (US)
        "basket:baskets_china:cn_solar",                    # cn_basket_ids (curated CN)
        f"basket:baskets_china_ths:thsc{KNOWN_CODE}",       # ths_concept -> code join
        # W3A: the concept's own vocabulary resolution. NOT a fourth expression path —
        # it resolves a vendor id to canonical vocabulary, and the guard asserts it can
        # never name a different theme than the one-hop basket path does.
        f"ltheme:ths:{KNOWN_CODE}",
    }
    assert {e["dst"] for e in canonical} == {"theme:solar"}


def test_a_crosswalk_basket_that_does_not_exist_mints_nothing(tree):
    """`not_a_basket` is listed in the fixture crosswalk. Skipping it is honest;
    minting the node would invent a basket out of a mapping."""
    view = _build(tree)
    assert not any(n["node_id"].endswith("not_a_basket") for n in view.nodes)


def test_the_ths_join_carries_the_concept_maps_own_receipt(tree):
    view = _build(tree)
    joined = _edge(view, "EXPRESSES", f"basket:baskets_china_ths:thsc{KNOWN_CODE}",
                   "theme:solar")
    direct = _edge(view, "EXPRESSES", "basket:baskets:solar_us", "theme:solar")
    assert len(joined["evidence_refs"]) == 2 and len(direct["evidence_refs"]) == 1


def test_tracks_is_emitted_for_both_etf_proxy_shapes(tree):
    view = _build(tree)
    tracks = _by_type(view, "TRACKS")
    assert {(e["src"], e["dst"]) for e in tracks} == {
        ("etf:TAN", "basket:baskets:solar_us"),
        ("etf:XLP", "basket:baskets:multi_us"),
        ("etf:XLU", "basket:baskets:multi_us"),
    }
    assert {n["kind"] for n in view.nodes if n["node_id"].startswith("etf:")} == {"etf"}


def test_no_company_theme_edge_is_derived(tree):
    """Evidence grain law: composing membership with expression is the consumer's join,
    made against evidence it can see — not a fact this store asserts."""
    view = _build(tree)
    assert {e["type"] for e in view.edges} <= {"MEMBER_OF", "EXPRESSES", "TRACKS"}
    for e in view.edges:
        assert not (e["src"].startswith("co:") and e["dst"].startswith("theme:"))


def test_node_kinds_and_names(tree):
    view = _build(tree)
    kinds = {}
    for n in view.nodes:
        kinds.setdefault(n["kind"], []).append(n)
    assert set(kinds) == {"company", "basket", "etf", "theme", "local_theme"}
    assert {n["status"] for n in view.nodes} == {"canonical"}
    assert {n["identity_epoch"] for n in view.nodes} == {1}
    theme = kinds["theme"][0]
    assert json.loads(theme["external_ids"])["foresight_id"] == "solar"
    ths_basket = next(n for n in kinds["basket"] if n["node_id"].endswith(KNOWN_CODE))
    assert json.loads(ths_basket["external_ids"])["ths_code"] == KNOWN_CODE
    # A company seen in two families keeps both names it was given.
    shared = next(n for n in kinds["company"] if n["node_id"] == "co:cn:600001.SS")
    assert shared["name_zh"] == "甲公司"


# ---------------------------------------------------------------------------
# 5. Vendor drift and family refusal
# ---------------------------------------------------------------------------

def test_a_drifted_ths_code_is_reported_and_never_fatal(tree):
    view = _build(tree)
    assert view.unknown_ths_codes == [DRIFTED_CODE]
    assert view.ths_unmapped_concept_count == 2, (
        "two of the three fixture concepts are not mapped into any theme row")
    assert view.per_suite["crosswalk"]["ths_codes_mapped"] == 1


def test_a_family_whose_members_carry_no_symbol_key_is_refused(tree, tmp_path):
    """A suite that quietly contributes nothing looks exactly like a suite that is
    genuinely empty — so it is refused by name and recorded."""
    root, _xwalk = tree
    doc = _us_doc()
    for basket in doc["baskets"].values():
        for m in basket["members"]:
            m["isin"] = m.pop("symbol")
    _write(root / "baskets" / "membership.json", doc)
    view = _build(tree)
    assert "baskets" in view.skipped_suites
    assert "symbol" in view.skipped_suites["baskets"]
    assert not any(e["src"].startswith("co:us:") for e in view.edges)


def test_a_missing_family_is_skipped_with_a_reason(tree):
    root, _xwalk = tree
    (root / "baskets_china" / "membership.json").unlink()
    view = _build(tree)
    assert view.skipped_suites["baskets_china"] == "membership.json missing"
    assert view.per_suite["baskets"]["member_edges"] == 3


# ---------------------------------------------------------------------------
# 6. Determinism, append-only semantics, survivorship
# ---------------------------------------------------------------------------

def test_edge_ids_are_deterministic_across_runs(tree):
    a = _build(tree, belief_time="2026-08-11")
    b = _build(tree, belief_time="2026-09-01")
    assert [e["edge_id"] for e in a.edges] == [e["edge_id"] for e in b.edges]
    assert [e["evidence_id"] for e in a.evidence] == [e["evidence_id"] for e in b.evidence]


def test_a_re_run_over_an_unchanged_input_appends_nothing(tree):
    view = _build(tree)
    assert store.write_edges(view.edges, lane="nightly") == len(view.edges)
    again = _build(tree, era="observed", belief_time="2026-08-12")
    delta = materialize.changed_edges(again.edges, store.read_edges())
    assert delta == [], "an unchanged night must not append a duplicate history"
    assert store.write_edges(delta, lane="nightly") == 0


def test_a_removal_appends_a_closing_row_and_leaves_the_original_intact(tree):
    root, _xwalk = tree
    first = _build(tree)
    store.write_edges(first.edges, lane="nightly")
    opened = _edge(first, "MEMBER_OF", "co:us:BBB", "basket:baskets:solar_us")
    assert opened["valid_to"] is None

    _write(root / "baskets" / "membership.json", _us_doc(removed="2026-08-20"))
    second = _build(tree, era="observed", belief_time="2026-08-21")
    delta = materialize.changed_edges(second.edges, store.read_edges())
    assert [e["edge_id"] for e in delta] == [opened["edge_id"]], (
        "only the closed edge changed; everything else must stay quiet")
    assert store.write_edges(delta, lane="nightly") == 1

    history = store.read_edges(latest_belief=False)
    rows = history[history["edge_id"] == opened["edge_id"]].sort_values("belief_time")
    assert len(rows) == 2, "the closing row must be an APPEND, not an edit"
    # pandas reads an absent valid_to back as NaN, not None — the store's own null.
    assert pd.isna(rows.iloc[0]["valid_to"]) and rows.iloc[0]["era"] == "reconstruction"
    assert rows.iloc[1]["valid_to"] == "2026-08-20" and rows.iloc[1]["era"] == "observed"
    assert rows.iloc[1]["belief_time"] > rows.iloc[0]["belief_time"]

    latest = store.read_edges()
    row = latest[latest["edge_id"] == opened["edge_id"]].iloc[0]
    assert row["valid_to"] == "2026-08-20", "the view must show the CLOSED belief"
    assert (latest["edge_id"] == opened["edge_id"]).sum() == 1


def test_a_re_run_is_still_a_no_op_once_the_store_holds_a_closed_interval(tree):
    """The all-open fixture above is NOT enough. A parquet column that is entirely null
    reads back as None, but a MIXED valid_to (one closed interval among many open ones)
    reads back with NaN in the empty cells — and a None-vs-NaN comparison made every open
    edge look changed. The first nightly over the real store proposed re-appending 5,610
    of 5,628 edges while the all-open fixture saw a clean no-op."""
    root, _xwalk = tree
    store.write_edges(_build(tree).edges, lane="nightly")
    _write(root / "baskets" / "membership.json", _us_doc(removed="2026-08-20"))
    closing = _build(tree, era="observed", belief_time="2026-08-21")
    assert store.write_edges(materialize.changed_edges(closing.edges, store.read_edges()),
                             lane="nightly") == 1
    stored = store.read_edges()
    assert stored["valid_to"].notna().any() and stored["valid_to"].isna().any(), (
        "this test is only meaningful against a MIXED valid_to column")

    again = _build(tree, era="observed", belief_time="2026-08-22")
    assert materialize.changed_edges(again.edges, stored) == []


def test_a_closed_edge_survives_a_later_rebuild(tree):
    """Dead members never leave the denominator: a closed membership stays resolvable in
    the current view, it does not become an absence."""
    root, _xwalk = tree
    store.write_edges(_build(tree).edges, lane="nightly")
    _write(root / "baskets" / "membership.json", _us_doc(removed="2026-08-20"))
    closing = _build(tree, era="observed", belief_time="2026-08-21")
    store.write_edges(materialize.changed_edges(closing.edges, store.read_edges()),
                      lane="nightly")

    rebuilt = _build(tree, era="observed", belief_time="2026-09-30")
    store.write_edges(materialize.changed_edges(rebuilt.edges, store.read_edges()),
                      lane="nightly")
    latest = store.read_edges()
    closed = latest[latest["valid_to"].notna()]
    assert len(closed) == 1
    assert closed.iloc[0]["src"] == "co:us:BBB"


def test_the_writes_are_lane_gated_fail_closed(tree):
    view = _build(tree)
    assert store.write_edges(view.edges, lane=None) == 0
    assert store.write_nodes(view.nodes, lane="render") == 0
    assert not store.edges_path().exists()
    # ...and the one-shot backfill bypass is an explicit ARGUMENT, never an env default.
    assert store.write_edges(view.edges, lane=None, allow_backfill=True) == len(view.edges)


def test_the_latest_belief_view_is_max_belief_time_per_edge(tree):
    view = _build(tree)
    one = dict(view.edges[0])
    two = dict(one, belief_time="2026-12-31", valid_to="2026-12-01")
    store.write_edges([one, two], lane="nightly")
    assert len(store.read_edges(latest_belief=False)) == 2
    latest = store.read_edges()
    assert len(latest) == 1 and latest.iloc[0]["valid_to"] == "2026-12-01"


def test_the_stores_round_trip_through_parquet(tree):
    view = _build(tree)
    store.write_nodes(view.nodes, lane="nightly")
    store.write_evidence(view.evidence, lane="nightly")
    store.write_edges(view.edges, lane="nightly")
    assert list(pd.read_parquet(store.nodes_path()).columns) == list(store.NODE_COLUMNS)
    assert list(pd.read_parquet(store.edges_path()).columns) == list(store.EDGE_COLUMNS)
    assert list(pd.read_parquet(store.evidence_path()).columns) == \
        list(store.EVIDENCE_COLUMNS)
    refs = pd.read_parquet(store.edges_path())["evidence_refs"].iloc[0]
    assert len(list(refs)) >= 1, "evidence_refs must survive the parquet round-trip"


def test_the_reserved_exposure_axes_are_declared_null(tree):
    """W2 measures them. Until then they are columns, not numbers — and a null must not
    be mistaken for a measurement of zero."""
    view = _build(tree)
    for e in view.edges:
        for f in store.RESERVED_EDGE_FIELDS:
            assert e[f] is None


def test_ths_membership_doc_generation_closes_when_pit_edges_arrive(tree):
    """B1: a stored membership_doc.v1 THS MEMBER_OF generation must close on cutover.

    The PIT re-key mints disjoint edge_ids; without an explicit close of the prior
    generation, ``changed_edges`` leaves both open. Assert no company/basket pair ends
    with two open MEMBER_OF edges, and that orphans absent from the PIT also close.
    """
    root, _xwalk = tree
    basket = f"basket:baskets_china_ths:thsc{KNOWN_CODE}"

    def _doc_edge(src: str) -> dict:
        row = {
            "edge_id": f"member_of:{src}->{basket}@{CN_SEED}",
            "type": "MEMBER_OF", "src": src, "dst": basket,
            "valid_from": CN_SEED, "valid_to": None,
            "evidence_time": THS_DOC_DATE, "belief_time": "2026-06-01",
            "era": "reconstruction", "source_class": "scrape",
            "date_provenance": "seed_constant",
            "evidence_refs": ["ev:deadbeefdeadbeef"],
            "confidence_basis": "membership_doc.v1",
            "computed_at": "2026-06-01T00:00:00Z",
            "engine_version": store.ENGINE_VERSION,
        }
        for field in store.RESERVED_EDGE_FIELDS:
            row[field] = None
        return row

    prior = [_doc_edge("co:cn:600001.SS"), _doc_edge("co:cn:600099.SS")]
    store.write_edges(prior, lane="nightly")

    view = _build(tree, era="observed", belief_time="2026-08-12")
    history = pd.read_parquet(root / "baskets_china_ths" / "membership_history.parquet")
    pit_birth = materialize.ths_membership_pit_birth(history)
    assert pit_birth == THS_DOC_DATE

    closings = materialize.supersede_ths_membership_doc_edges(
        store.read_edges(), valid_to=pit_birth, belief_time="2026-08-12",
        era="observed", computed_at="2026-08-12T00:00:00Z")
    assert {c["edge_id"] for c in closings} == {e["edge_id"] for e in prior}
    assert all(c["valid_to"] == pit_birth for c in closings)

    computed = list(view.edges) + closings
    delta = materialize.changed_edges(computed, store.read_edges())
    store.write_edges(delta, lane="nightly")

    latest = store.read_edges()
    ths = latest[
        (latest["type"] == "MEMBER_OF")
        & latest["dst"].astype(str).str.startswith("basket:baskets_china_ths:")
    ]
    open_ths = ths[ths["valid_to"].isna()]
    assert not open_ths.duplicated(subset=["src", "dst"]).any(), (
        "no company/basket pair may carry two open MEMBER_OF edges after cutover")
    for eid in (e["edge_id"] for e in prior):
        row = latest[latest["edge_id"] == eid].iloc[0]
        assert row["valid_to"] == pit_birth
    pit_open = open_ths[open_ths["confidence_basis"] == "membership_pit.ths.v1"]
    assert set(pit_open["src"]) == {"co:cn:600001.SS", "co:cn:600002.SS"}
    # Generation cutover is a named full-family close — shrink wall must waive it.
    assert materialize.source_shrink_refusals(
        delta, pd.DataFrame(prior), allow={materialize.THS_FAMILY}) == []
    # Without the waiver the wall refuses (sanity that we are not greening vacuously).
    refusals = materialize.source_shrink_refusals(closings, pd.DataFrame(prior), allow=())
    assert refusals and materialize.THS_FAMILY in refusals[0]
