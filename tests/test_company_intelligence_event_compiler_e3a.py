"""E3-A shadow extraction tests — AAPL FY2026 Q3.

Pins fixture SHAs. Validates gold file integrity.
Validates shadow compiler behavior (segmenter, scoring, ledger format).

Frozen source SHAs (load-bearing — any divergence must STOP the eval):
  Exhibit 99.1: 070abd6a9cdb7070e546d24ffcbc41c65450d939c6f88f189cb18ec711cf5fdb
  Transcript:   a8ff5d03e875fef5604791edbf625186c447af049e6e02f55bb89c68c7cc9f9f

Gold:
  Path:   research/earnings_intelligence/e3/gold/aapl_fy2026_q3_qa_gold.json
  SHA256: 6b1100b148396db9a29974da5bc6e0cc55e5534185e50e061fe3635d429ed761

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
GOLD_SHA256 = "6b1100b148396db9a29974da5bc6e0cc55e5534185e50e061fe3635d429ed761"

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
    assert gold["schema"] == "aapl_fy2026_q3_qa_gold.v1"


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


def test_score_attempt_no_candidates():
    """score_attempt with 0 candidates must trivially pass all hard gates."""
    from engine.company_intelligence.e3_shadow_compiler import ModelAttempt, score_attempt
    attempt = ModelAttempt(provider="test", model="test", status="provider_unavailable")
    gold = json.loads(GOLD_PATH.read_bytes())
    score = score_attempt(attempt, gold)
    assert score["hard_gates"]["all_pass"] is True
    assert score["hard_gates"]["accepted_unsupported"] == 0
    assert score["hard_gates"]["cross_event"] == 0
    assert score["accepted_count"] == 0
    assert score["source_span_replay_success_pct"] == 100.0


def test_score_attempt_cross_event_detected():
    """score_attempt must detect cross-event contamination in candidates."""
    from engine.company_intelligence.e3_shadow_compiler import ModelAttempt, score_attempt
    attempt = ModelAttempt(
        provider="test", model="test", status="ok",
        candidates=[{
            "ordinal": 0,
            "event_id": "evt_cik0000000000_2026q3_results",  # wrong event
            "questioner_name": "Amit Daryanani",
            "questioner_affiliation": "Evercore",
            "topics": ["demand"],
        }],
    )
    gold = json.loads(GOLD_PATH.read_bytes())
    score = score_attempt(attempt, gold)
    assert score["cross_event_contamination_accepted"] == 1
    assert score["hard_gates"]["cross_event"] == 1
    assert score["hard_gates"]["all_pass"] is False


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
    # Verify they are separate entries (not collapsed)
    assert len(respondent_names) == 2


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
