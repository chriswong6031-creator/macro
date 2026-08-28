"""TFG-1 R2 — deterministic transcript-format hardening discriminators.

Frozen law under test:
  DEC:E3FMT-STRUCTURAL-SEPARATORS-PROXY-IDENTITY-AND-SOURCE-CONDITIONED-HOLDOUT
  DEC:E3FMT-DEVELOPMENT-GOLD-R2-FIRST-HANDOFF-OMISSIONS
  research/earnings_intelligence/e3/TFG0_QA_RESPONDENT_IDENTITY_EVIDENCE_AMENDMENT_2026-08-27.md

These are synthetic transcript-shaped discriminators. The exact 16-call development
matrix and the sealed eight-slot holdout are scored by a separate held-source proof
run, never by this module: CI must not reach the network and must not be able to
observe holdout bodies.

Every fixture below is modelled on a real shape in the frozen development corpus and
is named for it, so a failure points at the source pattern it encodes.
"""
from __future__ import annotations

import copy
import gzip
import re
import hashlib
import json
from pathlib import Path

import pytest

from engine.company_intelligence.qa_reconstruction import reconstruct_qa

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "engine/company_intelligence/qa_reconstruction.py"
AAPL_FIXTURE = ROOT / "tests/fixtures/company_intelligence/aapl_fy2026_q3.json.gz"

SHA = "a" * 64
EVENT_ID = "evt_tfg1_r2_synthetic"
DOCUMENT_ID = "tx:TFG1R2/2026Q2"

# AAPL production oracle — must not move under generalization.
AAPL_SHA256 = "a8ff5d03e875fef5604791edbf625186c447af049e6e02f55bb89c68c7cc9f9f"
AAPL_BOUNDARIES = [32, 42, 52, 63, 76, 84, 97]
AAPL_EXCHANGES = 7
AAPL_ANSWER_TURNS = 26
AAPL_REPLAY_SPANS = 68


def _seg(role: str, speaker: str, text: str) -> dict[str, str]:
    return {"role": role, "speaker": speaker, "text": text}


def _run(segments, **overrides):
    payload = dict(
        event_id=EVENT_ID,
        document_id=DOCUMENT_ID,
        document_sha256=SHA,
        segments=segments,
    )
    payload.update(overrides)
    return reconstruct_qa(**payload)


def _prelude() -> list[dict[str, str]]:
    """Opening housekeeping + prepared remarks that must never yield a separator."""
    return [
        _seg(
            "Operator",
            "Operator",
            "Good morning and welcome to the second quarter earnings conference call. "
            "All lines have been placed on mute. I would now like to turn the call over "
            "to your host, Chief Executive Officer. Please go ahead.",
        ),
        _seg("CEO", "Amy Chen", "Thank you, operator, and good morning everyone."),
        _seg("CFO", "Dana Reed", "Revenue grew 12% year over year in the quarter."),
    ]


# --------------------------------------------------------------------------
# Structural separators — terminal cues carry zero admission authority
# --------------------------------------------------------------------------

def test_question_handoff_without_terminal_cue_is_a_structural_separator():
    """KREF #15 / ARRY #31 shape: a named question handoff with no go-ahead clause.

    The frozen method law gives terminal cue phrases zero admission authority, so a
    handoff that names the questioner and is followed by a source turn is a separator
    even though the words 'go ahead' never appear.
    """
    segs = _prelude() + [
        _seg("Operator", "Operator",
             "Thank you. Our first question comes from Tom Catherwood with BTIG."),
        _seg("Analyst", "Tom Catherwood", "Good morning. On the loan book -- what drove the yield?"),
        _seg("CEO", "Amy Chen", "The yield moved with the floating-rate mix."),
    ]
    out = _run(segs)
    assert out["qualifying_boundaries"] == [3], out


def test_opening_housekeeping_with_go_ahead_is_not_a_separator():
    """The opening turn-it-over-to-management line contains 'please go ahead'.

    It names no questioner and hands to prepared remarks, so admitting it would mint a
    false first exchange. This is the exact false positive the cue rule cannot reject.
    """
    segs = _prelude() + [
        _seg("Operator", "Operator",
             "Our first question comes from Tom Catherwood with BTIG."),
        _seg("Analyst", "Tom Catherwood", "Good morning. What drove the yield?"),
        _seg("CEO", "Amy Chen", "The floating-rate mix."),
    ]
    out = _run(segs)
    assert 0 not in out["qualifying_boundaries"], "opening go-ahead was admitted as a separator"


def test_queue_instruction_naming_nobody_is_not_a_separator():
    """Star-one queue housekeeping names no questioner and must never be a boundary."""
    segs = _prelude() + [
        _seg("Operator", "Operator",
             "If you would like to ask a question, please press star one on your "
             "telephone keypad. You may press star two to withdraw. Please go ahead."),
        _seg("CEO", "Amy Chen", "While we wait, let me add one more point on capital."),
    ]
    out = _run(segs)
    assert out["qualifying_boundaries"] == [], out


def test_closing_handoff_back_to_management_is_not_a_separator():
    """'I would like to turn the call back over to' is a return, not a question handoff."""
    segs = _prelude() + [
        _seg("Operator", "Operator",
             "Our next question comes from Joe Osha with Guggenheim."),
        _seg("Analyst", "Joe Osha", "Thanks. How should we think about backlog?"),
        _seg("CEO", "Amy Chen", "Backlog converts over three quarters."),
        _seg("Operator", "Operator",
             "That concludes our question and answer session. I would like to turn the "
             "call back over to Amy Chen for closing remarks. Please go ahead."),
        _seg("CEO", "Amy Chen", "Thank you all for joining us today."),
    ]
    out = _run(segs)
    assert out["qualifying_boundaries"] == [3], out


def test_handoff_with_no_following_source_turn_is_not_a_separator():
    """A separator requires an immediately following non-housekeeping source turn."""
    segs = _prelude() + [
        _seg("Operator", "Operator",
             "Our next question comes from Joe Osha with Guggenheim."),
        _seg("Operator", "Operator", "Mr. Osha, your line has disconnected."),
    ]
    out = _run(segs)
    assert out["qualifying_boundaries"] == [], out


# --------------------------------------------------------------------------
# Questioner identity — direct / explicit full-name proxy / unresolved
# --------------------------------------------------------------------------

def test_direct_name_equality_resolves_the_questioner():
    segs = _prelude() + [
        _seg("Operator", "Operator",
             "Our next question comes from the line of Joe Osha with Guggenheim."),
        _seg("Analyst", "Joe Osha", "Thanks for taking the question. On gross margin?"),
        _seg("CFO", "Dana Reed", "Gross margin benefited from mix."),
    ]
    out = _run(segs)
    assert out["status"] == "ok", out
    assert out["exchanges"][0]["questioner"]["name"] == "Joe Osha"


def test_explicit_full_name_proxy_is_source_supported():
    """GEF #30 shape: a different FULL-NAME speaker who states the on-for relation."""
    segs = _prelude() + [
        _seg("Operator", "Operator",
             "Our next question comes from the line of George Staphos with Bank of America."),
        _seg("Analyst", "Michael Roxland",
             "Good morning. This is Michael Roxland on for George Staphos. On volumes?"),
        _seg("CEO", "Amy Chen", "Volumes were up low single digits."),
    ]
    out = _run(segs)
    assert out["status"] == "ok", out
    q = out["exchanges"][0]["questioner"]
    assert q["name"] == "Michael Roxland"
    assert q["affiliation_state"] == "unresolved", "proxy inherited the principal's affiliation"


def test_placeholder_speaker_with_first_name_only_stays_unresolved():
    """MBLY #21 — the exact ratified omission.

    Operator names Joshua Buchalter; the next structured speaker is the placeholder
    'Speaker 4' and self-identifies only as 'Lanny on for Josh'. Frozen proxy law needs
    a FULL-NAME next speaker, so this is a separator with an unresolved questioner.
    """
    segs = _prelude() + [
        _seg("Operator", "Operator",
             "Thank you. Our next question comes from the line of Joshua Buchalter "
             "with TD Cowen."),
        _seg("", "Speaker 4", "Hi. Good morning. This is Lanny on for Josh. Can you hear me okay?"),
        _seg("CEO", "Amy Chen", "Yes, we can hear you."),
    ]
    out = _run(segs)
    assert 3 in out["qualifying_boundaries"], "unresolved questioner erased the structural separator"
    assert out["status"] == "failed"
    assert out["failure"]["code"] == "unresolved_questioner_identity", out["failure"]


def test_name_near_miss_is_not_repaired():
    """No edit distance, nickname map or initial matching may rescue a mismatch."""
    segs = _prelude() + [
        _seg("Operator", "Operator",
             "Our next question comes from the line of Jonathan Smith with Jefferies."),
        _seg("Analyst", "Jon Smyth", "Morning. On the margin outlook?"),
        _seg("CFO", "Dana Reed", "We expect it to hold."),
    ]
    out = _run(segs)
    assert out["status"] == "failed"
    assert out["failure"]["code"] == "unresolved_questioner_identity", out["failure"]


def test_on_for_relation_must_name_the_operator_principal():
    """An on-for clause naming somebody else does not bind the proxy."""
    segs = _prelude() + [
        _seg("Operator", "Operator",
             "Our next question comes from the line of George Staphos with Bank of America."),
        _seg("Analyst", "Michael Roxland",
             "Good morning. This is Michael Roxland on for Anthony Pettinari. On volumes?"),
        _seg("CEO", "Amy Chen", "Volumes were up."),
    ]
    out = _run(segs)
    assert out["status"] == "failed"
    assert out["failure"]["code"] == "unresolved_questioner_identity", out["failure"]


def test_unresolved_separator_prevents_adjacent_span_merge():
    """Spans may never merge across an unresolved but real structural boundary."""
    segs = _prelude() + [
        _seg("Operator", "Operator",
             "Our next question comes from the line of Joe Osha with Guggenheim."),
        _seg("Analyst", "Joe Osha", "Thanks. On backlog?"),
        _seg("CEO", "Amy Chen", "Backlog converts over three quarters."),
        _seg("Operator", "Operator",
             "Our next question comes from the line of Joshua Buchalter with TD Cowen."),
        _seg("", "Speaker 4", "This is Lanny on for Josh. On pricing?"),
        _seg("CEO", "Amy Chen", "Pricing held."),
        _seg("Operator", "Operator",
             "Our next question comes from the line of Tom Catherwood with BTIG."),
        _seg("Analyst", "Tom Catherwood", "On the loan book?"),
        _seg("CEO", "Amy Chen", "Yields moved with the mix."),
    ]
    out = _run(segs)
    assert out["qualifying_boundaries"] == [3, 6, 9], out
    assert out["status"] == "failed"
    assert out["failure"]["code"] == "unresolved_questioner_identity"
    assert out["failure"]["boundary_segment_index"] == 6, out["failure"]


# --------------------------------------------------------------------------
# Affiliation parsing — punctuation safety
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "affiliation",
    ["J.P. Morgan", "Bank of America Merrill Lynch", "Wells Fargo Securities, LLC"],
)
def test_affiliation_survives_internal_punctuation(affiliation):
    segs = _prelude() + [
        _seg("Operator", "Operator",
             f"Our next question comes from the line of Joe Osha with {affiliation}. "
             "Please go ahead."),
        _seg("Analyst", "Joe Osha", "Thanks. On backlog?"),
        _seg("CEO", "Amy Chen", "Backlog converts over three quarters."),
    ]
    out = _run(segs)
    assert out["status"] == "ok", out
    assert out["exchanges"][0]["questioner"]["affiliation"] == affiliation


# --------------------------------------------------------------------------
# AAPL production oracle — generalization must not move it
# --------------------------------------------------------------------------

def _aapl_segments() -> list[dict]:
    raw = gzip.open(AAPL_FIXTURE).read()
    assert hashlib.sha256(raw).hexdigest() == AAPL_SHA256
    return copy.deepcopy(json.loads(raw)["segments"])


def test_aapl_boundaries_and_turns_are_unchanged_by_generalization():
    out = reconstruct_qa(
        event_id="evt_cik0000320193_2026q3_results",
        document_id="tx:AAPL/2026Q3",
        document_sha256=AAPL_SHA256,
        segments=_aapl_segments(),
    )
    assert out["status"] == "ok", out
    assert out["qualifying_boundaries"] == AAPL_BOUNDARIES
    assert len(out["exchanges"]) == AAPL_EXCHANGES
    turns = sum(len(ex["respondents"]) for ex in out["exchanges"])
    assert turns == AAPL_ANSWER_TURNS
    spans = sum(len(ex["question_spans"]) + len(ex["answer_spans"]) for ex in out["exchanges"])
    assert spans == AAPL_REPLAY_SPANS


@pytest.mark.parametrize("bad_sha", ["", "b" * 63, "B" * 64, "z" * 64, "0x" + "b" * 62])
def test_aapl_malformed_revision_digest_fails_closed(bad_sha):
    """Revision binding is fail-closed on the digest itself.

    `reconstruct_qa` treats `document_sha256` as the revision label it binds every
    emitted span to; it does not re-hash the body. So the discriminator that matters
    here is that a digest which is not a 64-char lowercase hex string is refused
    outright rather than silently binding spans to an unusable revision identity.
    """
    out = reconstruct_qa(
        event_id="evt_cik0000320193_2026q3_results",
        document_id="tx:AAPL/2026Q3",
        document_sha256=bad_sha,
        segments=_aapl_segments(),
    )
    assert out["status"] == "failed"
    assert out["failure"]["code"] == "transcript_sha_invalid", out["failure"]


# --------------------------------------------------------------------------
# Hard safety — no external, fuzzy or model identity inference
# --------------------------------------------------------------------------

def test_reconstruction_module_has_no_network_fuzzy_or_model_inference():
    """Word-boundary matched on purpose: a bare substring scan reports `fullmatch`
    as the model token `llm`, which is a false alarm that trains readers to ignore
    this guard."""
    source = MODULE_PATH.read_text(encoding="utf-8")
    banned = (
        "requests", "urllib", "httpx", "socket",              # network
        "difflib", "rapidfuzz", "fuzzywuzzy", "Levenshtein",  # fuzzy identity
        "openai", "anthropic", "llm", "completion", "embedding",  # model inference
    )
    hits = [w for w in banned if re.search(rf"\b{re.escape(w)}\b", source)]
    assert not hits, f"{hits} reached the deterministic compiler"
