"""E3-A shadow extraction tests — AAPL FY2026 Q3.

Pins fixture SHAs. Validates gold file integrity.
Validates shadow compiler behavior (segmenter, scoring, ledger format).

Frozen source SHAs (load-bearing — any divergence must STOP the eval):
  Exhibit 99.1: 070abd6a9cdb7070e546d24ffcbc41c65450d939c6f88f189cb18ec711cf5fdb
  Transcript:   a8ff5d03e875fef5604791edbf625186c447af049e6e02f55bb89c68c7cc9f9f

Gold:
  Path:   research/earnings_intelligence/e3/gold/aapl_fy2026_q3_qa_gold.json
  SHA256: fc6df84d2a8d0d96475ce697ba92ffdd071d5c283b8daee97c1b3381382fa42c
  Schema: aapl_fy2026_q3_qa_gold.v2
  Supersedes v1: 6b1100b148396db9a29974da5bc6e0cc55e5534185e50e061fe3635d429ed761

Taxonomy:
  version: qa_topic.v1
  hash:    a928ca72ab2e91bda74bd1e69021e08a5234e501f095610e623655db7e323b5e
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

# ── Constants ─────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent
FIXTURE_DIR = REPO_ROOT / "tests/fixtures/company_intelligence"

FROZEN_EXHIBIT_SHA = "070abd6a9cdb7070e546d24ffcbc41c65450d939c6f88f189cb18ec711cf5fdb"
FROZEN_TRANSCRIPT_SHA = "a8ff5d03e875fef5604791edbf625186c447af049e6e02f55bb89c68c7cc9f9f"

GOLD_PATH = REPO_ROOT / "research/earnings_intelligence/e3/gold/aapl_fy2026_q3_qa_gold.json"
GOLD_SHA256 = "fc6df84d2a8d0d96475ce697ba92ffdd071d5c283b8daee97c1b3381382fa42c"
SUPERSEDED_GOLD_SHA_V1 = "6b1100b148396db9a29974da5bc6e0cc55e5534185e50e061fe3635d429ed761"

TAXONOMY_VERSION = "qa_topic.v1"
TAXONOMY_HASH = "a928ca72ab2e91bda74bd1e69021e08a5234e501f095610e623655db7e323b5e"

EVENT_ID = "evt_cik0000320193_2026q3_results"
TX_DOC_ID = "tx:AAPL/2026Q3"
RELEASE_DOC_ID = "release:0000320193-26-000018"

EXPECTED_EXCHANGE_COUNT = 7
EXPECTED_SEGMENT_COUNT = 108
EXPECTED_OPERATOR_INTRO_SEGMENTS = [32, 42, 52, 63, 76, 84, 97]

CLOSED_TAXONOMY_MEMBERS = frozenset({
    "demand", "product", "pricing", "costs_supply",
    "capacity", "capital_allocation", "regulation",
    "other", "unavailable",
})


# ── SHA pin tests ──────────────────────────────────────────────────────────────


def test_exhibit_sha_pinned():
    """Exhibit 99.1 SHA must match frozen spec."""
    path = FIXTURE_DIR / "aapl_fy2026_q3_ex99_1.htm"
    assert path.exists(), f"Fixture missing: {path}"
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == FROZEN_EXHIBIT_SHA, (
        f"Exhibit 99.1 SHA divergence: actual={actual} frozen={FROZEN_EXHIBIT_SHA}"
    )


def test_transcript_sha_pinned():
    """Transcript SHA (uncompressed) must match frozen spec."""
    path = FIXTURE_DIR / "aapl_fy2026_q3.json.gz"
    assert path.exists(), f"Fixture missing: {path}"
    with gzip.open(path) as f:
        actual = hashlib.sha256(f.read()).hexdigest()
    assert actual == FROZEN_TRANSCRIPT_SHA, (
        f"Transcript SHA divergence: actual={actual} frozen={FROZEN_TRANSCRIPT_SHA}"
    )


def test_gold_sha_pinned():
    """Gold file SHA must match the pinned value (gold is frozen)."""
    assert GOLD_PATH.exists(), f"Gold file missing: {GOLD_PATH}"
    actual = hashlib.sha256(GOLD_PATH.read_bytes()).hexdigest()
    assert actual == GOLD_SHA256, (
        f"Gold SHA divergence: actual={actual} pinned={GOLD_SHA256}\n"
        "If you intentionally updated the gold, update GOLD_SHA256 in this test."
    )


# ── Gold file structural integrity ────────────────────────────────────────────


@pytest.fixture(scope="module")
def gold() -> dict:
    return json.loads(GOLD_PATH.read_bytes())


def test_gold_schema(gold):
    assert gold["schema"] == "aapl_fy2026_q3_qa_gold.v2"
    assert gold["supersedes"]["gold_sha256"] == SUPERSEDED_GOLD_SHA_V1


def test_gold_exchange_count(gold):
    assert gold["qa_exchange_count"] == EXPECTED_EXCHANGE_COUNT
    assert len(gold["exchanges"]) == EXPECTED_EXCHANGE_COUNT


def test_gold_source_shas(gold):
    pkg = gold["source_package"]
    sources = {s["kind"]: s for s in pkg["sources"]}
    assert sources["issuer_release"]["source_sha256"] == FROZEN_EXHIBIT_SHA
    assert sources["transcript"]["source_sha256_uncompressed"] == FROZEN_TRANSCRIPT_SHA
    assert pkg["sha_divergence_check"] == "pass"


def test_gold_event_id(gold):
    for ex in gold["exchanges"]:
        assert ex["event_id"] == EVENT_ID, f"Exchange {ex['ordinal']} has wrong event_id"


def test_gold_taxonomy_version_and_hash(gold):
    tax = gold["taxonomy"]
    assert tax["version"] == TAXONOMY_VERSION
    assert tax["hash"] == TAXONOMY_HASH
    # Recompute hash from canonical JSON
    canonical = json.dumps(
        {"schema": "qa_topic_taxonomy.v1", "version": TAXONOMY_VERSION,
         "members": sorted(tax["members"])},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    recomputed = hashlib.sha256(canonical).hexdigest()
    assert recomputed == TAXONOMY_HASH, (
        f"Taxonomy hash mismatch: recomputed={recomputed} stored={TAXONOMY_HASH}"
    )


def test_gold_taxonomy_members_closed(gold):
    members = set(gold["taxonomy"]["members"])
    assert members == CLOSED_TAXONOMY_MEMBERS, (
        f"Taxonomy members differ.\nExpected: {sorted(CLOSED_TAXONOMY_MEMBERS)}\n"
        f"Got: {sorted(members)}"
    )


def test_gold_no_open_topic_labels(gold):
    """Every topic label in every exchange must be in the closed taxonomy."""
    for ex in gold["exchanges"]:
        ordinal = ex["ordinal"]
        for topic in ex.get("topics", []):
            assert topic in CLOSED_TAXONOMY_MEMBERS, (
                f"Exchange {ordinal} has unknown topic label: {topic!r}"
            )


def test_gold_ordinals_sequential(gold):
    ordinals = [ex["ordinal"] for ex in gold["exchanges"]]
    assert ordinals == list(range(EXPECTED_EXCHANGE_COUNT))


def test_gold_exchange_ids_format(gold):
    """exchange_id format: qx_{event_id}_{document_sha256[:12]}_{ordinal:02d}"""
    sha_prefix = FROZEN_TRANSCRIPT_SHA[:12]
    for ex in gold["exchanges"]:
        expected = f"qx_{EVENT_ID}_{sha_prefix}_{ex['ordinal']:02d}"
        assert ex["exchange_id"] == expected, (
            f"Exchange {ex['ordinal']} has bad exchange_id: {ex['exchange_id']!r}\n"
            f"Expected: {expected!r}"
        )


def test_gold_document_sha_on_exchanges(gold):
    for ex in gold["exchanges"]:
        assert ex["document_sha256"] == FROZEN_TRANSCRIPT_SHA
        assert ex["document_id"] == TX_DOC_ID


def test_gold_questioner_fields(gold):
    """Questioner must have name/affiliation with source-supported states."""
    for ex in gold["exchanges"]:
        q = ex["questioner"]
        assert q["name"], f"Exchange {ex['ordinal']}: questioner name empty"
        assert q["affiliation"], f"Exchange {ex['ordinal']}: questioner affiliation empty"
        assert q["name_state"] == "source_supported"
        assert q["affiliation_state"] == "source_supported"


def test_gold_no_identity_not_in_source(gold):
    """identity_not_in_source is not a valid absence reason (freeze §7)."""
    raw = json.dumps(gold)
    assert "identity_not_in_source" not in raw, (
        "Found forbidden typed absence reason 'identity_not_in_source'"
    )


def test_gold_respondents_not_collapsed(gold):
    """Exchange 5 (Wamsi Mohan) must have both Tim Cook and John Ternus."""
    ex5 = gold["exchanges"][5]
    names = {r["name"] for r in ex5["respondents"]}
    assert "Tim Cook" in names, "Exchange 5: Tim Cook missing from respondents"
    assert "John Ternus" in names, "Exchange 5: John Ternus missing from respondents"


def test_gold_exchange_0_preserves_two_tim_answer_turns(gold):
    """Kevan 34/35 → Tim 36/37 → analyst 38 → Tim 39/40 is two Tim turns."""
    ex0 = gold["exchanges"][0]
    names = [r["name"] for r in ex0["respondents"]]
    assert names == ["Kevan Parekh", "Tim Cook", "Tim Cook"]
    assert [r["span_indexes"] for r in ex0["respondents"]] == [[0, 1], [2, 3], [4, 5]]
    assert [s["segment_index"] for s in ex0["answer_spans"]] == [34, 35, 36, 37, 39, 40]
    assert ex0["answer_spans"][2]["speaker"] == "Tim Cook"
    assert ex0["answer_spans"][4]["speaker"] == "Tim Cook"


def test_gold_respondents_are_answer_turns_not_unique_speakers(gold):
    """respondents[] partitions answer_spans; same speaker may repeat after a follow-up."""
    for ex in gold["exchanges"]:
        n_ans = len(ex["answer_spans"])
        seen: list[int] = []
        for resp in ex["respondents"]:
            seen.extend(resp["span_indexes"])
        assert seen == list(range(n_ans)), (
            f"Exchange {ex['ordinal']}: respondents do not partition answer_spans "
            f"({seen} vs {list(range(n_ans))})"
        )
    assert sum(len(ex["respondents"]) for ex in gold["exchanges"]) == 26


def test_gold_no_overlay_14(gold):
    """The exchange count must not be 14; overlay 14 is not a valid boundary count."""
    assert gold["qa_exchange_count"] != 14, "exchange_count must not be 14 (freeze §7.2)"
    assert len(gold["exchanges"]) != 14, "exchanges[] length must not be 14"


def test_gold_question_spans_nonempty(gold):
    for ex in gold["exchanges"]:
        assert ex["question_spans"], f"Exchange {ex['ordinal']}: empty question_spans"


def test_gold_span_segment_indexes_valid(gold):
    """All span segment_indexes must be within [0, 107]."""
    for ex in gold["exchanges"]:
        for span in ex["question_spans"] + ex["answer_spans"]:
            idx = span["segment_index"]
            assert 0 <= idx <= 107, (
                f"Exchange {ex['ordinal']}: segment_index {idx} out of range"
            )


def test_gold_span_byte_ranges_valid(gold):
    """All start_byte < end_byte and end_byte <= actual segment UTF-8 length."""
    with gzip.open(FIXTURE_DIR / "aapl_fy2026_q3.json.gz") as f:
        tx = json.load(f)
    segs = tx["segments"]

    for ex in gold["exchanges"]:
        for span in ex["question_spans"] + ex["answer_spans"]:
            idx = span["segment_index"]
            seg_bytes = segs[idx]["text"].encode("utf-8")
            assert span["start_byte"] == 0, (
                f"Exchange {ex['ordinal']} seg {idx}: start_byte != 0"
            )
            assert span["end_byte"] == len(seg_bytes), (
                f"Exchange {ex['ordinal']} seg {idx}: end_byte {span['end_byte']} "
                f"!= actual byte length {len(seg_bytes)}"
            )
            assert span["text_sha256"] == hashlib.sha256(seg_bytes).hexdigest()


def test_gold_respondent_span_indexes_valid(gold):
    """respondents[].span_indexes must reference valid answer_spans indexes."""
    for ex in gold["exchanges"]:
        n_ans = len(ex["answer_spans"])
        for resp in ex["respondents"]:
            for idx in resp["span_indexes"]:
                assert 0 <= idx < n_ans, (
                    f"Exchange {ex['ordinal']} respondent {resp['name']}: "
                    f"span_index {idx} out of range (n_answer_spans={n_ans})"
                )


def test_gold_usefulness_bar_written_refusal(gold):
    bar = gold["usefulness_bar"]
    assert bar["decision"] == "refusal"
    assert bar["numeric_threshold"] is None
    assert isinstance(bar["written_refusal"], str) and len(bar["written_refusal"]) > 50
    assert bar["return_to_sol"] is True


def test_gold_frozen_at_set(gold):
    assert gold.get("frozen_at"), "frozen_at timestamp must be set"


def test_gold_no_event_workspace_advance(gold):
    """Gold must not be an event_workspace.v1 payload (no workspace schema or top-level generation_id)."""
    assert gold.get("schema") != "event_workspace.v1", "Gold must not use event_workspace.v1 schema"
    assert "generation_id" not in gold, "Gold must not have a top-level generation_id (workspace field)"
    # live_generation_id in source_package is a reference, not a promotion — allowed
    assert "qa_exchanges" not in gold, "Gold must not have qa_exchanges (workspace promotion field)"


# ── Shadow compiler unit tests ────────────────────────────────────────────────


def test_verify_fixture_shas_pass():
    """SHA verification must pass on the pinned fixtures."""
    from engine.company_intelligence.e3_shadow_compiler import verify_fixture_shas
    result = verify_fixture_shas(REPO_ROOT)
    assert result["check"] == "pass"
    assert result["exhibit_sha"] == FROZEN_EXHIBIT_SHA
    assert result["transcript_sha"] == FROZEN_TRANSCRIPT_SHA


def test_stable_segment_id_deterministic():
    """stable_segment_id must be deterministic for same inputs."""
    from engine.company_intelligence.e3_shadow_compiler import stable_segment_id
    id1 = stable_segment_id(FROZEN_TRANSCRIPT_SHA, 0)
    id2 = stable_segment_id(FROZEN_TRANSCRIPT_SHA, 0)
    assert id1 == id2
    assert id1.startswith("seg_")
    # Different index → different ID
    id3 = stable_segment_id(FROZEN_TRANSCRIPT_SHA, 1)
    assert id1 != id3


def test_stable_segment_id_format():
    from engine.company_intelligence.e3_shadow_compiler import stable_segment_id
    sid = stable_segment_id(FROZEN_TRANSCRIPT_SHA, 42)
    parts = sid.split("_")
    assert parts[0] == "seg"
    assert parts[1] == FROZEN_TRANSCRIPT_SHA[:16]
    assert parts[2] == "0042"


def test_segment_count():
    from engine.company_intelligence.e3_shadow_compiler import load_transcript_segments
    segs = load_transcript_segments(REPO_ROOT)
    assert len(segs) == EXPECTED_SEGMENT_COUNT


def test_operator_intro_segments():
    """The 7 operator-delimited intro segments must exist and contain 'go ahead'."""
    from engine.company_intelligence.e3_shadow_compiler import load_transcript_segments
    segs = load_transcript_segments(REPO_ROOT)
    for seg_idx in EXPECTED_OPERATOR_INTRO_SEGMENTS:
        seg = segs[seg_idx]
        assert seg.get("role") == "Operator", (
            f"Segment {seg_idx}: expected role='Operator', got {seg.get('role')!r}"
        )
        assert "go ahead" in seg.get("text", "").lower(), (
            f"Segment {seg_idx}: 'go ahead' not found in text: {seg.get('text', '')[:100]!r}"
        )


def test_score_attempt_no_candidates_not_exercised():
    """Zero candidates must NOT report 100% replay or all_pass=true."""
    from engine.company_intelligence.e3_shadow_compiler import (
        ModelAttempt, load_transcript_segments, score_attempt,
    )
    attempt = ModelAttempt(provider="test", model="test", status="provider_unavailable")
    gold = json.loads(GOLD_PATH.read_bytes())
    segs = load_transcript_segments(REPO_ROOT)
    score = score_attempt(attempt, gold, segs)
    assert score["hard_gates"]["status"] == "NOT_EXERCISED"
    assert score["hard_gates"]["all_pass"] is False
    assert score["accepted_count"] == 0
    assert score["source_span_replay_success_pct"] is None
    assert score["source_span_replay_success_pct"] != 100.0


def test_score_attempt_cross_event_detected():
    """Foreign event_id is rejected and never trusted as a TP."""
    from engine.company_intelligence.e3_shadow_compiler import (
        ModelAttempt, gold_exchange_to_candidate, load_transcript_segments,
        score_attempt,
    )
    gold = json.loads(GOLD_PATH.read_bytes())
    segs = load_transcript_segments(REPO_ROOT)
    cand = gold_exchange_to_candidate(gold["exchanges"][0])
    cand["event_id"] = "evt_cik0000000000_2026q3_results"
    attempt = ModelAttempt(provider="test", model="test", status="ok", candidates=[cand])
    score = score_attempt(attempt, gold, segs)
    assert score["cross_event_rejected"] == 1
    assert score["accepted_cross_event"] == 0
    assert score["hard_gates"]["accepted_cross_event"] == 0
    assert score["hard_gates"]["cross_event"] == 0
    assert score["accepted_count"] == 0
    assert score["hard_gates"]["status"] == "NOT_EXERCISED"
    assert score["exchange_boundary_quality"]["tp"] == 0


def test_parse_candidates_valid_json():
    from engine.company_intelligence.e3_shadow_compiler import _parse_candidates
    raw = json.dumps([{"ordinal": 0, "questioner_name": "Test"}])
    result = _parse_candidates(raw)
    assert len(result) == 1
    assert result[0]["ordinal"] == 0


def test_parse_candidates_markdown_wrapped():
    from engine.company_intelligence.e3_shadow_compiler import _parse_candidates
    raw = "```json\n[{\"ordinal\": 0}]\n```"
    result = _parse_candidates(raw)
    assert len(result) == 1


def test_parse_candidates_invalid_returns_empty():
    from engine.company_intelligence.e3_shadow_compiler import _parse_candidates
    result = _parse_candidates("not valid json at all")
    assert result == []


# ── Gold operator boundary matches transcript structure ────────────────────────


def test_gold_exchange_0_questioner():
    gold = json.loads(GOLD_PATH.read_bytes())
    ex = gold["exchanges"][0]
    assert ex["questioner"]["name"] == "Amit Daryanani"
    assert ex["questioner"]["affiliation"] == "Evercore"


def test_gold_exchange_5_has_john_ternus():
    """Exchange 5 (Wamsi Mohan) must include John Ternus as distinct respondent."""
    gold = json.loads(GOLD_PATH.read_bytes())
    ex = gold["exchanges"][5]
    respondent_names = [r["name"] for r in ex["respondents"]]
    assert "John Ternus" in respondent_names
    assert "Tim Cook" in respondent_names
    assert respondent_names[-1] == "John Ternus"
    assert respondent_names.count("John Ternus") == 1
    assert len(respondent_names) == 5


def test_gold_all_seven_questioners(gold):
    names = {ex["questioner"]["name"] for ex in gold["exchanges"]}
    expected = {
        "Amit Daryanani",
        "Michael Ng",
        "Ben Reitzes",
        "Erik Woodring",
        "Aaron Rakers",
        "Wamsi Mohan",
        "Samik Chatterjee",
    }
    assert names == expected


def test_gold_respondent_name_and_role_match_answer_segment_metadata(gold):
    """Pin respondent identity to held transcript metadata, not biography."""
    with gzip.open(FIXTURE_DIR / "aapl_fy2026_q3.json.gz") as f:
        segs = json.load(f)["segments"]
    for ex in gold["exchanges"]:
        for span in ex["answer_spans"]:
            seg = segs[span["segment_index"]]
            assert span["speaker"] == seg["speaker"]
            assert span["role"] == seg["role"]
        for resp in ex["respondents"]:
            assert any(
                span["speaker"] == resp["name"] and span["role"] == resp["role"]
                for span in ex["answer_spans"]
            ), f"exchange {ex['ordinal']}: {resp} not in answer segment metadata"
    ternus_span = segs[94]
    assert ternus_span["speaker"] == "John Ternus"
    assert ternus_span["role"] == "CEO"
    gold_ternus = next(
        r for r in gold["exchanges"][5]["respondents"] if r["name"] == "John Ternus"
    )
    assert gold_ternus["role"] == ternus_span["role"] == "CEO"


def test_adjudication_receipt_dual_session():
    path = REPO_ROOT / "research/earnings_intelligence/e3/gold/aapl_fy2026_q3_adjudication_receipt.json"
    receipt = json.loads(path.read_bytes())
    assert receipt["adjudication_method"] == "dual_session"
    assert receipt["gold_sha256"] == GOLD_SHA256
    assert receipt["gold_correction"] is True
    assert receipt["pass_b"]["pass_kind"] == "independent_pre_inference_dual_adjudication"
    assert receipt["pass_a"]["boundary_segments"] == EXPECTED_OPERATOR_INTRO_SEGMENTS
    assert receipt["pass_b"]["boundary_segments"] == EXPECTED_OPERATOR_INTRO_SEGMENTS
    assert receipt["reconciliation"]["boundaries_agree"] is True
    assert receipt["reconciliation"]["respondents_law"] == "answer_turn"
    assert receipt["reconciliation"]["john_ternus_role"]["pinned"] == "CEO"
    assert receipt["source"]["assumed_from_handoff"] is False
    assert receipt["reconciliation"]["superseded_gold_sha256"] == SUPERSEDED_GOLD_SHA_V1


def test_qwen_resolves_worker_override_before_yaml(monkeypatch):
    from engine.company_intelligence.e3_shadow_compiler import resolve_qwen_openai_compat_cfg
    monkeypatch.delenv("EARNINGS_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("EARNINGS_LLM_MODEL", raising=False)
    cfg = resolve_qwen_openai_compat_cfg(
        REPO_ROOT, {"base_url": "http://localhost:11434/v1", "model": "qwen3.5:9b"}
    )
    assert cfg["base_url"] == "http://127.0.0.1:11435/v1"
    assert cfg["model"] == "qwen3.5:9b"
    assert cfg["base_url_source"] == "earnings_worker_plist"
    monkeypatch.setenv("EARNINGS_LLM_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("EARNINGS_LLM_MODEL", "qwen3.5:9b")
    env_cfg = resolve_qwen_openai_compat_cfg(
        REPO_ROOT, {"base_url": "http://localhost:11434/v1", "model": "placeholder"}
    )
    assert env_cfg["base_url_source"] == "env"
    assert env_cfg["base_url"] == "http://127.0.0.1:9/v1"


def _gold_cand(gold, ordinal=0, **overrides):
    from engine.company_intelligence.e3_shadow_compiler import gold_exchange_to_candidate
    cand = gold_exchange_to_candidate(gold["exchanges"][ordinal])
    cand.update(overrides)
    return cand


def test_validator_boundary_need_not_be_in_question_indexes(gold):
    """Closed schema lists boundary_segment_index separately from question indexes."""
    from engine.company_intelligence.e3_shadow_compiler import (
        load_transcript_segments, validate_candidate,
    )
    segs = load_transcript_segments(REPO_ROOT)
    cand = _gold_cand(gold, ordinal=0)
    cand["question_segment_indexes"] = [33, 38]
    cand["boundary_segment_index"] = 32
    result = validate_candidate(cand, segs)
    assert result["ok"] is True


def test_validator_out_of_range_segment_rejected(gold):
    from engine.company_intelligence.e3_shadow_compiler import (
        load_transcript_segments, validate_candidate,
    )
    segs = load_transcript_segments(REPO_ROOT)
    cand = _gold_cand(gold, question_segment_indexes=[32, 999])
    result = validate_candidate(cand, segs)
    assert result["ok"] is False
    assert result["reason"] == "out_of_range_segment"


def test_validator_unknown_topic_rejected(gold):
    from engine.company_intelligence.e3_shadow_compiler import (
        load_transcript_segments, validate_candidate,
    )
    segs = load_transcript_segments(REPO_ROOT)
    cand = _gold_cand(gold, topics=["deflection"])
    result = validate_candidate(cand, segs)
    assert result["ok"] is False
    assert result["reason"] == "unknown_topic"


def test_validator_missing_or_wrong_type_rejected(gold):
    from engine.company_intelligence.e3_shadow_compiler import (
        load_transcript_segments, validate_candidate,
    )
    segs = load_transcript_segments(REPO_ROOT)
    missing = _gold_cand(gold)
    del missing["affiliation"]
    assert validate_candidate(missing, segs)["reason"] == "invalid_schema"
    wrong = _gold_cand(gold)
    wrong["ordinal"] = "0"
    assert validate_candidate(wrong, segs)["reason"] == "invalid_schema"


def test_validator_foreign_event_field_rejected_never_trusted(gold):
    from engine.company_intelligence.e3_shadow_compiler import (
        load_transcript_segments, validate_candidate,
    )
    segs = load_transcript_segments(REPO_ROOT)
    cand = _gold_cand(gold, event_id="evt_foreign")
    result = validate_candidate(cand, segs)
    assert result["ok"] is False
    assert result["reason"] == "cross_event"


def test_correct_questioner_wrong_operator_boundary_is_not_tp(gold):
    from engine.company_intelligence.e3_shadow_compiler import (
        ModelAttempt, load_transcript_segments, score_attempt,
    )
    segs = load_transcript_segments(REPO_ROOT)
    cand = _gold_cand(gold, ordinal=0)
    cand["boundary_segment_index"] = 42
    cand["question_segment_indexes"] = [42, 43]
    cand["answer_segment_indexes"] = [44]
    cand["respondents"] = [{"name": "Tim Cook", "role": "CEO"}]
    attempt = ModelAttempt(provider="test", model="test", status="ok", candidates=[cand])
    score = score_attempt(attempt, gold, segs)
    matched = [row for row in score["per_exchange"] if row["candidate_ordinal"] == 0]
    assert matched[0]["gold_ordinal"] == 1
    assert score["exchange_boundary_quality"]["tp"] == 1
    assert score["exchange_boundary_quality"]["recall"] <= 1.0


def test_duplicate_prediction_cannot_inflate_tp(gold):
    from engine.company_intelligence.e3_shadow_compiler import (
        ModelAttempt, load_transcript_segments, score_attempt,
    )
    segs = load_transcript_segments(REPO_ROOT)
    cand = _gold_cand(gold, ordinal=0)
    dup = dict(cand)
    dup["ordinal"] = 99
    attempt = ModelAttempt(
        provider="test", model="test", status="ok", candidates=[cand, dup],
    )
    score = score_attempt(attempt, gold, segs)
    assert score["exchange_boundary_quality"]["tp"] == 1
    assert score["exchange_boundary_quality"]["recall"] <= 1.0
    assert score["exchange_boundary_quality"]["recall"] == pytest.approx(1.0 / 7)


def test_wrong_respondent_role_is_identity_error(gold):
    from engine.company_intelligence.e3_shadow_compiler import (
        ModelAttempt, load_transcript_segments, score_attempt,
    )
    segs = load_transcript_segments(REPO_ROOT)
    cand = _gold_cand(gold, ordinal=5)
    cand["respondents"] = [
        {"name": "Tim Cook", "role": "CEO"},
        {"name": "John Ternus", "role": "SVP Hardware Engineering"},
    ]
    attempt = ModelAttempt(provider="test", model="test", status="ok", candidates=[cand])
    score = score_attempt(attempt, gold, segs)
    row = next(r for r in score["per_exchange"] if r["gold_ordinal"] == 5)
    assert "respondent_roles" in row["identity_errors"]
    ident = score["identity_role_availability"]
    assert ident["respondent_role_order_match_rate"] == 0.0


def test_altered_source_bytes_fail_replay(gold):
    from engine.company_intelligence.e3_shadow_compiler import (
        gold_exchange_to_candidate, validate_candidate,
    )
    cand = gold_exchange_to_candidate(gold["exchanges"][0])
    mutated = [{"text": "", "speaker": "x", "role": "y"} for _ in range(108)]
    result = validate_candidate(cand, mutated)
    assert result["ok"] is False
    assert result["reason"] == "span_replay_failure"


def test_valid_synthetic_candidate_is_shadow_admitted_with_real_replay(gold):
    from engine.company_intelligence.e3_shadow_compiler import (
        ModelAttempt, load_transcript_segments, score_attempt, validate_candidate,
    )
    segs = load_transcript_segments(REPO_ROOT)
    cand = _gold_cand(gold, ordinal=0)
    admitted = validate_candidate(cand, segs)
    assert admitted["ok"] is True
    attempt = ModelAttempt(provider="test", model="test", status="ok", candidates=[cand])
    score = score_attempt(attempt, gold, segs)
    assert score["accepted_count"] == 1
    assert score["accepted_span_replay_count"] == 1
    assert score["source_span_replay_success_pct"] == 100.0
    assert score["n_model_candidates"] == 1
    assert score["exchange_boundary_quality"]["tp"] == 1


def test_hardcoded_false_green_cannot_return():
    """If the old 100.0 / 0.0 / accepted_count=0 / all_pass=true path is restored, fail."""
    from engine.company_intelligence.e3_shadow_compiler import (
        ModelAttempt, load_transcript_segments, score_attempt,
    )
    segs = load_transcript_segments(REPO_ROOT)
    gold = json.loads(GOLD_PATH.read_bytes())
    empty = score_attempt(
        ModelAttempt(provider="t", model="t", status="provider_unavailable"),
        gold,
        segs,
    )
    assert empty["hard_gates"]["status"] == "NOT_EXERCISED"
    assert empty["hard_gates"]["all_pass"] is not True
    assert empty["source_span_replay_success_pct"] != 100.0
    assert empty["accepted_count"] == 0


def test_rejected_unsupported_is_not_accepted_unsupported(gold):
    """A validator rejection is not an accepted-object hard-gate violation."""
    from engine.company_intelligence.e3_shadow_compiler import (
        ModelAttempt, load_transcript_segments, score_attempt, validate_candidates,
    )
    segs = load_transcript_segments(REPO_ROOT)
    cand = _gold_cand(gold, ordinal=0)
    mutated = [{"text": "", "speaker": "x", "role": "y"} for _ in range(108)]
    validated = validate_candidates([cand], mutated)
    assert validated["unsupported_rejected"] == 1
    assert validated["accepted_unsupported"] == 0
    assert validated["accepted_count"] == 0
    attempt = ModelAttempt(provider="t", model="t", status="ok", candidates=[cand])
    score = score_attempt(attempt, gold, mutated)
    assert score["unsupported_rejected"] == 1
    assert score["accepted_unsupported"] == 0
    assert score["hard_gates"]["accepted_unsupported"] == 0
    assert score["hard_gates"]["status"] == "NOT_EXERCISED"


def test_run_e3a_eval_hermetic_end_to_end(monkeypatch, tmp_path):
    """Full run_e3a_eval path through telemetry + receipt write.

    Must fail against 3cadd220 (_bounded_telemetry_proof use-before-assignment).
    """
    import engine.company_intelligence.e3_shadow_compiler as e3

    live = {
        "available": True,
        "reader": "engine.neuralweb.company_intelligence_reader.read_event_workspace",
        "generation_id": e3.PINNED_GENERATION_ID,
        "workspace_sha256": e3.PINNED_WORKSPACE_SHA,
        "workspace_url": None,
        "marker_url": None,
        "release_source_sha256": e3.FROZEN_EXHIBIT_SHA,
        "transcript_source_sha256": e3.FROZEN_TRANSCRIPT_SHA,
        "matches_frozen_fixtures": True,
        "assumed_from_handoff": False,
        "note": None,
    }
    monkeypatch.setattr(e3, "verify_live_workspace_shas", lambda: live)

    qwen = e3.ModelAttempt(
        provider="openai_compat",
        model="qwen3.5:9b",
        status="ok",
        endpoint_class="loopback",
        base_url_source="earnings_worker_plist",
        est_cost_usd=0.0,
        preflight={"status": "ok", "endpoint_class": "loopback"},
    )
    gold = json.loads(GOLD_PATH.read_bytes())
    haiku = e3.ModelAttempt(
        provider="oauth",
        model="claude-haiku-4-5",
        status="ok",
        is_comparator=True,
        candidates=[e3.gold_exchange_to_candidate(gold["exchanges"][0])],
        input_tokens=12,
        output_tokens=8,
        est_cost_usd=0.01,
        comparator_note="benchmark-only",
        preflight={"comparator_freeze": {"status": "frozen"}},
    )
    monkeypatch.setattr(e3, "_attempt_qwen", lambda prompt, root: qwen)
    monkeypatch.setattr(e3, "_attempt_comparator", lambda prompt, root, run_id="": haiku)
    monkeypatch.setattr(
        e3,
        "freeze_comparator_choice",
        lambda root, run_id="": {
            "freeze": {"status": "frozen", "model": "claude-haiku-4-5", "providers": []},
            "providers": [],
            "cfg": {},
        },
    )
    monkeypatch.setattr(e3, "ledger_attempt", lambda *a, **k: None)

    receipt_path = tmp_path / "eval_receipt.json"
    monkeypatch.setattr(e3, "EVAL_RECEIPT_PATH", receipt_path)

    def _shards(run_id: str, repo_root: Path) -> dict[str, str]:
        health = tmp_path / f"provider_health_{run_id}.jsonl"
        health.write_text("", encoding="utf-8")
        return {
            "ai_costs_shard": f"e3a-test-{run_id}",
            "provider_health_path": str(health),
        }

    monkeypatch.setattr(e3, "_enable_eval_shards", _shards)

    receipt = e3.run_e3a_eval(REPO_ROOT)
    assert receipt_path.is_file(), "eval receipt must be written"
    bindings = receipt.get("bindings") or receipt
    for key in (
        "git_head",
        "compiler_sha256",
        "system_prompt_sha256",
        "gold_sha256",
        "taxonomy_hash",
        "run_id",
    ):
        assert bindings.get(key), f"receipt missing binding {key}"
    assert receipt["bindings"]["gold_sha256"] == hashlib.sha256(
        GOLD_PATH.read_bytes()
    ).hexdigest()
    proof = receipt["telemetry_proof"]
    assert proof["lane"] == "earnings_event_compiler"
    assert receipt["model_attempts"]["qwen"]["n_candidates"] == 0
    assert receipt["model_attempts"]["comparator"]["n_candidates"] == 1
    assert receipt["summary"]["e3b_auto_unlocked"] is False


def test_local_qwen_cost_is_zero_not_unpriced(tmp_path, monkeypatch):
    """Loopback Ollama transport is local/free $0.00, not an unpriced metered call."""
    monkeypatch.delenv("AI_COSTS_SHARD", raising=False)
    from engine.company_intelligence.e3_shadow_compiler import (
        ModelAttempt, ledger_attempt,
    )
    attempt = ModelAttempt(
        provider="openai_compat",
        model="qwen3.5:9b",
        endpoint_class="loopback",
        status="ok",
        est_cost_usd=0.0,
        input_tokens=10,
        output_tokens=2,
    )
    ledger_attempt(attempt, tmp_path, "abc123")
    ledger = tmp_path / "data/ai_costs/usage.jsonl"
    row = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    assert row["est_cost_usd"] == 0.0
    assert row["cost_basis"] == "local"
    assert row["provider"] == "openai_compat"
    assert row["cycle_id"] == "abc123"
    assert row["lane"] == "earnings_event_compiler"
