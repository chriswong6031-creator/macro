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
        "Stages, dated and sourced",
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


def _render_policy_watch_with_lifecycle(lifecycle_fixture, monkeypatch, tmp_path):
    """Renders the REAL page via scripts.build_policy_watch.main(), monkeypatching only
    the lifecycle view so every other context var (intel, dates, fed_stance, ...) is the
    real production shape — avoids re-guessing the whole context surface."""
    import scripts.build_policy_watch as bpw
    from engine import policy_intent_desk as _pid

    monkeypatch.setattr(_pid, "lifecycle_view", lambda root=None: lifecycle_fixture)
    monkeypatch.setattr(_pid, "ingest_lifecycle", lambda root=None: 0)

    captured = {}

    def _fake_write_page(path, html):
        captured["html"] = html

    monkeypatch.setattr(bpw, "write_page", _fake_write_page)
    bpw.main()
    assert "html" in captured, "build_policy_watch.main() did not render policy_watch"
    return captured["html"]


LIFECYCLE_FIXTURE = {
    "schema": "policy_lifecycle.v1", "as_of": "2026-09-01", "null_reason": None,
    "counts": {"proposed": 1, "passed": 0, "in_force": 1, "enforced": 0, "other": 0, "unknown": 1},
    "items": [
        {"id": "L1", "title_en": "Lever One", "title_zh": "杠杆一",
         "jurisdiction": "US-FED", "jurisdiction_en": "United States — federal", "jurisdiction_zh": "美国联邦",
         "state": "in_force", "stage_rank": 2, "reached": ["proposed", "passed", "in_force"], "gaps": [],
         "basis": "FACT", "detail_en": "Dated move.", "detail_zh": "已落地。",
         "state_asof": "2026-03-01", "known_at": "2026-03-02T00:00:00Z",
         "source": {"url": "https://www.federalregister.gov/x", "label": "Federal Register", "title": "doc", "doc_id": "1"},
         "next_step": {"stage": "enforced", "date": None},
         "stalled": False, "corrected": False, "conflict": False, "why": None},
        {"id": "L2", "title_en": "Lever Two", "title_zh": "杠杆二",
         "jurisdiction": "US-FED", "jurisdiction_en": "United States — federal", "jurisdiction_zh": "美国联邦",
         "state": "proposed", "stage_rank": 0, "reached": ["proposed"], "gaps": [],
         "state_asof": "2026-01-01", "known_at": "2026-01-02T00:00:00Z",
         "source": {"url": "https://www.federalregister.gov/y", "label": "Federal Register", "title": "doc", "doc_id": "2"},
         "next_step": {"stage": "passed", "date": None},
         "stalled": False, "corrected": False, "conflict": False, "why": None},
        {"id": "L3", "title_en": "Lever Three", "title_zh": "杠杆三",
         "jurisdiction": None, "jurisdiction_en": None, "jurisdiction_zh": None,
         "state": "unknown", "stage_rank": None, "reached": [], "gaps": [],
         "state_asof": None, "known_at": None, "source": None,
         "next_step": None, "stalled": False, "corrected": False, "conflict": False, "why": "no_document"},
    ],
}


def test_every_lifecycle_row_carries_state_asof_and_source(monkeypatch, tmp_path):
    html = _render_policy_watch_with_lifecycle(LIFECYCLE_FIXTURE, monkeypatch, tmp_path)
    assert html.count("pw-stage-asof") >= 2  # both dated items
    assert 'href="https://www.federalregister.gov/x"' in html
    assert 'href="https://www.federalregister.gov/y"' in html
    assert "Not tracked yet" in html  # unknown item's typed badge


def test_lifecycle_markup_carries_no_machine_state_names(monkeypatch, tmp_path):
    html = _render_policy_watch_with_lifecycle(LIFECYCLE_FIXTURE, monkeypatch, tmp_path)
    text_only = re.sub(r"<[^>]+>", " ", html)
    for token in ("in_force", "no_document", "struck_down"):
        assert token not in text_only, f"machine token {token!r} leaked into visible text"


def test_lifecycle_strings_are_bilingual_and_never_in_title_attr(monkeypatch, tmp_path):
    html = _render_policy_watch_with_lifecycle(LIFECYCLE_FIXTURE, monkeypatch, tmp_path)
    assert "Not tracked yet" in html and "尚未跟踪" in html
    assert "In force" in html and "已生效" in html
    for m in re.finditer(r'title="([^"]*)"', html):
        assert not any("\u4e00" <= ch <= "\u9fff" for ch in m.group(1)), "CJK found in a title= attribute"


def test_light_mode_changes_the_mechanism_not_only_the_token():
    template = (ROOT / "templates" / "policy_watch.html.j2").read_text(encoding="utf-8")
    m = re.search(r'html\[data-theme="light"\]\s*\.pw-stage-seg\.is-current\{([^}]*)\}', template)
    assert m, "light current-segment rule missing"
    assert "box-shadow:none" in m.group(1)
    assert "outline:" in m.group(1)
    m2 = re.search(r'html\[data-theme="light"\]\s*\.pw-stage\.is-stalled\{([^}]*)\}', template)
    assert m2, "light stalled rule missing"
    assert "border-left" in m2.group(1)


def test_policy_watch_l1_section_count_is_unchanged():
    template = (ROOT / "templates" / "policy_watch.html.j2").read_text(encoding="utf-8")
    assert template.count('<section class="pw-section"') == 7
