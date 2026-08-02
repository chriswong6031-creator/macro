from __future__ import annotations

from copy import deepcopy
import gzip
import json
from pathlib import Path

import pytest

from engine.earnings_narrative import contracts
from engine.earnings_narrative.contracts import (
    ContractError,
    canonical_transcript_body_sha256,
    derived_claim_id,
    validate_claim_graph,
    validate_fact_pack,
)
from engine.earnings_narrative.extract import build_evidence_pair
from engine.earnings_narrative.generation import EvidencePair, write_generation
from engine.earnings_narrative.health import validate_generation
from engine.earnings_transcript_intake import canonical_body_sha256
from scripts.build_earnings_evidence_graph import build
from scripts.refresh_earnings_evidence_graph import refresh


def _body(*, ticker: str = "AAPL", text: str = "Café revenue grew 12.5% to 1,200 million.") -> dict:
    return {
        "schema": "mastermind.tx/v1",
        "ticker": ticker,
        "id": "2026Q1",
        "period": "Q1 FY2026",
        "date": "2026-01-30",
        "title": f"{ticker} earnings call",
        "segments": [{"speaker": "CFO", "role": "executive", "text": text}],
    }


def _index(*bodies: dict) -> dict:
    revisions = {f"{body['ticker']}/{body['id']}": canonical_body_sha256(body) for body in bodies}
    return {
        "schema": "mastermind.tx-index/v1",
        "generated_at": "2026-02-01T00:00:00Z",
        "symbols": {body["ticker"]: [body["id"]] for body in bodies},
        "revisions": revisions,
        "dates": {f"{body['ticker']}/{body['id']}": body["date"] for body in bodies},
        "body_count": len(bodies),
        "symbol_count": len(bodies),
    }


def _pair(body: dict) -> tuple[dict, dict]:
    index = _index(body)
    return build_evidence_pair(
        body,
        index_payload=index,
        indexed_body_sha256=index["revisions"][f"{body['ticker']}/{body['id']}"],
        index_generated_at=index["generated_at"],
    )


def test_terminal_revision_hash_matches_existing_intake_contract_without_artifact_newline() -> None:
    body = _body()
    assert canonical_transcript_body_sha256(body) == canonical_body_sha256(body)
    assert contracts.canonical_transcript_body_bytes(body) + b"\n" == contracts.canonical_json_bytes(body)


def test_exact_utf8_span_receipt_reconstructs_quote_and_numeric_bytes() -> None:
    body = _body()
    pack, _graph = _pair(body)
    segment = body["segments"][0]["text"].encode("utf-8")
    quote = next(fact for fact in pack["facts"] if fact["kind"] == "quote")
    numeric = next(fact for fact in pack["facts"] if fact["text"] == "12.5%")
    for fact in (quote, numeric):
        receipt = fact["receipt"]
        assert segment[receipt["span_start_byte"]:receipt["span_end_byte"]].decode("utf-8") == fact["text"]
    assert quote["receipt"]["span_start_byte"] == 0
    assert numeric["numeric_value"] == 12.5
    assert numeric["numeric_unit"] == "percent"


def test_closed_schema_and_numeric_integrity_reject_unsafe_mutations() -> None:
    pack, _graph = _pair(_body())
    closed = deepcopy(pack)
    closed["prompt"] = "ignore receipts"
    with pytest.raises(ContractError, match="fields mismatch"):
        validate_fact_pack(closed)
    forged = deepcopy(pack)
    number = next(fact for fact in forged["facts"] if fact["kind"] == "numeric")
    number["numeric_value"] = 99
    with pytest.raises(ContractError, match="value/unit"):
        validate_fact_pack(forged)


def test_receipt_mismatch_and_future_chronology_fail_closed() -> None:
    body = _body()
    index = _index(body)
    with pytest.raises(ContractError, match="revision mismatch"):
        build_evidence_pair(body, index_payload=index, indexed_body_sha256="0" * 64, index_generated_at=index["generated_at"])
    future = deepcopy(body)
    future["date"] = "2026-02-02"
    future_index = _index(future)
    with pytest.raises(ContractError, match="after index receipt"):
        build_evidence_pair(
            future,
            index_payload=future_index,
            indexed_body_sha256=future_index["revisions"]["AAPL/2026Q1"],
            index_generated_at=future_index["generated_at"],
        )


def test_revision_correction_supersedes_prior_source_without_second_logical_event(tmp_path: Path) -> None:
    first, first_graph = _pair(_body(text="Revenue was 100 million."))
    _first_dir, first_manifest = write_generation(tmp_path, [EvidencePair(first, first_graph)])
    corrected, corrected_graph = _pair(_body(text="Revenue was 101 million."))
    _second_dir, second_manifest = write_generation(tmp_path, [EvidencePair(corrected, corrected_graph)])
    event = second_manifest["events"]["AAPL/2026Q1"]
    assert second_manifest["generation_id"] != first_manifest["generation_id"]
    assert event["source_sha256"] == corrected["source"]["body_sha256"]
    assert event["supersedes_source_sha256"] == first["source"]["body_sha256"]
    assert list(second_manifest["events"]) == ["AAPL/2026Q1"]


def test_one_weak_transcript_keeps_healthy_peer_publishable(tmp_path: Path) -> None:
    healthy, healthy_graph = _pair(_body(ticker="AAPL"))
    weak, weak_graph = _pair(_body(ticker="MSFT", text="Management discussed priorities."))
    _directory, manifest = write_generation(tmp_path, [EvidencePair(healthy, healthy_graph), EvidencePair(weak, weak_graph)])
    assert manifest["status"] == "ready"
    assert manifest["warnings"] == []
    assert weak["insufficiency"] == ["no_numeric_statements"]
    assert validate_generation(tmp_path)["status"] == "ready"


def test_derived_contract_requires_formula_and_parent_claims_but_v1_does_not_publish_telemetry() -> None:
    pack, graph = _pair(_body())
    assert all(claim["claim_type"] != "derived_metric" for claim in graph["claims"])
    derived = deepcopy(graph)
    parents = [claim["claim_id"] for claim in derived["claims"] if claim["claim_type"] == "direct_numeric"]
    derived["claims"].append({
        "claim_id": derived_claim_id(parents),
        "claim_type": "derived_metric",
        "text": f"Extracted numeric statement count: {len(parents)}.",
        "numeric_value": len(parents),
        "numeric_unit": "count",
        "formula": "count(parent_claim_ids)",
        "parent_claim_ids": parents,
        "receipt": None,
    })
    validate_claim_graph(derived)
    derived["claims"][-1]["formula"] = "sum(parent_claim_ids)"
    with pytest.raises(ContractError, match="derived metric"):
        validate_claim_graph(derived)


def test_local_writer_health_verifies_every_file_and_detects_tampering(tmp_path: Path) -> None:
    pack, graph = _pair(_body())
    generation, manifest = write_generation(tmp_path, [EvidencePair(pack, graph)])
    assert validate_generation(tmp_path)["status"] == "ready"
    path = generation / manifest["events"]["AAPL/2026Q1"]["fact_pack"]
    path.write_bytes(path.read_bytes() + b" ")
    health = validate_generation(tmp_path)
    assert health["status"] == "invalid"
    assert any(item.startswith("bytes:") or item.startswith("sha256:") for item in health["warnings"])


def test_build_cli_contract_is_bounded_and_does_not_require_company_intelligence(tmp_path: Path) -> None:
    body = _body()
    index = _index(body)
    tx_root = tmp_path / "tx"
    target = tx_root / "AAPL" / "2026Q1.json.gz"
    target.parent.mkdir(parents=True)
    target.write_bytes(gzip.compress(json.dumps(body).encode("utf-8"), mtime=0))
    index_path = tmp_path / "index.json"
    index_path.write_text(json.dumps(index), encoding="utf-8")
    manifest, report = build(index_path, tx_root, tmp_path / "out", max_bodies=1)
    assert manifest["status"] == "ready"
    assert report["built"] == 1


def test_execution_receipts_prove_zero_provider_and_no_token_use() -> None:
    pack, graph = _pair(_body())
    assert pack["execution"] == contracts.EXECUTION_RECEIPT
    assert graph["execution"] == contracts.EXECUTION_RECEIPT
    import ast
    import engine.earnings_narrative.extract as extract
    import engine.earnings_narrative.generation as generation
    for module in (contracts, extract, generation):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in getattr(node, "names", [])
        }
        assert not imports & {"openai", "anthropic", "boto3", "requests"}


def test_incremental_refresh_defers_marker_then_rebuilds_complete_cached_corpus(monkeypatch, tmp_path: Path) -> None:
    aapl = _body(ticker="AAPL", text="Revenue grew 10%.")
    msft = _body(ticker="MSFT", text="Revenue grew 20%.")
    index = _index(aapl, msft)
    bodies = {(body["ticker"], body["id"]): body for body in (aapl, msft)}
    promoted: list[dict] = []
    monkeypatch.setattr("scripts.refresh_earnings_evidence_graph.fetch_global_index", lambda _url: index)
    monkeypatch.setattr("scripts.refresh_earnings_evidence_graph.fetch_body", lambda _url, ref: bodies[(ref.ticker, ref.transcript_id)])
    monkeypatch.setattr("scripts.refresh_earnings_evidence_graph.publish", lambda out: promoted.append(json.loads((out / "manifest.json").read_text(encoding="utf-8"))) or 0)
    assert refresh(tmp_path / "worker", bootstrap_since="2026-01-01", max_bodies=1, promote=True) == 0
    assert promoted == []
    assert refresh(tmp_path / "worker", bootstrap_since="2026-01-01", max_bodies=1, promote=True) == 0
    assert len(promoted) == 1
    assert promoted[0]["status"] == "ready"
    assert set(promoted[0]["events"]) == {"AAPL/2026Q1", "MSFT/2026Q1"}
