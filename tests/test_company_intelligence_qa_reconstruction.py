"""E3-A2 deterministic Q&A reconstruction — gold oracle + anti-hardcode mutations.

Gold is an evaluation oracle only. Runtime reconstruction must not import or
read research artifacts.
"""
from __future__ import annotations

import ast
import copy
import gzip
import hashlib
import json
import subprocess
from pathlib import Path

from engine.company_intelligence.qa_reconstruction import reconstruct_qa

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "engine/company_intelligence/qa_reconstruction.py"
FIXTURE_PATH = ROOT / "tests/fixtures/company_intelligence/aapl_fy2026_q3.json.gz"
GOLD_PATH = ROOT / "research/earnings_intelligence/e3/gold/aapl_fy2026_q3_qa_gold.json"
PROOF_PATH = ROOT / "research/earnings_intelligence/e3/e3a2_aapl_fy2026_q3_reconstruction_receipt.json"

TRANSCRIPT_SHA256 = "a8ff5d03e875fef5604791edbf625186c447af049e6e02f55bb89c68c7cc9f9f"
EVENT_ID = "evt_cik0000320193_2026q3_results"
DOCUMENT_ID = "tx:AAPL/2026Q3"

# Oracle-only. These constants live in tests, never in runtime reconstruction.
ORACLE_BOUNDARIES = [32, 42, 52, 63, 76, 84, 97]
ORACLE_EXCHANGE_COUNT = 7
ORACLE_TURN_COUNT = 26
ORACLE_EX0_TURNS = [
    ("Kevan Parekh", "CFO", [34, 35]),
    ("Tim Cook", "CEO", [36, 37]),
    ("Tim Cook", "CEO", [39, 40]),
]


def _load_segments() -> list[dict]:
    with gzip.open(FIXTURE_PATH) as handle:
        raw = handle.read()
    assert hashlib.sha256(raw).hexdigest() == TRANSCRIPT_SHA256
    return copy.deepcopy(json.loads(raw)["segments"])


def _load_gold() -> dict:
    return json.loads(GOLD_PATH.read_text())


def _reconstruct(segments, **overrides):
    payload = dict(
        event_id=EVENT_ID,
        document_id=DOCUMENT_ID,
        document_sha256=TRANSCRIPT_SHA256,
        segments=segments,
    )
    payload.update(overrides)
    return reconstruct_qa(**payload)


def _span_indexes(spans: list[dict]) -> list[int]:
    return [span["segment_index"] for span in spans]


def _turn_seg_indexes(exchange: dict) -> list[tuple[str, str, list[int]]]:
    answers = exchange["answer_spans"]
    out = []
    for turn in exchange["respondents"]:
        segs = [answers[i]["segment_index"] for i in turn["span_indexes"]]
        out.append((turn["name"], turn["role"], segs))
    return out


def _seg(role: str, speaker: str, text: str) -> dict:
    return {"role": role, "speaker": speaker, "text": text}


def _synthetic_two_exchange_call(
    *,
    analyst_name: str = "Jordan Blake",
    affiliation: str = "North Peak",
    manager_name: str = "Alex Rivera",
    manager_role: str = "CEO",
    second_analyst: str = "Riley Chen",
    second_affil: str = "Lakeview",
) -> list[dict]:
    """Issuer-agnostic Operator-delimited skeleton with a follow-up split."""
    return [
        _seg("IR", "IR Host", "Welcome to the call."),
        _seg("CEO", manager_name, "Prepared remarks."),
        _seg(
            "Operator",
            "Operator",
            f"We will take our first question from {analyst_name} from {affiliation}. Please go ahead.",
        ),
        _seg("", analyst_name, "What about demand?"),
        _seg(manager_role, manager_name, "Demand is steady."),
        _seg("", analyst_name, "And follow up on mix?"),
        _seg(manager_role, manager_name, "Mix is better."),
        _seg("IR", "IR Host", "Thank you. Next question please."),
        _seg(
            "Operator",
            "Operator",
            f"Our next question is from {second_analyst} of {second_affil}. Please go ahead.",
        ),
        _seg("", second_analyst, "Capital allocation?"),
        _seg("CFO", "Sam Ledger", "We remain disciplined."),
        _seg("Operator", "Operator", "This concludes the conference."),
    ]


def test_aapl_fixture_sha_still_frozen():
    with gzip.open(FIXTURE_PATH) as handle:
        assert hashlib.sha256(handle.read()).hexdigest() == TRANSCRIPT_SHA256


def test_aapl_gold_structural_parity_ignoring_topics():
    gold = _load_gold()
    result = _reconstruct(_load_segments())
    assert result["status"] == "ok"
    assert result["failure"] is None
    assert result["model_calls"] == 0
    assert result["topic_authority"] == "none"
    assert result["semantic_status"] == "unresolved"
    assert result["qualifying_boundaries"] == ORACLE_BOUNDARIES
    assert len(result["exchanges"]) == ORACLE_EXCHANGE_COUNT
    assert result["unclassified_segment_count"] == 0

    total_turns = 0
    for expected, got in zip(gold["exchanges"], result["exchanges"], strict=True):
        assert got["exchange_id"] == expected["exchange_id"]
        assert got["ordinal"] == expected["ordinal"]
        assert got["questioner"]["name"] == expected["questioner"]["name"]
        assert got["questioner"]["affiliation"] == expected["questioner"]["affiliation"]
        assert _span_indexes(got["question_spans"]) == _span_indexes(expected["question_spans"])
        assert _span_indexes(got["answer_spans"]) == _span_indexes(expected["answer_spans"])
        assert [span["text_sha256"] for span in got["question_spans"]] == [
            span["text_sha256"] for span in expected["question_spans"]
        ]
        assert [span["text_sha256"] for span in got["answer_spans"]] == [
            span["text_sha256"] for span in expected["answer_spans"]
        ]
        for gold_span, got_span in zip(expected["question_spans"], got["question_spans"], strict=True):
            assert got_span["start_byte"] == gold_span["start_byte"]
            assert got_span["end_byte"] == gold_span["end_byte"]
            assert got_span["speaker"] == gold_span["speaker"]
            assert got_span["role"] == gold_span["role"]
        for gold_span, got_span in zip(expected["answer_spans"], got["answer_spans"], strict=True):
            assert got_span["start_byte"] == gold_span["start_byte"]
            assert got_span["end_byte"] == gold_span["end_byte"]
            assert got_span["speaker"] == gold_span["speaker"]
            assert got_span["role"] == gold_span["role"]
        expected_turns = [(t["name"], t["role"], t["span_indexes"]) for t in expected["respondents"]]
        got_turns = [(t["name"], t["role"], t["span_indexes"]) for t in got["respondents"]]
        assert got_turns == expected_turns
        total_turns += len(got["respondents"])
        assert not (set(_span_indexes(got["question_spans"])) & set(_span_indexes(got["answer_spans"])))
        owned: list[int] = []
        for turn in got["respondents"]:
            owned.extend(turn["span_indexes"])
        assert owned == list(range(len(got["answer_spans"])))
        assert "topics" not in got
        assert got["semantic_status"] == "unresolved"
        assert got["topic_authority"] == "none"

    assert total_turns == ORACLE_TURN_COUNT
    assert _turn_seg_indexes(result["exchanges"][0]) == ORACLE_EX0_TURNS


def test_every_emitted_span_byte_replays_against_fixture():
    segments = _load_segments()
    result = _reconstruct(segments)
    for exchange in result["exchanges"]:
        for span in exchange["question_spans"] + exchange["answer_spans"]:
            encoded = segments[span["segment_index"]]["text"].encode("utf-8")
            sliced = encoded[span["start_byte"]:span["end_byte"]]
            assert sliced == encoded
            assert hashlib.sha256(sliced).hexdigest() == span["text_sha256"]


def test_renamed_analyst_and_affiliation_follow_source():
    result = _reconstruct(
        _synthetic_two_exchange_call(
            analyst_name="Morgan Hale", affiliation="Redwood Research"
        ),
        document_sha256="a" * 64,
        event_id="evt_synth",
        document_id="tx:SYNTH",
    )
    assert result["status"] == "ok"
    questioner = result["exchanges"][0]["questioner"]
    assert questioner["name"] == "Morgan Hale"
    assert questioner["affiliation"] == "Redwood Research"


def test_renamed_management_speaker_and_role_follow_source():
    result = _reconstruct(
        _synthetic_two_exchange_call(manager_name="Pat Okonkwo", manager_role="COO"),
        document_sha256="a" * 64,
        event_id="evt_synth",
        document_id="tx:SYNTH",
    )
    assert result["status"] == "ok"
    turns = result["exchanges"][0]["respondents"]
    assert [(t["name"], t["role"]) for t in turns] == [
        ("Pat Okonkwo", "COO"),
        ("Pat Okonkwo", "COO"),
    ]
    assert turns[0]["span_indexes"] == [0]
    assert turns[1]["span_indexes"] == [1]


def test_pre_qa_insert_shifts_indexes_mechanically():
    pad = [{"role": "IR", "speaker": "Host", "text": f"preamble {i}"} for i in range(5)]
    result = _reconstruct(pad + _load_segments())
    assert result["status"] == "ok"
    assert result["qualifying_boundaries"] == [index + 5 for index in ORACLE_BOUNDARIES]
    gold = _load_gold()
    for expected, got in zip(gold["exchanges"], result["exchanges"], strict=True):
        assert _span_indexes(got["question_spans"]) == [
            index + 5 for index in _span_indexes(expected["question_spans"])
        ]
        assert _span_indexes(got["answer_spans"]) == [
            index + 5 for index in _span_indexes(expected["answer_spans"])
        ]
        assert got["questioner"]["name"] == expected["questioner"]["name"]


def test_same_manager_before_and_after_analyst_followup_is_two_turns():
    result = _reconstruct(
        _synthetic_two_exchange_call(),
        document_sha256="b" * 64,
        event_id="evt_split",
        document_id="tx:SPLIT",
    )
    turns = result["exchanges"][0]["respondents"]
    assert len(turns) == 2
    assert turns[0]["name"] == turns[1]["name"] == "Alex Rivera"
    assert turns[0]["span_indexes"] != turns[1]["span_indexes"]


def test_operator_without_go_ahead_does_not_open_exchange():
    segments = _synthetic_two_exchange_call()
    segments[2]["text"] = "Stand by for our first question from Jordan Blake from North Peak."
    result = _reconstruct(
        segments,
        document_sha256="c" * 64,
        event_id="evt_noga",
        document_id="tx:NOGA",
    )
    assert result["status"] == "ok"
    assert result["qualifying_boundaries"] == [8]
    assert len(result["exchanges"]) == 1
    assert result["exchanges"][0]["questioner"]["name"] == "Riley Chen"


def test_unexpected_third_party_refuses_rather_than_dropping():
    segments = _synthetic_two_exchange_call()
    segments.insert(5, _seg("", "Unknown Guest", "Can I jump in?"))
    result = _reconstruct(
        segments,
        document_sha256="d" * 64,
        event_id="evt_third",
        document_id="tx:THIRD",
    )
    assert result["status"] == "failed"
    assert result["failure"]["code"] == "unexpected_non_housekeeping_speaker"
    assert result["exchanges"] == []


def test_operator_intro_name_mismatch_refuses():
    segments = _synthetic_two_exchange_call()
    segments[3]["speaker"] = "Different Person"
    result = _reconstruct(
        segments,
        document_sha256="e" * 64,
        event_id="evt_mis",
        document_id="tx:MIS",
    )
    assert result["status"] == "failed"
    assert result["failure"]["code"] == "operator_analyst_name_conflict"


def test_corrupt_source_hash_fails_replay():
    segments = _synthetic_two_exchange_call()
    segments[3]["text_sha256"] = "0" * 64
    result = _reconstruct(
        segments,
        document_sha256="f" * 64,
        event_id="evt_bad",
        document_id="tx:BAD",
    )
    assert result["status"] == "failed"
    assert result["failure"]["code"] == "span_replay_failed"


def test_new_transcript_sha_mints_new_exchange_ids():
    segments = _load_segments()
    original = _reconstruct(segments)
    alt_sha = "ab" * 32
    mutated = _reconstruct(segments, document_sha256=alt_sha)
    assert mutated["status"] == "ok"
    original_ids = [exchange["exchange_id"] for exchange in original["exchanges"]]
    new_ids = [exchange["exchange_id"] for exchange in mutated["exchanges"]]
    assert original_ids != new_ids
    assert all(alt_sha[:12] in exchange_id for exchange_id in new_ids)
    assert all(TRANSCRIPT_SHA256[:12] in exchange_id for exchange_id in original_ids)
    assert [exchange_id.split("_")[-1] for exchange_id in original_ids] == [
        exchange_id.split("_")[-1] for exchange_id in new_ids
    ]


def test_zero_boundaries_fail_closed():
    result = _reconstruct(
        [
            _seg("IR", "Host", "Hello."),
            _seg("CEO", "Pat", "Remarks only. No questions."),
            _seg("Operator", "Operator", "This concludes today's conference."),
        ],
        document_sha256="1" * 64,
        event_id="evt_none",
        document_id="tx:NONE",
    )
    assert result["status"] == "failed"
    assert result["failure"]["code"] == "zero_qa_boundaries"


def test_question_without_management_speech_refuses():
    result = _reconstruct(
        [
            _seg(
                "Operator",
                "Operator",
                "We will take our first question from Jordan Blake from North Peak. Please go ahead.",
            ),
            _seg("", "Jordan Blake", "Hello?"),
            _seg("IR", "Host", "We seem to have lost the line."),
        ],
        document_sha256="2" * 64,
        event_id="evt_qonly",
        document_id="tx:QONLY",
    )
    assert result["status"] == "failed"
    assert result["failure"]["code"] == "question_without_management_speech"


def test_unresolved_affiliation_preserves_name():
    segments = _synthetic_two_exchange_call()
    segments[2]["text"] = (
        "We will take our first question from Jordan Blake from North Peak. "
        "We will also take a question from Jordan Blake of Other Desk. Please go ahead."
    )
    result = _reconstruct(
        segments,
        document_sha256="3" * 64,
        event_id="evt_aff",
        document_id="tx:AFF",
    )
    assert result["status"] == "ok"
    questioner = result["exchanges"][0]["questioner"]
    assert questioner["name"] == "Jordan Blake"
    assert questioner["affiliation_state"] == "unresolved"
    assert questioner["affiliation"] == ""


def test_empty_segment_fails_closed():
    segments = _synthetic_two_exchange_call()
    segments[4]["text"] = ""
    result = _reconstruct(
        segments,
        document_sha256="4" * 64,
        event_id="evt_empty",
        document_id="tx:EMPTY",
    )
    assert result["status"] == "failed"
    assert result["failure"]["code"] == "malformed_empty_segment"


def test_invalid_sha_fails_closed():
    result = _reconstruct(_synthetic_two_exchange_call(), document_sha256="not-a-sha")
    assert result["status"] == "failed"
    assert result["failure"]["code"] == "transcript_sha_invalid"


_FORBIDDEN_SUBSTRINGS = (
    "AAPL",
    "aapl",
    "Tim Cook",
    "Kevan Parekh",
    "John Ternus",
    "Daryanani",
    "Evercore",
    "Goldman",
    "Melius",
    "Woodring",
    "Rakers",
    "Wamsi",
    "Chatterjee",
    "qa_gold",
    "earnings_intelligence/e3/gold",
)

_FORBIDDEN_INDEX_CONSTANTS = frozenset({32, 42, 52, 63, 76, 84, 97, 26})


def test_runtime_module_has_no_gold_import_or_path():
    source = MODULE_PATH.read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert "gold" not in module.casefold()
            assert "earnings_intelligence" not in module
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "gold" not in alias.name.casefold()
    assert "aapl_fy2026_q3_qa_gold" not in source
    assert "research/earnings_intelligence" not in source
    assert GOLD_PATH.name not in source


def test_runtime_module_has_no_named_issuer_literals_or_boundary_constants():
    source = MODULE_PATH.read_text()
    for needle in _FORBIDDEN_SUBSTRINGS:
        assert needle not in source, needle
    tree = ast.parse(source)
    numbers = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, int)
    ]
    leaked = _FORBIDDEN_INDEX_CONSTANTS.intersection(numbers)
    assert not leaked, leaked


def test_runtime_does_not_need_gold_to_reconstruct_synthetic():
    result = _reconstruct(
        _synthetic_two_exchange_call(),
        document_sha256="9" * 64,
        event_id="evt_noleak",
        document_id="tx:NOLEAK",
    )
    assert result["status"] == "ok"
    assert result["model_calls"] == 0


def _module_sha() -> str:
    return hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()


def _git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def test_proof_receipt_matches_live_reconstruction():
    gold = _load_gold()
    result = _reconstruct(_load_segments())
    committed = json.loads(PROOF_PATH.read_text())
    assert result["status"] == "ok"
    assert committed["transcript_sha256"] == TRANSCRIPT_SHA256
    assert committed["event_id"] == EVENT_ID
    assert committed["document_id"] == DOCUMENT_ID
    assert committed["qualifying_boundaries"] == ORACLE_BOUNDARIES
    assert committed["exchange_count"] == ORACLE_EXCHANGE_COUNT
    assert committed["answer_turn_count"] == ORACLE_TURN_COUNT
    assert committed["reconstruction_module_sha256"] == _module_sha()
    assert committed["structural_gold_parity"] is True
    assert committed["model_calls"] == 0
    assert committed["workspace_written"] is False
    assert committed["r2_written"] is False
    assert committed["terminal_modified"] is False
    assert committed["topic_authority"] == "none"
    assert committed["e3b_unlocked"] is False
    assert committed["unclassified_segment_count"] == 0
    assert committed["gold_sha256"] == hashlib.sha256(GOLD_PATH.read_bytes()).hexdigest()
    assert committed["gold_exchange_count"] == gold["qa_exchange_count"]
    assert committed["git_head_at_proof"]
    assert committed["exchange_0_turns"] == [
        {"name": name, "role": role, "segment_indexes": segs}
        for name, role, segs in ORACLE_EX0_TURNS
    ]
    assert committed["question_span_count"] == sum(
        len(exchange["question_spans"]) for exchange in result["exchanges"]
    )
    assert committed["answer_span_count"] == sum(
        len(exchange["answer_spans"]) for exchange in result["exchanges"]
    )
    _git_head()  # proof is bound to a real git head; value is committed separately
