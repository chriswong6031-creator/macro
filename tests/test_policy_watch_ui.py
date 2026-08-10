from __future__ import annotations

import re
from pathlib import Path

from scripts.build_policy_watch import _featured_predictions, brief, source_label


ROOT = Path(__file__).resolve().parent.parent


def test_policy_watch_glance_helpers_are_plain_and_deterministic():
    long = "One useful sentence that already says what matters. " + "Detail " * 60
    assert brief(long, 90) == "One useful sentence that already says what matters."
    assert brief("A" * 200, 40) == "A" * 40 + "…"
    assert source_label("https://www.federalreserve.gov/newsevents.htm") == "Federal Reserve"
    assert source_label("https://example.com/policy") == "example.com"


def test_featured_calls_put_needs_review_first():
    calls = [
        {"id": "P1", "status": "open", "check_by": "2026-12-31"},
        {"id": "P2", "status": "hit", "check_by": "2026-06-01"},
        {"id": "P3", "status": "open", "check_by": "2026-07-01"},
    ]
    dates = {"predictions": {"P1": {"overdue": False}, "P2": {"overdue": False}, "P3": {"overdue": True}}}
    rows = _featured_predictions(calls, dates, limit=3)
    assert [row["id"] for row in rows] == ["P3", "P1", "P2"]
    assert rows[0]["needs_review"] is True


def test_broken_ceasefire_call_is_forced_into_review():
    rows = _featured_predictions(
        [{"id": "P44", "status": "open", "check_by": "2026-08-31"}],
        {"predictions": {"P44": {"overdue": False}}},
    )
    assert rows[0]["needs_review"] is True


def test_policy_watch_template_uses_macro_ui_roles_and_plain_labels():
    template = (ROOT / "templates" / "policy_watch.html.j2").read_text(encoding="utf-8")

    for weight in (500, 600, 700):
        assert f'src:url("/fonts/InterDisplay-{weight}.woff2")' in template
    assert "font-family:var(--font-ui)" in template
    assert "font-family:var(--font-display)" in template
    assert "max-width:1500px" in template
    assert "gbtn gbtn-sm" in template
    assert "grid-template-columns:1fr" in template
    assert "overflow-wrap:anywhere" in template

    for old_copy in (
        "Intent Desk",
        "Realpolitik",
        "accountability spine",
        "Read the full thesis",
        "model key",
        "Catalyst spine",
    ):
        assert old_copy not in template

    for new_copy in (
        "What matters now",
        "Fed changes to watch",
        "White House & Treasury",
        "Where policy may help or hurt",
        "Calls and results",
        "See all calls",
    ):
        assert new_copy in template


def test_generated_policy_watch_links_resolvable_page_css():
    page = (ROOT / "site" / "policy_watch.html").read_text(encoding="utf-8")
    match = re.search(r'href="assets/css/([0-9a-f]{8})\.css\?v=\1"', page)
    assert match, "policy_watch.html must link its content-hashed page stylesheet"
    css = (ROOT / "site" / "assets" / "css" / f"{match.group(1)}.css").read_text(encoding="utf-8")

    assert 'url("/fonts/InterDisplay-600.woff2")' in css
    assert 'url("fonts/InterDisplay-600.woff2")' not in css
    assert "The policy moves that matter for markets. Last verified" in page
    assert "See all calls" in page
    assert "Under review after the ceasefire collapsed" in page
    assert "READ BEING UPDATED" not in page
    assert "What policymakers do, not what they say" not in page
    assert "Miran role: authored before CEA/Fed tenure" not in page
    assert "[1]" not in page
