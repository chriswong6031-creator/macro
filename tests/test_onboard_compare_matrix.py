"""The in-sheet compare panel may never claim a feature the pricing page doesn't.

`templates/onboard.js` carries its own COMPARE table because the onboarding sheet
is site-wide: it opens over macro pages that never load the landing's
`#pricing-matrix`. Two hand-authored copies of the same truth is exactly how a
plan page and a checkout drift apart, so this pins them:

  * every feature row in the sheet exists, verbatim, in the landing table
  * the sheet's group headings are the landing's group headings
  * neither side quietly grows a row the other never heard of

If you add a feature, add it to BOTH `templates/index.html` and the COMPARE table
in `templates/onboard.js` (and re-run `python -m scripts.check_template_site_sync
--fix` so the site/ copies follow).
"""
from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANDING = ROOT / "templates" / "index.html"
ONBOARD = ROOT / "templates" / "onboard.js"


def _landing_matrix() -> tuple[list[str], list[str]]:
    """(group headings, feature labels) from the landing's #pricing-matrix."""
    src = LANDING.read_text(encoding="utf-8")
    m = re.search(r'<table class="mx" id="pricing-matrix".*?</table>', src, re.S)
    assert m, "landing lost its #pricing-matrix table"
    table = m.group(0)

    groups = [
        html.unescape(g).strip()
        for g in re.findall(r'<tr class="grp"><td colspan="4"[^>]*>(.*?)</td>', table, re.S)
    ]
    feats = [
        html.unescape(f).strip()
        for f in re.findall(r'<span class="ft"[^>]*>(.*?)</span>', table, re.S)
    ]
    return groups, feats


def _sheet_matrix() -> tuple[list[str], list[str]]:
    """(group headings, feature labels) from the COMPARE table in onboard.js."""
    src = ONBOARD.read_text(encoding="utf-8")
    m = re.search(r"var COMPARE = \[(.*?)\n  \];", src, re.S)
    assert m, "onboard.js lost its COMPARE table"
    block = m.group(1)

    groups = [g for g in re.findall(r'\{ g: \["([^"]+)"', block)]
    feats = [f for f in re.findall(r'\{ l: \["([^"]+)"', block)]
    return groups, feats


def test_every_sheet_feature_exists_on_the_pricing_page():
    _, landing = _landing_matrix()
    _, sheet = _sheet_matrix()
    unknown = [f for f in sheet if f not in landing]
    assert not unknown, (
        "the compare panel claims features the pricing page does not list: "
        f"{unknown}. Add them to templates/index.html or drop them from COMPARE."
    )


def test_no_pricing_page_feature_is_missing_from_the_sheet():
    _, landing = _landing_matrix()
    _, sheet = _sheet_matrix()
    missing = [f for f in landing if f not in sheet]
    assert not missing, (
        "the pricing page lists features the compare panel omits: "
        f"{missing}. 'Compare every feature' has to mean every feature."
    )


def test_group_headings_match():
    landing_groups, _ = _landing_matrix()
    sheet_groups, _ = _sheet_matrix()
    assert sheet_groups == landing_groups, (
        f"compare-panel groups {sheet_groups} != pricing-page groups {landing_groups}"
    )


def test_row_counts_line_up():
    _, landing = _landing_matrix()
    _, sheet = _sheet_matrix()
    assert len(sheet) == len(landing) == len(set(sheet)), (
        f"row counts drifted — sheet {len(sheet)}, landing {len(landing)}"
    )
