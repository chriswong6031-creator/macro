"""Regression guards for the reports archive typography and timeline rail."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "reports.html.j2"
PUBLISHED = ROOT / "site" / "reports.html"


def test_reports_page_uses_san_francisco_with_inter_fallback() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")

    assert "-apple-system,BlinkMacSystemFont" in source
    assert '"SF Pro Text","SF Pro Display",Inter' in source
    assert "--rc-display:" in source
    assert "--rc-serif:" not in source
    assert "Georgia" not in source


def test_timeline_date_and_marker_occupy_separate_grid_columns() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")
    compact = re.sub(r"\s+", " ", source)

    assert '<time class="rc-date" datetime="{{ r.date }}">' in source
    assert ".rc-date{ grid-column:1; grid-row:1;" in compact
    assert (
        ".rc-rail .dot{ grid-column:2; grid-row:1; position:relative;"
        in compact
    )
    assert ".rc-rail .dot{ position:absolute;" not in compact


def test_published_reports_stylesheet_hash_matches_its_contents() -> None:
    html = PUBLISHED.read_text(encoding="utf-8")
    match = re.search(
        r'href="assets/css/([0-9a-f]{8})\.css\?v=\1"',
        html,
    )

    assert match, "reports.html must reference a content-hashed stylesheet"
    css = ROOT / "site" / "assets" / "css" / f"{match.group(1)}.css"
    assert css.exists()
    assert hashlib.sha256(css.read_bytes()).hexdigest().startswith(match.group(1))

    published_css = re.sub(r"\s+", " ", css.read_text(encoding="utf-8"))
    assert '"SF Pro Text","SF Pro Display",Inter' in published_css
    assert ".rc-date{ grid-column:1; grid-row:1;" in published_css
    assert (
        ".rc-rail .dot{ grid-column:2; grid-row:1; position:relative;"
        in published_css
    )
    assert html.count('<time class="rc-date" datetime="') == 6
