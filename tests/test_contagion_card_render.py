"""tests/test_contagion_card_render.py — end-to-end render tests for the
contagion pressure strip in the shared risk-radar card template.

Verifies that the CGL W1 wiring fix (post-transform rd.contagion attachment)
actually fires in _risk_radar_card.html.j2 for three market families:

  1. cn/hk/ca family — rd.contagion path (Path A: rd.contagion set directly)
  2. us family       — same path (build_site.py already attaches post-transform;
                       tested here as a positive control)
  3. intl / no-contagion — strip absent when neither path fires

All inputs are SYNTHETIC — no live data/ or site/ writes (MM_DATA_GUARD compliant).
Template rendering is via jinja2 direct module call (same idiom as
tests/test_rr_scorecard_card.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TEMPLATES = ROOT / "templates"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _jinja_env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES)))
    env.globals["zip"] = zip
    return env


def _minimal_pressure_block(level: str = "moderate") -> dict:
    """Minimal contagion_links.v1 pressure block (schema from engine/contagion_links.py)."""
    return {
        "raw": 0.42,
        "pct": 0.71,
        "level": level,          # "low" | "moderate" | "high"
        "line_en": f"Contagion pressure {level}",
        "line_zh": f"传导压力{level}",
        "top_exporters": [
            {
                "market": "us",
                "name_en": "United States",
                "name_zh": "美国",
                "weight": 0.38,
                "contribution": 0.16,
                "dd21": -0.06,
                "ret10": -0.04,
            }
        ],
        "shadow_state": "caution",
        "incumbent_state": "watch",
        "incumbent_as_of": "2026-07-16",
    }


def _minimal_rd(contagion=None) -> dict:
    """Minimal post-transform rd dict matching _radar_to_rd() output schema."""
    rd = {
        "state": "caution",
        "top_score": 72,
        "label_en": "credit",
        "label_zh": "信用",
        "state_zh": "谨慎",
        "do_en": "Trim risk.",
        "do_zh": "降低风险。",
        "gross": None,
        "dd5": 0.08,
        "dd10": 0.14,
        "dd21": 0.28,
        "dd_lift": 1.6,
        "dd_base": {"h5": 0.036, "h10": 0.086, "h21": 0.178},
        "is_loud": True,
        "scares": [],
        "forward_log": None,
        "cycle": None,
        "counterread": None,
        "amp": 0,
        "amp_keys": [],
        "amp_flags_en": [],
        "amp_flags_zh": [],
        "severe_gated": False,
        "ceiling": None,
        "recovery": None,
        "track": None,
    }
    if contagion is not None:
        rd["contagion"] = contagion
    return rd


# Marker text that appears in the contagion strip when it renders.
# From _risk_radar_card.html.j2: the strip uses class "rrx-cgl" or similar.
# We assert on the pressure level word which always appears when _cgl_blk is set.
_STRIP_MARKERS = ("Building", "Low", "High", "传导")


def _strip_present(html: str) -> bool:
    return any(m in html for m in _STRIP_MARKERS) and "rrx-cgl" in html


def _strip_absent(html: str) -> bool:
    return "rrx-cgl" not in html


# ---------------------------------------------------------------------------
# 1. CN/HK/CA family: rd.contagion path (Path A)
# ---------------------------------------------------------------------------

def test_cn_family_strip_renders_with_rd_contagion():
    """When rd.contagion is set (post-transform attachment), the strip renders."""
    env = _jinja_env()
    tmpl = env.get_template("_risk_radar_card.html.j2")
    rd = _minimal_rd(contagion=_minimal_pressure_block("moderate"))
    html = tmpl.module.risk_radar_card(rd, [])
    assert _strip_present(html), (
        "Contagion strip did not render — rd.contagion was set but 'rrx-cgl' absent from output.\n"
        f"Output snippet: {html[:500]}"
    )


def test_cn_family_strip_absent_without_contagion():
    """When rd.contagion is absent and CGL is not in context, the strip is silent."""
    env = _jinja_env()
    tmpl = env.get_template("_risk_radar_card.html.j2")
    rd = _minimal_rd()   # no 'contagion' key
    html = tmpl.module.risk_radar_card(rd, [])
    assert _strip_absent(html), (
        "Contagion strip unexpectedly rendered without rd.contagion or CGL.\n"
        f"Output snippet: {html[:500]}"
    )


def test_cn_family_strip_renders_high_level():
    """High-pressure block renders — level=high uses 'warn' chip class."""
    env = _jinja_env()
    tmpl = env.get_template("_risk_radar_card.html.j2")
    rd = _minimal_rd(contagion=_minimal_pressure_block("high"))
    html = tmpl.module.risk_radar_card(rd, [])
    assert "High" in html or "高" in html, "Level 'high' glance word absent"
    assert _strip_present(html)


def test_cn_family_strip_renders_low_level():
    """Low-pressure block renders — level=low uses 'ok' chip class."""
    env = _jinja_env()
    tmpl = env.get_template("_risk_radar_card.html.j2")
    rd = _minimal_rd(contagion=_minimal_pressure_block("low"))
    html = tmpl.module.risk_radar_card(rd, [])
    assert "Low" in html or "低" in html, "Level 'low' glance word absent"
    assert _strip_present(html)


# ---------------------------------------------------------------------------
# 2. US family: same rd.contagion path (positive control — build_site.py already works)
# ---------------------------------------------------------------------------

def test_us_family_strip_renders_with_rd_contagion():
    """US market: rd.contagion (same key, different pressure block) fires the strip."""
    env = _jinja_env()
    tmpl = env.get_template("_risk_radar_card.html.j2")
    us_pressure = _minimal_pressure_block("moderate")
    us_pressure["top_exporters"][0]["market"] = "kr"
    us_pressure["top_exporters"][0]["name_en"] = "South Korea"
    rd = _minimal_rd(contagion=us_pressure)
    html = tmpl.module.risk_radar_card(rd, [])
    assert _strip_present(html), "US contagion strip not rendered"


# ---------------------------------------------------------------------------
# 3. (Path B removed — FIX 3: dead path, rd.market never set by _radar_to_rd)
# CGL context passes remain in builders for the intl.html.j2 directed table.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 4. Byte-identical-to-no-strip when contagion absent
# ---------------------------------------------------------------------------

def test_strip_absent_output_byte_identical_across_calls():
    """Two renders without contagion produce identical HTML (idempotency guard)."""
    env = _jinja_env()
    tmpl = env.get_template("_risk_radar_card.html.j2")
    rd = _minimal_rd()
    html1 = tmpl.module.risk_radar_card(rd, [])
    html2 = tmpl.module.risk_radar_card(rd, [])
    assert html1 == html2


def test_strip_adds_content_relative_to_baseline():
    """A render WITH contagion differs from one WITHOUT (the strip is non-empty)."""
    env = _jinja_env()
    tmpl = env.get_template("_risk_radar_card.html.j2")
    rd_base = _minimal_rd()
    rd_with = _minimal_rd(contagion=_minimal_pressure_block("moderate"))
    html_base = tmpl.module.risk_radar_card(rd_base, [])
    html_with = tmpl.module.risk_radar_card(rd_with, [])
    assert html_with != html_base, "Contagion strip added no new bytes — wiring is still a no-op"
    assert len(html_with) > len(html_base), "Contagion strip should add content"


# ---------------------------------------------------------------------------
# FIX 2: Stale disclosure renders when blk["stale"]=True
# ---------------------------------------------------------------------------

def test_stale_disclosure_renders_when_stale_flag_set():
    """When blk["stale"]=True and built_date is set, the 'as of YYYY-MM-DD' token renders."""
    env = _jinja_env()
    tmpl = env.get_template("_risk_radar_card.html.j2")
    blk = _minimal_pressure_block("moderate")
    blk["stale"] = True
    blk["built_date"] = "2026-07-16"
    rd = _minimal_rd(contagion=blk)
    html = tmpl.module.risk_radar_card(rd, [])
    assert "2026-07-16" in html, (
        "Stale disclosure date '2026-07-16' missing from rendered HTML when stale=True"
    )
    assert "as of" in html or "截至" in html, (
        "Stale disclosure prefix ('as of' or '截至') missing when stale=True"
    )


def test_stale_disclosure_absent_when_not_stale():
    """When blk does not have stale=True, no stale disclosure is rendered."""
    env = _jinja_env()
    tmpl = env.get_template("_risk_radar_card.html.j2")
    blk = _minimal_pressure_block("moderate")
    # no stale key set
    rd = _minimal_rd(contagion=blk)
    html = tmpl.module.risk_radar_card(rd, [])
    assert "as of 20" not in html, (
        "Stale disclosure 'as of YYYY-...' present in HTML even though stale=False"
    )
