"""Tests for packet B-F12-6 (records-only): F12 post-tenancy commercial and
account scope.

Covers:
- the records doc exists and is UTF-8 non-empty
- both closed rows (MO-PAID-079, MO-PAID-080) appear with a >=40-char
  acceptance line each
- the commercial_only / account_only ceilings sit near their rows
- the Chairman pricing-defer blockquote is present verbatim
- the four sibling-boundary bullets (B-F12-1/3/4/6) are present and the
  B-F12-3 boundary line does not restate role-check SQL
- nulls (seat billing, seat_limit enforcement, team-scoped entitlement view)
  are printed with a typed state from {NOT_BUILT, PROVEN_LIVE, DEFER}
- no fabricated "10 seats" claim and no banned "validated" word
- the minimum macro:<path>:<line> evidence refs resolve in this checkout
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "research" / "market_intelligence_productization" / \
    "MARKET_ONTOLOGY_F12_COMMERCIAL_ACCOUNT_SCOPE_2026-09-06.md"
ROWS = ("MO-PAID-079", "MO-PAID-080")

DEFER_BLOCKQUOTE = (
    "> **Deferred to the Chairman:** no pricing, plan, price, offer, or "
    "seat-charge change is made or implied by this packet; any team pricing "
    "or seat-pricing decision is the Chairman's alone."
)

MIN_MACRO_REFS = (
    "app/billing.py:643",
    "app/billing.py:679",
    "app/main.py:1004",
    "app/main.py:1044",
    "templates/account.js:397",
)

TYPED_STATES = ("NOT_BUILT", "PROVEN_LIVE", "DEFER")


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_doc_exists_and_is_utf8():
    assert DOC.is_file()
    text = DOC.read_text(encoding="utf-8")
    assert len(text.strip()) > 0


def test_both_rows_present_with_acceptance_line():
    text = _text()
    for row in ROWS:
        assert row in text, f"{row} missing from doc"
        pattern = rf"^- \*\*Acceptance \({row}\)\*\*: (.+)$"
        m = re.search(pattern, text, re.M)
        assert m is not None, f"no acceptance line found for {row}"
        assert len(m.group(1).strip()) >= 40, f"acceptance line for {row} too short"


def test_ceilings_named_next_to_their_rows():
    text = _text()
    for row, ceiling in (("MO-PAID-079", "commercial_only"), ("MO-PAID-080", "account_only")):
        idx_row = text.find(row, text.find("## 6."))
        idx_ceiling = text.find(ceiling, text.find("## 6."))
        assert idx_row != -1 and idx_ceiling != -1, f"{row}/{ceiling} not found in section 6"
        assert abs(idx_row - idx_ceiling) <= 400, f"{ceiling} not within 400 chars of {row}"


def test_pricing_deferred_to_chairman():
    text = _text()
    normalized = re.sub(r"\s+", " ", text)
    expected = re.sub(r"\s+", " ", DEFER_BLOCKQUOTE)
    assert expected in normalized


def test_sibling_boundaries_named():
    text = _text()
    b3_line = None
    for lane in ("B-F12-1", "B-F12-3", "B-F12-4", "B-F12-6"):
        found = False
        for line in text.splitlines():
            if lane in line and "owns" in line:
                found = True
                if lane == "B-F12-3":
                    b3_line = line
                break
        assert found, f"no boundary line found for {lane}"
    assert b3_line is not None
    assert "check (role in" not in b3_line


def test_nulls_are_typed_and_printed():
    text = _text()
    assert "NOT_BUILT" in text
    assert "PROVEN_LIVE" in text
    for term in ("seat", "team-scoped entitlement", "seat_limit"):
        found = False
        for line in text.splitlines():
            if term in line and any(state in line for state in TYPED_STATES):
                found = True
                break
        assert found, f"'{term}' not found on a line carrying a typed state"


def test_no_fabricated_seat_limit_and_no_validated_claim():
    text = _text()
    for line in text.splitlines():
        if "10 seats" in line:
            assert "NOT_BUILT" in line or "not enforced" in line, \
                f"'10 seats' appears without a disclaimer: {line!r}"
    assert "validated" not in text.lower()


def test_macro_evidence_refs_resolve():
    text = _text()
    refs = re.findall(r"macro:([\w./-]+\.(?:py|js|yml|j2|md|csv)):(\d+)", text)
    assert refs, "no macro: evidence refs found"
    seen = set()
    for path, line in refs:
        seen.add(f"{path}:{line}")
        target = ROOT / path
        assert target.is_file(), f"macro ref path does not exist: {path}"
        n_lines = len(target.read_text(encoding="utf-8", errors="replace").splitlines())
        assert n_lines >= int(line), f"macro ref line {line} out of range for {path} ({n_lines} lines)"
    for required in MIN_MACRO_REFS:
        assert required in seen, f"required macro ref missing: {required}"

    term_refs = re.findall(r"terminal:([\w./-]+)", text)
    assert term_refs, "no terminal: cross-repo refs found"
    assert "cross-repo, read-only reference" in text
