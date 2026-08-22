"""V4-D2B3 — GMI identity correction lineage (node lifecycle, resurrection-proof bake
suppression, the guard invariants, and the one-shot curated correction script).

Frozen contract: ``research/prophet_v4/d2/D2B3_FROZEN_CONTRACT_2026-08-21.md`` (§0-§14,
AMENDMENT §1/§2). This file drives the §10 HOSTILE TEST MATRIX plus the two AMENDMENT
§1 mandatory tests (R-A1 (i)/(ii)). Matrix item numbers are cited in each test's
docstring for traceability back to the contract.

Two test populations, deliberately kept apart:

* SYNTHETIC fixtures (tmp_path, a miniature membership tree) — matrix 3, R-A1 (i)/(ii),
  and every store/materialize mechanism test. Bake tests never touch the committed
  store (contract instruction: "Matrix 3's double-bake and all bake tests run on
  synthetic fixtures in tmp paths, never the committed store").
* The REAL committed store (``data/theme_graph/``) and the REAL registry file
  (``config/theme_graph_identity_breaks.yml``) — matrix 1, 2, 4 (epoch routing "driven
  from the real registry file"), 5, 6, 8, 9, 10, 13. These are SKIPPED (never failed)
  when the store is not checked out (a checkout that omitted ``data/``), because an
  absent store answers nothing about the correction — it is not a failure of it.
  NONE of these compare against a git ref (fixed 2026-08-22, adjudicated review
  FIX-1/FIX-2): every assertion pins a VERBATIM value or an append-only-lawful
  structural relationship (row counts, which edge_ids carry >=2 belief rows, which row
  the latest-belief collapse returns) directly on the store's own contents — durable
  regardless of which commit HEAD happens to be, and never fragile to a shallow/
  blobless CI clone.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from engine.theme_graph import identity, materialize, store
from lib import config
from scripts import check_theme_graph_contracts as guard
from scripts import correct_gmi_identity_lineage as corr

ROOT = Path(__file__).resolve().parents[1]
REAL_STORE_DIR = ROOT / "data" / "theme_graph"
REAL_BREAKS_FILE = ROOT / "config" / "theme_graph_identity_breaks.yml"

needs_real_store = pytest.mark.skipif(
    not (REAL_STORE_DIR / "nodes.parquet").exists(),
    reason="data/theme_graph/ not checked out in this worktree (sparse checkout)")


# ===========================================================================
# 1. STORE — write_node_lifecycle / read_node_lifecycle / read_nodes(current=)
# ===========================================================================

STAMP_A = "2024-01-02T00:00:00Z"
STAMP_B = "2024-06-01T00:00:00Z"


def _lifecycle_row(**over) -> dict:
    row = {
        "schema": "gmi.node_lifecycle/v1", "node_id": "co:us:ZOMB", "status": "retired",
        "retire_date": "2024-01-01", "merged_into": None, "reason": "identity_break",
        "evidence": "fixture", "ratified_by": "fixture", "computed_at": STAMP_A,
        "engine_version": store.ENGINE_VERSION,
    }
    row.update(over)
    return row


def test_write_node_lifecycle_is_lane_gated_fail_closed(tmp_path, monkeypatch):
    """Matrix 14 — lifecycle writes are refused outside the sanctioned lanes, same as
    every other store writer (nodes/edges/evidence/capability/identity_resolution)."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    assert store.write_node_lifecycle([_lifecycle_row()], lane=None) == 0
    assert not store.node_lifecycle_path().exists()
    assert store.write_node_lifecycle([_lifecycle_row()], lane="render") == 0
    assert store.write_node_lifecycle([_lifecycle_row()], lane="nightly") == 1
    assert store.write_node_lifecycle([_lifecycle_row()], lane=None,
                                      allow_backfill=True) == 0, (
        "a second row with the SAME (node_id, computed_at) key is keep-first — the "
        "one-shot correction's bypass is idempotent, never a duplicate append")


def test_read_node_lifecycle_collapses_to_latest_computed_at(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    store.write_node_lifecycle([
        _lifecycle_row(computed_at=STAMP_A, status="retired"),
        _lifecycle_row(computed_at=STAMP_B, status="merged", merged_into="co:us:OTHER"),
    ], lane="nightly")
    full = store.read_node_lifecycle(latest=False)
    assert len(full) == 2
    latest = store.read_node_lifecycle(latest=True)
    assert len(latest) == 1
    assert latest.iloc[0]["status"] == "merged"
    assert latest.iloc[0]["merged_into"] == "co:us:OTHER"


def test_read_nodes_current_false_is_byte_identical_to_raw(tmp_path, monkeypatch):
    """Matrix 12 (first half) — the default overload changes NOTHING: every existing
    consumer that never passes current= is unaffected."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    node = {"node_id": "co:us:ZOMB", "kind": "company", "name_en": None, "name_zh": None,
            "market_scope": "us", "tier": None, "status": "canonical", "merged_into": None,
            "birth_date": None, "retire_date": None, "identity_epoch": 1,
            "external_ids": "{}", "provenance": "fixture", "computed_at": STAMP_A,
            "engine_version": store.ENGINE_VERSION, "source_meta": None}
    store.write_nodes([node], lane="nightly")
    store.write_node_lifecycle([_lifecycle_row()], lane="nightly")
    raw_no_kw = store.read_nodes()
    raw_explicit = store.read_nodes(current=False)
    pd.testing.assert_frame_equal(raw_no_kw, raw_explicit)
    assert raw_no_kw.iloc[0]["status"] == "canonical", (
        "current=False must NEVER see the lifecycle overlay")


def test_read_nodes_current_true_overlays_status_and_retire_date(tmp_path, monkeypatch):
    """Matrix 12 (second half) — the overlay is correct on a MIXED fixture: one node
    with a lifecycle act, one without, row COUNT unchanged either way."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)

    def _node(nid, **over):
        row = {"node_id": nid, "kind": "company", "name_en": None, "name_zh": None,
               "market_scope": "us", "tier": None, "status": "canonical",
               "merged_into": None, "birth_date": None, "retire_date": None,
               "identity_epoch": 1, "external_ids": "{}", "provenance": "fixture",
               "computed_at": STAMP_A, "engine_version": store.ENGINE_VERSION,
               "source_meta": None}
        row.update(over)
        return row

    store.write_nodes([_node("co:us:ZOMB"), _node("co:us:SAFE")], lane="nightly")
    store.write_node_lifecycle([_lifecycle_row(node_id="co:us:ZOMB",
                                               retire_date="2024-01-01")], lane="nightly")

    current = store.read_nodes(current=True)
    assert len(current) == 2, "current=True OVERLAYS, it never removes a row"
    zomb = current[current["node_id"] == "co:us:ZOMB"].iloc[0]
    safe = current[current["node_id"] == "co:us:SAFE"].iloc[0]
    assert zomb["status"] == "retired" and zomb["retire_date"] == "2024-01-01"
    assert safe["status"] == "canonical" and pd.isna(safe["retire_date"])

    raw = store.read_nodes(current=False)
    assert raw[raw["node_id"] == "co:us:ZOMB"].iloc[0]["status"] == "canonical", (
        "the raw table is UNAFFECTED by the overlay — nodes.parquet is never rewritten")


# ===========================================================================
# 2. MATERIALIZE — the post-pass structural suppression (R-D2B3-4 / R-A1 / R-A6)
# ===========================================================================

def _co_node(node_id, symbol, *, provenance="membership_doc:baskets") -> dict:
    return {"node_id": node_id, "kind": "company",
           "external_ids": json.dumps({"symbol": symbol}), "provenance": provenance}


def _etf_node(node_id, symbol) -> dict:
    return {"node_id": node_id, "kind": "etf",
           "external_ids": json.dumps({"symbol": symbol}), "provenance": "membership_doc:baskets"}


def _member_edge(src, dst="basket:baskets:demo") -> dict:
    return {"edge_id": f"member_of:{src}->{dst}@2023-05-09", "type": "MEMBER_OF",
           "src": src, "dst": dst}


def test_suppress_etf_conflict_removes_the_company_node_and_its_edges():
    """R-D2B3-4(a) / R-A1 — a company node sharing a symbol with a same-generation etf
    node is refused; the etf node and edges pointing at OTHER companies are untouched."""
    nodes = [_co_node("co:us:DUAL", "DUAL"), _co_node("co:us:SAFE", "SAFE"),
            _etf_node("etf:DUAL", "DUAL")]
    edges = [_member_edge("co:us:DUAL"), _member_edge("co:us:SAFE")]
    kept_nodes, kept_edges, refusals = materialize._suppress_conflicts_and_retired(
        nodes, edges, retired_node_ids=frozenset())
    assert {n["node_id"] for n in kept_nodes} == {"co:us:SAFE", "etf:DUAL"}
    assert {e["edge_id"] for e in kept_edges} == {_member_edge("co:us:SAFE")["edge_id"]}
    assert refusals == [{"symbol": "DUAL", "suite": "baskets", "reason": "etf_conflict",
                         "conflicting_node": "etf:DUAL"}]


def test_suppress_retired_remint_removes_the_company_node_and_its_edges():
    """R-D2B3-4(b) / R-A6 — a re-mint of a node whose latest lifecycle status is
    retired/merged is refused with a typed receipt, never a raise."""
    nodes = [_co_node("co:us:ZOMB", "ZOMB"), _co_node("co:us:SAFE", "SAFE")]
    edges = [_member_edge("co:us:ZOMB"), _member_edge("co:us:SAFE")]
    kept_nodes, kept_edges, refusals = materialize._suppress_conflicts_and_retired(
        nodes, edges, retired_node_ids=frozenset({"co:us:ZOMB"}))
    assert {n["node_id"] for n in kept_nodes} == {"co:us:SAFE"}
    assert {e["edge_id"] for e in kept_edges} == {_member_edge("co:us:SAFE")["edge_id"]}
    assert refusals == [{"symbol": "ZOMB", "suite": "baskets", "reason": "retired_remint",
                         "conflicting_node": "co:us:ZOMB"}]


def test_suppress_is_a_pure_no_op_on_a_clean_generation():
    nodes = [_co_node("co:us:SAFE", "SAFE")]
    edges = [_member_edge("co:us:SAFE")]
    kept_nodes, kept_edges, refusals = materialize._suppress_conflicts_and_retired(
        nodes, edges, retired_node_ids=frozenset())
    assert kept_nodes == nodes and kept_edges == edges and refusals == []


def test_suppress_never_raises_on_a_retired_remint():
    """R-A6, restated as a negative: nothing here may ever raise — a raise inside the
    nightly bake is an outage weapon, not a fence."""
    nodes = [_co_node("co:us:ZOMB", "ZOMB")]
    kept_nodes, kept_edges, refusals = materialize._suppress_conflicts_and_retired(
        nodes, [], retired_node_ids=frozenset({"co:us:ZOMB"}))
    assert kept_nodes == [] and refusals[0]["reason"] == "retired_remint"


# ===========================================================================
# 3. R-A1 mandatory tests (i)/(ii) — two simulated consecutive-day bakes, synthetic
# ===========================================================================

def _doc(basket_id, symbol, *, etf_proxy=None) -> dict:
    return {
        "version": "2026-08-11", "seed_date": "2023-05-09",
        "baskets": {
            basket_id: {
                "name": basket_id, "created": "2023-05-09", "etf_proxy": etf_proxy,
                "members": [{"symbol": symbol, "added": "2023-05-09", "removed": None,
                            "name": symbol}],
            },
        },
    }


@pytest.fixture
def resurrection_tree(tmp_path, monkeypatch):
    """A single-suite tree whose source document keeps listing 'ZOMB' forever — the
    resurrection attack this suppression exists to defeat. The corrected store already
    holds ZOMB retired + its edge annulled; retired_node_ids is what the caller
    (scripts/build_theme_graph.py) would pass in from that lifecycle view."""
    data_root = tmp_path / "data"
    (data_root / "baskets").mkdir(parents=True)
    (data_root / "baskets" / "membership.json").write_text(
        json.dumps(_doc("zombsuite", "ZOMB")), encoding="utf-8")
    xwalk = tmp_path / "theme_crosswalk.yml"
    xwalk.write_text(yaml.safe_dump({"version": 3, "date": "2026-07-09", "themes": []}),
                     encoding="utf-8")
    monkeypatch.setattr(identity, "load_breaks", lambda *a, **k: {})
    monkeypatch.setattr(config, "data_dir", lambda: data_root)

    # Simulate the one-shot correction having already run: ZOMB retired, its open
    # MEMBER_OF edge annulled (valid_to := valid_from — the entity_type_conflict shape).
    zomb_id = "co:us:ZOMB"
    basket_id = "basket:baskets:zombsuite"
    edge_id = materialize.edge_id_for("MEMBER_OF", zomb_id, basket_id, "2023-05-09")
    store.write_node_lifecycle([{
        "schema": "gmi.node_lifecycle/v1", "node_id": zomb_id, "status": "retired",
        "retire_date": "2024-01-01", "merged_into": None, "reason": "entity_type_conflict",
        "evidence": "fixture", "ratified_by": "fixture", "computed_at": "2024-01-01T00:00:00Z",
        "engine_version": store.ENGINE_VERSION,
    }], lane="nightly")
    evrow = {"evidence_id": "ev:0000000000000fff", "kind": "operator_curation",
            "published_at": "2024-01-01", "effective_at": None, "source_ref": "fixture",
            "licensing_internal_ok": True, "licensing_display_ok": True,
            "licensing_redistribution_ok": True, "retention": None,
            "computed_at": "2024-01-01T00:00:00Z", "provider": None, "claim_type": None}
    store.write_evidence([evrow], lane="nightly")
    annulled_edge = {
        "edge_id": edge_id, "type": "MEMBER_OF", "src": zomb_id, "dst": basket_id,
        "valid_from": "2023-05-09", "valid_to": "2023-05-09", "evidence_time": "2023-05-09",
        "belief_time": "2024-01-01", "era": "observed", "source_class": "curated",
        "date_provenance": "curated_changelog", "evidence_refs": ["ev:0000000000000fff"],
        "confidence_basis": "membership_doc.v1", "computed_at": "2024-01-01T00:00:00Z",
        "engine_version": store.ENGINE_VERSION,
    }
    for f in store.RESERVED_EDGE_FIELDS:
        annulled_edge[f] = None
    store.write_edges([annulled_edge], lane="nightly")
    return data_root, xwalk, edge_id, zomb_id


def _retired_ids() -> frozenset[str]:
    lc = store.read_node_lifecycle(latest=True)
    return frozenset(str(n) for n in
                     lc.loc[lc["status"].isin(store.RETIRED_LIKE_STATUSES), "node_id"])


def test_r_a1_i_annulled_edge_stays_closed_across_two_consecutive_day_bakes(resurrection_tree):
    """R-A1 mandatory test (i): the annulled edge stays closed across belief_time=d and
    belief_time=d+1, even though the SOURCE keeps listing the symbol every night."""
    data_root, xwalk, edge_id, zomb_id = resurrection_tree

    day1 = materialize.build(era="observed", belief_time="2024-01-02",
                             computed_at="2024-01-02T00:00:00Z", data_dir=data_root,
                             crosswalk_path=xwalk, retired_node_ids=_retired_ids())
    assert zomb_id not in {n["node_id"] for n in day1.nodes}, (
        "the suppression must remove the node from THIS build's own computed view")
    delta1 = materialize.changed_edges(day1.edges, store.read_edges(latest_belief=True))
    store.write_edges(delta1, lane="nightly")

    day2 = materialize.build(era="observed", belief_time="2024-01-03",
                             computed_at="2024-01-03T00:00:00Z", data_dir=data_root,
                             crosswalk_path=xwalk, retired_node_ids=_retired_ids())
    assert zomb_id not in {n["node_id"] for n in day2.nodes}
    delta2 = materialize.changed_edges(day2.edges, store.read_edges(latest_belief=True))
    store.write_edges(delta2, lane="nightly")

    current = store.read_edges(latest_belief=True)
    row = current[current["edge_id"] == edge_id]
    assert len(row) == 1
    assert row.iloc[0]["valid_to"] == "2023-05-09", (
        "the annulled interval must stand — no resurrection across either bake")


def test_r_a1_ii_changed_edges_proposes_no_row_for_the_corrected_edge_id(resurrection_tree):
    """R-A1 mandatory test (ii): on the day after correction, changed_edges proposes
    NOTHING for the corrected edge_id — the fence is the bake never COMPUTING the row,
    not a write-side no-op."""
    data_root, xwalk, edge_id, zomb_id = resurrection_tree
    view = materialize.build(era="observed", belief_time="2024-01-02",
                             computed_at="2024-01-02T00:00:00Z", data_dir=data_root,
                             crosswalk_path=xwalk, retired_node_ids=_retired_ids())
    delta = materialize.changed_edges(view.edges, store.read_edges(latest_belief=True))
    assert edge_id not in {e["edge_id"] for e in delta}
    assert any(r["reason"] == "retired_remint" and r["conflicting_node"] == zomb_id
              for r in view.company_mint_refusals), (
        "the refusal receipt must be present on the bake that suppressed the re-mint")


def _dual_doc() -> dict:
    """A company member ('DUAL') in one basket AND an etf_proxy of the SAME symbol on
    another basket, in the SAME suite — both mint every night from a LIVE source, with
    no retirement/lifecycle dependency at all. This is rule (a)'s own fence
    (entity-kind conflict), never rule (b) — the two must be tested independently
    (FIX-6, adjudicated review 2026-08-22): the resurrection_tree fixture above only
    ever exercises rule (b)."""
    return {
        "version": "2026-08-11", "seed_date": "2023-05-09",
        "baskets": {
            "dualsuite_a": {
                "name": "dualsuite_a", "created": "2023-05-09", "etf_proxy": None,
                "members": [{"symbol": "DUAL", "added": "2023-05-09", "removed": None,
                            "name": "DUAL"}],
            },
            "dualsuite_b": {
                "name": "dualsuite_b", "created": "2023-05-09", "etf_proxy": "DUAL",
                "members": [],
            },
        },
    }


@pytest.fixture
def etf_conflict_resurrection_tree(tmp_path, monkeypatch):
    """Mirrors ``resurrection_tree`` but for rule (a) — the entity-kind conflict fence
    — instead of rule (b): the source keeps minting BOTH co:us:DUAL (company) and
    etf:DUAL (etf) every night, structurally, with no lifecycle dependency at all."""
    data_root = tmp_path / "data"
    (data_root / "baskets").mkdir(parents=True)
    (data_root / "baskets" / "membership.json").write_text(
        json.dumps(_dual_doc()), encoding="utf-8")
    xwalk = tmp_path / "theme_crosswalk.yml"
    xwalk.write_text(yaml.safe_dump({"version": 3, "date": "2026-07-09", "themes": []}),
                     encoding="utf-8")
    monkeypatch.setattr(identity, "load_breaks", lambda *a, **k: {})
    monkeypatch.setattr(config, "data_dir", lambda: data_root)

    # Simulate the one-shot correction having already run: co:us:DUAL retired
    # (entity_type_conflict), its open MEMBER_OF edge annulled.
    dual_id = "co:us:DUAL"
    basket_id = "basket:baskets:dualsuite_a"
    edge_id = materialize.edge_id_for("MEMBER_OF", dual_id, basket_id, "2023-05-09")
    store.write_node_lifecycle([{
        "schema": "gmi.node_lifecycle/v1", "node_id": dual_id, "status": "retired",
        "retire_date": "2024-01-01", "merged_into": None, "reason": "entity_type_conflict",
        "evidence": "fixture", "ratified_by": "fixture", "computed_at": "2024-01-01T00:00:00Z",
        "engine_version": store.ENGINE_VERSION,
    }], lane="nightly")
    evrow = {"evidence_id": "ev:0000000000000eee", "kind": "operator_curation",
            "published_at": "2024-01-01", "effective_at": None, "source_ref": "fixture",
            "licensing_internal_ok": True, "licensing_display_ok": True,
            "licensing_redistribution_ok": True, "retention": None,
            "computed_at": "2024-01-01T00:00:00Z", "provider": None, "claim_type": None}
    store.write_evidence([evrow], lane="nightly")
    annulled_edge = {
        "edge_id": edge_id, "type": "MEMBER_OF", "src": dual_id, "dst": basket_id,
        "valid_from": "2023-05-09", "valid_to": "2023-05-09", "evidence_time": "2023-05-09",
        "belief_time": "2024-01-01", "era": "observed", "source_class": "curated",
        "date_provenance": "curated_changelog", "evidence_refs": ["ev:0000000000000eee"],
        "confidence_basis": "membership_doc.v1", "computed_at": "2024-01-01T00:00:00Z",
        "engine_version": store.ENGINE_VERSION,
    }
    for f in store.RESERVED_EDGE_FIELDS:
        annulled_edge[f] = None
    store.write_edges([annulled_edge], lane="nightly")
    return data_root, xwalk, edge_id, dual_id


def test_r_a1_etf_conflict_fence_holds_across_two_consecutive_day_bakes(
        etf_conflict_resurrection_tree):
    """FIX-6 (adjudicated review 2026-08-22) — rule (a), the ENTITY-KIND CONFLICT
    fence, is never exercised by the R-A1 (i)/(ii) tests above (they only drive rule
    (b), retired-remint). Structurally identical claim, independently proven: on BOTH
    of two consecutive days, the refusal receipt is present with reason=etf_conflict,
    no co:us:DUAL node is computed, no edge is src'd from it, etf:DUAL + its TRACKS
    edge ARE computed, and on day 2 changed_edges proposes nothing for the corrected
    edge_id."""
    data_root, xwalk, edge_id, dual_id = etf_conflict_resurrection_tree

    for day, computed_at in (("2024-01-02", "2024-01-02T00:00:00Z"),
                             ("2024-01-03", "2024-01-03T00:00:00Z")):
        view = materialize.build(era="observed", belief_time=day, computed_at=computed_at,
                                 data_dir=data_root, crosswalk_path=xwalk,
                                 retired_node_ids=_retired_ids())
        node_ids = {n["node_id"] for n in view.nodes}
        assert dual_id not in node_ids, f"{day}: the conflicting company must not mint"
        assert "etf:DUAL" in node_ids, f"{day}: the lawful etf node must still mint"
        assert not any(e["src"] == dual_id for e in view.edges), (
            f"{day}: no edge may be src'd from the suppressed company node")
        assert any(e["src"] == "etf:DUAL" and e["type"] == "TRACKS" for e in view.edges), (
            f"{day}: the lawful TRACKS edge must still compute")
        assert any(r["reason"] == "etf_conflict" and r["conflicting_node"] == "etf:DUAL"
                  for r in view.company_mint_refusals), (
            f"{day}: the etf_conflict refusal receipt must be present")

        delta = materialize.changed_edges(view.edges, store.read_edges(latest_belief=True))
        assert edge_id not in {e["edge_id"] for e in delta}, (
            f"{day}: changed_edges must propose nothing for the corrected edge_id")
        store.write_edges(delta, lane="nightly")


# ===========================================================================
# 4. Correction script — target discovery, ABX generality, idempotency, Data OS fence
# ===========================================================================

def test_identity_break_targets_skips_an_absent_prior_node_abx_shape():
    """Matrix 5 — ABX: the prior node does not exist in nodes.parquet, so the
    correction script mints NOTHING for it — a no-op, not an error."""
    nodes_df = pd.DataFrame([{"node_id": "co:us:GOLD"}])
    breaks_rows = [
        {"symbol": "GOLD", "market": "us", "break_date": "2025-12-02",
         "prior_node_retired_as": "co:us:GOLD", "ratified_by": "x", "ratified_at": "2026-08-14"},
        {"symbol": "ABX", "market": "us", "break_date": "2025-12-30",
         "prior_node_retired_as": "co:us:ABX", "ratified_by": "x", "ratified_at": "2026-08-14"},
    ]
    targets = corr.identity_break_targets(nodes_df, breaks_rows)
    assert [t["node_id"] for t in targets] == ["co:us:GOLD"]


def test_entity_conflict_targets_finds_only_the_symbol_collision():
    nodes_df = pd.DataFrame([
        {"node_id": "co:us:DUAL", "kind": "company",
         "external_ids": json.dumps({"symbol": "DUAL"})},
        {"node_id": "co:us:SAFE", "kind": "company",
         "external_ids": json.dumps({"symbol": "SAFE"})},
        {"node_id": "etf:DUAL", "kind": "etf",
         "external_ids": json.dumps({"symbol": "DUAL"})},
    ])
    targets = corr.entity_conflict_targets(nodes_df)
    assert [t["node_id"] for t in targets] == ["co:us:DUAL"]


def test_compute_correction_is_idempotent_against_an_already_retired_node():
    nodes_df = pd.DataFrame([{"node_id": "co:us:GOLD"}])
    breaks_rows = [{"symbol": "GOLD", "market": "us", "break_date": "2025-12-02",
                    "prior_node_retired_as": "co:us:GOLD", "ratified_by": "x",
                    "ratified_at": "2026-08-14"}]
    lifecycle_rows, edge_rows, evidence_rows, receipt = corr.compute_correction(
        nodes_df=nodes_df, live_edges=pd.DataFrame(columns=list(store.EDGE_COLUMNS)),
        breaks_rows=breaks_rows, already_retired={"co:us:GOLD"},
        today="2026-08-22", computed_at="2026-08-22T00:00:00Z")
    assert lifecycle_rows == [] and edge_rows == [] and evidence_rows == []
    assert receipt["skipped_already_retired"] == ["co:us:GOLD"]


def test_correction_script_imports_nothing_under_data_reference():
    """§8 / commission OUT OF SCOPE — a static, test-guarded invariant: the correction
    script may not import engine.theme_graph.materialize/identity_resolution (which
    transitively read data/reference/) or scripts.build_security_master. Checked over
    the CODE only (an AST module docstring may narrate the invariant in prose — that is
    documentation, not an import)."""
    import ast

    path = ROOT / "scripts" / "correct_gmi_identity_lineage.py"
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))
    body = tree.body[1:] if (tree.body and isinstance(tree.body[0], ast.Expr)
                             and isinstance(tree.body[0].value, ast.Constant)
                             and isinstance(tree.body[0].value.value, str)) else tree.body
    code_only = ast.unparse(ast.Module(body=body, type_ignores=[]))

    assert "data/reference" not in code_only
    assert "build_security_master" not in code_only
    assert "lib.dataos" not in code_only

    imported_modules = {
        alias.name for node in ast.walk(tree) for alias in getattr(node, "names", [])
        if isinstance(node, ast.Import)
    } | {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    forbidden = {"engine.theme_graph.materialize", "engine.theme_graph.identity_resolution",
                "scripts.build_security_master", "lib.dataos", "lib.dataos.identity"}
    assert not (imported_modules & forbidden), imported_modules & forbidden
    assert not hasattr(corr, "build_security_master")


def test_correction_script_writes_only_via_allow_backfill_never_env_lane():
    """The bypass is the explicit argument, never an environment default (store.py's
    own house law) — grep the script for the sanctioned shape."""
    src = (ROOT / "scripts" / "correct_gmi_identity_lineage.py").read_text(encoding="utf-8")
    assert "allow_backfill=True" in src
    assert "COLLECT_LANE" not in src and "US_LANE" not in src


# ===========================================================================
# 5. Guard — dedicated pytest-level pins for the two new §6 invariants (matrix 11)
# (the full breach-class sweep, incl. missing-evidence/backdating/no-ratified_at, is
# exercised via scripts/check_theme_graph_contracts.py's own selftest(), which
# tests/test_theme_graph_contracts.py::test_the_guards_selftest_passes already runs)
# ===========================================================================

def test_guard_breach_retirement_invariant_fires_on_a_canonical_prior(tmp_path):
    root = tmp_path / "store"
    root.mkdir()
    nodes = [{"node_id": "co:us:ZOMB", "kind": "company", "name_en": None, "name_zh": None,
             "market_scope": "us", "tier": None, "status": "canonical", "merged_into": None,
             "birth_date": None, "retire_date": None, "identity_epoch": 1,
             "external_ids": "{}", "provenance": "fixture", "computed_at": STAMP_A,
             "engine_version": store.ENGINE_VERSION}]
    pd.DataFrame(nodes).reindex(columns=list(store.NODE_COLUMNS)).to_parquet(
        root / "nodes.parquet", index=False)
    pd.DataFrame(columns=list(store.EDGE_COLUMNS)).to_parquet(root / "edges.parquet", index=False)
    pd.DataFrame(columns=list(store.EVIDENCE_COLUMNS)).to_parquet(
        root / "evidence.parquet", index=False)
    bfile = tmp_path / "breaks.yml"
    bfile.write_text(
        "breaks:\n  - symbol: ZOMB\n    market: us\n    break_date: '2024-01-01'\n"
        "    prior_node_retired_as: co:us:ZOMB\n    new_epoch: 2\n"
        "    evidence: fixture\n    ratified_by: fixture\n"
        "    ratified_at: '2024-01-02'\n", encoding="utf-8")
    breaches, _notices = guard.audit(root, bfile)
    assert any("break-retirement invariant" in b for b in breaches)


# ===========================================================================
# 6. Matrix 4 — epoch routing, driven from the REAL registry file
# ===========================================================================

def test_epoch_routing_from_the_real_registry_gold_and_abx():
    """A synthetic membership doc naming GOLD (market us) mints ONLY co:us:GOLD#2; same
    for ABX->co:us:ABX#2. Driven from the REAL config/theme_graph_identity_breaks.yml,
    no literal epoch numbers hand-copied here."""
    if not REAL_BREAKS_FILE.exists():
        pytest.skip("config/theme_graph_identity_breaks.yml not checked out")
    breaks = identity.load_breaks(REAL_BREAKS_FILE)
    assert breaks.get(("us", "GOLD"), 1) >= 2
    assert breaks.get(("us", "ABX"), 1) >= 2
    assert identity.company_node_id("baskets", "GOLD", breaks=breaks) == \
        f"co:us:GOLD#{breaks[('us', 'GOLD')]}"
    assert identity.company_node_id("baskets", "ABX", breaks=breaks) == \
        f"co:us:ABX#{breaks[('us', 'ABX')]}"


def test_real_breaks_registry_rows_all_carry_a_parseable_ratified_at():
    """R-A9/R-A4 — every row in the REAL registry must satisfy the fail-closed law the
    guard now enforces (a red here would mean the guard reds on the committed store)."""
    if not REAL_BREAKS_FILE.exists():
        pytest.skip("config/theme_graph_identity_breaks.yml not checked out")
    doc = yaml.safe_load(REAL_BREAKS_FILE.read_text(encoding="utf-8")) or {}
    from datetime import date
    for row in doc.get("breaks") or []:
        at = row.get("ratified_at")
        assert at, f"{row.get('symbol')}: missing ratified_at"
        date.fromisoformat(str(at))


# ===========================================================================
# 7. Live-store assertions against the ACTUAL corrected store — matrix 1, 2, 6, 8, 9, 10
#
# FIX-1 (adjudicated review 2026-08-22, MAJOR): the previous versions of these tests
# compared the working tree against `git show HEAD:...` — on THIS branch HEAD IS the
# correction commit, so that comparison is TAUTOLOGICAL (it proves only "the tree is
# not dirty relative to its own last commit", not that anything survived a correction).
# It is also fragile in a shallow/blobless CI clone. Every check below instead pins
# VERBATIM values on the append-only rows themselves — facts that hold no matter which
# commit HEAD happens to be, and that fail loudly if the write-once law is ever broken
# in place. `subprocess`/git usage is gone from this file entirely.
# ===========================================================================

#: GOLD and IBIT were minted in the same natural nightly generation — verified
#: directly against the committed store (both node rows carry this exact computed_at).
ORIGINAL_MINT_AT = "2026-08-11T12:12:07Z"
ORIGINAL_BELIEF_TIME = "2026-08-11"
GOLD_EDGE_ID = "member_of:co:us:GOLD->basket:baskets:gold_miners@2023-05-09"
IBIT_EDGE_ID = "member_of:co:us:IBIT->basket:baskets:crypto_rails@2023-05-09"


@needs_real_store
def test_matrix_1_nodes_parquet_rows_retain_verbatim_original_values():
    """Matrix 1 / FIX-1(a) — the original co:us:GOLD/co:us:IBIT node ROWS retain their
    VERBATIM original values after correction: status=canonical, identity_epoch=1,
    retire_date=None, merged_into=None, and the exact original mint computed_at — the
    write-once law means these fields never move. Pinned directly, never via a git
    comparison that would be tautological on this branch."""
    nodes = store.read_nodes(current=False)
    for nid in ("co:us:GOLD", "co:us:IBIT"):
        row = nodes[nodes["node_id"] == nid]
        if row.empty:
            pytest.skip(f"{nid} not present in this checkout's committed store")
        r = row.iloc[0]
        assert r["status"] == "canonical"
        assert r["identity_epoch"] == 1
        assert pd.isna(r["retire_date"])
        assert pd.isna(r["merged_into"])
        assert r["computed_at"] == ORIGINAL_MINT_AT, (
            f"{nid}'s node row must still carry its ORIGINAL mint computed_at "
            f"({ORIGINAL_MINT_AT!r}) verbatim — any other value means the write-once "
            f"row moved")


@needs_real_store
def test_matrix_2_and_fix1b_edge_history_retains_both_belief_rows_verbatim():
    """Matrix 2 / FIX-1(b) — for EACH corrected edge_id, the full history
    (latest_belief=False) contains BOTH the original open-belief row with its VERBATIM
    original values (proving it was never edited in place) AND a later correction row
    (proving the fix was an APPEND) — plus the ordinary current-view assertions matrix
    2 already made (co:us:B's edge stays open; the current view shows GOLD's belief
    CLOSED). Never a git comparison."""
    history = store.read_edges(latest_belief=False)
    if history.empty:
        pytest.skip("no committed edges in this checkout")

    gold_rows = history[history["edge_id"] == GOLD_EDGE_ID]
    if gold_rows.empty:
        pytest.skip("GOLD's gold_miners edge not present in this checkout")
    gold_original = gold_rows[gold_rows["belief_time"] == ORIGINAL_BELIEF_TIME]
    assert len(gold_original) == 1, "the ORIGINAL belief row must survive untouched"
    g = gold_original.iloc[0]
    assert g["valid_from"] == "2023-05-09" and pd.isna(g["valid_to"])
    assert g["era"] == "reconstruction" and g["source_class"] == "curated"
    assert g["computed_at"] == ORIGINAL_MINT_AT

    gold_correction = gold_rows[gold_rows["belief_time"] != ORIGINAL_BELIEF_TIME]
    assert len(gold_correction) >= 1, "the correction must be an APPEND, not an edit"
    assert (gold_correction["valid_to"] == "2025-12-02").all(), (
        "GOLD's correction is a TRUNCATION at the ratified break_date, verbatim")

    ibit_rows = history[history["edge_id"] == IBIT_EDGE_ID]
    if not ibit_rows.empty:
        ibit_original = ibit_rows[ibit_rows["belief_time"] == ORIGINAL_BELIEF_TIME]
        assert len(ibit_original) == 1, "IBIT's ORIGINAL belief row must survive untouched"
        i = ibit_original.iloc[0]
        assert i["valid_from"] == "2023-05-09" and pd.isna(i["valid_to"])
        assert i["computed_at"] == ORIGINAL_MINT_AT

        ibit_correction = ibit_rows[ibit_rows["belief_time"] != ORIGINAL_BELIEF_TIME]
        assert len(ibit_correction) >= 1
        c = ibit_correction.iloc[0]
        assert c["valid_to"] == c["valid_from"], (
            "IBIT's correction is an ANNULMENT (valid_to == valid_from), deliberately "
            "distinct from GOLD's truncation")

    # The ordinary current-view claim matrix 2 makes: the CORRECTION row wins (later
    # belief), and co:us:B's own gold_miners edge stays open throughout.
    current = store.read_edges(latest_belief=True)
    gold_current = current[current["edge_id"] == GOLD_EDGE_ID]
    assert not gold_current.empty and gold_current.iloc[0]["valid_to"] == "2025-12-02", (
        "the current view must show the CLOSED belief"
    )
    b_current = current[(current["src"] == "co:us:B")
                        & (current["dst"] == "basket:baskets:gold_miners")]
    assert not b_current.empty and pd.isna(b_current.iloc[0]["valid_to"])


@needs_real_store
def test_matrix_6_no_edge_or_lifecycle_row_links_b_to_any_gold_node():
    """Matrix 6 — two ratified epochs never merge: nothing links co:us:B to any
    GOLD-symbol node."""
    edges = store.read_edges(latest_belief=False)
    cross = edges[((edges["src"] == "co:us:B") & edges["dst"].str.contains("GOLD", na=False))
                 | ((edges["dst"] == "co:us:B") & edges["src"].str.contains("GOLD", na=False))]
    assert cross.empty
    lifecycle = store.read_node_lifecycle(latest=False)
    if not lifecycle.empty:
        gold_rows = lifecycle[lifecycle["node_id"].str.contains("GOLD", na=False)]
        assert not gold_rows["merged_into"].astype(str).str.contains("co:us:B", na=False).any()


@needs_real_store
def test_matrix_8_etf_ibit_and_its_two_tracks_edges_are_untouched():
    """Matrix 8 / FIX-5 (adjudicated review 2026-08-22) — etf:IBIT node + BOTH of its
    exact TRACKS edges, verbatim, not merely 'at least one': to basket:baskets:crypto
    (valid_from=2026-06-15) and basket:baskets:crypto_rails (valid_from=2026-07-03),
    both open (valid_to null) — a weaker '>= 1' assertion would pass even if one of the
    two lawful edges had been silently dropped."""
    nodes = store.read_nodes(current=False)
    etf_row = nodes[nodes["node_id"] == "etf:IBIT"]
    if etf_row.empty:
        pytest.skip("etf:IBIT not present in this checkout's committed store")
    assert etf_row.iloc[0]["kind"] == "etf"

    tracks = store.read_edges(latest_belief=True)
    ibit_tracks = tracks[(tracks["src"] == "etf:IBIT") & (tracks["type"] == "TRACKS")]
    by_dst = {str(r["dst"]): r for _, r in ibit_tracks.iterrows()}
    assert set(by_dst) == {"basket:baskets:crypto", "basket:baskets:crypto_rails"}, (
        f"exactly two TRACKS edges expected, got {sorted(by_dst)}")
    assert by_dst["basket:baskets:crypto"]["valid_from"] == "2026-06-15"
    assert by_dst["basket:baskets:crypto_rails"]["valid_from"] == "2026-07-03"
    assert all(pd.isna(r["valid_to"]) for r in by_dst.values()), (
        "both lawful TRACKS relationships must stay open")


@needs_real_store
def test_matrix_9_identity_resolution_history_is_append_only_untouched():
    """Matrix 9 / FIX-1 — sidecar laundering attack, proven WITHOUT git: the D2A
    identity_resolution side-car is append-only and re-derived every build, so 'the
    correction never wrote it' is proven by checking the HISTORICAL generations still
    carry their old states — a deletion/edit would show up as a MISSING row, not merely
    a byte difference against an arbitrary git ref."""
    idres = store.read_identity_resolution(latest=False)
    if idres.empty:
        pytest.skip("identity_resolution.parquet not present")
    for nid, expected_states in (("co:us:GOLD", {"DEFERRED_IDENTITY_EXCEPTION"}),
                                 ("co:us:B", {"DEFERRED_IDENTITY_EXCEPTION"}),
                                 ("co:us:IBIT", {"ENTITY_TYPE_CONFLICT"})):
        rows = idres[idres["node_id"] == nid]
        if rows.empty:
            continue  # this node's history predates the sidecar, or checkout is sparse
        seen_states = set(rows["resolution_state"].astype(str))
        assert seen_states & expected_states, (
            f"{nid}'s HISTORICAL identity_resolution generations must still show "
            f"{expected_states} among {seen_states} — the correction script never "
            f"writes this table, so no historical row may vanish or change value")


@needs_real_store
def test_matrix_10_blast_radius_node_lifecycle_and_edge_history_deltas():
    """Matrix 10 / FIX-1 — exact blast radius, proven WITHOUT git: node_lifecycle.
    parquet carries exactly 2 rows (GOLD, IBIT — not ABX), and the edge history carries
    EXACTLY 2 more rows than there are distinct edge_ids — i.e. only the two corrected
    edges have ever received a second belief row. A wider blast radius (a third edge
    with 2+ belief rows, or a nodes.parquet row count that moved) would break this
    delta even without a git baseline to diff against."""
    lifecycle = store.read_node_lifecycle(latest=True)
    if lifecycle.empty:
        pytest.skip("correction not yet applied in this checkout")
    assert len(lifecycle) == 2
    assert set(lifecycle["node_id"]) == {"co:us:GOLD", "co:us:IBIT"}
    assert set(lifecycle["status"]) == {"retired"}

    history = store.read_edges(latest_belief=False)
    current = store.read_edges(latest_belief=True)
    assert len(history) - len(current) == 2, (
        f"expected exactly 2 more historical rows than distinct edge_ids "
        f"({len(history)} vs {len(current)}) — only GOLD's and IBIT's edges may carry "
        f"a second belief row")
    multi_belief = history.groupby("edge_id").size()
    assert set(multi_belief[multi_belief > 1].index) == {GOLD_EDGE_ID, IBIT_EDGE_ID}


# ===========================================================================
# 8. Matrix 13 — first production use of the closure lineage (FIX-2, adjudicated
# review 2026-08-22, MAJOR: this matrix item had NO test at all). A repo sweep
# (review 2026-08-22) confirmed zero equality assumptions on edges==edges_latest_belief
# anywhere in tests/, scripts/, or engine/ — this pins the first DIVERGENT production
# use, using only append-only-lawful assertions (no moving totals: never a hardcoded
# 8,292/8,294-style row count, which would go stale on the next natural nightly).
# ===========================================================================

@needs_real_store
def test_matrix_13_edges_and_edges_latest_belief_first_lawful_divergence():
    """Matrix 13 — after D2B3, edges.parquet > edges_latest_belief for the first time
    in production. Pinned structurally: total rows strictly exceed distinct edge_ids;
    the two corrected edge_ids each carry >= 2 belief rows; the latest-belief view
    still returns EXACTLY ONE row per edge_id and, for the two corrected ids, that row
    IS the correction (later belief wins, never the stale original); and the guard —
    which reads both the raw and the collapsed view — reports no breach on this now
    lawfully-divergent store."""
    history = store.read_edges(latest_belief=False)
    current = store.read_edges(latest_belief=True)
    if history.empty:
        pytest.skip("no committed edges in this checkout")

    assert len(history) > len(current), (
        "edges.parquet must strictly exceed edges_latest_belief — the first "
        "production use of the closure lineage")
    assert current["edge_id"].is_unique, (
        "the latest-belief view must return exactly one row per edge_id")

    for eid, expected_valid_to_is_valid_from in ((GOLD_EDGE_ID, False), (IBIT_EDGE_ID, True)):
        rows = history[history["edge_id"] == eid]
        if rows.empty:
            continue
        assert len(rows) >= 2, f"{eid} must carry >= 2 belief rows"
        row = current[current["edge_id"] == eid]
        assert len(row) == 1
        r = row.iloc[0]
        if expected_valid_to_is_valid_from:
            assert r["valid_to"] == r["valid_from"], (
                f"{eid}: the current view must be the ANNULMENT correction, not the "
                f"stale original open row")
        else:
            assert not pd.isna(r["valid_to"]), (
                f"{eid}: the current view must be the TRUNCATION correction, not the "
                f"stale original open row")

    breaches, _notices = guard.audit(REAL_STORE_DIR, REAL_BREAKS_FILE)
    assert breaches == [], (
        f"the guard must report no breach on a store where edges > "
        f"edges_latest_belief for the first time: {breaches}")
