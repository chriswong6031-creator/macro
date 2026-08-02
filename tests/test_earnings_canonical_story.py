from __future__ import annotations

import ast
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from engine.earnings_narrative.contracts import (
    ContractError,
    EXECUTION_RECEIPT,
    canonical_json_bytes,
)
from engine.earnings_narrative.digest import (
    build_event_digest,
    validate_event_digest,
    validate_event_digest_against_evidence,
)
from engine.earnings_narrative.extract import build_evidence_pair
from engine.earnings_narrative.story import (
    build_canonical_story,
    derivative_ids,
    validate_canonical_story,
    validate_correction_against_prior,
    validate_story_against_digest,
)
from engine.earnings_transcript_intake import canonical_body_sha256
from engine.press import validators, writer
from engine.press.earnings_adapter import story_to_press_slot
from scripts.build_earnings_story_packet import build_packet, load_published_packet


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
                "speaker": "Operator",
                "role": "operator",
                "text": "We will now begin the question-and-answer session.",
            },
            {
                "speaker": "Research Analyst",
                "role": "analyst",
                "text": "Can you discuss customer demand and the 10% slowdown in Europe?",
            },
            {
                "speaker": "Chief Financial Officer",
                "role": "executive",
                "text": "Demand remains strong, but supply constraints could pressure margins by 200 bps.",
            },
        ],
    }


def _index(body: dict, *, generated_at: str = "2026-02-01T00:00:00Z") -> dict:
    body_hash = canonical_body_sha256(body)
    return {
        "schema": "mastermind.tx-index/v1",
        "generated_at": generated_at,
        "symbols": {body["ticker"]: [body["id"]]},
        "revisions": {f"{body['ticker']}/{body['id']}": body_hash},
        "dates": {f"{body['ticker']}/{body['id']}": body["date"]},
        "body_count": 1,
        "symbol_count": 1,
    }


def _pair(body: dict, *, generated_at: str = "2026-02-01T00:00:00Z") -> tuple[dict, dict]:
    index = _index(body, generated_at=generated_at)
    return build_evidence_pair(
        body,
        index_payload=index,
        indexed_body_sha256=index["revisions"][f"{body['ticker']}/{body['id']}"],
        index_generated_at=index["generated_at"],
    )


def _digest(body: dict | None = None) -> tuple[dict, dict, dict, dict]:
    body = body or _body()
    pack, graph = _pair(body)
    digest = build_event_digest(pack, graph, body)
    return body, pack, graph, digest


def test_digest_story_and_press_slot_are_deterministic_receipt_complete() -> None:
    body, pack, graph, digest = _digest()
    replay = build_event_digest(pack, graph, body)
    assert canonical_json_bytes(digest) == canonical_json_bytes(replay)
    validate_event_digest_against_evidence(digest, pack, graph, body)
    assert digest["citation_coverage"] == 1.0
    assert digest["execution"] == EXECUTION_RECEIPT
    assert digest["guidance"]
    assert digest["capital_allocation"]
    assert digest["qa_exchanges"]
    assert digest["risks"]
    assert "single_source_transcript_only" in digest["quality"]["warnings"]
    assert all(item["evidence"][0]["kind"] == "quote" for item in digest["facts"])

    story = build_canonical_story(
        digest,
        tier="A",
        reasons=["material guidance and risk evidence", "multiple exact numeric receipts"],
        decision_source="governed_triage",
    )
    validate_story_against_digest(story, digest)
    assert story["status"] == "source_ready"
    assert story["approved_claim_ids"] == digest["claims"]
    assert story["copy"]["headline"] is None
    assert story["seo"]["indexing"] == "noindex_until_approved"
    assert story["execution"] == EXECUTION_RECEIPT

    slot = story_to_press_slot(story, digest)
    assert slot["model_key"] == "press_research"
    assert slot["min_anchored_receipts"] == 5
    assert slot["sources"] == ["chronicle:defeatbeta:AAPL:2026Q1"]
    assert slot["source_revisions"][slot["sources"][0]] == f"sha256:{pack['source']['body_sha256']}"
    assert slot["approved_claim_ids"] == digest["claims"]
    assert slot["article_derivative_id"] == story["derivatives"]["article_id"]


def test_closed_contracts_reject_claim_numeric_and_field_invention() -> None:
    _body_value, _pack, _graph, digest = _digest()
    extra = deepcopy(digest)
    extra["summary"] = "unsupported prose"
    with pytest.raises(ContractError, match="fields mismatch"):
        validate_event_digest(extra)

    forged_number = deepcopy(digest)
    numeric = next(
        evidence
        for fact in forged_number["facts"]
        for evidence in fact["evidence"]
        if evidence["kind"] == "numeric"
    )
    numeric["numeric_value"] = 999
    with pytest.raises(ContractError, match="numeric evidence"):
        validate_event_digest(forged_number)

    story = build_canonical_story(
        digest, tier="B", reasons=["governed article candidate"], decision_source="governed_triage",
    )
    changed_claim_set = deepcopy(story)
    changed_claim_set["approved_claim_ids"] = changed_claim_set["approved_claim_ids"][1:]
    with pytest.raises(ContractError, match="approved spans"):
        validate_canonical_story(changed_claim_set)

    slot = story_to_press_slot(story, digest)
    report = validators.check_fact_anchor(
        {"body_html": "<p>Revenue reached 999 million.</p>"}, slot, {"validators": {}}
    )
    assert report["ok"] is False
    assert "999" in report["metrics"]["unanchored"]


def test_digest_rejects_rehashed_claim_to_wrong_fact_and_selection_disclosure() -> None:
    _body_value, _pack, _graph, digest = _digest()
    forged_binding = deepcopy(digest)
    first = forged_binding["facts"][0]["evidence"][0]
    other = next(
        evidence
        for fact in forged_binding["facts"][1:]
        for evidence in fact["evidence"]
        if evidence["fact_id"] != first["fact_id"]
    )
    first["fact_id"] = other["fact_id"]
    with pytest.raises(ContractError, match="claim_id must bind fact_id"):
        validate_event_digest(forged_binding)

    forged_selection = deepcopy(digest)
    forged_selection["selection"]["candidate_count"] = 0
    with pytest.raises(ContractError, match="candidate_count"):
        validate_event_digest(forged_selection)


def test_transcript_correction_keeps_story_identity_and_invalidates_derivatives() -> None:
    first_body, _first_pack, _first_graph, first_digest = _digest()
    first_story = build_canonical_story(
        first_digest,
        tier="A",
        reasons=["initial governed promotion"],
        decision_source="governed_triage",
    )
    corrected_body = _body(
        guidance="For the full year, we expect revenue of 510 million and an operating margin of 21%."
    )
    corrected_pack, corrected_graph = _pair(corrected_body, generated_at="2026-02-02T00:00:00Z")
    corrected_digest = build_event_digest(corrected_pack, corrected_graph, corrected_body)
    corrected_story = build_canonical_story(
        corrected_digest,
        tier="A",
        reasons=["corrected source revision retained promotion"],
        decision_source="governed_triage",
        prior_story=first_story,
    )
    assert canonical_body_sha256(first_body) != canonical_body_sha256(corrected_body)
    assert corrected_story["story_id"] == first_story["story_id"]
    assert corrected_story["story_revision_id"] != first_story["story_revision_id"]
    assert corrected_story["correction"]["status"] == "corrected"
    assert corrected_story["correction"]["supersedes_revision_id"] == first_story["story_revision_id"]
    assert corrected_story["correction"]["invalidates_derivative_ids"] == derivative_ids(first_story)
    validate_correction_against_prior(corrected_story, first_story)
    with pytest.raises(ContractError, match="requires its prior"):
        story_to_press_slot(corrected_story, corrected_digest)
    corrected_slot = story_to_press_slot(
        corrected_story, corrected_digest, prior_story=first_story,
    )
    assert corrected_slot["canonical_story_revision_id"] == corrected_story["story_revision_id"]

    forged_parent = deepcopy(corrected_story)
    forged_parent["correction"]["supersedes_revision_id"] = "storyrev_" + "f" * 32
    forged_parent["story_revision_id"] = "storyrev_" + "0" * 32
    forged_parent["story_revision_id"] = "storyrev_" + sha256(
        canonical_json_bytes(forged_parent)
    ).hexdigest()[:32]
    validate_canonical_story(forged_parent)
    with pytest.raises(ContractError, match="differs from prior"):
        validate_correction_against_prior(forged_parent, first_story)
    with pytest.raises(ContractError, match="differs from prior"):
        story_to_press_slot(forged_parent, corrected_digest, prior_story=first_story)


def test_insufficient_digest_stays_tier_c_and_cannot_enter_press() -> None:
    body = _body(guidance="Management discussed priorities.")
    body["segments"] = [{"speaker": "Executive", "role": "executive", "text": "Management discussed priorities."}]
    pack, graph = _pair(body)
    digest = build_event_digest(pack, graph, body)
    assert digest["facts"] == []
    assert digest["quality"]["status"] == "insufficient"
    assert "no_material_sentences" in digest["quality"]["insufficiency"]
    story = build_canonical_story(digest)
    assert story["promotion"]["tier"] == "C"
    assert story["derivatives"]["article_id"] is None
    with pytest.raises(ContractError, match="not eligible"):
        story_to_press_slot(story, digest)
    with pytest.raises(ContractError, match="requires a ready"):
        build_canonical_story(
            digest, tier="B", reasons=["invalid promotion"], decision_source="operator",
        )


def test_distribution_compilers_import_no_provider_or_network_clients() -> None:
    import engine.earnings_narrative.digest as digest_module
    import engine.earnings_narrative.story as story_module
    import engine.press.earnings_adapter as adapter_module

    for module in (digest_module, story_module, adapter_module):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in getattr(node, "names", [])
        }
        assert not imports & {"openai", "anthropic", "boto3", "requests", "httpx"}


def _write_evidence_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    body = _body()
    pack, graph = _pair(body)
    paths = (
        tmp_path / "fact_pack.json",
        tmp_path / "claim_graph.json",
        tmp_path / "source_body.json",
    )
    for path, payload in zip(paths, (pack, graph, body), strict=True):
        path.write_bytes(canonical_json_bytes(payload))
    return paths


def test_packet_builder_writes_replay_stable_tier_a_outputs(tmp_path: Path) -> None:
    fact_pack_path, claim_graph_path, source_body_path = _write_evidence_fixture(tmp_path)
    out_dir = tmp_path / "packet"
    first = build_packet(
        fact_pack_path,
        claim_graph_path,
        source_body_path,
        out_dir,
        tier="A",
        reasons=["governed material event"],
        decision_source="governed_triage",
    )
    first_pointer_bytes = (out_dir / "latest.json").read_bytes()
    first_generation = out_dir / first["packet_pointer"]["generation_path"]
    first_names = sorted(path.name for path in out_dir.iterdir())
    first_generation_bytes = {
        path.name: path.read_bytes() for path in sorted(first_generation.iterdir())
    }
    second = build_packet(
        fact_pack_path,
        claim_graph_path,
        source_body_path,
        out_dir,
        tier="A",
        reasons=["governed material event"],
        decision_source="governed_triage",
    )
    assert first_names == ["generations", "latest.json"]
    assert sorted(first_generation_bytes) == [
        "canonical_story.json", "event_digest.json", "press_slot.json",
    ]
    assert first_pointer_bytes == (out_dir / "latest.json").read_bytes()
    assert first_generation_bytes == {
        path.name: path.read_bytes() for path in sorted(first_generation.iterdir())
    }
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    loaded = load_published_packet(out_dir)
    assert canonical_json_bytes(loaded) == canonical_json_bytes(second)


def test_packet_builder_tier_c_removes_stale_press_slot(tmp_path: Path) -> None:
    fact_pack_path, claim_graph_path, source_body_path = _write_evidence_fixture(tmp_path)
    out_dir = tmp_path / "packet"
    tier_a = build_packet(
        fact_pack_path,
        claim_graph_path,
        source_body_path,
        out_dir,
        tier="A",
        reasons=["governed material event"],
        decision_source="governed_triage",
    )
    tier_a_generation = out_dir / tier_a["packet_pointer"]["generation_path"]
    assert (tier_a_generation / "press_slot.json").exists()
    result = build_packet(fact_pack_path, claim_graph_path, source_body_path, out_dir)
    assert result["press_slot"] is None
    current_generation = out_dir / result["packet_pointer"]["generation_path"]
    assert not (current_generation / "press_slot.json").exists()
    assert (current_generation / "event_digest.json").exists()
    assert (current_generation / "canonical_story.json").exists()
    assert tier_a_generation != current_generation
    assert (tier_a_generation / "press_slot.json").exists()


def test_packet_builder_fails_closed_before_writing_forged_evidence(tmp_path: Path) -> None:
    fact_pack_path, claim_graph_path, source_body_path = _write_evidence_fixture(tmp_path)
    forged_pack = json.loads(fact_pack_path.read_text(encoding="utf-8"))
    forged_pack["facts"][0]["text"] = "Unsupported replacement."
    fact_pack_path.write_bytes(canonical_json_bytes(forged_pack))
    out_dir = tmp_path / "packet"
    with pytest.raises(ContractError):
        build_packet(fact_pack_path, claim_graph_path, source_body_path, out_dir, tier="A")
    assert not out_dir.exists()


def test_article_promotion_requires_deterministic_receipt_floor(tmp_path: Path) -> None:
    body = _body()
    body["segments"] = [{
        "speaker": "Chief Financial Officer",
        "role": "executive",
        "text": "Revenue grew 12% during the quarter.",
    }]
    pack, graph = _pair(body)
    paths = (
        tmp_path / "fact_pack.json",
        tmp_path / "claim_graph.json",
        tmp_path / "source_body.json",
    )
    for path, payload in zip(paths, (pack, graph, body), strict=True):
        path.write_bytes(canonical_json_bytes(payload))
    out_dir = tmp_path / "packet"
    with pytest.raises(ContractError, match="lacks distinct numeric receipts"):
        build_packet(
            *paths,
            out_dir,
            tier="A",
            reasons=["invalid thin promotion"],
            decision_source="operator",
        )
    assert not out_dir.exists()


def test_article_receipt_floor_excludes_calendar_years() -> None:
    body = _body()
    body["segments"] = [{
        "speaker": "Chief Financial Officer",
        "role": "executive",
        "text": "Revenue planning spans 2020, 2021, 2022, 2023, 2024, 2025, and 2026.",
    }]
    pack, graph = _pair(body)
    digest = build_event_digest(pack, graph, body)
    with pytest.raises(ContractError, match="lacks distinct numeric receipts"):
        build_canonical_story(
            digest,
            tier="A",
            reasons=["calendar labels are not receipts"],
            decision_source="operator",
        )


def test_press_claim_scope_is_prompted_and_deterministically_enforced() -> None:
    _body_value, _pack, _graph, digest = _digest()
    story = build_canonical_story(
        digest,
        tier="A",
        reasons=["governed material event"],
        decision_source="governed_triage",
    )
    slot = story_to_press_slot(story, digest)
    fact = slot["facts"][0]
    claim_ids = " ".join(fact["claim_ids"])
    draft = {
        "title": slot["story"]["title_hint"],
        "description": fact["text"],
        "slug": slot["slug_hint"],
        "body_html": (
            f'<p class="press-byline">{slot["byline"]}</p>'
            f'<p data-claim-ids="{claim_ids}">{fact["text"]}</p>'
            '<p class="press-footer">Educational content — not investment advice. Markets involve risk.</p>'
        ),
    }
    report = validators.check_claim_scope(draft, slot, {})
    assert report["ok"] is True
    _system, prompt = writer.build_prompt(slot, {}, attempt=0)
    assert "data-claim-ids" in prompt
    assert fact["claim_ids"][0] in prompt

    missing = deepcopy(draft)
    missing["body_html"] = missing["body_html"].replace(
        f' data-claim-ids="{claim_ids}"', "",
    )
    assert validators.check_claim_scope(missing, slot, {})["ok"] is False

    unsupported = deepcopy(draft)
    unsupported["body_html"] = unsupported["body_html"].replace(
        fact["text"], "A lunar colony will double cryptocurrency demand next week.", 1,
    )
    scoped = validators.check_claim_scope(unsupported, slot, {})
    assert scoped["ok"] is False
    assert scoped["metrics"]["unsupported_sentences"]

    reversed_direction = deepcopy(draft)
    reversed_direction["body_html"] = reversed_direction["body_html"].replace(
        fact["text"], "Revenue fell 12% while gross margin reached 45%.", 1,
    )
    direction_report = validators.check_claim_scope(reversed_direction, slot, {})
    assert direction_report["ok"] is False
    assert direction_report["metrics"]["unsupported_sentences"]

    sensational_title = deepcopy(draft)
    sensational_title["title"] = "AAPL Faces Existential Collapse"
    assert validators.check_claim_scope(sensational_title, slot, {})["ok"] is False

    raw_bypass = deepcopy(draft)
    raw_bypass["body_html"] += "<div>A lunar colony will double cryptocurrency demand.</div>"
    bypass_report = validators.check_claim_scope(raw_bypass, slot, {})
    assert bypass_report["ok"] is False
    assert any("unscoped" in item for item in bypass_report["metrics"]["missing_attributes"])

    # Source-ready canonical packets are extractive by contract.  These are
    # semantic changes that a shared-word / numeric-overlap checker accepted:
    # the source fact must remain exact until a separately attested verifier
    # exists.
    for label, changed in {
        "invented cause": "Revenue grew 12% to 120 million because demand accelerated, while gross margin reached 45%.",
        "changed negation": "Revenue didn't grow 12% to 120 million, while gross margin reached 45%.",
        "spelled numeric rewrite": "Revenue grew twelve percent to 120 million, while gross margin reached 45%.",
    }.items():
        altered = deepcopy(draft)
        altered["body_html"] = altered["body_html"].replace(fact["text"], changed, 1)
        report = validators.check_claim_scope(altered, slot, {})
        assert report["ok"] is False, label
        assert report["metrics"]["unsupported_sentences"], label

    uncertain_fact = next(
        item for item in slot["facts"] if "could pressure margins" in item["text"]
    )
    certain_draft = {
        "title": slot["story"]["title_hint"],
        "description": uncertain_fact["text"],
        "slug": slot["slug_hint"],
        "body_html": (
            f'<p class="press-byline">{slot["byline"]}</p>'
            f'<p data-claim-ids="{" ".join(uncertain_fact["claim_ids"])}">'
            "Demand remains strong, but supply constraints will pressure margins by 200 bps.</p>"
            '<p class="press-footer">Educational content — not investment advice. Markets involve risk.</p>'
        ),
    }
    certain_report = validators.check_claim_scope(certain_draft, slot, {})
    assert certain_report["ok"] is False
    assert certain_report["metrics"]["unsupported_sentences"]

    implied_description = deepcopy(draft)
    implied_description["description"] = "Revenue growth proves demand has structurally turned for the company."
    assert validators.check_claim_scope(implied_description, slot, {})["ok"] is False

    implied_title = deepcopy(draft)
    implied_title["title"] = "AAPL revenue growth proves demand has structurally turned"
    assert validators.check_claim_scope(implied_title, slot, {})["ok"] is False

    self_attested = deepcopy(slot)
    self_attested["canonical_story_status"] = "approved"
    self_attested["canonical_emit_allowed"] = True
    assert validators.check_claim_scope(draft, self_attested, {})["ok"] is False


def test_packet_builder_cli_is_directly_executable() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/build_earnings_story_packet.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--fact-pack" in completed.stdout


def test_packet_pointer_rejects_tampered_immutable_generation(tmp_path: Path) -> None:
    fact_pack_path, claim_graph_path, source_body_path = _write_evidence_fixture(tmp_path)
    out_dir = tmp_path / "packet"
    result = build_packet(
        fact_pack_path,
        claim_graph_path,
        source_body_path,
        out_dir,
        tier="A",
        reasons=["governed material event"],
        decision_source="governed_triage",
    )
    generation = out_dir / result["packet_pointer"]["generation_path"]
    story_path = generation / "canonical_story.json"
    story_path.write_bytes(story_path.read_bytes() + b" ")
    with pytest.raises(ContractError, match="receipt mismatch"):
        load_published_packet(out_dir)
    with pytest.raises(ContractError, match="generation collision"):
        build_packet(
            fact_pack_path,
            claim_graph_path,
            source_body_path,
            out_dir,
            tier="A",
            reasons=["governed material event"],
            decision_source="governed_triage",
        )


def test_corrected_packet_carries_and_replays_exact_prior_manifest(tmp_path: Path) -> None:
    first_paths = _write_evidence_fixture(tmp_path / "first")
    first_out = tmp_path / "first_packet"
    first = build_packet(
        *first_paths,
        first_out,
        tier="A",
        reasons=["initial governed material event"],
        decision_source="governed_triage",
    )
    prior_path = (
        first_out / first["packet_pointer"]["generation_path"] / "canonical_story.json"
    )

    corrected_body = _body(
        guidance="For the full year, we expect revenue of 510 million and an operating margin of 21%."
    )
    corrected_pack, corrected_graph = _pair(
        corrected_body, generated_at="2026-02-02T00:00:00Z",
    )
    corrected_root = tmp_path / "corrected"
    corrected_root.mkdir()
    corrected_paths = (
        corrected_root / "fact_pack.json",
        corrected_root / "claim_graph.json",
        corrected_root / "source_body.json",
    )
    for path, payload in zip(
        corrected_paths, (corrected_pack, corrected_graph, corrected_body), strict=True,
    ):
        path.write_bytes(canonical_json_bytes(payload))
    corrected_out = tmp_path / "corrected_packet"
    corrected = build_packet(
        *corrected_paths,
        corrected_out,
        tier="A",
        reasons=["corrected governed material event"],
        decision_source="governed_triage",
        prior_story_path=prior_path,
    )
    loaded = load_published_packet(corrected_out)
    assert loaded["prior_story"] == first["canonical_story"]
    assert loaded["canonical_story"]["correction"]["status"] == "corrected"
    assert "prior_story.json" in loaded["packet_pointer"]["files"]
    assert loaded["press_slot"] == corrected["press_slot"]
