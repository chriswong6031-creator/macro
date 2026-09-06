"""Records-only contract tests for packet B-F11-3 (MO-PAID-031/032/054).

Pure text assertions against the frozen contract doc + agentos decision
record. No network, no data/, no site/ — safe in a sparse worktree.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    ROOT
    / "research"
    / "market_intelligence_productization"
    / "MARKET_ONTOLOGY_F11_POST_VERTICAL_CONTRACT_2026-09-06.md"
)
DEC_PATH = ROOT / "agentos" / "decisions" / "DEC-F11-ASSISTANT-GROUNDS-ON-PRODUCT-ARTIFACTS.md"
SCHEMA_PATH = ROOT / "agentos" / "schema" / "decision.schema.yml"

ROW_IDS = ["MO-PAID-031", "MO-PAID-032", "MO-PAID-054"]


def _contract_text() -> str:
    return CONTRACT_PATH.read_text(encoding="utf-8")


def _sections(text: str) -> dict[str, str]:
    """Split the doc on '## ' headings, keyed by the row id in the heading."""
    parts = re.split(r"(?m)^## ", text)
    sections: dict[str, str] = {}
    for part in parts[1:]:
        heading_line = part.split("\n", 1)[0]
        for row in ROW_IDS:
            if heading_line.startswith(f"{row} — "):
                sections[row] = part
    return sections


def test_contract_doc_exists():
    assert CONTRACT_PATH.exists(), f"missing {CONTRACT_PATH}"
    assert CONTRACT_PATH.stat().st_size > 0


@pytest.mark.parametrize("row", ROW_IDS)
def test_one_heading_per_ledger_row(row):
    text = _contract_text()
    pattern = re.compile(rf"(?m)^## {re.escape(row)} — ")
    matches = pattern.findall(text)
    assert len(matches) == 1, f"expected exactly one heading for {row}, found {len(matches)}"


@pytest.mark.parametrize("row", ROW_IDS)
def test_each_row_section_has_acceptance_and_ceiling(row):
    sections = _sections(_contract_text())
    assert row in sections, f"no section found for {row}"
    body = sections[row]
    assert re.search(r"(?m)^\*\*Acceptance:\*\*", body), f"{row} missing an Acceptance: line"
    assert re.search(r"(?m)^\*\*Authority ceiling:\*\*", body), f"{row} missing an Authority ceiling: line"


@pytest.mark.parametrize(
    "row,ceiling",
    [
        ("MO-PAID-031", "non_authoritative_assistant"),
        ("MO-PAID-032", "workflow_only"),
        ("MO-PAID-054", "non_authoritative_assistant"),
    ],
)
def test_ceiling_tokens_are_the_ledger_ceilings(row, ceiling):
    sections = _sections(_contract_text())
    assert ceiling in sections[row], f"{row} section missing ceiling token {ceiling}"


def test_forbidden_corpora_are_named_by_dnr_key():
    sections = _sections(_contract_text())
    body = sections["MO-PAID-031"]
    assert "DNR:KILL-PUBLIC-INTERNALS" in body
    assert "DNR:KILL-LLM-CONFIDENCE" in body


def test_single_scheduler_owner_named():
    sections = _sections(_contract_text())
    body = sections["MO-PAID-032"]
    assert ".github/workflows/daily.yml" in body
    assert ".github/workflows/weekly.yml" in body
    assert "no second scheduler" in body


def test_email_null_is_printed_not_claimed():
    sections = _sections(_contract_text())
    body = sections["MO-PAID-032"]
    assert "MO-PAID-085" in body
    assert "SEND PATH IS NOT WIRED" in body


def test_write_back_is_propose_only():
    sections = _sections(_contract_text())
    body = sections["MO-PAID-054"]
    assert "amended_from" in body
    assert re.search(r"(?m)^\*\*Never in place\.\*\*", body)
    assert re.search(r"(?m)^\*\*Never a score\.\*\*", body)


def test_decision_record_present_and_shaped():
    assert DEC_PATH.exists(), f"missing {DEC_PATH}"
    raw = DEC_PATH.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", raw, re.DOTALL)
    assert match, "decision record missing YAML frontmatter delimiters"
    frontmatter = yaml.safe_load(match.group(1))

    assert frontmatter["key"] == "F11-ASSISTANT-GROUNDS-ON-PRODUCT-ARTIFACTS"
    assert DEC_PATH.name == f"DEC-{frontmatter['key']}.md"

    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    required = schema.get("required") or schema.get("required_fields") or []
    if not required:
        # Fall back to the fields the spec names explicitly if the schema
        # shape differs from what we expect.
        required = [
            "key",
            "question",
            "answer",
            "rationale",
            "alternatives",
            "evidence",
            "affects",
            "confidence",
            "reversibility",
            "decided_by",
            "decided_at",
        ]
    for field in required:
        assert field in frontmatter, f"decision record missing required field {field!r}"

    assert isinstance(frontmatter["alternatives"], list)
    assert len(frontmatter["alternatives"]) >= 1
    for alt in frontmatter["alternatives"]:
        assert "option" in alt
        assert "why_not" in alt

    assert any(
        "MARKET_ONTOLOGY_F11_POST_VERTICAL_CONTRACT_2026-09-06.md" in item
        for item in frontmatter["affects"]
    ), "decision record 'affects' must name the contract doc path"


def test_no_front_facing_falsifier_vocabulary():
    text = _contract_text()
    assert "证伪" not in text, "front-facing falsifier vocabulary must not appear untranslated"

    for line in text.splitlines():
        if "falsifier" in line.lower():
            assert (
                "engine/falsifier_tripwires.py" in line or "never says" in line
            ), f"'falsifier' appears outside a code-path citation or a 'never says' disclosure: {line!r}"
