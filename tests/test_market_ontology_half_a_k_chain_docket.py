"""Pins packet B-A-F04-K1: the Half-A K-chain gate docket + its DEC record.

Records-only packet -- these tests assert that eight Half-A closure-ledger rows are
recorded as DOCKETED (never built/promoted/closed), each naming a gate from the closed
K2-C/K3-D/K5/D2C->W3C-fold vocabulary, an opener, a ledger-verbatim authority ceiling,
and one bounded first slice.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]

ROWS = (
    "MO-PAID-016", "MO-PAID-018", "MO-PAID-024", "MO-PAID-033",
    "MO-PAID-042", "MO-PAID-043", "MO-PAID-044", "MO-DELTA-006",
)

DOCKET = REPO / "research/market_intelligence_productization/MARKET_ONTOLOGY_HALF_A_K_CHAIN_GATE_DOCKET_2026-09-06.md"
LEDGER = REPO / "research/market_intelligence_productization/MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv"
DEC = REPO / "agentos/decisions/DEC-HALF-A-K-CHAIN-GATED-ROWS-ARE-DOCKETED-NOT-BUILT-2026-09-06.md"

GATE_TOKENS = {"K2-C", "K3-D", "K5", "D2C→W3C fold"}

_BLOCK_RE = re.compile(r"^## (MO-[A-Z]+-\d+)\b", re.MULTILINE)
_ANY_HEADING_RE = re.compile(r"^## ", re.MULTILINE)


def _blocks() -> dict[str, str]:
    text = DOCKET.read_text(encoding="utf-8")
    matches = list(_BLOCK_RE.finditer(text))
    heading_starts = [m.start() for m in _ANY_HEADING_RE.finditer(text)]
    out: dict[str, str] = {}
    for i, m in enumerate(matches):
        row_id = m.group(1)
        start = m.end()
        # bound the block at the next heading of ANY kind (not only the next MO- row),
        # so trailing non-row sections never bleed into the last row's block.
        later_headings = [h for h in heading_starts if h > m.start()]
        end = later_headings[0] if later_headings else len(text)
        out[row_id] = text[start:end]
    return out


def _field(block: str, label: str) -> str:
    # fields may wrap across multiple lines; capture until the next bold field,
    # a blank line, or the end of the block.
    pattern = re.compile(
        r"^- \*\*" + re.escape(label) + r":\*\*\s*(.*?)(?=\n- \*\*|\n\n|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(block)
    if not m:
        raise AssertionError(f"field {label!r} not found in block")
    return re.sub(r"\s+", " ", m.group(1)).strip()


def _norm(s: str) -> str:
    s = s.replace("`", "")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _ledger() -> dict[str, dict]:
    with LEDGER.open(newline="", encoding="utf-8") as f:
        return {row["id"]: row for row in csv.DictReader(f)}


def test_docket_and_dec_files_exist():
    assert DOCKET.exists(), f"missing docket: {DOCKET}"
    assert DEC.exists(), f"missing DEC: {DEC}"
    assert LEDGER.exists(), f"missing ledger: {LEDGER}"
    text = DOCKET.read_text(encoding="utf-8")
    assert len(text) > 2000, "docket looks too small to be substantive"


def test_all_eight_rows_have_a_block():
    blocks = _blocks()
    missing = [r for r in ROWS if r not in blocks]
    assert not missing, f"rows missing a docket block: {missing}"


@pytest.mark.parametrize("row", ROWS)
def test_every_row_is_docketed_not_closed(row):
    block = _blocks()[row]
    disposition = _field(block, "Disposition")
    assert disposition == "DOCKETED", f"{row}: expected Disposition=DOCKETED, got {disposition!r}"


_ALLOWED_NEGATIONS = re.compile(
    r"(?i)\b(?:not[_ ]built|none is built|nothing here has been\s+built|no row .{0,40} built)\b"
)
_BANNED = re.compile(r"(?i)\b(built|promoted|capability[-_ ]closed|shipped|delivered|proven[-_ ]live)\b")
_BANNED_CLOSED = re.compile(r"\bCLOSED\b")


@pytest.mark.parametrize("row", ROWS)
def test_no_row_is_described_as_built_promoted_or_closed(row):
    block = _blocks()[row]
    scrubbed = _ALLOWED_NEGATIONS.sub("", block)
    m = _BANNED.search(scrubbed)
    assert not m, f"{row}: block contains banned claim word {m.group(0)!r}"
    m2 = _BANNED_CLOSED.search(scrubbed)
    assert not m2, f"{row}: block contains banned word 'CLOSED'"


@pytest.mark.parametrize("row", ROWS)
def test_every_row_names_a_gate_from_the_closed_vocabulary(row):
    block = _blocks()[row]
    gate_str = _field(block, "Gate")
    tokens = [t.strip() for t in gate_str.replace("`", "").split("+")]
    for tok in tokens:
        assert tok in GATE_TOKENS, f"{row}: gate token {tok!r} not in closed vocabulary {GATE_TOKENS}"


@pytest.mark.parametrize("row", ROWS)
def test_every_row_names_an_opener(row):
    block = _blocks()[row]
    opener = _field(block, "Opener")
    assert len(opener) >= 40, f"{row}: opener too short: {opener!r}"
    assert re.search(r"#\d{3,5}|\bSol\b|\bChairman\b|separately commissioned", opener), (
        f"{row}: opener does not name a PR/Sol/Chairman/commission: {opener!r}"
    )


@pytest.mark.parametrize("row", ROWS)
def test_authority_ceiling_is_verbatim_from_the_ledger(row):
    block = _blocks()[row]
    docket_val = _norm(_field(block, "Authority ceiling (verbatim from ledger)"))
    ledger_val = _norm(_ledger()[row]["authority_ceiling"])
    assert docket_val == ledger_val, (
        f"{row}: authority ceiling mismatch\n  docket: {docket_val!r}\n  ledger: {ledger_val!r}"
    )


@pytest.mark.parametrize("row", ROWS)
def test_every_row_names_one_bounded_first_slice(row):
    block = _blocks()[row]
    slice_str = _field(block, "First bounded slice when it opens")
    assert len(slice_str) >= 60, f"{row}: first-slice text too short: {slice_str!r}"


def test_mo_delta_006_is_lawful_now_but_uncalibrated():
    block = _blocks()["MO-DELTA-006"]
    assert "LAWFUL-NOW-BUT-UNCALIBRATED" in block
    assert "REJECTED_BY_DESIGN" in block
    for word in ("direction", "confidence", "expected-impact", "gate", "size"):
        assert word in block, f"MO-DELTA-006 block missing required word {word!r}"


def test_docket_prints_its_nulls():
    text = DOCKET.read_text(encoding="utf-8")
    assert "## What we do not know — nulls, printed" in text
    assert "## Ledger reconciliation — deliberately deferred" in text
    assert "#6498" in text
    assert "#6924" in text
    assert "#6925" in text


def test_docket_avoids_the_banned_claim_word():
    assert "validated" not in DOCKET.read_text(encoding="utf-8").lower()


def test_dec_record_matches_its_filename_and_points_at_the_docket():
    text = DEC.read_text(encoding="utf-8")
    fm_text = text.split("---")[1]
    fm = yaml.safe_load(fm_text)
    key = fm["key"]
    assert key == "HALF-A-K-CHAIN-GATED-ROWS-ARE-DOCKETED-NOT-BUILT-2026-09-06"
    assert DEC.stem == f"DEC-{key}", f"filename stem {DEC.stem!r} != DEC-{key!r}"
    required = (
        "key", "question", "answer", "rationale", "alternatives", "evidence",
        "affects", "confidence", "reversibility", "decided_by", "decided_at",
    )
    for field in required:
        assert field in fm and fm[field], f"DEC missing required field: {field}"
    alts = fm["alternatives"]
    assert len(alts) >= 1
    for alt in alts:
        assert "option" in alt and alt["option"]
        assert "why_not" in alt and alt["why_not"]
    assert "DOCKETED" in fm["answer"]
    assert "MARKET_ONTOLOGY_HALF_A_K_CHAIN_GATE_DOCKET_2026-09-06.md" in text


def test_this_packet_does_not_claim_the_ledger_csv_was_updated():
    blocks = _blocks()
    for row, block in blocks.items():
        assert "disposition column" not in block.lower(), (
            f"{row}: block should not claim the ledger CSV disposition column was written"
        )
    text = DOCKET.read_text(encoding="utf-8")
    assert text.count("writes no disposition column") == 1
