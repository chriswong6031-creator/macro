"""Tests for packet B-F09-7: Half-B rights, source and upstream-gate docket.

Pure-Python, no network, no data/ reads. Safe in a sparse worktree.
"""
import csv
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
F1 = REPO_ROOT / "research/market_intelligence_productization/MARKET_ONTOLOGY_HALF_B_RIGHTS_AND_UPSTREAM_GATE_DOCKET_2026-09-06.md"
F2 = REPO_ROOT / "agentos/decisions/DEC-HALF-B-RIGHTS-GATED-ROWS-ARE-DOCKETED-NOT-BUILT-2026-09-06.md"
F3 = REPO_ROOT / "research/market_intelligence_productization/MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv"

DOCKET_TOKEN = "DOCKETED_TERMINAL_HALF_B"
DOCKET_PATH_TEXT = "MARKET_ONTOLOGY_HALF_B_RIGHTS_AND_UPSTREAM_GATE_DOCKET_2026-09-06.md"

ROW_IDS = [
    "MO-DELTA-020", "MO-PAID-061", "MO-DELTA-022", "MO-PAID-063",
    "MO-DELTA-024", "MO-PAID-065", "MO-DELTA-025", "MO-PAID-066",
    "MO-DELTA-026", "MO-PAID-069", "MO-DELTA-027", "MO-PAID-040",
    "MO-DELTA-028", "MO-DELTA-030", "MO-PAID-041", "MO-PAID-019",
    "MO-PAID-029", "MO-PAID-030", "MO-PAID-035", "MO-PAID-037",
]

EXPECTED_HEADER = (
    "id", "family", "granular_disposition", "capability_state_c2",
    "state_delta", "current_owner", "real_producer", "real_consumer",
    "missing_contract_or_proof", "correction_behavior", "next_bounded_child",
    "acceptance_test", "source_rights", "authority_ceiling", "adjudication_notes",
)

EXPECTED_DISPOSITION_CENSUS = {
    "NEW_BOUNDED_BUILD": 46,
    "UPGRADE_EXISTING_OWNER": 40,
    "PROJECTION_ONLY": 21,
    "CONTEXT_ONLY": 8,
    "BLOCKED_RIGHTS": 7,
    "EXACT_EQUIVALENT": 5,
    "REJECTED_BY_DESIGN": 3,
}

# Pure single-gate Family A rows (not compound-gated A+B/A+C/A+EvalOS/derived) —
# these are the rows whose first slice must start "ON GATE OPEN ONLY:".
PURE_FAMILY_A_ROWS = [
    "MO-DELTA-020", "MO-PAID-061", "MO-DELTA-024", "MO-PAID-065",
    "MO-DELTA-025", "MO-PAID-066", "MO-DELTA-027", "MO-PAID-040",
    "MO-DELTA-028", "MO-PAID-035",
]


def _docket_text():
    return F1.read_text(encoding="utf-8")


def _row_section(text, row_id):
    pattern = re.compile(
        r"### " + re.escape(row_id) + r"\n(.*?)(?=\n### |\Z)", re.S
    )
    m = pattern.search(text)
    assert m, f"no ### {row_id} section found"
    return m.group(1)


def _csv_rows():
    raw = F3.read_bytes()
    rows = list(csv.reader(raw.decode("utf-8").splitlines(keepends=True)))
    header = rows[0]
    by_id = {r[0]: r for r in rows[1:] if r}
    return header, rows, by_id


def _section5_text(text):
    m = re.search(r"## 5\. .*?\n(.*?)\n## 6\.", text, re.S)
    assert m, "could not locate section 5"
    return m.group(1)


def test_all_twenty_rows_have_a_docket_section():
    text = _docket_text()
    found = re.findall(r"^### (\S+)\s*$", text, re.M)
    assert set(found) == set(ROW_IDS)
    assert len(found) == 20


def test_each_row_has_the_four_required_fields():
    text = _docket_text()
    required = [
        "**Blocked on (verbatim from the ledger):**",
        "**Who can open it:**",
        "**Authority ceiling if it opens (verbatim):**",
        "**First bounded slice on the day it opens:**",
    ]
    for row_id in ROW_IDS:
        section = _row_section(text, row_id)
        for field in required:
            assert field in section, f"{row_id} missing {field}"


def test_blocked_on_quotes_the_ledger_verbatim():
    text = _docket_text()
    _, _, by_id = _csv_rows()
    for row_id in ROW_IDS:
        section = _row_section(text, row_id)
        blocked_line = next(
            l for l in section.splitlines() if "Blocked on" in l
        )
        missing = by_id[row_id][8]
        assert missing in blocked_line, f"{row_id}: {missing!r} not in {blocked_line!r}"


def test_ceiling_quotes_the_ledger_verbatim():
    text = _docket_text()
    _, _, by_id = _csv_rows()
    for row_id in ROW_IDS:
        section = _row_section(text, row_id)
        ceiling_line = next(
            l for l in section.splitlines() if "Authority ceiling" in l
        )
        ceiling = by_id[row_id][13]
        assert ceiling in ceiling_line, f"{row_id}: {ceiling!r} not in {ceiling_line!r}"


def test_ledger_carries_disposition_and_docket_path():
    _, _, by_id = _csv_rows()
    for row_id in ROW_IDS:
        row = by_id[row_id]
        assert DOCKET_TOKEN in row[10], f"{row_id} missing docket token in col10"
        assert DOCKET_PATH_TEXT in row[14], f"{row_id} missing docket path in col14"


def test_ledger_shape_and_denominator_unchanged():
    header, rows, _ = _csv_rows()
    data_rows = [r for r in rows[1:] if r]
    assert tuple(header) == EXPECTED_HEADER
    assert len(data_rows) == 130
    from collections import Counter
    census = Counter(r[2] for r in data_rows)
    assert dict(census) == EXPECTED_DISPOSITION_CENSUS


def test_ledger_round_trip_is_byte_identical():
    import io
    raw = F3.read_bytes()
    rows = list(csv.reader(raw.decode("utf-8").splitlines(keepends=True)))
    buf = io.StringIO(newline="")
    csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n").writerows(rows)
    assert buf.getvalue().encode("utf-8") == raw


def test_customer_section_uses_plain_words():
    text = _docket_text()
    section5 = _section5_text(text)
    assert not re.search(r"MO-(DELTA|PAID)-\d+", section5)
    for token in [
        "BLOCKED_RIGHTS", "NEW_BOUNDED_BUILD", "PROJECTION_ONLY",
        "CONTEXT_ONLY", "UPGRADE_EXISTING_OWNER", "EXACT_EQUIVALENT",
        "REJECTED_BY_DESIGN",
    ]:
        assert token not in section5
    assert not re.search(r"\bK1\b|K2-C|K3-D|\bFIF\b|WS:|\bF0\d\b", section5)
    assert not re.search(r"falsifier|refuted|证伪", section5, re.I)


def test_customer_section_has_en_zh_parity():
    text = _docket_text()
    section5 = _section5_text(text)
    en_paras = re.findall(r"— EN:\*\*", section5)
    zh_paras = re.findall(r"— ZH:\*\*", section5)
    assert len(en_paras) == 3
    assert len(zh_paras) == 3
    cjk = re.findall(r"[一-鿿]", section5)
    assert len(cjk) > 20


def test_no_build_is_commissioned():
    text = _docket_text()
    for row_id in PURE_FAMILY_A_ROWS:
        section = _row_section(text, row_id)
        first_line = next(
            l for l in section.splitlines() if "First bounded slice" in l
        )
        assert "ON GATE OPEN ONLY:" in first_line, f"{row_id}: {first_line!r}"
    assert "TODO" not in text
    # "schedule"/"commission" (excluding "recommission") may appear only in a
    # negation ("never as a schedule", "nothing ... commissions") — never as
    # a bare directive against a gated row.
    negations = r"never|no line|nothing|does not|not authoris"
    for m in re.finditer(r"\bschedule\b", text, re.I):
        window = text[max(0, m.start() - 40): m.end() + 20]
        assert re.search(negations, window, re.I), window
    for m in re.finditer(r"(?<!re)\bcommission(ed|ing|s)?\b", text, re.I):
        window = text[max(0, m.start() - 40): m.end() + 20]
        assert re.search(negations, window, re.I), window


def test_arbitrage_rows_carry_no_signal_authority():
    text = _docket_text()
    for row_id in ("MO-DELTA-030", "MO-PAID-041"):
        section = _row_section(text, row_id)
        assert re.search(r"no signal authority", section, re.I)
        assert "prospective validation" in section


def test_row_accounting_repair_is_written():
    _, _, by_id = _csv_rows()
    for row_id in ("MO-DELTA-025", "MO-PAID-066"):
        notes = by_id[row_id][14]
        assert "ETF-held par" in notes
        assert "not issuer debt outstanding" in notes
        assert "not a canonical issuer join" in notes
    for row_id in ("MO-PAID-019", "MO-PAID-029"):
        notes = by_id[row_id][14]
        assert "not a canonical issuer join" in notes


def test_dec_record_shape():
    text = F2.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    end = text.index("\n---", 4)
    frontmatter = yaml.safe_load(text[4:end])
    required_keys = {
        "key", "question", "answer", "rationale", "alternatives",
        "evidence", "affects", "confidence", "reversibility",
        "decided_by", "decided_at",
    }
    assert required_keys.issubset(frontmatter.keys()), required_keys - frontmatter.keys()
    assert frontmatter["reversibility"] in {"easy", "costly", "one_way"}
    assert frontmatter["confidence"] in {"high", "medium", "low"}
    assert isinstance(frontmatter["alternatives"], list)
    assert len(frontmatter["alternatives"]) >= 1
    for alt in frontmatter["alternatives"]:
        assert "option" in alt and "why_not" in alt
    assert "created" not in frontmatter
    assert "updated" not in frontmatter


def test_no_k2c_or_k3d_recommission():
    text = _docket_text()
    for m in re.finditer(r"\brecommission\w*", text, re.I):
        window = text[max(0, m.start() - 15): m.start()]
        assert re.search(r"never|does not", window, re.I), window
    assert "never recommission" in text.lower() or "does not recommission" in text.lower()
