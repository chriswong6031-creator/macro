from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from engine.earnings_narrative.contracts import ContractError, canonical_json_sha256
from engine.earnings_narrative.extract import build_evidence_pair
from engine.earnings_narrative.generation import EvidencePair, write_generation
from engine.earnings_narrative.promotion import load_promotion_policy
from engine.earnings_narrative.story_packets import (
    build_story_packet,
    evidence_receipts_from_manifest,
    load_evidence_event,
    validate_story_packet_manifest,
)
from engine.earnings_narrative.story_store import (
    _verify_lineage_transition,
    verify_story_packet_store,
    write_story_packet_generation,
)
from engine.earnings_transcript_intake import canonical_body_sha256


def _body(*, guidance: str = "For the full year, we expect revenue of 500 million and an operating margin of 20%.") -> dict:
    return {
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
                "text": guidance,
            },
            {
                "speaker": "Chief Executive Officer",
                "role": "executive",
                "text": "We will invest 50 million in capacity and continue our share repurchase program.",
            },
            {
                "speaker": "Research Analyst",
                "role": "analyst",
                "text": "Can you discuss customer demand and the 10% slowdown in Europe?",
            },
        ],
    }


def _pair(body: dict, *, generated_at: str) -> tuple[dict, dict]:
    body_sha = canonical_body_sha256(body)
    index = {
        "schema": "mastermind.tx-index/v1",
        "generated_at": generated_at,
        "symbols": {"AAPL": ["2026Q1"]},
        "revisions": {"AAPL/2026Q1": body_sha},
        "dates": {"AAPL/2026Q1": "2026-01-30"},
        "body_count": 1,
        "symbol_count": 1,
    }
    return build_evidence_pair(
        body,
        index_payload=index,
        indexed_body_sha256=body_sha,
        index_generated_at=generated_at,
    )


def _write_evidence(root: Path, body: dict, *, generated_at: str) -> dict:
    fact_pack, claim_graph = _pair(body, generated_at=generated_at)
    _path, manifest = write_generation(
        root,
        [EvidencePair(fact_pack=fact_pack, claim_graph=claim_graph, transcript=body)],
        coverage={
            "selection_policy": "explicit_input",
            "batch_limit": 1,
            "historical_completeness": False,
            "index_body_count": 1,
            "index_generated_at": generated_at,
        },
    )
    return manifest


def _current_packet(store: Path, manifest: dict) -> dict:
    index = manifest["packets"]["AAPL/2026Q1"]
    receipt = manifest["files"][index["object_key"]]
    path = store / receipt["object_key"]
    import json
    return json.loads(path.read_text(encoding="utf-8"))


def test_store_binds_exact_evidence_root_and_reuses_unchanged_packet(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    store = tmp_path / "story-packets"
    evidence_manifest = _write_evidence(evidence, _body(), generated_at="2026-02-01T00:00:00Z")
    _generation, manifest = write_story_packet_generation(store, evidence)
    validate_story_packet_manifest(manifest)
    assert manifest["evidence_root"]["generation_id"] == evidence_manifest["generation_id"]
    assert manifest["evidence_root"]["manifest_sha256"] == canonical_json_sha256(evidence_manifest)
    packet = _current_packet(store, manifest)
    assert packet["story"]["promotion"]["tier"] == "B"
    assert packet["press_slot"] is not None
    assert packet["press_slot"]["canonical_emit_allowed"] is False
    assert "slowdown in Europe" not in packet["press_slot"]["raw_documents"][0]["text"]
    health = verify_story_packet_store(store)
    assert health["status"] == "ready"
    assert health["packet_count"] == 1

    _same_generation, same = write_story_packet_generation(store, evidence)
    assert same["generation_id"] == manifest["generation_id"]
    assert same["packets"] == manifest["packets"]


def test_source_correction_keeps_story_identity_and_records_prior_invalidation(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    store = tmp_path / "story-packets"
    _write_evidence(evidence, _body(), generated_at="2026-02-01T00:00:00Z")
    _first_path, first_manifest = write_story_packet_generation(store, evidence)
    first_packet = _current_packet(store, first_manifest)

    # Same logical event, changed immutable transcript revision.
    _write_evidence(
        evidence,
        _body(guidance="For the full year, we expect revenue of 510 million and an operating margin of 21%."),
        generated_at="2026-02-02T00:00:00Z",
    )
    _corrected_path, corrected_manifest = write_story_packet_generation(store, evidence)
    corrected = _current_packet(store, corrected_manifest)
    assert corrected["story"]["story_id"] == first_packet["story"]["story_id"]
    assert corrected["story"]["story_revision_id"] != first_packet["story"]["story_revision_id"]
    assert corrected["story"]["correction"]["status"] == "corrected"
    assert corrected["prior"]["packet_id"] == first_packet["packet_id"]
    assert corrected["story"]["correction"]["invalidates_derivative_ids"] == sorted({
        item for item in first_packet["story"]["derivatives"].values() if isinstance(item, str)
    } | {
        item for name in ("x_post_ids", "short_form_ids") for item in first_packet["story"]["derivatives"][name]
    })
    health = verify_story_packet_store(store)
    assert health["status"] == "ready"

    forged_packet = deepcopy(corrected)
    forged_packet["prior"]["packet_id"] = "storypacket_" + "0" * 32
    with pytest.raises(ContractError, match="direct parent packet id"):
        _verify_lineage_transition(
            corrected_manifest,
            {"AAPL/2026Q1": forged_packet},
            first_manifest,
            {"AAPL/2026Q1": first_packet},
        )

    forged = deepcopy(corrected_manifest)
    forged["packets"] = {}
    forged["files"] = {}
    forged["generation_id"] = "0" * 32
    # Closed contract catches the forged content receipt before a shrinking
    # marker could be promoted.  The store health also checks real ancestry.
    with pytest.raises(ContractError):
        validate_story_packet_manifest(forged)


def test_build_story_packet_requires_a_policy_snapshot_for_prior_packet(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    store = tmp_path / "story-packets"
    _write_evidence(evidence, _body(), generated_at="2026-02-01T00:00:00Z")
    _first_path, first_manifest = write_story_packet_generation(store, evidence)
    first_packet = _current_packet(store, first_manifest)

    corrected_evidence = _write_evidence(
        evidence,
        _body(guidance="For the full year, we expect revenue of 510 million and an operating margin of 21%."),
        generated_at="2026-02-02T00:00:00Z",
    )
    _manifest, fact_pack, claim_graph, transcript = load_evidence_event(
        evidence,
        key="AAPL/2026Q1",
        manifest=corrected_evidence,
    )

    with pytest.raises(ContractError, match="immutable historical policy snapshot"):
        build_story_packet(
            fact_pack,
            claim_graph,
            transcript,
            evidence=evidence_receipts_from_manifest(corrected_evidence, key="AAPL/2026Q1"),
            policy=load_promotion_policy(),
            prior_packet=first_packet,
        )
