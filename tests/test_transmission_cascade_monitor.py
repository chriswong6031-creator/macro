"""tests/test_transmission_cascade_monitor.py — TXI W4 Cascade Monitor render (deliverable D).

Renders templates/transmission.html.j2 with the chain-state fixture subset and asserts the
Cascade Monitor section:
  - renders one row per non-dormant chain, ordered expressed → propagating → arming
  - shows hop-progress dots + the "N of M links confirmed" line + the tier disclosure
  - dormant chains collapse to a single muted "Quiet:" line
  - receipts ride data-tip-en/zh, never title=; the word "validated" never appears
  - the whole section is baked CONDITIONALLY: absent/empty chains → it does not render
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "transmission" / "chain_state.json"
TEMPLATES = Path(__file__).resolve().parents[1] / "templates"

_C = {"blue": "#285FFF", "indigo": "#4559DC", "ink": "#0B1733", "text": "#344054",
      "muted": "#6F6F6F", "faint": "#A0A0A0", "red": "#D30B0B", "amber": "#F5AD42",
      "green": "#1a7f43", "grid": "#EAECF0", "card": "#FFFFFF", "bg": "#F7F8FA",
      "gold": "#C8A53B", "teal": "#1F8A70"}


class _NoneDict(dict):
    """Returns None for any missing attr/key (lets the unrelated page sections render
    with all-None fields instead of raising, so we can exercise the monitor in isolation)."""
    def __getattr__(self, k):
        return self.get(k)

    def __getitem__(self, k):
        return dict.get(self, k, None)


def _nd(**kw):
    return _NoneDict(**kw)


def _render(chains):
    pytest.importorskip("jinja2")
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=True)
    S = _nd(rates=_nd(direction="stable", regime="neutral"),
            inflation=_nd(direction="steady"), expectations=_nd(anchoring="anchored"))
    tx = _nd(state=S, chains=[], scenarios=[], headwinds=[], tailwinds=[], transmission={},
             caveats=[], scored_status=_nd(en="x", zh="x"),
             inflation_decomposition=_nd(), breakeven_decomp=None)
    return env.get_template("transmission.html.j2").render(
        C=_C, as_of="2026-07-24", built="x", span="x", tx=tx, gate={}, yc=None,
        dx=None, hero=None, changes=None, chains=chains)


def _subset():
    from engine.transmission_publish import derive_display_subset
    return derive_display_subset(json.loads(FIX.read_text(encoding="utf-8")))


def _monitor_segment(html: str) -> str:
    i = html.find("<!-- ===================== CASCADE MONITOR")
    assert i >= 0, "cascade monitor section marker not found"
    j = html.find("===================== SCENARIOS", i)
    return html[i:j]


def test_monitor_renders_rows_in_progress_order():
    html = _render(_subset())
    seg = _monitor_segment(html)
    import re
    tags = re.findall(r'cm-state-tag (\w+)"', seg)
    assert tags == ["expressed", "propagating", "arming"], tags
    assert seg.count('class="cm-row') == 3


def test_monitor_shows_links_line_and_tier_disclosure():
    seg = _monitor_segment(_render(_subset()))
    assert "links confirmed" in seg
    assert "blast radius" in seg
    assert "base rates accrue nightly" in seg          # tier honesty
    assert "早期监测——基准率逐夜累积" in seg          # zh tier honesty


def test_monitor_dormant_collapses_to_quiet_line():
    seg = _monitor_segment(_render(_subset()))
    assert seg.count("cm-quiet") == 1
    assert "Vol-regime shift" in seg   # the dormant chain name in the quiet line


def test_monitor_receipts_use_data_tip_not_title():
    seg = _monitor_segment(_render(_subset()))
    assert "data-tip-en=" in seg and "data-tip-zh=" in seg
    assert "title=" not in seg, "receipts must ride data-tip-*, never title="


def test_monitor_no_validated_claim():
    html = _render(_subset())
    assert "validated" not in html.lower()


def test_monitor_absent_when_chains_none():
    html = _render(None)
    # the section markup (eyebrow) must not render; only the CSS comment mentions it
    assert '<p class="cm-eyebrow">' not in html


def test_monitor_absent_when_no_chains_list():
    html = _render({"schema": "x", "chains": []})
    assert '<p class="cm-eyebrow">' not in html
