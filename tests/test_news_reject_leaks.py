"""Phase-0 news-intelligence upgrade — regression tests for the verified filter
leaks the theme/entity gates let through on the live macro feed.

The DROP cases are the exact garbage headlines flagged in the news-intelligence
upgrade review; the KEEP cases are the real stories each reject family resembles
and must NOT swallow (the false-positive guard that makes the rules safe to ship).
"""
import pytest

from engine import news_common as nc


# (title, expected reject-reason token)
DROP_CASES = [
    ("Here's what's worth streaming in July 2026 on Netflix, Hulu, HBO Max and more",
     "lifestyle_content"),
    ("Nuveen Real Asset Income and Growth Fund declares $0.1335 dividend",
     "routine_fund_distribution"),
    ("What You Need To Know Ahead of Cincinnati Financial's Earnings Release",
     "calendar_preview"),
    ("At 76, I'm working at Walmart. Why do I still owe payroll taxes?",
     "personal_finance_advice"),
    ("‘I claimed Social Security at 62’: At 76, I'm working at Walmart. "
     "Why do I still owe payroll taxes?",
     "personal_finance_advice"),
]

# Real stories the reject families must leave alone.
KEEP_CASES = [
    "Company cuts full-year revenue guidance as orders slow",
    "Defense contractor wins $2.4B Navy contract",
    "Apple raises quarterly dividend 4%, announces $110B buyback",
    "Social Security trust fund projected to deplete by 2033, trustees say",
    "Netflix raises streaming prices across US plans",
    "Micron's earnings are a must-watch event this week",
]


@pytest.mark.parametrize("title,reason", DROP_CASES)
def test_garbage_is_rejected_with_reason(title, reason):
    assert nc.is_low_value(title) is True, f"leaked: {title!r}"
    assert nc.low_value_reason(title) == reason, (
        f"{title!r} -> {nc.low_value_reason(title)!r}, expected {reason!r}")


@pytest.mark.parametrize("title", KEEP_CASES)
def test_real_news_survives(title):
    assert nc.is_low_value(title) is False, (
        f"false-positive drop ({nc.low_value_reason(title)}): {title!r}")


def test_macro_release_stub_is_a_known_gap():
    """Bare official-release titles ('Manufacturing and Trade Inventories and
    Sales') still leak the title-only gate — suppressing them needs release-registry
    context (Fable phase 2: macro-surprise parser), NOT a generic title regex.
    Documented here so the boundary is explicit and does not silently regress."""
    assert nc.low_value_reason("Manufacturing and Trade Inventories and Sales") is None
