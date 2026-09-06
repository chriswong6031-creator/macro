"""Tests for engine/debt_maturity.py (packet B-F09-3)."""
from __future__ import annotations

import ast
import json
import re
from datetime import date
from pathlib import Path

import pytest

from engine.debt_maturity import BUCKETS, extract_maturity_ladder

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "debt_maturity"
AAPL_CIK = "0000320193"


def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


def test_six_buckets_map_from_exact_tags():
    assert [b[0] for b in BUCKETS] == ["y1", "y2", "y3", "y4", "y5", "after5"]
    tags = [b[1] for b in BUCKETS]
    assert tags == [
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive",
    ]


def test_latest_annual_period_wins():
    facts = _load("aapl_trimmed.json")
    result = extract_maturity_ladder(facts, cik=AAPL_CIK, as_of=date(2025, 1, 1))
    assert result["period"]["form"] == "10-K"
    assert result["period"]["fp"] == "FY"
    assert result["period"]["end"] == "2024-09-28"


def test_buckets_never_mix_filings():
    facts = _load("aapl_trimmed.json")
    result = extract_maturity_ladder(facts, cik=AAPL_CIK, as_of=date(2025, 1, 1))
    y4 = next(b for b in result["buckets"] if b["key"] == "y4")
    assert y4["reported"] is False
    assert y4["drop_reason"] == "period_mismatch"
    # excluded from the total
    assert result["total_reported_usd"] == 11128000000 + 10912000000 + 0


def test_unit_not_usd_is_not_reported_not_zero():
    facts = _load("aapl_trimmed.json")
    result = extract_maturity_ladder(facts, cik=AAPL_CIK, as_of=date(2025, 1, 1))
    y3 = next(b for b in result["buckets"] if b["key"] == "y3")
    assert y3["usd"] is None
    assert y3["reported"] is False
    assert y3["drop_reason"] == "unit_not_usd"
    assert y3["display"] is None


def test_missing_bucket_is_null_not_zero():
    facts = _load("aapl_trimmed.json")
    result = extract_maturity_ladder(facts, cik=AAPL_CIK, as_of=date(2025, 1, 1))
    after5 = next(b for b in result["buckets"] if b["key"] == "after5")
    assert after5["usd"] is None
    assert after5["reported"] is False
    assert result["buckets_reported"] < result["buckets_total"]


def test_reported_zero_survives_as_zero():
    facts = _load("aapl_trimmed.json")
    result = extract_maturity_ladder(facts, cik=AAPL_CIK, as_of=date(2025, 1, 1))
    y5 = next(b for b in result["buckets"] if b["key"] == "y5")
    assert y5["reported"] is True
    assert y5["usd"] == 0
    assert y5["display"] == "$0"


def test_no_companyfacts_is_no_filings():
    result = extract_maturity_ladder(None, cik=AAPL_CIK)
    assert result["status"] == "no_filings"
    assert result["buckets"] == []


def test_facts_without_maturity_tags_is_no_maturity_facts():
    result = extract_maturity_ladder({"facts": {"us-gaap": {}}}, cik=AAPL_CIK)
    assert result["status"] == "no_maturity_facts"


def test_identity_is_cik_only():
    facts = _load("aapl_trimmed.json")
    # a fixture whose entityName does not match the passed CIK still resolves
    # purely off the CIK we pass — the module never reads entityName.
    result = extract_maturity_ladder(facts, cik="0000999999", as_of=date(2025, 1, 1))
    assert result["cik"] == "0000999999"
    assert result["status"] == "reported"
    with pytest.raises(ValueError):
        extract_maturity_ladder(facts, cik="AAPL")  # a ticker/name is not a CIK
    with pytest.raises(ValueError):
        extract_maturity_ladder(facts, cik="")


def test_module_is_pure():
    src = Path("engine/debt_maturity.py").read_text()
    tree = ast.parse(src)
    banned_calls = {"open", "urlopen"}
    banned_attrs = {"now", "read_csv", "read_parquet"}
    banned_modules = {"requests", "urllib", "pandas"}

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [n.name for n in node.names]
            mod = getattr(node, "module", None)
            for m in list(names) + ([mod] if mod else []):
                assert m not in banned_modules, f"forbidden import: {m}"
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in banned_calls:
                pytest.fail(f"forbidden call at module scope: {fn.id}")
            if isinstance(fn, ast.Attribute) and fn.attr in banned_attrs:
                pytest.fail(f"forbidden call: {fn.attr}")
    assert "Path(" not in src.replace("# noqa", "")


def test_glance_tier_has_no_machine_text():
    tmpl_path = Path("templates/_debt_maturity.html.j2")
    src = tmpl_path.read_text()
    banned = ["us-gaap", "LongTermDebtMaturities", "accn", "XBRL", "frame"]
    # split at the <details> boundary; everything before/around it minus the
    # details block itself must be free of raw machine vocabulary.
    m = re.search(r"<details.*?</details>", src, re.DOTALL)
    assert m, "expected a <details> disclosure block"
    outside = src[: m.start()] + src[m.end():]
    for term in banned:
        assert term not in outside, f"banned term {term!r} leaked outside <details>"
    inside = m.group(0)
    # the banned vocabulary should actually be reachable inside the details
    assert "accn" in inside


def test_en_zh_parity():
    src = Path("templates/_debt_maturity.html.j2").read_text()
    calls = re.findall(r"\bt\(([^()]*(?:\([^()]*\)[^()]*)*)\)", src)
    assert calls, "expected t() calls in the partial"
    for args in calls:
        # split on the top-level comma (args may themselves contain '~' concatenation
        # but never nested parens at this point since the regex already balanced those)
        depth = 0
        top_commas = 0
        for ch in args:
            if ch in "([":
                depth += 1
            elif ch in ")]":
                depth -= 1
            elif ch == "," and depth == 0:
                top_commas += 1
        assert top_commas >= 1, f"t() call missing a zh arg: {args!r}"


def test_no_translated_title_attribute():
    src = Path("templates/_debt_maturity.html.j2").read_text()
    assert "title=" not in src


def test_stock_page_wiring():
    ticker_tmpl = Path("templates/ticker.html.j2").read_text()
    assert '{% include "_debt_maturity.html.j2" %}' in ticker_tmpl
    assert 'id="debt-maturity"' in Path("templates/_debt_maturity.html.j2").read_text()
    assert '#debt-maturity' in ticker_tmpl
    build_pages_src = Path("scripts/build_ticker_pages.py").read_text()
    assert '"debt_maturity"' in build_pages_src


def test_sections_gate_ignores_null_panel():
    import scripts.build_ticker_pages as btp

    # use a non-empty base blob (any truthy blob already contributes its own
    # +1 in sections_available) so the debt_maturity-specific delta is isolated
    agg = {"intel_map": {}, "news_map": {}}
    base_blob = {"_marker": True}
    base = btp.sections_available(base_blob, {}, agg, "TEST")

    for status in ("no_filings", "no_maturity_facts", "not_applicable"):
        blob = dict(base_blob, debt_maturity={"status": status})
        with_null = btp.sections_available(blob, {}, agg, "TEST")
        assert with_null == base, f"status={status} unexpectedly added to the gate"

    reported_blob = dict(base_blob, debt_maturity={"status": "reported"})
    with_reported = btp.sections_available(reported_blob, {}, agg, "TEST")
    assert with_reported == base + 1
