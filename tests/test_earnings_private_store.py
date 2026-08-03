"""Security and receipt tests for the private Earnings Wire publication."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from engine.earnings_narrative.extract import build_evidence_pair
from engine.earnings_narrative.generation import EvidencePair, write_generation
from engine.earnings_narrative.context_packets import canonical_json_bytes
from engine.earnings_narrative.private_publication import (
    POINTER_KEY,
    EarningsPrivatePublicationError,
    load_private_context_packet,
    load_private_manifest,
    load_private_record,
    prepare_private_publication,
    publish_private_publication,
)
from engine.earnings_narrative.public_wire import (
    build_public_wire_manifest,
    compile_public_wire_article,
)
from engine.earnings_narrative.story_store import write_story_packet_generation
from engine.earnings_transcript_intake import canonical_body_sha256
from engine.research_vault.r2_store import LocalStore
from scripts.build_earnings_public_wire import PublicWireBuildError, publish_public_wire


ROOT = Path(__file__).resolve().parents[1]


def _staged_publication(tmp_path: Path) -> tuple[Path, Path, str]:
    body = {
        "schema": "mastermind.tx/v1",
        "ticker": "AAPL",
        "id": "2026Q1",
        "period": "Q1 FY2026",
        "date": "2026-01-30",
        "title": "AAPL earnings call",
        "segments": [
            {
                "speaker": "Chief Executive Officer",
                "role": "executive",
                "text": "Revenue grew 12% to 120 million, while gross margin reached 45%.",
            },
            {
                "speaker": "Chief Financial Officer",
                "role": "executive",
                "text": "We expect revenue of 500 million and an operating margin of 20%.",
            },
            {
                "speaker": "Chief Executive Officer",
                "role": "executive",
                "text": "We will invest 50 million in capacity and continue repurchases.",
            },
            {
                "speaker": "Chief Financial Officer",
                "role": "executive",
                "text": "Supply constraints could pressure margins by 200 bps.",
            },
        ],
    }
    body_sha = canonical_body_sha256(body)
    index = {
        "schema": "mastermind.tx-index/v1",
        "generated_at": "2026-02-01T00:00:00Z",
        "symbols": {"AAPL": ["2026Q1"]},
        "revisions": {"AAPL/2026Q1": body_sha},
        "dates": {"AAPL/2026Q1": "2026-01-30"},
        "body_count": 1,
        "symbol_count": 1,
    }
    fact_pack, claim_graph = build_evidence_pair(
        body,
        index_payload=index,
        indexed_body_sha256=body_sha,
        index_generated_at=index["generated_at"],
    )
    evidence = tmp_path / "evidence"
    write_generation(
        evidence,
        [EvidencePair(fact_pack=fact_pack, claim_graph=claim_graph, transcript=body)],
        coverage={
            "selection_policy": "explicit_input",
            "batch_limit": 1,
            "historical_completeness": False,
            "index_body_count": 1,
            "index_generated_at": index["generated_at"],
        },
    )
    story_store = tmp_path / "story"
    _generation, source_manifest = write_story_packet_generation(story_store, evidence)
    source_manifest_bytes = (story_store / "manifest.json").read_bytes()
    entry = source_manifest["packets"]["AAPL/2026Q1"]
    packet_bytes = (story_store / entry["object_key"]).read_bytes()
    packet = json.loads(packet_bytes)
    receipt = source_manifest["files"][entry["object_key"]]
    article = compile_public_wire_article(
        packet,
        policy_snapshot=source_manifest["policy"]["snapshot"],
        generation_id=source_manifest["generation_id"],
        object_key=entry["object_key"],
        object_sha256=receipt["sha256"],
        object_bytes=receipt["bytes"],
    )
    publication = build_public_wire_manifest(
        [article],
        source_generation_id=source_manifest["generation_id"],
        source_manifest_sha256=sha256(source_manifest_bytes).hexdigest(),
        source_packet_count=1,
        source_packet_manifest_schema=source_manifest["schema"],
    )
    public_dir = tmp_path / "public" / "site" / "stocks" / "earnings"
    private_dir = tmp_path / "private-stage"
    publish_public_wire(
        publication,
        out_dir=public_dir,
        private_out_dir=private_dir,
        company_reader=lambda _params: {
            "available": True,
            "generation_id": "c" * 24,
            "company": {"display_name": "Apple Inc."},
            "latest_event": {
                "fiscal_year": 2026,
                "fiscal_quarter": 1,
                "call_date": "2026-01-30",
            },
            "history": [],
        },
    )
    return public_dir, private_dir, str(article["event"]["slug"])


def test_private_generation_is_off_repo_receipted_and_api_readable(tmp_path: Path) -> None:
    public_dir, private_dir, slug = _staged_publication(tmp_path)
    assert not (public_dir.parents[1] / "premiumdata").exists()
    assert (private_dir / "records" / f"{slug}.json").is_file()
    assert (private_dir / "context" / "latest.json").is_file()

    prepared = prepare_private_publication(private_dir)
    store = LocalStore(tmp_path / "private-r2")
    pointer = publish_private_publication(store, prepared)
    assert pointer["generation_id"] == prepared.generation_id
    assert store.get_bytes(POINTER_KEY) is not None

    current = load_private_manifest(store)
    assert current["record_count"] == 1
    record = load_private_record(store, slug, manifest=current)
    assert record["schema"] == "earnings.tier_payload/v1"
    assert record["locked_facts"] >= 1
    packet, catalog, receipt = load_private_context_packet(store, "AAPL", manifest=current)
    assert packet["event"]["ticker"] == "AAPL"
    assert packet["authority"]["prophet_authority"] is False
    assert catalog["objects"]["AAPL"]["sha256"] == receipt["sha256"]


def test_private_publisher_rejects_tampering_and_unexpected_files(tmp_path: Path) -> None:
    _public_dir, private_dir, slug = _staged_publication(tmp_path)
    record_path = private_dir / "records" / f"{slug}.json"
    record = json.loads(record_path.read_bytes())
    record["facts_html"] = '<script>location="https://attacker.test"</script>'
    record_path.write_bytes(canonical_json_bytes(record))
    with pytest.raises(EarningsPrivatePublicationError, match="active content"):
        prepare_private_publication(private_dir)

    _public_dir, private_dir, _slug = _staged_publication(tmp_path / "second")
    (private_dir / "operator-note.txt").write_text("must not publish", encoding="utf-8")
    with pytest.raises(EarningsPrivatePublicationError, match="unexpected files"):
        prepare_private_publication(private_dir)


def test_private_context_rejects_packet_beyond_generation_cutoff(tmp_path: Path) -> None:
    from engine.neuralweb.earnings_context_reader import read_earnings_evidence

    _public_dir, private_dir, _slug = _staged_publication(tmp_path)
    context_dir = private_dir / "context"
    manifest_path = context_dir / "latest.json"
    manifest = json.loads(manifest_path.read_bytes())
    ticker = next(iter(manifest["objects"]))
    packet_path = context_dir / manifest["objects"][ticker]["path"]
    packet = json.loads(packet_path.read_bytes())

    # Rebind every receipt and identity after moving the packet into the future.
    # Independent hashes alone must not make it valid for an older PIT catalog.
    packet["source"]["known_at"] = "2099-01-01T00:00:00Z"
    packet["context_id"] = "earnctx_" + ("0" * 32)
    packet["context_id"] = "earnctx_" + sha256(canonical_json_bytes(packet)).hexdigest()[:32]
    packet_body = canonical_json_bytes(packet)
    packet_path.write_bytes(packet_body)
    manifest["objects"][ticker].update({
        "context_id": packet["context_id"],
        "sha256": sha256(packet_body).hexdigest(),
        "bytes": len(packet_body),
    })
    manifest["generation_id"] = "earnctxgen_" + ("0" * 32)
    manifest["generation_id"] = (
        "earnctxgen_" + sha256(canonical_json_bytes(manifest)).hexdigest()[:32]
    )
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    with pytest.raises(EarningsPrivatePublicationError, match="context packet AAPL is invalid") as exc:
        prepare_private_publication(private_dir)
    assert "knowledge cutoff" in str(exc.value.__cause__)
    replay = read_earnings_evidence({"ticker": ticker}, root=private_dir)
    assert replay["available"] is False
    assert "knowledge cutoff" in replay["note"]


def test_private_output_refuses_every_path_inside_public_repository() -> None:
    from engine.neuralweb.earnings_context_reader import _context_dir
    from scripts.build_earnings_public_wire import _private_output_dir

    with pytest.raises(PublicWireBuildError, match="outside the public repository"):
        _private_output_dir(ROOT / "site" / "premiumdata" / "earnings")
    with pytest.raises(PublicWireBuildError, match="outside the public repository"):
        _private_output_dir(ROOT / "data" / "earnings-private")
    assert _context_dir(ROOT) is None
    assert _context_dir(ROOT / "site" / "premiumdata" / "earnings") is None


def test_repo_local_context_override_cannot_reopen_public_static_path(
    monkeypatch,
) -> None:
    from engine.neuralweb.earnings_context_reader import _context_dir

    monkeypatch.setenv(
        "EARNINGS_EVIDENCE_CONTEXT_DIR",
        str(ROOT / "site" / "premiumdata" / "earnings" / "context"),
    )
    assert _context_dir() is None


def test_private_pointer_is_published_last_and_idempotently(tmp_path: Path) -> None:
    _public_dir, private_dir, _slug = _staged_publication(tmp_path)
    prepared = prepare_private_publication(private_dir)
    store = LocalStore(tmp_path / "private-r2")
    first = publish_private_publication(store, prepared)
    second = publish_private_publication(store, prepared)
    assert second == first
    assert load_private_manifest(store)["generation_id"] == prepared.generation_id


def test_zero_locked_records_is_a_valid_context_only_private_generation(tmp_path: Path) -> None:
    from scripts.build_earnings_public_wire import _write_premium_payloads

    empty_stage = tmp_path / "empty-stage"
    _write_premium_payloads(
        [{"locked_facts": []}],
        private_out_dir=empty_stage,
    )
    assert (empty_stage / "records").is_dir()
    assert list((empty_stage / "records").iterdir()) == []

    _public_dir, private_dir, _slug = _staged_publication(tmp_path / "context-source")
    for record in (private_dir / "records").glob("*.json"):
        record.unlink()
    prepared = prepare_private_publication(private_dir)
    assert prepared.manifest["record_count"] == 0
    assert prepared.manifest["ticker_count"] == 1
    store = LocalStore(tmp_path / "context-only-r2")
    publish_private_publication(store, prepared)
    assert load_private_manifest(store)["record_count"] == 0
