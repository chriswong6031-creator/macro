"""S1F owner facade validates frozen bindings before any owner transport."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.research.dislocation_p0_a1_lib import canonical_json
from scripts.research.dislocation_p0_s1f_owner_run import (
    OwnerRunBlocked, _fts_document_names, _packet_artifacts, _primary_view,
    _validate_inputs,
)
from scripts.research.dislocation_p0_s1f_runner import _batch_plan, _selection_logical_hash
from scripts.research.dislocation_p0_s1f_selection import AUTHORITY, STRATA, exact70_manifest


def _write(path: Path, value: dict) -> None:
    path.write_text(canonical_json(value) + "\n", encoding="utf-8")


def _fixtures(tmp_path: Path) -> tuple[Path, Path, Path]:
    rows: list[dict] = []
    number = 1
    for stratum in STRATA:
        for era, form in [("modern", "8-K")] * 7 + [("development", "6-K")] * 3:
            cik = f"{number:010d}"; accession = f"000000000{number % 10}-24-{number:06d}"
            rows.append({
                "stratum": stratum, "era": era, "form": form, "base_form": form,
                "cik": cik, "accession": accession, "filed_on": "2024-02-01" if era == "modern" else "2020-02-01",
                "selection_key": f"{stratum}|{era}|{form}|{cik}|{accession}",
                "query_edges": [{"hit_id": f"{accession}:matched.htm", "filename": "matched.htm", "query_receipt_sha256": f"{number:064x}"}],
            }); number += 1
    # exact70_manifest validates the production selection key formula, so add
    # candidates using its validated shape rather than hand-writing a manifest.
    from scripts.research.dislocation_p0_a1_lib import selection_key
    for row in rows:
        row["selection_key"] = selection_key(family=row["stratum"], era=row["era"], base=row["form"], cik=row["cik"], accession=row["accession"])
    design_ciks = [f"0000009{number:03d}" for number in range(20)]
    manifest = exact70_manifest(rows, design_ciks=design_ciks, frozen_universe_sha256="a" * 64)
    candidates = manifest["candidates"]
    logical = _selection_logical_hash(candidates)
    policy = {"batches": [{"batch_id": f"b{index}", "retrieval_stratum": stratum, "packet_count": 10} for index, stratum in enumerate(STRATA, start=1)]}
    batch = _batch_plan(policy=policy, policy_sha256="b" * 64, candidates=candidates, selection_logical_sha256=logical, universe_sha256="a" * 64)
    receipt = {"schema": "mastermind.dislocation_p0.s1f_exact70_selection_receipt.v1", "status": "COMPLETE", "selection_count": 70, "selection_identity_count": 70, "selection_manifest_sha256": manifest["manifest_sha256"], "selection_logical_sha256": logical, "design_ciks_excluded": design_ciks, "batch_plan_sha256": batch["batch_plan_sha256"], "selection_packet_manifest": "S1F_EXACT70_SOURCE_MANIFEST.json", "batch_plan": "S1F_EXACT70_AUDIT_BATCH_PLAN.json", "authority": dict(AUTHORITY)}
    receipt["receipt_sha256"] = __import__("hashlib").sha256(canonical_json(receipt).encode()).hexdigest()
    selection_path, receipt_path, batch_path = tmp_path / "selection.json", tmp_path / "receipt.json", tmp_path / "batch.json"
    _write(selection_path, manifest); _write(receipt_path, receipt); _write(batch_path, batch)
    return selection_path, receipt_path, batch_path


def test_owner_facade_rejects_batch_identity_mutation_before_transport(tmp_path: Path) -> None:
    selection, receipt, batch = _fixtures(tmp_path)
    candidates, bound_receipt, bound_batch = _validate_inputs(selection_path=selection, receipt_path=receipt, batch_plan_path=batch)
    assert len(candidates) == 70 and bound_receipt["status"] == "COMPLETE" and len(bound_batch["batches"]) == 7
    value = json.loads(batch.read_text())
    value["batches"][0]["packets"][0]["accession"] = "0000000000-99-999999"
    value.pop("batch_plan_sha256"); value["batch_plan_sha256"] = __import__("hashlib").sha256(canonical_json(value).encode()).hexdigest()
    _write(batch, value)
    with pytest.raises(OwnerRunBlocked, match="selection receipt binding mismatch"):
        _validate_inputs(selection_path=selection, receipt_path=receipt, batch_plan_path=batch)


def test_primary_view_preserves_owner_type_null_as_unavailable_and_no_description() -> None:
    document = {"document_id": "d", "document_name": "primary.htm", "content_sha256": "a" * 64, "byte_length": 1, "document_type": None}
    view = _primary_view(document, source_path="primary/01_d.source")
    assert view["document_type"] is None and view["document_type_status"] == "OWNER_UNAVAILABLE" and "description" not in view
    document["document_type"] = "8-K"
    typed = _primary_view(document, source_path="primary/01_d.source")
    assert typed["document_type"] == "8-K" and typed["document_type_status"] == "OWNER_AVAILABLE"


def test_owner_fts_crosswire_is_refused() -> None:
    with pytest.raises(OwnerRunBlocked, match="crosswire"):
        _fts_document_names({"accession": "a", "query_edges": [{"hit_id": "b:primary.htm", "filename": "primary.htm", "query_receipt_sha256": "r"}]})


def test_primary_exact_match_reuses_one_source_file_and_is_never_a_substitute() -> None:
    from types import SimpleNamespace
    document = {
        "document_id": "d", "document_name": "matched.htm", "content_sha256": "a" * 64,
        "byte_length": 4, "archive_url": "https://www.sec.gov/Archives/edgar/data/1/a/matched.htm",
        "document_type": None,
    }
    packet = SimpleNamespace(
        slot=1, issuer={"cik": "0000000001"}, filing={"accession": "a", "base_form": "8-K"},
        clocks={"accepted_at": "2024-01-01T00:00:00Z", "filed_on": "2024-01-01"}, lineage={},
        manifest_storage_key="m", manifest_id="m", filing_id="f", matched_documents=(document,),
        source_documents=(b"same",), primary_context=document, primary_context_source=b"same",
    )
    candidate = {"cik": "0000000001", "accession": "a", "selection_key": "s", "stratum": STRATA[0], "query_edges": []}
    public, model, files, _hosts = _packet_artifacts(candidates=[candidate], packets=[packet])
    assert list(files) == ["packets/01_d.source"]
    assert model[0]["primary_context"]["source_path"] == model[0]["documents"][0]["source_path"]
    assert public[0]["primary_document_substitution"] is False
    assert model[0]["primary_document_substitution"] is False
