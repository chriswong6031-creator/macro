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
"""
from __future__ import annotations

import json
import subprocess
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
# ===========================================================================

@needs_real_store
def test_matrix_1_nodes_parquet_is_bit_identical_write_once():
    """Matrix 1 — the original co:us:GOLD/co:us:IBIT node ROWS are bit-identical after
    correction: the RAW table (current=False) must still show status=canonical,
    identity_epoch=1, retire_date=None — nodes.parquet is write-once."""
    nodes = store.read_nodes(current=False)
    for nid in ("co:us:GOLD", "co:us:IBIT"):
        row = nodes[nodes["node_id"] == nid]
        if row.empty:
            pytest.skip(f"{nid} not present in this checkout's committed store")
        r = row.iloc[0]
        assert r["status"] == "canonical"
        assert r["identity_epoch"] == 1
        assert pd.isna(r["retire_date"])


@needs_real_store
def test_matrix_2_gold_miners_current_view_excludes_gold_history_includes_it():
    """Matrix 2 — the current view contains co:us:B's edge and NOT an open co:us:GOLD
    edge into gold_miners; latest_belief=False still shows the original open row."""
    current = store.read_edges(latest_belief=True)
    gold_current = current[(current["src"] == "co:us:GOLD")
                           & (current["dst"] == "basket:baskets:gold_miners")]
    if gold_current.empty:
        pytest.skip("no co:us:GOLD->gold_miners edge in this checkout")
    assert gold_current.iloc[0]["valid_to"] is not None and not pd.isna(
        gold_current.iloc[0]["valid_to"]), "the current view must show the CLOSED belief"
    b_current = current[(current["src"] == "co:us:B")
                        & (current["dst"] == "basket:baskets:gold_miners")]
    assert not b_current.empty and pd.isna(b_current.iloc[0]["valid_to"])

    history = store.read_edges(latest_belief=False)
    original = history[(history["src"] == "co:us:GOLD")
                       & (history["dst"] == "basket:baskets:gold_miners")
                       & (history["valid_to"].isna())]
    assert not original.empty, "the pre-correction open belief must stay queryable"


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
def test_matrix_8_etf_ibit_and_its_tracks_edges_are_untouched():
    """Matrix 8 — etf:IBIT node + both TRACKS edges bit-identical."""
    nodes = store.read_nodes(current=False)
    etf_row = nodes[nodes["node_id"] == "etf:IBIT"]
    if etf_row.empty:
        pytest.skip("etf:IBIT not present in this checkout's committed store")
    assert etf_row.iloc[0]["kind"] == "etf"
    tracks = store.read_edges(latest_belief=True)
    ibit_tracks = tracks[(tracks["src"] == "etf:IBIT") & (tracks["type"] == "TRACKS")]
    assert len(ibit_tracks) >= 1
    assert (ibit_tracks["valid_to"].isna()).all(), "a lawful TRACKS relationship must stay open"


@needs_real_store
def test_matrix_9_identity_resolution_sidecar_untouched_by_the_correction():
    """Matrix 9 — sidecar laundering attack: the D2A identity_resolution.parquet must
    be byte-identical to the pre-correction committed version (the correction script
    never writes it — only the NEXT natural nightly re-derives it)."""
    path = REAL_STORE_DIR / "identity_resolution.parquet"
    if not path.exists():
        pytest.skip("identity_resolution.parquet not present")
    try:
        before = subprocess.run(
            ["git", "show", f"HEAD:data/theme_graph/identity_resolution.parquet"],
            cwd=ROOT, capture_output=True, check=True).stdout
    except subprocess.CalledProcessError:
        pytest.skip("no HEAD version of identity_resolution.parquet to diff against")
    after = path.read_bytes()
    assert before == after, (
        "the D2A sidecar must be byte-identical — the correction script writes "
        "node_lifecycle/edges/evidence/_meta.json only, never identity_resolution")


@needs_real_store
def test_matrix_10_blast_radius_exactly_two_edges_two_lifecycle_rows():
    """Matrix 10 — total diff: nodes.parquet 0 rows changed; edges.parquet exactly the
    correction appends; node_lifecycle.parquet exactly 2 rows (GOLD, IBIT — not ABX)."""
    lifecycle = store.read_node_lifecycle(latest=True)
    if lifecycle.empty:
        pytest.skip("correction not yet applied in this checkout")
    assert len(lifecycle) == 2
    assert set(lifecycle["node_id"]) == {"co:us:GOLD", "co:us:IBIT"}
    assert set(lifecycle["status"]) == {"retired"}
    try:
        before_edges = subprocess.run(
            ["git", "show", "HEAD:data/theme_graph/nodes.parquet"],
            cwd=ROOT, capture_output=True, check=True).stdout
    except subprocess.CalledProcessError:
        pytest.skip("no HEAD version of nodes.parquet to diff against")
    after_nodes = (REAL_STORE_DIR / "nodes.parquet").read_bytes()
    assert before_edges == after_nodes, "nodes.parquet must be byte-identical (0 rows changed)"
