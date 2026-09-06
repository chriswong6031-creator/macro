"""B-F06-2 records guard: the F06 scope freeze must keep its ceiling in writing.

Records-only guard. It asserts the frozen doc still carries the two ledger row ids,
the verbatim no-ranker ceiling, the two binding DNR keys, the display-only panel map
and the merge gates. It reads one markdown file and nothing else: no network, no
fixtures, no repo state beyond the doc.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_REL = (
    "research/market_intelligence_productization/"
    "MARKET_ONTOLOGY_F06_SCREENER_AND_COCKPIT_SCOPE_2026-09-06.md"
)
DOC = REPO_ROOT / DOC_REL

PANELS = (
    "Overview",
    "Evidence",
    "Event chronology",
    "Company drivers",
    "Prophet and availability",
    "Risks / failed gates",
    "Next observables",
    "Owner/model receipts",
)
COVERAGE_STATES = (
    "AVAILABLE", "NOT_COVERED", "NOT_APPLICABLE", "UNAVAILABLE",
    "STALE", "RIGHTS_BLOCKED", "CONFLICTED", "CORRECTED", "PARTIAL",
)


@pytest.fixture(scope="module")
def doc() -> str:
    assert DOC.is_file(), f"F06 scope freeze missing at {DOC_REL}"
    return DOC.read_text(encoding="utf-8")


def test_doc_lives_at_the_owned_path_in_the_productization_index() -> None:
    # Entry point: the productization directory listing IS the index, so the file
    # must sit in that directory under the MARKET_ONTOLOGY_ naming convention.
    assert DOC.parent.name == "market_intelligence_productization"
    assert DOC.name.startswith("MARKET_ONTOLOGY_F06_")


def test_both_ledger_row_ids_are_recorded(doc: str) -> None:
    for row_id in ("MO-DELTA-002", "MO-PAID-021"):
        assert row_id in doc, f"{row_id} is not recorded in the scope freeze"


def test_the_no_ranker_ceiling_is_written_verbatim(doc: str) -> None:
    assert "no ranker / no score / no size" in doc
    assert "never a trade ranker" in doc
    assert "research_priority_only" in doc


def test_the_screener_question_is_in_plain_product_words(doc: str) -> None:
    assert "which names deserve a look first, and why" in doc


def test_both_dnr_keys_are_named_binding(doc: str) -> None:
    for key in ("KILL-CAUSAL-DAG-ALPHA", "KILL-LLM-CONFIDENCE"):
        assert key in doc, f"{key} is not named"
    section = doc.split("## 5.", 1)[-1].split("## 6.", 1)[0]
    assert "BINDING" in section.upper()
    for key in ("KILL-CAUSAL-DAG-ALPHA", "KILL-LLM-CONFIDENCE"):
        assert key in section, f"{key} is named outside the binding section"


def test_every_b1b_panel_is_present_and_marked_display_only(doc: str) -> None:
    section = doc.split("## 3.", 1)[-1].split("## 4.", 1)[0]
    rows = [line for line in section.splitlines() if line.strip().startswith("|")]
    for panel in PANELS:
        matches = [r for r in rows if f"| {panel} |" in r]
        assert matches, f"panel {panel!r} missing from the B1B map"
        for row in matches:
            assert "`display_only`" in row, f"panel {panel!r} is not marked display_only"


def test_the_cockpit_reads_the_frozen_object_and_claims_no_authority(doc: str) -> None:
    assert "security_state.v1" in doc
    for literal in ("can_rank: false", "can_gate: false", "can_size: false"):
        assert literal in doc, f"authority literal {literal!r} not echoed"


def test_both_merge_gates_are_recorded(doc: str) -> None:
    for pr in ("#6920", "#6905"):
        assert pr in doc, f"merge gate {pr} is not recorded"


def test_all_nine_coverage_states_are_disclosed_in_plain_words(doc: str) -> None:
    section = doc.split("## 4.", 1)[-1].split("## 5.", 1)[0]
    for state in COVERAGE_STATES:
        assert f"`{state}`" in section, f"coverage_state {state} has no printed wording"


def test_no_falsifier_vocabulary_on_reader_facing_wording(doc: str) -> None:
    section = doc.split("## 4.", 1)[-1].split("## 5.", 1)[0]
    for banned in ("falsified", "refuted", "thesis is false", "证伪"):
        assert banned not in section.lower(), f"{banned!r} in reader-facing wording"
