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
    receipt_for_span,
    validate_claim_graph,
    validate_fact_pack,
    validate_manifest,
    verify_fact_pack_against_transcript,
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
    assert pack["source"]["source_kind"] == "transcript"
    assert pack["source"]["locator"] == "/data/tx/AAPL/2026Q1.json.gz"


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


def test_manifest_generation_id_is_content_addressed_and_dates_are_exact() -> None:
    body = _body()
    pack, graph = _pair(body)
    from engine.earnings_narrative.generation import build_generation
    manifest, _files = build_generation([EvidencePair(pack, graph, body)])
    forged = deepcopy(manifest)
    forged["generation_id"] = "f" * 32
    with pytest.raises(ContractError, match="generation_id does not match"):
        validate_manifest(forged)
    with pytest.raises(ContractError, match="ISO date"):
        contracts.iso_date("2026-01-30 trailing", field="date")


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
    first_body = _body(text="Revenue was 100 million.")
    first, first_graph = _pair(first_body)
    _first_dir, first_manifest = write_generation(tmp_path, [EvidencePair(first, first_graph, first_body)])
    corrected_body = _body(text="Revenue was 101 million.")
    corrected, corrected_graph = _pair(corrected_body)
    _second_dir, second_manifest = write_generation(tmp_path, [EvidencePair(corrected, corrected_graph, corrected_body)])
    event = second_manifest["events"]["AAPL/2026Q1"]
    assert second_manifest["generation_id"] != first_manifest["generation_id"]
    assert event["source_sha256"] == corrected["source"]["body_sha256"]
    assert event["supersedes_source_sha256"] == first["source"]["body_sha256"]
    assert second_manifest["parent_generation_id"] == first_manifest["generation_id"]
    assert list(second_manifest["events"]) == ["AAPL/2026Q1"]
    _retry_dir, retry_manifest = write_generation(tmp_path, [EvidencePair(corrected, corrected_graph, corrected_body)])
    assert retry_manifest["generation_id"] == second_manifest["generation_id"]
    assert retry_manifest["parent_generation_id"] == first_manifest["generation_id"]
    assert retry_manifest["events"]["AAPL/2026Q1"]["supersedes_source_sha256"] == first["source"]["body_sha256"]
    source_path = first_manifest["events"]["AAPL/2026Q1"]["source_body"]
    old_source_path = tmp_path / first_manifest["files"][source_path]["object_key"]
    assert json.loads(old_source_path.read_text(encoding="utf-8"))["segments"][0]["text"] == "Revenue was 100 million."
    assert first["source"]["locator"] == corrected["source"]["locator"]


def test_one_weak_transcript_keeps_healthy_peer_publishable(tmp_path: Path) -> None:
    healthy_body = _body(ticker="AAPL")
    weak_body = _body(ticker="MSFT", text="Management discussed priorities.")
    healthy, healthy_graph = _pair(healthy_body)
    weak, weak_graph = _pair(weak_body)
    _directory, manifest = write_generation(tmp_path, [EvidencePair(healthy, healthy_graph, healthy_body), EvidencePair(weak, weak_graph, weak_body)])
    assert manifest["status"] == "ready"
    assert manifest["warnings"] == []
    assert weak["insufficiency"] == ["no_numeric_statements"]
    assert validate_generation(tmp_path)["status"] == "ready"
    source_path = manifest["events"]["AAPL/2026Q1"]["source_body"]
    assert (tmp_path / manifest["files"][source_path]["object_key"]).is_file()


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
    })
    validate_claim_graph(derived)
    derived["claims"][-1]["formula"] = "sum(parent_claim_ids)"
    with pytest.raises(ContractError, match="derived metric"):
        validate_claim_graph(derived)


def test_local_writer_health_verifies_every_file_and_detects_tampering(tmp_path: Path) -> None:
    body = _body()
    pack, graph = _pair(body)
    generation, manifest = write_generation(tmp_path, [EvidencePair(pack, graph, body)])
    assert validate_generation(tmp_path)["status"] == "ready"
    fact_path = manifest["events"]["AAPL/2026Q1"]["fact_pack"]
    path = tmp_path / manifest["files"][fact_path]["object_key"]
    path.write_bytes(path.read_bytes() + b" ")
    health = validate_generation(tmp_path)
    assert health["status"] == "invalid"
    assert any(item.startswith("bytes:") or item.startswith("sha256:") for item in health["warnings"])


def test_source_replay_rejects_a_self_consistent_claim_receipt_from_other_raw_bytes() -> None:
    body = _body()
    pack, _graph = _pair(body)
    forged = deepcopy(pack)
    fact = next(item for item in forged["facts"] if item["kind"] == "quote")
    forged_text = "Bogus transcript statement."
    fact["text"] = forged_text
    fact["receipt"] = receipt_for_span(
        source_sha256=forged["source"]["body_sha256"],
        segment_index=0,
        segment_text=forged_text,
        start_byte=0,
        end_byte=len(forged_text.encode("utf-8")),
        text=forged_text,
    )
    validate_fact_pack(forged)
    with pytest.raises(ContractError, match="does not replay"):
        verify_fact_pack_against_transcript(forged, body)


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
    assert manifest["coverage"]["historical_completeness"] is True


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


def test_workflow_cache_is_limited_to_intake_not_append_only_cas_output() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "earnings-evidence-graph.yml").read_text(encoding="utf-8")
    intake_paths = "${{ runner.temp }}/earnings-evidence/intake-state.json\n            ${{ runner.temp }}/earnings-evidence/bodies"
    assert workflow.count(intake_paths) == 2
    cache_sections = [
        workflow.split(anchor, 1)[1].split("\n      - name:", 1)[0]
        for anchor in ("uses: actions/cache/restore@v4", "uses: actions/cache/save@v4")
    ]
    for section in cache_sections:
        assert "path: ${{ runner.temp }}/earnings-evidence\n" not in section
        assert "earnings-evidence/output" not in section
        assert "earnings-evidence/objects" not in section
        assert "earnings-evidence/generations" not in section
    assert "earnings-evidence-v1-" not in workflow
    assert workflow.count("earnings-evidence-v2-") == 3


def test_workflow_serializes_the_hourly_backfill_throttle() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "earnings-evidence-graph.yml").read_text(encoding="utf-8")
    # Scheduled work has no dispatch inputs, so both the advertised default and
    # the event fallback must cap the serial lane at the same 500 bodies/hour.
    assert 'cron: "43 * * * *"' in workflow
    assert 'default: "500"' in workflow
    assert "MAX_BODIES: ${{ inputs.max_bodies || '500' }}" in workflow
    assert "group: earnings-evidence-graph-publication" in workflow
    assert "cancel-in-progress: false" in workflow


def test_direct_graph_is_structural_and_resolves_each_fact_once() -> None:
    pack, graph = _pair(_body())
    direct = [claim for claim in graph["claims"] if claim["claim_type"] != "derived_metric"]
    assert all(set(claim) == {"claim_id", "claim_type", "fact_id"} for claim in direct)
    assert {claim["fact_id"] for claim in direct} == {fact["fact_id"] for fact in pack["facts"]}
    assert len(json.dumps(graph, ensure_ascii=False)) < len(json.dumps(pack, ensure_ascii=False))


def test_append_only_full_history_backfills_in_bounded_batches(monkeypatch, tmp_path: Path) -> None:
    old = _body(ticker="OLD", text="Historic revenue grew 1%.")
    old["date"] = "2025-01-30"
    aapl = _body(ticker="AAPL", text="Revenue grew 10%.")
    msft = _body(ticker="MSFT", text="Revenue grew 20%.")
    current = {"index": _index(old, aapl, msft), "remote": None}
    bodies = {(body["ticker"], body["id"]): body for body in (old, aapl, msft)}
    published: list[dict] = []
    monkeypatch.setattr("scripts.refresh_earnings_evidence_graph.fetch_global_index", lambda _url: current["index"])
    monkeypatch.setattr("scripts.refresh_earnings_evidence_graph.fetch_body", lambda _url, ref: bodies[(ref.ticker, ref.transcript_id)])
    monkeypatch.setattr("scripts.refresh_earnings_evidence_graph.load_remote_root_state", lambda: (current["remote"], None, None))
    def publish_root(out: Path, **_kwargs: object) -> int:
        current["remote"] = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        published.append(current["remote"])
        return 0
    monkeypatch.setattr("scripts.refresh_earnings_evidence_graph.publish", publish_root)
    worker, public = tmp_path / "worker", tmp_path / "public"
    for _ in range(3):
        assert refresh(worker, max_bodies=1, out_dir=public, promote=True) == 0
    final = published[-1]
    assert set(final["events"]) == {"OLD/2026Q1", "AAPL/2026Q1", "MSFT/2026Q1"}
    assert final["coverage"]["historical_completeness"] is True
    assert all(len(next_manifest["events"]) >= len(previous["events"]) for previous, next_manifest in zip(published, published[1:]))
    assert published[0]["warnings"] == ["backfill_pending"]


def test_unchanged_index_is_true_noop_and_receipts_stay_stable(monkeypatch, tmp_path: Path) -> None:
    aapl = _body(ticker="AAPL", text="Revenue grew 10%.")
    msft = _body(ticker="MSFT", text="Revenue grew 20%.")
    current = {"index": _index(aapl), "remote": None}
    bodies = {(body["ticker"], body["id"]): body for body in (aapl, msft)}
    publishes: list[dict] = []
    monkeypatch.setattr("scripts.refresh_earnings_evidence_graph.fetch_global_index", lambda _url: current["index"])
    monkeypatch.setattr("scripts.refresh_earnings_evidence_graph.fetch_body", lambda _url, ref: bodies[(ref.ticker, ref.transcript_id)])
    monkeypatch.setattr("scripts.refresh_earnings_evidence_graph.load_remote_root_state", lambda: (current["remote"], None, None))
    def publish_root(out: Path, **_kwargs: object) -> int:
        current["remote"] = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        publishes.append(current["remote"])
        return 0
    monkeypatch.setattr("scripts.refresh_earnings_evidence_graph.publish", publish_root)
    worker, public = tmp_path / "worker", tmp_path / "public"
    assert refresh(worker, max_bodies=1, out_dir=public, promote=True) == 0
    first = publishes[-1]
    assert refresh(worker, max_bodies=1, out_dir=public, promote=True) == 0
    assert publishes == [first]
    current["index"] = _index(aapl, msft)
    current["index"]["generated_at"] = "2026-02-02T00:00:00Z"
    assert refresh(worker, max_bodies=1, out_dir=public, promote=True) == 0
    second = publishes[-1]
    aapl_path = first["events"]["AAPL/2026Q1"]["fact_pack"]
    assert first["files"][aapl_path] == second["files"][aapl_path]
    assert json.loads((worker / "bodies" / "AAPL" / "2026Q1.receipt.json").read_text(encoding="utf-8"))["index_generated_at"] == "2026-02-01T00:00:00Z"


def test_refresh_canonicalizes_terminal_plus_zero_timestamp_for_root_contract(monkeypatch, tmp_path: Path) -> None:
    body = _body()
    index = _index(body)
    index["generated_at"] = "2026-02-01T00:00:00+00:00"
    current = {"index": index, "remote": None}
    monkeypatch.setattr("scripts.refresh_earnings_evidence_graph.fetch_global_index", lambda _url: current["index"])
    monkeypatch.setattr("scripts.refresh_earnings_evidence_graph.fetch_body", lambda _url, _ref: body)
    monkeypatch.setattr("scripts.refresh_earnings_evidence_graph.load_remote_root_state", lambda: (current["remote"], None, None))

    def publish_root(out: Path, **_kwargs: object) -> int:
        current["remote"] = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        return 0

    monkeypatch.setattr("scripts.refresh_earnings_evidence_graph.publish", publish_root)
    assert refresh(tmp_path / "worker", max_bodies=1, out_dir=tmp_path / "public", promote=True) == 0
    assert current["remote"]["generated_at"] == "2026-02-01T00:00:00Z"
    assert current["remote"]["coverage"]["index_generated_at"] == "2026-02-01T00:00:00Z"


def test_cache_loss_uses_remote_catalog_for_correction_lineage(monkeypatch, tmp_path: Path) -> None:
    original = _body(ticker="AAPL", text="Revenue was 100 million.")
    corrected = _body(ticker="AAPL", text="Revenue was 101 million.")
    current = {"index": _index(original), "body": original, "remote": None}
    monkeypatch.setattr("scripts.refresh_earnings_evidence_graph.fetch_global_index", lambda _url: current["index"])
    monkeypatch.setattr("scripts.refresh_earnings_evidence_graph.fetch_body", lambda _url, _ref: current["body"])
    monkeypatch.setattr("scripts.refresh_earnings_evidence_graph.load_remote_root_state", lambda: (current["remote"], None, None))
    monkeypatch.setattr("scripts.refresh_earnings_evidence_graph.publish", lambda _out, **_kwargs: 0)
    first_public = tmp_path / "first-public"
    assert refresh(tmp_path / "first-worker", max_bodies=1, out_dir=first_public, promote=True) == 0
    current["remote"] = json.loads((first_public / "manifest.json").read_text(encoding="utf-8"))
    current["index"] = _index(corrected)
    current["body"] = corrected
    second_public = tmp_path / "second-public"
    assert refresh(tmp_path / "second-worker", max_bodies=1, out_dir=second_public, promote=True) == 0
    final = json.loads((second_public / "manifest.json").read_text(encoding="utf-8"))
    assert final["events"]["AAPL/2026Q1"]["supersedes_source_sha256"] == current["remote"]["events"]["AAPL/2026Q1"]["source_sha256"]


def test_corrected_index_revision_never_reuses_a_stale_cached_body_receipt(monkeypatch, tmp_path: Path) -> None:
    original = _body(text="Revenue was 100 million.")
    corrected = _body(text="Revenue was 101 million.")
    current = {"index": _index(original), "body": original, "remote": None}
    fetched: list[str] = []
    monkeypatch.setattr("scripts.refresh_earnings_evidence_graph.fetch_global_index", lambda _url: current["index"])
    monkeypatch.setattr("scripts.refresh_earnings_evidence_graph.fetch_body", lambda _url, ref: fetched.append(ref.body_sha256) or current["body"])
    monkeypatch.setattr("scripts.refresh_earnings_evidence_graph.load_remote_root_state", lambda: (current["remote"], None, None))
    def publish_root(out: Path, **_kwargs: object) -> int:
        current["remote"] = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        return 0
    monkeypatch.setattr("scripts.refresh_earnings_evidence_graph.publish", publish_root)
    worker, public = tmp_path / "worker", tmp_path / "public"
    assert refresh(worker, max_bodies=1, out_dir=public, promote=True) == 0
    current["index"] = _index(corrected)
    current["body"] = corrected
    assert refresh(worker, max_bodies=1, out_dir=public, promote=True) == 0
    final = json.loads((public / "manifest.json").read_text(encoding="utf-8"))
    assert fetched == [canonical_body_sha256(original), canonical_body_sha256(corrected)]
    assert final["events"]["AAPL/2026Q1"]["source_sha256"] == canonical_body_sha256(corrected)
