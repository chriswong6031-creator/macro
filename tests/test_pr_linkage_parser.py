from tests.test_pr_linkage_validator import VALID, codes, report


def test_authority_zone_rejects_later_copy_and_unclosed_fence():
    later = "## Context\n" + VALID
    assert "HEADER_MISSING" in codes(report(later))
    assert "HEADER_AUTHORITY_ZONE_INVALID" in codes(report(later))
    assert "HEADER_AUTHORITY_ZONE_INVALID" in codes(report("```\n" + VALID))


def test_parser_rejects_placeholder_bidi_and_line_breaks():
    assert "PLACEHOLDER_UNRESOLVED" in codes(report(VALID.replace("MAS-28", "<MAS-###>", 1)))
    assert "WAVE_INVALID" in codes(report(VALID.replace("MAS28-W1", "MAS 28")))


def test_relationship_hints_are_markdown_aware():
    harmless = VALID + "\n```\nFixes MAS-28\n```\n> Fixes MAS-28\n<!-- Fixes MAS-28 -->"
    assert "CLOSING_KEYWORD_FOR_NON_MERGE_DONE" not in codes(report(harmless))
    assert "CLOSING_KEYWORD_FOR_NON_MERGE_DONE" in codes(report(VALID + "\nFixes MAS-28"))
