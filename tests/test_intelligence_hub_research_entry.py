"""tests/test_intelligence_hub_research_entry.py — A-F10-1 entry point.

Packet A-F10-1 wires the Research Implication cards (measurement.html
`#ric-section`) into the one place a research reader would look for them: the
"Track record" band on `intelligence_hub.html`.

These tests pin the TEMPLATES (not committed site/ pages). Render-lane output
is owned by the bot; sparse worktrees omit site/; asserting against site/
would red on every sparse checkout and pin bot stamps nobody in this packet
controls.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HUB_TMPL = REPO / "templates" / "intelligence_hub.html.j2"
MEASUREMENT_TMPL = REPO / "templates" / "measurement.html.j2"


def _read(path: Path) -> str:
    assert path.exists(), f"missing template: {path}"
    return path.read_text(encoding="utf-8")


def test_hub_template_links_to_research_implications_anchor():
    hub = _read(HUB_TMPL)
    hrefs = re.findall(r'href="measurement\.html#ric-section"', hub)
    assert len(hrefs) == 1, f"expected exactly one entry link, found {len(hrefs)}"


def test_measurement_template_defines_ric_section_anchor():
    measurement = _read(MEASUREMENT_TMPL)
    assert 'id="ric-section"' in measurement, (
        "measurement template has no #ric-section — the hub's entry link would be dead"
    )


def test_hub_entry_is_bilingual_in_template():
    hub = _read(HUB_TMPL)
    m = re.search(r'<a class="card rid"[^>]*>(.*?)</a>', hub, flags=re.DOTALL)
    assert m, "no .rid entry row found in the hub template"
    row = m.group(1)
    spans = re.findall(
        r'class="(rid-k|rid-t|rid-d)">'
        r'<span class="l-en">(.*?)</span><span class="l-zh">(.*?)</span>',
        row,
        flags=re.DOTALL,
    )
    assert len(spans) == 3, f"expected rid-k/rid-t/rid-d bilingual spans, got {spans!r}"
    for _cls, en, zh in spans:
        assert en.strip(), "empty EN span in the hub entry row"
        assert zh.strip(), "empty ZH span in the hub entry row"
        assert re.search(r"[一-鿿]", zh), f"ZH span has no Chinese: {zh!r}"


def test_hub_entry_lives_inside_existing_track_record_band():
    """Entry must not mint a new top-level L1 band (MPDS budget)."""
    hub = _read(HUB_TMPL)
    # Locate the Track-record band heading, then the rid link, then the next band.
    tr = re.search(
        r'<div class="band"[^>]*>.*?Track record.*?</div>(.*?)(?=<div class="band"|$)',
        hub,
        flags=re.DOTALL,
    )
    assert tr, "Track record band not found"
    band_body = tr.group(1)
    assert 'class="card rid"' in band_body, (
        "research-implications entry must live inside the Track-record band body"
    )
    # The rid link must appear BEFORE the next band opener that follows Track record.
    rid_pos = hub.find('class="card rid"')
    # Count bands: entry must not increase L1 band count vs a tree without the rid
    # (we only assert the rid is not wrapped in its own .band).
    before_rid = hub[:rid_pos]
    after_open = before_rid.rfind('<div class="band"')
    assert after_open != -1
    # Between that band open and the rid there should be no NEW band open for the rid.
    window = hub[after_open:rid_pos]
    assert window.count('<div class="band"') == 1


def test_hub_template_uses_only_the_authenticated_nav_family():
    hub = _read(HUB_TMPL)
    assert '_site_nav.html.j2' in hub
    assert "_public_nav" not in hub
    assert "_public_chrome" not in hub
