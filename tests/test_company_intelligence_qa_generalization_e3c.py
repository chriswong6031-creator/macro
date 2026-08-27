"""E3-C second-event generalization — measured GOOGL Q2 FY2026 refusal.

This module pins a **negative result**, not a target. The unchanged E3-A2/E3-B
deterministic compiler was run against the frozen GOOGL package
(``e3c_googl_2026q2_source_completeness_receipt.json``) and refused. E3-A2
explicitly preserved that risk: "Source-format limitations (operator-intro
identity grammar; other vendor intros may refuse) are preserved for later
generalization."

Nothing here licenses tuning the compiler on GOOGL. These assertions exist so
the refusal is reproducible, and so any future generalization has to move a
measured boundary deliberately rather than silently. If a later wave legitimately
teaches the compiler this vendor's grammar, these tests are expected to fail and
must be re-adjudicated against a fresh receipt — they are not a wall to route
around.
"""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from engine.company_intelligence.event_workspace import WorkspaceError
from engine.company_intelligence.qa_exchange import (
    ACCEPTED_QA_TRANSCRIPT_SHA256,
    accepted_qa_exchanges_for_transcript,
    validate_qa_exchange,
)
from engine.company_intelligence.qa_reconstruction import reconstruct_qa

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/company_intelligence"

# Frozen by research/earnings_intelligence/e3/e3c_googl_2026q2_source_completeness_receipt.json
GOOGL_FIXTURE = FIXTURES / "googl_fy2026_q2.json.gz"
GOOGL_EVENT_ID = "evt_cik0001652044_2026q2_results"
GOOGL_DOCUMENT_ID = "tx:GOOGL/2026Q2"
GOOGL_TRANSCRIPT_SHA256 = "a44db883463181ba73a536cb3643b81ea59a3e10c0f191859f7717538452d2a9"
GOOGL_SEGMENT_COUNT = 90
# The receipt's source-only Operator question-intro census. Admission evidence only.
RECEIPT_OPERATOR_INTRO_INDEXES = [0, 33, 40, 48, 54, 58, 66, 70, 75, 80]

AAPL_FIXTURE = FIXTURES / "aapl_fy2026_q3.json.gz"
AAPL_EVENT_ID = "evt_cik0000320193_2026q3_results"
AAPL_DOCUMENT_ID = "tx:AAPL/2026Q3"


def _load(fixture: Path) -> tuple[list[dict], str]:
    raw = gzip.decompress(fixture.read_bytes())
    return json.loads(raw)["segments"], hashlib.sha256(raw).hexdigest()


def _googl() -> tuple[list[dict], str]:
    return _load(GOOGL_FIXTURE)


def _aapl_accepted() -> list[dict]:
    segments, sha = _load(AAPL_FIXTURE)
    assert sha == ACCEPTED_QA_TRANSCRIPT_SHA256
    return accepted_qa_exchanges_for_transcript(
        event_id=AAPL_EVENT_ID,
        document_id=AAPL_DOCUMENT_ID,
        document_sha256=sha,
        segments=segments,
    )


# --------------------------------------------------------------------------
# Held package integrity — the fixture is the exact frozen revision
# --------------------------------------------------------------------------


def test_googl_fixture_is_the_frozen_receipt_revision() -> None:
    segments, sha = _googl()
    assert sha == GOOGL_TRANSCRIPT_SHA256
    assert len(segments) == GOOGL_SEGMENT_COUNT
    operator_intros = [
        index
        for index, segment in enumerate(segments)
        if str(segment.get("role") or "").strip().casefold() == "operator"
        and "question" in str(segment.get("text") or "").casefold()
    ]
    # The receipt's ten source-level Operator question-intro boundaries all exist.
    assert set(RECEIPT_OPERATOR_INTRO_INDEXES).issubset(set(operator_intros))


# --------------------------------------------------------------------------
# The measured refusal
# --------------------------------------------------------------------------


def test_unchanged_compiler_refuses_googl_and_publishes_nothing() -> None:
    """E3-C pass rule §11.2(3) is NOT met: the generic compiler refuses GOOGL."""
    segments, sha = _googl()
    result = reconstruct_qa(
        event_id=GOOGL_EVENT_ID,
        document_id=GOOGL_DOCUMENT_ID,
        document_sha256=sha,
        segments=segments,
    )
    assert result["status"] == "failed"
    assert result["failure"]["code"] == "operator_intro_identity_unparsed"
    assert result["failure"]["boundary_segment_index"] == 0
    assert result["exchanges"] == []

    # The publication gate is fail-closed: no workspace write, no typed absence
    # invented, and the E2 event is left untouched.
    assert accepted_qa_exchanges_for_transcript(
        event_id=GOOGL_EVENT_ID,
        document_id=GOOGL_DOCUMENT_ID,
        document_sha256=sha,
        segments=segments,
    ) == []


# --------------------------------------------------------------------------
# Blocker 1 — the boundary cue is vendor-specific
# --------------------------------------------------------------------------


def test_googl_operator_intros_do_not_carry_the_go_ahead_boundary_cue() -> None:
    """Nine real analyst intros end "Your line is now open", never "go ahead"."""
    segments, sha = _googl()
    operators = [
        (index, " ".join(str(segment.get("text") or "").split()).casefold())
        for index, segment in enumerate(segments)
        if str(segment.get("role") or "").strip().casefold() == "operator"
    ]
    with_cue = [index for index, text in operators if "go ahead" in text]
    # Exactly one Operator segment carries the cue, and it is the pre-presentation
    # IR handoff at segment 0 — not a Q&A boundary at all.
    assert with_cue == [0]
    assert "head of investor relations. please go ahead." in dict(operators)[0]

    analyst_intros = [index for index in RECEIPT_OPERATOR_INTRO_INDEXES if index != 0]
    assert len(analyst_intros) == 9
    for index in analyst_intros:
        assert "your line is now open" in dict(operators)[index]
        assert "go ahead" not in dict(operators)[index]

    result = reconstruct_qa(
        event_id=GOOGL_EVENT_ID,
        document_id=GOOGL_DOCUMENT_ID,
        document_sha256=sha,
        segments=segments,
    )
    # The generic detector therefore sees one boundary, and it is a false one.
    assert result["qualifying_boundaries"] == [0]


# --------------------------------------------------------------------------
# Blocker 2 — this vendor publishes no management role at all
# --------------------------------------------------------------------------


def test_googl_management_speech_carries_no_source_role() -> None:
    segments, _ = _googl()
    roles = {str(segment.get("role") or "") for segment in segments}
    assert roles == {"Operator", "IR", ""}
    management = [
        segment
        for segment in segments
        if str(segment.get("speaker") or "") in {"Sundar Pichai", "Philipp Schindler", "Anat Ashkenazi"}
    ]
    assert management, "fixture must contain Alphabet management speech"
    # Every management turn is roleless, so the generic classifier cannot tell
    # management from an unexpected speaker.
    assert all(str(segment.get("role") or "") == "" for segment in management)


def test_missing_source_role_alone_flips_reconstruction_from_ok_to_refused() -> None:
    """Minimal pair: identical shape, role present vs absent."""

    def _shape(management_role: str) -> dict:
        segments = [
            {
                "role": "Operator",
                "speaker": "Operator",
                "text": "Our first question comes from Dana Lee with Example Capital. Please go ahead.",
            },
            {"role": "", "speaker": "Dana Lee", "text": "Thanks. How is demand trending?"},
            {"role": management_role, "speaker": "Robin Ochoa", "text": "Demand improved through the quarter."},
        ]
        return reconstruct_qa(
            event_id="evt_cik0000000000_2026q1_results",
            document_id="tx:EXMPL/2026Q1",
            document_sha256="0" * 64,
            segments=segments,
        )

    with_role = _shape("CEO")
    assert with_role["status"] == "ok"
    assert len(with_role["exchanges"]) == 1

    without_role = _shape("")
    assert without_role["status"] == "failed"
    assert without_role["failure"]["code"] == "unexpected_non_housekeeping_speaker"


# --------------------------------------------------------------------------
# Blocker 3 — qa_exchange.v1 cannot mint a source-supported roleless respondent
# --------------------------------------------------------------------------


def test_qa_exchange_refuses_a_respondent_without_a_source_role() -> None:
    exchanges = _aapl_accepted()
    poisoned = copy.deepcopy(exchanges[0])
    poisoned["respondents"][0]["role"] = ""
    with pytest.raises(WorkspaceError, match="role must be source-supported"):
        validate_qa_exchange(
            poisoned,
            event_id=AAPL_EVENT_ID,
            document_id=AAPL_DOCUMENT_ID,
            document_sha256=ACCEPTED_QA_TRANSCRIPT_SHA256,
        )


# --------------------------------------------------------------------------
# Containment held throughout the refusal
# --------------------------------------------------------------------------


def test_cross_event_aapl_material_is_rejected_under_googl_identity() -> None:
    accepted = _aapl_accepted()

    # Poison 1 — an accepted AAPL exchange offered to the GOOGL workspace.
    with pytest.raises(WorkspaceError, match="event_id does not match parent workspace"):
        validate_qa_exchange(
            copy.deepcopy(accepted[0]),
            event_id=GOOGL_EVENT_ID,
            document_id=GOOGL_DOCUMENT_ID,
            document_sha256=GOOGL_TRANSCRIPT_SHA256,
        )

    # Poison 2 — AAPL spans smuggled inside a correctly relabelled GOOGL envelope.
    relabelled = copy.deepcopy(accepted[0])
    relabelled["event_id"] = GOOGL_EVENT_ID
    relabelled["document_id"] = GOOGL_DOCUMENT_ID
    relabelled["document_sha256"] = GOOGL_TRANSCRIPT_SHA256
    relabelled["exchange_id"] = f"qx_{GOOGL_EVENT_ID}_{GOOGL_TRANSCRIPT_SHA256[:12]}_00"
    with pytest.raises(WorkspaceError, match="span document_id mismatch"):
        validate_qa_exchange(
            relabelled,
            event_id=GOOGL_EVENT_ID,
            document_id=GOOGL_DOCUMENT_ID,
            document_sha256=GOOGL_TRANSCRIPT_SHA256,
        )


@pytest.mark.parametrize(
    "event_id,document_id,fixture",
    [
        (AAPL_EVENT_ID, AAPL_DOCUMENT_ID, AAPL_FIXTURE),
        (GOOGL_EVENT_ID, GOOGL_DOCUMENT_ID, GOOGL_FIXTURE),
    ],
)
def test_a_changed_transcript_sha_fails_closed(event_id: str, document_id: str, fixture: Path) -> None:
    segments, sha = _load(fixture)
    mutated = ("b" if sha[0] != "b" else "c") + sha[1:]
    assert accepted_qa_exchanges_for_transcript(
        event_id=event_id,
        document_id=document_id,
        document_sha256=mutated,
        segments=segments,
    ) == []


# --------------------------------------------------------------------------
# AAPL is untouched by this wave
# --------------------------------------------------------------------------


def test_aapl_regression_is_exact() -> None:
    exchanges = _aapl_accepted()
    assert len(exchanges) == 7
    assert sum(len(item["respondents"]) for item in exchanges) == 26
    assert sum(len(item["question_spans"]) for item in exchanges) == 32
    assert sum(len(item["answer_spans"]) for item in exchanges) == 36
    assert sum(
        len(item["question_spans"]) + len(item["answer_spans"]) for item in exchanges
    ) == 68
