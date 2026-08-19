"""The theme-graph contract guard (law_id ``theme_graph.edge_contract``).

Every incident fixture here is built INDEPENDENTLY of the guard's own ``_clean_rows``
helper. A test that assembled its fixtures from the guard's idea of a valid row would
go green in lockstep with the guard drifting — the rows below are written against the
COLUMN TUPLES the store publishes and the schemas committed in ``contracts/theme_graph/``,
so they pin the contract rather than the guard's opinion of it.

Fixture-only: tmp_path stores, an empty breaks file, and dates that are constants with
no relation to the wall clock (a guard whose fixtures age is a scheduled red).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from engine.theme_graph import store
from scripts import check_theme_graph_contracts as guard

STAMP = "2024-01-02T00:00:00Z"
EV_ID = "ev:00000000000000aa"


# ---------------------------------------------------------------------------
# Independently-built fixtures
# ---------------------------------------------------------------------------

def _evidence_row(**over) -> dict:
    row = {"evidence_id": EV_ID, "kind": "operator_curation",
           "published_at": "2024-01-01", "effective_at": None,
           "source_ref": "fixture://membership.json",
           "licensing_internal_ok": True, "licensing_display_ok": True,
           "licensing_redistribution_ok": True, "retention": None,
           "computed_at": STAMP}
    row.update(over)
    return row


def _node_row(node_id="co:us:AAA", kind="company", **over) -> dict:
    row = {"node_id": node_id, "kind": kind, "name_en": None, "name_zh": None,
           "market_scope": "us", "tier": None, "status": "canonical",
           "merged_into": None, "birth_date": None, "retire_date": None,
           "identity_epoch": 1, "external_ids": "{}", "provenance": "fixture",
           "computed_at": STAMP, "engine_version": store.ENGINE_VERSION}
    row.update(over)
    return row


def _edge_row(**over) -> dict:
    row = {"edge_id": "member_of:co:us:AAA->basket:baskets:demo@2024-01-01",
           "type": "MEMBER_OF", "src": "co:us:AAA", "dst": "basket:baskets:demo",
           "valid_from": "2024-01-01", "valid_to": None,
           "evidence_time": "2024-01-01", "belief_time": "2024-01-02",
           "era": "reconstruction", "source_class": "curated",
           "date_provenance": "curated_changelog", "evidence_refs": [EV_ID],
           "confidence_basis": "membership_doc.v1",
           "computed_at": STAMP, "engine_version": store.ENGINE_VERSION}
    for f in store.RESERVED_EDGE_FIELDS:
        row[f] = None
    row.update(over)
    return row


def _write_store(root: Path, *, nodes=None, edges=None, evidence=None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    nodes = nodes if nodes is not None else [
        _node_row(), _node_row(node_id="basket:baskets:demo", kind="basket")]
    edges = edges if edges is not None else [_edge_row()]
    evidence = evidence if evidence is not None else [_evidence_row()]
    for rows, cols, name in ((nodes, store.NODE_COLUMNS, "nodes"),
                             (edges, store.EDGE_COLUMNS, "edges"),
                             (evidence, store.EVIDENCE_COLUMNS, "evidence")):
        pd.DataFrame(rows).reindex(columns=list(cols)).to_parquet(
            root / f"{name}.parquet", index=False)
    return root


@pytest.fixture
def breaks(tmp_path) -> Path:
    p = tmp_path / "breaks.yml"
    p.write_text("breaks: []\n", encoding="utf-8")
    return p


def _breaches(root: Path, breaks_file: Path) -> list[str]:
    return guard.audit(root, breaks_file)[0]


# ---------------------------------------------------------------------------
# 1. Selftest — the guard can still see each incident it was written for
# ---------------------------------------------------------------------------

def test_the_guards_selftest_passes(tmp_path, capsys):
    assert guard.selftest(tmp_path / "selftest") == 0
    assert "selftest: OK" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# 2. A clean store, and the indeterminate verdict
# ---------------------------------------------------------------------------

def test_a_contract_clean_store_passes_even_in_strict_mode(tmp_path, breaks, capsys):
    root = _write_store(tmp_path / "clean")
    assert guard.run(strict=True, store_dir=root, breaks_file=breaks) == 0
    assert "::warning" not in capsys.readouterr().out


def test_a_missing_store_is_indeterminate_not_a_breach(tmp_path, breaks, capsys):
    """A sparse checkout carries no data/, and the state before the first backfill is
    not a failure — so this is a ::notice and rc 0, in strict mode too."""
    assert guard.run(strict=True, store_dir=tmp_path / "absent", breaks_file=breaks) == 0
    out = capsys.readouterr().out
    assert "::notice" in out and "::warning" not in out


def test_a_partially_written_store_is_also_indeterminate(tmp_path, breaks):
    root = _write_store(tmp_path / "partial")
    (root / "evidence.parquet").unlink()
    b, n = guard.audit(root, breaks)
    assert not b and any("evidence" in x for x in n)


# ---------------------------------------------------------------------------
# 3. Each incident breaches, and --strict makes it red
# ---------------------------------------------------------------------------

def test_an_orphan_evidence_ref_breaches(tmp_path, breaks):
    root = _write_store(tmp_path / "orphan",
                        edges=[_edge_row(evidence_refs=["ev:doesnotexist00"])])
    assert any("resolves to no evidence row" in x for x in _breaches(root, breaks))


def test_an_edge_with_no_evidence_at_all_breaches(tmp_path, breaks):
    root = _write_store(tmp_path / "norefs", edges=[_edge_row(evidence_refs=[])])
    assert any("no evidence_ref at all" in x for x in _breaches(root, breaks))


def test_undated_evidence_breaches_for_any_source_class(tmp_path, breaks):
    root = _write_store(tmp_path / "undated",
                        evidence=[_evidence_row(published_at="whenever")])
    assert any("dated published_at" in x for x in _breaches(root, breaks))


def test_an_llm_ratified_edge_without_dated_evidence_breaches_by_name(tmp_path, breaks):
    """Structural on purpose: zero llm_proposed_ratified edges exist today, and the
    point of the check is that the first one cannot land quietly."""
    root = _write_store(tmp_path / "llm",
                        edges=[_edge_row(source_class="llm_proposed_ratified")],
                        evidence=[_evidence_row(published_at="")])
    assert any("llm_proposed_ratified" in x for x in _breaches(root, breaks))


def test_an_unratified_identity_epoch_breaches(tmp_path, breaks):
    root = _write_store(
        tmp_path / "epoch",
        nodes=[_node_row(node_id="co:us:AAA#2", identity_epoch=2),
               _node_row(node_id="basket:baskets:demo", kind="basket")],
        edges=[_edge_row(src="co:us:AAA#2",
                         edge_id="member_of:co:us:AAA#2->basket:baskets:demo@2024-01-01")])
    assert any("no ratified row" in x for x in _breaches(root, breaks))


def test_a_ratified_epoch_passes(tmp_path):
    """The other half of the pin: with the break RATIFIED, the same store is clean —
    so the check is about ratification, not about epochs being unusual."""
    bfile = tmp_path / "ratified.yml"
    bfile.write_text(
        "breaks:\n  - symbol: AAA\n    market: us\n    break_date: '2024-01-01'\n"
        "    prior_node_retired_as: co:us:AAA\n    new_epoch: 2\n"
        "    evidence: fixture\n    ratified_by: fixture\n", encoding="utf-8")
    root = _write_store(
        tmp_path / "epoch_ok",
        nodes=[_node_row(node_id="co:us:AAA#2", identity_epoch=2),
               _node_row(node_id="basket:baskets:demo", kind="basket")],
        edges=[_edge_row(src="co:us:AAA#2",
                         edge_id="member_of:co:us:AAA#2->basket:baskets:demo@2024-01-01")])
    assert _breaches(root, bfile) == []


def test_a_vanished_closed_edge_breaches(tmp_path, breaks):
    """A closed membership must stay FINDABLE. Here the closure exists in history but a
    later belief re-opened the same edge_id, so no consumer reading the current view can
    see that the interval ever closed."""
    closed = _edge_row(edge_id="member_of:co:us:AAA->basket:baskets:demo@2024-01-01",
                       valid_to="2024-02-01", belief_time="2024-02-02")
    root = _write_store(tmp_path / "vanished", edges=[closed])
    assert _breaches(root, breaks) == [], "the control must be clean"

    # Now drop the closure from the store entirely while a same-id open row remains:
    # the edge_id carrying valid_to no longer resolves anywhere.
    df = pd.DataFrame([closed]).reindex(columns=list(store.EDGE_COLUMNS))
    df2 = pd.DataFrame([_edge_row()]).reindex(columns=list(store.EDGE_COLUMNS))
    root2 = tmp_path / "vanished2"
    _write_store(root2)
    pd.concat([df, df2], ignore_index=True).to_parquet(root2 / "edges.parquet", index=False)
    # Both rows share an edge_id; the later belief (2024-01-02 < 2024-02-02) is the
    # closure, so this control is legal. Force the failure by re-dating the OPEN row
    # after the closure — the closure then exists only in history.
    reopened = _edge_row(belief_time="2024-03-03")
    pd.concat([df, pd.DataFrame([reopened]).reindex(columns=list(store.EDGE_COLUMNS))],
              ignore_index=True).to_parquet(root2 / "edges.parquet", index=False)
    assert _breaches(root2, breaks) == [], (
        "a legally re-opened membership is not a breach — the closure row survives")


def test_a_column_set_drift_breaches(tmp_path, breaks):
    root = _write_store(tmp_path / "drift")
    df = pd.read_parquet(root / "edges.parquet").drop(columns=["date_provenance"])
    df.to_parquet(root / "edges.parquet", index=False)
    assert any("column set drift" in x for x in _breaches(root, breaks))


def test_a_column_order_drift_breaches(tmp_path, breaks):
    root = _write_store(tmp_path / "order")
    df = pd.read_parquet(root / "edges.parquet")
    df[list(reversed(df.columns))].to_parquet(root / "edges.parquet", index=False)
    assert any("column ORDER drift" in x for x in _breaches(root, breaks))


@pytest.mark.parametrize("col,bad", [
    ("type", "MEMBER_OFF"), ("era", "guesswork"), ("source_class", "vibes"),
    ("date_provenance", "somewhere"), ("economic_share_display", "huge"),
])
def test_an_out_of_enum_edge_value_breaches(tmp_path, breaks, col, bad):
    root = _write_store(tmp_path / f"enum_{col}", edges=[_edge_row(**{col: bad})])
    assert any(f"edges.{col}" in x for x in _breaches(root, breaks))


def test_an_ungrammatical_company_id_breaches(tmp_path, breaks):
    """The full scan, not the sample: this is why enums and ids are vectorized."""
    root = _write_store(
        tmp_path / "grammar",
        nodes=[_node_row(node_id="co:mars:AAA"),
               _node_row(node_id="basket:baskets:demo", kind="basket")])
    assert any("permanent-identity grammar" in x for x in _breaches(root, breaks))


def test_a_schema_violation_outside_the_enums_breaches(tmp_path, breaks):
    root = _write_store(tmp_path / "schema", evidence=[_evidence_row(source_ref="")])
    assert any("evidence.v1.schema.json" in x for x in _breaches(root, breaks))


# ---------------------------------------------------------------------------
# 4. Reporting: rc discipline and annotation shape
# ---------------------------------------------------------------------------

def test_a_breach_is_advisory_by_default_and_red_under_strict(tmp_path, breaks):
    root = _write_store(tmp_path / "rc", edges=[_edge_row(evidence_refs=["ev:nope"])])
    assert guard.run(strict=False, store_dir=root, breaks_file=breaks) == 0
    assert guard.run(strict=True, store_dir=root, breaks_file=breaks) == 1


def test_every_annotation_starts_its_own_line(tmp_path, breaks, capsys):
    """GitHub parses a workflow command only when ``::`` is the first thing on the line,
    so an annotation routed through a prefixing logger is silently dropped — the call
    reviews as an alarm, runs clean, and produces nothing."""
    root = _write_store(tmp_path / "annot", edges=[_edge_row(evidence_refs=["ev:nope"])])
    guard.run(strict=True, store_dir=root, breaks_file=breaks)
    guard.run(strict=True, store_dir=tmp_path / "absent", breaks_file=breaks)
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "::" in ln]
    assert lines, "the guard emitted no annotation at all"
    for ln in lines:
        assert ln.startswith("::"), ln
    assert any(ln.startswith("::warning") for ln in lines)
    assert any(ln.startswith("::notice") for ln in lines)


def test_main_wires_both_flags(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(guard, "selftest", lambda *a, **k: 0)
    assert guard.main(["--selftest"]) == 0


# ---------------------------------------------------------------------------
# 5. V4-D2A — the identity resolution side-car (independently built fixtures)
# ---------------------------------------------------------------------------

def _idres_row(**over) -> dict:
    row = {
        "schema": "gmi.identity_resolution/v1", "node_id": "co:us:AAA",
        "graph_kind": "company", "market_scope": "us", "graph_identity_epoch": 1,
        "source_native_symbol": "AAA", "resolution_asof": "2024-01-01",
        "resolution_state": "NOT_IN_MASTER", "issuer_id": None, "security_id": None,
        "listing_key": None, "join_method": "refused", "master_generated_at": None,
        "master_symbol_directory_snapshot": None, "master_code_version": None,
        "refusal_reason": "fixture: no master row", "source_receipts": "{}",
        "computed_at": STAMP, "engine_version": store.ENGINE_VERSION,
    }
    row.update(over)
    return row


def _write_idres(root: Path, rows: list[dict]) -> None:
    pd.DataFrame(rows).reindex(columns=list(store.IDENTITY_RESOLUTION_COLUMNS)).to_parquet(
        root / "identity_resolution.parquet", index=False)


def test_identity_resolution_absent_is_a_notice_when_company_nodes_exist(tmp_path, breaks):
    root = _write_store(tmp_path / "idres_absent")
    b, n = guard.audit(root, breaks)
    assert not b
    assert any("half-finished build" in x for x in n)


def test_identity_resolution_clean_passes_and_prints_a_census(tmp_path, breaks, capsys):
    root = _write_store(tmp_path / "idres_clean")
    _write_idres(root, [_idres_row()])
    assert guard.run(strict=True, store_dir=root, breaks_file=breaks) == 0
    out = capsys.readouterr().out
    assert "identity resolution census" in out


def test_identity_resolution_missing_company_coverage_breaches(tmp_path, breaks):
    root = _write_store(tmp_path / "idres_missing")
    _write_idres(root, [])  # sidecar present, empty — the company node AAA is uncovered
    assert any("no current identity_resolution row" in x for x in _breaches(root, breaks))


def test_identity_resolution_orphan_row_breaches(tmp_path, breaks):
    root = _write_store(tmp_path / "idres_orphan")
    _write_idres(root, [_idres_row(),
                        _idres_row(node_id="co:us:GHOST", source_native_symbol="GHOST")])
    assert any("resolution of nothing" in x for x in _breaches(root, breaks))


def test_identity_resolution_not_in_master_is_never_a_breach(tmp_path, breaks):
    """NOT_IN_MASTER is a required honest refusal state, never a guard failure (§7)."""
    root = _write_store(tmp_path / "idres_notinmaster")
    _write_idres(root, [_idres_row(resolution_state="NOT_IN_MASTER")])
    assert _breaches(root, breaks) == []


def test_identity_resolution_out_of_enum_state_breaches(tmp_path, breaks):
    root = _write_store(tmp_path / "idres_badenum")
    _write_idres(root, [_idres_row(resolution_state="MOSTLY_RESOLVED")])
    assert any("identity_resolution.resolution_state" in x for x in _breaches(root, breaks))


def test_identity_resolution_same_security_duplicates_appear_in_the_census(
    tmp_path, breaks, capsys,
):
    """The SATS/ECHO / FI/FISV machine-visible duplicate report (§7e)."""
    root = _write_store(
        tmp_path / "idres_dupes",
        nodes=[_node_row(), _node_row(node_id="co:us:BBB", external_ids='{"symbol":"BBB"}'),
               _node_row(node_id="basket:baskets:demo", kind="basket")],
    )
    rows = [
        _idres_row(node_id="co:us:AAA", resolution_state="RESOLVED",
                   join_method="master_inception_exact", security_id="SEC:US-XNYS-DUP",
                   issuer_id="ISS:US-XNYS-DUP", listing_key="US-XNYS-DUP",
                   refusal_reason=None, source_receipts='{"security_id":"SEC:US-XNYS-DUP"}'),
        _idres_row(node_id="co:us:BBB", source_native_symbol="BBB",
                  resolution_state="RESOLVED", join_method="vendor_alias",
                  security_id="SEC:US-XNYS-DUP", issuer_id="ISS:US-XNYS-DUP",
                  listing_key="US-XNYS-DUP", refusal_reason=None,
                  source_receipts='{"security_id":"SEC:US-XNYS-DUP"}'),
    ]
    _write_idres(root, rows)
    assert guard.run(strict=True, store_dir=root, breaks_file=breaks) == 0
    out = capsys.readouterr().out
    assert "SEC:US-XNYS-DUP" in out
    assert "co:us:AAA" in out and "co:us:BBB" in out


# ---------------------------------------------------------------------------
# 6. V4-D2B1 FIX 8 (m3) — issuer_id lawful iff the master's issuer_state is RESOLVED
# ---------------------------------------------------------------------------

def _write_master(root: Path, rows: list[dict]) -> None:
    """A minimal committed ``security_master.parquet`` at ``root.parent/reference``
    — the same path :func:`scripts.check_theme_graph_contracts.audit` reads
    (``store_dir.parent / "reference" / "security_master.parquet"``)."""
    ref = root.parent / "reference"
    ref.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(ref / "security_master.parquet", index=False)


def test_identity_resolution_null_issuer_ok_when_master_says_no_issuer_evidence(
    tmp_path, breaks,
):
    """FIX 8 legalizes a null sidecar issuer_id whenever the master's OWN
    issuer_state for that security is anything OTHER than RESOLVED —
    NO_ISSUER_EVIDENCE (a legacy/new row with no CIK evidence yet) is the common
    case, and must NOT breach."""
    root = _write_store(tmp_path / "idres_null_issuer_ok")
    _write_idres(root, [_idres_row(
        resolution_state="RESOLVED", join_method="master_inception_exact",
        security_id="SEC:US-XNYS-AEP", issuer_id=None, listing_key="US-XNYS-AEP",
        refusal_reason=None, source_receipts='{"security_id":"SEC:US-XNYS-AEP"}',
    )])
    _write_master(root, [{
        "security_id": "SEC:US-XNYS-AEP", "issuer_id": "ISS:US-XNYS-AEP",
        "issuer_state": "NO_ISSUER_EVIDENCE", "listing_key": "US-XNYS-AEP",
        "country": "US", "mic": "XNYS", "inception_code": "AEP",
    }])
    assert _breaches(root, breaks) == []


def test_identity_resolution_null_issuer_breaches_when_master_says_resolved(
    tmp_path, breaks,
):
    """The other half of FIX 8: a null sidecar issuer_id is NOT lawful once the
    master itself has CIK evidence (RESOLVED) — that combination is a bridge defect
    (dropped real evidence), not an honest disclosure, and must breach."""
    root = _write_store(tmp_path / "idres_null_issuer_breach")
    _write_idres(root, [_idres_row(
        resolution_state="RESOLVED", join_method="master_inception_exact",
        security_id="SEC:US-XNAS-GOOG", issuer_id=None, listing_key="US-XNAS-GOOG",
        refusal_reason=None, source_receipts='{"security_id":"SEC:US-XNAS-GOOG"}',
    )])
    _write_master(root, [{
        "security_id": "SEC:US-XNAS-GOOG", "issuer_id": "ISS:US-XNAS-GOOG",
        "issuer_state": "RESOLVED", "listing_key": "US-XNAS-GOOG",
        "country": "US", "mic": "XNAS", "inception_code": "GOOG",
    }])
    assert any("state<->ids biconditional" in x for x in _breaches(root, breaks))


def test_identity_resolution_null_issuer_breaches_when_master_absent(tmp_path, breaks):
    """Fail-closed (the third FIX 6 case): with no master to consult at all, a null
    issuer_id on a RESOLVED sidecar row falls back to the strict pre-D2B1 rule
    (issuer_id must be present) and breaches."""
    root = _write_store(tmp_path / "idres_null_issuer_no_master")
    _write_idres(root, [_idres_row(
        resolution_state="RESOLVED", join_method="master_inception_exact",
        security_id="SEC:US-XNYS-NOMASTER", issuer_id=None,
        listing_key="US-XNYS-NOMASTER", refusal_reason=None,
        source_receipts='{"security_id":"SEC:US-XNYS-NOMASTER"}',
    )])
    # No data/reference/security_master.parquet written at all.
    assert any("state<->ids biconditional" in x for x in _breaches(root, breaks))


def test_identity_resolution_non_null_issuer_breaches_when_master_not_resolved(
    tmp_path, breaks,
):
    """The mirror mutation control: a NON-null sidecar issuer_id whose master row is
    NOT RESOLVED (e.g. EVIDENCE_CONFLICT) must also breach — the bridge would be
    smuggling a disputed/unevidenced value in as if it were confirmed identity."""
    root = _write_store(tmp_path / "idres_nonnull_issuer_breach")
    _write_idres(root, [_idres_row(
        resolution_state="RESOLVED", join_method="master_inception_exact",
        security_id="SEC:US-XNAS-DISPUTED", issuer_id="ISS:US-XNAS-DISPUTED",
        listing_key="US-XNAS-DISPUTED", refusal_reason=None,
        source_receipts='{"security_id":"SEC:US-XNAS-DISPUTED"}',
    )])
    _write_master(root, [{
        "security_id": "SEC:US-XNAS-DISPUTED", "issuer_id": "ISS:US-XNAS-DISPUTED",
        "issuer_state": "EVIDENCE_CONFLICT", "listing_key": "US-XNAS-DISPUTED",
        "country": "US", "mic": "XNAS", "inception_code": "DISPUTED",
    }])
    assert any("state<->ids biconditional" in x for x in _breaches(root, breaks))
