"""tests/test_check_entity_thesis_registry.py — unit tests for the ETM integrity gate.

All tests use tmp_path fixtures with synthetic artifacts; they never read live data/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from engine.neuralweb.entity_thesis_mechanism_registry import (  # noqa: E402
    AUTHORITY_BLOCK,
    SCHEMA,
)
from scripts.check_entity_thesis_registry import check, selftest  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _write_artifact(tmp_path: Path, artifact: dict) -> Path:
    p = tmp_path / "data" / "neuralweb" / "entity_thesis_mechanism_registry.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(artifact), encoding="utf-8")
    return p


def _clean() -> dict:
    """Minimal artifact that passes all checks."""
    return {
        "schema": SCHEMA,
        "is_context_only": True,
        "authority": AUTHORITY_BLOCK,
        "rows": {},
        "edges": [],
        "trial_families": {},
        "possible_duplicates": [],
        "counts": {"rows_by_type": {}, "edges_by_kind": {}},
    }


# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------

class TestSelftest:
    def test_selftest_exits_zero(self):
        rc = selftest()
        assert rc == 0, "selftest() returned non-zero — at least one synthetic fixture misbehaved"


# ---------------------------------------------------------------------------
# Clean fixture
# ---------------------------------------------------------------------------

class TestCleanFixture:
    def test_clean_artifact_no_violations(self, tmp_path):
        p = _write_artifact(tmp_path, _clean())
        viols = check(p)
        assert viols == [], f"unexpected violations on clean artifact: {viols}"


# ---------------------------------------------------------------------------
# Absent artifact → exit 0
# ---------------------------------------------------------------------------

class TestAbsentArtifact:
    def test_absent_artifact_returns_no_violations(self, tmp_path):
        absent = tmp_path / "data" / "neuralweb" / "entity_thesis_mechanism_registry.json"
        # do not create the file
        viols = check(absent)
        assert viols == [], "absent artifact should produce zero violations (pre-first-build grace)"


# ---------------------------------------------------------------------------
# ETM-C1: schema mismatch
# ---------------------------------------------------------------------------

class TestETMC1:
    def test_wrong_schema_fires_c1(self, tmp_path):
        art = _clean()
        art["schema"] = "wrong.schema.v99"
        p = _write_artifact(tmp_path, art)
        viols = check(p)
        assert any(v.startswith("ETM-C1") for v in viols), f"ETM-C1 not fired; viols={viols}"

    def test_correct_schema_no_c1(self, tmp_path):
        p = _write_artifact(tmp_path, _clean())
        viols = check(p)
        assert not any(v.startswith("ETM-C1") for v in viols)


# ---------------------------------------------------------------------------
# ETM-C2: authority violations
# ---------------------------------------------------------------------------

class TestETMC2:
    def test_wrong_authority_block_fires_c2(self, tmp_path):
        art = _clean()
        art["authority"] = {"role": "wrong"}
        p = _write_artifact(tmp_path, art)
        viols = check(p)
        assert any(v.startswith("ETM-C2") for v in viols)

    def test_is_context_only_false_fires_c2(self, tmp_path):
        art = _clean()
        art["is_context_only"] = False
        p = _write_artifact(tmp_path, art)
        viols = check(p)
        assert any(v.startswith("ETM-C2") for v in viols)

    def test_row_with_wrong_authority_fires_c2(self, tmp_path):
        art = _clean()
        art["rows"] = {
            "thesis:some_slug": {
                "registry_id": "thesis:some_slug",
                "registry_type": "thesis",
                "authority": "gating",  # wrong
            }
        }
        art["counts"]["rows_by_type"] = {"thesis": 1}
        p = _write_artifact(tmp_path, art)
        viols = check(p)
        assert any(v.startswith("ETM-C2") for v in viols)

    def test_correct_authority_no_c2(self, tmp_path):
        art = _clean()
        art["rows"] = {
            "thesis:ok_slug": {
                "registry_id": "thesis:ok_slug",
                "registry_type": "thesis",
                "authority": "display_only",
            }
        }
        art["counts"]["rows_by_type"] = {"thesis": 1}
        p = _write_artifact(tmp_path, art)
        viols = check(p)
        assert not any(v.startswith("ETM-C2") for v in viols)

    # T6 — F5: row with can_gate: true fires C2
    def test_row_with_can_gate_fires_c2(self, tmp_path):
        art = _clean()
        art["rows"] = {
            "thesis:gated_slug": {
                "registry_id": "thesis:gated_slug",
                "registry_type": "thesis",
                "authority": "display_only",
                "can_gate": True,
            }
        }
        art["counts"]["rows_by_type"] = {"thesis": 1}
        p = _write_artifact(tmp_path, art)
        viols = check(p)
        assert any(v.startswith("ETM-C2") for v in viols), f"ETM-C2 not fired for can_gate; viols={viols}"


# ---------------------------------------------------------------------------
# ETM-C3: namespace grammar
# ---------------------------------------------------------------------------

class TestETMC3:
    def test_claim_cluster_emitted_fires_c3(self, tmp_path):
        art = _clean()
        art["rows"] = {
            "claim:abcdef1234567890": {
                "registry_id": "claim:abcdef1234567890",
                "registry_type": "claim_cluster",
                "authority": "display_only",
            }
        }
        art["counts"]["rows_by_type"] = {"claim_cluster": 1}
        p = _write_artifact(tmp_path, art)
        viols = check(p)
        assert any(v.startswith("ETM-C3") for v in viols)

    def test_unknown_registry_type_fires_c3(self, tmp_path):
        art = _clean()
        art["rows"] = {
            "thesis:ok_slug": {
                "registry_id": "thesis:ok_slug",
                "registry_type": "invented_type",
                "authority": "display_only",
            }
        }
        art["counts"]["rows_by_type"] = {"invented_type": 1}
        p = _write_artifact(tmp_path, art)
        viols = check(p)
        assert any(v.startswith("ETM-C3") for v in viols)

    def test_entity_id_bad_format_fires_c3(self, tmp_path):
        art = _clean()
        art["rows"] = {
            "entity:BADFORMAT": {  # missing market segment
                "registry_id": "entity:BADFORMAT",
                "registry_type": "entity",
                "authority": "display_only",
            }
        }
        art["counts"]["rows_by_type"] = {"entity": 1}
        p = _write_artifact(tmp_path, art)
        viols = check(p)
        assert any(v.startswith("ETM-C3") for v in viols)

    def test_valid_entity_id_no_c3(self, tmp_path):
        art = _clean()
        art["rows"] = {
            "entity:US:AAPL": {
                "registry_id": "entity:US:AAPL",
                "registry_type": "entity",
                "authority": "display_only",
            }
        }
        art["counts"]["rows_by_type"] = {"entity": 1}
        p = _write_artifact(tmp_path, art)
        viols = check(p)
        assert not any(v.startswith("ETM-C3") for v in viols)

    def test_valid_species_id_no_c3(self, tmp_path):
        art = _clean()
        art["rows"] = {
            "species:S1@1.0": {
                "registry_id": "species:S1@1.0",
                "registry_type": "species_link",
                "authority": "display_only",
            }
        }
        art["counts"]["rows_by_type"] = {"species_link": 1}
        p = _write_artifact(tmp_path, art)
        viols = check(p)
        assert not any(v.startswith("ETM-C3") for v in viols)

    def test_valid_mechanism_id_no_c3(self, tmp_path):
        art = _clean()
        art["rows"] = {
            "mechanism:A9_WASHOUT": {
                "registry_id": "mechanism:A9_WASHOUT",
                "registry_type": "mechanism",
                "authority": "display_only",
            }
        }
        art["counts"]["rows_by_type"] = {"mechanism": 1}
        p = _write_artifact(tmp_path, art)
        viols = check(p)
        assert not any(v.startswith("ETM-C3") for v in viols)


# ---------------------------------------------------------------------------
# ETM-C4: invented links
# ---------------------------------------------------------------------------

class TestETMC4:
    def _art_with_rows(self) -> dict:
        art = _clean()
        art["rows"] = {
            "thesis:alpha": {
                "registry_id": "thesis:alpha",
                "registry_type": "thesis",
                "authority": "display_only",
            }
        }
        art["counts"]["rows_by_type"] = {"thesis": 1}
        return art

    def test_missing_source_path_fires_c4(self, tmp_path):
        art = self._art_with_rows()
        art["edges"] = [
            {"src": "thesis:alpha", "dst": "thesis:alpha",
             "kind": "self", "source": {"detail": "ok"}}
        ]
        art["counts"]["edges_by_kind"] = {"self": 1}
        p = _write_artifact(tmp_path, art)
        viols = check(p)
        assert any(v.startswith("ETM-C4") for v in viols)

    def test_missing_source_detail_fires_c4(self, tmp_path):
        art = self._art_with_rows()
        art["edges"] = [
            {"src": "thesis:alpha", "dst": "thesis:alpha",
             "kind": "self", "source": {"path": "data/test.json"}}
        ]
        art["counts"]["edges_by_kind"] = {"self": 1}
        p = _write_artifact(tmp_path, art)
        viols = check(p)
        assert any(v.startswith("ETM-C4") for v in viols)

    def test_unresolvable_src_fires_c4(self, tmp_path):
        art = self._art_with_rows()
        art["edges"] = [
            {"src": "thesis:nonexistent_row", "dst": "thesis:alpha",
             "kind": "x", "source": {"path": "data/test.json", "detail": "ok"}}
        ]
        art["counts"]["edges_by_kind"] = {"x": 1}
        p = _write_artifact(tmp_path, art)
        viols = check(p)
        assert any(v.startswith("ETM-C4") for v in viols)

    def test_gov_dst_resolvable_no_c4(self, tmp_path):
        art = self._art_with_rows()
        art["edges"] = [
            {"src": "thesis:alpha", "dst": "gov:abcdef1234567890",
             "kind": "governed_by",
             "source": {"path": "data/neuralweb/governance.jsonl", "detail": "event_id"}}
        ]
        art["counts"]["edges_by_kind"] = {"governed_by": 1}
        p = _write_artifact(tmp_path, art)
        viols = check(p)
        assert not any(v.startswith("ETM-C4") for v in viols)

    def test_rf_src_resolvable_no_c4(self, tmp_path):
        art = self._art_with_rows()
        art["rows"]["mechanism:A9"] = {
            "registry_id": "mechanism:A9",
            "registry_type": "mechanism",
            "authority": "display_only",
        }
        art["counts"]["rows_by_type"] = {"thesis": 1, "mechanism": 1}
        art["edges"] = [
            {"src": "rf:rf-20260101-oracle-alpha_x",
             "dst": "mechanism:A9",
             "kind": "rf_candidate_of_mechanism",
             "source": {"path": "data/research_factory/candidates.jsonl", "detail": "spec_ref"}}
        ]
        art["counts"]["edges_by_kind"] = {"rf_candidate_of_mechanism": 1}
        p = _write_artifact(tmp_path, art)
        viols = check(p)
        assert not any(v.startswith("ETM-C4") for v in viols)


# ---------------------------------------------------------------------------
# ETM-C5: suggestion-only law
# ---------------------------------------------------------------------------

class TestETMC5:
    def test_wrong_basis_fires_c5(self, tmp_path):
        art = _clean()
        art["possible_duplicates"] = [
            {"a": "thesis:x", "b": "thesis:y",
             "basis": "manual_assertion", "suggestion_only": True, "shared_tokens": ["foo"]}
        ]
        p = _write_artifact(tmp_path, art)
        viols = check(p)
        assert any(v.startswith("ETM-C5") for v in viols)

    # T5 — F4(b): auto_merge in possible_duplicates fires C5
    def test_auto_merge_in_possible_duplicates_fires_c5(self, tmp_path):
        art = _clean()
        art["possible_duplicates"] = [
            {"a": "thesis:x", "b": "thesis:y",
             "basis": "token_overlap_suggestion_only",
             "suggestion_only": True,
             "shared_tokens": ["foo"],
             "auto_merge": True}
        ]
        p = _write_artifact(tmp_path, art)
        viols = check(p)
        assert any(v.startswith("ETM-C5") for v in viols), f"ETM-C5 not fired for auto_merge; viols={viols}"

    def test_correct_basis_no_c5(self, tmp_path):
        art = _clean()
        art["possible_duplicates"] = [
            {"a": "thesis:x", "b": "thesis:y",
             "basis": "token_overlap_suggestion_only",
             "suggestion_only": True,
             "shared_tokens": ["foo"],
             "note": "suggestion only — not a merge"}
        ]
        p = _write_artifact(tmp_path, art)
        viols = check(p)
        assert not any(v.startswith("ETM-C5") for v in viols)


# ---------------------------------------------------------------------------
# ETM-C6: counts drift
# ---------------------------------------------------------------------------

class TestETMC6:
    def test_wrong_rows_by_type_fires_c6(self, tmp_path):
        art = _clean()
        art["rows"] = {
            "thesis:one": {
                "registry_id": "thesis:one",
                "registry_type": "thesis",
                "authority": "display_only",
            }
        }
        # claim 99 instead of 1
        art["counts"]["rows_by_type"] = {"thesis": 99}
        p = _write_artifact(tmp_path, art)
        viols = check(p)
        assert any(v.startswith("ETM-C6") for v in viols)

    def test_wrong_edges_by_kind_fires_c6(self, tmp_path):
        art = _clean()
        art["rows"] = {
            "thesis:one": {
                "registry_id": "thesis:one",
                "registry_type": "thesis",
                "authority": "display_only",
            }
        }
        art["counts"]["rows_by_type"] = {"thesis": 1}
        art["edges"] = [
            {"src": "thesis:one", "dst": "thesis:one",
             "kind": "self",
             "source": {"path": "data/test.json", "detail": "ok"}}
        ]
        # lie about the count
        art["counts"]["edges_by_kind"] = {"self": 99}
        p = _write_artifact(tmp_path, art)
        viols = check(p)
        assert any(v.startswith("ETM-C6") for v in viols)

    def test_correct_counts_no_c6(self, tmp_path):
        art = _clean()
        art["rows"] = {
            "thesis:one": {
                "registry_id": "thesis:one",
                "registry_type": "thesis",
                "authority": "display_only",
            }
        }
        art["counts"]["rows_by_type"] = {"thesis": 1}
        art["edges"] = [
            {"src": "thesis:one", "dst": "thesis:one",
             "kind": "self",
             "source": {"path": "data/test.json", "detail": "ok"}}
        ]
        art["counts"]["edges_by_kind"] = {"self": 1}
        p = _write_artifact(tmp_path, art)
        viols = check(p)
        assert not any(v.startswith("ETM-C6") for v in viols)
